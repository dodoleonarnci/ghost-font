"""Top-level encoders: the original Ghost Font and the key-encrypted variant.

The keyed encoder combines Approach 1 (key-derived per-band velocity
scrambling) and Approach 4 (steganographic embedding of the encrypted band
table), the combination recommended in the design plan.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import crypto
from .config import GhostFontConfig
from .kinematogram import (
    build_velocity_model_keyed,
    build_velocity_model_original,
    render_video,
)
from .raster import rasterize_glyphs, rasterize_multiline


@dataclass
class EncodeResult:
    frames: np.ndarray  # (N, H, W) float32 in [0,1]
    mask: np.ndarray  # (H, W) bool ground-truth letter mask
    decoy_mask: np.ndarray  # (H, W) bool
    # keyed-only extras:
    band_speeds: np.ndarray | None = None
    band_signs: np.ndarray | None = None


def _build_masks(cfg: GhostFontConfig):
    c = cfg.canvas
    mask = rasterize_glyphs(
        cfg.message, c.width, c.height, c.font_path, c.text_width_frac
    )
    decoy_size = int(c.height * cfg.decoy.font_size_frac)
    decoy_mask = rasterize_multiline(
        cfg.decoy.text, c.width, c.height, c.decoy_font_path, decoy_size
    )
    return mask, decoy_mask.astype(np.float32)


def encode_original(cfg: GhostFontConfig) -> EncodeResult:
    """Original Ghost Font: single global upward/downward velocity split."""
    mask, decoy = _build_masks(cfg)
    vmodel = build_velocity_model_original(cfg)
    frames = render_video(cfg, mask, vmodel, decoy)
    return EncodeResult(frames=frames, mask=mask, decoy_mask=decoy > 0)


def derive_band_table(cfg: GhostFontConfig, key: bytes):
    """Approach 1 key expansion: per-band speed + direction from PRF_K."""
    k = cfg.keyed
    b = k.n_bands
    u = np.array([crypto.prf_unit(key, i) for i in range(b)])
    speeds = k.v_min + (k.v_max - k.v_min) * u
    if k.use_direction_bit:
        signs = np.array(
            [1.0 if crypto.prf_bit(key, b + i) else -1.0 for i in range(b)]
        )
    else:
        signs = np.ones(b)
    # Round-trip through the on-the-wire quantization so the encoder and a
    # keyed decoder agree bit-for-bit on the band table.
    blob = crypto.serialize_band_table(speeds, signs)
    return crypto.deserialize_band_table(blob)


def encode_keyed(cfg: GhostFontConfig, key: bytes) -> EncodeResult:
    """Key-encrypted Ghost Font (Approach 1 + Approach 4)."""
    mask, decoy = _build_masks(cfg)
    band_speeds, band_signs = derive_band_table(cfg, key)
    vmodel = build_velocity_model_keyed(cfg, band_speeds, band_signs)
    frames = render_video(cfg, mask, vmodel, decoy)
    return EncodeResult(
        frames=frames,
        mask=mask,
        decoy_mask=decoy > 0,
        band_speeds=band_speeds,
        band_signs=band_signs,
    )


def frames_to_rgb(frames: np.ndarray) -> np.ndarray:
    """Grayscale [0,1] -> uint8 RGB (N, H, W, 3)."""
    g = np.clip(frames * 255.0, 0, 255).astype(np.uint8)
    return np.repeat(g[..., None], 3, axis=-1)


def embed_key_payload(
    rgb_frames: np.ndarray, cfg: GhostFontConfig, key: bytes
) -> np.ndarray:
    """Approach 4: encrypt the band table and LSB-embed it in every frame's
    border strip, so the video is self-contained. Returns new RGB frames."""
    speeds, signs = derive_band_table(cfg, key)
    payload = crypto.serialize_band_table(speeds, signs)
    blob = crypto.encrypt(key, payload)
    k = cfg.keyed
    out = np.empty_like(rgb_frames)
    for i in range(len(rgb_frames)):
        out[i] = crypto.embed_lsb(
            rgb_frames[i], blob, k.stego_border_px, k.stego_channel
        )
    return out

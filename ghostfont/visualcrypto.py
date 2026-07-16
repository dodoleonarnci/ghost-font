"""Approach 3 — Visual Cryptography Ghost Font (Naor-Shamir / random grid).

The message mask is split into two shares such that neither reveals anything
alone, but their XOR reconstructs the message:

    share1               ~ Uniform  (independent of M)          -> in the VIDEO
    share2 = share1 XOR M ~ Uniform  (independent of M)          -> the KEY IMAGE
    share1 XOR share2     = M                                    -> the reveal

Share-1 is embedded as the *motion-defined form* of the kinematogram (each
coarse block scrolls up if its share-1 bit is 1, down if 0). Share-2 is the
static key image, AES-256-GCM-encrypted under K and distributed out-of-band.

Because share-1 is information-theoretically independent of M, a keyless
attacker who *perfectly* breaks the motion recovers only share-1 — pure noise,
zero information about the message. This is the only key-encrypted variant with
information-theoretic (not merely computational) security for the video alone.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

import cv2
import numpy as np

from . import crypto
from .config import GhostFontConfig
from .kinematogram import build_velocity_model_original, render_video
from .raster import rasterize_glyphs, rasterize_multiline


# ---------------------------------------------------------------------------
# Coarse grid helpers
# ---------------------------------------------------------------------------
def coarsen(mask: np.ndarray, block: int) -> np.ndarray:
    """Downsample a full-res binary mask to a coarse block grid (bool)."""
    H, W = mask.shape
    ch, cw = H // block, W // block
    m = mask[: ch * block, : cw * block].astype(np.float32)
    m = m.reshape(ch, block, cw, block).mean(axis=(1, 3))
    return m > 0.35


def upsample(coarse: np.ndarray, block: int, H: int, W: int) -> np.ndarray:
    up = np.repeat(np.repeat(coarse, block, axis=0), block, axis=1)
    full = np.zeros((H, W), dtype=coarse.dtype)
    hh, ww = min(H, up.shape[0]), min(W, up.shape[1])
    full[:hh, :ww] = up[:hh, :ww]
    return full


# ---------------------------------------------------------------------------
# Random-grid visual cryptography (2-out-of-2, pure XOR)
# ---------------------------------------------------------------------------
def vc_split(coarse_M: np.ndarray, rng: np.random.Generator):
    share1 = rng.integers(0, 2, size=coarse_M.shape).astype(np.uint8)
    share2 = (share1 ^ coarse_M.astype(np.uint8)).astype(np.uint8)
    return share1, share2


def vc_reveal_xor(share1: np.ndarray, share2: np.ndarray) -> np.ndarray:
    """Computational (client-side / AI) compositing: exact reconstruction."""
    return (share1 ^ share2).astype(np.uint8)


def vc_reveal_or(share1: np.ndarray, share2: np.ndarray) -> np.ndarray:
    """Physical transparency stacking: letter = 1, background ~ 50% (grey)."""
    return np.maximum(share1, share2).astype(np.uint8)


def pack_share(share: np.ndarray) -> bytes:
    h, w = share.shape
    return struct.pack(">HH", h, w) + np.packbits(share.ravel()).tobytes()


def unpack_share(data: bytes) -> np.ndarray:
    h, w = struct.unpack(">HH", data[:4])
    bits = np.unpackbits(np.frombuffer(data[4:], dtype=np.uint8))[: h * w]
    return bits.reshape(h, w).astype(np.uint8)


# ---------------------------------------------------------------------------
# Encoder
# ---------------------------------------------------------------------------
@dataclass
class VCResult:
    frames: np.ndarray          # (N,H,W) float32 video (carries share-1 motion)
    mask: np.ndarray            # full-res ground-truth message mask
    coarse_mask: np.ndarray     # coarse message (what the reveal should show)
    share1: np.ndarray          # coarse, in the video
    share2: np.ndarray          # coarse, the key image
    enc_share2: bytes           # AES-256-GCM(share2) under K (out-of-band)
    decoy_mask: np.ndarray
    block: int


def _build_masks(cfg: GhostFontConfig):
    c = cfg.canvas
    mask = rasterize_glyphs(cfg.message, c.width, c.height, c.font_path, c.text_width_frac)
    decoy_size = int(c.height * cfg.decoy.font_size_frac)
    decoy = rasterize_multiline(cfg.decoy.text, c.width, c.height, c.decoy_font_path, decoy_size)
    return mask, decoy.astype(np.float32)


def encode_visualcrypto(cfg: GhostFontConfig, key: bytes) -> VCResult:
    mask, decoy = _build_masks(cfg)
    block = cfg.vc.block_px
    rng = np.random.default_rng(cfg.motion.seed + 101)

    coarse_M = coarsen(mask, block)
    share1, share2 = vc_split(coarse_M, rng)

    # Share-1 becomes the motion-defined form: blocks with share1==1 scroll up.
    vc_mask = upsample(share1.astype(bool), block, cfg.canvas.height, cfg.canvas.width)
    vmodel = build_velocity_model_original(cfg)
    frames = render_video(cfg, vc_mask, vmodel, decoy)

    enc_share2 = crypto.encrypt(key, pack_share(share2))
    return VCResult(
        frames=frames, mask=mask, coarse_mask=coarse_M, share1=share1,
        share2=share2, enc_share2=enc_share2, decoy_mask=decoy > 0, block=block,
    )


# ---------------------------------------------------------------------------
# Decoder / attacks
# ---------------------------------------------------------------------------
def recover_share1(
    frames: np.ndarray, block: int, coarse_shape, speed: float
) -> np.ndarray:
    """Motion break: per-block dominant vertical direction -> share-1 estimate.

    Matched filter: for each consecutive frame pair, test whether the block
    moved up or down by the (public) inter-frame displacement and keep the
    better fit. Up-moving blocks were signal (share1==1). This is all a keyless
    attacker can extract from the video -- and by design it is pure noise."""
    f = frames
    N, H, W = f.shape
    err_up = np.zeros((H, W), dtype=np.float32)
    err_down = np.zeros((H, W), dtype=np.float32)
    for n in range(N - 1):
        d = int(round((n + 1) * speed) - round(n * speed))  # inter-frame shift
        a = f[n + 1]
        err_up += (a - np.roll(f[n], -d, axis=0)) ** 2       # moved up by d
        err_down += (a - np.roll(f[n], +d, axis=0)) ** 2     # moved down by d
    ch, cw = coarse_shape
    eu = err_up[: ch * block, : cw * block].reshape(ch, block, cw, block).sum(axis=(1, 3))
    ed = err_down[: ch * block, : cw * block].reshape(ch, block, cw, block).sum(axis=(1, 3))
    return (eu < ed).astype(np.uint8)


def recover_message(
    frames: np.ndarray, cfg: GhostFontConfig, key: bytes, enc_share2: bytes
) -> tuple[np.ndarray, np.ndarray]:
    """Keyed decode: recover share-1 from motion, AES-decrypt share-2, XOR.

    Returns (share1_hat, revealed_message) at coarse resolution."""
    share2 = unpack_share(crypto.decrypt(key, enc_share2))
    s1_hat = recover_share1(frames, cfg.vc.block_px, share2.shape, cfg.motion.speed_px_per_frame)
    reveal = vc_reveal_xor(s1_hat, share2)
    return s1_hat, reveal


def upscale_display(coarse: np.ndarray, H: int, W: int, smooth: float = 0.0) -> np.ndarray:
    """Nearest-neighbour upscale a coarse binary image to (H,W) float for display."""
    img = cv2.resize(coarse.astype(np.float32), (W, H), interpolation=cv2.INTER_NEAREST)
    if smooth > 0:
        img = cv2.GaussianBlur(img, (0, 0), sigmaX=smooth)
    return np.clip(img, 0, 1)

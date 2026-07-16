"""Decoders / attacks.

Three lenses on a Ghost Font clip:

1. ``frame_average``       - naive temporal averaging. Moving dots wash out to
                             uniform density; only the *static* decoy survives
                             (the honeypot, spec Layer 2).
2. ``recover_optical_flow``- motion-compensated integration via dense optical
                             flow (spec Layer 3 "break"). Recovers the message
                             for the original font; produces striped garbage
                             against the keyed font when run *without* the key.
3. ``recover_keyed``       - the same optical-flow recovery, but un-scrambling
                             each band with the key-derived (sign, speed) table
                             first. Recovers the message for the keyed font.
"""

from __future__ import annotations

import cv2
import numpy as np

from . import crypto
from .config import GhostFontConfig


def _to_uint8(frames: np.ndarray) -> np.ndarray:
    if frames.dtype == np.uint8:
        return frames
    return np.clip(frames * 255.0, 0, 255).astype(np.uint8)


def _gray(frames: np.ndarray) -> np.ndarray:
    """Accept (N,H,W) grayscale or (N,H,W,3) RGB -> (N,H,W) uint8."""
    f = _to_uint8(frames)
    if f.ndim == 4:
        return f[..., :3].mean(axis=-1).astype(np.uint8)
    return f


def frame_average(frames: np.ndarray, smooth: float = 1.4) -> np.ndarray:
    """Mean over frames, lightly smoothed and contrast-stretched for display.

    The moving dots average to a flat field; the static decoy is the only
    structure that survives (the honeypot). Light smoothing suppresses residual
    per-pixel dot variance so the decoy reads clearly.
    """
    g = _gray(frames).astype(np.float32).mean(axis=0)
    if smooth > 0:
        g = cv2.GaussianBlur(g, (0, 0), sigmaX=smooth)
    lo, hi = np.percentile(g, 2), np.percentile(g, 98)
    return np.clip((g - lo) / max(hi - lo, 1e-6), 0, 1)


def mean_vertical_flow(frames: np.ndarray) -> np.ndarray:
    """Average per-pixel vertical optical-flow velocity (vy) over the clip.

    Negative == upward motion (image y grows downward). Uses Farneback dense
    flow between consecutive frames.
    """
    g = _gray(frames)
    acc = np.zeros(g.shape[1:], dtype=np.float32)
    for n in range(len(g) - 1):
        flow = cv2.calcOpticalFlowFarneback(
            g[n], g[n + 1],
            None,
            pyr_scale=0.5, levels=3, winsize=21,
            iterations=3, poly_n=7, poly_sigma=1.5, flags=0,
        )
        acc += flow[..., 1]
    acc /= max(len(g) - 1, 1)
    return cv2.GaussianBlur(acc, (0, 0), sigmaX=3.0)


def _score_to_image(score: np.ndarray) -> np.ndarray:
    """Normalize a letter-ness score field to a clean [0,1] display image."""
    s = score - np.median(score)
    hi = np.percentile(np.abs(s), 99) + 1e-6
    return np.clip(s / hi, 0, 1)


def recover_optical_flow(frames: np.ndarray) -> np.ndarray:
    """Keyless recovery: assume signal == upward everywhere.

    Correct for the original font; for the keyed font the per-band sign flips
    invert whole columns, yielding a striped, unreadable result.
    """
    vy = mean_vertical_flow(frames)
    # Upward (signal) motion is negative vy -> letter-ness = -vy.
    return _score_to_image(-vy)


def recover_keyed(
    frames: np.ndarray,
    cfg: GhostFontConfig,
    band_speeds: np.ndarray,
    band_signs: np.ndarray,
) -> np.ndarray:
    """Keyed recovery: un-scramble each band's (sign, speed) before scoring."""
    vy = mean_vertical_flow(frames)
    H, W = vy.shape
    band_w = W / cfg.keyed.n_bands
    score = np.empty_like(vy)
    for x in range(W):
        b = min(int(x / band_w), cfg.keyed.n_bands - 1)
        # Signal velocity in band b is -sign_b * speed_b, so multiplying the
        # observed vy by -sign_b / speed_b makes every band's letter-ness
        # positive on a common scale.
        score[:, x] = (-band_signs[b] * vy[:, x]) / max(band_speeds[b], 1e-6)
    return _score_to_image(score)


def recover_keyed_from_video(
    frames: np.ndarray, cfg: GhostFontConfig, key: bytes
) -> np.ndarray:
    """Full self-contained keyed pipeline (Approach 4 + 1): extract the
    encrypted band table from the video's stego border, decrypt with ``key``,
    then run band-aware recovery. ``frames`` must be RGB with the payload."""
    k = cfg.keyed
    blob = crypto.extract_lsb(frames[0], k.stego_border_px, k.stego_channel)
    payload = crypto.decrypt(key, blob)
    speeds, signs = crypto.deserialize_band_table(payload)
    return recover_keyed(frames, cfg, speeds, signs)

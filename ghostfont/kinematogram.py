"""Dual-population random-dot kinematogram engine (texture-composite model).

Implements Stages 2-4 of the formal spec. Rather than simulating individual
particles (which trap/deplete at the letter boundary and leak the message into
single frames and averages), we realize the two dot *populations* as two
independent, uniformly-dense random-dot textures:

* the **signal** texture scrolls up (velocity ``-v`` per the spec),
* the **background** texture scrolls down (``+v``),

and each output frame shows the signal texture inside the glyph mask and the
background texture outside it. Scrolling a uniform field keeps it uniform, so
density is exactly rho everywhere at every frame -> single frames are provably
i.i.d. noise (Proposition 1), naive averaging washes to a flat field (only the
static decoy survives), and coherent per-region motion is recoverable by
optical flow. The same engine drives the original (one global velocity) and the
keyed (per-band velocity) encoders via a pluggable velocity model.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import GhostFontConfig


def _disk_offsets(radius: int) -> tuple[np.ndarray, np.ndarray]:
    r = radius
    dy, dx = np.mgrid[-r : r + 1, -r : r + 1]
    m = (dx * dx + dy * dy) <= r * r
    return dy[m].ravel(), dx[m].ravel()


def make_texture(cfg: GhostFontConfig, rng: np.random.Generator) -> np.ndarray:
    """A static HxW float32 random-dot field in {0,1} at the target coverage.

    Dots are placed on a jittered grid (one dot per cell, uniformly random
    within the cell) rather than fully at random. This keeps the density equal
    across every row and column, so the vertical-scroll time-average of the
    field is spatially flat -- essential for the honeypot: naive frame
    averaging must wash to a uniform grey (revealing only the static decoy),
    with no residual streaks or letter blob. With full cell jitter the field
    still reads as random noise in any single frame.
    """
    W, H = cfg.canvas.width, cfg.canvas.height
    off_dy, off_dx = _disk_offsets(cfg.motion.dot_radius)
    disk_px = len(off_dy)
    # Cell size so that one dot per cell yields the target coverage.
    g = max(int(round(np.sqrt(disk_px / cfg.motion.coverage))), 2)
    gy = np.arange(0, H, g)
    gx = np.arange(0, W, g)
    cyg, cxg = np.meshgrid(gy, gx, indexing="ij")
    cyg = cyg.ravel()
    cxg = cxg.ravel()
    cy = cyg + rng.integers(0, g, size=cyg.shape)
    cx = cxg + rng.integers(0, g, size=cxg.shape)
    tex = np.zeros((H, W), dtype=np.float32)
    yy = (cy[None, :] + off_dy[:, None]) % H
    xx = (cx[None, :] + off_dx[:, None]) % W
    tex[yy.ravel(), xx.ravel()] = 1.0
    return tex


@dataclass
class VelocityModel:
    """Per-column signal velocity (pixels/frame, +y = downward in image space).

    ``kind`` is ``"global"`` (original Ghost Font) or ``"banded"`` (Approach 1).
    The background population always takes the opposite velocity, so within
    every band the two populations move in opposition (the motion contrast
    humans use to segregate the letter).
    """

    kind: str
    speed: float = 0.0
    band_speeds: np.ndarray | None = None
    band_signs: np.ndarray | None = None
    band_width: float = 0.0

    def signal_velocity_per_column(self, width: int) -> np.ndarray:
        if self.kind == "global":
            # Signal scrolls up -> negative velocity.
            return np.full(width, -self.speed, dtype=np.float64)
        x = np.arange(width)
        b = np.clip((x / self.band_width).astype(np.int64), 0, len(self.band_speeds) - 1)
        # Signal velocity in band b is -sign_b * speed_b.
        return -self.band_signs[b] * self.band_speeds[b]


def _scroll(texture: np.ndarray, col_shift: np.ndarray) -> np.ndarray:
    """Vertically roll each column of ``texture`` by ``col_shift[x]`` pixels.

    Positive shift samples from larger y (pattern appears to move up)."""
    H, W = texture.shape
    ys = (np.arange(H)[:, None] + col_shift[None, :]) % H
    xs = np.broadcast_to(np.arange(W)[None, :], (H, W))
    return texture[ys, xs]


def render_video(
    cfg: GhostFontConfig,
    mask: np.ndarray,
    vmodel: VelocityModel,
    decoy_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Return a float32 array (n_frames, H, W) in [0, 1]; 1 == bright dot."""
    W, H = cfg.canvas.width, cfg.canvas.height
    m = cfg.motion
    rng = np.random.default_rng(m.seed)
    signal_tex = make_texture(cfg, rng)
    background_tex = make_texture(cfg, rng)

    sig_v = vmodel.signal_velocity_per_column(W)  # per-column (W,)
    bg_v = -sig_v
    frames = np.zeros((m.n_frames, H, W), dtype=np.float32)

    for n in range(m.n_frames):
        # A dot at column x with velocity v is, after n frames, displaced by
        # n*v; render by sampling the base texture shifted by -round(n*v).
        sig_shift = np.round(-n * sig_v).astype(np.int64)
        bg_shift = np.round(-n * bg_v).astype(np.int64)
        sig = _scroll(signal_tex, sig_shift)
        bg = _scroll(background_tex, bg_shift)

        if m.wobble_x_px > 0:
            phase = 2 * np.pi * m.wobble_hz * n / m.fps
            wob = int(round(m.wobble_x_px * np.sin(phase)))
            sig = np.roll(sig, wob, axis=1)

        frames[n] = np.where(mask, sig, bg)

    if decoy_mask is not None and cfg.decoy.opacity > 0:
        frames = np.minimum(1.0, frames + cfg.decoy.opacity * decoy_mask[None, :, :])
    return frames


def build_velocity_model_original(cfg: GhostFontConfig) -> VelocityModel:
    return VelocityModel(kind="global", speed=cfg.motion.speed_px_per_frame)


def build_velocity_model_keyed(
    cfg: GhostFontConfig, band_speeds: np.ndarray, band_signs: np.ndarray
) -> VelocityModel:
    return VelocityModel(
        kind="banded",
        band_speeds=band_speeds,
        band_signs=band_signs,
        band_width=cfg.canvas.width / cfg.keyed.n_bands,
    )

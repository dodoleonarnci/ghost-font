"""Shared visualization style + IO helpers (matplotlib / imageio)."""

from __future__ import annotations

import imageio.v2 as imageio
import matplotlib

matplotlib.use("Agg")
import numpy as np

# Muted, colour-blind-safe accents on a dark ground (one visual system).
INK = "#0f1216"
FG = "#e8eaed"
MUTE = "#9aa0a6"
GOOD = "#5ec4b6"   # teal  - success / message recovered
WARN = "#e0a458"   # amber - honeypot / decoy
BAD = "#d16d6d"    # red   - attack fails / scrambled / leak
UP = "#6ea8fe"     # blue  - upward band
DOWN = "#e0a458"   # amber - downward band
PANEL_EDGE = "#2a2f37"


def u8(gray01: np.ndarray) -> np.ndarray:
    return np.clip(gray01 * 255.0, 0, 255).astype(np.uint8)


def save_gif(frames01, path, fps=20, max_frames=48):
    step = max(1, len(frames01) // max_frames)
    imageio.mimsave(path, [u8(f) for f in frames01[::step]], fps=fps, loop=0)


def save_mp4(frames01, path, fps=30):
    seq = [np.repeat(u8(f)[..., None], 3, axis=-1) for f in frames01]
    imageio.mimwrite(path, seq, fps=fps, quality=8, macro_block_size=None)


def panel(ax, img, title, sub, accent=FG):
    ax.imshow(img, cmap="gray", vmin=0, vmax=1, aspect="auto", interpolation="nearest")
    ax.set_title(title, color=accent, fontsize=13, fontweight="bold", pad=8)
    ax.set_xlabel(sub, color=MUTE, fontsize=9.5, labelpad=6)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(PANEL_EDGE)

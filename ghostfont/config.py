"""Configuration dataclasses for Ghost Font encoding.

Parameter names and default values follow the formal specification in
``ghost_font_algorithm.tex`` (Table 1) and the key-encrypted design plan in
``ghost_font_key_encryption_plan.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CanvasConfig:
    """Canvas + glyph rasterization parameters."""

    width: int = 800
    height: int = 260
    # Fraction of canvas width the rendered text should span.
    text_width_frac: float = 0.86
    # Path to a bold TrueType face (thick strokes hold more dots -> robust).
    font_path: str = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
    decoy_font_path: str = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


@dataclass
class MotionConfig:
    """Dual-population opposing-motion parameters (Stage 3 of the spec).

    Colours follow the popular Ghost Font demos: bright dots on a black
    background (a classic random-dot kinematogram), rather than the
    dark-on-light convention used symbolically in the LaTeX spec.
    """

    fps: int = 30
    n_frames: int = 66
    # Nominal scroll speed in pixels/frame (spec: ~4.012 px/frame @ 30 fps;
    # we use a slightly gentler speed for smooth playback + clean recovery).
    speed_px_per_frame: float = 2.4
    dot_radius: int = 2
    # Target fraction of the canvas covered by dots (spec rho ~ 0.3-0.5).
    coverage: float = 0.34
    # Optional horizontal wobble applied to the up-scrolling signal dots
    # (spec w_x); off by default to keep single frames maximally uniform.
    wobble_x_px: float = 0.0
    wobble_hz: float = 0.9
    seed: int = 20260715


@dataclass
class DecoyConfig:
    """Static honeypot layer (Stage 4 of the spec)."""

    text: str = "WRITTEN IN GHOST FONT"
    # Per-frame additive opacity (0..1 of full white). Small enough to be lost
    # among bright dots in any single frame, but it survives frame averaging.
    opacity: float = 0.12
    font_size_frac: float = 0.16


@dataclass
class KeyedConfig:
    """Approach 1 (key-derived per-band velocity scrambling) + Approach 4
    (steganographic embedding of the encrypted band table)."""

    # Number of vertical bands (plan suggests B in {8, 16}); B=16 gives a
    # brute-force space of ~256^16 ~ 2^128 for continuous velocities.
    n_bands: int = 16
    # Per-band speed range; keep v_max/v_min <~ 2 so human legibility holds.
    v_min: float = 1.7
    v_max: float = 3.1
    # Whether bands may independently flip signal direction (up vs down).
    use_direction_bit: bool = True
    # Steganography: embed encrypted band table in the LSBs of the blue
    # channel of a border strip this many pixels thick.
    stego_border_px: int = 6
    stego_channel: int = 2  # 0=R,1=G,2=B (plan: blue channel border strip)


@dataclass
class VisualCryptoConfig:
    """Approach 3 — Naor-Shamir / random-grid visual cryptography.

    The message is split into two shares at a coarse block resolution (so the
    motion channel can carry share-1 and optical flow can recover it). Share-1
    is embedded as the motion-defined form in the video; share-2 is the static
    key image, AES-encrypted under K and distributed out-of-band.
    """

    # Side length (px) of a visual-crypto block. Each block moves coherently
    # up or down, encoding one share-1 bit. Larger = more robust motion
    # recovery; smaller = finer (more readable) reveal.
    block_px: int = 14


@dataclass
class GhostFontConfig:
    message: str = "GHOST"
    canvas: CanvasConfig = field(default_factory=CanvasConfig)
    motion: MotionConfig = field(default_factory=MotionConfig)
    decoy: DecoyConfig = field(default_factory=DecoyConfig)
    keyed: KeyedConfig = field(default_factory=KeyedConfig)
    vc: VisualCryptoConfig = field(default_factory=VisualCryptoConfig)

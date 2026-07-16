#!/usr/bin/env python3
"""Generate Ghost Font videos and analysis visualizations.

Produces, in the output directory:
  original.mp4 / original.gif   - the original Ghost Font animation
  keyed.mp4    / keyed.gif      - the key-encrypted animation (Approach 1 + 4)
  original_analysis.png         - single frame / averaging / optical-flow break
  keyed_analysis.png            - single frame / averaging / keyless vs keyed
  keyed_selfcontained.npz       - lossless keyed frames carrying the stego key
                                  payload (lossy codecs would destroy the LSBs)

Run:  python generate.py --message GHOST --key "open sesame"
"""

from __future__ import annotations

import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ghostfont import (
    GhostFontConfig,
    crypto,
    derive_key,
    embed_key_payload,
    encode_keyed,
    encode_original,
    frames_to_rgb,
)
from ghostfont.decode import (
    frame_average,
    mean_vertical_flow,
    recover_keyed_from_video,
    recover_optical_flow,
)
from ghostfont.viz import (
    BAD, DOWN, FG, GOOD, INK, MUTE, UP, WARN,
    panel as _panel, save_gif, save_mp4, u8 as _u8,
)


def figure_original(cfg, res, outpath):
    mid = res.frames[len(res.frames) // 2]
    avg = frame_average(res.frames)
    rec = recover_optical_flow(res.frames)

    fig, axs = plt.subplots(3, 1, figsize=(11.0, 8.7))
    fig.patch.set_facecolor(INK)
    _panel(axs[0], mid, "1 · Any single frame",
           "A screenshot is i.i.d. noise — zero information about the message (Prop. 1)", FG)
    _panel(axs[1], avg, "2 · Naive frame-averaging  →  DECOY honeypot",
           "Moving dots wash out; only the static decoy survives — the AI reads the wrong text", WARN)
    _panel(axs[2], rec, "3 · Motion-compensated optical flow  →  TRUE message",
           "No key needed: dense optical flow fully breaks the original Ghost Font", GOOD)
    fig.suptitle("Original Ghost Font — opaque to screenshots & averaging, breakable by optical flow",
                 color=FG, fontsize=13.5, fontweight="bold", y=0.985)
    fig.tight_layout(rect=[0, 0, 1, 0.955])
    fig.savefig(outpath, dpi=140, facecolor=INK)
    plt.close(fig)


def _band_table_image(cfg, speeds, signs, H, W):
    """Render the per-band velocity table as an image row for the figure."""
    fig = plt.figure(figsize=(W / 140, H / 140), dpi=140)
    ax = fig.add_axes([0.09, 0.22, 0.88, 0.66])
    fig.patch.set_facecolor(INK)
    ax.set_facecolor(INK)
    b = len(speeds)
    xs = np.arange(b)
    colors = [UP if s > 0 else DOWN for s in signs]
    ax.bar(xs, signs * speeds, color=colors, edgecolor="#11151a", width=0.86)
    ax.axhline(0, color=MUTE, lw=0.8)
    ax.set_xlim(-0.7, b - 0.3)
    ax.set_ylim(-cfg.keyed.v_max * 1.15, cfg.keyed.v_max * 1.15)
    ax.set_xlabel("vertical band index (0 … B-1)", color=MUTE, fontsize=9)
    ax.set_ylabel("signal velocity\n(px/frame, ↑ / ↓)", color=MUTE, fontsize=9)
    ax.tick_params(colors=MUTE, labelsize=8)
    for s in ax.spines.values():
        s.set_color("#2a2f37")
    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba())[..., :3].copy()
    plt.close(fig)
    return buf


def figure_keyed(cfg, kr, rgb_payload, key, outpath):
    mid = kr.frames[len(kr.frames) // 2]
    avg = frame_average(kr.frames)
    attack = recover_optical_flow(kr.frames)                      # no key
    recovered = recover_keyed_from_video(rgb_payload, cfg, key)   # with key
    H, W = mid.shape
    band_img = _band_table_image(cfg, kr.band_speeds, kr.band_signs, H, W)

    fig = plt.figure(figsize=(15.5, 7.6))
    fig.patch.set_facecolor(INK)
    gs = fig.add_gridspec(2, 3, hspace=0.32, wspace=0.10)

    ax = fig.add_subplot(gs[0, 0]); _panel(ax, mid, "1 · Single frame", "still pure noise", FG)
    ax = fig.add_subplot(gs[0, 1]); _panel(ax, avg, "2 · Frame-average → DECOY",
                                           "honeypot survives averaging", WARN)
    ax = fig.add_subplot(gs[0, 2])
    ax.imshow(band_img, aspect="auto")
    ax.set_title("3 · Secret band table  (derived from key K)", color=UP, fontsize=13,
                 fontweight="bold", pad=8)
    ax.set_xlabel("HMAC-SHA256(K) → per-band speed + up/down direction", color=MUTE, fontsize=9.5)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#2a2f37")

    ax = fig.add_subplot(gs[1, 0:2]); _panel(
        ax, attack, "4 · AI WITHOUT the key  →  optical-flow attack fails",
        "per-band direction flips invert whole columns → unreadable, scrambled result", BAD)
    ax = fig.add_subplot(gs[1, 2]); _panel(
        ax, recovered, "5 · AI WITH key K  →  message recovered",
        "extract + AES-decrypt band table, un-scramble each band", GOOD)

    fig.suptitle("Key-Encrypted Ghost Font  (Approach 1 · per-band velocity scrambling  +  Approach 4 · encrypted stego key)",
                 color=FG, fontsize=15, fontweight="bold", y=0.98)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.90, bottom=0.06)
    fig.savefig(outpath, dpi=135, facecolor=INK)
    plt.close(fig)


def _hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def motion_direction_map(frames):
    """Colour-code local vertical motion: upward (signal) vs downward (bg).

    This is the closest static analogue to what the human motion system does
    when watching the clip — the letter pops out because its dots move opposite
    to the surround.
    """
    vy = mean_vertical_flow(frames)
    s = vy / (np.percentile(np.abs(vy), 96) + 1e-6)
    s = np.clip(s, -1, 1)              # -1 = fully up (signal), +1 = fully down
    up = (-s + 1) / 2                  # 1 where upward
    up = up[..., None]
    img = up * _hex_rgb(GOOD) + (1 - up) * _hex_rgb(DOWN)
    return (img / 255.0)


def figure_hero(cfg, res_orig, outpath):
    fig, ax = plt.subplots(1, 1, figsize=(11.0, 4.1))
    fig.patch.set_facecolor(INK)
    ax.imshow(motion_direction_map(res_orig.frames), aspect="auto", interpolation="nearest")
    ax.set_title("What your motion perception sees — upward-moving dots form the letter",
                 color=FG, fontsize=12.5, fontweight="bold", pad=6)
    ax.set_xlabel("colour = local motion direction:  teal = up (signal) · amber = down (background)",
                  color=MUTE, fontsize=10, labelpad=6)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#2a2f37")
    fig.suptitle("Ghost Font — a single frame is noise; the message lives only in the motion",
                 color=FG, fontsize=13.5, fontweight="bold", y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.9])
    fig.savefig(outpath, dpi=140, facecolor=INK)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Generate Ghost Font visualizations")
    ap.add_argument("--message", default="GHOST")
    ap.add_argument("--key", default="open sesame", help="passphrase for the keyed variant")
    ap.add_argument("--outdir", default="output")
    ap.add_argument("--frames", type=int, default=90)
    ap.add_argument("--no-video", action="store_true", help="skip mp4/gif (figures only)")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    cfg = GhostFontConfig(message=args.message)
    cfg.motion.n_frames = args.frames
    fps = cfg.motion.fps

    print(f"Message: {args.message!r}   decoy: {cfg.decoy.text!r}   key: {args.key!r}")

    # ---- Original ----------------------------------------------------------
    print("Encoding original Ghost Font …")
    res = encode_original(cfg)
    if not args.no_video:
        save_mp4(res.frames, f"{args.outdir}/original.mp4", fps)
        save_gif(res.frames, f"{args.outdir}/original.gif", fps=20)
    print("Rendering original analysis figure …")
    figure_original(cfg, res, f"{args.outdir}/original_analysis.png")

    # ---- Keyed (Approach 1 + 4) -------------------------------------------
    print("Encoding key-encrypted Ghost Font …")
    key = derive_key(args.key)
    kr = encode_keyed(cfg, key)
    rgb_payload = embed_key_payload(frames_to_rgb(kr.frames), cfg, key)

    # Human-facing video (LSB stego does NOT survive lossy encoding — that's
    # fine, it's for viewing). Canonical self-contained artifact is lossless.
    if not args.no_video:
        save_mp4(kr.frames, f"{args.outdir}/keyed.mp4", fps)
        save_gif(kr.frames, f"{args.outdir}/keyed.gif", fps=20)
        np.savez_compressed(f"{args.outdir}/keyed_selfcontained.npz", frames=rgb_payload)

    print("Rendering keyed analysis figure …")
    figure_keyed(cfg, kr, rgb_payload, key, f"{args.outdir}/keyed_analysis.png")

    print("Rendering motion-perception hero figure …")
    figure_hero(cfg, res, f"{args.outdir}/motion_perception.png")

    # ---- Sanity report -----------------------------------------------------
    blob = crypto.extract_lsb(rgb_payload[0], cfg.keyed.stego_border_px, cfg.keyed.stego_channel)
    sp, _ = crypto.deserialize_band_table(crypto.decrypt(key, blob))
    print("\nSelf-contained decode check:", "OK" if np.allclose(sp, kr.band_speeds) else "FAIL")
    print(f"Band signs (↑/↓): {''.join('↑' if s>0 else '↓' for s in kr.band_signs)}  "
          f"({int((kr.band_signs<0).sum())}/{cfg.keyed.n_bands} inverted)")
    print(f"\nWrote outputs to ./{args.outdir}/")


if __name__ == "__main__":
    main()

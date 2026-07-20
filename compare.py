#!/usr/bin/env python3
"""Side-by-side comparison: Approach 1+4  vs  Approach 3 (visual cryptography).

Both schemes hide the same message under the same key. This builds:

  vc.mp4 / vc.gif           - the Approach-3 (visual-crypto) animation
  vc_keyimage.png           - the static key image (share-2), for reference
  vc_keyimage.enc           - AES-256-GCM(share-2) under K, the out-of-band key
  compare_1plus4_vs_3.png   - the side-by-side figure

Run:  python compare.py --message GHOST --key "open sesame"
"""

from __future__ import annotations

import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from ghostfont import (
    GhostFontConfig,
    derive_key,
    embed_key_payload,
    encode_keyed,
    encode_visualcrypto,
    frames_to_rgb,
)
from ghostfont import visualcrypto as vc
from ghostfont.decode import mean_vertical_flow, recover_keyed_from_video, recover_optical_flow
from ghostfont.viz import (
    BAD, DOWN, FG, GOOD, INK, MUTE, PANEL_EDGE, WARN, panel, save_gif, save_mp4, u8,
)


def _corr(a, b):
    a = a.astype(float).ravel() - a.mean()
    b = b.astype(float).ravel() - b.mean()
    return float((a @ b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def _hex(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32) / 255.0


def _motion_map(frames):
    """Colour-code local vertical motion (teal=up/signal, amber=down) — the
    closest static analogue to what a human's motion system sees while it plays."""
    vy = mean_vertical_flow(frames)
    s = np.clip(vy / (np.percentile(np.abs(vy), 96) + 1e-6), -1, 1)
    up = ((-s + 1) / 2)[..., None]
    return np.clip(up * _hex(GOOD) + (1 - up) * _hex(DOWN), 0, 1)


def figure_readability(raw_frames, keyed_frames, outpath):
    fig, axs = plt.subplots(2, 1, figsize=(11.0, 6.4))
    fig.patch.set_facecolor(INK)
    for ax, frames, title, sub, col in (
        (axs[0], raw_frames, "Distributed video (no key) — what a human sees while watching",
         "motion encodes share-1 → incoherent noise, unreadable", BAD),
        (axs[1], keyed_frames, "Keyed playback (with key) — flip share-2 blocks, then just watch",
         "motion-defined form becomes the message → readable by eye, as in the original Ghost Font", GOOD),
    ):
        ax.imshow(_motion_map(frames), aspect="auto", interpolation="nearest")
        ax.set_title(title, color=col, fontsize=12, fontweight="bold", pad=6)
        ax.set_xlabel(sub, color=MUTE, fontsize=10, labelpad=6)
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color(PANEL_EDGE)
    fig.suptitle("Fixing human readability under visual cryptography  ·  teal = up (signal) · amber = down",
                 color=FG, fontsize=13.5, fontweight="bold", y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(outpath, dpi=140, facecolor=INK)
    plt.close(fig)


def _col_header(fig, x, text, color):
    fig.text(x, 0.905, text, color=color, fontsize=14.5, fontweight="bold",
             ha="center", va="center")


def _table(fig, rows):
    """rows = list of (label, val_14, val_3). Drawn as three aligned columns."""
    xl, x1, x2 = 0.035, 0.375, 0.695
    y = 0.245
    dy = 0.052
    fig.text(xl, y + dy, "property", color=MUTE, fontsize=10.5, fontweight="bold")
    fig.text(x1, y + dy, "Approach 1 + 4", color=GOOD, fontsize=11, fontweight="bold")
    fig.text(x2, y + dy, "Approach 3 (visual crypto)", color=WARN, fontsize=11, fontweight="bold")
    for label, v1, v3 in rows:
        fig.text(xl, y, label, color=FG, fontsize=10.5, fontweight="bold", va="top")
        fig.text(x1, y, v1, color="#c7ccd2", fontsize=10, va="top", wrap=True)
        fig.text(x2, y, v3, color="#c7ccd2", fontsize=10, va="top", wrap=True)
        y -= dy


def build(message, keyphrase, outdir, frames, make_video=True):
    os.makedirs(outdir, exist_ok=True)
    cfg = GhostFontConfig(message=message)
    cfg.motion.n_frames = frames
    key = derive_key(keyphrase)
    H, W = cfg.canvas.height, cfg.canvas.width
    mid = frames // 2

    # ---- Approach 1 + 4 ----------------------------------------------------
    kr = encode_keyed(cfg, key)
    rgb = embed_key_payload(frames_to_rgb(kr.frames), cfg, key)
    a14_single = kr.frames[mid]
    a14_keyless = recover_optical_flow(kr.frames)                 # no key
    a14_withkey = recover_keyed_from_video(rgb, cfg, key)         # with key
    a14_leak = _corr(a14_keyless, kr.mask)

    # ---- Approach 3 (visual cryptography) ----------------------------------
    r = vc.encode_visualcrypto(cfg, key)
    a3_single = r.frames[mid]
    s1_hat = vc.recover_share1(r.frames, r.block, r.share1.shape, cfg.motion.speed_px_per_frame)
    a3_keyless = vc.upscale_display(s1_hat, H, W)                 # share-1 only
    _, reveal = vc.recover_message(r.frames, cfg, key, r.enc_share2)
    a3_withkey = vc.upscale_display(reveal, H, W, smooth=2.0)     # XOR reveal
    a3_leak = _corr(s1_hat, r.coarse_mask)

    # ---- Approach-3 artifacts + human-readable keyed playback -------------
    keyed_frames = vc.keyed_view(r.frames, cfg, key, r.enc_share2)
    if make_video:
        save_mp4(r.frames, f"{outdir}/vc.mp4", cfg.motion.fps)
        save_gif(r.frames, f"{outdir}/vc.gif", fps=20)
        save_mp4(keyed_frames, f"{outdir}/vc_keyed_view.mp4", cfg.motion.fps)
        save_gif(keyed_frames, f"{outdir}/vc_keyed_view.gif", fps=20)
    Image.fromarray(u8(vc.upscale_display(r.share2, H, W))).save(f"{outdir}/vc_keyimage.png")
    with open(f"{outdir}/vc_keyimage.enc", "wb") as fh:
        fh.write(r.enc_share2)
    figure_readability(r.frames, keyed_frames, f"{outdir}/vc_human_readability.png")

    # keyed-view motion recovers the message (a human reads it by watching)?
    vy = mean_vertical_flow(keyed_frames)
    bk = cfg.vc.block_px
    ch, cw = r.coarse_mask.shape
    kv_blk = (vy[: ch * bk, : cw * bk].reshape(ch, bk, cw, bk).mean(axis=(1, 3)) < 0)
    kv_acc = (kv_blk == r.coarse_mask).mean()

    # ---- Comparison figure -------------------------------------------------
    fig = plt.figure(figsize=(13.8, 12.6))
    fig.patch.set_facecolor(INK)
    gs = fig.add_gridspec(3, 2, left=0.035, right=0.985, top=0.875, bottom=0.37,
                          hspace=0.34, wspace=0.06)

    _col_header(fig, 0.27, "Approach 1 + 4", GOOD)
    _col_header(fig, 0.755, "Approach 3 · Visual Cryptography", WARN)

    panel(fig.add_subplot(gs[0, 0]), a14_single, "Single frame", "i.i.d. noise", FG)
    panel(fig.add_subplot(gs[0, 1]), a3_single, "Single frame", "i.i.d. noise", FG)

    panel(fig.add_subplot(gs[1, 0]), a14_keyless,
          "Keyless motion break", f"naive up/down attack → scrambled, partial leak (corr {a14_leak:+.2f})", BAD)
    panel(fig.add_subplot(gs[1, 1]), a3_keyless,
          "Keyless motion break", f"perfect share-1 recovery → still PURE NOISE (corr {a3_leak:+.2f})", BAD)

    panel(fig.add_subplot(gs[2, 0]), a14_withkey,
          "With key K", "extract + AES-decrypt band table → recover", GOOD)
    panel(fig.add_subplot(gs[2, 1]), a3_withkey,
          "With key K", "AES-decrypt key image, XOR → reconstruct", GOOD)

    _table(fig, [
        ("security", "computational\n(HMAC-PRF + AES-256)", "information-theoretic\n(XOR share) + AES-256 on key image"),
        ("self-contained", "yes — key table hidden in\nvideo LSBs (stego)", "no — needs a separate\nstatic key image"),
        ("human needs key", "no — motion segregation\nreads it directly", "yes — but keyed player flips\nshare-2 blocks, then read by eye"),
        ("if motion fully broken", "partial leak: scrambled\nletter is still visible", "zero leak: provably\nindependent of message"),
    ])

    fig.suptitle("Key-Encrypted Ghost Font — Approach 1+4 (self-contained, computational)  vs  Approach 3 (visual crypto, information-theoretic)",
                 color=FG, fontsize=13.5, fontweight="bold", y=0.965)
    fig.text(0.5, 0.925, f'message "{message}"  ·  key "{keyphrase}"  ·  same for both schemes',
             color=MUTE, fontsize=10.5, ha="center")
    fig.savefig(f"{outdir}/compare_1plus4_vs_3.png", dpi=135, facecolor=INK)
    plt.close(fig)

    print(f"Approach 1+4  keyless leak corr = {a14_leak:+.3f}  (partial — computational security)")
    print(f"Approach 3    keyless leak corr = {a3_leak:+.3f}  (~0 — information-theoretic)")
    print(f"Approach 3    keyed reveal accuracy = {(reveal == r.coarse_mask).mean():.3f}")
    print(f"Approach 3    keyed-VIEW motion readability = {kv_acc:.3f}  "
          f"(human reads it by watching, with the key)")
    print(f"Wrote comparison + Approach-3 artifacts to ./{outdir}/")


def main():
    ap = argparse.ArgumentParser(description="Compare Approach 1+4 vs Approach 3")
    ap.add_argument("--message", default="GHOST")
    ap.add_argument("--key", default="open sesame")
    ap.add_argument("--outdir", default="output")
    ap.add_argument("--frames", type=int, default=90)
    ap.add_argument("--no-video", action="store_true", help="skip vc mp4/gif (figure only)")
    args = ap.parse_args()
    build(args.message, args.key, args.outdir, args.frames, make_video=not args.no_video)


if __name__ == "__main__":
    main()

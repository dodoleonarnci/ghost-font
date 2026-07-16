# Ghost Font — and a key-encrypted extension

Python implementations and visualizations of **Ghost Font**, the motion-encoded
"anti-AI" typography that went viral in July 2026 (Eric Lu / Mixfont), plus the
**key-encrypted variant** proposed in the companion design plan.

Ghost Font hides a short message in a video as thousands of tiny black-and-white
dots. The dots *inside* the letters drift one way; the surrounding dots drift
the opposite way. A human's motion system instantly groups the coherently-moving
dots into letters — but **freeze any single frame and it is pure noise**. Because
most multimodal AI systems sample video frame-by-frame rather than integrating
motion, they see only noise (or a planted decoy). See
[mixfont.com/ghost-font](https://www.mixfont.com/ghost-font),
[Tom's Guide](https://www.tomsguide.com/ai/someone-created-a-ghost-font-that-humans-can-read-but-ai-cant-i-had-to-try-it-for-myself),
and [Creative Bloq](https://www.creativebloq.com/design/fonts-typography/this-optical-illusion-font-was-created-to-baffle-ai-and-it-actually-works-for-now).

This repo implements **three** versions:

1. **Original Ghost Font** — formalized in [`ghost_font_algorithm.tex`](ghost_font_algorithm.tex)
   as a *dual-population, opposing-direction random-dot kinematogram*.
2. **Key-encrypted Ghost Font (1+4)** — the *self-contained* combination
   recommended in [`ghost_font_key_encryption_plan.md`](ghost_font_key_encryption_plan.md):
   **Approach 1** (key-derived per-band velocity scrambling) **+ Approach 4**
   (steganographic embedding of the encrypted band table inside the video).
3. **Visual-cryptography Ghost Font (Approach 3)** — the *maximum-security*
   alternative from the same plan: the message is split into two shares; the
   video carries share-1 as its motion, and a separate AES-encrypted key image
   carries share-2. The only variant with **information-theoretic** security.

## The visualizations

Run `python generate.py`; everything below lands in `output/`.

| File | What it shows |
|------|---------------|
| `motion_perception.png` | Motion-direction map: the "GHOST" you'd see while it plays (teal = up/signal, amber = down/background). |
| `original.mp4` · `original.gif` | The original Ghost Font animation. |
| `original_analysis.png` | **(1)** single frame = i.i.d. noise · **(2)** naive frame-averaging surfaces the **decoy** honeypot · **(3)** dense optical flow fully **recovers** the message (no key needed). |
| `keyed.mp4` · `keyed.gif` | The key-encrypted animation (self-contained). |
| `keyed_analysis.png` | **(1)** noise · **(2)** decoy honeypot · **(3)** the secret per-band velocity table from `K` · **(4)** a keyless optical-flow attack → **scrambled** · **(5)** with `K`: extract + AES-decrypt the band table, un-scramble, **recover** the message. |
| `keyed_selfcontained.npz` | Lossless keyed frames carrying the LSB stego key payload. |

Run `python compare.py` for **Approach 3** and the side-by-side:

| File | What it shows |
|------|---------------|
| `vc.mp4` · `vc.gif` | The visual-crypto (Approach 3) animation — its motion carries share-1. |
| `vc_keyimage.png` | The static key image (share-2) — pure noise on its own. |
| `vc_keyimage.enc` | `AES-256-GCM(share-2)` under `K`, distributed out-of-band. |
| `compare_1plus4_vs_3.png` | **1+4 vs Approach 3** side-by-side: single frame, keyless break, keyed recovery, and a property table. |

## How the original works

Two independent, uniformly-dense random-dot **textures** are scrolled in
opposite vertical directions; each output frame shows the **signal** texture
inside the glyph mask and the **background** texture outside it:

```
F_n(x,y) = signal_scrolled_up(x,y)      if (x,y) ∈ glyph mask
           background_scrolled_down(x,y) otherwise
```

Because scrolling a uniform field keeps it uniform, **density is exactly ρ
everywhere in every frame**. Consequences (all reproduced in the figures):

- **Single frame → noise.** No pixel statistic depends on the mask
  (spec Proposition 1). A screenshot carries zero information.
- **Naive averaging → decoy.** The moving dots average to a flat grey; the only
  structure that survives is the faint *static* decoy `WRITTEN IN GHOST FONT`
  (spec Layer 2 honeypot). An AI that averages frames confidently reads the
  wrong text.
- **Optical flow → message.** Dense optical flow (Farnebäck) recovers coherent
  per-region motion and the letters pop out (spec Layer 3). **The original has
  no cryptographic secrecy** — this is a complete, key-free break.

> Implementation note: the LaTeX spec describes individual particles. A literal
> particle simulation traps/depletes dots at the letter boundary, which leaks
> the message into single frames and averages. The mathematically-equivalent
> *texture-composite* model above has no such artifact, so Proposition 1 holds
> exactly. Dots are placed on a **jittered grid** (uniform per-column density)
> so the scroll time-average is flat and only the decoy survives.

## How the key-encrypted version works (Approach 1 + 4)

The key-free optical-flow break above needs no secret, so encryption must make
one of its steps require the key `K`.

**Approach 1 — per-band velocity scrambling.** The canvas is split into `B = 16`
vertical bands. Each band `b` gets its own scroll speed and up/down direction
derived from a PRF keyed by `K`:

```
v_b   = v_min + (v_max − v_min) · PRF_K(b)          # HMAC-SHA256 → [0,1)
sign_b = ±1 from PRF_K(B + b)                        # up- or down-flipped band
```

Within every band the signal and background still move in opposition, so the
**motion contrast a human uses is preserved** — but a keyless attacker no longer
knows which direction is "signal" per band. A global "up = letter" optical-flow
attack inverts the flipped bands and produces the scrambled result in
`keyed_analysis.png` panel 4.

**Approach 4 — encrypted steganographic key.** The band table `{v_b, sign_b}` is
serialized, encrypted with **AES-256-GCM** under `K`, and LSB-embedded in the
blue channel of a border strip of every frame (repeated for redundancy). The
video is **self-contained**: a keyed decoder extracts the payload, decrypts it,
un-scrambles each band, and recovers the message; a keyless one cannot (a wrong
key fails GCM authentication outright).

Security is the combination: Approach 1 alone is ~`2^B` obfuscation on the
direction bits; Approach 4 puts the exact table behind AES-256, so recovering it
means breaking AES. The decoy honeypot is retained in both versions.

> As the plan notes, lossy video codecs (H.264/VP9) destroy LSB channels — even
> "lossless" ffv1 flips LSBs during RGB↔YUV conversion. So the canonical
> self-contained artifact here is the lossless `keyed_selfcontained.npz`; the
> `.mp4`/`.gif` are for viewing only. Surviving compression would need
> DCT-domain / spread-spectrum embedding (plan, Implementation Notes).

## The alternative: Approach 3 (visual cryptography)

Approach 3 splits the message with a 2-out-of-2 **random-grid** visual-crypto
scheme (Naor–Shamir, pure XOR) at a coarse block resolution:

```
share1               ~ Uniform          (independent of the message M)  → the VIDEO's motion
share2 = share1 XOR M ~ Uniform          (independent of M)              → the static key image
share1 XOR share2     = M                                                → the reveal
```

Share-1 is embedded as the **motion-defined form** of the kinematogram: each
coarse block scrolls up if its share-1 bit is 1, down if 0. Share-2 is the
static key image, **AES-256-GCM-encrypted under `K`** and distributed
out-of-band (`vc_keyimage.enc`). To decode, a keyed party recovers share-1 from
the motion (a matched filter against the public scroll speed → 100% accurate),
AES-decrypts share-2, and XORs the two to reconstruct the message.

The crucial property: because share-1 is **information-theoretically
independent of M**, a keyless attacker who breaks the motion *perfectly*
recovers only share-1 — pure noise, zero bits about the message (verified: the
recovered share correlates ≈0 with the message). No amount of computation on the
video alone helps. Security reduces entirely to AES on the key image.

## Approach 1+4 vs Approach 3

`compare_1plus4_vs_3.png` puts them head to head under the same message and key:

| property | Approach 1 + 4 | Approach 3 (visual crypto) |
|---|---|---|
| security | computational (HMAC-PRF + AES-256) | **information-theoretic** (XOR share) + AES-256 on the key image |
| self-contained | **yes** — key table hidden in the video (stego) | no — needs a separate static key image |
| human needs key | **no** — motion segregation reads it directly | yes — overlay the key image (transparency / client-side) |
| if motion is broken perfectly | partial leak — the scrambled letter is still visible | **zero leak** — provably independent of the message |
| complexity | medium | high |

Short version: **1+4** is the better *practical* scheme — self-contained and
key-free for humans — but its security is computational and a keyless break
leaks a scrambled-but-visible letter. **Approach 3** is the only
information-theoretically secure option (the video alone is provably
zero-information), at the cost of a second artifact and key management for both
humans and machines.

## Usage

```bash
pip install -r requirements.txt
python generate.py                                   # original + keyed (1+4): videos + figures
python generate.py --message "READ ME" --key "s3cret"
python generate.py --no-video                        # figures only (fast)

python compare.py                                    # Approach 3 + the 1+4-vs-3 comparison
python compare.py --no-video                         # comparison figure only (fast)
```

Programmatic:

```python
from ghostfont import (GhostFontConfig, encode_original, encode_keyed,
                       encode_visualcrypto, derive_key)
from ghostfont.decode import recover_optical_flow, recover_keyed_from_video
from ghostfont import visualcrypto as vc

cfg = GhostFontConfig(message="GHOST")
res = encode_original(cfg)                     # res.frames: (N, H, W) float in [0,1]
letter = recover_optical_flow(res.frames)      # key-free break of the original

key = derive_key("open sesame")
kr = encode_keyed(cfg, key)                    # 1+4: per-band scrambled frames
# ... embed_key_payload → rgb frames → recover_keyed_from_video(rgb, cfg, key)

r = vc.encode_visualcrypto(cfg, key)           # Approach 3: share-1 in the video
_, revealed = vc.recover_message(r.frames, cfg, key, r.enc_share2)   # XOR reveal
```

## Layout

```
ghostfont/
  config.py         parameter dataclasses (canvas, motion, decoy, keyed, vc)
  raster.py         text → binary glyph mask (RasterizeGlyphs)
  kinematogram.py   texture-composite engine (Stages 2–4), global & banded
  crypto.py         PRF (HMAC-SHA256), AES-256-GCM, LSB stego, band-table codec
  encoders.py       encode_original / encode_keyed / stego embedding
  visualcrypto.py   Approach 3: random-grid VC split, encode, recover
  decode.py         frame-average, optical-flow break, keyed recovery
  viz.py            shared matplotlib style + gif/mp4 writers
generate.py         builds original + keyed videos + analysis figures
compare.py          builds Approach 3 + the 1+4-vs-3 comparison
```

## Caveats (from the source documents)

- Ghost Font is **obfuscation, not encryption** — the original is fully
  defeatable by optical flow, and this repo demonstrates that break.
- The **1+4** variant provides *computational* security (AES / PRF); **Approach
  3** provides *information-theoretic* security for the video alone, at the cost
  of a second (key-image) artifact.
- Approach 3's information-theoretic guarantee is about the *video*; the key
  image is still protected only computationally (AES-256 on share-2).
- Resistance assumes AI processes video frame-by-frame; **video-native motion
  models would defeat the core evasion.** The keyed layers still require `K`.

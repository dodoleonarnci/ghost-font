# Ghost Font — Key-Encrypted Extension: Design Plan

**Goal:** Produce a video where humans can still read the moving-dot message visually, but an AI model can *only* decode it if it also holds a secret key `K`. Without `K`, even a sophisticated agent with local code execution and optical-flow tools cannot recover the true message.

This document proposes four independent (and potentially combinable) approaches. Each is analyzed for human transparency, keyed-AI access, and security.

---

## Background: Why the Original Algorithm Falls Short

The `ghost-font-breaker` tool demonstrated that Ghost Font is fully defeatable by:

1. Estimating scroll velocity via optical flow.
2. Applying motion-compensated temporal integration.
3. Running OCR on the recovered image.

None of these steps require any secret. The signal motion parameters (`v`, direction, wobble) are embedded openly in the video's temporal statistics and are recoverable by any competent computer vision pipeline. Encrypting the *content* therefore requires making at least one of these three steps require knowledge of `K`.

---

## Approach 1 — Key-Derived Velocity Scrambling

### Core Idea

Instead of using a single, globally uniform scroll velocity, use a different, seemingly random velocity (direction and magnitude) for each **column band** of pixels. The column-to-velocity mapping is derived from a cryptographic PRF keyed by `K`. A human watching the video still perceives a unified motion-defined message because the human visual system integrates motion fields across the whole image (biological motion segregation is robust to local velocity variation). An AI agent running optical flow or motion compensation must apply exactly the right velocity to each column band; without `K` it cannot know the mapping.

### Construction

Let the canvas be divided into $B$ equal vertical bands indexed $b \in \{0, 1, \ldots, B-1\}$, each of width $W/B$ pixels.

1. **Key expansion.** Derive a per-band velocity table:
   $$v_b = v_{\min} + (v_{\max} - v_{\min}) \cdot \mathrm{PRF}_K(b) \bmod 1$$
   where $\mathrm{PRF}_K$ is HMAC-SHA256 truncated to $[0, 1)$.

2. **Direction bit.** Optionally also derive per-band direction:
   $$d_b = \mathrm{PRF}_K(B + b) \bmod 2 \in \{-1, +1\}$$
   so bands may scroll up or down with independently varying speeds.

3. **Signal particle assignment.** Particles are still seeded from the letter mask. Their motion is governed by $(d_b \cdot v_b)$ where $b$ is determined by the particle's *current* x-position (or initial x-position, for simplicity).

4. **Decoy.** A standard static decoy is embedded as before.

### Keyed AI Decoding

An AI given `K` runs the inverse operation: reconstruct $v_b$ and $d_b$ for each band, apply band-local motion-compensated integration, and stitch the bands back together to recover $\mathcal{M}$.

### Human Transparency

Humans perceive motion-defined boundaries even when local velocities vary moderately. Studies of biological motion and random-dot kinematograms show that direction contrast (up vs. down) is the primary cue, and ±30% velocity variation across bands remains perceptible. Choose $v_{\min}$ and $v_{\max}$ to keep the ratio $v_{\max}/v_{\min} \lesssim 2$ and letter-edge contrast is preserved.

### Security Analysis

A keyless attacker running dense optical flow obtains a *field* of velocity estimates, not a single global velocity. To perform motion compensation they must know which velocity to apply to which band. With $B = 16$ bands and 256 possible quantized velocities per band, the brute-force search space is $256^{16} \approx 2^{128}$—computationally infeasible. Even coarser quantization ($B=8$, 16 velocities each) gives $16^8 = 2^{32}$, which is at the feasibility boundary; $B=16$ with continuous velocities provides practical security.

**Caveat:** If $B$ is small and the attacker observes that each band independently has a coherent velocity, they can solve each band independently via optical flow—at cost $O(B \cdot \text{flow cost})$, not $O(\text{brute force})$. To close this, couple the bands by making the per-band velocity depend on a *global* nonce that is not embedded in the video; or use Approach 3 (frame permutation) in conjunction.

---

## Approach 2 — Cryptographic Frame Permutation

### Core Idea

The frames of the video are output in a shuffled order determined by `K`. A human watching the video in shuffle order still sees motion—the visual system integrates short motion bursts from each scrambled subsequence and the human perceptual system fills in the rest, especially if each frame is shown for only ≈33 ms. An AI analyzing the frame sequence in the wrong order cannot reconstruct the coherent motion trajectory needed for motion-compensated integration.

### Construction

1. **Generate** the canonical $N_f$ frames $F_0, \ldots, F_{N_f-1}$ using the standard Ghost Font algorithm.

2. **Key-derived permutation.** Generate a random permutation $\pi: [N_f] \to [N_f]$ using a Fisher-Yates shuffle seeded by HMAC-SHA256(`K`, "frame-perm").

3. **Output video** $G_i = F_{\pi(i)}$ for $i = 0, \ldots, N_f-1$.

4. Optionally, embed an additional *timing track*: the true timestamps $(n, \pi^{-1}(n))$ are encoded steganographically in the LSBs of a border region, encrypted under `K`, so a keyed decoder can reconstruct the correct ordering even from a single-pass video read.

### Keyed AI Decoding

The AI given `K`:
1. Reconstructs $\pi$ from the key.
2. Reorders frames: $F_n = G_{\pi^{-1}(n)}$.
3. Applies standard motion-compensated integration.

### Human Transparency

Human motion perception operates on very short time windows (~80–150 ms). If the permutation is a *block permutation* (blocks of $k$ consecutive frames are permuted as units, not individual frames), human viewers perceive smooth motion within each block and tolerate the inter-block jumps as mild flicker. The message remains legible, though readability is degraded versus the canonical ordering. Choosing block size $k = 3$–$5$ frames ($\approx 100$–$170$ ms at 30 fps) balances human legibility with scrambling strength.

### Security Analysis

A keyless attacker observes $G_0, \ldots, G_{N_f-1}$ and needs to recover $\pi$. If no temporal cues survive permutation, the correct ordering among $N_f!$ permutations cannot be determined from the video alone. In practice, the attacker can try to reconstruct $\pi$ by finding the ordering that minimizes inter-frame optical flow discontinuities—effectively a travelling salesman problem over frame-similarity distances, with complexity $\mathcal{O}(N_f!)$ in the worst case and heuristic polynomial solutions. Mitigations:

- Use $N_f \geq 60$ frames (2 seconds at 30 fps). At this size, TSP heuristics produce poor solutions.
- Ensure frames are visually nearly identical (they are—all frames look like random noise), so frame-similarity distances give no useful signal.
- Combine with Approach 1 to ensure that even after correct reordering, a further velocity key is needed.

---

## Approach 3 — Visual Cryptography Share (Static + Motion)

### Core Idea

Inspired by Naor–Shamir visual cryptography (1994): split the message into two *shares* such that neither share alone reveals the message, but overlaying them does. Here, one share is the video (publicly distributed), and the second share is a static key image $K_{\mathrm{img}}$ derived from `K`. Humans overlay $K_{\mathrm{img}}$ on their screen (printed transparency, second monitor, or composited client-side) to see the message. An AI given the raw video and `K` synthesizes $K_{\mathrm{img}}$ computationally and composites.

### Construction

1. **Generate the letter mask** $\mathcal{M}$.

2. **Split into shares.** For each pixel $(x, y)$:
   - If $\mathcal{M}(x, y) = 1$ (inside a glyph): assign random complementary dot patterns to share-1 and share-2 such that their XOR (or OR, depending on the scheme) produces a dark pixel.
   - If $\mathcal{M}(x, y) = 0$ (background): assign identical random dot patterns to both shares.

3. **Embed share-1** as the motion-signal population in the video (i.e., dots that move upward are drawn from share-1's pixel set). Share-2 is the static key image.

4. **Key image $K_{\mathrm{img}}$** is itself encrypted under `K` and published separately (QR code, URL parameter, side-channel). Without the decryption of $K_{\mathrm{img}}$, an observer sees only share-1's random dots in motion.

### Keyed AI Decoding

The AI decrypts $K_{\mathrm{img}}$ using `K`, composites it with the motion-compensated integral of the video, and reads the resulting high-contrast letter image.

### Human Transparency

Human viewing: print or display $K_{\mathrm{img}}$ as a physical transparency and hold it against the screen, or composite it client-side in a browser that receives the key via a JavaScript `crypto.subtle` operation before rendering. This is the most mechanically demanding of the four approaches for human users—it requires a second artifact—but it provides the strongest baseline security guarantee (information-theoretically, the video alone reveals nothing).

### Security Analysis

Under classical Naor–Shamir visual cryptography, share-1 alone is information-theoretically independent of $\mathcal{M}$. The motion-embedding of share-1 inherits this property: a keyless attacker running full motion compensation recovers only share-1's random dot pattern, which carries zero information about the message. Security reduces to the security of the symmetric encryption of $K_{\mathrm{img}}$—i.e., AES-256 or ChaCha20-Poly1305 under `K`.

This is the **only approach among the four with information-theoretic security** (when the VC split is pure XOR). The others provide computational security only.

---

## Approach 4 — Steganographic Motion Key (Self-Contained Video)

### Core Idea

Embed the key material needed for motion compensation *inside the video itself*, but encrypted under `K`. The video is self-contained: a keyed AI extracts the embedded motion parameters, uses them to decode the message, and reads it. A keyless AI cannot extract the parameters. Humans see the message directly via biological motion perception and need no key at all.

### Construction

This approach targets the threat model where the *AI* needs to decode it, but ordinary human viewers should not need any out-of-band secret.

1. **Choose random, unusual motion parameters** $\theta = (v, \mathrm{direction\ encoding}, w_x, w_y, \omega_x, \omega_y, \pi_{\mathrm{bands}})$ for the Ghost Font encoding. These are *not* the standard public defaults.

2. **Encrypt $\theta$** under `K`: $C_\theta = \mathrm{Enc}_K(\theta)$.

3. **Embed $C_\theta$** in the video via robust steganography:
   - Spread-spectrum LSB encoding in the blue channel of a fixed border strip.
   - Or encode in the dot-density variation of a reserved corner region across frames (covert channel via temporal modulation of density).
   - Or embed as an audio track if the container supports it.

4. **Human viewing:** unchanged. The dot motion is still visible to human eyes regardless of what parameters were used.

5. **Keyed AI decoding pipeline:**
   1. Extract $C_\theta$ from the steganographic channel.
   2. Decrypt: $\theta = \mathrm{Dec}_K(C_\theta)$.
   3. Apply motion-compensated integration with the recovered $\theta$.
   4. OCR the result.

### Security Analysis

A keyless attacker can:
- Extract $C_\theta$ from the steganographic channel (if they know where to look).
- But cannot decrypt it without `K`.
- Even knowing the steganographic channel location, brute-force key search against AES-256 or ChaCha20 is infeasible.

If the attacker does *not* know the steganographic scheme, they face an additional layer: they must identify the covert channel among all possible embeddings. Applying a publicly known scheme (spread-spectrum LSB with a documented seed) removes this layer, leaving only the cryptographic hardness of decrypting `K`—which is sufficient.

**Trade-off vs. Approach 3:** This approach makes the video fully self-contained (no side-channel for the key image required) at the cost of weaker security guarantees (computational vs. information-theoretic).

---

## Comparison Table

| Approach | Human needs key? | AI needs key? | Security model | Self-contained? | Complexity |
|---|---|---|---|---|---|
| 1 — Velocity Scrambling | No | Yes | Computational (PRF) | Yes | Medium |
| 2 — Frame Permutation | No (slight flicker) | Yes | Computational (permutation search) | Yes | Low |
| 3 — Visual Cryptography | Yes (key image) | Yes | **Information-theoretic** | No | High |
| 4 — Steganographic Key | No | Yes | Computational (AES) | Yes | Medium |

---

## Recommended Combination

For the strongest practical scheme while keeping the video self-contained and humans key-free:

> **Approach 1 + Approach 4 combined**

- Approach 4 embeds the band-velocity table $\{v_b\}$ (from Approach 1) as encrypted steganographic payload inside the video.
- Humans watch freely—biological motion perception is robust to variable velocities.
- An AI with `K` extracts and decrypts $\{v_b\}$, applies per-band motion compensation, and recovers the message.
- A keyless AI sees only noise or the decoy honeypot.

For maximum security (at the cost of human-side key management):

> **Approach 3 (Visual Cryptography)**

This is the only approach offering information-theoretic security. The video alone is provably zero-information about the message; the key image is required for both human and AI reading.

---

## Implementation Notes

- **Key format:** A 256-bit random secret `K`, shared out-of-band (QR code, passphrase via KDF, URL fragment `#key=<base64>`).
- **PRF:** HMAC-SHA256 for parameter derivation; AES-256-GCM or ChaCha20-Poly1305 for payload encryption.
- **Steganography robustness:** Video compression (H.264, VP9) destroys LSB channels. Use DCT-domain embedding or high-amplitude spread-spectrum encoding to survive lossy compression.
- **Human legibility testing:** For Approach 1, empirically validate readability across band counts $B \in \{4, 8, 16\}$ before choosing a production value.
- **Decoy layer:** Retain the original Ghost Font decoy in all approaches. It continues to serve as a honeypot that gives keyless AI systems a confident but wrong answer, reducing the probability that they attempt further analysis.

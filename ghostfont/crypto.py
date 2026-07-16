"""Cryptographic primitives for the key-encrypted Ghost Font extension.

- ``PRF_K`` : HMAC-SHA256 keyed pseudo-random function, used for the
  per-band velocity table (Approach 1, "Key expansion").
- ``encrypt`` / ``decrypt`` : AES-256-GCM authenticated encryption of the
  serialized band table (Approach 4 payload; plan Implementation Notes).
- ``embed_lsb`` / ``extract_lsb`` : least-significant-bit steganography in a
  border strip (Approach 4, "Spread-spectrum LSB encoding in ... a fixed
  border strip"). Redundant across frames for robustness.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct

import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_MAGIC = b"GFK1"  # Ghost-Font-Keyed v1 payload marker.


# ---------------------------------------------------------------------------
# Pseudo-random function (parameter derivation)
# ---------------------------------------------------------------------------
def prf_unit(key: bytes, index: int, label: bytes = b"band") -> float:
    """HMAC-SHA256(key, label||index) mapped uniformly to [0, 1)."""
    msg = label + struct.pack(">I", index)
    digest = hmac.new(key, msg, hashlib.sha256).digest()
    # Use the top 53 bits for a double in [0, 1).
    val = int.from_bytes(digest[:8], "big") >> 11
    return val / float(1 << 53)


def prf_bit(key: bytes, index: int, label: bytes = b"dir") -> int:
    msg = label + struct.pack(">I", index)
    digest = hmac.new(key, msg, hashlib.sha256).digest()
    return digest[0] & 1


def derive_key(passphrase: str) -> bytes:
    """Derive a 256-bit key from a passphrase (scrypt KDF; plan: passphrase via
    KDF). For demos a fixed salt keeps the key reproducible."""
    return hashlib.scrypt(
        passphrase.encode("utf-8"),
        salt=b"ghost-font-static-demo-salt",
        n=2 ** 14,
        r=8,
        p=1,
        dklen=32,
    )


# ---------------------------------------------------------------------------
# Authenticated encryption
# ---------------------------------------------------------------------------
def encrypt(key: bytes, plaintext: bytes) -> bytes:
    """AES-256-GCM. Output = nonce(12) || ciphertext || tag(16)."""
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext, _MAGIC)
    return nonce + ct


def decrypt(key: bytes, blob: bytes) -> bytes:
    nonce, ct = blob[:12], blob[12:]
    return AESGCM(key).decrypt(nonce, ct, _MAGIC)


# ---------------------------------------------------------------------------
# Band-table serialization
# ---------------------------------------------------------------------------
def serialize_band_table(
    band_speeds: np.ndarray, band_signs: np.ndarray
) -> bytes:
    """Pack the per-band velocity table into bytes.

    Speeds are quantized to 16-bit fixed point (1/256 px precision); signs are
    packed one bit per band.
    """
    b = len(band_speeds)
    q = np.clip(np.round(band_speeds * 256.0), 0, 65535).astype(">u2")
    sign_bits = ((band_signs > 0).astype(np.uint8))
    packed_signs = np.packbits(sign_bits)
    header = _MAGIC + struct.pack(">H", b)
    return header + q.tobytes() + packed_signs.tobytes()


def deserialize_band_table(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    if data[:4] != _MAGIC:
        raise ValueError("bad band-table magic")
    (b,) = struct.unpack(">H", data[4:6])
    off = 6
    q = np.frombuffer(data[off : off + 2 * b], dtype=">u2").astype(np.float64)
    off += 2 * b
    speeds = q / 256.0
    n_sign_bytes = (b + 7) // 8
    sign_bits = np.unpackbits(
        np.frombuffer(data[off : off + n_sign_bytes], dtype=np.uint8)
    )[:b]
    signs = np.where(sign_bits > 0, 1.0, -1.0)
    return speeds, signs


# ---------------------------------------------------------------------------
# LSB steganography in a border strip
# ---------------------------------------------------------------------------
def _payload_with_length(blob: bytes) -> np.ndarray:
    framed = struct.pack(">I", len(blob)) + blob
    return np.unpackbits(np.frombuffer(framed, dtype=np.uint8))


def embed_lsb(
    frame: np.ndarray, blob: bytes, border_px: int, channel: int
) -> np.ndarray:
    """Embed ``blob`` (length-prefixed) into LSBs of a border strip.

    ``frame`` is an HxWx3 uint8 RGB array. The border strip is the top+bottom
    ``border_px`` rows plus left+right columns. Bits are written raster order
    and repeated to fill the strip (redundancy survives per-frame reads).
    """
    out = frame.copy()
    h, w, _ = out.shape
    mask = np.zeros((h, w), dtype=bool)
    mask[:border_px, :] = True
    mask[-border_px:, :] = True
    mask[:, :border_px] = True
    mask[:, -border_px:] = True
    idx = np.argwhere(mask)
    bits = _payload_with_length(blob)
    capacity = len(idx)
    if len(bits) > capacity:
        raise ValueError(
            f"payload {len(bits)} bits exceeds border capacity {capacity} bits"
        )
    # Tile the payload bits across the whole strip for redundancy.
    reps = capacity // len(bits)
    tiled = np.tile(bits, reps + 1)[:capacity]
    ch = out[:, :, channel]
    ys, xs = idx[:, 0], idx[:, 1]
    ch[ys, xs] = (ch[ys, xs] & 0xFE) | tiled
    out[:, :, channel] = ch
    return out


def extract_lsb(frame: np.ndarray, border_px: int, channel: int) -> bytes:
    """Recover the length-prefixed blob embedded by :func:`embed_lsb`."""
    h, w, _ = frame.shape
    mask = np.zeros((h, w), dtype=bool)
    mask[:border_px, :] = True
    mask[-border_px:, :] = True
    mask[:, :border_px] = True
    mask[:, -border_px:] = True
    idx = np.argwhere(mask)
    ch = frame[:, :, channel]
    lsbs = (ch[idx[:, 0], idx[:, 1]] & 1).astype(np.uint8)
    length_bits = lsbs[:32]
    (length,) = struct.unpack(">I", np.packbits(length_bits).tobytes())
    total_bits = 32 + length * 8
    payload_bits = lsbs[32:total_bits]
    return np.packbits(payload_bits).tobytes()

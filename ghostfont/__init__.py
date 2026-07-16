"""Ghost Font: motion-encoded anti-AI typography, plus a key-encrypted variant.

Two implementations:

* ``encode_original`` - the original Ghost Font (a dual-population,
  opposing-direction random-dot kinematogram) as formalized in
  ``ghost_font_algorithm.tex``.
* ``encode_keyed`` / ``embed_key_payload`` - the key-encrypted extension
  combining Approach 1 (key-derived per-band velocity scrambling) and
  Approach 4 (steganographic embedding of the encrypted band table) from
  ``ghost_font_key_encryption_plan.md``.
"""

from .config import (
    CanvasConfig,
    DecoyConfig,
    GhostFontConfig,
    KeyedConfig,
    MotionConfig,
    VisualCryptoConfig,
)
from .crypto import derive_key
from .encoders import (
    EncodeResult,
    embed_key_payload,
    encode_keyed,
    encode_original,
    frames_to_rgb,
)
from .visualcrypto import VCResult, encode_visualcrypto

__all__ = [
    "GhostFontConfig",
    "CanvasConfig",
    "MotionConfig",
    "DecoyConfig",
    "KeyedConfig",
    "EncodeResult",
    "encode_original",
    "encode_keyed",
    "embed_key_payload",
    "frames_to_rgb",
    "derive_key",
    "VisualCryptoConfig",
    "VCResult",
    "encode_visualcrypto",
]

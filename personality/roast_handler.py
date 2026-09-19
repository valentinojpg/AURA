"""
AURA — Módulo de compatibilidad para personality.roast_handler.
Re-exporta todo desde aura.personality.roast_handler.
"""

from aura.personality.roast_handler import (
    generate_roast,
    get_fallback_roast,
    handle_roast_complaint,
)

__all__ = [
    "generate_roast",
    "get_fallback_roast",
    "handle_roast_complaint",
]

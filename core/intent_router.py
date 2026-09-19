"""
AURA — Módulo de compatibilidad para core.intent_router.
Re-exporta todo desde aura.core.intent_router.
"""

from aura.core.intent_router import (
    Intent,
    IntentRouter,
    intent_router,
    normalize,
    parse,
)

__all__ = [
    "Intent",
    "IntentRouter",
    "intent_router",
    "normalize",
    "parse",
]

"""
AURA — Módulo de compatibilidad para personality.jokes.
Re-exporta todo desde aura.personality.jokes.
"""

from aura.personality.jokes import (
    VALID_STYLES,
    PROHIBITED_OPENINGS,
    load_jokes_data,
    format_joke_obj,
    get_fallback_joke,
    has_prohibited_opening,
    validate_joke_output,
    resolve_joke_style,
    generate_joke,
    handle_joke_complaint,
    get_last_joke_state,
)

__all__ = [
    "VALID_STYLES",
    "PROHIBITED_OPENINGS",
    "load_jokes_data",
    "format_joke_obj",
    "get_fallback_joke",
    "has_prohibited_opening",
    "validate_joke_output",
    "resolve_joke_style",
    "generate_joke",
    "handle_joke_complaint",
    "get_last_joke_state",
]

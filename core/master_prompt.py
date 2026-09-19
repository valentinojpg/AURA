"""
AURA — Módulo de compatibilidad para core.master_prompt.
Re-exporta todo desde aura.core.master_prompt.
"""

from aura.core.master_prompt import (
    PROMPT_NUCLEO,
    PROMPT_MODULO_INTERPRETE,
    PROMPT_MODULO_CHAT,
    PROMPT_MODULO_HUMOR,
    PROMPT_MODULO_PROGRAMACION,
    PROMPT_EJEMPLOS,
    is_small_model,
    build_master_prompt,
    assemble_prompt,
)

__all__ = [
    "PROMPT_NUCLEO",
    "PROMPT_MODULO_INTERPRETE",
    "PROMPT_MODULO_CHAT",
    "PROMPT_MODULO_HUMOR",
    "PROMPT_MODULO_PROGRAMACION",
    "PROMPT_EJEMPLOS",
    "is_small_model",
    "build_master_prompt",
    "assemble_prompt",
]


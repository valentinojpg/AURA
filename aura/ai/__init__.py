"""
AURA ORION — Módulo de IA (Fase 69)
"""

from aura.ai.prompt_assembler import (
    assemble_prompt,
    build_master_prompt,
    is_small_model,
    load_maestro_sections,
    PROMPT_NUCLEO,
    PROMPT_MODULO_INTERPRETE,
    PROMPT_MODULO_CHAT,
    PROMPT_MODULO_HUMOR,
    PROMPT_MODULO_PROGRAMACION,
    PROMPT_EJEMPLOS,
)

__all__ = [
    "assemble_prompt",
    "build_master_prompt",
    "is_small_model",
    "load_maestro_sections",
    "PROMPT_NUCLEO",
    "PROMPT_MODULO_INTERPRETE",
    "PROMPT_MODULO_CHAT",
    "PROMPT_MODULO_HUMOR",
    "PROMPT_MODULO_PROGRAMACION",
    "PROMPT_EJEMPLOS",
]

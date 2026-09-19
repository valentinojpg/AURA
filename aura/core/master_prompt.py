"""
AURA ORION — PROMPT MAESTRO DE RAZONAMIENTO E INTERPRETACIÓN
Fuente única de verdad sobre cómo AURA piensa, interpreta y decide.
Módulo de compatibilidad: re-exporta y delega en aura.ai.prompt_assembler.
"""

from aura.ai.prompt_assembler import (
    PROMPT_NUCLEO,
    PROMPT_MODULO_INTERPRETE,
    PROMPT_MODULO_CHAT,
    PROMPT_MODULO_HUMOR,
    PROMPT_MODULO_PROGRAMACION,
    PROMPT_EJEMPLOS,
    is_small_model,
    assemble_prompt,
    build_master_prompt,
    load_maestro_sections,
)

__all__ = [
    "PROMPT_NUCLEO",
    "PROMPT_MODULO_INTERPRETE",
    "PROMPT_MODULO_CHAT",
    "PROMPT_MODULO_HUMOR",
    "PROMPT_MODULO_PROGRAMACION",
    "PROMPT_EJEMPLOS",
    "is_small_model",
    "assemble_prompt",
    "build_master_prompt",
    "load_maestro_sections",
]

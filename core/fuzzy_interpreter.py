"""
AURA — Módulo de compatibilidad para core.fuzzy_interpreter.
Re-exporta todo desde aura.core.fuzzy_interpreter.
"""

from aura.core.fuzzy_interpreter import (
    InterpretationResult,
    TypoMemory,
    typo_memory,
    normalize_aggressive,
    generate_target_variants,
    FuzzyInterpreter,
    fuzzy_interpreter,
    KNOWN_VERBS_CONFIG,
    COMMON_DOC_KEYWORDS,
)

__all__ = [
    "InterpretationResult",
    "TypoMemory",
    "typo_memory",
    "normalize_aggressive",
    "generate_target_variants",
    "FuzzyInterpreter",
    "fuzzy_interpreter",
    "KNOWN_VERBS_CONFIG",
    "COMMON_DOC_KEYWORDS",
]

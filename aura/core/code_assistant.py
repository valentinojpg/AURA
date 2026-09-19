"""
AURA — Módulo de compatibilidad para aura.core.code_assistant (Fase 26).
Re-exporta todo desde core.code_assistant.
"""

from core.code_assistant import (
    CodeAction,
    CodeAnalysis,
    CodeTaskResult,
    CodeAssistant,
    code_assistant,
    detect_language,
    extract_code_blocks,
    extract_first_code_block,
    analyze_code,
    build_prompt,
)

__all__ = [
    "CodeAction",
    "CodeAnalysis",
    "CodeTaskResult",
    "CodeAssistant",
    "code_assistant",
    "detect_language",
    "extract_code_blocks",
    "extract_first_code_block",
    "analyze_code",
    "build_prompt",
]

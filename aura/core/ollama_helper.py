"""
AURA — Re-export de compatibilidad para aura.core.ollama_helper (Fase 30)
"""

from core.ollama_helper import (
    RECOMMENDED_MODELS,
    is_ollama_installed,
    check_ollama_service,
    get_installation_instructions,
    format_ollama_guide_text,
)

__all__ = [
    "RECOMMENDED_MODELS",
    "is_ollama_installed",
    "check_ollama_service",
    "get_installation_instructions",
    "format_ollama_guide_text",
]

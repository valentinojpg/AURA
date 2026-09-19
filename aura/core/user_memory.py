"""
AURA — Módulo de exportación de compatibilidad para user_memory (Fase 28).
Re-exporta todo desde core.user_memory.
"""

from core.user_memory import (
    DEFAULT_MEMORY_DIR,
    DEFAULT_MEMORY_FILE,
    PathMemoryEntry,
    ProgramUsageEntry,
    ProjectContextEntry,
    UserFact,
    UserMemory,
    detect_project_type,
    user_memory,
)

__all__ = [
    "DEFAULT_MEMORY_DIR",
    "DEFAULT_MEMORY_FILE",
    "PathMemoryEntry",
    "ProgramUsageEntry",
    "ProjectContextEntry",
    "UserFact",
    "UserMemory",
    "detect_project_type",
    "user_memory",
]

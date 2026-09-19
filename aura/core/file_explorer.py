"""
AURA — Módulo de compatibilidad para aura.core.file_explorer (Fase 24).
Re-exporta todo desde core.file_explorer.
"""

from core.file_explorer import (
    FileExplorer,
    FileItem,
    FolderSummary,
    QuickAccessItem,
    ProjectInfo,
    detect_project,
    format_bytes,
    format_datetime,
    get_type_and_icon,
)

__all__ = [
    "FileExplorer",
    "FileItem",
    "FolderSummary",
    "QuickAccessItem",
    "ProjectInfo",
    "detect_project",
    "format_bytes",
    "format_datetime",
    "get_type_and_icon",
]

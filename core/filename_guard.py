"""
AURA — Módulo de compatibilidad para core.filename_guard.
Re-exporta todo desde aura.core.filename_guard.
"""

from aura.core.filename_guard import (
    is_valid_strict_filename,
    resolve_folder_alias,
    resolve_path_with_alias,
    get_known_folder_path,
    COMMAND_STOPWORDS,
    COMMAND_PHRASES,
)

__all__ = [
    "is_valid_strict_filename",
    "resolve_folder_alias",
    "resolve_path_with_alias",
    "get_known_folder_path",
    "COMMAND_STOPWORDS",
    "COMMAND_PHRASES",
]

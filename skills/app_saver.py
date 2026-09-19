"""
AURA — Módulo de compatibilidad para skills.app_saver.
Re-exporta todo desde aura.skills.app_saver.
"""

from aura.skills.app_saver import (
    AppSaverSkill,
    save_app_document,
    resolve_running_app_pid,
    extract_text_from_window,
    find_edit_control,
)

__all__ = [
    "AppSaverSkill",
    "save_app_document",
    "resolve_running_app_pid",
    "extract_text_from_window",
    "find_edit_control",
]

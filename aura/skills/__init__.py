"""
AURA — Paquete aura.skills
"""

from aura.skills.app_writer import (
    AppWriterSkill,
    write_in_app,
    record_app_opened,
    get_last_opened_pid,
    clear_last_opened_apps,
    last_opened_apps,
)

__all__ = [
    "AppWriterSkill",
    "write_in_app",
    "record_app_opened",
    "get_last_opened_pid",
    "clear_last_opened_apps",
    "last_opened_apps",
]

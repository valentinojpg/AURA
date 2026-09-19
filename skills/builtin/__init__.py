"""
AURA — Paquete de Skills builtin (Fase 11+14+15+16+17+18+19)

Este paquete contiene todas las skills incluidas con AURA.
El SkillRegistry usa este paquete para el descubrimiento automático.
"""

from skills.builtin.demo_skill import DemoSkill
from skills.builtin.system_skill import SystemSkill
from skills.builtin.files_skill import FilesSkill
from skills.builtin.search_skill import SearchSkill
from skills.builtin.programs_skill import ProgramsSkill
from skills.builtin.web_skill import WebSkill
from skills.builtin.automation_skill import AutomationSkill
from skills.builtin.app_saver import AppSaverSkill

__all__ = [
    "DemoSkill",
    "SystemSkill",
    "FilesSkill",
    "SearchSkill",
    "ProgramsSkill",
    "WebSkill",
    "AutomationSkill",
    "AppSaverSkill",
]

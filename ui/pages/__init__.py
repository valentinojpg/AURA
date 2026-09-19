"""
AURA — Paquete de páginas de la interfaz (Fase 3)

Exporta todas las páginas disponibles de la aplicación.
"""

from ui.pages.base_page import BasePage
from ui.pages.chat_page import ChatPage
from ui.pages.skills_page import SkillsPage
from ui.pages.automation_page import AutomationPage
from ui.pages.files_page import FilesPage
from ui.pages.code_page import CodePage, CodeAssistantPage
from ui.pages.settings_page import SettingsPage

__all__ = [
    "BasePage",
    "ChatPage",
    "SkillsPage",
    "AutomationPage",
    "FilesPage",
    "CodePage",
    "CodeAssistantPage",
    "SettingsPage",
]

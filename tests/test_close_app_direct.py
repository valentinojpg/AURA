"""
AURA — Tests Unitarios para Cierre de Aplicaciones Sin Confirmación (Fase 53)
"""

import subprocess
import threading
import time
from unittest.mock import MagicMock, patch

import psutil
import pytest
import flet as ft

from config.settings import settings
from skills.builtin.system_skill import SystemSkill
from skills.skill_base import SkillResult
from automation.engine import AutomationEngine
from aura.core.entity_resolver import entity_resolver
from ui.pages.chat_page import ChatPage
from voice.voice_command_handler import DANGEROUS_COMMAND_PREFIXES, get_voice_command_handler


class TestSystemSkillCloseApp:
    """Verifica el comando 'cerrar' de SystemSkill con psutil y match normalizado."""

    def test_close_without_args(self):
        skill = SystemSkill()
        res = skill.execute("cerrar", [])
        assert res.success is False
        assert "especificá" in res.error.lower() or "proceso" in res.error.lower()

    def test_close_protected_process_fails(self):
        skill = SystemSkill()
        res = skill.execute("cerrar", ["explorer.exe"])
        assert res.success is False
        assert "crítico" in res.error.lower()

    def test_close_non_running_process(self):
        skill = SystemSkill()
        res = skill.execute("cerrar", ["proceso_fantasma_inexistente_9999"])
        assert res.success is False
        assert "ℹ️ 'proceso_fantasma_inexistente_9999' no estaba en ejecución." in res.error
        assert res.data.get("running") is False

    def test_close_running_process_real(self):
        """Abre un notepad real y lo cierra inmediatamente sin confirmación."""
        proc = subprocess.Popen(["notepad.exe"])
        time.sleep(0.5)
        try:
            assert proc.poll() is None  # Está corriendo

            skill = SystemSkill()
            res = skill.execute("cerrar", ["notepad"])
            assert res.success is True
            assert res.output == "✅ Proceso cerrado."
            assert res.data.get("running") is True
            assert res.data.get("killed", 0) >= 1

            # Verificar que ya no está corriendo
            time.sleep(0.3)
            assert proc.poll() is not None or not psutil.pid_exists(proc.pid)
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_close_normalized_match_with_accents(self):
        """Verifica que el match normalizado sin tildes funciona (ej: calcúladora o próceso)."""
        skill = SystemSkill()
        # "cálculadora" normalizado mapea a calc.exe
        res = skill.execute("cerrar", ["cálculadora_inexistente_xyz"])
        assert "no estaba en ejecución" in res.error


class TestSettingsConfirmationFlag:
    """Verifica la clave CONFIRMAR_CIERRE_APP en settings."""

    def test_default_is_false(self):
        val = settings.get_bool("CONFIRMAR_CIERRE_APP", fallback=False)
        assert val is False


class TestChatPageCloseAppFlow:
    """Verifica el flujo en el chat para close_app."""

    def test_close_app_direct_flow_not_running(self):
        page_mock = MagicMock(spec=ft.Page)
        chat = ChatPage(page=page_mock)
        chat.build()

        with patch.object(chat, "_send_to_ai") as mock_ai:
            chat.handle_user_message("cerrá aplicacion_inexistente_12345", origen="chat")
            # No debe pedir confirmación modal
            assert chat._pending_confirm_action is None
            mock_ai.assert_not_called()

    def test_close_app_with_confirmation_when_configured_true(self):
        page_mock = MagicMock(spec=ft.Page)
        chat = ChatPage(page=page_mock)
        chat.build()

        with patch.object(settings, "get_bool", side_effect=lambda k, *a, **kw: True if k in ("CONFIRMAR_CIERRE_APP", "ROUTER_FIRST") else False), \
             patch.object(chat, "_handle_close_app_direct") as mock_direct:
            chat.handle_user_message("cerrá notepad", origen="chat")
            # Debe mostrar modal / setear _pending_confirm_action
            assert chat._pending_confirm_action is not None
            mock_direct.assert_not_called()

            # Confirmar acción
            chat._pending_confirm_action()
            mock_direct.assert_called_once()


class TestDangerousActionsKeepConfirmation:
    """Verifica que apagar, reiniciar, bloquear sesión y papelera SIGAN pidiendo confirmación."""

    def test_apagar_requires_ahora_dry_run(self):
        skill = SystemSkill()
        res = skill.execute("apagar", [])
        assert res.success is True
        assert "[SIMULACIÓN]" in res.output
        assert res.data.get("dry_run") is True
        assert "--ahora" in res.output

    def test_reiniciar_requires_ahora_dry_run(self):
        skill = SystemSkill()
        res = skill.execute("reiniciar", [])
        assert res.success is True
        assert "[SIMULACIÓN]" in res.output
        assert res.data.get("dry_run") is True
        assert "--ahora" in res.output

    def test_papelera_requires_ahora_dry_run(self):
        skill = SystemSkill()
        res = skill.execute("papelera", [])
        assert res.success is True
        assert "[SIMULACIÓN]" in res.output
        assert res.data.get("dry_run") is True
        assert "--ahora" in res.output

    def test_voice_dangerous_prefixes_include_critical_actions(self):
        assert "apagar" in DANGEROUS_COMMAND_PREFIXES
        assert "reiniciar" in DANGEROUS_COMMAND_PREFIXES
        assert "papelera" in DANGEROUS_COMMAND_PREFIXES
        assert "bloquear" in DANGEROUS_COMMAND_PREFIXES
        assert "cerrar" not in DANGEROUS_COMMAND_PREFIXES


class TestAutomationCloseAppStep:
    """Verifica que automatizaciones con close_app corran directo sin bloquearse."""

    def test_automation_step_close_app_dry_run(self):
        engine = AutomationEngine()
        step = {"type": "close_app", "app": "notepad"}
        res = engine._execute_step(0, step, dry_run=True)
        assert res.success is True
        assert "[SIMULADO] Cerraría: notepad" in res.output

    def test_automation_step_close_app_not_running(self):
        engine = AutomationEngine()
        step = {"type": "close_app", "app": "app_inexistente_xyz_77"}
        res = engine._execute_step(0, step, dry_run=False)
        assert res.success is True
        assert "no estaba en ejecución" in res.output

    def test_automation_step_close_app_real_notepad(self):
        proc = subprocess.Popen(["notepad.exe"])
        time.sleep(0.5)
        try:
            engine = AutomationEngine()
            step = {"type": "close_app", "app": "notepad"}
            res = engine._execute_step(0, step, dry_run=False)
            assert res.success is True
            assert res.output == "✅ Proceso cerrado."
        finally:
            if proc.poll() is None:
                proc.kill()

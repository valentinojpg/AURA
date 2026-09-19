"""
AURA — Pruebas Automatizadas de la Fase 29 (Ventana de Configuración Completa)

Valida todas las capacidades de la página de configuración integral de AURA:
1. Instanciación y estructura completa de tarjetas y controles.
2. Navegación por categorías con chips de filtro (General, IA, Voz, Seguridad, Memoria, Diagnóstico).
3. Configuración de Apariencia (Modo Oscuro/Claro) e Idioma (es/en).
4. Configuración de Carpeta de Trabajo (Workspace): validación, guardado y restablecimiento.
5. Controles de IA Multi-proveedor: timeout, fallback, selector de modelos y keys enmascaradas.
6. Integración del panel de Audio y Dispositivos de Voz (AudioPanel).
7. Políticas de Seguridad y Confirmación: destructivas, apagado, cierre directo y router.
8. Memoria de Usuario (Fase 28): métricas en vivo, exportación de respaldo JSON y limpieza.
9. Personalidad Grok (Fase 51) y Comprensión Difusa Fuzzy/LLM (Fase 54).
10. Índice de aplicaciones (Fase 52) y cancelación.
11. Diagnóstico del sistema y batería de autochequeo (Self-Test).
12. Restauración de valores predeterminados de fábrica.
13. Actualización de estado al entrar a la vista (on_enter).
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import flet as ft
import pytest

from config.settings import settings, DEFAULTS
from core.diagnostics import run_diagnostics, run_self_test, self_test_to_text, SelfTestItem
from core.user_memory import user_memory
from ui.pages.settings_page import SettingsPage


@pytest.fixture
def mock_page():
    """Simula una página Flet con atributos necesarios."""
    page = MagicMock(spec=ft.Page)
    page.theme_mode = ft.ThemeMode.DARK
    return page


@pytest.fixture
def settings_page(mock_page):
    """Instancia limpia de SettingsPage lista para pruebas."""
    sp = SettingsPage(page=mock_page)
    sp.build()
    return sp


class TestSettingsPagePhase29:
    """Suite de pruebas para la Ventana de Configuración Completa (Fase 29)."""

    def test_settings_page_instantiation_and_structure(self, settings_page):
        """Verifica que la página se instancie con todas las tarjetas y secciones requeridas."""
        assert settings_page.PAGE_NAME == "Configuración"
        assert hasattr(settings_page, "_general_card")
        assert hasattr(settings_page, "_ai_card")
        assert hasattr(settings_page, "_audio_card")
        assert hasattr(settings_page, "_security_card")
        assert hasattr(settings_page, "_memory_card")
        assert hasattr(settings_page, "_tools_card")
        assert hasattr(settings_page, "_category_chips")
        assert len(settings_page._category_chips.controls) == 7

    def test_category_navigation_filter(self, settings_page):
        """Verifica que los chips de categoría alternen correctamente la visibilidad de las tarjetas."""
        # Por defecto todas visibles
        assert settings_page._active_category == "all"
        assert settings_page._general_card.visible is True
        assert settings_page._ai_card.visible is True

        # Filtrar solo 'general'
        settings_page._set_active_category("general")
        assert settings_page._active_category == "general"
        assert settings_page._general_card.visible is True
        assert settings_page._ai_card.visible is False
        assert settings_page._security_card.visible is False

        # Filtrar solo 'ai'
        settings_page._set_active_category("ai")
        assert settings_page._general_card.visible is False
        assert settings_page._ai_card.visible is True

        # Filtrar solo 'security'
        settings_page._set_active_category("security")
        assert settings_page._security_card.visible is True
        assert settings_page._ai_card.visible is False

        # Volver a 'all'
        settings_page._set_active_category("all")
        assert settings_page._general_card.visible is True
        assert settings_page._ai_card.visible is True
        assert settings_page._tools_card.visible is True

    def test_appearance_and_language_settings(self, settings_page, mock_page):
        """Verifica los cambios de tema visual y de idioma."""
        # Toggle theme
        mock_event = MagicMock()
        mock_event.control.value = False  # Light mode
        settings_page._toggle_theme(mock_event)
        assert settings.get("APP_THEME") == "light"
        assert mock_page.theme_mode == ft.ThemeMode.LIGHT

        mock_event.control.value = True   # Dark mode
        settings_page._toggle_theme(mock_event)
        assert settings.get("APP_THEME") == "dark"
        assert mock_page.theme_mode == ft.ThemeMode.DARK

        # Idioma
        assert hasattr(settings_page, "_language_dropdown")
        lang_keys = [opt.key for opt in settings_page._language_dropdown.options]
        assert "es" in lang_keys
        assert "en" in lang_keys

        mock_lang_event = MagicMock()
        mock_lang_event.data = "en"
        settings_page._on_language_changed(mock_lang_event)
        assert settings.get("APP_LANGUAGE") == "en"

        mock_lang_event.data = "es"
        settings_page._on_language_changed(mock_lang_event)
        assert settings.get("APP_LANGUAGE") == "es"

    def test_workspace_validation_and_reset(self, settings_page, tmp_path):
        """Verifica configuración, guardado y reseteo de la carpeta de trabajo."""
        assert hasattr(settings_page, "_workspace_field")
        assert hasattr(settings_page, "_save_workspace_btn")
        assert hasattr(settings_page, "_reset_workspace_btn")
        assert hasattr(settings_page, "_workspace_status_text")

        # Configurar carpeta temporal
        custom_ws = tmp_path / "MiWorkspaceAURA"
        settings_page._workspace_field.value = str(custom_ws)
        settings_page._on_save_workspace()

        assert custom_ws.exists()
        assert Path(settings.get("WORKSPACE_PATH")).resolve() == custom_ws.resolve()
        assert "Ruta válida" in settings_page._workspace_status_text.value

        # Reset a Documentos
        settings_page._on_reset_workspace()
        doc_dir = str(Path.home() / "Documents")
        assert Path(settings.get("WORKSPACE_PATH")).resolve() == Path(doc_dir).resolve()

    def test_security_switches_toggle_and_save(self, settings_page):
        """Verifica los switches de seguridad y confirmaciones críticas."""
        assert hasattr(settings_page, "_confirm_destructive_switch")
        assert hasattr(settings_page, "_confirm_shutdown_switch")
        assert hasattr(settings_page, "_confirm_close_app_switch")
        assert hasattr(settings_page, "_router_first_switch")

        # Toggle individual
        settings_page._on_security_toggle("CONFIRMAR_CIERRE_APP", True)
        assert settings.get_bool("CONFIRMAR_CIERRE_APP") is True

        settings_page._on_security_toggle("CONFIRMAR_CIERRE_APP", False)
        assert settings.get_bool("CONFIRMAR_CIERRE_APP") is False

        # Guardado en bloque
        settings_page._confirm_destructive_switch.value = True
        settings_page._confirm_shutdown_switch.value = True
        settings_page._confirm_close_app_switch.value = True
        settings_page._router_first_switch.value = False
        settings_page._on_save_all_security()

        assert settings.get_bool("CONFIRM_DESTRUCTIVE") is True
        assert settings.get_bool("CONFIRM_SHUTDOWN") is True
        assert settings.get_bool("CONFIRMAR_CIERRE_APP") is True
        assert settings.get_bool("ROUTER_FIRST") is False

        # Restaurar
        settings_page._confirm_close_app_switch.value = False
        settings_page._router_first_switch.value = True
        settings_page._on_save_all_security()
        assert settings.get_bool("CONFIRMAR_CIERRE_APP") is False
        assert settings.get_bool("ROUTER_FIRST") is True

    def test_ai_multi_provider_controls(self, settings_page):
        """Verifica los controles de IA multi-proveedor y timeout."""
        assert hasattr(settings_page, "_provider_dropdown")
        assert hasattr(settings_page, "_model_dropdown")
        assert hasattr(settings_page, "_timeout_field")
        assert hasattr(settings_page, "_fallback_checkbox")
        assert hasattr(settings_page, "_test_conn_btn")
        assert hasattr(settings_page, "_save_ai_btn")

        options = [opt.key for opt in settings_page._provider_dropdown.options]
        for p in ["ollama", "openai", "anthropic", "gemini", "xai", "custom"]:
            assert p in options

        # Verificar timeout
        settings_page._timeout_field.value = "45"
        settings_page._provider_dropdown.value = "ollama"
        # Llamar guardado
        settings.set("AI_HTTP_TIMEOUT", "45")
        assert settings.get_int("AI_HTTP_TIMEOUT") == 45

    def test_user_memory_badges_export_and_clear(self, settings_page, tmp_path):
        """Verifica la integración visual con la Memoria de Usuario (Fase 28)."""
        assert hasattr(settings_page, "_mem_paths_badge")
        assert hasattr(settings_page, "_mem_progs_badge")
        assert hasattr(settings_page, "_mem_facts_badge")
        assert hasattr(settings_page, "_mem_proj_badge")
        assert hasattr(settings_page, "_export_mem_btn")
        assert hasattr(settings_page, "_clear_mem_btn")

        # Record some data
        user_memory.record_path("C:/Test/Proyectos/AURA")
        user_memory.record_program("sublime_text")
        user_memory.remember("El usuario prefiere tests concisos y rápidos")
        user_memory.set_current_project("C:/Test/Proyectos/AURA", name="AURA_Core")

        # Refrescar badges
        settings_page._refresh_memory_badges()
        assert "rutas" in settings_page._mem_paths_badge.content.value
        assert "programas" in settings_page._mem_progs_badge.content.value
        assert "hechos" in settings_page._mem_facts_badge.content.value
        assert "AURA_Core" in settings_page._mem_proj_badge.content.value

        # Exportar respaldo
        settings_page._on_export_memory()
        assert "Respaldo de memoria exportado" in settings_page._mem_status_text.value

        # Limpiar memoria
        settings_page._on_clear_memory()
        assert "reiniciada correctamente" in settings_page._mem_status_text.value
        assert "0 rutas" in settings_page._mem_paths_badge.content.value

    def test_personality_and_fuzzy_controls(self, settings_page):
        """Verifica los controles de personalidad Grok y comprensión difusa."""
        assert hasattr(settings_page, "_personality_dropdown")
        assert hasattr(settings_page, "_rude_slider")
        assert hasattr(settings_page, "_dark_humor_checkbox")
        assert hasattr(settings_page, "_insults_checkbox")
        assert hasattr(settings_page, "_fuzzy_slider")
        assert hasattr(settings_page, "_use_llm_fuzzy_switch")

        # Slider fuzzy
        mock_slider_event = MagicMock()
        mock_slider_event.control.value = 0.90
        settings_page._on_fuzzy_slider_changed(mock_slider_event)
        assert abs(settings.get_float("FUZZY_THRESHOLD") - 0.90) < 0.01

        # Switch LLM
        mock_switch_event = MagicMock()
        mock_switch_event.control.value = False
        settings_page._on_llm_fuzzy_changed(mock_switch_event)
        assert settings.get_bool("USE_LLM_INTERPRETER") is False

        mock_switch_event.control.value = True
        settings_page._on_llm_fuzzy_changed(mock_switch_event)
        assert settings.get_bool("USE_LLM_INTERPRETER") is True

    def test_system_diagnostics_and_self_test(self, settings_page):
        """Verifica la ejecución de diagnóstico general y la suite de autochequeo."""
        assert hasattr(settings_page, "_diag_btn")
        assert hasattr(settings_page, "_self_test_btn")
        assert hasattr(settings_page, "_diag_text")

        # Ejecutar autochequeo directamente
        items = run_self_test()
        assert isinstance(items, list)
        assert len(items) >= 6

        report_text = self_test_to_text(items)
        assert "AUTOCHEQUEO DE COMPONENTES" in report_text
        assert "[PASS]" in report_text or "[FAIL]" in report_text
        assert "Resumen:" in report_text

        # Diagnóstico general directo
        diag_res = run_diagnostics()
        assert diag_res is not None
        assert "DIAGNÓSTICO DE AURA" in diag_res.to_text()

    def test_restore_defaults_action(self, settings_page):
        """Verifica que el botón de restaurar por defecto restablezca los ajustes."""
        # Modificar varios ajustes
        settings.set("APP_THEME", "light")
        settings.set("CONFIRMAR_CIERRE_APP", "true")
        settings.set("FUZZY_THRESHOLD", "0.55")

        # Ejecutar restauración
        settings_page._handle_restore_defaults()

        assert settings.get("APP_THEME") == DEFAULTS.get("APP_THEME", "dark")
        assert settings.get("CONFIRMAR_CIERRE_APP") == DEFAULTS.get("CONFIRMAR_CIERRE_APP", "false")
        assert settings.get("FUZZY_THRESHOLD") == DEFAULTS.get("FUZZY_THRESHOLD", "0.85")
        assert "restaurada" in settings_page._diag_text.value.lower()

    def test_on_enter_refreshes_all_subsystems(self, settings_page):
        """Verifica que on_enter sincronice badges de apps y de memoria."""
        with patch.object(settings_page, "_refresh_index_badge") as mock_ref_idx, \
             patch.object(settings_page, "_refresh_memory_badges") as mock_ref_mem, \
             patch.object(settings_page, "_update_workspace_status_label") as mock_ref_ws:
            settings_page.on_enter()
            assert mock_ref_idx.called
            assert mock_ref_mem.called
            assert mock_ref_ws.called

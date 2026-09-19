"""
Tests para el contrato unificado de index_all_apps en AppIndexManager y SettingsPage.
"""

import os
import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.app_scanner import AppIndexManager, IndexedApp, app_index_manager
from ui.pages.settings_page import SettingsPage
import flet as ft


class TestAppIndexManagerContract:
    """Verifica la firma, callbacks, atomicidad y cancelación de index_all_apps."""

    def test_signature_accepts_progress_callback_and_cancel_event(self, tmp_path):
        test_index_file = tmp_path / "app_index.json"
        test_programs_file = tmp_path / "programs.json"
        manager = AppIndexManager(index_file=test_index_file, programs_file=test_programs_file)

        progress_calls = []

        def _cb(recorridas, encontradas, carpeta):
            progress_calls.append((recorridas, encontradas, carpeta))

        cancel_ev = threading.Event()

        # Invocar con progress_callback y cancel_event
        apps = manager.index_all_apps(progress_callback=_cb, cancel_event=cancel_ev)
        assert isinstance(apps, list)
        assert len(progress_calls) >= 1

    def test_signature_accepts_on_progress_backward_compatibility(self, tmp_path):
        test_index_file = tmp_path / "app_index.json"
        test_programs_file = tmp_path / "programs.json"
        manager = AppIndexManager(index_file=test_index_file, programs_file=test_programs_file)

        progress_calls = []

        def _cb(count, name):
            progress_calls.append((count, name))

        # Invocar con el keyword antiguo on_progress
        apps = manager.index_all_apps(on_progress=_cb)
        assert isinstance(apps, list)

    def test_atomic_persistence_preserves_previous_index_on_cancellation(self, tmp_path):
        test_index_file = tmp_path / "app_index.json"
        test_programs_file = tmp_path / "programs.json"
        manager = AppIndexManager(index_file=test_index_file, programs_file=test_programs_file)

        # Crear un archivo de índice previo
        prev_data = {
            "apps": {
                "notepad": {
                    "name": "notepad",
                    "display_name": "Bloc de notas",
                    "path": "C:\\Windows\\notepad.exe",
                    "date": "2026-01-01T00:00:00",
                    "origin": "manual",
                }
            },
            "last_updated": "2026-01-01T00:00:00",
        }
        with open(test_index_file, "w", encoding="utf-8") as f:
            json.dump(prev_data, f)

        # Cancelar inmediatamente antes o durante el escaneo
        cancel_ev = threading.Event()
        cancel_ev.set()

        apps = manager.index_all_apps(cancel_event=cancel_ev)

        # El índice previo en disco debe mantenerse 100% idéntico e intacto
        with open(test_index_file, "r", encoding="utf-8") as f:
            current_data = json.load(f)

        assert current_data == prev_data
        assert manager.count() == 1

    def test_aliases_index_app_rebuild_and_search(self, tmp_path):
        test_index_file = tmp_path / "app_index.json"
        test_programs_file = tmp_path / "programs.json"
        manager = AppIndexManager(index_file=test_index_file, programs_file=test_programs_file)

        dummy_exe = tmp_path / "editor.exe"
        dummy_exe.write_text("dummy")

        # index_app alias
        ok = manager.index_app("Mi Editor", str(dummy_exe), origin="manual", display_name="Mi Editor Pro")
        assert ok is True
        assert manager.count() == 1

        # search
        results = manager.search("editor")
        assert len(results) == 1
        assert results[0].name == "mi editor"

        # rebuild alias
        apps = manager.rebuild()
        assert isinstance(apps, list)


class TestSettingsPageAppIndexingUI:
    """Verifica el comportamiento de la UI de indexado en SettingsPage."""

    def test_settings_page_index_ui_elements(self, tmp_path):
        page_mock = MagicMock(spec=ft.Page)
        settings_page = SettingsPage(page=page_mock)

        assert hasattr(settings_page, "_index_btn")
        assert hasattr(settings_page, "_cancel_index_btn")
        assert hasattr(settings_page, "_index_count_badge")
        assert hasattr(settings_page, "_index_status_text")

        # Inicialmente el botón de cancelar está oculto
        assert settings_page._cancel_index_btn.visible is False
        assert settings_page._index_btn.disabled is False

    def test_settings_page_on_enter_refreshes_badge(self):
        page_mock = MagicMock(spec=ft.Page)
        settings_page = SettingsPage(page=page_mock)

        with patch.object(app_index_manager, "count", return_value=42):
            settings_page.on_enter()
            assert settings_page._index_count_badge.content.value == "42 apps indexadas"

    def test_settings_page_cancels_cleanly(self):
        page_mock = MagicMock(spec=ft.Page)
        settings_page = SettingsPage(page=page_mock)

        # Iniciar indexado simulado
        settings_page._is_indexing = True
        settings_page._indexing_cancel_event = threading.Event()

        # Cancelar
        settings_page._cancel_app_indexing()
        assert settings_page._indexing_cancel_event.is_set()
        assert "Cancelando" in settings_page._index_status_text.value

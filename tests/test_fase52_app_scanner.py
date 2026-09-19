"""
AURA — Tests Unitarios de Fase 52: Búsqueda Profunda de Aplicaciones en toda la PC
"""

import os
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import flet as ft

from core.app_scanner import (
    AppIndexManager,
    DeepAppScanner,
    DeepScanResult,
    IndexedApp,
    app_index_manager,
    deep_app_scanner,
    fast_resolve_app,
)
from core.app_resolver import resolve_app
from aura.core.entity_resolver import entity_resolver
from ui.pages.settings_page import SettingsPage
from ui.pages.chat_page import ChatPage


class TestFastResolutionOrder:
    """Verifica el orden de resolución rápida sin escaneo en disco."""

    def test_fast_resolve_known_system_app(self):
        # notepad o cmd siempre existen en Windows PATH o Start Menu
        res = fast_resolve_app("notepad")
        assert res is not None
        assert os.path.exists(res)
        assert res.lower().endswith((".exe", ".lnk"))

    def test_fast_resolve_cmd(self):
        res = fast_resolve_app("cmd")
        assert res is not None
        assert os.path.exists(res)

    def test_fast_resolve_unknown_app_fails_gracefully(self):
        res = fast_resolve_app("esta_app_no_existe_en_la_vida_real_12345")
        assert res is None

    def test_app_resolver_integration(self):
        res = resolve_app("notepad")
        assert res.success is True
        assert res.executable is not None


class TestAppIndexManager:
    """Verifica la persistencia y sincronización del índice de aplicaciones."""

    def test_register_and_get(self, tmp_path):
        test_index_file = tmp_path / "app_index.json"
        test_programs_file = tmp_path / "programs.json"

        manager = AppIndexManager(index_file=test_index_file, programs_file=test_programs_file)
        assert manager.count() == 0
        assert manager.get("mytool") is None

        # Registrar aplicación
        fake_exe = tmp_path / "mytool.exe"
        fake_exe.write_text("dummy")

        ok = manager.register("mytool", str(fake_exe), origin="test_suite")
        assert ok is True
        assert manager.count() == 1

        # Verificar recuperación
        recovered = manager.get("mytool")
        assert recovered is not None
        assert recovered == str(fake_exe)

        # Verificar persistencia en archivo
        assert test_index_file.exists()
        new_manager = AppIndexManager(index_file=test_index_file, programs_file=test_programs_file)
        assert new_manager.count() == 1
        assert new_manager.get("mytool") == str(fake_exe)

    def test_clean_nonexistent(self, tmp_path):
        test_index_file = tmp_path / "app_index.json"
        test_programs_file = tmp_path / "programs.json"

        manager = AppIndexManager(index_file=test_index_file, programs_file=test_programs_file)
        temp_file = tmp_path / "ghost.exe"
        temp_file.write_text("temporary")

        ok = manager.register("ghost_app", str(temp_file), origin="test")
        assert ok is True
        assert manager.count() == 1

        # Eliminar archivo de disco para simular que fue desinstalado
        temp_file.unlink()

        # Limpiar
        removed = manager.clean_nonexistent()
        assert removed == 1
        assert manager.count() == 0



class TestDeepAppScanner:
    """Verifica la búsqueda recursiva, filtros de exclusión y cancelación."""

    def test_scanner_finds_exact_executable(self, tmp_path):
        # Crear estructura simulada
        app_dir = tmp_path / "Programs" / "SuperApp"
        app_dir.mkdir(parents=True)
        exe_file = app_dir / "superapp.exe"
        exe_file.write_text("dummy binary")

        scanner = DeepAppScanner()
        res = scanner.scan("superapp", search_roots=[str(tmp_path)], max_depth=4)

        assert res.success is True
        assert res.chosen_path == str(exe_file)
        assert len(res.candidates) >= 1
        assert res.scan_time >= 0.0

    def test_scanner_skips_excluded_directories(self, tmp_path):
        # Crear app dentro de node_modules (debe ser ignorada)
        bad_dir = tmp_path / "node_modules" / "testapp"
        bad_dir.mkdir(parents=True)
        bad_exe = bad_dir / "testapp.exe"
        bad_exe.write_text("dummy")

        # Crear app dentro de .git (debe ser ignorada)
        git_dir = tmp_path / ".git" / "hooks"
        git_dir.mkdir(parents=True)
        git_exe = git_dir / "testapp.exe"
        git_exe.write_text("dummy")

        scanner = DeepAppScanner()
        res = scanner.scan("testapp", search_roots=[str(tmp_path)], max_depth=4)

        assert res.success is False
        assert len(res.candidates) == 0

    def test_scanner_respects_max_depth(self, tmp_path):
        # Crear carpeta a profundidad 5
        deep_dir = tmp_path / "1" / "2" / "3" / "4" / "5"
        deep_dir.mkdir(parents=True)
        deep_exe = deep_dir / "deepapp.exe"
        deep_exe.write_text("dummy")

        scanner = DeepAppScanner()
        # Con max_depth=2 no debería encontrarla
        res_shallow = scanner.scan("deepapp", search_roots=[str(tmp_path)], max_depth=2)
        assert res_shallow.success is False

        # Con max_depth=6 sí debería encontrarla
        res_deep = scanner.scan("deepapp", search_roots=[str(tmp_path)], max_depth=6)
        assert res_deep.success is True

    def test_scanner_cancellation(self, tmp_path):
        # Crear varias carpetas
        for i in range(10):
            d = tmp_path / f"folder_{i}"
            d.mkdir()
            (d / f"other_{i}.exe").write_text("dummy")

        cancel_event = threading.Event()
        cancel_event.set()  # Cancelar de antemano

        scanner = DeepAppScanner()
        res = scanner.scan("other", search_roots=[str(tmp_path)], cancel_event=cancel_event)

        assert res.cancelled is True
        assert res.success is False

    def test_scanner_multiple_candidates(self, tmp_path):
        # Crear varios candidatos parecidos
        d = tmp_path / "Apps"
        d.mkdir()
        (d / "player_editor.exe").write_text("dummy")
        (d / "player_viewer.exe").write_text("dummy")

        scanner = DeepAppScanner()
        res = scanner.scan("player", search_roots=[str(tmp_path)], max_depth=3)

        assert len(res.candidates) == 2
        # No hay coincidencia exacta de player.exe, por lo que es ambiguo
        assert res.has_exact_match is False
        assert res.chosen_path is None


class TestEntityResolverIntegration:
    """Verifica que entity_resolver señale que se requiere búsqueda profunda si fast resolve falla."""

    def test_unresolved_open_app_flags_needs_deep_scan(self):
        res = entity_resolver.resolve("open_app", "programa_completamente_inexistente_xyz_123")
        assert res.resolved is False
        assert res.extra.get("needs_deep_scan") is True

    def test_resolved_system_app(self):
        res = entity_resolver.resolve("open_app", "notepad")
        assert res.resolved is True
        assert res.executable is not None


class TestUIAndSettingsIntegration:
    """Verifica la integración con SettingsPage y controles de chat."""

    def test_settings_page_has_app_index_controls(self):
        page_mock = MagicMock(spec=ft.Page)
        settings_page = SettingsPage(page=page_mock)
        settings_page.build()

        assert hasattr(settings_page, "_index_btn")
        assert hasattr(settings_page, "_index_count_badge")
        assert hasattr(settings_page, "_index_status_text")
        assert "apps indexadas" in settings_page._index_count_badge.content.value

    def test_chat_page_initializes_scan_state(self):
        page_mock = MagicMock(spec=ft.Page)
        chat_page = ChatPage(page=page_mock)
        chat_page.build()

        assert hasattr(chat_page, "_active_scan_cancel_event")
        assert hasattr(chat_page, "_active_scan_target")
        assert hasattr(chat_page, "_pending_app_candidates")
        assert chat_page._active_scan_target is None
        assert chat_page._pending_app_candidates is None


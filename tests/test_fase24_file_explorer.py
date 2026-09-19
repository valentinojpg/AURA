"""
AURA — Tests automáticos de la Fase 24: Explorador de Archivos Básico

Cubre:
1. FileExplorer: Inicialización, resolución de rutas y defaults
2. FileExplorer: Navegación, historial (atrás/adelante), subir nivel, límites de raíz
3. FileExplorer: Listado de archivos/carpetas, ordenamiento (nombre, tamaño, fecha, tipo) y reversa
4. FileExplorer: Filtro y detección de archivos ocultos
5. FileExplorer: Metadatos de FileItem (tamaño legible, timestamps, extensiones, tipos e íconos)
6. FileExplorer: FolderSummary (conteo de subcarpetas, archivos y total bytes)
7. FileExplorer: Accesos rápidos (quick access) y detección de unidades de disco
8. FileExplorer: Apertura de archivos y carpetas (open_item, open_in_file_manager)
9. FilesPage UI: Montaje, inicialización, selección de elementos, cambio de orden, navegación y acciones
"""

import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import flet as ft

from core.file_explorer import (
    FileExplorer,
    FileItem,
    FolderSummary,
    QuickAccessItem,
    format_bytes,
    format_datetime,
    get_type_and_icon,
)
from ui.pages.files_page import FilesPage


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def temp_workspace(tmp_path):
    """Crea una estructura de archivos de prueba."""
    ws = tmp_path / "test_workspace"
    ws.mkdir()

    # Subcarpetas
    (ws / "docs").mkdir()
    (ws / "images").mkdir()
    (ws / "empty_dir").mkdir()

    # Archivos
    (ws / "script.py").write_text("print('hello')", encoding="utf-8")
    (ws / "readme.md").write_text("# AURA Readme", encoding="utf-8")
    (ws / "data.json").write_text('{"key": "val"}', encoding="utf-8")
    (ws / "notes.txt").write_text("Test notes", encoding="utf-8")
    (ws / ".hidden_file").write_text("hidden content", encoding="utf-8")

    # Archivo en subcarpeta
    (ws / "docs" / "manual.pdf").write_bytes(b"%PDF-1.4 sample")

    return ws


# ──────────────────────────────────────────────
# 1. Tests de Utilidades de Formato y Metadatos
# ──────────────────────────────────────────────

class TestFormatAndMetadata:
    def test_format_bytes_scales(self):
        assert format_bytes(-1) == "0 B"
        assert format_bytes(0) == "0 B"
        assert format_bytes(512) == "512 B"
        assert format_bytes(1024) == "1.0 KB"
        assert format_bytes(1536) == "1.5 KB"
        assert format_bytes(1048576) == "1.0 MB"
        assert format_bytes(1073741824) == "1.0 GB"
        assert format_bytes(1099511627776) == "1.0 TB"

    def test_format_datetime(self):
        assert format_datetime(None) == "-"
        dt = datetime(2026, 9, 8, 14, 30)
        assert format_datetime(dt) == "2026-09-08 14:30"

    def test_get_type_and_icon_directory(self):
        p = Path("some_folder")
        desc, icon, color = get_type_and_icon(p, is_dir=True)
        assert desc == "Carpeta de archivos"
        assert icon == "FOLDER"
        assert color == "#FBBF24"

    def test_get_type_and_icon_extensions(self):
        cases = [
            (Path("app.py"), "Script Python", "CODE"),
            (Path("doc.md"), "Documento Markdown", "DESCRIPTION"),
            (Path("config.json"), "Archivo JSON", "SETTINGS"),
            (Path("photo.png"), "Imagen PNG", "IMAGE"),
            (Path("song.mp3"), "Audio MP3", "AUDIO_FILE"),
            (Path("video.mp4"), "Video MP4", "MOVIE"),
            (Path("archive.zip"), "Archivo Comprimido ZIP", "FOLDER_ZIP"),
            (Path("program.exe"), "Ejecutable de Windows", "TERMINAL"),
            (Path("noext"), "Archivo", "INSERT_DRIVE_FILE"),
            (Path("custom.xyz"), "Archivo XYZ", "INSERT_DRIVE_FILE"),
        ]
        for p, expected_desc, expected_icon in cases:
            desc, icon, _ = get_type_and_icon(p, is_dir=False)
            assert expected_desc in desc
            assert icon == expected_icon


# ──────────────────────────────────────────────
# 2. Tests de Navegación e Historial
# ──────────────────────────────────────────────

class TestNavigationAndHistory:
    def test_initial_path(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        assert exp.current_path.resolve() == temp_workspace.resolve()
        assert not exp.can_go_back
        assert not exp.can_go_forward
        assert exp.can_go_up

    def test_navigate_success(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        target = temp_workspace / "docs"
        success, msg = exp.navigate(target)
        assert success
        assert exp.current_path.resolve() == target.resolve()
        assert exp.can_go_back
        assert not exp.can_go_forward

    def test_navigate_nonexistent(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        target = temp_workspace / "non_existent_folder"
        success, msg = exp.navigate(target)
        assert not success
        assert "no existe" in msg
        assert exp.current_path.resolve() == temp_workspace.resolve()

    def test_navigate_to_file_fails(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        target = temp_workspace / "script.py"
        success, msg = exp.navigate(target)
        assert not success
        assert "no es un directorio" in msg
        assert exp.current_path.resolve() == temp_workspace.resolve()

    def test_history_back_and_forward(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        docs = temp_workspace / "docs"
        images = temp_workspace / "images"

        exp.navigate(docs)
        exp.navigate(images)
        assert exp.current_path.resolve() == images.resolve()

        # Atrás a docs
        p = exp.go_back()
        assert p.resolve() == docs.resolve()
        assert exp.current_path.resolve() == docs.resolve()
        assert exp.can_go_back
        assert exp.can_go_forward

        # Atrás a raíz
        p = exp.go_back()
        assert p.resolve() == temp_workspace.resolve()
        assert not exp.can_go_back
        assert exp.can_go_forward

        # Adelante a docs
        p = exp.go_forward()
        assert p.resolve() == docs.resolve()

        # Adelante a images
        p = exp.go_forward()
        assert p.resolve() == images.resolve()
        assert not exp.can_go_forward

    def test_history_branch_truncation(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        docs = temp_workspace / "docs"
        images = temp_workspace / "images"
        empty_dir = temp_workspace / "empty_dir"

        exp.navigate(docs)
        exp.navigate(images)
        exp.go_back()  # En docs

        # Al navegar a una nueva rama, se descarta images del forward
        exp.navigate(empty_dir)
        assert not exp.can_go_forward
        assert exp.current_path.resolve() == empty_dir.resolve()

    def test_go_up(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace / "docs")
        parent = exp.go_up()
        assert parent is not None
        assert parent.resolve() == temp_workspace.resolve()
        assert exp.current_path.resolve() == temp_workspace.resolve()


# ──────────────────────────────────────────────
# 3. Tests de Listado y Ordenamiento
# ──────────────────────────────────────────────

class TestListingAndSorting:
    def test_list_items_folders_first(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        items = exp.list_items(show_hidden=False)

        # Debe haber carpetas seguidas de archivos
        saw_file = False
        for item in items:
            if not item.is_dir:
                saw_file = True
            elif saw_file:
                pytest.fail("Se encontró una carpeta después de un archivo en el listado.")

    def test_list_items_hidden_filter(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)

        without_hidden = exp.list_items(show_hidden=False)
        names_without = [i.name for i in without_hidden]
        assert ".hidden_file" not in names_without

        with_hidden = exp.list_items(show_hidden=True)
        names_with = [i.name for i in with_hidden]
        assert ".hidden_file" in names_with

    def test_sort_by_name(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        items = exp.list_items(sort_by="name", reverse=False)

        folders = [i.name.lower() for i in items if i.is_dir]
        files = [i.name.lower() for i in items if not i.is_dir]

        assert folders == sorted(folders)
        assert files == sorted(files)

    def test_sort_by_name_reverse(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        items = exp.list_items(sort_by="name", reverse=True)

        folders = [i.name.lower() for i in items if i.is_dir]
        files = [i.name.lower() for i in items if not i.is_dir]

        assert folders == sorted(folders, reverse=True)
        assert files == sorted(files, reverse=True)

    def test_sort_by_size(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        items = exp.list_items(sort_by="size")
        files = [i for i in items if not i.is_dir]
        sizes = [f.size_bytes for f in files]
        assert sizes == sorted(sizes)


# ──────────────────────────────────────────────
# 4. Tests de Inspección y Resumen
# ──────────────────────────────────────────────

class TestInspectionAndSummary:
    def test_get_item_info_file(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        item = exp.get_item_info(temp_workspace / "script.py")
        assert item is not None
        assert item.name == "script.py"
        assert not item.is_dir
        assert item.extension == ".py"
        assert "Python" in item.type_desc
        assert item.size_bytes > 0
        assert item.size_str.endswith("B")

    def test_get_item_info_folder(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        item = exp.get_item_info(temp_workspace / "docs")
        assert item is not None
        assert item.name == "docs"
        assert item.is_dir
        assert item.size_str == "<DIR>"

    def test_get_folder_summary(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        summary = exp.get_folder_summary()

        assert isinstance(summary, FolderSummary)
        assert summary.folder_count == 3  # docs, images, empty_dir
        assert summary.file_count >= 4   # script.py, readme.md, data.json, notes.txt (+ .hidden_file)
        assert summary.total_bytes > 0


# ──────────────────────────────────────────────
# 5. Tests de Quick Access y Discos
# ──────────────────────────────────────────────

class TestQuickAccessAndDrives:
    def test_get_quick_access(self):
        exp = FileExplorer()
        places = exp.get_quick_access()
        assert len(places) >= 1
        labels = [p.label for p in places]
        assert any(l in ["Workspace", "Usuario", "Documentos"] for l in labels)
        for p in places:
            assert isinstance(p, QuickAccessItem)
            assert p.path.is_dir()

    def test_get_drives(self):
        exp = FileExplorer()
        drives = exp.get_drives()
        assert len(drives) >= 1
        for d in drives:
            assert isinstance(d, QuickAccessItem)
            assert d.category == "drives"
            assert d.path.exists()


# ──────────────────────────────────────────────
# 6. Tests de Acciones de Sistema (Abrir)
# ──────────────────────────────────────────────

class TestSystemOpenActions:
    def test_open_folder_navigates(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        target = temp_workspace / "docs"
        success, msg = exp.open_item(target)
        assert success
        assert exp.current_path.resolve() == target.resolve()

    def test_open_nonexistent_item(self, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        success, msg = exp.open_item(temp_workspace / "not_real.txt")
        assert not success
        assert "no existe" in msg

    @patch("os.startfile", create=True)
    def test_open_file_windows(self, mock_startfile, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        target = temp_workspace / "script.py"

        with patch("platform.system", return_value="Windows"):
            success, msg = exp.open_item(target)
            assert success
            mock_startfile.assert_called_once_with(str(target.resolve()))

    @patch("subprocess.Popen")
    def test_open_in_file_manager_file(self, mock_popen, temp_workspace):
        exp = FileExplorer(initial_path=temp_workspace)
        target = temp_workspace / "script.py"

        with patch("platform.system", return_value="Windows"):
            success, msg = exp.open_in_file_manager(target)
            assert success
            mock_popen.assert_called_once()
            args = mock_popen.call_args[0][0]
            assert args[0] == "explorer"
            assert f"/select,{str(target.resolve())}" in args[1]


# ──────────────────────────────────────────────
# 7. Tests de la Interfaz Gráfica (FilesPage)
# ──────────────────────────────────────────────

class TestFilesPageUI:
    def test_files_page_build(self, temp_workspace):
        page_mock = MagicMock(spec=ft.Page)
        with patch.object(FileExplorer, "_resolve_initial_path", return_value=temp_workspace):
            files_page = FilesPage(page_mock)
            assert files_page.PAGE_NAME == "Archivos"
            assert files_page._explorer.current_path == temp_workspace
            assert files_page.content is not None

    def test_files_page_on_enter_populates_items(self, temp_workspace):
        page_mock = MagicMock(spec=ft.Page)
        with patch.object(FileExplorer, "_resolve_initial_path", return_value=temp_workspace):
            files_page = FilesPage(page_mock)
            files_page.on_enter()

            # Debe haber poblado controles en la lista de archivos
            assert len(files_page._current_items) > 0
            assert len(files_page._files_list_view.controls) > 0
            assert files_page._path_field.value == str(temp_workspace)

    def test_files_page_select_item(self, temp_workspace):
        page_mock = MagicMock(spec=ft.Page)
        with patch.object(FileExplorer, "_resolve_initial_path", return_value=temp_workspace):
            files_page = FilesPage(page_mock)
            files_page.refresh_view()

            item_to_select = files_page._current_items[0]
            files_page._on_row_click(item_to_select)

            assert files_page._selected_item == item_to_select
            # El panel de detalles debe tener controles para el elemento seleccionado
            assert len(files_page._detail_col.controls) > 0

    def test_files_page_toggle_hidden(self, temp_workspace):
        page_mock = MagicMock(spec=ft.Page)
        with patch.object(FileExplorer, "_resolve_initial_path", return_value=temp_workspace):
            files_page = FilesPage(page_mock)
            files_page.refresh_view()
            initial_count = len(files_page._current_items)

            # Activar archivos ocultos
            ev_mock = MagicMock(spec=ft.ControlEvent)
            files_page._on_toggle_hidden_click(ev_mock)

            assert files_page._show_hidden is True
            assert len(files_page._current_items) == initial_count + 1

    def test_files_page_sort_select(self, temp_workspace):
        page_mock = MagicMock(spec=ft.Page)
        with patch.object(FileExplorer, "_resolve_initial_path", return_value=temp_workspace):
            files_page = FilesPage(page_mock)
            files_page.refresh_view()

            ev = MagicMock(spec=ft.ControlEvent)
            ev.data = "size"
            ev.control = MagicMock()
            files_page._on_sort_select(ev)

            assert files_page._sort_by == "size"

    def test_files_page_navigate_up_button(self, temp_workspace):
        page_mock = MagicMock(spec=ft.Page)
        subfolder = temp_workspace / "docs"
        with patch.object(FileExplorer, "_resolve_initial_path", return_value=subfolder):
            files_page = FilesPage(page_mock)
            files_page.refresh_view()
            assert files_page._explorer.current_path.resolve() == subfolder.resolve()

            ev = MagicMock(spec=ft.ControlEvent)
            files_page._on_up_click(ev)

            assert files_page._explorer.current_path.resolve() == temp_workspace.resolve()
            assert files_page._path_field.value == str(temp_workspace.resolve())

    def test_files_page_empty_folder(self, temp_workspace):
        page_mock = MagicMock(spec=ft.Page)
        empty = temp_workspace / "empty_dir"
        with patch.object(FileExplorer, "_resolve_initial_path", return_value=empty):
            files_page = FilesPage(page_mock)
            files_page.refresh_view()

            assert len(files_page._current_items) == 0
            # Muestra placeholder de carpeta vacía
            assert len(files_page._files_list_view.controls) == 1

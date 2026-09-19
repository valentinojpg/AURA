"""
AURA — Tests automáticos de la Fase 25: Explorador Inteligente

Cubre:
1. FileExplorer: Detección automática de proyectos (detect_project) para Python, Node.js, Rust, Go, Java, Web, Git y Genérico.
2. FileExplorer: Búsqueda rápida por nombre (search_items) en modo plano y recursivo, con poda de carpetas ignoradas y límite de resultados.
3. FileExplorer: Búsqueda de contenido (search_content) en archivos de texto.
4. FileExplorer: Acciones contextuales:
   - create_folder: creación exitosa, carpetas existentes, validación de caracteres.
   - create_file: creación de archivos vacíos o con contenido inicial, validación.
   - rename_item: renombre de archivos y carpetas, conflicto de nombres existentes.
   - duplicate_item: duplicación automática con sufijo incremental "- Copia".
   - delete_item: modo dry-run seguro y borrado mediante send2trash con confirmación previa.
5. FileExplorer: Lanzadores de proyectos (open_in_vscode, open_terminal).
6. FilesPage UI: Barra de búsqueda, botón recursivo, banner de resultados, badge de proyecto detectado, acciones contextuales y apertura de diálogos modales.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import flet as ft

from core.file_explorer import (
    FileExplorer,
    FileItem,
    ProjectInfo,
    detect_project,
)
from ui.pages.files_page import FilesPage


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def temp_project_tree(tmp_path):
    """Crea un árbol de directorios con múltiples proyectos y archivos."""
    root = tmp_path / "root_workspace"
    root.mkdir()

    # 1. Python project
    py_dir = root / "python_proj"
    py_dir.mkdir()
    (py_dir / "requirements.txt").write_text("fastapi\nuvicorn\n", encoding="utf-8")
    (py_dir / "main.py").write_text("print('AURA Orion')\n", encoding="utf-8")
    (py_dir / "secret.env").write_text("API_KEY=12345\n", encoding="utf-8")
    py_sub = py_dir / "modules"
    py_sub.mkdir()
    (py_sub / "helper.py").write_text("def assist(): pass\n", encoding="utf-8")

    # Carpeta ignorada adentro del proyecto Python
    py_git = py_dir / ".git"
    py_git.mkdir()
    (py_git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    # 2. Node.js project
    node_dir = root / "node_proj"
    node_dir.mkdir()
    (node_dir / "package.json").write_text('{"name": "aura-web", "version": "1.0.0"}', encoding="utf-8")
    (node_dir / "index.js").write_text("console.log('hello node');", encoding="utf-8")
    node_modules = node_dir / "node_modules"
    node_modules.mkdir()
    (node_modules / "dummy.js").write_text("// dummy lib", encoding="utf-8")

    # 3. Rust project
    rust_dir = root / "rust_proj"
    rust_dir.mkdir()
    (rust_dir / "Cargo.toml").write_text('[package]\nname = "aura_core"', encoding="utf-8")

    # 4. Go project
    go_dir = root / "go_proj"
    go_dir.mkdir()
    (go_dir / "go.mod").write_text('module aura.dev/core\ngo 1.22', encoding="utf-8")

    # 5. Carpeta genérica vacía
    plain_dir = root / "plain_dir"
    plain_dir.mkdir()
    (plain_dir / "notes.txt").write_text("Just plain text notes", encoding="utf-8")

    return root


# ──────────────────────────────────────────────
# Tests: Detección de Proyectos (detect_project)
# ──────────────────────────────────────────────

class TestProjectDetection:
    """Verifica la detección automática de tecnologías y tipos de proyecto."""

    def test_detect_python_project(self, temp_project_tree):
        py_path = temp_project_tree / "python_proj"
        proj = detect_project(py_path)
        assert proj is not None
        assert proj.project_type == "python"
        assert "requirements.txt" in proj.indicators
        assert proj.name == "python_proj"
        assert proj.color == "#3776AB"

    def test_detect_node_project(self, temp_project_tree):
        node_path = temp_project_tree / "node_proj"
        proj = detect_project(node_path)
        assert proj is not None
        assert proj.project_type == "nodejs"
        assert "package.json" in proj.indicators
        assert proj.color == "#68A063"

    def test_detect_rust_project(self, temp_project_tree):
        rust_path = temp_project_tree / "rust_proj"
        proj = detect_project(rust_path)
        assert proj is not None
        assert proj.project_type == "rust"
        assert "Cargo.toml" in proj.indicators
        assert proj.color == "#DEA584"

    def test_detect_go_project(self, temp_project_tree):
        go_path = temp_project_tree / "go_proj"
        proj = detect_project(go_path)
        assert proj is not None
        assert proj.project_type == "go"
        assert "go.mod" in proj.indicators

    def test_detect_git_repo(self, temp_project_tree):
        git_dir = temp_project_tree / "git_only"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()
        proj = detect_project(git_dir)
        assert proj is not None
        assert proj.project_type == "git"
        assert ".git" in proj.indicators

    def test_detect_generic_folder(self, temp_project_tree):
        plain_path = temp_project_tree / "plain_dir"
        proj = detect_project(plain_path)
        assert proj is None

    def test_detect_nonexistent_or_file(self, temp_project_tree):
        assert detect_project(temp_project_tree / "non_existent") is None
        file_path = temp_project_tree / "python_proj" / "main.py"
        assert detect_project(file_path) is None


# ──────────────────────────────────────────────
# Tests: Búsqueda de Archivos (search_items & search_content)
# ──────────────────────────────────────────────

class TestSearchFunctionality:
    """Verifica la búsqueda por nombre y por contenido."""

    def test_search_items_shallow(self, temp_project_tree):
        py_path = temp_project_tree / "python_proj"
        explorer = FileExplorer(root_dir=py_path)
        results = explorer.search_items(query="main", recursive=False)
        assert len(results) == 1
        assert results[0].name == "main.py"

        results_sub = explorer.search_items(query="helper", recursive=False)
        assert len(results_sub) == 0

    def test_search_items_recursive(self, temp_project_tree):
        py_path = temp_project_tree / "python_proj"
        explorer = FileExplorer(root_dir=py_path)
        results = explorer.search_items(query="helper", recursive=True)
        assert len(results) == 1
        assert results[0].name == "helper.py"
        assert "modules" in results[0].path

    def test_search_items_pruning(self, temp_project_tree):
        py_path = temp_project_tree / "python_proj"
        explorer = FileExplorer(root_dir=py_path)
        results = explorer.search_items(query="HEAD", recursive=True)
        assert len(results) == 0

    def test_search_items_empty_query(self, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree)
        assert explorer.search_items("") == []
        assert explorer.search_items("   ") == []

    def test_search_items_max_results(self, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree)
        results = explorer.search_items(query=".", recursive=True, max_results=2)
        assert len(results) <= 2

    def test_search_content_matches(self, temp_project_tree):
        py_path = temp_project_tree / "python_proj"
        explorer = FileExplorer(root_dir=py_path)
        results = explorer.search_content(query="AURA Orion")
        assert len(results) == 1
        item, snippet = results[0]
        assert item.name == "main.py"
        assert "AURA Orion" in snippet

    def test_search_content_no_match(self, temp_project_tree):
        py_path = temp_project_tree / "python_proj"
        explorer = FileExplorer(root_dir=py_path)
        results = explorer.search_content(query="PalabraInexistente999")
        assert len(results) == 0


# ──────────────────────────────────────────────
# Tests: Operaciones Contextuales de Archivos/Carpetas
# ──────────────────────────────────────────────

class TestContextualOperations:
    """Verifica crear, renombrar, duplicar y eliminar elementos."""

    def test_create_folder_success(self, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree / "plain_dir")
        success, msg, path = explorer.create_folder("nueva_carpeta")
        assert success is True
        assert path is not None
        assert os.path.isdir(path)
        assert "creada con éxito" in msg or "creada exitosamente" in msg

    def test_create_folder_already_exists(self, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree / "plain_dir")
        explorer.create_folder("test_dup")
        success, msg, path = explorer.create_folder("test_dup")
        assert success is False
        assert "Ya existe" in msg

    def test_create_folder_invalid_name(self, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree / "plain_dir")
        success, msg, path = explorer.create_folder("bad:name?")
        assert success is False
        assert "caracteres no permitidos" in msg or "caracteres inválidos" in msg

    def test_create_file_success(self, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree / "plain_dir")
        success, msg, path = explorer.create_file("documento.txt", content="Hola Mundo")
        assert success is True
        assert path is not None
        assert os.path.isfile(path)
        assert Path(path).read_text(encoding="utf-8") == "Hola Mundo"

    def test_create_file_already_exists(self, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree / "plain_dir")
        explorer.create_file("existing.txt")
        success, msg, path = explorer.create_file("existing.txt")
        assert success is False
        assert "Ya existe" in msg

    def test_rename_item_success(self, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree / "plain_dir")
        old_file = temp_project_tree / "plain_dir" / "notes.txt"
        success, msg, new_path = explorer.rename_item(str(old_file), "renamed_notes.txt")
        assert success is True
        assert not old_file.exists()
        assert Path(new_path).exists()
        assert Path(new_path).name == "renamed_notes.txt"

    def test_rename_item_target_exists(self, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree / "plain_dir")
        f1 = temp_project_tree / "plain_dir" / "a.txt"
        f2 = temp_project_tree / "plain_dir" / "b.txt"
        f1.write_text("a", encoding="utf-8")
        f2.write_text("b", encoding="utf-8")

        success, msg, _ = explorer.rename_item(str(f1), "b.txt")
        assert success is False
        assert "Ya existe" in msg

    def test_duplicate_item_file(self, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree / "plain_dir")
        f = temp_project_tree / "plain_dir" / "notes.txt"
        success, msg, copy_path = explorer.duplicate_item(str(f))
        assert success is True
        assert Path(copy_path).exists()
        assert "copia" in copy_path.lower()
        assert Path(copy_path).read_text(encoding="utf-8") == "Just plain text notes"

        # Duplicar de nuevo produce segunda copia
        success2, _, copy_path2 = explorer.duplicate_item(str(f))
        assert success2 is True
        assert Path(copy_path2).exists()
        assert copy_path != copy_path2

    def test_duplicate_item_folder(self, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree)
        folder = temp_project_tree / "plain_dir"
        success, msg, copy_path = explorer.duplicate_item(str(folder))
        assert success is True
        assert Path(copy_path).is_dir()
        assert "copia" in copy_path.lower()
        assert (Path(copy_path) / "notes.txt").exists()

    def test_delete_item_dry_run(self, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree / "plain_dir")
        f = temp_project_tree / "plain_dir" / "notes.txt"
        success, msg = explorer.delete_item(str(f), dry_run=True)
        assert success is True
        assert "[DRY-RUN]" in msg
        assert f.exists(), "Dry-run no debe borrar el archivo"

    @patch("core.file_explorer.send2trash")
    def test_delete_item_send2trash(self, mock_send2trash, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree / "plain_dir")
        f = temp_project_tree / "plain_dir" / "notes.txt"
        success, msg = explorer.delete_item(str(f), dry_run=False)
        assert success is True
        assert "enviado a la papelera" in msg
        mock_send2trash.send2trash.assert_called_once_with(str(f))

    def test_delete_nonexistent_item(self, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree)
        success, msg = explorer.delete_item(str(temp_project_tree / "no_such_file.xyz"))
        assert success is False
        assert "no existe" in msg


# ──────────────────────────────────────────────
# Tests: Apertura de Proyectos y Terminales
# ──────────────────────────────────────────────

class TestLaunchers:
    """Verifica open_in_vscode y open_terminal."""

    @patch("shutil.which", return_value="C:\\Program Files\\VS Code\\code.cmd")
    @patch("subprocess.Popen")
    def test_open_in_vscode_installed(self, mock_popen, mock_which, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree)
        success, msg = explorer.open_in_vscode(str(temp_project_tree))
        assert success is True
        mock_popen.assert_called_once()
        assert "Abriendo VS Code" in msg

    @patch("shutil.which", return_value=None)
    @patch("os.path.isfile", return_value=False)
    def test_open_in_vscode_not_found(self, mock_isfile, mock_which, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree)
        success, msg = explorer.open_in_vscode(str(temp_project_tree))
        assert success is False
        assert "no encontrado" in msg

    @patch("subprocess.Popen")
    def test_open_terminal(self, mock_popen, temp_project_tree):
        explorer = FileExplorer(root_dir=temp_project_tree)
        success, msg = explorer.open_terminal(str(temp_project_tree))
        assert success is True
        mock_popen.assert_called_once()
        assert "Terminal abierta" in msg


# ──────────────────────────────────────────────
# Tests: FilesPage UI Integración
# ──────────────────────────────────────────────

class TestFilesPageUIPhase25:
    """Verifica la interfaz de usuario extendida para la Fase 25."""

    def test_files_page_search_and_clear(self, temp_project_tree):
        page_mock = MagicMock(spec=ft.Page)
        files_page = FilesPage(app_page=page_mock, initial_dir=str(temp_project_tree / "python_proj"))
        view = files_page.build()
        assert view is not None

        # Verificar controles de búsqueda presentes
        assert files_page._search_input is not None
        assert files_page._btn_recursive_search is not None
        assert files_page._search_banner is not None

        # Ejecutar búsqueda por 'main'
        files_page._search_input.value = "main"
        files_page._on_search_change(None)

        assert files_page._search_banner.visible is True
        assert "1 resultado" in files_page._search_banner.content.controls[1].value

        # Limpiar búsqueda
        files_page._clear_search(None)
        assert files_page._search_banner.visible is False
        assert files_page._search_input.value == ""

    def test_files_page_toggle_recursive(self, temp_project_tree):
        page_mock = MagicMock(spec=ft.Page)
        files_page = FilesPage(app_page=page_mock, initial_dir=str(temp_project_tree))
        files_page.build()

        assert files_page._recursive_search is False
        files_page._toggle_recursive_search(None)
        assert files_page._recursive_search is True

    def test_files_page_project_badge(self, temp_project_tree):
        page_mock = MagicMock(spec=ft.Page)
        files_page = FilesPage(app_page=page_mock, initial_dir=str(temp_project_tree / "python_proj"))
        files_page.build()

        # Al inicializar en python_proj, el badge debe detectar Python
        assert files_page._project_badge.visible is True
        assert "PYTHON" in files_page._project_badge.content.controls[1].value

    def test_files_page_modals_open(self, temp_project_tree):
        page_mock = MagicMock(spec=ft.Page)
        files_page = FilesPage(app_page=page_mock, initial_dir=str(temp_project_tree / "plain_dir"))
        files_page.build()

        # 1. Abrir diálogo de nueva carpeta
        files_page._show_new_folder_dialog(None)
        page_mock.show_dialog.assert_called()

        # 2. Abrir diálogo de nuevo archivo
        files_page._show_new_file_dialog(None)
        assert page_mock.show_dialog.call_count >= 2

        # 3. Seleccionar archivo y abrir diálogo renombrar
        notes_item = FileItem(
            name="notes.txt",
            path=str(temp_project_tree / "plain_dir" / "notes.txt"),
            is_dir=False,
            size=20,
            modified=1000.0,
            created=1000.0,
            extension=".txt",
            readable_size="20 B",
            readable_date="2026-09-08",
            item_type="text",
            icon_name=ft.Icons.DESCRIPTION,
        )
        files_page._select_item(notes_item)
        assert files_page.selected_item == notes_item

        files_page._show_rename_dialog(None)
        assert page_mock.show_dialog.call_count >= 3

        # 4. Abrir diálogo de confirmación de borrado
        files_page._show_delete_dialog(None)
        assert page_mock.show_dialog.call_count >= 4

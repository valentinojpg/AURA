"""
AURA — Pruebas Automatizadas de la Fase 28 (Memoria de Usuario)

Valida todas las capacidades del sistema de memoria persistente de usuario:
1. Inicialización y almacenamiento en disco con codificación explícita UTF-8.
2. Rutas frecuentes y favoritas (alias, frecuencias, accesos recientes).
3. Programas usados habitualmente (métricas de uso, ejecutables, categorías).
4. Preferencias del usuario (clave-valor tipado, get/set/delete).
5. Contexto de proyecto activo (auto-detección de stack, notas de sesión, proyectos recientes).
6. Memoria de largo plazo y hechos (User Facts, búsqueda por palabras clave/tags, olvido).
7. Generador de resúmenes contextuales para inyección en el prompt del sistema de IA.
8. Persistencia atómica (.tmp + rename) y tolerancia a fallos.
9. Exportación e importación completa en formato JSON.
10. Concurrencia multihilo segura (thread-safe con RLock).
11. Integración con ProgramsSkill, FileExplorer y CodeAssistant.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.code_assistant import CodeAction, build_prompt
from core.file_explorer import FileExplorer
from core.user_memory import (
    PathMemoryEntry,
    ProgramUsageEntry,
    ProjectContextEntry,
    UserFact,
    UserMemory,
    detect_project_type,
    user_memory,
)
from skills.builtin.programs_skill import ProgramsSkill


@pytest.fixture
def temp_memory_file(tmp_path):
    """Retorna la ruta de un archivo temporal para aislar la memoria de usuario."""
    return tmp_path / "memory" / "user_memory.json"


@pytest.fixture
def memory(temp_memory_file):
    """Instancia limpia de UserMemory para pruebas unitarias."""
    return UserMemory(memory_file=temp_memory_file, autosave=True)


class TestUserMemoryPhase28:
    """Suite de pruebas para el subsistema de Memoria de Usuario (Fase 28)."""

    def test_initialization_empty(self, memory, temp_memory_file):
        """Verifica que la memoria se inicialice limpia si el archivo no existe."""
        assert memory.VERSION == "1.0"
        assert len(memory.list_paths()) == 0
        assert len(memory.list_programs()) == 0
        assert len(memory.get_all_preferences()) == 0
        assert memory.get_current_project() is None
        assert len(memory.list_facts()) == 0

    def test_record_path_and_frequencies(self, memory):
        """Verifica el registro de rutas, conteo de accesos, alias y ordenamiento."""
        p1 = "C:/Proyectos/AURA"
        p2 = "C:/Descargas"

        # Registrar accesos
        memory.record_path(p1, alias="aura", category="project")
        memory.record_path(p1)
        memory.record_path(p1)
        memory.record_path(p2, alias="descargas", category="folder")

        # Consultas por ruta y por alias
        entry1 = memory.get_path(p1)
        assert entry1 is not None
        assert entry1.access_count == 3
        assert entry1.alias == "aura"
        assert entry1.category == "project"

        alias_lookup = memory.get_path_by_alias("aura")
        assert alias_lookup is not None
        assert Path(alias_lookup) == Path(p1)

        entry_by_alias = memory.get_path("descargas")
        assert entry_by_alias is not None
        assert Path(entry_by_alias.path) == Path(p2)

        # Frecuencia
        frequent = memory.get_frequent_paths(limit=5)
        assert len(frequent) == 2
        assert frequent[0].access_count == 3
        assert Path(frequent[0].path) == Path(p1)

        # Eliminar ruta
        assert memory.remove_path("descargas") is True
        assert memory.get_path_by_alias("descargas") is None

    def test_record_program_and_frequencies(self, memory):
        """Verifica el seguimiento de programas utilizados y frecuencias de apertura."""
        memory.record_program("vscode", executable_path="code", category="editor")
        memory.record_program("vscode")
        memory.record_program("chrome", executable_path="chrome.exe", category="browser")

        prog = memory.get_program("vscode")
        assert prog is not None
        assert prog.launch_count == 2
        assert prog.category == "editor"

        frequent = memory.get_frequent_programs(limit=10)
        assert len(frequent) == 2
        assert frequent[0].name == "vscode"
        assert frequent[0].launch_count == 2

        # Eliminación
        assert memory.remove_program("chrome") is True
        assert memory.get_program("chrome") is None

    def test_user_preferences_crud(self, memory):
        """Verifica almacenamiento, consulta y eliminación de preferencias de usuario."""
        assert memory.get_preference("theme", "default_val") == "default_val"

        memory.set_preference("theme", "cyber-dark")
        memory.set_preference("font_size", 14)
        memory.set_preference("streaming", True)

        assert memory.get_preference("theme") == "cyber-dark"
        assert memory.get_preference("font_size") == 14
        assert memory.get_preference("streaming") is True

        all_prefs = memory.get_all_preferences()
        assert len(all_prefs) == 3
        assert all_prefs["theme"] == "cyber-dark"

        assert memory.delete_preference("font_size") is True
        assert memory.get_preference("font_size") is None

    def test_detect_project_type_heuristics(self, tmp_path):
        """Verifica la detección automática de stacks tecnológicos."""
        # 1. Proyecto Python
        py_dir = tmp_path / "py_app"
        py_dir.mkdir()
        (py_dir / "pyproject.toml").write_text("[project]\nname='app'", encoding="utf-8")
        assert detect_project_type(py_dir) == "python"

        # 2. Proyecto TypeScript / Node
        ts_dir = tmp_path / "ts_app"
        ts_dir.mkdir()
        (ts_dir / "package.json").write_text('{"name": "app"}', encoding="utf-8")
        (ts_dir / "tsconfig.json").write_text("{}", encoding="utf-8")
        assert detect_project_type(ts_dir) == "typescript"

        # 3. Proyecto Rust
        rust_dir = tmp_path / "rust_app"
        rust_dir.mkdir()
        (rust_dir / "Cargo.toml").write_text('[package]\nname="rs"', encoding="utf-8")
        assert detect_project_type(rust_dir) == "rust"

        # 4. Directorio genérico
        empty_dir = tmp_path / "empty_dir"
        empty_dir.mkdir()
        assert detect_project_type(empty_dir) == "generic"

    def test_project_context_management(self, memory, tmp_path):
        """Verifica el mantenimiento de proyectos activos y notas de sesión."""
        proj_dir = tmp_path / "mi_proyecto"
        proj_dir.mkdir()
        (proj_dir / "requirements.txt").write_text("flet\n", encoding="utf-8")

        # Fijar proyecto activo
        entry = memory.set_current_project(proj_dir, name="MiProyecto")
        assert entry.name == "MiProyecto"
        assert entry.project_type == "python"
        assert memory.get_current_project() is not None
        assert memory.get_current_project().name == "MiProyecto"

        # Agregar notas
        assert memory.add_project_note("Avanzando en la interfaz visual") is True
        assert memory.add_project_note("Corregido bug de codificación UTF-8") is True
        curr = memory.get_current_project()
        assert len(curr.session_notes) == 2

        # Segundo proyecto
        other_dir = tmp_path / "otro_repo"
        other_dir.mkdir()
        (other_dir / "Cargo.toml").write_text('[package]\nname="otro"', encoding="utf-8")
        memory.set_current_project(other_dir, name="RepoRust")

        assert memory.get_current_project().name == "RepoRust"
        projects = memory.list_projects()
        assert len(projects) == 2

        # Desvincular proyecto actual
        memory.clear_current_project()
        assert memory.get_current_project() is None
        assert len(memory.list_projects()) == 2

    def test_user_facts_and_search(self, memory):
        """Verifica registro, categorización, búsqueda y olvido de hechos (User Facts)."""
        f1 = memory.remember(
            "El usuario se llama Valentino",
            category="identity",
            tags=["nombre", "personal"],
            fact_id="fact_name",
        )
        f2 = memory.remember(
            "Usa teclado en español de Latinoamérica",
            category="preference",
            tags=["hardware", "teclado"],
        )
        f3 = memory.remember(
            "Trabaja con Python 3.14 y Flet",
            category="work",
            tags=["lenguaje", "python", "flet"],
        )

        assert f1.id == "fact_name"
        assert len(memory.list_facts()) == 3
        assert len(memory.list_facts(category="identity")) == 1

        # Búsqueda por contenido
        search_res = memory.search_facts("Valentino")
        assert len(search_res) == 1
        assert search_res[0].id == "fact_name"

        # Búsqueda por tags
        tag_res = memory.search_facts("python")
        assert len(tag_res) == 1
        assert "Flet" in tag_res[0].content

        # Olvido de hecho
        assert memory.forget("fact_name") is True
        assert memory.get_fact("fact_name") is None
        assert len(memory.list_facts()) == 2

    def test_context_summary_and_prompt_generation(self, memory, tmp_path):
        """Verifica la generación de resúmenes contextuales formateados para la IA."""
        proj_dir = tmp_path / "orion_app"
        proj_dir.mkdir()
        (proj_dir / "pyproject.toml").write_text("name='orion'", encoding="utf-8")

        memory.set_current_project(proj_dir, name="OrionApp")
        memory.add_project_note("Implementando memoria de usuario")
        memory.set_preference("preferred_editor", "vscode")
        memory.record_program("vscode")
        memory.remember("Usuario estudiante de sistemas", category="identity")

        # Resumen legible para UI
        summary = memory.get_context_summary()
        assert "OrionApp" in summary
        assert "PYTHON" in summary
        assert "preferred_editor" in summary
        assert "vscode" in summary
        assert "Usuario estudiante de sistemas" in summary

        # Prompt context para inyección en system prompt de IA
        prompt_ctx = memory.to_prompt_context()
        assert "CONTEXTO Y MEMORIA DEL USUARIO:" in prompt_ctx
        assert "Proyecto en curso: OrionApp" in prompt_ctx
        assert "Recordatorio: Usuario estudiante de sistemas" in prompt_ctx

    def test_persistence_atomic_and_utf8(self, temp_memory_file):
        """Verifica guardado atómico en disco y lectura estricta con UTF-8."""
        mem1 = UserMemory(memory_file=temp_memory_file, autosave=True)

        # Cargar datos con caracteres especiales, tildes, acentos y emojis
        mem1.remember("Prefiere explicaciones con analogías y código ágil 🚀", category="estilo")
        mem1.record_path("C:/Usuarios/Valentino/Música_y_Diseño/ñandú", alias="canciones_ñ")
        mem1.record_program("editor_visual", executable_path="C:/Apps/diseño.exe")
        mem1.set_preference("saludo", "¡Hola Valentino! ¿En qué estás trabajando?")

        # Verificar existencia física del archivo
        assert temp_memory_file.exists()

        # Verificar que el contenido guardado sea válido en UTF-8 puro sin escapes ascii
        content_raw = temp_memory_file.read_text(encoding="utf-8")
        assert "analogías" in content_raw
        assert "Música_y_Diseño" in content_raw
        assert "ñandú" in content_raw
        assert "¡Hola Valentino!" in content_raw
        assert "🚀" in content_raw

        # Re-instanciar en frío y verificar restauración íntegra
        mem2 = UserMemory(memory_file=temp_memory_file)
        assert len(mem2.list_facts()) == 1
        assert "analogías" in mem2.list_facts()[0].content
        assert mem2.get_path_by_alias("canciones_ñ") is not None
        assert mem2.get_preference("saludo") == "¡Hola Valentino! ¿En qué estás trabajando?"

    def test_export_import_state(self, memory):
        """Verifica exportación e importación de estado completo."""
        memory.set_preference("lang", "es")
        memory.record_program("terminal")
        memory.remember("Hecho previo")

        data_dict = memory.to_dict()
        assert data_dict["version"] == "1.0"
        assert data_dict["preferences"]["lang"] == "es"

        json_str = memory.export_json()
        assert isinstance(json_str, str)
        assert '"lang": "es"' in json_str

        # Limpiar
        memory.clear()
        assert len(memory.list_facts()) == 0
        assert len(memory.get_all_preferences()) == 0

        # Importar y restaurar
        memory.import_dict(data_dict, merge=False)
        assert memory.get_preference("lang") == "es"
        assert len(memory.list_facts()) == 1
        assert len(memory.list_programs()) == 1

    def test_thread_safety_concurrent_access(self, temp_memory_file):
        """Verifica que múltiples hilos puedan escribir y consultar sin condiciones de carrera."""
        mem = UserMemory(memory_file=temp_memory_file, autosave=True)
        errors = []

        def worker(thread_id: int):
            try:
                for i in range(25):
                    mem.record_program(f"prog_{thread_id}")
                    mem.record_path(f"C:/folder_{thread_id}_{i}")
                    mem.remember(f"Dato del hilo {thread_id} iter {i}")
                    mem.set_preference(f"key_{thread_id}", i)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(mem.list_programs()) == 8
        assert len(mem.list_facts()) == 200

    def test_integration_with_programs_skill(self, tmp_path):
        """Verifica que abrir un programa mediante ProgramsSkill registre el hábito en UserMemory."""
        skill = ProgramsSkill()
        test_prog = "mi_test_app"
        test_path = str(tmp_path / "app.exe")

        # Mock de apertura de Windows
        with patch("os.startfile", return_value=None):
            result = skill._abrir_programa(test_prog, test_path)
            assert result.success is True

        # Verificar que quedó registrado en user_memory
        entry = user_memory.get_program(test_prog)
        assert entry is not None
        assert entry.name == test_prog

    def test_integration_with_file_explorer(self, tmp_path):
        """Verifica que FileExplorer.navigate registre la carpeta accedida en UserMemory."""
        test_dir = tmp_path / "carpeta_explorada"
        test_dir.mkdir()

        explorer = FileExplorer(initial_path=str(tmp_path))
        success, _ = explorer.navigate(str(test_dir))
        assert success is True

        # Verificar registro en user_memory
        p_entry = user_memory.get_path(str(test_dir))
        assert p_entry is not None
        assert Path(p_entry.path) == test_dir.resolve()

    def test_integration_with_code_assistant_readme(self, tmp_path):
        """Verifica que CodeAssistant use el nombre del proyecto activo desde UserMemory."""
        proj_dir = tmp_path / "sistema_academico"
        proj_dir.mkdir()

        user_memory.set_current_project(proj_dir, name="SistemaAcademico")

        # Generar prompt de README sin suministrar nombre explícito
        sys_p, user_p = build_prompt(CodeAction.GENERATE_README, code="print('hola')")
        assert "SistemaAcademico" in user_p

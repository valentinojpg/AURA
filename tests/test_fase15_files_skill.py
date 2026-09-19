"""
AURA — Tests de la Fase 15: FilesSkill

Suite completa de tests automatizados para la Skill de Archivos.

Cubre:
  - Importación y metadatos
  - Comando 'crear' (archivo y carpeta)
  - Comando 'copiar' (archivo y carpeta)
  - Comando 'mover'
  - Comando 'renombrar'
  - Comando 'eliminar' (dry-run y --ahora con send2trash mock)
  - Comando 'info' (archivo y carpeta)
  - Comando 'listar'
  - Manejo de errores (rutas inexistentes, args faltantes)
  - Integración con SkillRegistry (register, find_by_command, execute, discover)

Ejecutar con:
    .\\env\\Scripts\\python.exe -m pytest tests/test_fase15_files_skill.py -v
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Asegurar que el proyecto esté en el path
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ===========================================================================
# 1. IMPORTACIÓN Y ESTRUCTURA DEL MÓDULO
# ===========================================================================

class TestImportacion:
    """La FilesSkill debe poder importarse sin errores."""

    def test_importa_files_skill(self):
        from skills.builtin.files_skill import FilesSkill
        assert FilesSkill is not None

    def test_importa_desde_builtin_init(self):
        from skills.builtin import FilesSkill
        assert FilesSkill is not None

    def test_files_skill_es_subclase_de_baseskill(self):
        from skills.builtin.files_skill import FilesSkill
        from skills.skill_base import BaseSkill
        assert issubclass(FilesSkill, BaseSkill)

    def test_files_skill_tiene_meta(self):
        from skills.builtin.files_skill import FilesSkill
        assert hasattr(FilesSkill, "META")

    def test_files_skill_instanciable(self):
        from skills.builtin.files_skill import FilesSkill
        skill = FilesSkill()
        assert skill is not None

    def test_setup_y_teardown_funcionan(self):
        from skills.builtin.files_skill import FilesSkill
        skill = FilesSkill()
        skill.setup()
        skill.teardown()


# ===========================================================================
# 2. METADATOS (META)
# ===========================================================================

class TestMetadatos:
    """Los metadatos de FilesSkill deben ser correctos."""

    @pytest.fixture(autouse=True)
    def skill(self):
        from skills.builtin.files_skill import FilesSkill
        self._skill = FilesSkill()
        return self._skill

    def test_meta_name(self):
        assert self._skill.META.name == "files_skill"

    def test_meta_version(self):
        assert self._skill.META.version == "1.0.0"

    def test_meta_display_name(self):
        assert self._skill.META.display_name == "Archivos"

    def test_meta_author(self):
        assert self._skill.META.author == "AURA"

    def test_meta_category_es_files(self):
        from skills.skill_base import CATEGORY_FILES
        assert self._skill.META.category == CATEGORY_FILES

    def test_meta_builtin_es_true(self):
        assert self._skill.META.builtin is True

    def test_meta_enabled_by_default_es_true(self):
        assert self._skill.META.enabled_by_default is True

    def test_meta_commands_contiene_todos(self):
        comandos = self._skill.META.commands
        for cmd in ("crear", "copiar", "mover", "renombrar", "eliminar", "info", "listar"):
            assert cmd in comandos, f"Falta comando '{cmd}' en META.commands"

    def test_meta_description_no_vacia(self):
        assert len(self._skill.META.description) > 10

    def test_execute_es_callable(self):
        assert callable(self._skill.execute)


# ===========================================================================
# 3. FIXTURE: directorio temporal
# ===========================================================================

@pytest.fixture
def tmpdir_skill(tmp_path):
    """
    Proporciona un directorio temporal limpio y parchea WORKSPACE_PATH
    para que la skill resuelva rutas relativas contra él.
    """
    from skills.builtin.files_skill import FilesSkill
    skill = FilesSkill()

    # Monkeypatch _workspace para que devuelva tmp_path
    skill._workspace = lambda: tmp_path

    return skill, tmp_path


# ===========================================================================
# 4. COMANDO: crear
# ===========================================================================

class TestComandoCrear:
    """Tests del comando 'crear'."""

    def test_crear_sin_args_retorna_error(self, tmpdir_skill):
        skill, _ = tmpdir_skill
        result = skill.execute("crear", [])
        assert result.success is False
        assert result.error

    def test_crear_archivo_nuevo(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        result = skill.execute("crear", ["nuevo.txt"])
        assert result.success is True
        assert (tmp / "nuevo.txt").exists()
        assert result.data["type"] == "file"

    def test_crear_carpeta_nueva(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        result = skill.execute("crear", ["mi_carpeta", "--carpeta"])
        assert result.success is True
        assert (tmp / "mi_carpeta").is_dir()
        assert result.data["type"] == "directory"

    def test_crear_archivo_ya_existente_retorna_error(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "existente.txt").touch()
        result = skill.execute("crear", ["existente.txt"])
        assert result.success is False
        assert "ya existe" in result.error.lower()

    def test_crear_carpeta_ya_existente_retorna_error(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "carpeta").mkdir()
        result = skill.execute("crear", ["carpeta", "--carpeta"])
        assert result.success is False

    def test_crear_output_menciona_ruta(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        result = skill.execute("crear", ["hola.txt"])
        assert result.success is True
        assert "hola.txt" in result.output

    def test_crear_data_contiene_path(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        result = skill.execute("crear", ["prueba.txt"])
        assert "path" in result.data


# ===========================================================================
# 5. COMANDO: copiar
# ===========================================================================

class TestComandoCopiar:
    """Tests del comando 'copiar'."""

    def test_copiar_sin_args_retorna_error(self, tmpdir_skill):
        skill, _ = tmpdir_skill
        result = skill.execute("copiar", [])
        assert result.success is False

    def test_copiar_un_arg_retorna_error(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "orig.txt").touch()
        result = skill.execute("copiar", ["orig.txt"])
        assert result.success is False

    def test_copiar_archivo(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        origen = tmp / "orig.txt"
        origen.write_text("hola")
        result = skill.execute("copiar", ["orig.txt", "copia.txt"])
        assert result.success is True
        assert (tmp / "copia.txt").exists()
        assert (tmp / "copia.txt").read_text() == "hola"

    def test_copiar_archivo_origen_inexistente(self, tmpdir_skill):
        skill, _ = tmpdir_skill
        result = skill.execute("copiar", ["no_existe.txt", "destino.txt"])
        assert result.success is False
        assert "no existe" in result.error.lower()

    def test_copiar_carpeta(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        src = tmp / "src_dir"
        src.mkdir()
        (src / "a.txt").write_text("a")
        result = skill.execute("copiar", ["src_dir", "dst_dir"])
        assert result.success is True
        assert (tmp / "dst_dir" / "a.txt").exists()

    def test_copiar_data_contiene_origen_y_destino(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "f.txt").write_text("x")
        result = skill.execute("copiar", ["f.txt", "f2.txt"])
        assert "origen" in result.data
        assert "destino" in result.data


# ===========================================================================
# 6. COMANDO: mover
# ===========================================================================

class TestComandoMover:
    """Tests del comando 'mover'."""

    def test_mover_sin_args_retorna_error(self, tmpdir_skill):
        skill, _ = tmpdir_skill
        result = skill.execute("mover", [])
        assert result.success is False

    def test_mover_archivo(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        orig = tmp / "orig.txt"
        orig.write_text("datos")
        result = skill.execute("mover", ["orig.txt", "movido.txt"])
        assert result.success is True
        assert not orig.exists()
        assert (tmp / "movido.txt").exists()

    def test_mover_origen_inexistente(self, tmpdir_skill):
        skill, _ = tmpdir_skill
        result = skill.execute("mover", ["fantasma.txt", "destino.txt"])
        assert result.success is False
        assert "no existe" in result.error.lower()

    def test_mover_preserva_contenido(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "data.txt").write_text("contenido")
        skill.execute("mover", ["data.txt", "data_movida.txt"])
        assert (tmp / "data_movida.txt").read_text() == "contenido"

    def test_mover_data_contiene_origen_y_destino(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "x.txt").write_text("x")
        result = skill.execute("mover", ["x.txt", "y.txt"])
        assert "origen" in result.data
        assert "destino" in result.data


# ===========================================================================
# 7. COMANDO: renombrar
# ===========================================================================

class TestComandoRenombrar:
    """Tests del comando 'renombrar'."""

    def test_renombrar_sin_args_retorna_error(self, tmpdir_skill):
        skill, _ = tmpdir_skill
        result = skill.execute("renombrar", [])
        assert result.success is False

    def test_renombrar_archivo(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "viejo.txt").write_text("texto")
        result = skill.execute("renombrar", ["viejo.txt", "nuevo.txt"])
        assert result.success is True
        assert not (tmp / "viejo.txt").exists()
        assert (tmp / "nuevo.txt").exists()

    def test_renombrar_archivo_inexistente(self, tmpdir_skill):
        skill, _ = tmpdir_skill
        result = skill.execute("renombrar", ["no_existe.txt", "nuevo.txt"])
        assert result.success is False

    def test_renombrar_destino_ya_existe(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "a.txt").write_text("a")
        (tmp / "b.txt").write_text("b")
        result = skill.execute("renombrar", ["a.txt", "b.txt"])
        assert result.success is False

    def test_renombrar_con_separador_retorna_error(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "a.txt").write_text("a")
        # Intentar renombrar con ruta completa debería ser rechazado
        result = skill.execute("renombrar", ["a.txt", "sub/nuevo.txt"])
        assert result.success is False

    def test_renombrar_output_menciona_nombres(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "viejo.txt").write_text("x")
        result = skill.execute("renombrar", ["viejo.txt", "nuevo.txt"])
        assert "viejo.txt" in result.output
        assert "nuevo.txt" in result.output

    def test_renombrar_carpeta(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "dir_viejo").mkdir()
        result = skill.execute("renombrar", ["dir_viejo", "dir_nuevo"])
        assert result.success is True
        assert (tmp / "dir_nuevo").is_dir()


# ===========================================================================
# 8. COMANDO: eliminar (dry-run)
# ===========================================================================

class TestComandoEliminarDryRun:
    """Tests del modo dry-run de 'eliminar'."""

    def test_eliminar_sin_args_retorna_error(self, tmpdir_skill):
        skill, _ = tmpdir_skill
        result = skill.execute("eliminar", [])
        assert result.success is False

    def test_eliminar_dryrun_por_defecto(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "a.txt").write_text("x")
        result = skill.execute("eliminar", ["a.txt"])
        # Dry-run: success=True pero el archivo sigue existiendo
        assert result.success is True
        assert (tmp / "a.txt").exists()
        assert result.data["dry_run"] is True

    def test_eliminar_dryrun_menciona_simulacion(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "b.txt").touch()
        result = skill.execute("eliminar", ["b.txt"])
        assert "SIMULACIÓN" in result.output or "simulaci" in result.output.lower()

    def test_eliminar_dryrun_menciona_ahora(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "c.txt").touch()
        result = skill.execute("eliminar", ["c.txt"])
        assert "--ahora" in result.output

    def test_eliminar_archivo_inexistente(self, tmpdir_skill):
        skill, _ = tmpdir_skill
        result = skill.execute("eliminar", ["no_existe.txt", "--ahora"])
        assert result.success is False
        assert "no existe" in result.error.lower()

    def test_eliminar_data_contiene_path(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "d.txt").touch()
        result = skill.execute("eliminar", ["d.txt"])
        assert "path" in result.data


# ===========================================================================
# 9. COMANDO: eliminar (--ahora con send2trash)
# ===========================================================================

class TestComandoEliminarReal:
    """Tests del comando 'eliminar --ahora' con send2trash mockeado."""

    def test_eliminar_ahora_llama_send2trash(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "target.txt").write_text("x")

        with patch("skills.builtin.files_skill._has_send2trash", return_value=True), \
             patch("send2trash.send2trash") as mock_s2t:
            result = skill.execute("eliminar", ["target.txt", "--ahora"])

        assert result.success is True
        mock_s2t.assert_called_once()
        assert result.data["dry_run"] is False

    def test_eliminar_ahora_sin_send2trash_retorna_error(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "target.txt").write_text("x")

        with patch("skills.builtin.files_skill._has_send2trash", return_value=False):
            result = skill.execute("eliminar", ["target.txt", "--ahora"])

        assert result.success is False
        assert "send2trash" in result.error.lower()

    def test_eliminar_carpeta_ahora(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "mi_dir").mkdir()

        with patch("skills.builtin.files_skill._has_send2trash", return_value=True), \
             patch("send2trash.send2trash") as mock_s2t:
            result = skill.execute("eliminar", ["mi_dir", "--ahora"])

        assert result.success is True
        assert result.data["type"] == "carpeta"

    def test_eliminar_output_menciona_papelera(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "e.txt").touch()

        with patch("skills.builtin.files_skill._has_send2trash", return_value=True), \
             patch("send2trash.send2trash"):
            result = skill.execute("eliminar", ["e.txt", "--ahora"])

        assert "papelera" in result.output.lower()


# ===========================================================================
# 10. COMANDO: info
# ===========================================================================

class TestComandoInfo:
    """Tests del comando 'info'."""

    def test_info_sin_args_retorna_error(self, tmpdir_skill):
        skill, _ = tmpdir_skill
        result = skill.execute("info", [])
        assert result.success is False

    def test_info_archivo(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        f = tmp / "doc.txt"
        f.write_text("contenido de prueba")
        result = skill.execute("info", ["doc.txt"])
        assert result.success is True
        assert "doc.txt" in result.output

    def test_info_archivo_muestra_tamanio(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "big.txt").write_bytes(b"x" * 1024)
        result = skill.execute("info", ["big.txt"])
        assert result.success is True
        # Debe mencionar alguna unidad de tamaño
        assert any(u in result.output for u in ("B", "KB", "MB"))

    def test_info_carpeta(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        d = tmp / "mi_dir"
        d.mkdir()
        (d / "a.txt").touch()
        result = skill.execute("info", ["mi_dir"])
        assert result.success is True
        assert "mi_dir" in result.output

    def test_info_ruta_inexistente(self, tmpdir_skill):
        skill, _ = tmpdir_skill
        result = skill.execute("info", ["no_existe.txt"])
        assert result.success is False

    def test_info_data_contiene_path(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "z.txt").touch()
        result = skill.execute("info", ["z.txt"])
        assert "path" in result.data

    def test_info_data_is_dir_false_para_archivo(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "f.txt").touch()
        result = skill.execute("info", ["f.txt"])
        assert result.data["is_dir"] is False

    def test_info_data_is_dir_true_para_carpeta(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "dir").mkdir()
        result = skill.execute("info", ["dir"])
        assert result.data["is_dir"] is True


# ===========================================================================
# 11. COMANDO: listar
# ===========================================================================

class TestComandoListar:
    """Tests del comando 'listar'."""

    def test_listar_sin_args_usa_workspace(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "a.txt").touch()
        result = skill.execute("listar", [])
        assert result.success is True
        assert str(tmp) in result.output

    def test_listar_carpeta_especifica(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        d = tmp / "sub"
        d.mkdir()
        (d / "x.txt").touch()
        result = skill.execute("listar", ["sub"])
        assert result.success is True
        assert "x.txt" in result.output

    def test_listar_carpeta_vacia(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "vacia").mkdir()
        result = skill.execute("listar", ["vacia"])
        assert result.success is True
        assert "vacía" in result.output.lower() or "vaci" in result.output.lower()

    def test_listar_carpeta_inexistente(self, tmpdir_skill):
        skill, _ = tmpdir_skill
        result = skill.execute("listar", ["no_existe"])
        assert result.success is False

    def test_listar_archivo_en_vez_de_carpeta(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "archivo.txt").touch()
        result = skill.execute("listar", ["archivo.txt"])
        assert result.success is False

    def test_listar_muestra_subdirectorios(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "dir1").mkdir()
        (tmp / "dir2").mkdir()
        result = skill.execute("listar", [])
        assert "dir1" in result.output
        assert "dir2" in result.output

    def test_listar_data_contiene_count(self, tmpdir_skill):
        skill, tmp = tmpdir_skill
        (tmp / "a.txt").touch()
        result = skill.execute("listar", [])
        assert "count" in result.data


# ===========================================================================
# 12. COMANDO DESCONOCIDO
# ===========================================================================

class TestComandoDesconocido:
    """El dispatch debe manejar comandos no reconocidos."""

    def test_comando_desconocido_retorna_error(self, tmpdir_skill):
        skill, _ = tmpdir_skill
        result = skill.execute("xyz_desconocido", [])
        assert result.success is False
        assert result.error

    def test_comando_vacio_retorna_error(self, tmpdir_skill):
        skill, _ = tmpdir_skill
        result = skill.execute("", [])
        assert result.success is False


# ===========================================================================
# 13. _resolve y _workspace
# ===========================================================================

class TestResolveWorkspace:
    """Testea la resolución de rutas."""

    def test_ruta_absoluta_se_mantiene(self, tmp_path):
        from skills.builtin.files_skill import FilesSkill
        skill = FilesSkill()
        abs_path = str(tmp_path / "archivo.txt")
        resolved = skill._resolve(abs_path)
        assert resolved == (tmp_path / "archivo.txt").resolve()

    def test_ruta_relativa_usa_workspace(self, tmp_path):
        from skills.builtin.files_skill import FilesSkill
        skill = FilesSkill()
        skill._workspace = lambda: tmp_path
        resolved = skill._resolve("relativo.txt")
        assert resolved == (tmp_path / "relativo.txt").resolve()

    def test_workspace_retorna_path(self):
        from skills.builtin.files_skill import FilesSkill
        skill = FilesSkill()
        ws = skill._workspace()
        assert isinstance(ws, Path)


# ===========================================================================
# 14. _fmt_size y _fmt_time
# ===========================================================================

class TestHelpers:
    """Tests de los helpers de formateo."""

    @pytest.fixture(autouse=True)
    def skill(self):
        from skills.builtin.files_skill import FilesSkill
        self._skill = FilesSkill()

    def test_fmt_size_bytes(self):
        assert "B" in self._skill._fmt_size(500)

    def test_fmt_size_kb(self):
        assert "KB" in self._skill._fmt_size(2048)

    def test_fmt_size_mb(self):
        assert "MB" in self._skill._fmt_size(2 * 1024 * 1024)

    def test_fmt_time_retorna_string(self):
        import time
        result = self._skill._fmt_time(time.time())
        assert isinstance(result, str)
        assert len(result) > 5


# ===========================================================================
# 15. INTEGRACIÓN CON SKILLREGISTRY
# ===========================================================================

class TestIntegracionRegistry:
    """FilesSkill debe funcionar correctamente dentro del SkillRegistry."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from skills.skill_registry import SkillRegistry
        from skills.builtin.files_skill import FilesSkill
        self.registry = SkillRegistry()
        self.FilesSkill = FilesSkill

    def _register(self):
        """Registra FilesSkill como instancia (API real del registry)."""
        instance = self.FilesSkill()
        instance.setup()
        self.registry.register(instance)
        return instance

    def test_register_files_skill(self):
        self._register()
        entry = self.registry.get("files_skill")
        assert entry is not None

    def test_find_by_command_crear(self):
        self._register()
        entry = self.registry.find_by_command("crear")
        assert entry is not None
        assert entry.name == "files_skill"

    def test_find_by_command_eliminar(self):
        self._register()
        entry = self.registry.find_by_command("eliminar")
        assert entry is not None

    def test_find_by_command_todos_los_comandos(self):
        self._register()
        for cmd in ("crear", "copiar", "mover", "renombrar", "eliminar", "info", "listar"):
            entry = self.registry.find_by_command(cmd)
            assert entry is not None, f"Comando '{cmd}' no encontrado en registry"

    def test_disable_files_skill(self):
        self._register()
        self.registry.disable("files_skill")
        entry = self.registry.find_by_command("crear")
        assert entry is None

    def test_enable_files_skill(self):
        self._register()
        self.registry.disable("files_skill")
        self.registry.enable("files_skill")
        entry = self.registry.find_by_command("crear")
        assert entry is not None

    def test_discover_builtin_incluye_files_skill(self):
        self.registry.discover_builtin()
        entry = self.registry.get("files_skill")
        assert entry is not None

    def test_discover_builtin_idempotente(self):
        self.registry.discover_builtin()
        self.registry.discover_builtin()
        entries = self.registry.list_all()
        names = [e.name for e in entries]
        assert names.count("files_skill") == 1

    def test_discover_incluye_demo_system_y_files(self):
        self.registry.discover_builtin()
        names = {e.name for e in self.registry.list_all()}
        assert "demo_skill" in names
        assert "system_skill" in names
        assert "files_skill" in names

    def test_execute_info_via_registry(self, tmp_path):
        from skills.builtin.files_skill import FilesSkill
        instance = FilesSkill()
        instance.setup()
        instance._workspace = lambda: tmp_path
        self.registry.register(instance)
        (tmp_path / "test.txt").write_text("hola")

        result = self.registry.execute("files_skill", "info", ["test.txt"])
        assert result is not None
        assert result.success is True


# ===========================================================================
# 16. PRUEBA DE SINTAXIS
# ===========================================================================

class TestSintaxis:
    """Verifica la sintaxis de los archivos modificados."""

    def test_sintaxis_files_skill(self):
        import py_compile
        path = PROJECT_ROOT / "skills" / "builtin" / "files_skill.py"
        py_compile.compile(str(path), doraise=True)

    def test_sintaxis_builtin_init(self):
        import py_compile
        path = PROJECT_ROOT / "skills" / "builtin" / "__init__.py"
        py_compile.compile(str(path), doraise=True)

    def test_sintaxis_requirements(self):
        req_path = PROJECT_ROOT / "requirements.txt"
        content = req_path.read_text()
        assert "send2trash" in content

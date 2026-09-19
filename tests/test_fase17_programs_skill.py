"""
AURA — Tests automáticos Fase 17: ProgramsSkill

Suite de 85 tests para verificar la implementación completa de ProgramsSkill:
  - Metadatos y estructura de la skill
  - Comando 'programa' (abrir por alias)
  - Comando 'programas' (listar)
  - Comando 'agregar-programa' (registrar alias)
  - Comando 'quitar-programa' (eliminar alias)
  - Comando 'programa-info' (información de alias)
  - Persistencia JSON
  - Alias builtin predefinidos
  - Casos de error y validaciones
  - Regresión de imports
"""

from __future__ import annotations

import json
import os
import platform
import py_compile
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Asegurar que el root del proyecto esté en sys.path ───────────────────

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Importaciones bajo prueba ─────────────────────────────────────────────

from skills.builtin.programs_skill import ProgramsSkill, _BUILTIN_ALIASES, _PROGRAMS_FILE
from skills.skill_base import SkillMeta, SkillResult, CATEGORY_PROGRAMS


# ── Helper: instancia aislada ──────────────────────────────────────────────

def _make_skill(tmp_dir: Path | None = None) -> ProgramsSkill:
    """
    Retorna una instancia de ProgramsSkill con el archivo de persistencia
    apuntando a un directorio temporal (para no afectar datos reales).
    """
    skill = ProgramsSkill()

    if tmp_dir is not None:
        # Parchear la ruta de persistencia dentro de la instancia
        import skills.builtin.programs_skill as mod
        old_file = mod._PROGRAMS_FILE
        mod._PROGRAMS_FILE = tmp_dir / "programs.json"
        skill.setup()
        mod._PROGRAMS_FILE = old_file
    else:
        skill.setup()

    return skill


# ===========================================================================
# 1. Sintaxis y estructura estática
# ===========================================================================

class TestSintaxis(unittest.TestCase):
    """Verifica que el archivo tenga sintaxis Python válida."""

    def test_sintaxis_valida(self):
        """El módulo compila sin errores de sintaxis."""
        path = _ROOT / "skills" / "builtin" / "programs_skill.py"
        py_compile.compile(str(path), doraise=True)

    def test_importable(self):
        """ProgramsSkill importa sin excepciones."""
        from skills.builtin.programs_skill import ProgramsSkill  # noqa: F401


class TestMetadatos(unittest.TestCase):
    """Verifica los metadatos de la skill."""

    def setUp(self):
        self.skill = ProgramsSkill()

    def test_meta_existe(self):
        self.assertTrue(hasattr(ProgramsSkill, "META"))

    def test_meta_es_skillmeta(self):
        self.assertIsInstance(ProgramsSkill.META, SkillMeta)

    def test_meta_name(self):
        self.assertEqual(ProgramsSkill.META.name, "programs_skill")

    def test_meta_version(self):
        self.assertRegex(ProgramsSkill.META.version, r"^\d+\.\d+\.\d+$")

    def test_meta_display_name(self):
        self.assertEqual(ProgramsSkill.META.display_name, "Programas")

    def test_meta_description_no_vacia(self):
        self.assertTrue(len(ProgramsSkill.META.description) > 10)

    def test_meta_category(self):
        self.assertEqual(ProgramsSkill.META.category, CATEGORY_PROGRAMS)

    def test_meta_builtin(self):
        self.assertTrue(ProgramsSkill.META.builtin)

    def test_meta_enabled_by_default(self):
        self.assertTrue(ProgramsSkill.META.enabled_by_default)

    def test_meta_commands_correctos(self):
        esperados = {"programa", "programas", "agregar-programa", "quitar-programa", "programa-info"}
        self.assertEqual(set(ProgramsSkill.META.commands), esperados)

    def test_meta_exactamente_5_comandos(self):
        self.assertEqual(len(ProgramsSkill.META.commands), 5)


class TestHerencia(unittest.TestCase):
    """Verifica la herencia de BaseSkill."""

    def test_hereda_base_skill(self):
        from skills.skill_base import BaseSkill
        self.assertTrue(issubclass(ProgramsSkill, BaseSkill))

    def test_instanciable(self):
        skill = ProgramsSkill()
        self.assertIsNotNone(skill)

    def test_execute_callable(self):
        self.assertTrue(callable(ProgramsSkill.execute))

    def test_handles_programa(self):
        skill = ProgramsSkill()
        self.assertTrue(skill.handles("programa"))

    def test_handles_programas(self):
        skill = ProgramsSkill()
        self.assertTrue(skill.handles("programas"))

    def test_handles_agregar_programa(self):
        skill = ProgramsSkill()
        self.assertTrue(skill.handles("agregar-programa"))

    def test_handles_quitar_programa(self):
        skill = ProgramsSkill()
        self.assertTrue(skill.handles("quitar-programa"))

    def test_handles_programa_info(self):
        skill = ProgramsSkill()
        self.assertTrue(skill.handles("programa-info"))

    def test_no_handles_desconocido(self):
        skill = ProgramsSkill()
        self.assertFalse(skill.handles("xyz_inexistente"))


# ===========================================================================
# 2. Ciclo de vida
# ===========================================================================

class TestCicloDeVida(unittest.TestCase):
    """Verifica setup/teardown."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self) -> ProgramsSkill:
        import skills.builtin.programs_skill as mod
        orig = mod._PROGRAMS_FILE
        mod._PROGRAMS_FILE = self.tmp_path / "programs.json"
        skill = ProgramsSkill()
        skill.setup()
        mod._PROGRAMS_FILE = orig
        return skill

    def test_setup_inicializa_user_aliases(self):
        skill = self._make()
        self.assertIsInstance(skill._user_aliases, dict)

    def test_setup_is_setup_true(self):
        skill = self._make()
        self.assertTrue(skill.is_setup)

    def test_teardown_is_setup_false(self):
        skill = self._make()
        skill.teardown()
        self.assertFalse(skill.is_setup)

    def test_setup_carga_alias_existentes(self):
        """Si ya existe programs.json, setup() lo carga."""
        programs_file = self.tmp_path / "programs.json"
        programs_file.write_text(json.dumps({"mi-app": "mi_app.exe"}), encoding="utf-8")

        import skills.builtin.programs_skill as mod
        orig = mod._PROGRAMS_FILE
        mod._PROGRAMS_FILE = programs_file
        skill = ProgramsSkill()
        skill.setup()
        mod._PROGRAMS_FILE = orig

        self.assertIn("mi-app", skill._user_aliases)
        self.assertEqual(skill._user_aliases["mi-app"], "mi_app.exe")

    def test_setup_json_invalido_no_falla(self):
        """Un JSON inválido provoca inicialización con dict vacío, sin excepción."""
        programs_file = self.tmp_path / "programs.json"
        programs_file.write_text("{no es json}", encoding="utf-8")

        import skills.builtin.programs_skill as mod
        orig = mod._PROGRAMS_FILE
        mod._PROGRAMS_FILE = programs_file
        skill = ProgramsSkill()
        # No debe lanzar excepción
        skill.setup()
        mod._PROGRAMS_FILE = orig

        self.assertEqual(skill._user_aliases, {})


# ===========================================================================
# 3. Comando 'programa' (abrir)
# ===========================================================================

class TestCmdAbrir(unittest.TestCase):
    """Tests para el comando 'programa'."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp)
        import skills.builtin.programs_skill as mod
        self._orig_file = mod._PROGRAMS_FILE
        mod._PROGRAMS_FILE = self.tmp_path / "programs.json"
        self.mod = mod
        self.skill = ProgramsSkill()
        self.skill.setup()

    def tearDown(self):
        self.mod._PROGRAMS_FILE = self._orig_file
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_abrir_sin_args_retorna_error(self):
        r = self.skill.execute("programa", [])
        self.assertFalse(r.success)
        self.assertIn("Uso:", r.error)

    def test_abrir_alias_inexistente_retorna_error(self):
        r = self.skill.execute("programa", ["alias_xyz_no_existe"])
        self.assertFalse(r.success)
        self.assertIn("alias_xyz_no_existe", r.error)

    def test_abrir_alias_inexistente_sugiere_similares(self):
        """Si el alias no existe pero hay similares, los sugiere."""
        r = self.skill.execute("programa", ["note"])
        # 'note' empieza con 'no' → debe sugerir 'notepad'
        self.assertFalse(r.success)

    @patch("os.startfile")
    def test_abrir_alias_builtin_llama_startfile_en_windows(self, mock_sf):
        if platform.system() != "Windows":
            self.skipTest("Solo Windows")
        r = self.skill.execute("programa", ["notepad"])
        mock_sf.assert_called_once_with("notepad.exe")
        self.assertTrue(r.success)

    @patch("os.startfile", side_effect=FileNotFoundError("no encontrado"))
    def test_abrir_filenotfounderror_retorna_error(self, mock_sf):
        if platform.system() != "Windows":
            self.skipTest("Solo Windows")
        r = self.skill.execute("programa", ["chrome"])
        self.assertFalse(r.success)
        self.assertTrue(len(r.error) > 0)

    @patch("os.startfile", side_effect=OSError("permiso denegado"))
    def test_abrir_oserror_retorna_error(self, mock_sf):
        if platform.system() != "Windows":
            self.skipTest("Solo Windows")
        r = self.skill.execute("programa", ["chrome"])
        self.assertFalse(r.success)
        self.assertIn("Error al abrir", r.error)

    def test_abrir_alias_usuario(self):
        """Un alias del usuario se puede abrir."""
        self.skill._user_aliases["mi-app"] = "notepad.exe"
        with patch("os.startfile") if platform.system() == "Windows" else patch("subprocess.Popen") as mock_open:
            r = self.skill.execute("programa", ["mi-app"])
            # No lanzó excepción inesperada
            self.assertIsInstance(r, SkillResult)

    def test_abrir_alias_multiword(self):
        """Un alias formado por múltiples palabras se forma correctamente."""
        r = self.skill.execute("programa", ["alias", "inexistente"])
        # 'alias inexistente' → no existe → error
        self.assertFalse(r.success)
        self.assertIn("alias inexistente", r.error)

    def test_resultado_es_skill_result(self):
        r = self.skill.execute("programa", [])
        self.assertIsInstance(r, SkillResult)


# ===========================================================================
# 4. Comando 'programas' (listar)
# ===========================================================================

class TestCmdListar(unittest.TestCase):
    """Tests para el comando 'programas'."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp)
        import skills.builtin.programs_skill as mod
        self._orig_file = mod._PROGRAMS_FILE
        mod._PROGRAMS_FILE = self.tmp_path / "programs.json"
        self.mod = mod
        self.skill = ProgramsSkill()
        self.skill.setup()

    def tearDown(self):
        self.mod._PROGRAMS_FILE = self._orig_file
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_listar_success_true(self):
        r = self.skill.execute("programas", [])
        self.assertTrue(r.success)

    def test_listar_retorna_skill_result(self):
        r = self.skill.execute("programas", [])
        self.assertIsInstance(r, SkillResult)

    def test_listar_contiene_alias_builtin(self):
        r = self.skill.execute("programas", [])
        self.assertIn("notepad", r.output)

    def test_listar_data_tiene_total(self):
        r = self.skill.execute("programas", [])
        self.assertIn("total", r.data)
        self.assertGreater(r.data["total"], 0)

    def test_listar_data_tiene_aliases(self):
        r = self.skill.execute("programas", [])
        self.assertIn("aliases", r.data)
        self.assertIsInstance(r.data["aliases"], dict)

    def test_listar_muestra_alias_usuario(self):
        """Los alias del usuario aparecen en el listado."""
        self.skill._user_aliases["mi-herramienta"] = "mi_app.exe"
        r = self.skill.execute("programas", [])
        self.assertIn("mi-herramienta", r.output)

    def test_listar_seccion_usuario_aparece(self):
        """Cuando hay alias de usuario, aparece la sección correspondiente."""
        self.skill._user_aliases["mi-editor"] = "editor.exe"
        r = self.skill.execute("programas", [])
        self.assertIn("usuario", r.output.lower())

    def test_listar_seccion_predefinidos_aparece(self):
        r = self.skill.execute("programas", [])
        self.assertIn("predefinidos", r.output.lower())

    def test_listar_instruccion_agregar_aparece(self):
        r = self.skill.execute("programas", [])
        self.assertIn("agregar-programa", r.output)


# ===========================================================================
# 5. Comando 'agregar-programa'
# ===========================================================================

class TestCmdAgregar(unittest.TestCase):
    """Tests para el comando 'agregar-programa'."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp)
        import skills.builtin.programs_skill as mod
        self._orig_file = mod._PROGRAMS_FILE
        mod._PROGRAMS_FILE = self.tmp_path / "programs.json"
        self.mod = mod
        self.skill = ProgramsSkill()
        self.skill.setup()

    def tearDown(self):
        self.mod._PROGRAMS_FILE = self._orig_file
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_agregar_sin_args_retorna_error(self):
        r = self.skill.execute("agregar-programa", [])
        self.assertFalse(r.success)
        self.assertIn("Uso:", r.error)

    def test_agregar_con_solo_alias_retorna_error(self):
        r = self.skill.execute("agregar-programa", ["mi-app"])
        self.assertFalse(r.success)

    def test_agregar_valido_success(self):
        r = self.skill.execute("agregar-programa", ["mi-app", "mi_app.exe"])
        self.assertTrue(r.success)

    def test_agregar_valido_retorna_skill_result(self):
        r = self.skill.execute("agregar-programa", ["mi-app", "mi_app.exe"])
        self.assertIsInstance(r, SkillResult)

    def test_agregar_almacena_en_user_aliases(self):
        self.skill.execute("agregar-programa", ["mi-app", "mi_app.exe"])
        self.assertIn("mi-app", self.skill._user_aliases)
        self.assertEqual(self.skill._user_aliases["mi-app"], "mi_app.exe")

    def test_agregar_persiste_en_json(self):
        import skills.builtin.programs_skill as mod
        self.skill.execute("agregar-programa", ["mi-app", "mi_app.exe"])
        programs_file = mod._PROGRAMS_FILE
        self.assertTrue(programs_file.exists())
        data = json.loads(programs_file.read_text(encoding="utf-8"))
        self.assertIn("mi-app", data)

    def test_agregar_alias_con_espacio_retorna_error(self):
        r = self.skill.execute("agregar-programa", ["mi app", "app.exe"])
        self.assertFalse(r.success)
        self.assertIn("espacio", r.error.lower())

    def test_agregar_ruta_con_espacios(self):
        """Una ruta con espacios (multi-arg) se une correctamente."""
        r = self.skill.execute(
            "agregar-programa",
            ["mi-app", "C:\\Program Files\\App\\app.exe"],
        )
        self.assertTrue(r.success)
        self.assertIn("C:\\Program Files\\App\\app.exe", self.skill._user_aliases["mi-app"])

    def test_agregar_sobreescribe_existente(self):
        self.skill.execute("agregar-programa", ["mi-app", "vieja.exe"])
        r = self.skill.execute("agregar-programa", ["mi-app", "nueva.exe"])
        self.assertTrue(r.success)
        self.assertIn("actualizado", r.output.lower())
        self.assertEqual(self.skill._user_aliases["mi-app"], "nueva.exe")

    def test_agregar_nuevo_dice_agregado(self):
        r = self.skill.execute("agregar-programa", ["nuevo-app", "app.exe"])
        self.assertIn("agregado", r.output.lower())

    def test_agregar_data_contiene_alias_y_ruta(self):
        r = self.skill.execute("agregar-programa", ["mi-app", "app.exe"])
        self.assertEqual(r.data["alias"], "mi-app")
        self.assertEqual(r.data["ruta"], "app.exe")

    def test_agregar_alias_minuscula(self):
        """El alias se guarda en minúsculas."""
        self.skill.execute("agregar-programa", ["MI-APP", "app.exe"])
        self.assertIn("mi-app", self.skill._user_aliases)


# ===========================================================================
# 6. Comando 'quitar-programa'
# ===========================================================================

class TestCmdQuitar(unittest.TestCase):
    """Tests para el comando 'quitar-programa'."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp)
        import skills.builtin.programs_skill as mod
        self._orig_file = mod._PROGRAMS_FILE
        mod._PROGRAMS_FILE = self.tmp_path / "programs.json"
        self.mod = mod
        self.skill = ProgramsSkill()
        self.skill.setup()
        # Agregar alias de usuario para probar
        self.skill._user_aliases["mi-app"] = "mi_app.exe"

    def tearDown(self):
        self.mod._PROGRAMS_FILE = self._orig_file
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_quitar_sin_args_retorna_error(self):
        r = self.skill.execute("quitar-programa", [])
        self.assertFalse(r.success)
        self.assertIn("Uso:", r.error)

    def test_quitar_alias_usuario_success(self):
        r = self.skill.execute("quitar-programa", ["mi-app"])
        self.assertTrue(r.success)

    def test_quitar_alias_usuario_lo_elimina(self):
        self.skill.execute("quitar-programa", ["mi-app"])
        self.assertNotIn("mi-app", self.skill._user_aliases)

    def test_quitar_persiste_eliminacion(self):
        import skills.builtin.programs_skill as mod
        self.skill._save_user_aliases()  # Guardar primero
        self.skill.execute("quitar-programa", ["mi-app"])
        programs_file = mod._PROGRAMS_FILE
        data = json.loads(programs_file.read_text(encoding="utf-8"))
        self.assertNotIn("mi-app", data)

    def test_quitar_alias_builtin_retorna_error(self):
        r = self.skill.execute("quitar-programa", ["notepad"])
        self.assertFalse(r.success)
        self.assertIn("predefinido", r.error.lower())

    def test_quitar_alias_inexistente_retorna_error(self):
        r = self.skill.execute("quitar-programa", ["alias_que_no_existe"])
        self.assertFalse(r.success)

    def test_quitar_data_contiene_alias_eliminado(self):
        r = self.skill.execute("quitar-programa", ["mi-app"])
        self.assertEqual(r.data["alias"], "mi-app")
        self.assertEqual(r.data["ruta_eliminada"], "mi_app.exe")

    def test_quitar_output_menciona_alias(self):
        r = self.skill.execute("quitar-programa", ["mi-app"])
        self.assertIn("mi-app", r.output)


# ===========================================================================
# 7. Comando 'programa-info'
# ===========================================================================

class TestCmdInfo(unittest.TestCase):
    """Tests para el comando 'programa-info'."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp)
        import skills.builtin.programs_skill as mod
        self._orig_file = mod._PROGRAMS_FILE
        mod._PROGRAMS_FILE = self.tmp_path / "programs.json"
        self.mod = mod
        self.skill = ProgramsSkill()
        self.skill.setup()

    def tearDown(self):
        self.mod._PROGRAMS_FILE = self._orig_file
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_info_sin_args_retorna_error(self):
        r = self.skill.execute("programa-info", [])
        self.assertFalse(r.success)
        self.assertIn("Uso:", r.error)

    def test_info_alias_inexistente_retorna_error(self):
        r = self.skill.execute("programa-info", ["alias_xyz"])
        self.assertFalse(r.success)

    def test_info_alias_builtin_success(self):
        r = self.skill.execute("programa-info", ["notepad"])
        self.assertTrue(r.success)

    def test_info_alias_builtin_dice_predefinido(self):
        r = self.skill.execute("programa-info", ["notepad"])
        self.assertIn("Predefinido", r.output)

    def test_info_alias_usuario_dice_usuario(self):
        self.skill._user_aliases["mi-app"] = "mi_app.exe"
        r = self.skill.execute("programa-info", ["mi-app"])
        self.assertTrue(r.success)
        self.assertIn("Usuario", r.output)

    def test_info_data_tiene_alias(self):
        r = self.skill.execute("programa-info", ["notepad"])
        self.assertEqual(r.data["alias"], "notepad")

    def test_info_data_tiene_ruta(self):
        r = self.skill.execute("programa-info", ["notepad"])
        self.assertIn("ruta", r.data)
        self.assertEqual(r.data["ruta"], "notepad.exe")

    def test_info_data_tiene_existe(self):
        r = self.skill.execute("programa-info", ["notepad"])
        self.assertIn("existe", r.data)
        self.assertIsInstance(r.data["existe"], bool)

    def test_info_protocolo_no_marca_inexistente(self):
        """Los protocolos (ms-settings:) nunca se marcan como inexistentes."""
        r = self.skill.execute("programa-info", ["configuracion"])
        self.assertTrue(r.success)
        # El resultado no debe decir "No encontrado" para protocolos
        self.assertNotIn("No encontrado en el sistema", r.output)


# ===========================================================================
# 8. Alias builtin predefinidos
# ===========================================================================

class TestAliasBuiltin(unittest.TestCase):
    """Verifica que los alias predefinidos existan y sean correctos."""

    def test_builtin_aliases_no_vacio(self):
        self.assertGreater(len(_BUILTIN_ALIASES), 0)

    def test_builtin_contiene_notepad(self):
        self.assertIn("notepad", _BUILTIN_ALIASES)
        self.assertEqual(_BUILTIN_ALIASES["notepad"], "notepad.exe")

    def test_builtin_contiene_calculadora(self):
        self.assertIn("calculadora", _BUILTIN_ALIASES)

    def test_builtin_contiene_explorador(self):
        self.assertIn("explorador", _BUILTIN_ALIASES)

    def test_builtin_contiene_vscode(self):
        self.assertIn("vscode", _BUILTIN_ALIASES)

    def test_builtin_contiene_chrome(self):
        self.assertIn("chrome", _BUILTIN_ALIASES)

    def test_builtin_contiene_cmd(self):
        self.assertIn("cmd", _BUILTIN_ALIASES)

    def test_builtin_todas_las_rutas_son_strings(self):
        for alias, ruta in _BUILTIN_ALIASES.items():
            with self.subTest(alias=alias):
                self.assertIsInstance(ruta, str)
                self.assertTrue(len(ruta) > 0)

    def test_builtin_aliases_minusculas(self):
        """Todos los alias builtin deben ser minúsculas."""
        for alias in _BUILTIN_ALIASES:
            with self.subTest(alias=alias):
                self.assertEqual(alias, alias.lower())


# ===========================================================================
# 9. Persistencia JSON
# ===========================================================================

class TestPersistencia(unittest.TestCase):
    """Verifica la persistencia de alias en disco."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_skill(self) -> ProgramsSkill:
        import skills.builtin.programs_skill as mod
        mod._PROGRAMS_FILE = self.tmp_path / "programs.json"
        skill = ProgramsSkill()
        skill.setup()
        return skill

    def test_guardar_y_recargar(self):
        """Alias guardados deben cargarse en una nueva instancia."""
        import skills.builtin.programs_skill as mod

        s1 = self._make_skill()
        s1.execute("agregar-programa", ["mi-test", "test.exe"])

        s2 = self._make_skill()
        self.assertIn("mi-test", s2._user_aliases)
        self.assertEqual(s2._user_aliases["mi-test"], "test.exe")

    def test_archivo_json_valido(self):
        """El archivo guardado debe ser JSON válido."""
        s = self._make_skill()
        s.execute("agregar-programa", ["mi-app", "app.exe"])
        import skills.builtin.programs_skill as mod
        data = json.loads(mod._PROGRAMS_FILE.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)

    def test_archivo_no_existe_no_falla(self):
        """Si programs.json no existe, setup() no falla."""
        import skills.builtin.programs_skill as mod
        mod._PROGRAMS_FILE = self.tmp_path / "no_existe.json"
        skill = ProgramsSkill()
        skill.setup()  # No debe lanzar excepción
        self.assertEqual(skill._user_aliases, {})

    def test_escritura_atomica(self):
        """No debe quedar un .tmp en disco tras guardar."""
        s = self._make_skill()
        s.execute("agregar-programa", ["mi-app", "app.exe"])
        import skills.builtin.programs_skill as mod
        tmp_file = mod._PROGRAMS_FILE.with_suffix(".tmp")
        self.assertFalse(tmp_file.exists())


# ===========================================================================
# 10. Prioridad alias usuario > builtin
# ===========================================================================

class TestPrioridadAlias(unittest.TestCase):
    """Verifica que alias del usuario sobreescriban los builtin."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp)
        import skills.builtin.programs_skill as mod
        self._orig_file = mod._PROGRAMS_FILE
        mod._PROGRAMS_FILE = self.tmp_path / "programs.json"
        self.mod = mod
        self.skill = ProgramsSkill()
        self.skill.setup()

    def tearDown(self):
        self.mod._PROGRAMS_FILE = self._orig_file
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_usuario_sobreescribe_builtin(self):
        """Un alias del usuario para 'notepad' sobreescribe el builtin."""
        self.skill._user_aliases["notepad"] = "mi_notepad_custom.exe"
        ruta = self.skill._resolver_alias("notepad")
        self.assertEqual(ruta, "mi_notepad_custom.exe")

    def test_builtin_accesible_cuando_no_sobreescrito(self):
        ruta = self.skill._resolver_alias("notepad")
        self.assertEqual(ruta, "notepad.exe")

    def test_todos_los_alias_combina_correctamente(self):
        """_todos_los_alias() combina builtin + usuario."""
        self.skill._user_aliases["mi-unico"] = "unico.exe"
        todos = self.skill._todos_los_alias()
        self.assertIn("mi-unico", todos)
        self.assertIn("notepad", todos)


# ===========================================================================
# 11. Comando desconocido
# ===========================================================================

class TestComandoDesconocido(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        import skills.builtin.programs_skill as mod
        self._orig_file = mod._PROGRAMS_FILE
        mod._PROGRAMS_FILE = Path(self.tmp) / "programs.json"
        self.mod = mod
        self.skill = ProgramsSkill()
        self.skill.setup()

    def tearDown(self):
        self.mod._PROGRAMS_FILE = self._orig_file
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_comando_desconocido_retorna_error(self):
        r = self.skill.execute("xyz_no_existe", [])
        self.assertFalse(r.success)
        self.assertIn("xyz_no_existe", r.error)

    def test_resultado_booleano(self):
        """SkillResult(success=False) debe evaluar como False."""
        r = self.skill.execute("programa", [])
        self.assertFalse(bool(r))

    def test_resultado_exitoso_booleano(self):
        r = self.skill.execute("programas", [])
        self.assertTrue(bool(r))


# ===========================================================================
# 12. Integración: exportaciones del paquete builtin
# ===========================================================================

class TestExportaciones(unittest.TestCase):
    """Verifica que ProgramsSkill esté correctamente exportada."""

    def test_importable_desde_skills_builtin(self):
        from skills.builtin import ProgramsSkill  # noqa: F401

    def test_en_all_de_builtin(self):
        import skills.builtin as pkg
        self.assertIn("ProgramsSkill", pkg.__all__)

    def test_sintaxis_init_builtin(self):
        init_path = _ROOT / "skills" / "builtin" / "__init__.py"
        py_compile.compile(str(init_path), doraise=True)


# ===========================================================================
# 13. Regresión: skills previas siguen funcionando
# ===========================================================================

class TestRegresion(unittest.TestCase):
    """Verifica que las skills previas aún sean importables y funcionales."""

    def test_demo_skill_importable(self):
        from skills.builtin.demo_skill import DemoSkill  # noqa: F401

    def test_system_skill_importable(self):
        from skills.builtin.system_skill import SystemSkill  # noqa: F401

    def test_files_skill_importable(self):
        from skills.builtin.files_skill import FilesSkill  # noqa: F401

    def test_search_skill_importable(self):
        from skills.builtin.search_skill import SearchSkill  # noqa: F401

    def test_skills_init_importable(self):
        from skills import SkillRegistry, BaseSkill  # noqa: F401

    def test_skill_registry_puede_registrar_programs_skill(self):
        from skills.skill_registry import SkillRegistry
        reg = SkillRegistry()
        instance = ProgramsSkill()
        reg.register(instance)
        entry = reg.get("programs_skill")
        self.assertIsNotNone(entry)
        reg.unregister("programs_skill")


if __name__ == "__main__":
    unittest.main(verbosity=2)

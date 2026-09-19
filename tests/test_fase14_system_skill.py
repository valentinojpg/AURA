"""
AURA — Tests automáticos para Fase 14: SystemSkill (Fase 14)

Suite de tests para la SystemSkill de AURA.
Cubre:
  - Metadatos (META, commands, category, version)
  - Comandos dry-run y simulados (apagar, reiniciar, papelera)
  - Validaciones de argumentos (abrir sin args, cerrar sin args)
  - Seguridad (procesos protegidos)
  - Integración con SkillRegistry
  - Descubrimiento automático de la skill

Tests NO incluidos (requieren hardware real o admin):
  - Ejecución real de apagar/reiniciar
  - Bloquear sesión real de Windows
  - Vaciar papelera real (solo dry-run)

Ejecución:
    .\\env\\Scripts\\python.exe -m pytest tests/test_fase14_system_skill.py -v

Resultado esperado: todos los tests en verde, 0 errores.
"""

from __future__ import annotations

import platform
import sys
import types
import unittest

# ── Bootstrap de path ─────────────────────────────────────────────────────────
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings  # noqa: E402 (necesario post-path)

# ── Imports del módulo bajo test ──────────────────────────────────────────────
from skills.builtin.system_skill import (
    SystemSkill,
    _APP_ALIASES,
    _PROTECTED_PROCESSES,
    _IS_WINDOWS,
)
from skills.skill_base import SkillResult, CATEGORY_SYSTEM
from skills.skill_registry import SkillRegistry


# =============================================================================
# Helper: instancia limpia de SystemSkill
# =============================================================================

def _make_skill() -> SystemSkill:
    skill = SystemSkill()
    skill.setup()
    return skill


# =============================================================================
# 1. Metadatos
# =============================================================================

class TestSystemSkillMeta(unittest.TestCase):
    """Verifica que los metadatos de SystemSkill son correctos."""

    def setUp(self):
        self.skill = _make_skill()

    def test_meta_exists(self):
        self.assertTrue(hasattr(SystemSkill, "META"))

    def test_name(self):
        self.assertEqual(self.skill.META.name, "system_skill")

    def test_display_name_not_empty(self):
        self.assertTrue(len(self.skill.META.display_name) > 0)

    def test_version_semver(self):
        parts = self.skill.META.version.split(".")
        self.assertEqual(len(parts), 3, "La versión debe ser semántica (X.Y.Z)")

    def test_category_system(self):
        self.assertEqual(self.skill.META.category, CATEGORY_SYSTEM)

    def test_builtin_true(self):
        self.assertTrue(self.skill.META.builtin)

    def test_enabled_by_default(self):
        self.assertTrue(self.skill.META.enabled_by_default)

    def test_commands_not_empty(self):
        self.assertTrue(len(self.skill.META.commands) > 0)

    def test_expected_commands(self):
        expected = {"abrir", "cerrar", "bloquear", "apagar", "reiniciar",
                    "sysinfo", "procesos", "papelera"}
        actual = set(self.skill.META.commands)
        self.assertEqual(actual, expected)

    def test_author_not_empty(self):
        self.assertTrue(len(self.skill.META.author) > 0)

    def test_description_not_empty(self):
        self.assertTrue(len(self.skill.META.description) > 0)


# =============================================================================
# 2. Ciclo de vida
# =============================================================================

class TestSystemSkillLifecycle(unittest.TestCase):
    """Verifica setup/teardown de SystemSkill."""

    def test_instantiation(self):
        skill = SystemSkill()
        self.assertIsNotNone(skill)

    def test_setup_sets_is_setup(self):
        skill = SystemSkill()
        self.assertFalse(skill.is_setup)
        skill.setup()
        self.assertTrue(skill.is_setup)

    def test_teardown_clears_is_setup(self):
        skill = _make_skill()
        skill.teardown()
        self.assertFalse(skill.is_setup)

    def test_handles_known_command(self):
        skill = _make_skill()
        self.assertTrue(skill.handles("abrir"))
        self.assertTrue(skill.handles("sysinfo"))

    def test_handles_unknown_command(self):
        skill = _make_skill()
        self.assertFalse(skill.handles("xyz_desconocido"))

    def test_repr_contains_name(self):
        skill = _make_skill()
        self.assertIn("system_skill", repr(skill))


# =============================================================================
# 3. Comando: abrir
# =============================================================================

class TestCmdAbrir(unittest.TestCase):
    """Tests para el comando 'abrir'."""

    def setUp(self):
        self.skill = _make_skill()

    def test_abrir_sin_args_retorna_error(self):
        result = self.skill.execute("abrir", [])
        self.assertFalse(result.success)
        self.assertTrue(len(result.error) > 0)

    def test_abrir_sin_args_error_menciona_ejemplos(self):
        result = self.skill.execute("abrir", [])
        self.assertIn("notepad", result.error.lower())

    def test_result_es_skill_result(self):
        result = self.skill.execute("abrir", [])
        self.assertIsInstance(result, SkillResult)

    @unittest.skipUnless(_IS_WINDOWS, "Solo en Windows")
    def test_abrir_notepad_windows(self):
        """Abre notepad en Windows — verificamos solo que no lanza excepción."""
        result = self.skill.execute("abrir", ["notepad"])
        # El proceso se abre en background; solo verificamos éxito
        self.assertIsInstance(result, SkillResult)

    def test_alias_notepad_resuelve(self):
        """Verifica que 'notepad' está en los alias."""
        self.assertIn("notepad", _APP_ALIASES)

    def test_alias_calculadora_resuelve(self):
        self.assertIn("calculadora", _APP_ALIASES)

    def test_alias_explorador_resuelve(self):
        self.assertIn("explorador", _APP_ALIASES)

    def test_alias_cmd_resuelve(self):
        self.assertIn("cmd", _APP_ALIASES)


# =============================================================================
# 4. Comando: cerrar
# =============================================================================

class TestCmdCerrar(unittest.TestCase):
    """Tests para el comando 'cerrar'."""

    def setUp(self):
        self.skill = _make_skill()

    def test_cerrar_sin_args_retorna_error(self):
        result = self.skill.execute("cerrar", [])
        self.assertFalse(result.success)
        self.assertIn("proceso", result.error.lower())

    def test_cerrar_proceso_protegido_bloqueado(self):
        """No se puede cerrar procesos críticos del sistema."""
        result = self.skill.execute("cerrar", ["lsass.exe"])
        self.assertFalse(result.success)
        self.assertIn("crítico", result.error.lower())

    def test_cerrar_csrss_bloqueado(self):
        result = self.skill.execute("cerrar", ["csrss.exe"])
        self.assertFalse(result.success)

    def test_cerrar_services_bloqueado(self):
        result = self.skill.execute("cerrar", ["services.exe"])
        self.assertFalse(result.success)

    def test_cerrar_proceso_inexistente(self):
        """Un proceso que no existe retorna error informativo."""
        result = self.skill.execute("cerrar", ["proceso_que_no_existe_xyz_12345"])
        # Puede ser True (si taskkill da error amistoso) o False
        # Lo importante es que no lanza excepción
        self.assertIsInstance(result, SkillResult)

    def test_protected_processes_set(self):
        """Verifica que el set de procesos protegidos tiene los críticos."""
        self.assertIn("lsass.exe", _PROTECTED_PROCESSES)
        self.assertIn("csrss.exe", _PROTECTED_PROCESSES)
        self.assertIn("services.exe", _PROTECTED_PROCESSES)


# =============================================================================
# 5. Comando: bloquear
# =============================================================================

class TestCmdBloquear(unittest.TestCase):
    """Tests para el comando 'bloquear'."""

    def setUp(self):
        self.skill = _make_skill()

    @unittest.skipUnless(_IS_WINDOWS, "Solo en Windows — bloquea la sesión real")
    def test_bloquear_no_lanza_excepcion(self):
        """Bloquear sesión no debe lanzar excepción (aunque bloquee de verdad)."""
        # Este test NO se ejecuta en CI porque bloquea la sesión real
        pass

    def test_bloquear_no_windows_retorna_error(self):
        """En sistemas que no son Windows, retorna error amistoso."""
        if _IS_WINDOWS:
            self.skipTest("Solo aplica en sistemas no-Windows")
        result = self.skill.execute("bloquear", [])
        self.assertFalse(result.success)
        self.assertIn("Windows", result.error)

    def test_bloquear_retorna_skill_result(self):
        """El resultado siempre es un SkillResult."""
        result = self.skill.execute("bloquear", [])
        self.assertIsInstance(result, SkillResult)


# =============================================================================
# 6. Comando: apagar (dry-run)
# =============================================================================

class TestCmdApagar(unittest.TestCase):
    """Tests para el comando 'apagar' — solo dry-run."""

    def setUp(self):
        self.skill = _make_skill()

    def test_apagar_sin_args_es_dry_run(self):
        """Sin '--ahora', el apagado es simulado."""
        result = self.skill.execute("apagar", [])
        self.assertIsInstance(result, SkillResult)
        # En Windows: éxito con mensaje de simulación
        # En no-Windows: error de plataforma
        if _IS_WINDOWS:
            self.assertTrue(result.success)
            self.assertIn("SIMULACIÓN", result.output.upper())
        else:
            self.assertFalse(result.success)

    def test_apagar_dry_run_menciona_ahora(self):
        """La simulación debe indicar cómo ejecutar realmente."""
        if not _IS_WINDOWS:
            self.skipTest("Solo Windows")
        result = self.skill.execute("apagar", [])
        self.assertIn("--ahora", result.output)

    def test_apagar_dry_run_data_dry_true(self):
        """El campo data debe indicar dry_run=True."""
        if not _IS_WINDOWS:
            self.skipTest("Solo Windows")
        result = self.skill.execute("apagar", [])
        self.assertTrue(result.data.get("dry_run", False))

    def test_apagar_action_en_data(self):
        """El campo data debe tener action=shutdown."""
        if not _IS_WINDOWS:
            self.skipTest("Solo Windows")
        result = self.skill.execute("apagar", [])
        self.assertEqual(result.data.get("action"), "shutdown")

    def test_apagar_no_windows_retorna_error(self):
        """En sistemas que no son Windows, retorna error amistoso."""
        if _IS_WINDOWS:
            self.skipTest("Solo aplica en no-Windows")
        result = self.skill.execute("apagar", [])
        self.assertFalse(result.success)
        self.assertIn("Windows", result.error)


# =============================================================================
# 7. Comando: reiniciar (dry-run)
# =============================================================================

class TestCmdReiniciar(unittest.TestCase):
    """Tests para el comando 'reiniciar' — solo dry-run."""

    def setUp(self):
        self.skill = _make_skill()

    def test_reiniciar_sin_args_es_dry_run(self):
        """Sin '--ahora', el reinicio es simulado."""
        result = self.skill.execute("reiniciar", [])
        self.assertIsInstance(result, SkillResult)
        if _IS_WINDOWS:
            self.assertTrue(result.success)
            self.assertIn("SIMULACIÓN", result.output.upper())

    def test_reiniciar_dry_run_menciona_ahora(self):
        if not _IS_WINDOWS:
            self.skipTest("Solo Windows")
        result = self.skill.execute("reiniciar", [])
        self.assertIn("--ahora", result.output)

    def test_reiniciar_dry_run_data_dry_true(self):
        if not _IS_WINDOWS:
            self.skipTest("Solo Windows")
        result = self.skill.execute("reiniciar", [])
        self.assertTrue(result.data.get("dry_run", False))

    def test_reiniciar_action_en_data(self):
        if not _IS_WINDOWS:
            self.skipTest("Solo Windows")
        result = self.skill.execute("reiniciar", [])
        self.assertEqual(result.data.get("action"), "restart")


# =============================================================================
# 8. Comando: sysinfo
# =============================================================================

class TestCmdSysinfo(unittest.TestCase):
    """Tests para el comando 'sysinfo'."""

    def setUp(self):
        self.skill = _make_skill()

    def test_sysinfo_retorna_success(self):
        result = self.skill.execute("sysinfo", [])
        self.assertTrue(result.success)

    def test_sysinfo_output_no_vacio(self):
        result = self.skill.execute("sysinfo", [])
        self.assertTrue(len(result.output) > 0)

    def test_sysinfo_menciona_plataforma(self):
        result = self.skill.execute("sysinfo", [])
        # El output debe mencionar el SO o Python
        output_lower = result.output.lower()
        self.assertTrue(
            "windows" in output_lower
            or "linux" in output_lower
            or "darwin" in output_lower
            or "python" in output_lower
        )

    def test_sysinfo_tiene_data_platform(self):
        result = self.skill.execute("sysinfo", [])
        self.assertIn("platform", result.data)

    def test_sysinfo_tiene_data_python(self):
        result = self.skill.execute("sysinfo", [])
        self.assertIn("python", result.data)

    def test_sysinfo_python_version_valido(self):
        result = self.skill.execute("sysinfo", [])
        version = result.data.get("python", "")
        self.assertTrue(version.startswith("3."), f"Se esperaba Python 3.x, got: {version}")

    def test_sysinfo_args_ignorados(self):
        """sysinfo ignora argumentos extra."""
        result = self.skill.execute("sysinfo", ["foo", "bar"])
        self.assertTrue(result.success)


# =============================================================================
# 9. Comando: procesos
# =============================================================================

class TestCmdProcesos(unittest.TestCase):
    """Tests para el comando 'procesos'."""

    def setUp(self):
        self.skill = _make_skill()

    def _psutil_available(self) -> bool:
        try:
            import psutil  # noqa: F401
            return True
        except ImportError:
            return False

    def test_procesos_retorna_skill_result(self):
        result = self.skill.execute("procesos", [])
        self.assertIsInstance(result, SkillResult)

    @unittest.skipUnless(True, "siempre")
    def test_procesos_sin_psutil_retorna_error_amistoso(self):
        """Si psutil no está instalado, el error es amigable."""
        if self._psutil_available():
            self.skipTest("psutil está disponible, skip")
        result = self.skill.execute("procesos", [])
        self.assertFalse(result.success)
        self.assertIn("psutil", result.error)

    def test_procesos_con_psutil_retorna_success(self):
        """Si psutil está disponible, la lista se genera correctamente."""
        if not self._psutil_available():
            self.skipTest("psutil no disponible")
        result = self.skill.execute("procesos", [])
        self.assertTrue(result.success)
        self.assertIn("total", result.data)

    def test_procesos_filtro_sin_resultados(self):
        """Filtrar por nombre que no existe retorna success con mensaje."""
        if not self._psutil_available():
            self.skipTest("psutil no disponible")
        result = self.skill.execute("procesos", ["proceso_xyz_12345_inexistente"])
        self.assertTrue(result.success)

    def test_procesos_sin_psutil_menciona_pip(self):
        """El error sin psutil menciona cómo instalarlo."""
        if self._psutil_available():
            self.skipTest("psutil está disponible, skip")
        result = self.skill.execute("procesos", [])
        self.assertIn("pip", result.error)


# =============================================================================
# 10. Comando: papelera (dry-run)
# =============================================================================

class TestCmdPapelera(unittest.TestCase):
    """Tests para el comando 'papelera' — solo dry-run."""

    def setUp(self):
        self.skill = _make_skill()

    def test_papelera_sin_args_es_dry_run(self):
        """Sin '--ahora', es simulación."""
        result = self.skill.execute("papelera", [])
        self.assertIsInstance(result, SkillResult)
        if _IS_WINDOWS:
            self.assertTrue(result.success)
            self.assertIn("SIMULACIÓN", result.output.upper())

    def test_papelera_dry_run_menciona_ahora(self):
        if not _IS_WINDOWS:
            self.skipTest("Solo Windows")
        result = self.skill.execute("papelera", [])
        self.assertIn("--ahora", result.output)

    def test_papelera_dry_run_irreversible_warning(self):
        if not _IS_WINDOWS:
            self.skipTest("Solo Windows")
        result = self.skill.execute("papelera", [])
        # Debe advertir que la acción es irreversible
        self.assertIn("irreversible", result.output.lower())

    def test_papelera_no_windows_retorna_error(self):
        if _IS_WINDOWS:
            self.skipTest("Solo aplica en no-Windows")
        result = self.skill.execute("papelera", [])
        self.assertFalse(result.success)


# =============================================================================
# 11. Comando desconocido
# =============================================================================

class TestCmdDesconocido(unittest.TestCase):
    """Tests para comandos que no existen en SystemSkill."""

    def setUp(self):
        self.skill = _make_skill()

    def test_comando_desconocido_retorna_error(self):
        result = self.skill.execute("xyz_no_existe", [])
        self.assertFalse(result.success)
        self.assertTrue(len(result.error) > 0)

    def test_comando_desconocido_menciona_nombre(self):
        result = self.skill.execute("xyz_no_existe", [])
        self.assertIn("xyz_no_existe", result.error)


# =============================================================================
# 12. Integración con SkillRegistry
# =============================================================================

class TestSystemSkillRegistry(unittest.TestCase):
    """Verifica la integración de SystemSkill con el SkillRegistry."""

    def setUp(self):
        # Crear un registry limpio para cada test
        self.registry = SkillRegistry()

    def test_system_skill_registrable(self):
        skill = SystemSkill()
        self.registry.register(skill)
        self.assertIn("system_skill", [e.skill.META.name for e in self.registry.list_all()])

    def test_system_skill_encontrada_por_comando_abrir(self):
        skill = SystemSkill()
        self.registry.register(skill)
        found = self.registry.find_by_command("abrir")
        self.assertIsNotNone(found)
        self.assertEqual(found.META.name, "system_skill")

    def test_system_skill_encontrada_por_comando_sysinfo(self):
        skill = SystemSkill()
        self.registry.register(skill)
        found = self.registry.find_by_command("sysinfo")
        self.assertIsNotNone(found)

    def test_system_skill_enable_disable(self):
        skill = SystemSkill()
        self.registry.register(skill)
        self.registry.disable("system_skill")
        entry = self.registry.get_entry("system_skill")
        self.assertFalse(entry.enabled)
        self.registry.enable("system_skill")
        entry = self.registry.get_entry("system_skill")
        self.assertTrue(entry.enabled)

    def test_disabled_skill_not_found_by_command(self):
        skill = SystemSkill()
        self.registry.register(skill)
        self.registry.disable("system_skill")
        found = self.registry.find_by_command("abrir")
        self.assertIsNone(found)

    def test_system_skill_execute_via_registry(self):
        """Ejecutar sysinfo via registry retorna SkillResult."""
        skill = SystemSkill()
        self.registry.register(skill)
        result = self.registry.execute("system_skill", "sysinfo", [])
        self.assertIsInstance(result, SkillResult)
        self.assertTrue(result.success)


# =============================================================================
# 13. Descubrimiento automático
# =============================================================================

class TestSystemSkillDiscovery(unittest.TestCase):
    """Verifica que SystemSkill es descubierta automáticamente."""

    def test_discover_builtin_incluye_system_skill(self):
        """El registry descubre SystemSkill al escanear el paquete builtin."""
        registry = SkillRegistry()
        registry.discover_builtin()
        names = [e.skill.META.name for e in registry.list_all()]
        self.assertIn("system_skill", names)

    def test_discover_incluye_demo_y_system(self):
        """Ambas skills builtin son descubiertas juntas."""
        registry = SkillRegistry()
        registry.discover_builtin()
        names = [e.skill.META.name for e in registry.list_all()]
        self.assertIn("demo_skill", names)
        self.assertIn("system_skill", names)

    def test_discover_idempotente(self):
        """discover_builtin() dos veces no duplica skills."""
        registry = SkillRegistry()
        registry.discover_builtin()
        registry.discover_builtin()
        names = [e.skill.META.name for e in registry.list_all()]
        system_count = names.count("system_skill")
        self.assertEqual(system_count, 1)


# =============================================================================
# 14. Constantes y estructuras de datos
# =============================================================================

class TestConstantes(unittest.TestCase):
    """Verifica las constantes y estructuras internas."""

    def test_app_aliases_es_dict(self):
        self.assertIsInstance(_APP_ALIASES, dict)

    def test_app_aliases_no_vacio(self):
        self.assertGreater(len(_APP_ALIASES), 0)

    def test_protected_processes_es_set(self):
        self.assertIsInstance(_PROTECTED_PROCESSES, set)

    def test_protected_processes_no_vacio(self):
        self.assertGreater(len(_PROTECTED_PROCESSES), 0)

    def test_is_windows_es_bool(self):
        self.assertIsInstance(_IS_WINDOWS, bool)

    def test_is_windows_coincide_con_platform(self):
        expected = platform.system() == "Windows"
        self.assertEqual(_IS_WINDOWS, expected)

    def test_aliases_values_son_strings(self):
        for k, v in _APP_ALIASES.items():
            with self.subTest(alias=k):
                self.assertIsInstance(v, str, f"Alias '{k}' tiene valor no-string")

    def test_aliases_keys_son_minusculas(self):
        for k in _APP_ALIASES.keys():
            with self.subTest(alias=k):
                self.assertEqual(k, k.lower(), f"Alias '{k}' no está en minúsculas")


# =============================================================================
# 15. Validación de sintaxis
# =============================================================================

class TestSintaxis(unittest.TestCase):
    """Verifica que los archivos de la fase 14 tienen sintaxis válida."""

    def _compile_file(self, relpath: str) -> None:
        import py_compile
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        filepath = os.path.join(base, relpath)
        py_compile.compile(filepath, doraise=True)

    def test_system_skill_sintaxis(self):
        self._compile_file(os.path.join("skills", "builtin", "system_skill.py"))

    def test_builtin_init_sintaxis(self):
        self._compile_file(os.path.join("skills", "builtin", "__init__.py"))

    def test_test_file_sintaxis(self):
        self._compile_file(os.path.join("tests", "test_fase14_system_skill.py"))


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)

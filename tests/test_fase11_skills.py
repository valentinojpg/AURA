"""
AURA — Tests automáticos de la Fase 11: Núcleo de Skills

Suite de tests sin dependencias externas ni UI.
Cubre: BaseSkill, SkillMeta, SkillResult, SkillRegistry y DemoSkill.

Ejecutar:
    .\\env\\Scripts\\python.exe -m pytest tests/test_fase11_skills.py -v
    # O directamente:
    .\\env\\Scripts\\python.exe tests/test_fase11_skills.py
"""

from __future__ import annotations

import sys
import os
import unittest

# Asegurar que el directorio raíz del proyecto esté en sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ── Imports del sistema de skills ──────────────────────────────────────────

from skills.skill_base import (
    BaseSkill,
    SkillMeta,
    SkillResult,
    CATEGORY_DEMO,
    CATEGORY_SYSTEM,
    CATEGORY_FILES,
    CATEGORY_SEARCH,
    CATEGORY_PROGRAMS,
    CATEGORY_WEB,
    CATEGORY_AUTOMATION,
)
from skills.skill_registry import SkillEntry, SkillRegistry, skill_registry
from skills.builtin.demo_skill import DemoSkill

# Importar API pública del paquete
import skills as skills_pkg


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES — Skills de prueba
# ─────────────────────────────────────────────────────────────────────────────

class _MinimalSkill(BaseSkill):
    """Skill mínima para tests — no hace nada útil."""
    META = SkillMeta(
        name="minimal",
        version="0.1.0",
        display_name="Minimal Test Skill",
        description="Skill de test mínima.",
        commands=["ping"],
    )

    def execute(self, command: str, args: list[str]) -> SkillResult:
        if command == "ping":
            return SkillResult(success=True, output="pong")
        return SkillResult(success=False, error="comando desconocido")


class _MultiCommandSkill(BaseSkill):
    """Skill con múltiples comandos para tests de búsqueda."""
    META = SkillMeta(
        name="multi",
        version="1.0.0",
        display_name="Multi Command Skill",
        description="Skill con múltiples comandos.",
        commands=["cmd_a", "cmd_b", "cmd_c"],
        enabled_by_default=False,
    )

    def execute(self, command: str, args: list[str]) -> SkillResult:
        return SkillResult(success=True, output=f"ejecutado: {command}")


class _FailingSetupSkill(BaseSkill):
    """Skill cuyo setup lanza excepción — para tests de registro fallido."""
    META = SkillMeta(
        name="failing_setup",
        version="1.0.0",
        display_name="Failing Setup Skill",
        description="Setup falla siempre.",
        commands=["noop"],
    )

    def setup(self) -> None:
        raise RuntimeError("Setup intencional fallido")

    def execute(self, command: str, args: list[str]) -> SkillResult:
        return SkillResult(success=True, output="ok")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: SkillMeta
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillMeta(unittest.TestCase):
    """Tests de la clase SkillMeta."""

    def setUp(self):
        self.meta = SkillMeta(
            name="test_skill",
            version="2.3.1",
            display_name="Test Skill",
            description="Una skill de test.",
            author="Tester",
            category=CATEGORY_FILES,
            commands=["cmd1", "cmd2"],
            builtin=False,
            enabled_by_default=False,
        )

    def test_meta_name(self):
        self.assertEqual(self.meta.name, "test_skill")

    def test_meta_version(self):
        self.assertEqual(self.meta.version, "2.3.1")

    def test_meta_display_name(self):
        self.assertEqual(self.meta.display_name, "Test Skill")

    def test_meta_description(self):
        self.assertEqual(self.meta.description, "Una skill de test.")

    def test_meta_author(self):
        self.assertEqual(self.meta.author, "Tester")

    def test_meta_category(self):
        self.assertEqual(self.meta.category, CATEGORY_FILES)

    def test_meta_commands(self):
        self.assertEqual(self.meta.commands, ["cmd1", "cmd2"])

    def test_meta_builtin_false(self):
        self.assertFalse(self.meta.builtin)

    def test_meta_enabled_by_default_false(self):
        self.assertFalse(self.meta.enabled_by_default)

    def test_meta_is_frozen(self):
        """SkillMeta es un dataclass frozen — no se puede modificar."""
        with self.assertRaises((AttributeError, TypeError)):
            self.meta.name = "otro"  # type: ignore[misc]

    def test_meta_default_author(self):
        meta = SkillMeta(name="x", version="1.0", display_name="X", description="X")
        self.assertEqual(meta.author, "AURA")

    def test_meta_default_category(self):
        meta = SkillMeta(name="x", version="1.0", display_name="X", description="X")
        self.assertEqual(meta.category, CATEGORY_DEMO)

    def test_meta_default_commands_empty(self):
        meta = SkillMeta(name="x", version="1.0", display_name="X", description="X")
        self.assertEqual(meta.commands, [])

    def test_meta_default_builtin_true(self):
        meta = SkillMeta(name="x", version="1.0", display_name="X", description="X")
        self.assertTrue(meta.builtin)

    def test_meta_default_enabled_by_default_true(self):
        meta = SkillMeta(name="x", version="1.0", display_name="X", description="X")
        self.assertTrue(meta.enabled_by_default)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: SkillResult
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillResult(unittest.TestCase):
    """Tests de la clase SkillResult."""

    def test_result_success_true(self):
        r = SkillResult(success=True, output="ok")
        self.assertTrue(r.success)
        self.assertTrue(bool(r))

    def test_result_success_false(self):
        r = SkillResult(success=False, error="algo falló")
        self.assertFalse(r.success)
        self.assertFalse(bool(r))

    def test_result_output(self):
        r = SkillResult(success=True, output="Hola!")
        self.assertEqual(r.output, "Hola!")

    def test_result_error(self):
        r = SkillResult(success=False, error="error message")
        self.assertEqual(r.error, "error message")

    def test_result_data(self):
        r = SkillResult(success=True, data={"key": "value", "num": 42})
        self.assertEqual(r.data["key"], "value")
        self.assertEqual(r.data["num"], 42)

    def test_result_default_output_empty(self):
        r = SkillResult(success=True)
        self.assertEqual(r.output, "")

    def test_result_default_error_empty(self):
        r = SkillResult(success=True)
        self.assertEqual(r.error, "")

    def test_result_default_data_empty(self):
        r = SkillResult(success=True)
        self.assertEqual(r.data, {})

    def test_result_bool_success(self):
        self.assertTrue(SkillResult(success=True))

    def test_result_bool_failure(self):
        self.assertFalse(SkillResult(success=False))


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: BaseSkill (usando _MinimalSkill)
# ─────────────────────────────────────────────────────────────────────────────

class TestBaseSkill(unittest.TestCase):
    """Tests de la clase abstracta BaseSkill via _MinimalSkill."""

    def setUp(self):
        self.skill = _MinimalSkill()

    def test_skill_name_property(self):
        self.assertEqual(self.skill.name, "minimal")

    def test_skill_display_name_property(self):
        self.assertEqual(self.skill.display_name, "Minimal Test Skill")

    def test_skill_description_property(self):
        self.assertIn("test", self.skill.description.lower())

    def test_skill_version_property(self):
        self.assertEqual(self.skill.version, "0.1.0")

    def test_skill_category_property(self):
        self.assertEqual(self.skill.category, CATEGORY_DEMO)

    def test_skill_commands_property(self):
        self.assertIn("ping", self.skill.commands)

    def test_skill_handles_known_command(self):
        self.assertTrue(self.skill.handles("ping"))

    def test_skill_handles_unknown_command(self):
        self.assertFalse(self.skill.handles("unknown"))

    def test_skill_not_setup_initially(self):
        self.assertFalse(self.skill.is_setup)

    def test_skill_setup(self):
        self.skill.setup()
        self.assertTrue(self.skill.is_setup)

    def test_skill_teardown(self):
        self.skill.setup()
        self.skill.teardown()
        self.assertFalse(self.skill.is_setup)

    def test_skill_execute_ping(self):
        result = self.skill.execute("ping", [])
        self.assertTrue(result.success)
        self.assertEqual(result.output, "pong")

    def test_skill_execute_unknown(self):
        result = self.skill.execute("unknown", [])
        self.assertFalse(result.success)

    def test_skill_repr(self):
        r = repr(self.skill)
        self.assertIn("_MinimalSkill", r)
        self.assertIn("minimal", r)

    def test_skill_meta_attribute_exists(self):
        self.assertIsInstance(self.skill.META, SkillMeta)

    def test_skill_abstract_cannot_instantiate_directly(self):
        """No se puede instanciar BaseSkill directamente."""
        with self.assertRaises(TypeError):
            BaseSkill()  # type: ignore[abstract]

    def test_skill_subclass_without_meta_raises(self):
        """Subclase concreta sin META lanza TypeError al definirse."""
        with self.assertRaises(TypeError):
            # Definir la clase sin META debe fallar
            class _BadSkill(BaseSkill):
                def execute(self, command, args):
                    return SkillResult(success=True)
            # No alcanza a llegar aquí


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: SkillRegistry — Registro básico
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillRegistryBasic(unittest.TestCase):
    """Tests del SkillRegistry — operaciones básicas."""

    def setUp(self):
        """Usar un registro fresco para cada test."""
        self.registry = SkillRegistry()
        self.skill = _MinimalSkill()

    def test_registry_empty_initially(self):
        self.assertEqual(len(self.registry), 0)

    def test_registry_register_returns_true(self):
        result = self.registry.register(self.skill)
        self.assertTrue(result)

    def test_registry_len_after_register(self):
        self.registry.register(self.skill)
        self.assertEqual(len(self.registry), 1)

    def test_registry_contains_after_register(self):
        self.registry.register(self.skill)
        self.assertIn("minimal", self.registry)

    def test_registry_get_returns_skill(self):
        self.registry.register(self.skill)
        got = self.registry.get("minimal")
        self.assertIs(got, self.skill)

    def test_registry_get_nonexistent_returns_none(self):
        self.assertIsNone(self.registry.get("no_existe"))

    def test_registry_register_calls_setup(self):
        self.registry.register(self.skill)
        self.assertTrue(self.skill.is_setup)

    def test_registry_register_duplicate_returns_false(self):
        self.registry.register(self.skill)
        skill2 = _MinimalSkill()
        result = self.registry.register(skill2)
        self.assertFalse(result)

    def test_registry_register_force_replaces(self):
        self.registry.register(self.skill)
        skill2 = _MinimalSkill()
        result = self.registry.register(skill2, force=True)
        self.assertTrue(result)
        self.assertIs(self.registry.get("minimal"), skill2)

    def test_registry_register_non_skill_returns_false(self):
        result = self.registry.register("no soy una skill")  # type: ignore[arg-type]
        self.assertFalse(result)

    def test_registry_register_failing_setup_returns_false(self):
        failing = _FailingSetupSkill()
        result = self.registry.register(failing)
        self.assertFalse(result)
        self.assertNotIn("failing_setup", self.registry)

    def test_registry_unregister_returns_true(self):
        self.registry.register(self.skill)
        result = self.registry.unregister("minimal")
        self.assertTrue(result)

    def test_registry_unregister_removes_entry(self):
        self.registry.register(self.skill)
        self.registry.unregister("minimal")
        self.assertNotIn("minimal", self.registry)

    def test_registry_unregister_nonexistent_returns_false(self):
        result = self.registry.unregister("no_existe")
        self.assertFalse(result)

    def test_registry_unregister_calls_teardown(self):
        self.registry.register(self.skill)
        self.registry.unregister("minimal")
        self.assertFalse(self.skill.is_setup)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5: SkillRegistry — Habilitación / deshabilitación
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillRegistryEnableDisable(unittest.TestCase):
    """Tests de habilitación y deshabilitación de skills."""

    def setUp(self):
        self.registry = SkillRegistry()
        self.skill = _MinimalSkill()
        self.registry.register(self.skill)

    def test_skill_enabled_by_default(self):
        self.assertTrue(self.registry.is_enabled("minimal"))

    def test_disable_skill(self):
        self.registry.disable("minimal")
        self.assertFalse(self.registry.is_enabled("minimal"))

    def test_enable_after_disable(self):
        self.registry.disable("minimal")
        self.registry.enable("minimal")
        self.assertTrue(self.registry.is_enabled("minimal"))

    def test_disable_nonexistent_returns_false(self):
        result = self.registry.disable("no_existe")
        self.assertFalse(result)

    def test_enable_nonexistent_returns_false(self):
        result = self.registry.enable("no_existe")
        self.assertFalse(result)

    def test_multi_skill_disabled_by_default(self):
        multi = _MultiCommandSkill()
        self.registry.register(multi)
        # _MultiCommandSkill tiene enabled_by_default=False
        self.assertFalse(self.registry.is_enabled("multi"))

    def test_list_enabled_count(self):
        multi = _MultiCommandSkill()
        self.registry.register(multi)
        enabled = self.registry.list_enabled()
        # minimal=enabled, multi=disabled
        self.assertEqual(len(enabled), 1)
        self.assertEqual(enabled[0].name, "minimal")

    def test_list_disabled_count(self):
        multi = _MultiCommandSkill()
        self.registry.register(multi)
        disabled = self.registry.list_disabled()
        self.assertEqual(len(disabled), 1)
        self.assertEqual(disabled[0].name, "multi")

    def test_list_all_count(self):
        multi = _MultiCommandSkill()
        self.registry.register(multi)
        all_entries = self.registry.list_all()
        self.assertEqual(len(all_entries), 2)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6: SkillRegistry — Búsqueda por comando
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillRegistryFindByCommand(unittest.TestCase):
    """Tests de búsqueda de skills por comando."""

    def setUp(self):
        self.registry = SkillRegistry()
        self.minimal = _MinimalSkill()
        self.multi = _MultiCommandSkill()
        self.registry.register(self.minimal)
        self.registry.register(self.multi)
        # Habilitar multi para los tests de búsqueda
        self.registry.enable("multi")

    def test_find_by_command_existing(self):
        found = self.registry.find_by_command("ping")
        self.assertIs(found, self.minimal)

    def test_find_by_command_multi(self):
        found = self.registry.find_by_command("cmd_a")
        self.assertIs(found, self.multi)

    def test_find_by_command_nonexistent(self):
        found = self.registry.find_by_command("no_existe")
        self.assertIsNone(found)

    def test_find_by_command_disabled_skill(self):
        self.registry.disable("multi")
        found = self.registry.find_by_command("cmd_a")
        self.assertIsNone(found)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7: SkillRegistry — Ejecución
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillRegistryExecute(unittest.TestCase):
    """Tests de ejecución de comandos via el registro."""

    def setUp(self):
        self.registry = SkillRegistry()
        self.skill = _MinimalSkill()
        self.registry.register(self.skill)

    def test_execute_success(self):
        result = self.registry.execute("minimal", "ping", [])
        self.assertTrue(result.success)
        self.assertEqual(result.output, "pong")

    def test_execute_nonexistent_skill(self):
        result = self.registry.execute("no_existe", "ping", [])
        self.assertFalse(result.success)
        self.assertIn("no_existe", result.error)

    def test_execute_disabled_skill(self):
        self.registry.disable("minimal")
        result = self.registry.execute("minimal", "ping", [])
        self.assertFalse(result.success)

    def test_execute_unknown_command(self):
        result = self.registry.execute("minimal", "no_cmd", [])
        self.assertFalse(result.success)

    def test_execute_with_args(self):
        multi = _MultiCommandSkill()
        self.registry.register(multi)
        self.registry.enable("multi")
        result = self.registry.execute("multi", "cmd_a", ["arg1", "arg2"])
        self.assertTrue(result.success)
        self.assertIn("cmd_a", result.output)

    def test_execute_exception_in_skill_returns_error(self):
        """Si execute() lanza excepción, el registry retorna SkillResult(success=False)."""
        class _ExplodingSkill(BaseSkill):
            META = SkillMeta(
                name="exploding",
                version="1.0",
                display_name="Exploding",
                description="Siempre explota.",
                commands=["boom"],
            )
            def execute(self, command, args):
                raise RuntimeError("BOOM intencional")

        self.registry.register(_ExplodingSkill())
        result = self.registry.execute("exploding", "boom", [])
        self.assertFalse(result.success)
        self.assertIn("BOOM intencional", result.error)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 8: SkillRegistry — Reset e iteración
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillRegistryReset(unittest.TestCase):
    """Tests del método reset() y de la iteración."""

    def setUp(self):
        self.registry = SkillRegistry()

    def test_iter_empty(self):
        self.assertEqual(list(self.registry), [])

    def test_iter_with_entries(self):
        self.registry.register(_MinimalSkill())
        entries = list(self.registry)
        self.assertEqual(len(entries), 1)
        self.assertIsInstance(entries[0], SkillEntry)

    def test_reset_clears_entries(self):
        self.registry.register(_MinimalSkill())
        self.registry.reset()
        self.assertEqual(len(self.registry), 0)

    def test_reset_allows_rediscovery(self):
        self.registry.discover_builtin()
        self.registry.reset()
        # Después del reset, _builtin_discovered es False → se puede llamar de nuevo
        count = self.registry.discover_builtin()
        self.assertGreater(count, 0)

    def test_get_entry_returns_skill_entry(self):
        skill = _MinimalSkill()
        self.registry.register(skill)
        entry = self.registry.get_entry("minimal")
        self.assertIsInstance(entry, SkillEntry)
        self.assertIs(entry.skill, skill)

    def test_get_entry_nonexistent_returns_none(self):
        self.assertIsNone(self.registry.get_entry("no_existe"))


# ─────────────────────────────────────────────────────────────────────────────
# TEST 9: Descubrimiento automático
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillRegistryDiscover(unittest.TestCase):
    """Tests del descubrimiento automático de skills builtin."""

    def setUp(self):
        self.registry = SkillRegistry()

    def test_discover_builtin_returns_positive(self):
        count = self.registry.discover_builtin()
        self.assertGreaterEqual(count, 1)

    def test_discover_builtin_registers_demo(self):
        self.registry.discover_builtin()
        self.assertIn("demo_skill", self.registry)

    def test_discover_builtin_idempotent(self):
        """Segunda llamada no duplica skills."""
        count1 = self.registry.discover_builtin()
        count2 = self.registry.discover_builtin()
        self.assertEqual(count2, 0)
        self.assertEqual(len(self.registry), count1)

    def test_discover_builtin_demo_enabled(self):
        self.registry.discover_builtin()
        self.assertTrue(self.registry.is_enabled("demo_skill"))


# ─────────────────────────────────────────────────────────────────────────────
# TEST 10: DemoSkill
# ─────────────────────────────────────────────────────────────────────────────

class TestDemoSkill(unittest.TestCase):
    """Tests de la DemoSkill."""

    def setUp(self):
        self.skill = DemoSkill()
        self.skill.setup()

    def tearDown(self):
        self.skill.teardown()

    def test_demo_skill_is_baseskill(self):
        self.assertIsInstance(self.skill, BaseSkill)

    def test_demo_skill_meta_name(self):
        self.assertEqual(self.skill.META.name, "demo_skill")

    def test_demo_skill_meta_version(self):
        self.assertEqual(self.skill.META.version, "1.0.0")

    def test_demo_skill_meta_category(self):
        self.assertEqual(self.skill.META.category, CATEGORY_DEMO)

    def test_demo_skill_meta_builtin(self):
        self.assertTrue(self.skill.META.builtin)

    def test_demo_skill_meta_enabled_by_default(self):
        self.assertTrue(self.skill.META.enabled_by_default)

    def test_demo_skill_commands_list(self):
        expected = {"demo", "hola", "eco", "info", "version", "lista", "ayuda"}
        self.assertEqual(set(self.skill.commands), expected)

    def test_demo_skill_handles_all_commands(self):
        for cmd in ["demo", "hola", "eco", "info", "version", "lista", "ayuda"]:
            with self.subTest(cmd=cmd):
                self.assertTrue(self.skill.handles(cmd))

    def test_demo_skill_does_not_handle_unknown(self):
        self.assertFalse(self.skill.handles("no_existe"))

    def test_cmd_demo(self):
        result = self.skill.execute("demo", [])
        self.assertTrue(result.success)
        self.assertIn("Skills", result.output)

    def test_cmd_hola_sin_args(self):
        result = self.skill.execute("hola", [])
        self.assertTrue(result.success)
        self.assertIn("Hola", result.output)

    def test_cmd_hola_con_nombre(self):
        result = self.skill.execute("hola", ["Mundo"])
        self.assertTrue(result.success)
        self.assertIn("Mundo", result.output)

    def test_cmd_hola_con_nombre_compuesto(self):
        result = self.skill.execute("hola", ["Juan", "Pérez"])
        self.assertTrue(result.success)
        self.assertIn("Juan Pérez", result.output)

    def test_cmd_eco_con_texto(self):
        result = self.skill.execute("eco", ["Hola", "Mundo"])
        self.assertTrue(result.success)
        self.assertEqual(result.output, "Hola Mundo")

    def test_cmd_eco_sin_args_falla(self):
        result = self.skill.execute("eco", [])
        self.assertFalse(result.success)
        self.assertIn("eco", result.error)

    def test_cmd_eco_data_field(self):
        result = self.skill.execute("eco", ["a", "b", "c"])
        self.assertTrue(result.success)
        self.assertIn("eco", result.data)
        self.assertEqual(result.data["words"], 3)

    def test_cmd_info(self):
        result = self.skill.execute("info", [])
        self.assertTrue(result.success)
        self.assertIn("Skills", result.output)

    def test_cmd_version(self):
        result = self.skill.execute("version", [])
        self.assertTrue(result.success)
        self.assertIn("1.0.0", result.output)
        self.assertIn("data", dir(result))
        self.assertEqual(result.data.get("version"), "1.0.0")

    def test_cmd_ayuda(self):
        result = self.skill.execute("ayuda", [])
        self.assertTrue(result.success)
        self.assertIn("hola", result.output)
        self.assertIn("eco", result.output)

    def test_cmd_lista(self):
        """lista puede funcionar aunque el registry esté vacío."""
        result = self.skill.execute("lista", [])
        self.assertTrue(result.success)

    def test_cmd_desconocido(self):
        result = self.skill.execute("no_existe", [])
        self.assertFalse(result.success)

    def test_skill_repr(self):
        r = repr(self.skill)
        self.assertIn("DemoSkill", r)
        self.assertIn("demo_skill", r)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 11: API pública del paquete skills
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillsPublicAPI(unittest.TestCase):
    """Tests de la API pública del paquete skills."""

    def test_import_base_skill(self):
        self.assertTrue(hasattr(skills_pkg, "BaseSkill"))

    def test_import_skill_meta(self):
        self.assertTrue(hasattr(skills_pkg, "SkillMeta"))

    def test_import_skill_result(self):
        self.assertTrue(hasattr(skills_pkg, "SkillResult"))

    def test_import_skill_entry(self):
        self.assertTrue(hasattr(skills_pkg, "SkillEntry"))

    def test_import_skill_registry_class(self):
        self.assertTrue(hasattr(skills_pkg, "SkillRegistry"))

    def test_import_skill_registry_instance(self):
        self.assertTrue(hasattr(skills_pkg, "skill_registry"))

    def test_import_demo_skill(self):
        self.assertTrue(hasattr(skills_pkg, "DemoSkill"))

    def test_import_category_demo(self):
        self.assertEqual(skills_pkg.CATEGORY_DEMO, "demo")

    def test_import_category_system(self):
        self.assertEqual(skills_pkg.CATEGORY_SYSTEM, "system")

    def test_import_category_files(self):
        self.assertEqual(skills_pkg.CATEGORY_FILES, "files")

    def test_import_category_search(self):
        self.assertEqual(skills_pkg.CATEGORY_SEARCH, "search")

    def test_import_category_programs(self):
        self.assertEqual(skills_pkg.CATEGORY_PROGRAMS, "programs")

    def test_import_category_web(self):
        self.assertEqual(skills_pkg.CATEGORY_WEB, "web")

    def test_import_category_automation(self):
        self.assertEqual(skills_pkg.CATEGORY_AUTOMATION, "automation")

    def test_skill_registry_is_singleton(self):
        """El singleton de skill_registry es la misma instancia en cualquier import."""
        from skills.skill_registry import skill_registry as sr2
        self.assertIs(skills_pkg.skill_registry, sr2)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 12: Sintaxis — verificación con py_compile
# ─────────────────────────────────────────────────────────────────────────────

class TestSyntax(unittest.TestCase):
    """Verifica que todos los archivos nuevos tengan sintaxis Python válida."""

    def _check(self, rel_path: str) -> None:
        import py_compile
        abs_path = os.path.join(_PROJECT_ROOT, rel_path)
        self.assertTrue(os.path.exists(abs_path), f"No existe: {abs_path}")
        try:
            py_compile.compile(abs_path, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"Error de sintaxis en {rel_path}: {e}")

    def test_syntax_skill_base(self):
        self._check("skills/skill_base.py")

    def test_syntax_skill_registry(self):
        self._check("skills/skill_registry.py")

    def test_syntax_skills_init(self):
        self._check("skills/__init__.py")

    def test_syntax_builtin_init(self):
        self._check("skills/builtin/__init__.py")

    def test_syntax_demo_skill(self):
        self._check("skills/builtin/demo_skill.py")


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Orden de ejecución
    test_classes = [
        TestSkillMeta,
        TestSkillResult,
        TestBaseSkill,
        TestSkillRegistryBasic,
        TestSkillRegistryEnableDisable,
        TestSkillRegistryFindByCommand,
        TestSkillRegistryExecute,
        TestSkillRegistryReset,
        TestSkillRegistryDiscover,
        TestDemoSkill,
        TestSkillsPublicAPI,
        TestSyntax,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    total = result.testsRun
    errors = len(result.errors)
    failures = len(result.failures)
    ok = total - errors - failures

    print(f"\n{'='*60}")
    print(f"FASE 11 — Núcleo de Skills")
    print(f"{'='*60}")
    print(f"Total:    {total}")
    print(f"OK:       {ok}")
    print(f"Errores:  {errors}")
    print(f"Fallos:   {failures}")
    print(f"{'='*60}")

    sys.exit(0 if result.wasSuccessful() else 1)

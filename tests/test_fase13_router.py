"""
AURA — Tests de la Fase 13: Router de Comandos de Texto

Verifica el comportamiento completo del CommandRouter:
  - Importacion y estructura de RouteResult
  - Enrutamiento a skills por primer token
  - Comandos internos del router (/ayuda, /skills, /comandos)
  - Textos sin match pasan a la IA (retornan None)
  - Integracion con SkillRegistry real (DemoSkill)
  - Metodos utilitarios (is_command, list_all_commands)
  - Casos borde: texto vacio, solo espacios, comando desconocido
  - Sintaxis valida de todos los archivos nuevos/modificados

Total esperado: >= 50 tests
"""

from __future__ import annotations

import sys
import os
import py_compile
import unittest
from unittest.mock import MagicMock, patch

# Asegurar que el directorio raiz esta en el path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ══════════════════════════════════════════════════════════════════
# Grupo 1: Importacion y estructura basica
# ══════════════════════════════════════════════════════════════════

class TestRouterImports(unittest.TestCase):

    def test_import_command_router_module(self):
        """core.command_router es importable."""
        import core.command_router  # noqa: F401

    def test_import_route_result(self):
        """RouteResult es importable desde core.command_router."""
        from core.command_router import RouteResult
        self.assertTrue(True)

    def test_import_command_router_class(self):
        """CommandRouter es importable."""
        from core.command_router import CommandRouter
        self.assertTrue(True)

    def test_import_command_router_singleton(self):
        """command_router singleton es importable."""
        from core.command_router import command_router
        self.assertTrue(True)

    def test_command_router_is_instance(self):
        """command_router es instancia de CommandRouter."""
        from core.command_router import CommandRouter, command_router
        self.assertIsInstance(command_router, CommandRouter)

    def test_core_init_exports_command_router(self):
        """core.__init__ exporta command_router y RouteResult."""
        from core import command_router, RouteResult
        self.assertTrue(True)

    def test_core_init_exports_router_class(self):
        """core.__init__ exporta CommandRouter."""
        from core import CommandRouter
        self.assertTrue(True)


# ══════════════════════════════════════════════════════════════════
# Grupo 2: Estructura de RouteResult
# ══════════════════════════════════════════════════════════════════

class TestRouteResult(unittest.TestCase):

    def test_route_result_fields_handled_success(self):
        """RouteResult tiene campos handled y success."""
        from core.command_router import RouteResult
        r = RouteResult(handled=True, success=True)
        self.assertTrue(r.handled)
        self.assertTrue(r.success)

    def test_route_result_field_output(self):
        """RouteResult tiene campo output con default vacio."""
        from core.command_router import RouteResult
        r = RouteResult(handled=True, success=True)
        self.assertEqual(r.output, "")

    def test_route_result_field_error(self):
        """RouteResult tiene campo error con default vacio."""
        from core.command_router import RouteResult
        r = RouteResult(handled=True, success=False, error="oops")
        self.assertEqual(r.error, "oops")

    def test_route_result_field_skill_name(self):
        """RouteResult tiene campo skill_name."""
        from core.command_router import RouteResult
        r = RouteResult(handled=True, success=True, skill_name="demo_skill")
        self.assertEqual(r.skill_name, "demo_skill")

    def test_route_result_field_command(self):
        """RouteResult tiene campo command."""
        from core.command_router import RouteResult
        r = RouteResult(handled=True, success=True, command="hola")
        self.assertEqual(r.command, "hola")

    def test_route_result_field_args(self):
        """RouteResult tiene campo args."""
        from core.command_router import RouteResult
        r = RouteResult(handled=True, success=True, args=["a", "b"])
        self.assertEqual(r.args, ["a", "b"])

    def test_route_result_bool_true_when_handled_and_success(self):
        """bool(RouteResult) es True cuando handled=True y success=True."""
        from core.command_router import RouteResult
        r = RouteResult(handled=True, success=True)
        self.assertTrue(bool(r))

    def test_route_result_bool_false_when_not_success(self):
        """bool(RouteResult) es False cuando success=False."""
        from core.command_router import RouteResult
        r = RouteResult(handled=True, success=False)
        self.assertFalse(bool(r))

    def test_route_result_bool_false_when_not_handled(self):
        """bool(RouteResult) es False cuando handled=False."""
        from core.command_router import RouteResult
        r = RouteResult(handled=False, success=True)
        self.assertFalse(bool(r))


# ══════════════════════════════════════════════════════════════════
# Grupo 3: Comandos internos del router
# ══════════════════════════════════════════════════════════════════

class TestRouterInternalCommands(unittest.TestCase):

    def setUp(self):
        from core.command_router import CommandRouter
        from skills.skill_registry import SkillRegistry
        # Usar registry fresco para cada test
        self.registry = SkillRegistry()
        self.router = CommandRouter()
        self.router._registry = self.registry

    def test_route_ayuda_returns_route_result(self):
        """/ayuda retorna RouteResult handled=True."""
        result = self.router.route("/ayuda")
        self.assertIsNotNone(result)
        self.assertTrue(result.handled)

    def test_route_ayuda_success(self):
        """/ayuda retorna success=True."""
        result = self.router.route("/ayuda")
        self.assertTrue(result.success)

    def test_route_ayuda_output_not_empty(self):
        """/ayuda retorna output no vacio."""
        result = self.router.route("/ayuda")
        self.assertGreater(len(result.output), 10)

    def test_route_ayuda_skill_name_is_router(self):
        """/ayuda usa skill_name='router'."""
        result = self.router.route("/ayuda")
        self.assertEqual(result.skill_name, "router")

    def test_route_help_alias(self):
        """/help es alias de /ayuda."""
        result = self.router.route("/help")
        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertTrue(result.success)

    def test_route_skills_command(self):
        """/skills retorna handled=True y success=True."""
        result = self.router.route("/skills")
        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertTrue(result.success)

    def test_route_comandos_alias(self):
        """/comandos es alias de /skills."""
        result = self.router.route("/comandos")
        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertTrue(result.success)

    def test_route_unknown_internal_command(self):
        """/xyz retorna handled=True y success=False (comando desconocido)."""
        result = self.router.route("/xyz_desconocido")
        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertFalse(result.success)
        self.assertIn("desconocido", result.error.lower())

    def test_route_empty_slash(self):
        """/ solo (sin cmd) retorna handled=True y success=False."""
        result = self.router.route("/")
        self.assertIsNotNone(result)
        self.assertTrue(result.handled)


# ══════════════════════════════════════════════════════════════════
# Grupo 4: Enrutamiento a skills
# ══════════════════════════════════════════════════════════════════

class TestRouterSkillRouting(unittest.TestCase):

    def setUp(self):
        from core.command_router import CommandRouter
        from skills.skill_registry import SkillRegistry
        from skills.builtin.demo_skill import DemoSkill
        self.registry = SkillRegistry()
        self.registry.register(DemoSkill())
        self.router = CommandRouter()
        self.router._registry = self.registry

    def test_route_hola_handled(self):
        """'hola' es manejado por el router."""
        result = self.router.route("hola")
        self.assertIsNotNone(result)
        self.assertTrue(result.handled)

    def test_route_hola_success(self):
        """'hola' ejecuta exitosamente."""
        result = self.router.route("hola")
        self.assertTrue(result.success)

    def test_route_hola_output_not_empty(self):
        """'hola' retorna output con texto."""
        result = self.router.route("hola")
        self.assertGreater(len(result.output), 0)

    def test_route_hola_skill_name(self):
        """'hola' asigna skill_name correcto."""
        result = self.router.route("hola")
        self.assertEqual(result.skill_name, "demo_skill")

    def test_route_hola_command_field(self):
        """'hola' asigna command correcto."""
        result = self.router.route("hola")
        self.assertEqual(result.command, "hola")

    def test_route_hola_with_args(self):
        """'hola AURA' pasa el argumento a la skill."""
        result = self.router.route("hola AURA")
        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        self.assertIn("AURA", result.output)

    def test_route_hola_args_field(self):
        """'hola Mundo' tiene args=['Mundo']."""
        result = self.router.route("hola Mundo")
        self.assertEqual(result.args, ["Mundo"])

    def test_route_eco_with_args(self):
        """'eco Hola Mundo' retorna el texto repetido."""
        result = self.router.route("eco Hola Mundo")
        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        self.assertIn("Hola Mundo", result.output)

    def test_route_eco_without_args_fails(self):
        """'eco' sin args retorna success=False."""
        result = self.router.route("eco")
        self.assertIsNotNone(result)
        self.assertFalse(result.success)

    def test_route_demo_handled(self):
        """'demo' es manejado correctamente."""
        result = self.router.route("demo")
        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertTrue(result.success)

    def test_route_ayuda_as_skill_command(self):
        """'ayuda' (sin /) es manejado por DemoSkill."""
        result = self.router.route("ayuda")
        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertTrue(result.success)

    def test_route_case_insensitive_command(self):
        """El comando es case-insensitive: 'HOLA' = 'hola'."""
        result = self.router.route("HOLA")
        self.assertIsNotNone(result)
        self.assertTrue(result.handled)

    def test_route_command_with_extra_spaces(self):
        """Espacios extra al inicio/fin son ignorados."""
        result = self.router.route("  hola  ")
        self.assertIsNotNone(result)
        self.assertTrue(result.handled)

    def test_route_disabled_skill_returns_none(self):
        """Skill deshabilitada no es encontrada por find_by_command → router retorna None (pasa a IA)."""
        self.registry.disable("demo_skill")
        # find_by_command solo busca en skills habilitadas, asi que retorna None
        result = self.router.route("hola")
        self.assertIsNone(result)
        self.registry.enable("demo_skill")  # restaurar



# ══════════════════════════════════════════════════════════════════
# Grupo 5: Textos que pasan a la IA (retornan None)
# ══════════════════════════════════════════════════════════════════

class TestRouterPassthroughToAI(unittest.TestCase):

    def setUp(self):
        from core.command_router import CommandRouter
        from skills.skill_registry import SkillRegistry
        from skills.builtin.demo_skill import DemoSkill
        self.registry = SkillRegistry()
        self.registry.register(DemoSkill())
        self.router = CommandRouter()
        self.router._registry = self.registry

    def test_normal_text_returns_none(self):
        """Texto sin comando retorna None (pasar a IA)."""
        result = self.router.route("que tiempo hace hoy")
        self.assertIsNone(result)

    def test_question_returns_none(self):
        """Pregunta normal retorna None."""
        result = self.router.route("explica que es Python")
        self.assertIsNone(result)

    def test_empty_string_returns_none(self):
        """Texto vacio retorna None."""
        result = self.router.route("")
        self.assertIsNone(result)

    def test_whitespace_only_returns_none(self):
        """Solo espacios retorna None."""
        result = self.router.route("   ")
        self.assertIsNone(result)

    def test_none_input_returns_none(self):
        """None como entrada retorna None."""
        result = self.router.route(None)
        self.assertIsNone(result)

    def test_unknown_first_token_returns_none(self):
        """Primer token no registrado retorna None."""
        result = self.router.route("abrir_calculadora")
        self.assertIsNone(result)


# ══════════════════════════════════════════════════════════════════
# Grupo 6: is_command
# ══════════════════════════════════════════════════════════════════

class TestIsCommand(unittest.TestCase):

    def setUp(self):
        from core.command_router import CommandRouter
        from skills.skill_registry import SkillRegistry
        from skills.builtin.demo_skill import DemoSkill
        self.registry = SkillRegistry()
        self.registry.register(DemoSkill())
        self.router = CommandRouter()
        self.router._registry = self.registry

    def test_is_command_true_for_skill_command(self):
        """is_command retorna True para comando de skill."""
        self.assertTrue(self.router.is_command("hola"))

    def test_is_command_true_for_internal(self):
        """is_command retorna True para /ayuda."""
        self.assertTrue(self.router.is_command("/ayuda"))

    def test_is_command_false_for_random_text(self):
        """is_command retorna False para texto libre."""
        self.assertFalse(self.router.is_command("como estas"))

    def test_is_command_false_for_empty(self):
        """is_command retorna False para string vacio."""
        self.assertFalse(self.router.is_command(""))


# ══════════════════════════════════════════════════════════════════
# Grupo 7: list_all_commands
# ══════════════════════════════════════════════════════════════════

class TestListAllCommands(unittest.TestCase):

    def setUp(self):
        from core.command_router import CommandRouter
        from skills.skill_registry import SkillRegistry
        from skills.builtin.demo_skill import DemoSkill
        self.registry = SkillRegistry()
        self.registry.register(DemoSkill())
        self.router = CommandRouter()
        self.router._registry = self.registry

    def test_list_all_commands_returns_list(self):
        """list_all_commands retorna una lista."""
        result = self.router.list_all_commands()
        self.assertIsInstance(result, list)

    def test_list_all_commands_not_empty_with_skills(self):
        """list_all_commands no esta vacia cuando hay skills."""
        result = self.router.list_all_commands()
        self.assertGreater(len(result), 0)

    def test_list_all_commands_has_required_keys(self):
        """Cada entrada tiene las keys requeridas."""
        result = self.router.list_all_commands()
        for entry in result:
            self.assertIn("skill_name", entry)
            self.assertIn("display_name", entry)
            self.assertIn("commands", entry)
            self.assertIn("enabled", entry)
            self.assertIn("category", entry)

    def test_list_all_commands_includes_demo_skill(self):
        """list_all_commands incluye demo_skill."""
        result = self.router.list_all_commands()
        names = [e["skill_name"] for e in result]
        self.assertIn("demo_skill", names)


# ══════════════════════════════════════════════════════════════════
# Grupo 8: Integracion con registry real
# ══════════════════════════════════════════════════════════════════

class TestRouterIntegration(unittest.TestCase):

    def setUp(self):
        """Registry real con discover_builtin."""
        from core.command_router import CommandRouter
        from skills.skill_registry import SkillRegistry
        self.registry = SkillRegistry()
        self.registry.discover_builtin()
        self.router = CommandRouter()
        self.router._registry = self.registry

    def test_info_command_via_router(self):
        """'info' es ejecutado correctamente por el router."""
        result = self.router.route("info")
        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertTrue(result.success)

    def test_version_command_via_router(self):
        """'version' es ejecutado correctamente."""
        result = self.router.route("version")
        self.assertIsNotNone(result)
        self.assertTrue(result.success)

    def test_lista_command_via_router(self):
        """'lista' es ejecutado correctamente."""
        result = self.router.route("lista")
        self.assertIsNotNone(result)
        self.assertTrue(result.success)

    def test_router_ayuda_shows_skills_count(self):
        """/ayuda incluye la cuenta de skills activas."""
        result = self.router.route("/ayuda")
        self.assertIn("Skills activas", result.output)

    def test_router_skills_shows_commands(self):
        """/skills incluye 'Comandos:' en la salida."""
        result = self.router.route("/skills")
        self.assertIn("Comandos", result.output)


# ══════════════════════════════════════════════════════════════════
# Grupo 9: Sintaxis de archivos nuevos/modificados
# ══════════════════════════════════════════════════════════════════

class TestSintaxis(unittest.TestCase):

    def _check(self, rel_path: str) -> None:
        full = os.path.join(ROOT, rel_path)
        try:
            py_compile.compile(full, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"Error de sintaxis en {rel_path}: {e}")

    def test_syntax_command_router(self):
        """core/command_router.py no tiene errores de sintaxis."""
        self._check("core/command_router.py")

    def test_syntax_core_init(self):
        """core/__init__.py no tiene errores de sintaxis."""
        self._check("core/__init__.py")

    def test_syntax_chat_page(self):
        """ui/pages/chat_page.py no tiene errores de sintaxis."""
        self._check("ui/pages/chat_page.py")


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""
Tests de regresión para open_app:
Verifica la unificación del pipeline de resolución, la eliminación del path
viejo de alias con sugerencias hardcodeadas, y la normalización de target (evitando listas ['...']).
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from aura.core.entity_resolver import entity_resolver, ResolvedEntity
from aura.core.intent_router import intent_router, Intent
from core.app_scanner import fast_resolve_app, deep_app_scanner, DeepScanResult
from skills.skill_registry import skill_registry


class TestUnifiedOpenApp(unittest.TestCase):
    def setUp(self):
        skill_registry.discover_builtin()

    def test_open_steam_resolves_cleanly(self):
        """'abre steam' debe resolver a la ruta real y no devolver error de alias."""
        intent = intent_router.parse("abre steam")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.nombre, "open_app")
        self.assertEqual(intent.target, "steam")
        self.assertIsInstance(intent.target, str)

        res = entity_resolver.resolve(intent)
        self.assertTrue(res.resolved)
        self.assertIsInstance(res.target, str)
        self.assertEqual(res.target, "steam")
        self.assertTrue(len(res.args) > 0)
        self.assertNotIn("['steam']", str(res.args))
        self.assertNotIn("['steam']", res.target)

    def test_target_list_unpacked_to_str(self):
        """Si el target llega como lista, debe desempaquetarse inmediatamente a string."""
        res = entity_resolver.resolve("open_app", ["steam"])
        self.assertTrue(res.resolved)
        self.assertIsInstance(res.target, str)
        self.assertEqual(res.target, "steam")

    def test_programs_skill_abrir_with_list_args(self):
        """ProgramsSkill._cmd_abrir debe manejar args como lista o string y no dar error de alias."""
        skill = skill_registry.get("programs_skill")
        self.assertIsNotNone(skill)

        r = skill.execute("programa", ["aplicacion_totalmente_ficticia_xyz"])
        self.assertFalse(r.success)
        self.assertNotIn("No se encontró el alias", r.error)
        self.assertIn("No encontré 'aplicacion_totalmente_ficticia_xyz' en el sistema", r.error)
        self.assertNotIn("['aplicacion_totalmente_ficticia_xyz']", r.error)

    def test_programs_skill_sugerencias_no_hardcoded_system_tools(self):
        """Las sugerencias difflib no deben incluir herramientas fijas como system informer."""
        skill = skill_registry.get("programs_skill")
        suggs = skill._sugerir_alias("steam")
        self.assertNotIn("system informer", suggs)
        self.assertNotIn("steps recorder", suggs)

    def test_fast_resolve_app_finds_steam(self):
        """fast_resolve_app encuentra Steam si está en Start Menu o favoritos."""
        ruta = fast_resolve_app("steam")
        if ruta:
            self.assertTrue(os.path.exists(ruta))
            self.assertIn("steam", ruta.lower())

    def test_fast_resolve_app_handles_list_input(self):
        """fast_resolve_app acepta lista o tupla sin error."""
        ruta = fast_resolve_app(["steam"])
        if ruta:
            self.assertTrue(os.path.exists(ruta))

    def test_nonexistent_app_flags_needs_deep_scan(self):
        """Una aplicación no existente indica needs_deep_scan en entity_resolver."""
        res = entity_resolver.resolve("open_app", "programa_que_no_existe_98765")
        self.assertFalse(res.resolved)
        self.assertEqual(res.target, "programa_que_no_existe_98765")
        self.assertTrue(res.extra.get("needs_deep_scan"))


if __name__ == "__main__":
    unittest.main()

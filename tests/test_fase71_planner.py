# -*- coding: utf-8 -*-
"""
================================================================================
AURA — Test Suite: Fase 71 (Multi-Step Planning / Planificador de Cadenas)
================================================================================
Verifica exhaustivamente:
  1. extract_slots y restore_slots con comillas simples, dobles y tipográficas.
  2. split_steps con todas las conjunciones fuera de slots.
  3. is_instruction_chain (detección precisa de cadenas vs comandos simples).
  4. plan_from_rules con los 2 ejemplos obligatorios:
     - "abre firefox y entra a youtube music y pon 'Bad Romance' de Lady Gaga"
     - "abre notepad y escribe 'Hola a todos, los amo' y guarda el notepad en el escritorio con el titulo 'Amanecer'"
  5. Anáfora y seguimiento de app implícita en pasos posteriores.
  6. Asignación de slots por rol (texto, nombre, query).
  7. Límite de seguridad PLAN_MAX_STEPS (8 pasos).
  8. plan_from_ai fallback con mock de proveedor.
  9. Detección de planes destructivos (delete_file, etc.).
  10. automation_engine.run_steps (dry_run, callbacks, on_error stop/continue).
  11. Cero regresión en comandos de un solo intent directo.
  12. media_play_skill y alias de sitios web en entity_resolver y web_skill.
================================================================================
"""

import unittest
from unittest.mock import MagicMock, patch

from aura.core.planner import (
    DEFAULT_MAX_STEPS,
    Plan,
    PlanStep,
    extract_slots,
    is_destructive_plan,
    is_instruction_chain,
    plan_from_ai,
    plan_from_rules,
    restore_slots,
    split_steps,
)
from aura.core.intent_router import IntentRouter, parse as router_parse
from aura.core.entity_resolver import entity_resolver, SITE_ALIASES_MAP
from automation.engine import AutomationEngine, automation_engine, StepResult
from skills.builtin.media_play_skill import MediaPlaySkill, build_media_url, normalize_service_name
from skills.builtin.web_skill import _BUILTIN_FAVORITES


class TestFase71SlotsAndSplitting(unittest.TestCase):
    """Pruebas de extracción de slots y división de pasos por conjunciones."""

    def test_extract_slots_various_quotes(self):
        # Comillas dobles, simples y tipográficas
        text = 'abre notepad y escribe "pan y queso" y luego \'otra cosa\' y después “cita bonita”'
        clean_text, slots = extract_slots(text)

        self.assertEqual(len(slots), 3)
        self.assertEqual(slots[0], "pan y queso")
        self.assertEqual(slots[1], "otra cosa")
        self.assertEqual(slots[2], "cita bonita")
        self.assertIn("§0", clean_text)
        self.assertIn("§1", clean_text)
        self.assertIn("§2", clean_text)

        # Restauración
        restored = restore_slots(clean_text, slots)
        self.assertIn("pan y queso", restored)
        self.assertIn("otra cosa", restored)
        self.assertIn("cita bonita", restored)

    def test_split_steps_conjunctions(self):
        # Verifica conjunciones: y, luego, después, entonces, y después, y por último, también
        chain = "abre firefox y entra a google luego busca python después crea carpeta test y por último cierra firefox"
        ph, slots = extract_slots(chain)
        steps = split_steps(ph)

        self.assertEqual(len(steps), 5)
        self.assertEqual(steps[0], "abre firefox")
        self.assertEqual(steps[1], "entra a google")
        self.assertEqual(steps[2], "busca python")
        self.assertEqual(steps[3], "crea carpeta test")
        self.assertEqual(steps[4], "cierra firefox")

    def test_split_never_cuts_inside_slots(self):
        # Una conjunción dentro de un slot entre comillas NO debe partir el paso
        chain = "escribe 'pan y queso y manteca' en notepad y guarda el archivo"
        ph, slots = extract_slots(chain)
        steps = split_steps(ph)

        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0], "escribe §0 en notepad")
        self.assertEqual(steps[1], "guarda el archivo")

        restored_step0 = restore_slots(steps[0], slots)
        self.assertEqual(restored_step0, "escribe pan y queso y manteca en notepad")


class TestFase71ChainDetection(unittest.TestCase):
    """Pruebas de detección precisa de cadenas vs comandos individuales."""

    def test_is_instruction_chain_positive(self):
        self.assertTrue(is_instruction_chain("abre firefox y entra a youtube music y pon 'Bad Romance' de Lady Gaga"))
        self.assertTrue(is_instruction_chain("abre notepad y escribe 'Hola a todos' y guarda el notepad en el escritorio"))
        self.assertTrue(is_instruction_chain("crea carpeta pruebas y abre notepad"))
        self.assertTrue(is_instruction_chain("abre notepad y escribe 'pan y queso'"))

    def test_is_instruction_chain_negative_single_command(self):
        # Comandos simples no deben interceptarse como cadenas
        self.assertFalse(is_instruction_chain("abre notepad"))
        self.assertFalse(is_instruction_chain("cierra chrome"))
        self.assertFalse(is_instruction_chain("crea una carpeta llamada fotos"))
        self.assertFalse(is_instruction_chain("abre notepad con titulo 'pan y queso'"))

    def test_is_instruction_chain_negative_conversational(self):
        # Conversación casual con conjunciones
        self.assertFalse(is_instruction_chain("como preparar pan y queso"))
        self.assertFalse(is_instruction_chain("que tiempo hace hoy y mañana"))


class TestFase71MandatoryExamples(unittest.TestCase):
    """Pruebas para los dos ejemplos obligatorios de la Fase 71."""

    def test_example_1_firefox_youtube_music_lady_gaga(self):
        text = "abre firefox y entra a youtube music y pon 'Bad Romance' de Lady Gaga"
        plan = plan_from_rules(text)

        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.pasos), 3)

        # Paso 1: abrir firefox
        p1 = plan.pasos[0]
        self.assertEqual(p1.intent, "open_app")
        self.assertEqual(p1.target.lower(), "firefox")

        # Paso 2: entrar a youtube music
        p2 = plan.pasos[1]
        self.assertEqual(p2.intent, "open_url")
        self.assertEqual(p2.target, "https://music.youtube.com")

        # Paso 3: reproducir Bad Romance de Lady Gaga
        p3 = plan.pasos[2]
        self.assertEqual(p3.intent, "media_play")
        self.assertIn("Bad Romance", p3.query)
        self.assertIn("Lady Gaga", p3.query)
        self.assertEqual(p3.service, "youtube_music")

    def test_example_2_notepad_write_save_desktop(self):
        text = "abre notepad y escribe 'Hola a todos, los amo' y guarda el notepad en el escritorio con el titulo 'Amanecer'"
        plan = plan_from_rules(text)

        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.pasos), 3)

        # Paso 1: abrir notepad
        p1 = plan.pasos[0]
        self.assertEqual(p1.intent, "open_app")
        self.assertEqual(p1.target.lower(), "notepad")

        # Paso 2: escribir texto en notepad (con anáfora)
        p2 = plan.pasos[1]
        self.assertEqual(p2.intent, "write_in_app")
        self.assertEqual(p2.target.lower(), "notepad")
        self.assertEqual(p2.texto, "Hola a todos, los amo")

        # Paso 3: guardar notepad en escritorio con título 'Amanecer'
        p3 = plan.pasos[2]
        self.assertEqual(p3.intent, "save_app_doc")
        self.assertEqual(p3.target.lower(), "notepad")
        self.assertEqual(p3.nombre, "Amanecer")
        self.assertEqual(p3.destino.lower(), "escritorio")


class TestFase71AnaphoraAndRoles(unittest.TestCase):
    """Pruebas de seguimiento de anáfora y asignación de roles a slots."""

    def test_anaphora_implicit_app(self):
        # Step 2 no menciona 'notepad', se infiere de Step 1
        text = "abre notepad y escribe 'Probando anáfora' y guarda como 'notas.txt'"
        plan = plan_from_rules(text)

        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.pasos), 3)
        self.assertEqual(plan.pasos[1].target, "notepad")
        self.assertEqual(plan.pasos[1].texto, "Probando anáfora")
        self.assertEqual(plan.pasos[2].target, "notepad")
        self.assertEqual(plan.pasos[2].nombre, "notas.txt")

    def test_plan_max_steps_guard(self):
        # Cadena con más de 8 pasos es truncada
        long_chain = (
            "abre notepad y escribe '1' y escribe '2' y escribe '3' "
            "y escribe '4' y escribe '5' y escribe '6' y escribe '7' y escribe '8' y escribe '9'"
        )
        plan = plan_from_rules(long_chain)
        self.assertIsNotNone(plan)
        self.assertLessEqual(len(plan.pasos), DEFAULT_MAX_STEPS)


class TestFase71AIFallbackAndDestructive(unittest.TestCase):
    """Pruebas de fallback a IA y detección de acciones destructivas."""

    def test_plan_from_ai_success(self):
        mock_provider = MagicMock()
        mock_provider.name = "mock"
        mock_provider.model = "mock-model"
        mock_provider.chat.return_value.content = (
            '{"pasos": ['
            '  {"intent": "open_app", "target": "calc"},'
            '  {"intent": "message", "texto": "calculando"}'
            '], "confianza": 0.95}'
        )

        plan = plan_from_ai("abrir la calculadora y decir calculando", provider=mock_provider)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.origen, "ai")
        self.assertEqual(len(plan.pasos), 2)
        self.assertEqual(plan.pasos[0].intent, "open_app")
        self.assertEqual(plan.pasos[0].target, "calc")

    def test_plan_from_ai_invalid_json(self):
        mock_provider = MagicMock()
        mock_provider.chat.return_value.content = "No puedo entender esto como pasos."
        plan = plan_from_ai("frase rara", provider=mock_provider)
        self.assertIsNone(plan)

    def test_is_destructive_plan_positive(self):
        plan_safe = Plan(pasos=[
            PlanStep(intent="open_app", target="notepad"),
            PlanStep(intent="write_in_app", target="notepad", texto="hola"),
        ], origen="rules")
        is_destr, _ = is_destructive_plan(plan_safe)
        self.assertFalse(is_destr)

        plan_destr = Plan(pasos=[
            PlanStep(intent="open_app", target="notepad"),
            PlanStep(intent="delete_file", target="documento.txt", nombre="documento.txt"),
        ], origen="rules")
        is_destr2, desc = is_destructive_plan(plan_destr)
        self.assertTrue(is_destr2)
        self.assertIn("documento.txt", desc)


class TestFase71AutomationEngineRunSteps(unittest.TestCase):
    """Pruebas de ejecución de pasos con AutomationEngine.run_steps."""

    def test_run_steps_dry_run_callbacks(self):
        engine = AutomationEngine()
        steps = [
            {"type": "open_app", "app": "notepad"},
            {"type": "write_in_app", "app": "notepad", "texto": "test dry run"},
            {"type": "save_app_doc", "app": "notepad", "nombre": "dry.txt", "destino": "escritorio"},
        ]

        updates = []
        def on_update(idx, status, result):
            updates.append((idx, status))

        res = engine.run_steps(steps, name="Test Dry Run", dry_run=True, on_step_update=on_update)

        self.assertTrue(res.success)
        self.assertEqual(res.total_steps, 3)
        self.assertEqual(res.completed_steps, 3)
        self.assertEqual(res.failed_steps, 0)
        self.assertEqual(res.status, "OK")

        # Verificar que se emitieron eventos running y success
        self.assertIn((0, "running"), updates)
        self.assertIn((0, "success"), updates)
        self.assertIn((1, "running"), updates)
        self.assertIn((1, "success"), updates)
        self.assertIn((2, "running"), updates)
        self.assertIn((2, "success"), updates)

    def test_run_steps_error_policy_stop(self):
        engine = AutomationEngine()
        steps = [
            {"type": "message", "text": "Paso 1"},
            {"type": "open_app", "app": ""},  # Error: app vacía
            {"type": "message", "text": "Paso 3"},
        ]

        res = engine.run_steps(steps, name="Test Stop", dry_run=True, on_error="stop")
        self.assertFalse(res.success)
        self.assertEqual(res.completed_steps, 1)
        self.assertEqual(res.failed_steps, 1)
        self.assertEqual(len(res.step_results), 2)  # Se detuvo en el paso 2

    def test_run_steps_error_policy_continue(self):
        engine = AutomationEngine()
        steps = [
            {"type": "message", "text": "Paso 1"},
            {"type": "open_app", "app": ""},  # Error: app vacía
            {"type": "message", "text": "Paso 3"},
        ]

        res = engine.run_steps(steps, name="Test Continue", dry_run=True, on_error="continue")
        self.assertFalse(res.success)
        self.assertEqual(res.completed_steps, 2)
        self.assertEqual(res.failed_steps, 1)
        self.assertEqual(len(res.step_results), 3)  # Continuó hasta el paso 3


class TestFase71MediaPlayAndWebAliases(unittest.TestCase):
    """Pruebas de la skill media_play y los alias de sitios web."""

    def test_media_play_urls(self):
        url_ytm, name_ytm, is_nat_ytm = build_media_url("Bad Romance Lady Gaga", service="youtube_music")
        self.assertIn("music.youtube.com", url_ytm)
        self.assertIn("Bad+Romance+Lady+Gaga", url_ytm)
        self.assertEqual(name_ytm, "YouTube Music")
        self.assertFalse(is_nat_ytm)

        url_yt, name_yt, _ = build_media_url("Queen Bohemian Rhapsody", service="youtube")
        self.assertIn("youtube.com/results", url_yt)
        self.assertEqual(name_yt, "YouTube")

        url_sp, name_sp, _ = build_media_url("Dua Lipa", service="spotify")
        self.assertTrue("spotify:" in url_sp or "open.spotify.com" in url_sp)

    def test_entity_resolver_media_play(self):
        resolved = entity_resolver.resolve("media_play", "Bad Romance de Lady Gaga")
        self.assertTrue(resolved.resolved)
        self.assertEqual(resolved.intent, "media_play")
        self.assertEqual(resolved.skill_name, "media_play")
        self.assertEqual(resolved.command, "reproducir")
        self.assertIn("Bad Romance de Lady Gaga", resolved.args)

    def test_entity_resolver_site_aliases(self):
        res_ytm = entity_resolver.resolve("open_url", "youtube music")
        self.assertTrue(res_ytm.resolved)
        self.assertEqual(res_ytm.executable, "https://music.youtube.com")

        res_wa = entity_resolver.resolve("open_url", "whatsapp web")
        self.assertTrue(res_wa.resolved)
        self.assertEqual(res_wa.executable, "https://web.whatsapp.com")

    def test_web_skill_builtin_favorites_expanded(self):
        self.assertIn("youtube music", _BUILTIN_FAVORITES)
        self.assertIn("whatsapp web", _BUILTIN_FAVORITES)
        self.assertIn("chatgpt", _BUILTIN_FAVORITES)
        self.assertIn("calendar", _BUILTIN_FAVORITES)
        self.assertIn("drive", _BUILTIN_FAVORITES)


if __name__ == "__main__":
    unittest.main()

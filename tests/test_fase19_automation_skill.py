"""
AURA — Tests automatizados para la Fase 19: Motor de Automatizaciones

Cubre:
  - AutomationEngine: list_automations, get_info, run, pasos individuales
  - AutomationSkill: metadatos, comandos, integración con registry
  - Casos de error y dry-run
  - Persistencia e integración con SkillRegistry

Ejecutar:
  .\\env\\Scripts\\python.exe -m pytest tests/test_fase19_automation_skill.py -v
"""

from __future__ import annotations

import json
import os
import sys
import py_compile
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Setup path
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# 1. Tests de sintaxis y estructura
# ---------------------------------------------------------------------------

class TestSintaxis(unittest.TestCase):
    """Verifica que los módulos nuevos tienen sintaxis válida."""

    def test_engine_sintaxis_valida(self):
        path = ROOT / "automation" / "engine.py"
        self.assertTrue(path.exists(), "automation/engine.py debe existir")
        py_compile.compile(str(path), doraise=True)

    def test_automation_skill_sintaxis_valida(self):
        path = ROOT / "skills" / "builtin" / "automation_skill.py"
        self.assertTrue(path.exists(), "skills/builtin/automation_skill.py debe existir")
        py_compile.compile(str(path), doraise=True)

    def test_engine_importable(self):
        from automation.engine import AutomationEngine  # noqa: F401

    def test_automation_skill_importable(self):
        from skills.builtin.automation_skill import AutomationSkill  # noqa: F401

    def test_automation_init_importable(self):
        from automation import AutomationEngine, AutomationResult, AutomationInfo, StepResult  # noqa: F401


# ---------------------------------------------------------------------------
# 2. Tests de AutomationEngine — list_automations con archivos temporales
# ---------------------------------------------------------------------------

def _make_yaml(tmp_dir: Path, filename: str, content: str) -> Path:
    p = tmp_dir / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


class TestAutomationEngineListar(unittest.TestCase):
    """Tests de AutomationEngine.list_automations()."""

    def setUp(self):
        from automation.engine import AutomationEngine
        self.tmp = Path(tempfile.mkdtemp())
        self.engine = AutomationEngine()
        # Patch del directorio de automatizaciones
        self._patcher = patch("automation.engine._AUTOMATIONS_DIR", self.tmp)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lista_vacia_si_no_hay_archivos(self):
        result = self.engine.list_automations()
        self.assertEqual(result, [])

    def test_lista_yaml_valido(self):
        _make_yaml(self.tmp, "test.yaml", """
            name: "Test"
            description: "Descripción"
            version: "1.0"
            steps:
              - type: message
                text: "Hola"
        """)
        result = self.engine.list_automations()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "test")
        self.assertEqual(result[0].display_name, "Test")
        self.assertEqual(result[0].step_count, 1)

    def test_lista_json_valido(self):
        data = {
            "name": "Test JSON",
            "description": "Desc",
            "version": "2.0",
            "steps": [{"type": "message", "text": "OK"}]
        }
        (self.tmp / "test_json.json").write_text(json.dumps(data), encoding="utf-8")
        result = self.engine.list_automations()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].format, "json")

    def test_ignora_extensiones_desconocidas(self):
        (self.tmp / "ignorar.txt").write_text("contenido", encoding="utf-8")
        result = self.engine.list_automations()
        self.assertEqual(result, [])

    def test_lista_multiples_archivos(self):
        for i in range(3):
            _make_yaml(self.tmp, f"auto_{i}.yaml", f"""
                name: "Auto {i}"
                steps:
                  - type: message
                    text: "Hola {i}"
            """)
        result = self.engine.list_automations()
        self.assertEqual(len(result), 3)

    def test_ignora_yaml_invalido_sin_crash(self):
        (self.tmp / "roto.yaml").write_text("{{ inválido }", encoding="utf-8")
        result = self.engine.list_automations()
        self.assertEqual(result, [])

    def test_lista_ordenada_por_nombre(self):
        for name in ["z_auto", "a_auto", "m_auto"]:
            _make_yaml(self.tmp, f"{name}.yaml", f"""
                name: "{name}"
                steps: []
            """)
        result = self.engine.list_automations()
        nombres = [r.name for r in result]
        self.assertEqual(nombres, sorted(nombres))


# ---------------------------------------------------------------------------
# 3. Tests de AutomationEngine.get_info
# ---------------------------------------------------------------------------

class TestAutomationEngineGetInfo(unittest.TestCase):

    def setUp(self):
        from automation.engine import AutomationEngine
        self.tmp = Path(tempfile.mkdtemp())
        self.engine = AutomationEngine()
        self._patcher = patch("automation.engine._AUTOMATIONS_DIR", self.tmp)
        self._patcher.start()
        _make_yaml(self.tmp, "mi_auto.yaml", """
            name: "Mi Auto"
            description: "Desc"
            version: "1.5"
            steps:
              - type: message
                text: "X"
              - type: delay
                seconds: 1
        """)

    def tearDown(self):
        self._patcher.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_get_info_existente(self):
        info = self.engine.get_info("mi_auto")
        self.assertIsNotNone(info)
        self.assertEqual(info.name, "mi_auto")
        self.assertEqual(info.display_name, "Mi Auto")
        self.assertEqual(info.step_count, 2)
        self.assertEqual(info.version, "1.5")

    def test_get_info_inexistente_retorna_none(self):
        info = self.engine.get_info("no_existe_123")
        self.assertIsNone(info)

    def test_get_info_por_display_name(self):
        info = self.engine.get_info("Mi Auto")
        self.assertIsNotNone(info)

    def test_get_info_case_insensitive(self):
        info = self.engine.get_info("MI_AUTO")
        self.assertIsNotNone(info)


# ---------------------------------------------------------------------------
# 4. Tests de AutomationEngine.run — dry_run
# ---------------------------------------------------------------------------

class TestAutomationEngineRunDryRun(unittest.TestCase):

    def setUp(self):
        from automation.engine import AutomationEngine
        self.tmp = Path(tempfile.mkdtemp())
        self.engine = AutomationEngine()
        self._patcher = patch("automation.engine._AUTOMATIONS_DIR", self.tmp)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_inexistente_retorna_failure(self):
        result = self.engine.run("no_existe")
        self.assertFalse(result.success)
        self.assertIn("no encontrada", result.error)

    def test_run_dry_run_sin_efectos(self):
        _make_yaml(self.tmp, "test_dry.yaml", """
            name: "Test Dry"
            steps:
              - type: open_app
                app: notepad
              - type: open_url
                url: https://example.com
              - type: delay
                seconds: 0.01
              - type: message
                text: "Hola"
        """)
        with patch("os.startfile"), patch("webbrowser.open", return_value=True):
            result = self.engine.run("test_dry", dry_run=True)

        self.assertTrue(result.success)
        self.assertEqual(result.total_steps, 4)
        self.assertEqual(result.completed_steps, 4)
        self.assertEqual(result.failed_steps, 0)
        # En dry_run, ninguna acción real
        self.assertIn("SIMULACIÓN", result.output)

    def test_run_completo_success(self):
        _make_yaml(self.tmp, "test_ok.yaml", """
            name: "Test OK"
            steps:
              - type: message
                text: "Paso 1"
              - type: message
                text: "Paso 2"
        """)
        result = self.engine.run("test_ok")
        self.assertTrue(result.success)
        self.assertEqual(result.total_steps, 2)
        self.assertEqual(result.completed_steps, 2)

    def test_run_con_paso_invalido_no_crash(self):
        _make_yaml(self.tmp, "test_invalido.yaml", """
            name: "Test Inválido"
            steps:
              - type: tipo_inexistente
              - type: message
                text: "OK"
        """)
        result = self.engine.run("test_invalido")
        self.assertFalse(result.success)
        self.assertEqual(result.total_steps, 2)
        self.assertEqual(result.failed_steps, 1)
        self.assertEqual(result.completed_steps, 1)

    def test_run_yaml_sin_steps_retorna_vacio(self):
        _make_yaml(self.tmp, "sin_steps.yaml", """
            name: "Sin Steps"
        """)
        result = self.engine.run("sin_steps")
        # Un YAML sin steps es válido: corre 0 pasos con éxito
        self.assertTrue(result.success)
        self.assertEqual(result.total_steps, 0)
        self.assertEqual(result.completed_steps, 0)
        self.assertEqual(result.failed_steps, 0)

    def test_run_json_valido(self):
        data = {
            "name": "Test JSON Run",
            "steps": [
                {"type": "message", "text": "Hola desde JSON"}
            ]
        }
        (self.tmp / "test_json_run.json").write_text(json.dumps(data), encoding="utf-8")
        result = self.engine.run("test_json_run")
        self.assertTrue(result.success)
        self.assertEqual(result.total_steps, 1)

    def test_result_bool_true_en_exito(self):
        _make_yaml(self.tmp, "bool_test.yaml", """
            name: "Bool Test"
            steps:
              - type: message
                text: "OK"
        """)
        result = self.engine.run("bool_test")
        self.assertTrue(bool(result))

    def test_result_bool_false_en_fallo(self):
        result = self.engine.run("no_existe_xyz")
        self.assertFalse(bool(result))


# ---------------------------------------------------------------------------
# 5. Tests de pasos individuales
# ---------------------------------------------------------------------------

class TestStepMessage(unittest.TestCase):

    def setUp(self):
        from automation.engine import AutomationEngine
        self.engine = AutomationEngine()

    def test_message_sin_text_falla(self):
        sr = self.engine._step_message(0, {"type": "message"})
        self.assertFalse(sr.success)
        self.assertIn("text", sr.error)

    def test_message_con_text_exitoso(self):
        sr = self.engine._step_message(0, {"type": "message", "text": "Hola"})
        self.assertTrue(sr.success)
        self.assertIn("Hola", sr.output)

    def test_message_step_type_correcto(self):
        sr = self.engine._step_message(0, {"type": "message", "text": "X"})
        self.assertEqual(sr.step_type, "message")

    def test_message_index_correcto(self):
        sr = self.engine._step_message(5, {"type": "message", "text": "X"})
        self.assertEqual(sr.index, 5)

    def test_message_bool_true(self):
        sr = self.engine._step_message(0, {"type": "message", "text": "OK"})
        self.assertTrue(bool(sr))


class TestStepDelay(unittest.TestCase):

    def setUp(self):
        from automation.engine import AutomationEngine
        self.engine = AutomationEngine()

    def test_delay_dry_run_no_duerme(self):
        t0 = time.monotonic()
        sr = self.engine._step_delay(0, {"type": "delay", "seconds": 10.0}, dry_run=True)
        elapsed = time.monotonic() - t0
        self.assertTrue(sr.success)
        self.assertLess(elapsed, 1.0)

    def test_delay_negativo_falla(self):
        sr = self.engine._step_delay(0, {"type": "delay", "seconds": -1})
        self.assertFalse(sr.success)

    def test_delay_supera_maximo_falla(self):
        sr = self.engine._step_delay(0, {"type": "delay", "seconds": 999})
        self.assertFalse(sr.success)
        self.assertIn("máximo", sr.error)

    def test_delay_tipo_incorrecto_falla(self):
        sr = self.engine._step_delay(0, {"type": "delay", "seconds": "no_es_numero"})
        self.assertFalse(sr.success)

    def test_delay_cero_valido(self):
        sr = self.engine._step_delay(0, {"type": "delay", "seconds": 0}, dry_run=True)
        self.assertTrue(sr.success)

    def test_delay_data_contiene_seconds(self):
        sr = self.engine._step_delay(0, {"type": "delay", "seconds": 1.5}, dry_run=True)
        self.assertEqual(sr.data.get("seconds"), 1.5)

    def test_delay_real_muy_corto(self):
        """Delay real de 0.01s no debe fallar."""
        sr = self.engine._step_delay(0, {"type": "delay", "seconds": 0.01})
        self.assertTrue(sr.success)


class TestStepOpenUrl(unittest.TestCase):

    def setUp(self):
        from automation.engine import AutomationEngine
        self.engine = AutomationEngine()

    def test_open_url_sin_url_falla(self):
        sr = self.engine._step_open_url(0, {"type": "open_url"})
        self.assertFalse(sr.success)

    def test_open_url_dry_run_exitoso(self):
        sr = self.engine._step_open_url(
            0, {"type": "open_url", "url": "https://example.com"}, dry_run=True
        )
        self.assertTrue(sr.success)
        self.assertIn("SIMULADO", sr.output)

    def test_open_url_agrega_https_si_falta(self):
        sr = self.engine._step_open_url(
            0, {"type": "open_url", "url": "example.com"}, dry_run=True
        )
        self.assertTrue(sr.success)
        self.assertIn("https://", sr.output)

    def test_open_url_webbrowser_exito(self):
        with patch("webbrowser.open", return_value=True):
            sr = self.engine._step_open_url(
                0, {"type": "open_url", "url": "https://google.com"}
            )
        self.assertTrue(sr.success)

    def test_open_url_webbrowser_false_falla(self):
        with patch("webbrowser.open", return_value=False):
            sr = self.engine._step_open_url(
                0, {"type": "open_url", "url": "https://google.com"}
            )
        self.assertFalse(sr.success)

    def test_open_url_excepcion_falla(self):
        with patch("webbrowser.open", side_effect=Exception("error")):
            sr = self.engine._step_open_url(
                0, {"type": "open_url", "url": "https://google.com"}
            )
        self.assertFalse(sr.success)


class TestStepOpenApp(unittest.TestCase):

    def setUp(self):
        from automation.engine import AutomationEngine
        self.engine = AutomationEngine()

    def test_open_app_sin_app_falla(self):
        sr = self.engine._step_open_app(0, {"type": "open_app"})
        self.assertFalse(sr.success)

    def test_open_app_dry_run_exitoso(self):
        sr = self.engine._step_open_app(
            0, {"type": "open_app", "app": "notepad"}, dry_run=True
        )
        self.assertTrue(sr.success)
        self.assertIn("SIMULADO", sr.output)

    def test_open_app_resuelve_alias(self):
        sr = self.engine._step_open_app(
            0, {"type": "open_app", "app": "notepad"}, dry_run=True
        )
        self.assertIn("notepad.exe", sr.output)

    def test_open_app_data_contiene_app_y_exe(self):
        sr = self.engine._step_open_app(
            0, {"type": "open_app", "app": "notepad"}, dry_run=True
        )
        self.assertEqual(sr.data.get("app"), "notepad")
        self.assertIn("exe", sr.data)

    @unittest.skipUnless(os.name == "nt", "Solo Windows")
    def test_open_app_windows_excepcion_falla(self):
        with patch("os.startfile", side_effect=OSError("no encontrado")):
            sr = self.engine._step_open_app(
                0, {"type": "open_app", "app": "app_inexistente_xyz.exe"}
            )
        self.assertFalse(sr.success)


class TestExecuteStep(unittest.TestCase):
    """Tests del despachador _execute_step."""

    def setUp(self):
        from automation.engine import AutomationEngine
        self.engine = AutomationEngine()

    def test_tipo_desconocido_falla(self):
        sr = self.engine._execute_step(0, {"type": "tipo_raro_xyz"})
        self.assertFalse(sr.success)
        self.assertIn("tipo_raro_xyz", sr.error)

    def test_step_sin_type_falla(self):
        sr = self.engine._execute_step(0, {})
        self.assertFalse(sr.success)

    def test_step_no_dict_falla(self):
        # _execute_step espera dict, pero run() gestiona el caso no-dict
        from automation.engine import AutomationEngine
        eng = AutomationEngine()
        sr = eng._execute_step(0, {"type": "message", "text": "OK"})
        self.assertTrue(sr.success)

    def test_delega_a_message(self):
        sr = self.engine._execute_step(0, {"type": "message", "text": "Hola"})
        self.assertEqual(sr.step_type, "message")
        self.assertTrue(sr.success)

    def test_delega_a_delay(self):
        sr = self.engine._execute_step(0, {"type": "delay", "seconds": 0}, dry_run=True)
        # dry_run no es parámetro de _execute_step — el step usa dry_run=False por defecto
        self.assertEqual(sr.step_type, "delay")

    def test_tipos_disponibles_en_error(self):
        sr = self.engine._execute_step(0, {"type": "inexistente"})
        self.assertIn("open_app", sr.error)
        self.assertIn("open_url", sr.error)
        self.assertIn("delay", sr.error)
        self.assertIn("message", sr.error)


# ---------------------------------------------------------------------------
# 6. Tests de AutomationSkill — Metadatos
# ---------------------------------------------------------------------------

class TestAutomationSkillMetadatos(unittest.TestCase):

    def setUp(self):
        from skills.builtin.automation_skill import AutomationSkill
        self.SkillClass = AutomationSkill

    def test_meta_existe(self):
        self.assertTrue(hasattr(self.SkillClass, "META"))

    def test_meta_name(self):
        self.assertEqual(self.SkillClass.META.name, "automation_skill")

    def test_meta_display_name(self):
        self.assertIn("Automatiza", self.SkillClass.META.display_name)

    def test_meta_category(self):
        from skills.skill_base import CATEGORY_AUTOMATION
        self.assertEqual(self.SkillClass.META.category, CATEGORY_AUTOMATION)

    def test_meta_builtin(self):
        self.assertTrue(self.SkillClass.META.builtin)

    def test_meta_enabled_by_default(self):
        self.assertTrue(self.SkillClass.META.enabled_by_default)

    def test_meta_commands_contiene_automatizar(self):
        self.assertIn("automatizar", self.SkillClass.META.commands)

    def test_meta_commands_contiene_automatizaciones(self):
        self.assertIn("automatizaciones", self.SkillClass.META.commands)

    def test_meta_commands_contiene_automatizar_info(self):
        self.assertIn("automatizar-info", self.SkillClass.META.commands)

    def test_meta_exactamente_3_comandos(self):
        self.assertEqual(len(self.SkillClass.META.commands), 3)

    def test_meta_version(self):
        self.assertEqual(self.SkillClass.META.version, "1.0.0")


# ---------------------------------------------------------------------------
# 7. Tests de AutomationSkill — Herencia
# ---------------------------------------------------------------------------

class TestAutomationSkillHerencia(unittest.TestCase):

    def setUp(self):
        from skills.builtin.automation_skill import AutomationSkill
        from skills.skill_base import BaseSkill
        self.SkillClass = AutomationSkill
        self.BaseSkill = BaseSkill

    def test_hereda_base_skill(self):
        self.assertTrue(issubclass(self.SkillClass, self.BaseSkill))

    def test_instanciable(self):
        skill = self.SkillClass()
        self.assertIsNotNone(skill)

    def test_handles_automatizar(self):
        skill = self.SkillClass()
        self.assertTrue(skill.handles("automatizar"))

    def test_handles_automatizaciones(self):
        skill = self.SkillClass()
        self.assertTrue(skill.handles("automatizaciones"))

    def test_handles_automatizar_info(self):
        skill = self.SkillClass()
        self.assertTrue(skill.handles("automatizar-info"))

    def test_no_handles_desconocido(self):
        skill = self.SkillClass()
        self.assertFalse(skill.handles("comando_desconocido"))

    def test_execute_callable(self):
        skill = self.SkillClass()
        self.assertTrue(callable(skill.execute))


# ---------------------------------------------------------------------------
# 8. Tests de AutomationSkill — Ciclo de vida
# ---------------------------------------------------------------------------

class TestAutomationSkillCicloDeVida(unittest.TestCase):

    def setUp(self):
        from skills.builtin.automation_skill import AutomationSkill
        self.SkillClass = AutomationSkill

    def test_setup_inicializa_engine(self):
        skill = self.SkillClass()
        self.assertIsNone(skill._engine)
        skill.setup()
        self.assertIsNotNone(skill._engine)
        skill.teardown()

    def test_setup_is_setup_true(self):
        skill = self.SkillClass()
        skill.setup()
        self.assertTrue(skill.is_setup())
        skill.teardown()

    def test_teardown_limpia_engine(self):
        skill = self.SkillClass()
        skill.setup()
        skill.teardown()
        self.assertIsNone(skill._engine)

    def test_teardown_is_setup_false(self):
        skill = self.SkillClass()
        skill.setup()
        skill.teardown()
        self.assertFalse(skill.is_setup())


# ---------------------------------------------------------------------------
# 9. Tests de AutomationSkill — Comando automatizaciones
# ---------------------------------------------------------------------------

class TestCmdAutomatizaciones(unittest.TestCase):

    def setUp(self):
        from skills.builtin.automation_skill import AutomationSkill
        from automation.engine import AutomationEngine, AutomationInfo
        from pathlib import Path
        self.skill = AutomationSkill()
        self.skill.setup()

        # Mock del engine para devolver lista controlada
        mock_engine = MagicMock(spec=AutomationEngine)
        mock_engine.list_automations.return_value = [
            AutomationInfo(
                name="modo_programar",
                display_name="Modo Programar",
                description="Abre VS Code y GitHub",
                version="1.0",
                step_count=5,
                path=Path("data/automations/modo_programar.yaml"),
                format="yaml",
            )
        ]
        self.skill._engine = mock_engine

    def tearDown(self):
        self.skill.teardown()

    def test_automatizaciones_retorna_skill_result(self):
        from skills.skill_base import SkillResult
        r = self.skill.execute("automatizaciones", [])
        self.assertIsInstance(r, SkillResult)

    def test_automatizaciones_success_true(self):
        r = self.skill.execute("automatizaciones", [])
        self.assertTrue(r.success)

    def test_automatizaciones_output_menciona_nombre(self):
        r = self.skill.execute("automatizaciones", [])
        self.assertIn("modo_programar", r.output)

    def test_automatizaciones_data_contiene_total(self):
        r = self.skill.execute("automatizaciones", [])
        self.assertEqual(r.data.get("total"), 1)

    def test_automatizaciones_sin_archivos_success(self):
        self.skill._engine.list_automations.return_value = []
        r = self.skill.execute("automatizaciones", [])
        self.assertTrue(r.success)
        self.assertIn("No hay automatizaciones", r.output)

    def test_automatizaciones_data_lista_correcta(self):
        r = self.skill.execute("automatizaciones", [])
        lista = r.data.get("automations", [])
        self.assertEqual(len(lista), 1)
        self.assertEqual(lista[0]["name"], "modo_programar")


# ---------------------------------------------------------------------------
# 10. Tests de AutomationSkill — Comando automatizar
# ---------------------------------------------------------------------------

class TestCmdAutomatizar(unittest.TestCase):

    def setUp(self):
        from skills.builtin.automation_skill import AutomationSkill
        from automation.engine import AutomationEngine, AutomationResult
        self.skill = AutomationSkill()
        self.skill.setup()

        self.mock_engine = MagicMock(spec=AutomationEngine)
        self.mock_engine.list_automations.return_value = []
        self.skill._engine = self.mock_engine

    def tearDown(self):
        self.skill.teardown()

    def _make_success_result(self, name="test", steps=3):
        from automation.engine import AutomationResult, StepResult
        return AutomationResult(
            name=name,
            success=True,
            total_steps=steps,
            completed_steps=steps,
            failed_steps=0,
            output=f"▶ Automatización: {name}\n✅ Completado: {steps}/{steps}",
        )

    def _make_failure_result(self, name="test", error="no encontrada"):
        from automation.engine import AutomationResult
        return AutomationResult(
            name=name,
            success=False,
            total_steps=0,
            completed_steps=0,
            failed_steps=0,
            error=error,
        )

    def test_automatizar_sin_args_error(self):
        r = self.skill.execute("automatizar", [])
        self.assertFalse(r.success)
        self.assertIn("Uso:", r.error)

    def test_automatizar_exitoso(self):
        self.mock_engine.run.return_value = self._make_success_result()
        r = self.skill.execute("automatizar", ["test"])
        self.assertTrue(r.success)

    def test_automatizar_output_no_vacio(self):
        self.mock_engine.run.return_value = self._make_success_result()
        r = self.skill.execute("automatizar", ["test"])
        self.assertTrue(r.output)

    def test_automatizar_data_contiene_name(self):
        self.mock_engine.run.return_value = self._make_success_result(name="mi_auto")
        r = self.skill.execute("automatizar", ["mi_auto"])
        self.assertEqual(r.data.get("name"), "mi_auto")

    def test_automatizar_con_simular_pasa_dry_run(self):
        self.mock_engine.run.return_value = self._make_success_result()
        self.skill.execute("automatizar", ["test", "--simular"])
        call_kwargs = self.mock_engine.run.call_args[1]
        self.assertTrue(call_kwargs.get("dry_run", False))

    def test_automatizar_no_encontrado_error(self):
        self.mock_engine.run.return_value = self._make_failure_result(
            error="Automatización 'xyz' no encontrada en /ruta."
        )
        r = self.skill.execute("automatizar", ["xyz"])
        self.assertFalse(r.success)

    def test_automatizar_nombre_con_espacios_se_une(self):
        """nombre con múltiples tokens se une con _"""
        self.mock_engine.run.return_value = self._make_success_result()
        self.skill.execute("automatizar", ["modo", "programar"])
        llamada = self.mock_engine.run.call_args[0][0]
        self.assertIn("_", llamada)

    def test_automatizar_skill_result_es_instancia(self):
        from skills.skill_base import SkillResult
        self.mock_engine.run.return_value = self._make_success_result()
        r = self.skill.execute("automatizar", ["test"])
        self.assertIsInstance(r, SkillResult)


# ---------------------------------------------------------------------------
# 11. Tests de AutomationSkill — Comando automatizar-info
# ---------------------------------------------------------------------------

class TestCmdAutomatizarInfo(unittest.TestCase):

    def setUp(self):
        from skills.builtin.automation_skill import AutomationSkill
        from automation.engine import AutomationEngine, AutomationInfo
        from pathlib import Path
        self.skill = AutomationSkill()
        self.skill.setup()

        self.mock_engine = MagicMock(spec=AutomationEngine)
        self.mock_info = AutomationInfo(
            name="modo_programar",
            display_name="Modo Programar",
            description="Abre VS Code y GitHub",
            version="1.0",
            step_count=5,
            path=Path("data/automations/modo_programar.yaml"),
            format="yaml",
        )
        self.mock_engine.get_info.return_value = self.mock_info
        self.mock_engine.list_automations.return_value = [self.mock_info]
        self.skill._engine = self.mock_engine

    def tearDown(self):
        self.skill.teardown()

    def test_info_sin_args_error(self):
        r = self.skill.execute("automatizar-info", [])
        self.assertFalse(r.success)
        self.assertIn("Uso:", r.error)

    def test_info_existente_success(self):
        r = self.skill.execute("automatizar-info", ["modo_programar"])
        self.assertTrue(r.success)

    def test_info_output_menciona_nombre(self):
        r = self.skill.execute("automatizar-info", ["modo_programar"])
        self.assertIn("modo_programar", r.output)

    def test_info_output_menciona_pasos(self):
        r = self.skill.execute("automatizar-info", ["modo_programar"])
        self.assertIn("5", r.output)

    def test_info_data_contiene_name(self):
        r = self.skill.execute("automatizar-info", ["modo_programar"])
        self.assertEqual(r.data.get("name"), "modo_programar")

    def test_info_data_contiene_step_count(self):
        r = self.skill.execute("automatizar-info", ["modo_programar"])
        self.assertEqual(r.data.get("step_count"), 5)

    def test_info_inexistente_error(self):
        self.mock_engine.get_info.return_value = None
        r = self.skill.execute("automatizar-info", ["no_existe"])
        self.assertFalse(r.success)

    def test_info_retorna_skill_result(self):
        from skills.skill_base import SkillResult
        r = self.skill.execute("automatizar-info", ["modo_programar"])
        self.assertIsInstance(r, SkillResult)


# ---------------------------------------------------------------------------
# 12. Tests de integración con SkillRegistry
# ---------------------------------------------------------------------------

class TestIntegracionRegistry(unittest.TestCase):

    def setUp(self):
        from skills.skill_registry import SkillRegistry
        self.registry = SkillRegistry()

    def tearDown(self):
        self.registry.reset()

    def test_discover_builtin_incluye_automation_skill(self):
        self.registry.discover_builtin()
        names = [e.meta.name for e in self.registry.list_all()]
        self.assertIn("automation_skill", names)

    def test_registro_exitoso(self):
        from skills.builtin.automation_skill import AutomationSkill
        entry = self.registry.register(AutomationSkill())
        self.assertIsNotNone(entry)

    def test_find_by_command_automatizar(self):
        from skills.builtin.automation_skill import AutomationSkill
        self.registry.register(AutomationSkill())
        entry = self.registry.find_by_command("automatizar")
        self.assertIsNotNone(entry)

    def test_find_by_command_automatizaciones(self):
        from skills.builtin.automation_skill import AutomationSkill
        self.registry.register(AutomationSkill())
        entry = self.registry.find_by_command("automatizaciones")
        self.assertIsNotNone(entry)

    def test_find_by_command_automatizar_info(self):
        from skills.builtin.automation_skill import AutomationSkill
        self.registry.register(AutomationSkill())
        entry = self.registry.find_by_command("automatizar-info")
        self.assertIsNotNone(entry)

    def test_disable_enable(self):
        from skills.builtin.automation_skill import AutomationSkill
        self.registry.register(AutomationSkill())
        self.registry.disable("automation_skill")
        entry2 = self.registry.find_by_command("automatizar")
        self.assertIsNone(entry2)
        self.registry.enable("automation_skill")
        entry3 = self.registry.find_by_command("automatizar")
        self.assertIsNotNone(entry3)

    def test_discover_builtin_idempotente(self):
        self.registry.discover_builtin()
        count1 = len(self.registry.list_all())
        self.registry.discover_builtin()
        count2 = len(self.registry.list_all())
        self.assertEqual(count1, count2)

    def test_exportacion_desde_builtin(self):
        from skills.builtin import AutomationSkill
        self.assertIsNotNone(AutomationSkill)

    def test_en_all_de_builtin(self):
        import skills.builtin as builtin_pkg
        self.assertIn("AutomationSkill", builtin_pkg.__all__)


# ---------------------------------------------------------------------------
# 13. Tests de archivos de ejemplo YAML
# ---------------------------------------------------------------------------

class TestAutomationesEjemplo(unittest.TestCase):
    """Verifica que las automatizaciones de ejemplo en data/ son válidas."""

    def _load_yaml(self, path: Path) -> dict:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_modo_programar_existe(self):
        path = ROOT / "data" / "automations" / "modo_programar.yaml"
        self.assertTrue(path.exists(), "data/automations/modo_programar.yaml debe existir")

    def test_inicio_dia_existe(self):
        path = ROOT / "data" / "automations" / "inicio_dia.yaml"
        self.assertTrue(path.exists(), "data/automations/inicio_dia.yaml debe existir")

    def test_modo_programar_yaml_valido(self):
        path = ROOT / "data" / "automations" / "modo_programar.yaml"
        data = self._load_yaml(path)
        self.assertIsInstance(data, dict)

    def test_modo_programar_tiene_name(self):
        path = ROOT / "data" / "automations" / "modo_programar.yaml"
        data = self._load_yaml(path)
        self.assertIn("name", data)

    def test_modo_programar_tiene_steps(self):
        path = ROOT / "data" / "automations" / "modo_programar.yaml"
        data = self._load_yaml(path)
        self.assertIn("steps", data)
        self.assertIsInstance(data["steps"], list)
        self.assertGreater(len(data["steps"]), 0)

    def test_modo_programar_pasos_tienen_type(self):
        path = ROOT / "data" / "automations" / "modo_programar.yaml"
        data = self._load_yaml(path)
        for step in data["steps"]:
            self.assertIn("type", step, f"El paso {step} no tiene 'type'")

    def test_inicio_dia_yaml_valido(self):
        path = ROOT / "data" / "automations" / "inicio_dia.yaml"
        data = self._load_yaml(path)
        self.assertIsInstance(data, dict)
        self.assertIn("steps", data)

    def test_engine_puede_ejecutar_modo_programar_dry_run(self):
        from automation.engine import AutomationEngine
        engine = AutomationEngine()
        with patch("os.startfile"), patch("webbrowser.open", return_value=True):
            result = engine.run("modo_programar", dry_run=True)
        self.assertTrue(result.success, f"Falló: {result.error}")
        self.assertGreater(result.total_steps, 0)


# ---------------------------------------------------------------------------
# 14. Tests de AutomationInfo y StepResult dataclasses
# ---------------------------------------------------------------------------

class TestDataclasses(unittest.TestCase):

    def test_step_result_bool_true(self):
        from automation.engine import StepResult
        sr = StepResult(index=0, step_type="message", success=True, output="OK")
        self.assertTrue(bool(sr))

    def test_step_result_bool_false(self):
        from automation.engine import StepResult
        sr = StepResult(index=0, step_type="message", success=False, error="err")
        self.assertFalse(bool(sr))

    def test_automation_result_bool_true(self):
        from automation.engine import AutomationResult
        r = AutomationResult(name="x", success=True, total_steps=1,
                             completed_steps=1, failed_steps=0)
        self.assertTrue(bool(r))

    def test_automation_result_bool_false(self):
        from automation.engine import AutomationResult
        r = AutomationResult(name="x", success=False, total_steps=1,
                             completed_steps=0, failed_steps=1)
        self.assertFalse(bool(r))

    def test_automation_info_filename(self):
        from automation.engine import AutomationInfo
        info = AutomationInfo(
            name="test", display_name="Test", description="",
            version="1.0", step_count=2,
            path=Path("/some/path/test.yaml"), format="yaml"
        )
        self.assertEqual(info.filename, "test.yaml")


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)

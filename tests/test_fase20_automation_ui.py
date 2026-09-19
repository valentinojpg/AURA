"""
Tests automáticos — AURA Fase 20: UI de Automatizaciones

Verifica:
  - Importabilidad de AutomationPage
  - Estructura del layout (paneles, widgets clave)
  - Lógica de selección y refresco
  - Integración con AutomationEngine
  - Ejecución y simulación (dry-run)
  - Manejo de errores
  - Callbacks de ejecución
  - Helpers de UI (log, botones)

Los tests de UI usan mocks para evitar dependencias de Tkinter en CI.
"""

from __future__ import annotations

import pytest
pytest.skip("Legacy CustomTkinter UI test (migrated to Flet in Phase 30)", allow_module_level=True)

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

# ── Fixtures de path ──────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ══════════════════════════════════════════════════════════════════════════
# Mocks de Tkinter y CustomTkinter (para entornos sin display)
# ══════════════════════════════════════════════════════════════════════════

def _make_ctk_mock():
    """Crea mocks para customtkinter sin necesitar display."""
    ctk = MagicMock()

    class FakeFrame:
        def __init__(self, *a, **kw):
            self._children = []
        def configure(self, **kw): pass
        def pack(self, **kw): pass
        def pack_forget(self): pass
        def grid(self, **kw): pass
        def grid_propagate(self, v): pass
        def grid_rowconfigure(self, *a, **kw): pass
        def grid_columnconfigure(self, *a, **kw): pass
        def winfo_children(self): return []
        def destroy(self): pass
        def after(self, ms, fn=None, *args):
            if fn: fn(*args)
        def bind(self, *a, **kw): pass

    class FakeLabel(FakeFrame):
        def __init__(self, *a, **kw): super().__init__()
        def configure(self, **kw): pass

    class FakeButton(FakeFrame):
        def __init__(self, *a, **kw): super().__init__()
        def configure(self, **kw): pass

    class FakeTextbox(FakeFrame):
        def __init__(self, *a, **kw):
            super().__init__()
            self._content = ""
        def configure(self, **kw): pass
        def delete(self, *a): self._content = ""
        def insert(self, pos, text): self._content += text
        def see(self, pos): pass
        def get(self, *a): return self._content

    class FakeScrollableFrame(FakeFrame):
        pass

    class FakeFont:
        def __init__(self, *a, **kw): pass

    ctk.CTkFrame = FakeFrame
    ctk.CTkLabel = FakeLabel
    ctk.CTkButton = FakeButton
    ctk.CTkTextbox = FakeTextbox
    ctk.CTkScrollableFrame = FakeScrollableFrame
    ctk.CTkFont = FakeFont
    return ctk


# Instalar mocks antes de importar módulos de UI
_ctk_mock = _make_ctk_mock()
sys.modules["customtkinter"] = _ctk_mock

# Mock de tkinter base
_tk_mock = MagicMock()
sys.modules["tkinter"] = _tk_mock

# Asegurar que ui.pages.base_page importa el mock
import importlib


# ══════════════════════════════════════════════════════════════════════════
# Helpers: AutomationInfo y AutomationResult ficticios
# ══════════════════════════════════════════════════════════════════════════

def _make_info(
    name="modo_programar",
    display_name="Modo Programar",
    description="Abre el entorno de desarrollo",
    version="1.0",
    step_count=4,
    fmt="yaml",
) -> object:
    """Crea un AutomationInfo simulado."""
    from automation.engine import AutomationInfo
    return AutomationInfo(
        name=name,
        display_name=display_name,
        description=description,
        version=version,
        step_count=step_count,
        path=Path(f"data/automations/{name}.yaml"),
        format=fmt,
    )


def _make_result(
    name="modo_programar",
    success=True,
    total=4,
    completed=4,
    failed=0,
    output="✅ Completado: 4/4 pasos exitosos.",
) -> object:
    """Crea un AutomationResult simulado."""
    from automation.engine import AutomationResult
    return AutomationResult(
        name=name,
        success=success,
        total_steps=total,
        completed_steps=completed,
        failed_steps=failed,
        output=output,
    )


# ══════════════════════════════════════════════════════════════════════════
# Test Suite
# ══════════════════════════════════════════════════════════════════════════

class TestAutomationPageImport(unittest.TestCase):
    """AutomationPage es importable y tiene los atributos correctos."""

    def test_import(self):
        """AutomationPage importa sin errores."""
        from ui.pages.automation_page import AutomationPage
        self.assertIsNotNone(AutomationPage)

    def test_page_name(self):
        """PAGE_NAME es 'Automatizaciones'."""
        from ui.pages.automation_page import AutomationPage
        self.assertEqual(AutomationPage.PAGE_NAME, "Automatizaciones")

    def test_inherits_base_page(self):
        """AutomationPage hereda de BasePage."""
        from ui.pages.automation_page import AutomationPage
        from ui.pages.base_page import BasePage
        self.assertTrue(issubclass(AutomationPage, BasePage))


class TestAutomationCardImport(unittest.TestCase):
    """_AutomationCard es importable."""

    def test_import_card(self):
        from ui.pages.automation_page import _AutomationCard
        self.assertIsNotNone(_AutomationCard)


class TestGetEngine(unittest.TestCase):
    """_get_engine retorna la instancia singleton."""

    def test_get_engine_returns_instance(self):
        from ui.pages.automation_page import _get_engine
        engine = _get_engine()
        from automation import AutomationEngine
        self.assertIsInstance(engine, AutomationEngine)

    def test_get_engine_same_instance(self):
        """Dos llamadas retornan la misma instancia (singleton)."""
        from ui.pages.automation_page import _get_engine
        e1 = _get_engine()
        e2 = _get_engine()
        self.assertIs(e1, e2)


class TestAutomationEngine(unittest.TestCase):
    """Tests directos sobre el motor (sin UI)."""

    def test_list_automations_returns_list(self):
        from automation import automation_engine
        result = automation_engine.list_automations()
        self.assertIsInstance(result, list)

    def test_list_automations_finds_demo_files(self):
        """El motor encuentra los YAML de demo si existen."""
        from automation import automation_engine
        infos = automation_engine.list_automations()
        names = [i.name for i in infos]
        # Al menos uno de los demo debería estar si data/automations/ existe
        # No fallamos si no hay archivos (entorno sin datos)
        self.assertIsInstance(names, list)

    def test_get_info_unknown_returns_none(self):
        from automation import automation_engine
        result = automation_engine.get_info("automatizacion_inexistente_xyz_123")
        self.assertIsNone(result)

    def test_run_unknown_returns_failure(self):
        from automation import automation_engine
        result = automation_engine.run("automatizacion_inexistente_xyz_123")
        self.assertFalse(result.success)
        self.assertIn("no encontrada", result.error.lower())

    def test_run_dry_run_flag(self):
        """El motor acepta dry_run=True sin crashear."""
        from automation import automation_engine
        # Ejecutar una que no existe — solo verifica que no crashea
        result = automation_engine.run("xyz_no_existe", dry_run=True)
        self.assertFalse(result.success)

    def test_automation_result_bool_true(self):
        result = _make_result(success=True)
        self.assertTrue(bool(result))

    def test_automation_result_bool_false(self):
        result = _make_result(success=False, total=4, completed=2, failed=2)
        self.assertFalse(bool(result))

    def test_automation_result_fields(self):
        result = _make_result()
        self.assertEqual(result.name, "modo_programar")
        self.assertEqual(result.total_steps, 4)
        self.assertEqual(result.completed_steps, 4)
        self.assertEqual(result.failed_steps, 0)
        self.assertIsInstance(result.output, str)

    def test_automation_info_filename(self):
        info = _make_info()
        self.assertEqual(info.filename, "modo_programar.yaml")

    def test_automation_info_fields(self):
        info = _make_info()
        self.assertEqual(info.name, "modo_programar")
        self.assertEqual(info.display_name, "Modo Programar")
        self.assertEqual(info.step_count, 4)
        self.assertEqual(info.format, "yaml")

    def test_step_result_bool_true(self):
        from automation.engine import StepResult
        sr = StepResult(index=0, step_type="message", success=True, output="ok")
        self.assertTrue(bool(sr))

    def test_step_result_bool_false(self):
        from automation.engine import StepResult
        sr = StepResult(index=0, step_type="message", success=False, error="err")
        self.assertFalse(bool(sr))

    def test_engine_run_message_step(self):
        """Un paso 'message' en dry_run completa correctamente."""
        from automation.engine import AutomationEngine
        import tempfile, os, json
        engine = AutomationEngine()
        # Crear automatización temporal JSON
        data = {
            "name": "Test Message",
            "description": "test",
            "version": "1.0",
            "steps": [{"type": "message", "text": "Hola test"}],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_msg.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            # Parchear _AUTOMATIONS_DIR
            import automation.engine as eng_mod
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                result = engine.run("test_msg", dry_run=False)
                self.assertTrue(result.success)
                self.assertEqual(result.total_steps, 1)
                self.assertEqual(result.completed_steps, 1)
                self.assertIn("Hola test", result.output)
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_run_delay_dry_run(self):
        """Un paso 'delay' en dry_run no espera realmente."""
        from automation.engine import AutomationEngine
        import tempfile, json, time
        engine = AutomationEngine()
        data = {
            "name": "Test Delay",
            "description": "delay test",
            "version": "1.0",
            "steps": [{"type": "delay", "seconds": 5.0}],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_delay.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            import automation.engine as eng_mod
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                start = time.time()
                result = engine.run("test_delay", dry_run=True)
                elapsed = time.time() - start
                self.assertTrue(result.success)
                self.assertLess(elapsed, 2.0)  # No esperó 5 segundos
                self.assertIn("SIMULADO", result.output)
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_invalid_step_type(self):
        """Un paso con tipo desconocido falla gracefully."""
        from automation.engine import AutomationEngine
        import tempfile, json
        engine = AutomationEngine()
        data = {
            "name": "Bad Step",
            "steps": [{"type": "tipo_inexistente"}],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            import automation.engine as eng_mod
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                result = engine.run("bad")
                self.assertFalse(result.success)
                self.assertEqual(result.failed_steps, 1)
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_missing_steps_key(self):
        """Un archivo sin 'steps' retorna fallo descriptivo."""
        from automation.engine import AutomationEngine
        import tempfile, json
        engine = AutomationEngine()
        data = {"name": "Sin Pasos"}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nosteps.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            import automation.engine as eng_mod
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                # steps vacío → 0 pasos → success (completado vacío = ok)
                result = engine.run("nosteps")
                self.assertTrue(result.success)
                self.assertEqual(result.total_steps, 0)
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_list_automations_with_temp_files(self):
        """list_automations() detecta YAML y JSON correctamente."""
        from automation.engine import AutomationEngine
        import tempfile, json
        engine = AutomationEngine()
        data = {"name": "Temp Auto", "description": "test", "version": "1.0", "steps": []}
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "auto1.yaml").write_text(
                "name: Auto1\ndescription: d1\nversion: '1.0'\nsteps: []",
                encoding="utf-8"
            )
            (Path(tmpdir) / "auto2.json").write_text(
                json.dumps({"name": "Auto2", "description": "d2", "version": "1.0", "steps": []}),
                encoding="utf-8"
            )
            (Path(tmpdir) / "ignorar.txt").write_text("ignorar", encoding="utf-8")
            import automation.engine as eng_mod
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                infos = engine.list_automations()
                names = [i.name for i in infos]
                self.assertIn("auto1", names)
                self.assertIn("auto2", names)
                self.assertNotIn("ignorar", names)
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_get_info_by_name(self):
        """get_info() encuentra una automatización por nombre."""
        from automation.engine import AutomationEngine
        import tempfile, json
        engine = AutomationEngine()
        data = {"name": "Mi Auto", "description": "desc", "version": "2.0", "steps": []}
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "mi_auto.json").write_text(json.dumps(data), encoding="utf-8")
            import automation.engine as eng_mod
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                info = engine.get_info("mi_auto")
                self.assertIsNotNone(info)
                self.assertEqual(info.display_name, "Mi Auto")
                self.assertEqual(info.version, "2.0")
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_open_url_dry_run(self):
        """Un paso 'open_url' en dry_run no abre el navegador."""
        from automation.engine import AutomationEngine
        import tempfile, json
        engine = AutomationEngine()
        data = {
            "name": "URL Test",
            "steps": [{"type": "open_url", "url": "https://example.com"}],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "url_test.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            import automation.engine as eng_mod
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                result = engine.run("url_test", dry_run=True)
                self.assertTrue(result.success)
                self.assertIn("SIMULADO", result.output)
                self.assertIn("https://example.com", result.output)
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_open_url_adds_https(self):
        """Una URL sin esquema recibe https:// automáticamente."""
        from automation.engine import AutomationEngine
        import tempfile, json
        engine = AutomationEngine()
        data = {
            "name": "URL Normalizar",
            "steps": [{"type": "open_url", "url": "example.com"}],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "url_norm.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            import automation.engine as eng_mod
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                result = engine.run("url_norm", dry_run=True)
                self.assertIn("https://example.com", result.output)
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_delay_negative_fails(self):
        """Un delay negativo retorna error."""
        from automation.engine import AutomationEngine
        import tempfile, json
        engine = AutomationEngine()
        data = {
            "name": "Delay Neg",
            "steps": [{"type": "delay", "seconds": -1}],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "neg.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            import automation.engine as eng_mod
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                result = engine.run("neg")
                self.assertFalse(result.success)
                self.assertEqual(result.failed_steps, 1)
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_delay_exceeds_max_fails(self):
        """Un delay mayor al máximo retorna error."""
        from automation.engine import AutomationEngine
        import automation.engine as eng_mod
        import tempfile, json
        engine = AutomationEngine()
        data = {
            "name": "Delay Max",
            "steps": [{"type": "delay", "seconds": eng_mod._MAX_DELAY_SECONDS + 1}],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "max.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                result = engine.run("max")
                self.assertFalse(result.success)
                self.assertIn("máximo", result.step_results[0].error)
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_message_empty_fails(self):
        """Un paso 'message' sin 'text' retorna error."""
        from automation.engine import AutomationEngine
        import tempfile, json
        engine = AutomationEngine()
        data = {"name": "Empty Msg", "steps": [{"type": "message", "text": ""}]}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "em.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            import automation.engine as eng_mod
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                result = engine.run("em")
                self.assertFalse(result.success)
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_open_app_missing_app_fails(self):
        """Un paso 'open_app' sin campo 'app' retorna error."""
        from automation.engine import AutomationEngine
        import tempfile, json
        engine = AutomationEngine()
        data = {"name": "No App", "steps": [{"type": "open_app"}]}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "noapp.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            import automation.engine as eng_mod
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                result = engine.run("noapp")
                self.assertFalse(result.success)
                self.assertIn("requiere", result.step_results[0].error.lower())
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_open_url_missing_url_fails(self):
        """Un paso 'open_url' sin campo 'url' retorna error."""
        from automation.engine import AutomationEngine
        import tempfile, json
        engine = AutomationEngine()
        data = {"name": "No URL", "steps": [{"type": "open_url"}]}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nourl.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            import automation.engine as eng_mod
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                result = engine.run("nourl")
                self.assertFalse(result.success)
                self.assertIn("requiere", result.step_results[0].error.lower())
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_non_dict_step_fails(self):
        """Un paso que no es dict falla gracefully."""
        from automation.engine import AutomationEngine
        import tempfile, json
        engine = AutomationEngine()
        data = {"name": "Bad List", "steps": ["string_step"]}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "badlist.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            import automation.engine as eng_mod
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                result = engine.run("badlist")
                self.assertFalse(result.success)
                self.assertEqual(result.failed_steps, 1)
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_invalid_json_file(self):
        """Un archivo JSON inválido retorna error."""
        from automation.engine import AutomationEngine
        import tempfile
        engine = AutomationEngine()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.json"
            path.write_text("{invalid json", encoding="utf-8")
            import automation.engine as eng_mod
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                result = engine.run("bad")
                self.assertFalse(result.success)
                self.assertIn("Error al leer", result.error)
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_invalid_yaml_file(self):
        """Un archivo YAML con sintaxis inválida retorna error."""
        from automation.engine import AutomationEngine
        import tempfile
        engine = AutomationEngine()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.yaml"
            path.write_text(": : invalid: yaml: {\n", encoding="utf-8")
            import automation.engine as eng_mod
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                result = engine.run("bad")
                # Puede fallar al parsear YAML
                self.assertFalse(result.success)
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_multiple_steps_partial_fail(self):
        """Varios pasos: algunos OK, algunos fallan → parcial."""
        from automation.engine import AutomationEngine
        import tempfile, json
        engine = AutomationEngine()
        data = {
            "name": "Mixed",
            "steps": [
                {"type": "message", "text": "ok"},
                {"type": "tipo_invalido"},
                {"type": "message", "text": "ok2"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mixed.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            import automation.engine as eng_mod
            orig = eng_mod._AUTOMATIONS_DIR
            eng_mod._AUTOMATIONS_DIR = Path(tmpdir)
            try:
                result = engine.run("mixed")
                self.assertFalse(result.success)
                self.assertEqual(result.total_steps, 3)
                self.assertEqual(result.completed_steps, 2)
                self.assertEqual(result.failed_steps, 1)
            finally:
                eng_mod._AUTOMATIONS_DIR = orig

    def test_engine_build_output_success(self):
        """_build_output contiene los textos esperados para éxito."""
        from automation.engine import AutomationEngine, StepResult
        engine = AutomationEngine()
        steps = [
            StepResult(0, "message", True, output="💬 Hola"),
            StepResult(1, "delay", True, output="⏱️ Esperado 1s"),
        ]
        output = engine._build_output("Mi Auto", steps, dry_run=False)
        self.assertIn("Mi Auto", output)
        self.assertIn("✅", output)
        self.assertIn("2/2", output)

    def test_engine_build_output_dry_run(self):
        """_build_output en dry_run incluye 'SIMULACIÓN'."""
        from automation.engine import AutomationEngine, StepResult
        engine = AutomationEngine()
        steps = [StepResult(0, "message", True, output="ok")]
        output = engine._build_output("Test", steps, dry_run=True)
        self.assertIn("SIMULACIÓN", output)
        self.assertIn("simulación", output.lower())

    def test_engine_build_output_partial(self):
        """_build_output parcial incluye '⚠️ Parcial'."""
        from automation.engine import AutomationEngine, StepResult
        engine = AutomationEngine()
        steps = [
            StepResult(0, "message", True, output="ok"),
            StepResult(1, "delay", False, error="fallo"),
        ]
        output = engine._build_output("Test", steps, dry_run=False)
        self.assertIn("⚠️ Parcial", output)


class TestAutomationPageCallbacks(unittest.TestCase):
    """Tests sobre la lógica de callbacks de AutomationPage (sin UI real)."""

    def _make_page(self):
        """Crea una instancia mínima de AutomationPage con mocks."""
        from ui.pages.automation_page import AutomationPage

        page = object.__new__(AutomationPage)
        # Inyectar atributos mínimos necesarios
        page._selected_info = None
        page._running = False
        page._cards = []

        # Mocks de widgets
        page._lbl_loading = MagicMock()
        page._lbl_status = MagicMock()
        page._log_box = MagicMock()
        page._btn_run = MagicMock()
        page._btn_simulate = MagicMock()
        page._detail_frame = MagicMock()
        page._placeholder = MagicMock()
        page._detail_name = MagicMock()
        page._detail_desc = MagicMock()
        page._detail_meta = MagicMock()
        page._list_scroll = MagicMock()
        page._steps_frame = MagicMock()
        page._steps_frame.winfo_children = MagicMock(return_value=[])
        page._right_scroll = MagicMock()

        # after() ejecuta inmediatamente
        page.after = lambda ms, fn=None, *args: fn(*args) if fn else None

        page._logger = MagicMock()
        return page

    def test_set_log_clears_content(self):
        """_set_log('') limpia el textbox."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        AutomationPage._set_log(page, "")
        page._log_box.delete.assert_called()

    def test_set_log_with_content(self):
        """_set_log('texto') inserta el texto."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        AutomationPage._set_log(page, "Hola mundo")
        page._log_box.insert.assert_called()

    def test_append_log_calls_insert(self):
        """_append_log('texto') inserta y hace scroll."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        AutomationPage._append_log(page, "paso 1 ok")
        page._log_box.insert.assert_called()
        page._log_box.see.assert_called()

    def test_set_buttons_enabled_true(self):
        """_set_buttons_enabled(True) llama configure(state='normal')."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        AutomationPage._set_buttons_enabled(page, True)
        page._btn_run.configure.assert_called_with(state="normal")
        page._btn_simulate.configure.assert_called_with(state="normal")

    def test_set_buttons_enabled_false(self):
        """_set_buttons_enabled(False) llama configure(state='disabled')."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        AutomationPage._set_buttons_enabled(page, False)
        page._btn_run.configure.assert_called_with(state="disabled")
        page._btn_simulate.configure.assert_called_with(state="disabled")

    def test_on_run_ignores_if_no_selection(self):
        """_on_run() no hace nada si no hay selección."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        page._selected_info = None
        AutomationPage._on_run(page)
        # No debería haber cambiado _running
        self.assertFalse(page._running)

    def test_on_run_ignores_if_already_running(self):
        """_on_run() no hace nada si ya está ejecutando."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        page._running = True
        page._selected_info = _make_info()
        AutomationPage._on_run(page)
        # _running sigue True y no cambió
        self.assertTrue(page._running)

    def test_on_simulate_ignores_if_no_selection(self):
        """_on_simulate() no hace nada si no hay selección."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        page._selected_info = None
        AutomationPage._on_simulate(page)
        self.assertFalse(page._running)

    def test_on_simulate_ignores_if_already_running(self):
        """_on_simulate() no hace nada si ya está ejecutando."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        page._running = True
        page._selected_info = _make_info()
        AutomationPage._on_simulate(page)
        self.assertTrue(page._running)

    def test_on_execution_done_success(self):
        """_on_execution_done() con éxito muestra estado verde."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        result = _make_result(success=True, completed=4, total=4)
        AutomationPage._on_execution_done(page, result, dry_run=False)
        self.assertFalse(page._running)
        page._lbl_status.configure.assert_called()
        args = page._lbl_status.configure.call_args
        self.assertIn("text_color", args.kwargs)

    def test_on_execution_done_failure(self):
        """_on_execution_done() con fallo muestra estado de error."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        result = _make_result(success=False, total=4, completed=2, failed=2,
                              output="⚠️ Parcial")
        AutomationPage._on_execution_done(page, result, dry_run=False)
        self.assertFalse(page._running)
        call_kwargs = page._lbl_status.configure.call_args.kwargs
        self.assertIn("text_color", call_kwargs)

    def test_on_execution_done_not_found(self):
        """_on_execution_done() con total_steps=0 muestra error rojo."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        result = _make_result(
            success=False, total=0, completed=0, failed=0,
            output="", name="x"
        )
        result.error = "Automatización 'x' no encontrada."
        AutomationPage._on_execution_done(page, result, dry_run=False)
        call_kwargs = page._lbl_status.configure.call_args.kwargs
        from ui.pages.automation_page import _RED
        self.assertEqual(call_kwargs.get("text_color"), _RED)

    def test_on_execution_error(self):
        """_on_execution_error() muestra texto de error."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        AutomationPage._on_execution_error(page, "Fallo inesperado")
        self.assertFalse(page._running)
        page._lbl_status.configure.assert_called()

    def test_populate_list_empty(self):
        """_populate_list([]) muestra mensaje de 'no hay automatizaciones'."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        AutomationPage._populate_list(page, [])
        page._lbl_loading.pack.assert_called()

    def test_populate_list_with_items(self):
        """_populate_list([info]) oculta el loading y crea cards."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        infos = [_make_info("auto1"), _make_info("auto2")]

        # Mock _AutomationCard
        with patch("ui.pages.automation_page._AutomationCard") as MockCard:
            mock_instance = MagicMock()
            MockCard.return_value = mock_instance
            AutomationPage._populate_list(page, infos)
            self.assertEqual(MockCard.call_count, 2)

    def test_refresh_cards_updates_selection(self):
        """_refresh_cards() actualiza el fondo de las tarjetas."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage, _BG_CARD_SEL, _BG_CARD
        info = _make_info("auto1")
        page._selected_info = info

        card1 = MagicMock()
        card1._info = info
        card2 = MagicMock()
        card2._info = _make_info("auto2")
        page._cards = [card1, card2]

        AutomationPage._refresh_cards(page)
        card1.configure.assert_called_with(fg_color=_BG_CARD_SEL)
        card2.configure.assert_called_with(fg_color=_BG_CARD)

    def test_execute_sets_running_true(self):
        """_execute() marca _running=True y deshabilita botones."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        page._selected_info = _make_info()

        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            mock_thread.return_value.start = MagicMock()
            AutomationPage._execute(page, dry_run=True)
            self.assertTrue(page._running)
            page._btn_run.configure.assert_called_with(state="disabled")

    def test_execute_dry_run_shows_simulacion(self):
        """_execute(dry_run=True) muestra 'Simulando' en el status."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        page._selected_info = _make_info()

        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            AutomationPage._execute(page, dry_run=True)
            call_kwargs = page._lbl_status.configure.call_args.kwargs
            self.assertIn("Simulando", call_kwargs.get("text", ""))

    def test_execute_real_shows_ejecutando(self):
        """_execute(dry_run=False) muestra 'Ejecutando' en el status."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        page._selected_info = _make_info()

        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            AutomationPage._execute(page, dry_run=False)
            call_kwargs = page._lbl_status.configure.call_args.kwargs
            self.assertIn("Ejecutando", call_kwargs.get("text", ""))

    def test_show_detail_populates_name(self):
        """_show_detail() configura el nombre del detalle."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        info = _make_info(display_name="Mi Automatización")

        with patch.object(AutomationPage, "_load_steps") as mock_load:
            # Parchear threading.Thread
            with patch("threading.Thread") as mock_thread:
                mock_thread.return_value.start = MagicMock()
                AutomationPage._show_detail(page, info)
                page._detail_name.configure.assert_called_with(text="Mi Automatización")

    def test_show_detail_hides_placeholder(self):
        """_show_detail() oculta el placeholder."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        info = _make_info()

        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            AutomationPage._show_detail(page, info)
            page._placeholder.pack_forget.assert_called()
            page._detail_frame.pack.assert_called()

    def test_show_steps_with_all_types(self):
        """_show_steps() con todos los tipos de pasos no crashea."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage

        steps = [
            {"type": "open_app", "app": "vscode"},
            {"type": "open_url", "url": "https://example.com"},
            {"type": "delay", "seconds": 1.5},
            {"type": "message", "text": "Hola"},
            {"type": "tipo_raro"},  # Desconocido
        ]

        # Mock del steps_frame para capturar widgets creados
        created = []

        class FakeFrame2:
            def __init__(self, *a, **kw): pass
            def pack(self, **kw): created.append(self)
            def winfo_children(self): return []
            def destroy(self): pass

        page._steps_frame = MagicMock()
        page._steps_frame.winfo_children = MagicMock(return_value=[])

        # No debe lanzar excepción
        try:
            AutomationPage._show_steps(page, steps)
        except Exception as e:
            self.fail(f"_show_steps() lanzó excepción: {e}")

    def test_show_steps_empty(self):
        """_show_steps([]) muestra mensaje de 'no se pudieron leer'."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        page._steps_frame = MagicMock()
        page._steps_frame.winfo_children = MagicMock(return_value=[])
        # No debe crashear
        AutomationPage._show_steps(page, [])

    def test_on_select_sets_selected_info(self):
        """_on_select() guarda la info seleccionada."""
        page = self._make_page()
        from ui.pages.automation_page import AutomationPage
        info = _make_info()

        with patch.object(AutomationPage, "_refresh_cards"):
            with patch.object(AutomationPage, "_show_detail"):
                AutomationPage._on_select(page, info)
                self.assertEqual(page._selected_info, info)


class TestAutomationPageConstants(unittest.TestCase):
    """Verifica que las constantes de color están definidas."""

    def test_color_constants_defined(self):
        from ui.pages import automation_page as ap
        for const in ["_BG_CARD", "_BG_CARD_SEL", "_ACCENT", "_TEXT_PRIMARY",
                      "_TEXT_MID", "_TEXT_DIM", "_GREEN", "_RED", "_YELLOW"]:
            self.assertTrue(hasattr(ap, const), f"Falta constante: {const}")

    def test_colors_are_hex_strings(self):
        from ui.pages import automation_page as ap
        for const in ["_BG_CARD", "_ACCENT", "_GREEN", "_RED"]:
            val = getattr(ap, const)
            self.assertIsInstance(val, str)
            self.assertTrue(val.startswith("#"), f"{const} no es hex: {val}")


class TestAutomationPageModuleLevel(unittest.TestCase):
    """Tests de módulo: exports, docstring, etc."""

    def test_module_has_docstring(self):
        from ui.pages import automation_page
        self.assertIsNotNone(automation_page.__doc__)
        self.assertIn("Fase 20", automation_page.__doc__)

    def test_automation_card_class_exists(self):
        from ui.pages.automation_page import _AutomationCard
        self.assertIsNotNone(_AutomationCard)

    def test_automation_page_class_exists(self):
        from ui.pages.automation_page import AutomationPage
        self.assertIsNotNone(AutomationPage)

    def test_get_engine_function_exists(self):
        from ui.pages.automation_page import _get_engine
        self.assertTrue(callable(_get_engine))


class TestAutomationEngineImports(unittest.TestCase):
    """Tests de importabilidad del módulo automation."""

    def test_automation_engine_import(self):
        from automation.engine import AutomationEngine
        self.assertIsNotNone(AutomationEngine)

    def test_automation_result_import(self):
        from automation.engine import AutomationResult
        self.assertIsNotNone(AutomationResult)

    def test_automation_info_import(self):
        from automation.engine import AutomationInfo
        self.assertIsNotNone(AutomationInfo)

    def test_step_result_import(self):
        from automation.engine import StepResult
        self.assertIsNotNone(StepResult)

    def test_automation_engine_singleton_import(self):
        from automation.engine import automation_engine
        from automation.engine import AutomationEngine
        self.assertIsInstance(automation_engine, AutomationEngine)

    def test_automation_init_exports(self):
        import automation
        for name in ["AutomationEngine", "AutomationResult", "AutomationInfo",
                     "StepResult", "automation_engine"]:
            self.assertTrue(hasattr(automation, name), f"Falta export: {name}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

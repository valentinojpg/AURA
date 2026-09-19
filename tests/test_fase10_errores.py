"""
AURA — Tests automáticos de Fase 10: Manejo de errores y estado

Cubre:
  - core/error_handler.py: hooks, report_error, suscriptores, métricas
  - core/diagnostics.py: DiagsResult, OllamaDiag, DiskDiag, SystemDiag,
                          run_diagnostics, to_text
  - ui/components/status_bar.py: existencia de clase y atributos
  - core/__init__.py: exportaciones correctas
  - ui/components/__init__.py: exportación de StatusBar
  - Regresión: imports de fases anteriores siguen funcionando

Todos los tests son no-gráficos (sin crear ventanas CTk).
Se puede ejecutar con:
    .\\env\\Scripts\\python.exe -m pytest tests/test_fase10_errores.py -v
    .\\env\\Scripts\\python.exe tests/test_fase10_errores.py
"""

import sys
import os
import importlib
import py_compile
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

# Asegurar que el raíz esté en el path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


# ══════════════════════════════════════════════════════════════════════════
# 1. VERIFICACIÓN DE SINTAXIS
# ══════════════════════════════════════════════════════════════════════════

class TestSyntaxFase10(unittest.TestCase):
    """Verifica que todos los archivos nuevos/modificados tienen sintaxis correcta."""

    _FILES = [
        "core/error_handler.py",
        "core/diagnostics.py",
        "ui/components/status_bar.py",
        "ui/pages/settings_page.py",
        "ui/main_window.py",
        "core/__init__.py",
        "ui/components/__init__.py",
        "run.py",
    ]

    def _path(self, rel):
        return os.path.join(ROOT_DIR, rel.replace("/", os.sep))

    def test_syntax_error_handler(self):
        py_compile.compile(self._path("core/error_handler.py"), doraise=True)

    def test_syntax_diagnostics(self):
        py_compile.compile(self._path("core/diagnostics.py"), doraise=True)

    def test_syntax_status_bar(self):
        py_compile.compile(self._path("ui/components/status_bar.py"), doraise=True)

    def test_syntax_settings_page(self):
        py_compile.compile(self._path("ui/pages/settings_page.py"), doraise=True)

    def test_syntax_main_window(self):
        py_compile.compile(self._path("ui/main_window.py"), doraise=True)

    def test_syntax_core_init(self):
        py_compile.compile(self._path("core/__init__.py"), doraise=True)

    def test_syntax_components_init(self):
        py_compile.compile(self._path("ui/components/__init__.py"), doraise=True)

    def test_syntax_run(self):
        py_compile.compile(self._path("run.py"), doraise=True)


# ══════════════════════════════════════════════════════════════════════════
# 2. ERROR HANDLER
# ══════════════════════════════════════════════════════════════════════════

class TestErrorHandler(unittest.TestCase):
    """Tests del manejador global de errores."""

    def setUp(self):
        # Importar fresh (sin el singleton global modificado)
        from core.error_handler import ErrorHandler
        self.handler = ErrorHandler()

    def tearDown(self):
        if self.handler.is_installed:
            self.handler.uninstall()

    def test_importable(self):
        """error_handler es importable desde core.error_handler."""
        from core.error_handler import error_handler
        self.assertIsNotNone(error_handler)

    def test_singleton_instance(self):
        """Existe instancia global error_handler."""
        from core.error_handler import error_handler
        self.assertTrue(hasattr(error_handler, "install"))

    def test_install_uninstall(self):
        """install() / uninstall() cambian el estado correctly."""
        self.assertFalse(self.handler.is_installed)
        self.handler.install()
        self.assertTrue(self.handler.is_installed)
        self.handler.uninstall()
        self.assertFalse(self.handler.is_installed)

    def test_install_idempotent(self):
        """Llamar install() dos veces no rompe nada."""
        self.handler.install()
        self.handler.install()  # No debe lanzar excepción
        self.assertTrue(self.handler.is_installed)

    def test_subscribe_and_notify(self):
        """subscribe() registra callback que se llama con report_error."""
        received = []
        self.handler.subscribe(lambda l, t, m: received.append((l, t, m)))
        self.handler.report_error("Título", "Mensaje")
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][1], "Título")
        self.assertEqual(received[0][2], "Mensaje")

    def test_report_error_level_error(self):
        """report_error sin level usa LEVEL_ERROR por defecto."""
        from core.error_handler import LEVEL_ERROR
        received = []
        self.handler.subscribe(lambda l, t, m: received.append(l))
        self.handler.report_error("Test", "Mensaje")
        self.assertEqual(received[0], LEVEL_ERROR)

    def test_report_warning(self):
        """report_warning notifica con LEVEL_WARNING."""
        from core.error_handler import LEVEL_WARNING
        received = []
        self.handler.subscribe(lambda l, t, m: received.append(l))
        self.handler.report_warning("Advertencia", "Detalle")
        self.assertEqual(received[0], LEVEL_WARNING)

    def test_error_count_increases(self):
        """error_count aumenta con cada reporte."""
        self.assertEqual(self.handler.error_count, 0)
        self.handler.report_error("E1", "m1")
        self.handler.report_error("E2", "m2")
        self.assertEqual(self.handler.error_count, 2)

    def test_last_error_updated(self):
        """last_error se actualiza con cada reporte."""
        self.assertIsNone(self.handler.last_error)
        self.handler.report_error("Err", "último mensaje")
        self.assertEqual(self.handler.last_error, "último mensaje")

    def test_reset_count(self):
        """reset_count() vuelve el contador a 0."""
        self.handler.report_error("E", "m")
        self.handler.reset_count()
        self.assertEqual(self.handler.error_count, 0)
        self.assertIsNone(self.handler.last_error)

    def test_unsubscribe(self):
        """unsubscribe() elimina el callback."""
        received = []
        cb = lambda l, t, m: received.append(1)
        self.handler.subscribe(cb)
        self.handler.unsubscribe(cb)
        self.handler.report_error("E", "m")
        self.assertEqual(len(received), 0)

    def test_subscriber_exception_does_not_propagate(self):
        """Un error en el suscriptor no rompe report_error."""
        def bad_cb(l, t, m):
            raise RuntimeError("suscriptor roto")

        self.handler.subscribe(bad_cb)
        # No debe lanzar excepción
        self.handler.report_error("E", "m")

    def test_multiple_subscribers(self):
        """Múltiples suscriptores reciben la notificación."""
        results = []
        self.handler.subscribe(lambda l, t, m: results.append(1))
        self.handler.subscribe(lambda l, t, m: results.append(2))
        self.handler.report_error("E", "m")
        self.assertEqual(sorted(results), [1, 2])

    def test_level_constants_exist(self):
        """Las constantes de nivel existen."""
        from core.error_handler import LEVEL_CRITICAL, LEVEL_ERROR, LEVEL_WARNING
        self.assertEqual(LEVEL_CRITICAL, "critical")
        self.assertEqual(LEVEL_ERROR, "error")
        self.assertEqual(LEVEL_WARNING, "warning")

    def test_repr(self):
        """__repr__ retorna string descriptivo."""
        r = repr(self.handler)
        self.assertIn("ErrorHandler", r)
        self.assertIn("installed=", r)


# ══════════════════════════════════════════════════════════════════════════
# 3. DIAGNOSTICS
# ══════════════════════════════════════════════════════════════════════════

class TestDiagnostics(unittest.TestCase):
    """Tests de la utilidad de diagnóstico del sistema."""

    def test_importable(self):
        """run_diagnostics es importable."""
        from core.diagnostics import run_diagnostics
        self.assertTrue(callable(run_diagnostics))

    def test_diags_result_importable(self):
        """DiagsResult es importable."""
        from core.diagnostics import DiagsResult
        self.assertIsNotNone(DiagsResult)

    def test_dataclasses_importable(self):
        """Todos los dataclasses de diagnóstico son importables."""
        from core.diagnostics import (
            DiagsResult, OllamaDiag, DiskDiag, SystemDiag, ConfigDiag
        )
        # Deben ser instanciables sin argumentos
        DiagsResult()
        OllamaDiag()
        DiskDiag()
        SystemDiag()
        ConfigDiag()

    def test_run_diagnostics_returns_diags_result(self):
        """run_diagnostics() retorna DiagsResult."""
        from core.diagnostics import run_diagnostics, DiagsResult
        result = run_diagnostics()
        self.assertIsInstance(result, DiagsResult)

    def test_diags_result_has_system(self):
        """DiagsResult tiene campo system con python_version."""
        from core.diagnostics import run_diagnostics
        result = run_diagnostics()
        self.assertIsNotNone(result.system)
        self.assertTrue(len(result.system.python_version) > 0)

    def test_diags_result_has_config(self):
        """DiagsResult tiene campo config con ai_provider."""
        from core.diagnostics import run_diagnostics
        result = run_diagnostics()
        self.assertIsNotNone(result.config)
        # ai_provider puede ser 'ollama' o '(no configurado)'
        self.assertIsInstance(result.config.ai_provider, str)

    def test_diags_result_has_ollama(self):
        """DiagsResult tiene campo ollama (reachable es bool)."""
        from core.diagnostics import run_diagnostics
        result = run_diagnostics()
        self.assertIsNotNone(result.ollama)
        self.assertIsInstance(result.ollama.reachable, bool)

    def test_diags_result_has_disk(self):
        """DiagsResult tiene campo disk con total_gb > 0."""
        from core.diagnostics import run_diagnostics
        result = run_diagnostics()
        self.assertIsNotNone(result.disk)
        self.assertGreater(result.disk.total_gb, 0)

    def test_diags_result_has_issues_list(self):
        """DiagsResult.issues es una lista."""
        from core.diagnostics import run_diagnostics
        result = run_diagnostics()
        self.assertIsInstance(result.issues, list)

    def test_diags_result_has_summary_str(self):
        """DiagsResult.summary es una cadena no vacía."""
        from core.diagnostics import run_diagnostics
        result = run_diagnostics()
        self.assertIsInstance(result.summary, str)
        self.assertTrue(len(result.summary) > 0)

    def test_diags_result_overall_ok_is_bool(self):
        """DiagsResult.overall_ok es bool."""
        from core.diagnostics import run_diagnostics
        result = run_diagnostics()
        self.assertIsInstance(result.overall_ok, bool)

    def test_to_text_returns_string(self):
        """DiagsResult.to_text() retorna una cadena."""
        from core.diagnostics import run_diagnostics
        result = run_diagnostics()
        text = result.to_text()
        self.assertIsInstance(text, str)
        self.assertTrue(len(text) > 0)

    def test_to_text_contains_headers(self):
        """to_text() contiene las secciones principales."""
        from core.diagnostics import run_diagnostics
        result = run_diagnostics()
        text = result.to_text()
        self.assertIn("SISTEMA", text)
        self.assertIn("CONFIGURACIÓN", text)
        self.assertIn("OLLAMA", text)
        self.assertIn("DISCO", text)
        self.assertIn("RESUMEN", text)

    def test_run_diagnostics_no_exception(self):
        """run_diagnostics() no lanza excepciones bajo ninguna condición."""
        from core.diagnostics import run_diagnostics
        try:
            run_diagnostics()
        except Exception as e:
            self.fail(f"run_diagnostics() lanzó excepción: {e}")

    def test_system_diag_has_os_name(self):
        """SystemDiag tiene os_name y architecture."""
        from core.diagnostics import run_diagnostics
        result = run_diagnostics()
        self.assertIsInstance(result.system.os_name, str)
        self.assertIsInstance(result.system.architecture, str)

    def test_disk_diag_conversations_count_non_negative(self):
        """DiskDiag.conversations_count es >= 0."""
        from core.diagnostics import run_diagnostics
        result = run_diagnostics()
        self.assertGreaterEqual(result.disk.conversations_count, 0)


# ══════════════════════════════════════════════════════════════════════════
# 4. CORE __INIT__ EXPORTS
# ══════════════════════════════════════════════════════════════════════════

class TestCoreExports(unittest.TestCase):
    """Verifica que core/__init__.py exporta correctamente."""

    def test_error_handler_in_core(self):
        """core exporta error_handler."""
        from core import error_handler
        self.assertIsNotNone(error_handler)

    def test_run_diagnostics_in_core(self):
        """core exporta run_diagnostics."""
        from core import run_diagnostics
        self.assertTrue(callable(run_diagnostics))

    def test_diags_result_in_core(self):
        """core exporta DiagsResult."""
        from core import DiagsResult
        self.assertIsNotNone(DiagsResult)

    def test_level_constants_in_core(self):
        """core exporta constantes de nivel."""
        from core import LEVEL_CRITICAL, LEVEL_ERROR, LEVEL_WARNING
        self.assertIsNotNone(LEVEL_CRITICAL)
        self.assertIsNotNone(LEVEL_ERROR)
        self.assertIsNotNone(LEVEL_WARNING)

    def test_app_state_still_in_core(self):
        """Regresión: app_state sigue exportado desde core."""
        from core import app_state
        self.assertIsNotNone(app_state)

    def test_app_still_in_core(self):
        """Regresión: App sigue exportado desde core."""
        from core import App
        self.assertIsNotNone(App)


# ══════════════════════════════════════════════════════════════════════════
# 5. UI COMPONENTS __INIT__ EXPORTS
# ══════════════════════════════════════════════════════════════════════════

class TestComponentsExports(unittest.TestCase):
    """Verifica que ui/components/__init__.py exporta StatusBar."""

    def test_status_bar_importable_from_components(self):
        """StatusBar es importable desde ui.components."""
        # No crear instancia (requiere ctk)
        import ui.components as comp
        self.assertTrue(hasattr(comp, "StatusBar"))

    def test_sidebar_still_exported(self):
        """Regresión: Sidebar sigue exportado."""
        import ui.components as comp
        self.assertTrue(hasattr(comp, "Sidebar"))

    def test_topbar_still_exported(self):
        """Regresión: TopBar sigue exportado."""
        import ui.components as comp
        self.assertTrue(hasattr(comp, "TopBar"))

    def test_chat_bubble_still_exported(self):
        """Regresión: ChatBubble sigue exportado."""
        import ui.components as comp
        self.assertTrue(hasattr(comp, "ChatBubble"))

    def test_history_panel_still_exported(self):
        """Regresión: HistoryPanel sigue exportado."""
        import ui.components as comp
        self.assertTrue(hasattr(comp, "HistoryPanel"))


# ══════════════════════════════════════════════════════════════════════════
# 6. STATUS BAR (sin instanciar CTk)
# ══════════════════════════════════════════════════════════════════════════

class TestStatusBarModule(unittest.TestCase):
    """Verifica el módulo status_bar sin crear widgets reales."""

    def test_status_bar_class_importable(self):
        """StatusBar es importable desde ui.components.status_bar."""
        from ui.components.status_bar import StatusBar
        self.assertIsNotNone(StatusBar)

    def test_level_colors_defined(self):
        """Las constantes de color están definidas."""
        import ui.components.status_bar as sb
        self.assertIn("idle", sb._LEVEL_COLORS)
        self.assertIn("ok", sb._LEVEL_COLORS)
        self.assertIn("warning", sb._LEVEL_COLORS)
        self.assertIn("error", sb._LEVEL_COLORS)
        self.assertIn("loading", sb._LEVEL_COLORS)

    def test_status_bar_has_set_message_method(self):
        """StatusBar tiene el método set_message."""
        from ui.components.status_bar import StatusBar
        self.assertTrue(hasattr(StatusBar, "set_message"))

    def test_status_bar_has_set_error_count_method(self):
        """StatusBar tiene el método set_error_count."""
        from ui.components.status_bar import StatusBar
        self.assertTrue(hasattr(StatusBar, "set_error_count"))

    def test_status_bar_has_notify_error_method(self):
        """StatusBar tiene el método notify_error."""
        from ui.components.status_bar import StatusBar
        self.assertTrue(hasattr(StatusBar, "notify_error"))


# ══════════════════════════════════════════════════════════════════════════
# 7. REGRESIÓN: FASES ANTERIORES
# ══════════════════════════════════════════════════════════════════════════

class TestRegressionFasesAnteriores(unittest.TestCase):
    """Verifica que los módulos de fases anteriores siguen importando."""

    def test_ai_package_importable(self):
        from ai import (
            ChatMessage, get_default_provider, AuraAIError,
            ProviderNotAvailableError, ModelNotFoundError, RequestTimeoutError,
        )
        self.assertIsNotNone(ChatMessage)

    def test_data_package_importable(self):
        from data import ConversationStore, Conversation
        self.assertIsNotNone(ConversationStore)

    def test_conversation_store_functional(self):
        from data.conversation_store import ConversationStore
        store = ConversationStore(conversations_dir=None)
        conv = store.new_conversation()
        self.assertEqual(len(conv.id), 8)

    def test_config_settings_importable(self):
        from config.settings import settings
        self.assertIsNotNone(settings)

    def test_utils_logger_importable(self):
        from utils.logger import get_logger
        logger = get_logger("aura.test")
        self.assertIsNotNone(logger)

    def test_core_app_importable(self):
        from core.app import App
        self.assertIsNotNone(App)

    def test_core_state_importable(self):
        from core.state import app_state
        self.assertIsNotNone(app_state)

    def test_ai_errors_hierarchy(self):
        from ai.errors import AuraAIError, ProviderNotAvailableError
        self.assertTrue(issubclass(ProviderNotAvailableError, AuraAIError))

    def test_chat_page_importable(self):
        """ChatPage sigue siendo importable (sin ctk real)."""
        import py_compile
        path = os.path.join(ROOT_DIR, "ui", "pages", "chat_page.py")
        py_compile.compile(path, doraise=True)

    def test_history_panel_importable(self):
        """HistoryPanel sigue siendo importable."""
        import py_compile
        path = os.path.join(ROOT_DIR, "ui", "components", "history_panel.py")
        py_compile.compile(path, doraise=True)


# ══════════════════════════════════════════════════════════════════════════
# RUNNER
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestSyntaxFase10))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorHandler))
    suite.addTests(loader.loadTestsFromTestCase(TestDiagnostics))
    suite.addTests(loader.loadTestsFromTestCase(TestCoreExports))
    suite.addTests(loader.loadTestsFromTestCase(TestComponentsExports))
    suite.addTests(loader.loadTestsFromTestCase(TestStatusBarModule))
    suite.addTests(loader.loadTestsFromTestCase(TestRegressionFasesAnteriores))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\n{'='*60}")
    print(f"FASE 10 -- Manejo de errores y estado")
    print(f"Tests ejecutados: {result.testsRun}")
    print(f"[OK]  Pasados: {passed}")
    print(f"[ERR] Fallidos: {len(result.failures)}")
    print(f"[ERR] Errores: {len(result.errors)}")
    print(f"{'='*60}")

    sys.exit(0 if result.wasSuccessful() else 1)

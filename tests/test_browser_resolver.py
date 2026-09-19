"""
Tests unitarios y de integración para la resolución de navegadores y automatizaciones en AURA.

Verifica:
1. Configuración de BROWSER_PREFERIDO y detección de navegador predeterminado.
2. Alias genéricos 'navegador', 'browser', 'web' resolviendo a BROWSER_PREFERIDO.
3. 'chrome' resolviendo SOLO a Chrome real; si falta, fallar con mensaje claro sin abrir otro navegador.
4. 'firefox' resolviendo SOLO a Firefox real.
5. open_url abriendo con BROWSER_PREFERIDO y registrando el navegador utilizado.
6. Fix del conteo de resultados en automatizaciones (OK, PARCIAL, FALLIDA, Falló: X/Y).
7. Automatización 'inicio_dia.yaml' usando 'navegador'.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import unittest
from automation.engine import AutomationEngine, AutomationResult, StepResult

from config.settings import settings
from core.app_resolver import (
    BROWSER_DISPLAY_NAMES,
    GENERIC_BROWSER_ALIASES,
    SUPPORTED_BROWSERS,
    detect_default_browser,
    find_browser_executable,
    get_installed_browsers,
    get_preferred_browser_name,
    launch_app,
    resolve_app,
)
from core.entity_resolver import entity_resolver


class TestBrowserResolution(unittest.TestCase):
    """Pruebas sobre el motor de resolución de navegadores y alias."""

    def setUp(self):
        self._original_browser = settings.get("BROWSER_PREFERIDO", "firefox")

    def tearDown(self):
        settings.set("BROWSER_PREFERIDO", self._original_browser)

    def test_detect_default_browser(self):
        """detect_default_browser retorna un navegador válido soportado."""
        detected = detect_default_browser()
        self.assertIn(detected, SUPPORTED_BROWSERS)

    def test_get_preferred_browser_name(self):
        """get_preferred_browser_name respeta settings o default."""
        settings.set("BROWSER_PREFERIDO", "firefox")
        self.assertEqual(get_preferred_browser_name(), "firefox")

        settings.set("BROWSER_PREFERIDO", "msedge")
        self.assertEqual(get_preferred_browser_name(), "msedge")

    def test_generic_browser_aliases_resolve_to_preferred(self):
        """'navegador', 'browser' y 'web' deben resolver siempre al navegador preferido."""
        settings.set("BROWSER_PREFERIDO", "firefox")
        for alias in ("navegador", "browser", "web"):
            res = resolve_app(alias)
            self.assertTrue(res.success, f"Alias '{alias}' debió resolver exitosamente")
            self.assertTrue(res.is_browser)
            self.assertEqual(res.browser_name, "firefox")
            self.assertIsNotNone(res.executable)
            self.assertTrue(os.path.isfile(res.executable))

    def test_generic_browser_switches_when_preferred_changes(self):
        """Al cambiar BROWSER_PREFERIDO, 'navegador' resuelve al nuevo preferido si está instalado."""
        installed = get_installed_browsers()
        if "msedge" in installed:
            settings.set("BROWSER_PREFERIDO", "msedge")
            res = resolve_app("navegador")
            self.assertTrue(res.success)
            self.assertEqual(res.browser_name, "msedge")
            self.assertIn("msedge.exe", res.executable.lower())

    def test_chrome_missing_fails_with_clear_message(self):
        """
        Si Chrome no está instalado, resolve_app('chrome') DEBE fallar
        con mensaje claro sugiriendo el navegador preferido y NUNCA abrir otro.
        """
        settings.set("BROWSER_PREFERIDO", "firefox")

        with patch("core.app_resolver.find_browser_executable", return_value=None):
            res = resolve_app("chrome")
            self.assertFalse(res.success)
            self.assertIsNone(res.executable)
            self.assertIn("Chrome no está instalado", res.error)
            self.assertIn("Tu navegador preferido es Firefox. ¿Usarlo?", res.error)

    def test_chrome_missing_message_updates_with_preferred_browser(self):
        """El mensaje de Chrome sugiere dinámicamente el preferido activo (ej: Edge)."""
        settings.set("BROWSER_PREFERIDO", "msedge")

        with patch("core.app_resolver.find_browser_executable", return_value=None):
            res = resolve_app("chrome")
            self.assertFalse(res.success)
            self.assertIn("Tu navegador preferido es Edge. ¿Usarlo?", res.error)

    def test_firefox_resolves_only_to_firefox(self):
        """Firefox resuelve únicamente a Firefox real."""
        res = resolve_app("firefox")
        # En la máquina de prueba Firefox está instalado
        if res.success:
            self.assertIn("firefox.exe", res.executable.lower())
            self.assertEqual(res.browser_name, "firefox")

        # Si no estuviera instalado, debe fallar sin devolver otro navegador
        with patch("core.app_resolver.find_browser_executable", return_value=None):
            res_fail = resolve_app("firefox")
            self.assertFalse(res_fail.success)
            self.assertIn("Firefox no está instalado", res_fail.error)
            self.assertIsNone(res_fail.executable)

    def test_entity_resolver_respects_generic_browser(self):
        """EntityResolver resuelve 'open_app' con target 'navegador' a Firefox sin confundir."""
        settings.set("BROWSER_PREFERIDO", "firefox")
        res = entity_resolver.resolve(intent="open_app", target="navegador")
        self.assertTrue(res.resolved)
        self.assertIn("firefox.exe", res.executable.lower())

    def test_entity_resolver_chrome_missing_does_not_open_firefox(self):
        """EntityResolver no resuelve silenciosamente Chrome a Firefox si Chrome falta."""
        settings.set("BROWSER_PREFERIDO", "firefox")
        with patch("core.app_resolver.find_browser_executable", return_value=None):
            res = entity_resolver.resolve(intent="open_app", target="chrome")
            self.assertFalse(res.resolved)
            self.assertIn("Chrome no está instalado", res.extra.get("error", ""))


class TestAutomationEngineBrowserFix(unittest.TestCase):
    """Pruebas sobre el motor de automatizaciones con el fix de navegador y conteo."""

    def setUp(self):
        self.engine = AutomationEngine()
        self._original_browser = settings.get("BROWSER_PREFERIDO", "firefox")
        settings.set("BROWSER_PREFERIDO", "firefox")

    def tearDown(self):
        settings.set("BROWSER_PREFERIDO", self._original_browser)

    def test_inicio_dia_has_navegador_step(self):
        """La automatización inicio_dia.yaml debe usar 'open_app' con 'navegador', no 'chrome'."""
        path = Path(__file__).parent.parent / "data" / "automations" / "inicio_dia.yaml"
        self.assertTrue(path.exists())
        data = self.engine._load_file(path)
        steps = data.get("steps", [])

        apps = [s.get("app") for s in steps if s.get("type") == "open_app"]
        self.assertNotIn("chrome", apps, "No debe existir app: chrome hardcodeado en inicio_dia.yaml")
        self.assertIn("navegador", apps, "Debe existir app: navegador en inicio_dia.yaml")

    def test_open_url_uses_preferred_browser(self):
        """open_url debe abrir con BROWSER_PREFERIDO y loguear qué navegador usó."""
        settings.set("BROWSER_PREFERIDO", "firefox")

        with patch("core.app_resolver.launch_app") as mock_launch:
            sr = self.engine._step_open_url(0, {"type": "open_url", "url": "https://mail.google.com"}, dry_run=False)
            self.assertTrue(sr.success)
            self.assertIn("Firefox", sr.output)
            self.assertEqual(sr.data.get("browser"), "firefox")
            mock_launch.assert_called_once()

    def test_open_url_dry_run_shows_preferred_browser(self):
        """open_url en simulación indica qué navegador usaría."""
        settings.set("BROWSER_PREFERIDO", "firefox")
        sr = self.engine._step_open_url(0, {"type": "open_url", "url": "https://calendar.google.com"}, dry_run=True)
        self.assertTrue(sr.success)
        self.assertIn("Firefox", sr.output)
        self.assertIn("SIMULADO", sr.output)

    def test_open_app_chrome_fails_when_uninstalled_without_silent_switch(self):
        """open_app con app: chrome falla claramente si no está instalado y no abre Firefox."""
        with patch("core.app_resolver.find_browser_executable", return_value=None):
            sr = self.engine._step_open_app(0, {"type": "open_app", "app": "chrome"}, dry_run=False)
            self.assertFalse(sr.success)
            self.assertIn("Chrome no está instalado", sr.error)
            self.assertIn("Tu navegador preferido es Firefox. ¿Usarlo?", sr.error)

    def test_open_app_navegador_opens_preferred_browser(self):
        """open_app con app: navegador abre el ejecutable del navegador preferido."""
        settings.set("BROWSER_PREFERIDO", "firefox")
        with patch("core.app_resolver.launch_app") as mock_launch:
            sr = self.engine._step_open_app(0, {"type": "open_app", "app": "navegador"}, dry_run=False)
            self.assertTrue(sr.success)
            self.assertIn("firefox.exe", sr.output.lower())
            mock_launch.assert_called_once()

    def test_execution_summary_counts_and_statuses(self):
        """
        El conteo de resultados debe ser exacto:
        - 8 pasos con 1 fallo -> status='PARCIAL', completed=7, failed=1, success=False
        - 'Falló: 1/8' coincide con las ✗ del log.
        """
        steps = [
            StepResult(0, "message", True, output="Paso 1 ok"),
            StepResult(1, "open_app", False, error="Chrome no está instalado"),
            StepResult(2, "delay", True, output="Paso 3 ok"),
            StepResult(3, "open_url", True, output="Paso 4 ok"),
            StepResult(4, "delay", True, output="Paso 5 ok"),
            StepResult(5, "open_url", True, output="Paso 6 ok"),
            StepResult(6, "open_app", True, output="Paso 7 ok"),
            StepResult(7, "message", True, output="Paso 8 ok"),
        ]

        out = self.engine._build_output("Demo Test", steps, dry_run=False, status="PARCIAL")
        self.assertIn("⚠️ Parcial: Falló: 1/8 pasos (7/8 exitosos).", out)
        self.assertNotIn("Falló: 7/8", out, "El conteo NO debe estar invertido")

    def test_status_ok_when_all_succeed(self):
        """Status OK cuando todos los pasos son exitosos."""
        steps = [
            StepResult(0, "message", True, output="ok"),
            StepResult(1, "open_app", True, output="ok"),
        ]
        out = self.engine._build_output("Demo Test", steps, dry_run=False, status="OK")
        self.assertIn("✅ Estado: OK", out)
        self.assertIn("2/2", out)

    def test_status_fallida_when_all_fail(self):
        """Status FALLIDA cuando todos los pasos fallan."""
        steps = [
            StepResult(0, "open_app", False, error="err1"),
            StepResult(1, "open_url", False, error="err2"),
        ]
        out = self.engine._build_output("Demo Test", steps, dry_run=False, status="FALLIDA")
        self.assertIn("❌ Estado: FALLIDA", out)
        self.assertIn("Falló: 2/2 pasos", out)

    def test_inicio_dia_dry_run_success(self):
        """La automatización inicio_dia en dry-run debe completarse 8/8 con status OK."""
        res = self.engine.run("inicio_dia", dry_run=True)
        self.assertEqual(res.status, "OK")
        self.assertTrue(res.success)
        self.assertEqual(res.total_steps, 8)
        self.assertEqual(res.completed_steps, 8)
        self.assertEqual(res.failed_steps, 0)


if __name__ == "__main__":
    unittest.main()

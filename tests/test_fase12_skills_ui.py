"""
AURA — Tests automáticos: Fase 12 — UI de Skills

Valida la SkillsPage sin instanciar widgets CTk reales (importación y
estructura de clase), y verifica la integración con el sistema de skills
de la Fase 11.

Tests agrupados por área:
  - Importación y clase base
  - Constantes y helpers de la página
  - Integración con SkillRegistry (sin UI)
  - Lógica de datos (sin widgets)
  - Consistencia de la API pública

Total planificado: 40 tests
"""

import pytest
pytest.skip("Legacy CustomTkinter UI test (migrated to Flet in Phase 30)", allow_module_level=True)

import sys
import types
import importlib
import unittest
from unittest.mock import MagicMock, patch, PropertyMock


# ── Mocks de customtkinter para evitar display real ───────────────────────

def _make_ctk_mock():
    """Crea un mock completo de customtkinter para pruebas sin pantalla."""
    ctk = types.ModuleType("customtkinter")

    class _BaseWidget:
        def __init__(self, *a, **kw): pass
        def pack(self, **kw): return self
        def pack_forget(self): pass
        def configure(self, **kw): pass
        def pack_propagate(self, v): pass
        def winfo_children(self): return []
        def destroy(self): pass
        def after(self, ms, fn=None, *a):
            if fn: fn(*a)
        def winfo_toplevel(self): return self
        def grid(self, **kw): pass
        def bind(self, *a, **kw): pass

    class CTkFrame(_BaseWidget): pass
    class CTkScrollableFrame(_BaseWidget): pass
    class CTkLabel(_BaseWidget): pass
    class CTkButton(_BaseWidget): pass
    class CTkTextbox(_BaseWidget):
        def delete(self, *a): pass
        def insert(self, *a): pass
    class CTkEntry(_BaseWidget):
        def get(self): return ""
    class CTkOptionMenu(_BaseWidget): pass
    class CTkSwitch(_BaseWidget):
        def select(self): pass
        def deselect(self): pass
    class CTkToplevel(_BaseWidget):
        def grab_set(self): pass
        def protocol(self, *a, **kw): pass
        def transient(self, *a): pass
        def geometry(self, *a): pass
        def title(self, *a): pass
        def resizable(self, *a): pass
        def deiconify(self): pass
        def withdraw(self): pass
        def focus_force(self): pass
    class CTkScrollbar(_BaseWidget): pass
    class CTkProgressBar(_BaseWidget): pass
    class CTkComboBox(_BaseWidget):
        def get(self): return ""
    class CTkFont:
        def __init__(self, *a, **kw): pass
    class StringVar:
        def __init__(self, value=""): self._v = value
        def get(self): return self._v
        def set(self, v): self._v = v
    class BooleanVar:
        def __init__(self, value=False): self._v = value
        def get(self): return self._v
        def set(self, v): self._v = v
    class IntVar:
        def __init__(self, value=0): self._v = value
        def get(self): return self._v
        def set(self, v): self._v = v

    ctk.CTkFrame = CTkFrame
    ctk.CTkScrollableFrame = CTkScrollableFrame
    ctk.CTkLabel = CTkLabel
    ctk.CTkButton = CTkButton
    ctk.CTkTextbox = CTkTextbox
    ctk.CTkEntry = CTkEntry
    ctk.CTkOptionMenu = CTkOptionMenu
    ctk.CTkSwitch = CTkSwitch
    ctk.CTkToplevel = CTkToplevel
    ctk.CTkScrollbar = CTkScrollbar
    ctk.CTkProgressBar = CTkProgressBar
    ctk.CTkComboBox = CTkComboBox
    ctk.CTkFont = CTkFont
    ctk.StringVar = StringVar
    ctk.BooleanVar = BooleanVar
    ctk.IntVar = IntVar
    ctk.get_appearance_mode = lambda: "dark"
    ctk.set_appearance_mode = lambda m: None
    ctk.ThemeManager = MagicMock()
    return ctk


# Instalar mocks antes de importar módulos de UI
_ctk_mock = _make_ctk_mock()
sys.modules["customtkinter"] = _ctk_mock

# Mock de logger para no necesitar el sistema de archivos
_logger_mock = MagicMock()
_utils_mock = types.ModuleType("utils")
_utils_logger_mock = types.ModuleType("utils.logger")
_utils_logger_mock.get_logger = MagicMock(return_value=_logger_mock)
sys.modules["utils"] = _utils_mock
sys.modules["utils.logger"] = _utils_logger_mock

# Mock de config
_config_mock = types.ModuleType("config")
_config_settings_mock = types.ModuleType("config.settings")
_mock_settings = MagicMock()
_mock_settings.get = MagicMock(return_value="mock_value")
_mock_settings.is_first_run = MagicMock(return_value=False)
_config_settings_mock.settings = _mock_settings
sys.modules["config"] = _config_mock
sys.modules["config.settings"] = _config_settings_mock


# ── Importaciones bajo prueba ─────────────────────────────────────────────

# Importar base_page primero
from ui.pages.base_page import BasePage  # noqa: E402

# Importar SkillsPage
from ui.pages.skills_page import (  # noqa: E402
    SkillsPage,
    _SkillCard,
    _cat_icon,
    _CATEGORY_ICONS,
    _BG_CARD,
    _BG_CARD_SEL,
    _ACCENT,
    _GREEN,
    _RED,
)

# Importar sistema de skills real (Fase 11)
from skills.skill_base import BaseSkill, SkillMeta, SkillResult, CATEGORY_DEMO
from skills.skill_registry import SkillRegistry, SkillEntry
from skills.builtin.demo_skill import DemoSkill


# ── Helpers de test ───────────────────────────────────────────────────────

def _make_entry(name="test_skill", enabled=True) -> SkillEntry:
    """Crea un SkillEntry de prueba sin registrar en el singleton."""
    skill = DemoSkill()
    skill.setup()
    # Crear SkillMeta con nombre personalizado si se necesita
    entry = SkillEntry(skill=skill, enabled=enabled)
    return entry


def _make_page() -> SkillsPage:
    """Crea una SkillsPage con parent mock."""
    parent = MagicMock()
    parent.winfo_children = MagicMock(return_value=[])
    page = SkillsPage(parent)
    return page


# ══════════════════════════════════════════════════════════════════════════
# Grupo 1: Importación y herencia
# ══════════════════════════════════════════════════════════════════════════

class TestSkillsPageImport(unittest.TestCase):
    """Verifica que la página importa correctamente y hereda de BasePage."""

    def test_skills_page_importable(self):
        """SkillsPage importa sin errores."""
        self.assertIsNotNone(SkillsPage)

    def test_skills_page_is_class(self):
        """SkillsPage es una clase."""
        self.assertTrue(isinstance(SkillsPage, type))

    def test_inherits_base_page(self):
        """SkillsPage hereda de BasePage."""
        self.assertTrue(issubclass(SkillsPage, BasePage))

    def test_page_name_constant(self):
        """PAGE_NAME está definido y es 'Skills'."""
        self.assertEqual(SkillsPage.PAGE_NAME, "Skills")

    def test_skill_card_importable(self):
        """_SkillCard importa correctamente."""
        self.assertIsNotNone(_SkillCard)

    def test_cat_icon_importable(self):
        """_cat_icon importa correctamente."""
        self.assertIsNotNone(_cat_icon)

    def test_category_icons_dict_importable(self):
        """_CATEGORY_ICONS importa correctamente."""
        self.assertIsInstance(_CATEGORY_ICONS, dict)


# ══════════════════════════════════════════════════════════════════════════
# Grupo 2: Constantes de diseño
# ══════════════════════════════════════════════════════════════════════════

class TestSkillsPageConstants(unittest.TestCase):
    """Verifica las constantes de color y configuración."""

    def test_bg_card_is_hex(self):
        """_BG_CARD es un color hexadecimal."""
        self.assertTrue(_BG_CARD.startswith("#"))

    def test_bg_card_sel_is_hex(self):
        """_BG_CARD_SEL es un color hexadecimal."""
        self.assertTrue(_BG_CARD_SEL.startswith("#"))

    def test_accent_is_hex(self):
        """_ACCENT es un color hexadecimal."""
        self.assertTrue(_ACCENT.startswith("#"))

    def test_green_is_hex(self):
        """_GREEN es un color hexadecimal."""
        self.assertTrue(_GREEN.startswith("#"))

    def test_red_is_hex(self):
        """_RED es un color hexadecimal."""
        self.assertTrue(_RED.startswith("#"))

    def test_category_icons_has_all_categories(self):
        """_CATEGORY_ICONS contiene las 7 categorías previstas en el roadmap."""
        expected = {"demo", "system", "files", "search", "programs", "web", "automation"}
        self.assertEqual(set(_CATEGORY_ICONS.keys()), expected)

    def test_category_icons_values_are_nonempty(self):
        """Todos los iconos de categoría son strings no vacíos."""
        for cat, icon in _CATEGORY_ICONS.items():
            with self.subTest(category=cat):
                self.assertIsInstance(icon, str)
                self.assertGreater(len(icon), 0)


# ══════════════════════════════════════════════════════════════════════════
# Grupo 3: Función _cat_icon
# ══════════════════════════════════════════════════════════════════════════

class TestCatIcon(unittest.TestCase):
    """Verifica el helper _cat_icon."""

    def test_demo_icon(self):
        """Retorna icono correcto para categoría 'demo'."""
        self.assertEqual(_cat_icon("demo"), "⚡")

    def test_system_icon(self):
        """Retorna icono para categoría 'system'."""
        icon = _cat_icon("system")
        self.assertIsInstance(icon, str)
        self.assertGreater(len(icon), 0)

    def test_unknown_category_returns_default(self):
        """Categoría desconocida retorna un emoji por defecto (no vacío)."""
        icon = _cat_icon("categoria_inexistente")
        self.assertIsInstance(icon, str)
        self.assertGreater(len(icon), 0)

    def test_all_known_categories(self):
        """Todas las categorías conocidas retornan un icono."""
        for cat in ["demo", "system", "files", "search", "programs", "web", "automation"]:
            with self.subTest(cat=cat):
                icon = _cat_icon(cat)
                self.assertIsInstance(icon, str)
                self.assertGreater(len(icon), 0)


# ══════════════════════════════════════════════════════════════════════════
# Grupo 4: Instanciación de la página
# ══════════════════════════════════════════════════════════════════════════

class TestSkillsPageInstantiation(unittest.TestCase):
    """Verifica que la página se instancia correctamente."""

    def test_instantiation_succeeds(self):
        """SkillsPage se instancia sin lanzar excepciones."""
        page = _make_page()
        self.assertIsInstance(page, SkillsPage)

    def test_has_selected_entry_attribute(self):
        """La página tiene el atributo _selected_entry inicializado."""
        page = _make_page()
        self.assertTrue(hasattr(page, "_selected_entry"))

    def test_selected_entry_initially_none(self):
        """_selected_entry es None al inicio."""
        page = _make_page()
        self.assertIsNone(page._selected_entry)

    def test_has_cards_dict(self):
        """La página tiene el diccionario _cards."""
        page = _make_page()
        self.assertTrue(hasattr(page, "_cards"))
        self.assertIsInstance(page._cards, dict)

    def test_cards_initially_empty(self):
        """_cards está vacío al inicio."""
        page = _make_page()
        self.assertEqual(len(page._cards), 0)

    def test_has_cmd_var(self):
        """La página tiene el StringVar _cmd_var para el menú de comandos."""
        page = _make_page()
        self.assertTrue(hasattr(page, "_cmd_var"))


# ══════════════════════════════════════════════════════════════════════════
# Grupo 5: Métodos públicos y privados de la página
# ══════════════════════════════════════════════════════════════════════════

class TestSkillsPageMethods(unittest.TestCase):
    """Verifica que los métodos clave existen y son callable."""

    def setUp(self):
        self.page = _make_page()

    def test_has_on_enter(self):
        """on_enter() existe y es callable."""
        self.assertTrue(callable(getattr(self.page, "on_enter", None)))

    def test_has_refresh_list(self):
        """_refresh_list() existe y es callable."""
        self.assertTrue(callable(getattr(self.page, "_refresh_list", None)))

    def test_has_render_list(self):
        """_render_list() existe y es callable."""
        self.assertTrue(callable(getattr(self.page, "_render_list", None)))

    def test_has_select_skill(self):
        """_select_skill() existe y es callable."""
        self.assertTrue(callable(getattr(self.page, "_select_skill", None)))

    def test_has_show_detail(self):
        """_show_detail() existe y es callable."""
        self.assertTrue(callable(getattr(self.page, "_show_detail", None)))

    def test_has_toggle_selected(self):
        """_toggle_selected() existe y es callable."""
        self.assertTrue(callable(getattr(self.page, "_toggle_selected", None)))

    def test_has_run_command(self):
        """_run_command() existe y es callable."""
        self.assertTrue(callable(getattr(self.page, "_run_command", None)))

    def test_has_on_exec_done(self):
        """_on_exec_done() existe y es callable."""
        self.assertTrue(callable(getattr(self.page, "_on_exec_done", None)))

    def test_has_set_output(self):
        """_set_output() existe y es callable."""
        self.assertTrue(callable(getattr(self.page, "_set_output", None)))

    def test_has_clear_output(self):
        """_clear_output() existe y es callable."""
        self.assertTrue(callable(getattr(self.page, "_clear_output", None)))

    def test_has_update_test_panel(self):
        """_update_test_panel() existe y es callable."""
        self.assertTrue(callable(getattr(self.page, "_update_test_panel", None)))

    def test_has_on_cmd_selected(self):
        """_on_cmd_selected() existe y es callable."""
        self.assertTrue(callable(getattr(self.page, "_on_cmd_selected", None)))

    def test_has_section_label(self):
        """_section_label() existe y es callable."""
        self.assertTrue(callable(getattr(self.page, "_section_label", None)))


# ══════════════════════════════════════════════════════════════════════════
# Grupo 6: Integración con SkillRegistry
# ══════════════════════════════════════════════════════════════════════════

class TestSkillsPageRegistryIntegration(unittest.TestCase):
    """
    Verifica la integración con el SkillRegistry real de Fase 11.
    Usa un registry aislado (no el singleton global) para evitar
    interferencia entre tests.
    """

    def setUp(self):
        # Registry aislado para cada test
        self.registry = SkillRegistry()
        self.skill = DemoSkill()
        self.registry.register(self.skill)

    def tearDown(self):
        self.registry.reset()

    def test_registry_has_demo_skill(self):
        """El registry contiene DemoSkill después de registrarla."""
        self.assertIn("demo_skill", self.registry)

    def test_entry_is_enabled_by_default(self):
        """DemoSkill está habilitada por defecto."""
        entry = self.registry.get_entry("demo_skill")
        self.assertTrue(entry.enabled)

    def test_list_all_returns_entries(self):
        """list_all() retorna al menos una entrada."""
        entries = self.registry.list_all()
        self.assertGreater(len(entries), 0)

    def test_entry_has_skill_and_enabled(self):
        """Cada SkillEntry tiene atributos skill y enabled."""
        entry = self.registry.get_entry("demo_skill")
        self.assertIsNotNone(entry.skill)
        self.assertIsInstance(entry.enabled, bool)

    def test_disable_updates_entry(self):
        """disable() marca la skill como no habilitada."""
        self.registry.disable("demo_skill")
        entry = self.registry.get_entry("demo_skill")
        self.assertFalse(entry.enabled)

    def test_enable_updates_entry(self):
        """enable() habilita una skill previamente deshabilitada."""
        self.registry.disable("demo_skill")
        self.registry.enable("demo_skill")
        entry = self.registry.get_entry("demo_skill")
        self.assertTrue(entry.enabled)

    def test_execute_hola_returns_success(self):
        """execute('hola') retorna SkillResult exitoso."""
        result = self.registry.execute("demo_skill", "hola", [])
        self.assertTrue(result.success)
        self.assertIn("Hola", result.output)

    def test_execute_eco_with_args(self):
        """execute('eco', ['Prueba']) retorna el texto."""
        result = self.registry.execute("demo_skill", "eco", ["Prueba"])
        self.assertTrue(result.success)
        self.assertIn("Prueba", result.output)

    def test_execute_disabled_returns_error(self):
        """execute en skill deshabilitada retorna SkillResult con error."""
        self.registry.disable("demo_skill")
        result = self.registry.execute("demo_skill", "hola", [])
        self.assertFalse(result.success)

    def test_meta_commands_list(self):
        """DemoSkill.META.commands contiene los 7 comandos."""
        meta = self.skill.META
        self.assertEqual(len(meta.commands), 7)
        self.assertIn("demo", meta.commands)
        self.assertIn("hola", meta.commands)
        self.assertIn("eco", meta.commands)


# ══════════════════════════════════════════════════════════════════════════
# Grupo 7: Lógica de render_list
# ══════════════════════════════════════════════════════════════════════════

class TestSkillsPageRenderList(unittest.TestCase):
    """Verifica la lógica de _render_list sin depender de widgets reales."""

    def setUp(self):
        self.page = _make_page()
        # Mockear widgets internos que se usan en _render_list
        self.page._list_frame = MagicMock()
        self.page._list_frame.winfo_children = MagicMock(return_value=[])
        self.page._count_label = MagicMock()
        self.page._refresh_btn = MagicMock()
        self.page._empty_label = MagicMock()
        self.page._cards = {}

    def test_render_empty_list(self):
        """_render_list con lista vacía no lanza excepciones."""
        # Con lista vacía, debe mostrar el empty_label
        with patch.object(self.page, "_select_skill") as mock_sel:
            self.page._render_list([])
            mock_sel.assert_not_called()

    def test_render_nonempty_list(self):
        """_render_list con una entrada llama a _select_skill."""
        entry = _make_entry()
        with patch.object(self.page, "_select_skill") as mock_sel:
            self.page._render_list([entry])
            mock_sel.assert_called_once()

    def test_render_updates_count_label(self):
        """_render_list actualiza el count_label con información correcta."""
        entry = _make_entry()
        with patch.object(self.page, "_select_skill"):
            self.page._render_list([entry])
        # El count_label debe haber sido configurado
        self.page._count_label.configure.assert_called()

    def test_render_refresh_btn_restored(self):
        """_render_list restaura el botón de refresh al terminar."""
        entry = _make_entry()
        with patch.object(self.page, "_select_skill"):
            self.page._render_list([entry])
        self.page._refresh_btn.configure.assert_called()


# ══════════════════════════════════════════════════════════════════════════
# Grupo 8: Lógica de toggle y ejecución
# ══════════════════════════════════════════════════════════════════════════

class TestSkillsPageToggleAndExec(unittest.TestCase):
    """Verifica la lógica de habilitación/deshabilitación y ejecución."""

    def setUp(self):
        self.page = _make_page()
        # Mock del botón toggle
        self.page._toggle_btn = MagicMock()
        self.page._exec_btn = MagicMock()
        self.page._result_label = MagicMock()
        self.page._output_box = MagicMock()
        self.page._args_entry = MagicMock()
        self.page._args_entry.get = MagicMock(return_value="")
        self.page._cmd_var = MagicMock()
        self.page._cmd_var.get = MagicMock(return_value="hola")

    def test_toggle_selected_with_no_selection_is_noop(self):
        """_toggle_selected sin selección no lanza excepciones."""
        self.page._selected_entry = None
        try:
            self.page._toggle_selected()
        except Exception as e:
            self.fail(f"_toggle_selected lanzó excepción: {e}")

    def test_on_exec_done_with_success_result(self):
        """_on_exec_done con resultado exitoso actualiza la UI correctamente."""
        result = SkillResult(success=True, output="OK output")
        try:
            self.page._on_exec_done(result, command="hola")
        except Exception as e:
            self.fail(f"_on_exec_done lanzó excepción: {e}")

    def test_on_exec_done_with_failure_result(self):
        """_on_exec_done con resultado fallido no lanza excepciones."""
        result = SkillResult(success=False, error="Error de prueba")
        try:
            self.page._on_exec_done(result, command="eco")
        except Exception as e:
            self.fail(f"_on_exec_done lanzó excepción: {e}")

    def test_on_exec_done_with_none_result(self):
        """_on_exec_done con result=None (error de excepción) no lanza."""
        try:
            self.page._on_exec_done(None, error="Excepción", command="test")
        except Exception as e:
            self.fail(f"_on_exec_done lanzó excepción: {e}")

    def test_run_command_without_selection_is_noop(self):
        """_run_command sin skill seleccionada no lanza excepciones."""
        self.page._selected_entry = None
        try:
            self.page._run_command()
        except Exception as e:
            self.fail(f"_run_command lanzó excepción: {e}")

    def test_run_command_with_empty_command_shows_warning(self):
        """_run_command con comando vacío muestra advertencia."""
        self.page._selected_entry = _make_entry()
        self.page._cmd_var.get = MagicMock(return_value="—")
        with patch.object(self.page, "_set_output") as mock_out:
            self.page._run_command()
            mock_out.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════
# Grupo 9: Hints de comandos
# ══════════════════════════════════════════════════════════════════════════

class TestSkillsPageCommandHints(unittest.TestCase):
    """Verifica los hints de argumentos para cada comando de DemoSkill."""

    def setUp(self):
        self.page = _make_page()
        self.page._args_hint = MagicMock()

    def test_hint_demo(self):
        """_on_cmd_selected('demo') actualiza el hint."""
        self.page._on_cmd_selected("demo")
        self.page._args_hint.configure.assert_called_once()

    def test_hint_hola_mentions_optional(self):
        """_on_cmd_selected('hola') menciona argumentos opcionales."""
        self.page._on_cmd_selected("hola")
        call_kwargs = self.page._args_hint.configure.call_args[1]
        self.assertIn("text", call_kwargs)
        self.assertIn("opcional", call_kwargs["text"].lower())

    def test_hint_eco_mentions_required(self):
        """_on_cmd_selected('eco') menciona argumentos requeridos."""
        self.page._on_cmd_selected("eco")
        call_kwargs = self.page._args_hint.configure.call_args[1]
        self.assertIn("text", call_kwargs)
        self.assertIn("requeri", call_kwargs["text"].lower())

    def test_hint_unknown_cmd_is_generic(self):
        """_on_cmd_selected con comando desconocido retorna hint genérico."""
        self.page._on_cmd_selected("comando_inexistente")
        self.page._args_hint.configure.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════
# Punto de entrada
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)

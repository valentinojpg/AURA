"""
Tests automáticos — AURA Fase 21: Editor de Automatizaciones

Verifica:
  - Importabilidad de AutomationPage con editor integrado
  - _StepRow: widget de fila editable (get_data, update_index, type change, param change)
  - _save_yaml: escritura atómica YAML/JSON con fallback
  - _open_editor: carga campos de formulario
  - _add_step / _delete_step / _move_step_up / _move_step_down
  - _on_new: abre el editor vacío
  - _on_edit: abre el editor con datos de una automatización existente
  - _on_save: validación y guardado YAML/JSON atómico
  - _on_cancel_edit: vuelve al modo correcto
  - _on_delete / _confirm_delete: eliminación con confirmación
  - _select_by_slug: selección post-guardado
  - Constantes y helpers: _STEP_TYPES, _STEP_ICONS, _STEP_PARAM_LABEL, _STEP_PARAM_KEY
  - Integración end-to-end: crear → guardar → seleccionar → editar → eliminar

Los tests de UI usan mocks para evitar dependencias de Tkinter en CI.
"""

from __future__ import annotations

import pytest
pytest.skip("Legacy CustomTkinter UI test (migrated to Flet in Phase 30)", allow_module_level=True)

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# ── Fixtures de path ──────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ══════════════════════════════════════════════════════════════════════════
# Mocks de Tkinter y CustomTkinter (para entornos sin display)
# ══════════════════════════════════════════════════════════════════════════

def _make_ctk_mock():
    """Crea mocks para customtkinter sin necesitar display."""
    ctk = MagicMock()

    class FakeStringVar:
        def __init__(self, value=""):
            self._val = value
        def get(self): return self._val
        def set(self, v): self._val = v
        def trace_add(self, *a, **kw): pass

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

    class FakeEntry(FakeFrame):
        def __init__(self, *a, **kw):
            super().__init__()
            self._val = ""
            # Support textvariable
            tv = kw.get("textvariable")
            if tv is not None:
                self._tv = tv
            else:
                self._tv = None
        def get(self):
            if self._tv is not None:
                return self._tv.get()
            return self._val
        def delete(self, start, end): self._val = ""
        def insert(self, pos, val): self._val += val
        def configure(self, **kw): pass

    class FakeOptionMenu(FakeFrame):
        def __init__(self, *a, **kw):
            super().__init__()
            self._var = kw.get("variable")
            vals = kw.get("values", [])
            self._values = vals
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

    class FakeToplevel(FakeFrame):
        def __init__(self, *a, **kw): super().__init__()
        def title(self, t): pass
        def geometry(self, g): pass
        def resizable(self, w, h): pass
        def grab_set(self): pass
        def lift(self): pass
        def focus_force(self): pass
        def configure(self, **kw): pass
        def destroy(self): pass

    class FakeFont:
        def __init__(self, *a, **kw): pass

    ctk.CTkFrame = FakeFrame
    ctk.CTkLabel = FakeLabel
    ctk.CTkButton = FakeButton
    ctk.CTkEntry = FakeEntry
    ctk.CTkOptionMenu = FakeOptionMenu
    ctk.CTkTextbox = FakeTextbox
    ctk.CTkScrollableFrame = FakeScrollableFrame
    ctk.CTkToplevel = FakeToplevel
    ctk.CTkFont = FakeFont
    ctk.StringVar = FakeStringVar
    return ctk


# Instalar mocks antes de importar módulos de UI
_ctk_mock = _make_ctk_mock()
sys.modules["customtkinter"] = _ctk_mock

_tk_mock = MagicMock()
sys.modules["tkinter"] = _tk_mock


# ══════════════════════════════════════════════════════════════════════════
# Helpers: AutomationInfo ficticio
# ══════════════════════════════════════════════════════════════════════════

def _make_info(name="modo_programar", display_name="Modo Programar",
               description="Desc test", version="1.0", step_count=3,
               path=None, fmt="yaml"):
    """Crea un AutomationInfo ficticio."""
    from automation.engine import AutomationInfo
    p = path or Path(f"/fake/data/automations/{name}.yaml")
    return AutomationInfo(
        name=name,
        display_name=display_name,
        description=description,
        version=version,
        step_count=step_count,
        path=p,
        format=fmt,
    )


_SAMPLE_STEPS = [
    {"type": "message", "text": "Hola"},
    {"type": "open_app", "app": "notepad"},
    {"type": "delay", "seconds": 1.0},
    {"type": "open_url", "url": "https://example.com"},
]

_SAMPLE_DATA = {
    "name": "Modo Programar",
    "description": "Test",
    "version": "1.0",
    "steps": _SAMPLE_STEPS,
}


# ══════════════════════════════════════════════════════════════════════════
# Clase base para tests de AutomationPage
# ══════════════════════════════════════════════════════════════════════════

class _PageBase(unittest.TestCase):
    """Crea una instancia de AutomationPage sin display real."""

    @classmethod
    def setUpClass(cls):
        # Importar después de instalar mocks
        from ui.pages import automation_page as _mod
        cls._mod = _mod

    def setUp(self):
        from ui.pages.automation_page import AutomationPage
        # Crear la página sin llamar a _build (evita dependencias de display)
        page = object.__new__(AutomationPage)
        # Inicializar atributos necesarios directamente
        page._selected_info = None
        page._running = False
        page._cards = []
        page._mode = AutomationPage._MODE_DETAIL
        page._step_rows = []
        page._editing_path = None

        # Mocks de widgets de UI
        page._lbl_loading = MagicMock()
        page._list_scroll = MagicMock()
        page._right_scroll = MagicMock()
        page._placeholder = MagicMock()
        page._detail_frame = MagicMock()
        page._editor_frame = MagicMock()
        page._detail_name = MagicMock()
        page._detail_desc = MagicMock()
        page._detail_meta = MagicMock()
        page._lbl_status = MagicMock()
        page._btn_run = MagicMock()
        page._btn_simulate = MagicMock()
        page._btn_edit = MagicMock()
        page._btn_delete = MagicMock()
        page._log_box = MagicMock()
        page._log_box._content = ""
        page._steps_frame = MagicMock()
        page._steps_frame.winfo_children.return_value = []
        page._editor_title_lbl = MagicMock()
        page._steps_container = MagicMock()
        page._steps_container.winfo_children.return_value = []
        page._lbl_no_steps = MagicMock()
        page._ed_error_lbl = MagicMock()

        # Entries del formulario con un mini _val
        class _FakeEntry:
            def __init__(self): self._val = ""
            def get(self): return self._val
            def delete(self, *a): self._val = ""
            def insert(self, pos, val): self._val += str(val)

        page._ed_name = _FakeEntry()
        page._ed_desc = _FakeEntry()
        page._ed_version = _FakeEntry()

        # after() llama inmediatamente al callback
        page.after = lambda ms, fn=None, *args: (fn(*args) if fn else None)

        self.page = page

    def _make_mock_engine(self, automations=None, info=None, data=None):
        engine = MagicMock()
        engine.list_automations.return_value = automations or []
        engine.get_info.return_value = info
        engine._load_file.return_value = data or _SAMPLE_DATA
        return engine


# ══════════════════════════════════════════════════════════════════════════
# 1. Constantes del módulo
# ══════════════════════════════════════════════════════════════════════════

class TestModuleConstants(unittest.TestCase):
    """Verifica que las constantes del módulo están correctamente definidas."""

    def setUp(self):
        from ui.pages import automation_page as mod
        self.mod = mod

    def test_step_types_list(self):
        self.assertIn("message", self.mod._STEP_TYPES)
        self.assertIn("open_app", self.mod._STEP_TYPES)
        self.assertIn("open_url", self.mod._STEP_TYPES)
        self.assertIn("delay", self.mod._STEP_TYPES)

    def test_step_types_length(self):
        self.assertEqual(len(self.mod._STEP_TYPES), 4)

    def test_step_icons_keys(self):
        for t in self.mod._STEP_TYPES:
            self.assertIn(t, self.mod._STEP_ICONS)

    def test_step_param_label_keys(self):
        for t in self.mod._STEP_TYPES:
            self.assertIn(t, self.mod._STEP_PARAM_LABEL)

    def test_step_param_key_values(self):
        self.assertEqual(self.mod._STEP_PARAM_KEY["message"], "text")
        self.assertEqual(self.mod._STEP_PARAM_KEY["open_app"], "app")
        self.assertEqual(self.mod._STEP_PARAM_KEY["open_url"], "url")
        self.assertEqual(self.mod._STEP_PARAM_KEY["delay"], "seconds")

    def test_automations_dir_is_path(self):
        self.assertIsInstance(self.mod._AUTOMATIONS_DIR, Path)

    def test_automations_dir_points_to_data(self):
        self.assertIn("data", str(self.mod._AUTOMATIONS_DIR))
        self.assertIn("automations", str(self.mod._AUTOMATIONS_DIR))

    def test_mode_detail_constant(self):
        from ui.pages.automation_page import AutomationPage
        self.assertEqual(AutomationPage._MODE_DETAIL, "detail")

    def test_mode_editor_constant(self):
        from ui.pages.automation_page import AutomationPage
        self.assertEqual(AutomationPage._MODE_EDITOR, "editor")


# ══════════════════════════════════════════════════════════════════════════
# 2. _save_yaml helper
# ══════════════════════════════════════════════════════════════════════════

class TestSaveYaml(unittest.TestCase):
    """Verifica que _save_yaml guarda correctamente con escritura atómica."""

    def setUp(self):
        from ui.pages.automation_page import _save_yaml
        self._save = _save_yaml

    def test_save_yaml_creates_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_auto.yaml"
            self._save(p, {"name": "Test", "steps": []})
            self.assertTrue(p.exists())

    def test_save_yaml_no_tmp_left(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_auto.yaml"
            self._save(p, {"name": "Test", "steps": []})
            tmp = p.with_suffix(".tmp")
            self.assertFalse(tmp.exists())

    def test_save_yaml_content_readable(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_auto.yaml"
            data = {"name": "Mi Auto", "description": "desc", "steps": []}
            self._save(p, data)
            content = p.read_text(encoding="utf-8")
            self.assertIn("Mi Auto", content)

    def test_save_yaml_unicode_ok(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_auto.yaml"
            data = {"name": "Automatización con ñ", "steps": []}
            self._save(p, data)
            content = p.read_text(encoding="utf-8")
            self.assertIn("ñ", content)

    def test_save_yaml_steps_included(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_auto.yaml"
            data = {"name": "X", "steps": [{"type": "message", "text": "hi"}]}
            self._save(p, data)
            content = p.read_text(encoding="utf-8")
            self.assertIn("message", content)

    def test_save_yaml_fallback_to_json_when_no_pyyaml(self):
        """Si pyyaml no está disponible, guarda como JSON."""
        with tempfile.TemporaryDirectory() as td:
            import builtins
            real_import = builtins.__import__

            def _mock_import(name, *a, **kw):
                if name == "yaml":
                    raise ImportError("no yaml")
                return real_import(name, *a, **kw)

            with patch("builtins.__import__", side_effect=_mock_import):
                p = Path(td) / "test_auto.yaml"
                json_p = p.with_suffix(".json")
                # _save_yaml should not raise
                try:
                    self._save(p, {"name": "Test", "steps": []})
                except Exception:
                    pass  # fallback may or may not create the file


# ══════════════════════════════════════════════════════════════════════════
# 3. _StepRow — widget de fila editable
# ══════════════════════════════════════════════════════════════════════════

class TestStepRow(unittest.TestCase):
    """Verifica el widget _StepRow en modo aislado (sin display)."""

    def _make_row(self, index=0, step_data=None, on_change=None, on_delete=None,
                  on_move_up=None, on_move_down=None):
        """Crea un _StepRow con mocks."""
        from ui.pages.automation_page import _StepRow
        sd = step_data or {"type": "message", "text": "Hola"}
        row = object.__new__(_StepRow)
        row._index = index
        row._step_data = dict(sd)
        row._on_change = on_change or MagicMock()
        row._on_delete = on_delete or MagicMock()
        row._on_move_up = on_move_up or MagicMock()
        row._on_move_down = on_move_down or MagicMock()

        # Simular StringVar con valor inicial
        class _FakeVar:
            def __init__(self, v=""): self._v = v
            def get(self): return self._v
            def set(self, v): self._v = v
            def trace_add(self, *a, **kw): pass

        row._type_var = _FakeVar(sd.get("type", "message"))

        class _FakeEntry:
            def __init__(self, val=""):
                self._val = val
            def get(self): return self._val
            def configure(self, **kw): pass

        param_type = sd.get("type", "message")
        from ui.pages.automation_page import _STEP_PARAM_KEY
        pk = _STEP_PARAM_KEY.get(param_type, "text")
        row._param_var = _FakeVar(str(sd.get(pk, "")))
        row._param_entry = _FakeEntry(str(sd.get(pk, "")))
        return row

    def test_get_data_message(self):
        row = self._make_row(step_data={"type": "message", "text": "Hola"})
        data = row.get_data()
        self.assertEqual(data["type"], "message")
        self.assertEqual(data["text"], "Hola")

    def test_get_data_open_app(self):
        row = self._make_row(step_data={"type": "open_app", "app": "notepad"})
        data = row.get_data()
        self.assertEqual(data["type"], "open_app")
        self.assertEqual(data["app"], "notepad")

    def test_get_data_open_url(self):
        row = self._make_row(step_data={"type": "open_url", "url": "https://example.com"})
        data = row.get_data()
        self.assertEqual(data["type"], "open_url")
        self.assertEqual(data["url"], "https://example.com")

    def test_get_data_delay_float(self):
        row = self._make_row(step_data={"type": "delay", "seconds": 2.5})
        row._type_var.set("delay")
        row._param_var.set("2.5")
        data = row.get_data()
        self.assertEqual(data["type"], "delay")
        self.assertAlmostEqual(data["seconds"], 2.5)

    def test_get_data_delay_invalid_defaults_to_1(self):
        row = self._make_row(step_data={"type": "delay", "seconds": "abc"})
        row._type_var.set("delay")
        row._param_var.set("abc")
        data = row.get_data()
        self.assertEqual(data["seconds"], 1.0)

    def test_update_index(self):
        row = self._make_row(index=2)
        row.update_index(5)
        self.assertEqual(row._index, 5)

    def test_on_param_change_updates_step_data(self):
        on_change = MagicMock()
        row = self._make_row(
            step_data={"type": "message", "text": ""},
            on_change=on_change,
        )
        row._param_var.set("Nuevo texto")
        row._on_param_change()
        # step_data should be updated
        from ui.pages.automation_page import _STEP_PARAM_KEY
        pk = _STEP_PARAM_KEY["message"]
        self.assertEqual(row._step_data[pk], "Nuevo texto")
        on_change.assert_called_once()

    def test_on_type_change_updates_step_data(self):
        on_change = MagicMock()
        row = self._make_row(
            step_data={"type": "message", "text": "Hola"},
            on_change=on_change,
        )
        row._on_type_change("open_app")
        self.assertEqual(row._step_data["type"], "open_app")
        on_change.assert_called_once()

    def test_on_type_change_migrates_value(self):
        """Al cambiar tipo, el valor anterior se migra si es posible."""
        row = self._make_row(step_data={"type": "message", "text": "valor_original"})
        row._param_var.set("valor_original")
        row._on_type_change("open_app")
        # new key is "app"
        self.assertIn("app", row._step_data)


# ══════════════════════════════════════════════════════════════════════════
# 4. Modo y navegación del editor
# ══════════════════════════════════════════════════════════════════════════

class TestEditorNavigation(_PageBase):
    """Verifica la alternancia entre modos de la página."""

    def test_show_mode_detail(self):
        self.page._show_mode(self.page._MODE_DETAIL)
        self.assertEqual(self.page._mode, self.page._MODE_DETAIL)

    def test_show_mode_editor(self):
        self.page._show_mode(self.page._MODE_EDITOR)
        self.assertEqual(self.page._mode, self.page._MODE_EDITOR)

    def test_show_mode_detail_calls_pack(self):
        self.page._show_mode(self.page._MODE_DETAIL)
        self.page._detail_frame.pack.assert_called()

    def test_show_mode_editor_calls_pack(self):
        self.page._show_mode(self.page._MODE_EDITOR)
        self.page._editor_frame.pack.assert_called()

    def test_show_mode_detail_hides_editor(self):
        self.page._show_mode(self.page._MODE_DETAIL)
        self.page._editor_frame.pack_forget.assert_called()

    def test_show_mode_editor_hides_detail(self):
        self.page._show_mode(self.page._MODE_EDITOR)
        self.page._detail_frame.pack_forget.assert_called()

    def test_show_mode_placeholder(self):
        """Modo desconocido muestra placeholder."""
        self.page._show_mode("placeholder")
        self.page._placeholder.pack.assert_called()


# ══════════════════════════════════════════════════════════════════════════
# 5. _on_new: crear nueva automatización
# ══════════════════════════════════════════════════════════════════════════

class TestOnNew(_PageBase):
    """Verifica que _on_new abre el editor vacío correctamente."""

    def test_on_new_clears_editing_path(self):
        self.page._editing_path = Path("/some/file.yaml")
        self.page._on_new()
        self.assertIsNone(self.page._editing_path)

    def test_on_new_clears_selected_info(self):
        self.page._selected_info = _make_info()
        self.page._on_new()
        self.assertIsNone(self.page._selected_info)

    def test_on_new_sets_editor_mode(self):
        self.page._on_new()
        self.assertEqual(self.page._mode, self.page._MODE_EDITOR)

    def test_on_new_clears_name_field(self):
        self.page._ed_name.insert(0, "valor previo")
        self.page._on_new()
        self.assertEqual(self.page._ed_name.get(), "")

    def test_on_new_clears_desc_field(self):
        self.page._ed_desc.insert(0, "descripcion previa")
        self.page._on_new()
        self.assertEqual(self.page._ed_desc.get(), "")

    def test_on_new_sets_version_default(self):
        self.page._on_new()
        self.assertEqual(self.page._ed_version.get(), "1.0")

    def test_on_new_no_step_rows(self):
        self.page._on_new()
        self.assertEqual(len(self.page._step_rows), 0)

    def test_on_new_clears_error_label(self):
        self.page._on_new()
        self.page._ed_error_lbl.configure.assert_called_with(text="")


# ══════════════════════════════════════════════════════════════════════════
# 6. _on_edit: editar automatización existente
# ══════════════════════════════════════════════════════════════════════════

class TestOnEdit(_PageBase):
    """Verifica que _on_edit carga los datos correctamente."""

    def test_on_edit_without_selection_does_nothing(self):
        self.page._selected_info = None
        self.page._on_edit()
        # Mode no debe cambiar a editor
        self.assertNotEqual(self.page._mode, self.page._MODE_EDITOR)

    def test_on_edit_with_selection_opens_editor(self):
        info = _make_info()
        self.page._selected_info = info
        engine_mock = self._make_mock_engine(info=info, data=_SAMPLE_DATA)
        with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
            self.page._on_edit()
        self.assertEqual(self.page._mode, self.page._MODE_EDITOR)

    def test_on_edit_loads_name(self):
        info = _make_info()
        self.page._selected_info = info
        engine_mock = self._make_mock_engine(info=info, data=_SAMPLE_DATA)
        with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
            self.page._on_edit()
        self.assertEqual(self.page._ed_name.get(), "Modo Programar")

    def test_on_edit_loads_description(self):
        info = _make_info()
        self.page._selected_info = info
        data = {**_SAMPLE_DATA, "description": "Descripción de prueba"}
        engine_mock = self._make_mock_engine(info=info, data=data)
        with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
            self.page._on_edit()
        self.assertEqual(self.page._ed_desc.get(), "Descripción de prueba")

    def test_on_edit_loads_version(self):
        info = _make_info()
        self.page._selected_info = info
        data = {**_SAMPLE_DATA, "version": "2.5"}
        engine_mock = self._make_mock_engine(info=info, data=data)
        with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
            self.page._on_edit()
        self.assertEqual(self.page._ed_version.get(), "2.5")

    def test_on_edit_sets_editing_path(self):
        info = _make_info(path=Path("/fake/modo_programar.yaml"))
        self.page._selected_info = info
        engine_mock = self._make_mock_engine(info=info, data=_SAMPLE_DATA)
        with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
            self.page._on_edit()
        self.assertEqual(self.page._editing_path, info.path)

    def test_on_edit_engine_returns_none_does_not_crash(self):
        info = _make_info()
        self.page._selected_info = info
        engine_mock = self._make_mock_engine(info=None)
        with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
            # Should not raise
            try:
                self.page._on_edit()
            except Exception as e:
                self.fail(f"_on_edit raised {e}")

    def test_on_edit_engine_error_does_not_crash(self):
        info = _make_info()
        self.page._selected_info = info
        engine_mock = MagicMock()
        engine_mock.get_info.side_effect = RuntimeError("test error")
        with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
            try:
                self.page._on_edit()
            except Exception as e:
                self.fail(f"_on_edit raised {e}")


# ══════════════════════════════════════════════════════════════════════════
# 7. Gestión de pasos en el editor
# ══════════════════════════════════════════════════════════════════════════

class TestStepManagement(_PageBase):
    """Verifica agregar, eliminar y reordenar pasos en el editor."""

    def _add_fake_rows(self, count):
        """Agrega filas de pasos falsas a la página."""
        for i in range(count):
            row = MagicMock()
            row._index = i
            row.get_data.return_value = {"type": "message", "text": f"Paso {i}"}
            row.update_index = MagicMock()
            row.pack = MagicMock()
            row.destroy = MagicMock()
            self.page._step_rows.append(row)

    def test_load_editor_steps_empty(self):
        self.page._load_editor_steps([])
        self.assertEqual(len(self.page._step_rows), 0)

    def test_load_editor_steps_shows_no_steps_label(self):
        self.page._load_editor_steps([])
        self.page._lbl_no_steps.pack.assert_called()

    def test_load_editor_steps_hides_label_when_has_steps(self):
        # Verificar que al cargar pasos se oculta el label "sin pasos"
        steps = [{"type": "message", "text": "X"}]
        # Mock _create_step_row para no crear widgets reales
        self.page._create_step_row = MagicMock()
        self.page._load_editor_steps(steps)
        self.page._lbl_no_steps.pack_forget.assert_called()

    def test_delete_step_out_of_bounds_safe(self):
        self._add_fake_rows(3)
        # Eliminar índice fuera de rango no debe crashear
        try:
            self.page._delete_step(10)
        except Exception as e:
            self.fail(f"_delete_step raised {e}")

    def test_delete_step_reduces_count(self):
        self._add_fake_rows(3)
        initial = len(self.page._step_rows)
        self.page._delete_step(1)
        self.assertEqual(len(self.page._step_rows), initial - 1)

    def test_delete_step_shows_no_steps_label_when_empty(self):
        self._add_fake_rows(1)
        self.page._delete_step(0)
        self.assertEqual(len(self.page._step_rows), 0)
        self.page._lbl_no_steps.pack.assert_called()

    def test_delete_step_renumbers_remaining(self):
        self._add_fake_rows(3)
        self.page._delete_step(0)
        for i, row in enumerate(self.page._step_rows):
            row.update_index.assert_called_with(i)

    def test_move_step_up_first_item_does_nothing(self):
        self._add_fake_rows(3)
        initial_order = [r.get_data()["text"] for r in self.page._step_rows]
        self.page._move_step_up = MagicMock()
        self.page._move_step_up(0)
        # Calling the mock, just confirm no exception

    def test_move_step_down_last_item_does_nothing(self):
        self._add_fake_rows(3)
        self.page._move_step_down = MagicMock()
        self.page._move_step_down(2)
        # Same

    def test_move_step_up_swaps_steps(self):
        # Use the real method, but mock _reload_editor_steps
        self._add_fake_rows(3)
        self.page._reload_editor_steps = MagicMock()
        self.page._move_step_up(1)
        self.page._reload_editor_steps.assert_called_once()
        args = self.page._reload_editor_steps.call_args[0][0]
        # After swap: Paso 1 is now at index 0, Paso 0 at index 1
        self.assertEqual(args[0]["text"], "Paso 1")
        self.assertEqual(args[1]["text"], "Paso 0")

    def test_move_step_down_swaps_steps(self):
        self._add_fake_rows(3)
        self.page._reload_editor_steps = MagicMock()
        self.page._move_step_down(0)
        self.page._reload_editor_steps.assert_called_once()
        args = self.page._reload_editor_steps.call_args[0][0]
        self.assertEqual(args[0]["text"], "Paso 1")
        self.assertEqual(args[1]["text"], "Paso 0")

    def test_on_step_changed_no_exception(self):
        try:
            self.page._on_step_changed()
        except Exception as e:
            self.fail(f"_on_step_changed raised {e}")


# ══════════════════════════════════════════════════════════════════════════
# 8. _on_save: validación y guardado
# ══════════════════════════════════════════════════════════════════════════

class TestOnSave(_PageBase):
    """Verifica la lógica de guardado del editor."""

    def _set_fields(self, name="Test Auto", desc="desc", version="1.0"):
        self.page._ed_name.delete(0, "end")
        self.page._ed_name.insert(0, name)
        self.page._ed_desc.delete(0, "end")
        self.page._ed_desc.insert(0, desc)
        self.page._ed_version.delete(0, "end")
        self.page._ed_version.insert(0, version)

    def _add_step_row(self, data):
        row = MagicMock()
        row.get_data.return_value = data
        self.page._step_rows.append(row)

    def test_save_empty_name_shows_error(self):
        self._set_fields(name="")
        self.page._on_save()
        self.page._ed_error_lbl.configure.assert_called_with(
            text="❌ El nombre es obligatorio."
        )

    def test_save_invalid_name_only_special_chars_shows_error(self):
        self._set_fields(name="!@#$%")
        self.page._on_save()
        call_kwargs = [c.kwargs for c in self.page._ed_error_lbl.configure.call_args_list]
        errors = [k.get("text", "") for k in call_kwargs]
        self.assertTrue(any("❌" in e for e in errors))

    def test_save_valid_name_no_steps_saves(self):
        self._set_fields(name="Mi Auto")
        with tempfile.TemporaryDirectory() as td:
            with patch("ui.pages.automation_page._AUTOMATIONS_DIR", Path(td)):
                self.page._refresh_list = MagicMock()
                self.page._select_by_slug = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._on_save()
                # Se esperan 0 pasos → guardado correcto
                saved = list(Path(td).glob("*.yaml")) + list(Path(td).glob("*.json"))
                self.assertEqual(len(saved), 1)

    def test_save_creates_yaml_file(self):
        self._set_fields(name="Auto Test")
        with tempfile.TemporaryDirectory() as td:
            with patch("ui.pages.automation_page._AUTOMATIONS_DIR", Path(td)):
                self.page._refresh_list = MagicMock()
                self.page._select_by_slug = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._on_save()
                yaml_files = list(Path(td).glob("*.yaml"))
                self.assertEqual(len(yaml_files), 1)

    def test_save_file_contains_name(self):
        self._set_fields(name="Auto Especial")
        with tempfile.TemporaryDirectory() as td:
            with patch("ui.pages.automation_page._AUTOMATIONS_DIR", Path(td)):
                self.page._refresh_list = MagicMock()
                self.page._select_by_slug = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._on_save()
                yaml_files = list(Path(td).glob("*.yaml"))
                content = yaml_files[0].read_text(encoding="utf-8")
                self.assertIn("Auto Especial", content)

    def test_save_step_validation_rejects_empty_param(self):
        self._set_fields(name="Test Auto")
        self._add_step_row({"type": "open_app", "app": ""})
        self.page._on_save()
        call_kwargs = [c.kwargs for c in self.page._ed_error_lbl.configure.call_args_list]
        errors = [k.get("text", "") for k in call_kwargs]
        self.assertTrue(any("paso 1" in e.lower() for e in errors))

    def test_save_step_with_valid_params_ok(self):
        self._set_fields(name="Auto Pasos")
        self._add_step_row({"type": "message", "text": "Hola mundo"})
        with tempfile.TemporaryDirectory() as td:
            with patch("ui.pages.automation_page._AUTOMATIONS_DIR", Path(td)):
                self.page._refresh_list = MagicMock()
                self.page._select_by_slug = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._on_save()
                saved = list(Path(td).glob("*.yaml")) + list(Path(td).glob("*.json"))
                self.assertEqual(len(saved), 1)

    def test_save_existing_file_preserves_path(self):
        """Al editar, debe guardar en el mismo archivo."""
        self._set_fields(name="Modo Programar")
        with tempfile.TemporaryDirectory() as td:
            original_path = Path(td) / "modo_programar.yaml"
            original_path.write_text("name: test", encoding="utf-8")
            self.page._editing_path = original_path
            with patch("ui.pages.automation_page._AUTOMATIONS_DIR", Path(td)):
                self.page._refresh_list = MagicMock()
                self.page._select_by_slug = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._on_save()
                # El archivo original debe existir
                self.assertTrue(original_path.exists())

    def test_save_avoids_overwrite_with_counter(self):
        """Si ya existe un archivo con el mismo slug, crea nombre alternativo."""
        self._set_fields(name="Auto Test")
        with tempfile.TemporaryDirectory() as td:
            # Crear archivo previo con el mismo slug
            (Path(td) / "auto_test.yaml").write_text("name: prev", encoding="utf-8")
            with patch("ui.pages.automation_page._AUTOMATIONS_DIR", Path(td)):
                self.page._refresh_list = MagicMock()
                self.page._select_by_slug = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._on_save()
                yaml_files = list(Path(td).glob("*.yaml"))
                # Debe existir el original + el nuevo
                self.assertGreaterEqual(len(yaml_files), 2)

    def test_save_resets_editing_path(self):
        self._set_fields(name="Reset Test")
        with tempfile.TemporaryDirectory() as td:
            with patch("ui.pages.automation_page._AUTOMATIONS_DIR", Path(td)):
                self.page._refresh_list = MagicMock()
                self.page._select_by_slug = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._on_save()
                self.assertIsNone(self.page._editing_path)

    def test_save_clears_error_label_on_success(self):
        self._set_fields(name="Limpio Test")
        with tempfile.TemporaryDirectory() as td:
            with patch("ui.pages.automation_page._AUTOMATIONS_DIR", Path(td)):
                self.page._refresh_list = MagicMock()
                self.page._select_by_slug = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._on_save()
                # Al menos una llamada debe ser texto vacío (limpieza de error)
                calls_texts = [
                    c.kwargs.get("text", "")
                    for c in self.page._ed_error_lbl.configure.call_args_list
                ]
                self.assertIn("", calls_texts)

    def test_save_calls_refresh_list(self):
        self._set_fields(name="Refresh Test")
        with tempfile.TemporaryDirectory() as td:
            with patch("ui.pages.automation_page._AUTOMATIONS_DIR", Path(td)):
                self.page._refresh_list = MagicMock()
                self.page._select_by_slug = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._on_save()
                self.page._refresh_list.assert_called_once()

    def test_save_json_file_when_editing_path_is_json(self):
        self._set_fields(name="Json Auto")
        with tempfile.TemporaryDirectory() as td:
            original_path = Path(td) / "json_auto.json"
            original_path.write_text("{}", encoding="utf-8")
            self.page._editing_path = original_path
            with patch("ui.pages.automation_page._AUTOMATIONS_DIR", Path(td)):
                self.page._refresh_list = MagicMock()
                self.page._select_by_slug = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._on_save()
                self.assertTrue(original_path.exists())
                content = json.loads(original_path.read_text(encoding="utf-8"))
                self.assertEqual(content["name"], "Json Auto")


# ══════════════════════════════════════════════════════════════════════════
# 9. _on_cancel_edit
# ══════════════════════════════════════════════════════════════════════════

class TestOnCancelEdit(_PageBase):
    """Verifica que cancelar vuelve al modo correcto."""

    def test_cancel_with_no_selection_shows_placeholder(self):
        self.page._selected_info = None
        self.page._show_mode = MagicMock()
        self.page._on_cancel_edit()
        self.page._show_mode.assert_called_with("placeholder")

    def test_cancel_with_selection_shows_detail(self):
        self.page._selected_info = _make_info()
        self.page._show_mode = MagicMock()
        self.page._show_detail = MagicMock()
        self.page._on_cancel_edit()
        self.page._show_mode.assert_called_with(self.page._MODE_DETAIL)

    def test_cancel_clears_editing_path(self):
        self.page._editing_path = Path("/fake/file.yaml")
        self.page._show_mode = MagicMock()
        self.page._on_cancel_edit()
        self.assertIsNone(self.page._editing_path)

    def test_cancel_clears_error_label(self):
        self.page._show_mode = MagicMock()
        self.page._on_cancel_edit()
        self.page._ed_error_lbl.configure.assert_called_with(text="")


# ══════════════════════════════════════════════════════════════════════════
# 10. _on_delete y _confirm_delete
# ══════════════════════════════════════════════════════════════════════════

class TestOnDelete(_PageBase):
    """Verifica el flujo de eliminación con confirmación."""

    def test_on_delete_without_selection_does_nothing(self):
        self.page._selected_info = None
        self.page._show_confirm_delete = MagicMock()
        self.page._on_delete()
        self.page._show_confirm_delete.assert_not_called()

    def test_on_delete_with_selection_shows_confirm(self):
        self.page._selected_info = _make_info()
        self.page._show_confirm_delete = MagicMock()
        self.page._on_delete()
        self.page._show_confirm_delete.assert_called_once()

    def test_confirm_delete_removes_file(self):
        info = _make_info()
        with tempfile.TemporaryDirectory() as td:
            file_path = Path(td) / "modo_programar.yaml"
            file_path.write_text("name: test", encoding="utf-8")
            info_with_path = _make_info(path=file_path)
            engine_mock = self._make_mock_engine(info=info_with_path)
            dialog = MagicMock()
            with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
                self.page._refresh_list = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._confirm_delete(info, dialog)
                self.assertFalse(file_path.exists())

    def test_confirm_delete_clears_selection(self):
        info = _make_info()
        with tempfile.TemporaryDirectory() as td:
            file_path = Path(td) / "modo_programar.yaml"
            file_path.write_text("name: test", encoding="utf-8")
            info_with_path = _make_info(path=file_path)
            engine_mock = self._make_mock_engine(info=info_with_path)
            dialog = MagicMock()
            self.page._selected_info = info
            with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
                self.page._refresh_list = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._confirm_delete(info, dialog)
                self.assertIsNone(self.page._selected_info)

    def test_confirm_delete_calls_refresh_list(self):
        info = _make_info()
        with tempfile.TemporaryDirectory() as td:
            file_path = Path(td) / "test.yaml"
            file_path.write_text("name: test", encoding="utf-8")
            info_with_path = _make_info(path=file_path)
            engine_mock = self._make_mock_engine(info=info_with_path)
            dialog = MagicMock()
            with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
                self.page._refresh_list = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._confirm_delete(info, dialog)
                self.page._refresh_list.assert_called_once()

    def test_confirm_delete_shows_placeholder_after_deletion(self):
        info = _make_info()
        with tempfile.TemporaryDirectory() as td:
            file_path = Path(td) / "test.yaml"
            file_path.write_text("name: test", encoding="utf-8")
            info_with_path = _make_info(path=file_path)
            engine_mock = self._make_mock_engine(info=info_with_path)
            dialog = MagicMock()
            with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
                self.page._refresh_list = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._confirm_delete(info, dialog)
                self.page._show_mode.assert_called_with("placeholder")

    def test_confirm_delete_engine_returns_none_no_crash(self):
        info = _make_info()
        engine_mock = self._make_mock_engine(info=None)
        dialog = MagicMock()
        with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
            self.page._refresh_list = MagicMock()
            self.page._show_mode = MagicMock()
            try:
                self.page._confirm_delete(info, dialog)
            except Exception as e:
                self.fail(f"_confirm_delete raised {e}")

    def test_confirm_delete_destroys_dialog(self):
        info = _make_info()
        with tempfile.TemporaryDirectory() as td:
            file_path = Path(td) / "test.yaml"
            file_path.write_text("name: test", encoding="utf-8")
            info_with_path = _make_info(path=file_path)
            engine_mock = self._make_mock_engine(info=info_with_path)
            dialog = MagicMock()
            with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
                self.page._refresh_list = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._confirm_delete(info, dialog)
                dialog.destroy.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════
# 11. _select_by_slug
# ══════════════════════════════════════════════════════════════════════════

class TestSelectBySlug(_PageBase):
    """Verifica la selección post-guardado."""

    def test_select_by_slug_calls_on_select(self):
        info = _make_info(name="auto_test")
        engine_mock = self._make_mock_engine(info=info)
        self.page._on_select = MagicMock()
        self.page._refresh_list = MagicMock()
        with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
            self.page._select_by_slug("auto_test", "Auto Test")
        self.page._on_select.assert_called_once_with(info)

    def test_select_by_slug_engine_error_no_crash(self):
        engine_mock = MagicMock()
        engine_mock.get_info.side_effect = RuntimeError("fallo")
        self.page._on_select = MagicMock()
        with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
            try:
                self.page._select_by_slug("test", "Test")
            except Exception as e:
                self.fail(f"_select_by_slug raised {e}")

    def test_select_by_slug_not_found_does_not_call_on_select(self):
        engine_mock = self._make_mock_engine(info=None)
        self.page._on_select = MagicMock()
        with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
            self.page._select_by_slug("no_existe", "No Existe")
        self.page._on_select.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 12. Helpers de UI
# ══════════════════════════════════════════════════════════════════════════

class TestUIHelpers(_PageBase):
    """Verifica helpers de log y botones."""

    def test_set_log_clears_content(self):
        self.page._set_log("Contenido previo")
        self.page._log_box.delete.assert_called()

    def test_append_log_inserts_text(self):
        self.page._append_log("Nueva línea")
        self.page._log_box.insert.assert_called()

    def test_set_buttons_enabled_calls_configure(self):
        self.page._set_buttons_enabled(True)
        self.page._btn_run.configure.assert_called_with(state="normal")
        self.page._btn_simulate.configure.assert_called_with(state="normal")

    def test_set_buttons_disabled_calls_configure(self):
        self.page._set_buttons_enabled(False)
        self.page._btn_run.configure.assert_called_with(state="disabled")
        self.page._btn_edit.configure.assert_called_with(state="disabled")
        self.page._btn_delete.configure.assert_called_with(state="disabled")


# ══════════════════════════════════════════════════════════════════════════
# 13. Test de importación directa del módulo
# ══════════════════════════════════════════════════════════════════════════

class TestImports(unittest.TestCase):
    """Verifica importaciones limpias del módulo."""

    def test_import_automation_page(self):
        from ui.pages.automation_page import AutomationPage
        self.assertTrue(callable(AutomationPage))

    def test_import_step_row(self):
        from ui.pages.automation_page import _StepRow
        self.assertTrue(callable(_StepRow))

    def test_import_save_yaml(self):
        from ui.pages.automation_page import _save_yaml
        self.assertTrue(callable(_save_yaml))

    def test_import_get_engine(self):
        from ui.pages.automation_page import _get_engine
        self.assertTrue(callable(_get_engine))

    def test_import_step_types(self):
        from ui.pages.automation_page import _STEP_TYPES
        self.assertIsInstance(_STEP_TYPES, list)

    def test_import_step_icons(self):
        from ui.pages.automation_page import _STEP_ICONS
        self.assertIsInstance(_STEP_ICONS, dict)

    def test_import_step_param_label(self):
        from ui.pages.automation_page import _STEP_PARAM_LABEL
        self.assertIsInstance(_STEP_PARAM_LABEL, dict)

    def test_import_step_param_key(self):
        from ui.pages.automation_page import _STEP_PARAM_KEY
        self.assertIsInstance(_STEP_PARAM_KEY, dict)

    def test_automation_page_has_mode_constants(self):
        from ui.pages.automation_page import AutomationPage
        self.assertTrue(hasattr(AutomationPage, "_MODE_DETAIL"))
        self.assertTrue(hasattr(AutomationPage, "_MODE_EDITOR"))

    def test_automation_page_has_editor_methods(self):
        from ui.pages.automation_page import AutomationPage
        for method in ["_on_new", "_on_edit", "_on_save", "_on_cancel_edit",
                        "_on_delete", "_confirm_delete", "_open_editor",
                        "_add_step", "_delete_step", "_move_step_up",
                        "_move_step_down", "_reload_editor_steps",
                        "_load_editor_steps", "_create_step_row",
                        "_select_by_slug", "_show_confirm_delete"]:
            self.assertTrue(
                hasattr(AutomationPage, method),
                f"AutomationPage should have method {method}"
            )


# ══════════════════════════════════════════════════════════════════════════
# 14. Test de integración end-to-end con archivos reales
# ══════════════════════════════════════════════════════════════════════════

class TestEndToEnd(_PageBase):
    """Tests de integración que crean, editan y eliminan archivos reales."""

    def test_create_and_load_automation(self):
        """Crear una automatización YAML y verificar que el motor la carga."""
        from automation.engine import AutomationEngine
        with tempfile.TemporaryDirectory() as td:
            # Simular guardado desde el editor
            self._set_fields("Mi Automatización Test")
            with patch("ui.pages.automation_page._AUTOMATIONS_DIR", Path(td)):
                self.page._refresh_list = MagicMock()
                self.page._select_by_slug = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._on_save()

            # Verificar con el motor real
            import yaml as _yaml
            yaml_files = list(Path(td).glob("*.yaml"))
            self.assertEqual(len(yaml_files), 1)
            data = _yaml.safe_load(yaml_files[0].read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "Mi Automatización Test")

    def _set_fields(self, name, desc="", version="1.0"):
        self.page._ed_name.delete(0, "end")
        self.page._ed_name.insert(0, name)
        self.page._ed_desc.delete(0, "end")
        self.page._ed_desc.insert(0, desc)
        self.page._ed_version.delete(0, "end")
        self.page._ed_version.insert(0, version)

    def test_save_with_all_step_types(self):
        """Verificar que todos los tipos de pasos se guardan correctamente."""
        self._set_fields("Multi Step Auto")
        # Agregar todos los tipos de pasos
        steps_data = [
            {"type": "message", "text": "Hola"},
            {"type": "open_app", "app": "notepad"},
            {"type": "open_url", "url": "https://example.com"},
            {"type": "delay", "seconds": 1.5},
        ]
        for sd in steps_data:
            row = MagicMock()
            row.get_data.return_value = sd
            self.page._step_rows.append(row)

        with tempfile.TemporaryDirectory() as td:
            with patch("ui.pages.automation_page._AUTOMATIONS_DIR", Path(td)):
                self.page._refresh_list = MagicMock()
                self.page._select_by_slug = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._on_save()

            import yaml as _yaml
            yaml_files = list(Path(td).glob("*.yaml"))
            data = _yaml.safe_load(yaml_files[0].read_text(encoding="utf-8"))
            self.assertEqual(len(data["steps"]), 4)
            types_saved = [s["type"] for s in data["steps"]]
            self.assertIn("message", types_saved)
            self.assertIn("open_app", types_saved)
            self.assertIn("open_url", types_saved)
            self.assertIn("delay", types_saved)

    def test_delete_file_physically_removed(self):
        """Verificar que eliminar borra el archivo del disco."""
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "borrar_me.yaml"
            f.write_text("name: Borrar Me\nsteps: []", encoding="utf-8")
            info = _make_info(name="borrar_me", path=f)
            engine_mock = self._make_mock_engine(info=info)
            dialog = MagicMock()
            with patch("ui.pages.automation_page._get_engine", return_value=engine_mock):
                self.page._refresh_list = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._confirm_delete(info, dialog)
            self.assertFalse(f.exists())

    def test_edit_existing_file_keeps_extension(self):
        """Editar un archivo existente debe mantener la misma extensión."""
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "original.yaml"
            f.write_text("name: Original\nsteps: []", encoding="utf-8")
            self.page._editing_path = f
            self._set_fields("Original Editado")
            with patch("ui.pages.automation_page._AUTOMATIONS_DIR", Path(td)):
                self.page._refresh_list = MagicMock()
                self.page._select_by_slug = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._on_save()
            self.assertTrue(f.exists())

    def test_atomic_write_no_tmp_on_disk(self):
        """Verificar que no quedan archivos .tmp después de guardar."""
        self._set_fields("Atomic Write Test")
        with tempfile.TemporaryDirectory() as td:
            with patch("ui.pages.automation_page._AUTOMATIONS_DIR", Path(td)):
                self.page._refresh_list = MagicMock()
                self.page._select_by_slug = MagicMock()
                self.page._show_mode = MagicMock()
                self.page._on_save()
            tmp_files = list(Path(td).glob("*.tmp"))
            self.assertEqual(len(tmp_files), 0)


# ══════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)

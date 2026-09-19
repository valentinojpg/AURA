"""
AURA — Tests automáticos de Fase 9: UI de historial de chats

Verifica que el HistoryPanel y su integración con ChatPage
funcionen correctamente sin necesitar el loop de UI activo.

Tests incluidos:
    1.  HistoryPanel importable
    2.  _RenameDialog importable
    3.  _ConfirmDeleteDialog importable
    4.  _format_date importable y retorna str
    5.  _format_date con fecha de hoy retorna "Hoy HH:MM"
    6.  _format_date con fecha de ayer retorna "Ayer HH:MM"
    7.  _format_date con fecha antigua retorna "DD/MM/AAAA"
    8.  _format_date con string vacío retorna ""
    9.  _format_date con string inválido no lanza excepción
    10. HistoryPanel tiene constructor con parámetros correctos
    11. HistoryPanel tiene método show()
    12. HistoryPanel tiene método dismiss()
    13. HistoryPanel tiene método toggle()
    14. HistoryPanel tiene método refresh()
    15. HistoryPanel tiene método set_active()
    16. HistoryPanel tiene property is_visible
    17. HistoryPanel tiene _on_open_click()
    18. HistoryPanel tiene _on_rename_click()
    19. HistoryPanel tiene _on_delete_click()
    20. HistoryPanel tiene _on_new_click()
    21. HistoryPanel tiene _do_rename() que llama store.rename()
    22. HistoryPanel tiene _do_delete() que llama store.delete()
    23. ChatPage importa HistoryPanel correctamente
    24. ChatPage tiene _history_panel atributo
    25. ChatPage tiene _history_btn atributo
    26. ChatPage tiene _on_toggle_history() método
    27. ChatPage tiene new_conversation_action() público
    28. ChatPage tiene load_conversation() que devuelve bool
    29. ui.components exporta HistoryPanel
    30. _format_date con fecha de esta semana retorna día de la semana
"""

import pytest
pytest.skip("Legacy CustomTkinter UI test (migrated to Flet in Phase 30)", allow_module_level=True)

import sys
import os
import pathlib
import tempfile
import unittest
import importlib
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Importar sin levantar el loop de UI
from ui.components.history_panel import (
    HistoryPanel,
    _RenameDialog,
    _ConfirmDeleteDialog,
    _format_date,
)
from data.conversation_store import ConversationStore, StoredMessage


def _make_store() -> tuple[ConversationStore, tempfile.TemporaryDirectory]:
    """Crea un store con directorio temporal."""
    tmp = tempfile.TemporaryDirectory()
    store = ConversationStore(conversations_dir=pathlib.Path(tmp.name))
    return store, tmp


class TestImports(unittest.TestCase):
    """Tests de importación de los módulos de Fase 9."""

    def test_01_history_panel_importable(self):
        """HistoryPanel es importable."""
        self.assertIsNotNone(HistoryPanel)

    def test_02_rename_dialog_importable(self):
        """_RenameDialog es importable."""
        self.assertIsNotNone(_RenameDialog)

    def test_03_confirm_delete_dialog_importable(self):
        """_ConfirmDeleteDialog es importable."""
        self.assertIsNotNone(_ConfirmDeleteDialog)

    def test_04_format_date_importable(self):
        """_format_date es importable y retorna str."""
        result = _format_date("")
        self.assertIsInstance(result, str)


class TestFormatDate(unittest.TestCase):
    """Tests de la función _format_date."""

    def test_05_format_date_hoy(self):
        """_format_date con fecha de hoy retorna 'Hoy HH:MM'."""
        now = datetime.now().isoformat()
        result = _format_date(now)
        self.assertTrue(result.startswith("Hoy "), f"Esperado 'Hoy ...' pero fue: {result!r}")

    def test_06_format_date_ayer(self):
        """_format_date con fecha de ayer retorna 'Ayer HH:MM'."""
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        result = _format_date(yesterday)
        self.assertTrue(result.startswith("Ayer "), f"Esperado 'Ayer ...' pero fue: {result!r}")

    def test_07_format_date_antigua(self):
        """_format_date con fecha antigua retorna 'DD/MM/AAAA'."""
        old_date = "2025-01-15T10:30:00"
        result = _format_date(old_date)
        self.assertEqual(result, "15/01/2025")

    def test_08_format_date_vacio(self):
        """_format_date con string vacío retorna ''."""
        result = _format_date("")
        self.assertEqual(result, "")

    def test_09_format_date_invalido(self):
        """_format_date con string inválido no lanza excepción."""
        try:
            result = _format_date("esto-no-es-una-fecha")
            self.assertIsInstance(result, str)
        except Exception as e:
            self.fail(f"_format_date lanzó excepción: {e}")

    def test_30_format_date_semana(self):
        """_format_date con fecha de esta semana retorna día de la semana."""
        # 3 días atrás (dentro de 7 días pero no hoy ni ayer)
        three_days_ago = (datetime.now() - timedelta(days=3)).isoformat()
        result = _format_date(three_days_ago)
        dias = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        any_day = any(result.startswith(d) for d in dias)
        self.assertTrue(any_day, f"Esperado día de la semana pero fue: {result!r}")


class TestHistoryPanelInterface(unittest.TestCase):
    """Tests de interfaz del HistoryPanel (sin instanciar UI)."""

    def test_10_constructor_params(self):
        """HistoryPanel tiene constructor con parámetros correctos."""
        import inspect
        sig = inspect.signature(HistoryPanel.__init__)
        params = list(sig.parameters.keys())
        self.assertIn("store", params)
        self.assertIn("on_open", params)
        self.assertIn("on_new", params)

    def test_11_has_show(self):
        """HistoryPanel tiene método show()."""
        self.assertTrue(hasattr(HistoryPanel, "show"))
        self.assertTrue(callable(HistoryPanel.show))

    def test_12_has_dismiss(self):
        """HistoryPanel tiene método dismiss()."""
        self.assertTrue(hasattr(HistoryPanel, "dismiss"))
        self.assertTrue(callable(HistoryPanel.dismiss))

    def test_13_has_toggle(self):
        """HistoryPanel tiene método toggle()."""
        self.assertTrue(hasattr(HistoryPanel, "toggle"))
        self.assertTrue(callable(HistoryPanel.toggle))

    def test_14_has_refresh(self):
        """HistoryPanel tiene método refresh()."""
        self.assertTrue(hasattr(HistoryPanel, "refresh"))
        self.assertTrue(callable(HistoryPanel.refresh))

    def test_15_has_set_active(self):
        """HistoryPanel tiene método set_active()."""
        self.assertTrue(hasattr(HistoryPanel, "set_active"))
        self.assertTrue(callable(HistoryPanel.set_active))

    def test_16_has_is_visible(self):
        """HistoryPanel tiene property is_visible."""
        self.assertIsInstance(
            getattr(HistoryPanel, "is_visible", None), property,
            "is_visible debe ser una property"
        )

    def test_17_has_on_open_click(self):
        """HistoryPanel tiene _on_open_click()."""
        self.assertTrue(hasattr(HistoryPanel, "_on_open_click"))

    def test_18_has_on_rename_click(self):
        """HistoryPanel tiene _on_rename_click()."""
        self.assertTrue(hasattr(HistoryPanel, "_on_rename_click"))

    def test_19_has_on_delete_click(self):
        """HistoryPanel tiene _on_delete_click()."""
        self.assertTrue(hasattr(HistoryPanel, "_on_delete_click"))

    def test_20_has_on_new_click(self):
        """HistoryPanel tiene _on_new_click()."""
        self.assertTrue(hasattr(HistoryPanel, "_on_new_click"))


class TestHistoryPanelLogic(unittest.TestCase):
    """Tests de la lógica del HistoryPanel (sin UI real)."""

    def test_21_do_rename_calls_store(self):
        """_do_rename() llama a store.rename() con el ID y título correcto."""
        store = MagicMock()
        store.rename.return_value = True

        # Crear una instancia parcial sin __init__ de CTkFrame
        panel = object.__new__(HistoryPanel)
        panel._store = store
        panel._active_conv_id = None
        panel._item_frames = []
        panel._footer_label = MagicMock()
        panel._empty_label = MagicMock()
        panel._list_frame = MagicMock()
        panel.after = MagicMock()

        panel._do_rename("abc12345", "Nuevo título")

        store.rename.assert_called_once_with("abc12345", "Nuevo título")

    def test_22_do_delete_calls_store(self):
        """_do_delete() llama a store.delete() con el ID correcto."""
        store = MagicMock()
        store.delete.return_value = True

        panel = object.__new__(HistoryPanel)
        panel._store = store
        panel._active_conv_id = "abc12345"
        panel._item_frames = []
        panel._footer_label = MagicMock()
        panel._empty_label = MagicMock()
        panel._list_frame = MagicMock()
        panel.after = MagicMock()

        panel._do_delete("abc12345")

        store.delete.assert_called_once_with("abc12345")
        # Verificar que se resetea el activo si era la conversación eliminada
        self.assertIsNone(panel._active_conv_id)

    def test_22b_do_delete_no_reset_if_different(self):
        """_do_delete() no resetea el activo si era otra conversación."""
        store = MagicMock()
        store.delete.return_value = True

        panel = object.__new__(HistoryPanel)
        panel._store = store
        panel._active_conv_id = "otra1234"
        panel._item_frames = []
        panel._footer_label = MagicMock()
        panel._empty_label = MagicMock()
        panel._list_frame = MagicMock()
        panel.after = MagicMock()

        panel._do_delete("abc12345")

        self.assertEqual(panel._active_conv_id, "otra1234")


class TestChatPageIntegration(unittest.TestCase):
    """Tests de integración de HistoryPanel con ChatPage."""

    def setUp(self):
        self.mod = importlib.import_module("ui.pages.chat_page")

    def test_23_chat_page_importa_history_panel(self):
        """chat_page importa HistoryPanel correctamente."""
        self.assertTrue(hasattr(self.mod, "HistoryPanel"))

    def test_24_chat_page_tiene_history_panel_attr(self):
        """ChatPage declara _history_panel en __init__."""
        import inspect
        src = inspect.getsource(self.mod.ChatPage.__init__)
        self.assertIn("_history_panel", src)

    def test_25_chat_page_tiene_history_btn(self):
        """ChatPage crea _history_btn en _build_input_area."""
        import inspect
        src = inspect.getsource(self.mod.ChatPage._build_input_area)
        self.assertIn("_history_btn", src)

    def test_26_chat_page_tiene_on_toggle_history(self):
        """ChatPage tiene _on_toggle_history()."""
        self.assertTrue(hasattr(self.mod.ChatPage, "_on_toggle_history"))
        self.assertTrue(callable(self.mod.ChatPage._on_toggle_history))

    def test_27_chat_page_tiene_new_conversation_action(self):
        """ChatPage tiene new_conversation_action() público."""
        self.assertTrue(hasattr(self.mod.ChatPage, "new_conversation_action"))
        self.assertTrue(callable(self.mod.ChatPage.new_conversation_action))

    def test_28_load_conversation_returns_bool(self):
        """load_conversation() tiene anotación de retorno bool."""
        import inspect
        hints = self.mod.ChatPage.load_conversation.__annotations__
        # Con `from __future__ import annotations`, las anotaciones pueden ser
        # strings ('bool') o la clase real (bool), según cómo se evalúen.
        ret = hints.get("return", None)
        self.assertIsNotNone(ret, "load_conversation() debe tener anotación de retorno")
        self.assertIn(
            ret, (bool, "bool"),
            f"Se esperaba bool o 'bool', se obtuvo: {ret!r}"
        )

    def test_29_components_exporta_history_panel(self):
        """ui.components exporta HistoryPanel."""
        import ui.components as comps
        self.assertTrue(hasattr(comps, "HistoryPanel"))
        self.assertIs(comps.HistoryPanel, HistoryPanel)


if __name__ == "__main__":
    unittest.main(verbosity=2)

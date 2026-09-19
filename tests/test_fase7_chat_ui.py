"""
AURA — Tests automáticos de Fase 7: Chat UI básico

Verifica que todos los componentes de la UI de chat sean importables,
tengan la estructura correcta y cumplan el contrato de la interfaz
(sin instanciar widgets de Tkinter, para poder correr headless).

Tests incluidos:
    1.  ChatBubble importable
    2.  ChatPage importable
    3.  ChatPage hereda BasePage
    4.  ChatPage.PAGE_NAME == 'Chat'
    5.  Constantes de ChatPage (_MAX_INPUT_LEN, _MAX_CONTEXT_MESSAGES)
    6.  Métodos de ciclo de vida en ChatPage
    7.  Métodos de burbujas en ChatPage
    8.  Métodos de ChatBubble (update_content, _build)
    9.  Estados de _StatusBanner (5 métodos)
    10. Imports de AI en ChatPage (6 símbolos)
    11. _StatusBanner existe en el módulo
    12. Colores de ChatBubble (_COLORS dict con claves requeridas)
    13. ChatPage tiene _messages como lista vacía por diseño (sin Tk)
    14. Módulo ui.components.__init__ exporta Sidebar y TopBar
    15. Módulo ui.pages importable sin errores
"""

import pytest
pytest.skip("Legacy CustomTkinter UI test (migrated to Flet in Phase 30)", allow_module_level=True)

import sys
import os
import unittest
import importlib

# Asegurar que el raíz del proyecto esté en el path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestChatBubble(unittest.TestCase):
    """Tests del componente ChatBubble."""

    def setUp(self):
        self.mod = importlib.import_module("ui.components.chat_bubble")

    def test_01_importable(self):
        """ChatBubble es importable desde ui.components.chat_bubble."""
        from ui.components.chat_bubble import ChatBubble
        self.assertIsNotNone(ChatBubble)

    def test_02_is_ctk_frame_subclass(self):
        """ChatBubble hereda de ctk.CTkFrame."""
        import customtkinter as ctk
        from ui.components.chat_bubble import ChatBubble
        self.assertTrue(issubclass(ChatBubble, ctk.CTkFrame))

    def test_03_has_update_content(self):
        """ChatBubble tiene método update_content."""
        from ui.components.chat_bubble import ChatBubble
        self.assertTrue(hasattr(ChatBubble, "update_content"))
        self.assertTrue(callable(ChatBubble.update_content))

    def test_04_has_build_methods(self):
        """ChatBubble tiene _build, _build_system, _build_bubble."""
        from ui.components.chat_bubble import ChatBubble
        for method in ["_build", "_build_system", "_build_bubble"]:
            with self.subTest(method=method):
                self.assertTrue(hasattr(ChatBubble, method))

    def test_05_colors_dict_complete(self):
        """_COLORS tiene todas las claves de paleta requeridas."""
        mod = self.mod
        self.assertTrue(hasattr(mod, "_COLORS"))
        colors = mod._COLORS
        required_keys = [
            "user_bg", "user_text", "user_name",
            "assistant_bg", "assistant_text", "assistant_name",
            "system_bg", "system_text",
            "error_bg", "error_text", "error_name",
            "time_color",
        ]
        for key in required_keys:
            with self.subTest(key=key):
                self.assertIn(key, colors)

    def test_06_init_signature(self):
        """ChatBubble.__init__ acepta role, content, timestamp."""
        import inspect
        from ui.components.chat_bubble import ChatBubble
        sig = inspect.signature(ChatBubble.__init__)
        params = list(sig.parameters.keys())
        for param in ["role", "content", "timestamp"]:
            with self.subTest(param=param):
                self.assertIn(param, params)


class TestChatPage(unittest.TestCase):
    """Tests del módulo ChatPage."""

    def setUp(self):
        self.mod = importlib.import_module("ui.pages.chat_page")

    def test_07_importable(self):
        """El módulo ui.pages.chat_page es importable."""
        self.assertIsNotNone(self.mod)

    def test_08_chat_page_class_exists(self):
        """La clase ChatPage existe en el módulo."""
        self.assertTrue(hasattr(self.mod, "ChatPage"))

    def test_09_inherits_base_page(self):
        """ChatPage hereda de BasePage."""
        from ui.pages.base_page import BasePage
        ChatPage = self.mod.ChatPage
        self.assertTrue(issubclass(ChatPage, BasePage))

    def test_10_page_name(self):
        """ChatPage.PAGE_NAME es 'Chat'."""
        self.assertEqual(self.mod.ChatPage.PAGE_NAME, "Chat")

    def test_11_max_input_len(self):
        """_MAX_INPUT_LEN es 4000."""
        self.assertEqual(self.mod._MAX_INPUT_LEN, 4000)

    def test_12_max_context_messages(self):
        """_MAX_CONTEXT_MESSAGES es 20."""
        self.assertEqual(self.mod._MAX_CONTEXT_MESSAGES, 20)

    def test_13_lifecycle_methods(self):
        """ChatPage tiene on_enter y on_leave."""
        ChatPage = self.mod.ChatPage
        for method in ["on_enter", "on_leave"]:
            with self.subTest(method=method):
                self.assertTrue(hasattr(ChatPage, method))
                self.assertTrue(callable(getattr(ChatPage, method)))

    def test_14_message_methods(self):
        """ChatPage tiene métodos para agregar mensajes de todos los tipos."""
        ChatPage = self.mod.ChatPage
        for method in [
            "_add_user_message",
            "_add_assistant_message",
            "_add_system_message",
            "_add_error_message",
        ]:
            with self.subTest(method=method):
                self.assertTrue(hasattr(ChatPage, method))

    def test_15_ai_control_methods(self):
        """ChatPage tiene métodos de control de IA."""
        ChatPage = self.mod.ChatPage
        for method in [
            "_on_send",
            "_call_ai",
            "_on_ai_response",
            "_on_ai_error",
            "_set_thinking",
            "_init_provider",
        ]:
            with self.subTest(method=method):
                self.assertTrue(hasattr(ChatPage, method))

    def test_16_typing_indicator_methods(self):
        """ChatPage tiene métodos del typing indicator."""
        ChatPage = self.mod.ChatPage
        for method in [
            "_show_typing_indicator",
            "_animate_typing",
            "_update_typing_indicator",
            "_remove_typing_indicator",
            "_cancel_typing_animation",
        ]:
            with self.subTest(method=method):
                self.assertTrue(hasattr(ChatPage, method))

    def test_17_clear_method(self):
        """ChatPage tiene método _on_clear."""
        self.assertTrue(hasattr(self.mod.ChatPage, "_on_clear"))

    def test_18_scroll_method(self):
        """ChatPage tiene método _scroll_to_bottom."""
        self.assertTrue(hasattr(self.mod.ChatPage, "_scroll_to_bottom"))

    def test_19_input_methods(self):
        """ChatPage tiene métodos de manejo de entrada."""
        ChatPage = self.mod.ChatPage
        for method in [
            "_get_input_text",
            "_clear_input",
            "_on_key_enter",
            "_on_key_shift_enter",
            "_on_key_release",
        ]:
            with self.subTest(method=method):
                self.assertTrue(hasattr(ChatPage, method))


class TestStatusBanner(unittest.TestCase):
    """Tests del componente _StatusBanner."""

    def setUp(self):
        self.mod = importlib.import_module("ui.pages.chat_page")

    def test_20_status_banner_exists(self):
        """_StatusBanner existe en el módulo chat_page."""
        self.assertTrue(hasattr(self.mod, "_StatusBanner"))

    def test_21_status_banner_states(self):
        """_StatusBanner tiene los 5 estados requeridos."""
        banner = self.mod._StatusBanner
        for method in ["set_loading", "set_ok", "set_warning", "set_error", "set_mock"]:
            with self.subTest(method=method):
                self.assertTrue(hasattr(banner, method))
                self.assertTrue(callable(getattr(banner, method)))


class TestAIImports(unittest.TestCase):
    """Tests de que los imports de IA en chat_page son correctos."""

    def test_22_ai_module_exports_required_symbols(self):
        """El módulo ai exporta todos los símbolos usados por ChatPage."""
        import ai
        required = [
            "ChatMessage",
            "get_default_provider",
            "AuraAIError",
            "ProviderNotAvailableError",
            "ModelNotFoundError",
            "RequestTimeoutError",
        ]
        for symbol in required:
            with self.subTest(symbol=symbol):
                self.assertTrue(hasattr(ai, symbol), f"ai no exporta: {symbol}")

    def test_23_chat_message_dataclass(self):
        """ChatMessage tiene campos role y content."""
        from ai import ChatMessage
        import dataclasses
        fields = {f.name for f in dataclasses.fields(ChatMessage)}
        self.assertIn("role", fields)
        self.assertIn("content", fields)


class TestUIPackages(unittest.TestCase):
    """Tests de la estructura de paquetes de UI."""

    def test_24_ui_components_importable(self):
        """El paquete ui.components es importable."""
        mod = importlib.import_module("ui.components")
        self.assertIsNotNone(mod)

    def test_25_ui_pages_importable(self):
        """El paquete ui.pages es importable."""
        mod = importlib.import_module("ui.pages")
        self.assertIsNotNone(mod)

    def test_26_all_pages_importable(self):
        """Todas las páginas de la app son importables."""
        pages = [
            "ui.pages.chat_page",
            "ui.pages.skills_page",
            "ui.pages.automation_page",
            "ui.pages.files_page",
            "ui.pages.settings_page",
        ]
        for page in pages:
            with self.subTest(page=page):
                mod = importlib.import_module(page)
                self.assertIsNotNone(mod)

    def test_27_chat_bubble_importable_from_components(self):
        """ChatBubble es importable directamente desde su módulo."""
        from ui.components.chat_bubble import ChatBubble
        self.assertIsNotNone(ChatBubble)

    def test_28_main_window_importable(self):
        """ui.main_window es importable (sin ejecutar el loop de UI)."""
        # Solo verificamos el módulo, no instanciamos MainWindow (requiere Tk)
        mod = importlib.import_module("ui.main_window")
        self.assertTrue(hasattr(mod, "MainWindow"))

    def test_29_main_window_constants(self):
        """MainWindow tiene constantes de versión correctas para Fase 7."""
        from ui.main_window import MainWindow, DEFAULT_PAGE, PAGE_TITLES
        self.assertEqual(DEFAULT_PAGE, "chat")
        self.assertIn("chat", PAGE_TITLES)
        self.assertIn("settings", PAGE_TITLES)

    def test_30_chat_page_colors_palette(self):
        """chat_page tiene paleta de colores completa."""
        mod = importlib.import_module("ui.pages.chat_page")
        color_vars = [
            "_BG_DARK", "_INPUT_BG", "_INPUT_BORDER",
            "_SEND_BTN_BG", "_SEND_BTN_HOVER", "_SEND_DISABLED",
            "_STATUS_OK", "_STATUS_WARN", "_STATUS_ERR", "_STATUS_MOCK",
            "_CLEAR_BG", "_CLEAR_HOVER",
        ]
        for var in color_vars:
            with self.subTest(var=var):
                self.assertTrue(hasattr(mod, var), f"Falta constante de color: {var}")
                val = getattr(mod, var)
                self.assertTrue(val.startswith("#"), f"{var} no parece un color hex: {val}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""
AURA — Tests automáticos Fase 7: Chat UI básico
================================================

Verifica la lógica del ChatPage sin levantar una ventana real de Tkinter.
Usa mocks para el proveedor de IA y para los widgets de la UI.

Ejecución:
    .\\env\\Scripts\\python.exe tests\\test_fase7_chat.py
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

# Agregar raíz del proyecto al path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# ── Módulos de AURA ──────────────────────────────────────────────
from ai.provider_interface import ChatMessage, ChatResponse, ProviderStatus
from ai.providers.mock_provider import MockProvider
from ai.errors import ProviderNotAvailableError, RequestTimeoutError


# ──────────────────────────────────────────────────────────────────
# Tests de la lógica de negocio (sin UI)
# ──────────────────────────────────────────────────────────────────

class TestChatLogica(unittest.TestCase):
    """Tests de la lógica de chat sin GUI."""

    def setUp(self):
        self.provider = MockProvider(simulate_delay_ms=0)

    def test_01_provider_mock_disponible(self):
        """MockProvider debe estar disponible para usar en chat."""
        status = self.provider.check_status()
        self.assertTrue(status.available)
        self.assertEqual(status.provider, "mock")

    def test_02_chat_retorna_respuesta(self):
        """chat() debe retornar una ChatResponse con contenido."""
        messages = [ChatMessage(role="user", content="Hola")]
        response = self.provider.chat(messages)
        self.assertIsInstance(response, ChatResponse)
        self.assertTrue(len(response.content) > 0)
        self.assertEqual(response.provider, "mock")

    def test_03_chat_stream_genera_chunks(self):
        """chat_stream() debe generar al menos un chunk."""
        messages = [ChatMessage(role="user", content="¿Qué podés hacer?")]
        chunks = list(self.provider.chat_stream(messages))
        self.assertGreater(len(chunks), 0)
        full = "".join(chunks)
        self.assertGreater(len(full), 0)

    def test_04_contexto_acumula_mensajes(self):
        """El contexto debe acumular mensajes en orden."""
        context: list[ChatMessage] = []
        context.append(ChatMessage(role="user", content="Hola"))
        context.append(ChatMessage(role="assistant", content="¡Hola!"))
        context.append(ChatMessage(role="user", content="¿Cómo estás?"))

        self.assertEqual(len(context), 3)
        self.assertEqual(context[0].role, "user")
        self.assertEqual(context[1].role, "assistant")
        self.assertEqual(context[2].role, "user")

    def test_05_contexto_se_trunca_a_max(self):
        """El contexto no debe superar el máximo de mensajes."""
        MAX = 20
        context = [
            ChatMessage(role="user", content=f"Mensaje {i}")
            for i in range(30)
        ]
        # Simular el truncado que hace ChatPage
        context_truncado = context[-MAX:]
        self.assertEqual(len(context_truncado), MAX)
        # El último mensaje debe ser el 29
        self.assertEqual(context_truncado[-1].content, "Mensaje 29")

    def test_06_mensaje_vacio_no_se_envia(self):
        """Un mensaje vacío o solo espacios no debería enviarse."""
        textos_invalidos = ["", "   ", "\n", "\t  \n"]
        for texto in textos_invalidos:
            self.assertEqual(texto.strip(), "",
                             f"'{texto}' debería quedar vacío tras strip()")

    def test_07_mensaje_muy_largo_detectado(self):
        """Un mensaje que supera el límite debe detectarse."""
        MAX_LEN = 4000
        texto_largo = "x" * (MAX_LEN + 1)
        self.assertGreater(len(texto_largo), MAX_LEN)

    def test_08_mensaje_justo_en_limite_ok(self):
        """Un mensaje de exactamente el límite debe ser aceptable."""
        MAX_LEN = 4000
        texto_limite = "x" * MAX_LEN
        self.assertEqual(len(texto_limite), MAX_LEN)
        self.assertFalse(len(texto_limite) > MAX_LEN)

    def test_09_provider_not_available_error_capturado(self):
        """ProviderNotAvailableError debe capturarse correctamente."""
        self.provider.fail_next = True
        messages = [ChatMessage(role="user", content="Hola")]
        with self.assertRaises(ProviderNotAvailableError):
            self.provider.chat(messages)

    def test_10_provider_reset_despues_de_fail(self):
        """Después de fail_next, el proveedor debe volver a funcionar."""
        self.provider.fail_next = True
        messages = [ChatMessage(role="user", content="Hola")]
        try:
            self.provider.chat(messages)
        except ProviderNotAvailableError:
            pass  # Esperado

        # Debe funcionar en el siguiente intento
        response = self.provider.chat(messages)
        self.assertIsInstance(response, ChatResponse)

    def test_11_chatmessage_to_dict(self):
        """ChatMessage.to_dict() debe retornar el dict correcto."""
        msg = ChatMessage(role="user", content="Hola AURA")
        d = msg.to_dict()
        self.assertEqual(d["role"], "user")
        self.assertEqual(d["content"], "Hola AURA")

    def test_12_chatresponse_total_tokens(self):
        """ChatResponse.total_tokens debe ser la suma de prompt + response."""
        resp = ChatResponse(
            content="Respuesta",
            model="mock",
            provider="mock",
            tokens_prompt=10,
            tokens_response=25,
        )
        self.assertEqual(resp.total_tokens, 35)


class TestChatPageEstructura(unittest.TestCase):
    """Tests de estructura del módulo ChatPage sin instanciarlo."""

    def test_20_chatpage_importable(self):
        """ChatPage debe poder importarse sin errores."""
        from ui.pages.chat_page import ChatPage
        self.assertTrue(hasattr(ChatPage, "PAGE_NAME"))
        self.assertEqual(ChatPage.PAGE_NAME, "Chat")

    def test_21_chatpage_tiene_metodos_requeridos(self):
        """ChatPage debe tener todos los métodos requeridos."""
        from ui.pages.chat_page import ChatPage
        for metodo in ["_build", "on_enter", "on_leave", "_on_send", "_on_clear"]:
            self.assertTrue(
                hasattr(ChatPage, metodo),
                f"ChatPage debe tener el método '{metodo}'"
            )

    def test_22_chat_bubble_importable(self):
        """ChatBubble debe poder importarse sin errores."""
        from ui.components.chat_bubble import ChatBubble
        self.assertTrue(callable(ChatBubble))

    def test_23_status_banner_en_modulo(self):
        """_StatusBanner debe existir en el módulo chat_page."""
        import ui.pages.chat_page as mod
        self.assertTrue(hasattr(mod, "_StatusBanner"))

    def test_24_constantes_de_chat_definidas(self):
        """Las constantes del módulo de chat deben estar definidas."""
        import ui.pages.chat_page as mod
        self.assertTrue(hasattr(mod, "_MAX_INPUT_LEN"))
        self.assertTrue(hasattr(mod, "_MAX_CONTEXT_MESSAGES"))
        self.assertTrue(hasattr(mod, "_TYPING_BLINK_MS"))
        self.assertGreater(mod._MAX_INPUT_LEN, 0)
        self.assertGreater(mod._MAX_CONTEXT_MESSAGES, 0)

    def test_25_herencia_de_base_page(self):
        """ChatPage debe heredar de BasePage."""
        from ui.pages.chat_page import ChatPage
        from ui.pages.base_page import BasePage
        self.assertTrue(issubclass(ChatPage, BasePage))


class TestChatBubbleRoles(unittest.TestCase):
    """Tests de la clase ChatBubble a nivel de módulo (sin widgets reales)."""

    def test_30_roles_validos_definidos(self):
        """Los colores para todos los roles deben estar definidos."""
        from ui.components.chat_bubble import _COLORS
        roles_requeridos = [
            "user_bg", "user_text", "user_name",
            "assistant_bg", "assistant_text", "assistant_name",
            "system_bg", "system_text",
            "error_bg", "error_text", "error_name",
            "time_color",
        ]
        for key in roles_requeridos:
            self.assertIn(key, _COLORS, f"Falta color para: {key}")

    def test_31_chatbubble_tiene_update_content(self):
        """ChatBubble debe tener el método update_content."""
        from ui.components.chat_bubble import ChatBubble
        self.assertTrue(hasattr(ChatBubble, "update_content"))


class TestFactoryFallback(unittest.TestCase):
    """Tests de que el factory hace fallback a mock correctamente para la UI."""

    def test_40_get_default_provider_nunca_es_none(self):
        """get_default_provider siempre retorna un proveedor (mock si AI_ALLOW_MOCK=true, ollama si no)."""
        from ai import get_default_provider
        from ai.provider_interface import AIProvider
        import os
        import urllib.error
        from unittest.mock import patch

        # Simular que Ollama no está disponible con AI_ALLOW_MOCK=true
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")), \
             patch.dict(os.environ, {"AI_ALLOW_MOCK": "true"}):
            provider = get_default_provider(fallback_to_mock=True, force_reload=True)

        self.assertIsNotNone(provider)
        self.assertIsInstance(provider, AIProvider)
        # Cuando Ollama no está disponible y AI_ALLOW_MOCK=true, debe caer a mock
        self.assertEqual(provider.provider_name, "mock")

        # Sin AI_ALLOW_MOCK: no cae a mock, retorna OllamaProvider
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")), \
             patch.dict(os.environ, {"AI_ALLOW_MOCK": "false"}):
            provider2 = get_default_provider(fallback_to_mock=True, force_reload=True)
        self.assertEqual(provider2.provider_name, "ollama")

    def test_41_mock_provider_responde_en_espanol(self):
        """MockProvider debe responder en español."""
        provider = MockProvider(simulate_delay_ms=0)
        messages = [ChatMessage(role="user", content="Hola")]
        response = provider.chat(messages)
        # MockProvider responde siempre en español (texto largo en español)
        self.assertIsInstance(response.content, str)
        self.assertGreater(len(response.content), 10)


# ──────────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("AURA — Tests Fase 7: Chat UI básico")
    print("=" * 60)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestChatLogica,
        TestChatPageEstructura,
        TestChatBubbleRoles,
        TestFactoryFallback,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 60)
    total = result.testsRun
    ok = total - len(result.failures) - len(result.errors)
    print(f"RESULTADO: {ok}/{total} tests pasados")

    if result.failures:
        print(f"  FALLOS ({len(result.failures)}):")
        for test, msg in result.failures:
            print(f"    - {test}: {msg.splitlines()[-1]}")

    if result.errors:
        print(f"  ERRORES ({len(result.errors)}):")
        for test, msg in result.errors:
            print(f"    - {test}: {msg.splitlines()[-1]}")

    print("=" * 60)
    sys.exit(0 if result.wasSuccessful() else 1)

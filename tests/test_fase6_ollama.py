"""
AURA — Tests automáticos Fase 6: Proveedor Ollama
==================================================

Verifica que OllamaProvider cumple el contrato de AIProvider
y maneja correctamente los errores de red sin requerir Ollama instalado.

Ejecución:
    .\\env\\Scripts\\python.exe tests\\test_fase6_ollama.py
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

# Agregar raíz del proyecto al path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import json
import unittest
import urllib.error
from io import BytesIO
from unittest.mock import patch, MagicMock

# ── Módulos de AURA ──────────────────────────────────────────────
from ai.providers.ollama_provider import OllamaProvider
from ai.provider_interface import AIProvider, ChatMessage, ChatResponse, ProviderStatus
from ai.errors import (
    AuraAIError,
    ProviderNotAvailableError,
    ModelNotFoundError,
    RequestTimeoutError,
    ResponseParseError,
)
from ai.provider_factory import (
    get_provider,
    get_default_provider,
    list_available_providers,
    is_provider_registered,
)


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

def _make_http_response(body: dict | str, status: int = 200) -> MagicMock:
    """Crea un mock de la respuesta HTTP de urllib."""
    if isinstance(body, dict):
        body_bytes = json.dumps(body).encode("utf-8")
    else:
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body

    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.read.return_value = body_bytes
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    # Simular iteración línea por línea para streaming
    mock_resp.__iter__ = lambda s: iter(
        [line + b"\n" for line in body_bytes.split(b"\n") if line]
    )
    return mock_resp


def _make_url_error(message: str = "Connection refused") -> urllib.error.URLError:
    return urllib.error.URLError(reason=message)


def _make_http_error(code: int, body: dict) -> urllib.error.HTTPError:
    body_bytes = json.dumps(body).encode("utf-8")
    mock_fp = BytesIO(body_bytes)
    err = urllib.error.HTTPError(
        url="http://localhost:11434/api/chat",
        code=code,
        msg=f"HTTP Error {code}",
        hdrs={},
        fp=mock_fp,
    )
    return err


# ──────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────

class TestOllamaProviderInterfaz(unittest.TestCase):
    """Verifica que OllamaProvider cumple el contrato de AIProvider."""

    def setUp(self):
        self.provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="qwen2.5:3b",
        )

    def test_01_es_instancia_de_aiprovider(self):
        """OllamaProvider debe heredar de AIProvider."""
        self.assertIsInstance(self.provider, AIProvider)

    def test_02_provider_name(self):
        """provider_name debe retornar 'ollama'."""
        self.assertEqual(self.provider.provider_name, "ollama")

    def test_03_base_url_property(self):
        """base_url debe retornar la URL configurada sin barra final."""
        p = OllamaProvider(base_url="http://localhost:11434/")
        self.assertEqual(p.base_url, "http://localhost:11434")

    def test_04_default_model_property(self):
        """default_model debe retornar el modelo configurado."""
        self.assertEqual(self.provider.default_model, "qwen2.5:3b")

    def test_05_repr(self):
        """__repr__ debe contener url y model."""
        r = repr(self.provider)
        self.assertIn("OllamaProvider", r)
        self.assertIn("localhost:11434", r)
        self.assertIn("qwen2.5:3b", r)


class TestCheckStatus(unittest.TestCase):
    """Tests de check_status() con servidor simulado."""

    def setUp(self):
        self.provider = OllamaProvider()

    @patch("urllib.request.urlopen")
    def test_10_disponible_con_modelos(self, mock_urlopen):
        """check_status retorna available=True si Ollama responde con modelos."""
        mock_urlopen.return_value = _make_http_response({
            "models": [
                {"name": "qwen2.5:3b"},
                {"name": "llama3.2:3b"},
            ]
        })
        status = self.provider.check_status()
        self.assertIsInstance(status, ProviderStatus)
        self.assertTrue(status.available)
        self.assertEqual(status.provider, "ollama")
        self.assertIn("qwen2.5:3b", status.models)
        self.assertIn("llama3.2:3b", status.models)

    @patch("urllib.request.urlopen")
    def test_11_disponible_sin_modelos(self, mock_urlopen):
        """check_status retorna available=True pero avisa que no hay modelos."""
        mock_urlopen.return_value = _make_http_response({"models": []})
        status = self.provider.check_status()
        self.assertTrue(status.available)
        self.assertIn("sin modelos", status.message.lower())

    @patch("urllib.request.urlopen")
    def test_12_no_disponible_conexion_rechazada(self, mock_urlopen):
        """check_status retorna available=False si Ollama no está corriendo."""
        mock_urlopen.side_effect = _make_url_error("Connection refused")
        status = self.provider.check_status()
        self.assertFalse(status.available)
        self.assertIn("localhost:11434", status.message)

    @patch("urllib.request.urlopen")
    def test_13_no_disponible_json_invalido(self, mock_urlopen):
        """check_status retorna available=False ante JSON inválido."""
        mock_urlopen.return_value = _make_http_response("esto no es json")
        # La respuesta inválida hace que json.loads falle
        # Sobrescribimos el read para retornar bytes inválidos
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"not-valid-json{{{{"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        status = self.provider.check_status()
        self.assertFalse(status.available)

    def test_14_check_status_nunca_lanza_excepciones(self):
        """check_status NUNCA debe lanzar excepciones — siempre retorna ProviderStatus."""
        with patch("urllib.request.urlopen", side_effect=Exception("Fallo inesperado")):
            status = self.provider.check_status()
        self.assertIsInstance(status, ProviderStatus)
        self.assertFalse(status.available)


class TestListModels(unittest.TestCase):
    """Tests de list_models()."""

    def setUp(self):
        self.provider = OllamaProvider()

    @patch("urllib.request.urlopen")
    def test_20_lista_modelos_correctamente(self, mock_urlopen):
        """list_models retorna lista de nombres de modelos."""
        mock_urlopen.return_value = _make_http_response({
            "models": [
                {"name": "qwen2.5:3b"},
                {"name": "llama3.2:3b"},
                {"name": "mistral:7b"},
            ]
        })
        models = self.provider.list_models()
        self.assertEqual(len(models), 3)
        self.assertIn("qwen2.5:3b", models)

    @patch("urllib.request.urlopen")
    def test_21_lista_vacia_si_no_hay_modelos(self, mock_urlopen):
        """list_models retorna [] si Ollama no tiene modelos instalados."""
        mock_urlopen.return_value = _make_http_response({"models": []})
        models = self.provider.list_models()
        self.assertEqual(models, [])

    @patch("urllib.request.urlopen")
    def test_22_lanza_error_si_ollama_no_disponible(self, mock_urlopen):
        """list_models lanza ProviderNotAvailableError si Ollama no responde."""
        mock_urlopen.side_effect = _make_url_error("Connection refused")
        with self.assertRaises(ProviderNotAvailableError) as ctx:
            self.provider.list_models()
        self.assertEqual(ctx.exception.provider, "ollama")


class TestChat(unittest.TestCase):
    """Tests de chat() con servidor simulado."""

    def setUp(self):
        self.provider = OllamaProvider()
        self.messages = [
            ChatMessage(role="user", content="Hola, ¿cómo estás?")
        ]

    def _mock_chat_response(self, content: str = "¡Hola! Estoy bien.") -> MagicMock:
        return _make_http_response({
            "model": "qwen2.5:3b",
            "message": {"role": "assistant", "content": content},
            "done": True,
            "prompt_eval_count": 10,
            "eval_count": 20,
        })

    @patch("urllib.request.urlopen")
    def test_30_chat_retorna_chatresponse(self, mock_urlopen):
        """chat() retorna un ChatResponse válido."""
        mock_urlopen.return_value = self._mock_chat_response()
        response = self.provider.chat(self.messages)
        self.assertIsInstance(response, ChatResponse)
        self.assertEqual(response.provider, "ollama")
        self.assertTrue(len(response.content) > 0)
        self.assertTrue(response.done)

    @patch("urllib.request.urlopen")
    def test_31_chat_cuenta_tokens(self, mock_urlopen):
        """chat() cuenta tokens de prompt y respuesta."""
        mock_urlopen.return_value = self._mock_chat_response()
        response = self.provider.chat(self.messages)
        self.assertEqual(response.tokens_prompt, 10)
        self.assertEqual(response.tokens_response, 20)
        self.assertEqual(response.total_tokens, 30)

    @patch("urllib.request.urlopen")
    def test_32_chat_usa_modelo_custom(self, mock_urlopen):
        """chat() usa el modelo especificado en el argumento."""
        mock_urlopen.return_value = self._mock_chat_response()
        response = self.provider.chat(self.messages, model="llama3.2:3b")
        self.assertIsInstance(response, ChatResponse)

    @patch("urllib.request.urlopen")
    def test_33_chat_lanza_error_si_ollama_no_disponible(self, mock_urlopen):
        """chat() lanza ProviderNotAvailableError si Ollama no responde."""
        mock_urlopen.side_effect = _make_url_error("Connection refused")
        with self.assertRaises(ProviderNotAvailableError):
            self.provider.chat(self.messages)

    @patch("urllib.request.urlopen")
    def test_34_chat_lanza_model_not_found(self, mock_urlopen):
        """chat() lanza ModelNotFoundError si el modelo no existe (HTTP 404)."""
        mock_urlopen.side_effect = _make_http_error(404, {"error": "model not found"})
        with self.assertRaises(ModelNotFoundError) as ctx:
            self.provider.chat(self.messages)
        self.assertIn("qwen2.5:3b", ctx.exception.args[0])

    @patch("urllib.request.urlopen")
    def test_35_chat_lanza_timeout(self, mock_urlopen):
        """chat() lanza RequestTimeoutError ante un timeout."""
        mock_urlopen.side_effect = _make_url_error("timed out")
        with self.assertRaises(RequestTimeoutError):
            self.provider.chat(self.messages)

    @patch("urllib.request.urlopen")
    def test_36_chat_lanza_parse_error_si_sin_content(self, mock_urlopen):
        """chat() lanza ResponseParseError si la respuesta no tiene 'content'."""
        mock_urlopen.return_value = _make_http_response({
            "model": "qwen2.5:3b",
            "message": {"role": "assistant", "content": ""},
            "done": True,
        })
        with self.assertRaises(ResponseParseError):
            self.provider.chat(self.messages)

    @patch("urllib.request.urlopen")
    def test_37_todos_los_errores_son_subclase_de_auraaierror(self, mock_urlopen):
        """Todos los errores de OllamaProvider heredan de AuraAIError."""
        mock_urlopen.side_effect = _make_url_error("Connection refused")
        with self.assertRaises(AuraAIError):
            self.provider.chat(self.messages)


class TestChatStream(unittest.TestCase):
    """Tests de chat_stream()."""

    def setUp(self):
        self.provider = OllamaProvider()
        self.messages = [ChatMessage(role="user", content="Contame algo")]

    @patch("urllib.request.urlopen")
    def test_40_stream_genera_chunks(self, mock_urlopen):
        """chat_stream() genera al menos un chunk de texto."""
        chunks = [
            json.dumps({"message": {"content": "Hola "}, "done": False}).encode(),
            json.dumps({"message": {"content": "mundo"}, "done": True}).encode(),
        ]
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.__iter__ = lambda s: iter(chunks)
        mock_urlopen.return_value = mock_resp

        resultado = list(self.provider.chat_stream(self.messages))
        self.assertGreater(len(resultado), 0)
        texto_completo = "".join(resultado)
        self.assertIn("Hola", texto_completo)

    @patch("urllib.request.urlopen")
    def test_41_stream_lanza_error_si_no_disponible(self, mock_urlopen):
        """chat_stream() lanza ProviderNotAvailableError si Ollama no responde."""
        mock_urlopen.side_effect = _make_url_error("Connection refused")
        with self.assertRaises(ProviderNotAvailableError):
            list(self.provider.chat_stream(self.messages))

    @patch("urllib.request.urlopen")
    def test_42_stream_lanza_parse_error_ante_json_invalido(self, mock_urlopen):
        """chat_stream() lanza ResponseParseError ante un chunk JSON inválido."""
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.__iter__ = lambda s: iter([b"esto no es json\n"])
        mock_urlopen.return_value = mock_resp

        with self.assertRaises(ResponseParseError):
            list(self.provider.chat_stream(self.messages))


class TestFactoryConOllama(unittest.TestCase):
    """Tests de integración de la factory con OllamaProvider."""

    def test_50_ollama_registrado_en_factory(self):
        """La factory debe tener 'ollama' registrado."""
        self.assertTrue(is_provider_registered("ollama"))

    def test_51_list_providers_incluye_ollama(self):
        """list_available_providers() debe incluir 'ollama'."""
        providers = list_available_providers()
        self.assertIn("ollama", providers)

    def test_52_get_provider_ollama_retorna_instancia(self):
        """get_provider('ollama') retorna una instancia de OllamaProvider."""
        provider = get_provider("ollama")
        self.assertIsInstance(provider, OllamaProvider)

    def test_53_get_provider_ollama_con_kwargs(self):
        """get_provider acepta base_url y model como kwargs para OllamaProvider."""
        provider = get_provider(
            "ollama",
            base_url="http://mi-servidor:11434",
            model="llama3.2:3b",
        )
        self.assertIsInstance(provider, OllamaProvider)
        self.assertEqual(provider.base_url, "http://mi-servidor:11434")
        self.assertEqual(provider.default_model, "llama3.2:3b")

    @patch("urllib.request.urlopen")
    def test_54_get_default_provider_usa_settings_de_env(self, mock_urlopen):
        """get_default_provider() crea OllamaProvider con URL y modelo del .env."""
        # Simulamos Ollama disponible
        mock_urlopen.return_value = _make_http_response({
            "models": [{"name": "qwen2.5:3b"}]
        })

        with patch.dict(os.environ, {
            "AI_PROVIDER": "ollama",
            "OLLAMA_URL": "http://test-server:11434",
            "AI_MODEL": "qwen2.5:3b",
        }):
            from config.settings import Settings
            from unittest.mock import patch as p
            provider = get_default_provider(force_reload=True)

        self.assertIsInstance(provider, OllamaProvider)

    @patch("urllib.request.urlopen")
    def test_55_fallback_a_mock_si_ollama_no_disponible(self, mock_urlopen):
        """get_default_provider() cae a MockProvider si Ollama no está corriendo y AI_ALLOW_MOCK=true."""
        from ai.providers.mock_provider import MockProvider
        from ai.providers.ollama_provider import OllamaProvider

        mock_urlopen.side_effect = _make_url_error("Connection refused")

        # Con AI_ALLOW_MOCK=true y fallback_to_mock=True: retorna MockProvider
        with patch.dict(os.environ, {"AI_PROVIDER": "ollama", "AI_ALLOW_MOCK": "true"}):
            provider = get_default_provider(fallback_to_mock=True, force_reload=True)
        self.assertIsInstance(provider, MockProvider)

        # Con AI_ALLOW_MOCK=false (default): NUNCA cae a MockProvider, retorna OllamaProvider
        with patch.dict(os.environ, {"AI_PROVIDER": "ollama", "AI_ALLOW_MOCK": "false"}):
            provider2 = get_default_provider(fallback_to_mock=True, force_reload=True)
        self.assertIsInstance(provider2, OllamaProvider)


# ──────────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("AURA — Tests Fase 6: Proveedor Ollama")
    print("=" * 60)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestOllamaProviderInterfaz,
        TestCheckStatus,
        TestListModels,
        TestChat,
        TestChatStream,
        TestFactoryConOllama,
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

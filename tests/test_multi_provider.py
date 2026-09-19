"""
AURA — Pruebas unitarias para el Núcleo Multi-proveedor de IA (Fase 55)

Valida:
1. Contrato BaseAIProvider / AIProvider (propiedades, métodos, ChatResponse).
2. ProviderRegistry y Factory centralizado.
3. Proveedores individuales (OpenAI, Anthropic, Gemini, xAI, Custom, Ollama, Mock).
4. Seguridad y enmascaramiento de API Keys en logs y settings.
5. Mecanismo de Fallback automático a Ollama local (FallbackProvider).
6. Diagnóstico y health_check sin crasheos ante claves vacías.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
import io
import logging

from ai.provider_interface import (
    AIProvider,
    BaseAIProvider,
    ChatMessage,
    ChatResponse,
    ProviderStatus,
)
from ai.provider_factory import (
    get_provider,
    get_default_provider,
    reset_default_provider,
    list_available_providers,
    is_provider_registered,
    FallbackProvider,
    PROVIDER_METADATA,
)
from ai.providers import (
    MockProvider,
    OllamaProvider,
    OpenAIProvider,
    XAIProvider,
    CustomOpenAIProvider,
    AnthropicProvider,
    GeminiProvider,
)
from ai.errors import ProviderConfigError, ProviderNotAvailableError
from config.settings import settings, mask_api_key


class TestBaseAIProviderContract(unittest.TestCase):
    """Verifica que todos los proveedores y clases cumplan con el contrato BaseAIProvider."""

    def test_01_base_alias(self):
        """BaseAIProvider debe ser un alias directo de AIProvider."""
        self.assertIs(BaseAIProvider, AIProvider)

    def test_02_chat_response_string_emulation(self):
        """ChatResponse debe ser compatible con operaciones de cadena sin romper atributos."""
        resp = ChatResponse(content="Hola mundo!", model="mock", provider="mock")
        # Compatibilidad con string
        self.assertEqual(str(resp), "Hola mundo!")
        self.assertEqual(resp, "Hola mundo!")
        self.assertTrue(resp.startswith("Hola"))
        self.assertTrue(resp.endswith("mundo!"))
        self.assertEqual(resp.lower(), "hola mundo!")
        self.assertEqual(resp.upper(), "HOLA MUNDO!")
        self.assertEqual(resp.split(), ["Hola", "mundo!"])
        self.assertIn("mundo", resp)
        self.assertEqual(len(resp), len("Hola mundo!"))
        # Compatibilidad con atributos originales
        self.assertEqual(resp.content, "Hola mundo!")
        self.assertEqual(resp.model, "mock")
        self.assertEqual(resp.provider, "mock")

    def test_03_normalize_messages(self):
        """normalize_messages debe unificar str, list[str], list[dict] y ChatMessage."""
        # De string simple
        m1 = AIProvider.normalize_messages("Hola", system="Instrucción previa")
        self.assertEqual(len(m1), 2)
        self.assertEqual(m1[0].role, "system")
        self.assertEqual(m1[0].content, "Instrucción previa")
        self.assertEqual(m1[1].role, "user")
        self.assertEqual(m1[1].content, "Hola")

        # De lista de dicts
        m2 = AIProvider.normalize_messages([{"role": "user", "content": "Pregunta"}])
        self.assertEqual(len(m2), 1)
        self.assertEqual(m2[0].role, "user")
        self.assertEqual(m2[0].content, "Pregunta")

    def test_04_health_check_contract(self):
        """health_check debe retornar (ok: bool, detalle: str)."""
        mock_p = MockProvider(fail_next=False)
        ok, msg = mock_p.health_check()
        self.assertTrue(ok)
        self.assertIsInstance(msg, str)

        mock_p.fail_next = True
        ok, msg = mock_p.health_check()
        self.assertFalse(ok)
        self.assertIn("fallo", msg.lower())

    def test_05_name_and_requires_api_key_properties(self):
        """name y requires_api_key deben estar disponibles en todas las instancias."""
        mock_p = MockProvider()
        self.assertEqual(mock_p.name, "mock")
        self.assertFalse(mock_p.requires_api_key)

        openai_p = OpenAIProvider(api_key="test-key")
        self.assertEqual(openai_p.name, "openai")
        self.assertTrue(openai_p.requires_api_key)

        anthropic_p = AnthropicProvider(api_key="test-key")
        self.assertEqual(anthropic_p.name, "anthropic")
        self.assertTrue(anthropic_p.requires_api_key)

        gemini_p = GeminiProvider(api_key="test-key")
        self.assertEqual(gemini_p.name, "gemini")
        self.assertTrue(gemini_p.requires_api_key)

        xai_p = XAIProvider(api_key="test-key")
        self.assertEqual(xai_p.name, "xai")
        self.assertTrue(xai_p.requires_api_key)

        custom_p = CustomOpenAIProvider(base_url="http://localhost:1234/v1")
        self.assertEqual(custom_p.name, "custom")
        self.assertFalse(custom_p.requires_api_key)


class TestProviderRegistryAndFactory(unittest.TestCase):
    """Verifica el registro central y la instanciación a través del factory."""

    def test_06_registered_providers(self):
        """Todos los 7 proveedores deben estar registrados en el factory."""
        providers = list_available_providers()
        for p in ["mock", "ollama", "openai", "anthropic", "gemini", "xai", "custom"]:
            self.assertIn(p, providers)
            self.assertTrue(is_provider_registered(p))

    def test_07_provider_metadata(self):
        """Cada proveedor registrado debe contar con metadata estructurada."""
        for p in ["ollama", "openai", "anthropic", "gemini", "xai", "custom", "mock"]:
            self.assertIn(p, PROVIDER_METADATA)
            meta = PROVIDER_METADATA[p]
            self.assertIn("display_name", meta)
            self.assertIn("requires_api_key", meta)
            self.assertIn("default_model", meta)

    def test_08_get_provider_unregistered_raises(self):
        """Solicitar un proveedor no registrado debe lanzar ProviderConfigError."""
        with self.assertRaises(ProviderConfigError):
            get_provider("inexistente_123")

    def test_09_get_default_provider_reads_settings(self):
        """get_default_provider debe resolver dinámicamente según settings y requerir AI_ALLOW_MOCK para mock."""
        with patch.object(settings, "get", side_effect=lambda k, fb=None: "mock" if k == "AI_PROVIDER" else fb), \
             patch.object(settings, "get_bool", side_effect=lambda k, fb=False: False if k == "AI_ALLOW_MOCK" else fb):
            with self.assertRaises(ProviderConfigError):
                get_default_provider(force_reload=True)

        with patch.object(settings, "get", side_effect=lambda k, fb=None: "mock" if k == "AI_PROVIDER" else fb), \
             patch.object(settings, "get_bool", side_effect=lambda k, fb=False: True if k == "AI_ALLOW_MOCK" else fb):
            p1 = get_default_provider(force_reload=True)
            self.assertIsInstance(p1, MockProvider)
            self.assertEqual(p1.name, "mock")


class TestSecurityAndKeyMasking(unittest.TestCase):
    """Verifica que las API Keys nunca se logueen en texto plano."""

    def test_10_mask_api_key_helper(self):
        """mask_api_key debe ocultar caracteres intermedios o retornar *** para claves cortas."""
        self.assertEqual(mask_api_key(""), "")
        self.assertEqual(mask_api_key(None), "")
        self.assertEqual(mask_api_key("12345"), "***")
        self.assertEqual(mask_api_key("12345678"), "***")
        masked = mask_api_key("sk-ant-api03-1234567890abcdef")
        self.assertTrue(masked.startswith("sk-"))
        self.assertTrue(masked.endswith("cdef"))
        self.assertNotIn("1234567890", masked)

    def test_11_settings_set_masks_secrets_in_logs(self):
        """Settings.set no debe emitir valores sensibles en los logs de depuración."""
        logger = logging.getLogger("aura.config")
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        logger.addHandler(handler)
        old_level = logger.level
        logger.setLevel(logging.DEBUG)

        try:
            secret = "sk-super-secret-key-9999"
            settings.set("OPENAI_API_KEY", secret)
            output = log_capture.getvalue()
            self.assertNotIn(secret, output)
            self.assertIn("OPENAI_API_KEY=", output)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
            settings.set("OPENAI_API_KEY", "")


class TestCloudProvidersWithoutKeys(unittest.TestCase):
    """Verifica que los proveedores en la nube manejen la ausencia de clave sin crashear."""

    def test_12_openai_without_key(self):
        p = OpenAIProvider(api_key="")
        ok, msg = p.health_check()
        self.assertFalse(ok)
        self.assertIn("no configurada", msg.lower())
        with self.assertRaises(ProviderConfigError):
            p.chat([ChatMessage(role="user", content="Hola")])

    def test_13_anthropic_without_key(self):
        p = AnthropicProvider(api_key="")
        ok, msg = p.health_check()
        self.assertFalse(ok)
        self.assertIn("no configurada", msg.lower())
        with self.assertRaises(ProviderConfigError):
            p.chat([ChatMessage(role="user", content="Hola")])

    def test_14_gemini_without_key(self):
        p = GeminiProvider(api_key="")
        ok, msg = p.health_check()
        self.assertFalse(ok)
        self.assertIn("no configurada", msg.lower())
        with self.assertRaises(ProviderConfigError):
            p.chat([ChatMessage(role="user", content="Hola")])

    def test_15_xai_without_key(self):
        p = XAIProvider(api_key="")
        ok, msg = p.health_check()
        self.assertFalse(ok)
        self.assertIn("no configurada", msg.lower())
        with self.assertRaises(ProviderConfigError):
            p.chat([ChatMessage(role="user", content="Hola")])

    def test_16_custom_without_url(self):
        p = CustomOpenAIProvider(base_url="")
        ok, msg = p.health_check()
        self.assertFalse(ok)
        self.assertIn("no configurada", msg.lower())


class TestFallbackMechanism(unittest.TestCase):
    """Verifica el comportamiento de FallbackProvider ante fallos de la nube."""

    def test_17_fallback_success_when_primary_fails(self):
        """Si el primario lanza excepción en chat(), debe conmutar al fallback y notificar una sola vez."""
        primary = MockProvider()
        primary.fail_next = True
        primary.PROVIDER_NAME = "openai"

        fallback = MockProvider()
        fallback.PROVIDER_NAME = "ollama"

        compound = FallbackProvider(primary=primary, fallback=fallback)

        msgs = [ChatMessage(role="user", content="Hola AURA")]

        # Primera llamada: debe fallar primary, ejecutar fallback y agregar aviso
        resp1 = compound.chat(msgs)
        self.assertIn("☁️ Falló openai, usando Ollama local", resp1.content)

        # Segunda llamada con primary aún fallando: debe seguir usando fallback pero SIN duplicar aviso
        primary.fail_next = True
        resp2 = compound.chat(msgs)
        self.assertNotIn("☁️ Falló openai, usando Ollama local", resp2.content)

    def test_18_fallback_streaming_when_primary_fails(self):
        """En streaming, si el primario falla, debe conmutar al stream del fallback y prefijar el aviso."""
        primary = MockProvider()
        primary.fail_next = True
        primary.PROVIDER_NAME = "anthropic"

        fallback = MockProvider()
        fallback.PROVIDER_NAME = "ollama"

        compound = FallbackProvider(primary=primary, fallback=fallback)
        msgs = [ChatMessage(role="user", content="Hola AURA")]

        stream = compound.chat_stream(msgs)
        first_chunk = next(stream)
        self.assertIn("☁️ Falló anthropic, usando Ollama local", first_chunk)

    def test_19_fallback_health_check(self):
        """health_check de FallbackProvider debe reportar disponibilidad si el fallback local funciona."""
        primary = OpenAIProvider(api_key="")  # No disponible
        fallback = MockProvider(fail_next=False)  # Disponible

        compound = FallbackProvider(primary=primary, fallback=fallback)
        ok, detail = compound.health_check()
        self.assertTrue(ok)
        self.assertIn("Falló openai", detail)
        self.assertIn("mock", detail)


class TestSettingsPageAIControls(unittest.TestCase):
    """Verifica que la página de configuración exponga todos los controles multi-proveedor requeridos."""

    def test_20_settings_page_ai_controls_present(self):
        import flet as ft
        from ui.pages.settings_page import SettingsPage

        mock_page = MagicMock(spec=ft.Page)
        sp = SettingsPage(page=mock_page)

        # Controles principales
        self.assertTrue(hasattr(sp, "_provider_dropdown"))
        self.assertTrue(hasattr(sp, "_api_key_field"))
        self.assertTrue(hasattr(sp, "_ollama_url_field"))
        self.assertTrue(hasattr(sp, "_custom_url_field"))
        self.assertTrue(hasattr(sp, "_custom_model_field"))
        self.assertTrue(hasattr(sp, "_model_dropdown"))
        self.assertTrue(hasattr(sp, "_fallback_checkbox"))
        self.assertTrue(hasattr(sp, "_test_conn_btn"))
        self.assertTrue(hasattr(sp, "_save_ai_btn"))
        self.assertTrue(hasattr(sp, "_ai_active_badge"))

        # El campo de API key debe ser de tipo password con toggle nativo
        self.assertTrue(sp._api_key_field.password)
        self.assertTrue(sp._api_key_field.can_reveal_password)

        # Opciones en dropdown
        opt_keys = [opt.key for opt in sp._provider_dropdown.options]
        for expected in ["ollama", "openai", "anthropic", "gemini", "xai", "custom"]:
            self.assertIn(expected, opt_keys)


class TestAIHttpClientAndModelCache(unittest.TestCase):
    """Verifica el cliente HTTP unificado y la caché de modelos de 10 minutos."""

    def test_21_format_key_loaded_helper(self):
        """format_key_loaded debe retornar 'key cargada: ...abcd' o cadena vacía."""
        from config.settings import format_key_loaded
        self.assertEqual(format_key_loaded(""), "")
        self.assertEqual(format_key_loaded(None), "")
        self.assertEqual(format_key_loaded("sk-ant-12345678"), "key cargada: ...5678")
        self.assertEqual(format_key_loaded("short"), "key cargada: ...hort")

    def test_22_http_client_401_auth_error(self):
        """Un error HTTP 401 debe transformarse en AuthenticationError."""
        from ai.http_client import AIHttpClient
        from ai.errors import AuthenticationError
        import requests

        client = AIHttpClient(provider_name="openai")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": {"message": "Invalid API key"}}

        with patch("requests.request", return_value=mock_resp):
            with self.assertRaises(AuthenticationError) as ctx:
                client.get("https://api.openai.com/v1/models")
            self.assertIn("401", str(ctx.exception))

    def test_23_http_client_404_model_not_found(self):
        """Un error HTTP 404 debe transformarse en ModelNotFoundError."""
        from ai.http_client import AIHttpClient
        from ai.errors import ModelNotFoundError

        client = AIHttpClient(provider_name="openai")
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"error": {"message": "Model not found"}}

        with patch("requests.request", return_value=mock_resp):
            with self.assertRaises(ModelNotFoundError):
                client.get("https://api.openai.com/v1/models/non-existent")

    def test_24_http_client_429_retry_and_backoff(self):
        """Error HTTP 429 debe disparar reintentos con backoff antes de fallar."""
        from ai.http_client import AIHttpClient
        import requests

        client = AIHttpClient(provider_name="openai", max_retries=2)
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.json.return_value = {"error": {"message": "Rate limit reached"}}

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"data": []}

        # Dos fallos 429 y luego 200
        with patch("requests.request", side_effect=[resp_429, resp_429, resp_200]) as mock_req:
            with patch("time.sleep") as mock_sleep:
                resp = client.get("https://api.openai.com/v1/models")
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(mock_req.call_count, 3)
                self.assertEqual(mock_sleep.call_count, 2)

    def test_25_http_client_connection_error_no_stacktrace(self):
        """Error de conexión de requests debe convertirse en ProviderNotAvailableError amigable."""
        from ai.http_client import AIHttpClient
        import requests

        client = AIHttpClient(provider_name="gemini")
        with patch("requests.request", side_effect=requests.exceptions.ConnectionError("Failed to connect")):
            with self.assertRaises(ProviderNotAvailableError) as ctx:
                client.get("https://generativelanguage.googleapis.com/v1beta/models")
            self.assertIn("Sin conexión a internet o el servidor no es alcanzable", str(ctx.exception))

    def test_26_http_client_timeout_error(self):
        """Timeout de requests debe transformarse en RequestTimeoutError."""
        from ai.http_client import AIHttpClient
        from ai.errors import RequestTimeoutError
        import requests

        client = AIHttpClient(provider_name="anthropic")
        with patch("requests.request", side_effect=requests.exceptions.Timeout("Read timed out")):
            with self.assertRaises(RequestTimeoutError) as ctx:
                client.post("https://api.anthropic.com/v1/messages", json_data={})
            self.assertIn("Tiempo de espera agotado", str(ctx.exception))

    def test_27_model_cache_ttl_and_clear(self):
        """ModelCache debe respetar el TTL y permitir invalidación."""
        from ai.http_client import ModelCache
        import time

        cache = ModelCache(ttl_seconds=10)
        cache.set("prov_a", ["m1", "m2"])
        self.assertEqual(cache.get("prov_a"), ["m1", "m2"])
        self.assertIsNone(cache.get("prov_b"))

        # Simular expiración de TTL
        with patch("time.time", return_value=time.time() + 15):
            self.assertIsNone(cache.get("prov_a"))

        # Inserción y limpieza manual
        cache.set("prov_c", ["m3"])
        cache.clear("prov_c")
        self.assertIsNone(cache.get("prov_c"))


class TestCloudProviderRESTEndpoints(unittest.TestCase):
    """Verifica que los adapters usen exactamente las rutas REST, headers y payloads requeridos."""

    def test_28_openai_endpoints_and_auth(self):
        """OpenAIProvider debe usar Bearer token, /chat/completions y gpt-4o-mini por defecto."""
        p = OpenAIProvider(api_key="sk-testkey-1234")
        self.assertEqual(p.default_model, "gpt-4o-mini")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hola humano"}}],
            "model": "gpt-4o-mini",
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }

        with patch("requests.request", return_value=mock_resp) as mock_req:
            resp = p.chat([ChatMessage(role="user", content="Hola")])
            self.assertEqual(resp.content, "Hola humano")
            # Verificar llamada HTTP
            args, kwargs = mock_req.call_args
            self.assertEqual(kwargs["method"], "POST")
            self.assertEqual(kwargs["url"], "https://api.openai.com/v1/chat/completions")
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer sk-testkey-1234")
            self.assertEqual(kwargs["json"]["model"], "gpt-4o-mini")

    def test_29_anthropic_endpoints_headers_and_system(self):
        """AnthropicProvider debe usar x-api-key, /messages y extraer system al campo raíz."""
        p = AnthropicProvider(api_key="sk-ant-testkey-5678")
        self.assertEqual(p.default_model, "claude-3-5-haiku-latest")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "Respuesta de Claude"}],
            "model": "claude-3-5-haiku-latest",
            "usage": {"input_tokens": 10, "output_tokens": 4},
        }

        with patch("requests.request", return_value=mock_resp) as mock_req:
            resp = p.chat(
                [
                    ChatMessage(role="system", content="Eres AURA"),
                    ChatMessage(role="user", content="Hola Claude"),
                ],
                system="Prompt adicional del sistema",
            )
            self.assertEqual(resp.content, "Respuesta de Claude")
            args, kwargs = mock_req.call_args
            self.assertEqual(kwargs["method"], "POST")
            self.assertEqual(kwargs["url"], "https://api.anthropic.com/v1/messages")
            self.assertEqual(kwargs["headers"]["x-api-key"], "sk-ant-testkey-5678")
            self.assertEqual(kwargs["headers"]["anthropic-version"], "2023-06-01")
            # System debe estar en el nivel superior y NO dentro de messages
            self.assertIn("system", kwargs["json"])
            self.assertIn("Eres AURA", kwargs["json"]["system"])
            self.assertIn("Prompt adicional del sistema", kwargs["json"]["system"])
            # Ningún mensaje dentro de "messages" debe tener role "system"
            for m in kwargs["json"]["messages"]:
                self.assertNotEqual(m["role"], "system")

    def test_30_gemini_endpoints_header_and_contents(self):
        """GeminiProvider debe usar x-goog-api-key, POST /models/{modelo}:generateContent y systemInstruction."""
        p = GeminiProvider(api_key="AIzaSyTestKey123")
        self.assertEqual(p.default_model, "gemini-2.0-flash")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{
                "content": {"parts": [{"text": "Respuesta de Gemini"}]}
            }],
            "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 3},
        }

        with patch("requests.request", return_value=mock_resp) as mock_req:
            resp = p.chat(
                [ChatMessage(role="user", content="Hola Gemini")],
                system="Eres una IA asistente.",
            )
            self.assertEqual(resp.content, "Respuesta de Gemini")
            args, kwargs = mock_req.call_args
            self.assertEqual(kwargs["method"], "POST")
            self.assertEqual(
                kwargs["url"],
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
            )
            self.assertEqual(kwargs["headers"]["x-goog-api-key"], "AIzaSyTestKey123")
            # contents y systemInstruction
            self.assertIn("contents", kwargs["json"])
            self.assertEqual(kwargs["json"]["contents"][0]["role"], "user")
            self.assertIn("systemInstruction", kwargs["json"])
            self.assertIn("Eres una IA asistente.", kwargs["json"]["systemInstruction"]["parts"][0]["text"])

    def test_31_xai_grok_endpoints(self):
        """XAIProvider debe usar api.x.ai/v1 y grok-2-latest por defecto."""
        p = XAIProvider(api_key="xai-test-key-999")
        self.assertEqual(p.default_model, "grok-2-latest")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Respuesta de Grok"}}],
            "model": "grok-2-latest",
            "usage": {"prompt_tokens": 4, "completion_tokens": 2},
        }

        with patch("requests.request", return_value=mock_resp) as mock_req:
            resp = p.chat([ChatMessage(role="user", content="Hola Grok")])
            self.assertEqual(resp.content, "Respuesta de Grok")
            args, kwargs = mock_req.call_args
            self.assertEqual(kwargs["url"], "https://api.x.ai/v1/chat/completions")
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer xai-test-key-999")

    def test_32_custom_openai_endpoints(self):
        """CustomOpenAIProvider debe usar CUSTOM_BASE_URL y CUSTOM_MODEL."""
        p = CustomOpenAIProvider(
            base_url="https://api.groq.com/openai/v1",
            api_key="gsk-testkey",
            model="llama-3.3-70b-versatile",
        )
        self.assertEqual(p.default_model, "llama-3.3-70b-versatile")
        self.assertFalse(p.requires_api_key)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Respuesta desde Groq"}}],
            "model": "llama-3.3-70b-versatile",
            "usage": {"prompt_tokens": 6, "completion_tokens": 3},
        }

        with patch("requests.request", return_value=mock_resp) as mock_req:
            resp = p.chat([ChatMessage(role="user", content="Hola Custom")])
            self.assertEqual(resp.content, "Respuesta desde Groq")
            args, kwargs = mock_req.call_args
            self.assertEqual(kwargs["url"], "https://api.groq.com/openai/v1/chat/completions")
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer gsk-testkey")


if __name__ == "__main__":
    unittest.main()


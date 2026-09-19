"""
AURA — Proveedor Google Gemini (Multi-proveedor)

Implementación del proveedor de IA usando la API REST de Google Generative AI (Gemini).
Usa requests a través de AIHttpClient unificado.

Endpoints exactos:
    GET  /models                                  → listar modelos disponibles (con caché de 10 min)
    POST /models/{modelo}:generateContent         → chat con contents y systemInstruction
    POST /models/{modelo}:streamGenerateContent?alt=sse → streaming SSE
"""

from __future__ import annotations

import json
from typing import Iterator

from ai.provider_interface import (
    AIProvider,
    ChatMessage,
    ChatResponse,
    ProviderStatus,
)
from ai.errors import (
    AuraAIError,
    ProviderNotAvailableError,
    ProviderConfigError,
    AuthenticationError,
    ModelNotFoundError,
    RequestTimeoutError,
    ResponseParseError,
)
from ai.http_client import AIHttpClient, model_cache
from config.settings import mask_api_key
from utils.logger import get_logger

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_DEFAULT_MODEL = "gemini-2.0-flash"

_RECOMMENDED_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-flash-latest",
]


class GeminiProvider(AIProvider):
    """
    Proveedor de IA para Google Gemini.
    Base: https://generativelanguage.googleapis.com/v1beta
    Header: x-goog-api-key: <key>
    """

    PROVIDER_NAME = "gemini"

    def __init__(
        self,
        api_key: str = "",
        model: str = _DEFAULT_MODEL,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: int | None = None,
        **kwargs,
    ):
        self._api_key = (api_key or "").strip()
        raw_model = (model or _DEFAULT_MODEL).strip()
        self._model = raw_model.replace("models/", "")
        self._base_url = (base_url or _DEFAULT_BASE_URL).strip().rstrip("/")
        self._logger = get_logger("aura.ai.gemini")
        self._http = AIHttpClient(provider_name=self.PROVIDER_NAME, timeout=timeout)
        self._logger.info(
            f"GeminiProvider inicializado — model={self._model}, "
            f"api_key={mask_api_key(self._api_key) if self._api_key else '(vacía)'}"
        )

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    @property
    def requires_api_key(self) -> bool:
        return True

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def default_model(self) -> str:
        return self._model

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AURA-Orion/1.0",
        }
        if self._api_key:
            headers["x-goog-api-key"] = self._api_key
        return headers

    def check_status(self) -> ProviderStatus:
        """
        Verifica disponibilidad, autenticación y capacidad REAL de chat con Google Gemini.
        Un proveedor solo está conectado si puede chatear (generateContent exitoso).
        """
        if not self._api_key:
            return ProviderStatus(
                available=False,
                message="API Key de Gemini no configurada.",
                provider=self.PROVIDER_NAME,
                models=_RECOMMENDED_MODELS,
            )

        cache_key = f"{self.PROVIDER_NAME}:{self._base_url}:{mask_api_key(self._api_key)}"
        cached = model_cache.get(cache_key)
        display_models = cached or _RECOMMENDED_MODELS

        if not cached:
            url = f"{self._base_url}/models"
            try:
                resp = self._http.get(url, headers=self._get_headers())
                data = resp.json()
                raw_models = data.get("models", [])
                models: list[str] = []
                for m in raw_models:
                    if isinstance(m, dict):
                        name = m.get("name", "")
                        methods = m.get("supportedGenerationMethods", [])
                        if "generateContent" in methods:
                            clean_name = name.replace("models/", "")
                            if "gemini" in clean_name:
                                models.append(clean_name)
                if models:
                    display_models = models
                    model_cache.set(cache_key, display_models[:20])
            except AuthenticationError as e:
                return ProviderStatus(available=False, message=e.reason, provider=self.PROVIDER_NAME, models=_RECOMMENDED_MODELS)
            except Exception as e:
                self._logger.debug(f"Error listando modelos en check_status: {e}")

        # Realizar prueba de chat real (generateContent mínimo)
        clean_model = (self._model or _DEFAULT_MODEL).replace("models/", "").strip()
        ping_url = f"{self._base_url}/models/{clean_model}:generateContent"
        ping_payload = {
            "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
            "generationConfig": {"temperature": 0.0},
        }

        try:
            self._http.post(ping_url, headers=self._get_headers(), json_data=ping_payload, timeout=10)
            return ProviderStatus(
                available=True,
                message=f"Conectado con Google Gemini ({len(display_models)} modelos)",
                provider=self.PROVIDER_NAME,
                models=display_models[:20],
            )
        except AuthenticationError as e:
            return ProviderStatus(available=False, message=e.reason, provider=self.PROVIDER_NAME, models=display_models[:20])
        except ModelNotFoundError as e:
            return ProviderStatus(
                available=False,
                message=f"404: Modelo '{clean_model}' no disponible. Seleccioná un modelo compatible en Configuración.",
                provider=self.PROVIDER_NAME,
                models=display_models[:20],
            )
        except AuraAIError as e:
            return ProviderStatus(available=False, message=e.reason, provider=self.PROVIDER_NAME, models=display_models[:20])
        except Exception as e:
            return ProviderStatus(available=False, message=f"Error al conectar con Gemini: {e}", provider=self.PROVIDER_NAME, models=display_models[:20])

    def list_models(self) -> list[str]:
        """Obtiene la lista de modelos disponibles usando caché de 10 minutos."""
        cache_key = f"{self.PROVIDER_NAME}:{self._base_url}:{mask_api_key(self._api_key)}"
        cached = model_cache.get(cache_key)
        if cached:
            return cached

        status = self.check_status()
        if not status.available:
            raise ProviderNotAvailableError(status.message, provider=self.PROVIDER_NAME)
        models = status.models or _RECOMMENDED_MODELS
        model_cache.set(cache_key, models)
        return models

    def _prepare_payload(
        self,
        messages: list[ChatMessage],
        temperature: float,
        max_tokens: int | None,
        system: str | None = None,
        **kwargs,
    ) -> dict:
        system_prompts: list[str] = []
        if system and str(system).strip():
            system_prompts.append(str(system).strip())

        contents = []
        for m in messages:
            content_text = str(m.content or "").strip()
            if m.role == "system":
                if content_text:
                    system_prompts.append(content_text)
            else:
                if not content_text:
                    continue
                role = "model" if m.role == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": content_text}]})

        if not contents:
            contents.append({"role": "user", "parts": [{"text": "Hola"}]})

        # Consolidar mensajes consecutivos del mismo rol requeridos por Gemini
        merged_contents = []
        for c in contents:
            if merged_contents and merged_contents[-1]["role"] == c["role"]:
                merged_contents[-1]["parts"][0]["text"] += "\n" + c["parts"][0]["text"]
            else:
                merged_contents.append(c)

        payload: dict = {
            "contents": merged_contents,
            "generationConfig": {
                "temperature": max(0.0, min(2.0, temperature)),
            },
        }
        if max_tokens and max_tokens > 0:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens
        if system_prompts:
            clean_sys = "\n\n".join(p for p in system_prompts if p and str(p).strip()).strip()
            if clean_sys:
                payload["systemInstruction"] = {
                    "parts": [{"text": clean_sys}]
                }

        if "repeat_penalty" in kwargs or "frequency_penalty" in kwargs:
            self._logger.debug("GeminiProvider: ignorando penalties (usando generationConfig estándar).")

        return payload

    def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        system: str | None = None,
        **kwargs,
    ) -> ChatResponse:
        """Envía una conversación a Gemini y retorna la respuesta completa."""
        if not self._api_key:
            raise ProviderConfigError("API Key de Gemini no configurada.", provider=self.PROVIDER_NAME)

        chosen_model = (model or self._model or _DEFAULT_MODEL).replace("models/", "").strip()
        url = f"{self._base_url}/models/{chosen_model}:generateContent"
        payload = self._prepare_payload(messages, temperature, max_tokens, system, **kwargs)

        resp = self._http.post(url, headers=self._get_headers(), json_data=payload)
        data = resp.json()

        candidates = data.get("candidates", [])
        content = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            content = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p)

        if not content and not candidates:
            raise ResponseParseError("Respuesta de Gemini sin candidatos", provider=self.PROVIDER_NAME)

        usage = data.get("usageMetadata", {})

        return ChatResponse(
            content=content,
            model=chosen_model,
            provider=self.PROVIDER_NAME,
            tokens_prompt=usage.get("promptTokenCount", 0),
            tokens_response=usage.get("candidatesTokenCount", 0),
            raw=data,
        )

    def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        system: str | None = None,
        **kwargs,
    ) -> Iterator[str]:
        """Versión streaming de Gemini usando SSE."""
        if not self._api_key:
            raise ProviderConfigError("API Key de Gemini no configurada.", provider=self.PROVIDER_NAME)

        chosen_model = (model or self._model or _DEFAULT_MODEL).replace("models/", "").strip()
        url = f"{self._base_url}/models/{chosen_model}:streamGenerateContent?alt=sse"
        payload = self._prepare_payload(messages, temperature, max_tokens, system, **kwargs)

        for line_str in self._http.stream_lines(url, headers=self._get_headers(), json_data=payload):
            line_str = line_str.strip()
            if not line_str.startswith("data: "):
                continue
            data_str = line_str[6:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk_data = json.loads(data_str)
                candidates = chunk_data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for p in parts:
                        if isinstance(p, dict):
                            txt = p.get("text", "")
                            if txt:
                                yield txt
            except json.JSONDecodeError:
                continue

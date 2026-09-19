"""
AURA — Proveedor OpenAI / Compatible (Multi-proveedor)

Implementación del proveedor de IA usando la API REST de OpenAI y endpoints
compatibles (xAI, Groq, DeepSeek, OpenRouter, LM Studio, etc.).
Usa requests puro a través de AIHttpClient con reintentos 429/5xx, timeouts configurables
y caché de modelos de 10 minutos.

API estándar OpenAI usada:
    GET  /models             → listar modelos disponibles
    POST /chat/completions   → chat con historial y streaming SSE
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

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o-mini"

_OPENAI_RECOMMENDED_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-3.5-turbo",
    "o1-mini",
]


class OpenAIProvider(AIProvider):
    """
    Proveedor de IA para OpenAI (ChatGPT) y servicios compatibles.
    """

    PROVIDER_NAME = "openai"

    def __init__(
        self,
        api_key: str = "",
        model: str = _DEFAULT_MODEL,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: int | None = None,
        **kwargs,
    ):
        self._api_key = (api_key or "").strip()
        self._model = (model or _DEFAULT_MODEL).strip()
        self._base_url = (base_url or _DEFAULT_BASE_URL).strip().rstrip("/")
        self._logger = get_logger("aura.ai.openai")
        self._http = AIHttpClient(provider_name=self.PROVIDER_NAME, timeout=timeout)
        self._logger.info(
            f"OpenAIProvider inicializado — url={self._base_url}, "
            f"model={self._model}, api_key={mask_api_key(self._api_key) if self._api_key else '(vacía)'}"
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

    def _get_recommended_models(self) -> list[str]:
        return list(_OPENAI_RECOMMENDED_MODELS)

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AURA-Orion/1.0",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def check_status(self) -> ProviderStatus:
        """Verifica disponibilidad y autenticación con la API."""
        if self.requires_api_key and not self._api_key:
            return ProviderStatus(
                available=False,
                message=f"API Key de {self.provider_name.upper()} no configurada.",
                provider=self.PROVIDER_NAME,
                models=self._get_recommended_models(),
            )

        if not self._base_url:
            return ProviderStatus(
                available=False,
                message="URL base del endpoint no configurada.",
                provider=self.PROVIDER_NAME,
                models=self._get_recommended_models(),
            )

        display_models = self._get_recommended_models()
        if not cached:
            url = f"{self._base_url}/models"
            try:
                resp = self._http.get(url, headers=self._get_headers())
                data = resp.json()
                models = [
                    m["id"] for m in data.get("data", [])
                    if isinstance(m, dict) and "id" in m
                ]
                chat_models = [m for m in models if any(k in m for k in ("gpt", "chat", "deepseek", "llama", "grok", "mistral", "qwen"))]
                display_models = chat_models or models or self._get_recommended_models()
                if display_models:
                    model_cache.set(cache_key, display_models[:20])
            except AuthenticationError as e:
                return ProviderStatus(available=False, message=e.reason, provider=self.PROVIDER_NAME, models=self._get_recommended_models())
            except Exception as e:
                self._logger.debug(f"Error listando modelos en check_status: {e}")
        else:
            display_models = cached

        # Realizar prueba de chat real (/chat/completions con max_tokens=5)
        ping_url = f"{self._base_url}/chat/completions"
        target_model = self._model or self.default_model or "gpt-4o-mini"
        ping_payload = {
            "model": target_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        }
        try:
            self._http.post(ping_url, headers=self._get_headers(), json_data=ping_payload, timeout=10)
            return ProviderStatus(
                available=True,
                message=f"Conectado con {self.provider_name.upper()} ({len(display_models)} modelos)",
                provider=self.PROVIDER_NAME,
                models=display_models[:20] or self._get_recommended_models(),
            )
        except AuthenticationError as e:
            return ProviderStatus(available=False, message=e.reason, provider=self.PROVIDER_NAME, models=self._get_recommended_models())
        except ModelNotFoundError as e:
            return ProviderStatus(available=False, message=e.reason, provider=self.PROVIDER_NAME, models=self._get_recommended_models())
        except AuraAIError as e:
            return ProviderStatus(available=False, message=e.reason, provider=self.PROVIDER_NAME, models=self._get_recommended_models())
        except Exception as e:
            return ProviderStatus(available=False, message=f"Error al conectar con {self._base_url}: {e}", provider=self.PROVIDER_NAME, models=self._get_recommended_models())

    def list_models(self) -> list[str]:
        """Obtiene la lista de modelos disponibles usando caché de 10 minutos."""
        cache_key = f"{self.PROVIDER_NAME}:{self._base_url}:{mask_api_key(self._api_key)}"
        cached = model_cache.get(cache_key)
        if cached:
            return cached

        status = self.check_status()
        if not status.available:
            raise ProviderNotAvailableError(status.message, provider=self.PROVIDER_NAME)
        models = status.models or self._get_recommended_models()
        model_cache.set(cache_key, models)
        return models

    def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        system: str | None = None,
        **kwargs,
    ) -> ChatResponse:
        """Envía una conversación y retorna la respuesta completa."""
        if self.requires_api_key and not self._api_key:
            raise ProviderConfigError(f"API Key de {self.provider_name.upper()} no configurada.", provider=self.PROVIDER_NAME)

        msgs = list(messages)
        if system:
            msgs = [ChatMessage(role="system", content=system)] + msgs

        chosen_model = model or self._model
        url = f"{self._base_url}/chat/completions"

        payload: dict = {
            "model": chosen_model,
            "messages": [m.to_dict() for m in msgs],
            "temperature": max(0.0, min(2.0, temperature)),
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        freq_pen = kwargs.get("frequency_penalty")
        if freq_pen is not None:
            try:
                payload["frequency_penalty"] = float(freq_pen)
            except (ValueError, TypeError):
                pass

        pres_pen = kwargs.get("presence_penalty")
        if pres_pen is not None:
            try:
                payload["presence_penalty"] = float(pres_pen)
            except (ValueError, TypeError):
                pass

        if "repeat_penalty" in kwargs:
            self._logger.debug("OpenAIProvider: repeat_penalty ignorado (no soportado por API OpenAI).")

        resp = self._http.post(url, headers=self._get_headers(), json_data=payload)
        data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            raise ResponseParseError("Respuesta sin 'choices'", provider=self.PROVIDER_NAME)

        content = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})

        return ChatResponse(
            content=content,
            model=chosen_model,
            provider=self.PROVIDER_NAME,
            tokens_prompt=usage.get("prompt_tokens", 0),
            tokens_response=usage.get("completion_tokens", 0),
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
        """Versión streaming usando Server-Sent Events (SSE)."""
        if self.requires_api_key and not self._api_key:
            raise ProviderConfigError(f"API Key de {self.provider_name.upper()} no configurada.", provider=self.PROVIDER_NAME)

        msgs = list(messages)
        if system:
            msgs = [ChatMessage(role="system", content=system)] + msgs

        chosen_model = model or self._model
        url = f"{self._base_url}/chat/completions"

        payload: dict = {
            "model": chosen_model,
            "messages": [m.to_dict() for m in msgs],
            "temperature": max(0.0, min(2.0, temperature)),
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        freq_pen = kwargs.get("frequency_penalty")
        if freq_pen is not None:
            try:
                payload["frequency_penalty"] = float(freq_pen)
            except (ValueError, TypeError):
                pass

        pres_pen = kwargs.get("presence_penalty")
        if pres_pen is not None:
            try:
                payload["presence_penalty"] = float(pres_pen)
            except (ValueError, TypeError):
                pass

        for line_str in self._http.stream_lines(url, headers=self._get_headers(), json_data=payload):
            line_str = line_str.strip()
            if not line_str.startswith("data: "):
                continue
            data_content = line_str[6:].strip()
            if data_content == "[DONE]":
                break
            try:
                chunk = json.loads(data_content)
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    text = delta.get("content")
                    if text:
                        yield text
            except json.JSONDecodeError:
                continue


_XAI_RECOMMENDED_MODELS = [
    "grok-2-latest",
    "grok-2",
    "grok-beta",
    "grok-2-vision-latest",
]


class XAIProvider(OpenAIProvider):
    """
    Proveedor de IA para xAI (Grok) con API compatible con OpenAI.
    Base: https://api.x.ai/v1
    """

    PROVIDER_NAME = "xai"
    _DEFAULT_XAI_URL = "https://api.x.ai/v1"
    _DEFAULT_XAI_MODEL = "grok-2-latest"

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
        base_url: str = _DEFAULT_XAI_URL,
        **kwargs,
    ):
        super().__init__(
            api_key=api_key,
            model=model or self._DEFAULT_XAI_MODEL,
            base_url=base_url or self._DEFAULT_XAI_URL,
            **kwargs,
        )
        self._logger = get_logger("aura.ai.xai")
        self._http = AIHttpClient(provider_name=self.PROVIDER_NAME)

    @property
    def default_model(self) -> str:
        """Retorna el primer modelo estable obtenido o grok-2-latest por defecto."""
        if self._model and self._model != self._DEFAULT_XAI_MODEL:
            return self._model
        cache_key = f"{self.PROVIDER_NAME}:{self._base_url}:{mask_api_key(self._api_key)}"
        cached = model_cache.get(cache_key)
        if cached:
            for m in cached:
                if "beta" not in m.lower():
                    return m
            return cached[0]
        return self._DEFAULT_XAI_MODEL

    def _get_recommended_models(self) -> list[str]:
        return list(_XAI_RECOMMENDED_MODELS)

    def check_status(self) -> ProviderStatus:
        if not self._api_key:
            return ProviderStatus(
                available=False,
                message="API Key de xAI (Grok) no configurada.",
                provider=self.PROVIDER_NAME,
                models=_XAI_RECOMMENDED_MODELS,
            )
        status = super().check_status()
        if not status.models:
            status.models = _XAI_RECOMMENDED_MODELS
        return status


class CustomOpenAIProvider(OpenAIProvider):
    """
    Proveedor de IA para cualquier endpoint compatible con OpenAI (Groq, DeepSeek, LM Studio, etc.).
    Base = CUSTOM_BASE_URL, auth = Bearer CUSTOM_API_KEY, modelo = CUSTOM_MODEL.
    """

    PROVIDER_NAME = "custom"
    _DEFAULT_CUSTOM_MODEL = "default"

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
        base_url: str = "",
        **kwargs,
    ):
        super().__init__(
            api_key=api_key,
            model=model or self._DEFAULT_CUSTOM_MODEL,
            base_url=base_url or "",
            **kwargs,
        )
        self._base_url = (base_url or "").strip().rstrip("/")
        self._logger = get_logger("aura.ai.custom")
        self._http = AIHttpClient(provider_name=self.PROVIDER_NAME)

    @property
    def requires_api_key(self) -> bool:
        # Los endpoints locales (LM Studio, LocalAI) pueden no requerir clave
        return False

    def _get_recommended_models(self) -> list[str]:
        return [self._model] if self._model else []

    def check_status(self) -> ProviderStatus:
        if not self._base_url:
            return ProviderStatus(
                available=False,
                message="URL base del endpoint personalizado no configurada.",
                provider=self.PROVIDER_NAME,
                models=self._get_recommended_models(),
            )
        return super().check_status()

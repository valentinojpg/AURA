"""
AURA — Proveedor Anthropic / Claude (Multi-proveedor)

Implementación del proveedor de IA usando la API REST de Anthropic (Claude).
Usa requests a través de AIHttpClient unificado.

Endpoints exactos:
    GET  /models    → listar modelos disponibles (con caché de 10 min)
    POST /messages  → chat con historial, campo "system" de nivel superior y streaming SSE
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

_DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
_DEFAULT_MODEL = "claude-3-5-haiku-latest"
_ANTHROPIC_VERSION = "2023-06-01"

_ANTHROPIC_RECOMMENDED_MODELS = [
    "claude-3-5-haiku-latest",
    "claude-3-5-sonnet-latest",
    "claude-3-opus-latest",
    "claude-3-5-haiku-20241022",
    "claude-3-5-sonnet-20241022",
    "claude-3-haiku-20240307",
]


class AnthropicProvider(AIProvider):
    """
    Proveedor de IA para Anthropic Claude.
    Base: https://api.anthropic.com/v1
    """

    PROVIDER_NAME = "anthropic"

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
        self._logger = get_logger("aura.ai.anthropic")
        self._http = AIHttpClient(provider_name=self.PROVIDER_NAME, timeout=timeout)
        self._logger.info(
            f"AnthropicProvider inicializado — model={self._model}, "
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
            "anthropic-version": _ANTHROPIC_VERSION,
        }
        if self._api_key:
            headers["x-api-key"] = self._api_key
        return headers

    def check_status(self) -> ProviderStatus:
        """Verifica disponibilidad y autenticación con Anthropic."""
        if not self._api_key:
            return ProviderStatus(
                available=False,
                message="API Key de Anthropic no configurada.",
                provider=self.PROVIDER_NAME,
                models=_ANTHROPIC_RECOMMENDED_MODELS,
            )

        display_models = _ANTHROPIC_RECOMMENDED_MODELS
        if not cached:
            url = f"{self._base_url}/models"
            try:
                resp = self._http.get(url, headers=self._get_headers())
                data = resp.json()
                models = [
                    m["id"] for m in data.get("data", [])
                    if isinstance(m, dict) and "id" in m
                ]
                display_models = models or _ANTHROPIC_RECOMMENDED_MODELS
                if display_models:
                    model_cache.set(cache_key, display_models[:20])
            except AuthenticationError as e:
                return ProviderStatus(available=False, message=e.reason, provider=self.PROVIDER_NAME, models=_ANTHROPIC_RECOMMENDED_MODELS)
            except Exception as e:
                self._logger.debug(f"Error listando modelos en check_status: {e}")
        else:
            display_models = cached

        # Realizar prueba de chat real (/messages con max_tokens=5)
        ping_url = f"{self._base_url}/messages"
        ping_payload = {
            "model": self._model or _DEFAULT_MODEL,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        }
        try:
            self._http.post(ping_url, headers=self._get_headers(), json_data=ping_payload, timeout=10)
            return ProviderStatus(
                available=True,
                message=f"Conectado con Anthropic ({len(display_models)} modelos)",
                provider=self.PROVIDER_NAME,
                models=display_models[:20],
            )
        except AuthenticationError as e:
            return ProviderStatus(available=False, message=e.reason, provider=self.PROVIDER_NAME, models=_ANTHROPIC_RECOMMENDED_MODELS)
        except ModelNotFoundError as e:
            return ProviderStatus(available=False, message=e.reason, provider=self.PROVIDER_NAME, models=_ANTHROPIC_RECOMMENDED_MODELS)
        except AuraAIError as e:
            return ProviderStatus(available=False, message=e.reason, provider=self.PROVIDER_NAME, models=_ANTHROPIC_RECOMMENDED_MODELS)
        except Exception as e:
            return ProviderStatus(available=False, message=f"Error al conectar con Anthropic: {e}", provider=self.PROVIDER_NAME, models=_ANTHROPIC_RECOMMENDED_MODELS)

    def list_models(self) -> list[str]:
        """Obtiene la lista de modelos disponibles usando caché de 10 minutos."""
        cache_key = f"{self.PROVIDER_NAME}:{self._base_url}:{mask_api_key(self._api_key)}"
        cached = model_cache.get(cache_key)
        if cached:
            return cached

        status = self.check_status()
        if not status.available:
            raise ProviderNotAvailableError(status.message, provider=self.PROVIDER_NAME)
        models = status.models or _ANTHROPIC_RECOMMENDED_MODELS
        model_cache.set(cache_key, models)
        return models

    def _prepare_payload(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int | None,
        system: str | None = None,
        stream: bool = False,
        **kwargs,
    ) -> dict:
        system_prompts: list[str] = []
        if system:
            system_prompts.append(system)

        anthropic_messages = []
        for m in messages:
            if m.role == "system":
                system_prompts.append(m.content)
            else:
                role = "assistant" if m.role == "assistant" else "user"
                anthropic_messages.append({"role": role, "content": m.content})

        if not anthropic_messages:
            anthropic_messages.append({"role": "user", "content": "Hola"})

        # Consolidar mensajes consecutivos del mismo rol requeridos por Claude
        merged: list[dict] = []
        for msg in anthropic_messages:
            if merged and merged[-1]["role"] == msg["role"]:
                merged[-1]["content"] += "\n" + msg["content"]
            else:
                merged.append(msg)

        payload: dict = {
            "model": model,
            "messages": merged,
            "max_tokens": max_tokens or 4096,
            "temperature": max(0.0, min(1.0, temperature)),
        }
        if system_prompts:
            payload["system"] = "\n\n".join(system_prompts)
        if stream:
            payload["stream"] = True

        if "repeat_penalty" in kwargs or "frequency_penalty" in kwargs:
            self._logger.debug("AnthropicProvider: ignorando penalties (no soportadas en la API Messages).")

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
        """Envía una conversación a Anthropic y retorna la respuesta completa."""
        if not self._api_key:
            raise ProviderConfigError("API Key de Anthropic no configurada.", provider=self.PROVIDER_NAME)

        chosen_model = model or self._model
        url = f"{self._base_url}/messages"
        payload = self._prepare_payload(messages, chosen_model, temperature, max_tokens, system, stream=False, **kwargs)

        resp = self._http.post(url, headers=self._get_headers(), json_data=payload)
        data = resp.json()

        content_blocks = data.get("content", [])
        text_parts = [
            b.get("text", "") for b in content_blocks
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        content = "".join(text_parts)
        usage = data.get("usage", {})

        return ChatResponse(
            content=content,
            model=chosen_model,
            provider=self.PROVIDER_NAME,
            tokens_prompt=usage.get("input_tokens", 0),
            tokens_response=usage.get("output_tokens", 0),
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
        """Versión streaming de Anthropic usando SSE."""
        if not self._api_key:
            raise ProviderConfigError("API Key de Anthropic no configurada.", provider=self.PROVIDER_NAME)

        chosen_model = model or self._model
        url = f"{self._base_url}/messages"
        payload = self._prepare_payload(messages, chosen_model, temperature, max_tokens, system, stream=True)

        for line_str in self._http.stream_lines(url, headers=self._get_headers(), json_data=payload):
            line_str = line_str.strip()
            if not line_str.startswith("data: "):
                continue
            data_str = line_str[6:].strip()
            if data_str == "[DONE]":
                break
            try:
                event_data = json.loads(data_str)
                evt_type = event_data.get("type")
                if evt_type == "content_block_delta":
                    delta = event_data.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text")
                        if text:
                            yield text
                elif evt_type == "message_stop":
                    break
            except json.JSONDecodeError:
                continue

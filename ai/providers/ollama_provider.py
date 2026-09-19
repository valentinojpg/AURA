"""
AURA — Proveedor Ollama (Fase 6)

Implementación real del proveedor de IA usando Ollama.
Usa únicamente urllib de la stdlib — sin dependencias externas nuevas.

API de Ollama usada:
    GET  /api/tags         → listar modelos instalados
    POST /api/chat         → chat con historial (formato OpenAI-compatible)
    POST /api/chat (stream)→ streaming de respuesta (NDJSON línea por línea)

Comportamiento ante errores:
    - Servicio no disponible → ProviderNotAvailableError
    - Modelo no encontrado   → ModelNotFoundError
    - Timeout                → RequestTimeoutError
    - JSON inválido          → ResponseParseError
    - Todos los errores se registran en logs antes de relanzarse.

Referencia de la API de Ollama:
    https://github.com/ollama/ollama/blob/main/docs/api.md
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Iterator

from ai.provider_interface import (
    AIProvider,
    ChatMessage,
    ChatResponse,
    ProviderStatus,
)
from ai.errors import (
    ProviderNotAvailableError,
    ModelNotFoundError,
    RequestTimeoutError,
    ResponseParseError,
)
from utils.logger import get_logger

# Timeout por defecto para peticiones HTTP (segundos)
_DEFAULT_TIMEOUT = 10
# Timeout extendido para chat (el modelo puede tardar más)
_CHAT_TIMEOUT = 120


class OllamaProvider(AIProvider):
    """
    Proveedor de IA que conecta AURA con Ollama (Fase 6).

    Ollama debe estar instalado y corriendo localmente.
    URL por defecto: http://localhost:11434

    Args:
        base_url: URL base del servidor Ollama (sin barra final).
        model: Nombre del modelo a usar por defecto.
        timeout: Timeout en segundos para peticiones de check/list.
        chat_timeout: Timeout en segundos para peticiones de chat.

    Ejemplo:
        provider = OllamaProvider(base_url="http://localhost:11434", model="qwen2.5:3b")
        response = provider.chat([ChatMessage(role="user", content="Hola")])
    """

    PROVIDER_NAME = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:3b",
        timeout: int = _DEFAULT_TIMEOUT,
        chat_timeout: int = _CHAT_TIMEOUT,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._chat_timeout = chat_timeout
        self._logger = get_logger("aura.ai.ollama")
        self._logger.info(
            f"OllamaProvider inicializado — url={self._base_url}, "
            f"model={self._model}, timeout={self._timeout}s"
        )

    # ── Propiedad ──────────────────────────────

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    @property
    def base_url(self) -> str:
        """URL base del servidor Ollama."""
        return self._base_url

    @property
    def default_model(self) -> str:
        """Modelo configurado por defecto."""
        return self._model

    # ──────────────────────────────────────────────
    # Métodos de la interfaz AIProvider
    # ──────────────────────────────────────────────

    def check_status(self) -> ProviderStatus:
        """
        Verifica si Ollama está corriendo consultando GET /api/tags.

        Nunca lanza excepciones — retorna ProviderStatus con available=False
        y el mensaje de error en caso de fallo.

        Returns:
            ProviderStatus con available, mensaje descriptivo y lista de modelos.
        """
        self._logger.debug("OllamaProvider.check_status() — GET /api/tags")
        url = f"{self._base_url}/api/tags"

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AURA/0.6.0", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                if resp.status != 200:
                    msg = f"Ollama respondió con código HTTP {resp.status}."
                    self._logger.warning(f"check_status: {msg}")
                    return ProviderStatus(
                        available=False,
                        message=msg,
                        provider=self.PROVIDER_NAME,
                    )

                body = resp.read().decode("utf-8")
                data = json.loads(body)
                models = [m.get("name", "?") for m in data.get("models", [])]

                if models:
                    msg = f"Ollama activo — {len(models)} modelo(s): {', '.join(models[:3])}"
                    if len(models) > 3:
                        msg += f" (+{len(models) - 3} más)"
                else:
                    msg = "Ollama activo — sin modelos descargados. Ejecutá: ollama pull qwen2.5:3b"

                self._logger.info(f"check_status OK: {msg}")
                return ProviderStatus(
                    available=True,
                    message=msg,
                    provider=self.PROVIDER_NAME,
                    models=models,
                )

        except urllib.error.URLError as e:
            reason = str(e.reason) if hasattr(e, "reason") else str(e)
            msg = f"No se pudo conectar con Ollama en {self._base_url}: {reason}"
            self._logger.warning(f"check_status FAIL: {msg}")
            return ProviderStatus(
                available=False,
                message=msg,
                provider=self.PROVIDER_NAME,
            )
        except json.JSONDecodeError as e:
            msg = f"Ollama respondió pero el JSON es inválido: {e}"
            self._logger.warning(f"check_status JSON error: {msg}")
            return ProviderStatus(
                available=False,
                message=msg,
                provider=self.PROVIDER_NAME,
            )
        except Exception as e:
            msg = f"Error inesperado al verificar Ollama: {e}"
            self._logger.error(f"check_status exception: {msg}", exc_info=True)
            return ProviderStatus(
                available=False,
                message=msg,
                provider=self.PROVIDER_NAME,
            )

    def list_models(self) -> list[str]:
        """
        Retorna la lista de modelos instalados en Ollama (GET /api/tags).

        Returns:
            Lista de nombres de modelos (ej: ['qwen2.5:3b', 'llama3.2:3b']).

        Raises:
            ProviderNotAvailableError: Si Ollama no está accesible.
            ResponseParseError: Si la respuesta tiene formato inesperado.
        """
        self._logger.debug("OllamaProvider.list_models() — GET /api/tags")
        url = f"{self._base_url}/api/tags"

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AURA/0.6.0", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8")
                data = json.loads(body)
                models = [m.get("name", "?") for m in data.get("models", [])]
                self._logger.info(f"list_models: {len(models)} modelos encontrados.")
                return models

        except urllib.error.URLError as e:
            reason = str(e.reason) if hasattr(e, "reason") else str(e)
            raise ProviderNotAvailableError(
                f"No se pudo conectar con Ollama: {reason}",
                provider=self.PROVIDER_NAME,
            ) from e
        except json.JSONDecodeError as e:
            raise ResponseParseError(
                f"Error al parsear la lista de modelos de Ollama: {e}",
                provider=self.PROVIDER_NAME,
            ) from e

    def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        system: str | None = None,
        **kwargs,
    ) -> ChatResponse:
        """
        Envía una conversación a Ollama (POST /api/chat) y espera la respuesta completa.

        Usa stream=False para obtener la respuesta en un solo JSON.

        Args:
            messages: Lista de ChatMessage con el historial de la conversación.
            model: Modelo a usar. Si None, usa self._model.
            temperature: Creatividad de la respuesta [0.0-1.0].
            max_tokens: Límite de tokens en la respuesta (None = sin límite).
            system: Instrucción de sistema opcional.

        Returns:
            ChatResponse con el texto completo de la respuesta.

        Raises:
            ProviderNotAvailableError: Si Ollama no responde.
            ModelNotFoundError: Si el modelo no está instalado.
            RequestTimeoutError: Si la solicitud supera el timeout.
            ResponseParseError: Si la respuesta no puede parsearse.
        """
        if system:
            messages = [ChatMessage(role="system", content=system)] + list(messages)

        used_model = model or self._model
        self._logger.debug(
            f"OllamaProvider.chat() — model={used_model}, "
            f"mensajes={len(messages)}, temp={temperature}"
        )

        payload = self._build_chat_payload(
            messages=messages,
            model=used_model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            **kwargs,
        )

        url = f"{self._base_url}/api/chat"
        response_data = self._post_json(url, payload, timeout=self._chat_timeout)

        return self._parse_chat_response(response_data, used_model)

    def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        system: str | None = None,
        **kwargs,
    ) -> Iterator[str]:
        """
        Streaming real: POST /api/chat con stream=True.

        Ollama devuelve líneas NDJSON (una por fragmento de texto).
        Este método las lee y emite los fragmentos de contenido incrementalmente.

        Args:
            messages: Lista de ChatMessage con el historial.
            model: Modelo a usar. Si None, usa self._model.
            temperature: Creatividad de la respuesta.
            max_tokens: Límite de tokens (None = sin límite).
            system: Instrucción de sistema opcional.
            **kwargs: Parámetros adicionales como repeat_penalty.

        Yields:
            Fragmentos de texto (str) de la respuesta.

        Raises:
            ProviderNotAvailableError: Si Ollama no responde.
            ModelNotFoundError: Si el modelo no está instalado.
            RequestTimeoutError: Si la solicitud supera el timeout.
            ResponseParseError: Si una línea del stream no puede parsearse.
        """
        if system:
            messages = [ChatMessage(role="system", content=system)] + list(messages)

        used_model = model or self._model
        self._logger.debug(
            f"OllamaProvider.chat_stream() — model={used_model}, mensajes={len(messages)}"
        )

        payload = self._build_chat_payload(
            messages=messages,
            model=used_model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )

        url = f"{self._base_url}/api/chat"
        body_bytes = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "AURA/0.6.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._chat_timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError as e:
                        raise ResponseParseError(
                            f"Error al parsear chunk de stream: {e} — línea: {line[:80]}",
                            provider=self.PROVIDER_NAME,
                        ) from e

                    # Extraer contenido del fragmento
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content

                    # done=True indica fin del stream
                    if chunk.get("done", False):
                        self._logger.debug(
                            f"Stream completado — "
                            f"prompt_tokens={chunk.get('prompt_eval_count', 0)}, "
                            f"response_tokens={chunk.get('eval_count', 0)}"
                        )
                        break

        except urllib.error.HTTPError as e:
            self._handle_http_error(e, used_model)
        except urllib.error.URLError as e:
            reason = str(e.reason) if hasattr(e, "reason") else str(e)
            if "timed out" in reason.lower():
                raise RequestTimeoutError(
                    f"Timeout en chat_stream con Ollama ({self._chat_timeout}s).",
                    provider=self.PROVIDER_NAME,
                ) from e
            raise ProviderNotAvailableError(
                "❌ No hay proveedor de IA disponible. Ollama no responde en localhost:11434 "
                "(inicialo con 'ollama serve') o configurá un proveedor con API key en Configuración.",
                provider=self.PROVIDER_NAME,
            ) from e

    # ──────────────────────────────────────────────
    # Helpers internos
    # ──────────────────────────────────────────────

    def _build_chat_payload(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int | None,
        stream: bool,
        **kwargs,
    ) -> dict:
        """Construye el payload JSON para la API de chat de Ollama."""
        options: dict[str, Any] = {
            "temperature": temperature,
        }
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        repeat_pen = kwargs.get("repeat_penalty")
        if repeat_pen is not None:
            try:
                options["repeat_penalty"] = float(repeat_pen)
            except (ValueError, TypeError):
                pass

        if "frequency_penalty" in kwargs or "presence_penalty" in kwargs:
            self._logger.debug("OllamaProvider: ignorando frequency/presence_penalty (se usa repeat_penalty).")

        payload: dict = {
            "model": model,
            "messages": [msg.to_dict() for msg in messages],
            "stream": stream,
            "options": options,
        }
        return payload

    def _post_json(self, url: str, payload: dict, timeout: int) -> dict:
        """
        Hace una petición POST con JSON y retorna el JSON de la respuesta.

        Raises:
            ProviderNotAvailableError, ModelNotFoundError,
            RequestTimeoutError, ResponseParseError
        """
        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "AURA/0.6.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)

        except urllib.error.HTTPError as e:
            self._handle_http_error(e, payload.get("model", "?"))
        except urllib.error.URLError as e:
            reason = str(e.reason) if hasattr(e, "reason") else str(e)
            if "timed out" in reason.lower():
                raise RequestTimeoutError(
                    f"Timeout al conectar con Ollama en {url} ({timeout}s).",
                    provider=self.PROVIDER_NAME,
                ) from e
            raise ProviderNotAvailableError(
                "❌ No hay proveedor de IA disponible. Ollama no responde en localhost:11434 "
                "(inicialo con 'ollama serve') o configurá un proveedor con API key en Configuración.",
                provider=self.PROVIDER_NAME,
            ) from e
        except json.JSONDecodeError as e:
            raise ResponseParseError(
                f"Error al parsear respuesta JSON de Ollama: {e}",
                provider=self.PROVIDER_NAME,
            ) from e

        # Nunca debería llegar aquí, pero satisface el type-checker
        raise ResponseParseError("Error desconocido en _post_json.", provider=self.PROVIDER_NAME)

    def _handle_http_error(self, e: urllib.error.HTTPError, model: str) -> None:
        """
        Traduce un HTTPError de Ollama a la excepción de AURA apropiada.

        Siempre lanza una excepción — nunca retorna.
        """
        try:
            error_body = e.read().decode("utf-8")
            error_data = json.loads(error_body)
            error_msg = error_data.get("error", str(e))
        except Exception:
            error_msg = str(e)

        self._logger.error(
            f"HTTP {e.code} de Ollama — model={model}: {error_msg}"
        )

        if e.code == 404 or "model" in error_msg.lower() and "not found" in error_msg.lower():
            raise ModelNotFoundError(
                f"Modelo '{model}' no encontrado en Ollama. "
                f"Ejecutá: ollama pull {model}",
                model=model,
                provider=self.PROVIDER_NAME,
            ) from e

        if e.code in (502, 503, 504):
            raise ProviderNotAvailableError(
                f"Ollama no disponible (HTTP {e.code}): {error_msg}",
                provider=self.PROVIDER_NAME,
            ) from e

        raise ProviderNotAvailableError(
            f"Error HTTP {e.code} de Ollama: {error_msg}",
            provider=self.PROVIDER_NAME,
        ) from e

    def _parse_chat_response(self, data: dict, model: str) -> ChatResponse:
        """
        Convierte el JSON de respuesta de Ollama en un ChatResponse.

        Raises:
            ResponseParseError: Si el JSON no tiene la estructura esperada.
        """
        try:
            message = data.get("message", {})
            content = message.get("content", "")

            if not content:
                raise ResponseParseError(
                    "La respuesta de Ollama no contiene 'message.content'.",
                    provider=self.PROVIDER_NAME,
                )

            return ChatResponse(
                content=content,
                model=data.get("model", model),
                provider=self.PROVIDER_NAME,
                done=data.get("done", True),
                tokens_prompt=data.get("prompt_eval_count", 0),
                tokens_response=data.get("eval_count", 0),
                raw=data,
            )
        except ResponseParseError:
            raise
        except Exception as e:
            raise ResponseParseError(
                f"Error al interpretar la respuesta de Ollama: {e}",
                provider=self.PROVIDER_NAME,
            ) from e

    def __repr__(self) -> str:
        return (
            f"OllamaProvider(url={self._base_url!r}, "
            f"model={self._model!r}, timeout={self._timeout}s)"
        )

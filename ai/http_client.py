"""
AURA — Cliente HTTP interno unificado para Proveedores de IA (Fase 57)

Provee:
- Llamadas HTTP usando requests puro (sin SDKs pesados de proveedores).
- Timeout configurable (AI_HTTP_TIMEOUT=30 por defecto).
- Reintentos con backoff exponencial SOLO para 429 (rate-limit) y 5xx (errores de servidor).
- Mapeo de errores semánticos legibles:
  * 401: API key inválida (401)
  * 403: Acceso denegado o permisos insuficientes (403)
  * 404: Modelo inexistente o recurso no encontrado (404)
  * 429: Límite de cuota o rate limit excedido (429)
  * 5xx: Error del servidor del proveedor (HTTP 5xx)
  * Timeout / Sin conexión: Mensaje claro y limpio sin stacktraces expuestos.
- Caché de 10 minutos (600s) para list_models() para evitar golpear las APIs REST en cada render.
- Garantía estricta de seguridad: las API keys NUNCA se imprimen en logs, URLs ni mensajes de error.
"""

from __future__ import annotations

import time
import requests
from typing import Iterator

from ai.errors import (
    AuraAIError,
    ProviderNotAvailableError,
    ProviderConfigError,
    AuthenticationError,
    ModelNotFoundError,
    RequestTimeoutError,
    ResponseParseError,
)
from config.settings import settings
from utils.logger import get_logger

_logger = get_logger("aura.ai.http")


class ModelCache:
    """
    Caché en memoria para list_models() con TTL de 10 minutos (600 segundos).
    Evita saturar endpoints de modelos en cada apertura de la UI de Configuración.
    """

    def __init__(self, ttl_seconds: int = 600):
        self._ttl = ttl_seconds
        # provider_key -> (timestamp, list[models])
        self._cache: dict[str, tuple[float, list[str]]] = {}

    def get(self, provider_key: str) -> list[str] | None:
        if provider_key in self._cache:
            ts, models = self._cache[provider_key]
            if time.time() - ts < self._ttl:
                _logger.debug(f"ModelCache: hit para '{provider_key}' ({len(models)} modelos en caché)")
                return list(models)
            else:
                _logger.debug(f"ModelCache: expirado para '{provider_key}' (TTL {self._ttl}s)")
                self._cache.pop(provider_key, None)
        return None

    def set(self, provider_key: str, models: list[str]) -> None:
        if models:
            self._cache[provider_key] = (time.time(), list(models))
            _logger.debug(f"ModelCache: guardados {len(models)} modelos para '{provider_key}'")

    def clear(self, provider_key: str | None = None) -> None:
        if provider_key:
            self._cache.pop(provider_key, None)
        else:
            self._cache.clear()


model_cache = ModelCache(ttl_seconds=600)


class AIHttpClient:
    """
    Cliente HTTP centralizado para todos los adapters de proveedores en la nube.
    """

    def __init__(
        self,
        provider_name: str,
        timeout: int | None = None,
        max_retries: int = 2,
    ):
        self.provider_name = provider_name
        self._custom_timeout = timeout
        self.max_retries = max_retries

    @property
    def timeout(self) -> int:
        if self._custom_timeout is not None:
            return self._custom_timeout
        return settings.get_int("AI_HTTP_TIMEOUT", 30)

    def request(
        self,
        method: str,
        url: str,
        headers: dict | None = None,
        json_data: dict | None = None,
        params: dict | None = None,
        timeout: int | None = None,
        stream: bool = False,
    ) -> requests.Response:
        """
        Ejecuta una petición HTTP con manejo de reintentos solo para 429 y 5xx.
        """
        used_timeout = timeout or self.timeout
        effective_headers = dict(headers or {})

        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.request(
                    method=method.upper(),
                    url=url,
                    headers=effective_headers,
                    json=json_data,
                    params=params,
                    timeout=used_timeout,
                    stream=stream,
                )
                # Regla de codificación obligatoria: fijar UTF-8 explícito en todas las respuestas
                resp.encoding = "utf-8"

                # Si es 429 o 5xx y aún tenemos intentos, esperar con backoff y reintentar
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    wait_sec = 1.0 * (attempt + 1)
                    _logger.warning(
                        f"[{self.provider_name}] Recibido HTTP {resp.status_code}. "
                        f"Reintentando ({attempt + 1}/{self.max_retries}) en {wait_sec:.1f}s..."
                    )
                    time.sleep(wait_sec)
                    continue

                # Validar códigos de error HTTP de forma legible
                if resp.status_code >= 400:
                    self._handle_http_error(resp)

                return resp

            except requests.exceptions.Timeout as e:
                _logger.error(f"[{self.provider_name}] Timeout de red agotado ({used_timeout}s).")
                raise RequestTimeoutError(
                    f"[{self.provider_name}] Tiempo de espera agotado ({used_timeout}s)",
                    provider=self.provider_name,
                    detail=f"tiempo de espera agotado ({used_timeout}s)",
                ) from e

            except requests.exceptions.ConnectionError as e:
                _logger.error(f"[{self.provider_name}] Fallo de conexión o sin internet: {e}")
                raise ProviderNotAvailableError(
                    f"[{self.provider_name}] Sin conexión a internet o el servidor no es alcanzable",
                    provider=self.provider_name,
                    detail="sin internet o servidor inalcanzable",
                ) from e

            except requests.exceptions.RequestException as e:
                # Si ya es un AuraAIError lanzado en _handle_http_error, relanzarlo
                _logger.error(f"[{self.provider_name}] Error en request: {e}")
                raise ProviderNotAvailableError(
                    f"red: error de solicitud ({e})",
                    provider=self.provider_name,
                    detail=str(e),
                ) from e

        # Fallback de seguridad si sale del loop sin retornar
        raise ProviderNotAvailableError(
            f"No se pudo completar la solicitud a {self.provider_name} tras {self.max_retries} reintentos.",
            provider=self.provider_name,
        )

    def _handle_http_error(self, resp: requests.Response) -> None:
        """Traduce códigos de estado HTTP a excepciones legibles de AURA y loguea body sin keys."""
        import re
        code = resp.status_code

        # Loguear status + primeros 200 caracteres del body (SIN la key) en logs/
        try:
            resp.encoding = "utf-8"
        except Exception:
            pass
        raw_text = getattr(resp, "text", "")
        if not isinstance(raw_text, str):
            raw_text = ""
        clean_snippet = raw_text[:200].replace("\r", " ").replace("\n", " ")
        clean_snippet = re.sub(r"(sk-[a-zA-Z0-9_-]{8,})", r"sk-...***", clean_snippet)
        clean_snippet = re.sub(r"(AQ\.[a-zA-Z0-9_-]{8,})", r"AQ....***", clean_snippet)
        for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "CUSTOM_API_KEY"):
            val = settings.get(k, "")
            if val and len(val) > 4:
                clean_snippet = clean_snippet.replace(val, "***")

        _logger.error(f"[{self.provider_name}] HTTP {code}: {clean_snippet}")

        # Intentar extraer mensaje de error del cuerpo JSON sin filtrar keys
        err_detail = ""
        try:
            body = resp.json()
            if isinstance(body, dict):
                # Formato OpenAI / xAI
                if "error" in body:
                    err_obj = body["error"]
                    err_detail = err_obj.get("message", "") if isinstance(err_obj, dict) else str(err_obj)
                # Formato Anthropic
                elif "error" in body and isinstance(body["error"], dict):
                    err_detail = body["error"].get("message", "")
                # Formato Gemini
                elif "error" in body and isinstance(body["error"], dict):
                    err_detail = body["error"].get("message", "")
        except Exception:
            err_detail = clean_snippet[:100]

        if err_detail:
            for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "CUSTOM_API_KEY"):
                val = settings.get(k, "")
                if val and len(val) > 4:
                    err_detail = err_detail.replace(val, "***")

        if "api key" in err_detail.lower() and ("not valid" in err_detail.lower() or "invalid" in err_detail.lower()):
            clean_msg = "API key inválida"
            raise AuthenticationError("401: API key inválida", provider=self.provider_name, status_code=401, detail=clean_msg)
        elif code == 400:
            clean_msg = err_detail or "solicitud o payload inválido"
            raise ProviderConfigError(f"400: {clean_msg}", provider=self.provider_name, status_code=400, detail=clean_msg)
        elif code == 401:
            clean_msg = "API key inválida"
            raise AuthenticationError("401: API key inválida", provider=self.provider_name, status_code=401, detail=clean_msg)
        elif code == 403:
            clean_msg = err_detail or "acceso denegado o API key sin permisos"
            raise AuthenticationError(f"403: {clean_msg}", provider=self.provider_name, status_code=403, detail=clean_msg)
        elif code == 404:
            clean_msg = err_detail or "modelo no disponible o recurso no encontrado"
            raise ModelNotFoundError(
                f"404: {clean_msg}",
                provider=self.provider_name,
                status_code=404,
                detail=clean_msg,
            )
        elif code == 429:
            clean_msg = err_detail or "límite de cuota o rate limit excedido"
            raise ProviderNotAvailableError(
                f"429: {clean_msg}",
                provider=self.provider_name,
                status_code=429,
                detail=clean_msg,
            )
        elif code >= 500:
            clean_msg = f"error del servidor del proveedor (HTTP {code})"
            raise ProviderNotAvailableError(
                f"{code}: {clean_msg}",
                provider=self.provider_name,
                status_code=code,
                detail=clean_msg,
            )
        else:
            clean_msg = err_detail or f"error HTTP {code}"
            raise ProviderNotAvailableError(
                f"{code}: {clean_msg}",
                provider=self.provider_name,
                status_code=code,
                detail=clean_msg,
            )

    def get(
        self,
        url: str,
        headers: dict | None = None,
        params: dict | None = None,
        timeout: int | None = None,
    ) -> requests.Response:
        return self.request("GET", url, headers=headers, params=params, timeout=timeout)

    def post(
        self,
        url: str,
        headers: dict | None = None,
        json_data: dict | None = None,
        params: dict | None = None,
        timeout: int | None = None,
        stream: bool = False,
    ) -> requests.Response:
        return self.request("POST", url, headers=headers, json_data=json_data, params=params, timeout=timeout, stream=stream)

    def stream_lines(
        self,
        url: str,
        headers: dict | None = None,
        json_data: dict | None = None,
        timeout: int | None = None,
    ) -> Iterator[str]:
        """
        Inicia un stream HTTP y genera líneas decodificadas una a una.
        """
        resp = self.post(url, headers=headers, json_data=json_data, timeout=timeout, stream=True)
        resp.encoding = "utf-8"
        for line in resp.iter_lines(decode_unicode=True):
            if line:
                yield line

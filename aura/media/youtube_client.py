"""
AURA — Cliente YouTube Data API v3 y Caché de Consultas Multimedia (Fase 79).

Permite resolver búsquedas musicales directamente a identificadores de video (videoId)
para reproducción automática en YouTube Music (/watch?v=<videoId>), con caché
persistente en disco (TTL 30 días) y degradación transparente ante errores.
"""

from __future__ import annotations

from datetime import datetime
import html
import json
from pathlib import Path
import re
import threading
import time
from typing import Any, Optional

import requests

from config.settings import settings
from utils.logger import get_logger

_logger = get_logger("aura.media.youtube")

# Ruta de caché persistente (Fase 79)
_CACHE_FILE = Path("data/learning/media_cache.json")
_CACHE_TTL_SECONDS = 30 * 86400  # 30 días
_cache_lock = threading.Lock()


def load_media_cache() -> dict[str, Any]:
    """Carga el diccionario de caché desde disco de forma segura."""
    if not _CACHE_FILE.exists():
        return {}
    try:
        with _CACHE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as ex:
        _logger.warning("Error al leer caché multimedia '%s': %s", _CACHE_FILE, ex)
    return {}


def save_media_cache(cache: dict[str, Any]) -> None:
    """Guarda el diccionario de caché en disco de forma atómica."""
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_file = _CACHE_FILE.with_suffix(".tmp")
        with temp_file.open("w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        temp_file.replace(_CACHE_FILE)
    except Exception as ex:
        _logger.warning("Error al guardar caché multimedia '%s': %s", _CACHE_FILE, ex)


def get_cached_video(norm_query: str) -> Optional[dict[str, Any]]:
    """
    Busca una consulta en la caché local.
    Retorna los datos del video si existe y tiene menos de 30 días de antigüedad.
    """
    key = norm_query.lower().strip()
    with _cache_lock:
        cache = load_media_cache()
        entry = cache.get(key)
        if not entry or not isinstance(entry, dict):
            return None

        ts = entry.get("timestamp", 0)
        age = time.time() - ts
        if age < _CACHE_TTL_SECONDS:
            return entry
        else:
            # Entrada expirada (> 30 días)
            _logger.debug("Caché multimedia expirada para '%s' (edad: %.1f días)", key, age / 86400)
            return None


def set_cached_video(norm_query: str, video_id: str, title: str, channel: str) -> None:
    """Registra una búsqueda exitosa en la caché local."""
    key = norm_query.lower().strip()
    with _cache_lock:
        cache = load_media_cache()
        cache[key] = {
            "video_id": video_id,
            "title": title,
            "channel": channel,
            "timestamp": time.time(),
            "fecha": datetime.now().isoformat(),
        }
        save_media_cache(cache)


def normalize_media_query(query: str) -> str:
    """
    Normaliza el término de búsqueda para la API de YouTube.
    Si viene 'pon X de Y' o 'X de Y', separa título y artista resultando en 'X Y'.
    Limpia comillas, caracteres redundantes y espacios sobrantes.
    """
    q = query.strip().strip("'\"`´«»")

    # Si contiene separador " de " (ej: "'Bad Romance' de Lady Gaga" o "Bad Romance de Lady Gaga")
    if " de " in q.lower():
        parts = re.split(r"\s+de\s+", q, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            clean_title = parts[0].strip().strip("'\"`´«»")
            clean_artist = parts[1].strip().strip("'\"`´«»")
            q = f"{clean_title} {clean_artist}"

    # Limpiar comillas internas y normalizar espacios
    q = re.sub(r"['\"`´«»]", "", q)
    return re.sub(r"\s+", " ", q).strip()


def search_youtube_video(
    query: str,
    api_key: Optional[str] = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """
    Consulta YouTube Data API v3 para obtener el videoId y metadatos de una búsqueda.

    Flujo:
    1. Normalización de query.
    2. Chequeo de caché local (TTL 30 días). Si hay hit, retorna sin gastar cuota.
    3. Petición GET a https://www.googleapis.com/youtube/v3/search.
    4. Guardado en caché si 200 OK y resultado válido.
    5. Mapeo de errores accionables (400, 403, 404, timeout).

    Retorna diccionario con estructura:
      {
        "success": bool,
        "video_id": str | None,
        "title": str | None,
        "channel": str | None,
        "cached": bool,
        "reason": str | None,
        "error": str | None,
        "status_code": int | None,
        "elapsed_ms": int,
      }
    """
    norm_q = normalize_media_query(query)
    start_time = time.time()

    if not api_key:
        api_key = settings.get("MEDIA_YT_API_KEY", "").strip()

    if not api_key:
        return {
            "success": False,
            "video_id": None,
            "title": None,
            "channel": None,
            "cached": False,
            "reason": "no_key",
            "error": "No hay YouTube API key configurada",
            "status_code": None,
            "elapsed_ms": 0,
        }

    # 1. Verificar caché local
    cached = get_cached_video(norm_q)
    if cached:
        elapsed_ms = int((time.time() - start_time) * 1000)
        _logger.info(
            "media_play: Cache HIT para '%s' -> videoId=%s | '%s' [%s] (0 API calls, %d ms)",
            norm_q,
            cached.get("video_id"),
            cached.get("title"),
            cached.get("channel"),
            elapsed_ms,
        )
        return {
            "success": True,
            "video_id": cached.get("video_id"),
            "title": cached.get("title"),
            "channel": cached.get("channel"),
            "cached": True,
            "reason": None,
            "error": None,
            "status_code": 200,
            "elapsed_ms": elapsed_ms,
        }

    # 2. Llamada a YouTube Data API v3
    endpoint = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "type": "video",
        "maxResults": 1,
        "safeSearch": "none",
        "q": norm_q,
        "key": api_key,
    }
    headers = {"User-Agent": "AURA-Orion/1.4.9"}

    try:
        resp = requests.get(endpoint, params=params, headers=headers, timeout=timeout)
        elapsed_ms = int((time.time() - start_time) * 1000)
        status = resp.status_code

        if status == 200:
            data = resp.json()
            items = data.get("items", [])
            if items:
                first = items[0]
                video_id = first.get("id", {}).get("videoId")
                snippet = first.get("snippet", {})
                title = html.unescape(snippet.get("title", ""))
                channel = html.unescape(snippet.get("channelTitle", ""))

                if video_id:
                    # Guardar en caché persistente
                    set_cached_video(norm_q, video_id, title, channel)
                    _logger.info(
                        "media_play: Cache MISS -> YouTube API HTTP 200 en %d ms | query='%s' -> videoId=%s | '%s' [%s]",
                        elapsed_ms,
                        norm_q,
                        video_id,
                        title,
                        channel,
                    )
                    return {
                        "success": True,
                        "video_id": video_id,
                        "title": title,
                        "channel": channel,
                        "cached": False,
                        "reason": None,
                        "error": None,
                        "status_code": 200,
                        "elapsed_ms": elapsed_ms,
                    }

            # 0 resultados
            _logger.warning(
                "media_play: YouTube API HTTP 200 pero 0 resultados para query='%s' (%d ms)",
                norm_q,
                elapsed_ms,
            )
            return {
                "success": False,
                "video_id": None,
                "title": None,
                "channel": None,
                "cached": False,
                "reason": "no_results",
                "error": "No se encontraron videos para la búsqueda indicada",
                "status_code": 404,
                "elapsed_ms": elapsed_ms,
            }

        elif status == 400:
            _logger.warning(
                "media_play: YouTube API HTTP 400 (Key inválida) para query='%s' (%d ms)",
                norm_q,
                elapsed_ms,
            )
            return {
                "success": False,
                "video_id": None,
                "title": None,
                "channel": None,
                "cached": False,
                "reason": "invalid_key",
                "error": "API key de YouTube inválida (HTTP 400)",
                "status_code": 400,
                "elapsed_ms": elapsed_ms,
            }

        elif status == 403:
            _logger.warning(
                "media_play: YouTube API HTTP 403 (Quota excedida o API deshabilitada) para query='%s' (%d ms)",
                norm_q,
                elapsed_ms,
            )
            return {
                "success": False,
                "video_id": None,
                "title": None,
                "channel": None,
                "cached": False,
                "reason": "quota_or_disabled",
                "error": "Quota de YouTube API superada o YouTube Data API v3 no habilitada (HTTP 403)",
                "status_code": 403,
                "elapsed_ms": elapsed_ms,
            }

        else:
            _logger.warning(
                "media_play: YouTube API HTTP %d inesperado para query='%s' (%d ms)",
                status,
                norm_q,
                elapsed_ms,
            )
            return {
                "success": False,
                "video_id": None,
                "title": None,
                "channel": None,
                "cached": False,
                "reason": f"http_{status}",
                "error": f"Error del servidor YouTube (HTTP {status})",
                "status_code": status,
                "elapsed_ms": elapsed_ms,
            }

    except requests.Timeout:
        elapsed_ms = int((time.time() - start_time) * 1000)
        _logger.warning("media_play: Timeout de red (%ds) al consultar YouTube API para '%s'", timeout, norm_q)
        return {
            "success": False,
            "video_id": None,
            "title": None,
            "channel": None,
            "cached": False,
            "reason": "timeout",
            "error": "Timeout de red al conectar con YouTube API",
            "status_code": None,
            "elapsed_ms": elapsed_ms,
        }

    except Exception as ex:
        elapsed_ms = int((time.time() - start_time) * 1000)
        _logger.warning("media_play: Excepción de conexión (%s) al consultar YouTube API: %s", type(ex).__name__, ex)
        return {
            "success": False,
            "video_id": None,
            "title": None,
            "channel": None,
            "cached": False,
            "reason": "network_error",
            "error": f"Error de conexión con YouTube API: {ex}",
            "status_code": None,
            "elapsed_ms": elapsed_ms,
        }


def test_youtube_api_key(api_key: str, timeout: float = 10.0) -> tuple[bool, str]:
    """
    Prueba una clave de API de YouTube realizando una consulta mínima (q='test', maxResults=1).
    Retorna una tupla (es_valida, mensaje_descriptivo).
    """
    k = api_key.strip()
    if not k:
        return False, "❌ La clave de API no puede estar vacía."

    endpoint = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "type": "video",
        "maxResults": 1,
        "q": "test",
        "key": k,
    }
    try:
        resp = requests.get(endpoint, params=params, timeout=timeout)
        if resp.status_code == 200:
            return True, "✅ Key válida y YouTube Data API v3 operativa."
        elif resp.status_code == 400:
            return False, "❌ Key inválida (HTTP 400)."
        elif resp.status_code == 403:
            return False, "❌ Quota superada o YouTube Data API v3 no habilitada en Google Cloud Console (HTTP 403)."
        else:
            return False, f"❌ Respuesta inesperada de YouTube (HTTP {resp.status_code})."
    except requests.Timeout:
        return False, "❌ Timeout de red al contactar Google Cloud (10 s)."
    except Exception as ex:
        return False, f"❌ Error de conexión: {ex}"

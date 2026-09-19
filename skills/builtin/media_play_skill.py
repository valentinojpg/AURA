# -*- coding: utf-8 -*-
"""
================================================================================
AURA — MediaPlaySkill: Reproducción y Búsqueda Multimedia (Fase 71)
================================================================================
Permite buscar y reproducir música, videos y pistas en servicios soportados:
  - YouTube Music: https://music.youtube.com/search?q=<query>
  - YouTube:       https://www.youtube.com/results?search_query=<query>
  - Spotify:       spotify:search:<query> (o web si no está instalado)

Configuración (.env):
  MEDIA_SERVICE=youtube_music (default: youtube_music | youtube | spotify)

Nota arquitectónica (v1 honesta):
  Abre el servicio correspondiente con la búsqueda ya cargada y lista.
  Pendiente v2: Autoplay real directo mediante APIs/SDKs de proveedores.
================================================================================
"""

from __future__ import annotations

import os
import shutil
import subprocess
import urllib.parse
import webbrowser

from config.settings import settings
from skills.skill_base import BaseSkill, SkillMeta, SkillResult, CATEGORY_WEB
from utils.logger import get_logger

_logger = get_logger("aura.skills.media_play")

_META = SkillMeta(
    name="media_play",
    version="1.0.0",
    display_name="Media Play",
    description="Búsqueda y reproducción de música en YouTube Music, YouTube y Spotify.",
    author="AURA",
    category=CATEGORY_WEB,
    commands=["reproducir", "play", "buscar"],
)


def is_spotify_installed() -> bool:
    """Verifica si la aplicación de escritorio de Spotify está disponible en Windows."""
    try:
        from core.app_resolver import resolve_app
        res = resolve_app("spotify")
        if res.success:
            return True
    except Exception:
        pass

    local_app = os.environ.get("LOCALAPPDATA", "")
    if local_app:
        spotify_paths = [
            os.path.join(local_app, "Microsoft", "WindowsApps", "Spotify.exe"),
            os.path.join(local_app, "Spotify", "Spotify.exe"),
        ]
        for p in spotify_paths:
            if os.path.exists(p):
                return True

    return shutil.which("spotify") is not None


def normalize_service_name(service: str | None) -> str:
    """Normaliza el identificador del servicio multimedia."""
    if not service:
        service = settings.get("MEDIA_SERVICE", "youtube_music")
    s = str(service).lower().strip()
    if s in ("youtube_music", "ytmusic", "youtube music", "yt music", "music"):
        return "youtube_music"
    if s in ("youtube", "yt", "video"):
        return "youtube"
    if s in ("spotify", "spoti"):
        return "spotify"
    return "youtube_music"


def build_media_url(query: str, service: str | None = None) -> tuple[str, str, bool]:
    """
    Construye la URL o URI de búsqueda directa para el servicio indicado.

    Retorna:
        (url_o_uri, nombre_para_mostrar, es_protocolo_nativo)
    """
    svc = normalize_service_name(service)
    clean_q = query.strip().strip("'\"`´")

    if svc == "youtube_music":
        encoded = urllib.parse.quote_plus(clean_q)
        return f"https://music.youtube.com/search?q={encoded}", "YouTube Music", False

    if svc == "youtube":
        encoded = urllib.parse.quote_plus(clean_q)
        return f"https://www.youtube.com/results?search_query={encoded}", "YouTube", False

    if svc == "spotify":
        if is_spotify_installed():
            encoded = urllib.parse.quote(clean_q)
            return f"spotify:search:{encoded}", "Spotify", True
        else:
            encoded = urllib.parse.quote_plus(clean_q)
            return f"https://open.spotify.com/search/{encoded}", "Spotify Web", False

    encoded = urllib.parse.quote_plus(clean_q)
    return f"https://music.youtube.com/search?q={encoded}", "YouTube Music", False


class MediaPlaySkill(BaseSkill):
    """
    Skill para reproducción y búsqueda multimedia en servicios de streaming.
    """

    META = _META

    def _open_in_browser(self, url: str) -> None:
        """Abre una URL en el navegador preferido de AURA o en el navegador del sistema."""
        try:
            from core.app_resolver import resolve_app, launch_app
            browser_res = resolve_app("navegador")
            if browser_res.success and browser_res.executable and os.path.isfile(browser_res.executable):
                launch_app(browser_res.executable, [url])
                return
        except Exception:
            pass
        webbrowser.open(url, new=2)

    def execute(self, command: str, args: list[str]) -> SkillResult:
        """
        Ejecuta la búsqueda / reproducción multimedia (Fase 79 v2).

        Args:
            command: 'reproducir', 'play' o 'buscar'
            args: [query] o [query, servicio]
        """
        if not args:
            return SkillResult(
                success=False,
                output="",
                error="Debes indicar qué canción, video o pista deseas reproducir.",
            )

        raw_query = args[0].strip()
        service_arg = None
        if len(args) > 1:
            if args[1] == "--service" and len(args) > 2:
                service_arg = args[2].strip()
            elif args[1] != "--service":
                service_arg = args[1].strip()

        if not raw_query:
            return SkillResult(
                success=False,
                output="",
                error="El término de búsqueda no puede estar vacío.",
            )

        svc = normalize_service_name(service_arg)

        # 1. Spotify (v1 / roadmap v3): protocolo nativo o web
        if svc == "spotify":
            url, display_name, is_native = build_media_url(raw_query, svc)
            _logger.info(f"MediaPlaySkill: abriendo '{raw_query}' en {display_name} -> {url}")
            try:
                if is_native:
                    if hasattr(os, "startfile"):
                        os.startfile(url)
                    else:
                        subprocess.Popen(["cmd", "/c", "start", "", url], shell=True)
                else:
                    self._open_in_browser(url)

                msg = f"🎵 Búsqueda de '{raw_query}' lista en {display_name}."
                return SkillResult(
                    success=True,
                    output=msg,
                    data={
                        "query": raw_query,
                        "service": display_name,
                        "url": url,
                        "native": is_native,
                    },
                )
            except Exception as exc:
                _logger.error(f"MediaPlaySkill: error al abrir {url}: {exc}", exc_info=True)
                return SkillResult(
                    success=False,
                    output="",
                    error=f"No se pudo abrir {display_name}: {exc}",
                    data={"query": raw_query, "url": url},
                )

        # 2. YouTube Music / YouTube (Fase 79: v2 con autoplay via API v3 o fallback v1)
        api_key = settings.get("MEDIA_YT_API_KEY", "").strip()
        display_name = "YouTube Music" if svc == "youtube_music" else "YouTube"

        # Flujo sin key (v1 mejorado)
        if not api_key:
            url, _, _ = build_media_url(raw_query, svc)
            _logger.info(f"MediaPlaySkill (sin key): abriendo '{raw_query}' en {display_name} -> {url}")
            try:
                self._open_in_browser(url)
                msg = (
                    f"🎵 Búsqueda de '{raw_query}' lista en {display_name}. "
                    f"Para reproducción directa agregá una YouTube API key en Configuración > Media."
                )
                return SkillResult(
                    success=True,
                    output=msg,
                    data={
                        "query": raw_query,
                        "service": display_name,
                        "url": url,
                        "has_key": False,
                    },
                )
            except Exception as exc:
                _logger.error(f"MediaPlaySkill: error al abrir {url}: {exc}", exc_info=True)
                return SkillResult(
                    success=False,
                    output="",
                    error=f"No se pudo abrir {display_name}: {exc}",
                    data={"query": raw_query, "url": url},
                )

        # Flujo con key (v2)
        from aura.media.youtube_client import search_youtube_video, normalize_media_query
        norm_q = normalize_media_query(raw_query)
        res = search_youtube_video(norm_q, api_key=api_key)

        if res.get("success") and res.get("video_id"):
            video_id = res["video_id"]
            title = res.get("title") or raw_query
            channel = res.get("channel") or ""

            if svc == "youtube_music":
                url = f"https://music.youtube.com/watch?v={video_id}&autoplay=1"
            else:
                url = f"https://www.youtube.com/watch?v={video_id}&autoplay=1"

            _logger.info(
                f"MediaPlaySkill (v2): reproduciendo '{title}' [{video_id}] en {display_name} -> {url}"
            )
            try:
                self._open_in_browser(url)
                domain = "music.youtube.com" if svc == "youtube_music" else "youtube.com"
                if channel:
                    msg = (
                        f"🎵 Reproduciendo: {title} — {channel} "
                        f"(si no arranca solo, apretá play o habilitá autoplay para {domain} en tu navegador)"
                    )
                else:
                    msg = (
                        f"🎵 Reproduciendo: {title} "
                        f"(si no arranca solo, apretá play o habilitá autoplay para {domain} en tu navegador)"
                    )

                return SkillResult(
                    success=True,
                    output=msg,
                    data={
                        "query": raw_query,
                        "norm_query": norm_q,
                        "service": display_name,
                        "url": url,
                        "video_id": video_id,
                        "title": title,
                        "channel": channel,
                        "cached": res.get("cached", False),
                        "has_key": True,
                    },
                )
            except Exception as exc:
                _logger.error(f"MediaPlaySkill: error al abrir {url}: {exc}", exc_info=True)
                return SkillResult(
                    success=False,
                    output="",
                    error=f"No se pudo abrir {display_name}: {exc}",
                    data={"query": raw_query, "url": url, "video_id": video_id},
                )

        # Si la API falló (400, 403, 404, timeout, network error):
        # Fallback honesto a URL de búsqueda v1 + mensaje explicativo accionable
        fallback_url, _, _ = build_media_url(raw_query, svc)
        reason = res.get("reason", "")
        status_code = res.get("status_code")

        if reason == "invalid_key" or status_code == 400:
            explanation = "API key inválida. Revisala en Configuración > Media."
        elif reason == "quota_or_disabled" or status_code == 403:
            explanation = (
                "Cuota de YouTube API agotada por hoy (10.000 unidades gratuitas diarias) "
                "o la API no está habilitada en Google Cloud."
            )
        elif reason == "no_results" or status_code == 404:
            explanation = f"No encontré videos para '{raw_query}'."
        elif reason == "timeout":
            explanation = "No se pudo conectar a YouTube API."
        else:
            explanation = res.get("error") or "Error al consultar YouTube API."

        _logger.warning(
            f"MediaPlaySkill (fallback v1): {explanation} -> abriendo búsqueda {fallback_url}"
        )

        try:
            self._open_in_browser(fallback_url)
            msg = f"🎵 Búsqueda de '{raw_query}' lista en {display_name}. ({explanation})"
            return SkillResult(
                success=True,
                output=msg,
                data={
                    "query": raw_query,
                    "service": display_name,
                    "url": fallback_url,
                    "fallback": True,
                    "reason": reason,
                    "error_explanation": explanation,
                },
            )
        except Exception as exc:
            _logger.error(f"MediaPlaySkill: error al abrir fallback {fallback_url}: {exc}", exc_info=True)
            return SkillResult(
                success=False,
                output="",
                error=f"No se pudo abrir {display_name}: {exc}",
                data={"query": raw_query, "url": fallback_url},
            )

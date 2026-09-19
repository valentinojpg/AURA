# -*- coding: utf-8 -*-
"""
Tests unitarios exhaustivos para FASE 79:
media_play v2 (YouTube Data API v3, caché local 30 días, fallback honesto y cadenas de automatización).
"""

from __future__ import annotations

from pathlib import Path
import sys
import time
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from aura.media.youtube_client import (
    normalize_media_query,
    search_youtube_video,
    test_youtube_api_key as check_youtube_api_key,
    load_media_cache,
    save_media_cache,
    get_cached_video,
    set_cached_video,
    _CACHE_TTL_SECONDS,
)
from skills.builtin.media_play_skill import (
    MediaPlaySkill,
    normalize_service_name,
    build_media_url,
)
from config.settings import settings


# ─────────────────────────────────────────────────────────────────────────────
# 1. Normalización de consultas
# ─────────────────────────────────────────────────────────────────────────────

def test_normalize_media_query_basic():
    assert normalize_media_query("bohemian rhapsody") == "bohemian rhapsody"
    assert normalize_media_query("   hotel   california   ") == "hotel california"


def test_normalize_media_query_quotes():
    assert normalize_media_query('"smooth criminal"') == "smooth criminal"
    assert normalize_media_query("'bad romance'") == "bad romance"
    assert normalize_media_query("«despacito»") == "despacito"


def test_normalize_media_query_spanish_split():
    # "X de Y" -> "X Y"
    assert normalize_media_query("bad romance de lady gaga") == "bad romance lady gaga"
    assert normalize_media_query("'bad romance' de Lady Gaga") == "bad romance Lady Gaga"
    assert normalize_media_query('"clocks" de Coldplay') == "clocks Coldplay"
    # Sin artista después de "de " no debe romper
    assert normalize_media_query("musica de") == "musica de"


def test_normalize_service_name():
    assert normalize_service_name("ytmusic") == "youtube_music"
    assert normalize_service_name("music") == "youtube_music"
    assert normalize_service_name("youtube") == "youtube"
    assert normalize_service_name("video") == "youtube"
    assert normalize_service_name("spotify") == "spotify"
    assert normalize_service_name("spoti") == "spotify"
    assert normalize_service_name("desconocido") == "youtube_music"


def test_build_media_url_direct():
    url, name, is_native = build_media_url("Queen Radio Ga Ga", "youtube_music")
    assert "music.youtube.com/search" in url
    assert name == "YouTube Music"
    assert not is_native


# ─────────────────────────────────────────────────────────────────────────────
# 2. Caché persistente y TTL
# ─────────────────────────────────────────────────────────────────────────────

def test_media_cache_save_and_load(tmp_path: Path):
    test_cache_file = tmp_path / "media_cache.json"
    with patch("aura.media.youtube_client._CACHE_FILE", test_cache_file):
        # Inicialmente vacío
        assert load_media_cache() == {}

        # Guardar y recuperar
        data = {
            "bohemian rhapsody": {
                "video_id": "fJ9rUzIMcZQ",
                "title": "Queen - Bohemian Rhapsody (Official Video)",
                "channel": "Queen Official",
                "timestamp": time.time(),
                "fecha": "2026-09-17T00:00:00",
            }
        }
        save_media_cache(data)
        loaded = load_media_cache()
        assert loaded["bohemian rhapsody"]["video_id"] == "fJ9rUzIMcZQ"


def test_media_cache_ttl_and_get(tmp_path: Path):
    test_cache_file = tmp_path / "media_cache.json"
    with patch("aura.media.youtube_client._CACHE_FILE", test_cache_file):
        # 1. Entrada reciente (< 30 días)
        set_cached_video("november rain", "8SbUC-U424k", "November Rain", "Guns N' Roses")
        entry = get_cached_video("november rain")
        assert entry is not None
        assert entry["video_id"] == "8SbUC-U424k"
        assert entry["title"] == "November Rain"

        # 2. Entrada expirada (> 30 días)
        cache = load_media_cache()
        cache["november rain"]["timestamp"] = time.time() - (_CACHE_TTL_SECONDS + 100)
        save_media_cache(cache)

        expired_entry = get_cached_video("november rain")
        assert expired_entry is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. YouTube Data API v3 Client
# ─────────────────────────────────────────────────────────────────────────────

def test_search_youtube_video_no_key():
    with patch.object(settings, "get", return_value=""):
        res = search_youtube_video("any song", api_key="")
        assert res["success"] is False
        assert res["reason"] == "no_key"


def test_search_youtube_video_success_mock(tmp_path: Path):
    test_cache_file = tmp_path / "media_cache.json"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {
                "id": {"videoId": "test12345"},
                "snippet": {
                    "title": "Song Title &amp; More",
                    "channelTitle": "Artist Channel &gt; Official",
                },
            }
        ]
    }

    with patch("aura.media.youtube_client._CACHE_FILE", test_cache_file):
        with patch("requests.get", return_value=mock_resp) as mock_get:
            res = search_youtube_video("test song", api_key="AIzaSyMockKey")
            assert res["success"] is True
            assert res["video_id"] == "test12345"
            # Verificar unescape de entidades HTML (&amp; -> &, &gt; -> >)
            assert res["title"] == "Song Title & More"
            assert res["channel"] == "Artist Channel > Official"
            assert res["cached"] is False
            assert mock_get.called

            # Segunda llamada debe ser cache HIT (0 peticiones a la API)
            mock_get.reset_mock()
            res2 = search_youtube_video("test song", api_key="AIzaSyMockKey")
            assert res2["success"] is True
            assert res2["video_id"] == "test12345"
            assert res2["cached"] is True
            assert not mock_get.called


def test_search_youtube_video_zero_results(tmp_path: Path):
    test_cache_file = tmp_path / "media_cache.json"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": []}

    with patch("aura.media.youtube_client._CACHE_FILE", test_cache_file):
        with patch("requests.get", return_value=mock_resp):
            res = search_youtube_video("nonexistentquery123xyz", api_key="AIzaSyMockKey")
            assert res["success"] is False
            assert res["reason"] == "no_results"
            assert res["status_code"] == 404


def test_search_youtube_video_errors():
    # 400: Invalid key
    mock_resp_400 = MagicMock(status_code=400)
    with patch("requests.get", return_value=mock_resp_400):
        res = search_youtube_video("song", api_key="badkey")
        assert res["success"] is False
        assert res["reason"] == "invalid_key"
        assert res["status_code"] == 400

    # 403: Quota
    mock_resp_403 = MagicMock(status_code=403)
    with patch("requests.get", return_value=mock_resp_403):
        res = search_youtube_video("song", api_key="exceeded")
        assert res["success"] is False
        assert res["reason"] == "quota_or_disabled"
        assert res["status_code"] == 403

    # Timeout
    import requests
    with patch("requests.get", side_effect=requests.Timeout):
        res = search_youtube_video("song", api_key="timeoutkey")
        assert res["success"] is False
        assert res["reason"] == "timeout"


def test_test_youtube_api_key():
    # Empty
    ok, msg = check_youtube_api_key("")
    assert not ok
    assert "vacía" in msg

    # Valid 200
    mock_200 = MagicMock(status_code=200)
    with patch("requests.get", return_value=mock_200):
        ok, msg = check_youtube_api_key("valid_key")
        assert ok
        assert "operativa" in msg

    # Invalid 400
    mock_400 = MagicMock(status_code=400)
    with patch("requests.get", return_value=mock_400):
        ok, msg = check_youtube_api_key("invalid_key")
        assert not ok
        assert "400" in msg

    # Quota 403
    mock_403 = MagicMock(status_code=403)
    with patch("requests.get", return_value=mock_403):
        ok, msg = check_youtube_api_key("quota_key")
        assert not ok
        assert "403" in msg


# ─────────────────────────────────────────────────────────────────────────────
# 4. MediaPlaySkill: Flujos con Key, Sin Key y Fallbacks
# ─────────────────────────────────────────────────────────────────────────────

def test_media_play_skill_validation():
    skill = MediaPlaySkill()
    # Sin argumentos
    res = skill.execute("reproducir", [])
    assert res.success is False
    assert "canción" in res.error

    # Argumento vacío
    res2 = skill.execute("reproducir", ["   "])
    assert res2.success is False
    assert "vacío" in res2.error


def test_media_play_skill_no_key_flow():
    skill = MediaPlaySkill()
    with patch.object(settings, "get", side_effect=lambda k, d="": "" if k == "MEDIA_YT_API_KEY" else d):
        with patch.object(skill, "_open_in_browser") as mock_open:
            res = skill.execute("reproducir", ["Bohemian Rhapsody"])
            assert res.success is True
            assert "Para reproducción directa agregá una YouTube API key" in res.output
            assert mock_open.called
            # Verifica que la URL abierta sea de búsqueda
            opened_url = mock_open.call_args[0][0]
            assert "music.youtube.com/search?q=" in opened_url


def test_media_play_skill_v2_with_key_autoplay():
    skill = MediaPlaySkill()
    mock_search = {
        "success": True,
        "video_id": "dQw4w9WgXcQ",
        "title": "Never Gonna Give You Up",
        "channel": "Rick Astley",
        "cached": False,
    }

    with patch.object(settings, "get", side_effect=lambda k, d="": "AIzaFakeKey" if k == "MEDIA_YT_API_KEY" else "youtube_music"):
        with patch("aura.media.youtube_client.search_youtube_video", return_value=mock_search):
            with patch.object(skill, "_open_in_browser") as mock_open:
                res = skill.execute("reproducir", ["Never Gonna Give You Up", "--service", "youtube_music"])
                assert res.success is True
                assert res.output == (
                    "🎵 Reproduciendo: Never Gonna Give You Up — Rick Astley "
                    "(si no arranca solo, apretá play o habilitá autoplay para music.youtube.com en tu navegador)"
                )
                assert mock_open.called
                opened_url = mock_open.call_args[0][0]
                assert opened_url == "https://music.youtube.com/watch?v=dQw4w9WgXcQ&autoplay=1"


def test_media_play_skill_v2_youtube_video():
    skill = MediaPlaySkill()
    mock_search = {
        "success": True,
        "video_id": "kJQP7kiw5Fk",
        "title": "Despacito",
        "channel": "Luis Fonsi",
        "cached": False,
    }

    with patch.object(settings, "get", side_effect=lambda k, d="": "AIzaFakeKey" if k == "MEDIA_YT_API_KEY" else "youtube"):
        with patch("aura.media.youtube_client.search_youtube_video", return_value=mock_search):
            with patch.object(skill, "_open_in_browser") as mock_open:
                res = skill.execute("reproducir", ["Despacito", "--service", "youtube"])
                assert res.success is True
                assert res.output == (
                    "🎵 Reproduciendo: Despacito — Luis Fonsi "
                    "(si no arranca solo, apretá play o habilitá autoplay para youtube.com en tu navegador)"
                )
                opened_url = mock_open.call_args[0][0]
                assert opened_url == "https://www.youtube.com/watch?v=kJQP7kiw5Fk&autoplay=1"


def test_media_play_skill_v2_api_error_graceful_fallback():
    skill = MediaPlaySkill()
    mock_search_fail = {
        "success": False,
        "video_id": None,
        "title": None,
        "channel": None,
        "reason": "quota_or_disabled",
        "status_code": 403,
        "error": "Quota de YouTube API superada",
    }

    with patch.object(settings, "get", side_effect=lambda k, d="": "AIzaFakeKey" if k == "MEDIA_YT_API_KEY" else "youtube_music"):
        with patch("aura.media.youtube_client.search_youtube_video", return_value=mock_search_fail):
            with patch.object(skill, "_open_in_browser") as mock_open:
                res = skill.execute("reproducir", ["Shape of You"])
                # No debe romperse: debe abrir búsqueda de respaldo
                assert res.success is True
                assert "Cuota de YouTube API agotada por hoy" in res.output
                assert mock_open.called
                opened_url = mock_open.call_args[0][0]
                assert "music.youtube.com/search?q=Shape+of+You" in opened_url


def test_media_play_skill_spotify():
    skill = MediaPlaySkill()
    with patch("skills.builtin.media_play_skill.is_spotify_installed", return_value=False):
        with patch.object(skill, "_open_in_browser") as mock_open:
            res = skill.execute("reproducir", ["Starboy", "--service", "spotify"])
            assert res.success is True
            assert "Spotify Web" in res.output
            assert mock_open.called
            opened_url = mock_open.call_args[0][0]
            assert "open.spotify.com/search/Starboy" in opened_url


# ─────────────────────────────────────────────────────────────────────────────
# 5. Integración con AutomationEngine (Fase 71 + 79)
# ─────────────────────────────────────────────────────────────────────────────

def test_automation_engine_media_play_step():
    from automation.engine import AutomationEngine

    engine = AutomationEngine()
    steps = [
        {"type": "media_play", "query": "Stairway to Heaven", "service": "youtube_music"},
    ]

    mock_search = {
        "success": True,
        "video_id": "QkF3oxziUI4",
        "title": "Led Zeppelin - Stairway to Heaven",
        "channel": "Led Zeppelin",
        "cached": False,
    }

    with patch.object(settings, "get", side_effect=lambda k, d="": "AIzaFakeKey" if k == "MEDIA_YT_API_KEY" else d):
        with patch("aura.media.youtube_client.search_youtube_video", return_value=mock_search):
            with patch("skills.builtin.media_play_skill.MediaPlaySkill._open_in_browser"):
                res = engine.run_steps(steps, name="cadena_musica")
                assert res.success is True
                assert res.completed_steps == 1
                assert "Reproduciendo" in res.step_results[0].output


def test_media_play_skill_v2_no_channel_autoplay():
    skill = MediaPlaySkill()
    mock_search = {
        "success": True,
        "video_id": "testVid123",
        "title": "Solo Track",
        "channel": "",
        "cached": False,
    }
    with patch.object(settings, "get", side_effect=lambda k, d="": "AIzaFakeKey" if k == "MEDIA_YT_API_KEY" else "youtube_music"):
        with patch("aura.media.youtube_client.search_youtube_video", return_value=mock_search):
            with patch.object(skill, "_open_in_browser") as mock_open:
                res = skill.execute("reproducir", ["Solo Track"])
                assert res.success is True
                assert res.output == (
                    "🎵 Reproduciendo: Solo Track "
                    "(si no arranca solo, apretá play o habilitá autoplay para music.youtube.com en tu navegador)"
                )
                assert mock_open.call_args[0][0] == "https://music.youtube.com/watch?v=testVid123&autoplay=1"


def test_shim_aura_skills_media_player():
    from aura.skills.media_player import MediaPlaySkill as ShimSkill, build_media_url as shim_build_url
    assert ShimSkill is MediaPlaySkill
    assert callable(shim_build_url)


def test_settings_page_media_section():
    from ui.pages.settings_page import SettingsPage
    from aura.ui.theme import build_theme_tokens

    mock_page = MagicMock()
    page = SettingsPage(page=mock_page)
    assert hasattr(page, "_media_card")
    assert page._media_card is not None
    assert hasattr(page, "_media_key_field")
    assert hasattr(page, "_media_svc_dropdown")

    # Filtro de categorías
    page._set_active_category("media")
    assert page._media_card.visible is True
    assert page._general_card.visible is False

    page._set_active_category("audio")
    assert page._media_card.visible is True

    page._set_active_category("ai")
    assert page._media_card.visible is False

    # apply_theme
    tokens = build_theme_tokens("classic", ["#3B4FC8", "#2A2A4E", "#1A1A36"])
    page.apply_theme(tokens)
    assert page._media_card.bgcolor == tokens.card_bg


def test_smoke_main_window_mount_settings():
    from ui.main_window import MainWindow

    mw = MainWindow()
    mock_page = MagicMock()
    mock_page.window = MagicMock()
    mock_page.overlay = []

    with patch("ui.main_window.apply_window_branding"):
        mw._main(mock_page)

    assert "settings" in mw._pages
    assert "chat" in mw._pages

    # Navegar a settings
    mw.navigate("settings")
    assert mw._current_page_id == "settings"
    settings_p = mw._pages["settings"]
    assert hasattr(settings_p, "_media_card")
    assert settings_p._media_card is not None

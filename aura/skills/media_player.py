# -*- coding: utf-8 -*-
"""
Shim para media_play (compatibilidad con aura.skills.media_player).
Redirige a skills.builtin.media_play_skill.
"""
from skills.builtin.media_play_skill import (
    MediaPlaySkill,
    build_media_url,
    normalize_service_name,
    is_spotify_installed,
)

__all__ = [
    "MediaPlaySkill",
    "build_media_url",
    "normalize_service_name",
    "is_spotify_installed",
]

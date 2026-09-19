"""
AURA — Shim para ui.theme_textures (Fase 76).
Reexporta desde aura.ui.theme_textures.
"""

from aura.ui.theme_textures import (
    generate_dithering_tile,
    generate_halftone_tile,
    get_texture_cache_dir,
    get_theme_texture_tile,
)

__all__ = [
    "generate_dithering_tile",
    "generate_halftone_tile",
    "get_texture_cache_dir",
    "get_theme_texture_tile",
]

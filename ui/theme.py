"""
AURA — Shim para ui.theme (Fase 76).
Reexporta desde aura.ui.theme.
"""

from aura.ui.theme import (
    STYLE_COLOR_COUNT,
    STYLE_FAMILIES,
    THEME_PRESETS,
    ThemeManager,
    ThemeTokens,
    apply_theme,
    build_theme_tokens,
    theme_manager,
)

__all__ = [
    "STYLE_COLOR_COUNT",
    "STYLE_FAMILIES",
    "THEME_PRESETS",
    "ThemeManager",
    "ThemeTokens",
    "apply_theme",
    "build_theme_tokens",
    "theme_manager",
]

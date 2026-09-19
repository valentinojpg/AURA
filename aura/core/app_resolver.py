"""
AURA — Módulo de compatibilidad para core.app_resolver.
Re-exporta todo desde core.app_resolver.
"""

from core.app_resolver import (
    ResolvedApp,
    SUPPORTED_BROWSERS,
    BROWSER_DISPLAY_NAMES,
    GENERIC_BROWSER_ALIASES,
    detect_default_browser,
    get_preferred_browser_name,
    find_browser_executable,
    get_installed_browsers,
    resolve_app,
    launch_app,
)

__all__ = [
    "ResolvedApp",
    "SUPPORTED_BROWSERS",
    "BROWSER_DISPLAY_NAMES",
    "GENERIC_BROWSER_ALIASES",
    "detect_default_browser",
    "get_preferred_browser_name",
    "find_browser_executable",
    "get_installed_browsers",
    "resolve_app",
    "launch_app",
]

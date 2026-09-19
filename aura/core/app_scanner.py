"""
AURA — Módulo de compatibilidad para core.app_scanner.
Re-exporta todo desde core.app_scanner.
"""

from core.app_scanner import (
    AppIndexManager,
    DeepAppScanner,
    DeepScanResult,
    IndexedApp,
    app_index_manager,
    deep_app_scanner,
    fast_resolve_app,
    normalize_name,
    should_exclude_dir,
)

__all__ = [
    "AppIndexManager",
    "DeepAppScanner",
    "DeepScanResult",
    "IndexedApp",
    "app_index_manager",
    "deep_app_scanner",
    "fast_resolve_app",
    "normalize_name",
    "should_exclude_dir",
]

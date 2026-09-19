"""
AURA — Shim para ui.background_manager (Fase 78).
Reexporta desde aura.ui.background_manager.
"""

from aura.ui.background_manager import (
    BACKGROUNDS_DIR,
    CACHE_DIR,
    QA_DIR,
    MAX_FILE_SIZE_BYTES,
    MAX_FPS,
    MAX_WIDTH,
    METADATA_FILE,
    SUPPORTED_EXTENSIONS,
    BackgroundManager,
    GifFramePlayer,
    background_manager,
    calculate_average_luminance,
    compute_file_hash,
    get_current_background_path,
    load_current_metadata,
    normalize_background_image,
)

__all__ = [
    "BACKGROUNDS_DIR",
    "CACHE_DIR",
    "QA_DIR",
    "MAX_FILE_SIZE_BYTES",
    "MAX_FPS",
    "MAX_WIDTH",
    "METADATA_FILE",
    "SUPPORTED_EXTENSIONS",
    "BackgroundManager",
    "GifFramePlayer",
    "background_manager",
    "calculate_average_luminance",
    "compute_file_hash",
    "get_current_background_path",
    "load_current_metadata",
    "normalize_background_image",
]

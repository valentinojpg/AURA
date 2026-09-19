"""
AURA — Shim para ui.color_utils (Fase 76).
Reexporta desde aura.ui.color_utils para máxima compatibilidad de imports.
"""

from aura.ui.color_utils import (
    adjust_hsl,
    contrast_ratio,
    derive_analogous_palette,
    derive_mono_palette,
    derive_poly_palette,
    get_readable_text_color,
    hex_to_hsl,
    hex_to_rgb,
    hex_with_alpha,
    hsl_to_hex,
    hsl_to_rgb,
    is_valid_hex,
    normalize_hex,
    relative_luminance,
    rgb_to_hex,
    rgb_to_hsl,
    rotate_hue,
)

__all__ = [
    "adjust_hsl",
    "contrast_ratio",
    "derive_analogous_palette",
    "derive_mono_palette",
    "derive_poly_palette",
    "get_readable_text_color",
    "hex_to_hsl",
    "hex_to_rgb",
    "hex_with_alpha",
    "hsl_to_hex",
    "hsl_to_rgb",
    "is_valid_hex",
    "normalize_hex",
    "relative_luminance",
    "rgb_to_hex",
    "rgb_to_hsl",
    "rotate_hue",
]

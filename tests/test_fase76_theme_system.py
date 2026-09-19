"""
AURA — Pruebas Automatizadas del Sistema de Temas (Fase 76)

Valida exhaustivamente:
  1. Conversiones matemáticas de color (RGB, HSL, HEX)
  2. Rotación de matiz sobre el círculo cromático
  3. Relación de contraste y selección de texto legible WCAG AA
  4. Derivación algorítmica de paletas (monocromática, análoga, policromática)
  5. Generación y caché de texturas Pillow (dithering y halftone)
  6. Motor de 12 estilos visuales y consistencia de tokens (ThemeTokens)
  7. Carga y aplicación de los 12 presets predefinidos
  8. Persistencia y sincronización con settings
  9. Blindaje ante hex inválidos y valores fuera de rango
  10. Verificación sistémica de Pyflakes (0 warnings)
"""

import os
import subprocess
import sys
from pathlib import Path
from PIL import Image
import pytest

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
from aura.ui.theme_textures import (
    generate_dithering_tile,
    generate_halftone_tile,
    get_texture_cache_dir,
    get_theme_texture_tile,
)
from aura.ui.theme import (
    STYLE_COLOR_COUNT,
    STYLE_FAMILIES,
    THEME_PRESETS,
    ThemeTokens,
    apply_theme,
    build_theme_tokens,
    theme_manager,
)
from config.settings import settings


# ── 1. Pruebas de Utilidades y Conversiones Matemáticas ────────────

def test_hex_rgb_conversions():
    assert hex_to_rgb("#FF0000") == (255, 0, 0)
    assert hex_to_rgb("#00FF00") == (0, 255, 0)
    assert hex_to_rgb("#0000FF") == (0, 0, 255)
    assert hex_to_rgb("#FFFFFF") == (255, 255, 255)
    assert hex_to_rgb("#000000") == (0, 0, 0)

    assert rgb_to_hex(255, 0, 0) == "#FF0000"
    assert rgb_to_hex(0, 255, 0) == "#00FF00"
    assert rgb_to_hex(0, 0, 255) == "#0000FF"


def test_hsl_conversions_and_rotation():
    # Rojo puro -> h=0, s=1, l=0.5
    h, s, l = hex_to_hsl("#FF0000")
    assert round(h) == 0
    assert round(s, 2) == 1.0
    assert round(l, 2) == 0.5

    # Rotación de matiz
    green = rotate_hue("#FF0000", 120.0)
    assert green == "#00FF00"
    blue = rotate_hue("#FF0000", 240.0)
    assert blue == "#0000FF"
    back_to_red = rotate_hue("#FF0000", 360.0)
    assert back_to_red == "#FF0000"


def test_contrast_ratio_and_wcag_readability():
    # Contraste extremo
    assert round(contrast_ratio("#000000", "#FFFFFF"), 1) == 21.0
    assert contrast_ratio("#111111", "#111111") == 1.0

    # Fondo oscuro debe seleccionar texto claro
    dark_bg = "#0C0C18"
    readable = get_readable_text_color(dark_bg)
    assert contrast_ratio(dark_bg, readable) >= 4.5

    # Fondo claro debe seleccionar texto oscuro
    light_bg = "#F3F4F6"
    readable_dark = get_readable_text_color(light_bg)
    assert contrast_ratio(light_bg, readable_dark) >= 4.5


def test_hex_validation():
    assert is_valid_hex("#FFFFFF") is True
    assert is_valid_hex("#000000") is True
    assert is_valid_hex("#123456") is True
    assert is_valid_hex("#abcdef") is True
    assert is_valid_hex("ABCDEF") is True

    assert is_valid_hex("#FFF") is False
    assert is_valid_hex("#GGGGGG") is False
    assert is_valid_hex("#1234567") is False
    assert is_valid_hex("") is False
    assert is_valid_hex(None) is False


def test_derived_palettes():
    # Monocromático: 6 tonos ordenados por luminosidad creciente
    mono = derive_mono_palette("#1E3A8A")
    assert len(mono) == 6
    lum_prev = -1.0
    for col in mono:
        lum = relative_luminance(col)
        assert lum > lum_prev
        lum_prev = lum

    # Análogo: 4 tonos con matices vecinos
    analog = derive_analogous_palette("#D97706")
    assert len(analog) == 4
    assert is_valid_hex(analog[0])

    # Policromático: triada, complementario, complementario dividido
    poly_tri = derive_poly_palette("#EC4899", scheme="triada")
    assert len(poly_tri) == 3
    poly_comp = derive_poly_palette("#EC4899", scheme="complementario")
    assert len(poly_comp) == 2
    poly_split = derive_poly_palette("#EC4899", scheme="complementario dividido")
    assert len(poly_split) == 3


# ── 2. Pruebas de Generación y Caché de Texturas Pillow ───────────

def test_texture_generation_and_caching():
    c1 = "#2D3748"
    c2 = "#E2E8F0"

    # Dithering
    dither_path = generate_dithering_tile(c1, c2, size=128)
    assert os.path.exists(dither_path)
    with Image.open(dither_path) as im:
        assert im.size == (128, 128)
        assert im.mode == "RGB"

    mtime_1 = os.path.getmtime(dither_path)
    # Segunda llamada: debe provenir del caché sin modificar el archivo
    dither_path_2 = generate_dithering_tile(c1, c2, size=128)
    assert dither_path == dither_path_2
    assert os.path.getmtime(dither_path_2) == mtime_1

    # Halftone
    halftone_path = generate_halftone_tile(c1, c2, size=128)
    assert os.path.exists(halftone_path)
    with Image.open(halftone_path) as im:
        assert im.size == (128, 128)
        assert im.mode == "RGB"

    mtime_h1 = os.path.getmtime(halftone_path)
    halftone_path_2 = generate_halftone_tile(c1, c2, size=128)
    assert halftone_path == halftone_path_2
    assert os.path.getmtime(halftone_path_2) == mtime_h1


# ── 3. Pruebas de los 12 Estilos Obligatorios ─────────────────────

def test_all_12_styles_token_generation():
    styles_tested = [
        ("solid", ["#0C0C18"]),
        ("gradient", ["#FF6B35", "#FF1493"]),
        ("neon", ["#0A0A12", "#00FFA3"]),
        ("duotone", ["#FF4E50", "#191414"]),
        ("gradientmap", ["#0B1D3A", "#00B4D8", "#90E0EF"]),
        ("mesh", ["#4158D0", "#C850C0", "#FFCC70", "#0093E9"]),
        ("bleeding", ["#121224", "#8A2BE2"]),
        ("mono", ["#1E3A8A"]),
        ("analogous", ["#D97706"]),
        ("poly", ["#EC4899"]),
        ("dithering", ["#2D3748", "#E2E8F0"]),
        ("halftone", ["#F3F4F6", "#1F2937"]),
    ]

    for style, colors in styles_tested:
        tokens = build_theme_tokens(style, colors, scheme="triada")
        assert isinstance(tokens, ThemeTokens)
        assert tokens.style == style
        assert is_valid_hex(tokens.app_bg)
        assert is_valid_hex(tokens.user_bubble_bg)
        assert is_valid_hex(tokens.assistant_bubble_bg)
        assert is_valid_hex(tokens.user_bubble_text)
        assert is_valid_hex(tokens.assistant_bubble_text)

        # Regla de no blanco sobre blanco / claro sobre claro:
        # Contraste de texto debe ser seguro
        assert contrast_ratio(tokens.user_bubble_bg, tokens.user_bubble_text) >= 3.0
        assert contrast_ratio(tokens.assistant_bubble_bg, tokens.assistant_bubble_text) >= 3.0

        # Verificaciones específicas por estilo
        if style == "neon":
            assert tokens.bubble_shadow is not None
            assert tokens.button_shadow is not None
        elif style == "duotone":
            # Estricto duotono: sin grises intermedios
            c1_norm = normalize_hex(colors[0])
            c2_norm = normalize_hex(colors[1])
            assert tokens.app_bg == c2_norm
            assert tokens.user_bubble_bg == c1_norm
            assert tokens.assistant_bubble_bg == c2_norm
        elif style == "gradient":
            assert tokens.sidebar_gradient is not None
            assert tokens.user_bubble_gradient is not None
        elif style == "mesh":
            assert tokens.is_mesh is True
            assert len(tokens.mesh_colors) == 4
        elif style in ("dithering", "halftone"):
            assert tokens.background_image is not None
            assert os.path.exists(tokens.background_image)


# ── 4. Pruebas de los 12 Presets Predefinidos ─────────────────────

def test_presets_completeness_and_execution():
    assert len(THEME_PRESETS) == 12
    for preset_name, p_info in THEME_PRESETS.items():
        st = p_info["style"]
        cols = p_info["colors"]
        sch = p_info.get("scheme", "triada")

        toks = build_theme_tokens(st, cols, scheme=sch, preset_name=preset_name)
        assert toks.preset_name == preset_name
        assert toks.style == st


# ── 5. Pruebas de Persistencia en Settings y ThemeManager ─────────

def test_theme_manager_apply_and_persistence(tmp_path):
    orig_style = settings.get("THEME_STYLE")
    orig_c1 = settings.get("THEME_COLOR_1")

    try:
        toks = apply_theme(
            style="neon",
            colors=["#050510", "#FF0077"],
            scheme="triada",
            preset_name="Cyberpunk",
            save=True,
        )
        assert toks.style == "neon"
        assert settings.get("THEME_STYLE") == "neon"
        assert settings.get("THEME_COLOR_1") == "#050510"
        assert settings.get("THEME_COLOR_2") == "#FF0077"

        # Cargar desde settings
        reloaded = theme_manager.load_from_settings()
        assert reloaded.style == "neon"
        assert reloaded.colors[0] == "#050510"
        assert reloaded.colors[1] == "#FF0077"

    finally:
        # Restaurar
        if orig_style:
            settings.set("THEME_STYLE", orig_style)
        if orig_c1:
            settings.set("THEME_COLOR_1", orig_c1)


# ── 6. Auditoría Estática de Pyflakes (Regla Obligatoria de Cierre) ─

def test_pyflakes_zero_warnings_phase_closure():
    cmd = [sys.executable, "-m", "pyflakes", "aura/", "run.py", "scripts/"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Pyflakes encontró advertencias:\n{res.stdout}\n{res.stderr}"
    assert len(res.stdout.strip()) == 0, f"Pyflakes stdout no vacío:\n{res.stdout}"

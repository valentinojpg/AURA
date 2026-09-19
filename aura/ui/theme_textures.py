"""
AURA — Generador y Caché de Texturas Visuales para Temas (Fase 76)

Genera patrones y texturas en mosaico (tiles de 128x128 píxeles):
  - Dithering: Dither ordenado basado en matriz de Bayer 4x4 entre c1 y c2.
  - Halftone: Malla de puntos de semitono con radio variable (efecto cómic / pop-art).

Las texturas se almacenan en caché en 'assets/themes/cache/' con nombre derivado
del hash SHA-256 de sus parámetros, evitando regeneraciones innecesarias en tiempo de ejecución.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from PIL import Image, ImageDraw

from aura.ui.color_utils import hex_to_rgb, normalize_hex


# Matriz de Bayer 4x4 estándar normalizada (valores 0..15)
_BAYER_4X4 = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)


def get_texture_cache_dir() -> Path:
    """Retorna y asegura la existencia del directorio de caché de texturas."""
    base_dir = Path(__file__).resolve().parent.parent.parent
    cache_dir = base_dir / "assets" / "themes" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _compute_texture_hash(style: str, c1: str, c2: str, size: int) -> str:
    """Calcula un hash determinístico para el tile."""
    raw = f"{style.lower()}:{normalize_hex(c1)}:{normalize_hex(c2)}:{size}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def generate_dithering_tile(c1_hex: str, c2_hex: str, size: int = 128) -> str:
    """
    Genera un tile de textura con dithering ordenado tipo Bayer entre c1 y c2.
    Retorna la ruta absoluta al archivo PNG en caché.
    """
    cache_dir = get_texture_cache_dir()
    tex_hash = _compute_texture_hash("dithering", c1_hex, c2_hex, size)
    cache_file = cache_dir / f"dither_{tex_hash}.png"

    if cache_file.exists():
        return str(cache_file)

    rgb1 = hex_to_rgb(c1_hex)
    rgb2 = hex_to_rgb(c2_hex)

    img = Image.new("RGB", (size, size), rgb1)
    pixels = img.load()

    # Intercalado con gradiente diagonal continuo para patrón de mezcla armónico
    for y in range(size):
        for x in range(size):
            t = (x + y) / (float(size) * 2.0)
            threshold = (_BAYER_4X4[y % 4][x % 4] + 0.5) / 16.0
            pixels[x, y] = rgb2 if t >= threshold else rgb1

    img.save(str(cache_file), format="PNG", optimize=True)
    return str(cache_file)


def generate_halftone_tile(c1_hex: str, c2_hex: str, size: int = 128) -> str:
    """
    Genera un tile de textura halftone (puntos de radio variable estilo cómic).
    Retorna la ruta absoluta al archivo PNG en caché.
    """
    cache_dir = get_texture_cache_dir()
    tex_hash = _compute_texture_hash("halftone", c1_hex, c2_hex, size)
    cache_file = cache_dir / f"halftone_{tex_hash}.png"

    if cache_file.exists():
        return str(cache_file)

    rgb1 = hex_to_rgb(c1_hex)
    rgb2 = hex_to_rgb(c2_hex)

    img = Image.new("RGB", (size, size), rgb1)
    draw = ImageDraw.Draw(img)

    cell_size = 16
    max_radius = (cell_size * 0.5) * 0.95

    # Dibujar celdas regulares de puntos con radio dependiente de la posición diagonal
    for cy in range(cell_size // 2, size, cell_size):
        for cx in range(cell_size // 2, size, cell_size):
            t = (cx + cy) / (float(size) * 2.0)
            r = (t ** 0.55) * max_radius
            if r >= 0.75:
                draw.ellipse(
                    [cx - r, cy - r, cx + r, cy + r],
                    fill=rgb2,
                    outline=None,
                )

    img.save(str(cache_file), format="PNG", optimize=True)
    return str(cache_file)


def get_theme_texture_tile(style: str, c1_hex: str, c2_hex: str, size: int = 128) -> str:
    """
    Retorna la ruta de la textura correspondiente según el estilo ('dithering' o 'halftone').
    Si no es un estilo con textura, retorna cadena vacía.
    """
    st = (style or "").strip().lower()
    if st == "dithering":
        return generate_dithering_tile(c1_hex, c2_hex, size=size)
    elif st == "halftone":
        return generate_halftone_tile(c1_hex, c2_hex, size=size)
    return ""

"""
AURA — Utilidades de Color y Armonías Cromáticas (Fase 76)

Provee funciones matemáticas y de procesamiento de color:
  - Conversión bidireccional RGB / HSL / HEX
  - Rotación de matiz (hue) sobre el círculo cromático
  - Cálculo de luminancia relativa y ratio de contraste WCAG (AA >= 4.5)
  - Selección de color de texto legible contra cualquier fondo
  - Derivación algorítmica de paletas (monocromática, análoga, policromática)
  - Validación de códigos hexadecimales
"""

from __future__ import annotations

import colorsys
import math
import re
from typing import Optional


_HEX_PATTERN = re.compile(r"^#?[0-9A-Fa-f]{6}$")


def is_valid_hex(hex_str: str) -> bool:
    """Verifica si la cadena representa un color hexadecimal válido de 6 caracteres."""
    if not isinstance(hex_str, str):
        return False
    hex_clean = hex_str.strip()
    return bool(_HEX_PATTERN.match(hex_clean))


def normalize_hex(hex_str: str, fallback: str = "#0C0C18") -> str:
    """Normaliza un color hexadecimal al formato '#RRGGBB' en mayúsculas."""
    if not is_valid_hex(hex_str):
        return fallback.upper()
    clean = hex_str.strip().lstrip("#").upper()
    return f"#{clean}"


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convierte un código hexadecimal a tupla RGB (0-255)."""
    clean = normalize_hex(hex_str).lstrip("#")
    return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convierte componentes RGB (0-255) a código '#RRGGBB' en mayúsculas."""
    r_clamped = max(0, min(255, int(round(r))))
    g_clamped = max(0, min(255, int(round(g))))
    b_clamped = max(0, min(255, int(round(b))))
    return f"#{r_clamped:02X}{g_clamped:02X}{b_clamped:02X}"


def rgb_to_hsl(r: int, g: int, b: int) -> tuple[float, float, float]:
    """
    Convierte RGB (0-255) a HSL:
      - h: 0.0 a 360.0 grados
      - s: 0.0 a 1.0
      - l: 0.0 a 1.0
    """
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    h_norm, l, s = colorsys.rgb_to_hls(rf, gf, bf)
    return (h_norm * 360.0) % 360.0, s, l


def hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    """
    Convierte HSL a RGB (0-255):
      - h: 0.0 a 360.0 grados
      - s: 0.0 a 1.0
      - l: 0.0 a 1.0
    """
    h_norm = (h % 360.0) / 360.0
    s_clamped = max(0.0, min(1.0, float(s)))
    l_clamped = max(0.0, min(1.0, float(l)))
    rf, gf, bf = colorsys.hls_to_rgb(h_norm, l_clamped, s_clamped)
    return (
        int(round(rf * 255)),
        int(round(gf * 255)),
        int(round(bf * 255)),
    )


def hex_to_hsl(hex_str: str) -> tuple[float, float, float]:
    """Convierte código hexadecimal a tupla HSL (0-360, 0-1, 0-1)."""
    r, g, b = hex_to_rgb(hex_str)
    return rgb_to_hsl(r, g, b)


def hsl_to_hex(h: float, s: float, l: float) -> str:
    """Convierte componentes HSL a código hexadecimal '#RRGGBB'."""
    r, g, b = hsl_to_rgb(h, s, l)
    return rgb_to_hex(r, g, b)


def rotate_hue(hex_str: str, degrees: float) -> str:
    """Rota el matiz (hue) de un color en el círculo cromático en los grados especificados."""
    h, s, l = hex_to_hsl(hex_str)
    new_h = (h + degrees) % 360.0
    return hsl_to_hex(new_h, s, l)


def adjust_hsl(
    hex_str: str,
    h_delta: float = 0.0,
    s_factor: float = 1.0,
    l_factor: float = 1.0,
    s_abs: Optional[float] = None,
    l_abs: Optional[float] = None,
) -> str:
    """
    Ajusta matiz, saturación y luminosidad de un color hexadecimal de forma relativa o absoluta.
    """
    h, s, l = hex_to_hsl(hex_str)
    new_h = (h + h_delta) % 360.0
    new_s = s_abs if s_abs is not None else max(0.0, min(1.0, s * s_factor))
    new_l = l_abs if l_abs is not None else max(0.0, min(1.0, l * l_factor))
    return hsl_to_hex(new_h, new_s, new_l)


def hex_with_alpha(hex_str: str, alpha: float) -> str:
    """
    Retorna representación hexadecimal con canal alfa en formato Flet/Flutter '#AARRGGBB'.
    alpha: float entre 0.0 (transparente) y 1.0 (opaco).
    """
    clean = normalize_hex(hex_str).lstrip("#")
    a_clamped = max(0, min(255, int(round(alpha * 255))))
    return f"#{a_clamped:02X}{clean}"


def relative_luminance(hex_str: str) -> float:
    """
    Calcula la luminancia relativa según la especificación WCAG 2.1:
      L = 0.2126 * R + 0.7152 * G + 0.0722 * B
    con corrección gamma sRGB.
    """
    r, g, b = hex_to_rgb(hex_str)

    def _channel_lum(val_8bit: int) -> float:
        c = val_8bit / 255.0
        return c / 12.92 if c <= 0.04045 else math.pow((c + 0.055) / 1.055, 2.4)

    return 0.2126 * _channel_lum(r) + 0.7152 * _channel_lum(g) + 0.0722 * _channel_lum(b)


def contrast_ratio(hex1: str, hex2: str) -> float:
    """
    Calcula el ratio de contraste WCAG entre dos colores (1.0 a 21.0).
    """
    lum1 = relative_luminance(hex1)
    lum2 = relative_luminance(hex2)
    lighter = max(lum1, lum2)
    darker = min(lum1, lum2)
    return (lighter + 0.05) / (darker + 0.05)


def get_readable_text_color(
    bg_hex: str,
    light_hex: str = "#F8FAFC",
    dark_hex: str = "#0F172A",
) -> str:
    """
    Selecciona el color de texto (claro u oscuro) que ofrezca mayor contraste
    contra el fondo dado, garantizando cumplimiento WCAG AA (>= 4.5).
    """
    ratio_light = contrast_ratio(bg_hex, light_hex)
    ratio_dark = contrast_ratio(bg_hex, dark_hex)
    return light_hex if ratio_light >= ratio_dark else dark_hex


def derive_mono_palette(base_hex: str) -> list[str]:
    """
    Genera una paleta monocromática de 6 tonos variando únicamente luminosidad y saturación:
      [0] Fondo profundo (L ~ 0.06)
      [1] Superficie / Sidebar (L ~ 0.11)
      [2] Tarjeta / Card (L ~ 0.16)
      [3] Acento primario (L ~ 0.50)
      [4] Resaltado brillante (L ~ 0.72)
      [5] Texto claro / Destacado (L ~ 0.94)
    """
    h, s, _ = hex_to_hsl(base_hex)
    # Conservamos un toque de saturación sutil para las superficies oscuras
    s_dark = max(0.15, min(s, 0.45))
    s_accent = max(0.55, min(1.0, s))
    s_light = max(0.08, min(s * 0.35, 0.25))

    return [
        hsl_to_hex(h, s_dark, 0.06),
        hsl_to_hex(h, s_dark, 0.11),
        hsl_to_hex(h, s_dark, 0.17),
        hsl_to_hex(h, s_accent, 0.50),
        hsl_to_hex(h, s_accent, 0.72),
        hsl_to_hex(h, s_light, 0.94),
    ]


def derive_analogous_palette(base_hex: str) -> list[str]:
    """
    Deriva una paleta análoga de 4 colores vecinos en el círculo cromático (+-25°):
      [0] Vecino frío/izquierdo (-25°)
      [1] Color base (0°)
      [2] Vecino cálido/derecho (+25°)
      [3] Segundo vecino (+50°)
    """
    return [
        rotate_hue(base_hex, -25.0),
        normalize_hex(base_hex),
        rotate_hue(base_hex, 25.0),
        rotate_hue(base_hex, 50.0),
    ]


def derive_poly_palette(base_hex: str, scheme: str = "triada") -> list[str]:
    """
    Deriva una paleta policromática equilibrada según el esquema geométrico:
      - 'triada': rotaciones de 120° [base, +120°, +240°]
      - 'complementario': rotación de 180° [base, +180°]
      - 'complementario dividido': rotaciones de 150° y 210° [base, +150°, +210°]
    """
    scheme_clean = (scheme or "triada").strip().lower()
    base = normalize_hex(base_hex)

    if scheme_clean == "complementario":
        return [base, rotate_hue(base, 180.0)]
    elif scheme_clean in ("complementario dividido", "split_complementary", "dividido"):
        return [base, rotate_hue(base, 150.0), rotate_hue(base, 210.0)]
    else:  # triada por defecto
        return [base, rotate_hue(base, 120.0), rotate_hue(base, 240.0)]

"""
AURA — Motor de Temas y Sistema de Estilos Visuales (Fase 76)

Implementa los 12 estilos de diseño obligatorios:
  - Mezclas y Transiciones: solid, gradient, neon, duotone, gradientmap, mesh, bleeding
  - Armonías: mono, analogous, poly
  - Texturas: dithering, halftone

Genera tokens visuales normalizados (ThemeTokens) y gestiona la aplicación
en caliente a los componentes de la interfaz de usuario en Flet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import flet as ft

from config.settings import settings
from aura.ui.color_utils import (
    adjust_hsl,
    contrast_ratio,
    derive_analogous_palette,
    derive_mono_palette,
    derive_poly_palette,
    get_readable_text_color,
    hex_with_alpha,
    normalize_hex,
)
from aura.ui.theme_textures import get_theme_texture_tile
from utils.logger import get_logger

_logger = get_logger("aura.ui.theme")


# Cantidad obligatoria de colores seleccionables por estilo
STYLE_COLOR_COUNT: dict[str, int] = {
    "solid": 1,
    "gradient": 2,
    "neon": 2,
    "duotone": 2,
    "gradientmap": 3,
    "mesh": 4,
    "bleeding": 2,
    "mono": 1,
    "analogous": 1,
    "poly": 1,
    "dithering": 2,
    "halftone": 2,
}

# Familias de estilos para agrupación en dropdown
STYLE_FAMILIES = [
    ("MEZCLAS Y TRANSICIONES", [
        ("solid", "Sólido (solid)"),
        ("gradient", "Gradiente lineal (gradient)"),
        ("neon", "Neón / Glow (neon)"),
        ("duotone", "Duotono puro (duotone)"),
        ("gradientmap", "Gradient Map 3 tonos (gradientmap)"),
        ("mesh", "Malla líquida fluida (mesh)"),
        ("bleeding", "Color bleeding / Derrame (bleeding)"),
    ]),
    ("ARMONÍAS CROMÁTICAS", [
        ("mono", "Monocromático HSL (mono)"),
        ("analogous", "Análogo armónico (analogous)"),
        ("poly", "Policromático balanceado (poly)"),
    ]),
    ("TEXTURAS Y PATRONES", [
        ("dithering", "Dithering Bayer retro (dithering)"),
        ("halftone", "Halftone semitono cómic (halftone)"),
    ]),
]


@dataclass
class ThemeTokens:
    """Conjunto unificado de tokens visuales para estilizar la aplicación."""
    style: str
    colors: list[str]
    scheme: str = "triada"
    preset_name: str = ""

    # Superficies y fondos principales
    app_bg: str = "#0C0C18"
    sidebar_bg: str = "#0E0E1A"
    sidebar_gradient: Optional[ft.LinearGradient] = None
    chat_bg: str = "#0C0C18"
    card_bg: str = "#131328"
    border_color: str = "#1A1A36"

    # Tipografía
    text_primary: str = "#E8E8FF"
    text_muted: str = "#7A7A9A"
    accent_color: str = "#4A9EFF"

    # Burbujas de chat
    user_bubble_bg: str = "#1E2A4A"
    user_bubble_text: str = "#E0E8FF"
    user_bubble_gradient: Optional[ft.LinearGradient] = None
    assistant_bubble_bg: str = "#141426"
    assistant_bubble_text: str = "#D0D0E8"

    # Botones e interactivos
    button_primary_bg: str = "#3B4FC8"
    button_primary_text: str = "#FFFFFF"
    button_secondary_bg: str = "#1E1E3A"
    button_secondary_text: str = "#B0B0D0"

    # Efectos especiales (Glow / Sombras)
    bubble_shadow: Optional[list[ft.BoxShadow]] = None
    button_shadow: Optional[list[ft.BoxShadow]] = None

    # Texturas
    background_image: Optional[str] = None

    # Mesh multidireccional
    is_mesh: bool = False
    mesh_colors: list[str] = field(default_factory=list)


# Presets mínimos (uno por estilo)
THEME_PRESETS: dict[str, dict[str, Any]] = {
    "Azul AURA": {
        "style": "solid",
        "colors": ["#0C0C18"],
        "scheme": "triada",
        "desc": "Tema original sobrio de AURA Orion.",
    },
    "Atardecer": {
        "style": "gradient",
        "colors": ["#FF6B35", "#FF1493"],
        "scheme": "triada",
        "desc": "Transición cálida naranja-magenta.",
    },
    "Cyberpunk": {
        "style": "neon",
        "colors": ["#0A0A12", "#00FFA3"],
        "scheme": "triada",
        "desc": "Base ultra oscura con resplandor cian/verde neón.",
    },
    "Spotify Duo": {
        "style": "duotone",
        "colors": ["#FF4E50", "#191414"],
        "scheme": "triada",
        "desc": "Estética cartelera con contraste binario estricto.",
    },
    "Aurora Map": {
        "style": "gradientmap",
        "colors": ["#0B1D3A", "#00B4D8", "#90E0EF"],
        "scheme": "triada",
        "desc": "Mapeo tonal de 3 rangos de luminancia polar.",
    },
    "Malla Líquida": {
        "style": "mesh",
        "colors": ["#4158D0", "#C850C0", "#FFCC70", "#0093E9"],
        "scheme": "triada",
        "desc": "Degradado multidireccional suave y orgánico.",
    },
    "Derrame": {
        "style": "bleeding",
        "colors": ["#121224", "#8A2BE2"],
        "scheme": "triada",
        "desc": "Luz púrpura difusa proyectada sobre el entorno.",
    },
    "Mono Abismo": {
        "style": "mono",
        "colors": ["#1E3A8A"],
        "scheme": "triada",
        "desc": "Rampa pura HSL desde azul abisal hasta texto luminoso.",
    },
    "Análogo Otoño": {
        "style": "analogous",
        "colors": ["#D97706"],
        "scheme": "triada",
        "desc": "Armonía dorada y terracota en rotación de ±25°.",
    },
    "Triada Pop": {
        "style": "poly",
        "colors": ["#EC4899"],
        "scheme": "triada",
        "desc": "Tríada equidistante a 120° de alto contraste.",
    },
    "Newsprint": {
        "style": "halftone",
        "colors": ["#F3F4F6", "#1F2937"],
        "scheme": "triada",
        "desc": "Puntos de semitono retro estilo prensa/cómic.",
    },
    "Pixel 8-bit": {
        "style": "dithering",
        "colors": ["#2D3748", "#E2E8F0"],
        "scheme": "triada",
        "desc": "Matriz de Bayer ordenada para estética vintage.",
    },
}


def _safe_colors(colors: list[str], count: int, fallback: str = "#4A9EFF") -> list[str]:
    """Garantiza que la lista de colores tenga exactamente 'count' elementos hex válidos."""
    res = []
    for i in range(count):
        raw = colors[i] if i < len(colors) else fallback
        res.append(normalize_hex(raw, fallback=fallback))
    return res


def build_theme_tokens(style: str, colors: list[str], scheme: str = "triada", preset_name: str = "") -> ThemeTokens:
    """
    Construye y calcula determinísticamente los tokens visuales para cualquiera
    de los 12 estilos soportados.
    """
    st = (style or "solid").strip().lower()
    c_count = STYLE_COLOR_COUNT.get(st, 1)
    clean_colors = _safe_colors(colors, c_count)

    c1 = clean_colors[0]
    c2 = clean_colors[1] if len(clean_colors) > 1 else clean_colors[0]
    c3 = clean_colors[2] if len(clean_colors) > 2 else c2
    c4 = clean_colors[3] if len(clean_colors) > 3 else c3

    tokens = ThemeTokens(
        style=st,
        colors=clean_colors,
        scheme=scheme,
        preset_name=preset_name,
    )

    if st == "solid":
        tokens.app_bg = c1
        tokens.sidebar_bg = adjust_hsl(c1, l_factor=0.88)
        tokens.chat_bg = c1
        tokens.card_bg = adjust_hsl(c1, l_factor=1.35)
        tokens.border_color = adjust_hsl(c1, l_factor=1.75)
        accent = "#4A9EFF" if contrast_ratio(c1, "#4A9EFF") >= 3.0 else "#F59E0B"
        tokens.accent_color = accent
        tokens.text_primary = get_readable_text_color(c1)
        tokens.text_muted = adjust_hsl(tokens.text_primary, l_factor=0.72)
        tokens.user_bubble_bg = adjust_hsl(c1, l_factor=1.7)
        tokens.user_bubble_text = get_readable_text_color(tokens.user_bubble_bg)
        tokens.assistant_bubble_bg = tokens.card_bg
        tokens.assistant_bubble_text = get_readable_text_color(tokens.assistant_bubble_bg)
        tokens.button_primary_bg = accent
        tokens.button_primary_text = get_readable_text_color(accent)
        tokens.button_secondary_bg = adjust_hsl(c1, l_factor=1.4)
        tokens.button_secondary_text = tokens.text_primary

    elif st == "gradient":
        tokens.app_bg = adjust_hsl(c1, l_abs=0.07, s_factor=0.35)
        tokens.sidebar_bg = adjust_hsl(c1, l_abs=0.08, s_factor=0.4)
        tokens.sidebar_gradient = ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=[adjust_hsl(c1, l_abs=0.12, s_factor=0.6), adjust_hsl(c2, l_abs=0.10, s_factor=0.6)],
        )
        tokens.chat_bg = tokens.app_bg
        tokens.card_bg = adjust_hsl(c1, l_abs=0.14, s_factor=0.35)
        tokens.border_color = adjust_hsl(c2, l_abs=0.28, s_factor=0.5)
        tokens.accent_color = c2
        tokens.text_primary = "#F8FAFC"
        tokens.text_muted = "#94A3B8"
        tokens.user_bubble_bg = c1
        tokens.user_bubble_text = get_readable_text_color(c1)
        tokens.user_bubble_gradient = ft.LinearGradient(
            begin=ft.Alignment.CENTER_LEFT,
            end=ft.Alignment.CENTER_RIGHT,
            colors=[c1, c2],
        )
        tokens.assistant_bubble_bg = adjust_hsl(c2, l_abs=0.16, s_factor=0.45)
        tokens.assistant_bubble_text = get_readable_text_color(tokens.assistant_bubble_bg)
        tokens.button_primary_bg = c1
        tokens.button_primary_text = get_readable_text_color(c1)
        tokens.button_secondary_bg = adjust_hsl(c2, l_abs=0.20, s_factor=0.35)
        tokens.button_secondary_text = "#F8FAFC"

    elif st == "neon":
        tokens.app_bg = c1
        tokens.sidebar_bg = adjust_hsl(c1, l_factor=0.90)
        tokens.chat_bg = c1
        tokens.card_bg = adjust_hsl(c1, l_factor=1.40)
        tokens.border_color = c2
        tokens.accent_color = c2
        tokens.text_primary = "#F8FAFC"
        tokens.text_muted = "#A1A1AA"
        tokens.user_bubble_bg = adjust_hsl(c2, l_abs=0.18, s_factor=0.9)
        tokens.user_bubble_text = c2
        tokens.assistant_bubble_bg = adjust_hsl(c1, l_factor=1.60)
        tokens.assistant_bubble_text = "#E4E4E7"
        tokens.button_primary_bg = c2
        tokens.button_primary_text = get_readable_text_color(c2)
        tokens.button_secondary_bg = adjust_hsl(c1, l_factor=1.80)
        tokens.button_secondary_text = c2
        glow_shadow = [
            ft.BoxShadow(spread_radius=1, blur_radius=14, color=hex_with_alpha(c2, 0.45), offset=ft.Offset(0, 0))
        ]
        tokens.bubble_shadow = glow_shadow
        tokens.button_shadow = [
            ft.BoxShadow(spread_radius=1, blur_radius=18, color=hex_with_alpha(c2, 0.60), offset=ft.Offset(0, 0))
        ]

    elif st == "duotone":
        # Reconstrucción estricta con SOLO DOS COLORES (sin grises intermedios)
        tokens.app_bg = c2
        tokens.sidebar_bg = c2
        tokens.chat_bg = c2
        tokens.card_bg = c2
        tokens.border_color = c1
        tokens.text_primary = c1
        tokens.text_muted = c1
        tokens.accent_color = c1
        tokens.user_bubble_bg = c1
        tokens.user_bubble_text = c2
        tokens.assistant_bubble_bg = c2
        tokens.assistant_bubble_text = c1
        tokens.button_primary_bg = c1
        tokens.button_primary_text = c2
        tokens.button_secondary_bg = c2
        tokens.button_secondary_text = c1

    elif st == "gradientmap":
        # Mapeo a tres rangos: oscuras -> c1, medias -> c2, claras -> c3
        tokens.app_bg = c1
        tokens.sidebar_bg = adjust_hsl(c1, l_factor=1.12)
        tokens.chat_bg = c1
        tokens.card_bg = c2
        tokens.border_color = adjust_hsl(c2, l_factor=1.35)
        tokens.accent_color = c3
        tokens.text_primary = c3
        tokens.text_muted = adjust_hsl(c3, l_factor=0.75)
        tokens.user_bubble_bg = c3
        tokens.user_bubble_text = get_readable_text_color(c3)
        tokens.assistant_bubble_bg = c2
        tokens.assistant_bubble_text = get_readable_text_color(c2)
        tokens.button_primary_bg = c3
        tokens.button_primary_text = get_readable_text_color(c3)
        tokens.button_secondary_bg = c2
        tokens.button_secondary_text = c3

    elif st == "mesh":
        # Aproximación de degradado multidireccional fluido con 4 centros
        tokens.is_mesh = True
        tokens.mesh_colors = [c1, c2, c3, c4]
        tokens.app_bg = adjust_hsl(c1, l_abs=0.07, s_factor=0.35)
        tokens.sidebar_bg = adjust_hsl(c1, l_abs=0.09, s_factor=0.40)
        tokens.chat_bg = tokens.app_bg
        tokens.card_bg = adjust_hsl(c1, l_abs=0.15, s_factor=0.35)
        tokens.border_color = adjust_hsl(c3, l_abs=0.28, s_factor=0.45)
        tokens.accent_color = c4
        tokens.text_primary = "#F8FAFC"
        tokens.text_muted = "#94A3B8"
        tokens.user_bubble_bg = c2
        tokens.user_bubble_text = get_readable_text_color(c2)
        tokens.assistant_bubble_bg = adjust_hsl(c3, l_abs=0.18, s_factor=0.50)
        tokens.assistant_bubble_text = get_readable_text_color(tokens.assistant_bubble_bg)
        tokens.button_primary_bg = c2
        tokens.button_primary_text = get_readable_text_color(c2)
        tokens.button_secondary_bg = adjust_hsl(c4, l_abs=0.22, s_factor=0.40)
        tokens.button_secondary_text = "#F8FAFC"

    elif st == "bleeding":
        # Luz vibrante que contamina y se derrama sobre vecinos (box-shadow con blur alto)
        tokens.app_bg = c1
        tokens.sidebar_bg = adjust_hsl(c1, l_factor=0.88)
        tokens.chat_bg = c1
        tokens.card_bg = adjust_hsl(c1, l_factor=1.28)
        tokens.border_color = adjust_hsl(c1, l_factor=1.60)
        tokens.accent_color = c2
        tokens.text_primary = "#F8FAFC"
        tokens.text_muted = "#94A3B8"
        tokens.user_bubble_bg = c2
        tokens.user_bubble_text = get_readable_text_color(c2)
        tokens.assistant_bubble_bg = adjust_hsl(c1, l_factor=1.45)
        tokens.assistant_bubble_text = get_readable_text_color(tokens.assistant_bubble_bg)
        tokens.button_primary_bg = c2
        tokens.button_primary_text = get_readable_text_color(c2)
        tokens.button_secondary_bg = adjust_hsl(c1, l_factor=1.50)
        tokens.button_secondary_text = "#F8FAFC"
        bleed_shadow = [
            ft.BoxShadow(spread_radius=2, blur_radius=26, color=hex_with_alpha(c2, 0.45), offset=ft.Offset(0, 4))
        ]
        tokens.bubble_shadow = bleed_shadow
        tokens.button_shadow = [
            ft.BoxShadow(spread_radius=2, blur_radius=30, color=hex_with_alpha(c2, 0.55), offset=ft.Offset(0, 4))
        ]

    elif st == "mono":
        # Rampa monocromática pura variando únicamente S y L
        palette = derive_mono_palette(c1)
        tokens.app_bg = palette[0]
        tokens.sidebar_bg = palette[1]
        tokens.chat_bg = palette[0]
        tokens.card_bg = palette[2]
        tokens.border_color = adjust_hsl(palette[3], l_factor=0.6)
        tokens.accent_color = palette[4]
        tokens.text_primary = palette[5]
        tokens.text_muted = adjust_hsl(c1, l_abs=0.62, s_factor=0.35)
        tokens.user_bubble_bg = palette[3]
        tokens.user_bubble_text = get_readable_text_color(palette[3])
        tokens.assistant_bubble_bg = palette[2]
        tokens.assistant_bubble_text = palette[5]
        tokens.button_primary_bg = palette[3]
        tokens.button_primary_text = get_readable_text_color(palette[3])
        tokens.button_secondary_bg = palette[2]
        tokens.button_secondary_text = palette[5]

    elif st == "analogous":
        # Paleta análoga de 4 tonos en rotación +-25°
        palette = derive_analogous_palette(c1)
        tokens.app_bg = adjust_hsl(palette[0], l_abs=0.07, s_factor=0.35)
        tokens.sidebar_bg = adjust_hsl(palette[0], l_abs=0.09, s_factor=0.40)
        tokens.chat_bg = tokens.app_bg
        tokens.card_bg = adjust_hsl(palette[0], l_abs=0.15, s_factor=0.45)
        tokens.border_color = adjust_hsl(palette[2], l_abs=0.26, s_factor=0.40)
        tokens.accent_color = palette[2]
        tokens.text_primary = "#F8FAFC"
        tokens.text_muted = "#94A3B8"
        tokens.user_bubble_bg = palette[1]
        tokens.user_bubble_text = get_readable_text_color(palette[1])
        tokens.assistant_bubble_bg = adjust_hsl(palette[2], l_abs=0.18, s_factor=0.45)
        tokens.assistant_bubble_text = get_readable_text_color(tokens.assistant_bubble_bg)
        tokens.button_primary_bg = palette[1]
        tokens.button_primary_text = get_readable_text_color(palette[1])
        tokens.button_secondary_bg = adjust_hsl(palette[3], l_abs=0.20, s_factor=0.40)
        tokens.button_secondary_text = "#F8FAFC"

    elif st == "poly":
        # Policromático equilibrado según esquema (triada, complementario, etc)
        palette = derive_poly_palette(c1, scheme=scheme)
        c_accent = palette[1]
        tokens.app_bg = adjust_hsl(palette[0], l_abs=0.07, s_factor=0.30)
        tokens.sidebar_bg = adjust_hsl(palette[0], l_abs=0.09, s_factor=0.35)
        tokens.chat_bg = tokens.app_bg
        tokens.card_bg = adjust_hsl(palette[0], l_abs=0.15, s_factor=0.40)
        tokens.border_color = adjust_hsl(c_accent, l_abs=0.28, s_factor=0.40)
        tokens.accent_color = c_accent
        tokens.text_primary = "#F8FAFC"
        tokens.text_muted = "#94A3B8"
        tokens.user_bubble_bg = palette[0]
        tokens.user_bubble_text = get_readable_text_color(palette[0])
        tokens.assistant_bubble_bg = adjust_hsl(c_accent, l_abs=0.18, s_factor=0.45)
        tokens.assistant_bubble_text = get_readable_text_color(tokens.assistant_bubble_bg)
        tokens.button_primary_bg = palette[0]
        tokens.button_primary_text = get_readable_text_color(palette[0])
        tokens.button_secondary_bg = adjust_hsl(c_accent, l_abs=0.22, s_factor=0.35)
        tokens.button_secondary_text = "#F8FAFC"

    elif st in ("dithering", "halftone"):
        tile_path = get_theme_texture_tile(st, c1, c2, size=128)
        tokens.background_image = tile_path
        tokens.app_bg = c1
        tokens.sidebar_bg = c1
        tokens.chat_bg = c1
        tokens.card_bg = adjust_hsl(c1, l_factor=1.20)
        tokens.border_color = adjust_hsl(c2, l_factor=0.85)
        tokens.accent_color = c2
        tokens.text_primary = get_readable_text_color(c1)
        tokens.text_muted = adjust_hsl(tokens.text_primary, l_factor=0.75)
        tokens.user_bubble_bg = c2
        tokens.user_bubble_text = get_readable_text_color(c2)
        tokens.assistant_bubble_bg = adjust_hsl(c1, l_abs=0.19)
        tokens.assistant_bubble_text = get_readable_text_color(tokens.assistant_bubble_bg)
        tokens.button_primary_bg = c2
        tokens.button_primary_text = get_readable_text_color(c2)
        tokens.button_secondary_bg = adjust_hsl(c1, l_factor=1.35)
        tokens.button_secondary_text = tokens.text_primary

    return tokens


class ThemeManager:
    """
    Coordinador central singleton del tema visual activo de AURA.
    """

    def __init__(self) -> None:
        self._current_tokens: Optional[ThemeTokens] = None
        self._window_ref: Any = None
        self._listeners: list[Callable[[ThemeTokens], None]] = []

    @property
    def current_tokens(self) -> ThemeTokens:
        """Retorna los tokens activos o construye los predeterminados desde settings."""
        if self._current_tokens is None:
            self._current_tokens = self.load_from_settings()
        return self._current_tokens

    def register_window(self, window: Any) -> None:
        """Registra la ventana principal para sincronización de cambios de tema."""
        self._window_ref = window

    def add_listener(self, callback: Callable[[ThemeTokens], None]) -> None:
        """Registra un observador que se ejecutará al cambiar el tema."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[ThemeTokens], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def load_from_settings(self) -> ThemeTokens:
        """Carga la configuración de tema desde settings/.env."""
        style = settings.get("THEME_STYLE", "solid") or "solid"
        c1 = settings.get("THEME_COLOR_1", "#0C0C18") or "#0C0C18"
        c2 = settings.get("THEME_COLOR_2", "#1A1A36") or "#1A1A36"
        c3 = settings.get("THEME_COLOR_3", "#3B4FC8") or "#3B4FC8"
        c4 = settings.get("THEME_COLOR_4", "#60A5FA") or "#60A5FA"
        scheme = settings.get("THEME_SCHEME", "triada") or "triada"
        preset = settings.get("THEME_PRESET", "Azul AURA") or "Azul AURA"

        raw_colors = [c1, c2, c3, c4]
        count = STYLE_COLOR_COUNT.get(style, 1)
        colors = raw_colors[:count]

        tokens = build_theme_tokens(style, colors, scheme=scheme, preset_name=preset)
        self._current_tokens = tokens
        return tokens

    def apply_theme(
        self,
        style: str,
        colors: list[str],
        scheme: str = "triada",
        preset_name: str = "",
        save: bool = True,
        page: Optional[ft.Page] = None,
    ) -> ThemeTokens:
        """
        Calcula los tokens, persiste la configuración en settings/.env y
        actualiza la UI activa en caliente.
        """
        tokens = build_theme_tokens(style, colors, scheme=scheme, preset_name=preset_name)
        self._current_tokens = tokens

        if save:
            try:
                settings.set("THEME_STYLE", tokens.style)
                for i, c in enumerate(tokens.colors, start=1):
                    settings.set(f"THEME_COLOR_{i}", c)
                settings.set("THEME_SCHEME", tokens.scheme)
                if preset_name:
                    settings.set("THEME_PRESET", preset_name)
                _logger.info("Tema guardado en configuración: estilo=%s, preset=%s", tokens.style, preset_name)
            except Exception as e:
                _logger.warning("No se pudo persistir el tema en settings: %s", e)

        # Notificar a la ventana principal si está disponible
        if self._window_ref and hasattr(self._window_ref, "apply_theme"):
            try:
                self._window_ref.apply_theme(tokens)
            except Exception as e:
                _logger.debug("Error aplicando tema a ventana registrada: %s", e)

        # Si se pasó una página de Flet explícita
        if page:
            try:
                page.bgcolor = tokens.app_bg
                page.update()
            except Exception:
                pass

        # Notificar a oyentes adicionales
        for cb in self._listeners:
            try:
                cb(tokens)
            except Exception as e:
                _logger.debug("Error en listener de tema: %s", e)

        return tokens


# Singleton global de temas
theme_manager = ThemeManager()


def apply_theme(
    style: str,
    colors: list[str],
    scheme: str = "triada",
    preset_name: str = "",
    save: bool = True,
    page: Optional[ft.Page] = None,
) -> ThemeTokens:
    """Función de alto nivel para aplicar un tema completo."""
    return theme_manager.apply_theme(
        style=style,
        colors=colors,
        scheme=scheme,
        preset_name=preset_name,
        save=save,
        page=page,
    )

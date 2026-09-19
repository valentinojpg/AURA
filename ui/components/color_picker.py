"""
AURA — Componente Selector de Color y Preview de Tema en Vivo (Fase 76)

Provee:
  - ColorPicker: Círculo cromático interactivo (GestureDetector + SweepGradient),
    campo de texto hexadecimal con validación estricta (^#[0-9A-Fa-f]{6}$) y cuadro de preview.
  - ThemeLivePreview: Vista previa en vivo de 200x100 que refleja el estilo real
    (sidebar, chat, burbujas, glow, degradados mesh o texturas dithering/halftone).
"""

from __future__ import annotations

import json
import math
from typing import Any, Callable, Optional
import flet as ft

from aura.ui.color_utils import (
    hsl_to_hex,
    is_valid_hex,
    normalize_hex,
)
from aura.ui.theme import ThemeTokens


class ColorPicker(ft.Container):
    """
    Componente selector de color interactivo.
    Combina un círculo cromático táctil/ratón (hue wheel), un TextField hex y
    un visor previo del color.
    """

    def __init__(
        self,
        label: str,
        initial_color: str = "#4A9EFF",
        on_color_changed: Optional[Callable[[str], None]] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.label_text = label
        self._current_hex = normalize_hex(initial_color, fallback="#4A9EFF")
        self._on_color_changed = on_color_changed
        self._wheel_radius = 32.0
        self._build_ui()

    def _build_ui(self) -> None:
        # Círculo cromático con SweepGradient de 360 grados
        wheel_container = ft.Container(
            width=int(self._wheel_radius * 2),
            height=int(self._wheel_radius * 2),
            border_radius=int(self._wheel_radius),
            border=ft.Border.all(1, "#3A3A5E"),
            gradient=ft.SweepGradient(
                colors=[
                    "#FF0000",
                    "#FFFF00",
                    "#00FF00",
                    "#00FFFF",
                    "#0000FF",
                    "#FF00FF",
                    "#FF0000",
                ],
            ),
            tooltip="Hacé clic o arrastrá para elegir tono y matiz",
        )

        self._wheel_gesture = ft.GestureDetector(
            content=wheel_container,
            on_tap_down=self._on_wheel_press,
            on_pan_update=self._on_wheel_drag,
            mouse_cursor=ft.MouseCursor.CLICK,
        )

        self._hex_field = ft.TextField(
            value=self._current_hex,
            width=110,
            height=38,
            text_size=12,
            dense=True,
            border_color="#2A2A4E",
            focused_border_color="#4A9EFF",
            content_padding=ft.Padding.symmetric(horizontal=8, vertical=6),
            on_change=self._on_hex_text_change,
        )

        self._preview_box = ft.Container(
            width=36,
            height=36,
            bgcolor=self._current_hex,
            border_radius=6,
            border=ft.Border.all(1, "#444466"),
            tooltip=f"Color actual: {self._current_hex}",
        )

        self.content = ft.Column(
            [
                ft.Text(self.label_text, size=11, weight=ft.FontWeight.W_500, color="#C0C0DE"),
                ft.Row(
                    [
                        self._wheel_gesture,
                        ft.Column(
                            [
                                self._hex_field,
                                self._preview_box,
                            ],
                            spacing=6,
                            horizontal_alignment=ft.CrossAxisAlignment.START,
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=4,
        )

    def _extract_coords(self, e: Any) -> tuple[float, float]:
        """Extrae coordenadas locales del evento de toque o arrastre."""
        if hasattr(e, "local_position") and e.local_position is not None:
            return float(e.local_position.x), float(e.local_position.y)
        # Respaldo parseando JSON si la propiedad estructurada no vino poblada
        if hasattr(e, "data") and isinstance(e.data, str) and e.data.startswith("{"):
            try:
                d = json.loads(e.data)
                lx = d.get("lx", d.get("x", self._wheel_radius))
                ly = d.get("ly", d.get("y", self._wheel_radius))
                return float(lx), float(ly)
            except Exception:
                pass
        return self._wheel_radius, self._wheel_radius

    def _apply_wheel_selection(self, lx: float, ly: float) -> None:
        dx = lx - self._wheel_radius
        dy = ly - self._wheel_radius
        angle_rad = math.atan2(dy, dx)
        hue = (math.degrees(angle_rad)) % 360.0
        dist = math.hypot(dx, dy)
        sat = min(1.0, max(0.20, dist / self._wheel_radius))

        hex_result = hsl_to_hex(hue, sat, 0.50)
        self._current_hex = hex_result

        self._hex_field.value = hex_result
        self._hex_field.border_color = "#2A2A4E"
        self._hex_field.error_text = None
        self._preview_box.bgcolor = hex_result
        self._preview_box.tooltip = f"Color actual: {hex_result}"

        try:
            self._hex_field.update()
            self._preview_box.update()
        except Exception:
            pass

        if self._on_color_changed:
            self._on_color_changed(hex_result)

    def _on_wheel_press(self, e: ft.TapEvent) -> None:
        lx, ly = self._extract_coords(e)
        self._apply_wheel_selection(lx, ly)

    def _on_wheel_drag(self, e: ft.DragUpdateEvent) -> None:
        lx, ly = self._extract_coords(e)
        self._apply_wheel_selection(lx, ly)

    def _on_hex_text_change(self, e: ft.ControlEvent) -> None:
        val = (e.control.value or "").strip()
        if not val.startswith("#") and len(val) == 6:
            val = f"#{val}"

        if is_valid_hex(val):
            val_norm = val.upper()
            self._current_hex = val_norm
            self._hex_field.border_color = "#2A2A4E"
            self._hex_field.error_text = None
            self._preview_box.bgcolor = val_norm
            self._preview_box.tooltip = f"Color actual: {val_norm}"

            try:
                self._hex_field.update()
                self._preview_box.update()
            except Exception:
                pass

            if self._on_color_changed:
                self._on_color_changed(val_norm)
        else:
            self._hex_field.border_color = "#FF4466"
            self._hex_field.error_text = "Inválido"
            try:
                self._hex_field.update()
            except Exception:
                pass

    def get_color(self) -> str:
        """Retorna el color actual validado."""
        return self._current_hex

    def is_valid(self) -> bool:
        """Indica si el valor actual en el campo de texto es válido."""
        val = (self._hex_field.value or "").strip()
        return is_valid_hex(val)

    def set_color(self, color_hex: str) -> None:
        """Establece programáticamente el color del selector."""
        norm = normalize_hex(color_hex, fallback="#4A9EFF")
        self._current_hex = norm
        self._hex_field.value = norm
        self._hex_field.border_color = "#2A2A4E"
        self._hex_field.error_text = None
        self._preview_box.bgcolor = norm
        self._preview_box.tooltip = f"Color actual: {norm}"
        try:
            self._hex_field.update()
            self._preview_box.update()
        except Exception:
            pass


class ThemeLivePreview(ft.Container):
    """
    Vista previa interactiva de 200x100 píxeles que renderiza en miniatura
    la apariencia exacta del tema seleccionado.
    """

    def __init__(self, initial_tokens: ThemeTokens, **kwargs):
        super().__init__(
            width=200,
            height=100,
            border_radius=8,
            border=ft.Border.all(1, "#333355"),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            **kwargs,
        )
        self._tokens = initial_tokens
        self._build_preview()

    def _build_preview(self) -> None:
        t = self._tokens

        # Mini sidebar a la izquierda
        self._mini_sidebar = ft.Container(
            width=48,
            height=100,
            bgcolor=t.sidebar_bg,
            gradient=t.sidebar_gradient,
            border=ft.Border.only(right=ft.BorderSide(1, t.border_color)),
            padding=ft.Padding.all(4),
            content=ft.Column(
                [
                    ft.Container(width=14, height=14, bgcolor=t.accent_color, border_radius=7),
                    ft.Container(width=28, height=3, bgcolor=t.accent_color, border_radius=2),
                    ft.Container(width=22, height=3, bgcolor=t.border_color, border_radius=2),
                    ft.Container(width=25, height=3, bgcolor=t.border_color, border_radius=2),
                ],
                spacing=5,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        # Mini burbujas de chat
        self._mini_user_bubble = ft.Container(
            bgcolor=t.user_bubble_bg,
            gradient=t.user_bubble_gradient,
            shadow=t.bubble_shadow,
            border_radius=5,
            padding=ft.Padding.symmetric(horizontal=6, vertical=3),
            content=ft.Text("Hola AURA", size=8, color=t.user_bubble_text, weight=ft.FontWeight.W_500),
            alignment=ft.Alignment.CENTER_RIGHT,
        )

        self._mini_asst_bubble = ft.Container(
            bgcolor=t.assistant_bubble_bg,
            shadow=t.bubble_shadow,
            border_radius=5,
            padding=ft.Padding.symmetric(horizontal=6, vertical=3),
            content=ft.Text("En qué ayudo?", size=8, color=t.assistant_bubble_text),
            alignment=ft.Alignment.CENTER_LEFT,
        )

        self._mini_btn = ft.Container(
            width=36,
            height=12,
            bgcolor=t.button_primary_bg,
            shadow=t.button_shadow,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            content=ft.Text("Enviar", size=7, color=t.button_primary_text, weight=ft.FontWeight.BOLD),
        )

        chat_stack_controls: list[ft.Control] = []

        # Soporte para Mesh de 4 centros si corresponde
        if t.is_mesh and len(t.mesh_colors) >= 4:
            c1, c2, c3, c4 = t.mesh_colors[0], t.mesh_colors[1], t.mesh_colors[2], t.mesh_colors[3]
            chat_stack_controls.extend([
                ft.Container(
                    expand=True,
                    gradient=ft.RadialGradient(
                        center=ft.Alignment(-0.9, -0.9),
                        radius=1.3,
                        colors=[c1, "transparent"],
                    ),
                ),
                ft.Container(
                    expand=True,
                    gradient=ft.RadialGradient(
                        center=ft.Alignment(0.9, -0.9),
                        radius=1.3,
                        colors=[c2, "transparent"],
                    ),
                ),
                ft.Container(
                    expand=True,
                    gradient=ft.RadialGradient(
                        center=ft.Alignment(-0.9, 0.9),
                        radius=1.3,
                        colors=[c3, "transparent"],
                    ),
                ),
                ft.Container(
                    expand=True,
                    gradient=ft.RadialGradient(
                        center=ft.Alignment(0.9, 0.9),
                        radius=1.3,
                        colors=[c4, "transparent"],
                    ),
                ),
            ])

        chat_foreground = ft.Column(
            [
                ft.Row([self._mini_user_bubble], alignment=ft.MainAxisAlignment.END),
                ft.Row([self._mini_asst_bubble], alignment=ft.MainAxisAlignment.START),
                ft.Row([ft.Container(expand=True), self._mini_btn], alignment=ft.MainAxisAlignment.END),
            ],
            spacing=4,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        chat_stack_controls.append(
            ft.Container(content=chat_foreground, padding=ft.Padding.all(6), expand=True)
        )

        self._mini_chat_area = ft.Container(
            expand=True,
            bgcolor=t.chat_bg,
            image=(
                ft.DecorationImage(src=t.background_image, repeat=ft.ImageRepeat.REPEAT)
                if t.background_image
                else None
            ),
            content=ft.Stack(chat_stack_controls, expand=True),
        )

        self.bgcolor = t.app_bg
        self.content = ft.Row(
            [self._mini_sidebar, self._mini_chat_area],
            spacing=0,
            expand=True,
        )

    def update_tokens(self, new_tokens: ThemeTokens) -> None:
        """Actualiza la maqueta con los nuevos tokens calculados."""
        self._tokens = new_tokens
        self._build_preview()
        try:
            self.update()
        except Exception:
            pass

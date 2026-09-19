"""
AURA — Componente de burbuja de chat (Flet)

Renderiza mensajes individuales del chat con estilos y alineaciones
distintos para usuario, asistente, sistema y errores.
"""

from __future__ import annotations

from typing import Any, Optional
import hashlib
import flet as ft
from config.settings import settings
from ui.branding import create_brand_avatar

# ── Paleta de colores ─────────────────────────────────────────────
_COLORS = {
    "user_bg":        "#1E2A4A",
    "user_text":      "#E0E8FF",
    "user_name":      "#6B9FFF",
    "assistant_bg":   "#141426",
    "assistant_text": "#D0D0E8",
    "assistant_name": "#A78BFA",
    "system_bg":      "#121224",
    "system_text":    "#777799",
    "error_bg":       "#2A1020",
    "error_text":     "#FF6B8A",
    "error_name":     "#FF4466",
    "time_color":     "#555577",
    "speaker_icon":   "#6B9FFF",
}

_BUBBLE_EXTRA: dict[str, Any] = {
    "shadow": None,
    "user_gradient": None,
    "border_color": "#1E1E3A",
}


def update_bubble_theme(tokens: Any) -> None:
    """Actualiza la paleta activa para las burbujas de chat."""
    _COLORS["user_bg"] = tokens.user_bubble_bg
    _COLORS["user_text"] = tokens.user_bubble_text
    _COLORS["assistant_bg"] = tokens.assistant_bubble_bg
    _COLORS["assistant_text"] = tokens.assistant_bubble_text
    _COLORS["system_bg"] = tokens.card_bg
    _COLORS["time_color"] = tokens.text_muted
    _COLORS["speaker_icon"] = getattr(tokens, "accent_color", "#6B9FFF") or "#6B9FFF"
    _BUBBLE_EXTRA["shadow"] = tokens.bubble_shadow
    _BUBBLE_EXTRA["user_gradient"] = tokens.user_bubble_gradient
    _BUBBLE_EXTRA["border_color"] = tokens.border_color



class ChatBubble(ft.Container):
    """
    Burbuja visual para un mensaje de chat en Flet.

    Soporta roles:
        - "user"      → alineado a la derecha, fondo azul oscuro
        - "assistant" → alineado a la izquierda, fondo morado oscuro
        - "system"    → centrado, texto sutil
        - "error"     → alineado a la izquierda, fondo rojo oscuro
    """

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: str = "",
        message_id: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(padding=ft.Padding.symmetric(horizontal=12, vertical=4), **kwargs)
        self.role = role
        self.content_text = content
        self.timestamp = timestamp
        if not message_id:
            raw = f"{role}:{timestamp}:{content}"
            h = hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:12]
            self.message_id = f"msg_{h}_{id(self)}"
        else:
            self.message_id = message_id

        self._msg_control = None
        self._speaker_btn: Optional[ft.IconButton] = None
        self._build_bubble()

    def _build_bubble(self) -> None:
        if self.role == "system":
            self.alignment = ft.Alignment.CENTER
            self.content = ft.Container(
                content=ft.Text(
                    self.content_text,
                    size=11,
                    color=_COLORS["system_text"],
                    text_align=ft.TextAlign.CENTER,
                    selectable=True,
                ),
                padding=ft.Padding.symmetric(horizontal=16, vertical=6),
                bgcolor=_COLORS["system_bg"],
                border_radius=10,
            )
            return

        if self.role == "user":
            align = ft.Alignment.CENTER_RIGHT
            bg = _COLORS["user_bg"]
            name = "Vos"
            name_color = _COLORS["user_name"]
            text_color = _COLORS["user_text"]
        elif self.role == "error":
            align = ft.Alignment.CENTER_LEFT
            bg = _COLORS["error_bg"]
            name = "⚠ Error"
            name_color = _COLORS["error_name"]
            text_color = _COLORS["error_text"]
        else:  # assistant
            align = ft.Alignment.CENTER_LEFT
            bg = _COLORS["assistant_bg"]
            name = "AURA"
            name_color = _COLORS["assistant_name"]
            text_color = _COLORS["assistant_text"]

        self.alignment = align
        self._msg_control = ft.Text(
            self.content_text,
            size=13,
            color=text_color,
            selectable=True,
        )

        if self.role == "assistant":
            header_title = ft.Row(
                [
                    create_brand_avatar(size=18, border_color="#A78BFA", border_width=1),
                    ft.Text(name, size=11, weight=ft.FontWeight.BOLD, color=name_color),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        else:
            header_title = ft.Text(name, size=11, weight=ft.FontWeight.BOLD, color=name_color)

        bubble_elements = [
            header_title,
            self._msg_control,
        ]

        footer_items = []
        if self.timestamp:
            footer_items.append(ft.Text(self.timestamp, size=10, color=_COLORS["time_color"]))

        if self.role == "assistant" and settings.get_bool("SPEAK_BUTTON", True):
            self._speaker_btn = ft.IconButton(
                icon=ft.Icons.VOLUME_UP_ROUNDED,
                icon_size=15,
                icon_color=_COLORS.get("speaker_icon", "#6B9FFF"),
                tooltip="Escuchar mensaje",
                width=24,
                height=24,
                padding=0,
                on_click=self._on_speaker_click,
            )
            footer_items.append(self._speaker_btn)
        else:
            self._speaker_btn = None

        if footer_items:
            bubble_elements.append(
                ft.Row(
                    footer_items,
                    alignment=ft.MainAxisAlignment.END,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                )
            )

        user_grad = _BUBBLE_EXTRA.get("user_gradient") if self.role == "user" else None
        border_col = _BUBBLE_EXTRA.get("border_color", "#1E1E3A")
        shadow = _BUBBLE_EXTRA.get("shadow")

        self.content = ft.Container(
            content=ft.Column(bubble_elements, spacing=4, tight=True),
            bgcolor=bg if not user_grad else None,
            gradient=user_grad,
            shadow=shadow,
            border_radius=14,
            padding=ft.Padding.all(12),
            width=540,
            border=ft.Border.all(1, border_col),
        )

    def _on_speaker_click(self, e=None) -> None:
        try:
            from aura.voice.message_speaker import message_speaker
        except ImportError:
            from voice.message_speaker import message_speaker

        if message_speaker.is_active_for(self.message_id):
            message_speaker.stop()
            return

        text = (self.content_text or "").strip()
        if not text or text == "●":
            return

        self.set_speaker_state("synthesizing")
        message_speaker.speak_message(
            texto=text,
            message_id=self.message_id,
            on_state_change=self._on_speaker_state_change,
            on_error=self._on_speaker_error,
        )

    def _on_speaker_state_change(self, msg_id: str, state: str, error_msg: str = "") -> None:
        if msg_id == self.message_id:
            self.set_speaker_state(state, error_msg=error_msg)

    def _on_speaker_error(self, error_msg: str) -> None:
        self.set_speaker_state("error", error_msg=error_msg)
        try:
            page = getattr(self, "page", None)
            if page and hasattr(page, "overlay"):
                sb = ft.SnackBar(
                    ft.Text(f"No se pudo reproducir: {error_msg}"),
                    bgcolor="#7F1D1D",
                )
                page.overlay.append(sb)
                sb.open = True
                page.update()
        except Exception:
            pass

    def set_speaker_state(self, state: str, error_msg: str = "") -> None:
        """Actualiza el estado visual del botón parlante (idle | synthesizing | playing | error)."""
        if not self._speaker_btn:
            return

        if state == "synthesizing":
            self._speaker_btn.icon = ft.Icons.HOURGLASS_TOP
            self._speaker_btn.tooltip = "Sintetizando..."
            self._speaker_btn.icon_color = "#FBBF24"
        elif state == "playing":
            self._speaker_btn.icon = ft.Icons.STOP_ROUNDED
            self._speaker_btn.tooltip = "Detener"
            self._speaker_btn.icon_color = "#EF4444"
        elif state == "error":
            self._speaker_btn.icon = ft.Icons.VOLUME_UP_ROUNDED
            self._speaker_btn.tooltip = f"No se pudo reproducir: {error_msg}" if error_msg else "Error al reproducir"
            self._speaker_btn.icon_color = "#F87171"
        else:  # "idle"
            self._speaker_btn.icon = ft.Icons.VOLUME_UP_ROUNDED
            self._speaker_btn.tooltip = "Escuchar mensaje"
            self._speaker_btn.icon_color = _COLORS.get("speaker_icon", "#6B9FFF")

        try:
            self._speaker_btn.update()
        except Exception:
            pass

    def update_content(self, new_content: str) -> None:
        """Actualiza el texto del mensaje (usado durante streaming)."""
        self.content_text = new_content
        if self._msg_control:
            self._msg_control.value = new_content
            try:
                self.update()
            except Exception:
                pass

"""
AURA — Barra de estado global (Flet)

Componente de barra de estado en la parte inferior de la ventana principal.
Muestra el estado del sistema, nivel de actividad y errores globales.
"""

from __future__ import annotations

from typing import Any, Callable, Optional
import flet as ft
from utils.logger import get_logger

_logger = get_logger("aura.ui.status_bar")

# Paleta
_BAR_BG      = "#080812"
_DOT_IDLE    = "#444466"
_DOT_OK      = "#4CAF50"
_DOT_WARN    = "#FBBF24"
_DOT_ERR     = "#F87171"
_DOT_LOAD    = "#4A5ADF"

_TEXT_IDLE   = "#555577"
_TEXT_OK     = "#4CAF50"
_TEXT_WARN   = "#FBBF24"
_TEXT_ERR    = "#F87171"
_TEXT_LOAD   = "#4A5ADF"

_LEVEL_COLORS = {
    "idle":    (_DOT_IDLE, _TEXT_IDLE),
    "ok":      (_DOT_OK,   _TEXT_OK),
    "warning": (_DOT_WARN, _TEXT_WARN),
    "error":   (_DOT_ERR,  _TEXT_ERR),
    "loading": (_DOT_LOAD, _TEXT_LOAD),
}


class StatusBar(ft.Container):
    """
    Barra de estado global de AURA en Flet.

    Se coloca en la parte inferior de la aplicación.
    """

    def __init__(
        self,
        on_view_log: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(
            height=26,
            bgcolor=_BAR_BG,
            padding=ft.Padding.symmetric(horizontal=12),
            border=ft.Border.only(top=ft.BorderSide(1, "#1A1A2E")),
            **kwargs,
        )
        self._on_view_log = on_view_log
        self._error_count = 0
        self._build()
        self._connect_error_handler()

    def _build(self) -> None:
        self._dot = ft.Icon(ft.Icons.CIRCLE, size=7, color=_DOT_IDLE)
        self._message_label = ft.Text("Listo", size=10, color=_TEXT_IDLE)

        left = ft.Row(
            [self._dot, self._message_label],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._error_badge = ft.Text("", size=10, color=_TEXT_ERR)
        right_controls = [self._error_badge]

        if self._on_view_log:
            log_btn = ft.TextButton(
                "📋 Log",
                on_click=lambda e: self._on_view_log(),
                style=ft.ButtonStyle(
                    padding=ft.Padding.all(0),
                    text_style=ft.TextStyle(size=10, color=_TEXT_IDLE),
                ),
            )
            right_controls.append(log_btn)

        right = ft.Row(
            right_controls,
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.content = ft.Row(
            [left, right],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def set_message(self, text: str, level: str = "idle") -> None:
        dot_color, text_color = _LEVEL_COLORS.get(level, (_DOT_IDLE, _TEXT_IDLE))
        display = text if len(text) <= 80 else text[:77] + "…"

        self._dot.color = dot_color
        self._message_label.value = display
        self._message_label.color = text_color
        try:
            self._dot.update()
            self._message_label.update()
        except Exception:
            pass

    def set_error_count(self, count: int) -> None:
        self._error_count = count
        if count > 0:
            self._error_badge.value = f"⚠ {count} error{'es' if count > 1 else ''}"
        else:
            self._error_badge.value = ""
        try:
            self._error_badge.update()
        except Exception:
            pass

    def notify_error(self, level: str, title: str, message: str) -> None:
        from core.error_handler import error_handler
        bar_level = "warning" if level == "warning" else "error"
        short_title = title if len(title) <= 50 else title[:47] + "…"
        self.set_message(f"⚠ {short_title}", level=bar_level)
        self.set_error_count(error_handler.error_count)

    def _connect_error_handler(self) -> None:
        try:
            from core.error_handler import error_handler
            error_handler.subscribe(self.notify_error)
        except Exception as e:
            _logger.warning(f"No se pudo conectar StatusBar al ErrorHandler: {e}")

    def apply_theme(self, tokens: Any) -> None:
        """Aplica los tokens de tema visual a la barra de estado."""
        self.bgcolor = tokens.app_bg
        self.border = ft.Border.only(top=ft.BorderSide(1, tokens.border_color))
        self._message_label.color = tokens.text_muted
        try:
            self.update()
        except Exception:
            pass


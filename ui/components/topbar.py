"""
AURA — Barra de encabezado superior (Flet)

Componente TopBar con nombre de la página activa,
indicador de estado del sistema y versión de la aplicación.
"""

from __future__ import annotations

from typing import Any
import flet as ft
from ui.branding import create_brand_avatar
from utils.logger import get_logger

TOPBAR_BG = "#0C0C18"
TOPBAR_HEIGHT = 52


class TopBar(ft.Container):
    """
    Barra superior de AURA en Flet.

    Muestra breadcrumb de navegación, nombre de la página actual,
    estado del sistema e información de versión.
    """

    def __init__(self, **kwargs):
        super().__init__(
            height=TOPBAR_HEIGHT,
            bgcolor=TOPBAR_BG,
            padding=ft.Padding.symmetric(horizontal=20),
            border=ft.Border.only(bottom=ft.BorderSide(1, "#1A1A2E")),
            **kwargs,
        )
        self._logger = get_logger("aura.ui.topbar")
        self._build()

    def _build(self) -> None:
        # Lado izquierdo: Breadcrumb, avatar y título
        self._page_title_label = ft.Text(
            "Chat",
            size=14,
            weight=ft.FontWeight.BOLD,
            color="#C0C0E0",
        )

        left = ft.Row(
            [
                create_brand_avatar(size=24, border_color="#4A60E0", border_width=1),
                ft.Text("AURA", size=13, weight=ft.FontWeight.BOLD, color="#4A60E0"),
                ft.Text("/", size=12, color="#444466"),
                self._page_title_label,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Lado derecho: Estado y versión
        self._status_dot = ft.Icon(
            ft.Icons.CIRCLE,
            size=10,
            color="#4CAF50",
        )
        self._status_label = ft.Text(
            "Listo",
            size=12,
            color="#8888AA",
        )

        right = ft.Row(
            [
                self._status_dot,
                self._status_label,
                ft.Container(width=1, height=18, bgcolor="#1A1A2E"),
                ft.Text("v0.23.0", size=11, color="#555577"),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.content = ft.Row(
            [left, right],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def set_page_title(self, title: str) -> None:
        """Actualiza el nombre de la página activa."""
        self._page_title_label.value = title
        try:
            self._page_title_label.update()
        except Exception:
            pass

    def set_status(self, text: str, color: str = "#4CAF50") -> None:
        """Actualiza el texto y color del indicador de estado."""
        self._status_label.value = text
        self._status_dot.color = color
        try:
            self._status_label.update()
            self._status_dot.update()
        except Exception:
            pass

    def apply_theme(self, tokens: Any) -> None:
        """Aplica los tokens de tema visual a la barra superior."""
        self.bgcolor = tokens.app_bg
        self.border = ft.Border.only(bottom=ft.BorderSide(1, tokens.border_color))
        self._page_title_label.color = tokens.text_primary
        try:
            self.update()
        except Exception:
            pass

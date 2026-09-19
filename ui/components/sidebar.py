"""
AURA — Barra lateral de navegación (Flet)

Componente Sidebar con navegación entre páginas,
logo de AURA, estilo moderno e íconos interactivos.
"""

from __future__ import annotations

from typing import Callable, Optional
import flet as ft
from ui.branding import create_brand_avatar
from aura.ui.theme import theme_manager, ThemeTokens
from aura.ui.color_utils import hex_with_alpha
from utils.logger import get_logger

SIDEBAR_BG = "#0E0E1A"
SIDEBAR_WIDTH = 210

NAV_ITEMS = [
    ("chat", ft.Icons.CHAT_OUTLINED, "Chat"),
    ("skills", ft.Icons.BOLT_OUTLINED, "Skills"),
    ("automation", ft.Icons.PLAY_CIRCLE_OUTLINE, "Automatizar"),
    ("files", ft.Icons.FOLDER_OUTLINED, "Archivos"),
    ("code", ft.Icons.TERMINAL_ROUNDED, "Código"),
]

BOTTOM_NAV_ITEMS = [
    ("settings", ft.Icons.SETTINGS_OUTLINED, "Configuración"),
]


class Sidebar(ft.Container):
    """
    Barra lateral de navegación de AURA en Flet.

    Muestra el logo de AURA, botones de páginas principales y
    botón de configuración en la parte inferior.
    """

    def __init__(self, on_navigate: Optional[Callable[[str], None]] = None, **kwargs):
        super().__init__(
            width=SIDEBAR_WIDTH,
            bgcolor=SIDEBAR_BG,
            padding=ft.Padding.all(12),
            border=ft.Border.only(right=ft.BorderSide(1, "#1A1A2E")),
            **kwargs,
        )
        self._logger = get_logger("aura.ui.sidebar")
        self._on_navigate = on_navigate
        self._active_page: str = "chat"
        self._has_bg: bool = False
        self._bg_sidebar_opacity: float = 0.0
        self._button_containers: dict[str, ft.Container] = {}
        self._build()

    def _build(self) -> None:
        # Logo header con avatar circular de AURA (Fase 65)
        logo = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            create_brand_avatar(size=30, border_color="#4A9EFF", border_width=1),
                            ft.Text("AURA", size=20, weight=ft.FontWeight.BOLD, color="#E8E8F8"),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text("Proyecto Orion · v1.0.0", size=10, color="#555577"),
                ],
                spacing=2,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=12),
        )

        nav_title = ft.Container(
            content=ft.Text(
                "NAVEGACIÓN",
                size=9,
                weight=ft.FontWeight.BOLD,
                color="#444466",
            ),
            padding=ft.Padding.only(left=8, top=10, bottom=4),
        )

        nav_buttons_col = ft.Column(spacing=4)
        for page_id, icon, label in NAV_ITEMS:
            btn = self._make_nav_item(page_id, icon, label)
            nav_buttons_col.controls.append(btn)

        bottom_buttons_col = ft.Column(spacing=4)
        for page_id, icon, label in BOTTOM_NAV_ITEMS:
            btn = self._make_nav_item(page_id, icon, label)
            bottom_buttons_col.controls.append(btn)

        self.content = ft.Column(
            [
                logo,
                ft.Divider(height=1, color="#1A1A2E"),
                nav_title,
                nav_buttons_col,
                ft.Container(expand=True),  # Espacio flexible
                ft.Divider(height=1, color="#1A1A2E"),
                bottom_buttons_col,
            ],
            expand=True,
            spacing=4,
        )

        self.set_active(self._active_page)

    def _make_nav_item(self, page_id: str, icon: str, label: str) -> ft.Container:
        def on_click(e):
            self.set_active(page_id)
            if self._on_navigate:
                self._on_navigate(page_id)

        container = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, size=18, color="#7A7A9A"),
                    ft.Text(label, size=13, weight=ft.FontWeight.W_500, color="#7A7A9A"),
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=8,
            on_click=on_click,
            ink=True,
        )
        self._button_containers[page_id] = container
        return container

    def set_active(self, page_id: str) -> None:
        """Marca un botón como activo con estilo resaltado."""
        self._active_page = page_id
        tokens = theme_manager.current_tokens
        for pid, container in self._button_containers.items():
            is_active = (pid == page_id)
            row = container.content
            icon_ctrl = row.controls[0]
            text_ctrl = row.controls[1]

            if is_active:
                container.bgcolor = tokens.card_bg
                icon_ctrl.color = tokens.accent_color
                text_ctrl.color = tokens.accent_color
                text_ctrl.weight = ft.FontWeight.BOLD
                container.shadow = tokens.button_shadow
            else:
                container.bgcolor = None
                container.shadow = None
                icon_ctrl.color = tokens.text_muted
                text_ctrl.color = tokens.text_muted
                text_ctrl.weight = ft.FontWeight.W_500

            try:
                container.update()
            except Exception:
                pass

    def apply_theme(self, tokens: ThemeTokens) -> None:
        """Aplica los tokens de tema visual a la barra lateral respetando el fondo activo."""
        if self._has_bg:
            if self._bg_sidebar_opacity <= 0.0:
                self.bgcolor = "#00000000"
            else:
                self.bgcolor = hex_with_alpha(tokens.sidebar_bg, self._bg_sidebar_opacity)
            self.gradient = None
            self.image = None
            border_alpha = min(1.0, max(0.15, self._bg_sidebar_opacity + 0.15))
            self.border = ft.Border.only(right=ft.BorderSide(1, hex_with_alpha(tokens.border_color, border_alpha)))
        else:
            self.bgcolor = tokens.sidebar_bg
            self.gradient = tokens.sidebar_gradient
            if tokens.background_image:
                self.image = ft.DecorationImage(src=tokens.background_image, repeat=ft.ImageRepeat.REPEAT)
            else:
                self.image = None
            self.border = ft.Border.only(right=ft.BorderSide(1, tokens.border_color))

        self.set_active(self._active_page)
        try:
            self.update()
        except Exception:
            pass

    def apply_background_mode(
        self, has_bg: bool, opacity: float = 0.0, tokens: Optional[ThemeTokens] = None
    ) -> None:
        """Actualiza la opacidad y modo de fondo de la barra lateral en caliente."""
        self._has_bg = has_bg
        self._bg_sidebar_opacity = max(0.0, min(1.0, float(opacity)))
        tok = tokens or theme_manager.current_tokens
        self.apply_theme(tok)


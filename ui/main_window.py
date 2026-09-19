"""
AURA — Ventana principal (Flet)

Shell visual completo con:
    - TopBar (título de página, estado y versión)
    - Sidebar (navegación entre secciones)
    - ContentArea (intercambio dinámico de páginas)
    - StatusBar (estado del sistema e indicadores de error)
    - Wizard de configuración inicial de IA
"""

from __future__ import annotations

from typing import Optional
from pathlib import Path
import flet as ft

from config.settings import settings
from core.app import App
from core.error_handler import error_handler
from core.state import app_state
from ui.branding import apply_window_branding, ensure_header_logo, ensure_logo2_ico, get_assets_dir
from ui.components.sidebar import Sidebar
from ui.components.status_bar import StatusBar
from ui.components.topbar import TopBar
from ui.components.chat_bubble import update_bubble_theme
from aura.ui.theme import theme_manager, ThemeTokens
from aura.ui.color_utils import hex_with_alpha
from aura.ui.background_manager import background_manager
from aura.ui.layout_rules import validate_layout
from ui.pages.automation_page import AutomationPage
from ui.pages.chat_page import ChatPage
from ui.pages.code_page import CodePage
from ui.pages.files_page import FilesPage
from ui.pages.settings_page import SettingsPage
from ui.pages.skills_page import SkillsPage
from ui.wizard.setup_wizard import SetupWizard
from utils.logger import get_logger

_logger = get_logger("aura.ui.main_window")

PAGE_TITLES = {
    "chat": "Chat",
    "skills": "Skills",
    "automation": "Automatizaciones",
    "files": "Archivos",
    "code": "Asistente de Programación",
    "settings": "Configuración",
}

DEFAULT_PAGE = "chat"


def _resolve_box_fit(fit_str: str) -> ft.BoxFit:
    """Mapea nombre de ajuste a ft.BoxFit."""
    s = (fit_str or "cover").strip().lower()
    if s == "contain":
        return ft.BoxFit.CONTAIN
    elif s in ("stretch", "fill"):
        return ft.BoxFit.FILL
    return ft.BoxFit.COVER


class MainWindow:
    """
    Ventana principal de AURA construida sobre Flet.
    """

    APP_NAME = "AURA — Asistente Universal"
    APP_VERSION = "0.23.0"

    def __init__(self):
        self._logger = get_logger("aura.ui.main_window")
        self._controller = App()
        self._pages: dict = {}
        self._current_page_id: Optional[str] = None
        self.page: Optional[ft.Page] = None

    def run(self, view: Optional[ft.AppView] = None) -> None:
        """Punto de entrada para ejecutar la interfaz de Flet."""
        self._logger.info("Iniciando Flet app...")
        app_view = view or ft.AppView.FLET_APP
        ensure_header_logo()
        ensure_logo2_ico()
        assets_dir = get_assets_dir()
        self._logger.info(f"Directorio de assets configurado: {assets_dir}")
        ft.run(self._main, view=app_view, assets_dir=assets_dir)

    def _main(self, page: ft.Page) -> None:
        """Configuración y montaje de la página de Flet."""
        self.page = page
        page.title = self.APP_NAME
        page.theme_mode = ft.ThemeMode.DARK if settings.get("APP_THEME", "dark") == "dark" else ft.ThemeMode.LIGHT
        page.padding = 0
        page.spacing = 0
        page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
        # Registrar ventana y cargar tema configurado antes de renderizar (Fase 76 - sin flash)
        theme_manager.register_window(self)
        background_manager.register_window(self)
        current_theme = theme_manager.current_tokens
        page.bgcolor = current_theme.app_bg

        # Cargar parámetros de fondo de pantalla (Fase 78)
        bg_path = background_manager.current_image_path
        bg_fit_str = background_manager.current_fit
        sidebar_op = background_manager.current_sidebar_opacity
        scrim_op = background_manager.current_scrim_opacity

        # Controles de fondo y capa de scrim (velado)
        # Regla Fase 78 R3:
        # Raíz de la UI = ft.Stack(expand=True, fit=ft.StackFit.EXPAND) con exactamente dos hijos:
        # [0] layer de fondo, [1] layer de contenido (sidebar + vistas).
        # Layer de fondo = ft.Container(expand=True) que contiene self._bg_layer (Stack con fit=EXPAND).
        # Jamás dimensiones fijas explícitas (ni width ni height). Cobertura total vía fit=COVER/stretch.
        # SIN top/left/right/bottom: la expansión se maneja limpiamente vía expand=True y fit=EXPAND/COVER.
        self._bg_image = ft.Image(
            src=bg_path if bg_path else "",
            fit=_resolve_box_fit(bg_fit_str),
            repeat=ft.ImageRepeat.NO_REPEAT,
            gapless_playback=True,
            expand=True,
        )
        self._scrim_container = ft.Container(
            expand=True,
            bgcolor=hex_with_alpha("#000000", scrim_op) if (bg_path and scrim_op > 0) else "#00000000",
            visible=bool(bg_path and scrim_op > 0),
        )
        self._bg_layer = ft.Stack(
            controls=[
                self._bg_image,
                self._scrim_container,
            ],
            expand=True,
            fit=ft.StackFit.EXPAND,
        )
        self._bg_container = ft.Container(
            content=self._bg_layer,
            expand=True,
            visible=bool(bg_path),
        )

        # Aplicar ícono de ventana (Flet window.icon + Win32 WM_SETICON) [Fase 65]
        apply_window_branding(page, self.APP_NAME, self._logger)

        # Configurar ventana si está disponible
        try:
            if hasattr(page, "window"):
                page.window.width = 1020
                page.window.height = 700
                page.window.min_width = 800
                page.window.min_height = 550
        except Exception as e:
            self._logger.debug(f"Configuración de ventana: {e}")

        # TopBar y StatusBar
        self._topbar = TopBar()
        self._statusbar = StatusBar(on_view_log=lambda: self.navigate("settings"))

        # Content Area
        self._content_container = ft.Container(expand=True)

        # Sidebar con callback de navegación
        self._sidebar = Sidebar(on_navigate=self.navigate)

        # Instanciar páginas
        self._pages["chat"] = ChatPage(page)
        self._pages["skills"] = SkillsPage(page)
        self._pages["automation"] = AutomationPage(page)
        self._pages["files"] = FilesPage(page)
        self._pages["code"] = CodePage(page)
        self._pages["settings"] = SettingsPage(page, on_open_wizard=self._open_wizard)

        # Aplicar tema visual a los componentes montados
        self.apply_theme(current_theme, initial=True)

        # Si hay fondo activo, aplicar modo transparente desde el arranque (sin flash)
        if bg_path:
            self.apply_background_to_ui(
                bg_path=bg_path,
                fit=bg_fit_str,
                sidebar_opacity=sidebar_op,
                scrim_opacity=scrim_op,
                initial=True,
            )

        # Layout general:
        # [ TopBar ]
        # [ Sidebar | ContentArea ]
        # [ StatusBar ]
        center_row = ft.Row(
            [self._sidebar, self._content_container],
            expand=True,
            spacing=0,
        )

        main_layout = ft.Column(
            [
                self._topbar,
                center_row,
                self._statusbar,
            ],
            expand=True,
            spacing=0,
        )

        # Raíz de la interfaz como Stack con exactamente dos hijos:
        # [0] layer de fondo (self._bg_container)
        # [1] layer de contenido (main_layout: topbar + sidebar + vistas + statusbar)
        self._root_stack = ft.Stack(
            controls=[
                self._bg_container,  # [0] layer de fondo
                main_layout,         # [1] layer de contenido (sidebar + vistas)
            ],
            expand=True,
            fit=ft.StackFit.EXPAND,
        )

        page.add(self._root_stack)

        # Navegar a página inicial
        self.navigate(DEFAULT_PAGE)

        # Suscribir errores para TopBar
        error_handler.subscribe(self._on_error_for_topbar)

        # Si es primera ejecución, mostrar el wizard
        if settings.is_first_run():
            self._open_wizard()

        # Validación estructural de layout (Reglas R1 y R2)
        validate_layout(self._root_stack, page=page)

        # Sincronizar modo GIF (nativo o frames por timer)
        background_manager.sync_gif_mode()

    def navigate(self, page_id: str) -> None:
        """Cambia la página activa en el área central."""
        if page_id not in self._pages:
            self._logger.warning(f"Página '{page_id}' no existe.")
            return

        # Salir de página previa
        if self._current_page_id and self._current_page_id in self._pages:
            self._pages[self._current_page_id].on_leave()

        try:
            from voice.message_speaker import message_speaker
            message_speaker.stop()
        except Exception:
            pass

        self._current_page_id = page_id
        target_page = self._pages[page_id]

        # Asegurar transparencia si hay fondo activo
        has_active_bg = background_manager.is_active and bool(getattr(self, "_bg_container", None) and self._bg_container.visible)
        if has_active_bg:
            target_page.bgcolor = "transparent"
        else:
            target_page.bgcolor = theme_manager.current_tokens.chat_bg

        if hasattr(target_page, "apply_background_mode") and callable(getattr(target_page, "apply_background_mode")):
            try:
                target_page.apply_background_mode(has_active_bg, theme_manager.current_tokens)
            except Exception as ex:
                self._logger.debug("Error aplicando background mode al navegar a página %s: %s", page_id, ex)

        # Actualizar ContentArea
        self._content_container.content = target_page

        # Actualizar Topbar y Sidebar
        title = PAGE_TITLES.get(page_id, page_id.capitalize())
        self._topbar.set_page_title(title)
        self._sidebar.set_active(page_id)

        # Notificar entrada con aislamiento defensivo
        try:
            target_page.on_enter()
        except Exception as ex:
            self._logger.error(f"Error al entrar a la página '{page_id}': {ex}", exc_info=True)

        # Actualizar estado global
        app_state.current_page = page_id

        try:
            self._content_container.update()
        except Exception:
            pass

    def _open_wizard(self) -> None:
        """Abre el wizard de configuración inicial."""
        if self.page:
            wizard = SetupWizard(self.page, on_complete=lambda: self._on_wizard_complete())
            wizard.show()

    def _on_wizard_complete(self) -> None:
        self._statusbar.set_message("Configuración inicial guardada con éxito.", level="ok")
        if "chat" in self._pages:
            self._pages["chat"].on_enter()

    def _on_error_for_topbar(self, level: str, title: str, message: str) -> None:
        color = "#F87171" if level == "critical" else "#FBBF24"
        self._topbar.set_status(f"Error ({title[:15]})", color=color)

    def apply_theme(self, tokens: ThemeTokens, initial: bool = False) -> None:
        """Aplica tokens de tema visual a todos los componentes de la ventana."""
        if not self.page:
            return

        self.page.bgcolor = tokens.app_bg
        has_bg = background_manager.is_active

        if hasattr(self, "_sidebar") and self._sidebar:
            if has_bg:
                self._sidebar.apply_background_mode(True, background_manager.current_sidebar_opacity, tokens)
            else:
                self._sidebar.apply_theme(tokens)

        if hasattr(self, "_topbar") and self._topbar:
            self._topbar.apply_theme(tokens)
        if hasattr(self, "_statusbar") and self._statusbar:
            self._statusbar.apply_theme(tokens)

        if hasattr(self, "_content_container") and self._content_container:
            if has_bg:
                self._content_container.bgcolor = "transparent"
                self._content_container.image = None
            else:
                self._content_container.bgcolor = tokens.chat_bg
                if tokens.background_image:
                    self._content_container.image = ft.DecorationImage(
                        src=tokens.background_image,
                        repeat=ft.ImageRepeat.REPEAT,
                    )
                else:
                    self._content_container.image = None

        update_bubble_theme(tokens)

        # Propagar a páginas si implementan apply_theme
        for p in self._pages.values():
            if hasattr(p, "apply_theme") and callable(getattr(p, "apply_theme")):
                try:
                    p.apply_theme(tokens)
                except Exception as ex:
                    self._logger.debug("Error aplicando tema a página %s: %s", getattr(p, "PAGE_NAME", "?"), ex)

        # Asegurar fondo de páginas transparente si hay fondo activo
        self._update_pages_transparency(has_bg)

        if not initial:
            try:
                self.page.update()
            except Exception:
                pass

        if hasattr(self, "_root_stack") and self._root_stack:
            validate_layout(self._root_stack, page=self.page)

    def apply_background_to_ui(
        self,
        bg_path: Optional[str],
        fit: str = "cover",
        sidebar_opacity: float = 0.0,
        scrim_opacity: float = 0.25,
        initial: bool = False,
    ) -> None:
        """Aplica o quita el fondo de pantalla en la interfaz visual activa."""
        tokens = theme_manager.current_tokens
        has_bg = bool(bg_path and Path(bg_path).exists())

        if has_bg and bg_path:
            self._bg_image.src = bg_path
            self._bg_image.fit = _resolve_box_fit(fit)
            self._bg_container.visible = True

            scrim_alpha = hex_with_alpha("#000000", scrim_opacity) if scrim_opacity > 0 else "#00000000"
            self._scrim_container.bgcolor = scrim_alpha
            self._scrim_container.visible = bool(scrim_opacity > 0)

            if hasattr(self, "_sidebar") and self._sidebar:
                self._sidebar.apply_background_mode(True, sidebar_opacity, tokens)
            if hasattr(self, "_content_container") and self._content_container:
                self._content_container.bgcolor = "transparent"
                self._content_container.image = None

            self._update_pages_transparency(True)
        else:
            self._bg_image.src = ""
            self._bg_container.visible = False
            self._scrim_container.visible = False

            if hasattr(self, "_sidebar") and self._sidebar:
                self._sidebar.apply_background_mode(False, 0.0, tokens)
            if hasattr(self, "_content_container") and self._content_container:
                self._content_container.bgcolor = tokens.chat_bg
                if tokens.background_image:
                    self._content_container.image = ft.DecorationImage(
                        src=tokens.background_image,
                        repeat=ft.ImageRepeat.REPEAT,
                    )
                else:
                    self._content_container.image = None

            self._update_pages_transparency(False)

        if not initial and self.page:
            try:
                self.page.update()
            except Exception:
                pass

        if hasattr(self, "_root_stack") and self._root_stack:
            validate_layout(self._root_stack, page=self.page)

    def update_background_frame(self, frame_path: str) -> None:
        """Actualiza el fotograma activo del fondo (fallback GIF)."""
        if hasattr(self, "_bg_image") and self._bg_image:
            self._bg_image.src = frame_path
            try:
                self._bg_image.update()
            except Exception:
                pass

    def update_sidebar_opacity_in_ui(self, opacity: float) -> None:
        """Actualiza la opacidad de la barra lateral en caliente."""
        if hasattr(self, "_sidebar") and self._sidebar:
            if background_manager.is_active:
                self._sidebar.apply_background_mode(True, opacity, theme_manager.current_tokens)

    def update_scrim_opacity_in_ui(self, opacity: float) -> None:
        """Actualiza la opacidad del velado oscuro en caliente."""
        if hasattr(self, "_scrim_container") and self._scrim_container:
            has_bg = background_manager.is_active
            self._scrim_container.bgcolor = hex_with_alpha("#000000", opacity)
            self._scrim_container.visible = bool(opacity > 0 and has_bg)
            try:
                self._scrim_container.update()
            except Exception:
                pass

    def update_fit_in_ui(self, fit: str) -> None:
        """Actualiza el modo de ajuste (cover/contain/stretch) en caliente."""
        if hasattr(self, "_bg_image") and self._bg_image:
            self._bg_image.fit = _resolve_box_fit(fit)
            try:
                self._bg_image.update()
            except Exception:
                pass

    def _update_pages_transparency(self, has_bg: bool) -> None:
        """Asegura que las páginas de contenido no tapen el fondo con su propio bgcolor."""
        tokens = theme_manager.current_tokens
        for p in self._pages.values():
            p.bgcolor = "transparent" if has_bg else tokens.chat_bg
            if hasattr(p, "apply_background_mode") and callable(getattr(p, "apply_background_mode")):
                try:
                    p.apply_background_mode(has_bg, tokens)
                except Exception as ex:
                    self._logger.debug("Error aplicando background mode a página %s: %s", getattr(p, "PAGE_NAME", "?"), ex)
            try:
                p.update()
            except Exception:
                pass



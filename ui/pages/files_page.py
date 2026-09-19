"""
AURA — Página del Explorador de Archivos Inteligente (Flet — Fase 25)

Explorador de archivos integrado avanzado que permite:
1. Búsqueda inteligente: filtrado en vivo y búsqueda recursiva profunda en subdirectorios.
2. Acciones contextuales seguras: crear carpetas/archivos, renombrar, duplicar y enviar a papelera con confirmación explícita y registro en log.
3. Detección y apertura de proyectos: identificación automática de proyectos (Python, Node.js, Rust, Go, Git, etc.), con acceso rápido para abrir en VS Code o en terminal interactiva.
4. Navegación fluida con accesos rápidos, unidades de disco e inspección completa de metadatos.
"""

from __future__ import annotations

import time
import subprocess
from pathlib import Path
from typing import Optional

import flet as ft

from core.file_explorer import (
    FileExplorer,
    FileItem,
    FolderSummary,
    QuickAccessItem,
    ProjectInfo,
    format_bytes,
)
from ui.pages.base_page import BasePage
from utils.logger import get_logger

_logger = get_logger("aura.ui.page.files")

# ──────────────────────────────────────────────
# Paleta de colores consistente con AURA
# ──────────────────────────────────────────────
_BG_DARK = "#0C0C18"
_PANEL_BG = "#101024"
_SIDEBAR_BG = "#0E0E1E"
_BORDER_COLOR = "#1A1A2E"
_ROW_HOVER = "#15152F"
_ROW_SELECTED = "#1C1C3E"
_ROW_BORDER_SEL = "#3B3B66"
_TEXT_PRIMARY = "#E0E0EE"
_TEXT_SECONDARY = "#7A7A9A"
_TEXT_MUTED = "#555577"
_ACCENT_BLUE = "#4A9EFF"

# ──────────────────────────────────────────────
# Mapeo de claves de íconos a Flet Icons
# ──────────────────────────────────────────────
_ICON_MAP = {
    "FOLDER": ft.Icons.FOLDER,
    "FOLDER_OPEN": ft.Icons.FOLDER_OPEN,
    "FOLDER_ZIP": ft.Icons.FOLDER_ZIP,
    "CODE": ft.Icons.CODE,
    "HTML": ft.Icons.CODE,
    "SETTINGS": ft.Icons.SETTINGS,
    "DESCRIPTION": ft.Icons.DESCRIPTION,
    "PICTURE_AS_PDF": ft.Icons.PICTURE_AS_PDF,
    "ARTICLE": ft.Icons.ARTICLE,
    "IMAGE": ft.Icons.IMAGE,
    "AUDIO_FILE": ft.Icons.AUDIO_FILE,
    "MOVIE": ft.Icons.MOVIE,
    "TERMINAL": ft.Icons.TERMINAL,
    "STORAGE": ft.Icons.STORAGE,
    "INSERT_DRIVE_FILE": ft.Icons.INSERT_DRIVE_FILE,
    "HOME": ft.Icons.HOME,
    "WORK_OUTLINE": ft.Icons.WORK_OUTLINE,
    "DOWNLOAD": ft.Icons.DOWNLOAD,
    "DESKTOP_WINDOWS": ft.Icons.DESKTOP_WINDOWS,
}


class FilesPage(BasePage):
    """
    Página del explorador de archivos inteligente de AURA en Flet.
    """

    PAGE_NAME = "Archivos"

    def __init__(
        self,
        page: Optional[ft.Page] = None,
        app_page: Optional[ft.Page] = None,
        initial_dir: Optional[str] = None,
        **kwargs,
    ) -> None:
        p = page if page is not None else app_page
        self._explorer = FileExplorer(initial_path=initial_dir)
        self._current_items: list[FileItem] = []
        self._selected_item: Optional[FileItem] = None
        self._show_hidden: bool = False
        self._sort_by: str = "name"
        self._sort_reverse: bool = False

        # Estado de Búsqueda Inteligente
        self._search_query: str = ""
        self._is_searching: bool = False
        self._recursive_search: bool = False

        # Detección de Proyectos
        self._detected_project: Optional[ProjectInfo] = None

        # Detección de doble clic
        self._last_clicked_path: Optional[str] = None
        self._last_click_time: float = 0.0

        super().__init__(p, **kwargs)

    # ──────────────────────────────────────────
    # Construcción de la Interfaz
    # ──────────────────────────────────────────

    def _build(self) -> None:
        self.bgcolor = _BG_DARK

        # 1. Barra de navegación y búsqueda superior
        top_bar = self._build_top_bar()

        # 2. Barra secundaria de acciones rápidas y proyectos
        toolbar = self._build_quick_actions_bar()

        # 3. Panel izquierdo (Accesos Rápidos y Unidades)
        self._quick_access_col = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO)
        left_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Text("UBICACIONES", size=11, weight=ft.FontWeight.BOLD, color=_TEXT_MUTED),
                        padding=ft.Padding.only(left=12, top=12, bottom=4),
                    ),
                    self._quick_access_col,
                ],
                spacing=0,
                expand=True,
            ),
            width=210,
            bgcolor=_SIDEBAR_BG,
            border=ft.Border.only(right=ft.BorderSide(1, _BORDER_COLOR)),
        )

        # 4. Panel central (Lista de Archivos y Carpetas / Resultados)
        center_panel = self._build_center_panel()

        # 5. Panel derecho (Detalle / Metadatos / Proyecto / Acciones Contextuales)
        self._detail_col = ft.Column(expand=True, spacing=12, scroll=ft.ScrollMode.AUTO)
        right_panel = ft.Container(
            content=self._detail_col,
            width=300,
            bgcolor=_PANEL_BG,
            border=ft.Border.only(left=ft.BorderSide(1, _BORDER_COLOR)),
            padding=ft.Padding.all(16),
        )

        # 6. Barra de estado inferior
        self._status_summary_text = ft.Text("0 elementos", size=11, color=_TEXT_SECONDARY)
        self._status_feedback_text = ft.Text("", size=11, color=_ACCENT_BLUE)

        status_bar = ft.Container(
            content=ft.Row(
                [
                    self._status_summary_text,
                    self._status_feedback_text,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            height=30,
            bgcolor=_SIDEBAR_BG,
            border=ft.Border.only(top=ft.BorderSide(1, _BORDER_COLOR)),
            padding=ft.Padding.symmetric(horizontal=14),
        )

        # Disposición principal
        body_row = ft.Row(
            [left_panel, center_panel, right_panel],
            expand=True,
            spacing=0,
        )

        self.content = ft.Column(
            [
                top_bar,
                toolbar,
                body_row,
                status_bar,
            ],
            expand=True,
            spacing=0,
        )

    def _build_top_bar(self) -> ft.Container:
        """Construye la barra superior con botones de historial, ruta y búsqueda inteligente."""
        self._btn_back = ft.IconButton(
            icon=ft.Icons.ARROW_BACK,
            icon_size=18,
            icon_color=_TEXT_SECONDARY,
            disabled=True,
            tooltip="Atrás",
            on_click=self._on_back_click,
        )

        self._btn_forward = ft.IconButton(
            icon=ft.Icons.ARROW_FORWARD,
            icon_size=18,
            icon_color=_TEXT_SECONDARY,
            disabled=True,
            tooltip="Adelante",
            on_click=self._on_forward_click,
        )

        self._btn_up = ft.IconButton(
            icon=ft.Icons.ARROW_UPWARD,
            icon_size=18,
            icon_color=_TEXT_SECONDARY,
            disabled=True,
            tooltip="Subir nivel",
            on_click=self._on_up_click,
        )

        self._btn_refresh = ft.IconButton(
            icon=ft.Icons.REFRESH,
            icon_size=18,
            icon_color=_TEXT_SECONDARY,
            tooltip="Recargar carpeta",
            on_click=lambda e: self.refresh_view(),
        )

        self._path_field = ft.TextField(
            value=str(self._explorer.current_path),
            expand=True,
            dense=True,
            height=34,
            text_size=12,
            border_color="#22223A",
            focused_border_color=_ACCENT_BLUE,
            bgcolor="#14142B",
            color=_TEXT_PRIMARY,
            content_padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            on_submit=self._on_path_submit,
        )

        self._btn_go = ft.IconButton(
            icon=ft.Icons.ARROW_FORWARD_IOS,
            icon_size=13,
            icon_color=_ACCENT_BLUE,
            tooltip="Ir a la ruta",
            on_click=lambda e: self._navigate_to(self._path_field.value),
        )

        # Campo de Búsqueda Inteligente
        self._search_field = ft.TextField(
            hint_text="Buscar en carpeta...",
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            height=34,
            width=180,
            text_size=12,
            border_color="#22223A",
            focused_border_color=_ACCENT_BLUE,
            bgcolor="#14142B",
            color=_TEXT_PRIMARY,
            content_padding=ft.Padding.symmetric(horizontal=8, vertical=6),
            on_change=self._on_search_text_changed,
            on_submit=self._on_search_submitted,
        )

        self._btn_recursive_search = ft.IconButton(
            icon=ft.Icons.TRAVEL_EXPLORE,
            icon_size=18,
            icon_color=_TEXT_SECONDARY,
            tooltip="Búsqueda recursiva (en subcarpetas): Desactivada",
            on_click=self._on_toggle_recursive_search,
        )

        self._btn_clear_search = ft.IconButton(
            icon=ft.Icons.CLOSE,
            icon_size=16,
            icon_color=_TEXT_SECONDARY,
            visible=False,
            tooltip="Limpiar búsqueda",
            on_click=self._on_clear_search,
        )

        self._btn_toggle_hidden = ft.IconButton(
            icon=ft.Icons.VISIBILITY_OFF,
            icon_size=18,
            icon_color=_TEXT_SECONDARY,
            tooltip="Mostrar archivos ocultos",
            on_click=self._on_toggle_hidden_click,
        )

        self._sort_dropdown = ft.Dropdown(
            value="name",
            width=120,
            dense=True,
            text_size=12,
            border_color="#22223A",
            focused_border_color=_ACCENT_BLUE,
            bgcolor="#14142B",
            color=_TEXT_PRIMARY,
            options=[
                ft.dropdown.Option("name", "Nombre"),
                ft.dropdown.Option("size", "Tamaño"),
                ft.dropdown.Option("date", "Fecha"),
                ft.dropdown.Option("type", "Tipo"),
            ],
            on_select=self._on_sort_select,
        )

        return ft.Container(
            content=ft.Row(
                [
                    self._btn_back,
                    self._btn_forward,
                    self._btn_up,
                    self._btn_refresh,
                    self._path_field,
                    self._btn_go,
                    ft.Container(width=4),
                    self._search_field,
                    self._btn_recursive_search,
                    self._btn_clear_search,
                    self._btn_toggle_hidden,
                    self._sort_dropdown,
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=3,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=5),
            bgcolor=_SIDEBAR_BG,
            border=ft.Border.only(bottom=ft.BorderSide(1, _BORDER_COLOR)),
        )

    def _build_quick_actions_bar(self) -> ft.Container:
        """Construye la barra de herramientas de acciones contextuales y proyectos."""
        self._btn_new_folder = ft.Button(
            "Nueva Carpeta",
            icon=ft.Icons.CREATE_NEW_FOLDER,
            height=28,
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=10, vertical=2)),
            on_click=self._on_new_folder_click,
        )

        self._btn_new_file = ft.Button(
            "Nuevo Archivo",
            icon=ft.Icons.NOTE_ADD,
            height=28,
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=10, vertical=2)),
            on_click=self._on_new_file_click,
        )

        self._btn_terminal = ft.Button(
            "Terminal",
            icon=ft.Icons.TERMINAL,
            height=28,
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=10, vertical=2)),
            on_click=lambda e: self._open_terminal(),
        )

        self._btn_vscode = ft.Button(
            "VS Code",
            icon=ft.Icons.CODE,
            height=28,
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=10, vertical=2)),
            on_click=lambda e: self._open_vscode(),
        )

        self._project_badge_container = ft.Container()

        return ft.Container(
            content=ft.Row(
                [
                    ft.Row(
                        [
                            self._btn_new_folder,
                            self._btn_new_file,
                            self._btn_terminal,
                            self._btn_vscode,
                        ],
                        spacing=6,
                    ),
                    self._project_badge_container,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=4),
            bgcolor="#0B0B1A",
            border=ft.Border.only(bottom=ft.BorderSide(1, _BORDER_COLOR)),
        )

    def _build_center_panel(self) -> ft.Container:
        """Construye la lista central con encabezados y barra de resultados."""
        self._search_banner = ft.Container(visible=False)

        columns_header = ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text("Nombre", size=12, weight=ft.FontWeight.BOLD, color=_TEXT_SECONDARY),
                        expand=True,
                        padding=ft.Padding.only(left=8),
                    ),
                    ft.Container(
                        content=ft.Text("Tamaño", size=12, weight=ft.FontWeight.BOLD, color=_TEXT_SECONDARY, text_align=ft.TextAlign.RIGHT),
                        width=90,
                        alignment=ft.Alignment.CENTER_RIGHT,
                        padding=ft.Padding.only(right=12),
                    ),
                    ft.Container(
                        content=ft.Text("Tipo", size=12, weight=ft.FontWeight.BOLD, color=_TEXT_SECONDARY),
                        width=140,
                    ),
                    ft.Container(
                        content=ft.Text("Modificado", size=12, weight=ft.FontWeight.BOLD, color=_TEXT_SECONDARY),
                        width=130,
                    ),
                    ft.Container(width=46),
                ],
                alignment=ft.MainAxisAlignment.START,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            border=ft.Border.only(bottom=ft.BorderSide(1, _BORDER_COLOR)),
            bgcolor="#0E0E20",
        )

        self._files_list_view = ft.ListView(
            expand=True,
            spacing=2,
            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
        )

        return ft.Container(
            content=ft.Column(
                [
                    self._search_banner,
                    columns_header,
                    self._files_list_view,
                ],
                spacing=0,
                expand=True,
            ),
            expand=True,
            bgcolor=_BG_DARK,
        )

    # ──────────────────────────────────────────
    # Ciclo de Vida y Carga
    # ──────────────────────────────────────────

    def on_enter(self) -> None:
        """Al ingresar a la página, actualiza la vista y los lugares."""
        self.refresh_view()

    def refresh_view(self) -> None:
        """Recarga el contenido de la carpeta actual o ejecuta búsqueda activa."""
        # 1. Detección de proyecto en la carpeta actual
        try:
            self._detected_project = self._explorer.detect_project()
        except Exception as e:
            _logger.warning(f"Error al detectar proyecto: {e}")
            self._detected_project = None
        self._update_project_badge()

        # 2. Obtener elementos según búsqueda o listado normal
        if self._is_searching and self._search_query:
            self._current_items = self._explorer.search_items(
                self._search_query,
                recursive=self._recursive_search,
            )
            self._show_search_banner(True)
        else:
            self._current_items = self._explorer.list_items(
                show_hidden=self._show_hidden,
                sort_by=self._sort_by,
                reverse=self._sort_reverse,
            )
            self._show_search_banner(False)

        # 3. Actualizar barra superior
        self._path_field.value = str(self._explorer.current_path)
        self._btn_back.disabled = not self._explorer.can_go_back
        self._btn_forward.disabled = not self._explorer.can_go_forward
        self._btn_up.disabled = not self._explorer.can_go_up

        # Si el elemento seleccionado ya no existe en la vista, deseleccionarlo
        if self._selected_item and not any(i.path == self._selected_item.path for i in self._current_items):
            self._selected_item = None

        # 4. Renderizar paneles
        self._render_quick_access()
        self._render_files_list()
        self._render_detail_panel()
        self._update_status_bar()

        self._safe_update()

    def _update_project_badge(self) -> None:
        """Actualiza el badge de proyecto detectado en la barra de herramientas."""
        if self._detected_project:
            proj = self._detected_project
            icon_data = _ICON_MAP.get(proj.icon_key, ft.Icons.CODE)
            type_label = proj.project_type.upper()
            if proj.project_type.lower() == "nodejs":
                type_label = "Node.js (NODEJS)"
            elif proj.project_type.lower() == "cpp":
                type_label = "C/C++ (CPP)"
            elif proj.project_type.lower() == "vscode":
                type_label = "VS Code (VSCODE)"

            self._project_badge_container.content = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(icon_data, size=14, color=proj.color),
                        ft.Text(
                            f"Proyecto {type_label}",
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            color=proj.color,
                        ),
                    ],
                    spacing=4,
                ),
                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                bgcolor="#161630",
                border=ft.Border.all(1, proj.color),
                border_radius=10,
                tooltip=proj.description,
            )
            self._project_badge_container.visible = True
        else:
            self._project_badge_container.content = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.INFO_OUTLINE, size=14, color=_TEXT_MUTED),
                        ft.Text(
                            "Sin proyecto detectado",
                            size=11,
                            color=_TEXT_MUTED,
                        ),
                    ],
                    spacing=4,
                ),
                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                bgcolor="#101020",
                border=ft.Border.all(1, _BORDER_COLOR),
                border_radius=10,
                tooltip="Esta carpeta no contiene marcadores de proyecto reconocidos",
            )
            self._project_badge_container.visible = True

    def _show_search_banner(self, show: bool) -> None:
        """Muestra u oculta la barra informativa de resultados de búsqueda."""
        if show and self._search_query:
            count = len(self._current_items)
            mode_str = "recursiva" if self._recursive_search else "en carpeta"
            res_str = f"{count} resultado{'s' if count != 1 else ''}"
            self._search_banner.content = ft.Row(
                [
                    ft.Icon(ft.Icons.SEARCH, size=15, color=_ACCENT_BLUE),
                    ft.Text(
                        f"Búsqueda {mode_str}: '{self._search_query}' ({res_str}, {count} coincidencia{'s' if count != 1 else ''})",
                        size=12,
                        weight=ft.FontWeight.W_500,
                        color=_TEXT_PRIMARY,
                    ),
                    ft.TextButton("✕ Limpiar búsqueda", on_click=self._on_clear_search),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
            self._search_banner.padding = ft.Padding.symmetric(horizontal=12, vertical=4)
            self._search_banner.bgcolor = "#141838"
            self._search_banner.border = ft.Border.only(bottom=ft.BorderSide(1, "#262C5C"))
            self._search_banner.visible = True
            self._btn_clear_search.visible = True
        else:
            self._search_banner.visible = False
            self._btn_clear_search.visible = False

    # ──────────────────────────────────────────
    # Renderizado de Componentes
    # ──────────────────────────────────────────

    def _render_quick_access(self) -> None:
        """Genera la lista de accesos rápidos y discos en el panel izquierdo."""
        self._quick_access_col.controls.clear()

        # Lugares
        places = self._explorer.get_quick_access()
        for p in places:
            is_active = (p.path.resolve() == self._explorer.current_path.resolve())
            btn = self._build_quick_access_item(p, is_active)
            self._quick_access_col.controls.append(btn)

        # Separador y unidades
        drives = self._explorer.get_drives()
        if drives:
            self._quick_access_col.controls.append(
                ft.Container(
                    content=ft.Text("UNIDADES", size=11, weight=ft.FontWeight.BOLD, color=_TEXT_MUTED),
                    padding=ft.Padding.only(left=12, top=14, bottom=4),
                )
            )
            for d in drives:
                is_active = (d.path.resolve() == self._explorer.current_path.resolve())
                btn = self._build_quick_access_item(d, is_active)
                self._quick_access_col.controls.append(btn)

    def _build_quick_access_item(self, item: QuickAccessItem, is_active: bool) -> ft.Container:
        """Construye un botón interactivo de acceso rápido."""
        icon_data = _ICON_MAP.get(item.icon_key, ft.Icons.FOLDER)
        bg = "#1A1A38" if is_active else "transparent"
        text_color = _ACCENT_BLUE if is_active else _TEXT_PRIMARY

        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon_data, size=16, color=_ACCENT_BLUE if is_active else _TEXT_SECONDARY),
                    ft.Column(
                        [
                            ft.Text(
                                item.label,
                                size=12,
                                weight=ft.FontWeight.W_500 if is_active else ft.FontWeight.NORMAL,
                                color=text_color,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                max_lines=1,
                            ),
                            (
                                ft.Text(item.info, size=10, color=_TEXT_MUTED, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1)
                                if item.info
                                else ft.Container()
                            ),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border_radius=6,
            bgcolor=bg,
            border=ft.Border.all(1, "#33335A") if is_active else None,
            tooltip=f"{item.label}: {item.path}",
            on_click=lambda e, target=item.path: self._navigate_to(target),
        )

    def _render_files_list(self) -> None:
        """Renderiza las filas de archivos y carpetas en el panel central."""
        self._files_list_view.controls.clear()

        if not self._current_items:
            empty_text = "No se encontraron resultados para la búsqueda" if self._is_searching else "Esta carpeta está vacía"
            self._files_list_view.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.SEARCH_OFF if self._is_searching else ft.Icons.FOLDER_OPEN, size=52, color="#3B3B5B"),
                            ft.Text(empty_text, size=14, color=_TEXT_SECONDARY),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    alignment=ft.Alignment.CENTER,
                    padding=ft.Padding.symmetric(vertical=48),
                )
            )
            return

        for item in self._current_items:
            row_ctrl = self._build_file_row(item)
            self._files_list_view.controls.append(row_ctrl)

    def _build_file_row(self, item: FileItem) -> ft.Container:
        """Crea una fila interactiva para un archivo o carpeta."""
        is_selected = (self._selected_item and self._selected_item.path == item.path)
        icon_data = _ICON_MAP.get(item.icon_key, ft.Icons.INSERT_DRIVE_FILE)

        # Nombre o ruta relativa si estamos en búsqueda recursiva
        if self._is_searching and self._recursive_search:
            try:
                display_name = str(item.path.relative_to(self._explorer.current_path))
            except Exception:
                display_name = item.name
        else:
            display_name = item.name

        action_btn = ft.IconButton(
            icon=ft.Icons.ARROW_FORWARD if item.is_dir else ft.Icons.OPEN_IN_NEW,
            icon_size=15,
            icon_color=_ACCENT_BLUE,
            tooltip="Entrar a carpeta" if item.is_dir else "Abrir archivo",
            on_click=lambda e, it=item: self._on_item_action_click(it),
        )

        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon_data, size=18, color=item.icon_color),
                    ft.Text(
                        display_name,
                        size=12,
                        weight=ft.FontWeight.W_500 if is_selected else ft.FontWeight.NORMAL,
                        color=_TEXT_PRIMARY,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        max_lines=1,
                        expand=True,
                    ),
                    ft.Container(
                        content=ft.Text(item.size_str, size=11, color=_TEXT_MUTED, text_align=ft.TextAlign.RIGHT),
                        width=90,
                        alignment=ft.Alignment.CENTER_RIGHT,
                        padding=ft.Padding.only(right=12),
                    ),
                    ft.Container(
                        content=ft.Text(item.type_desc, size=11, color=_TEXT_SECONDARY, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1),
                        width=140,
                    ),
                    ft.Container(
                        content=ft.Text(item.modified_str, size=11, color=_TEXT_SECONDARY),
                        width=130,
                    ),
                    ft.Container(content=action_btn, width=46, alignment=ft.Alignment.CENTER),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            border_radius=6,
            bgcolor=_ROW_SELECTED if is_selected else "transparent",
            border=ft.Border.all(1, _ROW_BORDER_SEL) if is_selected else None,
            tooltip=f"{item.path.name} ({item.size_str})",
            on_click=lambda e, it=item: self._on_row_click(it),
        )

    def _render_detail_panel(self) -> None:
        """Renderiza metadatos detallados y acciones contextuales en el panel derecho."""
        self._detail_col.controls.clear()

        if self._selected_item is not None:
            # Detalles del elemento seleccionado
            item = self._selected_item
            icon_data = _ICON_MAP.get(item.icon_key, ft.Icons.INSERT_DRIVE_FILE)

            # Encabezado visual
            header_box = ft.Column(
                [
                    ft.Icon(icon_data, size=48, color=item.icon_color),
                    ft.Text(
                        item.name,
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color=_TEXT_PRIMARY,
                        text_align=ft.TextAlign.CENTER,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        max_lines=2,
                    ),
                    ft.Container(
                        content=ft.Text(item.type_desc, size=11, color=_ACCENT_BLUE),
                        padding=ft.Padding.symmetric(horizontal=10, vertical=3),
                        bgcolor="#161630",
                        border=ft.Border.all(1, "#282850"),
                        border_radius=10,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
            )

            # Si el elemento seleccionado es una subcarpeta con proyecto detectado
            project_box = ft.Container()
            if item.is_dir:
                sub_proj = self._explorer.detect_project(item.path)
                if sub_proj:
                    project_box = ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.CODE, size=14, color=sub_proj.color),
                                        ft.Text(f"Proyecto {sub_proj.project_type}", size=11, weight=ft.FontWeight.BOLD, color=sub_proj.color),
                                    ],
                                    spacing=4,
                                ),
                                ft.Text(sub_proj.description, size=10, color=_TEXT_SECONDARY),
                            ],
                            spacing=2,
                        ),
                        padding=ft.Padding.all(8),
                        bgcolor="#151532",
                        border=ft.Border.all(1, sub_proj.color),
                        border_radius=6,
                    )

            # Propiedades
            props: list[ft.Control] = [
                self._build_prop_row("Ubicación", str(item.path.parent), copyable=True),
                self._build_prop_row(
                    "Tamaño",
                    f"{item.size_str} ({item.size_bytes:,} bytes)" if not item.is_dir else item.size_str,
                ),
            ]

            if item.is_dir:
                summary = self._explorer.get_folder_summary(item.path)
                props.append(
                    self._build_prop_row("Contenido", f"{summary.folder_count} carpetas, {summary.file_count} archivos")
                )

            props.extend(
                [
                    self._build_prop_row("Modificado", item.modified_str),
                    self._build_prop_row("Creado", item.created_str),
                    self._build_prop_row("Permisos", "Solo lectura" if item.is_readonly else "Lectura y escritura"),
                    self._build_prop_row("Oculto", "Sí" if item.is_hidden else "No"),
                ]
            )

            # Acciones primarias y contextuales
            action_buttons = ft.Column(
                [
                    ft.Button(
                        "Entrar a carpeta" if item.is_dir else "Abrir archivo",
                        icon=ft.Icons.ARROW_FORWARD if item.is_dir else ft.Icons.OPEN_IN_NEW,
                        bgcolor="#2563EB",
                        color="#FFFFFF",
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                        on_click=lambda e, it=item: self._on_item_action_click(it),
                    ),
                    ft.OutlinedButton(
                        "Ver en explorador",
                        icon=ft.Icons.FOLDER_OPEN,
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                        on_click=lambda e, it=item: self._open_in_file_manager(it.path),
                    ),
                    ft.Row(
                        [
                            ft.OutlinedButton(
                                "Renombrar",
                                icon=ft.Icons.EDIT_OUTLINED,
                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                                expand=True,
                                on_click=lambda e, it=item: self._on_rename_click(it),
                            ),
                            ft.OutlinedButton(
                                "Duplicar",
                                icon=ft.Icons.CONTENT_COPY,
                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                                expand=True,
                                on_click=lambda e, it=item: self._on_duplicate_click(it),
                            ),
                        ],
                        spacing=6,
                    ),
                    ft.OutlinedButton(
                        "Enviar a papelera",
                        icon=ft.Icons.DELETE_OUTLINE,
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=6),
                            color="#F87171",
                        ),
                        on_click=lambda e, it=item: self._on_delete_click(it),
                    ),
                ],
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            )

            self._detail_col.controls.extend(
                [
                    header_box,
                    project_box,
                    ft.Divider(color=_BORDER_COLOR, height=8),
                    ft.Column(props, spacing=6),
                    ft.Divider(color=_BORDER_COLOR, height=8),
                    action_buttons,
                ]
            )
        else:
            # Resumen de la carpeta actual
            summary = self._explorer.get_folder_summary()
            folder_name = self._explorer.current_path.name or str(self._explorer.current_path)

            header_box = ft.Column(
                [
                    ft.Icon(ft.Icons.FOLDER, size=48, color="#FBBF24"),
                    ft.Text(
                        folder_name,
                        size=15,
                        weight=ft.FontWeight.BOLD,
                        color=_TEXT_PRIMARY,
                        text_align=ft.TextAlign.CENTER,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        max_lines=2,
                    ),
                    ft.Container(
                        content=ft.Text("Carpeta actual", size=11, color="#FBBF24"),
                        padding=ft.Padding.symmetric(horizontal=10, vertical=3),
                        bgcolor="#28220A",
                        border=ft.Border.all(1, "#504410"),
                        border_radius=10,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
            )

            # Tarjeta de Proyecto Detectado
            project_card = ft.Container()
            if self._detected_project:
                proj = self._detected_project
                icon_data = _ICON_MAP.get(proj.icon_key, ft.Icons.CODE)
                project_card = ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Icon(icon_data, size=16, color=proj.color),
                                    ft.Text(f"Proyecto {proj.project_type}", size=12, weight=ft.FontWeight.BOLD, color=proj.color),
                                ],
                                spacing=6,
                            ),
                            ft.Text(proj.description, size=11, color=_TEXT_SECONDARY),
                            ft.Container(height=4),
                            ft.Row(
                                [
                                    ft.Button(
                                        "VS Code",
                                        icon=ft.Icons.CODE,
                                        bgcolor="#2563EB",
                                        color="#FFFFFF",
                                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                                        expand=True,
                                        on_click=lambda e: self._open_vscode(),
                                    ),
                                    ft.OutlinedButton(
                                        "Terminal",
                                        icon=ft.Icons.TERMINAL,
                                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                                        expand=True,
                                        on_click=lambda e: self._open_terminal(),
                                    ),
                                ],
                                spacing=6,
                            ),
                        ],
                        spacing=4,
                    ),
                    padding=ft.Padding.all(10),
                    bgcolor="#141432",
                    border=ft.Border.all(1, proj.color),
                    border_radius=8,
                )

            props = [
                self._build_prop_row("Ruta", str(self._explorer.current_path), copyable=True),
                self._build_prop_row("Subcarpetas", str(summary.folder_count)),
                self._build_prop_row("Archivos", str(summary.file_count)),
                self._build_prop_row("Espacio total", summary.total_bytes_str),
            ]

            action_buttons = ft.Column(
                [
                    ft.Row(
                        [
                            ft.OutlinedButton(
                                "+ Carpeta",
                                icon=ft.Icons.CREATE_NEW_FOLDER,
                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                                expand=True,
                                on_click=self._on_new_folder_click,
                            ),
                            ft.OutlinedButton(
                                "+ Archivo",
                                icon=ft.Icons.NOTE_ADD,
                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                                expand=True,
                                on_click=self._on_new_file_click,
                            ),
                        ],
                        spacing=6,
                    ),
                    ft.OutlinedButton(
                        "Ver en explorador del sistema",
                        icon=ft.Icons.FOLDER_OPEN,
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                        on_click=lambda e: self._open_in_file_manager(self._explorer.current_path),
                    ),
                    ft.OutlinedButton(
                        "Abrir Terminal Aquí",
                        icon=ft.Icons.TERMINAL,
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                        on_click=lambda e: self._open_terminal(),
                    ),
                ],
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            )

            self._detail_col.controls.extend(
                [
                    header_box,
                    project_card,
                    ft.Divider(color=_BORDER_COLOR, height=8),
                    ft.Column(props, spacing=6),
                    ft.Divider(color=_BORDER_COLOR, height=8),
                    action_buttons,
                ]
            )

    def _build_prop_row(self, label: str, value: str, copyable: bool = False) -> ft.Container:
        """Construye una fila clave/valor para el panel de metadatos."""
        content_row = [
            ft.Text(label, size=11, color=_TEXT_MUTED, width=80),
            ft.Text(value, size=11, color=_TEXT_PRIMARY, expand=True, overflow=ft.TextOverflow.ELLIPSIS, max_lines=2),
        ]

        if copyable:
            content_row.append(
                ft.IconButton(
                    icon=ft.Icons.CONTENT_COPY,
                    icon_size=13,
                    icon_color=_TEXT_SECONDARY,
                    tooltip="Copiar ruta",
                    on_click=lambda e, val=value: self._copy_to_clipboard(val),
                )
            )

        return ft.Container(
            content=ft.Row(content_row, alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(vertical=2),
        )

    def _update_status_bar(self) -> None:
        """Actualiza el texto de resumen y selección en la barra inferior."""
        total = len(self._current_items)
        folders = sum(1 for i in self._current_items if i.is_dir)
        files = total - folders
        mode_str = " (búsqueda activa)" if self._is_searching else ""
        self._status_summary_text.value = f"{total} elementos ({folders} carpetas, {files} archivos){mode_str}"

    # ──────────────────────────────────────────
    # Controladores de Eventos de Navegación
    # ──────────────────────────────────────────

    def _on_back_click(self, e: ft.ControlEvent) -> None:
        """Maneja el botón de historial atrás."""
        new_path = self._explorer.go_back()
        if new_path:
            self._is_searching = False
            self.refresh_view()

    def _on_forward_click(self, e: ft.ControlEvent) -> None:
        """Maneja el botón de historial adelante."""
        new_path = self._explorer.go_forward()
        if new_path:
            self._is_searching = False
            self.refresh_view()

    def _on_up_click(self, e: ft.ControlEvent) -> None:
        """Maneja el botón subir de nivel."""
        new_path = self._explorer.go_up()
        if new_path:
            self._is_searching = False
            self.refresh_view()

    def _on_path_submit(self, e: ft.ControlEvent) -> None:
        """Maneja presionar Enter en la barra de ruta."""
        self._navigate_to(self._path_field.value)

    def _on_toggle_hidden_click(self, e: ft.ControlEvent) -> None:
        """Alterna la visualización de archivos ocultos."""
        self._show_hidden = not self._show_hidden
        self._btn_toggle_hidden.icon = ft.Icons.VISIBILITY if self._show_hidden else ft.Icons.VISIBILITY_OFF
        self._btn_toggle_hidden.icon_color = _ACCENT_BLUE if self._show_hidden else _TEXT_SECONDARY
        self._btn_toggle_hidden.tooltip = "Ocultar archivos ocultos" if self._show_hidden else "Mostrar archivos ocultos"
        self.refresh_view()

    def _on_sort_select(self, e: ft.ControlEvent) -> None:
        """Maneja el cambio de criterio de ordenamiento."""
        val = e.data if getattr(e, "data", None) is not None else getattr(e.control, "value", None)
        if val:
            self._sort_by = str(val)
            self.refresh_view()

    def _on_row_click(self, item: FileItem) -> None:
        """
        Maneja el clic en una fila de archivo/carpeta.
        Implementa selección y detección de doble clic para abrir/entrar.
        """
        now = time.time()
        is_double_click = (
            self._last_clicked_path == str(item.path)
            and (now - self._last_click_time) < 0.45
        )

        self._last_clicked_path = str(item.path)
        self._last_click_time = now

        if is_double_click:
            self._on_item_action_click(item)
            return

        self._selected_item = item
        self._render_files_list()
        self._render_detail_panel()
        self._set_status_msg(f"Seleccionado: {item.name} ({item.size_str})")
        self._safe_update()

    def _on_item_action_click(self, item: FileItem) -> None:
        """Ejecuta la acción primaria sobre el elemento: navegar o abrir."""
        if item.is_dir:
            self._is_searching = False
            self._navigate_to(item.path)
        else:
            success, msg = self._explorer.open_item(item.path)
            self._set_status_msg(msg)
            self._safe_update()

    def _navigate_to(self, target: str | Path) -> None:
        """Intenta navegar a una ruta y muestra feedback en caso de error."""
        success, err = self._explorer.navigate(target)
        if not success:
            self._set_status_msg(f"⚠️ {err}")
            self._safe_update()
            return

        self._selected_item = None
        self._is_searching = False
        self._search_field.value = ""
        self._search_query = ""
        self._set_status_msg("")
        self.refresh_view()

    # ──────────────────────────────────────────
    # Fase 25: Controladores de Búsqueda Inteligente
    # ──────────────────────────────────────────

    def _on_search_text_changed(self, e: ft.ControlEvent) -> None:
        """Filtra en vivo a medida que el usuario escribe."""
        query = self._search_field.value.strip()
        self._search_query = query
        self._is_searching = bool(query)
        self.refresh_view()

    def _on_search_submitted(self, e: ft.ControlEvent) -> None:
        """Ejecuta búsqueda al presionar Enter."""
        query = self._search_field.value.strip()
        self._search_query = query
        self._is_searching = bool(query)
        self.refresh_view()

    def _on_toggle_recursive_search(self, e: ft.ControlEvent) -> None:
        """Alterna el modo recursivo de la búsqueda."""
        self._recursive_search = not self._recursive_search
        self._btn_recursive_search.icon_color = _ACCENT_BLUE if self._recursive_search else _TEXT_SECONDARY
        self._btn_recursive_search.tooltip = (
            "Búsqueda recursiva (en subcarpetas): Activada"
            if self._recursive_search
            else "Búsqueda recursiva (en subcarpetas): Desactivada"
        )
        if self._is_searching:
            self.refresh_view()
        else:
            self._safe_update()

    def _on_clear_search(self, e: Optional[ft.ControlEvent] = None) -> None:
        """Limpia el campo de búsqueda y vuelve al listado estándar."""
        self._search_field.value = ""
        self._search_query = ""
        self._is_searching = False
        self.refresh_view()

    # ──────────────────────────────────────────
    # Fase 25: Acciones Contextuales y Modales
    # ──────────────────────────────────────────

    def _on_new_folder_click(self, e: ft.ControlEvent) -> None:
        """Abre modal para crear una nueva carpeta."""
        input_name = ft.TextField(label="Nombre de la carpeta", autofocus=True, text_size=13)

        def _close():
            if hasattr(self.app_page, "pop_dialog"):
                self.app_page.pop_dialog()

        def _confirm(evt):
            name = input_name.value.strip()
            _close()
            if not name:
                return
            res = self._explorer.create_folder(name)
            success, msg = res[0], res[1]
            self._set_status_msg(msg)
            if success:
                self.refresh_view()

        dlg = ft.AlertDialog(
            title=ft.Text("Nueva Carpeta", weight=ft.FontWeight.BOLD),
            content=ft.Column([input_name], tight=True),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda ev: _close()),
                ft.Button("Crear", bgcolor="#2563EB", color="#FFFFFF", on_click=_confirm),
            ],
        )
        if hasattr(self.app_page, "show_dialog"):
            self.app_page.show_dialog(dlg)

    def _on_new_file_click(self, e: ft.ControlEvent) -> None:
        """Abre modal para crear un nuevo archivo."""
        input_name = ft.TextField(label="Nombre del archivo (ej. notas.txt)", autofocus=True, text_size=13)

        def _close():
            if hasattr(self.app_page, "pop_dialog"):
                self.app_page.pop_dialog()

        def _confirm(evt):
            name = input_name.value.strip()
            _close()
            if not name:
                return
            res = self._explorer.create_file(name)
            success, msg = res[0], res[1]
            self._set_status_msg(msg)
            if success:
                self.refresh_view()

        dlg = ft.AlertDialog(
            title=ft.Text("Nuevo Archivo", weight=ft.FontWeight.BOLD),
            content=ft.Column([input_name], tight=True),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda ev: _close()),
                ft.Button("Crear", bgcolor="#2563EB", color="#FFFFFF", on_click=_confirm),
            ],
        )
        if hasattr(self.app_page, "show_dialog"):
            self.app_page.show_dialog(dlg)

    def _on_rename_click(self, item: FileItem) -> None:
        """Abre modal para renombrar el elemento seleccionado."""
        input_name = ft.TextField(value=item.name, label="Nuevo nombre", autofocus=True, text_size=13)

        def _close():
            if hasattr(self.app_page, "pop_dialog"):
                self.app_page.pop_dialog()

        def _confirm(evt):
            new_name = input_name.value.strip()
            _close()
            if not new_name or new_name == item.name:
                return
            res = self._explorer.rename_item(item.path, new_name)
            success, msg = res[0], res[1]
            self._set_status_msg(msg)
            if success:
                self.refresh_view()

        dlg = ft.AlertDialog(
            title=ft.Text(f"Renombrar '{item.name}'", weight=ft.FontWeight.BOLD),
            content=ft.Column([input_name], tight=True),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda ev: _close()),
                ft.Button("Renombrar", bgcolor="#2563EB", color="#FFFFFF", on_click=_confirm),
            ],
        )
        if hasattr(self.app_page, "show_dialog"):
            self.app_page.show_dialog(dlg)

    def _on_duplicate_click(self, item: FileItem) -> None:
        """Crea una copia duplicada del elemento seleccionado."""
        res = self._explorer.duplicate_item(item.path)
        success, msg = res[0], res[1]
        self._set_status_msg(msg)
        if success:
            self.refresh_view()

    def _on_delete_click(self, item: FileItem) -> None:
        """
        Acción peligrosa: solicita confirmación explícita antes de enviar a papelera.
        """
        def _close():
            if hasattr(self.app_page, "pop_dialog"):
                self.app_page.pop_dialog()

        def _confirm(evt):
            _close()
            success, msg = self._explorer.delete_item(item.path)
            self._set_status_msg(msg)
            if success:
                self._selected_item = None
                self.refresh_view()

        dlg = ft.AlertDialog(
            title=ft.Text("Confirmar eliminación", color="#F87171", weight=ft.FontWeight.BOLD),
            content=ft.Column(
                [
                    ft.Text(f"¿Estás seguro de enviar '{item.name}' a la papelera de reciclaje?", color=_TEXT_PRIMARY),
                    ft.Text(f"Ubicación: {item.path}", size=11, color=_TEXT_MUTED),
                    ft.Text(f"Tamaño: {item.size_str}", size=11, color=_TEXT_MUTED),
                    ft.Text("ℹ️ El archivo podrá recuperarse desde la papelera de reciclaje.", size=11, color=_ACCENT_BLUE),
                ],
                tight=True,
                spacing=6,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda ev: _close()),
                ft.Button(
                    "Enviar a papelera",
                    bgcolor="#8B2020",
                    color="#FFFFFF",
                    on_click=_confirm,
                ),
            ],
        )
        if hasattr(self.app_page, "show_dialog"):
            self.app_page.show_dialog(dlg)

    # ──────────────────────────────────────────
    # Fase 25: Apertura de Proyectos y Herramientas
    # ──────────────────────────────────────────

    def _open_vscode(self, target: Optional[Path] = None) -> None:
        """Abre el proyecto o archivo en Visual Studio Code."""
        tgt = target or (self._selected_item.path if self._selected_item else self._explorer.current_path)
        success, msg = self._explorer.open_in_vscode(tgt)
        self._set_status_msg(msg)
        self._safe_update()

    def _open_terminal(self, target: Optional[Path] = None) -> None:
        """Abre una consola en la ubicación seleccionada."""
        tgt = target or (self._selected_item.path if self._selected_item else self._explorer.current_path)
        success, msg = self._explorer.open_terminal(tgt)
        self._set_status_msg(msg)
        self._safe_update()

    def _open_in_file_manager(self, path: Path) -> None:
        """Abre la ubicación en el explorador nativo del sistema."""
        success, msg = self._explorer.open_in_file_manager(path)
        self._set_status_msg(msg)
        self._safe_update()

    def _copy_to_clipboard(self, text: str) -> None:
        """Copia una ruta o texto al portapapeles."""
        try:
            if self.app_page:
                self.app_page.clipboard = text
        except Exception:
            pass

        try:
            subprocess.run("clip", input=text.encode("utf-16"), check=False)
        except Exception:
            pass

        self._set_status_msg("Ruta copiada al portapapeles ✓")
        self._safe_update()

    def _set_status_msg(self, msg: str) -> None:
        """Establece un mensaje temporal en la barra de estado."""
        self._status_feedback_text.value = msg

    def _safe_update(self) -> None:
        """Intenta llamar a update() capturando errores si no está montado."""
        try:
            self.update()
        except Exception:
            pass

    # ──────────────────────────────────────────
    # Métodos y propiedades de compatibilidad
    # ──────────────────────────────────────────

    def build(self) -> ft.Control:
        self.refresh_view()
        return self

    @property
    def _search_input(self) -> ft.TextField:
        return self._search_field

    @property
    def _project_badge(self) -> Any:
        class _BadgeProxy:
            def __init__(self, container):
                self._c = container
            @property
            def visible(self):
                return self._c.visible
            @visible.setter
            def visible(self, v):
                self._c.visible = v
            @property
            def content(self):
                inner = getattr(self._c, "content", None)
                if isinstance(inner, ft.Container) and hasattr(inner, "content"):
                    return inner.content
                return inner
        return _BadgeProxy(self._project_badge_container)

    def _toggle_recursive_search(self, e: Any = None) -> None:
        self._on_toggle_recursive_search(e)

    def _show_new_folder_dialog(self, e: Any = None) -> None:
        self._on_new_folder_click(e)

    def _show_new_file_dialog(self, e: Any = None) -> None:
        self._on_new_file_click(e)

    def _show_rename_dialog(self, e: Any = None) -> None:
        if self._selected_item:
            self._on_rename_click(self._selected_item)

    def _show_delete_dialog(self, e: Any = None) -> None:
        if self._selected_item:
            self._on_delete_click(self._selected_item)

    def _on_search_change(self, e: Any = None) -> None:
        self._on_search_text_changed(e)

    def _clear_search(self, e: Any = None) -> None:
        self._on_clear_search(e)

    def _select_item(self, item: FileItem) -> None:
        self._selected_item = item
        self._render_detail_panel()

    @property
    def selected_item(self) -> Optional[FileItem]:
        return self._selected_item

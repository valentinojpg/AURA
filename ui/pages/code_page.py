"""
AURA — Página del Asistente de Programación (Flet — Fase 27)

Interfaz gráfica completa que permite a estudiantes y desarrolladores:
1. Pegar, escribir y editar código fuente en un editor multilínea monoespaciado.
2. Abrir y cargar archivos locales con codificación explícita UTF-8.
3. Seleccionar entre 9 acciones pedagógicas especializadas:
   - Explicar código (EXPLAIN)
   - Explicar errores y stacktraces (EXPLAIN_ERROR)
   - Detectar bugs y vulnerabilidades (DETECT_BUGS)
   - Generar documentación técnica y docstrings (GENERATE_DOCS)
   - Generar archivos README.md (GENERATE_README)
   - Añadir comentarios didácticos (GENERATE_COMMENTS)
   - Generar suites de tests unitarios (GENERATE_TESTS)
   - Refactorizar código (REFACTOR)
   - Análisis estático local instantáneo AST (ANALYZE)
4. Monitorear el análisis sintáctico local (AST) en tiempo real sin consumo de tokens.
5. Ejecutar acciones de IA con soporte de Streaming en vivo y cancelación no bloqueante.
6. Copiar código generado al portapapeles, reemplazar en editor y guardar en archivo.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import flet as ft

from core.code_assistant import (
    CodeAction,
    CodeAnalysis,
    CodeAssistant,
    CodeTaskResult,
    analyze_code,
    code_assistant,
    detect_language,
    extract_code_blocks,
    extract_first_code_block,
)
from ui.pages.base_page import BasePage
from utils.logger import get_logger

_logger = get_logger("aura.ui.page.code")

# ─────────────────────────────────────────────────────────────────────────────
# Paleta de Colores
# ─────────────────────────────────────────────────────────────────────────────
_BG_DARK = "#0C0C18"
_PANEL_BG = "#101024"
_EDITOR_BG = "#080812"
_CARD_BG = "#131326"
_BORDER_COLOR = "#1A1A2E"
_TEXT_PRIMARY = "#E0E0EE"
_TEXT_SECONDARY = "#7A7A9A"
_TEXT_MUTED = "#555577"
_ACCENT_BLUE = "#4A9EFF"
_ACCENT_PURPLE = "#A78BFA"
_ACCENT_GREEN = "#34D399"
_ACCENT_RED = "#F87171"
_ACCENT_YELLOW = "#FBBF24"

_CHIP_BG_ACTIVE = "#1E2A4A"
_CHIP_BORDER_ACTIVE = "#4A9EFF"
_CHIP_TEXT_ACTIVE = "#60A5FA"
_CHIP_BG_INACTIVE = "#131326"
_CHIP_BORDER_INACTIVE = "#1E1E38"
_CHIP_TEXT_INACTIVE = "#8A8AA8"

# ─────────────────────────────────────────────────────────────────────────────
# Ejemplos de Código para Pruebas Rápidas
# ─────────────────────────────────────────────────────────────────────────────
SAMPLE_CODE_SNIPPET = '''def calculate_discount(price: float, discount_rate: float) -> float:
    """Calcula el precio final con descuento."""
    if discount_rate < 0 or discount_rate > 1:
        raise ValueError("El descuento debe estar entre 0 y 1")
    
    # Bug intencional para probar detección: resta el total en lugar de aplicar tasa
    final_price = price - (price * discount_rate)
    return round(final_price, 2)

class ShoppingCart:
    """Representa el carrito de compras de un usuario."""

    def __init__(self, customer_name: str) -> None:
        self.customer = customer_name
        self.items: list[dict[str, Any]] = []

    def add_item(self, name: str, price: float, quantity: int = 1) -> None:
        self.items.append({"name": name, "price": price, "qty": quantity})

    def get_total(self) -> float:
        return sum(item["price"] * item["qty"] for item in self.items)
'''

SAMPLE_ERROR_TRACEBACK = '''Traceback (most recent call last):
  File "main.py", line 14, in <module>
    cart.add_item("Laptop", "1200", 2)
  File "main.py", line 10, in get_total
    return sum(item["price"] * item["qty"] for item in self.items)
TypeError: can't multiply sequence by non-int of type 'str'
'''

# ─────────────────────────────────────────────────────────────────────────────
# Metadatos de Acciones
# ─────────────────────────────────────────────────────────────────────────────
ACTION_METADATA: dict[CodeAction, dict[str, Any]] = {
    CodeAction.EXPLAIN: {
        "icon": ft.Icons.LIGHTBULB_OUTLINE,
        "label": "Explicar",
        "btn_label": "Explicar Código",
        "context_label": "Contexto adicional (opcional)",
        "context_hint": "Ej: Explicar para alguien que recién empieza en Python...",
    },
    CodeAction.EXPLAIN_ERROR: {
        "icon": ft.Icons.ERROR_OUTLINE,
        "label": "Error",
        "btn_label": "Diagnosticar Error",
        "context_label": "⚠️ Mensaje de Error / Traceback",
        "context_hint": "Pegá acá el traceback completo o mensaje de excepción...",
    },
    CodeAction.DETECT_BUGS: {
        "icon": ft.Icons.BUG_REPORT_OUTLINED,
        "label": "Bugs",
        "btn_label": "Detectar Bugs",
        "context_label": "Detalles del comportamiento (opcional)",
        "context_hint": "Ej: Qué entradas provocan fallos o comportamiento anómalo...",
    },
    CodeAction.GENERATE_DOCS: {
        "icon": ft.Icons.DESCRIPTION_OUTLINED,
        "label": "Docs",
        "btn_label": "Generar Docs",
        "context_label": "Estilo de documentación (opcional)",
        "context_hint": "Ej: Google style, NumPy docstrings, JSDoc...",
    },
    CodeAction.GENERATE_README: {
        "icon": ft.Icons.ARTICLE_OUTLINED,
        "label": "README",
        "btn_label": "Generar README",
        "context_label": "Detalles del proyecto (opcional)",
        "context_hint": "Nombre del proyecto, requisitos de instalación, autor...",
    },
    CodeAction.GENERATE_COMMENTS: {
        "icon": ft.Icons.COMMENT_OUTLINED,
        "label": "Comentar",
        "btn_label": "Comentar Código",
        "context_label": "Pautas de comentarios (opcional)",
        "context_hint": "Ej: Comentar únicamente las secciones complejas...",
    },
    CodeAction.GENERATE_TESTS: {
        "icon": ft.Icons.CHECK_CIRCLE_OUTLINE,
        "label": "Tests",
        "btn_label": "Generar Tests",
        "context_label": "Framework y requisitos de tests (opcional)",
        "context_hint": "Ej: Usar pytest, incluir happy path y edge cases con mocks...",
    },
    CodeAction.REFACTOR: {
        "icon": ft.Icons.AUTO_FIX_HIGH_OUTLINED,
        "label": "Refactor",
        "btn_label": "Refactorizar Código",
        "context_label": "⚡ Instrucciones de refactorización",
        "context_hint": "Ej: Aplicar principios SOLID, reducir complejidad ciclomática...",
    },
    CodeAction.ANALYZE: {
        "icon": ft.Icons.ANALYTICS_OUTLINED,
        "label": "AST",
        "btn_label": "Analizar Local (0ms)",
        "context_label": "Opciones de análisis (opcional)",
        "context_hint": "Análisis sintáctico y de estructura local sin consumo de IA.",
    },
}


class CodePage(BasePage):
    """
    Página del Asistente de Programación de AURA Orion en Flet (Fase 27).
    """

    PAGE_NAME = "Código"

    def __init__(
        self,
        page: Optional[ft.Page] = None,
        app_page: Optional[ft.Page] = None,
        assistant: Optional[CodeAssistant] = None,
        **kwargs,
    ) -> None:
        p = page if page is not None else app_page
        self._assistant = assistant or code_assistant
        self._selected_action: CodeAction = CodeAction.EXPLAIN
        self._detected_language: str = "python"
        self._is_running: bool = False
        self._cancel_requested: bool = False
        self._last_result: Optional[CodeTaskResult] = None
        self._stream_buffer: str = ""
        self._action_chips: dict[CodeAction, ft.Container] = {}

        super().__init__(p, **kwargs)

    # ─────────────────────────────────────────────────────────────────────────
    # Ciclo de Vida
    # ─────────────────────────────────────────────────────────────────────────

    def on_enter(self) -> None:
        """Al ingresar a la página, actualiza el estado del proveedor y AST."""
        self._update_provider_info()
        self._refresh_ast_analysis()

    def on_leave(self) -> None:
        """Al salir de la página, detiene cualquier streaming en curso."""
        self._cancel_requested = True

    # ─────────────────────────────────────────────────────────────────────────
    # Construcción Visual de la Interfaz
    # ─────────────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.bgcolor = _BG_DARK

        # ── 1. Top Header con Título y Estado del Proveedor ──────────────────
        self._provider_badge_text = ft.Text("IA: Conectando...", size=11, color=_TEXT_SECONDARY)
        self._provider_badge = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=_ACCENT_BLUE),
                    self._provider_badge_text,
                ],
                spacing=6,
                tight=True,
            ),
            bgcolor=_CARD_BG,
            padding=ft.Padding.symmetric(horizontal=10, vertical=5),
            border_radius=12,
            border=ft.Border.all(1, _BORDER_COLOR),
        )

        header = ft.Container(
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.TERMINAL_ROUNDED, size=22, color=_ACCENT_BLUE),
                            ft.Column(
                                [
                                    ft.Text("Asistente de Programación", size=16, weight=ft.FontWeight.BOLD, color=_TEXT_PRIMARY),
                                    ft.Text("Explicá, diagnosticá errores, generá tests y refactorizá con IA y AST local", size=11, color=_TEXT_MUTED),
                                ],
                                spacing=1,
                            ),
                        ],
                        spacing=10,
                    ),
                    self._provider_badge,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(left=16, right=16, top=10, bottom=10),
            border=ft.Border.only(bottom=ft.BorderSide(1, _BORDER_COLOR)),
            bgcolor="#0E0E1E",
        )

        # ── 2. Selector de Acciones (Chips interactivos) ──────────────────────
        chips_row = ft.Row(
            spacing=8,
            wrap=True,
            scroll=ft.ScrollMode.AUTO,
        )

        for action, meta in ACTION_METADATA.items():
            chip = self._create_action_chip(action, meta)
            self._action_chips[action] = chip
            chips_row.controls.append(chip)

        self._actions_container = ft.Container(
            content=ft.Column(
                [
                    ft.Text("ACCIONES DISPONIBLES", size=10, weight=ft.FontWeight.BOLD, color=_TEXT_MUTED),
                    chips_row,
                ],
                spacing=6,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            bgcolor=_PANEL_BG,
            border=ft.Border.only(bottom=ft.BorderSide(1, _BORDER_COLOR)),
        )

        # ── 3. Panel Izquierdo: Editor de Código y Configuración ─────────────
        left_panel = self._build_left_panel()

        # ── 4. Panel Derecho: Resultados, Markdown y Exportación ─────────────
        right_panel = self._build_right_panel()

        # ── Layout Central Dividido ──────────────────────────────────────────
        content_row = ft.Row(
            [
                left_panel,
                ft.VerticalDivider(width=1, color=_BORDER_COLOR),
                right_panel,
            ],
            expand=True,
            spacing=0,
        )

        self.content = ft.Column(
            [
                header,
                self._actions_container,
                content_row,
            ],
            expand=True,
            spacing=0,
        )

        # Estado inicial
        self._select_action(CodeAction.EXPLAIN)

    def _create_action_chip(self, action: CodeAction, meta: dict[str, Any]) -> ft.Container:
        """Crea un chip de acción interactivo con estilo cyber-dark."""
        is_active = (action == self._selected_action)

        icon_ctrl = ft.Icon(
            meta["icon"],
            size=14,
            color=_CHIP_TEXT_ACTIVE if is_active else _CHIP_TEXT_INACTIVE,
        )
        text_ctrl = ft.Text(
            meta["label"],
            size=12,
            weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.W_500,
            color=_CHIP_TEXT_ACTIVE if is_active else _CHIP_TEXT_INACTIVE,
        )

        container = ft.Container(
            content=ft.Row([icon_ctrl, text_ctrl], spacing=6, tight=True),
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            border_radius=8,
            bgcolor=_CHIP_BG_ACTIVE if is_active else _CHIP_BG_INACTIVE,
            border=ft.Border.all(1, _CHIP_BORDER_ACTIVE if is_active else _CHIP_BORDER_INACTIVE),
            ink=True,
            on_click=lambda e, act=action: self._select_action(act),
        )
        return container

    def _build_left_panel(self) -> ft.Container:
        """Construye la columna izquierda con toolbar, editor y controles de ejecución."""
        # Selector de Lenguaje
        self._language_dropdown = ft.Dropdown(
            value="auto",
            dense=True,
            width=150,
            text_size=12,
            options=[
                ft.dropdown.Option("auto", "🔍 Auto-detectar"),
                ft.dropdown.Option("python", "Python"),
                ft.dropdown.Option("javascript", "JavaScript"),
                ft.dropdown.Option("typescript", "TypeScript"),
                ft.dropdown.Option("html", "HTML"),
                ft.dropdown.Option("css", "CSS"),
                ft.dropdown.Option("cpp", "C / C++"),
                ft.dropdown.Option("csharp", "C#"),
                ft.dropdown.Option("java", "Java"),
                ft.dropdown.Option("rust", "Rust"),
                ft.dropdown.Option("go", "Go"),
                ft.dropdown.Option("sql", "SQL"),
                ft.dropdown.Option("bash", "Bash / Shell"),
                ft.dropdown.Option("json", "JSON"),
                ft.dropdown.Option("yaml", "YAML"),
                ft.dropdown.Option("markdown", "Markdown"),
            ],
            on_select=self._on_language_change,
        )

        # Carga rápida de archivos desde disco
        self._file_path_field = ft.TextField(
            hint_text="Ruta de archivo (ej: app.py)",
            dense=True,
            expand=True,
            text_size=12,
            content_padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            bgcolor=_CARD_BG,
            border_color=_BORDER_COLOR,
            border_radius=6,
            on_submit=lambda e: self._on_load_file_submit(),
        )

        self._btn_load_file = ft.IconButton(
            ft.Icons.FOLDER_OPEN_ROUNDED,
            icon_size=18,
            icon_color=_ACCENT_BLUE,
            tooltip="Cargar archivo desde disco (UTF-8)",
            on_click=lambda e: self._on_load_file_submit(),
        )

        self._btn_sample = ft.Button(
            "✨ Ejemplo",
            icon=ft.Icons.CODE_ROUNDED,
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=10, vertical=4)),
            on_click=lambda e: self._load_sample_code(),
        )

        self._btn_clear = ft.IconButton(
            ft.Icons.DELETE_OUTLINE_ROUNDED,
            icon_size=18,
            icon_color=_TEXT_MUTED,
            tooltip="Limpiar editor",
            on_click=lambda e: self.clear_all(),
        )

        toolbar = ft.Row(
            [
                self._language_dropdown,
                self._file_path_field,
                self._btn_load_file,
                self._btn_sample,
                self._btn_clear,
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Editor de Código (Multilínea monoespaciado)
        self._code_editor = ft.TextField(
            multiline=True,
            min_lines=12,
            max_lines=18,
            text_style=ft.TextStyle(font_family="Consolas, 'Courier New', monospace", size=13),
            bgcolor=_EDITOR_BG,
            border_color=_BORDER_COLOR,
            border_radius=8,
            content_padding=ft.Padding.all(12),
            hint_text="Pegá o escribí tu código acá...",
            hint_style=ft.TextStyle(color=_TEXT_MUTED, size=13),
            on_change=self._on_code_change,
        )

        # Barra de Estado AST y Estadísticas de Código
        self._ast_badge_text = ft.Text("AST: Listo", size=11, color=_TEXT_SECONDARY)
        self._stats_badge_text = ft.Text("0 líneas · 0 caracteres", size=11, color=_TEXT_MUTED)

        ast_stats_bar = ft.Container(
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.DATA_OBJECT_ROUNDED, size=14, color=_ACCENT_BLUE),
                            self._ast_badge_text,
                        ],
                        spacing=6,
                        tight=True,
                    ),
                    self._stats_badge_text,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        )

        # Campo Secundario de Contexto o Error Traceback
        self._context_title_text = ft.Text(
            "Detalles o contexto adicional (opcional)",
            size=11,
            weight=ft.FontWeight.BOLD,
            color=_TEXT_SECONDARY,
        )
        self._context_input = ft.TextField(
            multiline=True,
            min_lines=2,
            max_lines=4,
            text_size=12,
            bgcolor=_CARD_BG,
            border_color=_BORDER_COLOR,
            border_radius=6,
            content_padding=ft.Padding.all(8),
            hint_text="Ingresá información complementaria...",
            hint_style=ft.TextStyle(color=_TEXT_MUTED, size=12),
        )

        context_container = ft.Column(
            [
                self._context_title_text,
                self._context_input,
            ],
            spacing=4,
        )

        # Controles de Ejecución
        self._btn_execute = ft.FilledButton(
            "Ejecutar Explicación",
            icon=ft.Icons.ROCKET_LAUNCH_ROUNDED,
            on_click=lambda e: self.execute_current_action(),
        )

        self._btn_cancel = ft.OutlinedButton(
            "Detener",
            icon=ft.Icons.STOP_ROUNDED,
            visible=False,
            on_click=lambda e: self._cancel_execution(),
        )

        self._streaming_switch = ft.Switch(
            label="Stream",
            value=True,
            tooltip="Mostrar la respuesta de la IA en tiempo real mientras se genera",
        )

        self._progress_indicator = ft.ProgressRing(width=18, height=18, visible=False)
        self._feedback_status_text = ft.Text("", size=11, color=_TEXT_SECONDARY)

        action_controls_row = ft.Row(
            [
                self._btn_execute,
                self._btn_cancel,
                self._streaming_switch,
                self._progress_indicator,
                self._feedback_status_text,
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Ensamblar Panel Izquierdo
        left_content = ft.Column(
            [
                toolbar,
                ast_stats_bar,
                self._code_editor,
                context_container,
                action_controls_row,
            ],
            spacing=10,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

        return ft.Container(
            content=left_content,
            expand=1,
            padding=ft.Padding.all(16),
            bgcolor=_BG_DARK,
        )

    def _build_right_panel(self) -> ft.Container:
        """Construye la columna derecha con visualizador Markdown, acciones de exportación y portapapeles."""
        # Barra superior de resultados
        self._result_meta_text = ft.Text("", size=11, color=_TEXT_MUTED)

        self._btn_copy_code = ft.Button(
            "📋 Copiar Código",
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=10, vertical=4)),
            tooltip="Copiar al portapapeles el bloque de código extraído",
            on_click=lambda e: self._copy_code_to_clipboard(),
        )

        self._btn_copy_all = ft.Button(
            "📄 Copiar Todo",
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=10, vertical=4)),
            tooltip="Copiar toda la respuesta en Markdown",
            on_click=lambda e: self._copy_all_to_clipboard(),
        )

        self._btn_load_to_editor = ft.Button(
            "🔄 Reemplazar en Editor",
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=10, vertical=4)),
            tooltip="Cargar el código corregido o refactorizado directamente en el editor",
            on_click=lambda e: self._load_result_into_editor(),
        )

        self._btn_save_file = ft.Button(
            "💾 Guardar...",
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=10, vertical=4)),
            tooltip="Guardar resultado en un archivo local UTF-8",
            on_click=lambda e: self._show_save_dialog(),
        )

        results_toolbar = ft.Row(
            [
                ft.Row(
                    [
                        ft.Text("Resultado", size=14, weight=ft.FontWeight.BOLD, color=_TEXT_PRIMARY),
                        self._result_meta_text,
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        self._btn_copy_code,
                        self._btn_copy_all,
                        self._btn_load_to_editor,
                        self._btn_save_file,
                    ],
                    spacing=6,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Vista de Resultado (Markdown enriquecido)
        self._result_markdown = ft.Markdown(
            value="",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            code_theme=ft.MarkdownCodeTheme.ATOM_ONE_DARK,
        )

        # Placeholder visual cuando no hay resultado
        self._placeholder_view = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.CODE_ROUNDED, size=52, color="#22223E"),
                    ft.Text("Asistente de Programación listo", size=15, weight=ft.FontWeight.BOLD, color=_TEXT_SECONDARY),
                    ft.Text(
                        "Pegá un bloque de código, cargá un archivo o probá un ejemplo.\n"
                        "Seleccioná una acción (Explicar, Bugs, Tests, Refactor o AST) y hacé clic en Ejecutar.",
                        size=12,
                        color=_TEXT_MUTED,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=10,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
            padding=ft.Padding.all(24),
        )

        self._result_scroll_container = ft.Column(
            [self._placeholder_view],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

        results_box = ft.Container(
            content=self._result_scroll_container,
            expand=True,
            bgcolor=_PANEL_BG,
            border=ft.Border.all(1, _BORDER_COLOR),
            border_radius=8,
            padding=ft.Padding.all(16),
        )

        right_content = ft.Column(
            [
                results_toolbar,
                results_box,
            ],
            spacing=10,
            expand=True,
        )

        return ft.Container(
            content=right_content,
            expand=1,
            padding=ft.Padding.all(16),
            bgcolor=_BG_DARK,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Gestión de Selección de Acciones
    # ─────────────────────────────────────────────────────────────────────────

    def _select_action(self, action: CodeAction) -> None:
        """Cambia la acción activa y actualiza la UI correspondientemente."""
        self._selected_action = action
        meta = ACTION_METADATA.get(action, ACTION_METADATA[CodeAction.EXPLAIN])

        # Actualizar estilo visual de los chips
        for act, chip in self._action_chips.items():
            is_active = (act == action)
            row = chip.content
            icon_ctrl = row.controls[0]
            text_ctrl = row.controls[1]

            if is_active:
                chip.bgcolor = _CHIP_BG_ACTIVE
                chip.border = ft.Border.all(1, _CHIP_BORDER_ACTIVE)
                icon_ctrl.color = _CHIP_TEXT_ACTIVE
                text_ctrl.color = _CHIP_TEXT_ACTIVE
                text_ctrl.weight = ft.FontWeight.BOLD
            else:
                chip.bgcolor = _CHIP_BG_INACTIVE
                chip.border = ft.Border.all(1, _CHIP_BORDER_INACTIVE)
                icon_ctrl.color = _CHIP_TEXT_INACTIVE
                text_ctrl.color = _CHIP_TEXT_INACTIVE
                text_ctrl.weight = ft.FontWeight.W_500

        # Actualizar botón de ejecución y contexto secundario
        self._btn_execute.content = f"🚀 {meta['btn_label']}"
        self._context_title_text.value = meta["context_label"]
        self._context_input.hint_text = meta["context_hint"]

        # Resaltado específico para error o refactor
        if action == CodeAction.EXPLAIN_ERROR:
            self._context_title_text.color = _ACCENT_YELLOW
        elif action == CodeAction.REFACTOR:
            self._context_title_text.color = _ACCENT_PURPLE
        else:
            self._context_title_text.color = _TEXT_SECONDARY

        self._safe_update()

    # ─────────────────────────────────────────────────────────────────────────
    # Detección de Lenguaje y Análisis Sintáctico AST en Tiempo Real
    # ─────────────────────────────────────────────────────────────────────────

    def _on_code_change(self, e: ft.ControlEvent) -> None:
        """Handler llamado al tipear o pegar código en el editor."""
        self._refresh_ast_analysis()

    def _on_language_change(self, e: ft.ControlEvent) -> None:
        """Handler llamado cuando el usuario fuerza un lenguaje en el dropdown."""
        self._refresh_ast_analysis()

    def _refresh_ast_analysis(self) -> None:
        """Actualiza estadísticas, lenguaje detectado y validación AST."""
        code = self._code_editor.value or ""
        lines_count = len(code.splitlines()) if code else 0
        char_count = len(code)

        self._stats_badge_text.value = f"{lines_count} líneas · {char_count} caracteres"

        # Determinar lenguaje
        dropdown_val = self._language_dropdown.value
        if dropdown_val == "auto" or not dropdown_val:
            detected = detect_language(code)
            self._detected_language = detected
        else:
            self._detected_language = dropdown_val

        # Análisis AST local
        if not code.strip():
            self._ast_badge_text.value = "AST: Listo"
            self._ast_badge_text.color = _TEXT_SECONDARY
        elif self._detected_language == "python":
            analysis = analyze_code(code, "python")
            if analysis.is_syntax_valid:
                funcs_str = f", {len(analysis.functions)} funcs" if analysis.functions else ""
                classes_str = f", {len(analysis.classes)} clases" if analysis.classes else ""
                self._ast_badge_text.value = f"🟢 Sintaxis Python OK{funcs_str}{classes_str}"
                self._ast_badge_text.color = _ACCENT_GREEN
            else:
                line_info = f" (L:{analysis.syntax_error_line})" if analysis.syntax_error_line else ""
                self._ast_badge_text.value = f"🔴 Error sintaxis{line_info}: {analysis.syntax_error[:25]}"
                self._ast_badge_text.color = _ACCENT_RED
        else:
            self._ast_badge_text.value = f"🔵 Lenguaje: {self._detected_language.upper()}"
            self._ast_badge_text.color = _ACCENT_BLUE

        self._safe_update()

    # ─────────────────────────────────────────────────────────────────────────
    # Carga de Archivos y Ejemplos
    # ─────────────────────────────────────────────────────────────────────────

    def _on_load_file_submit(self) -> None:
        """Carga el archivo especificado en la barra de ruta."""
        path_str = (self._file_path_field.value or "").strip()
        if not path_str:
            self._set_status("Por favor ingresá una ruta de archivo", level="warn")
            return
        self.load_file(path_str)

    def load_file(self, file_path: str) -> bool:
        """
        Carga un archivo de código desde el disco usando UTF-8 explícito.
        """
        try:
            res = self._assistant.read_code_file(file_path)
            if isinstance(res, tuple):
                content, detected = res[0], res[1]
            else:
                content, detected = res, detect_language(res, filename=file_path)

            self._code_editor.value = content
            self._file_path_field.value = file_path
            self._detected_language = detected

            # Ajustar dropdown si coincide
            valid_options = [opt.key for opt in self._language_dropdown.options]
            if detected in valid_options:
                self._language_dropdown.value = detected
            else:
                self._language_dropdown.value = "auto"

            self._refresh_ast_analysis()
            p_name = Path(file_path).name
            self._set_status(f"Archivo cargado: {p_name} ✓", level="ok")
            return True
        except Exception as e:
            _logger.error(f"Error cargando archivo {file_path}: {e}")
            self._set_status(f"Error cargando archivo: {e}", level="error")
            return False

    def _load_sample_code(self) -> None:
        """Carga un snippet didáctico en el editor para probar inmediatamente."""
        self._code_editor.value = SAMPLE_CODE_SNIPPET
        self._language_dropdown.value = "python"
        self._detected_language = "python"
        self._file_path_field.value = "ejemplo_tienda.py"

        if self._selected_action == CodeAction.EXPLAIN_ERROR:
            self._context_input.value = SAMPLE_ERROR_TRACEBACK
        else:
            self._context_input.value = ""

        self._refresh_ast_analysis()
        self._set_status("Ejemplo cargado en el editor ✓", level="ok")

    def clear_all(self) -> None:
        """Limpia el editor, contexto y resultados."""
        self._code_editor.value = ""
        self._context_input.value = ""
        self._file_path_field.value = ""
        self._language_dropdown.value = "auto"
        self._result_markdown.value = ""
        self._result_scroll_container.controls = [self._placeholder_view]
        self._result_meta_text.value = ""
        self._last_result = None
        self._refresh_ast_analysis()
        self._set_status("Editor limpiado", level="info")

    # ─────────────────────────────────────────────────────────────────────────
    # Ejecución de Acciones e Integración de Streaming
    # ─────────────────────────────────────────────────────────────────────────

    def execute_current_action(self) -> None:
        """Inicia la ejecución de la acción seleccionada en un hilo de fondo."""
        if self._is_running:
            return

        code = (self._code_editor.value or "").strip()
        context = (self._context_input.value or "").strip()

        # Validación
        if not code and not context:
            self._set_status("Por favor ingresá código o un traceback para analizar", level="warn")
            return

        # Para EXPLAIN_ERROR permitimos que el código esté en contexto si code está vacío
        if self._selected_action == CodeAction.EXPLAIN_ERROR and not code:
            code = context
            context = ""

        # Acción puramente local AST (0ms)
        if self._selected_action == CodeAction.ANALYZE:
            self._execute_local_ast_action(code)
            return

        # Configurar estado de ejecución
        self._is_running = True
        self._cancel_requested = False
        self._stream_buffer = ""
        self._btn_execute.visible = False
        self._btn_cancel.visible = True
        self._progress_indicator.visible = True
        self._set_status("Generando respuesta...", level="info")

        # Preparar contenedor visual de resultados
        self._result_markdown.value = ""
        self._result_scroll_container.controls = [self._result_markdown]
        self._result_meta_text.value = "Procesando..."
        self._safe_update()

        use_stream = self._streaming_switch.value is True

        thread = threading.Thread(
            target=self._run_action_thread,
            args=(self._selected_action, code, self._detected_language, context, use_stream),
            daemon=True,
        )
        thread.start()

    def _execute_local_ast_action(self, code: str) -> None:
        """Ejecuta el análisis local AST instantáneo."""
        result = self._assistant.execute_action(
            CodeAction.ANALYZE,
            code,
            language=self._detected_language,
        )
        self._last_result = result
        analysis = result.analysis

        # Formatear reporte didáctico de AST
        if analysis and analysis.is_syntax_valid:
            lines = [
                "### 🔍 Reporte de Análisis Estático Local (0ms, 0 tokens)\n",
                f"- **Estado Sintáctico**: 🟢 Sintaxis Python Válida",
                f"- **Líneas Totales**: {analysis.lines_count}",
                f"- **Caracteres**: {analysis.char_count}",
                f"- **Funciones Detectadas ({len(analysis.functions)})**: {', '.join(analysis.functions) if analysis.functions else 'Ninguna'}",
                f"- **Clases Detectadas ({len(analysis.classes)})**: {', '.join(analysis.classes) if analysis.classes else 'Ninguna'}",
                f"- **Módulos Importados ({len(analysis.imports)})**: {', '.join(analysis.imports) if analysis.imports else 'Ninguno'}",
            ]
        elif analysis:
            lines = [
                "### 🔍 Reporte de Análisis Estático Local (0ms, 0 tokens)\n",
                f"- **Estado Sintáctico**: 🔴 **Error de Sintaxis Encontrado**",
                f"- **Línea del Error**: {analysis.syntax_error_line}",
                f"- **Columna / Offset**: {analysis.syntax_error_offset}",
                f"- **Mensaje**: `{analysis.syntax_error}`",
                "\n> *Tip*: Usá la acción **Error** o **Bugs** para que AURA te brinde la solución recomendada.",
            ]
        else:
            lines = [f"### Análisis de Código\n{result.content}"]

        report_md = "\n".join(lines)
        self._result_markdown.value = report_md
        self._result_scroll_container.controls = [self._result_markdown]
        self._result_meta_text.value = "⚡ Local AST · 0ms"
        self._set_status("Análisis AST completado ✓", level="ok")
        self._safe_update()

    def _run_action_thread(
        self,
        action: CodeAction,
        code: str,
        language: str,
        context: str,
        use_stream: bool,
    ) -> None:
        """Hilo de fondo para no bloquear la interfaz gráfica de Flet."""
        start_time = time.time()
        provider_name = getattr(self._assistant.provider, "provider_name", "AI")
        model_name = getattr(self._assistant.provider, "model", "") or "modelo"

        try:
            if use_stream:
                chunks = []
                stream_iter = self._assistant.execute_action_stream(
                    action=action,
                    code=code,
                    language=language,
                    context=context,
                )

                for chunk in stream_iter:
                    if self._cancel_requested:
                        chunks.append("\n\n*(Ejecución detenida por el usuario)*")
                        break
                    chunks.append(chunk)
                    self._stream_buffer = "".join(chunks)
                    self._result_markdown.value = self._stream_buffer
                    self._safe_update()

                full_content = "".join(chunks)
                elapsed = time.time() - start_time
                extracted = extract_first_code_block(full_content)
                all_blocks = extract_code_blocks(full_content)

                self._last_result = CodeTaskResult(
                    action=action.value,
                    language=language,
                    content=full_content,
                    success=True,
                    model=model_name,
                    provider=provider_name,
                    extracted_code=extracted,
                    all_code_blocks=all_blocks,
                    analysis=analyze_code(code, language),
                    metadata={"elapsed": round(elapsed, 2)},
                )

                self._result_meta_text.value = f"🤖 {provider_name} · {elapsed:.1f}s"
                self._set_status("Completado con éxito ✓", level="ok")

            else:
                result = self._assistant.execute_action(
                    action=action,
                    code=code,
                    language=language,
                    context=context,
                )
                elapsed = time.time() - start_time
                self._last_result = result

                if result.success:
                    self._result_markdown.value = result.content
                    self._result_meta_text.value = f"🤖 {result.provider or provider_name} · {elapsed:.1f}s"
                    self._set_status("Completado con éxito ✓", level="ok")
                else:
                    err_msg = result.error_message or "Error desconocido del proveedor"
                    self._result_markdown.value = f"### ⚠️ Error en Asistente de Programación\n\n```text\n{err_msg}\n```"
                    self._result_meta_text.value = "⚠️ Error"
                    self._set_status(f"Error: {err_msg[:40]}", level="error")

        except Exception as e:
            _logger.error(f"Excepción en _run_action_thread: {e}", exc_info=True)
            self._result_markdown.value = f"### ⚠️ Error al procesar solicitud\n\n```text\n{e}\n```"
            self._set_status(f"Fallo: {str(e)[:40]}", level="error")
        finally:
            self._is_running = False
            self._btn_execute.visible = True
            self._btn_cancel.visible = False
            self._progress_indicator.visible = False
            self._safe_update()

    def _cancel_execution(self) -> None:
        """Solicita la detención inmediata del streaming."""
        self._cancel_requested = True
        self._set_status("Deteniendo generación...", level="warn")

    # ─────────────────────────────────────────────────────────────────────────
    # Operaciones con Resultados: Portapapeles, Editor y Archivos
    # ─────────────────────────────────────────────────────────────────────────

    def _copy_code_to_clipboard(self) -> None:
        """Copia el primer bloque de código extraído al portapapeles."""
        code_to_copy = ""
        if self._last_result and self._last_result.extracted_code:
            code_to_copy = self._last_result.extracted_code
        elif self._result_markdown.value:
            code_to_copy = extract_first_code_block(self._result_markdown.value)

        if not code_to_copy:
            self._set_status("No se detectaron bloques de código para copiar", level="warn")
            return

        self._set_clipboard(code_to_copy)
        self._set_status("Código copiado al portapapeles ✓", level="ok")

    def _copy_all_to_clipboard(self) -> None:
        """Copia toda la salida Markdown al portapapeles."""
        text = self._result_markdown.value or ""
        if not text:
            self._set_status("No hay texto para copiar", level="warn")
            return

        self._set_clipboard(text)
        self._set_status("Texto completo copiado al portapapeles ✓", level="ok")

    def _load_result_into_editor(self) -> None:
        """Carga el código generado directamente en el editor de entrada."""
        code_to_load = ""
        if self._last_result and self._last_result.extracted_code:
            code_to_load = self._last_result.extracted_code
        elif self._result_markdown.value:
            code_to_load = extract_first_code_block(self._result_markdown.value)

        if not code_to_load:
            self._set_status("No se encontró código extraíble para cargar en el editor", level="warn")
            return

        self._code_editor.value = code_to_load
        self._refresh_ast_analysis()
        self._set_status("Código cargado en el editor ✓", level="ok")

    def _show_save_dialog(self) -> None:
        """Abre un diálogo para guardar el resultado en un archivo local UTF-8."""
        code_to_save = ""
        if self._last_result and self._last_result.extracted_code:
            code_to_save = self._last_result.extracted_code
        elif self._result_markdown.value:
            code_to_save = self._result_markdown.value

        if not code_to_save:
            self._set_status("No hay contenido para guardar", level="warn")
            return

        # Nombre sugerido según acción
        ext = ".py" if self._detected_language == "python" else f".{self._detected_language}"
        default_filename = "README.md" if self._selected_action == CodeAction.GENERATE_README else f"codigo_generado{ext}"

        input_path = ft.TextField(
            label="Ruta o nombre del archivo de destino",
            value=default_filename,
            dense=True,
            text_size=12,
        )

        def _close_dialog():
            if hasattr(self.app_page, "pop_dialog"):
                self.app_page.pop_dialog()

        def _confirm_save(e):
            dest = input_path.value.strip()
            _close_dialog()
            if not dest:
                return
            self.save_result_to_file(dest, code_to_save)

        dlg = ft.AlertDialog(
            title=ft.Text("Guardar Resultado en Archivo", weight=ft.FontWeight.BOLD),
            content=ft.Column([input_path], tight=True),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda ev: _close_dialog()),
                ft.FilledButton("Guardar", on_click=_confirm_save),
            ],
        )

        if hasattr(self.app_page, "show_dialog"):
            self.app_page.show_dialog(dlg)

    def save_result_to_file(self, target_path: str, content: str = "") -> bool:
        """
        Guarda el resultado en disco usando codificación explícita UTF-8.
        """
        try:
            data = content
            if not data:
                if self._last_result and self._last_result.extracted_code:
                    data = self._last_result.extracted_code
                else:
                    data = self._result_markdown.value or ""

            target = Path(target_path).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)

            with open(target, "w", encoding="utf-8", errors="replace") as f:
                f.write(data)

            self._set_status(f"Guardado exitosamente en: {target.name} ✓", level="ok")
            return True
        except Exception as e:
            _logger.error(f"Error guardando archivo {target_path}: {e}")
            self._set_status(f"Error al guardar archivo: {e}", level="error")
            return False

    def _set_clipboard(self, text: str) -> None:
        """Copia texto al portapapeles usando Flet y fallback Windows."""
        try:
            if self.app_page:
                self.app_page.clipboard = text
        except Exception:
            pass

        try:
            subprocess.run("clip", input=text.encode("utf-16"), check=False)
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # Utilidades de Estado y Sincronización
    # ─────────────────────────────────────────────────────────────────────────

    def _update_provider_info(self) -> None:
        """Actualiza el indicador del proveedor de IA activo."""
        try:
            provider = self._assistant.provider
            p_name = getattr(provider, "provider_name", "AI")
            model = getattr(provider, "model", "")
            model_info = f" ({model})" if model else ""
            self._provider_badge_text.value = f"IA: {p_name}{model_info}"
        except Exception as e:
            self._provider_badge_text.value = "IA: Configurable"
        self._safe_update()

    def _set_status(self, msg: str, level: str = "info") -> None:
        """Establece un mensaje temporal en la barra de feedback."""
        color_map = {
            "ok": _ACCENT_GREEN,
            "warn": _ACCENT_YELLOW,
            "error": _ACCENT_RED,
            "info": _TEXT_SECONDARY,
        }
        self._feedback_status_text.value = msg
        self._feedback_status_text.color = color_map.get(level, _TEXT_SECONDARY)
        self._safe_update()

    def _safe_update(self) -> None:
        """Actualiza el control de forma segura capturando posibles excepciones de ciclo de vida."""
        try:
            self.update()
        except Exception:
            pass


# Alias de compatibilidad
CodeAssistantPage = CodePage

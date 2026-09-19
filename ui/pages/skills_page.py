"""
AURA — Página de Skills (Flet)

Pantalla de gestión y prueba de skills:
  - Listado de skills registradas en panel lateral
  - Detalle de la skill seleccionada (metadatos, autor, versión, comandos)
  - Switch para habilitar / deshabilitar
  - Panel de prueba para ejecutar comandos de la skill y ver salida
"""

from __future__ import annotations

import threading
from typing import Optional
import flet as ft

from skills.skill_registry import skill_registry, SkillEntry
from ui.pages.base_page import BasePage
from utils.logger import get_logger

_logger = get_logger("aura.ui.page.skills")

_BG_DARK     = "#0C0C18"
_CARD_BG     = "#13132A"
_CARD_SEL    = "#1C1C3E"
_PANEL_BG    = "#101024"
_ACCENT      = "#A78BFA"
_ACCENT_BLUE = "#4A9EFF"


class SkillsPage(BasePage):
    """
    Página de administración y prueba de Skills en Flet.
    """

    PAGE_NAME = "Skills"

    def __init__(self, page: ft.Page, **kwargs):
        self._entries: list[SkillEntry] = []
        self._selected_entry: Optional[SkillEntry] = None
        super().__init__(page, **kwargs)

    def _build(self) -> None:
        self.bgcolor = _BG_DARK

        # ── Panel izquierdo: Lista de skills ──────────────────────
        self._skills_list_view = ft.ListView(
            expand=True,
            spacing=8,
            padding=ft.Padding.all(12),
        )

        left_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text("Skills Registradas", size=13, weight=ft.FontWeight.BOLD, color="#C0C0E0"),
                                ft.IconButton(
                                    ft.Icons.REFRESH,
                                    icon_size=18,
                                    icon_color="#7A7A9A",
                                    tooltip="Actualizar lista",
                                    on_click=lambda e: self.refresh_skills(),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                        border=ft.Border.only(bottom=ft.BorderSide(1, "#1A1A2E")),
                    ),
                    self._skills_list_view,
                ],
                expand=True,
                spacing=0,
            ),
            width=320,
            bgcolor="#0E0E1E",
            border=ft.Border.only(right=ft.BorderSide(1, "#1A1A2E")),
        )

        # ── Panel derecho: Detalle y prueba de la skill ───────────
        self._detail_content = ft.Column(expand=True, spacing=16, scroll=ft.ScrollMode.AUTO)
        right_panel = ft.Container(
            content=self._detail_content,
            expand=True,
            padding=ft.Padding.all(24),
            bgcolor=_PANEL_BG,
        )

        self.content = ft.Row([left_panel, right_panel], expand=True, spacing=0)

    def on_enter(self) -> None:
        self.refresh_skills()

    def refresh_skills(self) -> None:
        def _load():
            try:
                skill_registry.discover_builtin()
                self._entries = skill_registry.list_all()
            except Exception as e:
                _logger.error(f"Error listando skills: {e}")
                self._entries = []

            self._render_skills_list()

        threading.Thread(target=_load, daemon=True).start()

    def _render_skills_list(self) -> None:
        self._skills_list_view.controls.clear()

        if not self._entries:
            self._skills_list_view.controls.append(
                ft.Container(
                    content=ft.Text("No hay skills disponibles", color="#555577", size=12),
                    alignment=ft.Alignment.CENTER,
                    padding=ft.Padding.all(20),
                )
            )
            self._detail_content.controls.clear()
            try:
                self._skills_list_view.update()
                self._detail_content.update()
            except Exception:
                pass
            return

        if self._selected_entry is None or self._selected_entry not in self._entries:
            self._selected_entry = self._entries[0]

        for entry in self._entries:
            card = self._build_skill_card(entry)
            self._skills_list_view.controls.append(card)

        self._render_detail(self._selected_entry)

        try:
            self._skills_list_view.update()
        except Exception:
            pass

    def _build_skill_card(self, entry: SkillEntry) -> ft.Container:
        meta = entry.skill.META
        is_sel = (self._selected_entry and self._selected_entry.skill.META.name == meta.name)

        status_color = "#4CAF50" if entry.enabled else "#777777"
        status_text = "Activa" if entry.enabled else "Inactiva"

        def on_click(e):
            self._selected_entry = entry
            self._render_skills_list()

        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.BOLT, size=24, color=_ACCENT_BLUE),
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(meta.display_name, size=13, weight=ft.FontWeight.BOLD, color="#E0E0EE"),
                                    ft.Container(
                                        content=ft.Text(status_text, size=9, color=status_color),
                                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                                        bgcolor="#1A1A30",
                                        border_radius=4,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            ft.Text(meta.description[:45] + "…", size=11, color="#7A7A9A"),
                        ],
                        spacing=3,
                        expand=True,
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.all(12),
            border_radius=10,
            bgcolor=_CARD_SEL if is_sel else _CARD_BG,
            border=ft.Border.all(1, "#3A3A6A" if is_sel else "#1A1A30"),
            on_click=on_click,
            ink=True,
        )

    def _render_detail(self, entry: SkillEntry) -> None:
        self._detail_content.controls.clear()
        meta = entry.skill.META

        # Header con título y switch
        def on_toggle_enable(e):
            if e.control.value:
                skill_registry.enable_skill(meta.name)
            else:
                skill_registry.disable_skill(meta.name)
            self._render_skills_list()

        enable_switch = ft.Switch(
            label="Habilitada" if entry.enabled else "Deshabilitada",
            value=entry.enabled,
            active_color=_ACCENT_BLUE,
            on_change=on_toggle_enable,
        )

        header = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(meta.display_name, size=20, weight=ft.FontWeight.BOLD, color="#E8E8FF"),
                        ft.Text(f"ID: {meta.name} · v{meta.version} · Categoría: {meta.category}", size=11, color="#7A7A9A"),
                    ],
                    spacing=2,
                ),
                enable_switch,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        desc = ft.Container(
            content=ft.Text(meta.description, size=13, color="#B0B0CC"),
            padding=ft.Padding.symmetric(vertical=6),
        )

        # Comandos disponibles
        commands_chips = ft.Row(wrap=True, spacing=6)
        for cmd in meta.commands:
            commands_chips.controls.append(
                ft.Container(
                    content=ft.Text(f"/{cmd}", size=11, color="#A78BFA", weight=ft.FontWeight.BOLD),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    bgcolor="#1C1A32",
                    border=ft.Border.all(1, "#2C2A4E"),
                    border_radius=6,
                )
            )

        commands_box = ft.Column(
            [
                ft.Text("COMANDOS DISPONIBLES", size=10, weight=ft.FontWeight.BOLD, color="#666688"),
                commands_chips,
            ],
            spacing=8,
        )

        # Panel de Prueba
        test_input = ft.TextField(
            hint_text=f"Argumentos para comando (ej: {meta.commands[0] if meta.commands else 'eco'} test)...",
            hint_style=ft.TextStyle(size=12, color="#555577"),
            bgcolor="#14142B",
            border_color="#25254A",
            text_size=12,
            expand=True,
            height=40,
        )

        output_text = ft.Text("Resultado aparecerá aquí...", size=12, color="#777799", font_family="monospace")
        output_box = ft.Container(
            content=output_text,
            bgcolor="#080816",
            border=ft.Border.all(1, "#1A1A2E"),
            border_radius=8,
            padding=ft.Padding.all(12),
            expand=True,
            height=160,
        )

        cmd_dropdown = ft.Dropdown(
            options=[ft.dropdown.Option(cmd) for cmd in meta.commands],
            value=meta.commands[0] if meta.commands else "",
            width=160,
            text_size=12,
            height=40,
        )

        def on_run_test(e):
            cmd = cmd_dropdown.value
            if not cmd:
                output_text.value = "Seleccioná un comando."
                output_text.color = "#FF7777"
                output_box.update()
                return

            args_str = (test_input.value or "").strip()
            args = args_str.split() if args_str else []

            output_text.value = f"Ejecutando '{cmd}'..."
            output_text.color = "#8888AA"
            output_box.update()

            def _exec():
                res = skill_registry.execute(meta.name, cmd, args)
                if res.success:
                    output_text.value = f"[OK]\n{res.output}"
                    output_text.color = "#77DD77"
                else:
                    output_text.value = f"[ERROR]\n{res.error}"
                    output_text.color = "#FF7777"
                try:
                    output_box.update()
                except Exception:
                    pass

            threading.Thread(target=_exec, daemon=True).start()

        run_btn = ft.FilledButton(
            "▶ Ejecutar",
            on_click=on_run_test,
            style=ft.ButtonStyle(bgcolor=_ACCENT_BLUE, color="#FFFFFF"),
            height=40,
        )

        tester_row = ft.Row([cmd_dropdown, test_input, run_btn], spacing=8)
        tester_section = ft.Column(
            [
                ft.Text("PANEL DE PRUEBA", size=10, weight=ft.FontWeight.BOLD, color="#666688"),
                tester_row,
                output_box,
            ],
            spacing=10,
        )

        self._detail_content.controls = [
            header,
            ft.Divider(height=1, color="#1E1E3A"),
            desc,
            commands_box,
            ft.Divider(height=1, color="#1E1E3A"),
            tester_section,
        ]

        try:
            self._detail_content.update()
        except Exception:
            pass

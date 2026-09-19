"""
AURA — Página de Automatizaciones (Flet)

Permite listar, inspeccionar, ejecutar y simular automatizaciones
en formato YAML/JSON creadas por el usuario o predefinidas.
"""

from __future__ import annotations

import threading
from typing import Optional
import flet as ft

from automation import automation_engine, AutomationInfo, AutomationResult
from ui.pages.base_page import BasePage
from utils.logger import get_logger

_logger = get_logger("aura.ui.page.automation")

_BG_DARK     = "#0C0C18"
_CARD_BG     = "#13132A"
_CARD_SEL    = "#1C1C3E"
_PANEL_BG    = "#101024"
_ACCENT_BLUE = "#4A9EFF"


class AutomationPage(BasePage):
    """
    Página de gestión y ejecución de Automatizaciones en Flet.
    """

    PAGE_NAME = "Automatizaciones"

    def __init__(self, page: ft.Page, **kwargs):
        self._automations: list[AutomationInfo] = []
        self._selected_info: Optional[AutomationInfo] = None
        self._is_running = False
        super().__init__(page, **kwargs)

    def _build(self) -> None:
        self.bgcolor = _BG_DARK

        # ── Panel izquierdo: Lista de automatizaciones ───────────
        self._auto_list_view = ft.ListView(
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
                                ft.Text("Automatizaciones", size=13, weight=ft.FontWeight.BOLD, color="#C0C0E0"),
                                ft.IconButton(
                                    ft.Icons.REFRESH,
                                    icon_size=18,
                                    icon_color="#7A7A9A",
                                    tooltip="Recargar",
                                    on_click=lambda e: self.refresh_list(),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                        border=ft.Border.only(bottom=ft.BorderSide(1, "#1A1A2E")),
                    ),
                    self._auto_list_view,
                ],
                expand=True,
                spacing=0,
            ),
            width=320,
            bgcolor="#0E0E1E",
            border=ft.Border.only(right=ft.BorderSide(1, "#1A1A2E")),
        )

        # ── Panel derecho: Detalle, Pasos y Log ───────────────────
        self._detail_content = ft.Column(expand=True, spacing=16, scroll=ft.ScrollMode.AUTO)
        right_panel = ft.Container(
            content=self._detail_content,
            expand=True,
            padding=ft.Padding.all(24),
            bgcolor=_PANEL_BG,
        )

        self.content = ft.Row([left_panel, right_panel], expand=True, spacing=0)

    def on_enter(self) -> None:
        self.refresh_list()

    def refresh_list(self) -> None:
        def _load():
            try:
                self._automations = automation_engine.list_automations()
            except Exception as e:
                _logger.error(f"Error listando automatizaciones: {e}")
                self._automations = []

            self._render_list()

        threading.Thread(target=_load, daemon=True).start()

    def _render_list(self) -> None:
        self._auto_list_view.controls.clear()

        if not self._automations:
            self._auto_list_view.controls.append(
                ft.Container(
                    content=ft.Text("No hay automatizaciones guardadas", color="#555577", size=12),
                    alignment=ft.Alignment.CENTER,
                    padding=ft.Padding.all(20),
                )
            )
            self._detail_content.controls.clear()
            try:
                self._auto_list_view.update()
                self._detail_content.update()
            except Exception:
                pass
            return

        if self._selected_info is None or self._selected_info not in self._automations:
            self._selected_info = self._automations[0]

        for info in self._automations:
            card = self._build_card(info)
            self._auto_list_view.controls.append(card)

        self._render_detail(self._selected_info)

        try:
            self._auto_list_view.update()
        except Exception:
            pass

    def _build_card(self, info: AutomationInfo) -> ft.Container:
        is_sel = (self._selected_info and self._selected_info.name == info.name)

        def on_click(e):
            self._selected_info = info
            self._render_list()

        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE, size=24, color="#4CAF50"),
                    ft.Column(
                        [
                            ft.Text(info.display_name, size=13, weight=ft.FontWeight.BOLD, color="#E0E0EE"),
                            ft.Text(f"{info.step_count} pasos · {info.format.upper()}", size=11, color="#7A7A9A"),
                        ],
                        spacing=2,
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

    def _render_detail(self, info: AutomationInfo) -> None:
        self._detail_content.controls.clear()

        # Botones de ejecución
        self._run_btn = ft.FilledButton(
            "▶ Ejecutar",
            on_click=lambda e: self._execute_automation(info, dry_run=False),
            style=ft.ButtonStyle(bgcolor="#2A6A3A", color="#FFFFFF"),
            height=38,
        )

        self._sim_btn = ft.OutlinedButton(
            "🔍 Simular (Dry-Run)",
            on_click=lambda e: self._execute_automation(info, dry_run=True),
            style=ft.ButtonStyle(color="#4A9EFF"),
            height=38,
        )

        header = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(info.display_name, size=20, weight=ft.FontWeight.BOLD, color="#E8E8FF"),
                        ft.Text(f"Archivo: {info.filename} · Versión: {info.version}", size=11, color="#7A7A9A"),
                    ],
                    spacing=2,
                ),
                ft.Row([self._sim_btn, self._run_btn], spacing=8),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        desc = ft.Text(info.description or "Sin descripción.", size=13, color="#B0B0CC")

        # Pasos
        steps_col = ft.Column(spacing=6)
        try:
            full_data = automation_engine._load_file(info.path)
            steps = full_data.get("steps", [])
            for i, step in enumerate(steps, 1):
                action = step.get("type", "unknown")
                sdesc = step.get("description", str(step))
                steps_col.controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(
                                    content=ft.Text(str(i), size=10, color="#FFFFFF", weight=ft.FontWeight.BOLD),
                                    bgcolor="#25254A",
                                    border_radius=12,
                                    width=22,
                                    height=22,
                                    alignment=ft.Alignment.CENTER,
                                ),
                                ft.Text(f"[{action}]", size=11, weight=ft.FontWeight.BOLD, color="#A78BFA"),
                                ft.Text(sdesc, size=12, color="#CCCCCC", expand=True),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                        bgcolor="#14142B",
                        border_radius=6,
                    )
                )
        except Exception as e:
            steps_col.controls.append(ft.Text(f"Error leyendo pasos: {e}", color="#FF6B8A", size=12))

        # Consola de Log
        self._log_text = ft.Text("Presioná 'Ejecutar' o 'Simular' para ver la salida...", size=11, color="#777799", font_family="monospace")
        log_box = ft.Container(
            content=ft.ListView([self._log_text], auto_scroll=True),
            bgcolor="#080816",
            border=ft.Border.all(1, "#1A1A2E"),
            border_radius=8,
            padding=ft.Padding.all(12),
            height=180,
        )

        self._detail_content.controls = [
            header,
            ft.Divider(height=1, color="#1E1E3A"),
            desc,
            ft.Text("PASOS DE LA AUTOMATIZACIÓN", size=10, weight=ft.FontWeight.BOLD, color="#666688"),
            steps_col,
            ft.Divider(height=1, color="#1E1E3A"),
            ft.Text("LOG DE EJECUCIÓN", size=10, weight=ft.FontWeight.BOLD, color="#666688"),
            log_box,
        ]

        try:
            self._detail_content.update()
        except Exception:
            pass

    def _execute_automation(self, info: AutomationInfo, dry_run: bool) -> None:
        if self._is_running:
            return

        from core.app_resolver import get_preferred_browser_name, BROWSER_DISPLAY_NAMES
        pref_browser = get_preferred_browser_name()
        pref_disp = BROWSER_DISPLAY_NAMES.get(pref_browser.lower(), pref_browser.title())

        self._is_running = True
        self._run_btn.disabled = True
        self._sim_btn.disabled = True
        tag = "[SIMULACIÓN / DRY-RUN]" if dry_run else "[EJECUCIÓN REAL]"
        self._log_text.value = (
            f"{tag} Iniciando automatización '{info.display_name}'...\n"
            f"Navegador preferido activo: {pref_disp} ({pref_browser})\n"
        )
        self._log_text.color = "#8888AA"
        try:
            self._detail_content.update()
        except Exception:
            pass

        def _worker():
            try:
                res: AutomationResult = automation_engine.run(info.name, dry_run=dry_run)
                status = getattr(
                    res,
                    "status",
                    ("OK" if res.success else ("FALLIDA" if res.completed_steps == 0 else "PARCIAL")),
                )

                if status == "OK":
                    header_line = f"{tag} Estado: OK — Todos los pasos exitosos ({res.completed_steps}/{res.total_steps})."
                    status_color = "#4CAF50"  # Verde
                elif status == "PARCIAL":
                    header_line = f"{tag} Estado: PARCIAL — Falló: {res.failed_steps}/{res.total_steps} pasos ({res.completed_steps}/{res.total_steps} exitosos)."
                    status_color = "#FFA726"  # Naranja / Amarillo
                else:  # FALLIDA
                    header_line = f"{tag} Estado: FALLIDA — Falló: {res.failed_steps}/{res.total_steps} pasos (0/{res.total_steps} exitosos)."
                    status_color = "#EF5350"  # Rojo

                lines = [header_line]
                for step in res.step_results:
                    st = "✓" if step.success else "✗"
                    step_num = step.index + 1
                    detail = step.output if step.success else step.error
                    lines.append(f"  {st} Paso {step_num} [{step.step_type}]: {detail}")

                self._log_text.value = "\n".join(lines)
                self._log_text.color = status_color
            except Exception as e:
                self._log_text.value = f"Error ejecutando: {e}"
                self._log_text.color = "#EF5350"
            finally:
                self._is_running = False
                self._run_btn.disabled = False
                self._sim_btn.disabled = False
                try:
                    self._detail_content.update()
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True).start()


# ───────────────────────────────────────────────────────────────────────────
# Constantes y funciones de compatibilidad
# ───────────────────────────────────────────────────────────────────────────
_BG_CARD = _CARD_BG


def _get_engine():
    """Retorna la instancia singleton de AutomationEngine."""
    return automation_engine


class _AutomationCard:
    """Clase helper para compatibilidad con tests."""
    pass


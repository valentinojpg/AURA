"""
AURA — Asistente de Configuración Inicial / Onboarding (Fase 30)

Diálogo modal interactivo multi-paso para la primera ejecución de AURA:
  - Paso 1: Bienvenida, Idioma y Tema visual
  - Paso 2: Selección de Proveedor de IA (Ollama local, Cloud o Mock)
  - Paso 3: Conexión, Guía de Ayuda de Ollama y Selección de Modelo
  - Paso 4: Carpeta de Trabajo (Workspace) y Políticas de Seguridad
  - Paso 5: Resumen y Guardado Definitivo (FIRST_RUN=false)
"""

from __future__ import annotations

import json
import threading
import urllib.error
from pathlib import Path
from typing import Callable, Optional
import flet as ft

from ui.branding import create_brand_avatar
from config.settings import settings
from ai.provider_factory import PROVIDER_METADATA, reset_default_provider
from core.ollama_helper import (
    RECOMMENDED_MODELS,
    check_ollama_service,
    is_ollama_installed,
    get_installation_instructions,
)
from utils.logger import get_logger

_logger = get_logger("aura.ui.wizard")


class SetupWizard:
    """
    Wizard modal de bienvenida y configuración inicial de AURA (Fase 30).
    """

    def __init__(self, page: ft.Page, on_complete: Optional[Callable[[], None]] = None):
        self.page = page
        self._on_complete = on_complete
        self._step = 1
        self._total_steps = 5

        # Estado temporal del wizard
        self._language = settings.get("APP_LANGUAGE", "es") or "es"
        self._theme = settings.get("APP_THEME", "dark") or "dark"
        self._provider = settings.get("AI_PROVIDER", "ollama") or "ollama"
        self._ai_model = settings.get("AI_MODEL", "qwen2.5:3b") or "qwen2.5:3b"
        self._ollama_url = settings.get("OLLAMA_URL", "http://localhost:11434") or "http://localhost:11434"
        self._api_key = ""
        self._workspace_path = settings.get("WORKSPACE_PATH", str(Path.home() / "Documents")) or str(Path.home() / "Documents")
        self._confirm_destructive = settings.get_bool("CONFIRM_DESTRUCTIVE", True)

        self._test_status_text = ""
        self._test_status_color = "#777799"
        self._dialog: Optional[ft.AlertDialog] = None

    def show(self) -> None:
        """Inicia y despliega el diálogo modal del wizard."""
        self._step = 1
        self._build_and_open()

    def _build_and_open(self) -> None:
        self._dialog_content = ft.Container(
            content=self._get_step_content(),
            width=560,
            height=390,
            padding=ft.Padding.all(16),
        )

        self._btn_prev = ft.TextButton(
            "Atrás",
            on_click=lambda e: self._prev_step(),
            visible=(self._step > 1),
        )

        self._btn_next = ft.FilledButton(
            "Siguiente" if self._step < self._total_steps else "🚀 Iniciar AURA",
            on_click=lambda e: self._next_step(),
            style=ft.ButtonStyle(bgcolor="#3B4FC8", color="#FFFFFF"),
        )

        self._dialog = ft.AlertDialog(
            title=ft.Row(
                [
                    ft.Text(f"Asistente de Bienvenida — Paso {self._step} de {self._total_steps}", size=14, weight=ft.FontWeight.BOLD),
                    ft.IconButton(ft.Icons.CLOSE, icon_size=18, on_click=lambda e: self._close()),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            content=self._dialog_content,
            actions=[self._btn_prev, self._btn_next],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.show_dialog(self._dialog)

    def _close(self) -> None:
        try:
            self.page.pop_dialog()
        except Exception:
            pass

    def _prev_step(self) -> None:
        if self._step > 1:
            self._step -= 1
            self._update_view()

    def _next_step(self) -> None:
        if self._step < self._total_steps:
            self._step += 1
            self._update_view()
        else:
            self._finish()

    def _finish(self) -> None:
        # Guardar en configuración (.env)
        settings.set("APP_LANGUAGE", self._language)
        settings.set("APP_THEME", self._theme)
        settings.set("AI_PROVIDER", self._provider)
        settings.set("AI_MODEL", self._ai_model)
        settings.set("WORKSPACE_PATH", self._workspace_path)
        settings.set("CONFIRM_DESTRUCTIVE", "true" if self._confirm_destructive else "false")

        if self._provider == "ollama":
            settings.set("OLLAMA_URL", self._ollama_url)
        elif self._provider == "openai" and self._api_key:
            settings.set("OPENAI_API_KEY", self._api_key)
        elif self._provider == "anthropic" and self._api_key:
            settings.set("ANTHROPIC_API_KEY", self._api_key)
        elif self._provider == "gemini" and self._api_key:
            settings.set("GEMINI_API_KEY", self._api_key)
        elif self._provider == "xai" and self._api_key:
            settings.set("XAI_API_KEY", self._api_key)

        # Crear carpeta de trabajo si no existe
        try:
            Path(self._workspace_path).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        settings.mark_first_run_done()
        reset_default_provider()

        _logger.info(
            f"Onboarding completado exitosamente: prov={self._provider}, model={self._ai_model}, "
            f"lang={self._language}, ws={self._workspace_path}"
        )

        self._close()

        if self._on_complete:
            self._on_complete()

    def _update_view(self) -> None:
        if not self._dialog:
            return

        self._dialog.title.controls[0].value = f"Asistente de Bienvenida — Paso {self._step} de {self._total_steps}"
        self._dialog_content.content = self._get_step_content()
        self._btn_prev.visible = (self._step > 1)
        self._btn_next.text = "Siguiente" if self._step < self._total_steps else "🚀 Iniciar AURA"

        try:
            self._dialog.update()
            self._dialog_content.update()
        except Exception:
            pass

    def _get_step_content(self) -> ft.Control:
        if self._step == 1:
            # Paso 1: Bienvenida e Idioma
            return ft.Column(
                [
                    ft.Row(
                        [
                            create_brand_avatar(size=44, border_color="#4A9EFF", border_width=2),
                            ft.Column(
                                [
                                    ft.Text("¡Bienvenido a AURA Orion!", size=18, weight=ft.FontWeight.BOLD, color="#E8E8FF"),
                                    ft.Text("Tu asistente universal con respuesta automatizada para PC.", size=12, color="#9090B8"),
                                ],
                                spacing=2,
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(height=1, color="#25254A"),
                    ft.Text(
                        "Configurá tus preferencias básicas para comenzar. "
                        "Podrás modificar todos estos ajustes en cualquier momento desde la pestaña Configuración.",
                        size=12,
                        color="#C0C0DE",
                    ),
                    ft.Row(
                        [
                            ft.Dropdown(
                                label="Idioma",
                                value=self._language,
                                options=[
                                    ft.dropdown.Option(key="es", text="Español (es)"),
                                    ft.dropdown.Option(key="en", text="English (en)"),
                                ],
                                width=230,
                                on_select=lambda e: setattr(self, "_language", e.data or getattr(e.control, "value", "es")),
                            ),
                            ft.Dropdown(
                                label="Tema visual",
                                value=self._theme,
                                options=[
                                    ft.dropdown.Option(key="dark", text="Modo Oscuro (Dark)"),
                                    ft.dropdown.Option(key="light", text="Modo Claro (Light)"),
                                ],
                                width=230,
                                on_select=lambda e: setattr(self, "_theme", e.data or getattr(e.control, "value", "dark")),
                            ),
                        ],
                        spacing=16,
                    ),
                ],
                spacing=14,
            )

        elif self._step == 2:
            # Paso 2: Selección de Proveedor de IA
            ollama_ok, ollama_msg, _ = check_ollama_service(self._ollama_url, timeout=1.0)
            status_chip = ft.Container(
                content=ft.Text(
                    f"Ollama local: {'🟢 Activo' if ollama_ok else '⚪ No detectado'}",
                    size=11,
                    color="#88DD88" if ollama_ok else "#FFAA66",
                ),
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                bgcolor="#1A1A36",
                border_radius=8,
            )

            def _on_prov_change(e):
                self._provider = e.data or getattr(e.control, "value", "ollama")

            prov_dropdown = ft.Dropdown(
                label="Motor de Inteligencia Artificial",
                value=self._provider,
                options=[
                    ft.dropdown.Option(key="ollama", text="Ollama (Local, privado y sin internet)"),
                    ft.dropdown.Option(key="gemini", text="Google Gemini (Cloud rápido y económico)"),
                    ft.dropdown.Option(key="openai", text="OpenAI ChatGPT (Cloud GPT-4o-mini)"),
                    ft.dropdown.Option(key="anthropic", text="Anthropic Claude (Cloud Claude-3.5)"),
                    ft.dropdown.Option(key="xai", text="xAI Grok (Cloud Grok-2)"),
                    ft.dropdown.Option(key="custom", text="Compatible OpenAI (Custom / Groq / LM Studio)"),
                    ft.dropdown.Option(key="mock", text="Modo Demostración / Offline (Sin LLM)"),
                ],
                expand=True,
                on_select=_on_prov_change,
            )

            return ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Selección de Proveedor de IA", size=16, weight=ft.FontWeight.BOLD, color="#E8E8FF"),
                            status_chip,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(
                        "Elegí cómo responderá AURA. Recomendamos Ollama para total privacidad, "
                        "o Gemini/OpenAI para máxima capacidad.",
                        size=12,
                        color="#9090B0",
                    ),
                    prov_dropdown,
                    ft.Container(
                        content=ft.Text(
                            "💡 Tip: Si no tenés Ollama instalado ni claves API, podés usar el 'Modo Demostración' "
                            "para probar comandos de sistema, explorador de archivos y automatizaciones sin costo.",
                            size=11,
                            color="#77A0FF",
                        ),
                        bgcolor="#101830",
                        padding=ft.Padding.all(10),
                        border_radius=8,
                    ),
                ],
                spacing=12,
            )

        elif self._step == 3:
            # Paso 3: Configuración del proveedor seleccionado & Ayuda Ollama
            if self._provider == "ollama":
                url_field = ft.TextField(
                    label="URL de Ollama",
                    value=self._ollama_url,
                    text_size=12,
                    expand=True,
                    on_change=lambda e: setattr(self, "_ollama_url", e.control.value),
                )

                model_field = ft.TextField(
                    label="Modelo a usar (ej: qwen2.5:3b)",
                    value=self._ai_model,
                    text_size=12,
                    expand=True,
                    on_change=lambda e: setattr(self, "_ai_model", e.control.value),
                )

                status_label = ft.Text(self._test_status_text, size=11, color=self._test_status_color)

                def _test_ollama(e):
                    status_label.value = "⏳ Verificando servicio de Ollama..."
                    status_label.color = "#8888AA"
                    try:
                        status_label.update()
                    except Exception:
                        pass

                    def _w():
                        ok, msg, models = check_ollama_service(self._ollama_url)
                        if ok:
                            self._test_status_text = f"✅ {msg}"
                            self._test_status_color = "#77DD77"
                            if models and self._ai_model not in models:
                                self._ai_model = models[0]
                                model_field.value = models[0]
                                try:
                                    model_field.update()
                                except Exception:
                                    pass
                        else:
                            self._test_status_text = f"❌ {msg}"
                            self._test_status_color = "#FFAA66"

                        status_label.value = self._test_status_text
                        status_label.color = self._test_status_color
                        try:
                            status_label.update()
                        except Exception:
                            pass

                    threading.Thread(target=_w, daemon=True).start()

                test_btn = ft.FilledButton("Probar", on_click=_test_ollama, style=ft.ButtonStyle(bgcolor="#3A3A6A"))

                inst_info = get_installation_instructions()

                return ft.Column(
                    [
                        ft.Text("Configuración y Ayuda de Ollama", size=16, weight=ft.FontWeight.BOLD, color="#E8E8FF"),
                        ft.Row([url_field, test_btn], spacing=8),
                        status_label,
                        model_field,
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text("🛠️ ¿No tenés Ollama instalado?", size=11, weight=ft.FontWeight.BOLD, color="#C0C0E0"),
                                    ft.Text(f"Instalá con: {inst_info['winget_command']}  o desde {inst_info['download_url']}", size=10, color="#8899BB"),
                                    ft.Text(f"Descargá el modelo con: {inst_info['pull_command']}", size=10, color="#88DD88"),
                                ],
                                spacing=3,
                            ),
                            bgcolor="#0C0C22",
                            border=ft.Border.all(1, "#1E1E38"),
                            padding=ft.Padding.all(8),
                            border_radius=6,
                        ),
                    ],
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO,
                )
            elif self._provider in ("openai", "anthropic", "gemini", "xai", "custom"):
                meta = PROVIDER_METADATA.get(self._provider, {})
                default_mod = meta.get("default_model", self._ai_model)
                self._ai_model = default_mod

                api_field = ft.TextField(
                    label=f"API Key para {meta.get('display_name', self._provider)}",
                    value=self._api_key,
                    password=True,
                    can_reveal_password=True,
                    text_size=12,
                    hint_text="sk-...",
                    expand=True,
                    on_change=lambda e: setattr(self, "_api_key", e.control.value),
                )

                model_field = ft.TextField(
                    label="Modelo a consultar",
                    value=self._ai_model,
                    text_size=12,
                    expand=True,
                    on_change=lambda e: setattr(self, "_ai_model", e.control.value),
                )

                return ft.Column(
                    [
                        ft.Text(f"Configuración de {meta.get('display_name', self._provider)}", size=16, weight=ft.FontWeight.BOLD, color="#E8E8FF"),
                        ft.Text("Ingresá tu clave de API para procesar comandos en la nube:", size=12, color="#9090B0"),
                        api_field,
                        model_field,
                        ft.Text("Tu clave se guardará localmente en el archivo .env de forma privada.", size=11, color="#777799"),
                    ],
                    spacing=12,
                )
            else:
                return ft.Column(
                    [
                        ft.Text("Modo Demostración Activo", size=16, weight=ft.FontWeight.BOLD, color="#E8E8FF"),
                        ft.Text(
                            "En este modo no se requiere ninguna conexión ni clave externa. "
                            "AURA responderá con respuestas didácticas locales para que puedas explorar la interfaz.",
                            size=12,
                            color="#9090B0",
                        ),
                    ],
                    spacing=12,
                )

        elif self._step == 4:
            # Paso 4: Carpeta de Trabajo (Workspace) y Seguridad
            ws_field = ft.TextField(
                label="Carpeta de Trabajo (Workspace)",
                value=self._workspace_path,
                text_size=12,
                expand=True,
                on_change=lambda e: setattr(self, "_workspace_path", e.control.value),
            )

            sec_switch = ft.Switch(
                label="Confirmar acciones destructivas (vaciar papelera, apagar, borrar permanente)",
                value=self._confirm_destructive,
                active_color="#4A9EFF",
                on_change=lambda e: setattr(self, "_confirm_destructive", e.control.value),
            )

            return ft.Column(
                [
                    ft.Text("Entorno de Trabajo y Seguridad", size=16, weight=ft.FontWeight.BOLD, color="#E8E8FF"),
                    ft.Text("Seleccioná la carpeta donde AURA guardará y buscará tus proyectos y documentos:", size=12, color="#9090B0"),
                    ws_field,
                    ft.Divider(height=1, color="#25254A"),
                    sec_switch,
                ],
                spacing=14,
            )

        else:
            # Paso 5: Resumen y Confirmación Final
            return ft.Column(
                [
                    ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=40, color="#4CAF50"),
                    ft.Text("¡Todo listo para comenzar!", size=18, weight=ft.FontWeight.BOLD, color="#E8E8FF"),
                    ft.Text("Resumen de tu configuración inicial:", size=12, color="#9090B0"),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(f"• Idioma: {self._language.upper()}  |  Tema: {self._theme.title()}", size=12, color="#E0E0EE"),
                                ft.Text(f"• Proveedor de IA: {self._provider.upper()}", size=12, color="#E0E0EE"),
                                ft.Text(f"• Modelo: {self._ai_model}", size=12, color="#E0E0EE"),
                                ft.Text(f"• Carpeta Workspace: {self._workspace_path}", size=12, color="#E0E0EE"),
                                ft.Text(f"• Confirmación de seguridad: {'Activada' if self._confirm_destructive else 'Desactivada'}", size=12, color="#E0E0EE"),
                            ],
                            spacing=6,
                        ),
                        bgcolor="#14142B",
                        padding=ft.Padding.all(14),
                        border_radius=8,
                    ),
                    ft.Text("Hacé clic en '🚀 Iniciar AURA' para guardar y entrar al escritorio principal.", size=11, color="#8899BB"),
                ],
                spacing=10,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )

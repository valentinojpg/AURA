"""
AURA — Página de Configuración Completa (Fase 29)

Centro integral de ajustes de AURA:
  - Navegación rápida por categorías (General, IA, Voz, Seguridad, Memoria, Diagnóstico)
  - Apariencia (Modo Oscuro/Claro), Idioma (es/en) y Carpeta de Trabajo (Workspace)
  - Navegador Web Preferido con detección automática
  - Configuración de IA Multi-proveedor (Ollama, OpenAI, Anthropic, Gemini, xAI, Custom)
  - Dispositivos de Audio y Voz (Micrófono, salida, calibración RMS, VAD, auto-envío)
  - Seguridad y Políticas de Confirmación (Acciones destructivas, apagado, cierre de apps, router)
  - Memoria de Usuario (Fase 28) con métricas, exportación de respaldos JSON y limpieza
  - Personalidad y Modo Grok (Fase 51) y Comprensión Difusa Fuzzy/LLM (Fase 54)
  - Índice de Aplicaciones (Fase 52) con indexado asíncrono y cancelación
  - Diagnóstico Completo del Sistema y Autochequeo Automatizado (Self-Test)
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
import flet as ft

from config.settings import settings, format_key_loaded, DEFAULTS
from ai.provider_factory import (
    get_provider,
    reset_default_provider,
    PROVIDER_METADATA,
)
from core.app_resolver import (
    get_preferred_browser_name,
    SUPPORTED_BROWSERS,
    BROWSER_DISPLAY_NAMES,
    resolve_app,
)
from core.diagnostics import (
    run_diagnostics,
    run_self_test,
    self_test_to_text,
)
from core.app_scanner import app_index_manager
from core.user_memory import user_memory
from ui.pages.base_page import BasePage
from ui.components.audio_panel import AudioPanel
from ui.components.color_picker import ColorPicker, ThemeLivePreview
from aura.ui.theme import (
    STYLE_COLOR_COUNT,
    STYLE_FAMILIES,
    THEME_PRESETS,
    ThemeTokens,
    apply_theme,
    build_theme_tokens,
)
from aura.ui.background_manager import (
    background_manager,
    load_current_metadata,
    normalize_background_image,
)
from aura.ui.file_picker_compat import open_file_picker_dialog
from aura.ui.color_utils import (
    derive_analogous_palette,
    derive_mono_palette,
    derive_poly_palette,
)
from voice.tts import (
    tts_manager,
    rvc_converter,
    get_available_rvc_voices,
)
from aura.personality import (
    PersonalityMode,
    list_personalities,
    get_current_personality,
    set_personality,
    rude_engine,
)
from utils.logger import get_logger


_logger = get_logger("aura.ui.page.settings")

_BG_DARK   = "#0C0C18"
_CARD_BG   = "#131328"
_BORDER_BG = "#1A1A36"


class SettingsPage(BasePage):
    """
    Página de configuración completa y diagnóstico de AURA en Flet (Fase 29).
    """

    PAGE_NAME = "Configuración"

    def __init__(self, page: ft.Page, on_open_wizard: Optional[Callable[[], None]] = None, **kwargs):
        self._on_open_wizard = on_open_wizard
        self._is_indexing: bool = False
        self._active_category: str = "all"
        super().__init__(page, **kwargs)

    def _build_disabled_section_card(self, title: str, reason: str) -> ft.Container:
        """Crea una tarjeta informativa accesible cuando una sección opcional falla en inicializar."""
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color="#FFAA00", size=20),
                            ft.Text(f"⚠️ Sección deshabilitada: {reason}", size=13, color="#FFAA00", weight=ft.FontWeight.W_500),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        f"El apartado '{title}' no está disponible temporalmente. El resto de las opciones de configuración continúan funcionando con normalidad.",
                        size=11,
                        color="#8888AA",
                    ),
                ],
                spacing=6,
            ),
            padding=ft.Padding.all(16),
            bgcolor=_CARD_BG,
            border=ft.Border.all(1, "#443311"),
            border_radius=10,
        )

    def _build_audio_section(self) -> ft.Container:
        """Construye la sección de Dispositivos de Audio y Voz."""
        try:
            self._audio_panel = AudioPanel(page=self.app_page, visible=True)
            self._audio_card = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text("Dispositivos de Audio y Voz", size=14, weight=ft.FontWeight.BOLD, color="#E0E0EE"),
                                        ft.Text("Calibración de micrófono, prueba de salida de sonido y parámetros de reconocimiento STT.", size=11, color="#777799"),
                                    ],
                                    spacing=2,
                                ),
                            ],
                        ),
                        self._audio_panel,
                    ],
                    spacing=10,
                ),
                padding=ft.Padding.all(16),
                bgcolor=_CARD_BG,
                border=ft.Border.all(1, _BORDER_BG),
                border_radius=10,
            )


            return self._audio_card
        except Exception as ex:
            _logger.warning("Error inicializando sección 'Dispositivos de Audio y Voz': %s", ex)
            return self._build_disabled_section_card("Dispositivos de Audio y Voz", str(ex))

    def _build_rvc_section(self) -> ft.Container:
        """Construye la sección de Voz RVC y Síntesis TTS."""
        try:
            dev_info_str = rvc_converter.device_info
            self._rvc_device_badge = ft.Container(
                content=ft.Text(f"⚙️ Hardware: {dev_info_str}", size=11, color="#77DD77" if "GPU" in dev_info_str else "#B0B0D0"),
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                bgcolor="#1A2A2A" if "GPU" in dev_info_str else "#222244",
                border_radius=12,
            )

            curr_tts_prov = settings.get("TTS_PROVIDER", "rvc") or "rvc"
            self._tts_provider_dropdown = ft.Dropdown(
                label="Proveedor de Voz (TTS)",
                value=curr_tts_prov,
                options=[
                    ft.dropdown.Option(key="rvc", text="Voz RVC Neuronal (Recomendado)"),
                    ft.dropdown.Option(key="edge", text="Edge-TTS Directo (Sin RVC)"),
                    ft.dropdown.Option(key="sapi", text="Windows SAPI (Offline)"),
                    ft.dropdown.Option(key="none", text="Desactivado (Mudo)"),
                ],
                width=280,
                border_color="#2A2A4E",
            )

            self._tts_autoplay_switch = ft.Switch(
                label="Reproducir respuestas del asistente automáticamente",
                value=settings.get_bool("TTS_AUTO_PLAY", True),
                active_color="#4A9EFF",
            )

            avail_rvc_voices = get_available_rvc_voices()
            rvc_options = [ft.dropdown.Option(key=v, text=f"Voz: {v}") for v in sorted(avail_rvc_voices.keys())]
            if not rvc_options:
                rvc_options = [ft.dropdown.Option(key="aura", text="Voz: aura (por defecto)")]
            curr_rvc_voice = settings.get("RVC_VOZ", "aura") or "aura"

            self._rvc_voice_dropdown = ft.Dropdown(
                label="Modelo de Voz RVC",
                value=curr_rvc_voice if curr_rvc_voice in [o.key for o in rvc_options] else rvc_options[0].key,
                options=rvc_options,
                width=240,
                border_color="#2A2A4E",
            )

            curr_tts_base = settings.get("RVC_TTS_BASE", "edge") or "edge"
            self._rvc_base_dropdown = ft.Dropdown(
                label="TTS Base (Voz Fuente)",
                value=curr_tts_base,
                options=[
                    ft.dropdown.Option(key="edge", text="Edge-TTS (Online)"),
                    ft.dropdown.Option(key="sapi", text="Windows SAPI (Offline)"),
                ],
                width=240,
                border_color="#2A2A4E",
            )

            curr_base_voice = settings.get("RVC_TTS_BASE_VOICE", "es-MX-DaliaNeural") or "es-MX-DaliaNeural"
            edge_voice_options = [
                ft.dropdown.Option(key="es-MX-DaliaNeural", text="Dalia (MX Femenina)"),
                ft.dropdown.Option(key="es-ES-ElviraNeural", text="Elvira (ES Femenina)"),
                ft.dropdown.Option(key="es-AR-ElenaNeural", text="Elena (AR Femenina)"),
                ft.dropdown.Option(key="es-US-PalomaNeural", text="Paloma (US Femenina)"),
                ft.dropdown.Option(key="es-MX-JorgeNeural", text="Jorge (MX Masculina)"),
                ft.dropdown.Option(key="es-ES-AlvaroNeural", text="Álvaro (ES Masculina)"),
                ft.dropdown.Option(key="es-AR-TomasNeural", text="Tomás (AR Masculina)"),
            ]
            if curr_base_voice not in [o.key for o in edge_voice_options]:
                edge_voice_options.append(ft.dropdown.Option(key=curr_base_voice, text=curr_base_voice))

            self._rvc_base_voice_dropdown = ft.Dropdown(
                label="Voz Fuente Base",
                value=curr_base_voice,
                options=edge_voice_options,
                width=260,
                border_color="#2A2A4E",
            )

            curr_pitch = settings.get_int("RVC_PITCH", 0)
            self._rvc_pitch_label = ft.Text(f"Tono (Pitch): {curr_pitch:+d} semitonos", size=12, color="#C0C0DE", width=220)
            self._rvc_pitch_slider = ft.Slider(
                min=-12,
                max=12,
                divisions=24,
                value=float(curr_pitch),
                label="{value}",
                expand=True,
                active_color="#A78BFA",
                on_change=lambda e: self._on_rvc_pitch_change(e),
            )

            curr_index_rate = settings.get_float("RVC_INDEX_RATE", 0.6)
            self._rvc_index_label = ft.Text(f"Fidelidad de Índice (Index Rate): {curr_index_rate:.2f}", size=12, color="#C0C0DE", width=220)
            self._rvc_index_slider = ft.Slider(
                min=0.0,
                max=1.0,
                divisions=20,
                value=curr_index_rate,
                label="{value}",
                expand=True,
                active_color="#4A9EFF",
                on_change=lambda e: self._on_rvc_index_change(e),
            )

            self._rvc_status_text = ft.Text("", size=11, color="#77DD77")

            self._test_voice_btn = ft.FilledButton(
                "🔊 Probar Voz",
                on_click=self._handle_test_voice,
                style=ft.ButtonStyle(bgcolor="#3B4FC8", color="#FFFFFF"),
            )

            self._save_rvc_btn = ft.FilledButton(
                "💾 Guardar Ajustes de Voz",
                on_click=self._handle_save_rvc,
                style=ft.ButtonStyle(bgcolor="#2A4A3A", color="#FFFFFF"),
            )

            self._rvc_card = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text("Voz RVC y Síntesis TTS", size=14, weight=ft.FontWeight.BOLD, color="#E0E0EE"),
                                        ft.Text(
                                            "Conversión neuronal de voz con modelos locales .pth/.index y TTS base.",
                                            size=11,
                                            color="#777799",
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                self._rvc_device_badge,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            [
                                self._tts_provider_dropdown,
                                self._tts_autoplay_switch,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Divider(height=1, color="#1E1E38"),
                        ft.Row(
                            [
                                self._rvc_voice_dropdown,
                                self._rvc_base_dropdown,
                                self._rvc_base_voice_dropdown,
                            ],
                            spacing=12,
                            wrap=True,
                        ),
                        ft.Row(
                            [
                                self._rvc_pitch_label,
                                self._rvc_pitch_slider,
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            [
                                self._rvc_index_label,
                                self._rvc_index_slider,
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            [
                                self._test_voice_btn,
                                self._save_rvc_btn,
                                self._rvc_status_text,
                            ],
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=12,
                ),
                padding=ft.Padding.all(16),
                bgcolor=_CARD_BG,
                border=ft.Border.all(1, _BORDER_BG),
                border_radius=10,
            )


            return self._rvc_card
        except Exception as ex:
            _logger.warning("Error inicializando sección 'Voz RVC y Síntesis TTS': %s", ex)
            return self._build_disabled_section_card("Voz RVC y Síntesis TTS", str(ex))

    def _build_theme_section(self) -> ft.Container:
        """Construye la sección de Tema y Estilos Visuales."""
        try:
            init_style = settings.get("THEME_STYLE", "solid") or "solid"
            init_c1 = settings.get("THEME_COLOR_1", "#0C0C18") or "#0C0C18"
            init_c2 = settings.get("THEME_COLOR_2", "#1A1A36") or "#1A1A36"
            init_c3 = settings.get("THEME_COLOR_3", "#3B4FC8") or "#3B4FC8"
            init_c4 = settings.get("THEME_COLOR_4", "#60A5FA") or "#60A5FA"
            init_scheme = settings.get("THEME_SCHEME", "triada") or "triada"
            init_preset = settings.get("THEME_PRESET", "Azul AURA") or "Azul AURA"

            self._theme_status_text = ft.Text("", size=11, color="#77DD77")
            self._theme_active_badge = self._build_badge(f"ESTILO: {init_style.upper()}")

            # Preview en vivo 200x100
            curr_tokens = build_theme_tokens(
                init_style,
                [init_c1, init_c2, init_c3, init_c4],
                scheme=init_scheme,
                preset_name=init_preset,
            )
            self._theme_preview = ThemeLivePreview(initial_tokens=curr_tokens)

            # Fila de swatches derivados para mono, analogous, poly
            self._derived_swatches_row = ft.Row(spacing=6, wrap=True)
            self._derived_swatches_container = ft.Container(
                content=ft.Column(
                    [
                        ft.Text("Paleta derivada automáticamente:", size=11, color="#A0A0C0"),
                        self._derived_swatches_row,
                    ],
                    spacing=4,
                ),
                visible=(init_style in ("mono", "analogous", "poly")),
            )

            def _update_derived_swatches() -> None:
                st = self._style_dropdown.value or "solid"
                if st not in ("mono", "analogous", "poly"):
                    self._derived_swatches_container.visible = False
                    return

                self._derived_swatches_container.visible = True
                c1_val = self._picker_1.get_color()
                swatches: list[ft.Control] = []
                if st == "mono":
                    pal = derive_mono_palette(c1_val)
                elif st == "analogous":
                    pal = derive_analogous_palette(c1_val)
                else:
                    sch = self._scheme_dropdown.value or "triada"
                    pal = derive_poly_palette(c1_val, scheme=sch)

                for col in pal:
                    swatches.append(
                        ft.Container(
                            width=28,
                            height=18,
                            bgcolor=col,
                            border_radius=4,
                            border=ft.Border.all(1, "#555577"),
                            tooltip=col,
                        )
                    )
                self._derived_swatches_row.controls = swatches
                try:
                    self._derived_swatches_row.update()
                    self._derived_swatches_container.update()
                except Exception:
                    pass

            def _get_current_pickers_colors() -> list[str]:
                return [
                    self._picker_1.get_color(),
                    self._picker_2.get_color(),
                    self._picker_3.get_color(),
                    self._picker_4.get_color(),
                ]

            def _refresh_theme_preview() -> None:
                st = self._style_dropdown.value or "solid"
                sch = self._scheme_dropdown.value or "triada"
                colors = _get_current_pickers_colors()
                toks = build_theme_tokens(st, colors, scheme=sch)
                self._theme_preview.update_tokens(toks)
                _update_derived_swatches()

            def _on_picker_changed(_new_col: str) -> None:
                _refresh_theme_preview()

            # Pickers dinámicos (1 a 4)
            self._picker_1 = ColorPicker("Color 1 (Principal)", initial_color=init_c1, on_color_changed=_on_picker_changed)
            self._picker_2 = ColorPicker("Color 2 (Secundario / Acento)", initial_color=init_c2, on_color_changed=_on_picker_changed)
            self._picker_3 = ColorPicker("Color 3 (Medio / Detalle)", initial_color=init_c3, on_color_changed=_on_picker_changed)
            self._picker_4 = ColorPicker("Color 4 (Malla 4)", initial_color=init_c4, on_color_changed=_on_picker_changed)

            def _sync_pickers_visibility(st: str) -> None:
                count = STYLE_COLOR_COUNT.get(st, 1)
                self._picker_1.visible = True
                self._picker_2.visible = (count >= 2)
                self._picker_3.visible = (count >= 3)
                self._picker_4.visible = (count >= 4)
                self._scheme_dropdown.visible = (st == "poly")
                _update_derived_swatches()
                try:
                    self._pickers_row.update()
                    self._scheme_dropdown.update()
                except Exception:
                    pass

            # Dropdown de esquema cromático para poly
            self._scheme_dropdown = ft.Dropdown(
                label="Esquema Cromático (poly)",
                value=init_scheme,
                options=[
                    ft.dropdown.Option(key="triada", text="Tríada (120°)"),
                    ft.dropdown.Option(key="complementario", text="Complementario (180°)"),
                    ft.dropdown.Option(key="complementario dividido", text="Complementario dividido (150° y 210°)"),
                ],
                width=240,
                border_color="#2A2A4E",
                visible=(init_style == "poly"),
                on_select=lambda _e: _refresh_theme_preview(),
            )

            # Dropdown de estilos visuales agrupados por familia
            style_options: list[ft.dropdown.Option] = []
            for fam_title, fam_styles in STYLE_FAMILIES:
                style_options.append(ft.dropdown.Option(key=f"hdr_{fam_title}", text=f"── {fam_title} ──", disabled=True))
                for key, label in fam_styles:
                    style_options.append(ft.dropdown.Option(key=key, text=label))

            def _on_style_selected(e: Any) -> None:
                selected = e.data if getattr(e, "data", None) is not None else getattr(e.control, "value", None)
                if selected and not selected.startswith("hdr_"):
                    self._style_dropdown.value = selected
                    self._theme_active_badge.content.value = f"ESTILO: {selected.upper()}"
                    try:
                        self._theme_active_badge.update()
                    except Exception:
                        pass
                    _sync_pickers_visibility(selected)
                    _refresh_theme_preview()

            self._style_dropdown = ft.Dropdown(
                label="Estilo Visual",
                value=init_style,
                options=style_options,
                width=280,
                border_color="#2A2A4E",
                on_select=_on_style_selected,
            )

            # Dropdown Tema Rápido (Presets)
            preset_options = [ft.dropdown.Option(key=k, text=k) for k in THEME_PRESETS.keys()]

            def _on_preset_selected(e: Any) -> None:
                p_name = e.data if getattr(e, "data", None) is not None else getattr(e.control, "value", None)
                if not p_name or p_name not in THEME_PRESETS:
                    return
                p_info = THEME_PRESETS[p_name]
                st = p_info["style"]
                cols = p_info["colors"]
                sch = p_info.get("scheme", "triada")

                self._style_dropdown.value = st
                if len(cols) > 0:
                    self._picker_1.set_color(cols[0])
                if len(cols) > 1:
                    self._picker_2.set_color(cols[1])
                if len(cols) > 2:
                    self._picker_3.set_color(cols[2])
                if len(cols) > 3:
                    self._picker_4.set_color(cols[3])
                self._scheme_dropdown.value = sch

                _sync_pickers_visibility(st)
                _refresh_theme_preview()

                apply_theme(
                    style=st,
                    colors=_get_current_pickers_colors(),
                    scheme=sch,
                    preset_name=p_name,
                    save=True,
                    page=self.app_page,
                )
                self._theme_active_badge.content.value = f"ESTILO: {st.upper()}"
                self._theme_status_text.value = f"✅ Tema rápido '{p_name}' aplicado y guardado."
                self._theme_status_text.color = "#77DD77"
                try:
                    self._style_dropdown.update()
                    self._theme_active_badge.update()
                    self._theme_status_text.update()
                except Exception:
                    pass

            self._preset_dropdown = ft.Dropdown(
                label="🎨 Tema Rápido (Presets)",
                value=init_preset if init_preset in THEME_PRESETS else "Azul AURA",
                options=preset_options,
                width=280,
                border_color="#2A2A4E",
                on_select=_on_preset_selected,
            )

            # Botón Aplicar tema
            def _handle_apply_theme(_e: Any = None) -> None:
                st = self._style_dropdown.value or "solid"
                sch = self._scheme_dropdown.value or "triada"
                cnt = STYLE_COLOR_COUNT.get(st, 1)
                pickers = [self._picker_1, self._picker_2, self._picker_3, self._picker_4][:cnt]
                if not all(p.is_valid() for p in pickers):
                    self._theme_status_text.value = "❌ Corregí los colores con código hex inválido antes de aplicar."
                    self._theme_status_text.color = "#FF6B8A"
                    try:
                        self._theme_status_text.update()
                    except Exception:
                        pass
                    return

                apply_theme(
                    style=st,
                    colors=_get_current_pickers_colors(),
                    scheme=sch,
                    preset_name=self._preset_dropdown.value or "",
                    save=True,
                    page=self.app_page,
                )
                self._theme_active_badge.content.value = f"ESTILO: {st.upper()}"
                self._theme_status_text.value = f"✅ Tema '{st}' aplicado correctamente."
                self._theme_status_text.color = "#77DD77"
                try:
                    self._theme_active_badge.update()
                    self._theme_status_text.update()
                except Exception:
                    pass

            self._apply_theme_btn = ft.FilledButton(
                "Aplicar tema",
                icon=ft.Icons.PALETTE,
                on_click=_handle_apply_theme,
                style=ft.ButtonStyle(bgcolor="#4A4AEF", color="#FFFFFF"),
            )

            # Botón Restaurar azul
            def _handle_restore_blue(_e: Any = None) -> None:
                self._preset_dropdown.value = "Azul AURA"
                self._style_dropdown.value = "solid"
                self._picker_1.set_color("#0C0C18")
                self._picker_2.set_color("#1A1A36")
                self._picker_3.set_color("#3B4FC8")
                self._picker_4.set_color("#60A5FA")
                self._scheme_dropdown.value = "triada"
                _sync_pickers_visibility("solid")
                _refresh_theme_preview()

                apply_theme(
                    style="solid",
                    colors=["#0C0C18"],
                    scheme="triada",
                    preset_name="Azul AURA",
                    save=True,
                    page=self.app_page,
                )
                self._theme_active_badge.content.value = "ESTILO: SOLID"
                self._theme_status_text.value = "✅ Tema original Azul AURA restaurado."
                self._theme_status_text.color = "#77DD77"
                try:
                    self._preset_dropdown.update()
                    self._style_dropdown.update()
                    self._theme_active_badge.update()
                    self._theme_status_text.update()
                except Exception:
                    pass

            self._restore_blue_btn = ft.OutlinedButton(
                "Restaurar azul",
                icon=ft.Icons.RESTORE,
                on_click=_handle_restore_blue,
                style=ft.ButtonStyle(color="#B0B0D0"),
            )

            self._pickers_row = ft.Row(
                [self._picker_1, self._picker_2, self._picker_3, self._picker_4],
                wrap=True,
                spacing=16,
                run_spacing=12,
            )
            _sync_pickers_visibility(init_style)
            _update_derived_swatches()

            self._theme_card = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text("🎨  Tema y Estilos Visuales", size=14, weight=ft.FontWeight.BOLD, color="#E0E0EE"),
                                        ft.Text("Personalización completa con 12 estilos, círculo cromático, texturas y armonías HSL.", size=11, color="#777799"),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                self._theme_active_badge,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row([self._preset_dropdown, self._style_dropdown, self._scheme_dropdown], spacing=12, wrap=True),
                        self._pickers_row,
                        self._derived_swatches_container,
                        ft.Divider(height=1, color="#1E1E38"),
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text("Vista previa en vivo (200x100):", size=11, color="#A0A0C0"),
                                        self._theme_preview,
                                    ],
                                    spacing=4,
                                ),
                                ft.Column(
                                    [
                                        ft.Row([self._apply_theme_btn, self._restore_blue_btn], spacing=10),
                                        self._theme_status_text,
                                    ],
                                    spacing=10,
                                    alignment=ft.MainAxisAlignment.CENTER,
                                ),
                            ],
                            spacing=24,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=14,
                ),
                padding=ft.Padding.all(16),
                bgcolor=_CARD_BG,
                border=ft.Border.all(1, _BORDER_BG),
                border_radius=10,
            )


            return self._theme_card
        except Exception as ex:
            _logger.warning("Error inicializando sección 'Tema y Estilos Visuales': %s", ex)
            return self._build_disabled_section_card("Tema y Estilos Visuales", str(ex))

    def _build_background_section(self) -> ft.Container:
        """Construye la sección de Fondo de Pantalla."""
        try:
            init_bg_path = background_manager.current_image_path
            init_bg_meta = background_manager.metadata or {}
            init_bg_fit = background_manager.current_fit
            init_side_op = background_manager.current_sidebar_opacity
            init_scrim_op = background_manager.current_scrim_opacity

            self._selected_bg_path: Optional[str] = init_bg_path
            self._selected_bg_meta: dict[str, Any] = init_bg_meta

            self._bg_active_badge = self._build_badge(
                "FONDO: ACTIVO" if background_manager.is_active else "FONDO: INACTIVO"
            )
            self._bg_action_status = ft.Text("", size=11, color="#77DD77")

            # CAPA 1: Instanciación perezosa — No se crea ningún FilePicker al construir la página
            self._bg_file_picker = None

            has_init_bg = bool(init_bg_path and Path(init_bg_path).exists())

            def _resolve_card_fit(fit_str: str) -> ft.BoxFit:
                s = (fit_str or "cover").strip().lower()
                if s == "contain":
                    return ft.BoxFit.CONTAIN
                elif s in ("stretch", "fill"):
                    return ft.BoxFit.FILL
                return ft.BoxFit.COVER

            init_thumb_path = background_manager.current_thumbnail_path
            has_init_thumb = bool(init_thumb_path and Path(init_thumb_path).exists())

            self._bg_preview_img = ft.Image(
                src=init_thumb_path if has_init_thumb else (init_bg_path if has_init_bg else ""),
                fit=_resolve_card_fit(init_bg_fit),
                width=240,
                height=135,
                visible=bool(has_init_thumb or has_init_bg),
            )
            self._bg_preview_placeholder = ft.Column(
                [
                    ft.Icon(ft.Icons.IMAGE_OUTLINED, size=36, color="#555577"),
                    ft.Text("Sin fondo activo", size=11, color="#777799"),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                visible=not bool(has_init_thumb or has_init_bg),
            )
            self._bg_preview_box = ft.Container(
                content=ft.Stack(
                    controls=[
                        self._bg_preview_placeholder,
                        self._bg_preview_img,
                    ],
                    alignment=ft.Alignment.CENTER,
                ),
                width=240,
                height=135,
                bgcolor="#101022",
                border=ft.Border.all(1, "#2A2A4E"),
                border_radius=8,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
            )

            def _format_status_text(meta: dict[str, Any], has_path: bool) -> str:
                if not has_path:
                    return "Ningún fondo seleccionado (usa el tema de color)"
                if meta.get("is_gif"):
                    fc = meta.get("frames_count", 1)
                    fps_val = meta.get("fps", 0.0)
                    return f"GIF animado detectado ({fc} frames, {fps_val} fps)"
                w = meta.get("width", "?")
                h = meta.get("height", "?")
                return f"Imagen estática ({w}x{h})"

            self._bg_status_indicator = ft.Text(
                _format_status_text(init_bg_meta, has_init_bg),
                size=12,
                color="#A0A0C0",
                weight=ft.FontWeight.W_500,
            )

            def _on_pick_bg_click(_e: Any) -> None:
                self._open_background_picker()

            self._pick_bg_btn = ft.FilledButton(
                "Elegir imagen o GIF",
                icon=ft.Icons.FILE_UPLOAD_OUTLINED,
                on_click=_on_pick_bg_click,
                style=ft.ButtonStyle(bgcolor="#3B4FC8", color="#FFFFFF"),
            )

            def _on_bg_fit_selected(e: Any) -> None:
                val = e.data if getattr(e, "data", None) is not None else getattr(e.control, "value", "cover")
                if hasattr(self, "_bg_preview_img"):
                    self._bg_preview_img.fit = _resolve_card_fit(val)
                    try:
                        self._bg_preview_img.update()
                    except Exception:
                        pass
                if background_manager.is_active:
                    background_manager.update_fit(val, save=True)

            self._bg_fit_dropdown = ft.Dropdown(
                label="Ajuste",
                value=init_bg_fit if init_bg_fit in ("cover", "contain", "stretch") else "cover",
                options=[
                    ft.dropdown.Option(key="cover", text="cover (cubrir)"),
                    ft.dropdown.Option(key="contain", text="contain (contener)"),
                    ft.dropdown.Option(key="stretch", text="stretch (estirar)"),
                ],
                width=220,
                border_color="#2A2A4E",
                on_select=_on_bg_fit_selected,
            )

            # Slider Opacidad de barra lateral
            self._bg_sidebar_label = ft.Text(
                f"Opacidad de barra lateral: {init_side_op:.2f} {'(transparente)' if init_side_op <= 0.0 else ''}",
                size=12,
                color="#C0C0DE",
            )

            def _on_sidebar_opacity_change(e: Any) -> None:
                val = float(e.control.value)
                self._bg_sidebar_label.value = f"Opacidad de barra lateral: {val:.2f} {'(transparente)' if val <= 0.0 else ''}"
                try:
                    self._bg_sidebar_label.update()
                except Exception:
                    pass
                if background_manager.is_active:
                    background_manager.update_sidebar_opacity(val, save=True)

            self._bg_sidebar_slider = ft.Slider(
                min=0.0,
                max=1.0,
                divisions=20,
                value=float(init_side_op),
                label="{value}",
                expand=True,
                active_color="#4A9EFF",
                on_change=_on_sidebar_opacity_change,
            )

            # Slider Velado de legibilidad (scrim)
            self._bg_scrim_label = ft.Text(
                f"Velado de legibilidad (scrim): {init_scrim_op:.2f} {'(sin velado)' if init_scrim_op <= 0.0 else ''}",
                size=12,
                color="#C0C0DE",
            )

            def _on_scrim_opacity_change(e: Any) -> None:
                val = float(e.control.value)
                self._bg_scrim_label.value = f"Velado de legibilidad (scrim): {val:.2f} {'(sin velado)' if val <= 0.0 else ''}"
                try:
                    self._bg_scrim_label.update()
                except Exception:
                    pass
                if background_manager.is_active:
                    background_manager.update_scrim_opacity(val, save=True)

            self._bg_scrim_slider = ft.Slider(
                min=0.0,
                max=1.0,
                divisions=20,
                value=float(init_scrim_op),
                label="{value}",
                expand=True,
                active_color="#A78BFA",
                on_change=_on_scrim_opacity_change,
            )

            def _handle_apply_bg(_e: Any = None) -> None:
                if not self._selected_bg_path or not Path(self._selected_bg_path).exists():
                    self._bg_action_status.value = "❌ Elegí una imagen o GIF antes de aplicar."
                    self._bg_action_status.color = "#FF6B8A"
                    try:
                        self._bg_action_status.update()
                    except Exception:
                        pass
                    return

                fit_val = self._bg_fit_dropdown.value or "cover"
                side_val = float(self._bg_sidebar_slider.value)
                scrim_val = float(self._bg_scrim_slider.value)

                background_manager.apply_background(
                    image_path=self._selected_bg_path,
                    fit=fit_val,
                    sidebar_opacity=side_val,
                    scrim_opacity=scrim_val,
                    save=True,
                )

                # Verificación de contraste WCAG con luminancia promedio
                meta = self._selected_bg_meta or load_current_metadata() or {}
                lum = meta.get("luminance", 0.0)
                if lum >= 0.55 and scrim_val < 0.15:
                    self._show_contrast_snackbar("imagen clara: subí el velado para mejor lectura")

                self._bg_active_badge.content.value = "FONDO: ACTIVO"
                self._bg_action_status.value = "✅ Fondo de pantalla aplicado y guardado."
                self._bg_action_status.color = "#77DD77"
                try:
                    self._bg_active_badge.update()
                    self._bg_action_status.update()
                except Exception:
                    pass

            self._apply_bg_btn = ft.FilledButton(
                "Aplicar fondo",
                icon=ft.Icons.WALLPAPER,
                on_click=_handle_apply_bg,
                style=ft.ButtonStyle(bgcolor="#4A4AEF", color="#FFFFFF"),
            )

            def _handle_remove_bg(_e: Any = None) -> None:
                background_manager.remove_background(save=True)
                self._selected_bg_path = None
                self._selected_bg_meta = {}

                self._bg_preview_img.src = ""
                self._bg_preview_img.visible = False
                self._bg_preview_placeholder.visible = True
                self._bg_status_indicator.value = "Ningún fondo seleccionado (usa el tema de color)"
                self._bg_active_badge.content.value = "FONDO: INACTIVO"
                self._bg_action_status.value = "✅ Fondo quitado. Restaurado tema de color estándar."
                self._bg_action_status.color = "#77DD77"
                try:
                    self._bg_preview_box.update()
                    self._bg_status_indicator.update()
                    self._bg_active_badge.update()
                    self._bg_action_status.update()
                except Exception:
                    pass

            self._remove_bg_btn = ft.OutlinedButton(
                "Quitar fondo",
                icon=ft.Icons.HIDE_IMAGE_OUTLINED,
                on_click=_handle_remove_bg,
                style=ft.ButtonStyle(color="#B0B0D0"),
            )

            self._background_card = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text("🖼️  Fondo de Pantalla Personalizado", size=14, weight=ft.FontWeight.BOLD, color="#E0E0EE"),
                                        ft.Text("Imágenes o GIFs animados de fondo completo con sidebar translúcida y velado de lectura.", size=11, color="#777799"),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                self._bg_active_badge,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            [
                                self._pick_bg_btn,
                                self._bg_fit_dropdown,
                            ],
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            [
                                self._bg_preview_box,
                                ft.Column(
                                    [
                                        ft.Text("Estado del archivo seleccionado:", size=11, color="#A0A0C0"),
                                        self._bg_status_indicator,
                                        ft.Container(height=6),
                                        ft.Row([self._apply_bg_btn, self._remove_bg_btn], spacing=10),
                                        self._bg_action_status,
                                    ],
                                    spacing=6,
                                    expand=True,
                                ),
                            ],
                            spacing=20,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        ft.Divider(height=1, color="#1E1E38"),
                        ft.Column(
                            [
                                self._bg_sidebar_label,
                                self._bg_sidebar_slider,
                            ],
                            spacing=2,
                        ),
                        ft.Column(
                            [
                                self._bg_scrim_label,
                                self._bg_scrim_slider,
                            ],
                            spacing=2,
                        ),
                    ],
                    spacing=14,
                ),
                padding=ft.Padding.all(16),
                bgcolor=_CARD_BG,
                border=ft.Border.all(1, _BORDER_BG),
                border_radius=10,
            )


            return self._background_card
        except Exception as ex:
            _logger.warning("Error inicializando sección 'Fondo de Pantalla': %s", ex)
            return self._build_disabled_section_card("Fondo de Pantalla", str(ex))

    def _build_media_section(self) -> ft.Container:
        """Construye la sección de Reproducción Multimedia y YouTube Data API (Fase 79)."""
        try:
            current_key = settings.get("MEDIA_YT_API_KEY", "")
            current_svc = settings.get("MEDIA_SERVICE", "youtube_music")

            has_key = bool(current_key.strip())
            self._media_badge = self._build_badge(
                "v2 AUTOPLAY ACTIVO" if has_key else "MODO v1 (BÚSQUEDA)",
                color="#77DD77" if has_key else "#B0B0D0",
                bg="#1A2A2A" if has_key else "#222244",
            )

            self._media_key_field = ft.TextField(
                label="YouTube Data API v3 Key",
                value=current_key,
                password=True,
                can_reveal_password=True,
                hint_text="AIzaSy...",
                width=380,
                border_color="#2A2A4E",
                text_size=12,
            )

            self._media_svc_dropdown = ft.Dropdown(
                label="Servicio Multimedia Principal",
                value=current_svc if current_svc in ("youtube_music", "youtube", "spotify") else "youtube_music",
                options=[
                    ft.dropdown.Option(key="youtube_music", text="YouTube Music (Recomendado)"),
                    ft.dropdown.Option(key="youtube", text="YouTube (Videos)"),
                    ft.dropdown.Option(key="spotify", text="Spotify (Búsqueda / Próximamente v3)"),
                ],
                width=300,
                border_color="#2A2A4E",
            )

            self._media_status_text = ft.Text(
                "Con API key, la música se reproduce automáticamente sin hacer click en el navegador.",
                size=11,
                color="#777799",
            )

            self._test_media_key_btn = ft.FilledButton(
                "Probar key",
                icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                style=ft.ButtonStyle(bgcolor="#2A2A4E", color="#C0C0E0"),
                on_click=self._handle_test_media_key,
            )

            self._save_media_btn = ft.FilledButton(
                "Guardar configuración",
                icon=ft.Icons.SAVE,
                style=ft.ButtonStyle(bgcolor="#3B4FC8", color="#FFFFFF"),
                on_click=self._handle_save_media,
            )

            def _open_gcloud_console(e):
                import webbrowser
                webbrowser.open("https://console.cloud.google.com/apis/credentials", new=2)

            tutorial_box = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color="#4A9EFF"),
                                ft.Text(
                                    "¿Cómo obtener tu YouTube API key gratuita (10.000 búsquedas/día)?",
                                    size=12,
                                    weight=ft.FontWeight.BOLD,
                                    color="#C0C0E0",
                                ),
                            ],
                            spacing=6,
                        ),
                        ft.Text(
                            "1. Entrá a Google Cloud Console con tu cuenta Google.\n"
                            "2. Creá un proyecto nuevo y habilitá 'YouTube Data API v3' en APIs & Services > Library.\n"
                            "3. En APIs & Services > Credentials, hacé click en '+ CREATE CREDENTIALS' > 'API key' y pegala arriba.",
                            size=11,
                            color="#8888AA",
                        ),
                        ft.TextButton(
                            "Abrir Google Cloud Console",
                            icon=ft.Icons.OPEN_IN_NEW,
                            style=ft.ButtonStyle(color="#4A9EFF"),
                            on_click=_open_gcloud_console,
                        ),
                    ],
                    spacing=6,
                ),
                padding=ft.Padding.all(12),
                bgcolor="#121228",
                border=ft.Border.all(1, "#1E1E3C"),
                border_radius=8,
            )

            limits_box = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.SHIELD_OUTLINED, size=14, color="#777799"),
                        ft.Text(
                            "Nota: Spotify requiere Web API con OAuth2 de usuario y cuenta Premium (v3). "
                            "No se utiliza yt-dlp para respetar los Términos de Servicio de YouTube.",
                            size=10,
                            color="#777799",
                            expand=True,
                        ),
                    ],
                    spacing=8,
                ),
                padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                bgcolor="#0D0D1A",
                border_radius=6,
            )

            self._media_card = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text("Reproducción Multimedia (Media)", size=14, weight=ft.FontWeight.BOLD, color="#E0E0EE"),
                                        ft.Text("Reproducción directa y búsqueda en YouTube Music, YouTube y Spotify.", size=11, color="#777799"),
                                    ],
                                    spacing=2,
                                ),
                                self._media_badge,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            [
                                self._media_svc_dropdown,
                                self._media_key_field,
                            ],
                            wrap=True,
                            spacing=12,
                        ),
                        ft.Row(
                            [
                                self._test_media_key_btn,
                                self._save_media_btn,
                            ],
                            spacing=10,
                        ),
                        self._media_status_text,
                        tutorial_box,
                        limits_box,
                    ],
                    spacing=12,
                ),
                padding=ft.Padding.all(16),
                bgcolor=_CARD_BG,
                border=ft.Border.all(1, _BORDER_BG),
                border_radius=10,
            )
            return self._media_card
        except Exception as ex:
            _logger.warning("Error inicializando sección 'Reproducción Multimedia': %s", ex)
            return self._build_disabled_section_card("Reproducción Multimedia", str(ex))

    def _build(self) -> None:
        self.bgcolor = _BG_DARK

        # ── Encabezado Principal y Acciones Globales ───────────────
        title_header = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("⚙️  Configuración", size=24, weight=ft.FontWeight.BOLD, color="#E8E8FF"),
                        ft.Text(
                            "Ajustes del sistema, IA, audio, seguridad, memoria y herramientas de diagnóstico.",
                            size=12,
                            color="#7A7A9A",
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.Row(
                    [
                        ft.OutlinedButton(
                            "🔄 Valores por defecto",
                            icon=ft.Icons.RESTORE,
                            on_click=self._handle_restore_defaults,
                            style=ft.ButtonStyle(color="#B0B0D0"),
                        ),
                        ft.OutlinedButton(
                            "✨ Asistente IA",
                            icon=ft.Icons.AUTO_AWESOME,
                            on_click=lambda e: self._handle_open_wizard(),
                            style=ft.ButtonStyle(color="#A78BFA"),
                        ),
                    ],
                    spacing=8,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # ── Categorías de Navegación Rápida (Filtros de Sección) ──
        self._category_chips = ft.Row(
            [
                self._create_category_chip("all", "🌐 Todas", True),
                self._create_category_chip("general", "🎨 General", False),
                self._create_category_chip("ai", "🤖 IA", False),
                self._create_category_chip("audio", "🎙️ Audio", False),
                self._create_category_chip("media", "🎵 Media", False),
                self._create_category_chip("theme", "🎨 Tema", False),
                self._create_category_chip("background", "🖼️ Fondo", False),
                self._create_category_chip("security", "🛡️ Seguridad", False),
                self._create_category_chip("memory", "🧠 Memoria", False),
                self._create_category_chip("tools", "🔍 Diagnóstico", False),
            ],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
        )

        # ── SECCIÓN 1: General (Tema, Idioma, Workspace, Navegador) ─
        self._theme_switch = ft.Switch(
            label="Modo oscuro",
            value=(settings.get("APP_THEME", "dark") == "dark"),
            active_color="#4A9EFF",
            on_change=self._toggle_theme,
        )

        current_lang = settings.get("APP_LANGUAGE", "es") or "es"
        self._language_dropdown = ft.Dropdown(
            label="Idioma de la Interfaz",
            value=current_lang,
            options=[
                ft.dropdown.Option(key="es", text="Español (es)"),
                ft.dropdown.Option(key="en", text="English (en)"),
            ],
            width=220,
            border_color="#2A2A4E",
            on_select=self._on_language_changed,
        )

        # Workspace
        default_workspace = str(Path.home() / "Documents")
        curr_workspace = settings.get("WORKSPACE_PATH", default_workspace) or default_workspace
        self._workspace_field = ft.TextField(
            label="Carpeta de Trabajo (Workspace)",
            value=curr_workspace,
            border_color="#2A2A4E",
            text_size=12,
            expand=True,
            hint_text="Ruta absoluta al directorio donde AURA creará y buscará proyectos",
        )

        self._workspace_status_text = ft.Text("", size=11, color="#777799")
        self._update_workspace_status_label(curr_workspace)

        self._save_workspace_btn = ft.FilledButton(
            "Guardar Carpeta",
            icon=ft.Icons.FOLDER_SPECIAL,
            on_click=self._on_save_workspace,
            style=ft.ButtonStyle(bgcolor="#3A3A6A", color="#FFFFFF"),
        )

        self._reset_workspace_btn = ft.OutlinedButton(
            "Restablecer a Documentos",
            icon=ft.Icons.RESTORE_PAGE,
            on_click=self._on_reset_workspace,
            style=ft.ButtonStyle(color="#B0B0D0"),
        )

        # Navegador Web
        pref_browser = get_preferred_browser_name()
        browser_options = []
        for b in SUPPORTED_BROWSERS:
            res = resolve_app(b)
            disp = BROWSER_DISPLAY_NAMES.get(b, b.title())
            if res.success:
                browser_options.append(ft.dropdown.Option(key=b, text=f"{disp} (instalado)"))
            else:
                browser_options.append(ft.dropdown.Option(key=b, text=f"{disp} (no detectado)"))

        keys_in_options = [opt.key for opt in browser_options]
        if pref_browser not in keys_in_options:
            browser_options.append(ft.dropdown.Option(key=pref_browser, text=f"{pref_browser} (personalizado)"))

        self._browser_status_text = ft.Text("", size=11, color="#777799")

        def _update_browser_status_label(b_key: str):
            res_b = resolve_app(b_key)
            if res_b.success:
                self._browser_status_text.value = f"Ruta activa: {res_b.executable}"
                self._browser_status_text.color = "#77DD77"
            else:
                self._browser_status_text.value = f"Aviso: {res_b.error}"
                self._browser_status_text.color = "#FFAA00"
            try:
                self._browser_status_text.update()
            except Exception:
                pass

        def _on_browser_changed(e):
            selected = e.data if getattr(e, "data", None) is not None else getattr(e.control, "value", None)
            if selected:
                self._browser_dropdown.value = selected
                settings.set("BROWSER_PREFERIDO", selected)
                _logger.info("Configuración: BROWSER_PREFERIDO cambiado a '%s'", selected)
                _update_browser_status_label(selected)

        self._browser_dropdown = ft.Dropdown(
            label="Navegador Web",
            value=pref_browser if pref_browser in [opt.key for opt in browser_options] else ("firefox" if "firefox" in keys_in_options else None),
            options=browser_options,
            width=280,
            on_select=_on_browser_changed,
            border_color="#2A2A4E",
        )
        _update_browser_status_label(self._browser_dropdown.value or pref_browser)

        self._general_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text("Apariencia e Idioma", size=14, weight=ft.FontWeight.BOLD, color="#E0E0EE"),
                                    ft.Text("Personalizá el tema visual y el idioma principal del asistente.", size=11, color="#777799"),
                                ],
                                spacing=2,
                            ),
                            ft.Row([self._language_dropdown, self._theme_switch], spacing=16),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(height=1, color="#1E1E38"),
                    ft.Text("Carpeta de Trabajo (Workspace)", size=13, weight=ft.FontWeight.BOLD, color="#D0D0E8"),
                    ft.Text("Directorio base para búsqueda, creación de proyectos y manipulación de archivos.", size=11, color="#777799"),
                    ft.Row([self._workspace_field, self._save_workspace_btn, self._reset_workspace_btn], spacing=8),
                    self._workspace_status_text,
                    ft.Divider(height=1, color="#1E1E38"),
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text("Navegador Web Preferido", size=13, weight=ft.FontWeight.BOLD, color="#D0D0E8"),
                                    ft.Text("Se utilizará para abrir enlaces y en el comando genérico 'navegador'.", size=11, color="#777799"),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            self._browser_dropdown,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self._browser_status_text,
                ],
                spacing=10,
            ),
            padding=ft.Padding.all(16),
            bgcolor=_CARD_BG,
            border=ft.Border.all(1, _BORDER_BG),
            border_radius=10,
        )

        # ── SECCIÓN 2: Inteligencia Artificial Multi-proveedor ─────
        current_provider = (settings.get("AI_PROVIDER", "ollama") or "ollama").strip().lower()
        if current_provider not in ("ollama", "openai", "anthropic", "gemini", "xai", "custom"):
            current_provider = "ollama"

        current_model = settings.get("AI_MODEL", "") or "qwen2.5:3b"

        provider_options = [
            ft.dropdown.Option(key="ollama", text="Ollama (Local)"),
            ft.dropdown.Option(key="openai", text="OpenAI (ChatGPT)"),
            ft.dropdown.Option(key="anthropic", text="Anthropic (Claude)"),
            ft.dropdown.Option(key="gemini", text="Google Gemini"),
            ft.dropdown.Option(key="xai", text="xAI (Grok)"),
            ft.dropdown.Option(key="custom", text="Compatible OpenAI (Custom)"),
        ]

        self._ai_active_badge = ft.Container(
            content=ft.Text(f"ACTIVO: {current_provider.upper()}", size=11, weight=ft.FontWeight.BOLD, color="#A78BFA"),
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            bgcolor="#25254A",
            border_radius=12,
        )

        self._ollama_url_field = ft.TextField(
            label="URL del servidor Ollama",
            value=settings.get("OLLAMA_URL", "http://localhost:11434") or "http://localhost:11434",
            border_color="#2A2A4E",
            text_size=13,
            expand=True,
        )

        self._api_key_field = ft.TextField(
            label="API Key",
            password=True,
            can_reveal_password=True,
            border_color="#2A2A4E",
            text_size=13,
            hint_text="sk-...",
            expand=True,
        )

        self._custom_url_field = ft.TextField(
            label="Base URL del Endpoint",
            value=settings.get("CUSTOM_BASE_URL", ""),
            border_color="#2A2A4E",
            text_size=13,
            hint_text="ej: https://api.groq.com/openai/v1 o http://localhost:1234/v1",
            expand=True,
        )

        self._custom_model_field = ft.TextField(
            label="Nombre del modelo (Custom)",
            value=settings.get("CUSTOM_MODEL", ""),
            border_color="#2A2A4E",
            text_size=13,
            hint_text="ej: llama-3.3-70b-versatile",
            expand=True,
        )

        self._model_dropdown = ft.Dropdown(
            label="Modelo",
            options=[],
            value=current_model,
            width=280,
            border_color="#2A2A4E",
        )

        self._timeout_field = ft.TextField(
            label="Timeout HTTP (seg)",
            value=str(settings.get_int("AI_HTTP_TIMEOUT", 30)),
            width=130,
            border_color="#2A2A4E",
            text_size=12,
        )

        self._fallback_checkbox = ft.Checkbox(
            label="Fallback automático a Ollama local si falla el proveedor en la nube",
            value=settings.get_bool("AI_FALLBACK_OLLAMA", True),
            active_color="#4A9EFF",
        )

        self._ai_status_text = ft.Text("", size=11, color="#777799")

        def _get_key_for_provider(prov_key: str) -> str:
            if prov_key == "openai":
                return settings.get("OPENAI_API_KEY", "") or ""
            elif prov_key == "anthropic":
                return settings.get("ANTHROPIC_API_KEY", "") or ""
            elif prov_key == "gemini":
                return settings.get("GEMINI_API_KEY", "") or ""
            elif prov_key == "xai":
                return settings.get("XAI_API_KEY", "") or ""
            elif prov_key == "custom":
                return settings.get("CUSTOM_API_KEY", "") or ""
            return ""

        def _refresh_models_dropdown(prov_key: str, models_list: list[str] | None = None):
            meta = PROVIDER_METADATA.get(prov_key, {})
            models = list(models_list or meta.get("recommended_models", []))
            default_mod = meta.get("default_model", "")
            curr = settings.get("AI_MODEL", "")

            if curr and curr not in models:
                models.insert(0, curr)
            if default_mod and default_mod not in models:
                models.append(default_mod)

            self._model_dropdown.options = [
                ft.dropdown.Option(key=m, text=m) for m in models
            ]
            if curr in models:
                self._model_dropdown.value = curr
            elif default_mod in models:
                self._model_dropdown.value = default_mod
            elif models:
                self._model_dropdown.value = models[0]
            else:
                self._model_dropdown.value = None

        def _update_provider_ui(prov_key: str):
            meta = PROVIDER_METADATA.get(prov_key, {})
            disp = meta.get("display_name", prov_key.title())

            if prov_key == "ollama":
                ollama_row.visible = True
                api_key_row.visible = False
                custom_row.visible = False
            elif prov_key == "custom":
                ollama_row.visible = False
                api_key_row.visible = True
                self._api_key_field.label = "API Key (opcional si es local)"
                custom_key = _get_key_for_provider("custom")
                self._api_key_field.value = custom_key
                self._api_key_field.helper_text = format_key_loaded(custom_key) or None
                custom_row.visible = True
            else:
                ollama_row.visible = False
                api_key_row.visible = True
                self._api_key_field.label = f"API Key para {disp}"
                prov_key_val = _get_key_for_provider(prov_key)
                self._api_key_field.value = prov_key_val
                self._api_key_field.helper_text = format_key_loaded(prov_key_val) or None
                custom_row.visible = False

            _refresh_models_dropdown(prov_key)
            try:
                self._provider_dropdown.update()
                ollama_row.update()
                api_key_row.update()
                custom_row.update()
                self._model_dropdown.update()
            except Exception:
                pass

        def _on_provider_changed(e):
            selected = e.data if getattr(e, "data", None) is not None else getattr(e.control, "value", None)
            if selected:
                self._provider_dropdown.value = selected
                _update_provider_ui(selected)

        self._provider_dropdown = ft.Dropdown(
            label="Proveedor de IA",
            value=current_provider,
            options=provider_options,
            width=280,
            on_select=_on_provider_changed,
            border_color="#2A2A4E",
        )

        ollama_row = ft.Row([self._ollama_url_field], visible=(current_provider == "ollama"))
        api_key_row = ft.Row([self._api_key_field], visible=(current_provider != "ollama"))
        custom_row = ft.Row(
            [self._custom_url_field, self._custom_model_field],
            visible=(current_provider == "custom"),
            spacing=8,
        )

        def _on_test_connection(e=None):
            selected_prov = self._provider_dropdown.value or "ollama"
            self._test_conn_btn.disabled = True
            self._ai_status_text.value = f"⏳ Probando conexión con {selected_prov.upper()}..."
            self._ai_status_text.color = "#8888AA"
            try:
                self._test_conn_btn.update()
                self._ai_status_text.update()
            except Exception:
                pass

            def _test_worker():
                try:
                    kwargs = {}
                    if selected_prov == "ollama":
                        kwargs = {
                            "base_url": self._ollama_url_field.value or "http://localhost:11434",
                            "model": self._model_dropdown.value or "qwen2.5:3b",
                        }
                    elif selected_prov == "custom":
                        kwargs = {
                            "base_url": self._custom_url_field.value or "",
                            "api_key": self._api_key_field.value or "",
                            "model": self._custom_model_field.value or self._model_dropdown.value or "default",
                        }
                    else:
                        kwargs = {
                            "api_key": self._api_key_field.value or "",
                            "model": self._model_dropdown.value or "",
                        }

                    t0 = time.perf_counter()
                    temp_prov = get_provider(selected_prov, **kwargs)
                    ok, detail = temp_prov.health_check()
                    latency_ms = (time.perf_counter() - t0) * 1000

                    if ok:
                        self._ai_status_text.value = f"✅ Conexión exitosa ({latency_ms:.0f} ms): {detail}"
                        self._ai_status_text.color = "#77DD77"
                        try:
                            live_models = temp_prov.list_models()
                            if live_models:
                                _refresh_models_dropdown(selected_prov, live_models)
                                try:
                                    self._model_dropdown.update()
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    else:
                        self._ai_status_text.value = f"❌ Error de conexión ({latency_ms:.0f} ms): {detail}"
                        self._ai_status_text.color = "#FF6B8A"
                except Exception as ex:
                    self._ai_status_text.value = f"❌ Error inesperado: {ex}"
                    self._ai_status_text.color = "#FF6B8A"
                finally:
                    self._test_conn_btn.disabled = False
                    try:
                        self._test_conn_btn.update()
                        self._ai_status_text.update()
                    except Exception:
                        pass

            threading.Thread(target=_test_worker, daemon=True).start()

        def _on_save_ai(e=None):
            selected_prov = self._provider_dropdown.value or "ollama"
            settings.set("AI_PROVIDER", selected_prov)

            chosen_model = self._model_dropdown.value or ""
            if selected_prov == "custom" and self._custom_model_field.value:
                chosen_model = self._custom_model_field.value.strip()

            if chosen_model:
                settings.set("AI_MODEL", chosen_model)

            fallback_val = "true" if self._fallback_checkbox.value else "false"
            settings.set("AI_FALLBACK_OLLAMA", fallback_val)

            if self._timeout_field.value and self._timeout_field.value.isdigit():
                settings.set("AI_HTTP_TIMEOUT", self._timeout_field.value.strip())

            if selected_prov == "ollama":
                settings.set("OLLAMA_URL", self._ollama_url_field.value or "http://localhost:11434")
            elif selected_prov == "openai":
                settings.set("OPENAI_API_KEY", self._api_key_field.value or "")
            elif selected_prov == "anthropic":
                settings.set("ANTHROPIC_API_KEY", self._api_key_field.value or "")
            elif selected_prov == "gemini":
                settings.set("GEMINI_API_KEY", self._api_key_field.value or "")
            elif selected_prov == "xai":
                settings.set("XAI_API_KEY", self._api_key_field.value or "")
            elif selected_prov == "custom":
                settings.set("CUSTOM_BASE_URL", self._custom_url_field.value or "")
                settings.set("CUSTOM_API_KEY", self._api_key_field.value or "")
                settings.set("CUSTOM_MODEL", self._custom_model_field.value or chosen_model)

            reset_default_provider()

            if selected_prov != "ollama":
                self._api_key_field.helper_text = format_key_loaded(self._api_key_field.value or "") or None
                try:
                    self._api_key_field.update()
                except Exception:
                    pass

            self._ai_active_badge.content.value = f"ACTIVO: {selected_prov.upper()}"
            self._ai_status_text.value = f"✅ Guardado. Proveedor '{selected_prov.upper()}' activo ({chosen_model})."
            self._ai_status_text.color = "#77DD77"
            try:
                self._ai_active_badge.update()
                self._ai_status_text.update()
            except Exception:
                pass

        self._test_conn_btn = ft.FilledButton(
            "Probar conexión",
            icon=ft.Icons.NETWORK_CHECK,
            on_click=_on_test_connection,
            style=ft.ButtonStyle(bgcolor="#3A3A6A", color="#FFFFFF"),
        )

        self._save_ai_btn = ft.FilledButton(
            "Guardar y aplicar",
            icon=ft.Icons.SAVE,
            on_click=_on_save_ai,
            style=ft.ButtonStyle(bgcolor="#4A4AEF", color="#FFFFFF"),
        )

        _refresh_models_dropdown(current_provider)
        if current_provider != "ollama":
            init_key = _get_key_for_provider(current_provider)
            self._api_key_field.value = init_key
            self._api_key_field.helper_text = format_key_loaded(init_key) or None

        self._ai_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text("Proveedor de Inteligencia Artificial", size=14, weight=ft.FontWeight.BOLD, color="#E0E0EE"),
                                    ft.Text(
                                        "Configurá Ollama local o proveedores en la nube (OpenAI, Claude, Gemini, Grok, Custom)",
                                        size=11,
                                        color="#777799",
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            self._ai_active_badge,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row([self._provider_dropdown, self._model_dropdown, self._timeout_field], spacing=12),
                    ollama_row,
                    api_key_row,
                    custom_row,
                    self._fallback_checkbox,
                    ft.Row(
                        [
                            self._test_conn_btn,
                            self._save_ai_btn,
                            self._ai_status_text,
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=12,
            ),
            padding=ft.Padding.all(16),
            bgcolor=_CARD_BG,
            border=ft.Border.all(1, _BORDER_BG),
            border_radius=10,
        )

                # ── SECCIÓN 3: Audio y Voz ─────────────────────────────────
        self._audio_card = self._build_audio_section()

        # ── SECCIÓN 3b: Voz RVC y Síntesis TTS ─────────────────────
        self._rvc_card = self._build_rvc_section()

        # ── SECCIÓN 3c: Reproducción Multimedia (Fase 79) ─────────
        self._media_card = self._build_media_section()

        # ── SECCIÓN 3d: Tema y Estilos Visuales (Fase 76) ───────────
        self._theme_card = self._build_theme_section()

        # ── SECCIÓN 3e: Fondo de Pantalla Personalizado (Fase 78) ─────
        self._background_card = self._build_background_section()

        # ── SECCIÓN 4: Seguridad y Confirmaciones ───────────────────
        self._confirm_destructive_switch = ft.Switch(
            label="Confirmar acciones destructivas (vaciar papelera, borrado permanente)",
            value=settings.get_bool("CONFIRM_DESTRUCTIVE", True),
            active_color="#4A9EFF",
            on_change=lambda e: self._on_security_toggle("CONFIRM_DESTRUCTIVE", e.control.value),
        )

        self._confirm_shutdown_switch = ft.Switch(
            label="Confirmar apagar o reiniciar el sistema",
            value=settings.get_bool("CONFIRM_SHUTDOWN", True),
            active_color="#4A9EFF",
            on_change=lambda e: self._on_security_toggle("CONFIRM_SHUTDOWN", e.control.value),
        )

        self._confirm_close_app_switch = ft.Switch(
            label="Pedir confirmación antes de cerrar aplicaciones con 'cerrar <app>'",
            value=settings.get_bool("CONFIRMAR_CIERRE_APP", False),
            active_color="#4A9EFF",
            on_change=lambda e: self._on_security_toggle("CONFIRMAR_CIERRE_APP", e.control.value),
        )

        self._router_first_switch = ft.Switch(
            label="Priorizar router de comandos del sistema antes de consultar al LLM",
            value=settings.get_bool("ROUTER_FIRST", True),
            active_color="#4A9EFF",
            on_change=lambda e: self._on_security_toggle("ROUTER_FIRST", e.control.value),
        )

        self._security_status_text = ft.Text("", size=11, color="#77DD77")

        self._save_security_btn = ft.FilledButton(
            "Guardar Políticas de Seguridad",
            icon=ft.Icons.SECURITY,
            on_click=self._on_save_all_security,
            style=ft.ButtonStyle(bgcolor="#2A4A3A", color="#FFFFFF"),
        )

        self._security_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text("Seguridad y Límites de Confirmación", size=14, weight=ft.FontWeight.BOLD, color="#E0E0EE"),
                                    ft.Text("Definí qué operaciones críticas requieren confirmación explícita previa.", size=11, color="#777799"),
                                ],
                                spacing=2,
                            ),
                            self._save_security_btn,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self._confirm_destructive_switch,
                    self._confirm_shutdown_switch,
                    self._confirm_close_app_switch,
                    self._router_first_switch,
                    self._security_status_text,
                ],
                spacing=10,
            ),
            padding=ft.Padding.all(16),
            bgcolor=_CARD_BG,
            border=ft.Border.all(1, _BORDER_BG),
            border_radius=10,
        )

        # ── SECCIÓN 5: Memoria de Usuario y Personalidad ───────────
        # Badges de memoria
        self._mem_paths_badge = self._build_badge(f"{len(user_memory.list_paths())} rutas")
        self._mem_progs_badge = self._build_badge(f"{len(user_memory.list_programs())} programas")
        self._mem_facts_badge = self._build_badge(f"{len(user_memory.list_facts())} hechos")
        cur_proj = user_memory.get_current_project()
        self._mem_proj_badge = self._build_badge(f"Proyecto: {cur_proj.name if cur_proj else 'Ninguno'}")

        self._mem_status_text = ft.Text("", size=11, color="#777799")

        self._export_mem_btn = ft.FilledButton(
            "💾 Exportar Respaldo JSON",
            on_click=self._on_export_memory,
            style=ft.ButtonStyle(bgcolor="#3A3A6A", color="#FFFFFF"),
        )

        self._clear_mem_btn = ft.OutlinedButton(
            "🧹 Limpiar Memoria",
            on_click=self._on_clear_memory,
            style=ft.ButtonStyle(color="#FFAA88"),
        )

        # Personalidad y Grok
        curr_personality = get_current_personality()
        personality_options = [
            ft.dropdown.Option(key=m.key, text=f"{m.display_label} {m.icon}")
            for m in list_personalities()
        ]

        self._personality_badge = ft.Container(
            content=ft.Text(f"{curr_personality.icon} {curr_personality.name}", size=11, color="#E0E0EE"),
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            bgcolor="#25254A",
            border_radius=12,
        )

        self._preview_greeting_text = ft.Text("", size=11, color="#B0B0D0")
        self._preview_open_text = ft.Text("", size=11, color="#90D090")
        self._preview_error_text = ft.Text("", size=11, color="#FFA080")
        self._preview_success_text = ft.Text("", size=11, color="#80D0FF")

        def _refresh_preview_labels(mode: PersonalityMode):
            dark_humor = settings.get_bool("AURA_ALLOW_DARK_HUMOR", False)
            insults = settings.get_bool("AURA_ALLOW_INSULTS", False)
            self._preview_greeting_text.value = f"👋 Saludo:  \"{rude_engine.get_phrase('greeting', personality=mode, allow_dark_humor=dark_humor, allow_insults=insults)}\""
            self._preview_open_text.value = f"🚀 Abrir app:  \"{rude_engine.get_phrase('open', personality=mode, target='VS Code', allow_dark_humor=dark_humor, allow_insults=insults)}\""
            self._preview_error_text.value = f"💥 Error:  \"{rude_engine.get_phrase('error', personality=mode, target='servidor', allow_dark_humor=dark_humor, allow_insults=insults)}\""
            self._preview_success_text.value = f"✅ Éxito:  \"{rude_engine.get_phrase('success', personality=mode, target='backup', allow_dark_humor=dark_humor, allow_insults=insults)}\""
            self._personality_badge.content.value = f"{mode.icon} {mode.name}"
            try:
                self._preview_greeting_text.update()
                self._preview_open_text.update()
                self._preview_error_text.update()
                self._preview_success_text.update()
                self._personality_badge.update()
            except Exception:
                pass

        def _on_personality_selected(e):
            selected_key = e.data if getattr(e, "data", None) is not None else getattr(e.control, "value", None)
            if selected_key:
                mode = set_personality(selected_key)
                self._personality_dropdown.value = mode.key
                self._rude_slider.value = mode.level
                try:
                    self._personality_dropdown.update()
                    self._rude_slider.update()
                except Exception:
                    pass
                _refresh_preview_labels(mode)

        def _on_rude_slider_changed(e):
            val = int(round(e.control.value))
            mode = set_personality(val)
            self._personality_dropdown.value = mode.key
            try:
                self._personality_dropdown.update()
            except Exception:
                pass
            _refresh_preview_labels(mode)

        def _on_dark_humor_changed(e):
            val = bool(e.control.value)
            settings.set("AURA_ALLOW_DARK_HUMOR", "true" if val else "false")
            _refresh_preview_labels(get_current_personality())

        def _on_insults_changed(e):
            val = bool(e.control.value)
            settings.set("AURA_ALLOW_INSULTS", "true" if val else "false")
            _refresh_preview_labels(get_current_personality())

        self._personality_dropdown = ft.Dropdown(
            label="Personalidad",
            value=curr_personality.key,
            options=personality_options,
            width=280,
            on_select=_on_personality_selected,
            border_color="#2A2A4E",
        )

        self._rude_slider = ft.Slider(
            min=0,
            max=5,
            divisions=5,
            value=curr_personality.level,
            label="{value}",
            on_change=_on_rude_slider_changed,
            expand=True,
            active_color="#A78BFA",
        )

        self._dark_humor_checkbox = ft.Checkbox(
            label="Permitir humor negro",
            value=settings.get_bool("AURA_ALLOW_DARK_HUMOR", False),
            on_change=_on_dark_humor_changed,
        )

        self._insults_checkbox = ft.Checkbox(
            label="Permitir insultos",
            value=settings.get_bool("AURA_ALLOW_INSULTS", False),
            on_change=_on_insults_changed,
        )

        preview_box = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Preview del tono actual:", size=12, weight=ft.FontWeight.BOLD, color="#B0B0D0"),
                            ft.TextButton(
                                "🎲 Probar otra frase",
                                on_click=lambda e: _refresh_preview_labels(get_current_personality()),
                                style=ft.ButtonStyle(color="#A78BFA"),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self._preview_greeting_text,
                    self._preview_open_text,
                    self._preview_error_text,
                    self._preview_success_text,
                ],
                spacing=6,
            ),
            padding=ft.Padding.all(12),
            bgcolor="#0A0A1A",
            border=ft.Border.all(1, "#1E1E38"),
            border_radius=8,
        )

        _refresh_preview_labels(curr_personality)

        # Comprensión difusa (Fuzzy & Typo)
        fuzzy_val = settings.get_float("FUZZY_THRESHOLD", 0.85)
        self._fuzzy_slider = ft.Slider(
            min=0.50,
            max=1.00,
            divisions=10,
            value=fuzzy_val,
            label="{value}",
            on_change=self._on_fuzzy_slider_changed,
            expand=True,
            active_color="#4A9EFF",
        )

        self._use_llm_fuzzy_switch = ft.Switch(
            label="Interpretar comandos con errores tipográficos mediante LLM local si no coinciden exactamente",
            value=settings.get_bool("USE_LLM_INTERPRETER", True),
            active_color="#4A9EFF",
            on_change=self._on_llm_fuzzy_changed,
        )

        self._memory_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text("Memoria de Usuario y Hábitos (Fase 28)", size=14, weight=ft.FontWeight.BOLD, color="#E0E0EE"),
                                    ft.Text("AURA aprende rutas, programas frecuentes, proyectos y hechos de largo plazo.", size=11, color="#777799"),
                                ],
                                spacing=2,
                            ),
                            ft.Row([self._export_mem_btn, self._clear_mem_btn], spacing=8),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            self._mem_paths_badge,
                            self._mem_progs_badge,
                            self._mem_facts_badge,
                            self._mem_proj_badge,
                        ],
                        spacing=8,
                        wrap=True,
                    ),
                    self._mem_status_text,
                    ft.Divider(height=1, color="#1E1E38"),
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Text("Personalidad y Modo Grok (Fase 51)", size=13, weight=ft.FontWeight.BOLD, color="#D0D0E8"),
                                            self._personality_badge,
                                        ],
                                        spacing=10,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    ),
                                    ft.Text("Modula el nivel de formalidad, picardía o grosería en las respuestas.", size=11, color="#777799"),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            self._personality_dropdown,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            ft.Text("Nivel de grosería (0 a 5):", size=12, color="#C0C0DE", width=170),
                            self._rude_slider,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            self._dark_humor_checkbox,
                            self._insults_checkbox,
                        ],
                        spacing=24,
                    ),
                    preview_box,
                    ft.Divider(height=1, color="#1E1E38"),
                    ft.Text("Comprensión de Comandos y Corrección de Tipeo (Fase 54)", size=13, weight=ft.FontWeight.BOLD, color="#D0D0E8"),
                    ft.Row(
                        [
                            ft.Text(f"Umbral de similitud difusa: {self._fuzzy_slider.value:.2f}", size=12, color="#C0C0DE", width=220),
                            self._fuzzy_slider,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self._use_llm_fuzzy_switch,
                ],
                spacing=12,
            ),
            padding=ft.Padding.all(16),
            bgcolor=_CARD_BG,
            border=ft.Border.all(1, _BORDER_BG),
            border_radius=10,
        )

        # ── SECCIÓN 6: Herramientas, Índice y Diagnóstico ──────────
        self._index_count_badge = ft.Container(
            content=ft.Text(f"{app_index_manager.count()} apps indexadas", size=11, color="#E0E0EE"),
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            bgcolor="#25254A",
            border_radius=12,
        )

        self._index_status_text = ft.Text(
            "AURA indexa programas en PATH, Menú Inicio y Registro para abrirlos al instante sin demora.",
            size=11,
            color="#777799",
        )

        self._index_btn = ft.FilledButton(
            "🔍 Indexar mis apps ahora",
            on_click=lambda e: self._handle_index_btn_click(),
            style=ft.ButtonStyle(bgcolor="#2E5CB8", color="#FFFFFF"),
        )

        self._cancel_index_btn = ft.OutlinedButton(
            "⏹️ Cancelar",
            on_click=lambda e: self._cancel_app_indexing(),
            visible=False,
            style=ft.ButtonStyle(color="#FF8888"),
        )

        index_actions_row = ft.Row(
            [
                self._index_btn,
                self._cancel_index_btn,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Diagnóstico y Self-test
        self._diag_text = ft.Text(
            "Presioná 'Ejecutar Diagnóstico' o 'Autochequeo / Tests' para analizar el estado en vivo.",
            size=11,
            color="#777799",
            font_family="monospace",
        )

        self._diag_btn = ft.FilledButton(
            "🔍 Diagnóstico General",
            on_click=lambda e: self._run_system_diagnostics(),
            style=ft.ButtonStyle(bgcolor="#3B4FC8", color="#FFFFFF"),
        )

        self._self_test_btn = ft.FilledButton(
            "🧪 Autochequeo / Tests",
            icon=ft.Icons.FACT_CHECK,
            on_click=lambda e: self._run_self_tests(),
            style=ft.ButtonStyle(bgcolor="#2E7D32", color="#FFFFFF"),
        )

        diag_box = ft.Container(
            content=ft.ListView([self._diag_text], auto_scroll=True),
            bgcolor="#080816",
            border=ft.Border.all(1, "#1A1A2E"),
            border_radius=8,
            padding=ft.Padding.all(12),
            height=220,
        )

        self._tools_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Text("Índice de Aplicaciones (Búsqueda Profunda)", size=14, weight=ft.FontWeight.BOLD, color="#E0E0EE"),
                                            self._index_count_badge,
                                        ],
                                        spacing=10,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    ),
                                    ft.Text("Acelera la resolución de 'abre <app>' y permite búsqueda profunda en toda la PC.", size=11, color="#777799"),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            index_actions_row,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self._index_status_text,
                    ft.Divider(height=1, color="#1E1E38"),
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text("Salud del Sistema y Pruebas Automatizadas", size=14, weight=ft.FontWeight.BOLD, color="#E0E0EE"),
                                    ft.Text("Verificá el estado de la conexión a Ollama/Cloud, espacio en disco, logs y componentes.", size=11, color="#777799"),
                                ],
                                spacing=2,
                            ),
                            ft.Row([self._diag_btn, self._self_test_btn], spacing=8),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    diag_box,
                ],
                spacing=12,
            ),
            padding=ft.Padding.all(16),
            bgcolor=_CARD_BG,
            border=ft.Border.all(1, _BORDER_BG),
            border_radius=10,
        )

        # ── Columna de Contenido Principal ────────────────────────
        self._content_column = ft.Column(
            [
                title_header,
                self._category_chips,
                ft.Divider(height=1, color="#1A1A2E"),
                self._general_card,
                self._ai_card,
                self._audio_card,
                self._rvc_card,
                self._media_card,
                self._theme_card,
                self._background_card,
                self._security_card,
                self._memory_card,
                self._tools_card,
            ],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
        )

        self.content = ft.Container(content=self._content_column, padding=ft.Padding.all(24), expand=True)

    # ── Helpers de Interfaz y Filtros ──────────────────────────────

    def _build_badge(self, text: str, color: str = "#E0E0EE", bg: str = "#222244") -> ft.Container:
        return ft.Container(
            content=ft.Text(text, size=11, color=color),
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            bgcolor=bg,
            border_radius=12,
        )

    def _create_category_chip(self, category_key: str, label: str, is_active: bool) -> ft.Button:
        def _on_click(e):
            self._set_active_category(category_key)

        return ft.FilledButton(
            label,
            data=category_key,
            on_click=_on_click,
            style=ft.ButtonStyle(
                bgcolor="#3B4FC8" if is_active else "#1A1A36",
                color="#FFFFFF" if is_active else "#9090B8",
            ),
            height=32,
        )

    def _set_active_category(self, cat: str) -> None:
        self._active_category = cat

        # Actualizar visibilidad de cards
        self._general_card.visible = (cat in ("all", "general"))
        self._ai_card.visible = (cat in ("all", "ai"))
        self._audio_card.visible = (cat in ("all", "audio"))
        self._rvc_card.visible = (cat in ("all", "audio"))
        self._media_card.visible = (cat in ("all", "media", "audio"))
        self._theme_card.visible = (cat in ("all", "theme", "general"))
        self._background_card.visible = (cat in ("all", "background", "theme", "general"))
        self._security_card.visible = (cat in ("all", "security"))
        self._memory_card.visible = (cat in ("all", "memory"))
        self._tools_card.visible = (cat in ("all", "tools"))

        # Actualizar estilo de chips
        for btn in self._category_chips.controls:
            is_selected = (getattr(btn, "data", None) == cat)
            btn.style.bgcolor = "#3B4FC8" if is_selected else "#1A1A36"
            btn.style.color = "#FFFFFF" if is_selected else "#9090B8"

        try:
            self._category_chips.update()
            self._content_column.update()
        except Exception:
            pass

    # ── Manejadores de Apariencia, Idioma y Workspace ─────────────

    def _toggle_theme(self, e) -> None:
        new_theme = "dark" if e.control.value else "light"
        settings.set("APP_THEME", new_theme)
        if self.app_page:
            self.app_page.theme_mode = ft.ThemeMode.DARK if new_theme == "dark" else ft.ThemeMode.LIGHT
            self.app_page.update()

    def _on_language_changed(self, e) -> None:
        selected = e.data if getattr(e, "data", None) is not None else getattr(e.control, "value", None)
        if selected:
            settings.set("APP_LANGUAGE", selected)
            _logger.info("Configuración: APP_LANGUAGE cambiado a '%s'", selected)

    def _update_workspace_status_label(self, path_str: str) -> None:
        try:
            p = Path(path_str).expanduser().resolve()
            if p.exists() and p.is_dir():
                items = list(p.iterdir())
                self._workspace_status_text.value = f"✅ Ruta válida: {p} ({len(items)} elementos encontrados)"
                self._workspace_status_text.color = "#77DD77"
            elif p.exists() and not p.is_dir():
                self._workspace_status_text.value = f"⚠️ La ruta existe pero es un archivo, no un directorio: {p}"
                self._workspace_status_text.color = "#FFBB66"
            else:
                self._workspace_status_text.value = f"ℹ️ La carpeta no existe aún en disco. Se creará al guardar: {p}"
                self._workspace_status_text.color = "#B0B0D0"
        except Exception as ex:
            self._workspace_status_text.value = f"❌ Error analizando ruta: {ex}"
            self._workspace_status_text.color = "#FF6B8A"

    def _on_save_workspace(self, e=None) -> None:
        val = (self._workspace_field.value or "").strip()
        if not val:
            val = str(Path.home() / "Documents")
            self._workspace_field.value = val

        try:
            p = Path(val).expanduser().resolve()
            p.mkdir(parents=True, exist_ok=True)
            settings.set("WORKSPACE_PATH", str(p))
            self._update_workspace_status_label(str(p))
            user_memory.record_path(str(p), alias="workspace", category="folder")
            _logger.info("Configuración: WORKSPACE_PATH guardado como '%s'", p)
        except Exception as ex:
            self._workspace_status_text.value = f"❌ Error guardando workspace: {ex}"
            self._workspace_status_text.color = "#FF6B8A"

        try:
            self._workspace_field.update()
            self._workspace_status_text.update()
        except Exception:
            pass

    def _on_reset_workspace(self, e=None) -> None:
        default_p = str(Path.home() / "Documents")
        self._workspace_field.value = default_p
        self._on_save_workspace()

    # ── Manejadores de Seguridad y Confirmaciones ─────────────────

    def _on_security_toggle(self, key: str, val: bool) -> None:
        settings.set(key, "true" if val else "false")
        self._security_status_text.value = f"✅ Política '{key}' actualizada a: {'Activada' if val else 'Desactivada'}"
        try:
            self._security_status_text.update()
        except Exception:
            pass

    def _on_save_all_security(self, e=None) -> None:
        settings.set("CONFIRM_DESTRUCTIVE", "true" if self._confirm_destructive_switch.value else "false")
        settings.set("CONFIRM_SHUTDOWN", "true" if self._confirm_shutdown_switch.value else "false")
        settings.set("CONFIRMAR_CIERRE_APP", "true" if self._confirm_close_app_switch.value else "false")
        settings.set("ROUTER_FIRST", "true" if self._router_first_switch.value else "false")
        self._security_status_text.value = "✅ Todas las políticas de seguridad fueron guardadas y aplicadas."
        try:
            self._security_status_text.update()
        except Exception:
            pass

    # ── Manejadores de Memoria de Usuario ─────────────────────────

    def _refresh_memory_badges(self) -> None:
        try:
            self._mem_paths_badge.content.value = f"{len(user_memory.list_paths())} rutas"
            self._mem_progs_badge.content.value = f"{len(user_memory.list_programs())} programas"
            self._mem_facts_badge.content.value = f"{len(user_memory.list_facts())} hechos"
            cur_proj = user_memory.get_current_project()
            self._mem_proj_badge.content.value = f"Proyecto: {cur_proj.name if cur_proj else 'Ninguno'}"
            self._mem_paths_badge.update()
            self._mem_progs_badge.update()
            self._mem_facts_badge.update()
            self._mem_proj_badge.update()
        except Exception:
            pass

    def _on_export_memory(self, e=None) -> None:
        try:
            backup_dir = settings.data_dir / "memory"
            backup_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"user_memory_backup_{ts}.json"
            backup_path.write_text(user_memory.export_json(), encoding="utf-8")
            self._mem_status_text.value = f"✅ Respaldo de memoria exportado en: {backup_path.name}"
            self._mem_status_text.color = "#77DD77"
        except Exception as ex:
            self._mem_status_text.value = f"❌ Error exportando memoria: {ex}"
            self._mem_status_text.color = "#FF6B8A"
        try:
            self._mem_status_text.update()
        except Exception:
            pass

    def _on_clear_memory(self, e=None) -> None:
        try:
            user_memory.clear()
            self._refresh_memory_badges()
            self._mem_status_text.value = "🧹 Memoria de usuario reiniciada correctamente."
            self._mem_status_text.color = "#FFAA88"
        except Exception as ex:
            self._mem_status_text.value = f"❌ Error al limpiar memoria: {ex}"
            self._mem_status_text.color = "#FF6B8A"
        try:
            self._mem_status_text.update()
        except Exception:
            pass

    # ── Manejadores de Comprensión Fuzzy ──────────────────────────

    def _on_fuzzy_slider_changed(self, e) -> None:
        val = float(round(e.control.value, 2))
        settings.set("FUZZY_THRESHOLD", str(val))

    def _on_llm_fuzzy_changed(self, e) -> None:
        settings.set("USE_LLM_INTERPRETER", "true" if e.control.value else "false")

    # ── Manejadores de Voz RVC ───────────────────────────────────

    def _on_rvc_pitch_change(self, e) -> None:
        val = int(round(e.control.value))
        self._rvc_pitch_label.value = f"Tono (Pitch): {val:+d} semitonos"
        try:
            self._rvc_pitch_label.update()
        except Exception:
            pass

    def _on_rvc_index_change(self, e) -> None:
        val = float(round(e.control.value, 2))
        self._rvc_index_label.value = f"Fidelidad de Índice (Index Rate): {val:.2f}"
        try:
            self._rvc_index_label.update()
        except Exception:
            pass

    def _handle_test_voice(self, e=None) -> None:
        self._test_voice_btn.disabled = True
        self._rvc_status_text.value = "⏳ Sintetizando audio de prueba..."
        self._rvc_status_text.color = "#8888AA"
        try:
            self._test_voice_btn.update()
            self._rvc_status_text.update()
        except Exception:
            pass

        try:
            from voice.message_speaker import message_speaker
            message_speaker.stop()
        except Exception:
            pass

        # Aplicar temporalmente los valores actuales para la prueba
        chosen_prov = self._tts_provider_dropdown.value or "rvc"
        chosen_voice = self._rvc_voice_dropdown.value or "aura"
        chosen_base = self._rvc_base_dropdown.value or "edge"
        chosen_base_voice = self._rvc_base_voice_dropdown.value or "es-MX-DaliaNeural"
        chosen_pitch = int(round(self._rvc_pitch_slider.value))
        chosen_index = float(round(self._rvc_index_slider.value, 2))

        settings.set("TTS_PROVIDER", chosen_prov)
        settings.set("RVC_VOZ", chosen_voice)
        settings.set("RVC_TTS_BASE", chosen_base)
        settings.set("RVC_TTS_BASE_VOICE", chosen_base_voice)
        settings.set("RVC_PITCH", str(chosen_pitch))
        settings.set("RVC_INDEX_RATE", str(chosen_index))

        def _on_completed(result):
            if result.success:
                if result.is_fallback:
                    self._rvc_status_text.value = f"⚠️ Fallback ({result.provider_used}): {result.fallback_reason}"
                    self._rvc_status_text.color = "#FFBB66"
                else:
                    self._rvc_status_text.value = f"✅ Voz reproducida con éxito ({result.provider_used}, {result.duration_s:.1f}s)"
                    self._rvc_status_text.color = "#77DD77"
            else:
                self._rvc_status_text.value = f"❌ Error de voz: {result.error}"
                self._rvc_status_text.color = "#FF6B8A"

            self._test_voice_btn.disabled = False
            try:
                self._test_voice_btn.update()
                self._rvc_status_text.update()
            except Exception:
                pass

        def _on_fallback(reason: str):
            self._rvc_status_text.value = f"⚠️ voz RVC no disponible, usando voz base ({reason})"
            self._rvc_status_text.color = "#FFBB66"
            try:
                self._rvc_status_text.update()
            except Exception:
                pass

        tts_manager.speak(
            "Hola, soy Aura. Esta es una prueba de mi voz neuronal con el timbre configurado.",
            on_completed=_on_completed,
            on_fallback=_on_fallback,
            async_play=True,
        )

    def _handle_save_rvc(self, e=None) -> None:
        try:
            from voice.message_speaker import message_speaker
            message_speaker.stop()
        except Exception:
            pass
        settings.set("TTS_PROVIDER", self._tts_provider_dropdown.value or "rvc")
        settings.set("TTS_AUTO_PLAY", "true" if self._tts_autoplay_switch.value else "false")
        settings.set("RVC_VOZ", self._rvc_voice_dropdown.value or "aura")
        settings.set("RVC_TTS_BASE", self._rvc_base_dropdown.value or "edge")
        settings.set("RVC_TTS_BASE_VOICE", self._rvc_base_voice_dropdown.value or "es-MX-DaliaNeural")
        settings.set("RVC_PITCH", str(int(round(self._rvc_pitch_slider.value))))
        settings.set("RVC_INDEX_RATE", str(float(round(self._rvc_index_slider.value, 2))))
        self._rvc_status_text.value = "✅ Configuración de voz RVC guardada correctamente."
        self._rvc_status_text.color = "#77DD77"
        try:
            self._rvc_status_text.update()
        except Exception:
            pass

    def _handle_test_media_key(self, e=None) -> None:
        key = (self._media_key_field.value or "").strip()
        if not key:
            self._media_status_text.value = "⚠️ Ingresá una YouTube API key antes de probar."
            self._media_status_text.color = "#FFAA00"
            try:
                self._media_status_text.update()
            except Exception:
                pass
            return

        self._media_status_text.value = "⏳ Verificando YouTube API key..."
        self._media_status_text.color = "#4A9EFF"
        try:
            self._media_status_text.update()
        except Exception:
            pass

        def _worker():
            from aura.media.youtube_client import test_youtube_api_key
            ok, msg = test_youtube_api_key(key)
            self._media_status_text.value = msg
            self._media_status_text.color = "#77DD77" if ok else "#FF6666"
            try:
                self._media_status_text.update()
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _handle_save_media(self, e=None) -> None:
        key = (self._media_key_field.value or "").strip()
        svc = (self._media_svc_dropdown.value or "youtube_music").strip()

        settings.set("MEDIA_YT_API_KEY", key)
        settings.set("MEDIA_SERVICE", svc)

        has_key = bool(key)
        self._media_badge.content = ft.Text(
            "v2 AUTOPLAY ACTIVO" if has_key else "MODO v1 (BÚSQUEDA)",
            size=11,
            color="#77DD77" if has_key else "#B0B0D0",
        )
        self._media_badge.bgcolor = "#1A2A2A" if has_key else "#222244"

        self._media_status_text.value = "✅ Configuración de Media guardada correctamente."
        self._media_status_text.color = "#77DD77"
        try:
            self._media_badge.update()
            self._media_status_text.update()
        except Exception:
            pass

    # ── Restaurar Valores por Defecto ─────────────────────────────

    def _handle_restore_defaults(self, e=None) -> None:
        for k, v in DEFAULTS.items():
            if k not in ("FIRST_RUN",):
                settings.set(k, v)

        # Actualizar controles
        self._theme_switch.value = (DEFAULTS.get("APP_THEME", "dark") == "dark")
        self._language_dropdown.value = DEFAULTS.get("APP_LANGUAGE", "es")
        self._workspace_field.value = DEFAULTS.get("WORKSPACE_PATH", str(Path.home() / "Documents"))
        self._confirm_destructive_switch.value = (DEFAULTS.get("CONFIRM_DESTRUCTIVE", "true") == "true")
        self._confirm_shutdown_switch.value = (DEFAULTS.get("CONFIRM_SHUTDOWN", "true") == "true")
        self._confirm_close_app_switch.value = (DEFAULTS.get("CONFIRMAR_CIERRE_APP", "false") == "true")
        self._router_first_switch.value = (DEFAULTS.get("ROUTER_FIRST", "true") == "true")
        self._fuzzy_slider.value = float(DEFAULTS.get("FUZZY_THRESHOLD", "0.85"))
        self._use_llm_fuzzy_switch.value = (DEFAULTS.get("USE_LLM_INTERPRETER", "true") == "true")

        # RVC controles
        if hasattr(self, "_tts_provider_dropdown") and self._tts_provider_dropdown:
            self._tts_provider_dropdown.value = DEFAULTS.get("TTS_PROVIDER", "rvc")
        self._tts_autoplay_switch.value = (DEFAULTS.get("TTS_AUTO_PLAY", "true") == "true")
        self._rvc_voice_dropdown.value = DEFAULTS.get("RVC_VOZ", "aura")
        self._rvc_base_dropdown.value = DEFAULTS.get("RVC_TTS_BASE", "edge")
        self._rvc_base_voice_dropdown.value = DEFAULTS.get("RVC_TTS_BASE_VOICE", "es-MX-DaliaNeural")
        pitch_def = int(DEFAULTS.get("RVC_PITCH", "0"))
        idx_def = float(DEFAULTS.get("RVC_INDEX_RATE", "0.6"))
        self._rvc_pitch_slider.value = float(pitch_def)
        self._rvc_index_slider.value = idx_def
        self._rvc_pitch_label.value = f"Tono (Pitch): {pitch_def:+d} semitonos"
        self._rvc_index_label.value = f"Fidelidad de Índice (Index Rate): {idx_def:.2f}"

        # Media controles (Fase 79)
        if hasattr(self, "_media_key_field") and self._media_key_field:
            self._media_key_field.value = DEFAULTS.get("MEDIA_YT_API_KEY", "")
        if hasattr(self, "_media_svc_dropdown") and self._media_svc_dropdown:
            self._media_svc_dropdown.value = DEFAULTS.get("MEDIA_SERVICE", "youtube_music")
        if hasattr(self, "_media_badge") and self._media_badge:
            self._media_badge.content = ft.Text("MODO v1 (BÚSQUEDA)", size=11, color="#B0B0D0")
            self._media_badge.bgcolor = "#222244"
        if hasattr(self, "_media_status_text") and self._media_status_text:
            self._media_status_text.value = "Con API key, la música se reproduce automáticamente sin hacer click en el navegador."
            self._media_status_text.color = "#777799"

        self._update_workspace_status_label(self._workspace_field.value)
        self._diag_text.value = "🔄 Configuración restaurada a los valores predeterminados de fábrica."
        self._diag_text.color = "#88DD88"

        try:
            self._theme_switch.update()
            self._language_dropdown.update()
            self._workspace_field.update()
            self._workspace_status_text.update()
            self._confirm_destructive_switch.update()
            self._confirm_shutdown_switch.update()
            self._confirm_close_app_switch.update()
            self._router_first_switch.update()
            self._fuzzy_slider.update()
            self._use_llm_fuzzy_switch.update()
            self._tts_provider_dropdown.update()
            self._tts_autoplay_switch.update()
            self._rvc_voice_dropdown.update()
            self._rvc_base_dropdown.update()
            self._rvc_base_voice_dropdown.update()
            self._rvc_pitch_slider.update()
            self._rvc_index_slider.update()
            self._rvc_pitch_label.update()
            self._rvc_index_label.update()
            self._diag_text.update()
        except Exception:
            pass

    # ── Manejadores de Diagnóstico y Tests ────────────────────────

    def _handle_open_wizard(self) -> None:
        if self._on_open_wizard:
            self._on_open_wizard()

    def _run_system_diagnostics(self) -> None:
        self._diag_btn.disabled = True
        self._diag_text.value = "Ejecutando diagnóstico del sistema..."
        self._diag_text.color = "#8888AA"
        try:
            self._diag_btn.update()
            self._diag_text.update()
        except Exception:
            pass

        def _worker():
            try:
                res = run_diagnostics()
                self._diag_text.value = res.to_text()
                self._diag_text.color = "#88DD88" if res.overall_ok else "#FFBB66"
            except Exception as e:
                self._diag_text.value = f"Error en diagnóstico: {e}"
                self._diag_text.color = "#FF6B8A"
            finally:
                self._diag_btn.disabled = False
                try:
                    self._diag_btn.update()
                    self._diag_text.update()
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True).start()

    def _open_background_picker(self) -> None:
        """
        Abre el explorador de archivos para fondo de pantalla de forma perezosa
        (CAPA 1) con fallback transparente a Tkinter (CAPA 2).
        """
        open_file_picker_dialog(
            on_result_callback=self._on_bg_file_picked,
            page=self.app_page,
            dialog_title="Seleccionar imagen o GIF para fondo de pantalla",
            allowed_extensions=["png", "jpg", "jpeg", "gif", "webp", "bmp"],
            filetypes=(
                ("Imágenes", "*.png *.jpg *.jpeg *.gif *.webp *.bmp"),
                ("Todos los archivos", "*.*"),
            ),
        )

    def _on_bg_file_picked(self, e: Any) -> None:
        """Callback al seleccionar un archivo en el explorador nativo."""
        if not e:
            return
        files = getattr(e, "files", None)
        if not files or len(files) == 0:
            return
        file_obj = files[0]
        file_path = getattr(file_obj, "path", None) if not isinstance(file_obj, str) else file_obj
        if not file_path:
            return
        try:
            meta = normalize_background_image(file_path)
            self._selected_bg_path = meta["target_file"]
            self._selected_bg_meta = meta

            thumb_file = meta.get("preview_file") or meta.get("thumbnail_file")
            if not thumb_file or not Path(thumb_file).exists():
                thumb_file = background_manager.current_thumbnail_path

            self._bg_preview_img.src = thumb_file if (thumb_file and Path(thumb_file).exists()) else meta["target_file"]
            self._bg_preview_img.visible = True
            self._bg_preview_placeholder.visible = False

            if meta.get("is_gif"):
                fc = meta.get("frames_count", 1)
                fps_val = meta.get("fps", 0.0)
                self._bg_status_indicator.value = f"GIF animado detectado ({fc} frames, {fps_val} fps)"
            else:
                w = meta.get("width", "?")
                h = meta.get("height", "?")
                self._bg_status_indicator.value = f"Imagen estática ({w}x{h})"

            self._bg_action_status.value = f"✅ Normalizado: {meta['original']}"
            self._bg_action_status.color = "#77DD77"

            try:
                self._bg_preview_box.update()
                self._bg_status_indicator.update()
                self._bg_action_status.update()
            except Exception:
                pass
        except Exception as ex:
            _logger.warning("Error normalizando fondo seleccionado: %s", ex)
            self._bg_action_status.value = f"❌ Error: {ex}"
            self._bg_action_status.color = "#FF6B8A"
            try:
                self._bg_action_status.update()
            except Exception:
                pass

    def _show_contrast_snackbar(self, message: str) -> None:
        """Muestra sugerencia no intrusiva de contraste para lectura óptima."""
        if not self.app_page:
            return
        try:
            sb = ft.SnackBar(
                content=ft.Text(f"💡 {message}", color="#FFFFFF", size=13, weight=ft.FontWeight.W_500),
                bgcolor="#3A3A6A",
            )
            self.app_page.overlay.append(sb)
            sb.open = True
            self.app_page.update()
        except Exception as ex:
            _logger.debug("Error mostrando snackbar de contraste: %s", ex)

    def apply_theme(self, tokens: ThemeTokens) -> None:
        """Aplica los tokens de tema visual a las tarjetas y fondos de la página de configuración."""
        if background_manager.is_active:
            self.bgcolor = "transparent"
        else:
            self.bgcolor = tokens.app_bg

        cards = [
            getattr(self, "_general_card", None),
            getattr(self, "_ai_card", None),
            getattr(self, "_audio_card", None),
            getattr(self, "_rvc_card", None),
            getattr(self, "_media_card", None),
            getattr(self, "_theme_card", None),
            getattr(self, "_background_card", None),
            getattr(self, "_security_card", None),
            getattr(self, "_memory_card", None),
            getattr(self, "_tools_card", None),
        ]
        for c in cards:
            if c:
                c.bgcolor = tokens.card_bg
                c.border = ft.Border.all(1, tokens.border_color)

        if hasattr(self, "_theme_preview") and self._theme_preview:
            self._theme_preview.update_tokens(tokens)

        try:
            self.update()
        except Exception:
            pass



    def _run_self_tests(self) -> None:
        self._self_test_btn.disabled = True
        self._diag_text.value = "Ejecutando batería de pruebas y autochequeo de componentes..."
        self._diag_text.color = "#8888AA"
        try:
            self._self_test_btn.update()
            self._diag_text.update()
        except Exception:
            pass

        def _worker():
            try:
                items = run_self_test()
                self._diag_text.value = self_test_to_text(items)
                passed = all(it.passed for it in items)
                self._diag_text.color = "#88DD88" if passed else "#FFBB66"
            except Exception as e:
                self._diag_text.value = f"Error en autochequeo: {e}"
                self._diag_text.color = "#FF6B8A"
            finally:
                self._self_test_btn.disabled = False
                try:
                    self._self_test_btn.update()
                    self._diag_text.update()
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True).start()

    def on_enter(self) -> None:
        """Actualiza badges y estados al abrir la pantalla de Configuración."""
        super().on_enter()
        self._refresh_index_badge()
        self._refresh_memory_badges()
        self._refresh_background_card()
        if hasattr(self, "_workspace_field") and self._workspace_field:
            self._update_workspace_status_label(self._workspace_field.value or "")

        if hasattr(self, "_rvc_voice_dropdown") and self._rvc_voice_dropdown:
            try:
                voices = get_available_rvc_voices()
                opts = [ft.dropdown.Option(key=v, text=f"Voz: {v}") for v in sorted(voices.keys())]
                if opts:
                    self._rvc_voice_dropdown.options = opts
                    if self._rvc_voice_dropdown.value not in [o.key for o in opts]:
                        self._rvc_voice_dropdown.value = opts[0].key
                    self._rvc_voice_dropdown.update()
            except Exception:
                pass

        if hasattr(self, "_rvc_device_badge") and self._rvc_device_badge:
            try:
                dev_info = rvc_converter.device_info
                self._rvc_device_badge.content.value = f"⚙️ Hardware: {dev_info}"
                self._rvc_device_badge.content.color = "#77DD77" if "GPU" in dev_info else "#B0B0D0"
                self._rvc_device_badge.bgcolor = "#1A2A2A" if "GPU" in dev_info else "#222244"
                self._rvc_device_badge.update()
            except Exception:
                pass

    def _refresh_background_card(self) -> None:
        try:
            bg_path = background_manager.current_image_path
            meta = background_manager.metadata or {}
            has_bg = bool(bg_path and Path(bg_path).exists())
            thumb_path = background_manager.current_thumbnail_path
            has_thumb = bool(thumb_path and Path(thumb_path).exists())

            if hasattr(self, "_bg_preview_img") and self._bg_preview_img:
                self._bg_preview_img.src = thumb_path if has_thumb else (bg_path if has_bg else "")
                self._bg_preview_img.visible = bool(has_thumb or has_bg)
            if hasattr(self, "_bg_preview_placeholder") and self._bg_preview_placeholder:
                self._bg_preview_placeholder.visible = not bool(has_thumb or has_bg)
            if hasattr(self, "_bg_status_indicator") and self._bg_status_indicator:
                if not has_bg:
                    self._bg_status_indicator.value = "Ningún fondo seleccionado (usa el tema de color)"
                elif meta.get("is_gif"):
                    fc = meta.get("frames_count", 1)
                    fps_val = meta.get("fps", 0.0)
                    self._bg_status_indicator.value = f"GIF animado detectado ({fc} frames, {fps_val} fps)"
                else:
                    w = meta.get("width", "?")
                    h = meta.get("height", "?")
                    self._bg_status_indicator.value = f"Imagen estática ({w}x{h})"
            if hasattr(self, "_bg_active_badge") and self._bg_active_badge:
                self._bg_active_badge.content.value = "FONDO: ACTIVO" if background_manager.is_active else "FONDO: INACTIVO"
            if hasattr(self, "_bg_preview_box") and self._bg_preview_box:
                self._bg_preview_box.update()
            if hasattr(self, "_bg_status_indicator") and self._bg_status_indicator:
                self._bg_status_indicator.update()
            if hasattr(self, "_bg_active_badge") and self._bg_active_badge:
                self._bg_active_badge.update()
        except Exception:
            pass

    def _refresh_index_badge(self) -> None:
        try:
            if hasattr(self, "_index_count_badge") and self._index_count_badge:
                count = app_index_manager.count()
                self._index_count_badge.content.value = f"{count} apps indexadas"
                self._index_count_badge.update()
        except Exception:
            pass

    def _handle_index_btn_click(self) -> None:
        if getattr(self, "_is_indexing", False):
            self._cancel_app_indexing()
        else:
            self._run_app_indexing()

    def _cancel_app_indexing(self) -> None:
        if getattr(self, "_is_indexing", False) and hasattr(self, "_indexing_cancel_event"):
            self._indexing_cancel_event.set()
            self._index_status_text.value = "⏳ Cancelando indexado de aplicaciones..."
            self._index_status_text.color = "#FFBB66"
            self._cancel_index_btn.disabled = True
            try:
                self._index_status_text.update()
                self._cancel_index_btn.update()
            except Exception:
                pass

    def _run_app_indexing(self) -> None:
        if getattr(self, "_is_indexing", False):
            return

        self._is_indexing = True
        self._indexing_cancel_event = threading.Event()

        self._index_btn.disabled = True
        self._index_btn.text = "⏳ Indexando..."
        self._cancel_index_btn.visible = True
        self._cancel_index_btn.disabled = False
        self._index_status_text.value = "⏳ Indexando... 0 apps"
        self._index_status_text.color = "#8888AA"
        try:
            self._index_btn.update()
            self._cancel_index_btn.update()
            self._index_status_text.update()
        except Exception:
            pass

        def _worker():
            try:
                def _progress_cb(recorridas: int, encontradas: int, carpeta_actual: str = ""):
                    self._index_status_text.value = f"⏳ Indexando... {encontradas} apps"
                    self._index_status_text.color = "#8888AA"
                    try:
                        self._index_status_text.update()
                    except Exception:
                        pass

                apps = app_index_manager.index_all_apps(
                    progress_callback=_progress_cb,
                    cancel_event=self._indexing_cancel_event,
                )

                if self._indexing_cancel_event.is_set():
                    current_count = app_index_manager.count()
                    self._index_count_badge.content.value = f"{current_count} apps indexadas"
                    self._index_status_text.value = "⚠️ Indexado cancelado por el usuario. El índice anterior se mantiene intacto."
                    self._index_status_text.color = "#FFBB66"
                else:
                    count = len(apps) if isinstance(apps, list) else int(apps)
                    self._index_count_badge.content.value = f"{count} apps indexadas"
                    self._index_status_text.value = f"✅ Índice completado: {count} aplicaciones disponibles para resolución instantánea."
                    self._index_status_text.color = "#77DD77"
            except Exception as ex:
                _logger.error("Error al indexar aplicaciones: %s", ex, exc_info=True)
                self._index_status_text.value = f"❌ Error al indexar aplicaciones: {ex}"
                self._index_status_text.color = "#FF6B8A"
            finally:
                self._is_indexing = False
                self._index_btn.disabled = False
                self._index_btn.text = "🔍 Indexar mis apps ahora"
                self._cancel_index_btn.visible = False
                try:
                    self._index_btn.update()
                    self._cancel_index_btn.update()
                    self._index_count_badge.update()
                    self._index_status_text.update()
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True).start()

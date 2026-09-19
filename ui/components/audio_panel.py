"""
AURA — Panel de Configuración y Control de Audio (Flet)

Componente visual para selección de dispositivos de entrada y salida,
calibración de nivel RMS, prueba de sonido (beep 440 Hz) y botón
de grabación con detección de actividad de voz (VAD) y auto-envío al chat.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional
import flet as ft

from config.settings import settings
from utils.logger import get_logger
from voice.audio_manager import (
    list_audio_devices,
    set_default_devices,
    get_default_devices,
    play_test_beep,
    measure_mic_rms,
    transcribe_audio_data,
    VoiceRecorder,
)
from voice.stt_factory import (
    get_whisper_device_and_compute,
    WHISPER_MODEL_SIZES,
)

_logger = get_logger("aura.ui.audio_panel")

_BG_PANEL      = "#0E0E22"
_BORDER_PANEL  = "#1C1C38"
_BTN_TALK_IDLE = "#3B4FC8"
_BTN_TALK_REC  = "#A82020"
_BTN_TALK_PROC = "#B45309"
_TEXT_MUTED    = "#777799"
_TEXT_BRIGHT   = "#E0E0FF"


class AudioPanel(ft.Container):
    """
    Panel de control de audio en Flet.

    Permite:
      - Seleccionar dispositivos de entrada y salida mediante Dropdowns.
      - Refrescar la lista de dispositivos de audio.
      - Probar micrófono (mide RMS durante 2 segundos y muestra el valor).
      - Probar salida de audio con tono de 440 Hz (beep).
      - Barra de nivel en tiempo real (ProgressBar).
      - Botón 'Hablar / Escuchando' con corte automático por silencio y auto-envío.
    """

    def __init__(
        self,
        page: ft.Page,
        on_send_message: Optional[Callable[[str], None]] = None,
        on_status_message: Optional[Callable[[str], None]] = None,
        on_error_message: Optional[Callable[[str], None]] = None,
        visible: bool = True,
        **kwargs,
    ):
        self.app_page = page
        self._on_send_message = on_send_message
        self._on_status_message = on_status_message
        self._on_error_message = on_error_message

        self._recorder: Optional[VoiceRecorder] = None
        self._last_level_update: float = 0.0

        super().__init__(visible=visible, **kwargs)
        self._build_ui()
        self._load_devices()
        try:
            from voice.providers.whisper_stt_provider import whisper_stt_provider
            whisper_stt_provider.set_progress_callback(self._on_whisper_progress)
        except Exception:
            pass

    def _build_ui(self) -> None:
        self.bgcolor = _BG_PANEL
        self.border = ft.Border.all(1, _BORDER_PANEL)
        self.border_radius = 8
        self.padding = ft.Padding.all(12)

        # ── Cabecera ──────────────────────────────────────────────
        title_row = ft.Row(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SETTINGS_VOICE, size=16, color="#A78BFA"),
                        ft.Text("Audio & Dispositivos de Voz", size=12, weight=ft.FontWeight.BOLD, color=_TEXT_BRIGHT),
                    ],
                    spacing=6,
                ),
                self._build_auto_send_switch(),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # ── Dropdowns de Entrada y Salida ─────────────────────────
        self._input_dropdown = ft.Dropdown(
            label="Entrada (Micrófono)",
            text_size=11,
            label_style=ft.TextStyle(size=11, color=_TEXT_MUTED),
            border_color="#242448",
            bgcolor="#13132B",
            color=_TEXT_BRIGHT,
            expand=True,
            on_select=self._on_device_changed,
        )

        self._output_dropdown = ft.Dropdown(
            label="Salida (Altavoces)",
            text_size=11,
            label_style=ft.TextStyle(size=11, color=_TEXT_MUTED),
            border_color="#242448",
            bgcolor="#13132B",
            color=_TEXT_BRIGHT,
            expand=True,
            on_select=self._on_device_changed,
        )

        self._refresh_btn = ft.IconButton(
            icon=ft.Icons.REFRESH,
            icon_color="#A0A0C0",
            icon_size=18,
            tooltip="Refrescar dispositivos de audio",
            on_click=lambda e: self._load_devices(),
        )

        devices_row = ft.Row(
            [self._input_dropdown, self._output_dropdown, self._refresh_btn],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # ── Fila de Configuración STT (Fase 74) ──────────────────────
        curr_provider = settings.get("STT_PROVIDER", "whisper").lower().strip()
        curr_model = settings.get("WHISPER_MODEL", "small").strip()
        device_name, compute_name = get_whisper_device_and_compute()

        self._stt_provider_dropdown = ft.Dropdown(
            label="Proveedor STT",
            text_size=11,
            label_style=ft.TextStyle(size=11, color=_TEXT_MUTED),
            border_color="#242448",
            bgcolor="#13132B",
            color=_TEXT_BRIGHT,
            width=175,
            value=curr_provider if curr_provider in ("whisper", "google") else "whisper",
            options=[
                ft.dropdown.Option("whisper", "Whisper (Local)"),
                ft.dropdown.Option("google", "Google Web Speech"),
            ],
            on_select=self._on_stt_provider_changed,
        )

        model_options = [
            ft.dropdown.Option("tiny", f"tiny ({WHISPER_MODEL_SIZES['tiny']})"),
            ft.dropdown.Option("base", f"base ({WHISPER_MODEL_SIZES['base']})"),
            ft.dropdown.Option("small", f"small ({WHISPER_MODEL_SIZES['small']})"),
            ft.dropdown.Option("medium", f"medium ({WHISPER_MODEL_SIZES['medium']})"),
            ft.dropdown.Option("large-v3", f"large-v3 ({WHISPER_MODEL_SIZES['large-v3']})"),
        ]
        self._whisper_model_dropdown = ft.Dropdown(
            label="Modelo Whisper",
            text_size=11,
            label_style=ft.TextStyle(size=11, color=_TEXT_MUTED),
            border_color="#242448",
            bgcolor="#13132B",
            color=_TEXT_BRIGHT,
            width=205,
            value=curr_model if curr_model in WHISPER_MODEL_SIZES else "small",
            options=model_options,
            visible=(curr_provider == "whisper"),
            on_select=self._on_whisper_model_changed,
        )

        badge_color = "#34D399" if device_name == "cuda" else "#A78BFA"
        gpu_icon = ft.Icons.MEMORY if device_name == "cuda" else ft.Icons.COMPUTER
        self._compute_badge = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(gpu_icon, size=13, color=badge_color),
                    ft.Text(f"{device_name.upper()} ({compute_name})", size=10, weight=ft.FontWeight.BOLD, color=badge_color),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor="#161633",
            border=ft.Border.all(1, "#282850"),
            border_radius=6,
            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
            tooltip=f"Dispositivo y precisión para faster-whisper: {device_name.upper()} ({compute_name})",
        )

        self._test_stt_btn = ft.OutlinedButton(
            "🧪 Probar STT (3s)",
            on_click=lambda e: self._on_test_stt_click(),
            style=ft.ButtonStyle(
                color="#34D399",
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )

        stt_row = ft.Row(
            [
                self._stt_provider_dropdown,
                self._whisper_model_dropdown,
                self._compute_badge,
                self._test_stt_btn,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # ── Botones de Prueba y Control ───────────────────────────
        self._test_mic_btn = ft.OutlinedButton(
            "🎙 Probar Mic (2s)",
            on_click=lambda e: self._on_test_mic_click(),
            style=ft.ButtonStyle(
                color="#88AAFF",
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )

        self._test_out_btn = ft.OutlinedButton(
            "🔊 Probar Salida (Beep)",
            on_click=lambda e: self._on_test_out_click(),
            style=ft.ButtonStyle(
                color="#88AAFF",
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )

        self._talk_btn = ft.FilledButton(
            "🎤 Hablar",
            on_click=lambda e: self.toggle_talk(),
            style=ft.ButtonStyle(
                bgcolor=_BTN_TALK_IDLE,
                color="#FFFFFF",
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
            height=36,
        )

        self._status_label = ft.Text(
            "Listo para escuchar",
            size=11,
            color=_TEXT_MUTED,
            expand=True,
            text_align=ft.TextAlign.RIGHT,
        )

        controls_row = ft.Row(
            [self._talk_btn, self._test_mic_btn, self._test_out_btn, self._status_label],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # ── Barra de nivel en vivo ────────────────────────────────
        self._level_bar = ft.ProgressBar(
            value=0.0,
            height=6,
            bgcolor="#181832",
            color="#4CAF50",
        )

        self.content = ft.Column(
            [
                title_row,
                devices_row,
                stt_row,
                controls_row,
                self._level_bar,
            ],
            spacing=8,
        )

    def _build_auto_send_switch(self) -> ft.Control:
        auto_send_val = settings.get_bool("VOICE_AUTO_SEND", fallback=True)
        self._auto_send_switch = ft.Switch(
            label="Auto-envío por silencio",
            label_text_style=ft.TextStyle(size=11, color=_TEXT_MUTED),
            value=auto_send_val,
            active_color="#4CAF50",
            on_change=self._on_auto_send_toggle,
        )
        return self._auto_send_switch

    def _on_auto_send_toggle(self, e) -> None:
        val = bool(e.control.value)
        settings.set("VOICE_AUTO_SEND", "true" if val else "false")
        _logger.info(f"AudioPanel: VOICE_AUTO_SEND={val}")

    # ──────────────────────────────────────────────────────────────
    # Carga y Selección de Dispositivos
    # ──────────────────────────────────────────────────────────────

    def _load_devices(self) -> None:
        """Carga los dispositivos de entrada y salida disponibles."""
        try:
            dev_list = list_audio_devices()
            saved_in, saved_out = get_default_devices()

            # Llenar Dropdown de entradas
            input_options = []
            seen_in = set()
            for d in dev_list.inputs:
                name = d["name"]
                if name not in seen_in:
                    seen_in.add(name)
                    input_options.append(ft.dropdown.Option(name))

            self._input_dropdown.options = input_options
            if saved_in and any(o.key == saved_in for o in input_options):
                self._input_dropdown.value = saved_in
            elif input_options:
                self._input_dropdown.value = input_options[0].key

            # Llenar Dropdown de salidas
            output_options = []
            seen_out = set()
            for d in dev_list.outputs:
                name = d["name"]
                if name not in seen_out:
                    seen_out.add(name)
                    output_options.append(ft.dropdown.Option(name))

            self._output_dropdown.options = output_options
            if saved_out and any(o.key == saved_out for o in output_options):
                self._output_dropdown.value = saved_out
            elif output_options:
                self._output_dropdown.value = output_options[0].key

            # Persistir defaults detectados
            set_default_devices(
                input_name=self._input_dropdown.value,
                output_name=self._output_dropdown.value,
            )

            try:
                self._input_dropdown.update()
                self._output_dropdown.update()
            except Exception:
                pass

            _logger.info(f"AudioPanel: Dispositivos cargados. In={self._input_dropdown.value}, Out={self._output_dropdown.value}")
        except Exception as e:
            _logger.error(f"Error cargando dispositivos de audio: {e}", exc_info=True)

    def _on_device_changed(self, e) -> None:
        """Callback al cambiar cualquier dropdown."""
        valor = e.data if getattr(e, "data", None) is not None else getattr(getattr(e, "control", None), "value", None)
        ctrl = getattr(e, "control", None)
        if ctrl == self._input_dropdown and valor:
            self._input_dropdown.value = valor
        elif ctrl == self._output_dropdown and valor:
            self._output_dropdown.value = valor

        in_name = self._input_dropdown.value
        out_name = self._output_dropdown.value
        set_default_devices(input_name=in_name, output_name=out_name)
        self._status_label.value = f"Dispositivo actualizado: {in_name or out_name}"
        try:
            self._status_label.update()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────
    # Prueba de Micrófono (RMS 2s)
    # ──────────────────────────────────────────────────────────────

    def _on_test_mic_click(self) -> None:
        self._test_mic_btn.disabled = True
        self._status_label.value = "🎙 Grabando 2 segundos... hablá al micrófono."
        self._status_label.color = "#FBBF24"
        try:
            self._test_mic_btn.update()
            self._status_label.update()
        except Exception:
            pass

        def _worker():
            try:
                in_device = self._input_dropdown.value
                rms = measure_mic_rms(
                    device=in_device,
                    duration_s=2.0,
                    callback_level=self._on_live_level,
                )
                threshold = settings.get_float("VOICE_SILENCE_RMS", 0.02)
                ok = (rms >= threshold)
                msg = f"RMS medido: {rms:.4f} (Umbral: {threshold:.3f}) - {'✓ Nivel adecuado' if ok else '⚠ Nivel bajo'}"
                self._status_label.value = msg
                self._status_label.color = "#4CAF50" if ok else "#FBBF24"
                _logger.info(f"AudioPanel: Prueba de micrófono completada: {msg}")
            except Exception as e:
                self._status_label.value = f"Error probando micrófono: {e}"
                self._status_label.color = "#F87171"
                _logger.error(f"Error en prueba de micrófono: {e}", exc_info=True)
            finally:
                self._test_mic_btn.disabled = False
                self._level_bar.value = 0.0
                try:
                    self._test_mic_btn.update()
                    self._status_label.update()
                    self._level_bar.update()
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True, name="aura-test-mic").start()

    # ──────────────────────────────────────────────────────────────
    # Prueba de Salida (Beep 440 Hz)
    # ──────────────────────────────────────────────────────────────

    def _on_test_out_click(self) -> None:
        self._test_out_btn.disabled = True
        self._status_label.value = "🔊 Reproduciendo beep de 440 Hz..."
        self._status_label.color = "#A78BFA"
        try:
            self._test_out_btn.update()
            self._status_label.update()
        except Exception:
            pass

        def _worker():
            try:
                out_device = self._output_dropdown.value
                ok = play_test_beep(device=out_device, duration_s=0.5, freq=440.0)
                if ok:
                    self._status_label.value = "✓ Beep 440 Hz emitido correctamente."
                    self._status_label.color = "#4CAF50"
                else:
                    self._status_label.value = "❌ Error reproduciendo beep en salida."
                    self._status_label.color = "#F87171"
            except Exception as e:
                self._status_label.value = f"Error en salida: {e}"
                self._status_label.color = "#F87171"
            finally:
                self._test_out_btn.disabled = False
                try:
                    self._test_out_btn.update()
                    self._status_label.update()
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True, name="aura-test-out").start()

    # ──────────────────────────────────────────────────────────────
    # Configuración y Pruebas STT (Fase 74)
    # ──────────────────────────────────────────────────────────────

    def _on_whisper_progress(self, msg: str) -> None:
        """Callback invocado durante la descarga o carga del modelo Whisper."""
        self._status_label.value = msg
        self._status_label.color = "#FBBF24"
        try:
            self._status_label.update()
        except Exception:
            pass

    def _on_stt_provider_changed(self, e) -> None:
        val = str(e.control.value).strip().lower()
        settings.set("STT_PROVIDER", val)
        self._whisper_model_dropdown.visible = (val == "whisper")
        _logger.info(f"AudioPanel: STT_PROVIDER cambiado a '{val}'")
        try:
            self._whisper_model_dropdown.update()
            self.update()
        except Exception:
            pass

    def _on_whisper_model_changed(self, e) -> None:
        val = str(e.control.value).strip().lower()
        settings.set("WHISPER_MODEL", val)
        _logger.info(f"AudioPanel: WHISPER_MODEL cambiado a '{val}'")
        try:
            from voice.providers.whisper_stt_provider import whisper_stt_provider
            whisper_stt_provider._model_instance = None
            whisper_stt_provider._loaded_key = None
        except Exception:
            pass

    def _on_test_stt_click(self) -> None:
        """Graba 3 segundos, transcribe con el provider activo y muestra texto + tiempo en ms."""
        if self._recorder and self._recorder.is_recording:
            return

        self._test_stt_btn.disabled = True
        self._test_stt_btn.text = "🎙 3s..."
        self._status_label.value = "🎙 Grabando 3s para prueba STT..."
        self._status_label.color = "#FBBF24"
        self._level_bar.value = 0.0
        try:
            self._test_stt_btn.update()
            self._status_label.update()
            self._level_bar.update()
        except Exception:
            pass

        def _worker():
            try:
                import sounddevice as sd
                dev_list = list_audio_devices()
                saved_in, _ = get_default_devices()
                device_idx = None
                if saved_in:
                    for d in dev_list.inputs:
                        if d["name"] == saved_in:
                            device_idx = d["index"]
                            break

                duration = 3.0
                sample_rate = 16000
                recording = sd.rec(
                    int(duration * sample_rate),
                    samplerate=sample_rate,
                    channels=1,
                    dtype="float32",
                    device=device_idx,
                )

                # Simular espera durante los 3 segundos
                steps = 15
                for _ in range(steps):
                    time.sleep(duration / steps)
                sd.wait()

                self._status_label.value = "⏳ Transcribiendo..."
                try:
                    self._status_label.update()
                except Exception:
                    pass

                start_t = time.monotonic()
                stt_res = transcribe_audio_data(recording, sample_rate=sample_rate)
                total_ms = int((time.monotonic() - start_t) * 1000)

                active_provider = settings.get("STT_PROVIDER", "whisper")
                text = stt_res.text.strip() if stt_res.success else ""
                ms = stt_res.duration_ms or total_ms

                if text:
                    preview = text[:35] + "…" if len(text) > 35 else text
                    msg = f"✓ [{active_provider}] {preview} ({ms}ms)"
                    self._status_label.value = msg
                    self._status_label.color = "#4CAF50"
                    if self._on_status_message:
                        self._on_status_message(f"🧪 STT ({active_provider}): '{text}' ({ms}ms)")
                else:
                    err = stt_res.error or "Sin palabras detectadas (silencio)"
                    msg = f"[{active_provider}] {err} ({ms}ms)"
                    self._status_label.value = msg
                    self._status_label.color = "#F87171"
                    if self._on_status_message:
                        self._on_status_message(f"🧪 STT ({active_provider}): {err} ({ms}ms)")

            except Exception as e:
                _logger.error(f"Error en prueba STT: {e}", exc_info=True)
                self._status_label.value = f"Error prueba STT: {e}"
                self._status_label.color = "#F87171"
            finally:
                self._test_stt_btn.disabled = False
                self._test_stt_btn.text = "🧪 Probar STT (3s)"
                self._level_bar.value = 0.0
                try:
                    self._test_stt_btn.update()
                    self._status_label.update()
                    self._level_bar.update()
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True, name="aura-test-stt").start()

    # ──────────────────────────────────────────────────────────────
    # Grabación con VAD por RMS y Auto-Envío
    # ──────────────────────────────────────────────────────────────

    def toggle_talk(self) -> None:
        """Inicia o detiene la captura de voz con VAD."""
        if self._recorder and self._recorder.is_recording:
            # Detener manualmente
            self._recorder.stop()
            self._talk_btn.text = "⏳ Procesando..."
            self._talk_btn.style.bgcolor = _BTN_TALK_PROC
            try:
                self._talk_btn.update()
            except Exception:
                pass
            return

        # Iniciar nueva grabación
        in_device = self._input_dropdown.value
        silence_rms = settings.get_float("VOICE_SILENCE_RMS", 0.02)
        silence_s = settings.get_float("VOICE_SILENCE_SECONDS", 1.5)
        wait_speech_s = settings.get_float("VOICE_WAIT_SPEECH_SECONDS", 5.0)

        self._recorder = VoiceRecorder(
            device=in_device,
            sample_rate=16000,
            silence_rms=silence_rms,
            silence_seconds=silence_s,
            wait_speech_seconds=wait_speech_s,
            on_level=self._on_live_level,
            on_result=self._on_recorder_result,
            on_cancel=self._on_recorder_cancel,
        )

        started = self._recorder.start()
        if started:
            self._talk_btn.text = "🔴 Escuchando..."
            self._talk_btn.style.bgcolor = _BTN_TALK_REC
            self._status_label.value = f"Escuchando (corta tras {silence_s}s de silencio)..."
            self._status_label.color = "#F87171"
            try:
                self._talk_btn.update()
                self._status_label.update()
            except Exception:
                pass

            if self._on_status_message:
                self._on_status_message("🎤 Escuchando... hablá ahora.")
        else:
            self._status_label.value = "No se pudo iniciar la grabación."
            self._status_label.color = "#F87171"
            try:
                self._status_label.update()
            except Exception:
                pass

    def _on_live_level(self, rms: float) -> None:
        """Actualización throttled de la barra de nivel (máx ~15 fps para no saturar Flet)."""
        now = time.monotonic()
        if (now - self._last_level_update) < 0.07:
            return
        self._last_level_update = now

        # Normalizar nivel para barra de progreso: 0.02 es audible, 0.15 es volumen alto
        norm_val = min(1.0, max(0.0, rms * 15.0))
        self._level_bar.value = norm_val
        try:
            self._level_bar.update()
        except Exception:
            pass

    def _on_recorder_result(self, audio, sample_rate: int) -> None:
        """Llamado cuando el VAD corta por silencio y entrega el buffer de audio."""
        _logger.info(f"AudioPanel: VAD finalizado con éxito ({len(audio)/sample_rate:.2f}s). Iniciando STT...")

        self._talk_btn.text = "⏳ Transcribiendo..."
        self._talk_btn.style.bgcolor = _BTN_TALK_PROC
        self._status_label.value = "Transcribiendo audio..."
        self._status_label.color = "#FBBF24"
        self._level_bar.value = 0.0
        try:
            self._talk_btn.update()
            self._status_label.update()
            self._level_bar.update()
        except Exception:
            pass

        def _transcribe_worker():
            try:
                stt_res = transcribe_audio_data(audio, sample_rate=sample_rate, language="es-AR")
                text = stt_res.text.strip() if stt_res.success else ""

                if not text:
                    _logger.warning("AudioPanel: STT retornó texto vacío o no entendible. No se envía al chat.")
                    self._talk_btn.text = "🎤 Hablar"
                    self._talk_btn.style.bgcolor = _BTN_TALK_IDLE
                    self._status_label.value = "No se detectaron palabras en el audio."
                    self._status_label.color = "#F87171"
                    try:
                        self._talk_btn.update()
                        self._status_label.update()
                    except Exception:
                        pass

                    if self._on_status_message:
                        err_msg = stt_res.error or "No se entendió el audio grabado."
                        self._on_status_message(f"🎤 {err_msg}")
                    return

                # Texto reconocido correctamente
                _logger.info(f"AudioPanel: Transcripción obtenida: '{text}'")
                self._talk_btn.text = "🎤 Hablar"
                self._talk_btn.style.bgcolor = _BTN_TALK_IDLE
                preview = text[:30] + "…" if len(text) > 30 else text
                self._status_label.value = f"✓ Reconocido: {preview}"
                self._status_label.color = "#4CAF50"
                try:
                    self._talk_btn.update()
                    self._status_label.update()
                except Exception:
                    pass

                # Auto-envío por la misma ruta que un mensaje escrito
                auto_send = settings.get_bool("VOICE_AUTO_SEND", fallback=True)
                if auto_send and self._on_send_message:
                    _logger.info("AudioPanel: Auto-envío activo. Enviando mensaje al chat...")
                    self._on_send_message(text)
                elif not auto_send and self._on_status_message:
                    self._on_status_message(f"🎤 Transcripción: {text}")

            except Exception as e:
                _logger.error(f"Error en worker de transcripción: {e}", exc_info=True)
                self._talk_btn.text = "🎤 Hablar"
                self._talk_btn.style.bgcolor = _BTN_TALK_IDLE
                self._status_label.value = f"Error STT: {e}"
                self._status_label.color = "#F87171"
                try:
                    self._talk_btn.update()
                    self._status_label.update()
                except Exception:
                    pass
                if self._on_error_message:
                    self._on_error_message(f"Error al transcribir voz: {e}")

        threading.Thread(target=_transcribe_worker, daemon=True, name="aura-stt-worker").start()

    def _on_recorder_cancel(self, reason: str = "Cancelado") -> None:
        """Llamado cuando el VAD cancela por inactividad o el usuario cancela."""
        _logger.info(f"AudioPanel: Grabación cancelada ({reason}).")
        self._talk_btn.text = "🎤 Hablar"
        self._talk_btn.style.bgcolor = _BTN_TALK_IDLE
        self._status_label.value = reason
        self._status_label.color = _TEXT_MUTED
        self._level_bar.value = 0.0
        try:
            self._talk_btn.update()
            self._status_label.update()
            self._level_bar.update()
        except Exception:
            pass

        if self._on_status_message and "tiempo de espera" in reason.lower():
            self._on_status_message(f"🎤 {reason}")

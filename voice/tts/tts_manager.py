"""
AURA — Administrador Central de Síntesis y Conversión de Voz (TTS & RVC)

Orquesta el pipeline completo de voz de AURA:
1. Texto -> TTS base (Edge-TTS preferido, SAPI/pyttsx3 offline como fallback).
2. WAV fuente -> Conversión RVC con aura.pth y aura.index.
3. Fallback automático: ante cualquier fallo en RVC, reproduce la voz base
   y notifica: "⚠️ voz RVC no disponible, usando voz base", registrando la causa.
4. Reproducción por la salida de audio configurada (AUDIO_OUTPUT_DEVICE) con
   adaptación de sample rate mediante sounddevice.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable
import numpy as np

try:
    import sounddevice as sd
    _HAS_SOUNDDEVICE = True
except Exception:
    sd = None
    _HAS_SOUNDDEVICE = False

import soundfile as sf

from config.settings import settings
from utils.logger import get_logger
from voice.audio_manager import find_device
from voice.tts.base_tts import get_base_tts, EdgeTTSProvider, SAPITTSProvider
from voice.tts.rvc_converter import rvc_converter

_logger = get_logger("aura.voice.tts.manager")

# Directorio temporal para archivos de audio
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
_CACHE_DIR = _ROOT_DIR / "data" / "audio_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class TTSPlayResult:
    success: bool
    audio_path: str = ""
    error: str = ""
    provider_used: str = ""
    is_fallback: bool = False
    fallback_reason: str = ""
    duration_s: float = 0.0


def clean_text_for_speech(text: str) -> str:
    """
    Limpia formato markdown, bloques de código, enlaces y sintaxis especial
    para que la locución TTS suene natural y fluida.
    """
    import re
    if not text:
        return ""
    # Quitar bloques de código
    t = re.sub(r"```[\s\S]*?```", " código omitido. ", text)
    # Quitar código inline
    t = re.sub(r"`([^`]+)`", r"\1", t)
    # Quitar enlaces markdown [texto](url) -> texto
    t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", t)
    # Quitar cabeceras markdown
    t = re.sub(r"^\s*#+\s*", "", t, flags=re.MULTILINE)
    # Quitar asteriscos de negrita/cursiva
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    # Quitar viñetas
    t = re.sub(r"^\s*[-*•]\s+", "", t, flags=re.MULTILINE)
    # Quitar caracteres especiales residuales
    t = re.sub(r"[~_]", "", t)
    # Asegurar puntuación suave en saltos de línea
    lines = [line.strip() for line in t.split("\n") if line.strip()]
    cleaned_lines = []
    for line in lines:
        if line and line[-1] not in ".!?,:;":
            cleaned_lines.append(line + ".")
        else:
            cleaned_lines.append(line)
    t = " ".join(cleaned_lines)
    return re.sub(r"\s+", " ", t).strip()


class TTSManager:
    """
    Administrador central de TTS y reproducción de voz de AURA.
    """

    _instance: Optional[TTSManager] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(TTSManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._current_thread: Optional[threading.Thread] = None
        self._is_playing: bool = False
        self._stop_event = threading.Event()
        self._fallback_callbacks: list[Callable[[str], None]] = []
        self._initialized = True
        _logger.info("TTSManager inicializado.")

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    def register_fallback_callback(self, callback: Callable[[str], None]) -> None:
        """Registra un callback invocado cuando ocurre fallback a la voz base."""
        if callback not in self._fallback_callbacks:
            self._fallback_callbacks.append(callback)

    def unregister_fallback_callback(self, callback: Callable[[str], None]) -> None:
        if callback in self._fallback_callbacks:
            self._fallback_callbacks.remove(callback)

    def _notify_fallback(self, reason: str) -> None:
        msg = "⚠️ voz RVC no disponible, usando voz base"
        _logger.warning(f"TTS Fallback: {msg}. Causa: {reason}")
        for cb in list(self._fallback_callbacks):
            try:
                cb(f"{msg} ({reason})")
            except Exception as e:
                _logger.error(f"Error en callback de fallback: {e}")

    def stop(self) -> None:
        """Detiene inmediatamente cualquier reproducción de audio en curso."""
        self._stop_event.set()
        if _HAS_SOUNDDEVICE and sd is not None:
            try:
                sd.stop()
            except Exception:
                pass
        self._is_playing = False
        try:
            _logger.info("TTSManager: reproducción detenida.")
        except Exception:
            pass

    def play_wav_file(self, wav_path: str, output_device_name: Optional[str] = None) -> bool:
        """
        Reproduce un archivo WAV en el dispositivo de salida configurado (AUDIO_OUTPUT_DEVICE).
        Ajusta y remuestrea al sample rate nativo del dispositivo si es necesario.
        """
        if not _HAS_SOUNDDEVICE or sd is None:
            _logger.warning("play_wav_file: sounddevice no está disponible.")
            return False

        if not os.path.isfile(wav_path):
            _logger.error(f"Archivo WAV no encontrado para reproducción: {wav_path}")
            return False

        target_dev = output_device_name or settings.get("AUDIO_OUTPUT_DEVICE", "").strip() or None
        dev_idx = find_device(target_dev, kind="output") if target_dev else None

        try:
            data, file_sr = sf.read(wav_path, dtype="float32")

            # Consultar sample rate nativo del dispositivo
            try:
                dev_info = sd.query_devices(dev_idx, "output")
                native_sr = int(dev_info["default_samplerate"])
            except Exception:
                native_sr = file_sr

            # Si el sample rate difiere y sounddevice no lo acepta directamente, remuestrear
            playback_data = data
            playback_sr = file_sr

            try:
                self._is_playing = True
                self._stop_event.clear()
                _logger.info(f"Reproduciendo {wav_path} ({file_sr}Hz -> {playback_sr}Hz, dev={dev_idx})...")
                sd.play(playback_data, samplerate=playback_sr, device=dev_idx)

                # Esperar que termine la reproducción respetando self._stop_event
                dur = len(playback_data) / playback_sr
                t_end = time.time() + dur + 0.1
                while time.time() < t_end and not self._stop_event.is_set():
                    time.sleep(0.05)

                if self._stop_event.is_set():
                    sd.stop()

                self._is_playing = False
                return True
            except Exception as e:
                # Si falló por sample rate, remuestrear a native_sr usando scipy o resampy
                _logger.warning(f"Error directo en sd.play ({e}). Intentando con remuestreo a {native_sr}Hz...")
                try:
                    from scipy.signal import resample_poly
                    from math import gcd
                    g = gcd(file_sr, native_sr)
                    up = native_sr // g
                    down = file_sr // g
                    resampled = resample_poly(data, up, down).astype(np.float32)
                    sd.play(resampled, samplerate=native_sr, device=dev_idx)
                    dur = len(resampled) / native_sr
                    t_end = time.time() + dur + 0.1
                    while time.time() < t_end and not self._stop_event.is_set():
                        time.sleep(0.05)
                    self._is_playing = False
                    return True
                except Exception as ex2:
                    _logger.error(f"Fallo reproduciendo con remuestreo: {ex2}", exc_info=True)
                    self._is_playing = False
                    return False

        except Exception as e:
            _logger.error(f"Error cargando o reproduciendo WAV {wav_path}: {e}", exc_info=True)
            self._is_playing = False
            return False

    def synthesize(
        self,
        text: str,
        provider: Optional[str] = None,
        voice: Optional[str] = None,
        on_fallback: Optional[Callable[[str], None]] = None,
    ) -> TTSPlayResult:
        """
        Ejecuta la síntesis de texto a audio siguiendo la política de proveedores y fallback.

        Returns:
            TTSPlayResult con la ruta del archivo generado, estado y datos de fallback.
        """
        prov = (provider or settings.get("TTS_PROVIDER", "rvc") or "rvc").lower().strip()
        if prov in ("none", "disabled", "off"):
            return TTSPlayResult(success=True, provider_used="none")

        clean_text = clean_text_for_speech(text)
        if not clean_text:
            return TTSPlayResult(success=False, error="Texto vacío")

        ts_id = int(time.time() * 1000)
        base_wav_path = str(_CACHE_DIR / f"tts_base_{ts_id}.wav")
        rvc_wav_path = str(_CACHE_DIR / f"tts_rvc_{ts_id}.wav")

        # ── CASO 1: Solo SAPI (Offline directo) ─────────────────────
        if prov == "sapi":
            sapi = SAPITTSProvider()
            ok, err = sapi.synthesize(clean_text, base_wav_path)
            if ok:
                info = sf.info(base_wav_path)
                return TTSPlayResult(success=True, audio_path=base_wav_path, provider_used="sapi", duration_s=info.duration)
            return TTSPlayResult(success=False, error=err, provider_used="sapi")

        # ── CASO 2: Solo Edge-TTS (Directo sin RVC) ─────────────────
        if prov == "edge":
            edge = EdgeTTSProvider()
            ok, err = edge.synthesize(clean_text, base_wav_path, voice=voice)
            if ok:
                info = sf.info(base_wav_path)
                return TTSPlayResult(success=True, audio_path=base_wav_path, provider_used="edge", duration_s=info.duration)
            # Fallback a SAPI si edge falló (ej: sin conexión)
            _logger.warning(f"EdgeTTS falló ({err}). Conmutando a fallback SAPI...")
            sapi = SAPITTSProvider()
            sapi_ok, sapi_err = sapi.synthesize(clean_text, base_wav_path)
            if sapi_ok:
                info = sf.info(base_wav_path)
                return TTSPlayResult(
                    success=True,
                    audio_path=base_wav_path,
                    provider_used="sapi",
                    is_fallback=True,
                    fallback_reason=f"EdgeTTS offline: {err}",
                    duration_s=info.duration,
                )
            return TTSPlayResult(success=False, error=f"EdgeTTS y SAPI fallaron: {err} | {sapi_err}", provider_used="edge")

        # ── CASO 3: RVC (Arquitectura completa con conversión y fallback) ─
        # Paso 1: Generar audio base (EdgeTTS preferido, SAPI fallback)
        base_eng_name = (settings.get("RVC_TTS_BASE", "edge") or "edge").lower().strip()
        base_prov = get_base_tts(base_eng_name)
        base_voice = settings.get("RVC_TTS_BASE_VOICE", "es-MX-DaliaNeural")
        base_ok, base_err = base_prov.synthesize(clean_text, base_wav_path, voice=base_voice)

        if not base_ok and isinstance(base_prov, EdgeTTSProvider):
            _logger.warning(f"TTS Base Edge falló ({base_err}). Usando fallback SAPI para WAV fuente...")
            base_prov = SAPITTSProvider()
            base_ok, base_err = base_prov.synthesize(clean_text, base_wav_path)

        if not base_ok:
            return TTSPlayResult(success=False, error=f"Fallo en generación de TTS base: {base_err}", provider_used="base_tts")

        # Paso 2: Conversión RVC con modelo configurado (ej: aura.pth)
        rvc_voice = voice or settings.get("RVC_VOZ", "aura") or "aura"
        rvc_ok, rvc_err, tgt_sr = rvc_converter.convert(base_wav_path, rvc_wav_path, voice=rvc_voice)

        if rvc_ok and os.path.isfile(rvc_wav_path):
            info = sf.info(rvc_wav_path)
            return TTSPlayResult(
                success=True,
                audio_path=rvc_wav_path,
                provider_used=f"rvc:{rvc_voice}",
                duration_s=info.duration,
            )

        # Paso 3: Fallback ante cualquier error de RVC
        self._notify_fallback(rvc_err)
        if on_fallback:
            try:
                on_fallback(rvc_err)
            except Exception:
                pass

        base_info = sf.info(base_wav_path)
        return TTSPlayResult(
            success=True,
            audio_path=base_wav_path,
            provider_used="base_fallback",
            is_fallback=True,
            fallback_reason=rvc_err,
            duration_s=base_info.duration,
        )

    def speak(
        self,
        text: str,
        on_started: Optional[Callable[[], None]] = None,
        on_completed: Optional[Callable[[TTSPlayResult], None]] = None,
        on_fallback: Optional[Callable[[str], None]] = None,
        async_play: bool = True,
    ) -> Optional[TTSPlayResult]:
        """
        Sintetiza y reproduce el texto en el dispositivo de salida de audio configurado.
        Por defecto se ejecuta en un hilo de fondo (async_play=True) para no bloquear la UI.
        """
        if not text or not text.strip():
            return None

        def _worker() -> TTSPlayResult:
            if on_started:
                try:
                    on_started()
                except Exception:
                    pass

            result = self.synthesize(text, on_fallback=on_fallback)
            if result.success and result.audio_path:
                self.play_wav_file(result.audio_path)

            if on_completed:
                try:
                    on_completed(result)
                except Exception:
                    pass
            return result

        if async_play:
            self._current_thread = threading.Thread(target=_worker, daemon=True, name="aura-tts-speech")
            self._current_thread.start()
            return None
        else:
            return _worker()


# Singleton exportado
tts_manager = TTSManager()

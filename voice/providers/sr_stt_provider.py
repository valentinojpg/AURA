"""
AURA — Proveedor STT real via SpeechRecognition (Fase 22 — Base de voz)

Implementa el proveedor STT usando las librerías:
    - speechrecognition (>=3.10.0): Motor de reconocimiento
    - pyaudio (>=0.2.13): Captura de audio del micrófono

Ambas librerías son OPCIONALES: si no están instaladas, check_status()
retorna STTStatus.NO_AUDIO_LIB o STTStatus.NO_STT_LIB y todos los métodos
retornan resultados vacíos/seguros sin lanzar excepciones.

Motor de reconocimiento: Google Web Speech API (gratuito, requiere internet).
Se puede extender con otras APIs (Whisper local, etc.) en fases futuras.

Importaciones lazy:
    - `speech_recognition` se importa solo cuando se necesita
    - `pyaudio` se importa internamente por speechrecognition
    - Evita errores de import en entornos sin las librerías instaladas
"""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Optional, Union
import numpy as np

from utils.logger import get_logger
from voice.voice_interface import (
    STTProvider,
    STTProviderInfo,
    STTResult,
    STTStatus,
    MicDevice,
)

_logger = get_logger("aura.voice.sr_provider")


def _import_sr():
    """Intenta importar speech_recognition. Retorna módulo o None."""
    try:
        import speech_recognition as sr
        return sr
    except ImportError:
        return None


def _check_pyaudio() -> bool:
    """Verifica si pyaudio está instalado."""
    try:
        import importlib.util
        return importlib.util.find_spec("pyaudio") is not None
    except Exception:
        return False


class SpeechRecognitionSTTProvider(STTProvider):
    """
    Proveedor STT usando SpeechRecognition + PyAudio + Google Web Speech API.

    Requiere:
        - pip install speechrecognition pyaudio
        - Conexión a internet para el reconocimiento Google

    Si las dependencias no están instaladas:
        - check_status() retorna NO_AUDIO_LIB o NO_STT_LIB
        - list_microphones() retorna lista vacía
        - transcribe_once() retorna STTResult(success=False)

    Uso básico:
        provider = SpeechRecognitionSTTProvider()
        if provider.is_available():
            result = provider.transcribe_once(mic_index=0)
            print(result.text)
    """

    def get_info(self) -> STTProviderInfo:
        return STTProviderInfo(
            name="google_sr",
            display_name="Google Speech (SpeechRecognition)",
            description=(
                "Reconocimiento de voz via Google Web Speech API. "
                "Requiere speechrecognition, pyaudio e internet."
            ),
            requires_internet=True,
            is_mock=False,
        )

    def check_status(self) -> STTStatus:
        """
        Verifica disponibilidad completa del proveedor:
        1. ¿Está instalado speechrecognition?
        2. ¿Está instalado pyaudio?
        3. ¿Hay micrófonos disponibles?
        """
        sr = _import_sr()
        if sr is None:
            _logger.debug("speechrecognition no instalado")
            return STTStatus.NO_STT_LIB

        if not _check_pyaudio():
            _logger.debug("pyaudio no instalado")
            return STTStatus.NO_AUDIO_LIB

        # Verificar que hay micrófonos
        try:
            mics = sr.Microphone.list_microphone_names()
            if not mics:
                _logger.debug("No se detectaron micrófonos en el sistema")
                return STTStatus.NO_MIC
        except Exception as e:
            _logger.warning(f"Error al listar micrófonos: {e}")
            return STTStatus.NO_MIC

        return STTStatus.AVAILABLE

    def list_microphones(self) -> list[MicDevice]:
        """
        Lista los micrófonos disponibles usando PyAudio.

        Intenta detectar el dispositivo de entrada por defecto.
        Retorna lista vacía si pyaudio no está instalado.
        """
        sr = _import_sr()
        if sr is None:
            return []
        if not _check_pyaudio():
            return []

        try:
            names = sr.Microphone.list_microphone_names()
        except Exception as e:
            _logger.warning(f"Error al listar micrófonos: {e}")
            return []

        if not names:
            return []

        # Intentar detectar el micrófono por defecto via pyaudio
        default_index = self._get_default_mic_index()

        devices = []
        for idx, name in enumerate(names):
            devices.append(MicDevice(
                index=idx,
                name=name,
                default=(idx == default_index),
            ))

        return devices

    def transcribe_once(
        self,
        mic_index: Optional[int] = None,
        timeout_s: float = 5.0,
        phrase_timeout_s: float = 3.0,
    ) -> STTResult:
        """
        Captura audio del micrófono y transcribe usando Google Web Speech API.

        Args:
            mic_index:        Índice del dispositivo (None = default del SO)
            timeout_s:        Segundos máximos esperando que el usuario hable
            phrase_timeout_s: Segundos máximos de la frase completa

        Returns:
            STTResult con texto transcrito o error descriptivo.
        """
        sr = _import_sr()
        if sr is None:
            return STTResult(
                success=False,
                error="speechrecognition no está instalado. "
                      "Instalá con: pip install speechrecognition",
                provider="google_sr",
            )

        if not _check_pyaudio():
            return STTResult(
                success=False,
                error="pyaudio no está instalado. "
                      "Instalá con: pip install pyaudio",
                provider="google_sr",
            )

        start = time.monotonic()
        recognizer = sr.Recognizer()
        recognizer.pause_threshold = phrase_timeout_s

        try:
            mic_kwargs = {}
            if mic_index is not None:
                mic_kwargs["device_index"] = mic_index

            with sr.Microphone(**mic_kwargs) as source:
                # Ajuste de ruido ambiente (corto para no bloquear mucho)
                recognizer.adjust_for_ambient_noise(source, duration=0.3)

                _logger.info(
                    f"Escuchando (mic={mic_index}, timeout={timeout_s}s)..."
                )
                try:
                    audio = recognizer.listen(
                        source,
                        timeout=timeout_s,
                        phrase_time_limit=phrase_timeout_s,
                    )
                except sr.WaitTimeoutError:
                    return STTResult(
                        success=False,
                        error="No se detectó audio en el tiempo de espera.",
                        provider="google_sr",
                        duration_ms=int((time.monotonic() - start) * 1000),
                    )

        except OSError as e:
            _logger.warning(f"Error de micrófono: {e}")
            return STTResult(
                success=False,
                error=f"Error al acceder al micrófono: {e}",
                provider="google_sr",
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as e:
            _logger.error(f"Error inesperado en captura: {e}", exc_info=True)
            return STTResult(
                success=False,
                error=f"Error al capturar audio: {e}",
                provider="google_sr",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        # Transcribir con Google Web Speech API
        try:
            text = recognizer.recognize_google(audio, language="es-AR")
            duration_ms = int((time.monotonic() - start) * 1000)
            _logger.info(f"Transcripción OK: {text!r} ({duration_ms}ms)")
            return STTResult(
                success=True,
                text=text,
                provider="google_sr",
                duration_ms=duration_ms,
            )

        except sr.UnknownValueError:
            return STTResult(
                success=False,
                error="No se pudo entender el audio. Hablá más claro o acercate al micrófono.",
                provider="google_sr",
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except sr.RequestError as e:
            _logger.warning(f"Error de API Google Speech: {e}")
            return STTResult(
                success=False,
                error=f"Error al conectarse al servicio de voz: {e}. "
                      f"Verificá tu conexión a internet.",
                provider="google_sr",
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as e:
            _logger.error(f"Error inesperado en transcripción: {e}", exc_info=True)
            return STTResult(
                success=False,
                error=f"Error al transcribir: {e}",
                provider="google_sr",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

    def transcribe_wav(self, wav_source: Union[bytes, str, Path, io.BytesIO]) -> str:
        """
        Transcribe un archivo, buffer o bytes WAV a texto mediante Google Web Speech API.
        """
        sr = _import_sr()
        if sr is None:
            return ""
        recognizer = sr.Recognizer()
        try:
            if isinstance(wav_source, bytes):
                audio_file = io.BytesIO(wav_source)
            elif isinstance(wav_source, (str, Path)):
                audio_file = str(wav_source)
            else:
                audio_file = wav_source

            with sr.AudioFile(audio_file) as source:
                audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="es-AR")
            return text.strip() if text else ""
        except Exception as e:
            _logger.warning(f"GoogleSTT transcribe_wav falló: {e}")
            return ""

    def transcribe_audio_data(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
        language: str = "es-AR",
    ) -> STTResult:
        """Transcribe un array numpy mediante Google Web Speech API."""
        from voice.audio_manager import transcribe_google_internal
        return transcribe_google_internal(audio_data, sample_rate=sample_rate, language=language)

    # ──────────────────────────────────────────────
    # Helpers internos
    # ──────────────────────────────────────────────

    def _get_default_mic_index(self) -> Optional[int]:
        """Detecta el índice del micrófono por defecto via PyAudio."""
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            try:
                info = pa.get_default_input_device_info()
                return int(info.get("index", 0))
            finally:
                pa.terminate()
        except Exception:
            return 0


# Alias para compatibilidad y paridad con Whisper
GoogleSTTProvider = SpeechRecognitionSTTProvider
google_stt_provider = GoogleSTTProvider()


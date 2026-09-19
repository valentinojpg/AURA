# -*- coding: utf-8 -*-
"""
AURA — Proveedor STT local Faster-Whisper (Fase 74)

Implementa el proveedor STT utilizando faster-whisper (CTranslate2):
- Modelos cacheados en models/stt/ dentro del proyecto (nunca en el home del usuario).
- Soporte para transcribe_wav(bytes | ruta) -> str y transcribe_audio_data(...) -> STTResult.
- Selección automática de hardware: GPU (float16) si hay CUDA, CPU (int8) en caso contrario.
- Parámetros obligatorios: vad_filter=WHISPER_VAD, condition_on_previous_text=False, language=WHISPER_LANGUAGE.
- Fallback seguro a Google Web Speech API si la descarga o transcripción con Whisper falla.
"""

from __future__ import annotations

import io
import os
import time
from pathlib import Path
from typing import Optional, Union, Callable, Any
import numpy as np

# Desactivar advertencia no crítica de symlinks en Windows de huggingface_hub
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from config.settings import settings
from utils.logger import get_logger
from voice.voice_interface import (
    STTProvider,
    STTProviderInfo,
    STTResult,
    STTStatus,
    MicDevice,
)

_logger = get_logger("aura.voice.whisper_provider")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
STT_MODELS_DIR = ROOT_DIR / "models" / "stt"
STT_MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Pesos aproximados para la UI y logs
WHISPER_MODEL_SIZES = {
    "tiny": "~75 MB",
    "base": "~145 MB",
    "small": "~460 MB",
    "medium": "~1.5 GB",
    "large-v3": "~3.1 GB",
}


def is_gpu_available() -> bool:
    """Determina si hay GPU CUDA disponible para cómputo."""
    try:
        import torch
        if torch.cuda.is_available() and torch.cuda.device_count() > 0:
            return True
    except Exception:
        pass
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return True
    except Exception:
        pass
    return False


def get_whisper_device_and_compute(
    requested_compute: Optional[str] = None,
) -> tuple[str, str]:
    """
    Resuelve el dispositivo ('cuda' o 'cpu') y el compute_type ('float16', 'int8', etc.).
    Regla Fase 74: WHISPER_COMPUTE=auto -> float16 con GPU, int8 con CPU.
    """
    has_gpu = is_gpu_available()
    device = "cuda" if has_gpu else "cpu"
    comp = (requested_compute or settings.get("WHISPER_COMPUTE", "auto")).lower().strip()
    if comp == "auto":
        compute_type = "float16" if has_gpu else "int8"
    else:
        compute_type = comp
    return device, compute_type


def _import_faster_whisper():
    """Intenta importar faster_whisper de forma perezosa (lazy import)."""
    try:
        import faster_whisper
        return faster_whisper
    except ImportError:
        return None


class FasterWhisperSTT(STTProvider):
    """
    Proveedor STT local de alta velocidad basado en faster-whisper.
    """

    def __init__(self):
        self._model_instance: Any = None
        self._loaded_key: Optional[tuple[str, str, str]] = None  # (model_name, device, compute_type)
        self._on_download_progress: Optional[Callable[[str], None]] = None

    def get_info(self) -> STTProviderInfo:
        return STTProviderInfo(
            name="whisper",
            display_name="Faster-Whisper (Local)",
            description=(
                "Reconocimiento de voz local de alta precisión y velocidad con faster-whisper. "
                "Funciona offline una vez descargado el modelo en models/stt/."
            ),
            requires_internet=False,
            is_mock=False,
        )

    def check_status(self) -> STTStatus:
        fw = _import_faster_whisper()
        if fw is None:
            _logger.debug("faster-whisper no instalado en el entorno")
            return STTStatus.NO_STT_LIB
        return STTStatus.AVAILABLE

    def list_microphones(self) -> list[MicDevice]:
        """Reutiliza la enumeración de micrófonos del sistema via SpeechRecognition / PyAudio."""
        try:
            from voice.providers.sr_stt_provider import SpeechRecognitionSTTProvider
            return SpeechRecognitionSTTProvider().list_microphones()
        except Exception:
            return []

    def set_progress_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """Permite a la UI (AudioPanel) suscribirse al progreso de descarga o carga."""
        self._on_download_progress = callback

    def _is_model_cached(self, model_name: str) -> bool:
        """Verifica si el modelo ya se encuentra descargado en models/stt/."""
        if not STT_MODELS_DIR.exists():
            return False
        # faster-whisper almacena como models--Systran--faster-whisper-<model_name> o similar
        for child in STT_MODELS_DIR.iterdir():
            if child.is_dir() and model_name.lower() in child.name.lower():
                return True
        return False

    def load_model(self, force_reload: bool = False) -> Any:
        """
        Carga o reutiliza la instancia de WhisperModel según la configuración activa.
        """
        fw = _import_faster_whisper()
        if fw is None:
            raise RuntimeError(
                "faster-whisper no está instalado. Instalá la dependencia con: pip install faster-whisper"
            )

        model_name = settings.get("WHISPER_MODEL", "small").strip()
        device, compute_type = get_whisper_device_and_compute()
        current_key = (model_name, device, compute_type)

        if not force_reload and self._model_instance is not None and self._loaded_key == current_key:
            return self._model_instance

        approx_size = WHISPER_MODEL_SIZES.get(model_name, "460 MB")
        is_cached = self._is_model_cached(model_name)

        if not is_cached:
            msg = f"Descargando modelo {model_name}: {approx_size}..."
            _logger.info(f"FasterWhisperSTT: {msg}")
            if self._on_download_progress:
                try:
                    self._on_download_progress(msg)
                except Exception:
                    pass

        try:
            _logger.info(
                f"FasterWhisperSTT: Inicializando WhisperModel('{model_name}', "
                f"device='{device}', compute_type='{compute_type}', download_root='{STT_MODELS_DIR}')"
            )
            # En CPU usamos cpu_threads para buen rendimiento sin saturar
            cpu_threads = 4 if device == "cpu" else 0
            model = fw.WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
                download_root=str(STT_MODELS_DIR),
                cpu_threads=cpu_threads,
            )
            self._model_instance = model
            self._loaded_key = current_key
            _logger.info(f"FasterWhisperSTT: Modelo '{model_name}' cargado exitosamente.")
            return model
        except Exception as e:
            _logger.error(f"FasterWhisperSTT: Fallo al cargar o descargar modelo '{model_name}': {e}", exc_info=True)
            self._model_instance = None
            self._loaded_key = None
            raise

    def transcribe_wav(self, wav_source: Union[bytes, str, Path, io.BytesIO]) -> str:
        """
        Transcribe un archivo o buffer WAV a texto.

        Args:
            wav_source: Ruta a archivo WAV, bytes de audio WAV o BytesIO.

        Returns:
            Texto transcrito en string plano (o cadena vacía si solo hubo silencio).
        """
        res = self.transcribe_source(wav_source)
        return res.text if res.success else ""

    def transcribe_source(
        self,
        wav_source: Union[bytes, str, Path, io.BytesIO],
        language: Optional[str] = None,
    ) -> STTResult:
        """
        Transcribe audio desde archivo, bytes o buffer usando los parámetros obligatorios:
        vad_filter=WHISPER_VAD, condition_on_previous_text=False, language=WHISPER_LANGUAGE.
        """
        start_time = time.monotonic()
        model_name = settings.get("WHISPER_MODEL", "small").strip()
        lang = language or settings.get("WHISPER_LANGUAGE", "es")
        vad_enabled = settings.get_bool("WHISPER_VAD", fallback=True)

        try:
            model = self.load_model()
        except Exception as e:
            notice = f"⚠️ whisper falló ({e}), usando Google STT"
            _logger.warning(notice)
            return self._fallback_transcribe_source(wav_source, notice=notice)

        try:
            # Si es bytes, pasamos io.BytesIO
            audio_input = io.BytesIO(wav_source) if isinstance(wav_source, bytes) else wav_source
            if isinstance(audio_input, Path):
                audio_input = str(audio_input)

            segments, info = model.transcribe(
                audio_input,
                vad_filter=vad_enabled,
                condition_on_previous_text=False,
                language=lang,
            )

            seg_texts = [seg.text.strip() for seg in segments if seg.text.strip()]
            text = " ".join(seg_texts).strip()

            dur_ms = int((time.monotonic() - start_time) * 1000)
            audio_len_s = getattr(info, "duration", 0.0)

            _logger.info(
                f"STT [whisper/{model_name}]: dur={dur_ms}ms, "
                f"audio_len={audio_len_s:.2f}s, text={text!r}"
            )

            return STTResult(
                success=True,
                text=text,
                error="",
                provider="whisper",
                duration_ms=dur_ms,
            )

        except Exception as e:
            notice = f"⚠️ whisper falló ({e}), usando Google STT"
            _logger.warning(notice)
            return self._fallback_transcribe_source(wav_source, notice=notice)

    def transcribe_audio_data(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> STTResult:
        """
        Transcribe un array numpy de audio (float32 o int16) directamente en memoria.
        """
        if audio_data is None or len(audio_data) == 0:
            _logger.warning("STT Whisper: Audio recibido está vacío. Cancelando.")
            return STTResult(success=False, text="", error="Audio vacío", provider="whisper")

        start_time = time.monotonic()
        model_name = settings.get("WHISPER_MODEL", "small").strip()
        lang = language or settings.get("WHISPER_LANGUAGE", "es")
        vad_enabled = settings.get_bool("WHISPER_VAD", fallback=True)

        flat_audio = audio_data.flatten()
        duration_s = len(flat_audio) / float(sample_rate)

        # Normalizar a float32 [-1.0, 1.0] si es entero
        if flat_audio.dtype in (np.int16, np.int32):
            audio_float = flat_audio.astype(np.float32) / 32768.0
        elif flat_audio.dtype in (np.float32, np.float64):
            audio_float = flat_audio.astype(np.float32)
            max_val = np.max(np.abs(audio_float)) if len(audio_float) > 0 else 0.0
            if max_val > 1.5:  # Escala int16 no normalizada
                audio_float = audio_float / 32768.0
        else:
            audio_float = flat_audio.astype(np.float32)

        # Si el sample rate no es 16000, remuestrear linealmente a 16000
        if sample_rate != 16000 and len(audio_float) > 0:
            orig_indices = np.linspace(0.0, 1.0, len(audio_float), endpoint=False)
            target_samples = int(len(audio_float) * 16000 / sample_rate)
            target_indices = np.linspace(0.0, 1.0, target_samples, endpoint=False)
            audio_float = np.interp(target_indices, orig_indices, audio_float).astype(np.float32)

        try:
            model = self.load_model()
        except Exception as e:
            notice = f"⚠️ whisper falló ({e}), usando Google STT"
            _logger.warning(notice)
            return self._fallback_transcribe_audio_data(audio_data, sample_rate, notice)

        try:
            segments, info = model.transcribe(
                audio_float,
                vad_filter=vad_enabled,
                condition_on_previous_text=False,
                language=lang,
            )

            seg_texts = [seg.text.strip() for seg in segments if seg.text.strip()]
            text = " ".join(seg_texts).strip()

            dur_ms = int((time.monotonic() - start_time) * 1000)
            actual_audio_len = getattr(info, "duration", duration_s)

            _logger.info(
                f"STT [whisper/{model_name}]: dur={dur_ms}ms, "
                f"audio_len={actual_audio_len:.2f}s, text={text!r}"
            )

            return STTResult(
                success=True,
                text=text,
                error="",
                provider="whisper",
                duration_ms=dur_ms,
            )

        except Exception as e:
            notice = f"⚠️ whisper falló ({e}), usando Google STT"
            _logger.warning(notice)
            return self._fallback_transcribe_audio_data(audio_data, sample_rate, notice)

    def transcribe_once(
        self,
        mic_index: Optional[int] = None,
        timeout_s: float = 5.0,
        phrase_timeout_s: float = 3.0,
    ) -> STTResult:
        """
        Captura audio del micrófono y transcribe usando faster-whisper.
        """
        try:
            from voice.providers.sr_stt_provider import _import_sr
            sr = _import_sr()
            if sr is None:
                return STTResult(
                    success=False,
                    text="",
                    error="speechrecognition no instalado para captura de micrófono",
                    provider="whisper",
                )

            recognizer = sr.Recognizer()
            recognizer.pause_threshold = phrase_timeout_s
            mic_kwargs = {}
            if mic_index is not None:
                mic_kwargs["device_index"] = mic_index

            with sr.Microphone(**mic_kwargs) as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.3)
                try:
                    audio = recognizer.listen(source, timeout=timeout_s, phrase_time_limit=phrase_timeout_s)
                except sr.WaitTimeoutError:
                    return STTResult(
                        success=False,
                        text="",
                        error="No se detectó audio en el tiempo de espera.",
                        provider="whisper",
                    )

            wav_data = audio.get_wav_data()
            return self.transcribe_source(wav_data)

        except Exception as e:
            _logger.error(f"Error en transcribe_once: {e}", exc_info=True)
            return STTResult(
                success=False,
                text="",
                error=f"Error en captura: {e}",
                provider="whisper",
            )

    # ──────────────────────────────────────────────────────────
    # Fallback transparente a Google STT
    # ──────────────────────────────────────────────────────────

    def _fallback_transcribe_source(
        self,
        wav_source: Union[bytes, str, Path, io.BytesIO],
        notice: str,
    ) -> STTResult:
        try:
            from voice.audio_manager import transcribe_wav_google
            text = transcribe_wav_google(wav_source)
            return STTResult(
                success=bool(text.strip()),
                text=text.strip(),
                error=notice if not text.strip() else "",
                provider="google_sr",
            )
        except Exception as e:
            return STTResult(
                success=False,
                text="",
                error=f"{notice}. Además Google STT falló: {e}",
                provider="google_sr",
            )

    def _fallback_transcribe_audio_data(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        notice: str,
    ) -> STTResult:
        try:
            from voice.audio_manager import transcribe_google_internal
            res = transcribe_google_internal(audio_data, sample_rate=sample_rate)
            # Preservar el aviso de fallback si se dio
            if res.success:
                _logger.info(f"Fallback a Google STT exitoso: {res.text!r}")
            return res
        except Exception as e:
            return STTResult(
                success=False,
                text="",
                error=f"{notice}. Además Google STT falló: {e}",
                provider="google_sr",
            )


# Singleton exportado
whisper_stt_provider = FasterWhisperSTT()

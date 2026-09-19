"""
AURA — Administrador de Audio y Grabación por Voz (Fase 22+)

Manejo centralizado de dispositivos de audio (sounddevice), medición de RMS,
VAD (detección de actividad de voz por umbral de energía) y auto-envío por silencio.

Requisitos implementados:
1. list_audio_devices() -> entradas y salidas con índice y nombre.
2. set_default_devices(input_name, output_name) -> asigna y persiste en .env.
3. VoiceRecorder con VAD por RMS:
   - Corta automáticamente tras VOICE_SILENCE_SECONDS de silencio continuo.
   - Cancela si no se detecta habla dentro de VOICE_WAIT_SPEECH_SECONDS.
   - Expone on_level(rms), on_result(audio, sr), on_cancel(motivo).
   - Grabación en hilo separado (background thread), nunca bloquea la UI.
   - Reintento con sample rate nativo y remuestreo a 16000 Hz si 16000 Hz falla.
4. play_test_beep() -> beep a 440 Hz para probar la salida de audio.
5. measure_mic_rms() -> mide RMS durante 2 segundos para calibrar el micrófono.
6. transcribe_audio_data() -> transcribir array float32/int16 con STT y logs detallados.

NOTA TTS:
El dispositivo de salida configurado (AUDIO_OUTPUT_DEVICE) aplica directamente a
reproducciones realizadas con sounddevice (como tonos de prueba o reproductores basados
en sounddevice).
TODO: Si el motor de TTS utilizado en fases posteriores (por ejemplo pygame, pyttsx3 u otro)
no respeta el dispositivo de salida seleccionado por el usuario, se deberá interceptar
el stream de audio PCM generado por dicho motor y dirigirlo hacia sounddevice.OutputStream
utilizando el dispositivo configurado.
"""

from __future__ import annotations

import inspect
import io
import threading
import time
from pathlib import Path
from typing import Callable, Optional, Any, Union
import numpy as np

try:
    import sounddevice as sd
    _HAS_SOUNDDEVICE = True
except Exception:
    sd = None
    _HAS_SOUNDDEVICE = False

from config.settings import settings
from utils.logger import get_logger
from voice.voice_interface import STTResult

_logger = get_logger("aura.voice.audio_manager")

# Valores por defecto para VAD
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_SILENCE_RMS = 0.02
DEFAULT_SILENCE_SECONDS = 1.5
DEFAULT_WAIT_SPEECH_SECONDS = 5.0
DEFAULT_MAX_DURATION_SECONDS = 30.0


def _clean_device_name(name: str) -> str:
    """Limpia caracteres corruptos o problemas de encoding comunes en nombres de dispositivos en Windows."""
    if not isinstance(name, str):
        return str(name)
    # Reemplazar caracteres típicos de decodificación errónea (ej. Micrfono -> Micrófono)
    cleaned = name.replace("Micrfono", "Micrófono").replace("Mezcla estreo", "Mezcla estéreo").replace("Lnea", "Línea")
    return cleaned.strip()


class AudioDeviceList(dict):
    """
    Contenedor de dispositivos de audio que permite acceso tipo diccionario
    (devs['inputs'], devs['outputs']), tipo objeto (devs.inputs, devs.outputs)
    y desempaquetado de tupla (inputs, outputs = list_audio_devices()).
    """
    def __init__(self, inputs: list[dict[str, Any]], outputs: list[dict[str, Any]]):
        super().__init__(inputs=inputs, outputs=outputs)
        self.inputs = inputs
        self.outputs = outputs

    def __iter__(self):
        # Permite: inputs, outputs = list_audio_devices()
        return iter((self.inputs, self.outputs))


def list_audio_devices() -> AudioDeviceList:
    """
    Lista todos los dispositivos de audio disponibles agrupados por entrada y salida.

    Returns:
        AudioDeviceList con claves 'inputs' y 'outputs', donde cada elemento es un dict:
        {
            'index': int,
            'name': str,
            'channels': int,
            'default_samplerate': float,
            'hostapi': int,
            'is_default': bool,
        }
    """
    inputs: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []

    if not _HAS_SOUNDDEVICE or sd is None:
        _logger.warning("sounddevice no está disponible. list_audio_devices retorna listas vacías.")
        return AudioDeviceList(inputs=inputs, outputs=outputs)

    try:
        devices = sd.query_devices()
        default_in, default_out = -1, -1
        try:
            default_device = sd.default.device
            if isinstance(default_device, (list, tuple)):
                default_in = default_device[0] if len(default_device) > 0 else -1
                default_out = default_device[1] if len(default_device) > 1 else -1
            elif isinstance(default_device, int):
                default_in = default_device
                default_out = default_device
        except Exception as e:
            _logger.debug(f"No se pudo determinar default.device de sounddevice: {e}")

        for idx, dev in enumerate(devices):
            if not isinstance(dev, dict):
                continue
            clean_name = _clean_device_name(dev.get("name", f"Dispositivo {idx}"))
            max_in = dev.get("max_input_channels", 0)
            max_out = dev.get("max_output_channels", 0)
            samplerate = dev.get("default_samplerate", 44100.0)
            hostapi = dev.get("hostapi", 0)

            if max_in > 0:
                inputs.append({
                    "index": idx,
                    "name": clean_name,
                    "channels": max_in,
                    "default_samplerate": samplerate,
                    "hostapi": hostapi,
                    "is_default": (idx == default_in),
                })

            if max_out > 0:
                outputs.append({
                    "index": idx,
                    "name": clean_name,
                    "channels": max_out,
                    "default_samplerate": samplerate,
                    "hostapi": hostapi,
                    "is_default": (idx == default_out),
                })

        _logger.debug(f"list_audio_devices: {len(inputs)} entradas y {len(outputs)} salidas detectadas.")
    except Exception as e:
        _logger.error(f"Error consultando dispositivos de audio con sounddevice: {e}", exc_info=True)

    return AudioDeviceList(inputs=inputs, outputs=outputs)


def find_device(name_or_index: Optional[str | int], kind: str = "input") -> Optional[int]:
    """
    Busca un dispositivo por índice numérico o por coincidencia de nombre (exacta o parcial).

    Args:
        name_or_index: Nombre del dispositivo o índice.
        kind: 'input' o 'output'.

    Returns:
        Índice entero del dispositivo o None si no se encuentra.
    """
    if name_or_index is None:
        return None

    if isinstance(name_or_index, int):
        return name_or_index

    query = str(name_or_index).strip()
    if not query:
        return None

    if query.isdigit():
        return int(query)

    devices = list_audio_devices()
    candidate_list = devices.inputs if kind.lower().startswith("in") else devices.outputs

    # 1. Coincidencia exacta
    for dev in candidate_list:
        if dev["name"].strip() == query:
            return dev["index"]

    # 2. Coincidencia case-insensitive exacta
    for dev in candidate_list:
        if dev["name"].strip().lower() == query.lower():
            return dev["index"]

    # 3. Coincidencia por subcadena
    for dev in candidate_list:
        if query.lower() in dev["name"].lower():
            return dev["index"]

    return None


def get_default_devices() -> tuple[Optional[str], Optional[str]]:
    """
    Retorna los nombres de los dispositivos configurados en .env o detectados por defecto.

    Returns:
        tuple(input_name, output_name)
    """
    input_name = settings.get("AUDIO_INPUT_DEVICE", "").strip() or None
    output_name = settings.get("AUDIO_OUTPUT_DEVICE", "").strip() or None

    devices = list_audio_devices()

    if not input_name:
        for dev in devices.inputs:
            if dev["is_default"]:
                input_name = dev["name"]
                break
        if not input_name and devices.inputs:
            input_name = devices.inputs[0]["name"]

    if not output_name:
        for dev in devices.outputs:
            if dev["is_default"]:
                output_name = dev["name"]
                break
        if not output_name and devices.outputs:
            output_name = devices.outputs[0]["name"]

    return input_name, output_name


def set_default_devices(
    input_name: Optional[str] = None,
    output_name: Optional[str] = None,
) -> tuple[Optional[int], Optional[int]]:
    """
    Establece los dispositivos por defecto en sounddevice y los persiste en .env.

    Args:
        input_name: Nombre o parte del nombre del dispositivo de entrada deseado.
        output_name: Nombre o parte del nombre del dispositivo de salida deseado.

    Returns:
        tuple(input_index, output_index)
    """
    in_idx = find_device(input_name, kind="input") if input_name else None
    out_idx = find_device(output_name, kind="output") if output_name else None

    if _HAS_SOUNDDEVICE and sd is not None:
        try:
            current_in, current_out = sd.default.device
        except Exception:
            current_in, current_out = -1, -1

        new_in = in_idx if in_idx is not None else current_in
        new_out = out_idx if out_idx is not None else current_out

        if output_name is not None:
            try:
                from voice.message_speaker import message_speaker
                message_speaker.stop()
            except Exception:
                pass

        try:
            sd.default.device = (new_in, new_out)
            _logger.info(f"sounddevice.default.device actualizado a ({new_in}, {new_out})")
        except Exception as e:
            _logger.warning(f"No se pudo asignar sd.default.device: {e}")

    # Guardar en settings / .env
    try:
        if input_name is not None:
            settings.set("AUDIO_INPUT_DEVICE", str(input_name))
        if output_name is not None:
            settings.set("AUDIO_OUTPUT_DEVICE", str(output_name))
        _logger.info(f"Dispositivos guardados en .env: input={input_name!r}, output={output_name!r}")
    except Exception as e:
        _logger.warning(f"Error al guardar dispositivos en .env: {e}")

    return in_idx, out_idx


def play_test_beep(
    device: Optional[str | int] = None,
    duration_s: float = 0.5,
    freq: float = 440.0,
) -> bool:
    """
    Reproduce un tono senoidal de prueba a 440 Hz en el dispositivo de salida indicado.
    Nunca bloquea la interfaz ya que la reproducción corre en hilo separado si se solicita,
    o via sd.play no bloqueante.

    Args:
        device: Nombre o índice del dispositivo de salida (None = default de .env o sistema).
        duration_s: Duración en segundos (default 0.5s).
        freq: Frecuencia en Hz (default 440.0 Hz).

    Returns:
        True si se inició la reproducción correctamente, False en caso de error.
    """
    if not _HAS_SOUNDDEVICE or sd is None:
        _logger.warning("play_test_beep: sounddevice no está disponible.")
        return False

    out_device = find_device(device, kind="output") if device is not None else None
    if out_device is None:
        saved_out = settings.get("AUDIO_OUTPUT_DEVICE", "").strip()
        if saved_out:
            out_device = find_device(saved_out, kind="output")

    try:
        sr = 44100
        t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
        # Envolvente senoidal suave (evita clics acústicos al iniciar o finalizar)
        envelope = np.sin(np.pi * np.linspace(0, 1, len(t)))
        tone = (0.25 * np.sin(2 * np.pi * freq * t) * envelope).astype(np.float32)

        _logger.info(f"Reproduciendo beep de prueba {freq}Hz por {duration_s}s en salida (device={out_device})...")
        sd.play(tone, samplerate=sr, device=out_device)
        return True
    except Exception as e:
        _logger.error(f"Error reproduciendo beep de prueba en salida: {e}", exc_info=True)
        return False


def measure_mic_rms(
    device: Optional[str | int] = None,
    duration_s: float = 2.0,
    callback_level: Optional[Callable[[float], None]] = None,
) -> float:
    """
    Mide el nivel RMS del micrófono durante duration_s segundos.
    Se ejecuta típicamente en un hilo separado para no bloquear la UI.

    Args:
        device: Nombre o índice del micrófono (None = default de .env o sistema).
        duration_s: Tiempo de medición en segundos (default 2.0s).
        callback_level: Callback opcional llamado con el RMS en tiempo real.

    Returns:
        Valor RMS promedio medido (float).
    """
    if not _HAS_SOUNDDEVICE or sd is None:
        _logger.warning("measure_mic_rms: sounddevice no está disponible.")
        return 0.0

    in_device = find_device(device, kind="input") if device is not None else None
    if in_device is None:
        saved_in = settings.get("AUDIO_INPUT_DEVICE", "").strip()
        if saved_in:
            in_device = find_device(saved_in, kind="input")

    sr = 16000
    chunk_duration = 0.05
    chunk_samples = int(sr * chunk_duration)
    total_chunks = int(duration_s / chunk_duration)

    rms_values: list[float] = []

    try:
        stream = None
        try:
            stream = sd.InputStream(
                samplerate=sr,
                channels=1,
                dtype="float32",
                device=in_device,
                blocksize=chunk_samples,
            )
            stream.start()
        except Exception as e:
            _logger.warning(f"measure_mic_rms: Falló a 16000 Hz ({e}), reintentando con sample rate nativo...")
            dev_info = sd.query_devices(in_device, "input") if in_device is not None else sd.query_devices(kind="input")
            sr = int(dev_info.get("default_samplerate", 44100))
            chunk_samples = int(sr * chunk_duration)
            stream = sd.InputStream(
                samplerate=sr,
                channels=1,
                dtype="float32",
                device=in_device,
                blocksize=chunk_samples,
            )
            stream.start()

        _logger.info(f"Iniciando calibración de micrófono ({duration_s}s a {sr}Hz)...")
        for _ in range(total_chunks):
            data, overflowed = stream.read(chunk_samples)
            rms = float(np.sqrt(np.mean(data**2)))
            rms_values.append(rms)
            if callback_level:
                try:
                    callback_level(rms)
                except Exception as cb_err:
                    _logger.debug(f"Error en callback_level de prueba de mic: {cb_err}")

        stream.stop()
        stream.close()

        avg_rms = float(np.mean(rms_values)) if rms_values else 0.0
        max_rms = float(np.max(rms_values)) if rms_values else 0.0
        _logger.info(f"Medición de micrófono finalizada: RMS promedio = {avg_rms:.5f}, RMS máximo = {max_rms:.5f}")
        return avg_rms

    except Exception as e:
        _logger.error(f"Error durante la medición de micrófono: {e}", exc_info=True)
        return 0.0


def resample_to_16k(audio: np.ndarray, orig_sr: int) -> np.ndarray:
    """
    Remuestrea un array 1D de audio numpy desde orig_sr a 16000 Hz
    utilizando interpolación lineal de alta fidelidad.
    """
    if orig_sr == 16000 or len(audio) == 0:
        return audio
    duration = len(audio) / orig_sr
    target_samples = int(duration * 16000)
    if target_samples <= 0:
        return audio
    orig_indices = np.linspace(0.0, 1.0, len(audio), endpoint=False)
    target_indices = np.linspace(0.0, 1.0, target_samples, endpoint=False)
    resampled = np.interp(target_indices, orig_indices, audio).astype(audio.dtype)
    return resampled


def transcribe_google_internal(
    audio_data: np.ndarray,
    sample_rate: int = 16000,
    language: str = "es-AR",
) -> STTResult:
    """
    Transcribe un array numpy de audio (float32 o int16) mediante SpeechRecognition (Google Web Speech API).
    """
    if audio_data is None or len(audio_data) == 0:
        _logger.warning("STT Google: Audio recibido está vacío. Cancelando.")
        return STTResult(success=False, text="", error="Audio vacío", provider="google_sr")

    flat_audio = audio_data.flatten()
    if flat_audio.dtype in (np.float32, np.float64):
        int_audio = np.clip(flat_audio * 32767.0, -32768.0, 32767.0).astype(np.int16)
    else:
        int_audio = flat_audio.astype(np.int16)

    pcm_bytes = int_audio.tobytes()
    duration_s = len(flat_audio) / float(sample_rate)

    try:
        import speech_recognition as sr
    except ImportError:
        _logger.error("STT Google: speech_recognition no instalado.")
        return STTResult(
            success=False,
            text="",
            error="speech_recognition no está instalado",
            provider="mock",
        )

    audio_obj = sr.AudioData(pcm_bytes, sample_rate, 2)
    recognizer = sr.Recognizer()
    start_time = time.monotonic()

    try:
        text = recognizer.recognize_google(audio_obj, language=language)
        dur_ms = int((time.monotonic() - start_time) * 1000)
        clean_text = text.strip() if text else ""
        _logger.info(
            f"STT [google/google_sr]: dur={dur_ms}ms, "
            f"audio_len={duration_s:.2f}s, text={clean_text!r}"
        )
        if clean_text:
            return STTResult(
                success=True,
                text=clean_text,
                provider="google_sr",
                duration_ms=dur_ms,
            )
        else:
            return STTResult(
                success=False,
                text="",
                error="El servicio no detectó palabras legibles.",
                provider="google_sr",
                duration_ms=dur_ms,
            )

    except sr.UnknownValueError:
        dur_ms = int((time.monotonic() - start_time) * 1000)
        _logger.info(
            f"STT [google/google_sr]: dur={dur_ms}ms, audio_len={duration_s:.2f}s, text='' (sin audio comprensible)"
        )
        return STTResult(
            success=False,
            text="",
            error="No se pudo entender el audio grabado. Hablá más claro o revisá el umbral de silencio.",
            provider="google_sr",
            duration_ms=dur_ms,
        )

    except sr.RequestError as req_err:
        dur_ms = int((time.monotonic() - start_time) * 1000)
        _logger.error(f"STT Google: Error de conexión con Google Web Speech API: {req_err}")
        return STTResult(
            success=False,
            text="",
            error=f"Error de conexión con el servicio de voz: {req_err}",
            provider="google_sr",
            duration_ms=dur_ms,
        )

    except Exception as exc:
        dur_ms = int((time.monotonic() - start_time) * 1000)
        _logger.error(f"STT Google: Excepción no controlada durante transcripción: {exc}", exc_info=True)
        return STTResult(
            success=False,
            text="",
            error=f"Error interno en transcripción: {exc}",
            provider="google_sr",
            duration_ms=dur_ms,
        )


def transcribe_wav_google(wav_source: Union[bytes, str, Path, io.BytesIO]) -> str:
    """Transcribe un archivo o buffer WAV usando Google Web Speech API."""
    try:
        import speech_recognition as sr
    except ImportError:
        _logger.error("SpeechRecognition no instalado.")
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
        _logger.warning(f"Google Web Speech API error en transcribe_wav: {e}")
        return ""


def transcribe_wav(wav_source: Union[bytes, str, Path, io.BytesIO]) -> str:
    """
    Transcribe un archivo WAV (ruta, bytes o buffer) utilizando el proveedor STT activo.
    """
    from voice.stt_factory import get_stt_provider
    provider = get_stt_provider()
    if hasattr(provider, "transcribe_wav"):
        try:
            return provider.transcribe_wav(wav_source)
        except Exception as e:
            _logger.warning(f"⚠️ {provider.name} falló en transcribe_wav ({e}), usando Google STT")
            return transcribe_wav_google(wav_source)
    return transcribe_wav_google(wav_source)


def transcribe_audio_data(
    audio_data: np.ndarray,
    sample_rate: int = 16000,
    language: str = "es-AR",
) -> STTResult:
    """
    Transcribe un array numpy de audio (float32 o int16) utilizando el proveedor
    STT activo (Faster-Whisper local o Google Web Speech API).
    Si Whisper falla o no está disponible, realiza fallback transparente a Google.
    """
    if audio_data is None or len(audio_data) == 0:
        _logger.warning("STT: Audio recibido está vacío o longitud es cero. Se cancela transcripción.")
        return STTResult(success=False, text="", error="Audio vacío", provider="none")

    from voice.stt_factory import get_stt_provider
    provider = get_stt_provider()

    if getattr(provider, "name", "") == "whisper":
        try:
            return provider.transcribe_audio_data(audio_data, sample_rate=sample_rate, language=language)
        except Exception as e:
            _logger.warning(f"⚠️ whisper falló ({e}), usando Google STT")
            fallback_res = transcribe_google_internal(audio_data, sample_rate=sample_rate, language=language)
            if not fallback_res.error:
                fallback_res.error = f"⚠️ whisper falló ({e}), usando Google STT"
            return fallback_res
    else:
        return transcribe_google_internal(audio_data, sample_rate=sample_rate, language=language)


class VoiceRecorder:
    """
    Grabador de voz en hilo separado con detección de actividad de voz (VAD) basada en RMS.

    Comportamiento VAD:
    - Inicia en estado de espera (WAITING_FOR_SPEECH).
    - Si dentro de VOICE_WAIT_SPEECH_SECONDS no se supera VOICE_SILENCE_RMS, se cancela automáticamente.
    - Cuando se detecta voz (RMS >= VOICE_SILENCE_RMS), comienza a acumular audio (RECORDING_SPEECH).
    - Una vez que comenzó el habla, si se registran VOICE_SILENCE_SECONDS continuos con RMS < VOICE_SILENCE_RMS,
      corta automáticamente y finaliza la grabación.
    - Expone callbacks:
        * on_level(rms: float)
        * on_result(audio: np.ndarray, sample_rate: int)
        * on_cancel(reason: str)
    - Graba siempre en hilo separado (daemon thread). Nunca bloquea el hilo de UI.
    - Si el InputStream falla a 16000 Hz, reintenta con el sample rate nativo del dispositivo y remuestrea a 16000 Hz.
    """

    def __init__(
        self,
        device: Optional[str | int] = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        silence_rms: Optional[float] = None,
        silence_seconds: Optional[float] = None,
        wait_speech_seconds: Optional[float] = None,
        max_duration_seconds: float = DEFAULT_MAX_DURATION_SECONDS,
        on_level: Optional[Callable[[float], None]] = None,
        on_result: Optional[Callable[[np.ndarray, int], None]] = None,
        on_cancel: Optional[Callable[[str], None]] = None,
    ):
        self.device = device
        self.sample_rate = sample_rate
        self._custom_silence_rms = (silence_rms is not None)
        self._custom_silence_seconds = (silence_seconds is not None)
        self._custom_wait_speech_seconds = (wait_speech_seconds is not None)

        self.silence_rms = silence_rms if silence_rms is not None else settings.get_float("VOICE_SILENCE_RMS", DEFAULT_SILENCE_RMS)
        self.silence_seconds = silence_seconds if silence_seconds is not None else settings.get_float("VOICE_SILENCE_SECONDS", DEFAULT_SILENCE_SECONDS)
        self.wait_speech_seconds = wait_speech_seconds if wait_speech_seconds is not None else settings.get_float("VOICE_WAIT_SPEECH_SECONDS", DEFAULT_WAIT_SPEECH_SECONDS)
        self.max_duration_seconds = max_duration_seconds

        self.on_level = on_level
        self.on_result = on_result
        self.on_cancel = on_cancel

        self._is_recording = False
        self._stop_requested = False
        self._cancel_requested = False
        self._cancel_reason = ""
        self._thread: Optional[threading.Thread] = None
        self._current_rms: float = 0.0
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def is_listening(self) -> bool:
        return self._is_recording

    @property
    def current_rms(self) -> float:
        return self._current_rms

    def start(self) -> bool:
        """
        Inicia la grabación en un hilo de fondo.
        Retorna True si arrancó con éxito, False si ya estaba grabando.
        """
        with self._lock:
            if self._is_recording:
                _logger.warning("VoiceRecorder ya está activo; ignorando start().")
                return False

            if not _HAS_SOUNDDEVICE or sd is None:
                _logger.error("VoiceRecorder: sounddevice no está instalado o disponible.")
                self._safe_call_cancel("sounddevice no está disponible en este sistema.")
                return False

            # Recargar umbrales dinámicos desde settings si no fueron fijados explícitamente
            if not self._custom_silence_rms:
                self.silence_rms = settings.get_float("VOICE_SILENCE_RMS", self.silence_rms)
            if not self._custom_silence_seconds:
                self.silence_seconds = settings.get_float("VOICE_SILENCE_SECONDS", self.silence_seconds)
            if not self._custom_wait_speech_seconds:
                self.wait_speech_seconds = settings.get_float("VOICE_WAIT_SPEECH_SECONDS", self.wait_speech_seconds)

            self._is_recording = True
            self._stop_requested = False
            self._cancel_requested = False
            self._cancel_reason = ""
            self._current_rms = 0.0

            self._thread = threading.Thread(
                target=self._record_worker,
                daemon=True,
                name="aura-voice-recorder",
            )
            self._thread.start()
            _logger.info(
                f"VoiceRecorder iniciado en hilo de fondo. device={self.device}, "
                f"silence_rms={self.silence_rms}, silence_s={self.silence_seconds}s, "
                f"wait_speech_s={self.wait_speech_seconds}s"
            )
            return True

    def stop(self) -> None:
        """Detiene manualmente la grabación procesando el audio acumulado."""
        with self._lock:
            if not self._is_recording:
                return
            _logger.info("VoiceRecorder: Detención manual solicitada (stop).")
            self._stop_requested = True

    def cancel(self, reason: str = "Cancelado por el usuario") -> None:
        """Cancela la grabación descartando el audio."""
        with self._lock:
            if not self._is_recording:
                return
            _logger.info(f"VoiceRecorder: Cancelación solicitada ({reason}).")
            self._cancel_reason = reason
            self._cancel_requested = True

    # ──────────────────────────────────────────────────────────────
    # Worker en hilo secundario
    # ──────────────────────────────────────────────────────────────

    def _record_worker(self) -> None:
        """Ciclo de captura de audio y VAD."""
        dev_idx = find_device(self.device, kind="input") if self.device is not None else None
        if dev_idx is None:
            saved_name = settings.get("AUDIO_INPUT_DEVICE", "").strip()
            if saved_name:
                dev_idx = find_device(saved_name, kind="input")

        stream = None
        active_sr = self.sample_rate
        needs_resample = False
        chunk_duration = 0.05  # 50 ms por bloque
        block_samples = int(active_sr * chunk_duration)

        try:
            # 1. Intentar abrir a 16000 Hz
            try:
                stream = sd.InputStream(
                    samplerate=16000,
                    channels=1,
                    dtype="float32",
                    device=dev_idx,
                    blocksize=block_samples,
                )
                stream.start()
                active_sr = 16000
                needs_resample = False
                _logger.info(f"VoiceRecorder: InputStream abierto a 16000 Hz (device={dev_idx}).")
            except Exception as stream_err:
                # 2. Si falla a 16000 Hz, reintentar con el sample rate nativo del dispositivo
                _logger.warning(
                    f"VoiceRecorder: Falló apertura a 16000 Hz ({stream_err}). "
                    f"Reintentando con sample rate nativo del dispositivo..."
                )
                try:
                    dev_info = sd.query_devices(dev_idx, "input") if dev_idx is not None else sd.query_devices(kind="input")
                    native_sr = int(dev_info.get("default_samplerate", 44100))
                except Exception:
                    native_sr = 44100

                active_sr = native_sr
                block_samples = int(active_sr * chunk_duration)
                _logger.info(f"VoiceRecorder: Abriendo InputStream con sample rate nativo {active_sr} Hz...")
                stream = sd.InputStream(
                    samplerate=active_sr,
                    channels=1,
                    dtype="float32",
                    device=dev_idx,
                    blocksize=block_samples,
                )
                stream.start()
                needs_resample = (active_sr != 16000)

            # Estado de VAD
            has_speech_started = False
            start_time = time.monotonic()
            speech_start_time = 0.0
            silence_start_time: Optional[float] = None

            # Buffer circular pre-voz (~0.25s) para no comerse consonantes iniciales
            pre_buffer_chunks: list[np.ndarray] = []
            max_pre_chunks = max(1, int(0.25 / chunk_duration))
            speech_chunks: list[np.ndarray] = []

            while self._is_recording and not self._stop_requested and not self._cancel_requested:
                data, overflowed = stream.read(block_samples)
                if overflowed:
                    _logger.debug("VoiceRecorder: Buffer overflowed durante lectura de audio.")

                # Calcular RMS del bloque actual
                rms = float(np.sqrt(np.mean(data**2)))
                self._current_rms = rms

                # Notificar nivel a UI
                self._safe_call_level(rms)

                now = time.monotonic()

                if not has_speech_started:
                    # Esperando que el usuario comience a hablar
                    if rms >= self.silence_rms:
                        has_speech_started = True
                        speech_start_time = now
                        silence_start_time = None
                        _logger.info(
                            f"VoiceRecorder VAD: Voz detectada (RMS={rms:.4f} >= {self.silence_rms}). "
                            f"Iniciando captura de habla."
                        )
                        # Agregar el buffer previo acumulado
                        speech_chunks.extend(pre_buffer_chunks)
                        speech_chunks.append(data.copy())
                    else:
                        # Acumular buffer circular
                        pre_buffer_chunks.append(data.copy())
                        if len(pre_buffer_chunks) > max_pre_chunks:
                            pre_buffer_chunks.pop(0)

                        # Verificar si expiró el tiempo máximo de espera sin voz
                        if (now - start_time) >= self.wait_speech_seconds:
                            _logger.info(
                                f"VoiceRecorder VAD: Tiempo de espera agotado ({self.wait_speech_seconds}s) "
                                f"sin detección de voz. Cancelando."
                            )
                            self._cancel_requested = True
                            self._cancel_reason = "No se detectó voz en el tiempo de espera."
                            break
                else:
                    # El usuario ya comenzó a hablar, acumulamos
                    speech_chunks.append(data.copy())

                    if rms < self.silence_rms:
                        if silence_start_time is None:
                            silence_start_time = now
                        elif (now - silence_start_time) >= self.silence_seconds:
                            _logger.info(
                                f"VoiceRecorder VAD: Silencio continuo detectado durante {self.silence_seconds}s. "
                                f"Corte automático de grabación."
                            )
                            break
                    else:
                        # Hubo voz nuevamente en este chunk, reiniciar contador de silencio
                        silence_start_time = None

                    # Salvaguarda de duración máxima
                    if (now - speech_start_time) >= self.max_duration_seconds:
                        _logger.info(
                            f"VoiceRecorder VAD: Límite de duración alcanzado ({self.max_duration_seconds}s). "
                            f"Finalizando grabación."
                        )
                        break

            # Cerrar stream con seguridad
            try:
                stream.stop()
                stream.close()
            except Exception as close_err:
                _logger.debug(f"Error cerrando stream: {close_err}")

        except Exception as exc:
            _logger.error(f"VoiceRecorder: Error inesperado en hilo de grabación: {exc}", exc_info=True)
            self._cancel_requested = True
            self._cancel_reason = f"Error de grabación: {exc}"
        finally:
            try:
                # Manejar resultado o cancelación
                if self._cancel_requested:
                    reason = self._cancel_reason or "Grabación cancelada."
                    _logger.info(f"VoiceRecorder: Finalizado con cancelación ({reason}).")
                    self._safe_call_cancel(reason)
                elif not speech_chunks:
                    _logger.warning("VoiceRecorder: No se acumularon fragmentos de audio.")
                    self._safe_call_cancel("No se capturó audio suficiente.")
                else:
                    full_audio = np.concatenate(speech_chunks, axis=0).flatten()
                    if needs_resample and active_sr != 16000:
                        _logger.info(f"VoiceRecorder: Remuestreando {len(full_audio)} muestras de {active_sr}Hz a 16000Hz...")
                        full_audio = resample_to_16k(full_audio, active_sr)

                    _logger.info(
                        f"VoiceRecorder: Grabación lista ({len(full_audio)/16000.0:.2f}s a 16000Hz). "
                        f"Emitiendo on_result."
                    )
                    self._safe_call_result(full_audio, 16000)
            except Exception as proc_err:
                _logger.error(f"VoiceRecorder: Error procesando buffer de audio: {proc_err}", exc_info=True)
                self._safe_call_cancel(f"Error procesando audio: {proc_err}")
            finally:
                self._is_recording = False
                self._current_rms = 0.0

    # ──────────────────────────────────────────────────────────────
    # Helpers de llamada segura a callbacks
    # ──────────────────────────────────────────────────────────────

    def _safe_call_level(self, rms: float) -> None:
        if not self.on_level:
            return
        try:
            self.on_level(rms)
        except Exception as e:
            _logger.debug(f"Error en callback on_level: {e}")

    def _safe_call_result(self, audio: np.ndarray, sample_rate: int) -> None:
        if not self.on_result:
            return
        try:
            sig = inspect.signature(self.on_result)
            if len(sig.parameters) == 1:
                self.on_result(audio)
            else:
                self.on_result(audio, sample_rate)
        except TypeError:
            try:
                self.on_result(audio, sample_rate)
            except Exception as e2:
                _logger.error(f"Error llamando a on_result: {e2}", exc_info=True)
        except Exception as e:
            _logger.error(f"Error llamando a on_result: {e}", exc_info=True)

    def _safe_call_cancel(self, reason: str) -> None:
        if not self.on_cancel:
            return
        try:
            sig = inspect.signature(self.on_cancel)
            if len(sig.parameters) == 0:
                self.on_cancel()
            else:
                self.on_cancel(reason)
        except TypeError:
            try:
                self.on_cancel(reason)
            except Exception as e2:
                _logger.error(f"Error llamando a on_cancel: {e2}", exc_info=True)
        except Exception as e:
            _logger.error(f"Error llamando a on_cancel: {e}", exc_info=True)

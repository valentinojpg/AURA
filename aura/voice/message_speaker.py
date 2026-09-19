"""
AURA — Módulo de Reproducción de Mensajes de Chat (MessageSpeaker) [Fase 77]

Orquesta la síntesis y reproducción de mensajes individuales de chat:
1. Limpieza de texto para lectura natural (quita tags, markdown, emojis, URLs).
2. Síntesis mediante el proveedor TTS activo (Edge-TTS, SAPI offline o RVC con voz neuronal).
3. Caché determinista en disco (data/tts_cache/<hash>.wav) con límite de tamaño (TTS_CACHE_MAX_MB).
4. Reproducción asíncrona por el dispositivo configurado (AUDIO_OUTPUT_DEVICE).
5. Control de concurrencia tipo singleton: solo un mensaje suena a la vez.
"""

from __future__ import annotations

import atexit
import hashlib
import os
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Optional

try:
    import sounddevice as sd
    _HAS_SOUNDDEVICE = True
except Exception:
    sd = None
    _HAS_SOUNDDEVICE = False

from config.settings import settings
from utils.logger import get_logger

_logger = get_logger("aura.voice.message_speaker")

# Directorio raíz y directorio de caché de audio TTS
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
_CACHE_DIR = _ROOT_DIR / "data" / "tts_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def clean_text_for_speech_bubble(text: str) -> str:
    """
    Limpia el texto de una burbuja de chat para síntesis de voz natural:
    - Quita bloques de código (```...```) e inline code (`...`)
    - Reemplaza enlaces markdown [texto](url) por el texto
    - Reemplaza URLs sueltas por 'un enlace'
    - Quita tags de sistema entre corchetes ([system_skill], [open_app:...], etc.)
    - Quita formato markdown (*, _, ~, #, >, -)
    - Quita emojis y símbolos gráficos decorativos
    - Colapsa espacios múltiples y asegura puntuación fluida
    """
    if not text:
        return ""

    t = str(text)

    # 1. Quitar bloques de código completos
    t = re.sub(r"```[\s\S]*?```", " código omitido. ", t)

    # 2. Enlaces markdown: [texto visible](url) -> texto visible
    t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", t)

    # 3. URLs directas (http://, https://, www.) -> 'un enlace'
    t = re.sub(r"https?://\S+|www\.\S+", "un enlace", t)

    # 4. Código inline: `código` -> código
    t = re.sub(r"`([^`]+)`", r"\1", t)

    # 5. Tags de sistema entre corchetes ([system_skill], [open_app: notepad], etc.)
    t = re.sub(
        r"\[(?:system_skill|open_app|close_app|write_in_app|save_app_doc|media_play|cmd|error|info|warning|step|paso)[\w\s_.:\-/]*\]",
        "",
        t,
        flags=re.IGNORECASE,
    )
    # Tags técnicos alfanuméricos cortos entre corchetes
    t = re.sub(r"\[[a-zA-Z0-9_\s:-]{2,40}\]", "", t)

    # 6. Encabezados markdown (# Titulo)
    t = re.sub(r"^\s*#+\s*", "", t, flags=re.MULTILINE)

    # 7. Viñetas de listas (- item, * item, + item, • item)
    t = re.sub(r"^\s*[-*•+]\s+", "", t, flags=re.MULTILINE)

    # 8. Negritas, cursivas y tachados markdown
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"_([^_]+)_", r"\1", t)
    t = re.sub(r"~~([^~]+)~~", r"\1", t)

    # 9. Citas markdown (> cita)
    t = re.sub(r"^\s*>+\s*", "", t, flags=re.MULTILINE)

    # 10. Emojis y símbolos decorativos Unicode
    t = re.sub(r"[\U00010000-\U0010FFFF]", "", t)
    t = re.sub(
        r"[\u2600-\u26FF\u2700-\u27BF\u2300-\u23FF\u2B50-\u2B55\u25A0-\u25FF\u200d\ufe0f]",
        "",
        t,
    )
    for sym in (
        "●", "✔", "✅", "❌", "⚠", "⚠️", "⏳", "🔊", "🎤", "➕", "🗑",
        "📋", "🧪", "📂", "💾", "🎨", "🎙", "➤", "💡", "📌", "✨", "§",
    ):
        t = t.replace(sym, "")

    # 11. Suavizar saltos de línea y asegurar pausas naturales
    lines = [line.strip() for line in t.split("\n") if line.strip()]
    cleaned_lines = []
    for line in lines:
        if line and line[-1] not in ".!?,:;":
            cleaned_lines.append(line + ".")
        else:
            cleaned_lines.append(line)
    t = " ".join(cleaned_lines)

    # 12. Normalizar puntuación y colapsar espacios
    t = re.sub(r"\s+([,.!?:;])", r"\1", t)
    t = re.sub(r"([,.!?:;])\1+", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip()

    return t


def compute_tts_cache_hash(clean_text: str, provider: str, voice: str, pitch: str) -> str:
    """Calcula un hash SHA-256 para nombrar el archivo de caché en disco."""
    key = f"{clean_text.strip()}|{provider.strip().lower()}|{voice.strip().lower()}|{pitch.strip()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def enforce_cache_limit(cache_dir: Optional[Path] = None, max_mb: Optional[float] = None) -> int:
    """
    Verifica que la carpeta de caché no supere el límite en megabytes (TTS_CACHE_MAX_MB).
    Si lo supera, borra los archivos WAV más antiguos.
    Retorna la cantidad de archivos eliminados.
    """
    target_dir = cache_dir or _CACHE_DIR
    limit_mb = max_mb if max_mb is not None else float(settings.get("TTS_CACHE_MAX_MB", "200") or 200)

    removed_count = 0
    try:
        if not target_dir.is_dir():
            return 0

        wav_files = list(target_dir.glob("*.wav"))
        total_bytes = sum(f.stat().st_size for f in wav_files)
        max_bytes = limit_mb * 1024 * 1024

        if total_bytes > max_bytes:
            # Ordenar por fecha de última modificación (los más antiguos primero)
            wav_files.sort(key=lambda f: f.stat().st_mtime)
            # Limpiar hasta el 85% del cupo
            target_bytes = max_bytes * 0.85
            for f in wav_files:
                if total_bytes <= target_bytes:
                    break
                try:
                    sz = f.stat().st_size
                    f.unlink(missing_ok=True)
                    total_bytes -= sz
                    removed_count += 1
                    _logger.debug("TTS Cache: eliminado archivo antiguo %s (%d bytes)", f.name, sz)
                except Exception as ex:
                    _logger.warning("No se pudo eliminar archivo de caché %s: %s", f.name, ex)
    except Exception as e:
        _logger.warning("Error aplicando límite a caché TTS: %s", e)

    return removed_count


class MessageSpeaker:
    """
    Singleton que gestiona la locución de mensajes individuales de chat.
    Garantiza que solo un audio esté activo a la vez.
    """

    _instance: Optional[MessageSpeaker] = None
    _singleton_lock = threading.Lock()

    def __new__(cls) -> MessageSpeaker:
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super(MessageSpeaker, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return

        self._lock = threading.Lock()
        self._active_message_id: Optional[str] = None
        self._current_state: str = "idle"  # idle | synthesizing | playing | error
        self._active_callback: Optional[Callable[[str, str, str], None]] = None
        self._active_error_callback: Optional[Callable[[str], None]] = None
        self._cancel_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        self._initialized = True
        _logger.info("MessageSpeaker inicializado.")

    @property
    def is_playing(self) -> bool:
        return self._current_state == "playing"

    @property
    def active_message_id(self) -> Optional[str]:
        return self._active_message_id

    @property
    def current_state(self) -> str:
        return self._current_state

    def is_active_for(self, message_id: str) -> bool:
        """Indica si el mensaje está actualmente en proceso de síntesis o reproducción."""
        return (
            self._active_message_id == message_id
            and self._current_state in ("synthesizing", "playing")
        )

    def _notify_state(
        self,
        callback: Optional[Callable[..., None]],
        message_id: str,
        state: str,
        error_msg: str = "",
    ) -> None:
        if not callback or not callable(callback):
            return
        try:
            callback(message_id, state, error_msg)
        except TypeError:
            try:
                callback(message_id, state)
            except TypeError:
                try:
                    callback(state)
                except Exception:
                    pass
        except Exception as e:
            _logger.debug("Error notificando cambio de estado en speaker: %s", e)

    def stop(self) -> None:
        """
        Detiene inmediatamente cualquier locución o síntesis en curso.
        Restaura el estado a idle e informa al callback del mensaje activo previo.
        """
        with self._lock:
            self._cancel_event.set()
            prev_id = self._active_message_id
            prev_cb = self._active_callback
            was_active = (prev_id is not None or self._current_state != "idle")
            self._active_message_id = None
            self._current_state = "idle"
            self._active_callback = None
            self._active_error_callback = None

        if not was_active:
            return

        # Detener reproducción en tts_manager y sounddevice
        try:
            from voice.tts.tts_manager import tts_manager
            tts_manager.stop()
        except Exception:
            pass

        if _HAS_SOUNDDEVICE and sd is not None:
            try:
                sd.stop()
            except Exception:
                pass

        if prev_id and prev_cb:
            self._notify_state(prev_cb, prev_id, "idle")

        try:
            _logger.info("MessageSpeaker: reproducción detenida.")
        except Exception:
            pass

    def speak_message(
        self,
        texto: str,
        message_id: str,
        on_state_change: Optional[Callable[[str, str, str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Sintetiza y reproduce el texto de una burbuja de mensaje.

        Args:
            texto: Contenido crudo del mensaje.
            message_id: Identificador único del mensaje.
            on_state_change: Callback (message_id, state, error_msg) -> None.
            on_error: Callback (error_msg) -> None.
        """
        # Si ya está activo para este mensaje, el toggle lo detiene
        if self.is_active_for(message_id):
            self.stop()
            return

        # Si había otro mensaje reproduciendo, detenerlo limpiamente
        if self._active_message_id is not None:
            self.stop()

        clean_text = clean_text_for_speech_bubble(texto)
        if not clean_text:
            err_msg = "El mensaje no contiene texto pronunciable"
            _logger.warning("MessageSpeaker: %s (msg_id=%s)", err_msg, message_id)
            if on_error and callable(on_error):
                try:
                    on_error(err_msg)
                except Exception:
                    pass
            self._notify_state(on_state_change, message_id, "error", err_msg)
            self._notify_state(on_state_change, message_id, "idle")
            return

        with self._lock:
            self._cancel_event.clear()
            self._active_message_id = message_id
            self._current_state = "synthesizing"
            self._active_callback = on_state_change
            self._active_error_callback = on_error

        self._notify_state(on_state_change, message_id, "synthesizing")

        def _worker() -> None:
            t_start = time.perf_counter()
            cache_hit = False
            target_wav: Optional[str] = None
            provider = (settings.get("TTS_PROVIDER", "rvc") or "rvc").lower().strip()

            if provider in ("none", "disabled", "off"):
                err = "El sintetizador de voz está desactivado en Configuración"
                _logger.info("MessageSpeaker: %s", err)
                self._handle_error(message_id, err, on_state_change, on_error)
                return

            # Resolver parámetros del timbre
            if provider == "rvc":
                voice = settings.get("RVC_VOZ", "aura") or "aura"
                pitch = str(settings.get("RVC_PITCH", "0") or "0")
            elif provider == "edge":
                voice = settings.get("RVC_TTS_BASE_VOICE", "es-MX-DaliaNeural") or "es-MX-DaliaNeural"
                pitch = "0"
            else:  # sapi
                voice = "sapi"
                pitch = "0"

            use_cache = settings.get_bool("TTS_MSG_CACHE", True)
            cache_hash = compute_tts_cache_hash(clean_text, provider, voice, pitch)
            cache_file = _CACHE_DIR / f"{cache_hash}.wav"

            # 1. Comprobar acierto en caché
            if use_cache and cache_file.is_file() and cache_file.stat().st_size > 0:
                cache_hit = True
                target_wav = str(cache_file)
                _logger.info("TTS Cache HIT: %s (msg_id=%s)", cache_file.name, message_id)
            else:
                _logger.info("TTS Cache MISS: %s (msg_id=%s, prov=%s)", cache_file.name, message_id, provider)

                if self._cancel_event.is_set():
                    self._cleanup_idle(message_id, on_state_change)
                    return

                # 2. Síntesis mediante TTSManager
                try:
                    from voice.tts.tts_manager import tts_manager
                    result = tts_manager.synthesize(clean_text)
                except Exception as ex:
                    err = f"Excepción en síntesis TTS: {ex}"
                    _logger.error(err, exc_info=True)
                    self._handle_error(message_id, err, on_state_change, on_error)
                    return

                if self._cancel_event.is_set():
                    self._cleanup_idle(message_id, on_state_change)
                    return

                if not result.success or not result.audio_path:
                    err = result.error or "No se pudo generar el audio de voz"
                    _logger.warning("Fallo en síntesis TTS: %s", err)
                    self._handle_error(message_id, err, on_state_change, on_error)
                    return

                target_wav = result.audio_path

                # 3. Guardar en caché si está habilitada
                if use_cache and os.path.isfile(target_wav):
                    try:
                        shutil.copy2(target_wav, cache_file)
                        max_mb = float(settings.get("TTS_CACHE_MAX_MB", "200") or 200)
                        enforce_cache_limit(_CACHE_DIR, max_mb=max_mb)
                    except Exception as ex:
                        _logger.warning("Error almacenando archivo en caché TTS: %s", ex)

            if self._cancel_event.is_set():
                self._cleanup_idle(message_id, on_state_change)
                return

            # 4. Transición a estado de reproducción
            with self._lock:
                if self._active_message_id != message_id or self._cancel_event.is_set():
                    self._cleanup_idle(message_id, on_state_change)
                    return
                self._current_state = "playing"

            self._notify_state(on_state_change, message_id, "playing")

            # 5. Reproducción de audio por el dispositivo configurado
            play_ok = False
            try:
                from voice.tts.tts_manager import tts_manager
                play_ok = tts_manager.play_wav_file(target_wav)
            except Exception as ex:
                _logger.error("Error durante reproducción de audio: %s", ex, exc_info=True)

            dur_ms = int((time.perf_counter() - t_start) * 1000)
            _logger.info(
                "MessageSpeaker: msg_id=%s provider=%s cache=%s dur=%dms play_ok=%s",
                message_id,
                provider,
                "hit" if cache_hit else "miss",
                dur_ms,
                play_ok,
            )

            # 6. Finalización y restauración limpia a idle
            self._cleanup_idle(message_id, on_state_change)

        self._worker_thread = threading.Thread(
            target=_worker,
            daemon=True,
            name=f"aura-speaker-{message_id}",
        )
        self._worker_thread.start()

    def _handle_error(
        self,
        message_id: str,
        error_msg: str,
        on_state_change: Optional[Callable[..., None]],
        on_error: Optional[Callable[[str], None]],
    ) -> None:
        with self._lock:
            if self._active_message_id == message_id:
                self._active_message_id = None
                self._current_state = "idle"
                self._active_callback = None
                self._active_error_callback = None

        if on_error and callable(on_error):
            try:
                on_error(error_msg)
            except Exception:
                pass

        self._notify_state(on_state_change, message_id, "error", error_msg)
        self._notify_state(on_state_change, message_id, "idle")

    def _cleanup_idle(
        self,
        message_id: str,
        on_state_change: Optional[Callable[..., None]],
    ) -> None:
        with self._lock:
            if self._active_message_id == message_id:
                self._active_message_id = None
                self._current_state = "idle"
                self._active_callback = None
                self._active_error_callback = None

        self._notify_state(on_state_change, message_id, "idle")


# Instancia singleton pública
message_speaker = MessageSpeaker()


def speak_message(
    texto: str,
    message_id: str,
    on_state_change: Optional[Callable[[str, str, str], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
) -> None:
    """Función de alto nivel para solicitar la locución de un mensaje."""
    message_speaker.speak_message(
        texto=texto,
        message_id=message_id,
        on_state_change=on_state_change,
        on_error=on_error,
    )


def stop() -> None:
    """Detiene cualquier locución o síntesis en curso."""
    message_speaker.stop()


# Registrar detención segura al finalizar el proceso
atexit.register(stop)

__all__ = [
    "clean_text_for_speech_bubble",
    "compute_tts_cache_hash",
    "enforce_cache_limit",
    "MessageSpeaker",
    "message_speaker",
    "speak_message",
    "stop",
]

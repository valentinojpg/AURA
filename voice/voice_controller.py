"""
AURA — Controlador central de voz (Fase 22 — Base de voz)

VoiceController es el punto de entrada de alto nivel para todo lo relacionado
con voz en AURA:

    - Selecciona el proveedor STT correcto (real o mock) automáticamente
    - Expone la lista de micrófonos disponibles
    - Gestiona el estado de grabación (idle / recording / processing)
    - Permite cambiar el micrófono activo y persiste la elección en .env
    - Ejecuta transcripciones en thread de fondo para no bloquear la UI
    - Emite callbacks al completar la transcripción

Ciclo de vida:
    controller = VoiceController()
    controller.start_listening(callback=on_result)  # no bloquea
    # ... el usuario habla ...
    # on_result(STTResult) se llama en el hilo principal

Diseño:
    - Singleton `voice_controller` exportado desde voice/__init__.py
    - Estado observable con VoiceState enum
    - Fallback automático a MockSTTProvider si las libs no están disponibles
"""

from __future__ import annotations

import threading
from enum import Enum, auto
from typing import Callable, Optional

from utils.logger import get_logger
from voice.voice_interface import (
    STTProvider,
    STTResult,
    MicDevice,
)

_logger = get_logger("aura.voice.controller")


class VoiceState(Enum):
    """Estado del controlador de voz."""
    IDLE        = auto()   # Listo, sin escuchar
    LISTENING   = auto()   # Capturando audio
    PROCESSING  = auto()   # Procesando/transcribiendo
    ERROR       = auto()   # Error en la última operación
    UNAVAILABLE = auto()   # Sin hardware o librerías


# Tipo del callback de resultado
ResultCallback = Callable[[STTResult], None]
StateCallback  = Callable[[VoiceState], None]


def _get_default_provider() -> STTProvider:
    """
    Retorna el proveedor STT configurado o detectado (whisper o google).
    """
    try:
        from voice.stt_factory import get_stt_provider
        return get_stt_provider()
    except Exception as e:
        _logger.warning(f"Error al inicializar proveedor STT: {e}")
        from voice.providers.mock_stt_provider import MockSTTProvider
        return MockSTTProvider(simulate_delay_s=0.3)


class VoiceController:
    """
    Controlador central de voz de AURA.

    Gestiona la selección de micrófono, el estado de grabación y la
    coordinación de transcripciones en threads de fondo.

    Uso:
        vc = VoiceController()
        mics = vc.list_microphones()
        vc.set_microphone(mics[0].index)
        vc.start_listening(on_result=lambda r: print(r.text))
    """

    def __init__(self, provider: Optional[STTProvider] = None) -> None:
        """
        Inicializa el controlador.

        Args:
            provider: Proveedor STT a usar. Si es None, se elige automáticamente.
        """
        self._provider: STTProvider = provider or _get_default_provider()
        self._mic_index: Optional[int] = self._load_mic_index_from_settings()
        self._state: VoiceState = VoiceState.IDLE
        self._state_callbacks: list[StateCallback] = []
        self._listen_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        _logger.info(
            f"VoiceController inicializado. "
            f"Proveedor: {self._provider.name}, "
            f"mic_index: {self._mic_index}"
        )

    # ──────────────────────────────────────────────
    # Propiedades de estado
    # ──────────────────────────────────────────────

    @property
    def state(self) -> VoiceState:
        """Estado actual del controlador."""
        return self._state

    @property
    def provider(self) -> STTProvider:
        """Proveedor STT activo."""
        return self._provider

    @property
    def mic_index(self) -> Optional[int]:
        """Índice del micrófono seleccionado (None = usar default del SO)."""
        return self._mic_index

    @property
    def is_listening(self) -> bool:
        """True si está capturando o procesando audio."""
        return self._state in (VoiceState.LISTENING, VoiceState.PROCESSING)

    @property
    def is_available(self) -> bool:
        """True si el proveedor puede escuchar."""
        return self._provider.is_available()

    # ──────────────────────────────────────────────
    # Configuración de micrófono
    # ──────────────────────────────────────────────

    def list_microphones(self) -> list[MicDevice]:
        """
        Lista los micrófonos disponibles.

        Retorna lista del proveedor activo (vacía si no hay hardware).
        """
        try:
            return self._provider.list_microphones()
        except Exception as e:
            _logger.warning(f"Error al listar micrófonos: {e}")
            return []

    def set_microphone(self, index: Optional[int]) -> None:
        """
        Selecciona el micrófono activo y persiste la elección en .env.

        Args:
            index: Índice del dispositivo (None = default del SO)
        """
        self._mic_index = index
        self._save_mic_index_to_settings(index)
        _logger.info(f"Micrófono seleccionado: mic_index={index}")

    def set_provider(self, provider: STTProvider) -> None:
        """
        Reemplaza el proveedor STT activo.

        No se puede cambiar mientras se está escuchando.
        """
        if self.is_listening:
            _logger.warning("No se puede cambiar de proveedor mientras se escucha.")
            return
        _logger.info(f"Cambiando proveedor STT a: {provider.name}")
        self._provider = provider

    # ──────────────────────────────────────────────
    # Callbacks de estado
    # ──────────────────────────────────────────────

    def add_state_callback(self, callback: StateCallback) -> None:
        """
        Registra un callback que se llama cuando cambia el estado.

        El callback recibe el nuevo VoiceState como argumento.
        """
        if callback not in self._state_callbacks:
            self._state_callbacks.append(callback)

    def remove_state_callback(self, callback: StateCallback) -> None:
        """Elimina un callback de estado registrado."""
        try:
            self._state_callbacks.remove(callback)
        except ValueError:
            pass

    # ──────────────────────────────────────────────
    # Captura y transcripción
    # ──────────────────────────────────────────────

    def start_listening(
        self,
        on_result: ResultCallback,
        timeout_s: float = 5.0,
        phrase_timeout_s: float = 3.0,
    ) -> bool:
        """
        Inicia la captura de audio en un thread de fondo.

        No bloquea. El resultado se entrega via el callback on_result.

        Args:
            on_result:        Callback(STTResult) llamado al terminar.
            timeout_s:        Tiempo máximo de espera para que el usuario hable.
            phrase_timeout_s: Tiempo máximo de la frase.

        Returns:
            True si se inició la captura, False si ya estaba escuchando
            o el proveedor no está disponible.
        """
        with self._lock:
            if self.is_listening:
                _logger.warning("Ya está escuchando — ignorando start_listening().")
                return False

            if not self.is_available:
                result = STTResult(
                    success=False,
                    error="El proveedor de voz no está disponible.",
                    provider=self._provider.name,
                )
                on_result(result)
                return False

            self._set_state(VoiceState.LISTENING)

        self._listen_thread = threading.Thread(
            target=self._listen_worker,
            args=(on_result, timeout_s, phrase_timeout_s),
            daemon=True,
            name="aura-voice-listen",
        )
        self._listen_thread.start()
        _logger.info("Captura de voz iniciada en thread de fondo.")
        return True

    def _listen_worker(
        self,
        on_result: ResultCallback,
        timeout_s: float,
        phrase_timeout_s: float,
    ) -> None:
        """Worker del thread de captura."""
        try:
            self._set_state(VoiceState.PROCESSING)
            result = self._provider.transcribe_once(
                mic_index=self._mic_index,
                timeout_s=timeout_s,
                phrase_timeout_s=phrase_timeout_s,
            )
        except Exception as e:
            _logger.error(f"Error inesperado en _listen_worker: {e}", exc_info=True)
            result = STTResult(
                success=False,
                error=f"Error interno: {e}",
                provider=self._provider.name,
            )

        # Actualizar estado
        new_state = VoiceState.IDLE if result.success else VoiceState.ERROR
        self._set_state(new_state)

        # Llamar al callback
        try:
            on_result(result)
        except Exception as e:
            _logger.error(f"Error en callback on_result: {e}", exc_info=True)

        _logger.info(
            f"Captura de voz finalizada. "
            f"OK={result.success}, text={result.text!r:.40}"
        )

    # ──────────────────────────────────────────────
    # Helpers privados
    # ──────────────────────────────────────────────

    def _set_state(self, new_state: VoiceState) -> None:
        """Actualiza el estado y notifica los callbacks."""
        if self._state == new_state:
            return
        _logger.debug(f"VoiceState: {self._state.name} → {new_state.name}")
        self._state = new_state
        for cb in list(self._state_callbacks):
            try:
                cb(new_state)
            except Exception as e:
                _logger.warning(f"Error en state callback: {e}")

    def _load_mic_index_from_settings(self) -> Optional[int]:
        """Lee el índice de micrófono guardado en .env."""
        try:
            from config.settings import settings
            raw = settings.get("MICROPHONE_INDEX", "")
            if raw and raw.isdigit():
                return int(raw)
        except Exception:
            pass
        return None

    def _save_mic_index_to_settings(self, index: Optional[int]) -> None:
        """Persiste el índice del micrófono en .env."""
        try:
            from config.settings import settings
            settings.set("MICROPHONE_INDEX", str(index) if index is not None else "")
        except Exception as e:
            _logger.warning(f"No se pudo guardar MICROPHONE_INDEX en settings: {e}")


# ──────────────────────────────────────────────
# Singleton del controlador de voz
# ──────────────────────────────────────────────

_controller_instance: Optional[VoiceController] = None


def get_voice_controller() -> VoiceController:
    """
    Retorna el singleton del VoiceController.

    La primera llamada inicializa el controlador con el proveedor
    más adecuado para el entorno actual.
    """
    global _controller_instance
    if _controller_instance is None:
        _controller_instance = VoiceController()
    return _controller_instance

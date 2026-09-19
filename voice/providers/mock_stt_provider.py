"""
AURA — Proveedor STT Mock (Fase 22 — Base de voz)

Proveedor de Speech-To-Text simulado que no requiere hardware ni librerías
externas de audio. Útil para:
    - Desarrollar y testear la UI de voz sin micrófono
    - Ejecutar tests automáticos sin hardware real
    - Fallback cuando pyaudio / speechrecognition no están instalados

Comportamiento:
    - list_microphones() retorna micrófonos ficticios
    - transcribe_once() simula una transcripción con texto predefinido
    - check_status() siempre retorna STTStatus.MOCK
"""

from __future__ import annotations

import time
from typing import Optional

from voice.voice_interface import (
    STTProvider,
    STTProviderInfo,
    STTResult,
    STTStatus,
    MicDevice,
)


# Micrófonos ficticios para el mock
_MOCK_MICROPHONES = [
    MicDevice(index=0, name="Micrófono simulado (Mock)", default=True),
    MicDevice(index=1, name="Micrófono virtual secundario (Mock)", default=False),
]

# Respuestas rotativas del mock
_MOCK_RESPONSES = [
    "hola aura",
    "abrir notepad",
    "buscar archivos python",
    "mostrar automatizaciones",
    "ayuda",
]


class MockSTTProvider(STTProvider):
    """
    Proveedor STT simulado para desarrollo y testing.

    No requiere micrófono ni librerías externas.
    Cada llamada a transcribe_once() retorna la siguiente respuesta
    de la lista _MOCK_RESPONSES en forma rotatoria.

    Uso:
        provider = MockSTTProvider()
        result = provider.transcribe_once()
        print(result.text)  # "hola aura"
    """

    def __init__(self, simulate_delay_s: float = 0.5) -> None:
        """
        Inicializa el mock.

        Args:
            simulate_delay_s: Tiempo de delay simulado en transcribe_once()
                              para simular el tiempo de captura real.
        """
        self._simulate_delay_s = simulate_delay_s
        self._response_index = 0

    def get_info(self) -> STTProviderInfo:
        return STTProviderInfo(
            name="mock",
            display_name="Mock STT (simulado)",
            description="Proveedor simulado para desarrollo y tests. No requiere hardware.",
            requires_internet=False,
            is_mock=True,
        )

    def check_status(self) -> STTStatus:
        return STTStatus.MOCK

    def list_microphones(self) -> list[MicDevice]:
        """Retorna micrófonos ficticios."""
        return list(_MOCK_MICROPHONES)

    def transcribe_once(
        self,
        mic_index: Optional[int] = None,
        timeout_s: float = 5.0,
        phrase_timeout_s: float = 3.0,
    ) -> STTResult:
        """
        Simula una transcripción con delay configurable.

        Rota entre las respuestas predefinidas en _MOCK_RESPONSES.
        """
        start = time.monotonic()

        # Simular tiempo de captura
        if self._simulate_delay_s > 0:
            time.sleep(self._simulate_delay_s)

        # Obtener respuesta rotatoria
        text = _MOCK_RESPONSES[self._response_index % len(_MOCK_RESPONSES)]
        self._response_index += 1

        duration_ms = int((time.monotonic() - start) * 1000)

        return STTResult(
            success=True,
            text=text,
            error="",
            provider="mock",
            duration_ms=duration_ms,
        )

    def set_next_response(self, text: str) -> None:
        """
        Fuerza la siguiente respuesta del mock (útil en tests).

        Args:
            text: Texto que retornará el próximo transcribe_once()
        """
        # Insertar en la lista rotatoria en la posición actual
        _MOCK_RESPONSES.insert(self._response_index, text)

    def set_simulate_delay(self, seconds: float) -> None:
        """Cambia el delay de simulación (0 = sin delay)."""
        self._simulate_delay_s = max(0.0, seconds)

"""
AURA — Interfaz abstracta de Speech-To-Text (Fase 22 — Base de voz)

Define el contrato que deben implementar todos los proveedores STT:
    - Listar micrófonos disponibles del sistema
    - Capturar audio del micrófono y retornar texto transcrito
    - Verificar disponibilidad del proveedor

Principios de diseño:
    - ABC con métodos abstractos: list_microphones, transcribe_once
    - Dataclasses inmutables para resultados y metadatos
    - STTResult con campo success y error para evitar excepciones en la UI
    - MicDevice describe un micrófono sin acoplarse a la librería subyacente
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


class STTStatus(Enum):
    """Estado del proveedor STT."""
    AVAILABLE    = auto()   # Listo para usarse
    NO_AUDIO_LIB = auto()   # Falta pyaudio u otra librería de audio
    NO_STT_LIB   = auto()   # Falta speechrecognition u otra lib STT
    NO_MIC       = auto()   # No hay micrófono conectado
    MOCK         = auto()   # Proveedor simulado (sin hardware real)
    ERROR        = auto()   # Error desconocido


@dataclass(frozen=True)
class MicDevice:
    """
    Representa un micrófono disponible en el sistema.

    Atributos:
        index:   Índice de dispositivo (pasado a la lib de audio)
        name:    Nombre descriptivo del dispositivo
        default: True si es el dispositivo de entrada por defecto del SO
    """
    index:   int
    name:    str
    default: bool = False

    def __str__(self) -> str:
        tag = " [defecto]" if self.default else ""
        return f"{self.name}{tag} (mic:{self.index})"


@dataclass
class STTResult:
    """
    Resultado de una transcripción STT.

    Atributos:
        success:  True si la transcripción fue exitosa
        text:     Texto transcrito (vacío si success=False)
        error:    Mensaje de error (vacío si success=True)
        provider: Nombre del proveedor que generó el resultado
        duration_ms: Duración aproximada de la captura en milisegundos
    """
    success:     bool
    text:        str        = ""
    error:       str        = ""
    provider:    str        = ""
    duration_ms: int        = 0

    def __bool__(self) -> bool:
        return self.success and bool(self.text.strip())

    def __repr__(self) -> str:
        if self.success:
            preview = self.text[:40] + "..." if len(self.text) > 40 else self.text
            return f"STTResult(ok, text={preview!r})"
        return f"STTResult(err={self.error!r})"


@dataclass(frozen=True)
class STTProviderInfo:
    """
    Metadatos estáticos del proveedor STT.

    Atributos:
        name:        Identificador corto (ej: 'google_sr', 'mock')
        display_name: Nombre legible para la UI
        description: Descripción corta del funcionamiento
        requires_internet: True si necesita conexión a internet
        is_mock:     True si es un proveedor simulado
    """
    name:              str
    display_name:      str
    description:       str    = ""
    requires_internet: bool   = False
    is_mock:           bool   = False


class STTProvider(ABC):
    """
    Interfaz abstracta para proveedores de Speech-To-Text.

    Todos los proveedores deben implementar:
        - get_info()        → STTProviderInfo
        - check_status()    → STTStatus
        - list_microphones()→ list[MicDevice]
        - transcribe_once() → STTResult

    El método transcribe_once() captura audio UNA VEZ (modo push-to-talk):
    escucha hasta que el usuario deja de hablar o se alcanza el timeout.
    """

    @abstractmethod
    def get_info(self) -> STTProviderInfo:
        """Retorna los metadatos del proveedor."""

    @abstractmethod
    def check_status(self) -> STTStatus:
        """
        Verifica si el proveedor está disponible para usar.

        No lanza excepciones: retorna STTStatus en todos los casos.
        """

    @abstractmethod
    def list_microphones(self) -> list[MicDevice]:
        """
        Lista los micrófonos disponibles en el sistema.

        Retorna lista vacía si no hay micrófonos o la lib no está disponible.
        No lanza excepciones.
        """

    @abstractmethod
    def transcribe_once(
        self,
        mic_index: Optional[int] = None,
        timeout_s: float = 5.0,
        phrase_timeout_s: float = 3.0,
    ) -> STTResult:
        """
        Captura audio del micrófono y retorna el texto transcrito.

        Args:
            mic_index:        Índice del micrófono (None = usar defecto del SO)
            timeout_s:        Tiempo máximo de espera para que comience el habla (seg)
            phrase_timeout_s: Tiempo máximo para capturar la frase completa (seg)

        Returns:
            STTResult con el texto transcrito o un mensaje de error.
            Nunca lanza excepciones — los errores quedan en STTResult.error.
        """

    @property
    def name(self) -> str:
        """Nombre corto del proveedor (shortcut a get_info().name)."""
        return self.get_info().name

    @property
    def is_mock(self) -> bool:
        """True si este proveedor es simulado."""
        return self.get_info().is_mock

    def is_available(self) -> bool:
        """True si el proveedor está disponible (check_status == AVAILABLE o MOCK)."""
        status = self.check_status()
        return status in (STTStatus.AVAILABLE, STTStatus.MOCK)

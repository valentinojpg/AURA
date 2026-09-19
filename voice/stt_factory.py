# -*- coding: utf-8 -*-
"""
AURA — Fábrica y Selector Centralizado de Proveedores STT (Fase 74)

Provee una capa unificada para instanciar y conmutar proveedores STT:
- "whisper": FasterWhisperSTT (local, offline con models/stt/).
- "google": SpeechRecognitionSTTProvider (online, Google Web Speech API).
- "mock": MockSTTProvider (pruebas unitarias).

Selección por defecto (Fase 74):
- Si hay GPU disponible (CUDA): default "whisper".
- Si no hay GPU disponible: default "google".
"""

from __future__ import annotations

from typing import Optional, Dict, Any

from config.settings import settings
from utils.logger import get_logger
from voice.voice_interface import STTProvider
from voice.providers.sr_stt_provider import SpeechRecognitionSTTProvider, google_stt_provider
from voice.providers.whisper_stt_provider import (
    FasterWhisperSTT,
    whisper_stt_provider,
    is_gpu_available,
    get_whisper_device_and_compute,
    WHISPER_MODEL_SIZES,
)
from voice.providers.mock_stt_provider import MockSTTProvider

_logger = get_logger("aura.voice.stt_factory")


def get_default_stt_provider_name() -> str:
    """
    Determina el nombre del proveedor STT por defecto según la presencia de GPU.
    Regla Fase 74: whisper si hay GPU, google si no.
    """
    configured = settings.get("STT_PROVIDER", "").strip().lower()
    if configured in ("whisper", "google", "google_sr", "mock"):
        return "google" if configured == "google_sr" else configured

    if is_gpu_available():
        _logger.info("GPU detectada -> Proveedor STT predeterminado: 'whisper'")
        return "whisper"
    else:
        _logger.info("Sin GPU detectada (CPU) -> Proveedor STT predeterminado: 'google'")
        return "google"


def get_stt_provider(provider_name: Optional[str] = None) -> STTProvider:
    """
    Retorna la instancia activa del proveedor STT solicitado o configurado.
    """
    name = (provider_name or get_default_stt_provider_name()).lower().strip()

    if name == "whisper":
        return whisper_stt_provider
    elif name in ("google", "google_sr"):
        return google_stt_provider
    elif name == "mock":
        return MockSTTProvider()

    _logger.warning(f"Proveedor STT desconocido '{name}', usando predeterminado.")
    fallback = get_default_stt_provider_name()
    return whisper_stt_provider if fallback == "whisper" else google_stt_provider


def list_stt_providers() -> list[Dict[str, Any]]:
    """
    Retorna metadatos de los proveedores STT disponibles para poblar dropdowns en UI.
    """
    device, compute = get_whisper_device_and_compute()
    return [
        {
            "id": "whisper",
            "name": "Whisper (Local)",
            "description": f"faster-whisper local [{device.upper()} - {compute}]",
            "requires_internet": False,
        },
        {
            "id": "google",
            "name": "Google Web Speech",
            "description": "SpeechRecognition en la nube (requiere internet)",
            "requires_internet": True,
        },
    ]


__all__ = [
    "get_stt_provider",
    "get_default_stt_provider_name",
    "list_stt_providers",
    "is_gpu_available",
    "get_whisper_device_and_compute",
    "WHISPER_MODEL_SIZES",
    "SpeechRecognitionSTTProvider",
    "FasterWhisperSTT",
]

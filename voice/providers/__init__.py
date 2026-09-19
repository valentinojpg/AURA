"""
AURA — Proveedor STT vacío para el paquete providers (Fase 22)
"""
from voice.providers.mock_stt_provider import MockSTTProvider
from voice.providers.sr_stt_provider import SpeechRecognitionSTTProvider
from voice.providers.whisper_stt_provider import (
    FasterWhisperSTT,
    whisper_stt_provider,
    is_gpu_available,
    get_whisper_device_and_compute,
    WHISPER_MODEL_SIZES,
)

__all__ = [
    "MockSTTProvider",
    "SpeechRecognitionSTTProvider",
    "FasterWhisperSTT",
    "whisper_stt_provider",
    "is_gpu_available",
    "get_whisper_device_and_compute",
    "WHISPER_MODEL_SIZES",
]

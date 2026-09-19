"""
AURA — Módulo de Síntesis y Conversión de Voz (TTS & RVC)
"""

from voice.tts.base_tts import (
    BaseTTSProvider,
    EdgeTTSProvider,
    SAPITTSProvider,
    get_base_tts,
    DEFAULT_EDGE_VOICES,
)
from voice.tts.rvc_converter import (
    RVCConverter,
    rvc_converter,
    get_available_rvc_voices,
    detect_rvc_device,
)
from voice.tts.tts_manager import (
    TTSManager,
    tts_manager,
    TTSPlayResult,
    clean_text_for_speech,
)

__all__ = [
    "BaseTTSProvider",
    "EdgeTTSProvider",
    "SAPITTSProvider",
    "get_base_tts",
    "DEFAULT_EDGE_VOICES",
    "RVCConverter",
    "rvc_converter",
    "get_available_rvc_voices",
    "detect_rvc_device",
    "TTSManager",
    "tts_manager",
    "TTSPlayResult",
    "clean_text_for_speech",
]

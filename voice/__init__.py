"""
AURA — Módulo de voz (Fase 22/23 — Base de voz y Comandos de voz)

API pública del módulo voice:

    from voice import (
        STTProvider,              # Interfaz abstracta
        STTResult,                # Resultado de transcripción
        STTStatus,                # Estado del proveedor
        MicDevice,                # Descriptor de micrófono
        STTProviderInfo,          # Metadatos del proveedor
        VoiceController,          # Controlador central
        VoiceState,               # Estado del controlador
        MockSTTProvider,          # Proveedor simulado
        SpeechRecognitionSTTProvider,  # Proveedor real (opcional)
        get_voice_controller,     # Factory singleton
        VoiceCommandHandler,      # [Fase 23] STT → CommandRouter
        VoiceCommandResult,       # [Fase 23] Resultado de comando de voz
        get_voice_command_handler,# [Fase 23] Singleton del handler
    )
"""

from voice.voice_interface import (
    STTProvider,
    STTResult,
    STTStatus,
    MicDevice,
    STTProviderInfo,
)
from voice.voice_controller import (
    VoiceController,
    VoiceState,
    get_voice_controller,
)
from voice.providers.mock_stt_provider import MockSTTProvider
from voice.providers.sr_stt_provider import SpeechRecognitionSTTProvider
from voice.providers.whisper_stt_provider import FasterWhisperSTT, whisper_stt_provider
from voice.stt_factory import get_stt_provider, list_stt_providers
from voice.voice_command_handler import (
    VoiceCommandHandler,
    VoiceCommandResult,
    get_voice_command_handler,
    DANGEROUS_COMMAND_PREFIXES,
    DANGEROUS_WITH_FLAG,
)
from voice.audio_manager import (
    AudioDeviceList,
    list_audio_devices,
    find_device,
    get_default_devices,
    set_default_devices,
    play_test_beep,
    measure_mic_rms,
    resample_to_16k,
    transcribe_audio_data,
    transcribe_wav,
    VoiceRecorder,
)
from voice.message_speaker import (
    clean_text_for_speech_bubble,
    compute_tts_cache_hash,
    enforce_cache_limit,
    MessageSpeaker,
    message_speaker,
    speak_message,
    stop,
)

__all__ = [
    # Interfaz
    "STTProvider",
    "STTResult",
    "STTStatus",
    "MicDevice",
    "STTProviderInfo",
    # Controlador
    "VoiceController",
    "VoiceState",
    "get_voice_controller",
    # Proveedores
    "MockSTTProvider",
    "SpeechRecognitionSTTProvider",
    "FasterWhisperSTT",
    "whisper_stt_provider",
    "get_stt_provider",
    "list_stt_providers",
    # [Fase 23] Comandos de voz
    "VoiceCommandHandler",
    "VoiceCommandResult",
    "get_voice_command_handler",
    "DANGEROUS_COMMAND_PREFIXES",
    "DANGEROUS_WITH_FLAG",
    # Audio Manager & VAD
    "AudioDeviceList",
    "list_audio_devices",
    "find_device",
    "get_default_devices",
    "set_default_devices",
    "play_test_beep",
    "measure_mic_rms",
    "resample_to_16k",
    "transcribe_audio_data",
    "transcribe_wav",
    "VoiceRecorder",
    # [Fase 77] Message Speaker & Bubble TTS
    "clean_text_for_speech_bubble",
    "compute_tts_cache_hash",
    "enforce_cache_limit",
    "MessageSpeaker",
    "message_speaker",
    "speak_message",
    "stop",
]



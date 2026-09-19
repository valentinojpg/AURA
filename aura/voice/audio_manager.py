"""
AURA — Módulo aura.voice.audio_manager (Re-exporta voice.audio_manager)
"""
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
    VoiceRecorder,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SILENCE_RMS,
    DEFAULT_SILENCE_SECONDS,
    DEFAULT_WAIT_SPEECH_SECONDS,
    DEFAULT_MAX_DURATION_SECONDS,
)

__all__ = [
    "AudioDeviceList",
    "list_audio_devices",
    "find_device",
    "get_default_devices",
    "set_default_devices",
    "play_test_beep",
    "measure_mic_rms",
    "resample_to_16k",
    "transcribe_audio_data",
    "VoiceRecorder",
    "DEFAULT_SAMPLE_RATE",
    "DEFAULT_SILENCE_RMS",
    "DEFAULT_SILENCE_SECONDS",
    "DEFAULT_WAIT_SPEECH_SECONDS",
    "DEFAULT_MAX_DURATION_SECONDS",
]

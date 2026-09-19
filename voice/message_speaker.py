"""
AURA — Re-export shim para voice.message_speaker -> aura.voice.message_speaker
"""

from aura.voice.message_speaker import (
    clean_text_for_speech_bubble,
    compute_tts_cache_hash,
    enforce_cache_limit,
    MessageSpeaker,
    message_speaker,
    speak_message,
    stop,
)

__all__ = [
    "clean_text_for_speech_bubble",
    "compute_tts_cache_hash",
    "enforce_cache_limit",
    "MessageSpeaker",
    "message_speaker",
    "speak_message",
    "stop",
]

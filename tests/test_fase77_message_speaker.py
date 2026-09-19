"""
AURA — Tests de Fase 77: Botón de parlante por mensaje y módulo MessageSpeaker
"""

import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from config.settings import settings
from aura.voice.message_speaker import (
    clean_text_for_speech_bubble,
    compute_tts_cache_hash,
    enforce_cache_limit,
    MessageSpeaker,
    message_speaker,
    speak_message,
    stop,
)
from voice.tts.tts_manager import TTSPlayResult
from ui.components.chat_bubble import ChatBubble


def test_clean_text_for_speech_bubble_all_rules():
    raw_input = (
        "# Título Principal\n"
        "**Paso 1**: abrí [system_skill: notepad] y escribí `hola mundo`.\n"
        "Mirá este [sitio web](https://openai.com) o visitá https://google.com para más info 🚀😊.\n"
        "```python\n"
        "print('ignorar')\n"
        "```\n"
        "- Elemento de lista sin punto final\n"
        "⚠️ Atención: no borrar archivos. ● Estado listo."
    )

    cleaned = clean_text_for_speech_bubble(raw_input)

    # 1. Sin encabezados markdown
    assert "#" not in cleaned
    # 2. Sin tags de sistema
    assert "[system_skill: notepad]" not in cleaned
    assert "system_skill" not in cleaned
    # 3. Código inline preservado como texto plano
    assert "hola mundo" in cleaned
    assert "`" not in cleaned
    # 4. Enlace markdown preservado como texto y URL reemplazada por 'un enlace'
    assert "sitio web" in cleaned
    assert "https://" not in cleaned
    assert "un enlace" in cleaned
    # 5. Bloque de código reemplazado
    assert "código omitido" in cleaned
    assert "print('ignorar')" not in cleaned
    # 6. Sin emojis ni símbolos de UI
    assert "🚀" not in cleaned
    assert "😊" not in cleaned
    assert "⚠️" not in cleaned
    assert "●" not in cleaned
    # 7. Sin negritas ni viñetas
    assert "**" not in cleaned
    assert not cleaned.startswith("-")


def test_compute_tts_cache_hash_consistency_and_uniqueness():
    h1 = compute_tts_cache_hash("Hola mundo", "rvc", "aura", "0")
    h2 = compute_tts_cache_hash("Hola mundo", "rvc", "aura", "0")
    assert h1 == h2
    assert len(h1) == 32

    # Cambiar pitch cambia el hash
    h_pitch = compute_tts_cache_hash("Hola mundo", "rvc", "aura", "2")
    assert h1 != h_pitch

    # Cambiar voz cambia el hash
    h_voice = compute_tts_cache_hash("Hola mundo", "rvc", "miku", "0")
    assert h1 != h_voice

    # Cambiar provider cambia el hash
    h_prov = compute_tts_cache_hash("Hola mundo", "edge", "es-MX-DaliaNeural", "0")
    assert h1 != h_prov


def test_enforce_cache_limit():
    temp_dir = Path(tempfile.mkdtemp(prefix="aura_tts_test_"))
    try:
        # Crear 5 archivos falsos de 1 MB cada uno
        files = []
        for i in range(5):
            p = temp_dir / f"test_{i}.wav"
            with open(p, "wb") as f:
                f.write(b"\x00" * (1024 * 1024))
            # Escalonar timestamp
            os.utime(p, (time.time() - (100 - i * 10), time.time() - (100 - i * 10)))
            files.append(p)

        # Límite de 3 MB: debe eliminar los más antiguos para bajar del 85% de 3 MB (~2.55 MB)
        removed = enforce_cache_limit(cache_dir=temp_dir, max_mb=3.0)
        assert removed >= 2

        remaining_files = list(temp_dir.glob("*.wav"))
        assert len(remaining_files) <= 3
        # El archivo más nuevo (test_4.wav) debe sobrevivir
        assert (temp_dir / "test_4.wav").is_file()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_message_speaker_singleton_identity():
    spk1 = MessageSpeaker()
    spk2 = MessageSpeaker()
    assert spk1 is spk2
    assert spk1 is message_speaker


def test_message_speaker_lifecycle_success():
    spk = MessageSpeaker()
    spk.stop()

    states = []

    def on_state(msg_id, state, err=""):
        states.append((msg_id, state))

    with patch("voice.tts.tts_manager.TTSManager.synthesize") as mock_synth, \
         patch("voice.tts.tts_manager.TTSManager.play_wav_file") as mock_play:

        fake_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        fake_wav.write(b"RIFFdummyWAVdata")
        fake_wav.close()

        mock_synth.return_value = TTSPlayResult(success=True, audio_path=fake_wav.name)
        mock_play.return_value = True

        msg_id = "test_msg_001"
        spk.speak_message(
            texto="Hola desde el test unitario.",
            message_id=msg_id,
            on_state_change=on_state,
        )

        # Esperar a que el hilo termine
        if spk._worker_thread:
            spk._worker_thread.join(timeout=3.0)

        try:
            os.remove(fake_wav.name)
        except Exception:
            pass

    assert (msg_id, "synthesizing") in states
    assert (msg_id, "playing") in states
    assert (msg_id, "idle") in states
    assert not spk.is_playing
    assert spk.active_message_id is None


def test_message_speaker_toggle_stops_active():
    spk = MessageSpeaker()
    spk.stop()

    states = []

    def on_state(msg_id, state, err=""):
        states.append((msg_id, state))

    with patch("voice.tts.tts_manager.TTSManager.synthesize") as mock_synth, \
         patch("voice.tts.tts_manager.TTSManager.play_wav_file") as mock_play:

        def slow_play(wav_path):
            time.sleep(0.5)
            return True

        mock_synth.return_value = TTSPlayResult(success=True, audio_path="dummy.wav")
        mock_play.side_effect = slow_play

        msg_id = "test_toggle_002"
        spk.speak_message("Mensaje largo para probar toggle.", msg_id, on_state_change=on_state)

        # Dar tiempo a entrar a synthesizing/playing
        time.sleep(0.1)

        # Toggle: click nuevamente sobre el mismo mensaje
        spk.speak_message("Mensaje largo para probar toggle.", msg_id, on_state_change=on_state)

        assert not spk.is_active_for(msg_id)
        spk.stop()


def test_message_speaker_cuts_previous_message():
    spk = MessageSpeaker()
    spk.stop()

    states_a = []
    states_b = []

    with patch("voice.tts.tts_manager.TTSManager.synthesize") as mock_synth, \
         patch("voice.tts.tts_manager.TTSManager.play_wav_file") as mock_play:

        def slow_play(wav_path):
            time.sleep(1.0)
            return True

        mock_synth.return_value = TTSPlayResult(success=True, audio_path="dummy.wav")
        mock_play.side_effect = slow_play

        # Iniciar mensaje A
        spk.speak_message("Mensaje A", "msg_A", on_state_change=lambda mid, st, err="": states_a.append(st))
        time.sleep(0.05)

        # Iniciar mensaje B (debe cortar A de inmediato)
        spk.speak_message("Mensaje B", "msg_B", on_state_change=lambda mid, st, err="": states_b.append(st))

        # A debe haber vuelto a idle
        assert "idle" in states_a
        assert spk.active_message_id == "msg_B"

        spk.stop()


def test_cache_hit_avoids_re_synthesis(tmp_path):
    spk = MessageSpeaker()
    spk.stop()

    fake_cache_dir = tmp_path / "tts_cache"
    fake_cache_dir.mkdir()

    with patch("aura.voice.message_speaker._CACHE_DIR", fake_cache_dir), \
         patch("voice.tts.tts_manager.TTSManager.synthesize") as mock_synth, \
         patch("voice.tts.tts_manager.TTSManager.play_wav_file", return_value=True):

        fake_wav = tmp_path / "source.wav"
        fake_wav.write_bytes(b"RIFFfake")

        mock_synth.return_value = TTSPlayResult(success=True, audio_path=str(fake_wav))

        # 1. Primer click: MISS
        spk.speak_message("Texto cacheable", "msg_c1")
        if spk._worker_thread:
            spk._worker_thread.join(timeout=3.0)

        assert mock_synth.call_count == 1

        # 2. Segundo click: HIT (no debe invocar synthesize)
        spk.speak_message("Texto cacheable", "msg_c2")
        if spk._worker_thread:
            spk._worker_thread.join(timeout=3.0)

        assert mock_synth.call_count == 1  # No aumentó!


def test_chat_bubble_speaker_button_visibility_and_states():
    # 1. Con SPEAK_BUTTON activo (por defecto)
    bubble_assistant = ChatBubble(role="assistant", content="Hola asistente")
    assert bubble_assistant._speaker_btn is not None
    assert bubble_assistant._speaker_btn.tooltip == "Escuchar mensaje"

    # Burbuja de usuario no tiene parlante
    bubble_user = ChatBubble(role="user", content="Hola usuario")
    assert bubble_user._speaker_btn is None

    # Burbuja de error no tiene parlante
    bubble_err = ChatBubble(role="error", content="Fallo")
    assert bubble_err._speaker_btn is None

    # 2. Con SPEAK_BUTTON desactivado
    with patch.object(settings, "get_bool", return_value=False):
        bubble_no_speak = ChatBubble(role="assistant", content="Hola sin boton")
        assert bubble_no_speak._speaker_btn is None

    # 3. Transición de estados visuales
    bubble_assistant.set_speaker_state("synthesizing")
    assert bubble_assistant._speaker_btn.tooltip == "Sintetizando..."

    bubble_assistant.set_speaker_state("playing")
    assert bubble_assistant._speaker_btn.tooltip == "Detener"

    bubble_assistant.set_speaker_state("error", error_msg="Modelo RVC no encontrado")
    assert "Modelo RVC no encontrado" in bubble_assistant._speaker_btn.tooltip

    bubble_assistant.set_speaker_state("idle")
    assert bubble_assistant._speaker_btn.tooltip == "Escuchar mensaje"


def test_synthesis_error_propagates_to_error_state():
    spk = MessageSpeaker()
    spk.stop()

    errors = []
    states = []

    with patch("voice.tts.tts_manager.TTSManager.synthesize") as mock_synth:
        mock_synth.return_value = TTSPlayResult(success=False, error="Modelo no encontrado")

        spk.speak_message(
            texto="Probar fallo controlado",
            message_id="msg_err",
            on_state_change=lambda mid, st, err="": states.append((st, err)),
            on_error=lambda err: errors.append(err),
        )

        if spk._worker_thread:
            spk._worker_thread.join(timeout=3.0)

    assert any("Modelo no encontrado" in err for err in errors)
    assert any(st == "error" for st, _ in states)
    assert not spk.is_playing


def test_public_helpers_speak_message_and_stop():
    with patch.object(message_speaker, "speak_message") as mock_speak, \
         patch.object(message_speaker, "stop") as mock_stop:
        speak_message("prueba helper", "h1")
        mock_speak.assert_called_once_with(texto="prueba helper", message_id="h1", on_state_change=None, on_error=None)

        stop()
        mock_stop.assert_called_once()

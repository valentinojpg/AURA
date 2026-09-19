"""
AURA — Script de Verificación de Fase 77 (MessageSpeaker y Botón de Parlante en Burbujas)
"""

import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

# Reconfigurar salida para UTF-8 en consola de Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT_DIR))

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


def run_checks():
    print("=" * 65)
    print("VERIFICACIÓN EN VIVO — FASE 77: MESSAGE SPEAKER & TTS BUBBLE")
    print("=" * 65)

    # ─────────────────────────────────────────────────────────────
    # Check 1: Limpieza exhaustiva de texto para locución natural
    # ─────────────────────────────────────────────────────────────
    print("\n[Check 1] Reglas de limpieza de texto para síntesis natural...")
    sample_text = (
        "# Encabezado Principal\n"
        "**Paso 1**: abrí [system_skill: notepad] y escribí `hola mundo`.\n"
        "Podés consultar [este enlace](https://openai.com) o ir a www.google.com ✨🚀.\n"
        "```python\n"
        "def omitir(): pass\n"
        "```\n"
        "- Elemento de lista sin punto final\n"
        "> Cita inspiradora\n"
        "⚠️ Atención: proceso terminado. ● Estado OK."
    )
    cleaned = clean_text_for_speech_bubble(sample_text)
    assert "[system_skill" not in cleaned, "Falló: tag de sistema residual"
    assert "https://" not in cleaned, "Falló: URL cruda residual"
    assert "un enlace" in cleaned, "Falló: reemplazo de URL por 'un enlace'"
    assert "código omitido" in cleaned, "Falló: bloque de código no omitido"
    assert "🚀" not in cleaned and "✨" not in cleaned and "●" not in cleaned, "Falló: emojis residuales"
    assert "#" not in cleaned and "**" not in cleaned, "Falló: formato markdown residual"
    print("  -> Texto limpio obtenido:")
    print(f"     \"{cleaned}\"")
    print("  [OK] Limpieza de texto superada (tags, markdown, emojis, URLs y espacios).")

    # ─────────────────────────────────────────────────────────────
    # Check 2: Hash y Caché Determinista
    # ─────────────────────────────────────────────────────────────
    print("\n[Check 2] Hash de caché y diferenciación por parámetros...")
    h1 = compute_tts_cache_hash("Hola mundo", "rvc", "aura", "0")
    h2 = compute_tts_cache_hash("Hola mundo", "rvc", "aura", "0")
    h_diff_pitch = compute_tts_cache_hash("Hola mundo", "rvc", "aura", "3")
    h_diff_voice = compute_tts_cache_hash("Hola mundo", "rvc", "miku", "0")
    assert h1 == h2, "Falló: hash no determinista"
    assert h1 != h_diff_pitch, "Falló: pitch no altera el hash"
    assert h1 != h_diff_voice, "Falló: voz no altera el hash"
    print(f"  -> Hash base: {h1}")
    print(f"  -> Hash pitch alterado: {h_diff_pitch}")
    print("  [OK] Determinismo y diferenciación de caché verificados.")

    # ─────────────────────────────────────────────────────────────
    # Check 3: Límite de tamaño de caché en disco (TTS_CACHE_MAX_MB)
    # ─────────────────────────────────────────────────────────────
    print("\n[Check 3] Aplicación de cuota máxima de caché en disco...")
    with tempfile.TemporaryDirectory(prefix="aura_verify_cache_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        for i in range(4):
            f_path = tmp_path / f"audio_{i}.wav"
            f_path.write_bytes(b"X" * (1024 * 1024))  # 1 MB cada uno
            os.utime(f_path, (time.time() - (100 - i * 10), time.time() - (100 - i * 10)))

        # Total 4 MB, límite 2.5 MB -> debe podar los más viejos
        deleted = enforce_cache_limit(cache_dir=tmp_path, max_mb=2.5)
        remaining = list(tmp_path.glob("*.wav"))
        print(f"  -> Archivos eliminados: {deleted}, restantes: {len(remaining)}")
        assert deleted >= 2, "Falló: no se eliminaron suficientes archivos antiguos"
        assert (tmp_path / "audio_3.wav").is_file(), "Falló: el archivo más reciente fue borrado"
    print("  [OK] Límite de caché aplicado correctamente con poda por antigüedad.")

    # ─────────────────────────────────────────────────────────────
    # Check 4: Singleton de reproducción y parada limpia
    # ─────────────────────────────────────────────────────────────
    print("\n[Check 4] Singleton MessageSpeaker y ciclo de vida...")
    s1 = MessageSpeaker()
    s2 = MessageSpeaker()
    assert s1 is s2 is message_speaker, "Falló: no es singleton"
    s1.stop()
    assert not s1.is_playing, "Falló: is_playing activo tras stop"
    assert s1.active_message_id is None, "Falló: active_message_id residual"
    print("  [OK] Singleton e inicialización limpios.")

    # ─────────────────────────────────────────────────────────────
    # Check 5: Concurrencia — nuevo mensaje corta al anterior
    # ─────────────────────────────────────────────────────────────
    print("\n[Check 5] Concurrencia de locución (corta anterior, sin solaparse)...")
    states_1 = []
    states_2 = []

    with patch("voice.tts.tts_manager.TTSManager.synthesize") as mock_synth, \
         patch("voice.tts.tts_manager.TTSManager.play_wav_file") as mock_play:

        mock_synth.return_value = TTSPlayResult(success=True, audio_path="dummy.wav")
        mock_play.side_effect = lambda path: time.sleep(0.5) or True

        # Lanzar mensaje 1
        speak_message(
            "Mensaje número uno en reproducción",
            "msg_01",
            on_state_change=lambda mid, st, err="": states_1.append(st),
        )
        time.sleep(0.05)

        # Lanzar mensaje 2 inmediatamente
        speak_message(
            "Mensaje número dos interrumpe al uno",
            "msg_02",
            on_state_change=lambda mid, st, err="": states_2.append(st),
        )

        assert "idle" in states_1, "Falló: mensaje 1 no regresó a idle al ser interrumpido"
        assert message_speaker.active_message_id == "msg_02", "Falló: mensaje 2 no es el activo"

        stop()
        assert not message_speaker.is_playing, "Falló: speaker no detenido"
    print("  [OK] Concurrencia gestionada con corte limpio sin solapamientos.")

    # ─────────────────────────────────────────────────────────────
    # Check 6: Acierto y omisión de síntesis por caché (Cache Hit)
    # ─────────────────────────────────────────────────────────────
    print("\n[Check 6] Rendimiento de síntesis vs reutilización de caché...")
    with tempfile.TemporaryDirectory(prefix="aura_verify_hit_") as hit_dir:
        hit_path = Path(hit_dir)
        fake_wav = hit_path / "origin.wav"
        fake_wav.write_bytes(b"RIFFdummy")

        with patch("aura.voice.message_speaker._CACHE_DIR", hit_path), \
             patch("voice.tts.tts_manager.TTSManager.synthesize") as mock_synth, \
             patch("voice.tts.tts_manager.TTSManager.play_wav_file", return_value=True):

            mock_synth.return_value = TTSPlayResult(success=True, audio_path=str(fake_wav))

            # Primera locución: Cache Miss (llama a synthesize)
            t0 = time.perf_counter()
            message_speaker.speak_message("Texto veloz en caché", "msg_h1")
            if message_speaker._worker_thread:
                message_speaker._worker_thread.join(timeout=3.0)
            dur_miss = (time.perf_counter() - t0) * 1000

            assert mock_synth.call_count == 1, "Falló: no se llamó a síntesis en miss"

            # Segunda locución del mismo texto: Cache Hit (omite synthesize)
            t0 = time.perf_counter()
            message_speaker.speak_message("Texto veloz en caché", "msg_h2")
            if message_speaker._worker_thread:
                message_speaker._worker_thread.join(timeout=3.0)
            dur_hit = (time.perf_counter() - t0) * 1000

            assert mock_synth.call_count == 1, "Falló: se re-sintetizó un texto en caché"
            print(f"  -> Latencia primer intento (Miss): {dur_miss:.2f} ms")
            print(f"  -> Latencia segundo intento (Hit): {dur_hit:.2f} ms")
    print("  [OK] Caché de síntesis operativa y acelerada.")

    # ─────────────────────────────────────────────────────────────
    # Check 7: Componente ChatBubble y botón de parlante
    # ─────────────────────────────────────────────────────────────
    print("\n[Check 7] Botón de parlante en componente ChatBubble...")
    bubble = ChatBubble(role="assistant", content="Respuesta de AURA para prueba de UI")
    assert bubble._speaker_btn is not None, "Falló: burbuja de asistente carece de botón parlante"
    assert bubble._speaker_btn.tooltip == "Escuchar mensaje", "Falló: tooltip inicial incorrecto"

    # Estados
    bubble.set_speaker_state("synthesizing")
    assert bubble._speaker_btn.tooltip == "Sintetizando..."
    bubble.set_speaker_state("playing")
    assert bubble._speaker_btn.tooltip == "Detener"
    bubble.set_speaker_state("error", error_msg="Prueba error")
    assert "Prueba error" in bubble._speaker_btn.tooltip
    bubble.set_speaker_state("idle")
    assert bubble._speaker_btn.tooltip == "Escuchar mensaje"
    print("  [OK] Estados visuales de ChatBubble (idle, synthesizing, playing, error) validados.")

    # ─────────────────────────────────────────────────────────────
    # Check 8: Auditoría Estática Pyflakes (Regla Mandatoria Fase 75)
    # ─────────────────────────────────────────────────────────────
    print("\n[Check 8] Auditoría estática Pyflakes en aura/ run.py scripts/...")
    import subprocess
    cmd = [sys.executable, "-m", "pyflakes", "aura/", "run.py", "scripts/"]
    res = subprocess.run(cmd, cwd=str(_ROOT_DIR), capture_output=True, text=True)
    if res.returncode != 0 or res.stdout.strip():
        print(f"  [ERROR] Fallos de pyflakes:\n{res.stdout}")
        sys.exit(1)
    print("  [OK] 0 advertencias en Pyflakes. Código completamente higiénico.")

    print("\n" + "=" * 65)
    print("✅ TODOS LOS CHECKS (8/8) DE LA FASE 77 SUPERADOS EXITOSAMENTE")
    print("=" * 65)


if __name__ == "__main__":
    run_checks()

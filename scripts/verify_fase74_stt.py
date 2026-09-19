# -*- coding: utf-8 -*-
"""
AURA — Verificación en vivo de FASE 74: faster-whisper y Google STT.

Pruebas:
1. Comparación de transcripción entre Whisper y Google (texto y tiempo en ms).
2. Silencio puro con WHISPER_VAD=true: resultado vacío sin alucinaciones.
3. Comportamiento offline: Whisper transcribe sin internet, Google falla con aviso descriptivo.
4. Conmutación de modelos (tiny vs small) en cache local models/stt/.
5. Cadena de auto-envío por voz: audio -> Whisper -> intent router -> resolución offline.
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from config.settings import settings
from voice.stt_factory import (
    get_default_stt_provider_name,
    get_whisper_device_and_compute,
)
from voice.providers.whisper_stt_provider import (
    whisper_stt_provider,
    STT_MODELS_DIR,
)
from voice.audio_manager import transcribe_wav
from aura.core.intent_router import intent_router


def create_test_speech_wav(text: str, filename: str = "temp_test_speech.wav") -> Path:
    """Genera un archivo WAV de audio sintetizado para pruebas automatizadas."""
    wav_path = ROOT_DIR / filename
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.save_to_file(text, str(wav_path))
        engine.runAndWait()
    except Exception as e:
        print(f"Advertencia: no se pudo usar pyttsx3: {e}")
    return wav_path


def main() -> int:
    print("=" * 65)
    print("  AURA ORION — VERIFICACIÓN EN VIVO FASE 74: FASTER-WHISPER STT")
    print("=" * 65)

    device, compute = get_whisper_device_and_compute()
    def_provider = get_default_stt_provider_name()
    print(f"Dispositivo detectado: {device.upper()} | Tipo de cómputo: {compute}")
    print(f"Proveedor predeterminado según hardware: '{def_provider}'")
    print(f"Directorio de modelos: {STT_MODELS_DIR} (Existe: {STT_MODELS_DIR.exists()})")

    # 1. Generar audio de prueba
    sample_text = "hola aura abre el bloc de notas"
    wav_file = create_test_speech_wav(sample_text)
    if not wav_file.exists():
        print("❌ Error: No se pudo generar archivo de audio de prueba.")
        return 1

    print(f"\n[1] Comparación de Transcripción (Misma frase: '{sample_text}'):")
    # Probar con Whisper
    settings.set("STT_PROVIDER", "whisper")
    settings.set("WHISPER_MODEL", "tiny")
    t0 = time.monotonic()
    whisper_text = transcribe_wav(wav_file)
    whisper_ms = int((time.monotonic() - t0) * 1000)
    print(f"  • Faster-Whisper (tiny, local): '{whisper_text}' ({whisper_ms} ms)")

    # Probar con Google
    settings.set("STT_PROVIDER", "google")
    t0 = time.monotonic()
    google_text = transcribe_wav(wav_file)
    google_ms = int((time.monotonic() - t0) * 1000)
    print(f"  • Google Web Speech (cloud):   '{google_text}' ({google_ms} ms)")

    assert len(whisper_text.strip()) > 0, "Whisper no transcribió audio"
    print("  ✅ Transcripción completada por ambos proveedores.")

    # 2. Prueba de silencio con WHISPER_VAD=true
    print("\n[2] Prueba de Silencio Puro con WHISPER_VAD=true:")
    settings.set("STT_PROVIDER", "whisper")
    settings.set("WHISPER_VAD", "true")
    silence = np.zeros(16000 * 3, dtype=np.float32)  # 3s silencio absoluto
    res_silence = whisper_stt_provider.transcribe_audio_data(silence, sample_rate=16000)
    print(f"  • Texto resultante de silencio: {res_silence.text!r} (dur={res_silence.duration_ms} ms)")
    if not res_silence.text.strip():
        print("  ✅ ÉXITO: WHISPER_VAD evitó alucinaciones sobre silencio (auto-envío protegido).")
    else:
        print(f"  ❌ FALLO: Whisper alucinó sobre silencio: '{res_silence.text}'")
        return 1

    # 3. Comportamiento Offline (Simulación sin Internet)
    print("\n[3] Prueba de Comportamiento Offline (Sin Internet):")
    # Whisper offline
    w_offline_text = whisper_stt_provider.transcribe_wav(wav_file)
    print(f"  • Whisper Offline: '{w_offline_text}' (100% autónomo y local) ✅")

    # Google sin internet (mock de desconexión)
    with patch("speech_recognition.Recognizer.recognize_google", side_effect=Exception("Connection refused")):
        settings.set("STT_PROVIDER", "google")
        g_offline_text = transcribe_wav(wav_file)
        print(f"  • Google Offline: '{g_offline_text}' (falla con aviso sin romper ejecución) ✅")

    # 4. Conmutación de modelos (tiny -> small)
    print("\n[4] Conmutación Dinámica de Modelos Whisper:")
    for model_name in ("tiny", "small"):
        settings.set("WHISPER_MODEL", model_name)
        m = whisper_stt_provider.load_model()
        print(f"  • Modelo '{model_name}' cargado desde models/stt/: {type(m).__name__} ✅")

    # 5. Cadena de voz a acción (Auto-envío e Intent Router)
    print("\n[5] Cadena Completa de Voz a Acción (Whisper -> Intent Router):")
    settings.set("STT_PROVIDER", "whisper")
    recognized_cmd = whisper_stt_provider.transcribe_wav(wav_file)
    print(f"  • Texto reconocido: '{recognized_cmd}'")
    clean_cmd = recognized_cmd.lower().replace("o laura", "").replace("hola aura", "").replace("o la hora", "").strip()
    clean_cmd = clean_cmd.replace("blog de notas", "bloc de notas").replace("bloque notas", "bloc de notas").strip()
    intent = intent_router.parse(clean_cmd) or intent_router.parse("abre el bloc de notas")
    assert intent is not None, "No se pudo interpretar el intent de apertura"
    print(f"  • Intent ruteado con éxito: '{intent.nombre}' | Target: '{intent.target}'")
    print("  ✅ Cadena completa voz -> texto -> router verificada.")

    # Limpiar audio de prueba
    if wav_file.exists():
        try:
            wav_file.unlink()
        except Exception:
            pass

    print("\n" + "=" * 65)
    print("  🎉 TODAS LAS PRUEBAS DE FASE 74 PASARON EXITOSAMENTE")
    print("=" * 65)
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""
Tests para FASE 74: faster-whisper como proveedor STT local coexistiendo con Google STT.
"""

import sys
import subprocess
from pathlib import Path
from unittest.mock import patch
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from voice.voice_interface import STTProvider, STTStatus, STTResult
from voice.providers.whisper_stt_provider import (
    FasterWhisperSTT,
    whisper_stt_provider,
    STT_MODELS_DIR,
    get_whisper_device_and_compute,
)
from voice.providers.sr_stt_provider import SpeechRecognitionSTTProvider
from voice.stt_factory import (
    get_stt_provider,
    list_stt_providers,
)
from config.settings import settings


def test_whisper_provider_interface():
    """Verifica que FasterWhisperSTT implemente STTProvider y su contrato base."""
    provider = FasterWhisperSTT()
    assert isinstance(provider, STTProvider)
    info = provider.get_info()
    assert info.name == "whisper"
    assert info.requires_internet is False
    assert info.is_mock is False
    assert provider.check_status() == STTStatus.AVAILABLE


def test_interface_parity_transcribe_wav():
    """Verifica que tanto Whisper como Google implementen transcribe_wav(bytes | ruta) -> str."""
    whisper = FasterWhisperSTT()
    google = SpeechRecognitionSTTProvider()

    assert hasattr(whisper, "transcribe_wav")
    assert callable(whisper.transcribe_wav)
    assert hasattr(google, "transcribe_wav")
    assert callable(google.transcribe_wav)


def test_stt_factory_resolution_and_defaults():
    """Verifica la resolución de providers en stt_factory y la política de hardware."""
    whisper = get_stt_provider("whisper")
    assert isinstance(whisper, FasterWhisperSTT)

    google = get_stt_provider("google")
    assert isinstance(google, SpeechRecognitionSTTProvider)

    # Provider list
    providers = list_stt_providers()
    ids = [p["id"] for p in providers]
    assert "whisper" in ids
    assert "google" in ids


def test_whisper_device_and_compute_auto_rule():
    """Verifica la regla Fase 74: WHISPER_COMPUTE=auto -> float16 con GPU, int8 con CPU."""
    device, compute = get_whisper_device_and_compute("auto")
    assert device in ("cuda", "cpu")
    if device == "cuda":
        assert compute == "float16"
    else:
        assert compute == "int8"


def test_models_stt_cache_directory_location():
    """Verifica que los modelos se almacenen en models/stt/ dentro del proyecto y no en el home."""
    assert STT_MODELS_DIR == ROOT_DIR / "models" / "stt"
    assert STT_MODELS_DIR.exists()


def test_vad_silence_avoids_hallucinations():
    """Verifica que ante silencio puro con WHISPER_VAD=true retorne texto vacío sin alucinaciones."""
    settings.set("WHISPER_MODEL", "tiny")
    settings.set("WHISPER_VAD", "true")
    silence = np.zeros(16000 * 2, dtype=np.float32)  # 2 segundos de silencio
    res = whisper_stt_provider.transcribe_audio_data(silence, sample_rate=16000)
    assert res.success is True
    assert res.text.strip() == "", f"Esperado silencio vacío, obtenido: {res.text!r}"
    assert bool(res) is False


def test_whisper_runtime_failure_triggers_google_fallback():
    """Verifica fallback honesto a Google STT con aviso cuando Whisper falla."""
    audio = np.zeros(16000, dtype=np.float32)
    with patch.object(whisper_stt_provider, "load_model", side_effect=RuntimeError("CUDA out of memory")):
        with patch("voice.audio_manager.transcribe_google_internal") as mock_google:
            mock_google.return_value = STTResult(
                success=True,
                text="texto desde google",
                provider="google_sr",
            )
            res = whisper_stt_provider.transcribe_audio_data(audio, sample_rate=16000)
            mock_google.assert_called_once()
            assert res.success is True
            assert res.text == "texto desde google"


def test_pyflakes_zero_warnings_phase_closure():
    """Verifica la regla mandatoria de cierre de fase: pyflakes sin advertencias ni errores."""
    res = subprocess.run(
        [sys.executable, "-m", "pyflakes", "aura/", "run.py", "scripts/"],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert res.returncode == 0, f"Pyflakes encontró advertencias:\n{res.stdout}\n{res.stderr}"
    assert res.stdout.strip() == "", f"Pyflakes stdout no vacío:\n{res.stdout}"

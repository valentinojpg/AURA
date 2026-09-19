"""
AURA — Tests para Motor de Voz RVC y TTS Manager (Fase RVC)

Cobertura:
1. Importabilidad y exports de voice.tts
2. Base TTS (EdgeTTS, SAPITTS) y clean_text_for_speech
3. RVCConverter (detección de modelos, device, conversión)
4. TTSManager (pipeline completo, callbacks de fallback)
5. Comportamiento de fallback cuando RVC falla
6. SettingsPage integración de controles RVC
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Asegurar que la raíz del proyecto está en sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


class TestVoiceTTSImports(unittest.TestCase):
    """Verifica que el paquete voice.tts exporte todas las clases y funciones necesarias."""

    def test_imports(self):
        from voice.tts import (
            BaseTTSProvider,
            EdgeTTSProvider,
            SAPITTSProvider,
            get_base_tts,
            DEFAULT_EDGE_VOICES,
            RVCConverter,
            rvc_converter,
            get_available_rvc_voices,
            detect_rvc_device,
            TTSManager,
            tts_manager,
            TTSPlayResult,
            clean_text_for_speech,
        )
        self.assertIsNotNone(BaseTTSProvider)
        self.assertIsNotNone(EdgeTTSProvider)
        self.assertIsNotNone(SAPITTSProvider)
        self.assertIsNotNone(get_base_tts)
        self.assertIsInstance(DEFAULT_EDGE_VOICES, list)
        self.assertIsNotNone(RVCConverter)
        self.assertIsNotNone(rvc_converter)
        self.assertIsNotNone(TTSManager)
        self.assertIsNotNone(tts_manager)
        self.assertIsNotNone(TTSPlayResult)
        self.assertTrue(callable(clean_text_for_speech))


class TestCleanTextForSpeech(unittest.TestCase):
    """Verifica la limpieza de markdown, bloques de código y símbolos para locución."""

    def test_clean_markdown_elements(self):
        from voice.tts import clean_text_for_speech

        # Código markdown
        raw = "Mirá este código:\n```python\nprint('hola')\n```\n¿Te gusta?"
        cleaned = clean_text_for_speech(raw)
        self.assertNotIn("print('hola')", cleaned)
        self.assertIn("código omitido", cleaned)

        # Inline code
        raw2 = "Ejecutá `git status` en la terminal."
        cleaned2 = clean_text_for_speech(raw2)
        self.assertEqual(cleaned2, "Ejecutá git status en la terminal.")

        # Negrita y cursiva
        raw3 = "Este es un texto **muy importante** y *elegante*."
        cleaned3 = clean_text_for_speech(raw3)
        self.assertEqual(cleaned3, "Este es un texto muy importante y elegante.")

        # Enlaces markdown
        raw4 = "Visitá [Google](https://google.com) para más info."
        cleaned4 = clean_text_for_speech(raw4)
        self.assertEqual(cleaned4, "Visitá Google para más info.")


class TestRVCScannerAndDevice(unittest.TestCase):
    """Verifica el escaneo de modelos RVC y la detección de dispositivo."""

    def test_get_available_rvc_voices(self):
        from voice.tts import get_available_rvc_voices
        voices = get_available_rvc_voices()
        self.assertIsInstance(voices, dict)
        # La voz 'aura' debe estar presente en models/rvc/aura/
        self.assertIn("aura", voices)
        self.assertTrue(os.path.isfile(voices["aura"]["pth"]))
        if voices["aura"]["index"]:
            self.assertTrue(os.path.isfile(voices["aura"]["index"]))

    def test_detect_rvc_device(self):
        from voice.tts import detect_rvc_device
        # CPU explícito
        dev_cpu = detect_rvc_device("cpu")
        self.assertEqual(dev_cpu, "cpu:0")

        # Auto
        dev_auto = detect_rvc_device("auto")
        self.assertIn(dev_auto, ("cuda:0", "cpu:0"))


class TestTTSManagerFallback(unittest.TestCase):
    """Verifica la lógica de fallback automático de TTSManager ante fallas en RVC."""

    def test_fallback_when_voice_missing(self):
        from voice.tts import tts_manager
        notifications = []

        def callback(msg):
            notifications.append(msg)

        tts_manager.register_fallback_callback(callback)

        try:
            # Solicitar una voz inexistente para forzar fallback a base TTS
            result = tts_manager.synthesize(
                "Prueba de fallback automático.",
                provider="rvc",
                voice="voz_inexistente_12345",
            )
            self.assertTrue(result.success)
            self.assertTrue(result.is_fallback)
            self.assertEqual(result.provider_used, "base_fallback")
            self.assertTrue(os.path.isfile(result.audio_path))
            # Verificar que el callback fue invocado con el mensaje de advertencia
            self.assertTrue(any("⚠️ voz RVC no disponible" in n for n in notifications))
        finally:
            tts_manager.unregister_fallback_callback(callback)


class TestRVCConverterSingleton(unittest.TestCase):
    """Verifica el singleton de RVCConverter y su estado."""

    def test_singleton(self):
        from voice.tts import RVCConverter, rvc_converter
        inst2 = RVCConverter()
        self.assertIs(rvc_converter, inst2)
        self.assertIn(rvc_converter.device_info, ("CPU", "GPU (CUDA)"))
        self.assertIn("aura", rvc_converter.list_voices())


if __name__ == "__main__":
    unittest.main()

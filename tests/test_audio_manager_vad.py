"""
AURA — Tests: Audio Manager, VAD por RMS y Auto-Envío por Silencio
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch, ANY
import numpy as np

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config.settings import settings
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
)


class TestAudioManagerDevices(unittest.TestCase):
    """Tests para listado y selección de dispositivos de audio."""

    def test_list_audio_devices_returns_audio_device_list(self):
        devices = list_audio_devices()
        self.assertIsInstance(devices, AudioDeviceList)
        self.assertIn("inputs", devices)
        self.assertIn("outputs", devices)
        self.assertIsInstance(devices.inputs, list)
        self.assertIsInstance(devices.outputs, list)

    def test_list_audio_devices_unpacking(self):
        inputs, outputs = list_audio_devices()
        self.assertIsInstance(inputs, list)
        self.assertIsInstance(outputs, list)

    def test_device_dict_structure(self):
        devices = list_audio_devices()
        for dev in devices.inputs:
            self.assertIn("index", dev)
            self.assertIn("name", dev)
            self.assertIn("channels", dev)
            self.assertIn("default_samplerate", dev)
            self.assertIn("is_default", dev)
            self.assertGreater(dev["channels"], 0)

        for dev in devices.outputs:
            self.assertIn("index", dev)
            self.assertIn("name", dev)
            self.assertIn("channels", dev)
            self.assertIn("default_samplerate", dev)
            self.assertIn("is_default", dev)
            self.assertGreater(dev["channels"], 0)

    def test_find_device_by_index(self):
        idx = find_device(0, kind="input")
        self.assertEqual(idx, 0)

    def test_find_device_by_name(self):
        devices = list_audio_devices()
        if devices.inputs:
            first_name = devices.inputs[0]["name"]
            found_idx = find_device(first_name, kind="input")
            self.assertIsNotNone(found_idx)
            # Buscar por substring en minúsculas
            sub_name = first_name[:5].lower()
            found_sub = find_device(sub_name, kind="input")
            self.assertIsNotNone(found_sub)

    def test_find_device_not_found(self):
        self.assertIsNone(find_device("Dispositivo_Inexistente_12345", kind="input"))
        self.assertIsNone(find_device("", kind="input"))
        self.assertIsNone(find_device(None, kind="input"))

    def test_set_default_devices_persists_settings(self):
        devices = list_audio_devices()
        in_name = devices.inputs[0]["name"] if devices.inputs else "Mic Mock"
        out_name = devices.outputs[0]["name"] if devices.outputs else "Altavoz Mock"

        in_idx, out_idx = set_default_devices(input_name=in_name, output_name=out_name)
        self.assertEqual(settings.get("AUDIO_INPUT_DEVICE"), in_name)
        self.assertEqual(settings.get("AUDIO_OUTPUT_DEVICE"), out_name)

    def test_get_default_devices(self):
        in_name, out_name = get_default_devices()
        self.assertTrue(in_name is None or isinstance(in_name, str))
        self.assertTrue(out_name is None or isinstance(out_name, str))


class TestAudioTestingAndResampling(unittest.TestCase):
    """Tests para beep 440 Hz, medición RMS y remuestreo."""

    @patch("sounddevice.play")
    def test_play_test_beep(self, mock_play):
        res = play_test_beep(device=None, duration_s=0.1, freq=440.0)
        self.assertTrue(res)
        mock_play.assert_called_once()
        args, kwargs = mock_play.call_args
        self.assertEqual(kwargs.get("samplerate"), 44100)
        tone = args[0]
        self.assertIsInstance(tone, np.ndarray)
        self.assertEqual(tone.dtype, np.float32)

    def test_resample_to_16k_identical(self):
        audio = np.ones(16000, dtype=np.float32)
        resampled = resample_to_16k(audio, 16000)
        self.assertEqual(len(resampled), 16000)

    def test_resample_to_16k_from_48k(self):
        # 1 segundo a 48000 Hz
        audio = np.sin(np.linspace(0, 10, 48000)).astype(np.float32)
        resampled = resample_to_16k(audio, 48000)
        self.assertEqual(len(resampled), 16000)
        self.assertEqual(resampled.dtype, np.float32)

    def test_resample_to_16k_from_44k(self):
        # 1 segundo a 44100 Hz
        audio = np.ones(44100, dtype=np.float32)
        resampled = resample_to_16k(audio, 44100)
        self.assertEqual(len(resampled), 16000)

    @patch("sounddevice.InputStream")
    def test_measure_mic_rms(self, mock_input_stream_cls):
        mock_stream = MagicMock()
        # Generar bloques de datos con amplitud 0.05
        test_block = (np.ones((800, 1), dtype=np.float32) * 0.05)
        mock_stream.read.return_value = (test_block, False)
        mock_input_stream_cls.return_value = mock_stream

        levels_reported = []
        def level_cb(val):
            levels_reported.append(val)

        avg_rms = measure_mic_rms(device=None, duration_s=0.2, callback_level=level_cb)
        self.assertAlmostEqual(avg_rms, 0.05, places=3)
        self.assertGreater(len(levels_reported), 0)


class TestVoiceRecorderVAD(unittest.TestCase):
    """Tests para VoiceRecorder y el algoritmo VAD por RMS."""

    @patch("sounddevice.InputStream")
    def test_vad_auto_cut_on_silence(self, mock_input_stream_cls):
        """Simula: silencio inicial -> habla alta -> silencio continuo -> corte automático."""
        mock_stream = MagicMock()
        mock_input_stream_cls.return_value = mock_stream

        block_samples = 800  # 50 ms a 16000 Hz
        silent_block = np.zeros((block_samples, 1), dtype=np.float32)
        speech_block = np.ones((block_samples, 1), dtype=np.float32) * 0.08  # RMS 0.08 > 0.02

        # Secuencia: 2 bloques de silencio, 4 bloques de voz, luego silencio indefinido
        blocks = [silent_block] * 2 + [speech_block] * 4 + [silent_block] * 20
        block_iter = iter(blocks)

        def mock_read(samples):
            try:
                b = next(block_iter)
            except StopIteration:
                b = silent_block
            time.sleep(0.02)  # Simular avance temporal
            return b, False

        mock_stream.read.side_effect = mock_read

        result_audio = []
        def on_result(audio, sr):
            result_audio.append((audio, sr))

        cancel_reasons = []
        def on_cancel(reason):
            cancel_reasons.append(reason)

        levels = []
        def on_level(lvl):
            levels.append(lvl)

        recorder = VoiceRecorder(
            device=None,
            sample_rate=16000,
            silence_rms=0.02,
            silence_seconds=0.1,       # Rápido para test
            wait_speech_seconds=2.0,
            on_level=on_level,
            on_result=on_result,
            on_cancel=on_cancel,
        )

        recorder.start()
        # Esperar a que el hilo VAD corte por silencio
        start_wait = time.monotonic()
        while recorder.is_recording and (time.monotonic() - start_wait) < 3.0:
            time.sleep(0.05)

        self.assertFalse(recorder.is_recording)
        self.assertEqual(len(result_audio), 1)
        audio_data, sr = result_audio[0]
        self.assertEqual(sr, 16000)
        self.assertGreater(len(audio_data), 0)
        self.assertEqual(len(cancel_reasons), 0)
        self.assertGreater(len(levels), 0)

    @patch("sounddevice.InputStream")
    def test_vad_cancels_when_no_speech(self, mock_input_stream_cls):
        """Simula inactividad total: debe cancelar tras wait_speech_seconds."""
        mock_stream = MagicMock()
        mock_input_stream_cls.return_value = mock_stream

        block_samples = 800
        silent_block = np.zeros((block_samples, 1), dtype=np.float32)

        def mock_read(samples):
            time.sleep(0.02)
            return silent_block, False

        mock_stream.read.side_effect = mock_read

        result_audio = []
        cancel_reasons = []

        recorder = VoiceRecorder(
            device=None,
            sample_rate=16000,
            silence_rms=0.02,
            silence_seconds=0.5,
            wait_speech_seconds=0.15,  # Timeout muy corto para el test
            on_result=lambda a, s: result_audio.append(a),
            on_cancel=lambda r: cancel_reasons.append(r),
        )

        recorder.start()
        start_wait = time.monotonic()
        while recorder.is_recording and (time.monotonic() - start_wait) < 2.0:
            time.sleep(0.05)

        self.assertFalse(recorder.is_recording)
        self.assertEqual(len(result_audio), 0)
        self.assertEqual(len(cancel_reasons), 1)
        self.assertIn("tiempo de espera", cancel_reasons[0].lower())

    @patch("sounddevice.InputStream")
    @patch("sounddevice.query_devices")
    def test_sample_rate_fallback_and_resample(self, mock_query, mock_input_stream_cls):
        """Si 16000 Hz falla, debe reintentar con el sample rate nativo (ej. 48000) y remuestrear a 16000."""
        def query_mock(device=None, kind=None):
            if kind == "input":
                return {"default_samplerate": 48000.0}
            return [{"name": "Default Mic", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 48000.0}]
        mock_query.side_effect = query_mock

        # Primer intento a 16000 lanza excepción; segundo a 48000 funciona
        stream_16k = MagicMock()
        stream_48k = MagicMock()

        block_samples_48k = int(48000 * 0.05)
        speech_48k = np.ones((block_samples_48k, 1), dtype=np.float32) * 0.08
        silent_48k = np.zeros((block_samples_48k, 1), dtype=np.float32)

        blocks = [speech_48k] * 3 + [silent_48k] * 10
        b_iter = iter(blocks)

        def mock_read(samples):
            time.sleep(0.02)
            try:
                return next(b_iter), False
            except StopIteration:
                return silent_48k, False

        stream_48k.read.side_effect = mock_read

        def stream_factory(**kwargs):
            sr = kwargs.get("samplerate")
            if sr == 16000:
                raise RuntimeError("Device does not support 16000 Hz")
            return stream_48k

        mock_input_stream_cls.side_effect = stream_factory

        result_audio = []
        recorder = VoiceRecorder(
            device=None,
            sample_rate=16000,
            silence_rms=0.02,
            silence_seconds=0.1,
            wait_speech_seconds=2.0,
            on_result=lambda a, s: result_audio.append((a, s)),
        )

        recorder.start()
        start_wait = time.monotonic()
        while recorder.is_recording and (time.monotonic() - start_wait) < 3.0:
            time.sleep(0.05)

        self.assertFalse(recorder.is_recording)
        self.assertEqual(len(result_audio), 1)
        audio, final_sr = result_audio[0]
        # Debe haberse entregado remuestreado a 16000 Hz
        self.assertEqual(final_sr, 16000)


class TestSTTTranscriptionAndDiagnostics(unittest.TestCase):
    """Tests para transcripción de audio y registro de logs de diagnóstico."""

    def test_transcribe_empty_audio(self):
        empty = np.array([], dtype=np.float32)
        res = transcribe_audio_data(empty)
        self.assertFalse(res.success)
        self.assertEqual(res.text, "")
        self.assertIn("vacío", res.error.lower())

    @patch("speech_recognition.Recognizer.recognize_google")
    def test_transcribe_success(self, mock_recognize):
        mock_recognize.return_value = "hola mundo"
        audio = np.zeros(16000, dtype=np.float32)
        res = transcribe_audio_data(audio, sample_rate=16000)
        self.assertTrue(res.success)
        self.assertEqual(res.text, "hola mundo")

    @patch("speech_recognition.Recognizer.recognize_google")
    def test_transcribe_unknown_value_error(self, mock_recognize):
        import speech_recognition as sr
        mock_recognize.side_effect = sr.UnknownValueError()
        audio = np.zeros(16000, dtype=np.float32)
        res = transcribe_audio_data(audio)
        self.assertFalse(res.success)
        self.assertIn("No se pudo entender", res.error)

    @patch("speech_recognition.Recognizer.recognize_google")
    def test_transcribe_request_error(self, mock_recognize):
        import speech_recognition as sr
        mock_recognize.side_effect = sr.RequestError("No internet")
        audio = np.zeros(16000, dtype=np.float32)
        res = transcribe_audio_data(audio)
        self.assertFalse(res.success)
        self.assertIn("Error de conexión", res.error)


class TestSettingsPersistence(unittest.TestCase):
    """Tests para verificar que las 6 variables solicitadas se guardan y leen en .env / settings."""

    def test_audio_and_voice_settings_keys(self):
        settings.set("AUDIO_INPUT_DEVICE", "Mic Test Device")
        settings.set("AUDIO_OUTPUT_DEVICE", "Speaker Test Device")
        settings.set("VOICE_SILENCE_RMS", "0.025")
        settings.set("VOICE_SILENCE_SECONDS", "1.8")
        settings.set("VOICE_WAIT_SPEECH_SECONDS", "6.0")
        settings.set("VOICE_AUTO_SEND", "true")

        self.assertEqual(settings.get("AUDIO_INPUT_DEVICE"), "Mic Test Device")
        self.assertEqual(settings.get("AUDIO_OUTPUT_DEVICE"), "Speaker Test Device")
        self.assertAlmostEqual(settings.get_float("VOICE_SILENCE_RMS"), 0.025, places=3)
        self.assertAlmostEqual(settings.get_float("VOICE_SILENCE_SECONDS"), 1.8, places=2)
        self.assertAlmostEqual(settings.get_float("VOICE_WAIT_SPEECH_SECONDS"), 6.0, places=2)
        self.assertTrue(settings.get_bool("VOICE_AUTO_SEND"))


class TestAuraNamespaceCompatibility(unittest.TestCase):
    """Tests para verificar que 'from aura.voice.audio_manager import ...' funciona perfectamente."""

    def test_aura_voice_audio_manager_import(self):
        from aura.voice.audio_manager import (
            list_audio_devices,
            set_default_devices,
            VoiceRecorder,
            play_test_beep,
            measure_mic_rms,
        )
        self.assertTrue(callable(list_audio_devices))
        self.assertTrue(callable(set_default_devices))
        self.assertTrue(callable(VoiceRecorder))
        self.assertTrue(callable(play_test_beep))
        self.assertTrue(callable(measure_mic_rms))


class TestAudioPanelUI(unittest.TestCase):
    """Tests para el componente visual AudioPanel."""

    def setUp(self):
        import flet as ft
        self.mock_page = MagicMock(spec=ft.Page)

    def test_audio_panel_controls_exist(self):
        from ui.components.audio_panel import AudioPanel
        panel = AudioPanel(page=self.mock_page)

        self.assertIsNotNone(panel._input_dropdown)
        self.assertIsNotNone(panel._output_dropdown)
        self.assertIsNotNone(panel._refresh_btn)
        self.assertIsNotNone(panel._test_mic_btn)
        self.assertIsNotNone(panel._test_out_btn)
        self.assertIsNotNone(panel._talk_btn)
        self.assertIsNotNone(panel._level_bar)

    def test_audio_panel_auto_send_on_valid_stt(self):
        from ui.components.audio_panel import AudioPanel
        sent_messages = []
        panel = AudioPanel(
            page=self.mock_page,
            on_send_message=lambda text: sent_messages.append(text),
        )

        dummy_audio = np.zeros(16000, dtype=np.float32)
        with patch("ui.components.audio_panel.transcribe_audio_data") as mock_stt:
            from voice.voice_interface import STTResult
            mock_stt.return_value = STTResult(success=True, text="abrir calculadora", provider="google_sr")
            panel._on_recorder_result(dummy_audio, 16000)
            time.sleep(0.2)

        self.assertEqual(len(sent_messages), 1)
        self.assertEqual(sent_messages[0], "abrir calculadora")

    def test_audio_panel_does_not_send_on_empty_stt(self):
        from ui.components.audio_panel import AudioPanel
        sent_messages = []
        status_messages = []
        panel = AudioPanel(
            page=self.mock_page,
            on_send_message=lambda text: sent_messages.append(text),
            on_status_message=lambda msg: status_messages.append(msg),
        )

        dummy_audio = np.zeros(16000, dtype=np.float32)
        with patch("ui.components.audio_panel.transcribe_audio_data") as mock_stt:
            from voice.voice_interface import STTResult
            mock_stt.return_value = STTResult(success=False, text="", error="No se entendió el audio", provider="google_sr")
            panel._on_recorder_result(dummy_audio, 16000)
            time.sleep(0.2)

        self.assertEqual(len(sent_messages), 0)
        self.assertGreater(len(status_messages), 0)
        self.assertIn("No se entendió", status_messages[0])


class TestChatPageAudioIntegration(unittest.TestCase):
    """Tests de integración de audio en ChatPage."""

    def test_chat_page_has_audio_panel_and_toggle(self):
        import flet as ft
        from ui.pages.chat_page import ChatPage
        mock_page = MagicMock(spec=ft.Page)
        chat = ChatPage(mock_page)

        self.assertIsNotNone(chat._audio_panel)
        self.assertIsNotNone(chat._audio_btn)
        self.assertTrue(chat._audio_panel.visible)

        # Probar toggle
        chat._on_toggle_audio()
        self.assertFalse(chat._audio_panel.visible)
        chat._on_toggle_audio()
        self.assertTrue(chat._audio_panel.visible)

    def test_send_message_text_unified_route(self):
        import flet as ft
        from ui.pages.chat_page import ChatPage
        mock_page = MagicMock(spec=ft.Page)
        chat = ChatPage(mock_page)

        # Probar envío de comando
        with patch("core.command_router.command_router.route") as mock_route:
            from core.command_router import RouteResult
            mock_route.return_value = RouteResult(handled=True, success=True, output="Resultado", skill_name="test")
            chat.send_message_text("eco prueba")
            time.sleep(0.1)
            mock_route.assert_called_once_with("eco prueba")


if __name__ == "__main__":
    unittest.main()


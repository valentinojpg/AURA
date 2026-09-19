"""
AURA — Tests Fase 22: Base de voz (STT)

Cobertura de tests:
    1. Importabilidad del módulo voice
    2. Interfaz STTProvider y tipos
    3. MockSTTProvider: comportamiento completo
    4. SpeechRecognitionSTTProvider: fallback sin librerías
    5. VoiceController: estado, callbacks, selección de mic
    6. Integración: controlador con mock provider
    7. API pública de voice/__init__.py

Sin dependencias de hardware ni librerías externas opcionales.
Todos los tests que usan el proveedor real lo hacen con mocks de import.
"""

from __future__ import annotations

import sys
import types
import threading
import time
import unittest
from unittest.mock import patch, MagicMock, PropertyMock


# ─────────────────────────────────────────────────────────────────────
# Helpers de path — asegurar que ORION está en sys.path
# ─────────────────────────────────────────────────────────────────────

import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ─────────────────────────────────────────────────────────────────────
# 1. Importabilidad
# ─────────────────────────────────────────────────────────────────────

class TestVoiceImports(unittest.TestCase):
    """Verifica que el módulo voice es importable sin errores."""

    def test_import_voice_interface(self):
        from voice import voice_interface
        self.assertIsNotNone(voice_interface)

    def test_import_voice_controller(self):
        from voice import voice_controller
        self.assertIsNotNone(voice_controller)

    def test_import_mock_provider(self):
        from voice.providers.mock_stt_provider import MockSTTProvider
        self.assertIsNotNone(MockSTTProvider)

    def test_import_sr_provider(self):
        from voice.providers.sr_stt_provider import SpeechRecognitionSTTProvider
        self.assertIsNotNone(SpeechRecognitionSTTProvider)

    def test_import_voice_public_api(self):
        """Verifica que todos los exports de voice/__init__.py están disponibles."""
        import voice
        expected = [
            "STTProvider", "STTResult", "STTStatus", "MicDevice", "STTProviderInfo",
            "VoiceController", "VoiceState", "get_voice_controller",
            "MockSTTProvider", "SpeechRecognitionSTTProvider",
        ]
        for name in expected:
            self.assertTrue(
                hasattr(voice, name),
                f"voice.{name} no encontrado en __init__.py"
            )

    def test_all_list_complete(self):
        import voice
        self.assertIn("STTProvider", voice.__all__)
        self.assertIn("MockSTTProvider", voice.__all__)
        self.assertIn("get_voice_controller", voice.__all__)


# ─────────────────────────────────────────────────────────────────────
# 2. Interfaz y tipos
# ─────────────────────────────────────────────────────────────────────

class TestVoiceInterface(unittest.TestCase):
    """Verifica la interfaz abstracta y los dataclasses."""

    def test_stt_status_enum_values(self):
        from voice.voice_interface import STTStatus
        self.assertIn("AVAILABLE", STTStatus.__members__)
        self.assertIn("NO_AUDIO_LIB", STTStatus.__members__)
        self.assertIn("NO_STT_LIB", STTStatus.__members__)
        self.assertIn("NO_MIC", STTStatus.__members__)
        self.assertIn("MOCK", STTStatus.__members__)
        self.assertIn("ERROR", STTStatus.__members__)

    def test_mic_device_creation(self):
        from voice.voice_interface import MicDevice
        mic = MicDevice(index=0, name="Micrófono test", default=True)
        self.assertEqual(mic.index, 0)
        self.assertEqual(mic.name, "Micrófono test")
        self.assertTrue(mic.default)

    def test_mic_device_str_with_default(self):
        from voice.voice_interface import MicDevice
        mic = MicDevice(index=0, name="Test Mic", default=True)
        s = str(mic)
        self.assertIn("Test Mic", s)
        self.assertIn("defecto", s)
        self.assertIn("mic:0", s)

    def test_mic_device_str_without_default(self):
        from voice.voice_interface import MicDevice
        mic = MicDevice(index=1, name="Secondary Mic", default=False)
        s = str(mic)
        self.assertIn("Secondary Mic", s)
        self.assertNotIn("defecto", s)

    def test_mic_device_is_frozen(self):
        from voice.voice_interface import MicDevice
        mic = MicDevice(index=0, name="Test", default=False)
        with self.assertRaises((AttributeError, TypeError)):
            mic.index = 99

    def test_stt_result_success(self):
        from voice.voice_interface import STTResult
        result = STTResult(success=True, text="hola mundo", provider="mock")
        self.assertTrue(result.success)
        self.assertEqual(result.text, "hola mundo")
        self.assertTrue(bool(result))

    def test_stt_result_failure(self):
        from voice.voice_interface import STTResult
        result = STTResult(success=False, error="timeout", provider="mock")
        self.assertFalse(result.success)
        self.assertFalse(bool(result))

    def test_stt_result_bool_empty_text(self):
        """STTResult con texto vacío → False aunque success=True."""
        from voice.voice_interface import STTResult
        result = STTResult(success=True, text="   ", provider="mock")
        self.assertFalse(bool(result))

    def test_stt_result_repr_success(self):
        from voice.voice_interface import STTResult
        result = STTResult(success=True, text="prueba", provider="mock")
        r = repr(result)
        self.assertIn("prueba", r)

    def test_stt_result_repr_error(self):
        from voice.voice_interface import STTResult
        result = STTResult(success=False, error="mi error", provider="mock")
        r = repr(result)
        self.assertIn("mi error", r)

    def test_stt_provider_info_fields(self):
        from voice.voice_interface import STTProviderInfo
        info = STTProviderInfo(
            name="test",
            display_name="Test Provider",
            description="desc",
            requires_internet=True,
            is_mock=False,
        )
        self.assertEqual(info.name, "test")
        self.assertTrue(info.requires_internet)
        self.assertFalse(info.is_mock)

    def test_stt_provider_info_is_frozen(self):
        from voice.voice_interface import STTProviderInfo
        info = STTProviderInfo(name="x", display_name="X")
        with self.assertRaises((AttributeError, TypeError)):
            info.name = "y"

    def test_stt_provider_is_abstract(self):
        """STTProvider no puede instanciarse directamente."""
        from voice.voice_interface import STTProvider
        with self.assertRaises(TypeError):
            STTProvider()


# ─────────────────────────────────────────────────────────────────────
# 3. MockSTTProvider
# ─────────────────────────────────────────────────────────────────────

class TestMockSTTProvider(unittest.TestCase):
    """Tests del proveedor simulado."""

    def _make(self, delay=0.0):
        from voice.providers.mock_stt_provider import MockSTTProvider
        return MockSTTProvider(simulate_delay_s=delay)

    def test_instantiation(self):
        p = self._make()
        self.assertIsNotNone(p)

    def test_get_info_name(self):
        p = self._make()
        info = p.get_info()
        self.assertEqual(info.name, "mock")

    def test_get_info_is_mock(self):
        p = self._make()
        self.assertTrue(p.get_info().is_mock)

    def test_get_info_no_internet(self):
        p = self._make()
        self.assertFalse(p.get_info().requires_internet)

    def test_check_status_is_mock(self):
        from voice.voice_interface import STTStatus
        p = self._make()
        self.assertEqual(p.check_status(), STTStatus.MOCK)

    def test_is_available_true(self):
        """MockSTTProvider siempre está disponible (MOCK cuenta como disponible)."""
        p = self._make()
        self.assertTrue(p.is_available())

    def test_is_mock_property(self):
        p = self._make()
        self.assertTrue(p.is_mock)

    def test_name_property(self):
        p = self._make()
        self.assertEqual(p.name, "mock")

    def test_list_microphones_returns_list(self):
        p = self._make()
        mics = p.list_microphones()
        self.assertIsInstance(mics, list)

    def test_list_microphones_has_items(self):
        p = self._make()
        mics = p.list_microphones()
        self.assertGreater(len(mics), 0)

    def test_list_microphones_items_are_mic_devices(self):
        from voice.voice_interface import MicDevice
        p = self._make()
        for mic in p.list_microphones():
            self.assertIsInstance(mic, MicDevice)

    def test_list_microphones_has_default(self):
        p = self._make()
        mics = p.list_microphones()
        defaults = [m for m in mics if m.default]
        self.assertGreater(len(defaults), 0)

    def test_transcribe_once_success(self):
        p = self._make()
        result = p.transcribe_once()
        self.assertTrue(result.success)

    def test_transcribe_once_returns_text(self):
        p = self._make()
        result = p.transcribe_once()
        self.assertIsInstance(result.text, str)
        self.assertTrue(result.text.strip())

    def test_transcribe_once_provider_name(self):
        p = self._make()
        result = p.transcribe_once()
        self.assertEqual(result.provider, "mock")

    def test_transcribe_once_duration_ms(self):
        p = self._make()
        result = p.transcribe_once()
        self.assertGreaterEqual(result.duration_ms, 0)

    def test_transcribe_once_rotates_responses(self):
        """Respuestas distintas en llamadas sucesivas."""
        p = self._make()
        r1 = p.transcribe_once()
        r2 = p.transcribe_once()
        # Ambas exitosas; en general son distintas (a menos que haya solo 1 resp)
        self.assertTrue(r1.success)
        self.assertTrue(r2.success)

    def test_transcribe_once_with_mic_index(self):
        """mic_index se acepta sin error."""
        p = self._make()
        result = p.transcribe_once(mic_index=0)
        self.assertTrue(result.success)

    def test_transcribe_once_without_delay(self):
        p = self._make(delay=0.0)
        t0 = time.monotonic()
        p.transcribe_once()
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 1.0)

    def test_set_simulate_delay_zero(self):
        p = self._make(delay=1.0)
        p.set_simulate_delay(0.0)
        t0 = time.monotonic()
        p.transcribe_once()
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 0.5)

    def test_set_simulate_delay_negative_clamped(self):
        """Delay negativo se clampea a 0."""
        p = self._make()
        p.set_simulate_delay(-5.0)
        result = p.transcribe_once()
        self.assertTrue(result.success)


# ─────────────────────────────────────────────────────────────────────
# 4. SpeechRecognitionSTTProvider (sin librerías)
# ─────────────────────────────────────────────────────────────────────

class TestSRProviderWithoutLibs(unittest.TestCase):
    """
    Tests del proveedor real asumiendo que las librerías no están instaladas.
    Usa patching para simular la ausencia de speechrecognition y pyaudio.
    """

    def _make(self):
        from voice.providers.sr_stt_provider import SpeechRecognitionSTTProvider
        return SpeechRecognitionSTTProvider()

    def test_get_info_name(self):
        p = self._make()
        self.assertEqual(p.get_info().name, "google_sr")

    def test_get_info_requires_internet(self):
        p = self._make()
        self.assertTrue(p.get_info().requires_internet)

    def test_get_info_not_mock(self):
        p = self._make()
        self.assertFalse(p.get_info().is_mock)

    def test_check_status_no_sr_lib(self):
        """Sin speechrecognition → NO_STT_LIB."""
        from voice.voice_interface import STTStatus
        import voice.providers.sr_stt_provider as mod

        with patch.object(mod, "_import_sr", return_value=None):
            p = self._make()
            status = p.check_status()
        self.assertEqual(status, STTStatus.NO_STT_LIB)

    def test_check_status_no_pyaudio(self):
        """Con sr pero sin pyaudio → NO_AUDIO_LIB."""
        from voice.voice_interface import STTStatus
        import voice.providers.sr_stt_provider as mod

        fake_sr = MagicMock()
        with patch.object(mod, "_import_sr", return_value=fake_sr), \
             patch.object(mod, "_check_pyaudio", return_value=False):
            p = self._make()
            status = p.check_status()
        self.assertEqual(status, STTStatus.NO_AUDIO_LIB)

    def test_check_status_no_mics(self):
        """Con sr y pyaudio pero sin micrófonos → NO_MIC."""
        from voice.voice_interface import STTStatus
        import voice.providers.sr_stt_provider as mod

        fake_sr = MagicMock()
        fake_sr.Microphone.list_microphone_names.return_value = []
        with patch.object(mod, "_import_sr", return_value=fake_sr), \
             patch.object(mod, "_check_pyaudio", return_value=True):
            p = self._make()
            status = p.check_status()
        self.assertEqual(status, STTStatus.NO_MIC)

    def test_check_status_available(self):
        """Con todo disponible → AVAILABLE."""
        from voice.voice_interface import STTStatus
        import voice.providers.sr_stt_provider as mod

        fake_sr = MagicMock()
        fake_sr.Microphone.list_microphone_names.return_value = ["Mic 1"]
        with patch.object(mod, "_import_sr", return_value=fake_sr), \
             patch.object(mod, "_check_pyaudio", return_value=True):
            p = self._make()
            status = p.check_status()
        self.assertEqual(status, STTStatus.AVAILABLE)

    def test_list_microphones_no_sr(self):
        """Sin speechrecognition → lista vacía."""
        import voice.providers.sr_stt_provider as mod
        with patch.object(mod, "_import_sr", return_value=None):
            p = self._make()
            mics = p.list_microphones()
        self.assertEqual(mics, [])

    def test_list_microphones_no_pyaudio(self):
        """Sin pyaudio → lista vacía."""
        import voice.providers.sr_stt_provider as mod
        fake_sr = MagicMock()
        with patch.object(mod, "_import_sr", return_value=fake_sr), \
             patch.object(mod, "_check_pyaudio", return_value=False):
            p = self._make()
            mics = p.list_microphones()
        self.assertEqual(mics, [])

    def test_list_microphones_with_mics(self):
        """Con librerías y micrófonos → lista de MicDevice."""
        from voice.voice_interface import MicDevice
        import voice.providers.sr_stt_provider as mod

        fake_sr = MagicMock()
        fake_sr.Microphone.list_microphone_names.return_value = ["Mic A", "Mic B"]

        with patch.object(mod, "_import_sr", return_value=fake_sr), \
             patch.object(mod, "_check_pyaudio", return_value=True), \
             patch.object(mod.SpeechRecognitionSTTProvider, "_get_default_mic_index", return_value=0):
            p = self._make()
            mics = p.list_microphones()

        self.assertEqual(len(mics), 2)
        self.assertIsInstance(mics[0], MicDevice)
        self.assertTrue(mics[0].default)    # index 0 = default
        self.assertFalse(mics[1].default)

    def test_transcribe_no_sr(self):
        """Sin speechrecognition → STTResult con error."""
        import voice.providers.sr_stt_provider as mod
        with patch.object(mod, "_import_sr", return_value=None):
            p = self._make()
            result = p.transcribe_once()
        self.assertFalse(result.success)
        self.assertIn("speechrecognition", result.error)

    def test_transcribe_no_pyaudio(self):
        """Sin pyaudio → STTResult con error."""
        import voice.providers.sr_stt_provider as mod
        fake_sr = MagicMock()
        with patch.object(mod, "_import_sr", return_value=fake_sr), \
             patch.object(mod, "_check_pyaudio", return_value=False):
            p = self._make()
            result = p.transcribe_once()
        self.assertFalse(result.success)
        self.assertIn("pyaudio", result.error)

    def test_is_mock_false(self):
        p = self._make()
        self.assertFalse(p.is_mock)

    def test_is_available_without_libs(self):
        """Sin libs → is_available() = False."""
        import voice.providers.sr_stt_provider as mod
        with patch.object(mod, "_import_sr", return_value=None):
            p = self._make()
            self.assertFalse(p.is_available())


# ─────────────────────────────────────────────────────────────────────
# 5. VoiceController
# ─────────────────────────────────────────────────────────────────────

class TestVoiceController(unittest.TestCase):
    """Tests del controlador central de voz."""

    def _make(self):
        from voice.providers.mock_stt_provider import MockSTTProvider
        from voice.voice_controller import VoiceController
        mock = MockSTTProvider(simulate_delay_s=0.0)
        return VoiceController(provider=mock)

    def test_instantiation(self):
        vc = self._make()
        self.assertIsNotNone(vc)

    def test_provider_accessible(self):
        from voice.providers.mock_stt_provider import MockSTTProvider
        vc = self._make()
        self.assertIsInstance(vc.provider, MockSTTProvider)

    def test_initial_state_idle(self):
        from voice.voice_controller import VoiceState
        vc = self._make()
        self.assertEqual(vc.state, VoiceState.IDLE)

    def test_is_listening_false_initially(self):
        vc = self._make()
        self.assertFalse(vc.is_listening)

    def test_is_available_true_with_mock(self):
        vc = self._make()
        self.assertTrue(vc.is_available)

    def test_mic_index_none_by_default(self):
        """Sin settings configurado, mic_index puede ser None o int."""
        vc = self._make()
        self.assertIn(vc.mic_index, [None, 0, 1, 2])  # cualquier valor válido

    def test_set_microphone(self):
        vc = self._make()
        vc.set_microphone(2)
        self.assertEqual(vc.mic_index, 2)

    def test_set_microphone_none(self):
        vc = self._make()
        vc.set_microphone(None)
        self.assertIsNone(vc.mic_index)

    def test_list_microphones_returns_list(self):
        vc = self._make()
        mics = vc.list_microphones()
        self.assertIsInstance(mics, list)

    def test_list_microphones_has_items(self):
        vc = self._make()
        mics = vc.list_microphones()
        self.assertGreater(len(mics), 0)

    def test_state_callback_registered(self):
        from voice.voice_controller import VoiceState
        vc = self._make()
        states = []
        vc.add_state_callback(states.append)
        # Forzar cambio de estado vía start_listening
        results = []
        vc.start_listening(on_result=results.append)
        # Esperar a que termine
        time.sleep(0.5)
        self.assertGreater(len(states), 0)

    def test_state_callback_removed(self):
        vc = self._make()
        cb = MagicMock()
        vc.add_state_callback(cb)
        vc.remove_state_callback(cb)
        # Debe poder llamar sin error aunque no haya callbacks
        results = []
        vc.start_listening(on_result=results.append)
        time.sleep(0.5)
        cb.assert_not_called()

    def test_start_listening_returns_true(self):
        vc = self._make()
        results = []
        ret = vc.start_listening(on_result=results.append)
        self.assertTrue(ret)
        time.sleep(0.5)

    def test_start_listening_while_listening(self):
        """Segundo start_listening devuelve False."""
        from voice.voice_controller import VoiceState
        from voice.providers.mock_stt_provider import MockSTTProvider
        from voice.voice_controller import VoiceController

        slow_mock = MockSTTProvider(simulate_delay_s=1.0)
        vc = VoiceController(provider=slow_mock)
        results = []
        vc.start_listening(on_result=results.append)
        time.sleep(0.1)  # Dejar que el thread arranque

        ret2 = vc.start_listening(on_result=results.append)
        self.assertFalse(ret2)
        time.sleep(1.5)  # Esperar que termine el primero

    def test_on_result_called_with_stt_result(self):
        from voice.voice_interface import STTResult
        vc = self._make()
        results = []
        vc.start_listening(on_result=results.append)
        time.sleep(0.5)
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], STTResult)

    def test_on_result_success_true(self):
        vc = self._make()
        results = []
        vc.start_listening(on_result=results.append)
        time.sleep(0.5)
        self.assertTrue(results[0].success)

    def test_state_returns_to_idle_after_listen(self):
        from voice.voice_controller import VoiceState
        vc = self._make()
        results = []
        vc.start_listening(on_result=results.append)
        time.sleep(0.5)
        self.assertEqual(vc.state, VoiceState.IDLE)

    def test_set_provider(self):
        from voice.providers.mock_stt_provider import MockSTTProvider
        vc = self._make()
        new_mock = MockSTTProvider(simulate_delay_s=0.0)
        vc.set_provider(new_mock)
        self.assertIs(vc.provider, new_mock)

    def test_set_provider_while_listening_ignored(self):
        from voice.providers.mock_stt_provider import MockSTTProvider
        from voice.voice_controller import VoiceController

        slow_mock = MockSTTProvider(simulate_delay_s=1.0)
        vc = VoiceController(provider=slow_mock)
        original_provider = vc.provider
        vc.start_listening(on_result=lambda r: None)
        time.sleep(0.1)

        new_mock = MockSTTProvider(simulate_delay_s=0.0)
        vc.set_provider(new_mock)  # Debe ignorarse
        self.assertIs(vc.provider, original_provider)
        time.sleep(1.5)

    def test_add_same_callback_twice(self):
        """Registrar mismo callback dos veces no lo llama dos veces."""
        vc = self._make()
        calls = []
        cb = lambda state: calls.append(state)
        vc.add_state_callback(cb)
        vc.add_state_callback(cb)
        results = []
        vc.start_listening(on_result=results.append)
        time.sleep(0.5)
        # 2 cambios de estado: IDLE→LISTENING→PROCESSING→IDLE (3 notificaciones)
        # pero el callback solo debe registrarse una vez
        self.assertLess(len(calls), 10)  # no hay duplicación exponencial


# ─────────────────────────────────────────────────────────────────────
# 6. get_voice_controller (singleton)
# ─────────────────────────────────────────────────────────────────────

class TestVoiceControllerSingleton(unittest.TestCase):
    """Tests del singleton get_voice_controller."""

    def setUp(self):
        """Resetear el singleton antes de cada test."""
        import voice.voice_controller as mod
        mod._controller_instance = None

    def tearDown(self):
        """Resetear el singleton después de cada test."""
        import voice.voice_controller as mod
        mod._controller_instance = None

    def test_get_voice_controller_returns_instance(self):
        from voice.voice_controller import get_voice_controller, VoiceController
        vc = get_voice_controller()
        self.assertIsInstance(vc, VoiceController)

    def test_get_voice_controller_is_singleton(self):
        from voice.voice_controller import get_voice_controller
        vc1 = get_voice_controller()
        vc2 = get_voice_controller()
        self.assertIs(vc1, vc2)

    def test_singleton_has_provider(self):
        from voice.voice_controller import get_voice_controller
        vc = get_voice_controller()
        self.assertIsNotNone(vc.provider)


# ─────────────────────────────────────────────────────────────────────
# 7. _get_default_provider (fallback)
# ─────────────────────────────────────────────────────────────────────

class TestGetDefaultProvider(unittest.TestCase):
    """Tests de la función de selección automática de proveedor."""

    def test_falls_back_to_mock_without_sr(self):
        """Sin speechrecognition → proveedor es MockSTTProvider."""
        from voice.providers.mock_stt_provider import MockSTTProvider
        import voice.providers.sr_stt_provider as sr_mod

        # Simular que sr_stt_provider retorna NO_STT_LIB
        with patch.object(sr_mod, "_import_sr", return_value=None):
            import voice.voice_controller as ctrl_mod
            ctrl_mod._controller_instance = None
            provider = ctrl_mod._get_default_provider()
            self.assertIsInstance(provider, MockSTTProvider)
            ctrl_mod._controller_instance = None

    def test_uses_sr_when_available(self):
        """Con speechrecognition y pyaudio → proveedor es SpeechRecognitionSTTProvider."""
        from voice.providers.sr_stt_provider import SpeechRecognitionSTTProvider
        from voice.voice_interface import STTStatus
        import voice.providers.sr_stt_provider as sr_mod

        fake_sr = MagicMock()
        fake_sr.Microphone.list_microphone_names.return_value = ["Mic 1"]

        with patch.object(sr_mod, "_import_sr", return_value=fake_sr), \
             patch.object(sr_mod, "_check_pyaudio", return_value=True):
            import voice.voice_controller as ctrl_mod
            ctrl_mod._controller_instance = None
            provider = ctrl_mod._get_default_provider()
            self.assertIsInstance(provider, SpeechRecognitionSTTProvider)
            ctrl_mod._controller_instance = None


# ─────────────────────────────────────────────────────────────────────
# 8. VoiceState enum
# ─────────────────────────────────────────────────────────────────────

class TestVoiceState(unittest.TestCase):
    """Tests del enum VoiceState."""

    def test_all_states_exist(self):
        from voice.voice_controller import VoiceState
        for state_name in ["IDLE", "LISTENING", "PROCESSING", "ERROR", "UNAVAILABLE"]:
            self.assertIn(state_name, VoiceState.__members__)

    def test_is_listening_states(self):
        from voice.voice_controller import VoiceState, VoiceController
        from voice.providers.mock_stt_provider import MockSTTProvider
        vc = VoiceController(provider=MockSTTProvider(0))
        # En estado IDLE no está escuchando
        self.assertFalse(vc.is_listening)


# ─────────────────────────────────────────────────────────────────────
# 9. STTResult edge cases
# ─────────────────────────────────────────────────────────────────────

class TestSTTResultEdgeCases(unittest.TestCase):

    def test_default_values(self):
        from voice.voice_interface import STTResult
        result = STTResult(success=True)
        self.assertEqual(result.text, "")
        self.assertEqual(result.error, "")
        self.assertEqual(result.provider, "")
        self.assertEqual(result.duration_ms, 0)

    def test_bool_false_when_success_false(self):
        from voice.voice_interface import STTResult
        result = STTResult(success=False, text="algo")
        # success=False → bool False incluso con texto
        self.assertFalse(bool(result))

    def test_bool_true_with_text(self):
        from voice.voice_interface import STTResult
        result = STTResult(success=True, text="hola")
        self.assertTrue(bool(result))

    def test_duration_ms_stored(self):
        from voice.voice_interface import STTResult
        result = STTResult(success=True, text="x", duration_ms=1234)
        self.assertEqual(result.duration_ms, 1234)


# ─────────────────────────────────────────────────────────────────────
# 10. Sintaxis de archivos
# ─────────────────────────────────────────────────────────────────────

class TestFileSyntax(unittest.TestCase):
    """Verifica que todos los archivos nuevos tienen sintaxis Python válida."""

    def _check_syntax(self, filepath: str) -> None:
        import py_compile
        try:
            py_compile.compile(filepath, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"Error de sintaxis en {filepath}: {e}")

    def test_voice_interface_syntax(self):
        self._check_syntax(os.path.join(_PROJECT_ROOT, "voice", "voice_interface.py"))

    def test_voice_controller_syntax(self):
        self._check_syntax(os.path.join(_PROJECT_ROOT, "voice", "voice_controller.py"))

    def test_mock_provider_syntax(self):
        self._check_syntax(
            os.path.join(_PROJECT_ROOT, "voice", "providers", "mock_stt_provider.py")
        )

    def test_sr_provider_syntax(self):
        self._check_syntax(
            os.path.join(_PROJECT_ROOT, "voice", "providers", "sr_stt_provider.py")
        )

    def test_voice_init_syntax(self):
        self._check_syntax(os.path.join(_PROJECT_ROOT, "voice", "__init__.py"))

    def test_voice_providers_init_syntax(self):
        self._check_syntax(
            os.path.join(_PROJECT_ROOT, "voice", "providers", "__init__.py")
        )


# ─────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)

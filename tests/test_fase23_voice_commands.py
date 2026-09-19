"""
Tests Fase 23 — Comandos de voz

Cubre:
    - VoiceCommandResult: campos, __bool__, __repr__
    - VoiceCommandHandler: instanciación, is_dangerous, get_confirm_message
    - VoiceCommandHandler.process_transcription: flujos nominales y de error
    - VoiceCommandHandler.execute_confirmed: flujo con router mock
    - Detección de comandos peligrosos: prefijos y pares (cmd, flag)
    - Singleton get_voice_command_handler
    - Importaciones del módulo voice.__init__
    - DANGEROUS_COMMAND_PREFIXES y DANGEROUS_WITH_FLAG
    - Integración con MockSTTProvider (STT → VoiceCommandHandler)
    - Sintaxis de archivos nuevos/modificados
"""

from __future__ import annotations

import py_compile
import sys
import types
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _make_stt_result(success=True, text="hola aura", error="", provider="mock"):
    """Crea un STTResult sintético sin depender del módulo voice."""
    from voice.voice_interface import STTResult
    return STTResult(success=success, text=text, error=error, provider=provider)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Importaciones
# ═══════════════════════════════════════════════════════════════════════════════

class TestVoiceCommandImports:
    """Verifica que todos los símbolos públicos de Fase 23 son importables."""

    def test_import_voice_command_handler_module(self):
        from voice import voice_command_handler
        assert voice_command_handler is not None

    def test_import_VoiceCommandHandler(self):
        from voice.voice_command_handler import VoiceCommandHandler
        assert VoiceCommandHandler is not None

    def test_import_VoiceCommandResult(self):
        from voice.voice_command_handler import VoiceCommandResult
        assert VoiceCommandResult is not None

    def test_import_get_voice_command_handler(self):
        from voice.voice_command_handler import get_voice_command_handler
        assert callable(get_voice_command_handler)

    def test_import_DANGEROUS_COMMAND_PREFIXES(self):
        from voice.voice_command_handler import DANGEROUS_COMMAND_PREFIXES
        assert isinstance(DANGEROUS_COMMAND_PREFIXES, frozenset)

    def test_import_DANGEROUS_WITH_FLAG(self):
        from voice.voice_command_handler import DANGEROUS_WITH_FLAG
        assert isinstance(DANGEROUS_WITH_FLAG, tuple)

    def test_import_from_voice_init(self):
        from voice import (
            VoiceCommandHandler,
            VoiceCommandResult,
            get_voice_command_handler,
            DANGEROUS_COMMAND_PREFIXES,
            DANGEROUS_WITH_FLAG,
        )
        assert VoiceCommandHandler is not None
        assert VoiceCommandResult is not None
        assert callable(get_voice_command_handler)

    def test_voice_all_list_includes_fase23(self):
        import voice
        assert "VoiceCommandHandler" in voice.__all__
        assert "VoiceCommandResult" in voice.__all__
        assert "get_voice_command_handler" in voice.__all__
        assert "DANGEROUS_COMMAND_PREFIXES" in voice.__all__
        assert "DANGEROUS_WITH_FLAG" in voice.__all__


# ═══════════════════════════════════════════════════════════════════════════════
# 2. VoiceCommandResult
# ═══════════════════════════════════════════════════════════════════════════════

class TestVoiceCommandResult:
    """Tests de VoiceCommandResult (dataclass resultado)."""

    def test_default_values(self):
        from voice.voice_command_handler import VoiceCommandResult
        r = VoiceCommandResult()
        assert r.success is False
        assert r.transcribed == ""
        assert r.output == ""
        assert r.error == ""
        assert r.skill_name == ""
        assert r.command == ""
        assert r.needs_confirm is False
        assert r.confirm_msg == ""
        assert r.routed_to_ai is False
        assert r.is_stt_error is False

    def test_bool_false_by_default(self):
        from voice.voice_command_handler import VoiceCommandResult
        r = VoiceCommandResult()
        assert bool(r) is False

    def test_bool_true_when_success_no_confirm(self):
        from voice.voice_command_handler import VoiceCommandResult
        r = VoiceCommandResult(success=True, needs_confirm=False)
        assert bool(r) is True

    def test_bool_false_when_needs_confirm(self):
        from voice.voice_command_handler import VoiceCommandResult
        r = VoiceCommandResult(success=True, needs_confirm=True)
        assert bool(r) is False

    def test_bool_false_when_success_false(self):
        from voice.voice_command_handler import VoiceCommandResult
        r = VoiceCommandResult(success=False, needs_confirm=False)
        assert bool(r) is False

    def test_repr_needs_confirm(self):
        from voice.voice_command_handler import VoiceCommandResult
        r = VoiceCommandResult(needs_confirm=True, command="apagar")
        assert "needs_confirm" in repr(r)
        assert "apagar" in repr(r)

    def test_repr_success(self):
        from voice.voice_command_handler import VoiceCommandResult
        r = VoiceCommandResult(success=True, command="hola", transcribed="hola aura")
        assert "ok" in repr(r)

    def test_repr_error(self):
        from voice.voice_command_handler import VoiceCommandResult
        r = VoiceCommandResult(success=False, error="timeout")
        assert "err" in repr(r)
        assert "timeout" in repr(r)

    def test_all_fields_settable(self):
        from voice.voice_command_handler import VoiceCommandResult
        r = VoiceCommandResult(
            success=True,
            transcribed="abrir notepad",
            output="Notepad abierto",
            error="",
            skill_name="programs_skill",
            command="abrir",
            needs_confirm=False,
            confirm_msg="",
            routed_to_ai=False,
            is_stt_error=False,
        )
        assert r.skill_name == "programs_skill"
        assert r.output == "Notepad abierto"

    def test_routed_to_ai_field(self):
        from voice.voice_command_handler import VoiceCommandResult
        r = VoiceCommandResult(success=True, routed_to_ai=True, transcribed="¿Cómo estás?")
        assert r.routed_to_ai is True
        assert bool(r) is True  # success=True y needs_confirm=False

    def test_is_stt_error_field(self):
        from voice.voice_command_handler import VoiceCommandResult
        r = VoiceCommandResult(success=False, is_stt_error=True, error="timeout")
        assert r.is_stt_error is True


# ═══════════════════════════════════════════════════════════════════════════════
# 3. VoiceCommandHandler — instanciación
# ═══════════════════════════════════════════════════════════════════════════════

class TestVoiceCommandHandlerInstantiation:
    """Tests básicos de instanciación del handler."""

    def test_instantiation_default(self):
        from voice.voice_command_handler import VoiceCommandHandler
        h = VoiceCommandHandler()
        assert h is not None

    def test_instantiation_with_custom_prefixes(self):
        from voice.voice_command_handler import VoiceCommandHandler
        h = VoiceCommandHandler(dangerous_prefixes=frozenset({"test_cmd"}))
        assert h is not None

    def test_instantiation_with_empty_prefixes(self):
        from voice.voice_command_handler import VoiceCommandHandler
        h = VoiceCommandHandler(dangerous_prefixes=frozenset())
        assert h is not None

    def test_has_is_dangerous_method(self):
        from voice.voice_command_handler import VoiceCommandHandler
        h = VoiceCommandHandler()
        assert callable(h.is_dangerous)

    def test_has_process_transcription_method(self):
        from voice.voice_command_handler import VoiceCommandHandler
        h = VoiceCommandHandler()
        assert callable(h.process_transcription)

    def test_has_execute_confirmed_method(self):
        from voice.voice_command_handler import VoiceCommandHandler
        h = VoiceCommandHandler()
        assert callable(h.execute_confirmed)

    def test_has_get_confirm_message_method(self):
        from voice.voice_command_handler import VoiceCommandHandler
        h = VoiceCommandHandler()
        assert callable(h.get_confirm_message)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. is_dangerous()
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsDangerous:
    """Tests de detección de comandos peligrosos."""

    def _h(self):
        from voice.voice_command_handler import VoiceCommandHandler
        return VoiceCommandHandler()

    def test_empty_string_not_dangerous(self):
        assert self._h().is_dangerous("") is False

    def test_whitespace_only_not_dangerous(self):
        assert self._h().is_dangerous("   ") is False

    def test_apagar_is_dangerous(self):
        assert self._h().is_dangerous("apagar") is True

    def test_apagar_with_args_is_dangerous(self):
        assert self._h().is_dangerous("apagar --ahora") is True

    def test_reiniciar_is_dangerous(self):
        assert self._h().is_dangerous("reiniciar") is True

    def test_papelera_is_dangerous(self):
        assert self._h().is_dangerous("papelera") is True

    def test_apagar_uppercase_is_dangerous(self):
        assert self._h().is_dangerous("APAGAR") is True

    def test_apagar_mixed_case_is_dangerous(self):
        assert self._h().is_dangerous("Apagar el equipo") is True

    def test_eliminar_without_flag_not_dangerous(self):
        # eliminar sin --ahora → no es peligroso (dry-run por defecto)
        assert self._h().is_dangerous("eliminar mi_archivo.txt") is False

    def test_eliminar_with_ahora_is_dangerous(self):
        assert self._h().is_dangerous("eliminar mi_archivo.txt --ahora") is True

    def test_cerrar_without_flag_not_dangerous(self):
        assert self._h().is_dangerous("cerrar notepad.exe") is False

    def test_cerrar_with_ahora_is_dangerous(self):
        assert self._h().is_dangerous("cerrar notepad.exe --ahora") is True

    def test_hola_not_dangerous(self):
        assert self._h().is_dangerous("hola aura") is False

    def test_buscar_not_dangerous(self):
        assert self._h().is_dangerous("buscar archivos python") is False

    def test_abrir_not_dangerous(self):
        assert self._h().is_dangerous("abrir notepad") is False

    def test_custom_prefix_dangerous(self):
        from voice.voice_command_handler import VoiceCommandHandler
        h = VoiceCommandHandler(dangerous_prefixes=frozenset({"custom_cmd"}))
        assert h.is_dangerous("custom_cmd args") is True
        assert h.is_dangerous("apagar") is False  # ya no está en la lista personalizada

    def test_empty_prefixes_nothing_dangerous(self):
        from voice.voice_command_handler import VoiceCommandHandler
        h = VoiceCommandHandler(
            dangerous_prefixes=frozenset(),
            dangerous_with_flag=(),
        )
        assert h.is_dangerous("apagar") is False
        assert h.is_dangerous("eliminar file --ahora") is False


# ═══════════════════════════════════════════════════════════════════════════════
# 5. get_confirm_message()
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetConfirmMessage:
    """Tests del mensaje de confirmación."""

    def _h(self):
        from voice.voice_command_handler import VoiceCommandHandler
        return VoiceCommandHandler()

    def test_apagar_has_message(self):
        msg = self._h().get_confirm_message("apagar el equipo")
        assert "apagar" in msg.lower() or "⚠" in msg

    def test_reiniciar_has_message(self):
        msg = self._h().get_confirm_message("reiniciar")
        assert "reiniciar" in msg.lower() or "⚠" in msg

    def test_papelera_has_message(self):
        msg = self._h().get_confirm_message("papelera --ahora")
        assert "papelera" in msg.lower() or "⚠" in msg

    def test_eliminar_has_message(self):
        msg = self._h().get_confirm_message("eliminar archivo --ahora")
        assert "eliminar" in msg.lower() or "⚠" in msg

    def test_cerrar_has_message(self):
        msg = self._h().get_confirm_message("cerrar proceso --ahora")
        assert "cerrar" in msg.lower() or "⚠" in msg

    def test_unknown_command_has_default_message(self):
        msg = self._h().get_confirm_message("cmd_desconocido args")
        assert len(msg) > 0

    def test_empty_string_returns_default(self):
        msg = self._h().get_confirm_message("")
        assert len(msg) > 0

    def test_all_known_dangerous_have_messages(self):
        from voice.voice_command_handler import DANGEROUS_COMMAND_PREFIXES, _CONFIRM_MESSAGES
        h = self._h()
        for cmd in DANGEROUS_COMMAND_PREFIXES:
            msg = h.get_confirm_message(cmd)
            assert len(msg) > 0, f"Sin mensaje para '{cmd}'"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. process_transcription() — flujos nominales
# ═══════════════════════════════════════════════════════════════════════════════

class TestProcessTranscription:
    """Tests de process_transcription con distintos STTResults."""

    def _h(self):
        from voice.voice_command_handler import VoiceCommandHandler
        return VoiceCommandHandler()

    def test_stt_failure_returns_stt_error(self):
        h = self._h()
        stt = _make_stt_result(success=False, text="", error="Sin audio detectado.")
        result = h.process_transcription(stt)
        assert result.is_stt_error is True
        assert result.success is False
        assert "Sin audio" in result.error

    def test_stt_empty_text_returns_stt_error(self):
        h = self._h()
        stt = _make_stt_result(success=True, text="   ")
        result = h.process_transcription(stt)
        assert result.is_stt_error is True
        assert result.success is False

    def test_apagar_returns_needs_confirm(self):
        h = self._h()
        stt = _make_stt_result(text="apagar el equipo")
        result = h.process_transcription(stt)
        assert result.needs_confirm is True
        assert result.transcribed == "apagar el equipo"
        assert result.command == "apagar"
        assert len(result.confirm_msg) > 0

    def test_reiniciar_returns_needs_confirm(self):
        h = self._h()
        stt = _make_stt_result(text="reiniciar")
        result = h.process_transcription(stt)
        assert result.needs_confirm is True

    def test_eliminar_with_ahora_returns_needs_confirm(self):
        h = self._h()
        stt = _make_stt_result(text="eliminar archivo.txt --ahora")
        result = h.process_transcription(stt)
        assert result.needs_confirm is True

    def test_eliminar_without_ahora_not_needs_confirm(self):
        """eliminar sin --ahora es dry-run → no requiere confirmación de voz."""
        h = self._h()
        stt = _make_stt_result(text="eliminar archivo.txt")
        # Este comando va al router; si el router lo maneja, result.needs_confirm=False
        result = h.process_transcription(stt)
        assert result.needs_confirm is False

    def test_transcribed_stored_in_result(self):
        h = self._h()
        stt = _make_stt_result(text="apagar")
        result = h.process_transcription(stt)
        assert result.transcribed == "apagar"

    def test_normal_command_routed_to_router(self):
        """Un comando normal (no peligroso) debe ir al router."""
        from voice.voice_command_handler import VoiceCommandHandler, VoiceCommandResult
        h = VoiceCommandHandler()
        stt = _make_stt_result(text="hola")

        # Mock via patch del command_router a nivel de módulo
        mock_route_result = MagicMock()
        mock_route_result.success = True
        mock_route_result.output = "¡Hola!"
        mock_route_result.error = ""
        mock_route_result.skill_name = "demo_skill"
        mock_route_result.command = "hola"

        with patch("voice.voice_command_handler.command_router") as mock_router:
            mock_router.route.return_value = mock_route_result
            result = h.process_transcription(stt)

        assert result.success is True
        assert result.output == "¡Hola!"
        assert result.skill_name == "demo_skill"
        assert result.routed_to_ai is False
        assert result.needs_confirm is False


    def test_text_not_a_command_routed_to_ai(self):
        """Texto que el router no reconoce debe marcarse como routed_to_ai."""
        from voice.voice_command_handler import VoiceCommandHandler
        h = VoiceCommandHandler()
        stt = _make_stt_result(text="¿Cuál es la capital de Argentina?")

        with patch("voice.voice_command_handler.command_router") as mock_router:
            mock_router.route.return_value = None  # No es un comando
            result = h.process_transcription(stt)

        assert result.success is True
        assert result.routed_to_ai is True
        assert result.transcribed == "¿Cuál es la capital de Argentina?"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. execute_confirmed()
# ═══════════════════════════════════════════════════════════════════════════════

class TestExecuteConfirmed:
    """Tests de execute_confirmed() — ejecución tras confirmación."""

    def _h(self):
        from voice.voice_command_handler import VoiceCommandHandler
        return VoiceCommandHandler()

    def test_execute_confirmed_success(self):
        h = self._h()

        mock_route = MagicMock()
        mock_route.success = True
        mock_route.output = "Equipo apagando en 30 segundos."
        mock_route.error = ""
        mock_route.skill_name = "system_skill"
        mock_route.command = "apagar"

        with patch("voice.voice_command_handler.command_router") as mock_router:
            mock_router.route.return_value = mock_route
            result = h.execute_confirmed("apagar --ahora")

        assert result.success is True
        assert result.output == "Equipo apagando en 30 segundos."
        assert result.skill_name == "system_skill"

    def test_execute_confirmed_routes_to_ai_if_not_command(self):
        h = self._h()
        with patch("voice.voice_command_handler.command_router") as mock_router:
            mock_router.route.return_value = None
            result = h.execute_confirmed("algo que no es comando")
        assert result.routed_to_ai is True

    def test_execute_confirmed_returns_error_on_exception(self):
        h = self._h()
        with patch("voice.voice_command_handler.command_router") as mock_router:
            mock_router.route.side_effect = RuntimeError("fallo inesperado")
            result = h.execute_confirmed("apagar --ahora")
        assert result.success is False
        assert "fallo inesperado" in result.error

    def test_execute_confirmed_passes_text_to_router(self):
        h = self._h()
        captured = {}

        def capture_route(text):
            captured["text"] = text
            return None

        with patch("voice.voice_command_handler.command_router") as mock_router:
            mock_router.route.side_effect = capture_route
            h.execute_confirmed("reiniciar --ahora")

        assert captured.get("text") == "reiniciar --ahora"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Singleton get_voice_command_handler
# ═══════════════════════════════════════════════════════════════════════════════

class TestSingleton:
    """Tests del singleton del handler."""

    def test_returns_instance(self):
        from voice.voice_command_handler import get_voice_command_handler
        h = get_voice_command_handler()
        assert h is not None

    def test_is_same_instance_on_second_call(self):
        from voice.voice_command_handler import get_voice_command_handler
        h1 = get_voice_command_handler()
        h2 = get_voice_command_handler()
        assert h1 is h2

    def test_instance_has_all_methods(self):
        from voice.voice_command_handler import get_voice_command_handler
        h = get_voice_command_handler()
        assert callable(h.process_transcription)
        assert callable(h.execute_confirmed)
        assert callable(h.is_dangerous)
        assert callable(h.get_confirm_message)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. DANGEROUS_COMMAND_PREFIXES y DANGEROUS_WITH_FLAG
# ═══════════════════════════════════════════════════════════════════════════════

class TestDangerousConstants:
    """Tests de las constantes de detección de peligro."""

    def test_prefixes_is_frozenset(self):
        from voice.voice_command_handler import DANGEROUS_COMMAND_PREFIXES
        assert isinstance(DANGEROUS_COMMAND_PREFIXES, frozenset)

    def test_prefixes_not_empty(self):
        from voice.voice_command_handler import DANGEROUS_COMMAND_PREFIXES
        assert len(DANGEROUS_COMMAND_PREFIXES) > 0

    def test_prefixes_contains_apagar(self):
        from voice.voice_command_handler import DANGEROUS_COMMAND_PREFIXES
        assert "apagar" in DANGEROUS_COMMAND_PREFIXES

    def test_prefixes_contains_reiniciar(self):
        from voice.voice_command_handler import DANGEROUS_COMMAND_PREFIXES
        assert "reiniciar" in DANGEROUS_COMMAND_PREFIXES

    def test_prefixes_contains_papelera(self):
        from voice.voice_command_handler import DANGEROUS_COMMAND_PREFIXES
        assert "papelera" in DANGEROUS_COMMAND_PREFIXES

    def test_with_flag_is_tuple(self):
        from voice.voice_command_handler import DANGEROUS_WITH_FLAG
        assert isinstance(DANGEROUS_WITH_FLAG, tuple)

    def test_with_flag_contains_eliminar_ahora(self):
        from voice.voice_command_handler import DANGEROUS_WITH_FLAG
        pairs = [(cmd, flag) for cmd, flag in DANGEROUS_WITH_FLAG]
        assert ("eliminar", "--ahora") in pairs

    def test_with_flag_contains_cerrar_ahora(self):
        from voice.voice_command_handler import DANGEROUS_WITH_FLAG
        pairs = [(cmd, flag) for cmd, flag in DANGEROUS_WITH_FLAG]
        assert ("cerrar", "--ahora") in pairs

    def test_all_prefixes_are_lowercase(self):
        from voice.voice_command_handler import DANGEROUS_COMMAND_PREFIXES
        for p in DANGEROUS_COMMAND_PREFIXES:
            assert p == p.lower(), f"Prefijo no lowercase: {p!r}"


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Integración STT → VoiceCommandHandler con MockSTTProvider
# ═══════════════════════════════════════════════════════════════════════════════

class TestSTTIntegration:
    """Tests de integración end-to-end: MockSTTProvider → VoiceCommandHandler."""

    def test_mock_stt_to_handler_happy_path(self):
        from voice.providers.mock_stt_provider import MockSTTProvider
        from voice.voice_command_handler import VoiceCommandHandler

        provider = MockSTTProvider(simulate_delay_s=0)
        provider.set_next_response("hola")

        h = VoiceCommandHandler()
        stt_result = provider.transcribe_once()

        with patch("voice.voice_command_handler.command_router") as mock_router:
            mock_r = MagicMock()
            mock_r.success = True
            mock_r.output = "¡Hola!"
            mock_r.error = ""
            mock_r.skill_name = "demo_skill"
            mock_r.command = "hola"
            mock_router.route.return_value = mock_r
            result = h.process_transcription(stt_result)

        assert result.success is True
        assert result.transcribed == "hola"

    def test_mock_stt_dangerous_triggers_confirm(self):
        from voice.providers.mock_stt_provider import MockSTTProvider
        from voice.voice_command_handler import VoiceCommandHandler

        provider = MockSTTProvider(simulate_delay_s=0)
        provider.set_next_response("apagar --ahora")

        h = VoiceCommandHandler()
        stt_result = provider.transcribe_once()
        result = h.process_transcription(stt_result)

        assert result.needs_confirm is True
        assert result.command == "apagar"

    def test_mock_stt_free_text_goes_to_ai(self):
        from voice.providers.mock_stt_provider import MockSTTProvider
        from voice.voice_command_handler import VoiceCommandHandler

        provider = MockSTTProvider(simulate_delay_s=0)
        provider.set_next_response("¿Cuánto es 2 + 2?")

        h = VoiceCommandHandler()
        stt_result = provider.transcribe_once()

        with patch("voice.voice_command_handler.command_router") as mock_router:
            mock_router.route.return_value = None
            result = h.process_transcription(stt_result)

        assert result.routed_to_ai is True
        assert result.transcribed == "¿Cuánto es 2 + 2?"

    def test_mock_stt_failure_gives_stt_error(self):
        from voice.voice_interface import STTResult
        from voice.voice_command_handler import VoiceCommandHandler

        h = VoiceCommandHandler()
        stt_result = STTResult(success=False, error="timeout", provider="mock")
        result = h.process_transcription(stt_result)

        assert result.is_stt_error is True
        assert "timeout" in result.error


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Sintaxis de archivos
# ═══════════════════════════════════════════════════════════════════════════════

class TestFileSyntax:
    """Verifica que los archivos nuevos/modificados compilan sin errores."""

    def test_voice_command_handler_syntax(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "voice", "voice_command_handler.py"
        )
        py_compile.compile(path, doraise=True)

    def test_voice_init_syntax(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "voice", "__init__.py"
        )
        py_compile.compile(path, doraise=True)

    def test_chat_page_syntax(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "ui", "pages", "chat_page.py"
        )
        py_compile.compile(path, doraise=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Edge cases y robustez
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Tests de casos límite y robustez del handler."""

    def test_process_transcription_with_none_text_in_stt(self):
        """STTResult con text=None (atributo ausente) no debe crashear."""
        from voice.voice_command_handler import VoiceCommandHandler
        from voice.voice_interface import STTResult
        h = VoiceCommandHandler()
        stt = STTResult(success=False, text="", error="No audio")
        result = h.process_transcription(stt)
        assert result.is_stt_error is True

    def test_process_transcription_router_exception(self):
        """Si el router lanza excepción, el resultado debe ser error no manejado."""
        from voice.voice_command_handler import VoiceCommandHandler
        h = VoiceCommandHandler()
        stt = _make_stt_result(text="hola")
        with patch("voice.voice_command_handler.command_router") as mock_router:
            mock_router.route.side_effect = Exception("router crash")
            result = h.process_transcription(stt)
        assert result.success is False
        assert "router crash" in result.error

    def test_is_dangerous_with_leading_trailing_spaces(self):
        from voice.voice_command_handler import VoiceCommandHandler
        h = VoiceCommandHandler()
        assert h.is_dangerous("  apagar  ") is True

    def test_confirm_msg_not_empty_for_all_prefixes(self):
        from voice.voice_command_handler import VoiceCommandHandler, DANGEROUS_COMMAND_PREFIXES
        h = VoiceCommandHandler()
        for cmd in DANGEROUS_COMMAND_PREFIXES:
            msg = h.get_confirm_message(cmd + " args")
            assert msg, f"Mensaje vacío para '{cmd}'"
            assert "?" in msg or "⚠" in msg, f"Mensaje sin indicador de alerta: {msg!r}"

    def test_result_with_needs_confirm_bool_false(self):
        """Un resultado que requiere confirmación NO es truthy."""
        from voice.voice_command_handler import VoiceCommandResult
        r = VoiceCommandResult(success=True, needs_confirm=True)
        assert not bool(r)

    def test_routed_to_ai_with_needs_confirm_false(self):
        from voice.voice_command_handler import VoiceCommandHandler
        h = VoiceCommandHandler()
        stt = _make_stt_result(text="¿Qué es la fotosíntesis?")
        with patch("voice.voice_command_handler.command_router") as mock_router:
            mock_router.route.return_value = None
            result = h.process_transcription(stt)
        assert result.routed_to_ai is True
        assert result.needs_confirm is False

    def test_stt_with_only_spaces_gives_stt_error(self):
        from voice.voice_command_handler import VoiceCommandHandler
        from voice.voice_interface import STTResult
        h = VoiceCommandHandler()
        stt = STTResult(success=True, text="     ", error="")
        result = h.process_transcription(stt)
        assert result.is_stt_error is True

"""
Tests automatizados para la Fase 54:
Comprensión de comandos con errores de tipeo (Fuzzy Matching + Intérprete IA + Aprendizaje).
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from aura.core.fuzzy_interpreter import (
    TypoMemory,
    normalize_aggressive,
    generate_target_variants,
    FuzzyInterpreter,
    fuzzy_interpreter,
    InterpretationResult,
)
from ai.provider_interface import AIProvider, ChatMessage, ChatResponse, ProviderStatus


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tests de CAPA 1: Normalización Agresiva y Generación de Variantes
# ─────────────────────────────────────────────────────────────────────────────

def test_normalize_aggressive():
    # Minúsculas, sin tildes, sin puntuación, colapso de espacios
    assert normalize_aggressive("  ¡CIERRRA,   NOTEPAD!!  ") == "cierrra notepad"
    assert normalize_aggressive("¿Cómo está la aplicación?") == "como esta la aplicacion"
    assert normalize_aggressive("abre el   archivo_test.py") == "abre el archivo test py"
    assert normalize_aggressive("cierrra notepa d") == "cierrra notepa d"


def test_generate_target_variants():
    # Tokens unidos, separados, sin ruido final
    variants = generate_target_variants("notepa d")
    assert "notepa d" in variants
    assert "notepad" in variants
    assert "notepa" in variants

    variants_single = generate_target_variants("notpad")
    assert "notpad" in variants_single

    variants_article = generate_target_variants("el bloc de notas")
    assert any("bloc" in v for v in variants_article)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tests de CAPA 2: Matching Difflib y Verbos
# ─────────────────────────────────────────────────────────────────────────────

def test_match_verb_close():
    fi = FuzzyInterpreter()
    # "cierrra" -> "cerrar" (cutoff 0.75)
    match = fi.match_verb("cierrra notepa d")
    assert match is not None
    intent, canon, remainder, ratio = match
    assert intent == "close_app"
    assert canon == "cerrar"
    assert remainder == "notepa d"
    assert ratio >= 0.75


def test_match_verb_open():
    fi = FuzzyInterpreter()
    match = fi.match_verb("abrirr notpad")
    assert match is not None
    intent, canon, remainder, ratio = match
    assert intent == "open_app"
    assert canon == "abrir"
    assert remainder == "notpad"
    assert ratio >= 0.75


def test_match_verb_search():
    fi = FuzzyInterpreter()
    match = fi.match_verb("busca infrme")
    assert match is not None
    intent, canon, remainder, ratio = match
    assert intent == "search_file"
    assert canon == "buscar"
    assert remainder == "infrme"


def test_match_verb_multiword():
    fi = FuzzyInterpreter()
    match = fi.match_verb("crear carpta fotos")
    assert match is not None
    intent, canon, remainder, ratio = match
    assert intent == "create_folder"
    assert canon == "crear carpeta"
    assert remainder == "fotos"


def test_interpret_cierrra_notepa_d():
    # Caso real del usuario: "cierrra notepa d" -> debe entender "cerrar notepad"
    fi = FuzzyInterpreter()
    res = fi.interpret_fuzzy("cierrra notepa d")
    assert res is not None
    assert res.intent == "close_app"
    assert res.target == "notepad"
    assert res.status == "execute_direct"
    assert "Entendí: cerrar notepad" in res.display_message
    assert res.confidence >= 0.85
    assert res.layer == 2


def test_interpret_abre_notpad():
    fi = FuzzyInterpreter()
    res = fi.interpret_fuzzy("abre notpad")
    assert res is not None
    assert res.intent == "open_app"
    assert res.target == "notepad"
    assert res.status == "execute_direct"
    assert "Entendí: abrir notepad" in res.display_message
    assert res.confidence >= 0.85


def test_interpret_abre_firefx():
    fi = FuzzyInterpreter()
    res = fi.interpret_fuzzy("abre firefx")
    assert res is not None
    assert res.intent == "open_app"
    assert res.target == "firefox"
    assert res.status == "execute_direct"
    assert "Entendí: abrir firefox" in res.display_message
    assert res.confidence >= 0.85


def test_interpret_busca_infrme():
    fi = FuzzyInterpreter()
    res = fi.interpret_fuzzy("busca infrme")
    assert res is not None
    assert res.intent == "search_file"
    assert res.target == "informe"
    assert res.status == "execute_direct"
    assert "Entendí: buscar informe" in res.display_message


def test_interpret_abre_steam_deep_scan():
    # "abre steam" no debe ser reemplazado por otro programa; debe reportar deep scan
    fi = FuzzyInterpreter()
    from aura.core.entity_resolver import ResolvedEntity
    dummy_resolved = ResolvedEntity(
        resolved=False,
        intent="open_app",
        target="steam",
        extra={"needs_deep_scan": True},
    )
    with patch.object(fi, "build_target_corpus", return_value={"notepad", "firefox", "chrome", "calc", "teams"}), \
         patch("aura.core.fuzzy_interpreter.entity_resolver.resolve", return_value=dummy_resolved):
        res = fi.interpret_fuzzy("abre steam")
        # Steam no está en fast path, debe dar needs_deep_scan o target="steam"
        assert res is not None
        assert res.intent == "open_app"
        assert res.target == "steam"
        assert res.status == "needs_deep_scan"


def test_no_verb_match_conversational():
    fi = FuzzyInterpreter()
    # Pregunta normal: no debe matchear verbos conocidos con >= 0.75
    res = fi.interpret_fuzzy("¿cómo funciona un dict?")
    assert res is None

    # Texto basura total
    res_trash = fi.interpret_fuzzy("asdfghjkl qwerty zxcvbnm")
    assert res_trash is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Tests de CAPA 3: Intérprete IA Local
# ─────────────────────────────────────────────────────────────────────────────

class DummyAIProvider(AIProvider):
    def __init__(self, reply: str):
        self.reply = reply

    @property
    def provider_name(self) -> str:
        return "dummy"

    def check_status(self) -> ProviderStatus:
        return ProviderStatus(available=True, message="OK")

    def list_models(self) -> list[str]:
        return ["dummy-model"]

    def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        return ChatResponse(content=self.reply, model="dummy-model", provider="dummy")

    def chat_stream(self, messages: list[ChatMessage]):
        yield self.reply


def test_llm_interpreter_valid_json():
    fi = FuzzyInterpreter()
    # Simular respuesta de Ollama con markdown fences
    raw_ai_reply = "```json\n{\"intent\": \"close_app\", \"target\": \"notepad\"}\n```"
    provider = DummyAIProvider(raw_ai_reply)

    res = fi.interpret_llm("apaga rapido notep", provider=provider)
    assert res is not None
    assert res.intent == "close_app"
    assert res.target == "notepad"
    assert res.status == "execute_ai"
    assert res.layer == 3
    assert "Interpreté: close_app notepad" in res.display_message


def test_llm_interpreter_null_intent():
    fi = FuzzyInterpreter()
    raw_ai_reply = "{\"intent\": null}"
    provider = DummyAIProvider(raw_ai_reply)

    res = fi.interpret_llm("¿cómo funciona un dict?", provider=provider)
    assert res is None


def test_llm_interpreter_invalid_json():
    fi = FuzzyInterpreter()
    raw_ai_reply = "No soy un comando, soy un asistente virtual."
    provider = DummyAIProvider(raw_ai_reply)

    res = fi.interpret_llm("hola que tal", provider=provider)
    assert res is None


def test_full_pipeline_conversational_falls_through():
    fi = FuzzyInterpreter()
    provider = DummyAIProvider("{\"intent\": null}")

    # Pregunta conversacional pasa por Capa 1, 2 y 3 y retorna None para chat normal
    res = fi.interpret("¿cómo funciona un dict?", provider=provider)
    assert res is None


def test_full_pipeline_garbage_falls_through():
    fi = FuzzyInterpreter()
    provider = DummyAIProvider("{\"intent\": null}")

    res = fi.interpret("asdfghjkl qwerty", provider=provider)
    assert res is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tests de Aprendizaje y Persistencia (TypoMemory)
# ─────────────────────────────────────────────────────────────────────────────

def test_typo_memory_learning(tmp_path: Path):
    mem_file = tmp_path / "typos.json"
    mem = TypoMemory(file_path=mem_file)

    # Inicialmente vacío
    assert mem.lookup("notepa d") is None

    # Aprender el typo
    mem.learn("notepa d", "notepad", "close_app", confidence=0.96, layer=2)

    # Ahora lookup lo encuentra
    found = mem.lookup("notepa d")
    assert found is not None
    assert found["target"] == "notepad"
    assert found["intent"] == "close_app"

    # Persistencia en archivo
    assert mem_file.exists()
    data = json.loads(mem_file.read_text(encoding="utf-8"))
    assert "notepa d" in data["typos"]
    assert data["typos"]["notepa d"]["target"] == "notepad"

    # Nueva instancia carga el typo persistido
    mem2 = TypoMemory(file_path=mem_file)
    assert mem2.lookup("notepa d")["target"] == "notepad"

    # En FuzzyInterpreter con esta memoria, se resuelve con confianza 1.0 directamente
    fi = FuzzyInterpreter(memory=mem)
    cands = fi.match_target("close_app", "notepa d")
    assert cands[0] == ("notepad", 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Tests de Integración en ChatPage
# ─────────────────────────────────────────────────────────────────────────────

import flet as ft
from ui.pages.chat_page import ChatPage


class TestChatPageFuzzyIntegration:
    def test_chat_cierrra_notepa_d(self):
        page_mock = MagicMock(spec=ft.Page)
        chat = ChatPage(page=page_mock)
        chat.build()

        system_messages = []
        chat._add_system_message = lambda msg: system_messages.append(msg)

        with patch.object(chat, "_handle_close_app_direct") as mock_close, \
             patch.object(chat, "_send_to_ai") as mock_ai:
            chat.handle_user_message("cierrra notepa d")
            mock_close.assert_called_once()
            mock_ai.assert_not_called()
            assert any("Entendí: cerrar notepad" in m for m in system_messages)

    def test_chat_abre_notpad(self):
        page_mock = MagicMock(spec=ft.Page)
        chat = ChatPage(page=page_mock)
        chat.build()

        system_messages = []
        chat._add_system_message = lambda msg: system_messages.append(msg)

        with patch.object(chat, "_execute_resolved_skill_async") as mock_exec, \
             patch.object(chat, "_send_to_ai") as mock_ai:
            chat.handle_user_message("abre notpad")
            mock_exec.assert_called_once()
            mock_ai.assert_not_called()
            assert any("Entendí: abrir notepad" in m for m in system_messages)

    def test_chat_abre_firefx(self):
        page_mock = MagicMock(spec=ft.Page)
        chat = ChatPage(page=page_mock)
        chat.build()

        system_messages = []
        chat._add_system_message = lambda msg: system_messages.append(msg)

        with patch.object(chat, "_execute_resolved_skill_async") as mock_exec, \
             patch.object(chat, "_send_to_ai") as mock_ai:
            chat.handle_user_message("abre firefx")
            mock_exec.assert_called_once()
            mock_ai.assert_not_called()
            assert any("Entendí: abrir firefox" in m for m in system_messages)

    def test_chat_busca_infrme(self):
        page_mock = MagicMock(spec=ft.Page)
        chat = ChatPage(page=page_mock)
        chat.build()

        system_messages = []
        chat._add_system_message = lambda msg: system_messages.append(msg)

        with patch.object(chat, "_execute_resolved_skill_async") as mock_exec, \
             patch.object(chat, "_send_to_ai") as mock_ai:
            chat.handle_user_message("busca infrme")
            mock_exec.assert_called_once()
            mock_ai.assert_not_called()
            assert any("Entendí: buscar informe" in m for m in system_messages)

    def test_chat_conversational_question_goes_to_ai(self):
        page_mock = MagicMock(spec=ft.Page)
        chat = ChatPage(page=page_mock)
        chat.build()
        chat._provider = DummyAIProvider("{\"intent\": null}")

        with patch.object(chat, "_send_to_ai") as mock_ai:
            chat.handle_user_message("¿cómo funciona un dict?")
            mock_ai.assert_called_once()

    def test_chat_garbage_text_goes_to_ai_without_crash(self):
        page_mock = MagicMock(spec=ft.Page)
        chat = ChatPage(page=page_mock)
        chat.build()
        chat._provider = DummyAIProvider("{\"intent\": null}")

        with patch.object(chat, "_send_to_ai") as mock_ai:
            chat.handle_user_message("asdfghjkl qwerty")
            mock_ai.assert_called_once()

    def test_chat_pending_clarification_choice(self):
        page_mock = MagicMock(spec=ft.Page)
        chat = ChatPage(page=page_mock)
        chat.build()

        # Simular que hay una aclaración pendiente para "close_app"
        chat._pending_clarification = {
            "intent": "close_app",
            "canon_verb": "cerrar",
            "candidates": ["notepad", "wordpad"],
            "raw_typo": "notepadx",
        }

        with patch.object(chat, "_handle_close_app_direct") as mock_close:
            chat.handle_user_message("1")
            assert chat._pending_clarification is None
            mock_close.assert_called_once()


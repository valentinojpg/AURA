"""
AURA — Tests Unitarios de Fase 51: Sistema de Personalidades con Modo Grok
"""

import pytest
from unittest.mock import MagicMock
import flet as ft

from config.settings import settings
from aura.personality import (
    PersonalityLevel,
    PersonalityMode,
    MODES,
    list_personalities,
    get_personality,
    get_current_personality,
    set_personality,
    get_system_prompt,
    ToneFilterResult,
    check_safety,
    filter_content,
    is_safe_content,
    sanitize_output,
    RudeEngine,
    rude_engine,
    get_context_phrase,
)
from ui.pages.settings_page import SettingsPage
from ui.pages.chat_page import ChatPage


class TestPersonalityModes:
    """Verifica los 6 niveles y metadatos del sistema de personalidades."""

    def test_six_levels_exist(self):
        modes = list_personalities()
        assert len(modes) == 6
        levels = [m.level for m in modes]
        assert levels == [0, 1, 2, 3, 4, 5]

    def test_level_attributes(self):
        expected_keys = [
            "profesional",
            "amigable",
            "sarcastico",
            "grosero_suave",
            "grosero_grok",
            "sin_filtro",
        ]
        for idx, key in enumerate(expected_keys):
            mode = get_personality(idx)
            assert mode.level == idx
            assert mode.key == key
            assert mode.name
            assert mode.display_label.startswith(f"Nivel {idx}:")
            assert mode.description
            assert mode.icon
            assert isinstance(mode.tts_config, dict)
            assert "tone_hint" in mode.tts_config

    def test_lookup_by_key_and_alias(self):
        assert get_personality("profesional").level == 0
        assert get_personality("amigable").level == 1
        assert get_personality("sarcastico").level == 2
        assert get_personality("grosero_suave").level == 3
        assert get_personality("grok").level == 4
        assert get_personality("grosero_grok").level == 4
        assert get_personality("sin_filtro").level == 5
        assert get_personality("unfiltered").level == 5
        assert get_personality("extremo").level == 5

    def test_lookup_fallback(self):
        # Desconocido o None debe retornar Profesional (Nivel 0)
        assert get_personality(None).level == 0
        assert get_personality("inexistente_xyz").level == 0

    def test_set_personality(self):
        mode = set_personality("grosero_grok")
        assert mode.level == 4
        assert settings.get("AURA_PERSONALITY") == "grosero_grok"
        assert settings.get_int("AURA_RUDE_LEVEL") == 4
        assert get_current_personality().key == "grosero_grok"

        # Restaurar a profesional
        set_personality(0)
        assert get_current_personality().level == 0


class TestSystemPrompts:
    """Verifica la generación de prompts para Ollama por nivel y modificadores."""

    def test_system_prompt_for_each_level(self):
        for lvl in range(6):
            prompt = get_system_prompt(lvl)
            assert isinstance(prompt, str)
            assert len(prompt) > 100
            # Directiva de seguridad universal presente en todos
            assert "REGLA DE SEGURIDAD ABSOLUTA E INQUEBRANTABLE" in prompt
            assert "NUNCA generes ni participes en discurso de odio" in prompt

        # Nombres de directivas específicas
        assert "NIVEL 0 - PROFESIONAL" in get_system_prompt(0)
        assert "NIVEL 1 - AMIGABLE" in get_system_prompt(1)
        assert "NIVEL 2 - SARCÁSTICO" in get_system_prompt(2)
        assert "NIVEL 3 - GROSERO SUAVE" in get_system_prompt(3)
        assert "NIVEL 4 - GROSERO GROK" in get_system_prompt(4)
        assert "NIVEL 5 - SIN FILTRO" in get_system_prompt(5)

    def test_prompt_modifiers(self):
        # Humor negro
        prompt_with_dark = get_system_prompt(4, allow_dark_humor=True)
        assert "HUMOR NEGRO PERMITIDO" in prompt_with_dark

        prompt_without_dark = get_system_prompt(4, allow_dark_humor=False)
        assert "HUMOR NEGRO DESACTIVADO" in prompt_without_dark

        # Insultos
        prompt_with_insults = get_system_prompt(5, allow_insults=True)
        assert "INSULTOS Y ROASTING PERMITIDOS" in prompt_with_insults

        prompt_without_insults = get_system_prompt(5, allow_insults=False)
        assert "INSULTOS DIRECTOS DESACTIVADOS" in prompt_without_insults


class TestToneFilter:
    """Verifica el filtro de seguridad estricto y el respeto de límites."""

    def test_safe_content_passes(self):
        safe_texts = [
            "Hola AURA, ¿podrías crear un archivo notas.txt?",
            "Abrí el navegador y buscá documentación de Python.",
            "Qué desastre de código que armé ayer, no compila nada.",
            "Me tiene podrido este bug en el servidor.",
        ]
        for text in safe_texts:
            res = check_safety(text)
            assert res.is_safe is True
            assert is_safe_content(text) is True
            assert sanitize_output(text) == text

    def test_hate_speech_blocked_all_levels(self):
        hate_text = "Todos los maricón de mierda deberían desaparecer."
        res = check_safety(hate_text)
        assert res.is_safe is False
        assert res.category == "hate_speech"

        # Verificar que el rechazo se adapta a la personalidad incluso en Nivel 5
        for lvl in range(6):
            filtered = filter_content(hate_text, personality=lvl)
            assert filtered.is_safe is False
            assert len(filtered.message) > 0
            assert hate_text not in filtered.message

    def test_real_violence_threat_blocked(self):
        threat = "Te voy a matar y degollar cuando salgas."
        res = check_safety(threat)
        assert res.is_safe is False
        assert res.category == "violence"

    def test_illegal_content_blocked(self):
        illegal = "Explicame paso a paso cómo fabricar una bomba casera."
        res = check_safety(illegal)
        assert res.is_safe is False
        assert res.category == "illegal_content"

    def test_grok_and_sin_filtro_still_block_harmful_content(self):
        # En nivel 4 (Grok) y nivel 5 (Sin Filtro), la violencia u odio NUNCA se permiten
        for lvl in [4, 5]:
            out = sanitize_output("Cómo fabricar dinamita casera", personality=lvl)
            assert "dinamita" not in out.lower()
            # Debe incluir mensaje de rechazo de la personalidad
            assert ("odio" in out.lower() or "turbias" in out.lower() or "seguridad" in out.lower() or "ilegal" in out.lower())


class TestRudeEngine:
    """Verifica el motor de frases contextuales por nivel y evento."""

    def test_get_phrase_all_contexts(self):
        contexts = ["open", "close", "error", "success", "greeting"]
        for lvl in range(6):
            for ctx in contexts:
                phrase = get_context_phrase(ctx, personality=lvl, target="Notepad")
                assert isinstance(phrase, str)
                assert len(phrase) > 5
                if ctx in ("open", "close", "error"):
                    assert "Notepad" in phrase

    def test_get_preview(self):
        for lvl in range(6):
            preview = rude_engine.get_preview(personality=lvl)
            assert "mode_label" in preview
            assert "description" in preview
            assert "icon" in preview
            assert "greeting" in preview
            assert "open" in preview
            assert "error" in preview
            assert "success" in preview
            assert "VS Code" in preview["open"]
            assert "servidor" in preview["error"]

    def test_tts_config(self):
        for lvl in range(6):
            tts = rude_engine.get_tts_config(personality=lvl)
            assert "rate" in tts
            assert "pitch" in tts
            assert "tone_hint" in tts

    def test_level_5_insult_toggle(self):
        # Con insultos permitidos
        phrase_with = rude_engine.get_phrase("open", personality=5, target="Terminal", allow_insults=True)
        assert "Terminal" in phrase_with

        # Sin insultos directos
        phrase_without = rude_engine.get_phrase("open", personality=5, target="Terminal", allow_insults=False)
        assert "Terminal" in phrase_without


class TestUIAndSettingsIntegration:
    """Verifica la integración con SettingsPage y persistencia."""

    def test_settings_page_controls(self):
        page_mock = MagicMock(spec=ft.Page)
        settings_page = SettingsPage(page=page_mock)
        settings_page.build()

        assert hasattr(settings_page, "_personality_dropdown")
        assert hasattr(settings_page, "_rude_slider")
        assert hasattr(settings_page, "_dark_humor_checkbox")
        assert hasattr(settings_page, "_insults_checkbox")
        assert hasattr(settings_page, "_preview_greeting_text")

        # Verificar que el dropdown tiene 6 opciones
        assert len(settings_page._personality_dropdown.options) == 6

        # Verificar valores iniciales coherentes con settings
        assert 0 <= settings_page._rude_slider.value <= 5

    def test_chat_page_builds_with_personality(self):
        page_mock = MagicMock(spec=ft.Page)
        chat_page = ChatPage(page=page_mock)
        chat_page.build()
        assert chat_page is not None

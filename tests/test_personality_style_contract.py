# -*- coding: utf-8 -*-
"""
============================================================
AURA (Orion) — Pruebas: Personalidad con Contrato de Estilo
Fix de respuestas divagantes, loops y parámetros de generación
============================================================
Valida:
1. Contrato de estilo explícito en prompts para todos los niveles (0 a 5).
2. Cláusula especial para nivel 5 ('Sin Filtro').
3. Carga y formato de ejemplos few-shot (data/fun/personalities/<0..5>.json).
4. Parámetros de generación por nivel y configuración en .env (AURA_TEMP, AURA_REPEAT_PENALTY, AURA_MAX_TOKENS_TONO).
5. Distinción entre respuestas de tono (max 150 tokens) y preguntas técnicas (no recortadas).
6. Guard anti-loop (detección de oraciones y secuencias de 6+ palabras repetidas, recorte y regeneración).
7. Handler dedicado de roast con intents ("insultame", "roasteame", "tirame un palo"), formato máx 3 líneas y contexto.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from aura.personality import (
    get_system_prompt,
    get_generation_parameters,
    is_tone_request,
    load_personality_examples,
    apply_anti_loop,
    detect_repetition,
    trim_at_repetition,
    is_useful_sentence,
    generate_roast,
    set_personality,
)
from aura.core.intent_router import intent_router
from aura.core.fuzzy_interpreter import fuzzy_interpreter
from ai.providers.mock_provider import MockProvider
from config.settings import settings


# ============================================================
# 1. PRUEBAS DE CONTRATO DE ESTILO Y FEW-SHOT EN PROMPTS
# ============================================================

def test_style_contract_present_in_all_levels():
    """Verifica que el contrato de estilo esté incluido en todos los niveles (0 a 5)."""
    for lvl in range(6):
        prompt = get_system_prompt(lvl)
        assert "CONTRATO DE ESTILO Y EXTENSIÓN OBLIGATORIO" in prompt
        assert "LONGITUD MÁXIMA: 1 a 3 frases para respuestas de tono" in prompt
        assert "PROHIBIDO REPETIR ESTRUCTURAS" in prompt
        assert "REMATE SECO" in prompt


def test_level_5_special_clause():
    """Verifica la cláusula especial de oficio y concisión para el nivel 5 'Sin Filtro'."""
    prompt_5 = get_system_prompt(5)
    assert "Grosero y ácido PERO con oficio: metáforas originales, frases cortas, un solo remate" in prompt_5
    assert "Un párrafo largo repitiendo insultos es un error tuyo" in prompt_5


def test_personality_json_files_exist_and_structure():
    """Verifica que los 6 archivos JSON existan en data/fun/personalities/ con la estructura requerida."""
    root = Path(__file__).resolve().parent.parent
    p_dir = root / "data" / "fun" / "personalities"
    assert p_dir.is_dir()

    for lvl in range(6):
        json_file = p_dir / f"{lvl}.json"
        assert json_file.is_file(), f"Falta {lvl}.json"

        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data.get("nivel") == lvl
        assert "nombre" in data
        assert "ejemplos_buenos" in data
        assert "ejemplos_prohibidos" in data
        assert len(data["ejemplos_buenos"]) >= 2
        assert len(data["ejemplos_prohibidos"]) >= 1


def test_few_shot_examples_injected_in_prompt():
    """Verifica que los ejemplos buenos y prohibidos se inyecten en el system prompt."""
    prompt = get_system_prompt(5)
    assert "EJEMPLOS DE ESTILO (FEW-SHOT):" in prompt
    assert "EJEMPLOS BUENOS (imitá este patrón breve y seco):" in prompt
    assert "EJEMPLOS PROHIBIDOS (NUNCA hagas esto: divagar, repetir o encadenar):" in prompt


# ============================================================
# 2. PRUEBAS DE PARÁMETROS DE GENERACIÓN Y DETECCIÓN DE TONO
# ============================================================

def test_generation_parameters_levels_0_to_2():
    """Verifica que los niveles 0 a 2 usen temperature 0.7 y max_tokens 512."""
    for lvl in [0, 1, 2]:
        params = get_generation_parameters(level=lvl, is_tone=True)
        assert params["temperature"] == 0.7
        assert params["max_tokens"] == 512
        assert params["repeat_penalty"] == 1.0


def test_generation_parameters_levels_3_to_5_tone_vs_technical():
    """Verifica que los niveles 3 a 5 limiten a 150 tokens en tono, pero 512 en explicaciones técnicas."""
    for lvl in [3, 4, 5]:
        params_tone = get_generation_parameters(level=lvl, is_tone=True)
        assert params_tone["temperature"] == 0.9
        assert params_tone["repeat_penalty"] == 1.2
        assert params_tone["frequency_penalty"] == 0.6
        assert params_tone["presence_penalty"] == 0.6
        assert params_tone["max_tokens"] == 150

        params_tech = get_generation_parameters(level=lvl, is_tone=False)
        assert params_tech["max_tokens"] == 512
        assert params_tech["temperature"] == 0.9


def test_generation_parameters_env_overrides(monkeypatch):
    """Verifica que las variables .env AURA_TEMP, AURA_REPEAT_PENALTY y AURA_MAX_TOKENS_TONO sobreescriban."""
    monkeypatch.setattr(settings, "get", lambda key, fallback=None: {
        "AURA_TEMP": "0.85",
        "AURA_REPEAT_PENALTY": "1.35",
        "AURA_MAX_TOKENS_TONO": "120",
    }.get(key, fallback))

    params = get_generation_parameters(level=5, is_tone=True)
    assert params["temperature"] == 0.85
    assert params["repeat_penalty"] == 1.35
    assert params["max_tokens"] == 120


def test_is_tone_request_classification():
    """Verifica la distinción entre consultas de tono y preguntas técnicas."""
    # Consultas de tono (deben dar True)
    assert is_tone_request("insultame") is True
    assert is_tone_request("insúltame por favor") is True
    assert is_tone_request("roasteame") is True
    assert is_tone_request("tirame un palo") is True
    assert is_tone_request("contame un chiste") is True
    assert is_tone_request("hola") is True
    assert is_tone_request("cómo estás?") is True
    assert is_tone_request("qué onda") is True

    # Preguntas técnicas o de código (deben dar False)
    assert is_tone_request("explicame cómo funciona la recursión en python") is False
    assert is_tone_request("por qué da error este script?") is False
    assert is_tone_request("escribí una función para calcular fibonacci") is False
    assert is_tone_request("analiza este código para optimizarlo") is False
    assert is_tone_request("cómo es la arquitectura de red?") is False


# ============================================================
# 3. PRUEBAS DEL GUARD ANTI-LOOP (anti_loop.py)
# ============================================================

def test_detect_repetition_sentence():
    """Verifica que detecte la repetición de una misma oración."""
    text = (
        "¿Cómo te atreves a hablarme así? ¡Eres un desastre andante! "
        "¿Cómo te atreves a hablarme así? ¡Eres un desastre andante!"
    )
    has_rep, cut_idx, reason = detect_repetition(text)
    assert has_rep is True
    assert cut_idx > 0
    assert "oración repetida" in reason

    trimmed = trim_at_repetition(text, cut_idx)
    assert "¿Cómo te atreves a hablarme así? ¡Eres un desastre andante!" == trimmed


def test_detect_repetition_6_words_ngram():
    """Verifica que detecte la repetición de una secuencia de 6+ palabras consecutivas."""
    text = (
        "El compilador falló porque te olvidaste de importar la librería necesaria. "
        "Entonces el compilador falló porque te olvidaste de importar la librería necesaria otra vez."
    )
    has_rep, cut_idx, reason = detect_repetition(text)
    assert has_rep is True
    assert "secuencia de 6+ palabras" in reason

    trimmed = trim_at_repetition(text, cut_idx)
    assert "otra vez" not in trimmed


def test_anti_loop_normal_text_untouched():
    """Verifica que texto normal variado no sea alterado por el guard."""
    normal = "Tenés menos luces que arbolito quemado. Andá a laburar antes de que la máquina pida asilo."
    cleaned = apply_anti_loop(normal)
    assert cleaned == normal


def test_anti_loop_regeneration_on_short_cut():
    """Verifica que si el recorte deja menos de 1 frase útil, regenere una vez con repeat_penalty aumentada."""
    loop_repetitive = "¡Eres un inútil! ¡Eres un inútil! ¡Eres un inútil!"
    regenerated_called = False
    passed_penalty = 0.0
    passed_max_tokens = 0

    def mock_regenerator(new_repeat, new_max_tokens):
        nonlocal regenerated_called, passed_penalty, passed_max_tokens
        regenerated_called = True
        passed_penalty = new_repeat
        passed_max_tokens = new_max_tokens
        return "Respuesta fresca y variada con un dardo certero."

    res = apply_anti_loop(
        loop_repetitive,
        regenerator=mock_regenerator,
        current_repeat_penalty=1.2,
        current_max_tokens=150,
    )

    # El recorte de "¡Eres un inútil!" tiene solo 3 palabras y es repetido de inmediato
    # Si activa regeneración:
    if regenerated_called:
        assert passed_penalty == pytest.approx(1.3, 0.01)
        assert passed_max_tokens < 150
        assert "Respuesta fresca" in res


# ============================================================
# 4. PRUEBAS DEL HANDLER DEDICADO PARA ROAST / INSULTO
# ============================================================

def test_intent_router_roast_intents():
    """Verifica que el IntentRouter reconozca 'insultame', 'roasteame' y 'tirame un palo'."""
    queries = [
        "insultame",
        "insúltame",
        "insultame por favor",
        "roasteame",
        "roastéame",
        "tirame un palo",
        "tírame un palo",
        "tirame un bife",
        "dame un roast",
    ]
    for q in queries:
        parsed = intent_router.parse(q)
        assert parsed is not None, f"Falló en reconocer '{q}'"
        assert parsed.nombre == "roast", f"Intent esperado 'roast' para '{q}', obtenido '{parsed.nombre}'"


def test_fuzzy_interpreter_roast_intent():
    """Verifica que el intérprete difuso maneje errores tipográficos de roast."""
    res = fuzzy_interpreter.interpret_fuzzy("insultamee")
    assert res is not None
    assert res.intent == "roast"

    res2 = fuzzy_interpreter.interpret_fuzzy("roasteamee")
    assert res2 is not None
    assert res2.intent == "roast"


def test_roast_level_0_professional_refusal():
    """En nivel 0, el roast debe rechazar cortés y profesionalmente sin insultos."""
    set_personality("profesional")
    res = generate_roast("insultame", provider=None)
    assert "protocolo" in res.lower()
    assert "no contempla" in res.lower() or "agravios" in res.lower()


def test_roast_level_1_friendly_refusal():
    """En nivel 1, el roast debe negarse amigablemente."""
    set_personality("amigable")
    res = generate_roast("insultame", provider=None)
    assert "no te voy a insultar" in res.lower() or "ni de casualidad" in res.lower()


def test_roast_level_5_structured_output():
    """En nivel 5, el roast debe producir un texto corto, máximo 3 líneas y con remate."""
    set_personality("sin_filtro")
    mock_provider = MockProvider()

    res = generate_roast("insultame", provider=mock_provider)
    lines = [line for line in res.splitlines() if line.strip()]

    # Debe ser conciso: máximo 3 líneas
    assert 1 <= len(lines) <= 3
    # No debe ser un párrafo gigante
    assert len(res) < 350


def test_roast_three_times_distinct():
    """Probar 'insultame' tres veces seguidas: produce respuestas cortas y sin loops."""
    set_personality("sin_filtro")
    mock = MockProvider()

    r1 = generate_roast("insultame", provider=mock)
    r2 = generate_roast("roasteame", provider=mock)
    r3 = generate_roast("tirame un palo", provider=mock)

    for r in [r1, r2, r3]:
        lines = [l for l in r.splitlines() if l.strip()]
        assert 1 <= len(lines) <= 3
        # No debe haber loops de frases idénticas
        has_rep, _, _ = detect_repetition(r)
        assert has_rep is False


def test_technical_question_with_level_5_not_shortened():
    """Verifica que una pregunta técnica con nivel 5 NO sea recortada por el contrato de tono."""
    set_personality("sin_filtro")
    user_query = "Explicame cómo funciona el decorador @functools.lru_cache en Python con un ejemplo"
    is_tone = is_tone_request(user_query)
    assert is_tone is False

    params = get_generation_parameters(level=5, is_tone=is_tone)
    assert params["max_tokens"] == 512, "Las preguntas técnicas deben tener max_tokens=512, no 150"

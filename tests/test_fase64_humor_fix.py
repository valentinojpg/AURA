"""
Tests para FASE 64 — Fix de humor: sin ejemplos prohibidos en contexto,
sin etiquetas fugadas, parámetros cuerdos, y banco local como fuente principal.
"""

from unittest.mock import MagicMock, patch
import os
import json
import logging
from pathlib import Path
import pytest

from config.settings import settings
from ai.provider_interface import ChatMessage, ChatResponse, ProviderStatus
from aura.core.intent_router import intent_router, Intent
from aura.core.fuzzy_interpreter import fuzzy_interpreter
from aura.personality.jokes import (
    generate_joke,
    handle_joke_complaint,
    get_fallback_joke,
    validate_joke_output,
    resolve_joke_style,
    JOKES_FILE,
)
from aura.personality.roast_handler import (
    generate_roast,
    get_fallback_roast,
    handle_roast_complaint,
)
from aura.personality.humor_tracker import (
    strip_humor_labels,
    validate_roast_output,
    set_last_humor_intent,
    get_last_humor_intent,
    save_last_roast_state,
    get_last_roast_state,
    save_last_joke_state,
    get_last_joke_state,
)
from aura.personality.humor_provider import get_humor_provider
from aura.personality.personalities import set_personality


# ─────────────────────────────────────────────────────────────────────────────
# 1. Few-shot Solo Positivo (sin ejemplos prohibidos en prompt)
# ─────────────────────────────────────────────────────────────────────────────

def test_few_shot_only_positive_in_joke_prompt():
    """El prompt enviado al modelo NO debe contener ejemplos prohibidos ni etiquetas 'Setup:'."""
    mock_provider = MagicMock()
    mock_provider.chat.return_value = ChatResponse(
        content="— ¿Por qué los peces no usan internet?\n— Porque le tienen miedo a las redes.",
        model="mock",
        provider="mock",
    )

    with patch.dict(os.environ, {"HUMOR_SOURCE": "model"}):
        generate_joke("un chiste de animales", estilo="absurdo", provider=mock_provider)

    assert mock_provider.chat.called
    call_args = mock_provider.chat.call_args[0]
    messages = call_args[0]
    user_prompt = messages[1].content

    # Verificar que NO están los ejemplos prohibidos en el prompt
    assert "EJEMPLOS PROHIBIDOS" not in user_prompt
    assert "servidores ineficaces" not in user_prompt
    assert "antigua Roma" not in user_prompt

    # Verificar que las reglas en prosa prohíben etiquetas y curiosidades
    assert "PROHIBIDO escribir etiquetas como 'Setup:', 'Remate:'" in user_prompt
    assert "PROHIBIDO abrir con '¿Sabías que...'" in user_prompt


# ─────────────────────────────────────────────────────────────────────────────
# 2. Sin Etiquetas de Esquema (strip_humor_labels y validación)
# ─────────────────────────────────────────────────────────────────────────────

def test_strip_humor_labels():
    """strip_humor_labels debe limpiar etiquetas al inicio y en el cuerpo del texto."""
    leaked_1 = "¿Cuánta pasta cae en el vaso...?\nRemate: Todo lo demás se queda sin juego."
    cleaned_1 = strip_humor_labels(leaked_1)
    assert "Remate:" not in cleaned_1
    assert "Todo lo demás se queda sin juego." in cleaned_1

    leaked_2 = "Setup: Premisa del chiste.\nRemate: Remate cómico.\nTagline: Cierre seco."
    cleaned_2 = strip_humor_labels(leaked_2)
    assert "Setup:" not in cleaned_2
    assert "Remate:" not in cleaned_2
    assert "Tagline:" not in cleaned_2
    assert "Premisa del chiste." in cleaned_2
    assert "Remate cómico." in cleaned_2

    leaked_3 = "Roast: Son las 3 de la tarde y no hiciste nada."
    cleaned_3 = strip_humor_labels(leaked_3)
    assert "Roast:" not in cleaned_3
    assert "Son las 3 de la tarde" in cleaned_3


def test_validation_rejects_leaked_labels():
    """Tanto validate_joke_output como validate_roast_output deben rechazar etiquetas fugadas."""
    bad_joke = "Setup: ¿Qué le dice un cable a otro?\nRemate: Seguime la corriente."
    ok_j, err_j = validate_joke_output(bad_joke)
    assert not ok_j
    assert "Etiqueta" in err_j

    bad_roast = "Roast: Vos sos un desastre con la programación.\nRemate: Chau."
    ok_r, err_r = validate_roast_output(bad_roast, level=5)
    assert not ok_r
    assert "Etiqueta" in err_r


# ─────────────────────────────────────────────────────────────────────────────
# 3. Parámetros Cuerdos para Humor en Modelos Chicos (sin escalada)
# ─────────────────────────────────────────────────────────────────────────────

def test_sane_generation_parameters_and_no_escalation():
    """temperature fija en 0.75, repeat_penalty <= 1.1, max_tokens <= 120, sin escalada en reintentos."""
    mock_provider = MagicMock()
    # 1er llamado: inválido (apertura prohibida)
    # 2do llamado: válido
    mock_provider.chat.side_effect = [
        ChatResponse(content="¿Sabías que los programadores no duermen?\nEs verdad.", model="mock", provider="mock"),
        ChatResponse(content="— ¿Por qué los programadores usan lentes?\n— Porque no ven C#.", model="mock", provider="mock"),
    ]

    with patch.dict(os.environ, {"HUMOR_SOURCE": "model"}):
        generate_joke("un chiste", provider=mock_provider)

    assert mock_provider.chat.call_count == 2
    for call in mock_provider.chat.call_args_list:
        kwargs = call.kwargs
        assert kwargs["temperature"] == 0.75, f"Esperada temp 0.75 fija, obtenida {kwargs['temperature']}"
        assert kwargs["max_tokens"] <= 120, f"max_tokens debe ser <= 120, obtenido {kwargs['max_tokens']}"
        assert kwargs["repeat_penalty"] <= 1.1, f"repeat_penalty debe ser <= 1.1, obtenido {kwargs['repeat_penalty']}"
        assert kwargs["frequency_penalty"] == 0.0
        assert kwargs["presence_penalty"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Routing Correcto roast vs chiste vs queja
# ─────────────────────────────────────────────────────────────────────────────

def test_intent_router_roast_variations():
    """Verifica que 'INSULTAME FUERTE', 'bardeame', 'tirame un insulto' caigan siempre en roast."""
    roast_phrases = [
        "INSULTAME FUERTE",
        "insultame fuerte",
        "insultame posta",
        "insultame bien fuerte",
        "insultame con todo",
        "insultame mas",
        "roasteame fuerte",
        "dame un insulto",
        "tirame un insulto",
        "haceme mierda",
        "bardeame",
        "quiero que me insultes",
    ]
    for phrase in roast_phrases:
        parsed = intent_router.parse(phrase)
        assert parsed is not None, f"No se parseó: {phrase}"
        assert parsed.nombre == "roast", f"Esperado 'roast' para '{phrase}', obtenido '{parsed.nombre}'"


def test_intent_router_roast_complaints():
    """Verifica que quejas tras roast caigan en queja_chiste para meta-corrección."""
    complaints = [
        "te pedi que me insultaras",
        "te pedí que me insultaras",
        "te pedi un insulto",
        "te pedi un roast",
        "eso no fue un insulto",
        "no me insultaste",
        "eso no es un roast",
        "eso no me dolio",
        "eso fue re suave",
        "insultame en serio",
    ]
    for comp in complaints:
        parsed = intent_router.parse(comp)
        assert parsed is not None, f"No se parseó queja: {comp}"
        assert parsed.nombre == "queja_chiste", f"Esperado 'queja_chiste' para '{comp}', obtenido '{parsed.nombre}'"


def test_last_humor_intent_tracking_and_complaint_routing():
    """Verifica que last_humor_intent se actualiza y la queja regenera el mismo tipo de humor."""
    # 1. Ejecutar roast actualiza last_humor_intent a 'roast'
    set_personality(5)
    with patch.dict(os.environ, {"HUMOR_SOURCE": "bank"}):
        roast = generate_roast("insultame fuerte")
        assert roast
        assert get_last_humor_intent() == "roast"

    # Queja tras roast con handle_roast_complaint
    with patch.dict(os.environ, {"HUMOR_SOURCE": "bank"}):
        corrective_roast = handle_roast_complaint("te pedi que me insultaras")
        assert corrective_roast
        assert get_last_humor_intent() == "roast"
        # Debe contener segunda persona
        valid, _ = validate_roast_output(corrective_roast, level=5)
        assert valid

    # 2. Ejecutar chiste actualiza last_humor_intent a 'chiste'
    with patch.dict(os.environ, {"HUMOR_SOURCE": "bank"}):
        joke = generate_joke("contame un chiste")
        assert joke
        assert get_last_humor_intent() == "chiste"

    # Queja tras chiste con handle_joke_complaint
    with patch.dict(os.environ, {"HUMOR_SOURCE": "bank"}):
        corrective_joke = handle_joke_complaint("pero me estas contando datos")
        assert corrective_joke
        assert get_last_humor_intent() == "chiste"
        valid, _ = validate_joke_output(corrective_joke)
        assert valid


def test_no_cross_contamination_in_fuzzy_capa3():
    """Verifica que el intérprete IA (Capa 3) prevenga la contaminación cruzada roast <-> pedir_chiste."""
    # Simular que el LLM devolvió pedir_chiste para 'insultame fuerte'
    mock_provider = MagicMock()
    mock_provider.chat.return_value = ChatResponse(
        content='{"intent": "pedir_chiste", "estilo": "negro"}',
        model="mock",
        provider="mock",
    )
    res = fuzzy_interpreter.interpret_llm("insultame fuerte", provider=mock_provider)
    assert res is not None
    # El guard debe haber sobreescrito a 'roast'
    assert res.intent == "roast"

    # Simular que el LLM devolvió roast para 'contame un chiste negro'
    mock_provider.chat.return_value = ChatResponse(
        content='{"intent": "roast"}',
        model="mock",
        provider="mock",
    )
    res_joke = fuzzy_interpreter.interpret_llm("contame un chiste negro", provider=mock_provider)
    assert res_joke is not None
    assert res_joke.intent == "pedir_chiste"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Validación de Coherencia + Banco Local
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_roast_output_rules():
    """Valida segunda persona y términos curados por nivel en roasts."""
    # Válido: segunda persona + término curado nivel 5 ('mierda', 'pelotudo')
    valid_roast = "Son las 15:00 y seguís perdiendo el tiempo, pedazo de pelotudo.\nTu código es una mierda que da vergüenza.\nAndá a laburar de una vez."
    ok, err = validate_roast_output(valid_roast, level=5)
    assert ok, f"Error inesperado: {err}"

    # Inválido: sin segunda persona (habla en tercera persona abstracta)
    no_second_person = "La programación es una actividad compleja.\nLos errores ocurren con frecuencia en el código.\nEl compilador es estricto."
    ok_sp, err_sp = validate_roast_output(no_second_person, level=5)
    assert not ok_sp
    assert "segunda persona" in err_sp

    # Inválido: sin términos curados del nivel
    no_curated = "Vos tenés una remera azul muy llamativa hoy.\nTu pelo está peinado hacia el costado.\nMirá qué lindo día hace afuera."
    ok_cur, err_cur = validate_roast_output(no_curated, level=5)
    assert not ok_cur
    assert "característicos" in err_cur

    # Inválido: más de 3 líneas
    too_long = "Línea 1 vos sos un desastre pelotudo.\nLínea 2.\nLínea 3.\nLínea 4."
    ok_len, err_len = validate_roast_output(too_long, level=5)
    assert not ok_len
    assert "3 líneas" in err_len


def test_validate_joke_output_repetition_rule():
    """El remate no puede repetir palabras del setup textualmente."""
    bad_repetitive = "Había una vez un elefante volando sobre el océano pacífico.\nEl elefante volando sobre el océano pacífico."
    ok, err = validate_joke_output(bad_repetitive)
    assert not ok
    assert "repite" in err.lower()


def test_double_validation_failure_falls_back_to_local_bank(caplog):
    """Dos fallos seguidos de validación entregan del banco local sin preguntar."""
    mock_provider = MagicMock()
    mock_provider.chat.side_effect = [
        ChatResponse(content="Dato: los gatos tienen cuatro patas.", model="mock", provider="mock"),
        ChatResponse(content="¿Sabías que el agua hierve a 100 grados?", model="mock", provider="mock"),
    ]

    with patch.dict(os.environ, {"HUMOR_SOURCE": "hybrid"}):
        with caplog.at_level(logging.WARNING):
            joke = generate_joke("un chiste de programadores", estilo="programador", provider=mock_provider)
            assert joke
            assert "segundo fallo consecutivo" in caplog.text
            valid, _ = validate_joke_output(joke)
            assert valid


def test_humor_source_bank_returns_instant_bank():
    """Con HUMOR_SOURCE=bank, retorna del banco inmediatamente sin llamar al provider."""
    mock_provider = MagicMock()
    with patch.dict(os.environ, {"HUMOR_SOURCE": "bank"}):
        joke = generate_joke("un chiste blanco", estilo="blanco", provider=mock_provider)
        assert joke
        assert not mock_provider.chat.called
        valid, _ = validate_joke_output(joke)
        assert valid

        roast = generate_roast("insultame fuerte", provider=mock_provider)
        assert roast
        assert not mock_provider.chat.called
        valid_r, _ = validate_roast_output(roast, level=5)
        assert valid_r


def test_jokes_json_minimum_counts():
    """Verifica que data/fun/jokes.json tenga al menos 20 chistes por estilo y 25 roasts por nivel (3,4,5)."""
    assert JOKES_FILE.exists()
    with open(JOKES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Chistes
    for estilo in ("negro", "acido", "absurdo", "programador", "blanco"):
        count = len(data.get("banco", {}).get(estilo, []))
        assert count >= 20, f"Estilo '{estilo}' tiene {count} chistes (mínimo 20)"

    # Roasts
    banco_roasts = data.get("banco_roasts", {})
    for lvl in ("3", "4", "5"):
        count = len(banco_roasts.get(lvl, []))
        assert count >= 25, f"Nivel {lvl} tiene {count} roasts (mínimo 25)"
        # Verificar que todos los roasts del banco cumplan el formato
        for r in banco_roasts[lvl]:
            valid, err = validate_roast_output(r.replace("{hora}", "15:00").replace("{app}", "notepad"), level=int(lvl))
            assert valid, f"Roast inválido en banco nivel {lvl} ({err}): {r}"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Ruteo por Provider (HUMOR_PROVIDER) y Degradación Graciosa
# ─────────────────────────────────────────────────────────────────────────────

def test_humor_provider_auto_fallback_to_bank_when_cloud_fails():
    """Si HUMOR_PROVIDER=auto y el provider cloud falla o está desconectado, degrada a banco sin error."""
    with patch.dict(os.environ, {"HUMOR_PROVIDER": "auto", "HUMOR_SOURCE": "hybrid"}):
        # Provocar que el provider arroje excepción de conexión caída
        failing_provider = MagicMock()
        failing_provider.chat.side_effect = ConnectionError("Cloud provider timeout/cut")
        failing_provider.status.return_value = ProviderStatus(available=True, message="OK", provider="mock")

        # Debe capturar el error y entregar del banco local sin crashear
        roast = generate_roast("insultame fuerte", provider=failing_provider)
        assert roast
        valid, _ = validate_roast_output(roast, level=5)
        assert valid

        joke = generate_joke("un chiste negro", estilo="negro", provider=failing_provider)
        assert joke
        valid_j, _ = validate_joke_output(joke)
        assert valid_j


def test_level_5_insultame_fuerte_three_distinct_times():
    """Prueba manual simulada: Nivel 5 + 'insultame fuerte' genera roasts coherentes, sin etiquetas y distintos."""
    set_personality(5)
    with patch.dict(os.environ, {"HUMOR_SOURCE": "bank"}):
        results = []
        for _ in range(5):
            r = generate_roast("insultame fuerte")
            assert "Remate:" not in r
            assert "Setup:" not in r
            valid, err = validate_roast_output(r, level=5)
            assert valid, f"Roast inválido ({err}): {r}"
            results.append(r)

        # Debe haber variedad en las respuestas
        assert len(set(results)) >= 2, "Se esperaba variedad en las respuestas de roast"

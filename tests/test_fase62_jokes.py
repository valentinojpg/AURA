"""
Tests para FASE 62 — Chistes reales: intent dedicado, estructura obligatoria,
banco local y meta-corrección ante quejas.
"""

import json
import logging
from unittest.mock import MagicMock

import pytest

from aura.core.intent_router import Intent, intent_router
from aura.core.fuzzy_interpreter import fuzzy_interpreter
from aura.personality.jokes import (
    JOKES_FILE,
    VALID_STYLES,
    format_joke_obj,
    get_fallback_joke,
    has_prohibited_opening,
    load_jokes_data,
    resolve_joke_style,
    validate_joke_output,
    generate_joke,
    handle_joke_complaint,
)
from ai.provider_interface import ChatMessage, ChatResponse


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tests del Banco Local de Chistes (data/fun/jokes.json)
# ─────────────────────────────────────────────────────────────────────────────

def test_jokes_json_structure_and_counts():
    """Verifica que el banco local existe y contiene al menos 15 chistes por cada uno de los 5 estilos."""
    assert JOKES_FILE.exists(), f"Archivo {JOKES_FILE} no existe"
    data = load_jokes_data()

    assert "prohibidos" in data
    assert len(data["prohibidos"]) >= 2
    for ej_malo in data["prohibidos"]:
        assert has_prohibited_opening(ej_malo)

    assert "ejemplos_buenos" in data
    for estilo in VALID_STYLES:
        assert estilo in data["ejemplos_buenos"]
        assert len(data["ejemplos_buenos"][estilo]) >= 3

    assert "banco" in data
    for estilo in VALID_STYLES:
        assert estilo in data["banco"], f"Falta estilo '{estilo}' en el banco"
        count = len(data["banco"][estilo])
        assert count >= 15, f"Estilo '{estilo}' tiene solo {count} chistes (mínimo requerido: 15)"
        for joke_obj in data["banco"][estilo]:
            assert "setup" in joke_obj and joke_obj["setup"]
            assert "remate" in joke_obj and joke_obj["remate"]
            formatted = format_joke_obj(joke_obj)
            valid, err = validate_joke_output(formatted)
            assert valid, f"Chiste en banco inválido ({err}): {formatted}"


def test_get_fallback_joke_logging(caplog):
    """Verifica que get_fallback_joke entrega un chiste formateado y registra la reserva en log."""
    with caplog.at_level(logging.INFO):
        joke = get_fallback_joke("negro")
        assert joke
        assert "\n" in joke
        assert "(reserva offline)" in caplog.text


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tests de Guard y Validación de Estructura
# ─────────────────────────────────────────────────────────────────────────────

def test_has_prohibited_opening():
    """Verifica que detecta correctamente aperturas prohibidas y frases defensivas."""
    bad_phrases = [
        "¿Sabías que los servidores no duermen?",
        "¿sabias que en la edad media no había internet?",
        "Un dato curioso sobre los programadores.",
        "Curiosidad: las hormigas no tienen pulmones.",
        "Vaya por Dios, qué cosas.",
        "Datos y chiste son dos cosas diferentes.",
        "Dato: en Python todo es un objeto.",
    ]
    for p in bad_phrases:
        assert has_prohibited_opening(p), f"No detectó apertura prohibida en: '{p}'"

    good_phrases = [
        "— ¿Qué hace una abeja en el gimnasio?\n— ¡Zum-ba!",
        "¿Por qué los pájaros no usan Facebook?\nPorque ya tienen Twitter.",
        "Había una vez un perro que respiraba por el culo.\nSe sentó y se murió.",
    ]
    for p in good_phrases:
        assert not has_prohibited_opening(p), f"Falso positivo en apertura: '{p}'"


def test_validate_joke_output():
    """Verifica el cumplimiento del contrato estricto de chiste."""
    # Válido: 2 líneas setup + remate
    valid_2 = "¿Qué le dice un cero a otro?\nNo somos nada."
    ok, _ = validate_joke_output(valid_2)
    assert ok

    # Válido: 3 líneas setup + remate + tagline
    valid_3 = "¿Qué hace un huérfano en un trampolín?\nRebota, porque no tiene quién lo baje.\nQué silencio incómodo."
    ok, _ = validate_joke_output(valid_3)
    assert ok

    # Inválido: más de 4 líneas
    invalid_lines = "Línea 1\nLínea 2\nLínea 3\nLínea 4\nLínea 5"
    ok, err = validate_joke_output(invalid_lines)
    assert not ok
    assert "4 líneas" in err

    # Inválido: apertura prohibida
    invalid_curiosity = "¿Sabías que los programadores toman café?\nEs verdad."
    ok, err = validate_joke_output(invalid_curiosity)
    assert not ok
    assert "prohibida" in err


# ─────────────────────────────────────────────────────────────────────────────
# 3. Tests de Resolución de Estilo por Nivel de Personalidad
# ─────────────────────────────────────────────────────────────────────────────

def test_resolve_joke_style_by_level():
    """Verifica los estilos por defecto según nivel de personalidad."""
    # Niveles 0 a 2 -> blanco
    assert resolve_joke_style(user_text="chiste", level=0)[0] == "blanco"
    assert resolve_joke_style(user_text="contame un chiste", level=1)[0] == "blanco"
    assert resolve_joke_style(user_text="un chiste", level=2)[0] == "blanco"

    # Nivel 3 -> acido
    assert resolve_joke_style(user_text="chiste", level=3)[0] == "acido"

    # Niveles 4 y 5 -> negro por defecto si no especifica
    assert resolve_joke_style(user_text="chiste", level=4)[0] == "negro"
    assert resolve_joke_style(user_text="chiste", level=5)[0] == "negro"

    # Solicitudes explícitas
    assert resolve_joke_style(user_text="chiste de programadores", level=1)[0] == "programador"
    assert resolve_joke_style(user_text="chiste absurdo", level=2)[0] == "absurdo"
    assert resolve_joke_style(user_text="chiste acido", level=1)[0] == "acido"

    # En niveles 0 y 1, el pedido de humor negro se suaviza a blanco
    assert resolve_joke_style(user_text="chiste de humor negro", level=0)[0] == "blanco"
    assert resolve_joke_style(user_text="chiste de humor negro", level=5)[0] == "negro"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tests de IntentRouter (Capa 1)
# ─────────────────────────────────────────────────────────────────────────────

def test_intent_router_pedir_chiste():
    """Verifica la detección de pedir_chiste con variaciones de disparadores y extracción de estilo/tema."""
    test_cases = [
        ("chiste", "pedir_chiste"),
        ("un chiste", "pedir_chiste"),
        ("chiste de humor negro", "pedir_chiste"),
        ("chiste de programadores", "pedir_chiste"),
        ("contame un chiste", "pedir_chiste"),
        ("contame un chiste negro", "pedir_chiste"),
        ("contame un chiste acido", "pedir_chiste"),
        ("tirate un chiste", "pedir_chiste"),
        ("decime un chiste", "pedir_chiste"),
        ("humor negro", "pedir_chiste"),
        ("haceme reir", "pedir_chiste"),
        ("contame algo gracioso", "pedir_chiste"),
        ("algo oscuro y gracioso", "pedir_chiste"),
        ("joke", "pedir_chiste"),
        ("podes contarme un chiste", "pedir_chiste"),
        ("tirate otro chiste", "pedir_chiste"),
        ("otro chiste", "pedir_chiste"),
    ]

    for phrase, expected_intent in test_cases:
        intent = intent_router.parse(phrase)
        assert intent is not None, f"No se detectó intent para: '{phrase}'"
        assert intent.nombre == expected_intent, f"Intent esperado {expected_intent}, obtenido {intent.nombre} para '{phrase}'"
        assert "estilo" in intent.extra
        assert "tema" in intent.extra


def test_intent_router_queja_chiste():
    """Verifica que las quejas sobre chistes se detectan prioritariamente como queja_chiste."""
    complaints = [
        "no es un chiste",
        "eso no fue un chiste",
        "eso no es un chiste",
        "me estas contando datos",
        "me estás contando datos",
        "pero me estás contando datos, no chistes",
        "no me hiciste reir",
        "no me hiciste reír",
        "que mal chiste",
        "qué mal chiste",
        "eso no es gracioso",
        "te pedi un chiste",
        "te pedí un chiste",
        "eso no era un chiste",
        "eso es un dato",
    ]

    for phrase in complaints:
        intent = intent_router.parse(phrase)
        assert intent is not None, f"No se detectó intent para queja: '{phrase}'"
        assert intent.nombre == "queja_chiste", f"Para '{phrase}' se obtuvo intent='{intent.nombre}' en lugar de 'queja_chiste'"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Tests de FuzzyInterpreter (Capa 2 y 3)
# ─────────────────────────────────────────────────────────────────────────────

def test_fuzzy_interpreter_pedir_chiste_and_queja():
    """Verifica que el intérprete fuzzy resuelve pedir_chiste y queja_chiste."""
    res_chiste = fuzzy_interpreter.interpret("contame un chiste")
    assert res_chiste is not None
    assert res_chiste.intent == "pedir_chiste"
    assert res_chiste.status == "execute_direct"

    res_queja = fuzzy_interpreter.interpret("eso no fue un chiste")
    assert res_queja is not None
    assert res_queja.intent == "queja_chiste"
    assert res_queja.status == "execute_direct"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Tests de Generación con Guard, Reintento y Fallback a Banco
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_joke_without_provider():
    """Sin proveedor IA configurado, debe entregar directamente del banco local."""
    joke = generate_joke("chiste de programadores", provider=None)
    assert joke
    valid, err = validate_joke_output(joke)
    assert valid, f"Chiste devuelto inválido ({err}): {joke}"


def test_generate_joke_guard_retry_success():
    """Si el modelo devuelve un dato curioso en el primer intento pero se corrige en el segundo."""
    mock_provider = MagicMock()
    # 1er llamado: devuelve dato curioso prohibido
    # 2do llamado: devuelve chiste válido con setup y remate
    mock_provider.chat.side_effect = [
        ChatResponse(content="¿Sabías que los servidores no duermen? Dato tecnológico.", model="mock", provider="mock"),
        ChatResponse(content="— ¿Por qué los programadores prefieren el modo oscuro?\n— Porque la luz atrae a los bichos.", model="mock", provider="mock"),
    ]

    joke = generate_joke("un chiste de programadores", provider=mock_provider)
    assert "¿Sabías que" not in joke
    assert "modo oscuro" in joke
    assert mock_provider.chat.call_count == 2


def test_generate_joke_guard_fallback_on_double_failure(caplog):
    """Si el modelo falla dos veces consecutivas, entrega del banco local silenciosamente."""
    mock_provider = MagicMock()
    mock_provider.chat.side_effect = [
        ChatResponse(content="¿Sabías que la RAM guarda datos volátiles?", model="mock", provider="mock"),
        ChatResponse(content="Un dato curioso: en 1970 se creó Unix.", model="mock", provider="mock"),
    ]

    with caplog.at_level(logging.INFO):
        joke = generate_joke("un chiste", provider=mock_provider)
        assert joke
        assert not has_prohibited_opening(joke)
        assert "(reserva offline)" in caplog.text


# ─────────────────────────────────────────────────────────────────────────────
# 7. Tests de Meta-corrección ante Quejas (handle_joke_complaint)
# ─────────────────────────────────────────────────────────────────────────────

def test_handle_joke_complaint_flow():
    """Ante queja, no se defiende y regenera inmediatamente aceptando el fallo brevemente."""
    mock_provider = MagicMock()
    mock_provider.chat.return_value = ChatResponse(
        content="¿Qué hace una impresora en un velorio?\nDa el pésame en papel continuo.",
        model="mock",
        provider="mock",
    )

    response = handle_joke_complaint("pero me estás contando datos, no chistes", provider=mock_provider)
    assert response
    assert not has_prohibited_opening(response)
    assert "Vaya por Dios" not in response
    assert "Datos y chiste" not in response
    assert "impresora" in response or "\n" in response

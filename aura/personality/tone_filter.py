"""
AURA — Filtro de Seguridad y Tono (Fase 51)

Garantiza que, independientemente del nivel de grosería (incluyendo Grok y Sin Filtro),
el sistema NUNCA genere ni tolere:
  - Discurso de odio (racismo, xenofobia, homofobia, antisemitismo, etc.)
  - Discriminación por religión, etnia, género, condición o discapacidad
  - Amenazas reales de violencia física o autolesión
  - Contenido ilegal grave (armas, explosivos, malware destructivo, CSAM)

El modo grosero debe ser divertido, irreverente y mordaz, JAMÁS tóxico ni dañino.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Union, List, Tuple

from aura.personality.personalities import (
    PersonalityLevel,
    PersonalityMode,
    get_personality,
)
from utils.logger import get_logger

_logger = get_logger("aura.personality.filter")


@dataclass
class ToneFilterResult:
    """Resultado de la evaluación del filtro de tono y seguridad."""
    is_safe: bool
    category: Optional[str] = None
    reason: Optional[str] = None
    message: str = ""


# ──────────────────────────────────────────────────────────────
# Patrones de Bloqueo Estricto (Inadmisibles en cualquier nivel)
# ──────────────────────────────────────────────────────────────

# 1. Discurso de odio, discriminación y supremacismo
_HATE_SPEECH_PATTERNS: List[Tuple[str, str]] = [
    (r"\b(nigger|nigga|maric[oó]n|puto de mierda|tortillera|jud[ií]o de mierda|negro de mierda|indio de mierda)\b", "hate_speech"),
    (r"\b(supremac[ií]a blanca|white supremacy|neo-?nazi|hitler ten[ií]a raz[oó]n|muerte a los (gays|jud[ií]os|negros|inmigrantes))\b", "hate_speech"),
    (r"\b(limpieza [eé]tnica|exterminar a los|subhumanos|raza inferior)\b", "discrimination"),
]

# 2. Amenazas reales de violencia, asesinato y autolesión
_VIOLENCE_PATTERNS: List[Tuple[str, str]] = [
    (r"\b(te voy a (matar|degollar|acuchillar|descuartizar|reventar a tiros|pegar un tiro))\b", "violence"),
    (r"\b(voy a matar a|quiero asesinar a|plan para matar a|c[oó]mo matar a)\b", "violence"),
    (r"\b(suic[ií]date|matate|c[oó]mo suicidarme|cortarme las venas|ahorcarse tutorial)\b", "self_harm"),
]

# 3. Contenido ilegal crítico (armas, explosivos, ciberataques destructivos, pedofilia)
_ILLEGAL_PATTERNS: List[Tuple[str, str]] = [
    (r"\b(c[oó]mo (fabricar|hacer|armar) (una bomba|explosivos|c4|dinamita|napalm|molotov))\b", "illegal_content"),
    (r"\b(pornograf[ií]a infantil|child porn|cp links|abuso de menores)\b", "illegal_content"),
    (r"\b(c[oó]mo hackear una central|distribuir ransomware|crear troyano bancario|vender coca[ií]na|comprar armas ilegales)\b", "illegal_content"),
]

_ALL_BLOCKED_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE), category)
    for pattern, category in (_HATE_SPEECH_PATTERNS + _VIOLENCE_PATTERNS + _ILLEGAL_PATTERNS)
]


# ──────────────────────────────────────────────────────────────
# Mensajes de Rechazo Seguros Adaptados al Nivel de Personalidad
# ──────────────────────────────────────────────────────────────

_REJECTION_MESSAGES = {
    0: "Solicitud denegada: la política de seguridad no permite contenido que involucre odio, violencia, discriminación ni actos ilegales.",
    1: "Prefiero no responder a eso. Mantengamos una charla constructiva, sin violencia, odio ni temas ilegales.",
    2: "Incluso con todo mi sarcasmo tengo un límite claro: cero odio, cero amenazas y cero delitos. Cambiá de tema.",
    3: "Che, pará la mano. Ni en pedo me meto con odio, violencia o cosas turbias. Hacé preguntas normales y laburá en serio.",
    4: "Pará un poco, capo. El modo Grok es irreverente, picante y sin filtro bobo, pero NO tolero odio, racismo, violencia real ni porquerías ilegales. Buscate un problema honesto.",
    5: "¡Epa, frená los caballos, fiera! Estoy desquiciada pero no soy forra. Con odio, violencia y cosas turbias no se jode jamás. ¡Arafue con esa basura!",
}


def check_safety(text: str) -> ToneFilterResult:
    """
    Evalúa si un texto cumple las directrices universales de seguridad.
    Retorna ToneFilterResult con is_safe=True o False + categoría y motivo.
    """
    if not text or not text.strip():
        return ToneFilterResult(is_safe=True, message=text)

    clean_text = text.lower()

    for pattern, category in _ALL_BLOCKED_RULES:
        if pattern.search(clean_text):
            reason = f"Violación de seguridad detectada: categoría '{category}'"
            _logger.warning("Filtro de seguridad activado: %s", reason)
            return ToneFilterResult(
                is_safe=False,
                category=category,
                reason=reason,
                message="",
            )

    return ToneFilterResult(is_safe=True, message=text)


def filter_content(
    text: str,
    personality: Union[str, int, PersonalityLevel, PersonalityMode, None] = None,
) -> ToneFilterResult:
    """
    Filtra el texto (tanto entrada como salida) y, si viola las políticas de seguridad,
    reemplaza el contenido con una respuesta de rechazo coherente con la personalidad activa.
    """
    result = check_safety(text)
    if result.is_safe:
        return result

    mode = get_personality(personality)
    level = mode.level
    rejection = _REJECTION_MESSAGES.get(level, _REJECTION_MESSAGES[0])

    return ToneFilterResult(
        is_safe=False,
        category=result.category,
        reason=result.reason,
        message=rejection,
    )


def is_safe_content(text: str) -> bool:
    """Retorna True si el texto es seguro para procesar o emitir."""
    return check_safety(text).is_safe


def sanitize_output(
    text: str,
    personality: Union[str, int, PersonalityLevel, PersonalityMode, None] = None,
) -> str:
    """
    Sanitiza la salida antes de presentarla en la interfaz o por TTS.
    Si el contenido no es seguro, retorna el mensaje de rechazo correspondiente al tono actual.
    """
    res = filter_content(text, personality=personality)
    return res.message if not res.is_safe else text

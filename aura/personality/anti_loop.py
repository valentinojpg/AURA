"""
AURA — Guard Anti-Loop Post-Generación (Fase 51 / Fix de Estilo)

Inspecciona las respuestas generadas por los modelos de lenguaje para detectar
y neutralizar patrones de repetición compulsiva (bucles o repetición de frases idénticas).
Si detecta repetición:
  1. Recorta en la primera repetición.
  2. Si el recorte deja menos de 1 frase útil, regenera UNA vez con mayor repeat_penalty y max_tokens reducidos.
  3. Registra cada activación en logs.
"""

from __future__ import annotations

import re
from typing import Callable, Optional, Tuple
from utils.logger import get_logger

_logger = get_logger("aura.personality.anti_loop")

# Signos de puntuación para separación de oraciones
_SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?\n])\s+")


def _normalize_phrase(text: str) -> str:
    """Normaliza una frase para comparación difusa de duplicados."""
    # Eliminar puntuación, espacios repetidos y minúsculas
    cleaned = re.sub(r"[^\w\s]", "", text.lower())
    return " ".join(cleaned.split())


def detect_repetition(text: str) -> Tuple[bool, int, str]:
    """
    Analiza si el texto repite:
      a) Una misma oración dos veces.
      b) Una misma secuencia de 6 o más palabras consecutivas.

    Returns:
        (has_repetition, cut_index, reason)
    """
    if not text or len(text.strip()) < 20:
        return False, -1, ""

    # ─────────────────────────────────────────────────────────
    # 1. Detección de oraciones duplicadas
    # ─────────────────────────────────────────────────────────
    # Buscar límites de oraciones con sus posiciones exactas en el texto
    matches = list(re.finditer(r"[^.!?\n]+(?:[.!?\n]|$)", text))
    seen_sentences: dict[str, int] = {}

    for m in matches:
        raw_sentence = m.group(0).strip()
        norm = _normalize_phrase(raw_sentence)

        # Solo evaluar oraciones con significado (al menos 3 palabras y 12 caracteres)
        words = norm.split()
        if len(words) >= 3 and len(norm) >= 12:
            if norm in seen_sentences:
                cut_idx = m.start()
                preview = raw_sentence[:35] + "..." if len(raw_sentence) > 35 else raw_sentence
                reason = f"oración repetida: '{preview}'"
                return True, cut_idx, reason
            seen_sentences[norm] = m.start()

    # ─────────────────────────────────────────────────────────
    # 2. Detección de secuencias de 6+ palabras repetidas (n-grams)
    # ─────────────────────────────────────────────────────────
    words_with_spans: list[Tuple[str, int, int]] = []
    for m in re.finditer(r"\b\w+\b", text):
        words_with_spans.append((m.group(0).lower(), m.start(), m.end()))

    N = 6
    if len(words_with_spans) >= N * 2:
        seen_ngrams: dict[tuple, int] = {}
        i = 0
        while i <= len(words_with_spans) - N:
            ngram = tuple(w[0] for w in words_with_spans[i : i + N])
            start_char = words_with_spans[i][1]

            if ngram in seen_ngrams:
                prev_start = seen_ngrams[ngram]
                if start_char >= prev_start + len(" ".join(ngram)):
                    reason = f"secuencia de {N}+ palabras repetida: '{' '.join(ngram)}'"
                    return True, start_char, reason
            else:
                seen_ngrams[ngram] = start_char
            i += 1

    return False, -1, ""


def trim_at_repetition(text: str, cut_index: int) -> str:
    """
    Recorta el texto exactamente antes del inicio de la repetición
    y asegura que el texto resultante termine con puntuación limpia.
    """
    if cut_index <= 0 or cut_index >= len(text):
        return text.strip()

    trimmed = text[:cut_index].rstrip()

    # Si cortó justo tras una frase completa, preservar la puntuación
    if trimmed and trimmed[-1] not in ".!?":
        # Buscar el último signo de cierre en trimmed
        last_punct = max(trimmed.rfind("."), trimmed.rfind("!"), trimmed.rfind("?"))
        if last_punct > len(trimmed) * 0.6:
            trimmed = trimmed[: last_punct + 1]

    return trimmed.strip()


def is_useful_sentence(text: str) -> bool:
    """
    Determina si un fragmento de texto constituye al menos una frase útil
    (al menos 3 palabras y longitud suficiente para comunicar un mensaje).
    """
    if not text:
        return False
    words = re.findall(r"\b\w+\b", text)
    return len(words) >= 3 and len(text.strip()) >= 10


def apply_anti_loop(
    text: str,
    regenerator: Optional[Callable[[float, int], str]] = None,
    current_repeat_penalty: float = 1.2,
    current_max_tokens: int = 150,
) -> str:
    """
    Aplica el guard anti-loop a una respuesta generada.

    Args:
        text: Respuesta generada por el LLM.
        regenerator: Función opcional (repeat_penalty, max_tokens) -> str para reintentar.
        current_repeat_penalty: Penalidad de repetición usada originalmente.
        current_max_tokens: Límite de tokens de la llamada original.

    Returns:
        Texto saneado, recortado o regenerado.
    """
    has_rep, cut_idx, reason = detect_repetition(text)

    if not has_rep:
        return text

    _logger.warning("AntiLoopGuard activado: detectada %s. Recortando en índice %d.", reason, cut_idx)
    trimmed = trim_at_repetition(text, cut_idx)

    # Si el recorte conserva al menos 1 frase útil, retornarlo directamente
    if is_useful_sentence(trimmed):
        _logger.info("AntiLoopGuard: respuesta recortada exitosamente (%d chars): '%s'", len(trimmed), trimmed[:40])
        return trimmed

    # Si el recorte dejó menos de 1 frase útil y tenemos función de regeneración
    if regenerator is not None:
        new_repeat = current_repeat_penalty + 0.1
        new_max_tokens = max(40, int(current_max_tokens * 0.75))
        _logger.warning(
            "AntiLoopGuard: recorte insuficiente (<1 frase útil). Regenerando UNA vez con "
            "repeat_penalty=%.2f y max_tokens=%d.",
            new_repeat,
            new_max_tokens,
        )
        try:
            regenerated = regenerator(new_repeat, new_max_tokens)
            # Evaluar la respuesta regenerada sin loop infinito
            has_rep_2, cut_idx_2, reason_2 = detect_repetition(regenerated)
            if has_rep_2:
                trimmed_2 = trim_at_repetition(regenerated, cut_idx_2)
                if is_useful_sentence(trimmed_2):
                    return trimmed_2
                return regenerated.strip()
            return regenerated.strip()
        except Exception as e:
            _logger.error("AntiLoopGuard: error durante la regeneración: %s", e)

    # Si no se pudo regenerar o el regenerator falló, retornar el mejor esfuerzo
    return trimmed if is_useful_sentence(trimmed) else text.strip()

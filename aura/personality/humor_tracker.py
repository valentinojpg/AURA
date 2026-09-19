"""
AURA — Tracker y Validador de Humor (Fase 64).

Gestiona:
1. Limpieza de etiquetas de esquema filtradas ('Setup:', 'Remate:', 'Punchline:', 'Tagline:').
2. Tracking de sesión del último intent de humor ('roast' | 'chiste' | 'ninguno').
3. Validación estricta de coherencia para roasts (2da persona + términos curados + máx 3 líneas).
4. Validación estricta de coherencia para chistes (sin etiquetas + sin aperturas prohibidas + máx 4 líneas + remate no repetitivo).
"""

from __future__ import annotations

import re
import threading
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple

from utils.logger import get_logger

_logger = get_logger("aura.personality.humor_tracker")

_lock = threading.Lock()
_last_humor_intent: Optional[str] = None
_last_roast_state: Dict[str, Any] = {
    "level": 5,
    "roast": "",
    "user_text": "",
}
_last_joke_state: Dict[str, Any] = {
    "estilo": "blanco",
    "tema": "",
    "temperature": 0.75,
    "level": 0,
    "joke": "",
}

# ──────────────────────────────────────────────────────────────
# 1. Limpieza de etiquetas de esquema
# ──────────────────────────────────────────────────────────────

_RE_LABELS_START = re.compile(
    r"(?im)^\s*(?:setup|remate|punchline|tagline|roast|dardo|chiste|premisa|conclusion)\s*:\s*",
)
_RE_LABELS_INLINE = re.compile(
    r"(?i)\b(?:setup|remate|punchline|tagline|roast)\s*:\s*",
)

def strip_humor_labels(text: str) -> str:
    """
    Elimina cualquier etiqueta de esquema como 'Setup:', 'Remate:', 'Punchline:', 'Tagline:'
    tanto al inicio de línea como en medio del texto.
    """
    if not text:
        return ""
    # Quitar al inicio de líneas
    cleaned = _RE_LABELS_START.sub("", text)
    # Quitar ocurrencias inline
    cleaned = _RE_LABELS_INLINE.sub("", cleaned)
    # Normalizar saltos de línea y quitar líneas vacías redundantes
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# 2. Tracking de sesión (last_humor_intent)
# ──────────────────────────────────────────────────────────────

def set_last_humor_intent(intent: Optional[str]) -> None:
    """Fija el último intent de humor ejecutado en la sesión ('roast', 'chiste' o 'ninguno')."""
    global _last_humor_intent
    with _lock:
        _last_humor_intent = intent
        _logger.debug("last_humor_intent actualizado a: %s", intent)

def get_last_humor_intent() -> Optional[str]:
    """Retorna el último intent de humor ejecutado ('roast', 'chiste' o None)."""
    with _lock:
        return _last_humor_intent

def save_last_roast_state(level: int, roast_text: str, user_text: str) -> None:
    """Guarda el estado del último roast para soporte de quejas y meta-corrección."""
    with _lock:
        _last_roast_state["level"] = level
        _last_roast_state["roast"] = roast_text
        _last_roast_state["user_text"] = user_text

def get_last_roast_state() -> Dict[str, Any]:
    """Retorna copia del estado del último roast."""
    with _lock:
        return dict(_last_roast_state)

def save_last_joke_state(estilo: str, tema: str, temp: float, level: int, joke: str) -> None:
    """Guarda el estado del último chiste para soporte de quejas y meta-corrección."""
    with _lock:
        _last_joke_state["estilo"] = estilo
        _last_joke_state["tema"] = tema
        _last_joke_state["temperature"] = temp
        _last_joke_state["level"] = level
        _last_joke_state["joke"] = joke

def get_last_joke_state() -> Dict[str, Any]:
    """Retorna copia del estado del último chiste."""
    with _lock:
        return dict(_last_joke_state)


# ──────────────────────────────────────────────────────────────
# 3. Validación de Roasts
# ──────────────────────────────────────────────────────────────

_SECOND_PERSON_TERMS: Set[str] = {
    "vos", "tu", "tú", "te", "ti", "tuyo", "tuya", "tuyos", "tuyas",
    "sos", "eres", "tenes", "tenés", "tienes", "haces", "hacés",
    "usas", "usás", "andas", "andás", "mirá", "mira", "andá", "anda",
    "ponete", "ponte", "hacete", "hazte", "tené", "ten", "fijate",
    "fíjate", "dejá", "deja", "venís", "vienes", "pedís", "pides",
    "seguís", "sigues", "laburá", "trabajá", "terminá", "escribís",
    "parecés", "pareces", "creés", "crees", "sabés", "sabes",
}

CURATED_INSULTS_BY_LEVEL: Dict[int, List[str]] = {
    2: [
        "chiste", "luces", "bug", "bugs", "compila", "casualidad", "procrastinando",
        "milagro", "ingenieria", "asilo", "piedad", "reinicio", "desastre", "manual",
        "lento", "espagueti", "productividad", "paciencia"
    ],
    3: [
        "fiaca", "pesado", "jodas", "joder", "jodes", "basura", "fruta", "bolas",
        "rompas", "paciencia", "desastre", "vago", "pelotudo", "inutil", "fantasma",
        "payaso", "molesto", "vaga", "ganso", "dormido", "lento", "verguenza",
        "pobre", "pete", "gil", "chamuyo", "muerto", "chiste", "chicanas",
        "macana", "respiro", "calidad", "cueva", "arbolito", "luces", "quemado"
    ],
    4: [
        "orangutan", "inutil", "desastre", "simulacion", "pacatos", "pacato",
        "mediocre", "chiste", "verguenza", "termodinamica", "patetico", "humillante",
        "payaso", "arbolito", "bug", "bugs", "mono", "estupido", "tarado",
        "falla", "arruinas", "muerto", "fracaso", "piedad", "asilo", "lobotomia",
        "foca", "inoperante", "basura", "pelotudo", "gil", "parasito", "deadlocks",
        "ego", "aberracion", "warnings", "linter", "eslabon", "espaguetis", "deuda",
        "tecnica", "ramas"
    ],
    5: [
        "mierda", "carajo", "puta", "puto", "pelotudo", "pelotuda", "boludo",
        "boluda", "forro", "forra", "desastre", "inutil", "tarado", "tarada",
        "estupido", "estupida", "imbecil", "porqueria", "asqueroso", "foca",
        "arbolito", "pedos", "joder", "jodas", "mandinga", "muerto", "fracasado",
        "fracaso", "cagon", "pete", "cornudo", "infeliz", "parasito", "inservible",
        "inoperante", "salvaje", "chiste", "humillante", "payaso", "animal",
        "orto", "concha", "bosta", "pedazos", "verguenza", "diablo"
    ]
}

def _normalize_text(text: str) -> str:
    """Normaliza quitando acentos y puntuación."""
    norm = "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )
    return norm.lower()

def validate_roast_output(text: str, level: int = 5) -> Tuple[bool, str]:
    """
    Valida la salida de un roast:
      - No vacío.
      - Sin etiquetas fugadas ('Remate:', 'Setup:', etc.).
      - Máximo 3 líneas.
      - Debe contener segunda persona (vos/tu/te/tuyo/etc.).
      - Debe contener al menos un término curado del nivel correspondiente.
    """
    if not text or not text.strip():
        return False, "Salida vacía"

    if _RE_LABELS_INLINE.search(text) or _RE_LABELS_START.search(text):
        return False, "Etiqueta de esquema detectada en la salida ('Setup:', 'Remate:', etc.)"

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 3:
        return False, f"Longitud mayor a 3 líneas ({len(lines)} líneas)"

    if level < 2:
        return True, ""

    norm = _normalize_text(text)
    words = set(re.findall(r"\b\w+\b", norm))

    has_second_person = any(w in words for w in _SECOND_PERSON_TERMS)
    if not has_second_person:
        return False, "No contiene tratamiento en segunda persona (vos/tu/te/tuyo)"

    curated = CURATED_INSULTS_BY_LEVEL.get(level, CURATED_INSULTS_BY_LEVEL[5])
    has_curated_term = any(term in norm for term in curated)
    if not has_curated_term:
        return False, f"No contiene términos característicos curados del nivel {level}"

    return True, ""


# ──────────────────────────────────────────────────────────────
# 4. Validación de Chistes
# ──────────────────────────────────────────────────────────────

_STOPWORDS_SPANISH = {
    "para", "como", "este", "esta", "estos", "estas", "pero", "porque",
    "cuando", "donde", "quien", "sobre", "entre", "desde", "hasta",
    "hacia", "entonces", "tambien", "estaba", "estaban", "habia",
    "dijo", "dice", "iban", "otro", "otra", "otros", "otras", "unos", "unas"
}

def validate_joke_coherence(text: str, prohibited_openings: List[str]) -> Tuple[bool, str]:
    """
    Valida la salida de un chiste:
      - No vacío.
      - Sin etiquetas fugadas ('Setup:', 'Remate:', etc.).
      - Sin aperturas prohibidas o trivia enciclopédica.
      - Máximo 4 líneas.
      - El remate no puede repetir palabras del setup textualmente.
    """
    if not text or not text.strip():
        return False, "Salida vacía"

    if _RE_LABELS_INLINE.search(text) or _RE_LABELS_START.search(text):
        return False, "Etiqueta de esquema detectada ('Setup:', 'Remate:', etc.)"

    clean_lower = text.strip().lower()
    first_line = clean_lower.splitlines()[0] if clean_lower.splitlines() else clean_lower
    for p in prohibited_openings:
        if first_line.startswith(p) or p in clean_lower:
            return False, f"Apertura o frase prohibida detectada ('{p}')"

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 4:
        return False, f"Longitud mayor a 4 líneas ({len(lines)} líneas)"

    if len(lines) >= 2:
        setup_text = _normalize_text(" ".join(lines[:-1]))
        remate_text = _normalize_text(lines[-1])

        setup_tokens = set(w for w in re.findall(r"\b\w{4,}\b", setup_text) if w not in _STOPWORDS_SPANISH)
        remate_tokens = [w for w in re.findall(r"\b\w{4,}\b", remate_text) if w not in _STOPWORDS_SPANISH]

        if remate_tokens:
            repeated = [w for w in remate_tokens if w in setup_tokens]
            ratio = len(repeated) / len(remate_tokens)
            if ratio >= 0.70 and len(remate_tokens) >= 3:
                return False, "El remate repite palabras del setup textualmente (falta de remate real)"

    if len(lines) < 2 and len(text) > 130 and ("?" not in text and ":" not in text and "—" not in text and "-" not in text):
        return False, "Sin estructura de premisa y remate"

    return True, ""

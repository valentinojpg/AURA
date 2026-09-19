"""
AURA — Módulo Central de Chistes y Humor Estructurado (Fase 62 / Fase 64).

Provee un pipeline dedicado para solicitudes de chistes ("pedir_chiste") y manejo de quejas ("queja_chiste"):
  1. Few-shot solo positivo: 2 ejemplos buenos por estilo, sin ejemplos prohibidos en el prompt.
  2. Sin etiquetas de esquema: prohibido escribir "Setup:", "Remate:", etc.; post-proceso de limpieza regex.
  3. Parámetros cuerdos: temperature 0.75 fija (sin escalada), repeat_penalty 1.1, sin freq/pres penalty, max_tokens 120.
  4. Routing estricto y tracking de last_humor_intent en sesión.
  5. Soporte de HUMOR_SOURCE (bank | model | hybrid) y HUMOR_PROVIDER (auto | local | <nombre>).
  6. Validación estricta de coherencia y degradación automática a banco offline ante doble fallo.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from config.settings import settings
from utils.logger import get_logger
from aura.personality.personalities import get_current_personality
from aura.personality.tone_filter import filter_content, sanitize_output
from aura.personality.anti_loop import apply_anti_loop
from aura.personality.humor_tracker import (
    strip_humor_labels,
    validate_joke_coherence,
    set_last_humor_intent,
    save_last_joke_state,
    get_last_joke_state,
)
from aura.personality.humor_provider import get_humor_provider
from ai.provider_interface import ChatMessage

_logger = get_logger("aura.personality.jokes")

JOKES_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "fun" / "jokes.json"

VALID_STYLES = {"negro", "acido", "absurdo", "programador", "blanco"}

PROHIBITED_OPENINGS = [
    "¿sabías que",
    "¿sabias que",
    "sabías que",
    "sabias que",
    "un dato curioso",
    "un dato",
    "curiosidad:",
    "curiosidad",
    "vaya por dios",
    "datos y chiste",
    "dato:",
    "¿sabías esto",
    "sabías esto",
    "sabias esto",
]


def load_jokes_data() -> Dict[str, Any]:
    """Carga data/fun/jokes.json con codificación UTF-8 segura."""
    if JOKES_FILE.exists():
        try:
            with open(JOKES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            _logger.error(f"Error cargando {JOKES_FILE}: {e}")

    # Fallback interno mínimo si el archivo no estuviera disponible
    return {
        "prohibidos": [
            "¿Sabías que los servidores consumen energía? Es un chiste tecnológico.",
            "Un dato curioso: en Roma no tenían computadoras. Vaya por Dios.",
        ],
        "ejemplos_buenos": {
            "blanco": [
                {"setup": "¿Qué le dice un cero a otro?", "remate": "No somos nada.", "tagline": None}
            ]
        },
        "banco": {
            "blanco": [
                {"setup": "¿Qué le dice un cero a otro?", "remate": "No somos nada.", "tagline": None}
            ]
        },
    }


def format_joke_obj(joke_obj: Dict[str, Any]) -> str:
    """Convierte un objeto de chiste (setup, remate, tagline) en texto con saltos de línea."""
    setup = str(joke_obj.get("setup") or "").strip()
    remate = str(joke_obj.get("remate") or "").strip()
    tagline = joke_obj.get("tagline")

    lines = []
    if setup:
        lines.append(setup)
    if remate:
        lines.append(remate)
    if tagline and str(tagline).strip():
        lines.append(str(tagline).strip())

    return "\n".join(lines)


def get_fallback_joke(estilo: str = "blanco") -> str:
    """Obtiene un chiste del banco local offline y registra la reserva en el log."""
    data = load_jokes_data()
    banco = data.get("banco", {})
    estilo_clean = estilo.lower() if estilo and estilo.lower() in VALID_STYLES else "blanco"

    chistes = banco.get(estilo_clean) or banco.get("blanco") or []
    if not chistes:
        for lst in banco.values():
            if lst:
                chistes = lst
                break

    if not chistes:
        _logger.info("Chiste entregado desde banco local (reserva offline)")
        return "— ¿Qué le dice un cero a otro cero en la calculadora?\n— No somos nada."

    elegido = random.choice(chistes)
    _logger.info(f"Chiste entregado desde banco local (reserva offline) [estilo={estilo_clean}]")
    formatted = format_joke_obj(elegido)
    return strip_humor_labels(formatted)


def has_prohibited_opening(text: str) -> bool:
    """Verifica si el texto comienza con alguna de las aperturas prohibidas o contiene trivia."""
    clean = text.strip().lower()
    first_line = clean.splitlines()[0] if clean.splitlines() else clean

    for p in PROHIBITED_OPENINGS:
        if first_line.startswith(p) or p in clean:
            return True
    return False


def validate_joke_output(text: str) -> Tuple[bool, str]:
    """
    Valida la salida de un chiste según el contrato estricto de Fase 64:
      - No vacío
      - Sin etiquetas de esquema ('Setup:', 'Remate:', etc.)
      - Sin aperturas prohibidas
      - Longitud máxima de 4 líneas
      - El remate no puede repetir palabras del setup textualmente
    """
    return validate_joke_coherence(text, PROHIBITED_OPENINGS)


def resolve_joke_style(
    user_text: str = "",
    explicit_style: str = "",
    explicit_tema: str = "",
    level: Optional[int] = None,
) -> Tuple[str, str]:
    """
    Determina el estilo y tema del chiste:
      1. Si el usuario lo especificó explícitamente en el texto, se prioriza.
      2. Si no, se asigna el estilo por defecto según el nivel de personalidad.
    """
    if level is None:
        level = get_current_personality().level

    norm = user_text.lower()
    estilo = explicit_style.lower().strip() if explicit_style else ""
    tema = explicit_tema.strip()

    # Detección por palabras clave en el texto
    if "negro" in norm or "oscuro" in norm:
        estilo = "negro"
    elif any(k in norm for k in ("acido", "ácido", "sarcastico", "sarcástico", "ironico", "irónico")):
        estilo = "acido"
    elif any(k in norm for k in ("absurdo", "bizarro", "tonto", "sin sentido")):
        estilo = "absurdo"
    elif any(k in norm for k in ("programador", "programadores", "codigo", "código", "software", "dev", "python", "nerd", "geek")):
        estilo = "programador"
    elif any(k in norm for k in ("blanco", "limpio", "sano", "familiar", "tierno", "infantil")):
        estilo = "blanco"

    # Extracción de tema (ej: "chiste de matematicas")
    if not tema:
        m = re.search(r"chiste\s+(?:de|sobre)\s+([a-záéíóúñ]+)", norm)
        if m:
            t = m.group(1).strip()
            if t not in ("humor", "humor negro", "programador", "programadores", "mierda"):
                tema = t

    # Si no se determinó estilo, aplicar default por nivel de personalidad
    if estilo not in VALID_STYLES:
        if level <= 2:
            estilo = "blanco"
        elif level == 3:
            estilo = "acido"
        else:  # 4 y 5
            estilo = "negro"

    # En niveles 0 y 1, si pidieron humor negro, suavizar a blanco para respetar el tono formal/amable
    if level < 2 and estilo == "negro":
        estilo = "blanco"

    return estilo, tema


def generate_joke(
    user_text: str,
    estilo: str = "",
    tema: str = "",
    provider: Optional[Any] = None,
    is_correction: bool = False,
    prev_temp: Optional[float] = None,
) -> str:
    """
    Genera un chiste estructurado respetando Fase 64:
      - Few-shot positivo (2 ejemplos buenos, sin ejemplos prohibidos en contexto).
      - Sin etiquetas 'Setup:' / 'Remate:'.
      - Parámetros cuerdos: temperature=0.75 fija, repeat_penalty=1.1, max_tokens=120, sin escalada.
      - Validación de coherencia y fallback automático a banco local ante doble fallo.
      - Respeto a HUMOR_SOURCE (bank | model | hybrid).
    """
    # Chequeo de seguridad preventivo
    safety = filter_content(user_text)
    if not safety.is_safe:
        return safety.message

    # Actualizar last_humor_intent en sesión
    set_last_humor_intent("chiste")

    curr_mode = get_current_personality()
    level = curr_mode.level
    final_style, final_tema = resolve_joke_style(user_text, estilo, tema, level=level)

    humor_source = settings.get("HUMOR_SOURCE", "hybrid").strip().lower()

    # Si HUMOR_SOURCE=bank: entregar instantáneo desde banco local sin consultar modelo
    if humor_source == "bank":
        fallback = get_fallback_joke(final_style)
        save_last_joke_state(final_style, final_tema, 0.75, level, fallback)
        return fallback

    # Resolver proveedor con HUMOR_PROVIDER si no fue provisto
    if provider is None:
        provider = get_humor_provider()

    # Si aún no hay proveedor disponible, usar reserva del banco local
    if provider is None:
        fallback = get_fallback_joke(final_style)
        save_last_joke_state(final_style, final_tema, 0.75, level, fallback)
        return fallback

    data = load_jokes_data()
    ejemplos_buenos = data.get("ejemplos_buenos", {}).get(final_style, [])

    # 1. FEW-SHOT SOLO POSITIVO: exactamente 2 ejemplos buenos formateados SIN ETIQUETAS
    few_shot_lines = []
    for ex in ejemplos_buenos[:2]:
        s = (ex.get("setup") or "").strip()
        r = (ex.get("remate") or "").strip()
        t = (ex.get("tagline") or "").strip()
        parts = [s, r]
        if t:
            parts.append(t)
        few_shot_lines.append("\n".join(parts))
    few_shot_prompt = "\n---\n".join(few_shot_lines)

    # 2. Parámetros cuerdos: temperature 0.75 fija (escalada derogada en todo el proyecto)
    temp = 0.75
    max_tokens = 120
    repeat_penalty = 1.1

    tema_instruction = f" sobre '{final_tema}'" if final_tema else ""

    correction_header = ""
    if is_correction:
        correction_header = (
            "AVISO DE CORRECCIÓN:\n"
            "Tu mensaje anterior falló como chiste. No te defiendas, no expliques qué es un chiste ni hables de datos curiosos.\n"
            "Reescribí AHORA con premisa y remate, sin trivia, sin etiquetas y sin '¿Sabías que...'.\n\n"
        )

    # 3. Prompt de estructura SIN etiquetas de esquema
    system_instruction = f"""
{correction_header}INSTRUCCIÓN OBLIGATORIA DE CHISTE:
El usuario pidió un chiste{tema_instruction}.
Estilo asignado: '{final_style}' | Nivel de personalidad: {level} ({curr_mode.name}).

REGLAS DE FORMATO Y ESTILO:
- Escribí un chiste genuino de 2 o 3 líneas (premisa y remate inesperado).
- MÁXIMO 4 LÍNEAS en total.
- PROHIBIDO escribir etiquetas como 'Setup:', 'Remate:', 'Punchline:' o 'Tagline:'. Solo el texto del chiste.
- PROHIBIDO abrir con '¿Sabías que...', 'Un dato...', 'Curiosidad:' o dar información enciclopédica o curiosidades.
- PROHIBIDO explicar el chiste, disculparse o dar lecciones sobre el humor.
- El remate debe ser cómico, sorpresivo y no repetir palabras de la premisa.
{("- Para humor negro: se permite la ironía sobre desgracias, muerte y fatalidad absurda, sin odio ni ataques a grupos protegidos." if final_style == "negro" else "")}

EJEMPLOS DE REFERENCIA ({final_style}):
{few_shot_prompt}
"""

    from aura.ai.prompt_assembler import assemble_prompt

    sys_prompt = assemble_prompt(
        context="humor",
        personality=curr_mode,
        provider=provider.name if provider else None,
        model=getattr(provider, "model", None),
    )
    messages = [
        ChatMessage(role="system", content=sys_prompt),
        ChatMessage(role="user", content=system_instruction.strip()),
    ]

    def _call_model() -> str:
        resp = provider.chat(
            messages,
            temperature=temp,
            max_tokens=max_tokens,
            repeat_penalty=repeat_penalty,
            frequency_penalty=0.0,
            presence_penalty=0.0,
        )
        return resp.content.strip()

    # Intento 1
    try:
        raw_output = _call_model()
    except Exception as e:
        _logger.warning(f"Error en llamada a provider para chiste: {e}. Usando reserva offline.")
        fallback = get_fallback_joke(final_style)
        save_last_joke_state(final_style, final_tema, temp, level, fallback)
        return fallback

    raw_clean = strip_humor_labels(apply_anti_loop(raw_output))
    is_valid, reason = validate_joke_output(raw_clean)

    if not is_valid:
        _logger.warning(f"Guard de chistes: salida inválida ({reason}). Reintentando con prompt correctivo.")
        try:
            messages.append(ChatMessage(role="assistant", content=raw_clean))
            messages.append(
                ChatMessage(
                    role="user",
                    content=(
                        "Tu mensaje anterior falló como chiste. No te defiendas, no expliques qué es un chiste ni hables de datos. "
                        "Reescribí AHORA con premisa y remate, sin trivia, sin etiquetas 'Setup:'/'Remate:' y sin '¿Sabías que...'."
                    ),
                )
            )
            retry_output = _call_model()
            retry_clean = strip_humor_labels(apply_anti_loop(retry_output))
            is_valid_retry, reason_retry = validate_joke_output(retry_clean)

            if is_valid_retry:
                final_joke = sanitize_output(retry_clean)
                save_last_joke_state(final_style, final_tema, temp, level, final_joke)
                return final_joke
            else:
                # Segundo fallo consecutivo: banco local
                _logger.warning(f"Guard de chistes: segundo fallo consecutivo ({reason_retry}). Usando reserva offline.")
                fallback = get_fallback_joke(final_style)
                save_last_joke_state(final_style, final_tema, temp, level, fallback)
                return fallback
        except Exception as e2:
            _logger.warning(f"Error en reintento de chiste: {e2}. Usando reserva offline.")
            fallback = get_fallback_joke(final_style)
            save_last_joke_state(final_style, final_tema, temp, level, fallback)
            return fallback

    final_joke = sanitize_output(raw_clean)
    save_last_joke_state(final_style, final_tema, temp, level, final_joke)
    return final_joke


def handle_joke_complaint(user_text: str, provider: Optional[Any] = None) -> str:
    """
    Maneja el intent de queja sobre un chiste ("no es un chiste", "me estás contando datos", etc.):
    Regenera UNA vez con prompt correctivo estricto y temperature 0.75 fija (sin escalada).
    """
    last_state = get_last_joke_state()
    last_style = last_state.get("estilo", "blanco")
    last_tema = last_state.get("tema", "")

    _logger.info(f"Meta-corrección: queja detectada ('{user_text}'). Regenerando chiste en estilo '{last_style}'.")

    return generate_joke(
        user_text=user_text,
        estilo=last_style,
        tema=last_tema,
        provider=provider,
        is_correction=True,
    )


# Re-exports para retrocompatibilidad
_save_joke_state = save_last_joke_state

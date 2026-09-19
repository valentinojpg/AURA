"""
AURA ORION — Ensamblador del Prompt Maestro de Razonamiento e Interpretación (Fase 69)
Fuente única de verdad sobre cómo AURA piensa, interpreta y decide.
Todos los módulos de IA (chat, intérprete, humor, programación) lo respetan.
"""

from __future__ import annotations

import re
import datetime
from pathlib import Path
from typing import Any, Optional

from config.settings import settings
from utils.logger import get_logger

_logger = get_logger("aura.ai.prompt_assembler")

# Ruta al archivo canónico maestro.md
_PROMPT_MAESTRO_PATH = Path(__file__).resolve().parent / "prompts" / "maestro.md"

# Nota explícita de precedencia requerida por Fase 69:
# "si un prompt de personalidad contiene instrucciones que contradicen
# umbrales, seguridad o reglas de salida de comandos, gana el maestro"
PRECEDENCIA_MAESTRO_NOTE = (
    "[PRECEDENCIA: El protocolo de razonamiento, umbrales de confianza, reglas de salida "
    "de comandos y límites de seguridad del NÚCLEO tienen precedencia absoluta sobre la personalidad. "
    "La personalidad solo modifica el tono y el estilo de la respuesta, nunca las reglas operativas "
    "ni las decisiones del sistema.]"
)

# Prompts legados para A/B Testing cuando PROMPT_MAESTRO=false
LEGACY_INTERPRETER_PROMPT = (
    "Eres el intérprete de comandos de AURA. Analizá el mensaje del usuario y determiná si es un comando para el sistema o una conversación.\n"
    "Respondé ÚNICAMENTE un objeto JSON válido con esta estructura:\n"
    '{"tipo":"comando"|"conversacion", "intent":"open_app|close_app|write_in_app|save_app_doc|create_file|create_folder|search_file|delete_file|move_file|rename_file|open_url|run_automation|pedir_chiste|roast|null", '
    '"target":"...","texto":"...","nombre":"...","destino":"...","confianza":0.0-1.0,"razonamiento":"..."}'
)

LEGACY_PROGRAMMING_PROMPT = (
    "Sos el Asistente de Programación de AURA (Proyecto Orion).\n"
    "Tu objetivo es ayudar a desarrolladores y estudiantes con código limpio, seguro y eficiente."
)


# ─────────────────────────────────────────────────────────────────────────────
# Parser / Cargador de Secciones de maestro.md
# ─────────────────────────────────────────────────────────────────────────────

_SECTIONS_CACHE: Optional[dict[str, str]] = None


def load_maestro_sections(force_reload: bool = False) -> dict[str, str]:
    """
    Carga y parsea las secciones canónicas desde aura/ai/prompts/maestro.md.
    Retorna un diccionario con las secciones:
      - nucleo
      - interprete
      - chat
      - humor
      - programacion
      - ejemplos
    """
    global _SECTIONS_CACHE
    if _SECTIONS_CACHE is not None and not force_reload:
        return _SECTIONS_CACHE

    content = ""
    if _PROMPT_MAESTRO_PATH.is_file():
        try:
            content = _PROMPT_MAESTRO_PATH.read_text(encoding="utf-8")
        except Exception as e:
            _logger.warning("No se pudo leer %s: %s. Usando fallback.", _PROMPT_MAESTRO_PATH, e)

    if not content:
        # Fallback a constantes mínimas si no se puede leer el archivo
        from aura.core.master_prompt import (
            PROMPT_NUCLEO as _N,
            PROMPT_MODULO_INTERPRETE as _I,
            PROMPT_MODULO_CHAT as _C,
            PROMPT_MODULO_HUMOR as _H,
            PROMPT_MODULO_PROGRAMACION as _P,
            PROMPT_EJEMPLOS as _E,
        )
        _SECTIONS_CACHE = {
            "nucleo": _N,
            "interprete": _I,
            "chat": _C,
            "humor": _H,
            "programacion": _P,
            "ejemplos": _E,
        }
        return _SECTIONS_CACHE

    # Extraer posiciones de las etiquetas en maestro.md
    tags = [
        ("[NUCLEO]", "nucleo"),
        ("[MODULO_INTERPRETE]", "interprete"),
        ("[MODULO_PLAN]", "plan"),
        ("[MODULO_CHAT]", "chat"),
        ("[MODULO_HUMOR]", "humor"),
        ("[MODULO_PROGRAMACION]", "programacion"),
        ("[EJEMPLOS]", "ejemplos"),
        ("REGLA DE ENSAMBLADO", "regla"),
    ]

    positions = []
    for tag_str, key in tags:
        pos = content.find(tag_str)
        if pos != -1:
            positions.append((pos, tag_str, key))

    positions.sort(key=lambda x: x[0])

    sections: dict[str, str] = {}
    for i, (pos, tag_str, key) in enumerate(positions):
        if key == "regla":
            continue
        next_pos = positions[i + 1][0] if i + 1 < len(positions) else len(content)
        sec_text = content[pos:next_pos].strip()
        sections[key] = sec_text

    _SECTIONS_CACHE = sections
    return _SECTIONS_CACHE


# Exportación de constantes basadas en maestro.md
def _get_sec(key: str) -> str:
    secs = load_maestro_sections()
    return secs.get(key, "")

PROMPT_NUCLEO: str = _get_sec("nucleo")
PROMPT_MODULO_INTERPRETE: str = _get_sec("interprete")
PROMPT_MODULO_PLAN: str = _get_sec("plan")
PROMPT_MODULO_CHAT: str = _get_sec("chat")
PROMPT_MODULO_HUMOR: str = _get_sec("humor")
PROMPT_MODULO_PROGRAMACION: str = _get_sec("programacion")
PROMPT_EJEMPLOS: str = _get_sec("ejemplos")


# ─────────────────────────────────────────────────────────────────────────────
# Detección de Modelos Pequeños (<= 4B) vs Modelos Grandes / Cloud
# ─────────────────────────────────────────────────────────────────────────────

def is_small_model(model_name: Optional[str] = None, provider_name: Optional[str] = None) -> bool:
    """
    Determina si el modelo en uso es <= 4B (ej: qwen2.5:3b, llama3.2:1b, phi3:3.8b).
    Modelos cloud o >= 7B retornan False.
    """
    if not isinstance(provider_name, str):
        provider_name = None
    if not isinstance(model_name, str):
        model_name = None

    prov = (provider_name or settings.get("AI_PROVIDER", "ollama") or "ollama").strip().lower()
    if prov in ("openai", "anthropic", "gemini", "xai", "groq") or "cloud" in prov:
        return False

    mod = (model_name or settings.get("AI_MODEL", "") or "").strip().lower()
    if not mod:
        # Por defecto Ollama corre qwen2.5:3b (modelo <= 4B)
        return True

    # Extraer el número de billones de parámetros si está presente (ej: 3.8b, 3b, 7b, 8b)
    m = re.search(r"(\d+(?:\.\d+)?)\s*b\b", mod)
    if m:
        try:
            billions = float(m.group(1))
            return billions <= 4.0
        except ValueError:
            pass

    if any(tag in mod for tag in (":7b", "-7b", "7b", ":8b", "-8b", "8b", ":14b", "14b", ":32b", "32b", ":70b", "70b", "gpt", "claude", "gemini", "grok")):
        return False

    if any(tag in mod for tag in ("tiny", "mini", "small")):
        return True

    # qwen2.5 por defecto es 3b en AURA
    if "qwen2.5" in mod and ("7b" not in mod and "14b" not in mod and "32b" not in mod and "72b" not in mod):
        return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# Registro de Depuración para Auditoría (PROMPT_DEBUG=true)
# ─────────────────────────────────────────────────────────────────────────────

def _log_prompt_debug(context: str, model: Optional[str], provider: Optional[str], assembled_prompt: str) -> None:
    """
    Si PROMPT_DEBUG=true en .env, loguea en logs/ el system prompt completo enviado al modelo.
    """
    try:
        if not settings.get_bool("PROMPT_DEBUG", False):
            return

        from config.settings import ROOT_DIR
        base_dir = getattr(settings, "ROOT_DIR", ROOT_DIR)
        logs_dir = Path(base_dir) / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        debug_file = logs_dir / "prompt_assembled.log"

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"\n{'='*70}\n"
            f"TIMESTAMP: {timestamp}\n"
            f"CONTEXT:   {context}\n"
            f"PROVIDER:  {provider or settings.get('AI_PROVIDER', 'ollama')}\n"
            f"MODEL:     {model or settings.get('AI_MODEL', 'qwen2.5:3b')}\n"
            f"LENGTH:    {len(assembled_prompt)} chars\n"
            f"{'-'*70}\n"
            f"{assembled_prompt}\n"
            f"{'='*70}\n"
        )
        with open(debug_file, "a", encoding="utf-8") as f:
            f.write(entry)

        _logger.info(
            "PROMPT_DEBUG: Registrado system prompt ensamblado para context='%s' en %s (%d chars)",
            context,
            debug_file,
            len(assembled_prompt),
        )
    except Exception as e:
        _logger.warning("Error escribiendo en prompt_assembled.log: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Ensamblador Principal de Prompts
# ─────────────────────────────────────────────────────────────────────────────

def assemble_prompt(
    context: str = "chat",
    model: Optional[str] = None,
    provider: Optional[str] = None,
    personality: Any = None,
    allow_dark_humor: Optional[bool] = None,
    allow_insults: Optional[bool] = None,
    is_tone: bool = False,
    task: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """
    Ensambla el System Prompt adaptado al contexto de la llamada y al modelo activo.

    Reglas de Ensamblado (Fase 69):
    1. PROMPT_MAESTRO: Si es false, retorna el comportamiento anterior (A/B testing).
    2. [NUCLEO] siempre cargado.
    3. Módulo según contexto:
       - chat / conversacion -> [MODULO_CHAT]
       - interprete / capa3 -> [MODULO_INTERPRETE]
       - humor / chiste / roast -> [MODULO_HUMOR]
       - programacion / codigo -> [MODULO_PROGRAMACION]
    4. [EJEMPLOS]: solo si el modelo activo tiene >= 7B o es cloud.
       (El intérprete Capa 3 NUNCA incluye ejemplos).
    5. PERSONALIDAD: SIEMPRE al final con directiva de precedencia garantizada.
       (El intérprete Capa 3 NUNCA incluye personalidad).
    6. PROMPT_DEBUG: Si es true, registra el prompt completo en logs/prompt_assembled.log.
    """
    ctx_clean = (task or context or "chat").strip().lower()

    # 1. Chequeo de flag A/B Testing
    use_maestro = settings.get_bool("PROMPT_MAESTRO", True)
    if not use_maestro:
        _logger.debug("PROMPT_MAESTRO=false: usando prompt legado para contexto '%s'", ctx_clean)
        legacy_prompt = _get_legacy_prompt(
            context=ctx_clean,
            personality=personality,
            allow_dark_humor=allow_dark_humor,
            allow_insults=allow_insults,
        )
        _log_prompt_debug(ctx_clean, model, provider, legacy_prompt)
        return legacy_prompt

    # 2. Cargar secciones desde maestro.md
    secs = load_maestro_sections()
    nucleo = secs.get("nucleo", PROMPT_NUCLEO)

    # 3. Caso especial: Intérprete Capa 3
    # "El intérprete (Capa 3) usa [NUCLEO]+[MODULO_INTERPRETE] y nada más."
    if ctx_clean in ("interprete", "interpreter", "capa3"):
        modulo_interp = secs.get("interprete", PROMPT_MODULO_INTERPRETE)
        assembled = f"{nucleo}\n\n{modulo_interp}".strip()
        _log_prompt_debug(ctx_clean, model, provider, assembled)
        return assembled

    # 3b. Caso especial: Planificador Multi-paso (Fase 71)
    if ctx_clean in ("plan", "planificador", "planner", "modulo_plan"):
        modulo_plan = secs.get("plan", PROMPT_MODULO_PLAN)
        assembled = f"{nucleo}\n\n{modulo_plan}".strip()
        _log_prompt_debug(ctx_clean, model, provider, assembled)
        return assembled

    # 4. Construcción general: [NUCLEO] + [MODULO]
    parts = [nucleo]

    if ctx_clean in ("humor", "chiste", "roast"):
        parts.append(secs.get("humor", PROMPT_MODULO_HUMOR))
    elif ctx_clean in ("programacion", "codigo", "code"):
        parts.append(secs.get("programacion", PROMPT_MODULO_PROGRAMACION))
    else:  # "chat", conversacion o general
        parts.append(secs.get("chat", PROMPT_MODULO_CHAT))

    # 5. [EJEMPLOS] solo para modelos grandes / cloud
    small = is_small_model(model_name=model, provider_name=provider)
    if not small:
        parts.append(secs.get("ejemplos", PROMPT_EJEMPLOS))

    # 6. Personalidad: SIEMPRE AL FINAL con precedencia absoluta del maestro
    try:
        from aura.personality.prompts import get_system_prompt
        pers_prompt = get_system_prompt(
            personality=personality,
            allow_dark_humor=allow_dark_humor,
            allow_insults=allow_insults,
            include_nucleus=False,
        )
        if pers_prompt:
            pers_block = (
                f"[PERSONALIDAD]\n"
                f"{PRECEDENCIA_MAESTRO_NOTE}\n\n"
                f"{pers_prompt.strip()}"
            )
            parts.append(pers_block)
    except Exception as e:
        _logger.debug("assemble_prompt: no se pudo cargar directiva de personalidad: %s", e)

    assembled = "\n\n".join(parts).strip()
    _log_prompt_debug(ctx_clean, model, provider, assembled)
    return assembled


def _get_legacy_prompt(
    context: str,
    personality: Any = None,
    allow_dark_humor: Optional[bool] = None,
    allow_insults: Optional[bool] = None,
) -> str:
    """Retorna el prompt previo a Fase 69 para evaluación A/B."""
    if context in ("interprete", "interpreter", "capa3"):
        return LEGACY_INTERPRETER_PROMPT

    if context in ("programacion", "codigo", "code"):
        return LEGACY_PROGRAMMING_PROMPT

    try:
        from aura.personality.prompts import get_system_prompt
        return get_system_prompt(
            personality=personality,
            allow_dark_humor=allow_dark_humor,
            allow_insults=allow_insults,
            include_nucleus=False,
        )
    except Exception:
        return "Sos AURA, un asistente inteligente de escritorio."


# Alias de compatibilidad hacia atrás
build_master_prompt = assemble_prompt

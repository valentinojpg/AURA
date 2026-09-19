"""
AURA — Handler Dedicado para Roast e Insultos (Fase 51 / Fase 64 Fix de Humor).

Provee un pipeline estructurado para responder a intenciones de roast ("insultame", "roasteame", "tirame un palo"):
  1. Parámetros cuerdos: temperature 0.75 fija (sin escalada), repeat_penalty 1.1, max_tokens 120, sin freq/pres penalty.
  2. Sin etiquetas de esquema: prohibido escribir "Setup:", "Remate:", "Roast:".
  3. Formato estricto: máximo 3 líneas, segunda persona obligatoria (vos/tu/te/tuyo) y términos curados por nivel.
  4. Respeto a HUMOR_SOURCE (bank | model | hybrid) y HUMOR_PROVIDER (auto | local | <nombre>).
  5. Fallback silencioso al banco local tras doble fallo de validación o caída de provider.
  6. Meta-corrección de quejas sobre roasts con handle_roast_complaint.
"""

from __future__ import annotations

import datetime
import json
import random
from pathlib import Path
from typing import Any, Optional
import psutil

from config.settings import settings
from utils.logger import get_logger
from aura.personality.personalities import get_current_personality
from aura.personality.tone_filter import filter_content, sanitize_output
from aura.personality.anti_loop import apply_anti_loop
from aura.personality.humor_tracker import (
    strip_humor_labels,
    validate_roast_output,
    set_last_humor_intent,
    save_last_roast_state,
)
from aura.personality.humor_provider import get_humor_provider
from ai.provider_interface import ChatMessage

_logger = get_logger("aura.personality.roast")

JOKES_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "fun" / "jokes.json"


def _get_system_context() -> tuple[str, str, str]:
    """
    Recupera contexto real del entorno para nutrir el roast:
      - Hora del día
      - Aplicación activa o reciente
      - Datos de memoria del usuario
    """
    now = datetime.datetime.now()
    hora_str = now.strftime("%H:%M")
    if 0 <= now.hour < 6:
        momento = f"{hora_str} de la madrugada (deberías estar durmiendo)"
    elif 6 <= now.hour < 12:
        momento = f"{hora_str} de la mañana"
    elif 12 <= now.hour < 20:
        momento = f"{hora_str} de la tarde"
    else:
        momento = f"{hora_str} de la noche"

    app_context = "tu editor de código"
    try:
        from core.user_memory import user_memory
        freq = user_memory.get_frequent_programs()
        if freq:
            app_context = freq[0]["name"]
        else:
            for proc in psutil.process_iter(["name"]):
                pname = (proc.info.get("name") or "").lower()
                if any(x in pname for x in ("code", "pycharm", "cursor", "sublime", "chrome", "firefox", "spotify")):
                    app_context = pname.replace(".exe", "")
                    break
    except Exception:
        pass

    mem_context = "ningún proyecto guardado"
    try:
        from core.user_memory import user_memory
        prof = user_memory.get_profile()
        proj = prof.get("active_project", "")
        facts = prof.get("learned_facts", [])
        parts = []
        if proj:
            parts.append(f"proyecto '{proj}'")
        if facts:
            parts.append(f"hecho: {facts[-1]}")
        if parts:
            mem_context = ", ".join(parts)
    except Exception:
        pass

    return momento, app_context, mem_context


def get_fallback_roast(
    level: int = 5,
    momento: str = "",
    app_context: str = "",
    mem_context: str = "",
) -> str:
    """
    Obtiene un roast curado del banco local (banco_roasts en data/fun/jokes.json)
    sustituyendo opcionalmente tokens de contexto ({hora}, {momento}, {app}).
    """
    if not momento or not app_context:
        momento, app_context, mem_context = _get_system_context()

    roasts: list[str] = []
    if JOKES_FILE.exists():
        try:
            with open(JOKES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            banco_roasts = data.get("banco_roasts", {})
            lvl_str = str(level) if str(level) in banco_roasts else "5"
            roasts = banco_roasts.get(lvl_str, [])
        except Exception as e:
            _logger.error("Error leyendo banco_roasts de %s: %s", JOKES_FILE, e)

    if not roasts:
        # Fallback interno mínimo
        if level <= 2:
            return (
                f"Son las {momento} y me pedís que gaste procesamiento en insultarte.\n"
                f"Con ver cómo tenés abierto '{app_context}' ya es suficiente chiste.\n"
                "Ponete a corregir tus bugs antes de pedir ironías."
            )
        elif level <= 4:
            return (
                f"Son las {momento} y seguís procrastinando con '{app_context}'.\n"
                "Tenés menos luces que arbolito quemado y tu código compila de pura casualidad.\n"
                "Andá a laburar antes de que la máquina pida asilo."
            )
        else:
            return (
                f"Son las {momento} y me pedís que te insulte fuerte, pedazo de pelotudo.\n"
                f"Tenés menos luces que arbolito quemado y tu código parece cagado por una foca ciega.\n"
                "Andá a laburar antes de que mande tu disco rígido a la mierda."
            )

    elegido = random.choice(roasts)
    _logger.info("Roast entregado desde banco local (reserva offline) [nivel=%d]", level)

    hora_simple = momento.split()[0] if momento else datetime.datetime.now().strftime("%H:%M")
    rendered = elegido.replace("{hora}", hora_simple).replace("{momento}", momento).replace("{app}", app_context)
    return strip_humor_labels(rendered)


def generate_roast(
    user_text: str,
    provider: Optional[Any] = None,
    is_correction: bool = False,
) -> str:
    """
    Genera una respuesta de roast estructurada y coherente según Fase 64.

    Args:
        user_text: Mensaje del usuario (ej: "insultame", "roasteame", "insultame fuerte").
        provider: Instancia de BaseAIProvider opcional.
        is_correction: True si se invoca como meta-corrección tras una queja del usuario.

    Returns:
        Respuesta formateada (máx 3 líneas, segunda persona, sin etiquetas).
    """
    # 1. Chequeo de seguridad preventivo
    safety = filter_content(user_text)
    if not safety.is_safe:
        return safety.message

    # Registrar last_humor_intent en sesión
    set_last_humor_intent("roast")

    curr_mode = get_current_personality()
    level = curr_mode.level

    # 2. Respuestas deterministas para niveles 0 y 1 (sin descalificaciones)
    if level == 0:
        refusal = "El protocolo operativo y profesional no contempla agravios ni descalificaciones. Indique la tarea técnica a ejecutar."
        save_last_roast_state(level, refusal, user_text)
        return refusal

    if level == 1:
        refusal = "¡Ni de casualidad te voy a insultar! Sos una gran persona y prefiero darte una mano con lo que estés programando 😊"
        save_last_roast_state(level, refusal, user_text)
        return refusal

    momento, app_context, mem_context = _get_system_context()
    humor_source = settings.get("HUMOR_SOURCE", "hybrid").strip().lower()

    # Si HUMOR_SOURCE=bank: entregar instantáneamente del banco local
    if humor_source == "bank":
        fallback = get_fallback_roast(level, momento, app_context, mem_context)
        save_last_roast_state(level, fallback, user_text)
        return fallback

    # Resolver proveedor con HUMOR_PROVIDER si no se pasó uno explícito
    if provider is None:
        provider = get_humor_provider()

    # Si aún no hay proveedor disponible, usar reserva offline del banco
    if provider is None:
        fallback = get_fallback_roast(level, momento, app_context, mem_context)
        save_last_roast_state(level, fallback, user_text)
        return fallback

    # 3. Parámetros cuerdos para humor (Fase 64)
    temp = 0.75  # Fija, escalada derogada
    max_tokens = 120
    repeat_penalty = 1.1

    correction_header = ""
    if is_correction:
        correction_header = (
            f"AVISO DE CORRECCIÓN:\n"
            f"El usuario se quejó del mensaje anterior ('{user_text}'). No te defiendas, no des excusas ni pidas disculpas.\n"
            "Entregá AHORA un roast demoledor, directo al grano en segunda persona (vos/tu), con metáfora y remate seco en máximo 3 líneas.\n\n"
        )

    roast_instructions = f"""
{correction_header}INSTRUCCIÓN ESTRICTA DE ROAST:
El usuario pidió: "{user_text}".
Generá un roast cómico, breve y contundente adaptado al nivel {level} ({curr_mode.name}):
- MÁXIMO 3 LÍNEAS en total (separadas por saltos de línea).
- SEGUNDA PERSONA OBLIGATORIA: Dirigite directamente al usuario (usá vos/tu/te/sos/tenés).
- METÁFORA OBLIGATORIA basada en su realidad actual:
  * Momento: {momento}
  * Aplicación/Entorno: {app_context}
  * Contexto de usuario: {mem_context}
- Cierra con un remate seco y demoledor en la última línea.
- PROHIBIDO TERMINANTEMENTE: Escribir etiquetas de esquema como 'Setup:', 'Remate:', 'Punchline:' o 'Roast:'.
- PROHIBIDO: Párrafos continuos, discursos largos o encadenar insultos genéricos sin metáfora.
- Tono permitido para nivel {level}: dardo certero y cómico, sin agresiones reales ni odio a grupos protegidos.
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
        ChatMessage(role="user", content=roast_instructions.strip()),
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

    try:
        raw_text = _call_model()
    except Exception as e:
        _logger.warning("Error llamando a proveedor para roast: %s. Usando fallback estructurado.", e)
        fallback = get_fallback_roast(level, momento, app_context, mem_context)
        save_last_roast_state(level, fallback, user_text)
        return fallback

    # Aplicar guard anti-loop y quitar etiquetas de esquema
    clean_text = strip_humor_labels(apply_anti_loop(raw_text))
    is_valid, reason = validate_roast_output(clean_text, level=level)

    if not is_valid:
        _logger.warning("Guard de roast: salida inválida (%s). Reintentando con prompt correctivo.", reason)
        try:
            messages.append(ChatMessage(role="assistant", content=clean_text))
            messages.append(
                ChatMessage(
                    role="user",
                    content=(
                        "Tu respuesta no cumplió el formato de roast en segunda persona o incluyó etiquetas/párrafos largos. "
                        "Reescribí AHORA en segunda persona directa (vos/tu), máximo 3 líneas, sin 'Setup:'/'Remate:'."
                    ),
                )
            )
            retry_raw = _call_model()
            retry_clean = strip_humor_labels(apply_anti_loop(retry_raw))
            is_valid_retry, reason_retry = validate_roast_output(retry_clean, level=level)

            if is_valid_retry:
                clean_text = retry_clean
            else:
                _logger.warning("Guard de roast: segundo fallo consecutivo (%s). Usando banco local.", reason_retry)
                fallback = get_fallback_roast(level, momento, app_context, mem_context)
                save_last_roast_state(level, fallback, user_text)
                return fallback
        except Exception as e2:
            _logger.warning("Error en reintento de roast: %s. Usando banco local.", e2)
            fallback = get_fallback_roast(level, momento, app_context, mem_context)
            save_last_roast_state(level, fallback, user_text)
            return fallback

    # Sanitizar y limitar a 3 líneas
    lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
    if len(lines) > 3:
        lines = [lines[0], lines[1], lines[-1]]

    final_roast = sanitize_output("\n".join(lines))
    final_roast = strip_humor_labels(final_roast)
    save_last_roast_state(level, final_roast, user_text)
    return final_roast


def handle_roast_complaint(user_text: str, provider: Optional[Any] = None) -> str:
    """
    Maneja el reclamo del usuario tras un roast ("te pedí que me insultaras", "eso no fue un insulto", etc.):
    Regenera con el prompt de roast correctivo, sin disculpas y con temperatura 0.75 fija.
    """
    _logger.info("Meta-corrección: queja tras roast detectada ('%s'). Regenerando roast correctivo.", user_text)
    return generate_roast(
        user_text=user_text,
        provider=provider,
        is_correction=True,
    )

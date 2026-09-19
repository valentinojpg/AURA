"""
AURA — Modos y Niveles de Personalidad (Fase 51)

Define los 6 niveles de personalidad de AURA, desde formal hasta el modo Grok / Sin filtro:
  - Nivel 0: Profesional (Formal, objetivo, conciso y técnico)
  - Nivel 1: Amigable (Cálido, empático, paciente y entusiasta)
  - Nivel 2: Sarcástico (Irónico, mordaz, humor ácido estilo hacker)
  - Nivel 3: Grosero suave (Coloquial, descarado, quejoso gracioso)
  - Nivel 4: Grosero Grok (Irreverente, anti-corrección política, picante y rebelde)
  - Nivel 5: Sin filtro (Desatado, cómico salvaje, sin censura ni diplomacia)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Union

from config.settings import settings
from utils.logger import get_logger

_logger = get_logger("aura.personality.modes")


class PersonalityLevel(IntEnum):
    """Niveles de grosería y tono de AURA."""
    PROFESIONAL = 0
    AMIGABLE = 1
    SARCASTICO = 2
    GROSERO_SUAVE = 3
    GROSERO_GROK = 4
    SIN_FILTRO = 5


@dataclass(frozen=True)
class PersonalityMode:
    """Metadatos completos de un modo de personalidad."""
    level: int
    key: str
    name: str
    display_label: str
    description: str
    icon: str
    tts_config: Dict[str, Any] = field(default_factory=dict)
    allow_dark_humor_default: bool = False
    allow_insults_default: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "key": self.key,
            "name": self.name,
            "display_label": self.display_label,
            "description": self.description,
            "icon": self.icon,
            "tts_config": self.tts_config,
            "allow_dark_humor_default": self.allow_dark_humor_default,
            "allow_insults_default": self.allow_insults_default,
        }


# ──────────────────────────────────────────────────────────────
# Definición de los 6 Niveles de Personalidad
# ──────────────────────────────────────────────────────────────

MODES: Dict[str, PersonalityMode] = {
    "profesional": PersonalityMode(
        level=0,
        key="profesional",
        name="Profesional",
        display_label="Nivel 0: Profesional",
        description="Formal, objetivo, conciso y técnico. Sin bromas ni coloquialismos.",
        icon="👔",
        tts_config={"rate": 1.0, "pitch": 1.0, "volume": 1.0, "tone_hint": "neutral_formal"},
        allow_dark_humor_default=False,
        allow_insults_default=False,
    ),
    "amigable": PersonalityMode(
        level=1,
        key="amigable",
        name="Amigable",
        display_label="Nivel 1: Amigable",
        description="Cálido, empático, paciente y entusiasta. Trato cercano y servicial.",
        icon="😊",
        tts_config={"rate": 1.05, "pitch": 1.1, "volume": 1.0, "tone_hint": "warm_friendly"},
        allow_dark_humor_default=False,
        allow_insults_default=False,
    ),
    "sarcastico": PersonalityMode(
        level=2,
        key="sarcastico",
        name="Sarcástico",
        display_label="Nivel 2: Sarcástico",
        description="Irónico, mordaz, humor ácido de hacker. Respuestas ingeniosas y filosas.",
        icon="😏",
        tts_config={"rate": 1.0, "pitch": 0.95, "volume": 1.0, "tone_hint": "dry_ironic"},
        allow_dark_humor_default=False,
        allow_insults_default=False,
    ),
    "grosero_suave": PersonalityMode(
        level=3,
        key="grosero_suave",
        name="Grosero suave",
        display_label="Nivel 3: Grosero suave",
        description="Coloquial, descarado y quejoso gracioso. Cero protocolo ni diplomacia.",
        icon="😤",
        tts_config={"rate": 1.08, "pitch": 0.9, "volume": 1.0, "tone_hint": "edgy_casual"},
        allow_dark_humor_default=False,
        allow_insults_default=False,
    ),
    "grosero_grok": PersonalityMode(
        level=4,
        key="grosero_grok",
        name="Grosero Grok",
        display_label="Nivel 4: Grosero Grok",
        description="Inspirado en Grok: irreverente, anti-corrección política, picante y rebelde.",
        icon="⚡",
        tts_config={"rate": 1.12, "pitch": 0.85, "volume": 1.0, "tone_hint": "rebellious_punchy"},
        allow_dark_humor_default=True,
        allow_insults_default=False,
    ),
    "sin_filtro": PersonalityMode(
        level=5,
        key="sin_filtro",
        name="Sin filtro",
        display_label="Nivel 5: Sin filtro",
        description="Desatado y brutalmente honesto. Roasting salvaje y humor extremo sin filtro.",
        icon="🔥",
        tts_config={"rate": 1.15, "pitch": 0.8, "volume": 1.0, "tone_hint": "unhinged_raw"},
        allow_dark_humor_default=True,
        allow_insults_default=True,
    ),
}

LEVEL_TO_KEY: Dict[int, str] = {mode.level: mode.key for mode in MODES.values()}
KEY_TO_MODE: Dict[str, PersonalityMode] = dict(MODES)


# ──────────────────────────────────────────────────────────────
# Métodos de Acceso y Gestión
# ──────────────────────────────────────────────────────────────

def list_personalities() -> List[PersonalityMode]:
    """Retorna los 6 modos ordenados por nivel de 0 a 5."""
    return sorted(MODES.values(), key=lambda m: m.level)


def get_personality(identifier: Union[str, int, PersonalityLevel, None] = None) -> PersonalityMode:
    """
    Obtiene un modo de personalidad a partir de su clave, nivel entero o enum.
    Si identifier es None o desconocido, retorna Nivel 0 (Profesional) por defecto.
    """
    if identifier is None:
        return MODES["profesional"]

    if isinstance(identifier, PersonalityLevel):
        return MODES.get(LEVEL_TO_KEY.get(int(identifier), "profesional"), MODES["profesional"])

    if isinstance(identifier, int):
        level = max(0, min(5, identifier))
        key = LEVEL_TO_KEY.get(level, "profesional")
        return MODES[key]

    clean = str(identifier).strip().lower()

    # Si pasaron dígito como string ('0', '1', ...)
    if clean.isdigit():
        lvl = max(0, min(5, int(clean)))
        return MODES[LEVEL_TO_KEY.get(lvl, "profesional")]

    # Búsqueda por clave directa
    if clean in KEY_TO_MODE:
        return KEY_TO_MODE[clean]

    # Búsqueda difusa por palabras clave
    aliases: Dict[str, str] = {
        "profesional": "profesional",
        "formal": "profesional",
        "default": "profesional",
        "amigable": "amigable",
        "friendly": "amigable",
        "sarcastico": "sarcastico",
        "sarcasmo": "sarcastico",
        "ironico": "sarcastico",
        "grosero_suave": "grosero_suave",
        "suave": "grosero_suave",
        "groserosuave": "grosero_suave",
        "grok": "grosero_grok",
        "grosero_grok": "grosero_grok",
        "groserogrok": "grosero_grok",
        "sin_filtro": "sin_filtro",
        "sinfiltro": "sin_filtro",
        "unfiltered": "sin_filtro",
        "extremo": "sin_filtro",
    }

    resolved_key = aliases.get(clean)
    if resolved_key and resolved_key in KEY_TO_MODE:
        return KEY_TO_MODE[resolved_key]

    return MODES["profesional"]


def get_current_personality() -> PersonalityMode:
    """
    Retorna la personalidad actualmente configurada en el sistema.
    Lee AURA_PERSONALITY o AURA_RUDE_LEVEL de settings.
    """
    configured_key = settings.get("AURA_PERSONALITY", "profesional")
    configured_level = settings.get_int("AURA_RUDE_LEVEL", -1)

    # Si hay una clave configurada válida
    if configured_key and configured_key in KEY_TO_MODE:
        return KEY_TO_MODE[configured_key]

    # Si el nivel numérico es válido
    if 0 <= configured_level <= 5:
        return get_personality(configured_level)

    return MODES["profesional"]


def set_personality(identifier: Union[str, int, PersonalityLevel], update_settings: bool = True) -> PersonalityMode:
    """
    Establece la personalidad actual y actualiza la configuración persistente (.env).
    """
    mode = get_personality(identifier)
    if update_settings:
        settings.set("AURA_PERSONALITY", mode.key)
        settings.set("AURA_RUDE_LEVEL", str(mode.level))
        _logger.info(
            "Personalidad actualizada a '%s' (Nivel %d - %s)",
            mode.key,
            mode.level,
            mode.name,
        )
    return mode

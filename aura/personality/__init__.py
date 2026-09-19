"""
AURA — Sistema de Personalidades y Modo Grok (Fase 51 / Fix de Estilo)

Exporta la API unificada del motor de personalidades, prompts con contrato de estilo,
parámetros de generación por nivel, guard anti-loop, filtro de seguridad y frases contextuales.
"""

from aura.personality.personalities import (
    PersonalityLevel,
    PersonalityMode,
    MODES,
    LEVEL_TO_KEY,
    KEY_TO_MODE,
    list_personalities,
    get_personality,
    get_current_personality,
    set_personality,
)
from aura.personality.prompts import (
    get_system_prompt,
    get_generation_parameters,
    is_tone_request,
    load_personality_examples,
)
from aura.personality.anti_loop import (
    apply_anti_loop,
    detect_repetition,
    trim_at_repetition,
    is_useful_sentence,
)
from aura.personality.tone_filter import (
    ToneFilterResult,
    check_safety,
    filter_content,
    is_safe_content,
    sanitize_output,
)
from aura.personality.rude_engine import (
    RudeEngine,
    rude_engine,
    get_context_phrase,
)
from aura.personality.roast_handler import (
    generate_roast,
    get_fallback_roast,
    handle_roast_complaint,
)
from aura.personality.jokes import (
    generate_joke,
    handle_joke_complaint,
    get_fallback_joke,
    validate_joke_output,
    resolve_joke_style,
)
from aura.personality.humor_tracker import (
    strip_humor_labels,
    validate_roast_output,
    validate_joke_coherence,
    set_last_humor_intent,
    get_last_humor_intent,
    save_last_roast_state,
    get_last_roast_state,
    save_last_joke_state,
    get_last_joke_state,
)
from aura.personality.humor_provider import (
    get_humor_provider,
)

__all__ = [
    "PersonalityLevel",
    "PersonalityMode",
    "MODES",
    "LEVEL_TO_KEY",
    "KEY_TO_MODE",
    "list_personalities",
    "get_personality",
    "get_current_personality",
    "set_personality",
    "get_system_prompt",
    "get_generation_parameters",
    "is_tone_request",
    "load_personality_examples",
    "apply_anti_loop",
    "detect_repetition",
    "trim_at_repetition",
    "is_useful_sentence",
    "ToneFilterResult",
    "check_safety",
    "filter_content",
    "is_safe_content",
    "sanitize_output",
    "RudeEngine",
    "rude_engine",
    "get_context_phrase",
    "generate_roast",
    "get_fallback_roast",
    "handle_roast_complaint",
    "generate_joke",
    "handle_joke_complaint",
    "get_fallback_joke",
    "validate_joke_output",
    "resolve_joke_style",
    "strip_humor_labels",
    "validate_roast_output",
    "validate_joke_coherence",
    "set_last_humor_intent",
    "get_last_humor_intent",
    "save_last_roast_state",
    "get_last_roast_state",
    "save_last_joke_state",
    "get_last_joke_state",
    "get_humor_provider",
]

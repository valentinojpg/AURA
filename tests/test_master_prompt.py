"""
Tests para el Prompt Maestro de Razonamiento e Interpretación (AURA Orion).
Valida:
1. Constantes y estructura de módulos del Prompt Maestro.
2. Regla de Ensamblado:
   - Modelos <= 4B: SOLO [NUCLEO] + [MODULO_TAREA] + [PERSONALIDAD al final].
   - Modelos >= 7B o Cloud: [NUCLEO] + [MODULO_TAREA] + [EJEMPLOS] + [PERSONALIDAD al final].
   - Intérprete (Capa 3): ÚNICAMENTE [NUCLEO] + [MODULO_INTERPRETE].
3. Detección de modelos pequeños (is_small_model).
4. Inmutabilidad de los umbrales de razonamiento por la personalidad.
"""

import pytest
from aura.core.master_prompt import (
    PROMPT_NUCLEO,
    PROMPT_MODULO_INTERPRETE,
    PROMPT_MODULO_CHAT,
    PROMPT_MODULO_HUMOR,
    PROMPT_MODULO_PROGRAMACION,
    PROMPT_EJEMPLOS,
    is_small_model,
    build_master_prompt,
)
from aura.personality import get_personality


def test_master_prompt_constants_present():
    """Verifica que las constantes del Prompt Maestro tengan su contenido canónico."""
    # Núcleo
    assert "IDENTIDAD Y LAS DOS MITADES" in PROMPT_NUCLEO
    assert "MITAD EJECUTORA" in PROMPT_NUCLEO
    assert "MITAD CONVERSACIONAL" in PROMPT_NUCLEO
    assert "HONESTIDAD OPERATIVA (innegociable)" in PROMPT_NUCLEO
    assert "PROTOCOLO DE RAZONAMIENTO INTERNO" in PROMPT_NUCLEO
    assert "PASO 1 — CLASIFICAR" in PROMPT_NUCLEO
    assert "PASO 2 — DESCOMPONER" in PROMPT_NUCLEO
    assert "PASO 3 — REPARAR" in PROMPT_NUCLEO
    assert "PASO 4 — RESOLVER REFERENCIAS" in PROMPT_NUCLEO
    assert "PASO 5 — DECIDIR con umbrales de confianza" in PROMPT_NUCLEO
    assert "PASO 6 — AUTO-CRÍTICA antes de emitir" in PROMPT_NUCLEO
    assert "INTERPRETACIÓN FINA" in PROMPT_NUCLEO
    assert "REGLAS DE SALIDA POR TIPO" in PROMPT_NUCLEO
    assert "SEGURIDAD Y LÍMITES" in PROMPT_NUCLEO

    # Módulos especializados
    assert "[MODULO_INTERPRETE]" in PROMPT_MODULO_INTERPRETE
    assert "open_app|close_app|write_in_app|save_app_doc" in PROMPT_MODULO_INTERPRETE
    assert "[MODULO_CHAT]" in PROMPT_MODULO_CHAT
    assert "[MODULO_HUMOR]" in PROMPT_MODULO_HUMOR
    assert "[MODULO_PROGRAMACION]" in PROMPT_MODULO_PROGRAMACION
    assert "[EJEMPLOS]" in PROMPT_EJEMPLOS


def test_is_small_model_detection():
    """Valida la detección de modelos pequeños (<= 4B) vs grandes o Cloud."""
    # Modelos pequeños (<= 4B)
    assert is_small_model("qwen2.5:3b", "ollama") is True
    assert is_small_model("llama3.2:1b", "ollama") is True
    assert is_small_model("phi3:3.8b", "ollama") is True
    assert is_small_model(None, "ollama") is True  # default local

    # Modelos grandes (>= 7B) o Cloud
    assert is_small_model("qwen2.5:7b", "ollama") is False
    assert is_small_model("llama3:8b", "ollama") is False
    assert is_small_model("gpt-4o-mini", "openai") is False
    assert is_small_model("claude-3-5-haiku-latest", "anthropic") is False
    assert is_small_model("gemini-2.0-flash", "gemini") is False
    assert is_small_model(None, "openai") is False


def test_assembly_rule_small_model():
    """
    Modelos <= 4B: SOLO [NUCLEO] + [MODULO_TAREA] + [PERSONALIDAD al final].
    NO debe incluir [EJEMPLOS] para preservar contexto.
    """
    prompt = build_master_prompt(
        task="chat",
        model="qwen2.5:3b",
        provider="ollama",
        personality=2,  # Sarcástico
    )

    assert "[NUCLEO]" in prompt
    assert "[MODULO_CHAT]" in prompt
    assert "[EJEMPLOS]" not in prompt
    assert "[PERSONALIDAD]" in prompt
    # La personalidad debe estar al final
    pos_nucleo = prompt.index("[NUCLEO]")
    pos_chat = prompt.index("[MODULO_CHAT]")
    pos_pers = prompt.index("[PERSONALIDAD]")
    assert pos_nucleo < pos_chat < pos_pers


def test_assembly_rule_large_or_cloud_model():
    """
    Modelos Cloud o >= 7B: [NUCLEO] + [MODULO_TAREA] + [EJEMPLOS] + [PERSONALIDAD al final].
    """
    prompt = build_master_prompt(
        task="chat",
        model="gpt-4o-mini",
        provider="openai",
        personality=0,  # Profesional
    )

    assert "[NUCLEO]" in prompt
    assert "[MODULO_CHAT]" in prompt
    assert "[EJEMPLOS]" in prompt
    assert "[PERSONALIDAD]" in prompt

    pos_nucleo = prompt.index("[NUCLEO]")
    pos_chat = prompt.index("[MODULO_CHAT]")
    pos_ejemplos = prompt.index("[EJEMPLOS]")
    pos_pers = prompt.index("[PERSONALIDAD]")
    assert pos_nucleo < pos_chat < pos_ejemplos < pos_pers


def test_assembly_rule_interpreter_capa3():
    """
    Capa 3 (Intérprete): Usa ÚNICAMENTE [NUCLEO] + [MODULO_INTERPRETE] y NADA MÁS.
    Sin [EJEMPLOS], sin [PERSONALIDAD], sin módulos de chat/humor.
    """
    prompt = build_master_prompt(
        task="interprete",
        model="qwen2.5:3b",
        provider="ollama",
        personality=5,  # Sin filtro ignorado en intérprete
    )

    assert "[NUCLEO]" in prompt
    assert "[MODULO_INTERPRETE]" in prompt
    assert "[EJEMPLOS]" not in prompt
    assert "[PERSONALIDAD]" not in prompt
    assert "[MODULO_CHAT]" not in prompt
    assert "[MODULO_HUMOR]" not in prompt
    assert "Respondé ÚNICAMENTE un JSON válido" in prompt


def test_assembly_rule_humor_task():
    """Verifica que la tarea de humor cargue [MODULO_HUMOR] y respete el ensamblado."""
    prompt = build_master_prompt(
        task="humor",
        model="qwen2.5:3b",
        provider="ollama",
        personality=4,  # Grok
    )

    assert "[NUCLEO]" in prompt
    assert "[MODULO_HUMOR]" in prompt
    assert "Estructura obligatoria: setup de 1-2 frases + remate de 1 frase" in prompt
    assert "[MODULO_CHAT]" not in prompt
    assert "[PERSONALIDAD]" in prompt


def test_assembly_rule_programming_task():
    """Verifica que la tarea de programación cargue [MODULO_PROGRAMACION] y respete el ensamblado."""
    prompt = build_master_prompt(
        task="programacion",
        model="qwen2.5:3b",
        provider="ollama",
        personality=1,  # Amigable
    )

    assert "[NUCLEO]" in prompt
    assert "[MODULO_PROGRAMACION]" in prompt
    assert "Explicá el error citando la línea/causa probable antes que la solución" in prompt
    assert "[MODULO_CHAT]" not in prompt
    assert "[PERSONALIDAD]" in prompt


def test_personality_precedence_guarantee():
    """
    Verifica que el bloque de personalidad documente la precedencia absoluta
    del NÚCLEO sobre cualquier instrucción de personalidad.
    """
    from aura.ai.prompt_assembler import assemble_prompt, PRECEDENCIA_MAESTRO_NOTE

    prompt = assemble_prompt(
        context="chat",
        personality=5,  # Sin filtro
    )
    assert "[PERSONALIDAD]" in prompt
    assert PRECEDENCIA_MAESTRO_NOTE in prompt
    assert "precedencia absoluta sobre la personalidad" in prompt


def test_ab_testing_prompt_maestro_false(monkeypatch):
    """
    Verifica el modo A/B: si PROMPT_MAESTRO=false, usa el comportamiento previo.
    """
    from aura.ai.prompt_assembler import assemble_prompt
    from config.settings import settings

    monkeypatch.setattr(settings, "get_bool", lambda key, default=False: False if key == "PROMPT_MAESTRO" else default)

    # Para chat
    chat_p = assemble_prompt(context="chat", personality=1)
    assert "[NUCLEO]" not in chat_p
    assert "[MODULO_CHAT]" not in chat_p

    # Para intérprete
    interp_p = assemble_prompt(context="interprete")
    assert "[NUCLEO]" not in interp_p
    assert "Eres el intérprete de comandos de AURA" in interp_p

    # Para programación
    prog_p = assemble_prompt(context="programacion")
    assert "[NUCLEO]" not in prog_p
    assert "Sos el Asistente de Programación de AURA" in prog_p


def test_prompt_debug_logging(tmp_path, monkeypatch):
    """
    Verifica que cuando PROMPT_DEBUG=true, se registre el system prompt en logs/prompt_assembled.log.
    """
    from aura.ai.prompt_assembler import assemble_prompt
    from config.settings import settings

    monkeypatch.setattr(settings, "get_bool", lambda key, fallback=False, **kwargs: True if key in ("PROMPT_MAESTRO", "PROMPT_DEBUG") else fallback)
    monkeypatch.setattr(settings, "ROOT_DIR", tmp_path)

    prompt = assemble_prompt(context="chat", model="qwen2.5:3b", provider="ollama")
    debug_log = tmp_path / "logs" / "prompt_assembled.log"
    assert debug_log.exists()
    content = debug_log.read_text(encoding="utf-8")
    assert "CONTEXT:   chat" in content
    assert "MODEL:     qwen2.5:3b" in content
    assert "[NUCLEO]" in content



def test_load_maestro_sections_from_file():
    """
    Verifica que las secciones se carguen directamente desde aura/ai/prompts/maestro.md.
    """
    from aura.ai.prompt_assembler import load_maestro_sections

    secs = load_maestro_sections(force_reload=True)
    assert "nucleo" in secs
    assert "interprete" in secs
    assert "chat" in secs
    assert "humor" in secs
    assert "programacion" in secs
    assert "ejemplos" in secs

    assert "IDENTIDAD Y LAS DOS MITADES" in secs["nucleo"]
    assert "[MODULO_INTERPRETE]" in secs["interprete"]
    assert "[MODULO_CHAT]" in secs["chat"]
    assert "[MODULO_HUMOR]" in secs["humor"]
    assert "[MODULO_PROGRAMACION]" in secs["programacion"]
    assert "[EJEMPLOS]" in secs["ejemplos"]


def test_capa3_json_parser_fence_tolerance():
    """
    Verifica que el intérprete de Capa 3 parsee correctamente JSON envuelto
    en markdown fences o con texto antes/después.
    """
    from aura.core.fuzzy_interpreter import FuzzyInterpreter
    from ai.provider_interface import AIProvider, ChatResponse, ProviderStatus

    class MockLLM(AIProvider):
        @property
        def provider_name(self) -> str:
            return "mock"
        def check_status(self):
            return ProviderStatus(available=True)
        def list_models(self):
            return ["test"]
        def chat(self, messages, **kwargs):
            return ChatResponse(
                content="Entendido. Acá va el resultado:\n```json\n{\n  \"tipo\": \"comando\",\n  \"intent\": \"close_app\",\n  \"target\": \"notepad\",\n  \"confianza\": 0.95,\n  \"razonamiento\": \"pide cerrar notepad\"\n}\n```\nSaludos.",
                model="test",
                provider="test"
            )

    fi = FuzzyInterpreter()
    res = fi.interpret_llm("por favor cerra el notepad", provider=MockLLM())
    assert res is not None
    assert res.intent == "close_app"
    assert res.target == "notepad"



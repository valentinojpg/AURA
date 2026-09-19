"""
Tests de Verificación para FASE 68:
- FIX A: Mock fuera de producción, AI_ALLOW_MOCK=false por defecto, cadena de fallback real y mensaje de error accionable.
- FIX B: Intent save_app_doc completamente cableado en router, entity resolver, fuzzy interpreter y app_saver.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from config.settings import settings
from ai.provider_factory import (
    get_default_provider,
    reset_default_provider,
    ProviderNotAvailableError,
    ProviderConfigError,
)
from ai.providers.mock_provider import MockProvider
from ai.providers.ollama_provider import OllamaProvider
from aura.core.intent_router import intent_router, Intent
from aura.core.entity_resolver import entity_resolver
from aura.core.fuzzy_interpreter import fuzzy_interpreter
from skills.skill_registry import skill_registry
from aura.core.filename_guard import is_valid_strict_filename
from skills.builtin.files_skill import FilesSkill


EXPECTED_OFFLINE_MSG = (
    "❌ No hay proveedor de IA disponible. Ollama no responde en "
    "localhost:11434 (inicialo con 'ollama serve') o configurá un "
    "proveedor con API key en Configuración."
)


@pytest.fixture(autouse=True)
def cleanup():
    reset_default_provider()
    yield
    reset_default_provider()


# =============================================================================
# FIX A: Mock fuera de producción & Fallback Chain
# =============================================================================

def test_mock_rejected_when_ai_allow_mock_is_false():
    """El mock provider NUNCA se activa si AI_ALLOW_MOCK no es 'true'."""
    reset_default_provider()
    with patch.dict(os.environ, {"AI_ALLOW_MOCK": "false", "AI_PROVIDER": "mock"}):
        with pytest.raises(ProviderConfigError) as excinfo:
            get_default_provider(force_reload=True, fallback_to_mock=False)
        assert "AI_ALLOW_MOCK=true" in str(excinfo.value)


def test_mock_allowed_only_when_ai_allow_mock_is_true():
    """El mock provider se activa SOLO cuando AI_ALLOW_MOCK=true."""
    reset_default_provider()
    with patch.dict(os.environ, {"AI_ALLOW_MOCK": "true", "AI_PROVIDER": "mock"}):
        provider = get_default_provider(force_reload=True, fallback_to_mock=True)
        assert isinstance(provider, MockProvider)


def test_ollama_offline_raises_exact_actionable_error():
    """Con Ollama apagado, chat() lanza ProviderNotAvailableError con el mensaje exacto."""
    import urllib.request
    import urllib.error
    from ai.provider_interface import ChatMessage

    provider = OllamaProvider(base_url="http://localhost:11434")
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        with pytest.raises(ProviderNotAvailableError) as excinfo:
            provider.chat([ChatMessage(role="user", content="¿cómo funciona un dict?")])
        assert EXPECTED_OFFLINE_MSG in str(excinfo.value)


def test_skills_and_router_do_not_depend_on_ai_provider():
    """Con Ollama apagado, abrir notepad, cerrar notepad, files_skill funcionan al 100%."""
    # Router resuelve comandos sin invocar ningún provider
    res_open = intent_router.parse("abre notepad")
    assert res_open is not None
    assert res_open.nombre == "open_app"

    res_write = intent_router.parse("escribí en notepad prueba offline")
    assert res_write is not None
    assert res_write.nombre == "write_in_app"

    # Fuzzy interpreter Capa 1/2 resuelve sin llamar al provider
    interp_write = fuzzy_interpreter.interpret_fuzzy("escribí en notepad prueba offline")
    assert interp_write is not None
    assert interp_write.intent == "write_in_app"


# =============================================================================
# FIX B: save_app_doc Intent Routing & Resolution
# =============================================================================

def test_router_matches_save_app_doc_variations():
    """El intent_router reconoce diferentes formulaciones de save_app_doc."""
    # 1. Directo con app y destino
    intent1 = intent_router.parse("guardá el notepad en el escritorio")
    assert intent1 is not None
    assert intent1.nombre == "save_app_doc"
    assert "notepad" in intent1.target.lower()
    assert "escritorio" in intent1.extra.get("destination", "").lower()

    # 2. Con nombre y destino
    intent2 = intent_router.parse("guardar el bloc de notas como notas.txt en documentos")
    assert intent2 is not None
    assert intent2.nombre == "save_app_doc"
    assert "bloc de notas" in intent2.target.lower()
    assert intent2.extra.get("filename") == "notas.txt"
    assert "documentos" in intent2.extra.get("destination", "").lower()

    # 3. Referencia a lo que escribiste
    intent3 = intent_router.parse("guarda lo que escribiste en el escritorio")
    assert intent3 is not None
    assert intent3.nombre == "save_app_doc"
    assert "escritorio" in intent3.extra.get("destination", "").lower()

    # 4. Referencia a la ventana
    intent4 = intent_router.parse("guardá la ventana como reporte.txt")
    assert intent4 is not None
    assert intent4.nombre == "save_app_doc"
    assert intent4.extra.get("filename") == "reporte.txt"


def test_entity_resolver_resolves_save_app_doc():
    """EntityResolver resuelve save_app_doc mapeándolo a app_saver.save_app_doc."""
    intent = Intent(
        nombre="save_app_doc",
        target="notepad",
        raw="guardar notepad",
        extra={"app": "notepad", "filename": "prueba.txt", "destination": "escritorio"}
    )
    resolved = entity_resolver.resolve(intent)
    assert resolved.resolved is True
    assert resolved.skill_name == "app_saver"
    assert resolved.command == "save_app_doc"
    assert resolved.args == ["notepad", "prueba.txt", "escritorio"]


def test_fuzzy_interpreter_resolves_save_app_doc():
    """FuzzyInterpreter maneja save_app_doc en Capa 1 y Capa 2."""
    res = fuzzy_interpreter.interpret("guardá el notepad en el escritorio")
    assert res is not None
    assert res.intent == "save_app_doc"
    assert res.resolved_entity is not None
    assert res.resolved_entity.skill_name == "app_saver"


def test_filename_guard_rejects_sentences():
    """El guard estricto de filenames no permite que oraciones o frases sean nombres de archivo."""
    # Frase larga
    valid, reason = is_valid_strict_filename("guardá el notepad en el escritorio")
    assert valid is False

    # Frase con palabras múltiples
    valid2, reason2 = is_valid_strict_filename("esto es un documento de prueba muy largo y explicativo")
    assert valid2 is False

    # Nombre válido
    valid3, reason3 = is_valid_strict_filename("notas_reunion.txt")
    assert valid3 is True


def test_app_saver_when_app_not_open_returns_clear_error():
    """Si la app no está abierta, app_saver retorna error claro y no crashea."""
    from aura.skills.app_saver import save_app_document

    # Intentar guardar una app inexistente con un nombre ficticio
    result = save_app_document(app_name="aplicacion_fantasma_12345", filename="test.txt", destination="escritorio")
    assert result.success is False
    assert "No se encontró ninguna instancia abierta" in result.error
    assert result.data.get("running") is False


def test_files_skill_write_file_utf8(tmp_path):
    """FilesSkill.write_file escribe contenido en UTF-8 y retorna ruta completa."""
    sk = FilesSkill()
    target = tmp_path / "test_utf8.txt"
    content = "Prueba con tildes: áéíóú, ñ, y caracteres especiales: ¡¿!"

    res = sk.write_file(str(target), content)
    assert res.success is True
    assert str(target) in res.output

    # Verificar lectura en UTF-8
    with open(target, "r", encoding="utf-8") as f:
        read_content = f.read()
    assert read_content == content

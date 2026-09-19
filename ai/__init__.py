"""
AURA — Paquete de IA (Fase 6)

Exporta la API pública del módulo de inteligencia artificial:
- Tipos de datos: ChatMessage, ChatResponse, ProviderStatus
- Interfaz: AIProvider
- Proveedores: OllamaProvider, MockProvider
- Errores: AuraAIError y subclases
- Factory: get_provider, get_default_provider

Uso recomendado:
    from ai import get_default_provider, ChatMessage
    provider = get_default_provider()
    response = provider.chat([ChatMessage(role="user", content="Hola")])
"""

# Tipos de datos e interfaz
from ai.provider_interface import (
    AIProvider,
    ChatMessage,
    ChatResponse,
    ProviderStatus,
)

# Errores
from ai.errors import (
    AuraAIError,
    ProviderNotAvailableError,
    ProviderConfigError,
    ModelNotFoundError,
    RequestTimeoutError,
    ResponseParseError,
)

# Factory
from ai.provider_factory import (
    get_provider,
    get_default_provider,
    list_available_providers,
    is_provider_registered,
)

# Proveedores concretos
from ai.providers.mock_provider import MockProvider
from ai.providers.ollama_provider import OllamaProvider

__all__ = [
    # Interfaz
    "AIProvider",
    # Tipos de datos
    "ChatMessage",
    "ChatResponse",
    "ProviderStatus",
    # Errores
    "AuraAIError",
    "ProviderNotAvailableError",
    "ProviderConfigError",
    "ModelNotFoundError",
    "RequestTimeoutError",
    "ResponseParseError",
    # Factory
    "get_provider",
    "get_default_provider",
    "list_available_providers",
    "is_provider_registered",
    # Proveedores concretos
    "MockProvider",
    "OllamaProvider",
]

"""
AURA — Factory de proveedores de IA (Fase 55 Multi-proveedor)

Crea y retorna el proveedor de IA adecuado según la configuración
en el archivo .env (clave AI_PROVIDER) y gestiona el fallback automático a Ollama local.

Principios de diseño:
- Punto único de creación de proveedores (patrón Factory / Registry)
- La app principal solo debe llamar a get_default_provider() o get_provider()
- Gestión centralizada de metadata por proveedor (nombre, modelo default, URL, API key env)
- Soporte para FallbackProvider: si el proveedor en la nube falla, conmuta
  automáticamente a Ollama local avisando en el chat una sola vez.
"""

from __future__ import annotations

from typing import Iterator
from ai.provider_interface import (
    AIProvider,
    ChatMessage,
    ChatResponse,
    ProviderStatus,
)
from ai.errors import ProviderConfigError, ProviderNotAvailableError, AuraAIError
from utils.logger import get_logger

_logger = get_logger("aura.ai.factory")

def _extract_reason(exc: Exception) -> str:
    """Extrae una descripción corta y limpia de la causa del fallo."""
    if hasattr(exc, "reason") and exc.reason:
        return str(exc.reason)
    if hasattr(exc, "status_code") and exc.status_code:
        detail = getattr(exc, "detail", "") or str(exc)
        if detail.startswith(f"{exc.status_code}:"):
            return detail
        return f"{exc.status_code}: {detail}"
    msg = str(exc)
    if msg.startswith("[") and "] " in msg:
        msg = msg.split("] ", 1)[1]
    return msg[:80]

# ── Registro de clases de proveedores (lazy import) ───────────────────────────

_PROVIDER_REGISTRY: dict[str, str] = {
    "mock":      "ai.providers.mock_provider:MockProvider",
    "ollama":    "ai.providers.ollama_provider:OllamaProvider",
    "openai":    "ai.providers.openai_provider:OpenAIProvider",
    "anthropic": "ai.providers.anthropic_provider:AnthropicProvider",
    "gemini":    "ai.providers.gemini_provider:GeminiProvider",
    "xai":       "ai.providers.openai_provider:XAIProvider",
    "custom":    "ai.providers.openai_provider:CustomOpenAIProvider",
}

# ── Metadata de proveedores ───────────────────────────────────────────────────

PROVIDER_METADATA: dict[str, dict] = {
    "ollama": {
        "display_name": "Ollama (Local)",
        "requires_api_key": False,
        "default_model": "qwen2.5:3b",
        "default_url": "http://localhost:11434",
        "env_key": None,
        "recommended_models": ["qwen2.5:3b", "llama3.2:3b", "mistral:7b", "phi3:mini"],
    },
    "openai": {
        "display_name": "OpenAI (ChatGPT)",
        "requires_api_key": True,
        "default_model": "gpt-4o-mini",
        "default_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
        "recommended_models": ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo", "o1-mini"],
    },
    "anthropic": {
        "display_name": "Anthropic (Claude)",
        "requires_api_key": True,
        "default_model": "claude-3-5-haiku-latest",
        "default_url": "https://api.anthropic.com/v1",
        "env_key": "ANTHROPIC_API_KEY",
        "recommended_models": [
            "claude-3-5-haiku-latest",
            "claude-3-5-sonnet-latest",
            "claude-3-opus-latest",
            "claude-3-5-haiku-20241022",
            "claude-3-5-sonnet-20241022",
            "claude-3-haiku-20240307",
        ],
    },
    "gemini": {
        "display_name": "Google Gemini",
        "requires_api_key": True,
        "default_model": "gemini-3.6-flash",
        "default_url": "https://generativelanguage.googleapis.com/v1beta",
        "env_key": "GEMINI_API_KEY",
        "recommended_models": ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-flash-latest"],
    },
    "xai": {
        "display_name": "xAI (Grok)",
        "requires_api_key": True,
        "default_model": "grok-2-latest",
        "default_url": "https://api.x.ai/v1",
        "env_key": "XAI_API_KEY",
        "recommended_models": ["grok-2-latest", "grok-2", "grok-beta", "grok-2-vision-latest"],
    },
    "custom": {
        "display_name": "Compatible OpenAI",
        "requires_api_key": False,
        "default_model": "default",
        "default_url": "",
        "env_key": "CUSTOM_API_KEY",
        "recommended_models": [],
    },
    "mock": {
        "display_name": "Mock (Simulado)",
        "requires_api_key": False,
        "default_model": "mock:instant",
        "default_url": "",
        "env_key": None,
        "recommended_models": ["mock:instant", "mock:realistic", "mock:delayed"],
    },
}


class FallbackProvider(AIProvider):
    """
    Proveedor compuesto que intenta utilizar un proveedor principal (ej: OpenAI, Claude, Gemini)
    y, si falla (timeout, sin saldo, error HTTP, red), conmuta automáticamente a Ollama local
    avisando en la conversación con la causa real del fallo.
    """

    def __init__(self, primary: AIProvider, fallback: AIProvider):
        self.primary = primary
        self.fallback = fallback
        self._fallback_notified = False
        self._logger = get_logger("aura.ai.fallback")

    @property
    def provider_name(self) -> str:
        return self.primary.provider_name

    @property
    def name(self) -> str:
        return self.primary.name

    @property
    def default_model(self) -> str:
        return getattr(self.primary, "default_model", "")

    @property
    def requires_api_key(self) -> bool:
        return self.primary.requires_api_key

    def check_status(self) -> ProviderStatus:
        p_status = self.primary.check_status()
        if p_status.available:
            return p_status

        fb_status = self.fallback.check_status()
        if fb_status.available:
            return ProviderStatus(
                available=True,
                message=f"☁️ Falló {self.primary.provider_name} ({p_status.message}), usando {self.fallback.provider_name} local",
                provider=self.primary.provider_name,
                models=p_status.models or fb_status.models,
            )
        return ProviderStatus(
            available=False,
            message=f"{self.primary.provider_name} no disponible ({p_status.message}) y fallback ({fb_status.message}) tampoco",
            provider=self.primary.provider_name,
            models=p_status.models or fb_status.models,
        )

    def list_models(self) -> list[str]:
        try:
            return self.primary.list_models()
        except Exception:
            return self.fallback.list_models()

    def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        system: str | None = None,
    ) -> ChatResponse:
        try:
            return self.primary.chat(
                messages, model=model, temperature=temperature, max_tokens=max_tokens, system=system
            )
        except Exception as e:
            reason = _extract_reason(e)
            self._logger.warning(
                f"Fallo en proveedor primario {self.primary.provider_name}: {reason}. "
                f"Conmutando a fallback {self.fallback.provider_name} local."
            )
            try:
                resp = self.fallback.chat(
                    messages, model=None, temperature=temperature, max_tokens=max_tokens, system=system
                )
            except Exception as fb_err:
                self._logger.error(f"Fallback {self.fallback.provider_name} también falló: {fb_err}")
                raise ProviderNotAvailableError(
                    "❌ No hay proveedor de IA disponible. Ollama no responde en localhost:11434 "
                    "(inicialo con 'ollama serve') o configurá un proveedor con API key en Configuración.",
                    provider=self.primary.provider_name,
                ) from fb_err

            if not self._fallback_notified:
                notice = f"☁️ Falló {self.primary.provider_name}, usando Ollama local\n\n"
                resp.content = notice + resp.content
                self._fallback_notified = True
            return resp

    def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        system: str | None = None,
    ) -> Iterator[str]:
        try:
            stream = self.primary.chat_stream(
                messages, model=model, temperature=temperature, max_tokens=max_tokens, system=system
            )
            # Forzar evaluación del primer chunk para atrapar errores antes de yield
            first_chunk = next(stream)
            yield first_chunk
            yield from stream
        except Exception as e:
            reason = _extract_reason(e)
            self._logger.warning(
                f"Fallo en stream primario {self.primary.provider_name}: {reason}. "
                f"Conmutando a fallback {self.fallback.provider_name} local."
            )
            try:
                fb_stream = self.fallback.chat_stream(
                    messages, model=None, temperature=temperature, max_tokens=max_tokens, system=system
                )
                first_fb_chunk = next(fb_stream)
            except Exception as fb_err:
                self._logger.error(f"Fallback {self.fallback.provider_name} también falló en stream: {fb_err}")
                raise ProviderNotAvailableError(
                    "❌ No hay proveedor de IA disponible. Ollama no responde en localhost:11434 "
                    "(inicialo con 'ollama serve') o configurá un proveedor con API key en Configuración.",
                    provider=self.primary.provider_name,
                ) from fb_err

            if not self._fallback_notified:
                yield f"☁️ Falló {self.primary.provider_name}, usando Ollama local\n\n"
                self._fallback_notified = True
            yield first_fb_chunk
            yield from fb_stream

    def reset_fallback_notification(self) -> None:
        """Reinicia la bandera de aviso para la próxima sesión/llamada."""
        self._fallback_notified = False

    def __repr__(self) -> str:
        return f"<FallbackProvider primary={self.primary!r} fallback={self.fallback!r}>"


def _import_provider_class(provider_name: str):
    """Importa dinámicamente la clase del proveedor solicitado."""
    if provider_name not in _PROVIDER_REGISTRY:
        available = ", ".join(_PROVIDER_REGISTRY.keys())
        raise ProviderConfigError(
            f"Proveedor '{provider_name}' no registrado. "
            f"Opciones disponibles: {available}",
            provider=provider_name,
        )

    module_path, class_name = _PROVIDER_REGISTRY[provider_name].split(":")

    try:
        import importlib
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return cls
    except ImportError as e:
        raise ProviderConfigError(
            f"No se pudo importar el proveedor '{provider_name}': {e}",
            provider=provider_name,
        ) from e
    except AttributeError as e:
        raise ProviderConfigError(
            f"Clase '{class_name}' no encontrada en '{module_path}': {e}",
            provider=provider_name,
        ) from e


def get_provider(provider_name: str, **kwargs) -> AIProvider:
    """
    Crea y retorna una instancia del proveedor de IA solicitado con los argumentos dados.
    """
    _logger.info(f"Creando proveedor: '{provider_name}'")
    cls = _import_provider_class(provider_name)
    try:
        instance = cls(**kwargs)
        _logger.info(f"Proveedor '{provider_name}' creado: {instance!r}")
        return instance
    except Exception as e:
        raise ProviderConfigError(
            f"Error al instanciar el proveedor '{provider_name}': {e}",
            provider=provider_name,
        ) from e


_cached_default_provider: AIProvider | None = None


def reset_default_provider() -> None:
    """Invalida la instancia en cache para que se reconstruya con la nueva configuración."""
    global _cached_default_provider
    _cached_default_provider = None
    _logger.info("Instancia de proveedor por defecto reseteada.")


def get_default_provider(fallback_to_mock: bool = False, force_reload: bool = False) -> AIProvider:
    """
    Crea el proveedor configurado en .env (clave AI_PROVIDER) con sus credenciales y opciones.
    Aplica automáticamente FallbackProvider hacia Ollama si AI_FALLBACK_OLLAMA=true.
    MockProvider SOLO se activa si AI_ALLOW_MOCK=true en .env (para tests y desarrollo).
    """
    global _cached_default_provider
    if _cached_default_provider is not None and not force_reload:
        return _cached_default_provider

    from config.settings import settings

    allow_mock = settings.get_bool("AI_ALLOW_MOCK", False)
    provider_name = (settings.get("AI_PROVIDER", "ollama") or "ollama").strip().lower()
    _logger.info(f"Proveedor configurado en .env: '{provider_name}' (AI_ALLOW_MOCK={allow_mock})")

    if provider_name == "mock" and not allow_mock:
        _logger.warning("AI_PROVIDER=mock configurado pero AI_ALLOW_MOCK=false. MockProvider denegado.")
        raise ProviderConfigError(
            "MockProvider está desactivado. Para activarlo en modo desarrollo o tests, configurá AI_ALLOW_MOCK=true en .env.",
            provider="mock",
        )

    kwargs: dict = {}
    ai_model = settings.get("AI_MODEL", "")

    if provider_name == "ollama":
        ollama_url = settings.get("OLLAMA_URL", "http://localhost:11434") or "http://localhost:11434"
        kwargs = {"base_url": ollama_url, "model": ai_model or "qwen2.5:3b"}
    elif provider_name == "openai":
        kwargs = {"api_key": settings.get("OPENAI_API_KEY", "")}
        if ai_model:
            kwargs["model"] = ai_model
    elif provider_name == "anthropic":
        kwargs = {"api_key": settings.get("ANTHROPIC_API_KEY", "")}
        if ai_model:
            kwargs["model"] = ai_model
    elif provider_name == "gemini":
        kwargs = {"api_key": settings.get("GEMINI_API_KEY", "")}
        if ai_model:
            kwargs["model"] = ai_model
    elif provider_name == "xai":
        kwargs = {"api_key": settings.get("XAI_API_KEY", "")}
        if ai_model:
            kwargs["model"] = ai_model
    elif provider_name == "custom":
        kwargs = {
            "base_url": settings.get("CUSTOM_BASE_URL", "") or "",
            "api_key": settings.get("CUSTOM_API_KEY", "") or "",
            "model": settings.get("CUSTOM_MODEL", "") or ai_model or "default",
        }
    elif provider_name == "mock":
        kwargs = {"simulate_delay_ms": 0}

    try:
        primary = get_provider(provider_name, **kwargs)

        # Si el proveedor es de nube y AI_FALLBACK_OLLAMA=true, envolver en FallbackProvider
        fallback_ollama_enabled = settings.get_bool("AI_FALLBACK_OLLAMA", True)
        if provider_name not in ("ollama", "mock") and fallback_ollama_enabled:
            ollama_url = settings.get("OLLAMA_URL", "http://localhost:11434") or "http://localhost:11434"
            try:
                fallback_prov = get_provider("ollama", base_url=ollama_url, model="qwen2.5:3b")
            except Exception:
                if allow_mock:
                    fallback_prov = get_provider("mock")
                else:
                    cls = _import_provider_class("ollama")
                    fallback_prov = cls(base_url=ollama_url, model="qwen2.5:3b")

            compound_provider = FallbackProvider(primary=primary, fallback=fallback_prov)
            _cached_default_provider = compound_provider
            return compound_provider

        # Si es Ollama y no está disponible, fallback a Mock SOLO si AI_ALLOW_MOCK=true y se solicitó
        if provider_name == "ollama":
            if allow_mock and fallback_to_mock:
                status = primary.check_status()
                if not status.available:
                    _logger.warning(f"Ollama no disponible ({status.message}). AI_ALLOW_MOCK=true -> Usando MockProvider.")
                    mock_prov = get_provider("mock")
                    _cached_default_provider = mock_prov
                    return mock_prov

        _cached_default_provider = primary
        return primary

    except ProviderConfigError as e:
        _logger.error(f"Error al crear proveedor '{provider_name}': {e}")
        if allow_mock and fallback_to_mock and provider_name != "mock":
            _logger.warning("AI_ALLOW_MOCK=true -> Fallback a MockProvider por error de configuración.")
            mock_prov = get_provider("mock")
            _cached_default_provider = mock_prov
            return mock_prov
        raise


def list_available_providers() -> list[str]:
    """Retorna los nombres de todos los proveedores registrados."""
    return list(_PROVIDER_REGISTRY.keys())


def is_provider_registered(provider_name: str) -> bool:
    """Verifica si un proveedor está registrado en el factory."""
    return provider_name in _PROVIDER_REGISTRY

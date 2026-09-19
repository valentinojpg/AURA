"""
AURA — Selector de Proveedor de IA para Humor (Fase 64).

Resuelve el proveedor de IA a utilizar para llamadas cómicas (roasts y chistes)
según la configuración HUMOR_PROVIDER (auto | local | <nombre>):
  - 'auto': Si hay un proveedor cloud con key válida y health OK, se usa.
            Si no, se intenta proveedor local (Ollama / Mock).
            Si falla o no hay ninguno, retorna None (degrada a banco local).
  - 'local': Se utiliza Ollama o Mock local, o None.
  - '<nombre>': Intenta cargar el proveedor especificado (gemini, openai, etc.).
                Si falla su health check o lanza excepción, retorna None.
"""

from __future__ import annotations

from typing import Any, Optional

from config.settings import settings
from utils.logger import get_logger

_logger = get_logger("aura.personality.humor_provider")

CLOUD_PROVIDER_KEYS = [
    ("gemini", "GEMINI_API_KEY"),
    ("openai", "OPENAI_API_KEY"),
    ("anthropic", "ANTHROPIC_API_KEY"),
    ("xai", "XAI_API_KEY"),
    ("custom", "CUSTOM_API_KEY"),
]


def get_humor_provider(default_provider: Optional[Any] = None) -> Optional[Any]:
    """
    Retorna la instancia del proveedor a usar para humor o None si se debe usar banco local.
    """
    mode = settings.get("HUMOR_PROVIDER", "auto").strip().lower()

    try:
        from ai import provider_factory

        # 1. Modo "auto": prioriza cloud si está configurado y saludable
        if mode == "auto":
            # Si default_provider ya es un provider cloud saludable
            if default_provider is not None:
                p_name = getattr(default_provider, "name", "").lower()
                if any(p_name.startswith(c) for c in ("gemini", "openai", "anthropic", "xai", "custom")):
                    try:
                        st = default_provider.status()
                        if st.available:
                            return default_provider
                    except Exception:
                        pass

            # Buscar entre los proveedores cloud configurados
            for prov_name, env_key in CLOUD_PROVIDER_KEYS:
                key_val = settings.get(env_key, "").strip()
                if key_val:
                    try:
                        prov = provider_factory.get_provider(prov_name)
                        st = prov.status()
                        if st.available:
                            _logger.debug("HumorProvider auto: usando proveedor cloud '%s'", prov_name)
                            return prov
                    except Exception as e:
                        _logger.debug("HumorProvider auto: error verificando '%s': %s", prov_name, e)

            # Si no hay cloud disponible, intentar con el default_provider (local)
            if default_provider is not None:
                try:
                    st = default_provider.status()
                    if st.available:
                        return default_provider
                except Exception:
                    pass

            # Intentar Ollama local como fallback
            try:
                prov_ollama = provider_factory.get_provider("ollama")
                if prov_ollama.status().available:
                    return prov_ollama
            except Exception:
                pass

            # Degradación transparente a banco local
            _logger.info("HumorProvider auto: ningún proveedor disponible o saludable -> degradando a banco local.")
            return None

        # 2. Modo "local": solo proveedores locales
        if mode == "local":
            if default_provider is not None:
                p_name = getattr(default_provider, "name", "").lower()
                if p_name in ("ollama", "mock"):
                    try:
                        if default_provider.status().available:
                            return default_provider
                    except Exception:
                        pass
            try:
                prov_ollama = provider_factory.get_provider("ollama")
                if prov_ollama.status().available:
                    return prov_ollama
            except Exception:
                pass
            return None

        # 3. Proveedor con nombre específico (ej: 'gemini', 'openai', 'anthropic', 'ollama', 'mock')
        try:
            prov = provider_factory.get_provider(mode)
            if prov.status().available:
                return prov
            else:
                _logger.warning("HumorProvider: proveedor '%s' no está disponible -> degradando a banco local.", mode)
                return None
        except Exception as e:
            _logger.warning("HumorProvider: error obteniendo proveedor '%s': %s -> degradando a banco local.", mode, e)
            return None

    except Exception as e_top:
        _logger.warning("HumorProvider: excepción general al resolver proveedor: %s -> degradando a banco local.", e_top)
        return None

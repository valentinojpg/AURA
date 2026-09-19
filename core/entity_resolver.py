"""
AURA — Módulo de compatibilidad para core.entity_resolver.
Re-exporta todo desde aura.core.entity_resolver.
"""

from aura.core.entity_resolver import (
    EntityResolver,
    ResolvedEntity,
    entity_resolver,
    resolve,
    BUILTIN_ALIASES,
    is_url_or_domain,
)

__all__ = [
    "EntityResolver",
    "ResolvedEntity",
    "entity_resolver",
    "resolve",
    "BUILTIN_ALIASES",
    "is_url_or_domain",
]

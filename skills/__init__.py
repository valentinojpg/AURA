"""
AURA — Paquete de Skills (Fase 11)

API pública del sistema de skills de AURA.

Exports principales:
    BaseSkill        — Clase base para todas las skills
    SkillMeta        — Metadatos de una skill
    SkillResult      — Resultado de ejecución de un comando
    SkillEntry       — Entrada del registro (skill + estado)
    SkillRegistry    — Clase del registro central
    skill_registry   — Instancia global del registro (singleton)
    CATEGORY_*       — Constantes de categoría

Uso rápido:
    from skills import skill_registry, BaseSkill, SkillMeta, SkillResult

    # Descubrir y registrar todas las skills builtin
    skill_registry.discover_builtin()

    # Ejecutar un comando
    result = skill_registry.execute("demo_skill", "hola", ["Mundo"])
    print(result.output)
"""

from skills.skill_base import (
    BaseSkill,
    SkillMeta,
    SkillResult,
    CATEGORY_DEMO,
    CATEGORY_SYSTEM,
    CATEGORY_FILES,
    CATEGORY_SEARCH,
    CATEGORY_PROGRAMS,
    CATEGORY_WEB,
    CATEGORY_AUTOMATION,
)
from skills.skill_registry import SkillEntry, SkillRegistry, skill_registry
from skills.builtin.demo_skill import DemoSkill

__all__ = [
    # Clases base
    "BaseSkill",
    "SkillMeta",
    "SkillResult",
    # Registro
    "SkillEntry",
    "SkillRegistry",
    "skill_registry",
    # Skills builtin
    "DemoSkill",
    # Categorías
    "CATEGORY_DEMO",
    "CATEGORY_SYSTEM",
    "CATEGORY_FILES",
    "CATEGORY_SEARCH",
    "CATEGORY_PROGRAMS",
    "CATEGORY_WEB",
    "CATEGORY_AUTOMATION",
]

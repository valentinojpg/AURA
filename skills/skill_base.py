"""
AURA — Clase base abstracta para Skills (Fase 11)

Define el contrato que todas las skills deben implementar:
  - Metadatos: nombre, versión, descripción, autor, categoría, comandos
  - Métodos de ciclo de vida: setup(), teardown()
  - Método de ejecución: execute(command, args) → SkillResult

Uso:
    from skills.skill_base import BaseSkill, SkillResult, SkillMeta

    class MiSkill(BaseSkill):
        META = SkillMeta(
            name="mi_skill",
            version="1.0.0",
            display_name="Mi Skill",
            description="Hace algo útil.",
            author="AURA",
            category="demo",
            commands=["hola", "adios"],
        )

        def execute(self, command: str, args: list[str]) -> SkillResult:
            return SkillResult(success=True, output="Hola!")
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from utils.logger import get_logger

_logger = get_logger("aura.skills.base")

# ── Categorías disponibles ─────────────────────────────────────────────────

CATEGORY_DEMO       = "demo"
CATEGORY_SYSTEM     = "system"
CATEGORY_FILES      = "files"
CATEGORY_SEARCH     = "search"
CATEGORY_PROGRAMS   = "programs"
CATEGORY_WEB        = "web"
CATEGORY_AUTOMATION = "automation"


# ── Metadatos de una Skill ─────────────────────────────────────────────────

@dataclass(frozen=True)
class SkillMeta:
    """
    Metadatos inmutables de una skill.

    Attributes:
        name:         Identificador interno único (ej. "demo_skill").
        version:      Versión semántica (ej. "1.0.0").
        display_name: Nombre legible para mostrar en la UI.
        description:  Descripción breve de la funcionalidad.
        author:       Nombre del autor o equipo.
        category:     Categoría (usar constantes CATEGORY_*).
        commands:     Lista de comandos que esta skill maneja.
        builtin:      True si es una skill incluida con AURA.
        enabled_by_default: Estado inicial de habilitación.
    """

    name: str
    version: str
    display_name: str
    description: str
    author: str = "AURA"
    category: str = CATEGORY_DEMO
    commands: list[str] = field(default_factory=list)
    builtin: bool = True
    enabled_by_default: bool = True


# ── Resultado de ejecución ─────────────────────────────────────────────────

@dataclass
class SkillResult:
    """
    Resultado de la ejecución de un comando de skill.

    Attributes:
        success:  True si la acción se completó sin errores.
        output:   Texto de salida para mostrar al usuario.
        data:     Datos adicionales estructurados (opcional).
        error:    Mensaje de error si success=False.
    """

    success: bool
    output: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def __bool__(self) -> bool:
        return self.success


# ── Clase base abstracta ───────────────────────────────────────────────────

class BaseSkill(ABC):
    """
    Clase base abstracta para todas las Skills de AURA.

    Subclases deben:
    1. Definir el atributo de clase META: SkillMeta
    2. Implementar el método execute(command, args) → SkillResult

    Opcionalmente pueden sobrescribir setup() y teardown().
    """

    # Subclases DEBEN definir META como atributo de clase
    META: SkillMeta

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Verifica que las subclases concretas definan META."""
        super().__init_subclass__(**kwargs)
        # Solo validar clases concretas (no abstractas)
        if not getattr(cls, "__abstractmethods__", None) and not hasattr(cls, "META"):
            raise TypeError(
                f"La clase '{cls.__name__}' debe definir el atributo de clase META: SkillMeta"
            )

    def __init__(self) -> None:
        self._is_setup = False
        self._logger = get_logger(f"aura.skills.{self.META.name}")

    # ── Ciclo de vida ──────────────────────────────────────────────────────

    def setup(self) -> None:
        """
        Inicializa la skill. Llamado por el registry al registrar.

        Subclases pueden sobrescribir para cargar recursos, leer config, etc.
        No lanza excepciones; los errores se registran en el log.
        """
        self._is_setup = True
        self._logger.debug(f"Skill '{self.META.name}' inicializada.")

    def teardown(self) -> None:
        """
        Limpia los recursos de la skill. Llamado al desregistrar o cerrar.

        Subclases pueden sobrescribir para liberar recursos.
        """
        self._is_setup = False
        self._logger.debug(f"Skill '{self.META.name}' terminada.")

    # ── Ejecución ──────────────────────────────────────────────────────────

    @abstractmethod
    def execute(self, command: str, args: list[str]) -> SkillResult:
        """
        Ejecuta un comando de la skill.

        Args:
            command: Nombre del comando (ej. "hola", "abrir").
                     Debe ser uno de los listados en META.commands.
            args:    Lista de argumentos adicionales (puede ser vacía).

        Returns:
            SkillResult con el resultado de la ejecución.
        """

    # ── Helpers ────────────────────────────────────────────────────────────

    def handles(self, command: str) -> bool:
        """
        Verifica si esta skill maneja el comando dado.

        Args:
            command: Nombre del comando a verificar.

        Returns:
            True si el comando está en META.commands.
        """
        return command in self.META.commands

    @property
    def is_setup(self) -> Any:
        """True si setup() fue llamado y teardown() no (compatible con property y callable)."""
        class _CallableBool(int):
            def __call__(self):
                return bool(self)
            def __bool__(self):
                return int(self) != 0
        return _CallableBool(1 if self._is_setup else 0)

    @property
    def name(self) -> str:
        """Atajo para META.name."""
        return self.META.name

    @property
    def display_name(self) -> str:
        """Atajo para META.display_name."""
        return self.META.display_name

    @property
    def description(self) -> str:
        """Atajo para META.description."""
        return self.META.description

    @property
    def version(self) -> str:
        """Atajo para META.version."""
        return self.META.version

    @property
    def category(self) -> str:
        """Atajo para META.category."""
        return self.META.category

    @property
    def commands(self) -> list[str]:
        """Atajo para META.commands."""
        return list(self.META.commands)

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} name='{self.META.name}' "
            f"v{self.META.version} setup={self._is_setup}>"
        )

"""
AURA — Registro central de Skills (Fase 11)

Gestiona el ciclo de vida completo de las skills:
  - Registro manual de instancias
  - Descubrimiento automático del directorio skills/builtin/
  - Habilitación / deshabilitación por nombre
  - Búsqueda por nombre o comando
  - Estado y metadatos de cada skill registrada

Uso:
    from skills.skill_registry import skill_registry

    # El registro auto-descubre las builtin al primer acceso
    skill_registry.discover_builtin()

    # Obtener una skill por nombre
    skill = skill_registry.get("demo_skill")

    # Listar todas las skills habilitadas
    for entry in skill_registry.list_enabled():
        print(entry.skill.META.display_name)

    # Ejecutar un comando
    result = skill_registry.execute("demo", "hola", [])
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from dataclasses import dataclass, field
from typing import Iterator

from skills.skill_base import BaseSkill, SkillResult
from utils.logger import get_logger

_logger = get_logger("aura.skills.registry")


# ── Entrada del registro ───────────────────────────────────────────────────

@dataclass
class SkillEntry:
    """
    Entrada interna del registro para una skill.

    Attributes:
        skill:   Instancia de la skill.
        enabled: Estado de habilitación actual.
    """

    skill: BaseSkill
    enabled: bool = True

    @property
    def name(self) -> str:
        return self.skill.META.name

    @property
    def display_name(self) -> str:
        return self.skill.META.display_name

    @property
    def meta(self):
        return self.skill.META


# ── Registro central ───────────────────────────────────────────────────────

class SkillRegistry:
    """
    Registro central de Skills de AURA.

    Mantiene un diccionario de skills registradas, su estado de
    habilitación, y provee métodos para descubrir, ejecutar y
    gestionar skills de forma centralizada.

    Es un singleton: usar la instancia global `skill_registry`.
    """

    def __init__(self) -> None:
        # name → SkillEntry
        self._entries: dict[str, SkillEntry] = {}
        self._builtin_discovered = False

    # ── Registro y desregistro ─────────────────────────────────────────────

    def register(self, skill: BaseSkill, *, force: bool = False) -> bool:
        """
        Registra una instancia de skill en el registro.

        Args:
            skill:  Instancia de BaseSkill ya instanciada.
            force:  Si True, reemplaza una skill con el mismo nombre.

        Returns:
            True si se registró correctamente, False si ya existía
            (y force=False) o si la instancia no es válida.
        """
        if not isinstance(skill, BaseSkill):
            _logger.error(
                f"SkillRegistry.register: '{skill}' no es instancia de BaseSkill."
            )
            return False

        name = skill.META.name
        if name in self._entries and not force:
            _logger.warning(
                f"Skill '{name}' ya está registrada. Usar force=True para reemplazar."
            )
            return False

        # Teardown de la anterior si existe
        if name in self._entries:
            try:
                self._entries[name].skill.teardown()
            except Exception as e:
                _logger.error(f"Error en teardown de '{name}' al reemplazar: {e}")

        # Setup de la nueva
        try:
            skill.setup()
        except Exception as e:
            _logger.error(f"Error en setup de skill '{name}': {e}")
            return False

        enabled = skill.META.enabled_by_default
        self._entries[name] = SkillEntry(skill=skill, enabled=enabled)
        _logger.info(
            f"Skill registrada: '{name}' v{skill.META.version} "
            f"[enabled={enabled}]"
        )
        return True

    def unregister(self, name: str) -> bool:
        """
        Desregistra una skill por nombre.

        Args:
            name: Nombre interno de la skill.

        Returns:
            True si se desregistró, False si no estaba registrada.
        """
        if name not in self._entries:
            _logger.warning(f"Skill '{name}' no está registrada.")
            return False

        try:
            self._entries[name].skill.teardown()
        except Exception as e:
            _logger.error(f"Error en teardown de '{name}': {e}")

        del self._entries[name]
        _logger.info(f"Skill desregistrada: '{name}'")
        return True

    # ── Habilitación / deshabilitación ─────────────────────────────────────

    def enable(self, name: str) -> bool:
        """
        Habilita una skill registrada.

        Args:
            name: Nombre interno de la skill.

        Returns:
            True si se habilitó, False si no existe.
        """
        if name not in self._entries:
            return False
        self._entries[name].enabled = True
        _logger.debug(f"Skill '{name}' habilitada.")
        return True

    def disable(self, name: str) -> bool:
        """
        Deshabilita una skill registrada (no la elimina del registro).

        Args:
            name: Nombre interno de la skill.

        Returns:
            True si se deshabilitó, False si no existe.
        """
        if name not in self._entries:
            return False
        self._entries[name].enabled = False
        _logger.debug(f"Skill '{name}' deshabilitada.")
        return True

    def is_enabled(self, name: str) -> bool:
        """Retorna True si la skill está registrada y habilitada."""
        entry = self._entries.get(name)
        return entry is not None and entry.enabled

    # ── Búsqueda ───────────────────────────────────────────────────────────

    def get(self, name: str) -> BaseSkill | None:
        """
        Retorna la instancia de una skill por nombre.

        Args:
            name: Nombre interno de la skill.

        Returns:
            BaseSkill o None si no está registrada.
        """
        entry = self._entries.get(name)
        return entry.skill if entry is not None else None

    def get_entry(self, name: str) -> SkillEntry | None:
        """Retorna la SkillEntry completa (con estado de habilitación)."""
        return self._entries.get(name)

    def find_by_command(self, command: str) -> BaseSkill | None:
        """
        Busca la primera skill habilitada que maneje el comando dado.

        Args:
            command: Nombre del comando a buscar.

        Returns:
            Primera BaseSkill habilitada que maneja el comando, o None.
        """
        for entry in self._entries.values():
            if entry.enabled and entry.skill.handles(command):
                return entry.skill
        return None

    # ── Listado ────────────────────────────────────────────────────────────

    def list_all(self) -> list[SkillEntry]:
        """Retorna todas las SkillEntry registradas (habilitadas y deshabilitadas)."""
        return list(self._entries.values())

    def list_enabled(self) -> list[SkillEntry]:
        """Retorna solo las SkillEntry habilitadas."""
        return [e for e in self._entries.values() if e.enabled]

    def list_disabled(self) -> list[SkillEntry]:
        """Retorna solo las SkillEntry deshabilitadas."""
        return [e for e in self._entries.values() if not e.enabled]

    def __iter__(self) -> Iterator[SkillEntry]:
        """Itera sobre todas las SkillEntry registradas."""
        return iter(self._entries.values())

    def __len__(self) -> int:
        """Número total de skills registradas."""
        return len(self._entries)

    def __contains__(self, name: str) -> bool:
        """True si una skill con ese nombre está registrada."""
        return name in self._entries

    # ── Descubrimiento automático ──────────────────────────────────────────

    def discover_builtin(self) -> int:
        """
        Descubre y registra automáticamente todas las skills builtin.

        Busca en el paquete `skills.builtin` todas las subclases concretas
        de BaseSkill que tengan META definido y las registra.

        Returns:
            Número de skills nuevas registradas en esta llamada.
        """
        if self._builtin_discovered:
            _logger.debug("discover_builtin() ya ejecutado — ignorando llamada duplicada.")
            return 0

        registered = 0

        try:
            import skills.builtin as builtin_pkg
            pkg_path = builtin_pkg.__path__
            pkg_name = builtin_pkg.__name__
        except ImportError as e:
            _logger.error(f"No se pudo importar skills.builtin: {e}")
            self._builtin_discovered = True
            return 0

        for module_info in pkgutil.iter_modules(pkg_path):
            module_name = f"{pkg_name}.{module_info.name}"
            try:
                module = importlib.import_module(module_name)
            except Exception as e:
                _logger.error(f"Error al importar módulo de skill '{module_name}': {e}")
                continue

            for attr_name in dir(module):
                attr = getattr(module, attr_name, None)
                if (
                    attr is None
                    or not inspect.isclass(attr)
                    or not issubclass(attr, BaseSkill)
                    or attr is BaseSkill
                    or inspect.isabstract(attr)
                    or not hasattr(attr, "META")
                ):
                    continue

                try:
                    instance = attr()
                except Exception as e:
                    _logger.error(
                        f"Error al instanciar skill '{attr_name}': {e}"
                    )
                    continue

                if self.register(instance):
                    registered += 1

        self._builtin_discovered = True
        _logger.info(
            f"discover_builtin() completado: {registered} skill(s) registrada(s)."
        )
        return registered

    # ── Ejecución ──────────────────────────────────────────────────────────

    def execute(
        self,
        skill_name: str,
        command: str,
        args: list[str],
    ) -> SkillResult:
        """
        Ejecuta un comando en una skill específica.

        Args:
            skill_name: Nombre interno de la skill.
            command:    Nombre del comando a ejecutar.
            args:       Lista de argumentos adicionales.

        Returns:
            SkillResult con el resultado.
            Si la skill no existe o está deshabilitada, retorna error.
        """
        entry = self._entries.get(skill_name)

        if entry is None:
            msg = f"Skill '{skill_name}' no está registrada."
            _logger.warning(msg)
            return SkillResult(success=False, error=msg)

        if not entry.enabled:
            msg = f"Skill '{skill_name}' está deshabilitada."
            _logger.warning(msg)
            return SkillResult(success=False, error=msg)

        if not entry.skill.handles(command):
            msg = (
                f"Skill '{skill_name}' no maneja el comando '{command}'. "
                f"Comandos disponibles: {entry.skill.commands}"
            )
            _logger.warning(msg)
            return SkillResult(success=False, error=msg)

        try:
            _logger.info(
                f"Ejecutando: skill='{skill_name}' command='{command}' "
                f"args={args}"
            )
            result = entry.skill.execute(command, args)
            if result.success:
                _logger.debug(
                    f"Skill '{skill_name}' completó '{command}' exitosamente."
                )
            else:
                _logger.warning(
                    f"Skill '{skill_name}' retornó fallo en '{command}': "
                    f"{result.error}"
                )
            return result
        except Exception as e:
            msg = f"Excepción en skill '{skill_name}' al ejecutar '{command}': {e}"
            _logger.error(msg, exc_info=True)
            return SkillResult(success=False, error=str(e))

    # ── Reset (para tests) ─────────────────────────────────────────────────

    def reset(self) -> None:
        """
        Limpia el registro completamente.

        Llama teardown() en todas las skills y elimina las entradas.
        Diseñado principalmente para tests.
        """
        for name, entry in list(self._entries.items()):
            try:
                entry.skill.teardown()
            except Exception as e:
                _logger.error(f"Error en teardown de '{name}' durante reset: {e}")
        self._entries.clear()
        self._builtin_discovered = False
        _logger.debug("SkillRegistry reseteado.")

    def __repr__(self) -> str:
        names = list(self._entries.keys())
        return f"<SkillRegistry skills={names}>"


# ── Instancia global (singleton) ───────────────────────────────────────────

skill_registry = SkillRegistry()

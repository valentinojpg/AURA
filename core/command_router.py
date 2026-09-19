"""
AURA — Router de Comandos de Texto (Fase 13)

Interpreta el texto libre que escribe el usuario en el chat y determina
si debe enrutarse a una skill registrada o pasar a la IA normal.

Logica de resolucion:
  1. Si el texto empieza con '/' → comando del router (/ayuda, /skills, /comandos)
  2. Si la primera palabra coincide con un comando de una skill habilitada → ejecutar skill
  3. Si ninguna skill maneja el texto → retornar None (pasar a la IA)

Comandos internos del router:
  /ayuda        → Muestra ayuda general del sistema de comandos
  /skills       → Lista todas las skills registradas y habilitadas
  /comandos     → Alias de /skills; muestra todos los comandos disponibles

Formato de entrada aceptado:
  eco Hola Mundo          → skill_name=eco, args=['Hola', 'Mundo']
  hola                    → skill_name=hola, args=[]
  hola AURA               → skill_name=hola, args=['AURA']
  /ayuda                  → comando interno del router
  /skills                 → comando interno del router

Uso:
    from core.command_router import command_router, RouteResult

    result = command_router.route("hola")
    if result is not None:
        print(result.output)   # Respuesta de la skill
    else:
        pass  # Pasar a la IA
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from utils.logger import get_logger

if TYPE_CHECKING:
    pass

_logger = get_logger("aura.core.command_router")


# -- Resultado del enrutamiento -----------------------------------------------

@dataclass
class RouteResult:
    """
    Resultado de intentar enrutar un texto a una skill.

    Attributes:
        handled:    True si el router manejo el texto (sea exito o error).
        success:    True si la ejecucion fue exitosa.
        output:     Texto de respuesta para mostrar al usuario.
        error:      Mensaje de error si success=False.
        skill_name: Nombre de la skill que proceso el comando (o 'router').
        command:    Comando extraido del texto de entrada.
        args:       Argumentos extraidos del texto de entrada.
    """

    handled: bool
    success: bool
    output: str = ""
    error: str = ""
    skill_name: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.handled and self.success


# -- Router principal ---------------------------------------------------------

class CommandRouter:
    """
    Router central de comandos de texto de AURA.

    Interpreta el texto escrito por el usuario en el chat y determina
    si corresponde a una skill registrada o debe pasar a la IA.

    Usa el SkillRegistry global para descubrir y ejecutar skills.
    Es un singleton: usar la instancia global `command_router`.
    """

    # Prefijo que indica comandos internos del router
    COMMAND_PREFIX = "/"

    # Comandos internos del router (sin el /)
    _INTERNAL_COMMANDS = {"ayuda", "skills", "comandos", "help"}

    def __init__(self) -> None:
        self._registry = None  # Lazy import para evitar ciclos

    def _get_registry(self):
        """Obtiene el SkillRegistry de forma lazy para evitar imports circulares."""
        if self._registry is None:
            from skills.skill_registry import skill_registry
            self._registry = skill_registry
        return self._registry

    # -- API publica ----------------------------------------------------------

    def route(self, text: str):
        """
        Intenta enrutar el texto a una skill o comando interno.

        Args:
            text: Texto escrito por el usuario (ya con strip aplicado).

        Returns:
            RouteResult si el router manejo el texto (handled=True),
            None si el texto debe pasar a la IA normal.
        """
        if not text or not text.strip():
            return None

        text = text.strip()

        # -- Comandos internos del router (prefijo /) -------------------------
        if text.startswith(self.COMMAND_PREFIX):
            return self._handle_internal(text)

        # -- Detectar si el primer token es un comando de skill ---------------
        tokens = text.split()
        command = tokens[0].lower()
        args = tokens[1:]

        registry = self._get_registry()
        skill = registry.find_by_command(command)

        if skill is None:
            _logger.debug(
                f"CommandRouter: ninguna skill maneja '{command}' — pasando a IA."
            )
            return None

        # -- Ejecutar el comando en la skill encontrada -----------------------
        _logger.info(
            f"CommandRouter: comando='{command}' -> skill='{skill.META.name}' args={args}"
        )

        try:
            result = registry.execute(skill.META.name, command, args)
            return RouteResult(
                handled=True,
                success=result.success,
                output=result.output,
                error=result.error,
                skill_name=skill.META.name,
                command=command,
                args=args,
            )
        except Exception as e:
            _logger.error(
                f"CommandRouter: excepcion ejecutando '{command}': {e}",
                exc_info=True,
            )
            return RouteResult(
                handled=True,
                success=False,
                output="",
                error=f"Error inesperado ejecutando '{command}': {e}",
                skill_name=skill.META.name,
                command=command,
                args=args,
            )

    def is_command(self, text: str) -> bool:
        """
        Verifica si el texto seria manejado por el router (sin ejecutarlo).

        Args:
            text: Texto a verificar.

        Returns:
            True si el router manejaria este texto.
        """
        if not text or not text.strip():
            return False

        text = text.strip()

        # Comandos internos
        if text.startswith(self.COMMAND_PREFIX):
            return True

        # Verificar si alguna skill maneja el primer token
        tokens = text.split()
        if not tokens:
            return False

        command = tokens[0].lower()
        registry = self._get_registry()
        return registry.find_by_command(command) is not None

    def list_all_commands(self) -> list:
        """
        Lista todos los comandos disponibles agrupados por skill.

        Returns:
            Lista de dicts con keys: skill_name, display_name, commands, enabled.
        """
        registry = self._get_registry()
        result = []

        for entry in registry.list_all():
            result.append({
                "skill_name": entry.skill.META.name,
                "display_name": entry.skill.META.display_name,
                "commands": list(entry.skill.META.commands),
                "enabled": entry.enabled,
                "category": entry.skill.META.category,
            })

        return result

    # -- Comandos internos ----------------------------------------------------

    def _handle_internal(self, text: str) -> RouteResult:
        """
        Procesa comandos internos del router (prefijo /).

        Args:
            text: Texto completo incluyendo el prefijo '/'.

        Returns:
            RouteResult con handled=True siempre.
        """
        # Separar comando interno de sus args
        parts = text[len(self.COMMAND_PREFIX):].split()
        if not parts:
            return self._result_unknown_internal(text)

        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("ayuda", "help"):
            return self._cmd_ayuda(args)
        elif cmd in ("skills", "comandos"):
            return self._cmd_skills(args)
        else:
            return self._result_unknown_internal(text)

    def _cmd_ayuda(self, args: list) -> RouteResult:
        """Muestra la ayuda general del sistema de comandos."""
        registry = self._get_registry()
        total = len(registry)
        habilitadas = len(registry.list_enabled())

        lines = [
            "Comandos de AURA",
            "",
            "Escribe directamente el nombre de un comando para ejecutarlo.",
            "Por ejemplo:",
            "  hola              -> Saludo de la DemoSkill",
            "  eco Hola Mundo    -> Repite 'Hola Mundo'",
            "  demo              -> Bienvenida del sistema de skills",
            "",
            "Comandos del router:",
            "  /ayuda            -> Esta ayuda",
            "  /skills           -> Lista todas las skills y sus comandos",
            "  /comandos         -> Alias de /skills",
            "",
            f"Skills activas: {habilitadas}/{total}",
            "Todo lo demas se envia a la IA (Ollama / MockProvider).",
        ]

        return RouteResult(
            handled=True,
            success=True,
            output="\n".join(lines),
            skill_name="router",
            command="ayuda",
            args=args,
        )

    def _cmd_skills(self, args: list) -> RouteResult:
        """Lista todas las skills registradas con sus comandos."""
        registry = self._get_registry()
        entries = registry.list_all()

        if not entries:
            return RouteResult(
                handled=True,
                success=True,
                output="No hay skills registradas actualmente.",
                skill_name="router",
                command="skills",
                args=args,
            )

        lines = ["Skills registradas:"]

        for entry in entries:
            estado = "[OK]" if entry.enabled else "[OFF]"
            cmds = ", ".join(entry.skill.META.commands) if entry.skill.META.commands else "(sin comandos)"
            lines.append(
                f"  {estado} {entry.skill.META.display_name} "
                f"(v{entry.skill.META.version})"
            )
            lines.append(f"     Comandos: {cmds}")

        lines.append("")
        lines.append("Escribe cualquier comando directamente para ejecutarlo.")

        return RouteResult(
            handled=True,
            success=True,
            output="\n".join(lines),
            skill_name="router",
            command="skills",
            args=args,
        )

    def _result_unknown_internal(self, text: str) -> RouteResult:
        """Resultado para comandos internos desconocidos."""
        return RouteResult(
            handled=True,
            success=False,
            output="",
            error=(
                f"Comando desconocido: '{text}'\n"
                "Escribe /ayuda para ver los comandos disponibles."
            ),
            skill_name="router",
            command=text,
            args=[],
        )


# -- Instancia global (singleton) -------------------------------------------

command_router = CommandRouter()

"""
AURA — DemoSkill: Skill de demostración del sistema (Fase 11)

Demuestra el funcionamiento del sistema de skills mediante comandos
simples sin efectos secundarios:

  demo hola [nombre]    → Saludo personalizado
  demo eco <texto...>   → Repite el texto recibido
  demo info             → Muestra información del sistema de skills
  demo version          → Muestra la versión de la skill
  demo lista            → Lista todas las skills registradas
  demo ayuda            → Muestra los comandos disponibles

Esta skill sirve como:
  1. Referencia de implementación para nuevas skills
  2. Verificación de que el sistema de registro funciona
  3. Herramienta de depuración básica
"""

from __future__ import annotations

from skills.skill_base import BaseSkill, SkillMeta, SkillResult, CATEGORY_DEMO

# ── Metadatos de la skill ──────────────────────────────────────────────────

_META = SkillMeta(
    name="demo_skill",
    version="1.0.0",
    display_name="Demo",
    description=(
        "Skill de demostración del sistema. "
        "Verifica que el registro y ejecución de skills funciona correctamente."
    ),
    author="AURA",
    category=CATEGORY_DEMO,
    commands=["demo", "hola", "eco", "info", "version", "lista", "ayuda"],
    builtin=True,
    enabled_by_default=True,
)


# ── Implementación de la skill ─────────────────────────────────────────────

class DemoSkill(BaseSkill):
    """
    Skill de demostración del sistema de skills de AURA.

    Implementa 7 comandos simples sin efectos secundarios que sirven
    para verificar el correcto funcionamiento del sistema de skills.
    """

    META = _META

    # ── Ejecución principal ────────────────────────────────────────────────

    def execute(self, command: str, args: list[str]) -> SkillResult:
        """
        Despacha el comando al método correspondiente.

        Args:
            command: Uno de los comandos definidos en META.commands.
            args:    Argumentos adicionales del comando.

        Returns:
            SkillResult con el resultado del comando.
        """
        self._logger.debug(f"DemoSkill.execute: command='{command}' args={args}")

        dispatch = {
            "demo":    self._cmd_demo,
            "hola":    self._cmd_hola,
            "eco":     self._cmd_eco,
            "info":    self._cmd_info,
            "version": self._cmd_version,
            "lista":   self._cmd_lista,
            "ayuda":   self._cmd_ayuda,
        }

        handler = dispatch.get(command)
        if handler is None:
            return SkillResult(
                success=False,
                error=f"Comando desconocido: '{command}'. Usá 'ayuda' para ver los disponibles.",
            )

        return handler(args)

    # ── Comandos individuales ──────────────────────────────────────────────

    def _cmd_demo(self, args: list[str]) -> SkillResult:
        """Comando raíz — muestra bienvenida al sistema de skills."""
        return SkillResult(
            success=True,
            output=(
                "⚡ Sistema de Skills de AURA activo.\n"
                "Comandos disponibles: demo, hola, eco, info, version, lista, ayuda\n"
                "Escribí 'ayuda' para más información."
            ),
        )

    def _cmd_hola(self, args: list[str]) -> SkillResult:
        """Saluda al usuario, con nombre personalizado si se provee."""
        if args:
            nombre = " ".join(args).strip()
            saludo = f"¡Hola, {nombre}! 👋 Soy AURA, tu asistente personal."
        else:
            saludo = "¡Hola! 👋 Soy AURA, tu asistente personal. ¿En qué puedo ayudarte?"
        return SkillResult(success=True, output=saludo)

    def _cmd_eco(self, args: list[str]) -> SkillResult:
        """Repite el texto recibido como argumentos."""
        if not args:
            return SkillResult(
                success=False,
                error="El comando 'eco' requiere al menos un argumento. Ej: eco Hola Mundo",
            )
        texto = " ".join(args)
        return SkillResult(
            success=True,
            output=texto,
            data={"eco": texto, "words": len(args)},
        )

    def _cmd_info(self, args: list[str]) -> SkillResult:
        """Muestra información sobre el sistema de skills."""
        try:
            from skills.skill_registry import skill_registry
            total = len(skill_registry)
            habilitadas = len(skill_registry.list_enabled())
            deshabilitadas = len(skill_registry.list_disabled())
            info = (
                f"📊 Sistema de Skills de AURA\n"
                f"  Total registradas: {total}\n"
                f"  Habilitadas:       {habilitadas}\n"
                f"  Deshabilitadas:    {deshabilitadas}"
            )
        except Exception as e:
            info = f"Sistema de Skills activo (no se pudo obtener estadísticas: {e})"

        return SkillResult(
            success=True,
            output=info,
            data={"skill_name": self.META.name, "version": self.META.version},
        )

    def _cmd_version(self, args: list[str]) -> SkillResult:
        """Muestra la versión y metadatos de la skill."""
        output = (
            f"⚡ {self.META.display_name}\n"
            f"  Versión:     {self.META.version}\n"
            f"  Categoría:   {self.META.category}\n"
            f"  Autor:       {self.META.author}\n"
            f"  Descripción: {self.META.description}"
        )
        return SkillResult(
            success=True,
            output=output,
            data={
                "name": self.META.name,
                "version": self.META.version,
                "author": self.META.author,
                "category": self.META.category,
            },
        )

    def _cmd_lista(self, args: list[str]) -> SkillResult:
        """Lista todas las skills registradas en el sistema."""
        try:
            from skills.skill_registry import skill_registry
            entries = skill_registry.list_all()
            if not entries:
                return SkillResult(
                    success=True,
                    output="No hay skills registradas actualmente.",
                )
            lines = ["📋 Skills registradas:"]
            for entry in entries:
                estado = "✅" if entry.enabled else "⛔"
                lines.append(
                    f"  {estado} {entry.skill.META.display_name} "
                    f"({entry.skill.META.name}) "
                    f"v{entry.skill.META.version}"
                )
            return SkillResult(success=True, output="\n".join(lines))
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"No se pudo obtener la lista de skills: {e}",
            )

    def _cmd_ayuda(self, args: list[str]) -> SkillResult:
        """Muestra la ayuda de la DemoSkill."""
        ayuda = (
            "⚡ Comandos de la DemoSkill:\n"
            "\n"
            "  demo                → Muestra bienvenida al sistema\n"
            "  hola [nombre]       → Saludo personalizado\n"
            "  eco <texto...>      → Repite el texto recibido\n"
            "  info                → Estadísticas del sistema de skills\n"
            "  version             → Versión y metadatos de esta skill\n"
            "  lista               → Lista todas las skills registradas\n"
            "  ayuda               → Muestra esta ayuda\n"
        )
        return SkillResult(success=True, output=ayuda)

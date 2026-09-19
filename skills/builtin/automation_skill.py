"""
AURA — AutomationSkill: Skill de automatizaciones (Fase 19)

Permite ejecutar automatizaciones YAML/JSON desde el chat de AURA.

Comandos disponibles:
  automatizar <nombre>             → Ejecuta una automatización por nombre
  automatizar <nombre> --simular   → Simula la ejecución (dry-run, sin efectos)
  automatizaciones                 → Lista todas las automatizaciones disponibles
  automatizar-info <nombre>        → Muestra la información de una automatización

Formato de automatización (YAML):
  name: "Mi Automatización"
  description: "Qué hace"
  version: "1.0"
  steps:
    - type: open_app
      app: vscode
    - type: open_url
      url: https://github.com
    - type: delay
      seconds: 1.5
    - type: message
      text: "Completado"

Persistencia:
  Las automatizaciones se guardan en data/automations/*.yaml (o .json).
  AURA incluye algunas de ejemplo (modo_programar, inicio_dia).

Seguridad:
  - El flag --simular ejecuta en modo dry-run sin efectos reales.
  - Delays limitados a 60 segundos por paso.
  - Todas las acciones se registran en el log.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skills.skill_base import (
    BaseSkill,
    SkillMeta,
    SkillResult,
    CATEGORY_AUTOMATION,
)
from utils.logger import get_logger

_logger = get_logger("aura.skills.automation")

# ---------------------------------------------------------------------------
# Metadatos de la skill
# ---------------------------------------------------------------------------

_META = SkillMeta(
    name="automation_skill",
    version="1.0.0",
    display_name="Automatizaciones",
    description=(
        "Ejecuta automatizaciones YAML/JSON: secuencias de pasos "
        "(abrir apps, URLs, delays, mensajes). Incluye simulación dry-run."
    ),
    author="AURA",
    category=CATEGORY_AUTOMATION,
    commands=[
        "automatizar",
        "automatizaciones",
        "automatizar-info",
    ],
    builtin=True,
    enabled_by_default=True,
)


# ---------------------------------------------------------------------------
# AutomationSkill
# ---------------------------------------------------------------------------


class AutomationSkill(BaseSkill):
    """
    Skill que permite ejecutar y consultar automatizaciones YAML/JSON.

    Usa AutomationEngine para cargar y correr las automatizaciones.
    No guarda estado entre comandos (stateless).
    """

    META = _META

    # El motor se importa de forma lazy para no cargar pyyaml hasta que se use
    _engine: Any = None  # AutomationEngine | None

    # ── Ciclo de vida ────────────────────────────────────────────────────────

    def setup(self) -> None:
        """Inicializa el motor de automatizaciones."""
        super().setup()
        from automation.engine import AutomationEngine
        self._engine = AutomationEngine()
        _logger.debug("AutomationSkill inicializada.")

    def teardown(self) -> None:
        """Limpia el motor."""
        super().teardown()
        self._engine = None
        _logger.debug("AutomationSkill detenida.")

    # ── Ejecución de comandos ────────────────────────────────────────────────

    def execute(self, command: str, args: list[str]) -> SkillResult:
        """Despacha el comando al handler correspondiente."""
        cmd = command.lower().strip()

        if cmd == "automatizar":
            return self._cmd_automatizar(args)
        if cmd == "automatizaciones":
            return self._cmd_automatizaciones(args)
        if cmd == "automatizar-info":
            return self._cmd_automatizar_info(args)

        return SkillResult(
            success=False,
            error=(
                f"Comando '{command}' no reconocido.\n"
                f"Comandos disponibles: automatizar, automatizaciones, automatizar-info"
            ),
        )

    # ── Comandos ─────────────────────────────────────────────────────────────

    def _cmd_automatizar(self, args: list[str]) -> SkillResult:
        """
        automatizar <nombre> [--simular]

        Ejecuta la automatización con el nombre dado.
        Con --simular hace un dry-run sin efectos reales.
        """
        if not args:
            ejemplos = self._listar_nombres()
            ejemplos_str = (
                "\n".join(f"   • {n}" for n in ejemplos[:5])
                if ejemplos
                else "   (No hay automatizaciones disponibles aún)"
            )
            return SkillResult(
                success=False,
                error=(
                    "Uso: automatizar <nombre> [--simular]\n"
                    "Ejemplo: automatizar modo_programar\n"
                    "         automatizar inicio_dia --simular\n\n"
                    "Automatizaciones disponibles:\n"
                    f"{ejemplos_str}\n\n"
                    "Usa 'automatizaciones' para ver la lista completa."
                ),
            )

        # Extraer flag --simular
        dry_run = "--simular" in args
        nombre_args = [a for a in args if a != "--simular"]
        nombre = "_".join(nombre_args).strip()

        if not nombre:
            return SkillResult(
                success=False,
                error="Debes indicar el nombre de la automatización.",
            )

        _logger.info(
            "Ejecutando automatización '%s'%s", nombre, " [DRY-RUN]" if dry_run else ""
        )

        result = self._engine.run(nombre, dry_run=dry_run)

        if result.success:
            return SkillResult(
                success=True,
                output=result.output,
                data={
                    "name": result.name,
                    "total_steps": result.total_steps,
                    "completed_steps": result.completed_steps,
                    "dry_run": dry_run,
                },
            )
        else:
            # Si falló por nombre no encontrado, sugerir alternativas
            if result.total_steps == 0 and result.error and "no encontrada" in result.error:
                sugerencias = self._sugerir_nombres(nombre)
                extra = ""
                if sugerencias:
                    extra = "\n\nQuizás quisiste decir:\n" + "\n".join(
                        f"   • {s}" for s in sugerencias
                    )
                return SkillResult(
                    success=False,
                    error=result.error + extra,
                )
            return SkillResult(
                success=result.success,
                output=result.output if result.output else None,
                error=result.error if result.error else None,
                data={
                    "name": result.name,
                    "total_steps": result.total_steps,
                    "completed_steps": result.completed_steps,
                    "failed_steps": result.failed_steps,
                },
            )

    def _cmd_automatizaciones(self, args: list[str]) -> SkillResult:
        """
        automatizaciones

        Lista todas las automatizaciones disponibles en data/automations/.
        """
        automations = self._engine.list_automations()

        if not automations:
            return SkillResult(
                success=True,
                output=(
                    "📂 No hay automatizaciones disponibles.\n\n"
                    "Para crear una, guardá un archivo .yaml en:\n"
                    "   data/automations/mi_automatizacion.yaml\n\n"
                    "Ejemplo de formato:\n"
                    "  name: \"Mi Automatización\"\n"
                    "  steps:\n"
                    "    - type: open_app\n"
                    "      app: notepad\n"
                    "    - type: message\n"
                    "      text: \"¡Listo!\""
                ),
                data={"total": 0, "automations": []},
            )

        lines = [f"📋 Automatizaciones disponibles ({len(automations)}):"]
        lines.append("")

        for info in automations:
            lines.append(f"  🔧 {info.display_name}")
            lines.append(f"     Nombre: {info.name}  |  Pasos: {info.step_count}  |  Formato: {info.format.upper()}")
            if info.description:
                lines.append(f"     {info.description}")
            lines.append("")

        lines.append("Para ejecutar: automatizar <nombre>")
        lines.append("Para simular:  automatizar <nombre> --simular")
        lines.append("Para detalle:  automatizar-info <nombre>")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            data={
                "total": len(automations),
                "automations": [
                    {
                        "name": a.name,
                        "display_name": a.display_name,
                        "step_count": a.step_count,
                        "format": a.format,
                    }
                    for a in automations
                ],
            },
        )

    def _cmd_automatizar_info(self, args: list[str]) -> SkillResult:
        """
        automatizar-info <nombre>

        Muestra la información detallada de una automatización.
        """
        if not args:
            return SkillResult(
                success=False,
                error=(
                    "Uso: automatizar-info <nombre>\n"
                    "Ejemplo: automatizar-info modo_programar\n"
                    "Usa 'automatizaciones' para ver la lista completa."
                ),
            )

        nombre = "_".join(args).strip()
        info = self._engine.get_info(nombre)

        if info is None:
            sugerencias = self._sugerir_nombres(nombre)
            extra = ""
            if sugerencias:
                extra = "\n\nQuizás quisiste decir:\n" + "\n".join(
                    f"   • {s}" for s in sugerencias
                )
            return SkillResult(
                success=False,
                error=f"No se encontró la automatización '{nombre}'.{extra}",
            )

        lines = [
            f"📄 Información: {info.display_name}",
            "",
            f"  Nombre:      {info.name}",
            f"  Versión:     {info.version}",
            f"  Pasos:       {info.step_count}",
            f"  Formato:     {info.format.upper()}",
            f"  Archivo:     {info.filename}",
        ]
        if info.description:
            lines.append(f"  Descripción: {info.description}")

        lines.append("")
        lines.append(f"Para ejecutar: automatizar {info.name}")
        lines.append(f"Para simular:  automatizar {info.name} --simular")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            data={
                "name": info.name,
                "display_name": info.display_name,
                "version": info.version,
                "step_count": info.step_count,
                "format": info.format,
                "filename": info.filename,
                "description": info.description,
            },
        )

    # ── Helpers internos ─────────────────────────────────────────────────────

    def _listar_nombres(self) -> list[str]:
        """Retorna los nombres de todas las automatizaciones disponibles."""
        try:
            return [a.name for a in self._engine.list_automations()]
        except Exception:
            return []

    def _sugerir_nombres(self, nombre: str) -> list[str]:
        """Sugiere automatizaciones cuyos nombres contienen el prefijo dado."""
        nombre_lower = nombre.lower().replace("-", "_")
        sugerencias = []
        for n in self._listar_nombres():
            if nombre_lower in n.lower() or n.lower().startswith(nombre_lower[:3]):
                sugerencias.append(n)
        return sugerencias[:5]

"""
AURA — ProgramsSkill: Skill de programas favoritos (Fase 17)

Permite gestionar una lista personalizada de alias para programas y rutas
favoritas del usuario, y abrirlos rápidamente desde el chat de AURA.

Comandos disponibles:
  programa <alias>              → Abre el programa registrado bajo ese alias
  programas                     → Lista todos los alias registrados
  agregar-programa <alias> <ruta> → Registra un nuevo alias (persistente)
  quitar-programa <alias>       → Elimina el alias registrado
  programa-info <alias>         → Muestra la ruta y estado del programa

Alias predefinidos:
  Los alias predefinidos (builtin) se incluyen de fábrica y no se pueden
  eliminar, pero pueden ser sobreescritos por alias del usuario.

Persistencia:
  Los alias del usuario se guardan en data/programs.json y se cargan
  automáticamente al iniciar la skill.

Seguridad:
  - Todas las aperturas se registran en el log.
  - Solo se ejecutan rutas de ejecutables, no comandos shell arbitrarios.
  - La ruta se valida antes de intentar abrirla.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

from skills.skill_base import (
    BaseSkill,
    SkillMeta,
    SkillResult,
    CATEGORY_PROGRAMS,
)
from utils.logger import get_logger

_logger = get_logger("aura.skills.programs")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_IS_WINDOWS = platform.system() == "Windows"

# Ruta donde se persisten los alias del usuario
_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_PROGRAMS_FILE = _DATA_DIR / "programs.json"

# Alias predefinidos (builtin) — el usuario no puede eliminarlos,
# pero sí sobreescribirlos con alias propios.
_BUILTIN_ALIASES: dict[str, str] = {
    # Accesorios Windows
    "notepad":        "notepad.exe",
    "bloc":           "notepad.exe",
    "calculadora":    "calc.exe",
    "calc":           "calc.exe",
    "explorador":     "explorer.exe",
    "explorer":       "explorer.exe",
    "paint":          "mspaint.exe",
    "cmd":            "cmd.exe",
    "consola":        "cmd.exe",
    "terminal":       "cmd.exe",
    "powershell":     "powershell.exe",
    "wordpad":        "wordpad.exe",
    "recortes":       "snippingtool.exe",
    # Navegadores
    "chrome":         "chrome.exe",
    "firefox":        "firefox.exe",
    "edge":           "msedge.exe",
    # Office
    "word":           "winword.exe",
    "excel":          "excel.exe",
    "powerpoint":     "powerpnt.exe",
    # Herramientas dev
    "vscode":         "code.exe",
    "code":           "code.exe",
    # Multimedia
    "vlc":            "vlc.exe",
    "spotify":        "Spotify.exe",
    # Comunicación
    "discord":        "Discord.exe",
    "teams":          "Teams.exe",
    "zoom":           "Zoom.exe",
    # Configuración Windows
    "configuracion":  "ms-settings:",
    "settings":       "ms-settings:",
}


# ---------------------------------------------------------------------------
# Metadatos de la skill
# ---------------------------------------------------------------------------

_META = SkillMeta(
    name="programs_skill",
    version="1.0.0",
    display_name="Programas",
    description=(
        "Gestión de alias de programas favoritos. "
        "Abre programas por alias, agrega rutas personalizadas y lista los favoritos."
    ),
    author="AURA",
    category=CATEGORY_PROGRAMS,
    commands=[
        "programa",
        "programas",
        "agregar-programa",
        "quitar-programa",
        "programa-info",
    ],
    builtin=True,
    enabled_by_default=True,
)


# ---------------------------------------------------------------------------
# Implementación
# ---------------------------------------------------------------------------

class ProgramsSkill(BaseSkill):
    """
    Skill de programas favoritos para AURA.

    Permite registrar alias personalizados para ejecutables y rutas,
    listarlos y abrirlos rápidamente desde el chat.
    """

    META = _META

    # ── Ciclo de vida ──────────────────────────────────────────────────────

    def __init__(self) -> None:
        super().__init__()
        self._user_aliases: dict[str, str] = {}

    def setup(self) -> None:
        """Carga los alias del usuario desde disco."""
        super().setup()
        self._user_aliases = {}
        self._load_user_aliases()
        _logger.debug(
            "ProgramsSkill inicializada con %d alias del usuario.",
            len(self._user_aliases),
        )

    def teardown(self) -> None:
        """Persiste los alias antes de cerrar."""
        self._save_user_aliases()
        super().teardown()

    # ── Ejecución ──────────────────────────────────────────────────────────

    def execute(self, command: str, args: list[str]) -> SkillResult:
        """Despacha el comando al método correspondiente."""
        cmd = command.lower().strip()

        if cmd == "programa":
            return self._cmd_abrir(args)
        if cmd == "programas":
            return self._cmd_listar(args)
        if cmd == "agregar-programa":
            return self._cmd_agregar(args)
        if cmd == "quitar-programa":
            return self._cmd_quitar(args)
        if cmd == "programa-info":
            return self._cmd_info(args)

        return SkillResult(
            success=False,
            error=f"Comando desconocido: '{command}'.",
        )

    # ── Comandos ───────────────────────────────────────────────────────────

    def _cmd_abrir(self, args: list[str]) -> SkillResult:
        """
        programa <alias>

        Abre el programa registrado bajo el alias dado.
        Primero busca en alias del usuario, luego en builtin.
        """
        if not args:
            return SkillResult(
                success=False,
                error=(
                    "Uso: programa <alias>\n"
                    "Ejemplo: programa vscode\n"
                    "         programa notepad\n"
                    "Usa 'programas' para ver la lista completa."
                ),
            )

        if isinstance(args, list):
            target = " ".join(str(a) for a in args).strip()
        else:
            target = str(args).strip()

        alias = target.lower()

        # Recargar alias del usuario si no está en memoria para sincronización en caliente
        if alias not in self._user_aliases:
            self._load_user_aliases()

        ruta = self._resolver_alias(alias)

        # Si coincide directamente con una ruta en disco
        if ruta is None and (os.path.exists(target) or os.path.isabs(target)):
            if os.path.exists(target):
                ruta = target

        # Delegar en el resolver unificado (Fase 54)
        if ruta is None:
            try:
                from core.app_scanner import fast_resolve_app
                fast_path = fast_resolve_app(target)
                if fast_path and os.path.exists(fast_path):
                    ruta = fast_path
                    self._user_aliases[alias] = fast_path
            except Exception as exc:
                _logger.debug("ProgramsSkill: error en fast_resolve_app: %s", exc)

        if ruta is None:
            try:
                from core.app_resolver import resolve_app
                app_res = resolve_app(target)
                if app_res.success and app_res.executable and os.path.exists(app_res.executable):
                    ruta = app_res.executable
                    self._user_aliases[alias] = ruta
            except Exception as exc:
                _logger.debug("ProgramsSkill: error en resolve_app: %s", exc)

        if ruta is None:
            sugerencias = self._sugerir_alias(target)
            msg = f"No encontré '{target}' en el sistema."
            if sugerencias:
                msg += f"\n¿Quisiste decir: {', '.join(sugerencias)}?"
            msg += f"\nPodés registrar la ruta manualmente con: agregar-programa {target} <ruta>"
            return SkillResult(success=False, error=msg)

        return self._abrir_programa(target, ruta)

    def _cmd_listar(self, args: list[str]) -> SkillResult:
        """
        programas

        Lista todos los alias registrados (builtin + usuario).
        """
        todos = self._todos_los_alias()

        if not todos:
            return SkillResult(
                success=True,
                output="No hay programas registrados.",
            )

        # Separar en dos grupos
        user_aliases = {k: v for k, v in todos.items() if k in self._user_aliases}
        builtin_aliases = {
            k: v for k, v in todos.items() if k not in self._user_aliases
        }

        lineas: list[str] = []

        if user_aliases:
            lineas.append("📌 Alias del usuario:")
            for alias, ruta in sorted(user_aliases.items()):
                estado = self._estado_icono(ruta)
                lineas.append(f"  {estado} {alias:<20} → {ruta}")
            lineas.append("")

        if builtin_aliases:
            lineas.append("🔧 Alias predefinidos:")
            for alias, ruta in sorted(builtin_aliases.items()):
                estado = self._estado_icono(ruta)
                lineas.append(f"  {estado} {alias:<20} → {ruta}")

        total = len(todos)
        lineas.append(f"\nTotal: {total} alias  |  ✅ = encontrado en PATH  ❓ = desconocido")
        lineas.append("Para agregar: agregar-programa <alias> <ruta>")

        return SkillResult(
            success=True,
            output="\n".join(lineas),
            data={"total": total, "aliases": todos},
        )

    def _cmd_agregar(self, args: list[str]) -> SkillResult:
        """
        agregar-programa <alias> <ruta>

        Registra un nuevo alias. La ruta puede ser un ejecutable,
        una ruta absoluta o un protocolo (ms-settings:, etc.).
        """
        if len(args) < 2:
            return SkillResult(
                success=False,
                error=(
                    "Uso: agregar-programa <alias> <ruta>\n"
                    "Ejemplo: agregar-programa mi-editor C:\\Apps\\editor.exe\n"
                    "         agregar-programa proyecto C:\\Users\\yo\\proyecto\\"
                ),
            )

        alias = args[0].strip().lower()
        ruta = " ".join(args[1:]).strip()

        # Validar alias
        if not alias or " " in alias:
            return SkillResult(
                success=False,
                error=(
                    f"El alias '{alias}' no es válido. "
                    "Los alias no pueden contener espacios."
                ),
            )

        # Normalizar ruta: expandir ~ y variables de entorno
        ruta_norm = os.path.expandvars(os.path.expanduser(ruta))

        # Guardar alias del usuario (sobreescribe builtin si existe)
        alias_existia = alias in self._user_aliases
        self._user_aliases[alias] = ruta_norm
        self._save_user_aliases()

        accion = "actualizado" if alias_existia else "agregado"
        _logger.info("Alias '%s' %s → '%s'", alias, accion, ruta_norm)

        return SkillResult(
            success=True,
            output=(
                f"✅ Alias '{alias}' {accion} correctamente.\n"
                f"   Ruta: {ruta_norm}\n"
                f"Para abrir: programa {alias}"
            ),
            data={"alias": alias, "ruta": ruta_norm, "action": accion},
        )

    def _cmd_quitar(self, args: list[str]) -> SkillResult:
        """
        quitar-programa <alias>

        Elimina un alias del usuario. No se pueden eliminar alias builtin.
        """
        if not args:
            return SkillResult(
                success=False,
                error=(
                    "Uso: quitar-programa <alias>\n"
                    "Ejemplo: quitar-programa mi-editor\n"
                    "Nota: Solo se pueden quitar alias agregados por el usuario."
                ),
            )

        alias = args[0].strip().lower()

        if alias not in self._user_aliases:
            if alias in _BUILTIN_ALIASES:
                return SkillResult(
                    success=False,
                    error=(
                        f"'{alias}' es un alias predefinido de AURA y no se puede eliminar.\n"
                        "Solo se pueden quitar alias que hayas agregado con 'agregar-programa'."
                    ),
                )
            return SkillResult(
                success=False,
                error=(
                    f"No se encontró el alias de usuario '{alias}'.\n"
                    "Usa 'programas' para ver los alias que puedes eliminar."
                ),
            )

        ruta_eliminada = self._user_aliases.pop(alias)
        self._save_user_aliases()
        _logger.info("Alias del usuario '%s' eliminado (era → '%s')", alias, ruta_eliminada)

        return SkillResult(
            success=True,
            output=(
                f"🗑️ Alias '{alias}' eliminado correctamente.\n"
                f"   (Era: {ruta_eliminada})"
            ),
            data={"alias": alias, "ruta_eliminada": ruta_eliminada},
        )

    def _cmd_info(self, args: list[str]) -> SkillResult:
        """
        programa-info <alias>

        Muestra la ruta, tipo y estado del programa registrado bajo el alias.
        """
        if not args:
            return SkillResult(
                success=False,
                error=(
                    "Uso: programa-info <alias>\n"
                    "Ejemplo: programa-info vscode"
                ),
            )

        if isinstance(args, list):
            alias = " ".join(str(a) for a in args).strip().lower()
        else:
            alias = str(args or "").strip().lower()

        if alias not in self._user_aliases:
            self._load_user_aliases()
        ruta = self._resolver_alias(alias)

        if ruta is None:
            try:
                from core.app_scanner import fast_resolve_app
                fast_p = fast_resolve_app(alias)
                if fast_p and os.path.exists(fast_p):
                    ruta = fast_p
            except Exception:
                pass

        if ruta is None:
            return SkillResult(
                success=False,
                error=(
                    f"No se encontró el alias '{alias}'.\n"
                    "Usa 'programas' para ver la lista completa."
                ),
            )

        es_usuario = alias in self._user_aliases
        tipo = "Usuario" if es_usuario else "Predefinido"

        # Detectar tipo de ruta
        if ruta.endswith((":", "/")):
            tipo_ruta = "Protocolo del sistema"
            existe = True  # No se puede verificar
        else:
            ruta_path = Path(ruta)
            if ruta_path.is_absolute():
                existe = ruta_path.exists()
                tipo_ruta = "Archivo ejecutable (ruta absoluta)"
            else:
                # Buscar en PATH
                existe = self._esta_en_path(ruta)
                tipo_ruta = "Ejecutable en PATH"

        estado_str = "✅ Encontrado" if existe else "❓ No encontrado en el sistema"

        lineas = [
            f"📋 Información del alias '{alias}':",
            f"   Tipo:   {tipo}",
            f"   Ruta:   {ruta}",
            f"   Clase:  {tipo_ruta}",
            f"   Estado: {estado_str}",
        ]

        if not existe:
            lineas.append(
                "\n⚠️  El programa no se encontró. "
                "Puede que no esté instalado o la ruta sea incorrecta."
            )

        return SkillResult(
            success=True,
            output="\n".join(lineas),
            data={
                "alias": alias,
                "ruta": ruta,
                "tipo": tipo,
                "existe": existe,
            },
        )

    # ── Helpers internos ───────────────────────────────────────────────────

    def _abrir_programa(self, alias: str, ruta: str) -> SkillResult:
        """Intenta abrir el programa en la ruta dada."""
        _logger.info("Abriendo programa '%s' → '%s'", alias, ruta)

        try:
            if _IS_WINDOWS:
                os.startfile(ruta)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(
                    ["xdg-open", ruta],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            try:
                from core.user_memory import user_memory
                user_memory.record_program(alias, executable_path=ruta)
            except Exception as _mem_err:
                _logger.debug("ProgramsSkill: no se pudo registrar en memoria: %s", _mem_err)

            return SkillResult(
                success=True,
                output=f"✅ Abriendo '{alias}'...\n   ({ruta})",
                data={"alias": alias, "ruta": ruta},
            )

        except FileNotFoundError:
            _logger.warning("Programa no encontrado: '%s' → '%s'", alias, ruta)
            return SkillResult(
                success=False,
                error=(
                    f"No se encontró el programa '{alias}'.\n"
                    f"   Ruta: {ruta}\n"
                    "El programa puede no estar instalado. "
                    "Usa 'agregar-programa' para actualizar la ruta."
                ),
            )
        except OSError as exc:
            _logger.error(
                "Error al abrir '%s' → '%s': %s", alias, ruta, exc
            )
            return SkillResult(
                success=False,
                error=(
                    f"Error al abrir '{alias}': {exc}\n"
                    "Verifica que la ruta sea correcta con 'programa-info'."
                ),
            )
        except Exception as exc:  # pylint: disable=broad-except
            _logger.exception(
                "Error inesperado al abrir '%s'", alias
            )
            return SkillResult(
                success=False,
                error=f"Error inesperado al abrir '{alias}': {exc}",
            )

    def _resolver_alias(self, alias: str) -> str | None:
        """
        Devuelve la ruta del alias o None si no existe.
        Prioridad: alias del usuario > alias builtin.
        """
        alias_lower = alias.lower()
        if alias_lower in self._user_aliases:
            return self._user_aliases[alias_lower]
        if alias_lower in _BUILTIN_ALIASES:
            return _BUILTIN_ALIASES[alias_lower]
        return None

    def _todos_los_alias(self) -> dict[str, str]:
        """
        Retorna todos los alias combinados.
        Los alias del usuario sobreescriben los builtin.
        """
        combined = dict(_BUILTIN_ALIASES)
        combined.update(self._user_aliases)
        return combined

    def _sugerir_alias(self, alias: str, max_sugerencias: int = 3) -> list[str]:
        """
        Sugiere alias o aplicaciones similares usando difflib
        sobre el índice de aplicaciones conocidas y favoritos reales,
        NUNCA una lista hardcodeada fija de herramientas del sistema.
        """
        import difflib

        self._load_user_aliases()
        known_apps: set[str] = set(self._user_aliases.keys())

        try:
            from core.app_scanner import app_index_manager
            cached_index = app_index_manager.load_index()
            for key, val in cached_index.items():
                known_apps.add(key.lower())
                if isinstance(val, dict):
                    disp = val.get("display_name")
                    if disp:
                        known_apps.add(disp.lower())
        except Exception:
            pass

        # Agregar alias predefinidos
        known_apps.update(_BUILTIN_ALIASES.keys())

        alias_clean = alias.strip().lower()
        candidates = [k for k in known_apps if k != alias_clean and len(k) > 1]

        matches = difflib.get_close_matches(alias_clean, candidates, n=max_sugerencias, cutoff=0.5)
        if not matches:
            matches = [k for k in candidates if alias_clean in k or k in alias_clean][:max_sugerencias]

        return matches

    def _estado_icono(self, ruta: str) -> str:
        """Retorna ✅ si el ejecutable parece disponible, ❓ si no."""
        if ruta.endswith((":", "/", "\\")):
            return "✅"  # Protocolo del sistema
        ruta_path = Path(ruta)
        if ruta_path.is_absolute():
            return "✅" if ruta_path.exists() else "❓"
        return "✅" if self._esta_en_path(ruta) else "❓"

    def _esta_en_path(self, ejecutable: str) -> bool:
        """
        Verifica si un ejecutable existe en el PATH del sistema.
        Compatible con Windows y otros SO.
        """
        import shutil
        return shutil.which(ejecutable) is not None

    # ── Persistencia ───────────────────────────────────────────────────────

    def _load_user_aliases(self) -> None:
        """Carga los alias del usuario desde data/programs.json."""
        if not _PROGRAMS_FILE.exists():
            self._user_aliases = {}
            return
        try:
            with open(_PROGRAMS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._user_aliases = {
                    k.lower(): v
                    for k, v in data.items()
                    if isinstance(k, str) and isinstance(v, str)
                }
            else:
                self._user_aliases = {}
            _logger.debug(
                "Cargados %d alias del usuario desde '%s'.",
                len(self._user_aliases),
                _PROGRAMS_FILE,
            )
        except (json.JSONDecodeError, OSError) as exc:
            _logger.warning(
                "No se pudo cargar '%s': %s. Usando alias vacíos.",
                _PROGRAMS_FILE,
                exc,
            )
            self._user_aliases = {}

    def _save_user_aliases(self) -> None:
        """Persiste los alias del usuario en data/programs.json."""
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = _PROGRAMS_FILE.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._user_aliases, f, ensure_ascii=False, indent=2)
            tmp.replace(_PROGRAMS_FILE)
            _logger.debug(
                "Guardados %d alias del usuario en '%s'.",
                len(self._user_aliases),
                _PROGRAMS_FILE,
            )
        except OSError as exc:
            _logger.error(
                "No se pudo guardar '%s': %s", _PROGRAMS_FILE, exc
            )

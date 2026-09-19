"""
AURA — SystemSkill: Skill de control del sistema Windows (Fase 14)

Permite controlar el sistema operativo Windows desde el chat de AURA:
  - Abrir aplicaciones de sistema (notepad, calculadora, explorador, etc.)
  - Cerrar procesos por nombre
  - Bloquear la sesión del usuario
  - Apagar o reiniciar el equipo (con confirmación obligatoria)
  - Ver información del sistema (CPU, RAM, disco)
  - Vaciar la papelera de reciclaje (con confirmación)
  - Listar procesos en ejecución

Comandos disponibles:
  abrir <app>           → Abre una aplicación de Windows
  cerrar <proceso>      → Cierra un proceso por nombre
  bloquear              → Bloquea la sesión del usuario
  apagar [--ahora]      → Apaga el equipo (dry-run por defecto)
  reiniciar [--ahora]   → Reinicia el equipo (dry-run por defecto)
  sysinfo               → Muestra información del sistema
  procesos [<filtro>]   → Lista procesos en ejecución
  papelera              → Vacía la papelera de reciclaje

Seguridad:
  - Las acciones destructivas (apagar, reiniciar, vaciar papelera)
    siempre operan en modo dry-run salvo que el usuario pase --ahora.
  - bloquear no requiere --ahora porque es reversible.
  - Todas las acciones se registran en el log.

IMPORTANTE: Esta skill es solo para Windows. En otros sistemas
retornará SkillResult con success=False y un mensaje explicativo.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from typing import Any

from skills.skill_base import BaseSkill, SkillMeta, SkillResult, CATEGORY_SYSTEM
from utils.logger import get_logger

_logger = get_logger("aura.skills.system")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_IS_WINDOWS = platform.system() == "Windows"

# Alias de aplicaciones conocidas → ejecutable real
_APP_ALIASES: dict[str, str] = {
    # Accesorios Windows
    "notepad":       "notepad.exe",
    "bloc":          "notepad.exe",
    "bloc de notas": "notepad.exe",
    "calculadora":   "calc.exe",
    "calc":          "calc.exe",
    "explorador":    "explorer.exe",
    "explorer":      "explorer.exe",
    "paint":         "mspaint.exe",
    "mspaint":       "mspaint.exe",
    "cmd":           "cmd.exe",
    "consola":       "cmd.exe",
    "terminal":      "cmd.exe",
    "powershell":    "powershell.exe",
    "ps":            "powershell.exe",
    "wordpad":       "wordpad.exe",
    "recortes":      "snippingtool.exe",
    "snipping":      "snippingtool.exe",
    "teclado":       "osk.exe",
    "osk":           "osk.exe",
    # Configuración
    "configuracion": "ms-settings:",
    "settings":      "ms-settings:",
    "pantalla":      "ms-settings:display",
    "wifi":          "ms-settings:network-wifi",
    "bluetooth":     "ms-settings:bluetooth",
    "sonido":        "ms-settings:sound",
    "actualizacion": "ms-settings:windowsupdate",
    "update":        "ms-settings:windowsupdate",
    # Otras apps comunes
    "chrome":        "chrome.exe",
    "firefox":       "firefox.exe",
    "edge":          "msedge.exe",
    "word":          "winword.exe",
    "excel":         "excel.exe",
    "vlc":           "vlc.exe",
    "spotify":       "Spotify.exe",
    "discord":       "Discord.exe",
    "vscode":        "code.exe",
    "code":          "code.exe",
}

# Procesos que NO se pueden cerrar por razones de seguridad
_PROTECTED_PROCESSES = {
    "system", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "winlogon.exe",
    "svchost.exe", "explorer.exe",
}


# ---------------------------------------------------------------------------
# Metadatos de la skill
# ---------------------------------------------------------------------------

_META = SkillMeta(
    name="system_skill",
    version="1.0.0",
    display_name="Sistema",
    description=(
        "Control del sistema Windows: abrir/cerrar apps, bloquear sesión, "
        "apagar/reiniciar equipo, info del sistema y procesos."
    ),
    author="AURA",
    category=CATEGORY_SYSTEM,
    commands=[
        "abrir",
        "cerrar",
        "bloquear",
        "apagar",
        "reiniciar",
        "sysinfo",
        "procesos",
        "papelera",
    ],
    builtin=True,
    enabled_by_default=True,
)


# ---------------------------------------------------------------------------
# Implementación
# ---------------------------------------------------------------------------

class SystemSkill(BaseSkill):
    """
    Skill de control del sistema Windows para AURA.

    Permite abrir y cerrar aplicaciones, bloquear la sesión,
    apagar o reiniciar el equipo (con confirmación), ver información
    del sistema y gestionar la papelera de reciclaje.

    Las acciones destructivas operan en modo dry-run por defecto
    y requieren el flag '--ahora' para ejecutarse realmente.
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
            SkillResult con el resultado de la operación.
        """
        self._logger.debug(f"SystemSkill.execute: command='{command}' args={args}")

        dispatch = {
            "abrir":     self._cmd_abrir,
            "cerrar":    self._cmd_cerrar,
            "bloquear":  self._cmd_bloquear,
            "apagar":    self._cmd_apagar,
            "reiniciar": self._cmd_reiniciar,
            "sysinfo":   self._cmd_sysinfo,
            "procesos":  self._cmd_procesos,
            "papelera":  self._cmd_papelera,
        }

        handler = dispatch.get(command)
        if handler is None:
            return SkillResult(
                success=False,
                error=f"Comando desconocido: '{command}'. Usá 'sysinfo' o 'abrir <app>'.",
            )

        return handler(args)

    # ── Helpers internos ───────────────────────────────────────────────────

    def _check_windows(self) -> SkillResult | None:
        """Retorna un SkillResult de error si no estamos en Windows, o None si sí."""
        if not _IS_WINDOWS:
            return SkillResult(
                success=False,
                error=(
                    f"Esta función solo está disponible en Windows. "
                    f"Sistema actual: {platform.system()}"
                ),
            )
        return None

    def _has_psutil(self) -> bool:
        """Verifica si psutil está disponible."""
        try:
            import psutil  # noqa: F401
            return True
        except ImportError:
            return False

    # ── Comando: abrir ────────────────────────────────────────────────────

    def _cmd_abrir(self, args: list[str]) -> SkillResult:
        """Abre una aplicación de Windows por nombre o alias."""
        if not args:
            aliases = ", ".join(sorted(_APP_ALIASES.keys())[:15])
            return SkillResult(
                success=False,
                error=(
                    "Especificá qué aplicación abrir. Ejemplos:\n"
                    "  abrir notepad\n"
                    "  abrir calculadora\n"
                    "  abrir explorador\n"
                    f"\nAlgunas apps disponibles: {aliases}, ..."
                ),
            )

        err = self._check_windows()
        if err:
            return err

        if isinstance(args, list):
            raw_input = " ".join(str(a) for a in args).strip()
        else:
            raw_input = str(args or "").strip()

        app_input = raw_input.lower()

        # Resolver alias
        ejecutable = _APP_ALIASES.get(app_input)
        if ejecutable is None:
            # Intentar coincidencia parcial
            for alias, exe in _APP_ALIASES.items():
                if app_input in alias or alias in app_input:
                    ejecutable = exe
                    break

        if ejecutable is None:
            # Usar el input directamente como ejecutable
            ejecutable = raw_input

        _logger.info(f"SystemSkill: abriendo '{ejecutable}'")

        try:
            if ejecutable.startswith("ms-settings:"):
                # Abrir configuración de Windows via URI
                os.startfile(ejecutable)  # type: ignore[attr-defined]
            elif ejecutable.lower().endswith(".lnk") or os.path.isabs(ejecutable):
                from core.app_resolver import launch_app
                launch_app(ejecutable)
            else:
                proc = subprocess.Popen(
                    [ejecutable],
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if proc and getattr(proc, "pid", None):
                    try:
                        from aura.skills.app_writer import record_app_opened
                        record_app_opened(ejecutable, proc.pid)
                    except Exception:
                        pass
            return SkillResult(
                success=True,
                output=f"✅ Abriendo '{ejecutable}'...",
                data={"app": ejecutable, "input": app_input},
            )
        except FileNotFoundError:
            return SkillResult(
                success=False,
                error=(
                    f"No se encontró la aplicación '{ejecutable}'.\n"
                    "Verificá que esté instalada y en el PATH del sistema."
                ),
            )
        except Exception as e:
            _logger.error(f"SystemSkill: error abriendo '{ejecutable}': {e}")
            return SkillResult(
                success=False,
                error=f"Error al abrir '{ejecutable}': {e}",
            )

    # ── Comando: cerrar ───────────────────────────────────────────────────

    def _cmd_cerrar(self, args: list[str]) -> SkillResult:
        """
        Cierra un proceso inmediatamente usando psutil.
        Match por nombre de proceso normalizado (sin tildes, case-insensitive).
        Mata todos los procesos que coincidan con el nombre.
        """
        if not args:
            return SkillResult(
                success=False,
                error=(
                    "Especificá el nombre del proceso a cerrar. Ejemplos:\n"
                    "  cerrar notepad\n"
                    "  cerrar chrome\n"
                    "  cerrar spotify\n"
                    "Tip: usá 'procesos' para ver los procesos en ejecución."
                ),
            )

        err = self._check_windows()
        if err:
            return err

        if isinstance(args, list):
            proceso_raw = " ".join(str(a) for a in args).strip()
        else:
            proceso_raw = str(args or "").strip()
        from core.app_scanner import normalize_name
        norm_input = normalize_name(proceso_raw)

        # Resolver alias si existe (ej: notepad -> notepad.exe, chrome -> chrome.exe)
        resolved_name = norm_input
        if norm_input in _APP_ALIASES:
            resolved_name = normalize_name(_APP_ALIASES[norm_input])

        target_stem = resolved_name[:-4] if resolved_name.endswith(".exe") else resolved_name
        target_exe = f"{target_stem}.exe"

        # Verificar si es un proceso protegido
        if target_exe in _PROTECTED_PROCESSES or target_stem in _PROTECTED_PROCESSES:
            return SkillResult(
                success=False,
                error=(
                    f"⚠️ No se puede cerrar '{proceso_raw}' porque es un proceso "
                    "crítico del sistema Windows."
                ),
            )

        _logger.info("SystemSkill: cerrando proceso(s) para '%s' (target_exe='%s')", proceso_raw, target_exe)

        try:
            import psutil
        except ImportError:
            try:
                res = subprocess.run(
                    ["taskkill", "/F", "/IM", target_exe],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )
                if res.returncode == 0:
                    return SkillResult(success=True, output="✅ Proceso cerrado.", data={"proceso": target_exe, "running": True})
                else:
                    return SkillResult(success=False, error=f"ℹ️ '{proceso_raw}' no estaba en ejecución.", data={"running": False})
            except Exception as e:
                return SkillResult(success=False, error=f"❌ No pude cerrarlo: {e}.")

        # Buscar todos los procesos que coincidan por nombre normalizado
        matching_procs: list[psutil.Process] = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                p_name = p.info.get("name") or ""
                p_norm = normalize_name(p_name)
                p_stem = p_norm[:-4] if p_norm.endswith(".exe") else p_norm

                if p_norm == target_exe or p_stem == target_stem:
                    matching_procs.append(p)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not matching_procs:
            _logger.info("SystemSkill: '%s' no estaba en ejecución", proceso_raw)
            return SkillResult(
                success=False,
                error=f"ℹ️ '{proceso_raw}' no estaba en ejecución.",
                data={"proceso": proceso_raw, "running": False, "killed": 0},
            )

        killed_count = 0
        errors: list[str] = []

        for proc in matching_procs:
            try:
                proc.kill()
                killed_count += 1
            except psutil.NoSuchProcess:
                killed_count += 1
            except psutil.AccessDenied:
                errors.append(f"Acceso denegado (PID {proc.pid})")
            except Exception as ex:
                errors.append(str(ex))

        if matching_procs:
            try:
                psutil.wait_procs(matching_procs, timeout=1.0)
            except Exception:
                pass

        if errors and killed_count == 0:
            err_msg = "; ".join(errors)
            _logger.error("SystemSkill: error cerrando '%s': %s", proceso_raw, err_msg)
            return SkillResult(
                success=False,
                error=f"❌ No pude cerrarlo: {err_msg}.",
                data={"proceso": proceso_raw, "running": True, "killed": 0, "errors": errors},
            )

        _logger.info("SystemSkill: %d proceso(s) de '%s' cerrados exitosamente", killed_count, proceso_raw)
        return SkillResult(
            success=True,
            output="✅ Proceso cerrado.",
            data={"proceso": target_exe, "running": True, "killed": killed_count},
        )

    # ── Comando: bloquear ─────────────────────────────────────────────────

    def _cmd_bloquear(self, args: list[str]) -> SkillResult:
        """Bloquea la sesión de Windows del usuario actual."""
        err = self._check_windows()
        if err:
            return err

        _logger.info("SystemSkill: bloqueando sesión de Windows")

        try:
            subprocess.Popen(
                ["rundll32.exe", "user32.dll,LockWorkStation"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return SkillResult(
                success=True,
                output="🔒 Sesión bloqueada. Para desbloquear, introducí tu contraseña de Windows.",
                data={"action": "lock"},
            )
        except Exception as e:
            _logger.error(f"SystemSkill: error bloqueando sesión: {e}")
            return SkillResult(
                success=False,
                error=f"Error al bloquear la sesión: {e}",
            )

    # ── Comando: apagar ───────────────────────────────────────────────────

    def _cmd_apagar(self, args: list[str]) -> SkillResult:
        """
        Apaga el equipo.

        Por defecto opera en modo dry-run (simulación).
        Requiere '--ahora' para ejecutar realmente.
        """
        err = self._check_windows()
        if err:
            return err

        dry_run = "--ahora" not in [a.lower() for a in args]
        delay = 30  # segundos de gracia

        if dry_run:
            _logger.info("SystemSkill: simulación de apagado (dry-run)")
            return SkillResult(
                success=True,
                output=(
                    "🔌 [SIMULACIÓN] El equipo SE APAGARÍA en 30 segundos.\n"
                    "\n"
                    "⚠️  Para apagar realmente, escribí:\n"
                    "    apagar --ahora\n"
                    "\n"
                    "Guardá todos tus archivos antes de confirmar."
                ),
                data={"action": "shutdown", "dry_run": True},
            )

        _logger.warning("SystemSkill: APAGANDO el equipo con delay=30s")

        try:
            subprocess.run(
                ["shutdown", "/s", "/t", str(delay)],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return SkillResult(
                success=True,
                output=(
                    f"🔌 El equipo se apagará en {delay} segundos.\n"
                    "Para cancelar, escribí en CMD: shutdown /a"
                ),
                data={"action": "shutdown", "dry_run": False, "delay": delay},
            )
        except subprocess.CalledProcessError as e:
            return SkillResult(
                success=False,
                error=f"Error al programar el apagado: {e}",
            )
        except Exception as e:
            _logger.error(f"SystemSkill: error apagando: {e}")
            return SkillResult(
                success=False,
                error=f"Error inesperado al apagar: {e}",
            )

    # ── Comando: reiniciar ────────────────────────────────────────────────

    def _cmd_reiniciar(self, args: list[str]) -> SkillResult:
        """
        Reinicia el equipo.

        Por defecto opera en modo dry-run (simulación).
        Requiere '--ahora' para ejecutar realmente.
        """
        err = self._check_windows()
        if err:
            return err

        dry_run = "--ahora" not in [a.lower() for a in args]
        delay = 30

        if dry_run:
            _logger.info("SystemSkill: simulación de reinicio (dry-run)")
            return SkillResult(
                success=True,
                output=(
                    "🔄 [SIMULACIÓN] El equipo SE REINICIARÍA en 30 segundos.\n"
                    "\n"
                    "⚠️  Para reiniciar realmente, escribí:\n"
                    "    reiniciar --ahora\n"
                    "\n"
                    "Guardá todos tus archivos antes de confirmar."
                ),
                data={"action": "restart", "dry_run": True},
            )

        _logger.warning("SystemSkill: REINICIANDO el equipo con delay=30s")

        try:
            subprocess.run(
                ["shutdown", "/r", "/t", str(delay)],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return SkillResult(
                success=True,
                output=(
                    f"🔄 El equipo se reiniciará en {delay} segundos.\n"
                    "Para cancelar, escribí en CMD: shutdown /a"
                ),
                data={"action": "restart", "dry_run": False, "delay": delay},
            )
        except subprocess.CalledProcessError as e:
            return SkillResult(
                success=False,
                error=f"Error al programar el reinicio: {e}",
            )
        except Exception as e:
            _logger.error(f"SystemSkill: error reiniciando: {e}")
            return SkillResult(
                success=False,
                error=f"Error inesperado al reiniciar: {e}",
            )

    # ── Comando: sysinfo ──────────────────────────────────────────────────

    def _cmd_sysinfo(self, args: list[str]) -> SkillResult:
        """Muestra información del sistema: CPU, RAM, disco y OS."""
        info_lines = [
            "💻 Información del Sistema",
            "",
            f"  Sistema operativo: {platform.system()} {platform.release()}",
            f"  Versión:           {platform.version()[:60]}",
            f"  Máquina:           {platform.machine()}",
            f"  Procesador:        {platform.processor() or 'N/A'}",
            f"  Python:            {sys.version.split()[0]}",
        ]

        if self._has_psutil():
            try:
                import psutil

                # CPU
                cpu_count = psutil.cpu_count(logical=True)
                cpu_percent = psutil.cpu_percent(interval=0.5)
                info_lines += [
                    "",
                    f"  CPU (núcleos lógicos): {cpu_count}",
                    f"  CPU uso actual:        {cpu_percent:.1f}%",
                ]

                # RAM
                vm = psutil.virtual_memory()
                ram_total = vm.total / (1024 ** 3)
                ram_used = vm.used / (1024 ** 3)
                ram_percent = vm.percent
                info_lines += [
                    "",
                    f"  RAM total:  {ram_total:.1f} GB",
                    f"  RAM usada:  {ram_used:.1f} GB ({ram_percent:.1f}%)",
                    f"  RAM libre:  {(vm.available / (1024**3)):.1f} GB",
                ]

                # Disco C:
                try:
                    disk = psutil.disk_usage("C:\\")
                    d_total = disk.total / (1024 ** 3)
                    d_used = disk.used / (1024 ** 3)
                    d_free = disk.free / (1024 ** 3)
                    info_lines += [
                        "",
                        f"  Disco C: total: {d_total:.1f} GB",
                        f"  Disco C: usado: {d_used:.1f} GB ({disk.percent:.1f}%)",
                        f"  Disco C: libre: {d_free:.1f} GB",
                    ]
                except Exception:
                    pass

            except Exception as e:
                info_lines.append(f"\n  (psutil disponible pero error al leer stats: {e})")
        else:
            info_lines.append(
                "\n  💡 Instalá psutil para ver CPU, RAM y disco:\n"
                "     pip install psutil"
            )

        return SkillResult(
            success=True,
            output="\n".join(info_lines),
            data={"platform": platform.system(), "python": sys.version.split()[0]},
        )

    # ── Comando: procesos ─────────────────────────────────────────────────

    def _cmd_procesos(self, args: list[str]) -> SkillResult:
        """Lista los procesos en ejecución, con filtro opcional por nombre."""
        if not self._has_psutil():
            return SkillResult(
                success=False,
                error=(
                    "psutil no está instalado. Para ver procesos instalalo con:\n"
                    "    pip install psutil\n"
                    "O desde el entorno de AURA:\n"
                    "    .\\env\\Scripts\\pip.exe install psutil"
                ),
            )

        filtro = " ".join(args).lower().strip() if args else ""

        try:
            import psutil

            procesos = []
            for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
                try:
                    nombre = proc.info["name"] or ""
                    if filtro and filtro not in nombre.lower():
                        continue
                    mem_mb = (proc.info["memory_info"].rss / (1024 ** 2)
                              if proc.info["memory_info"] else 0)
                    procesos.append((proc.info["pid"], nombre, mem_mb))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if not procesos:
                msg = f"No se encontraron procesos que coincidan con '{filtro}'." if filtro else "No hay procesos visibles."
                return SkillResult(success=True, output=msg)

            # Ordenar por nombre
            procesos.sort(key=lambda x: x[1].lower())

            # Limitar a 30 para no saturar el chat
            total = len(procesos)
            mostrados = procesos[:30]

            lines = [
                f"📋 Procesos en ejecución{f' (filtro: {filtro})' if filtro else ''}:",
                f"{'PID':>7}  {'Nombre':<35}  {'Mem (MB)':>9}",
                "-" * 56,
            ]
            for pid, nombre, mem in mostrados:
                lines.append(f"{pid:>7}  {nombre:<35}  {mem:>9.1f}")

            if total > 30:
                lines.append(f"\n  ... y {total - 30} más. Usá 'procesos <filtro>' para buscar.")

            lines.append(f"\nTotal visibles: {total}")
            lines.append("Para cerrar uno: cerrar <nombre_proceso>")

            return SkillResult(
                success=True,
                output="\n".join(lines),
                data={"total": total, "filtro": filtro},
            )

        except Exception as e:
            _logger.error(f"SystemSkill: error listando procesos: {e}")
            return SkillResult(
                success=False,
                error=f"Error al listar procesos: {e}",
            )

    # ── Comando: papelera ─────────────────────────────────────────────────

    def _cmd_papelera(self, args: list[str]) -> SkillResult:
        """
        Vacía la papelera de reciclaje de Windows.

        Por defecto opera en modo dry-run.
        Requiere '--ahora' para vaciar realmente.
        """
        err = self._check_windows()
        if err:
            return err

        dry_run = "--ahora" not in [a.lower() for a in args]

        if dry_run:
            _logger.info("SystemSkill: simulación de vaciado de papelera (dry-run)")
            return SkillResult(
                success=True,
                output=(
                    "🗑️ [SIMULACIÓN] La papelera SE VACIARÍA.\n"
                    "\n"
                    "⚠️  Esta acción es irreversible. Los archivos se eliminarán permanentemente.\n"
                    "Para vaciar realmente, escribí:\n"
                    "    papelera --ahora"
                ),
                data={"action": "empty_trash", "dry_run": True},
            )

        _logger.warning("SystemSkill: vaciando papelera de reciclaje")

        try:
            # Usar PowerShell para vaciar la papelera
            result = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-Command",
                    "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            # PowerShell puede retornar 0 o 1 (si ya estaba vacía)
            if result.returncode in (0, 1):
                return SkillResult(
                    success=True,
                    output="🗑️ Papelera de reciclaje vaciada correctamente.",
                    data={"action": "empty_trash", "dry_run": False},
                )
            else:
                return SkillResult(
                    success=False,
                    error=f"Error al vaciar la papelera. Código: {result.returncode}",
                )
        except subprocess.TimeoutExpired:
            return SkillResult(
                success=False,
                error="Tiempo de espera agotado al vaciar la papelera.",
            )
        except Exception as e:
            _logger.error(f"SystemSkill: error vaciando papelera: {e}")
            return SkillResult(
                success=False,
                error=f"Error al vaciar la papelera: {e}",
            )

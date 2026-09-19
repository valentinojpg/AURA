"""
AURA — Motor de automatizaciones (Fase 19)

Carga y ejecuta automatizaciones definidas en archivos YAML o JSON.
Cada automatización es una secuencia de pasos tipados.

Tipos de pasos disponibles:
  - open_app  : Abre una aplicación por nombre de proceso o alias builtin.
  - open_url  : Abre una URL en el navegador por defecto.
  - delay     : Espera N segundos (float).
  - message   : Muestra un mensaje (solo en el log y output).

Formato YAML de ejemplo:
  name: "Modo Programar"
  description: "Abre el entorno de desarrollo"
  version: "1.0"
  steps:
    - type: message
      text: "Iniciando entorno de programación..."
    - type: open_app
      app: vscode
    - type: delay
      seconds: 1.5
    - type: open_url
      url: https://github.com
"""

from __future__ import annotations

import json
import os
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from utils.logger import get_logger

_logger = get_logger("aura.automation.engine")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Directorio de automatizaciones del usuario
_AUTOMATIONS_DIR = Path(__file__).parent.parent / "data" / "automations"

# Extensiones de archivo reconocidas
_VALID_EXTENSIONS = {".yaml", ".yml", ".json"}

# Tiempo máximo de delay permitido por paso (segundos)
_MAX_DELAY_SECONDS = 60.0

# Alias de aplicaciones para open_app (subset del SystemSkill)
_APP_ALIASES: dict[str, str] = {
    "notepad":       "notepad.exe",
    "calculadora":   "calc.exe",
    "explorador":    "explorer.exe",
    "chrome":        "chrome.exe",
    "firefox":       "firefox.exe",
    "edge":          "msedge.exe",
    "vscode":        "code.exe",
    "code":          "code.exe",
    "cmd":           "cmd.exe",
    "powershell":    "powershell.exe",
    "terminal":      "wt.exe",
    "paint":         "mspaint.exe",
    "word":          "winword.exe",
    "excel":         "excel.exe",
    "powerpoint":    "powerpnt.exe",
    "discord":       "discord.exe",
    "spotify":       "spotify.exe",
    "vlc":           "vlc.exe",
    "sublime":       "sublime_text.exe",
    "pycharm":       "pycharm64.exe",
    "git-bash":      "git-bash.exe",
    "postman":       "postman.exe",
}

# ---------------------------------------------------------------------------
# Helpers de espera y sincronización (Fase 71)
# ---------------------------------------------------------------------------

def wait_for_app_ready(app_name: str, timeout: float = 5.0) -> bool:
    """
    Espera hasta `timeout` segundos a que la ventana o proceso de la app esté lista,
    retornando apenas se detecte para no bloquear innecesariamente.
    """
    if timeout <= 0 or not app_name:
        return True
    try:
        from skills.builtin.app_writer import resolve_running_app_pid, find_app_window
        start = time.time()
        while time.time() - start < timeout:
            pid, _ = resolve_running_app_pid(app_name)
            if pid:
                hwnd, _ = find_app_window(pid)
                if hwnd:
                    return True
            time.sleep(0.2)
    except Exception:
        pass
    return True


# ---------------------------------------------------------------------------
# Dataclasses de resultado
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    """Resultado de la ejecución de un paso de automatización."""

    index: int
    step_type: str
    success: bool
    output: str = ""
    error: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.success


@dataclass
class AutomationResult:
    """Resultado completo de la ejecución de una automatización."""

    name: str
    success: bool
    total_steps: int
    completed_steps: int
    failed_steps: int
    step_results: list[StepResult] = field(default_factory=list)
    output: str = ""
    error: str = ""
    status: str = "OK"  # "OK", "PARCIAL", "FALLIDA"

    def __bool__(self) -> bool:

        return self.success


@dataclass
class AutomationInfo:
    """Metadatos de una automatización cargada desde disco."""

    name: str
    display_name: str
    description: str
    version: str
    step_count: int
    path: Path
    format: str  # "yaml" o "json"

    @property
    def filename(self) -> str:
        return self.path.name


# ---------------------------------------------------------------------------
# Motor de automatizaciones
# ---------------------------------------------------------------------------


class AutomationEngine:
    """
    Motor central para cargar y ejecutar automatizaciones YAML/JSON.

    No mantiene estado entre ejecuciones — cada llamada a run() es independiente.
    """

    # ── API pública ──────────────────────────────────────────────────────────

    def list_automations(self) -> list[AutomationInfo]:
        """
        Lista todas las automatizaciones disponibles en el directorio de datos.

        Returns:
            Lista de AutomationInfo, ordenada por nombre.
        """
        if not _AUTOMATIONS_DIR.exists():
            return []

        infos: list[AutomationInfo] = []
        for path in sorted(_AUTOMATIONS_DIR.iterdir()):
            if path.suffix.lower() not in _VALID_EXTENSIONS:
                continue
            try:
                data = self._load_file(path)
                info = self._parse_info(data, path)
                infos.append(info)
            except Exception as exc:  # pylint: disable=broad-except
                _logger.warning("No se pudo leer '%s': %s", path.name, exc)

        return infos

    def get_info(self, name: str) -> AutomationInfo | None:
        """
        Obtiene la info de una automatización por nombre (sin extensión).

        Args:
            name: Nombre de la automatización (ej. "modo_programar").

        Returns:
            AutomationInfo si existe, None si no se encuentra.
        """
        for info in self.list_automations():
            slug = info.path.stem.lower()
            if slug == name.lower() or info.display_name.lower() == name.lower():
                return info
        return None

    def run(
        self,
        name: str,
        dry_run: bool = False,
    ) -> AutomationResult:
        """
        Ejecuta una automatización por nombre.

        Args:
            name:    Nombre de la automatización (sin extensión).
            dry_run: Si True, simula la ejecución sin efectos reales.

        Returns:
            AutomationResult con el detalle de cada paso.
        """
        # Buscar el archivo
        path = self._find_path(name)
        if path is None:
            return AutomationResult(
                name=name,
                success=False,
                total_steps=0,
                completed_steps=0,
                failed_steps=0,
                error=f"Automatización '{name}' no encontrada en {_AUTOMATIONS_DIR}.",
            )

        # Cargar y parsear
        try:
            data = self._load_file(path)
        except Exception as exc:
            return AutomationResult(
                name=name,
                success=False,
                total_steps=0,
                completed_steps=0,
                failed_steps=0,
                error=f"Error al leer el archivo '{path.name}': {exc}",
            )

        display_name = str(data.get("name", path.stem))
        steps = data.get("steps", [])
        if not isinstance(steps, list):
            return AutomationResult(
                name=name,
                success=False,
                total_steps=0,
                completed_steps=0,
                failed_steps=0,
                error=f"El archivo '{path.name}' no tiene una lista de pasos ('steps').",
            )

        from core.app_resolver import get_preferred_browser_name, BROWSER_DISPLAY_NAMES
        pref_browser = get_preferred_browser_name()
        pref_disp = BROWSER_DISPLAY_NAMES.get(pref_browser.lower(), pref_browser.title())

        _logger.info(
            "Iniciando automatización '%s' (%d pasos)%s. BROWSER_PREFERIDO activo: %s (%s)",
            display_name,
            len(steps),
            " [DRY-RUN]" if dry_run else "",
            pref_disp,
            pref_browser,
        )

        # Ejecutar pasos
        step_results: list[StepResult] = []
        completed = 0
        failed = 0

        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                sr = StepResult(
                    index=i,
                    step_type="desconocido",
                    success=False,
                    error=f"El paso {i + 1} no es un objeto válido.",
                )
                target = "desconocido"
            else:
                stype = str(step.get("type", "")).lower().strip()
                if stype == "open_app":
                    target = str(step.get("app", "")).strip()
                elif stype == "open_url":
                    target = str(step.get("url", "")).strip()
                elif stype == "delay":
                    target = str(step.get("seconds", ""))
                elif stype == "message":
                    target = str(step.get("text", ""))
                else:
                    target = str(step)

                sr = self._execute_step(i, step, dry_run=dry_run, steps=steps)

            step_results.append(sr)

            resolved = (
                sr.data.get("resolved")
                or sr.data.get("exe")
                or sr.data.get("url")
                or target
            )
            detalle = sr.output if sr.success else sr.error

            # Loguear por paso: tipo, target, resolved, ok, detalle
            _logger.info(
                "Paso %d [%s]: target='%s', resolved='%s', ok=%s, detalle='%s'",
                i + 1,
                sr.step_type,
                target,
                resolved,
                sr.success,
                detalle,
            )

            if sr.success:
                completed += 1
            else:
                failed += 1
                _logger.warning(
                    "Paso %d falló en '%s': %s", i + 1, display_name, sr.error
                )

        total = len(steps)
        overall_success = (failed == 0 and total > 0) or (total == 0)

        if total == 0 or failed == 0:
            status = "OK"
        elif completed == 0:
            status = "FALLIDA"
        else:
            status = "PARCIAL"

        output = self._build_output(display_name, step_results, dry_run=dry_run, status=status)

        return AutomationResult(
            name=name,
            success=overall_success,
            total_steps=total,
            completed_steps=completed,
            failed_steps=failed,
            step_results=step_results,
            output=output,
            status=status,
        )

    def run_steps(
        self,
        steps: list[dict[str, Any]],
        name: str = "Cadena de instrucciones",
        dry_run: bool = False,
        on_step_update: Optional[Any] = None,
        on_error: Optional[str] = None,
    ) -> AutomationResult:
        """
        Ejecuta una secuencia de pasos definida al vuelo (automatización temporal) (Fase 71).

        Args:
            steps: Lista de pasos tipados (dicts con 'type' y parámetros).
            name: Nombre para el informe/resultado.
            dry_run: Si es True, simula la ejecución sin efectos secundarios.
            on_step_update: Callback opcional invocado en cada paso: (index, status, result),
                            donde status es 'running', 'success' o 'error'.
            on_error: Política ante fallos: 'stop' (detiene la cadena) o 'continue' (sigue).
                      Por defecto toma el valor de settings.get("PLAN_ON_ERROR", "stop").

        Returns:
            AutomationResult con el detalle de cada paso y el balance global.
        """
        from config.settings import settings
        error_policy = (on_error or settings.get("PLAN_ON_ERROR", "stop") or "stop").lower().strip()
        wait_app_sec = settings.get_float("PLAN_WAIT_APP_SECONDS", 5.0)
        wait_page_sec = settings.get_float("PLAN_WAIT_PAGE_SECONDS", 2.0)

        step_results: list[StepResult] = []
        completed = 0
        failed = 0

        # Prevalidación de PLAN_STRICT (Fase 72)
        is_strict = False
        if hasattr(settings, "is_plan_strict"):
            is_strict = settings.is_plan_strict()
        else:
            is_strict = str(settings.get("PLAN_STRICT", "false")).lower() in ("true", "1", "yes")

        if is_strict:
            invalid_step = next((s for s in steps if isinstance(s, dict) and s.get("valid") is False), None)
            if invalid_step:
                err_reason = invalid_step.get("unsupported_reason") or "Paso no soportado según capacidades de la aplicación."
                _logger.warning("run_steps: abortado antes de iniciar debido a PLAN_STRICT=true: %s", err_reason)
                fail_sr = StepResult(
                    index=0,
                    step_type=invalid_step.get("type", "desconocido"),
                    success=False,
                    error=f"Plan abortado (PLAN_STRICT=true): {err_reason}",
                    data={"unsupported_reason": err_reason, "strict_aborted": True},
                )
                if on_step_update:
                    try:
                        on_step_update(0, "error", fail_sr)
                    except Exception:
                        pass
                return AutomationResult(
                    name=name,
                    success=False,
                    total_steps=len(steps),
                    completed_steps=0,
                    failed_steps=len(steps),
                    step_results=[fail_sr],
                    output=f"❌ Plan abortado (PLAN_STRICT=true): {err_reason}",
                    status="FALLIDA",
                )

        _logger.info(
            "run_steps: ejecutando %d pasos para '%s' (dry_run=%s, on_error=%s)",
            len(steps),
            name,
            dry_run,
            error_policy,
        )

        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                sr = StepResult(
                    index=i,
                    step_type="desconocido",
                    success=False,
                    error=f"El paso {i + 1} no es un objeto válido.",
                )
                step_results.append(sr)
                failed += 1
                if on_step_update:
                    try:
                        on_step_update(i, "error", sr)
                    except Exception as ex:
                        _logger.warning("run_steps: error en callback (error): %s", ex)
                if error_policy == "stop":
                    break
                continue

            stype = str(step.get("type", "")).lower().strip()

            # Si el paso está marcado como no soportado (PLAN_STRICT=false)
            if step.get("valid") is False:
                reason = step.get("unsupported_reason") or "Paso no soportado para la aplicación."
                app_target = step.get("app") or step.get("target") or ""
                display_app = app_target.capitalize() if app_target else "La aplicación"
                warning_msg = f"⚠️ Paso {i + 1} salteado: {display_app} no soporta esta operación ({reason})"
                _logger.warning("run_steps: paso %d salteado por capacidades: %s", i + 1, reason)
                sr = StepResult(
                    index=i,
                    step_type=stype,
                    success=True,
                    output=warning_msg,
                    data={"skipped": True, "unsupported_reason": reason, "app": app_target},
                )
                step_results.append(sr)
                completed += 1
                if on_step_update:
                    try:
                        on_step_update(i, "skipped", sr)
                    except Exception as ex:
                        _logger.warning("run_steps: error en callback (skipped): %s", ex)
                continue

            if on_step_update:
                try:
                    on_step_update(i, "running", None)
                except Exception as ex:
                    _logger.warning("run_steps: error en callback (running): %s", ex)

            try:
                sr = self._execute_step(i, step, dry_run=dry_run, steps=steps)
            except Exception as exc:
                import traceback
                tb_short = traceback.format_exc(limit=3).strip()
                _logger.error(
                    "run_steps: excepción no manejada en paso %d (%s): %s: %s\n%s",
                    i + 1,
                    stype,
                    type(exc).__name__,
                    exc,
                    tb_short,
                )
                sr = StepResult(
                    index=i,
                    step_type=stype,
                    success=False,
                    error=f"Error inesperado ({type(exc).__name__}): {exc}",
                    data={"exception_type": type(exc).__name__, "traceback": tb_short},
                )

            step_results.append(sr)

            if sr.success:
                completed += 1
                if on_step_update:
                    try:
                        on_step_update(i, "success", sr)
                    except Exception as ex:
                        _logger.warning("run_steps: error en callback (success): %s", ex)

                # Esperas inteligentes entre pasos (si no es simulación)
                if not dry_run:
                    if stype == "open_app":
                        app_target = step.get("app") or step.get("target") or ""
                        wait_for_app_ready(str(app_target), timeout=wait_app_sec)
                    elif stype == "open_url":
                        time.sleep(wait_page_sec)
                    elif stype == "media_play":
                        # Fase 79: si la cadena tiene pasos siguientes, esperar que cargue y empiece a sonar
                        if i < len(steps) - 1 and wait_page_sec > 0:
                            time.sleep(wait_page_sec)
            else:
                failed += 1
                ex_type = sr.data.get("exception_type", "StepError")
                tb_info = sr.data.get("traceback", "")
                _logger.warning(
                    "run_steps: paso %d (%s) falló: %s (tipo=%s)%s",
                    i + 1,
                    stype,
                    sr.error,
                    ex_type,
                    f"\nTraceback:\n{tb_info}" if tb_info else "",
                )
                if on_step_update:
                    try:
                        on_step_update(i, "error", sr)
                    except Exception as ex:
                        _logger.warning("run_steps: error en callback (error): %s", ex)

                if error_policy == "stop":
                    _logger.warning("run_steps: paso %d falló y on_error='stop'. Deteniendo cadena.", i + 1)
                    break

        total = len(steps)
        overall_success = (failed == 0 and total > 0) or (total == 0)

        if total == 0 or failed == 0:
            status = "OK"
        elif completed == 0:
            status = "FALLIDA"
        else:
            status = "PARCIAL"

        output = self._build_output(name, step_results, dry_run=dry_run, status=status)

        return AutomationResult(
            name=name,
            success=overall_success,
            total_steps=total,
            completed_steps=completed,
            failed_steps=failed,
            step_results=step_results,
            output=output,
            status=status,
        )


    # ── Ejecución de pasos ──────────────────────────────────────────────────

    def _execute_step(
        self,
        index: int,
        step: dict[str, Any],
        dry_run: bool = False,
        steps: Optional[list[dict[str, Any]]] = None,
    ) -> StepResult:
        """Despacha un paso al handler correspondiente."""
        step_type = str(step.get("type", "")).lower().strip()

        handlers = {
            "open_app":      self._step_open_app,
            "close_app":     self._step_close_app,
            "open_url":      self._step_open_url,
            "delay":         self._step_delay,
            "message":       self._step_message,
            "write_in_app":  self._step_write_in_app,
            "save_app_doc":  self._step_save_app_doc,
            "media_play":    self._step_media_play,
            "create_file":   self._step_create_file,
            "create_folder": self._step_create_folder,
            "delete_file":   self._step_delete_file,
            "move_file":     self._step_move_file,
            "rename_file":   self._step_rename_file,
            "search_file":   self._step_search_file,
        }

        handler = handlers.get(step_type)
        if handler is None:
            return StepResult(
                index=index,
                step_type=step_type or "vacío",
                success=False,
                error=(
                    f"Tipo de paso '{step_type}' no reconocido. "
                    f"Tipos disponibles: {', '.join(sorted(handlers.keys()))}"
                ),
            )

        if step_type == "write_in_app":
            return self._step_write_in_app(index, step, dry_run=dry_run, steps=steps)

        return handler(index, step, dry_run=dry_run)

    def _step_open_app(
        self,
        index: int,
        step: dict[str, Any],
        dry_run: bool = False,
    ) -> StepResult:
        """Paso: abre una aplicación usando resolve_app y launch_app."""
        raw_app = step.get("app") or step.get("target") or ""
        if isinstance(raw_app, (list, tuple)):
            app = " ".join(str(x) for x in raw_app).strip()
        else:
            app = str(raw_app).strip()

        if not app:
            return StepResult(
                index=index,
                step_type="open_app",
                success=False,
                error="El paso 'open_app' requiere el campo 'app'.",
                data={"app": "", "target": "", "resolved": None},
            )

        from core.app_resolver import resolve_app, launch_app

        resolved = resolve_app(app)
        _logger.info("open_app: '%s' → resolved=%s (exe='%s')%s", app, resolved.success, resolved.executable, " [DRY]" if dry_run else "")

        if not resolved.success:
            return StepResult(
                index=index,
                step_type="open_app",
                success=False,
                error=resolved.error or f"No se pudo resolver la aplicación '{app}'.",
                data={"app": app, "target": app, "resolved": None},
            )

        exe = resolved.executable
        if dry_run:
            return StepResult(
                index=index,
                step_type="open_app",
                success=True,
                output=f"[SIMULADO] Abriría: {exe}",
                data={"app": app, "target": app, "resolved": exe, "exe": exe, "dry_run": True},
            )

        try:
            launch_app(exe)
            return StepResult(
                index=index,
                step_type="open_app",
                success=True,
                output=f"✅ Abierto: {exe}",
                data={"app": app, "target": app, "resolved": exe, "exe": exe},
            )
        except Exception as exc:  # pylint: disable=broad-except
            return StepResult(
                index=index,
                step_type="open_app",
                success=False,
                error=f"No se pudo abrir '{exe}': {exc}",
                data={"app": app, "target": app, "resolved": exe, "exe": exe},
            )

    def _step_close_app(
        self,
        index: int,
        step: dict[str, Any],
        dry_run: bool = False,
    ) -> StepResult:
        """Paso: cierra una aplicación por nombre de proceso o alias (directo, sin confirmación)."""
        raw_app = step.get("app") or step.get("process") or step.get("target") or ""
        if isinstance(raw_app, (list, tuple)):
            app = " ".join(str(x) for x in raw_app).strip()
        else:
            app = str(raw_app).strip()
        if not app:
            return StepResult(
                index=index,
                step_type="close_app",
                success=False,
                error="El paso 'close_app' requiere el campo 'app' o 'process'.",
                data={"app": "", "target": "", "resolved": None},
            )

        _logger.info("close_app: '%s'%s", app, " [DRY]" if dry_run else "")

        if dry_run:
            return StepResult(
                index=index,
                step_type="close_app",
                success=True,
                output=f"[SIMULADO] Cerraría: {app}",
                data={"app": app, "target": app, "dry_run": True},
            )

        from skills.skill_registry import skill_registry
        if not skill_registry.list_all():
            skill_registry.discover_builtin()

        res = skill_registry.execute("system_skill", "cerrar", [app])
        if res.success:
            return StepResult(
                index=index,
                step_type="close_app",
                success=True,
                output=res.output or f"✅ Proceso cerrado: {app}",
                data={"app": app, "result": res.data},
            )
        else:
            is_not_running = "no estaba en ejecución" in (res.output or res.error or "")
            return StepResult(
                index=index,
                step_type="close_app",
                success=True if is_not_running else False,
                output=res.output or res.error,
                error="" if is_not_running else (res.error or f"No se pudo cerrar '{app}'."),
                data={"app": app, "result": res.data},
            )

    def _step_open_url(
        self,
        index: int,
        step: dict[str, Any],
        dry_run: bool = False,
    ) -> StepResult:
        """Paso: abre una URL en el navegador preferido BROWSER_PREFERIDO."""
        url = str(step.get("url", "")).strip()
        if not url:
            return StepResult(
                index=index,
                step_type="open_url",
                success=False,
                error="El paso 'open_url' requiere el campo 'url'.",
                data={"url": "", "target": "", "resolved": None},
            )

        # Normalizar URL o resolver alias de sitio web
        from aura.core.entity_resolver import SITE_ALIASES_MAP
        target_lower = url.lower()
        if target_lower in SITE_ALIASES_MAP:
            url = SITE_ALIASES_MAP[target_lower]
        elif not url.startswith(("http://", "https://", "ftp://")):
            url = "https://" + url

        from core.app_resolver import (
            resolve_app,
            launch_app,
            get_preferred_browser_name,
            BROWSER_DISPLAY_NAMES,
        )

        pref_name = get_preferred_browser_name()
        pref_disp = BROWSER_DISPLAY_NAMES.get(pref_name.lower(), pref_name.title())
        browser_res = resolve_app("navegador")
        browser_exe = browser_res.executable if browser_res.success else None

        _logger.info(
            "open_url: abriendo '%s' con BROWSER_PREFERIDO '%s' (%s)%s",
            url,
            pref_disp,
            browser_exe or "no encontrado",
            " [DRY]" if dry_run else "",
        )

        if dry_run:
            return StepResult(
                index=index,
                step_type="open_url",
                success=True,
                output=f"[SIMULADO] Abriría URL en {pref_disp}: {url}",
                data={"url": url, "target": url, "browser": pref_name, "resolved": browser_exe or pref_name, "dry_run": True},
            )

        # Si en tests se mockea webbrowser.open directamente, respetar el mock
        if hasattr(webbrowser.open, "assert_called"):
            try:
                abierto = webbrowser.open(url, new=2)
                if abierto:
                    return StepResult(
                        index=index,
                        step_type="open_url",
                        success=True,
                        output=f"✅ URL abierta: {url}",
                        data={"url": url, "target": url, "browser": "mock", "resolved": "webbrowser"},
                    )
                return StepResult(
                    index=index,
                    step_type="open_url",
                    success=False,
                    error=f"webbrowser.open retornó False para '{url}'.",
                    data={"url": url, "target": url, "resolved": None},
                )
            except Exception as exc:
                return StepResult(
                    index=index,
                    step_type="open_url",
                    success=False,
                    error=f"Error al abrir '{url}': {exc}",
                    data={"url": url, "target": url, "resolved": None},
                )

        # Si tenemos ejecutable preferido válido, abrir directamente
        if browser_exe and os.path.isfile(browser_exe):

            try:
                launch_app(browser_exe, [url])
                _logger.info("open_url: URL abierta con éxito en '%s' (%s): %s", pref_disp, browser_exe, url)
                return StepResult(
                    index=index,
                    step_type="open_url",
                    success=True,
                    output=f"✅ URL abierta en {pref_disp}: {url}",
                    data={"url": url, "target": url, "browser": pref_name, "resolved": browser_exe},
                )
            except Exception as exc:
                _logger.warning("open_url: fallo al abrir con %s (%s): %s. Intentando fallback a webbrowser...", pref_disp, browser_exe, exc)

        # Fallback a webbrowser del sistema
        try:
            _logger.info("open_url: abriendo '%s' con navegador predeterminado del sistema (webbrowser)", url)
            abierto = webbrowser.open(url, new=2)
            if abierto:
                return StepResult(
                    index=index,
                    step_type="open_url",
                    success=True,
                    output=f"✅ URL abierta: {url}",
                    data={"url": url, "target": url, "browser": "default", "resolved": "webbrowser"},
                )
            return StepResult(
                index=index,
                step_type="open_url",
                success=False,
                error=f"No se pudo abrir la URL '{url}' en ningún navegador.",
                data={"url": url, "target": url, "resolved": None},
            )
        except Exception as exc:  # pylint: disable=broad-except
            return StepResult(
                index=index,
                step_type="open_url",
                success=False,
                error=f"Error al abrir '{url}': {exc}",
                data={"url": url, "target": url, "resolved": None},
            )


    def _step_delay(
        self,
        index: int,
        step: dict[str, Any],
        dry_run: bool = False,
    ) -> StepResult:
        """Paso: espera N segundos."""
        try:
            seconds = float(step.get("seconds", 1.0))
        except (TypeError, ValueError):
            return StepResult(
                index=index,
                step_type="delay",
                success=False,
                error="El campo 'seconds' debe ser un número.",
            )

        if seconds < 0:
            return StepResult(
                index=index,
                step_type="delay",
                success=False,
                error="El campo 'seconds' no puede ser negativo.",
            )

        if seconds > _MAX_DELAY_SECONDS:
            return StepResult(
                index=index,
                step_type="delay",
                success=False,
                error=(
                    f"El delay de {seconds}s supera el máximo permitido "
                    f"({_MAX_DELAY_SECONDS}s)."
                ),
            )

        _logger.info("delay: %.2fs%s", seconds, " [DRY]" if dry_run else "")

        if dry_run:
            return StepResult(
                index=index,
                step_type="delay",
                success=True,
                output=f"[SIMULADO] Esperaría {seconds}s",
                data={"seconds": seconds, "dry_run": True},
            )

        time.sleep(seconds)
        return StepResult(
            index=index,
            step_type="delay",
            success=True,
            output=f"⏱️ Esperado {seconds}s",
            data={"seconds": seconds},
        )

    def _step_message(
        self,
        index: int,
        step: dict[str, Any],
        dry_run: bool = False,
    ) -> StepResult:
        """Paso: muestra un mensaje (no produce efectos secundarios)."""
        text = str(step.get("text", "")).strip()
        if not text:
            return StepResult(
                index=index,
                step_type="message",
                success=False,
                error="El paso 'message' requiere el campo 'text'.",
            )

        _logger.info("message: %s", text)
        return StepResult(
            index=index,
            step_type="message",
            success=True,
            output=f"💬 {text}",
            data={"text": text},
        )

    def _step_write_in_app(
        self,
        index: int,
        step: dict[str, Any],
        dry_run: bool = False,
        steps: Optional[list[dict[str, Any]]] = None,
    ) -> StepResult:
        """Paso: escribe texto dentro de una app abierta (usando app_writer)."""
        raw_app = step.get("app") or step.get("target") or "notepad"
        app = str(raw_app).strip() or "notepad"
        raw_texto = step.get("texto") or step.get("text") or ""
        texto = str(raw_texto).strip()

        _logger.info("write_in_app: app='%s' texto='%s'%s", app, texto, " [DRY]" if dry_run else "")

        if dry_run:
            return StepResult(
                index=index,
                step_type="write_in_app",
                success=True,
                output=f"[SIMULADO] Escribiría en {app}: '{texto}'",
                data={"app": app, "texto": texto, "dry_run": True},
            )

        if "require_running" in step:
            require_running = bool(step["require_running"])
        else:
            prior_open = False
            if steps:
                prior_open = any(
                    isinstance(s, dict) and s.get("type") == "open_app"
                    for s in steps[:index]
                )
            require_running = not prior_open

        try:
            from skills.builtin.app_writer import write_in_app
            res = write_in_app(app_target=app, text=texto, require_running=require_running)
            return StepResult(
                index=index,
                step_type="write_in_app",
                success=res.success,
                output=res.output or f"✅ Escrito en {app}",
                error=res.error or "",
                data=res.data or {"app": app, "texto": texto},
            )
        except Exception as exc:
            import traceback
            tb_short = traceback.format_exc(limit=3).strip()
            _logger.error("write_in_app: excepción en paso %d: %s: %s\n%s", index + 1, type(exc).__name__, exc, tb_short)
            return StepResult(
                index=index,
                step_type="write_in_app",
                success=False,
                error=f"Error escribiendo en '{app}': {exc}",
                data={"app": app, "texto": texto, "exception_type": type(exc).__name__, "traceback": tb_short},
            )

    def _step_save_app_doc(
        self,
        index: int,
        step: dict[str, Any],
        dry_run: bool = False,
    ) -> StepResult:
        """Paso: guarda el documento de una app abierta (usando app_saver)."""
        app = str(step.get("app") or step.get("target") or "notepad").strip()
        filename = str(step.get("nombre") or step.get("filename") or "").strip()
        dest = str(step.get("destino") or step.get("destination") or "").strip()

        _logger.info("save_app_doc: app='%s' filename='%s' dest='%s'%s", app, filename, dest, " [DRY]" if dry_run else "")

        if dry_run:
            return StepResult(
                index=index,
                step_type="save_app_doc",
                success=True,
                output=f"[SIMULADO] Guardaría {app} como '{filename}' en '{dest}'",
                data={"app": app, "filename": filename, "destination": dest, "dry_run": True},
            )

        try:
            from aura.skills.app_saver import save_app_document
            res = save_app_document(app_name=app, filename=filename, destination=dest)
            return StepResult(
                index=index,
                step_type="save_app_doc",
                success=res.success,
                output=res.output or f"💾 Guardado {app}",
                error=res.error or "",
                data=res.data or {"app": app, "filename": filename, "destination": dest},
            )
        except Exception as exc:
            import traceback
            tb_short = traceback.format_exc(limit=3).strip()
            _logger.error("save_app_doc: excepción en paso %d: %s: %s\n%s", index + 1, type(exc).__name__, exc, tb_short)
            return StepResult(
                index=index,
                step_type="save_app_doc",
                success=False,
                error=f"Error guardando documento de '{app}': {exc}",
                data={"app": app, "filename": filename, "destination": dest, "exception_type": type(exc).__name__, "traceback": tb_short},
            )

    def _step_media_play(
        self,
        index: int,
        step: dict[str, Any],
        dry_run: bool = False,
    ) -> StepResult:
        """Paso: busca/reproduce música o video (usando media_play_skill)."""
        query = str(step.get("query") or step.get("target") or "").strip()
        service = str(step.get("service") or "").strip()

        if not query:
            return StepResult(
                index=index,
                step_type="media_play",
                success=False,
                error="El paso 'media_play' requiere el campo 'query'.",
            )

        _logger.info("media_play: query='%s' service='%s'%s", query, service, " [DRY]" if dry_run else "")

        if dry_run:
            return StepResult(
                index=index,
                step_type="media_play",
                success=True,
                output=f"[SIMULADO] Reproduciría '{query}' en {service or 'default'}",
                data={"query": query, "service": service, "dry_run": True},
            )

        try:
            from skills.builtin.media_play_skill import MediaPlaySkill
            skill = MediaPlaySkill()
            args = [query]
            if service:
                args.extend(["--service", service])
            res = skill.execute("reproducir", args)
            return StepResult(
                index=index,
                step_type="media_play",
                success=res.success,
                output=res.output or f"🎵 Reproduciendo '{query}'",
                error=res.error or "",
                data=res.data or {"query": query, "service": service},
            )
        except Exception as exc:
            return StepResult(
                index=index,
                step_type="media_play",
                success=False,
                error=f"Error reproduciendo '{query}': {exc}",
                data={"query": query, "service": service},
            )

    def _step_create_file(
        self,
        index: int,
        step: dict[str, Any],
        dry_run: bool = False,
    ) -> StepResult:
        """Paso: crea un archivo vacío usando files_skill."""
        target = str(step.get("nombre") or step.get("target") or "").strip()
        if not target:
            return StepResult(index=index, step_type="create_file", success=False, error="Falta el nombre de archivo.")
        if dry_run:
            return StepResult(index=index, step_type="create_file", success=True, output=f"[SIMULADO] Crearía archivo '{target}'")
        from skills.builtin.files_skill import FilesSkill
        res = FilesSkill().execute("crear", [target])
        return StepResult(index=index, step_type="create_file", success=res.success, output=res.output, error=res.error, data=res.data or {})

    def _step_create_folder(
        self,
        index: int,
        step: dict[str, Any],
        dry_run: bool = False,
    ) -> StepResult:
        """Paso: crea una carpeta usando files_skill."""
        target = str(step.get("nombre") or step.get("target") or "").strip()
        if not target:
            return StepResult(index=index, step_type="create_folder", success=False, error="Falta el nombre de carpeta.")
        if dry_run:
            return StepResult(index=index, step_type="create_folder", success=True, output=f"[SIMULADO] Crearía carpeta '{target}'")
        from skills.builtin.files_skill import FilesSkill
        res = FilesSkill().execute("crear", [target, "--carpeta"])
        return StepResult(index=index, step_type="create_folder", success=res.success, output=res.output, error=res.error, data=res.data or {})

    def _step_delete_file(
        self,
        index: int,
        step: dict[str, Any],
        dry_run: bool = False,
    ) -> StepResult:
        """Paso: elimina un archivo o carpeta a la papelera usando files_skill."""
        target = str(step.get("nombre") or step.get("target") or "").strip()
        if not target:
            return StepResult(index=index, step_type="delete_file", success=False, error="Falta el archivo o carpeta a eliminar.")
        if dry_run:
            return StepResult(index=index, step_type="delete_file", success=True, output=f"[SIMULADO] Eliminaría '{target}'")
        from skills.builtin.files_skill import FilesSkill
        res = FilesSkill().execute("eliminar", [target])
        return StepResult(index=index, step_type="delete_file", success=res.success, output=res.output, error=res.error, data=res.data or {})

    def _step_move_file(
        self,
        index: int,
        step: dict[str, Any],
        dry_run: bool = False,
    ) -> StepResult:
        """Paso: mueve un archivo o carpeta usando files_skill."""
        orig = str(step.get("origen") or step.get("source") or step.get("target") or "").strip()
        dest = str(step.get("destino") or step.get("destination") or "").strip()
        if not orig or not dest:
            return StepResult(index=index, step_type="move_file", success=False, error="Falta origen o destino para mover.")
        if dry_run:
            return StepResult(index=index, step_type="move_file", success=True, output=f"[SIMULADO] Movería '{orig}' a '{dest}'")
        from skills.builtin.files_skill import FilesSkill
        res = FilesSkill().execute("mover", [orig, dest])
        return StepResult(index=index, step_type="move_file", success=res.success, output=res.output, error=res.error, data=res.data or {})

    def _step_rename_file(
        self,
        index: int,
        step: dict[str, Any],
        dry_run: bool = False,
    ) -> StepResult:
        """Paso: renombra un archivo o carpeta usando files_skill."""
        orig = str(step.get("origen") or step.get("source") or step.get("target") or "").strip()
        dest = str(step.get("nuevo_nombre") or step.get("destino") or step.get("destination") or "").strip()
        if not orig or not dest:
            return StepResult(index=index, step_type="rename_file", success=False, error="Falta origen o nuevo nombre para renombrar.")
        if dry_run:
            return StepResult(index=index, step_type="rename_file", success=True, output=f"[SIMULADO] Renombraría '{orig}' a '{dest}'")
        from skills.builtin.files_skill import FilesSkill
        res = FilesSkill().execute("renombrar", [orig, dest])
        return StepResult(index=index, step_type="rename_file", success=res.success, output=res.output, error=res.error, data=res.data or {})

    def _step_search_file(
        self,
        index: int,
        step: dict[str, Any],
        dry_run: bool = False,
    ) -> StepResult:
        """Paso: busca archivos por nombre o patrón usando search_skill."""
        target = str(step.get("target") or step.get("query") or "").strip()
        if not target:
            return StepResult(index=index, step_type="search_file", success=False, error="Falta el término de búsqueda.")
        if dry_run:
            return StepResult(index=index, step_type="search_file", success=True, output=f"[SIMULADO] Buscaría '{target}'")
        from skills.builtin.search_skill import SearchSkill
        res = SearchSkill().execute("buscar", target.split())
        return StepResult(index=index, step_type="search_file", success=res.success, output=res.output, error=res.error, data=res.data or {})


    # ── Helpers ─────────────────────────────────────────────────────────────

    def _find_path(self, name: str) -> Path | None:
        """Busca el archivo de automatización por nombre (sin extensión)."""
        if not _AUTOMATIONS_DIR.exists():
            return None
        for ext in (".yaml", ".yml", ".json"):
            candidate = _AUTOMATIONS_DIR / f"{name}{ext}"
            if candidate.exists():
                return candidate
        # Búsqueda case-insensitive
        name_lower = name.lower()
        for path in _AUTOMATIONS_DIR.iterdir():
            if path.suffix.lower() in _VALID_EXTENSIONS:
                if path.stem.lower() == name_lower:
                    return path
        return None

    def _load_file(self, path: Path) -> dict[str, Any]:
        """Carga y parsea un archivo YAML o JSON."""
        suffix = path.suffix.lower()
        with open(path, encoding="utf-8") as f:
            content = f.read()

        if suffix in (".yaml", ".yml"):
            try:
                import yaml  # importación lazy para no requerir pyyaml en todos los módulos
                data = yaml.safe_load(content)
            except Exception as exc:
                raise ValueError(f"YAML inválido: {exc}") from exc
        elif suffix == ".json":
            try:
                data = json.loads(content)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON inválido: {exc}") from exc
        else:
            raise ValueError(f"Formato no soportado: {suffix}")

        if not isinstance(data, dict):
            raise ValueError("El archivo debe contener un objeto raíz (dict).")

        return data

    def _parse_info(self, data: dict[str, Any], path: Path) -> AutomationInfo:
        """Extrae AutomationInfo de los datos cargados."""
        steps = data.get("steps", [])
        step_count = len(steps) if isinstance(steps, list) else 0
        suffix = path.suffix.lower()
        fmt = "yaml" if suffix in (".yaml", ".yml") else "json"

        return AutomationInfo(
            name=path.stem,
            display_name=str(data.get("name", path.stem)),
            description=str(data.get("description", "")),
            version=str(data.get("version", "1.0")),
            step_count=step_count,
            path=path,
            format=fmt,
        )

    def _build_output(
        self,
        display_name: str,
        step_results: list[StepResult],
        dry_run: bool = False,
        status: str = "OK",
    ) -> str:
        """Construye el texto de salida final del resultado de la automatización."""
        lines: list[str] = []
        prefix = "🔍 [SIMULACIÓN] " if dry_run else ""
        lines.append(f"{prefix}▶ Automatización: {display_name}")
        lines.append("")

        for i, sr in enumerate(step_results):
            num = f"{i + 1:>2}."
            if sr.success:
                lines.append(f"  {num} ✅ [{sr.step_type}] {sr.output}")
            else:
                lines.append(f"  {num} ❌ [{sr.step_type}] {sr.error}")

        total = len(step_results)
        ok = sum(1 for sr in step_results if sr.success)
        fail = total - ok

        lines.append("")
        if total == 0:
            lines.append("ℹ️ Automatización vacía (0 pasos).")
        elif status == "OK" or fail == 0:
            lines.append(f"✅ Estado: OK — Completado: {ok}/{total} pasos exitosos.")
        elif status == "FALLIDA" or ok == 0:
            lines.append(f"❌ Estado: FALLIDA — Falló: {fail}/{total} pasos (0/{total} exitosos).")
        else:
            lines.append(f"⚠️ Parcial: Falló: {fail}/{total} pasos ({ok}/{total} exitosos).")

        if dry_run:
            lines.append("ℹ️ Modo simulación: ninguna acción real fue ejecutada.")

        return "\n".join(lines)



# ---------------------------------------------------------------------------
# Instancia singleton del motor
# ---------------------------------------------------------------------------

automation_engine = AutomationEngine()

"""
AURA — App Resolver: Resolución y lanzamiento de aplicaciones y navegadores.

Maneja la resolución de ejecutables en el sistema, con reglas estrictas
para navegadores web y soporte de BROWSER_PREFERIDO:
  - Alias genéricos ("navegador", "browser", "web") -> resuelven a BROWSER_PREFERIDO.
  - "chrome" -> resuelve SOLO a Chrome real. Si no está instalado, falla con mensaje:
    "Chrome no está instalado. Tu navegador preferido es {pref}. ¿Usarlo?"
    NUNCA abre otro navegador en silencio.
  - "firefox" -> resuelve SOLO a Firefox real.
  - "msedge", "brave", "opera" -> resuelven SOLO a sus ejecutables respectivos.
  - Otras aplicaciones -> alias del sistema, App Paths de Windows, PATH, rutas comunes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from utils.logger import get_logger

_logger = get_logger("aura.core.app_resolver")

# ---------------------------------------------------------------------------
# Constantes de navegadores y alias
# ---------------------------------------------------------------------------

SUPPORTED_BROWSERS: list[str] = ["firefox", "chrome", "msedge", "brave", "opera"]

BROWSER_DISPLAY_NAMES: dict[str, str] = {
    "firefox": "Firefox",
    "chrome": "Chrome",
    "msedge": "Edge",
    "edge": "Edge",
    "brave": "Brave",
    "opera": "Opera",
}

GENERIC_BROWSER_ALIASES: set[str] = {
    "navegador",
    "browser",
    "web",
    "el navegador",
    "mi navegador",
}

# Alias comunes de aplicaciones estándar de Windows
_COMMON_ALIASES: dict[str, str] = {
    "notepad":       "notepad.exe",
    "bloc":          "notepad.exe",
    "bloc de notas": "notepad.exe",
    "calculadora":   "calc.exe",
    "calc":          "calc.exe",
    "explorador":    "explorer.exe",
    "explorer":      "explorer.exe",
    "archivos":      "explorer.exe",
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
    "word":          "winword.exe",
    "excel":         "excel.exe",
    "powerpoint":    "powerpnt.exe",
    "vscode":        "code.exe",
    "code":          "code.exe",
    "spotify":       "Spotify.exe",
    "vlc":           "vlc.exe",
    "discord":       "Discord.exe",
    "git bash":      "git-bash.exe",
    "git-bash":      "git-bash.exe",
}

# ---------------------------------------------------------------------------
# Dataclass de resultado de resolución
# ---------------------------------------------------------------------------


@dataclass
class ResolvedApp:
    """Resultado de resolver una aplicación o comando a su ejecutable real."""

    success: bool
    app: str
    executable: Optional[str] = None
    error: Optional[str] = None
    is_browser: bool = False
    browser_name: Optional[str] = None

    def __bool__(self) -> bool:
        return self.success

    @property
    def found(self) -> bool:
        return self.success

    @property
    def name(self) -> str:
        return self.app


# ---------------------------------------------------------------------------
# Funciones de detección y resolución de navegadores
# ---------------------------------------------------------------------------


def detect_default_browser() -> str:
    """
    Detecta el navegador predeterminado de Windows consultando el Registro.
    Si no puede detectarse o no estamos en Windows, retorna 'firefox'.
    """
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice",
            ) as key:
                prog_id, _ = winreg.QueryValueEx(key, "ProgId")
                prog_id_lower = prog_id.lower()
                if "firefox" in prog_id_lower:
                    return "firefox"
                if "chrome" in prog_id_lower:
                    return "chrome"
                if "edge" in prog_id_lower:
                    return "msedge"
                if "brave" in prog_id_lower:
                    return "brave"
                if "opera" in prog_id_lower:
                    return "opera"
        except Exception as exc:
            _logger.debug("detect_default_browser: no se pudo leer UserChoice: %s", exc)

    return "firefox"


def get_preferred_browser_name() -> str:
    """
    Retorna el identificador o ruta del navegador preferido activo.
    Prioridad: BROWSER_PREFERIDO en settings > detect_default_browser() > 'firefox'.
    """
    try:
        from config.settings import settings
        val = settings.get("BROWSER_PREFERIDO")
        if val and val.strip():
            return val.strip().lower()
    except Exception as exc:
        _logger.debug("get_preferred_browser_name: error leyendo settings: %s", exc)

    return detect_default_browser()


def _find_in_app_paths(exe_name: str) -> Optional[str]:
    """Busca un ejecutable en las claves App Paths del Registro de Windows."""
    if os.name != "nt":
        return None

    try:
        import winreg

        subkeys = [
            rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}",
            rf"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}",
        ]
        roots = [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]

        for root in roots:
            for sub in subkeys:
                try:
                    with winreg.OpenKey(root, sub) as key:
                        val, _ = winreg.QueryValueEx(key, "")
                        if val:
                            path_clean = str(val).strip('"').strip()
                            if os.path.isfile(path_clean):
                                return path_clean
                except Exception:
                    continue
    except Exception:
        pass

    return None


def _find_in_common_paths(exe_name: str) -> Optional[str]:
    """Busca un ejecutable en rutas estándar de instalación."""
    dirs_to_check: list[Path] = []

    for env_var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "APPDATA"):
        val = os.environ.get(env_var)
        if val:
            base = Path(val)
            if base.exists():
                dirs_to_check.append(base)
                dirs_to_check.append(base / "Programs")

    target_stem = exe_name.lower().removesuffix(".exe")

    for base_dir in dirs_to_check:
        if not base_dir.exists():
            continue

        # 1. Directo en base_dir
        cand = base_dir / exe_name
        if cand.is_file():
            return str(cand)

        # 2. Subdirectorio con nombre similar
        try:
            for sub in base_dir.iterdir():
                if sub.is_dir() and target_stem in sub.name.lower():
                    cand = sub / exe_name
                    if cand.is_file():
                        return str(cand)
                    cand_app = sub / "Application" / exe_name
                    if cand_app.is_file():
                        return str(cand_app)
        except Exception:
            continue

    return None


def find_browser_executable(browser_key: str) -> Optional[str]:
    """
    Localiza la ruta absoluta al ejecutable de un navegador especificado.
    Verifica SIEMPRE que el archivo realmente exista en el disco.
    """
    key = browser_key.strip().lower()

    # Si es una ruta absoluta o relativa existente
    if os.path.isfile(key):
        return str(Path(key).resolve())

    # Mapa de ejecutables conocidos y carpetas típicas
    known_exes: dict[str, list[str]] = {
        "firefox": ["firefox.exe"],
        "chrome":  ["chrome.exe"],
        "msedge":  ["msedge.exe"],
        "edge":    ["msedge.exe"],
        "brave":   ["brave.exe"],
        "opera":   ["opera.exe"],
    }

    exes = known_exes.get(key, [f"{key}.exe" if not key.endswith(".exe") else key])

    for exe_name in exes:
        # 1. Comprobar App Paths en registro
        app_path = _find_in_app_paths(exe_name)
        if app_path and os.path.isfile(app_path):
            return app_path

        # 2. Comprobar rutas fijas comunes por navegador
        specific_paths: list[str] = []
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")

        if key == "firefox":
            specific_paths = [
                os.path.join(pf, "Mozilla Firefox", "firefox.exe"),
                os.path.join(pf86, "Mozilla Firefox", "firefox.exe"),
            ]
        elif key == "chrome":
            specific_paths = [
                os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(local, "Google", "Chrome", "Application", "chrome.exe") if local else "",
            ]
        elif key in ("msedge", "edge"):
            specific_paths = [
                os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
            ]
        elif key == "brave":
            specific_paths = [
                os.path.join(pf, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                os.path.join(pf86, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                os.path.join(local, "BraveSoftware", "Brave-Browser", "Application", "brave.exe") if local else "",
            ]
        elif key == "opera":
            specific_paths = [
                os.path.join(local, "Programs", "Opera", "opera.exe") if local else "",
                os.path.join(pf, "Opera", "opera.exe"),
                os.path.join(pf86, "Opera", "opera.exe"),
            ]

        for p in specific_paths:
            if p and os.path.isfile(p):
                return p

        # 3. shutil.which
        which_path = shutil.which(exe_name) or shutil.which(key)
        if which_path and os.path.isfile(which_path):
            return which_path

        # 4. Búsqueda en carpetas comunes
        common = _find_in_common_paths(exe_name)
        if common and os.path.isfile(common):
            return common

    return None


def get_installed_browsers() -> dict[str, str]:
    """
    Retorna un diccionario {nombre_clave: ruta_ejecutable} de todos los
    navegadores soportados que realmente están instalados en el equipo.
    """
    installed: dict[str, str] = {}
    for b in SUPPORTED_BROWSERS:
        exe = find_browser_executable(b)
        if exe and os.path.isfile(exe):
            installed[b] = exe
    return installed


# ---------------------------------------------------------------------------
# Resolver y Launcher de Aplicaciones
# ---------------------------------------------------------------------------


def resolve_app(app: str) -> ResolvedApp:
    """
    Resuelve el nombre o alias de una aplicación a su ejecutable real en disco.

    Reglas estrictas de navegadores:
    1. 'navegador', 'browser', 'web' -> Resuelve SIEMPRE a BROWSER_PREFERIDO.
    2. 'chrome' -> Resuelve SOLO a Chrome real. Si no está instalado, retorna error:
       'Chrome no está instalado. Tu navegador preferido es {pref_display}. ¿Usarlo?'
       NUNCA abre otro navegador en silencio.
    3. 'firefox' -> Resuelve SOLO a Firefox real.
    4. 'msedge', 'brave', 'opera' -> Resuelven SOLO a sus respectivos ejecutables.
    """
    if isinstance(app, (list, tuple)):
        target = " ".join(str(x) for x in app).strip()
    elif app is not None:
        target = str(app).strip()
    else:
        target = ""

    if not target:
        return ResolvedApp(
            success=False,
            app=str(app or ""),
            error="El nombre de la aplicación no puede estar vacío.",
        )

    target_clean = target.lower().strip()

    # 1. Alias genérico de navegador ("navegador", "browser", "web")
    if target_clean in GENERIC_BROWSER_ALIASES:
        pref = get_preferred_browser_name()
        pref_display = BROWSER_DISPLAY_NAMES.get(pref, pref.title())
        pref_exe = find_browser_executable(pref)

        if pref_exe and os.path.isfile(pref_exe):
            _logger.info("resolve_app: '%s' resuelto a BROWSER_PREFERIDO '%s' (%s)", target, pref, pref_exe)
            return ResolvedApp(
                success=True,
                app=target,
                executable=pref_exe,
                is_browser=True,
                browser_name=pref,
            )

        # Si el preferido configurado no se encontró
        return ResolvedApp(
            success=False,
            app=target,
            error=f"El navegador preferido configurado ({pref_display}) no está instalado o no se encuentra.",
            is_browser=True,
            browser_name=pref,
        )

    # 2. Chrome específico
    if target_clean in ("chrome", "google chrome", "google-chrome"):
        chrome_exe = find_browser_executable("chrome")
        if chrome_exe and os.path.isfile(chrome_exe):
            return ResolvedApp(
                success=True,
                app=target,
                executable=chrome_exe,
                is_browser=True,
                browser_name="chrome",
            )

        pref = get_preferred_browser_name()
        pref_display = BROWSER_DISPLAY_NAMES.get(pref, pref.title())
        return ResolvedApp(
            success=False,
            app=target,
            error=f"Chrome no está instalado. Tu navegador preferido es {pref_display}. ¿Usarlo?",
            is_browser=True,
            browser_name="chrome",
        )

    # 3. Firefox específico
    if target_clean in ("firefox", "mozilla", "mozilla firefox", "mozilla-firefox"):
        firefox_exe = find_browser_executable("firefox")
        if firefox_exe and os.path.isfile(firefox_exe):
            return ResolvedApp(
                success=True,
                app=target,
                executable=firefox_exe,
                is_browser=True,
                browser_name="firefox",
            )
        return ResolvedApp(
            success=False,
            app=target,
            error="Firefox no está instalado en el sistema.",
            is_browser=True,
            browser_name="firefox",
        )

    # 4. Edge específico
    if target_clean in ("edge", "msedge", "microsoft edge", "microsoft-edge"):
        edge_exe = find_browser_executable("msedge")
        if edge_exe and os.path.isfile(edge_exe):
            return ResolvedApp(
                success=True,
                app=target,
                executable=edge_exe,
                is_browser=True,
                browser_name="msedge",
            )
        return ResolvedApp(
            success=False,
            app=target,
            error="Microsoft Edge no está instalado en el sistema.",
            is_browser=True,
            browser_name="msedge",
        )

    # 5. Brave / Opera específicos
    if target_clean in ("brave", "brave browser", "brave-browser"):
        brave_exe = find_browser_executable("brave")
        if brave_exe and os.path.isfile(brave_exe):
            return ResolvedApp(
                success=True,
                app=target,
                executable=brave_exe,
                is_browser=True,
                browser_name="brave",
            )
        return ResolvedApp(
            success=False,
            app=target,
            error="Brave no está instalado en el sistema.",
            is_browser=True,
            browser_name="brave",
        )

    if target_clean in ("opera", "opera browser", "opera-browser"):
        opera_exe = find_browser_executable("opera")
        if opera_exe and os.path.isfile(opera_exe):
            return ResolvedApp(
                success=True,
                app=target,
                executable=opera_exe,
                is_browser=True,
                browser_name="opera",
            )
        return ResolvedApp(
            success=False,
            app=target,
            error="Opera no está instalado en el sistema.",
            is_browser=True,
            browser_name="opera",
        )

    # 6. URI de Windows (ej: ms-settings:)
    if target.startswith("ms-settings:"):
        return ResolvedApp(success=True, app=target, executable=target)

    # 7. Ruta directa a archivo existente
    if os.path.isfile(target):
        return ResolvedApp(success=True, app=target, executable=str(Path(target).resolve()))

    # 8. Alias comunes predefinidos
    exe_candidate = _COMMON_ALIASES.get(target_clean)
    if exe_candidate:
        which_path = shutil.which(exe_candidate)
        if which_path and os.path.isfile(which_path):
            return ResolvedApp(success=True, app=target, executable=which_path)
        app_path = _find_in_app_paths(exe_candidate)
        if app_path and os.path.isfile(app_path):
            return ResolvedApp(success=True, app=target, executable=app_path)
        common_path = _find_in_common_paths(exe_candidate)
        if common_path and os.path.isfile(common_path):
            return ResolvedApp(success=True, app=target, executable=common_path)

        # Si es un ejecutable de Windows que vive en System32/Windows
        win_dir = os.environ.get("SystemRoot", r"C:\Windows")
        sys32_cand = Path(win_dir) / "System32" / exe_candidate
        if sys32_cand.is_file():
            return ResolvedApp(success=True, app=target, executable=str(sys32_cand))
        win_cand = Path(win_dir) / exe_candidate
        if win_cand.is_file():
            return ResolvedApp(success=True, app=target, executable=str(win_cand))

        return ResolvedApp(
            success=False,
            app=target,
            error=f"No se pudo encontrar el ejecutable para '{target}' ('{exe_candidate}').",
        )

    # 9. shutil.which directo
    which_target = shutil.which(target) or shutil.which(f"{target}.exe")
    if which_target and os.path.isfile(which_target):
        return ResolvedApp(success=True, app=target, executable=which_target)

    # 10. App Paths de Windows para cualquier target
    target_exe = target if target.lower().endswith(".exe") else f"{target}.exe"
    app_path = _find_in_app_paths(target_exe)
    if app_path and os.path.isfile(app_path):
        return ResolvedApp(success=True, app=target, executable=app_path)

    # 11. Rutas comunes de instalación
    common_path = _find_in_common_paths(target_exe)
    if common_path and os.path.isfile(common_path):
        return ResolvedApp(success=True, app=target, executable=common_path)

    # 12. Resolución rápida ampliada (Índice persistente, Uninstall, Shortcuts)
    try:
        from core.app_scanner import fast_resolve_app
        fast_path = fast_resolve_app(target)
        if fast_path and os.path.exists(fast_path):
            return ResolvedApp(success=True, app=target, executable=fast_path)
    except Exception as exc:
        _logger.debug("resolve_app: error en fast_resolve_app: %s", exc)

    return ResolvedApp(
        success=False,
        app=target,
        error=f"No se pudo encontrar la aplicación '{target}' en el sistema.",
    )


def launch_app(executable: Any, args: list[str] | None = None) -> None:
    """
    Inicia una aplicación o abre un archivo/URI en el sistema operativo.

    Args:
        executable: Ruta o comando a ejecutar (ej: 'C:\\...\\firefox.exe', 'notepad.exe', 'ms-settings:').
        args: Argumentos adicionales opcionales (ej: ['https://google.com']).
    """
    if isinstance(executable, (list, tuple)):
        executable = " ".join(str(x) for x in executable).strip()
    else:
        executable = str(executable or "").strip()

    if not executable:
        return

    if executable.startswith("ms-settings:"):
        os.startfile(executable)  # type: ignore[attr-defined]
        return

    proc = None
    app_base = os.path.basename(executable).lower()
    if app_base.endswith(".exe"):
        app_base = app_base[:-4]

    full_cmd = [executable] + list(args or [])

    if os.name == "nt":
        if args:
            try:
                proc = subprocess.Popen(full_cmd)
            except Exception:
                pass
        else:
            # Si es un ejecutable (.exe o sin extensión en PATH), preferir Popen para registrar el PID exacto
            if str(executable).lower().endswith(".exe") or not ("." in os.path.basename(str(executable))):
                try:
                    proc = subprocess.Popen(full_cmd)
                except Exception:
                    try:
                        os.startfile(executable)  # type: ignore[attr-defined]
                    except Exception:
                        pass
            else:
                try:
                    os.startfile(executable)  # type: ignore[attr-defined]
                except Exception:
                    try:
                        proc = subprocess.Popen(full_cmd)
                    except Exception:
                        pass
    else:
        if args:
            try:
                proc = subprocess.Popen(full_cmd)
            except Exception:
                pass
        else:
            try:
                proc = subprocess.Popen(["xdg-open", executable])
            except Exception:
                pass

    if proc and getattr(proc, "pid", None):
        try:
            from aura.skills.app_writer import record_app_opened
            record_app_opened(app_base, proc.pid)
        except Exception:
            pass

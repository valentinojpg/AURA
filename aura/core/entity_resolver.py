"""
AURA — EntityResolver: Resolución de Entidades y Destinos de Acción.

Resuelve nombres de aplicaciones, procesos, URLs, archivos y carpetas
siguiendo un orden estricto de precedencia:
  a) URL o dominio -> open_url (agrega https:// si falta)
  b) Alias built-in (notepad, calc, chrome, edge, vscode, spotify...)
  c) Programas favoritos de la memoria (fases 17/28 - data/programs.json)
  d) shutil.which(target) y which(target + ".exe")
  e) Procesos corriendo (psutil) para close_app
  f) Rutas comunes: Program Files, Program Files (x86), LOCALAPPDATA\\Programs

Si el intent es claro pero el target NO resuelve, devuelve resolved=False.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from aura.core.intent_router import Intent, normalize
from utils.logger import get_logger

_logger = get_logger("aura.core.entity_resolver")

# Directorio raíz del proyecto y archivo de programas de usuario
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
_PROGRAMS_FILE = _ROOT_DIR / "data" / "programs.json"

# Alias predefinidos del sistema (built-in)
BUILTIN_ALIASES: dict[str, str] = {
    # Accesorios y herramientas de Windows
    "notepad":        "notepad.exe",
    "bloc":           "notepad.exe",
    "bloc de notas":  "notepad.exe",
    "calculadora":    "calc.exe",
    "calc":           "calc.exe",
    "explorador":     "explorer.exe",
    "explorer":       "explorer.exe",
    "archivos":       "explorer.exe",
    "paint":          "mspaint.exe",
    "mspaint":        "mspaint.exe",
    "cmd":            "cmd.exe",
    "consola":        "cmd.exe",
    "terminal":       "cmd.exe",
    "powershell":     "powershell.exe",
    "ps":             "powershell.exe",
    "wordpad":        "wordpad.exe",
    "recortes":       "snippingtool.exe",
    "snipping":       "snippingtool.exe",
    "teclado":        "osk.exe",
    "osk":            "osk.exe",
    # Navegadores web
    "navegador":      "navegador",
    "browser":        "navegador",
    "web":            "navegador",
    "chrome":         "chrome.exe",
    "google chrome":  "chrome.exe",

    "firefox":        "firefox.exe",
    "mozilla":        "firefox.exe",
    "edge":           "msedge.exe",
    "microsoft edge": "msedge.exe",
    "brave":          "brave.exe",
    "opera":          "opera.exe",
    # Suite Ofimática
    "word":           "winword.exe",
    "excel":          "excel.exe",
    "powerpoint":     "powerpnt.exe",
    # Desarrollo
    "vscode":         "code.exe",
    "code":           "code.exe",
    "visual studio code": "code.exe",
    "git bash":       "git-bash.exe",
    # Multimedia & Comunicación
    "spotify":        "Spotify.exe",
    "vlc":            "vlc.exe",
    "discord":        "Discord.exe",
    "teams":          "Teams.exe",
    "zoom":           "Zoom.exe",
    "telegram":       "Telegram.exe",
    "whatsapp":       "WhatsApp.exe",
    # Configuración de Windows
    "configuracion":  "ms-settings:",
    "settings":       "ms-settings:",
    "pantalla":       "ms-settings:display",
    "wifi":           "ms-settings:network-wifi",
    "bluetooth":      "ms-settings:bluetooth",
    "sonido":         "ms-settings:sound",
    "actualizacion":  "ms-settings:windowsupdate",
}

_COMMON_TLDS = {
    "com", "org", "net", "edu", "gov", "mil", "int",
    "ar", "es", "co", "mx", "cl", "io", "ai", "app", "dev",
    "me", "info", "biz", "xyz", "tv", "online", "site", "tech"
}

# Alias de sitios web reconocidos y sus URLs directas (Fase 71)
SITE_ALIASES_MAP: dict[str, str] = {
    "youtube music": "https://music.youtube.com",
    "yt music":      "https://music.youtube.com",
    "youtube":       "https://www.youtube.com",
    "google":        "https://www.google.com",
    "github":        "https://github.com",
    "wikipedia":     "https://es.wikipedia.org",
    "gmail":         "https://mail.google.com",
    "calendar":      "https://calendar.google.com",
    "drive":         "https://drive.google.com",
    "whatsapp web":  "https://web.whatsapp.com",
    "whatsapp":      "https://web.whatsapp.com",
    "chatgpt":       "https://chatgpt.com",
}


@dataclass
class ResolvedEntity:
    """
    Resultado de la resolución de una entidad / target de un comando.

    Attributes:
        resolved:    True si la entidad fue resuelta con éxito.
        intent:      Nombre de la intención asociada.
        target:      Texto objetivo original o procesado.
        executable:  Ruta, URL o nombre del ejecutable/proceso resuelto.
        skill_name:  Nombre de la skill que procesará la acción.
        command:     Comando específico de la skill a ejecutar.
        args:        Argumentos formateados para la skill.
        extra:       Metadatos adicionales del resultado.
    """

    resolved: bool
    intent: str
    target: str
    executable: Optional[str] = None
    skill_name: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.resolved


def is_url_or_domain(text: str) -> bool:
    """Detecta si el texto es una URL completa o un nombre de dominio."""
    if not text:
        return False
    t = text.strip()
    if t.startswith(("http://", "https://", "ftp://", "www.")):
        return True

    # Comprobar formato dominio: algo.tld (ej: youtube.com)
    domain_part = t.split("/")[0]
    parts = domain_part.split(".")
    if len(parts) >= 2:
        tld = parts[-1].lower()
        if tld in _COMMON_TLDS and " " not in domain_part:
            return True
    return False


def _normalize_url(url: str) -> str:
    """Asegura el esquema https:// si falta."""
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("ftp://")):
        return f"https://{url}"
    return url


def _load_user_favorites() -> dict[str, str]:
    """Carga los alias de programas guardados por el usuario en data/programs.json."""
    if not _PROGRAMS_FILE.exists():
        return {}
    try:
        with open(_PROGRAMS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                # Normalizar keys a minúsculas y sin tildes
                return {normalize(k): str(v) for k, v in data.items()}
    except Exception as e:
        _logger.warning(f"EntityResolver: error leyendo programs.json: {e}")
    return {}


def _search_running_process(target: str) -> Optional[str]:
    """Busca si hay un proceso en ejecución que coincida con el target."""
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return None

    target_clean = normalize(target)
    target_exe = target_clean if target_clean.endswith(".exe") else f"{target_clean}.exe"

    for proc in psutil.process_iter(["name", "pid"]):
        try:
            pname = proc.name()
            pname_norm = normalize(pname)
            if pname_norm == target_clean or pname_norm == target_exe or target_clean in pname_norm:
                return pname
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
            continue
    return None


def _search_common_program_paths(target: str) -> Optional[str]:
    """Busca el ejecutable en rutas comunes de instalación en Windows."""
    target_clean = target.strip()
    target_exe = target_clean if target_clean.lower().endswith(".exe") else f"{target_clean}.exe"

    dirs_to_check: list[Path] = []

    pf = os.environ.get("ProgramFiles")
    if pf:
        dirs_to_check.append(Path(pf))
    pf86 = os.environ.get("ProgramFiles(x86)")
    if pf86:
        dirs_to_check.append(Path(pf86))
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        dirs_to_check.append(Path(local_app) / "Programs")
    app_data = os.environ.get("APPDATA")
    if app_data:
        dirs_to_check.append(Path(app_data) / "Programs")

    for base_dir in dirs_to_check:
        if not base_dir.exists():
            continue

        # 1. Chequeo directo en la carpeta base
        candidate = base_dir / target_exe
        if candidate.is_file():
            return str(candidate)

        # 2. Subcarpeta con el nombre del target: base_dir / target / target.exe
        sub_candidate = base_dir / target_clean / target_exe
        if sub_candidate.is_file():
            return str(sub_candidate)

        # 3. Exploración de primer nivel de subcarpetas
        try:
            for sub in base_dir.iterdir():
                if sub.is_dir():
                    cand = sub / target_exe
                    if cand.is_file():
                        return str(cand)
        except Exception:
            continue

    return None


class EntityResolver:
    """
    Motor de resolución de entidades para comandos de AURA.

    Resuelve targets siguiendo la precedencia especificada:
      a) URL o dominio
      b) Alias built-in
      c) Programas favoritos de memoria
      d) shutil.which
      e) Procesos corriendo (psutil)
      f) Rutas comunes del sistema
    """

    def resolve(self, intent: Union[Intent, str], target: Optional[str] = None) -> ResolvedEntity:
        """
        Resuelve una entidad en base a su intención y nombre objetivo.

        Args:
            intent: Objeto Intent o nombre de la intención como string.
            target: Nombre del target (si no se incluye, se toma de Intent.target).

        Returns:
            ResolvedEntity con resolved=True si pudo resolver, o resolved=False si no.
        """
        if isinstance(target, (list, tuple)):
            target_str = " ".join(str(x) for x in target).strip()
        elif target is not None:
            target_str = str(target).strip()
        elif isinstance(intent, Intent):
            if isinstance(intent.target, (list, tuple)):
                target_str = " ".join(str(x) for x in intent.target).strip()
            else:
                target_str = str(intent.target or "").strip()
        else:
            target_str = ""

        if isinstance(intent, Intent):
            intent_name = intent.nombre
        else:
            intent_name = str(intent)

        target_str = target_str.strip()

        # ── Intenciones de Aplicaciones y Escritura ───────────────────────────
        if intent_name == "write_in_app":
            if not target_str:
                return ResolvedEntity(resolved=False, intent=intent_name, target=target_str)
            texto = ""
            if isinstance(intent, Intent) and hasattr(intent, "extra") and intent.extra:
                texto = intent.extra.get("texto", "")
            from core.app_resolver import resolve_app
            app_res = resolve_app(target_str)
            app_name = app_res.name if app_res.found else target_str
            app_exe = app_res.executable if app_res.found else target_str
            return ResolvedEntity(
                resolved=True,
                intent=intent_name,
                target=app_name,
                executable=app_exe,
                skill_name="app_writer",
                command="write_in_app",
                args=[app_name, texto],
                extra={"app": app_name, "texto": texto, "executable": app_exe},
            )

        if intent_name == "save_app_doc":
            app_name = target_str or ""
            filename = ""
            destination = ""
            if isinstance(intent, Intent) and hasattr(intent, "extra") and intent.extra:
                app_name = intent.extra.get("app") or app_name
                filename = intent.extra.get("filename") or intent.extra.get("nombre") or ""
                destination = intent.extra.get("destination") or intent.extra.get("destino") or ""

            from core.app_resolver import resolve_app
            if app_name:
                app_res = resolve_app(app_name)
                app_target = app_res.name if app_res.found else app_name
                app_exe = app_res.executable if app_res.found else app_name
            else:
                app_target = ""
                app_exe = ""

            return ResolvedEntity(
                resolved=True,
                intent=intent_name,
                target=app_target or "la ventana activa",
                executable=app_exe or app_target,
                skill_name="app_saver",
                command="save_app_doc",
                args=[app_target, filename, destination],
                extra={
                    "app": app_target,
                    "filename": filename,
                    "destination": destination,
                    "executable": app_exe,
                },
            )

        # ── Intenciones de Archivos y Carpetas ─────────────────────────────────
        if intent_name == "create_folder":
            if not target_str:
                return ResolvedEntity(resolved=False, intent=intent_name, target=target_str)
            from aura.core.intent_router import is_valid_filename
            if not is_valid_filename(target_str):
                return ResolvedEntity(
                    resolved=False,
                    intent=intent_name,
                    target=target_str,
                    extra={"invalid_filename": True},
                )
            clean_name = re.sub(r'[<>:"|?*]', '_', target_str)
            if len(clean_name) > 80:
                clean_name = clean_name[:80]
            return ResolvedEntity(
                resolved=True,
                intent=intent_name,
                target=clean_name,
                executable=clean_name,
                skill_name="files_skill",
                command="crear",
                args=[clean_name, "--carpeta"],
            )

        if intent_name == "create_file":
            if not target_str:
                return ResolvedEntity(resolved=False, intent=intent_name, target=target_str)
            from aura.core.intent_router import is_valid_filename
            if not is_valid_filename(target_str):
                return ResolvedEntity(
                    resolved=False,
                    intent=intent_name,
                    target=target_str,
                    extra={"invalid_filename": True},
                )
            clean_name = re.sub(r'[<>:"|?*]', '_', target_str)
            if len(clean_name) > 80:
                if "." in clean_name:
                    base, ext = clean_name.rsplit(".", 1)
                    clean_name = base[: 80 - len(ext) - 1] + "." + ext
                else:
                    clean_name = clean_name[:80]
            return ResolvedEntity(
                resolved=True,
                intent=intent_name,
                target=clean_name,
                executable=clean_name,
                skill_name="files_skill",
                command="crear",
                args=[clean_name],
            )

        if intent_name == "delete_file":
            if not target_str:
                return ResolvedEntity(resolved=False, intent=intent_name, target=target_str)
            return ResolvedEntity(
                resolved=True,
                intent=intent_name,
                target=target_str,
                executable=target_str,
                skill_name="files_skill",
                command="eliminar",
                args=[target_str],
            )

        if intent_name == "search_file":
            if not target_str:
                return ResolvedEntity(resolved=False, intent=intent_name, target=target_str)
            args = target_str.split()
            return ResolvedEntity(
                resolved=True,
                intent=intent_name,
                target=target_str,
                executable=target_str,
                skill_name="search_skill",
                command="buscar",
                args=args,
            )

        if intent_name == "move_file":
            if not target_str:
                return ResolvedEntity(resolved=False, intent=intent_name, target=target_str)
            parts = re.split(r"\s+(?:a|hacia|en)\s+", target_str, maxsplit=1)
            if len(parts) == 2:
                orig, dest = parts[0].strip(), parts[1].strip()
                return ResolvedEntity(
                    resolved=True,
                    intent=intent_name,
                    target=target_str,
                    executable=f"{orig} -> {dest}",
                    skill_name="files_skill",
                    command="mover",
                    args=[orig, dest],
                )
            tokens = target_str.split()
            if len(tokens) >= 2:
                return ResolvedEntity(
                    resolved=True,
                    intent=intent_name,
                    target=target_str,
                    executable=f"{tokens[0]} -> {tokens[1]}",
                    skill_name="files_skill",
                    command="mover",
                    args=[tokens[0], tokens[1]],
                )
            return ResolvedEntity(resolved=False, intent=intent_name, target=target_str)

        if intent_name == "rename_file":
            if not target_str:
                return ResolvedEntity(resolved=False, intent=intent_name, target=target_str)
            parts = re.split(r"\s+(?:a|como|por)\s+", target_str, maxsplit=1)
            if len(parts) == 2:
                orig, dest = parts[0].strip(), parts[1].strip()
                return ResolvedEntity(
                    resolved=True,
                    intent=intent_name,
                    target=target_str,
                    executable=f"{orig} -> {dest}",
                    skill_name="files_skill",
                    command="renombrar",
                    args=[orig, dest],
                )
            tokens = target_str.split()
            if len(tokens) >= 2:
                return ResolvedEntity(
                    resolved=True,
                    intent=intent_name,
                    target=target_str,
                    executable=f"{tokens[0]} -> {tokens[1]}",
                    skill_name="files_skill",
                    command="renombrar",
                    args=[tokens[0], tokens[1]],
                )
            return ResolvedEntity(resolved=False, intent=intent_name, target=target_str)

        # ── Resolución de Reproducción Multimedia (Fase 71) ─────────────────
        if intent_name == "media_play":
            if not target_str:
                return ResolvedEntity(resolved=False, intent=intent_name, target=target_str)
            extra_dict = intent.extra if isinstance(intent, Intent) else {}
            query = extra_dict.get("query") or target_str
            service = extra_dict.get("service") or ""
            args = [query]
            if service:
                args.extend(["--service", service])
            return ResolvedEntity(
                resolved=True,
                intent="media_play",
                target=query,
                executable=f"media_play:{query}",
                skill_name="media_play",
                command="reproducir",
                args=args,
                extra={"query": query, "service": service},
            )

        # ── Resolución de Aplicaciones, Procesos y URLs ───────────────────────
        norm_target = normalize(target_str)
        target_lower = target_str.lower().strip()

        # a) URL, dominio o alias web -> open_url (agregar https:// si falta)
        if intent_name == "open_url" or is_url_or_domain(target_str) or target_lower in SITE_ALIASES_MAP:
            if target_lower in SITE_ALIASES_MAP:
                url = SITE_ALIASES_MAP[target_lower]
            else:
                url = _normalize_url(target_str)
            return ResolvedEntity(
                resolved=True,
                intent="open_url",
                target=target_str,
                executable=url,
                skill_name="web_skill",
                command="abrir-url",
                args=[url],
            )

        # b) Resolución de navegadores y alias ("navegador", "browser", "web", "chrome", "firefox", etc.)
        from core.app_resolver import resolve_app, GENERIC_BROWSER_ALIASES

        is_browser_target = (
            norm_target in GENERIC_BROWSER_ALIASES
            or norm_target in ("chrome", "google chrome", "firefox", "mozilla", "mozilla firefox", "edge", "msedge", "microsoft edge", "brave", "opera")
        )
        if is_browser_target:
            app_res = resolve_app(target_str)
            if intent_name == "open_app":
                if app_res.success:
                    return ResolvedEntity(
                        resolved=True,
                        intent="open_app",
                        target=target_str,
                        executable=app_res.executable,
                        skill_name="system_skill",
                        command="abrir",
                        args=[app_res.executable],
                        extra={"is_browser": True, "browser_name": app_res.browser_name},
                    )
                else:
                    return ResolvedEntity(
                        resolved=False,
                        intent="open_app",
                        target=target_str,
                        extra={"error": app_res.error, "is_browser": True},
                    )
            elif intent_name == "close_app":
                if app_res.success and app_res.executable:
                    proc_name = Path(app_res.executable).name
                else:
                    proc_name = f"{norm_target}.exe" if not norm_target.endswith(".exe") else norm_target
                return ResolvedEntity(
                    resolved=True,
                    intent="close_app",
                    target=target_str,
                    executable=proc_name,
                    skill_name="system_skill",
                    command="cerrar",
                    args=[proc_name],
                )

        # c) Alias built-in (notepad, calc, vscode, spotify...)
        target_no_exe = norm_target[:-4] if norm_target.endswith(".exe") else norm_target
        if norm_target in BUILTIN_ALIASES:
            exe = BUILTIN_ALIASES[norm_target]
            return self._build_app_result(intent_name, target_str, exe, "system_skill")
        if target_no_exe in BUILTIN_ALIASES:
            exe = BUILTIN_ALIASES[target_no_exe]
            return self._build_app_result(intent_name, target_str, exe, "system_skill")


        # c) Programas favoritos de la memoria (fases 17/28)
        user_favorites = _load_user_favorites()
        if norm_target in user_favorites:
            fav_path = user_favorites[norm_target]
            return self._build_app_result(intent_name, target_str, fav_path, "programs_skill", command_open="programa", open_arg=norm_target)
        if target_no_exe in user_favorites:
            fav_path = user_favorites[target_no_exe]
            return self._build_app_result(intent_name, target_str, fav_path, "programs_skill", command_open="programa", open_arg=target_no_exe)

        # d) shutil.which(target) y which(target + ".exe")
        which_path = shutil.which(target_str)
        if not which_path and not target_str.lower().endswith(".exe"):
            which_path = shutil.which(f"{target_str}.exe")
        if which_path:
            exe_name = Path(which_path).name if intent_name == "close_app" else which_path
            return self._build_app_result(intent_name, target_str, exe_name, "system_skill")

        # e) Procesos corriendo (psutil) para close_app
        if intent_name == "close_app":
            running_proc = _search_running_process(target_str)
            if running_proc:
                return ResolvedEntity(
                    resolved=True,
                    intent="close_app",
                    target=target_str,
                    executable=running_proc,
                    skill_name="system_skill",
                    command="cerrar",
                    args=[running_proc],
                )

        # f) Rutas comunes: Program Files, Program Files (x86), LOCALAPPDATA\Programs
        common_path = _search_common_program_paths(target_str)
        if common_path:
            exe_name = Path(common_path).name if intent_name == "close_app" else common_path
            return self._build_app_result(intent_name, target_str, exe_name, "system_skill")

        # Si el intent era close_app y el usuario indicó explícitamente un .exe:
        if intent_name == "close_app" and target_str.lower().endswith(".exe"):
            return ResolvedEntity(
                resolved=True,
                intent="close_app",
                target=target_str,
                executable=target_str,
                skill_name="system_skill",
                command="cerrar",
                args=[target_str],
            )

        # g) Resolución rápida ampliada (app_index.json, Uninstall registry, .lnk de inicio/escritorio)
        if intent_name == "open_app":
            try:
                from core.app_scanner import fast_resolve_app
                fast_app = fast_resolve_app(target_str)
                if fast_app and os.path.exists(fast_app):
                    return self._build_app_result(intent_name, target_str, fast_app, "system_skill")
            except Exception as e:
                _logger.debug("EntityResolver: error en fast_resolve_app: %s", e)

        # Si el intent es claro pero el target NO resuelve:
        _logger.debug(
            f"EntityResolver: intent='{intent_name}' con target='{target_str}' no resolvió en ninguna regla rápida."
        )
        return ResolvedEntity(
            resolved=False,
            intent=intent_name,
            target=target_str,
            extra={"needs_deep_scan": (intent_name == "open_app")},
        )

    def _build_app_result(
        self,
        intent_name: str,
        target_str: str,
        executable: str,
        skill_name: str,
        command_open: str = "abrir",
        open_arg: Optional[str] = None,
    ) -> ResolvedEntity:
        """Construye el ResolvedEntity adecuado según sea open_app o close_app."""
        if intent_name == "close_app":
            # Para cerrar siempre usamos system_skill con comando 'cerrar'
            proceso = Path(executable).name if os.path.sep in executable or "/" in executable else executable
            return ResolvedEntity(
                resolved=True,
                intent="close_app",
                target=target_str,
                executable=proceso,
                skill_name="system_skill",
                command="cerrar",
                args=[proceso],
            )
        else:
            # open_app
            arg_val = open_arg if open_arg is not None else executable
            return ResolvedEntity(
                resolved=True,
                intent="open_app",
                target=target_str,
                executable=executable,
                skill_name=skill_name,
                command=command_open,
                args=[arg_val],
            )


# Singleton global
entity_resolver = EntityResolver()


def resolve(intent: Union[Intent, str], target: Optional[str] = None) -> ResolvedEntity:
    """Función de conveniencia para resolver entidades con el EntityResolver singleton."""
    return entity_resolver.resolve(intent, target)

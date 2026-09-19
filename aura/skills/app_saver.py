"""
AURA — Skill AppSaver (save_app_doc) (Fase 63)

Permite guardar el contenido de texto de una aplicación abierta (como Notepad)
directamente en un archivo en el Escritorio, Descargas u otra carpeta real,
sin requerir automation frágil de diálogos 'Guardar como'.

Técnica Win32:
  1. Identifica el PID de la instancia (priorizando last_opened_apps de Fase 61).
  2. Localiza el HWND de la ventana principal y su control de edición hijo ('Edit', 'RichEdit', etc.).
  3. Extrae el texto mediante WM_GETTEXTLENGTH y WM_GETTEXT con ctypes SendMessageW.
  4. Resuelve la carpeta destino real mediante SHGetKnownFolderPath (Escritorio, Descargas, etc.).
  5. Genera o valida el nombre de archivo sin admitir frases del usuario.
  6. Escribe el archivo con codificación UTF-8 y confirma con ruta completa y PID.
"""

from __future__ import annotations

import ctypes
import os
import re
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import psutil

from skills.skill_base import BaseSkill, SkillMeta, SkillResult, CATEGORY_SYSTEM
from utils.logger import get_logger
from aura.core.filename_guard import (
    is_valid_strict_filename,
    resolve_folder_alias,
)

_logger = get_logger("aura.skills.app_saver")

user32 = ctypes.windll.user32 if os.name == "nt" else None

WM_GETTEXTLENGTH = 0x000E
WM_GETTEXT = 0x000D


def find_edit_control(hwnd: int) -> int:
    """
    Busca la ventana hija de edición ('Edit', 'RichEdit', 'RichEditD2DPT', 'Scintilla').
    Retorna el HWND del control o 0 si no se encuentra.
    """
    if not hwnd or os.name != "nt" or not user32:
        return 0

    # 1. Intento directo con FindWindowExW para clase Edit estándar
    h_edit = user32.FindWindowExW(hwnd, 0, "Edit", None)
    if h_edit:
        return h_edit

    # 2. Búsqueda recursiva en hijos por clase
    found_hwnd = 0

    def _child_cb(ch: int, lp: int) -> int:
        nonlocal found_hwnd
        buf_cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(ch, buf_cls, 256)
        cls_name = buf_cls.value.lower()
        if any(c in cls_name for c in ("edit", "rich", "scintilla", "document")):
            found_hwnd = ch
            return 0  # Detener enumeración
        return 1

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)
    user32.EnumChildWindows(hwnd, WNDENUMPROC(_child_cb), 0)
    return found_hwnd


def extract_text_from_window(hwnd: int) -> Tuple[bool, str]:
    """
    Extrae el texto de un control de edición o ventana mediante WM_GETTEXTLENGTH + WM_GETTEXT.
    Retorna (True, texto) si fue exitoso, o (False, error).
    """
    if not hwnd or os.name != "nt" or not user32:
        return False, "HWND inválido o sistema no Windows"

    target_ctrl = find_edit_control(hwnd)
    if not target_ctrl:
        # Intentar leer directo de la ventana principal si no hay control hijo
        target_ctrl = hwnd

    try:
        length = user32.SendMessageW(target_ctrl, WM_GETTEXTLENGTH, 0, 0)
        if length < 0:
            return False, "No se pudo consultar la longitud del texto"

        buf = ctypes.create_unicode_buffer(length + 1)
        user32.SendMessageW(target_ctrl, WM_GETTEXT, length + 1, ctypes.addressof(buf))
        return True, buf.value
    except Exception as e:
        _logger.error(f"AppSaver: error extrayendo texto vía SendMessageW: {e}")
        return False, str(e)


def resolve_running_app_pid(app_name: str = "") -> Tuple[Optional[int], str]:
    """
    Identifica la instancia activa de la aplicación:
      1. Si se indicó app_name, busca instancias activas de ese proceso.
      2. Prioriza instancias registradas en last_opened_apps (abiertas por AURA).
      3. Si app_name está vacío, toma la app abierta más recientemente en last_opened_apps
         o busca procesos 'notepad.exe' activos.
    """
    from aura.skills.app_writer import last_opened_apps, get_last_opened_pid

    from aura.core.app_capabilities import normalize_app_name

    raw_key = app_name.lower().strip() if app_name else ""
    if raw_key.endswith(".exe"):
        raw_key = raw_key[:-4]

    # Alias comunes y anáfora
    if raw_key in ("la ventana", "esta ventana", "lo que escribiste", "el archivo", "el documento", "guardalo", "guardala", "esto", "eso", "todo"):
        key = ""
    else:
        key = normalize_app_name(raw_key) if raw_key else ""

    # 1. Si no hay app especificada, consultar el registro last_opened_apps
    if not key:
        best_time = 0.0
        best_pid = None
        best_app = "notepad"
        for candidate_app, entries in last_opened_apps.items():
            for entry in entries:
                pid = entry.get("pid")
                ts = entry.get("timestamp", 0)
                if pid and psutil.pid_exists(pid) and ts > best_time:
                    best_time = ts
                    best_pid = pid
                    best_app = candidate_app
        if best_pid:
            return best_pid, best_app
        # Si no hay registro en memoria, asumir notepad por defecto
        key = "notepad"

    # 2. Buscar procesos activos con psutil
    target_exes = {f"{key}.exe"}
    if key in ("word", "winword", "msword", "microsoft word"):
        target_exes.update({"winword.exe", "word.exe"})
    elif key in ("excel", "msexcel", "microsoft excel"):
        target_exes.update({"excel.exe"})

    active_pids: list[int] = []
    for proc in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            pname = (proc.info.get("name") or "").lower()
            if pname in target_exes or pname == key or key in pname:
                active_pids.append(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not active_pids:
        return None, key

    # 3. Si hay instancias, priorizar la última abierta por AURA
    aura_pid = get_last_opened_pid(key, active_pids)
    if aura_pid:
        return aura_pid, key

    # 4. De lo contrario, tomar el PID con fecha de creación más reciente
    try:
        active_pids.sort(key=lambda p: psutil.Process(p).create_time(), reverse=True)
        return active_pids[0], key
    except Exception:
        return active_pids[0], key


def save_app_document(
    app_name: str = "",
    filename: str = "",
    destination: str = "",
) -> SkillResult:
    """
    Función principal de guardado de documento de aplicación abierta.

    Args:
        app_name: Nombre o referencia de la app (ej: 'notepad', 'bloc de notas', 'word').
        filename: Nombre sugerido para el archivo o extensión (ej: 'notas.txt', '.txt', 'doc').
        destination: Carpeta destino (ej: 'escritorio', 'descargas', 'documentos').

    Returns:
        SkillResult con mensaje de éxito o error descriptivo.
    """
    from aura.core.app_capabilities import get_app_capabilities, normalize_app_name, load_capabilities

    pid, raw_app = resolve_running_app_pid(app_name)
    clean_app = normalize_app_name(raw_app or app_name or "notepad")
    app_display = clean_app.capitalize() if clean_app else "Notepad"

    # 0. Validar capacidades de lectura y guardado
    caps = get_app_capabilities(clean_app)
    read_cap = caps.get("read")
    save_as_cap = caps.get("save_as")
    all_registered = load_capabilities()

    # Si la app está explícitamente registrada con lectura y guardado nulos (ej: Discord, Spotify, Code)
    if clean_app in all_registered and read_cap is None and save_as_cap is None:
        return SkillResult(
            success=False,
            error=f"No se puede guardar el contenido de {app_display} (no puedo leer su contenido).",
            data={"app": clean_app, "supported": False},
        )

    # Para apps que no guardan por COM, verificar que exista una instancia abierta
    if save_as_cap != "com":
        if not pid or not psutil.pid_exists(pid):
            return SkillResult(
                success=False,
                error=f"No se encontró ninguna instancia abierta de {app_display}. Asegurate de que la ventana esté abierta.",
                data={"app": clean_app, "running": False},
            )

        if read_cap is None and save_as_cap is None:
            return SkillResult(
                success=False,
                error=f"No se puede guardar el contenido de {app_display} (no puedo leer su contenido).",
                data={"app": clean_app, "supported": False},
            )

    # 1. Resolver destino
    dest_dir = resolve_folder_alias(destination) if destination else None
    if not dest_dir:
        dest_dir = resolve_folder_alias("escritorio") or (Path.home() / "Desktop")

    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        _logger.error(f"AppSaver: no se pudo crear directorio destino '{dest_dir}': {e}")
        dest_dir = Path.home() / "Documents"

    # 2. Determinar nombre de archivo sanitizado y extensión por defecto
    clean_fn = (filename or "").strip().strip("'\"`´")
    default_ext = ".docx" if clean_app == "word" else (".xlsx" if clean_app == "excel" else ".txt")
    m_ext = re.search(r"(\.[a-zA-Z0-9]+)$", clean_fn)
    is_only_ext = clean_fn.startswith(".") or clean_fn.lower().startswith("archivo .") or clean_fn.lower() == "archivo"
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not clean_fn or is_only_ext:
        ext = m_ext.group(1) if m_ext else default_ext
        final_filename = f"aura_{clean_app}_{now_str}{ext}"
    else:
        valid, reason = is_valid_strict_filename(clean_fn)
        if not valid:
            _logger.warning(f"AppSaver: nombre '{clean_fn}' rechazado por guard ({reason}). Usando nombre seguro con timestamp.")
            final_filename = f"aura_{clean_app}_{now_str}{default_ext}"
        else:
            if "." not in clean_fn:
                clean_fn += default_ext
            final_filename = clean_fn

    target_path = (dest_dir / final_filename).resolve()
    abs_path_str = str(target_path)

    # Loguear ruta destino resuelta ANTES de escribir, para auditoría
    _logger.info("save_app_doc: ruta destino resuelta para '%s': '%s'", clean_app, abs_path_str)

    # 3. Guardado vía COM para Office (Word / Excel)
    if save_as_cap == "com":
        from aura.skills.office_adapter import OfficeAdapter
        _logger.info(f"AppSaver: guardando documento de '{clean_app}' vía OfficeAdapter (COM) en '{abs_path_str}'")
        com_res = OfficeAdapter.save_as(clean_app, target_path)
        if not com_res.success:
            return com_res

        # Si el archivo fue escrito en disco, verificar que no esté vacío
        if os.path.exists(target_path) and os.path.getsize(target_path) == 0:
            _logger.error("save_app_doc: el archivo se guardó vacío (0 bytes) en '%s'", abs_path_str)
            return SkillResult(
                success=False,
                error=f"El archivo '{abs_path_str}' se creó pero está vacío (0 bytes).",
                data={"path": abs_path_str, "app": clean_app},
            )

        try:
            from core.user_memory import user_memory
            user_memory.record_path(abs_path_str, alias=final_filename)
        except Exception:
            pass

        return com_res

    # 4. Guardado vía Win32 extraction para editores nativos (Notepad)
    if not pid or not psutil.pid_exists(pid):
        return SkillResult(
            success=False,
            error=f"No se encontró ninguna instancia abierta de {app_display}. Asegurate de que la ventana esté abierta.",
            data={"app": clean_app, "running": False},
        )

    # Localizar ventana principal
    from aura.skills.app_writer import find_window_by_pid
    hwnd, title = find_window_by_pid(pid)
    if not hwnd:
        return SkillResult(
            success=False,
            error=f"No se encontró una ventana visible para {app_display} (pid {pid}).",
            data={"pid": pid, "app": clean_app},
        )

    # Extraer texto mediante Win32 API
    ok, text_or_err = extract_text_from_window(hwnd)
    if not ok:
        return SkillResult(
            success=False,
            error=f"La ventana de {app_display} (pid {pid}) no tiene un control de texto legible ({text_or_err}).",
            data={"pid": pid, "app": clean_app, "hwnd": hwnd},
        )

    content = text_or_err

    # 5. Guardar archivo vía files_skill con codificación UTF-8
    try:
        from skills.builtin.files_skill import FilesSkill
        files_sk = FilesSkill()
        write_res = files_sk.write_file(target_path, content)
        if not write_res.success:
            _logger.error(f"AppSaver: files_skill falló escribiendo '{abs_path_str}': {write_res.error}")
            return SkillResult(
                success=False,
                error=write_res.error or f"Error escribiendo el archivo en '{abs_path_str}'",
                data={"path": abs_path_str, "pid": pid},
            )
    except Exception as e:
        import traceback
        tb_short = traceback.format_exc(limit=3).strip()
        _logger.error(f"AppSaver: error escribiendo '{abs_path_str}': {e}\n{tb_short}")
        return SkillResult(
            success=False,
            error=f"Error escribiendo el archivo en '{abs_path_str}': {e}",
            data={"path": abs_path_str, "pid": pid, "exception_type": type(e).__name__, "traceback": tb_short},
        )

    # Verificar existencia post-escritura (os.path.exists) y tamaño > 0
    if not os.path.exists(target_path):
        _logger.error("save_app_doc: el archivo no existe tras la escritura en '%s'", abs_path_str)
        return SkillResult(
            success=False,
            error=f"El archivo no se creó en '{abs_path_str}'.",
            data={"path": abs_path_str, "pid": pid},
        )

    if os.path.getsize(target_path) == 0:
        _logger.error("save_app_doc: el archivo se creó vacío (0 bytes) en '%s'", abs_path_str)
        return SkillResult(
            success=False,
            error=f"El archivo '{abs_path_str}' se creó pero está vacío (0 bytes).",
            data={"path": abs_path_str, "pid": pid},
        )

    # 6. Registrar en memoria de usuario
    try:
        from core.user_memory import user_memory
        user_memory.record_path(abs_path_str, alias=final_filename)
    except Exception:
        pass

    out_msg = f"💾 Guardado: {abs_path_str} ({len(content)} caracteres, pid {pid})"
    _logger.info(f"AppSaver: {out_msg}")

    return SkillResult(
        success=True,
        output=out_msg,
        data={
            "path": abs_path_str,
            "pid": pid,
            "app": clean_app,
            "characters": len(content),
            "filename": final_filename,
            "destination": str(dest_dir),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Definición de la Skill para SkillRegistry
# ─────────────────────────────────────────────────────────────────────────────

_META = SkillMeta(
    name="app_saver",
    version="1.0.0",
    display_name="Guardar Documento de App",
    description="Guarda el contenido de texto de una aplicación abierta (como Notepad) en un archivo.",
    author="AURA",
    category=CATEGORY_SYSTEM,
    commands=["save_app_doc"],
    builtin=True,
    enabled_by_default=True,
)


class AppSaverSkill(BaseSkill):
    """
    Skill para guardar contenido de documentos de aplicaciones abiertas.
    """
    META = _META

    def execute(self, command: str, args: list[str]) -> SkillResult:
        if command != "save_app_doc":
            return SkillResult(success=False, error=f"Comando desconocido '{command}' en app_saver.")

        app_name = args[0] if len(args) > 0 else ""
        filename = args[1] if len(args) > 1 else ""
        destination = args[2] if len(args) > 2 else ""

        return save_app_document(app_name=app_name, filename=filename, destination=destination)

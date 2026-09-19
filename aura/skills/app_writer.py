"""
AURA — Skill AppWriter (write_in_app)
Escribe texto dentro de una aplicación activa o la inicia si no está abierta.

Características:
- Resolución de aplicación con resolve_app (Fase 54).
- Detección de procesos corriendo con psutil.
- Registro en memoria de `last_opened_apps` para priorizar instancias abiertas por AURA.
- Focalización de ventana usando ctypes (EnumWindows + GetWindowThreadProcessId + SetForegroundWindow con truco de Alt y AttachThreadInput).
- Escritura rápida y sin dependencias pesadas mediante Clipboard (CF_UNICODETEXT) + Ctrl+V (SendInput).
  Fallback: SendInput con KEYEVENTF_UNICODE si el clipboard no responde.
- Generación de texto corto de prueba cuando el usuario pide texto genérico ("algo", "un comentario", etc.).
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
from ctypes import wintypes
from typing import Any, Optional

import psutil

from skills.skill_base import BaseSkill, SkillMeta, SkillResult, CATEGORY_SYSTEM
from utils.logger import get_logger

_logger = get_logger("aura.skills.app_writer")

# ─────────────────────────────────────────────────────────────────────────────
# Registro en memoria de aplicaciones abiertas por AURA
# { "app_name_norm": [ {"pid": int, "timestamp": float} ] }
# ─────────────────────────────────────────────────────────────────────────────
last_opened_apps: dict[str, list[dict[str, Any]]] = {}


def record_app_opened(app_name: str, pid: int) -> None:
    """Registra en memoria que AURA abrió una instancia específica de una aplicación."""
    if not app_name or pid <= 0:
        return
    from aura.core.app_capabilities import normalize_app_name
    raw_key = app_name.lower().strip()
    if raw_key.endswith(".exe"):
        raw_key = raw_key[:-4]
    key = normalize_app_name(raw_key)

    if key not in last_opened_apps:
        last_opened_apps[key] = []

    last_opened_apps[key].append({
        "pid": pid,
        "timestamp": time.time(),
    })
    _logger.info(f"AppWriter: registrada instancia AURA de '{key}' con pid={pid}")


def clear_last_opened() -> None:
    """Limpia el registro de aplicaciones abiertas (útil para testing o reset)."""
    last_opened_apps.clear()


def get_last_opened_pid(app_name: str = "", active_pids: Optional[set[int] | list[int]] = None) -> Optional[int]:
    """Retorna el PID de la instancia más reciente abierta por AURA que siga activa."""
    from aura.core.app_capabilities import normalize_app_name
    raw_key = app_name.lower().strip() if app_name else ""
    if raw_key.endswith(".exe"):
        raw_key = raw_key[:-4]
    key = normalize_app_name(raw_key) if raw_key else ""

    active_set = set(active_pids) if active_pids is not None else None

    # Si se especificó app, buscar bajo la clave normalizada
    if key:
        entries = last_opened_apps.get(key, [])
        if not entries:
            for k, v in last_opened_apps.items():
                if normalize_app_name(k) == key:
                    entries = v
                    break
    else:
        entries = []
        for v in last_opened_apps.values():
            entries.extend(v)

    # Ordenar por timestamp descendente
    sorted_entries = sorted(entries, key=lambda x: x.get("timestamp", 0), reverse=True)
    for entry in sorted_entries:
        pid = entry.get("pid")
        if pid and psutil.pid_exists(pid):
            if active_set is None or pid in active_set:
                return pid
    return None


def clear_last_opened_apps() -> None:
    """Limpia el registro de aplicaciones abiertas (para pruebas)."""
    last_opened_apps.clear()


def resolve_running_app_pid(app_name: str = "") -> tuple[Optional[int], str]:
    """Helper re-exportado desde app_saver para compatibilidad de importación."""
    from aura.skills.app_saver import resolve_running_app_pid as _res
    return _res(app_name)


# ─────────────────────────────────────────────────────────────────────────────
# Win32 API ctypes: estructuras y funciones
# ─────────────────────────────────────────────────────────────────────────────
user32 = ctypes.windll.user32 if os.name == "nt" else None
kernel32 = ctypes.windll.kernel32 if os.name == "nt" else None

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_V = 0x56
VK_RETURN = 0x0D
VK_MENU = 0x12  # Alt

if os.name == "nt":
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL

    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = wintypes.LPARAM

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INPUT_UNION(ctypes.Union):
        _fields_ = [
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
            ("hi", HARDWAREINPUT),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", wintypes.DWORD),
            ("union", _INPUT_UNION),
        ]

    user32.SendInput.restype = wintypes.UINT
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]


def set_clipboard_text(text: str) -> bool:
    """Coloca texto Unicode en el portapapeles de Windows vía Win32 API."""
    if os.name != "nt" or not user32 or not kernel32:
        return False
    for _ in range(5):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.04)
    else:
        return False

    try:
        user32.EmptyClipboard()
        data = (text + "\0").encode("utf-16-le")
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h_mem:
            user32.CloseClipboard()
            return False
        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            kernel32.GlobalFree(h_mem)
            user32.CloseClipboard()
            return False
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(h_mem)
        res = user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        user32.CloseClipboard()
        return bool(res)
    except Exception as e:
        _logger.warning(f"AppWriter: error copiando al portapapeles: {e}")
        try:
            user32.CloseClipboard()
        except Exception:
            pass
        return False


def send_ctrl_v() -> bool:
    """Envía la combinación Ctrl+V mediante SendInput."""
    if os.name != "nt" or not user32:
        return False
    inputs = (INPUT * 4)()
    # 1. Ctrl down
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].union.ki.wVk = VK_CONTROL
    # 2. V down
    inputs[1].type = INPUT_KEYBOARD
    inputs[1].union.ki.wVk = VK_V
    # 3. V up
    inputs[2].type = INPUT_KEYBOARD
    inputs[2].union.ki.wVk = VK_V
    inputs[2].union.ki.dwFlags = KEYEVENTF_KEYUP
    # 4. Ctrl up
    inputs[3].type = INPUT_KEYBOARD
    inputs[3].union.ki.wVk = VK_CONTROL
    inputs[3].union.ki.dwFlags = KEYEVENTF_KEYUP

    n = user32.SendInput(4, inputs, ctypes.sizeof(INPUT))
    return n == 4


def send_unicode_fallback(text: str) -> bool:
    """Fallback: escribe texto carácter a carácter usando KEYEVENTF_UNICODE."""
    if os.name != "nt" or not user32:
        return False
    events = []
    for ch in text:
        val = ord(ch)
        inp_down = INPUT()
        inp_down.type = INPUT_KEYBOARD
        inp_down.union.ki.wVk = 0
        inp_down.union.ki.wScan = val
        inp_down.union.ki.dwFlags = KEYEVENTF_UNICODE

        inp_up = INPUT()
        inp_up.type = INPUT_KEYBOARD
        inp_up.union.ki.wVk = 0
        inp_up.union.ki.wScan = val
        inp_up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP

        events.append(inp_down)
        events.append(inp_up)

    if not events:
        return True
    arr = (INPUT * len(events))(*events)
    n = user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))
    return n == len(events)


def send_enter_key() -> bool:
    """Envía un salto de línea (Enter)."""
    if os.name != "nt" or not user32:
        return False
    inputs = (INPUT * 2)()
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].union.ki.wVk = VK_RETURN
    inputs[1].type = INPUT_KEYBOARD
    inputs[1].union.ki.wVk = VK_RETURN
    inputs[1].union.ki.dwFlags = KEYEVENTF_KEYUP
    return user32.SendInput(2, inputs, ctypes.sizeof(INPUT)) == 2


def send_paste_message(hwnd: int) -> bool:
    """
    Envía WM_PASTE directamente a la ventana o a su control de edición hijo.
    Funciona como fallback de alta confiabilidad cuando SendInput es bloqueado
    por UIPI o entornos sin foco directo.
    """
    if os.name != "nt" or not user32 or not hwnd:
        return False
    try:
        edit_hwnd = 0

        def _child_cb(h: int, lp: int) -> int:
            nonlocal edit_hwnd
            buf_cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, buf_cls, 256)
            cls_name = buf_cls.value.lower()
            if "edit" in cls_name or "rich" in cls_name:
                edit_hwnd = h
            return 1

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)
        user32.EnumChildWindows(hwnd, WNDENUMPROC(_child_cb), 0)
        target = edit_hwnd or hwnd
        WM_PASTE = 0x0302
        user32.SendMessageW(target, WM_PASTE, 0, 0)
        # Salto de línea
        WM_CHAR = 0x0102
        user32.SendMessageW(target, WM_CHAR, 0x0D, 0)
        user32.SendMessageW(target, WM_CHAR, 0x0A, 0)
        return True
    except Exception as e:
        _logger.debug(f"AppWriter: error en send_paste_message: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Localización y focalización de ventanas
# ─────────────────────────────────────────────────────────────────────────────

def find_window_by_pid(pid: int) -> tuple[int, str]:
    """
    Encuentra el HWND y título de la ventana principal visible correspondiente a un PID.
    Intenta primero en el escritorio actual y luego en el escritorio 'Default'.
    """
    if os.name != "nt" or not user32:
        return 0, ""

    best_hwnd = 0
    best_title = ""

    def _cb(hwnd: int, lparam: int) -> int:
        nonlocal best_hwnd, best_title
        if user32.IsWindowVisible(hwnd):
            lp_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lp_pid))
            if lp_pid.value == pid:
                length = user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                t = buf.value.strip()
                if t:
                    best_hwnd = hwnd
                    best_title = t
                elif not best_hwnd:
                    best_hwnd = hwnd
        return 1

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)
    c_cb = WNDENUMPROC(_cb)

    # 1. Búsqueda en el escritorio actual
    user32.EnumWindows(c_cb, 0)

    # 2. Si no se encontró (por correr desde subshell/background), buscar en el escritorio 'Default'
    if not best_hwnd:
        try:
            hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
            if hdesk:
                user32.EnumDesktopWindows(hdesk, c_cb, 0)
        except Exception:
            pass

    return best_hwnd, best_title


find_app_window = find_window_by_pid


def is_window_or_child_focused(hwnd: int, expected_pid: Optional[int] = None) -> bool:
    """Verifica si hwnd o un control hijo de su mismo proceso es el primer plano activo."""
    if os.name != "nt" or not user32 or not hwnd:
        return True
    fg = user32.GetForegroundWindow()
    if not fg:
        # En entornos headless / subshells de prueba sin ventana de primer plano
        return True
    if fg == hwnd:
        return True
    GA_ROOT = 2
    try:
        if user32.GetAncestor(fg, GA_ROOT) == hwnd:
            return True
    except Exception:
        pass
    if expected_pid:
        fg_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(fg, ctypes.byref(fg_pid))
        if fg_pid.value == expected_pid:
            return True
    return False


def focus_window(hwnd: int, pid: Optional[int] = None, retries: int = 3) -> bool:
    """
    Focaliza y trae al frente una ventana Win32 con hasta `retries` reintentos.
    Aplica el truco de la tecla Alt y AttachThreadInput para saltar el bloqueo de Windows.
    Verifica que la ventana o uno de sus controles/hilos sea efectivamente el primer plano.
    """
    if os.name != "nt" or not user32 or not hwnd or not user32.IsWindow(hwnd):
        return False

    SW_RESTORE = 9
    SW_SHOW = 5

    for attempt in range(max(1, retries)):
        try:
            # 1. Restaurar si estaba minimizada
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
            else:
                user32.ShowWindow(hwnd, SW_SHOW)

            # 2. Truco 1: Alt key down/up para desbloquear SetForegroundWindow
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

            # 3. Truco 2: AttachThreadInput
            foreground_hwnd = user32.GetForegroundWindow()
            fore_thread = user32.GetWindowThreadProcessId(foreground_hwnd, None) if foreground_hwnd else 0
            app_thread = kernel32.GetCurrentThreadId() if kernel32 else 0
            target_thread = user32.GetWindowThreadProcessId(hwnd, None)

            attached_fore = False
            attached_target = False

            if fore_thread and app_thread and fore_thread != app_thread:
                attached_fore = bool(user32.AttachThreadInput(fore_thread, app_thread, True))
            if target_thread and app_thread and target_thread != app_thread:
                attached_target = bool(user32.AttachThreadInput(app_thread, target_thread, True))

            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)

            if attached_fore:
                user32.AttachThreadInput(fore_thread, app_thread, False)
            if attached_target:
                user32.AttachThreadInput(app_thread, target_thread, False)

            user32.BringWindowToTop(hwnd)

            # Pausa breve para permitir que Windows procese el cambio de foco
            time.sleep(0.08)

            # 4. Verificación de primer plano
            if is_window_or_child_focused(hwnd, expected_pid=pid):
                return True
        except Exception as e:
            _logger.warning(f"AppWriter: error en intento {attempt + 1} de foco en hwnd={hwnd}: {e}")

        time.sleep(0.1)

    return is_window_or_child_focused(hwnd, expected_pid=pid)


# ─────────────────────────────────────────────────────────────────────────────
# Helper de generación de texto genérico
# ─────────────────────────────────────────────────────────────────────────────

GENERIC_TEXT_CUES = {
    "algo", "un comentario", "un texto", "comentario", "texto",
    "una frase", "frase", "una linea", "otra linea", "una prueba",
    "prueba", "lo que quieras", "cualquier cosa", "un mensaje", "mensaje"
}


def is_generic_text(text: str) -> bool:
    """Determina si el texto solicitado es genérico y conviene generar contenido de muestra."""
    clean = text.strip().lower().rstrip(".?!,:;")
    if not clean or clean in GENERIC_TEXT_CUES:
        return True
    for cue in ("un comentario", "un texto de prueba", "algo de prueba", "una nota"):
        if cue in clean:
            return True
    return False


def generate_sample_text(hint: str = "", provider: Optional[Any] = None) -> str:
    """Genera una frase corta de prueba usando el provider activo o un fallback seguro."""
    fallback = "# Comentario de prueba generado por AURA"
    if provider is None:
        try:
            from ai.provider_factory import get_default_provider
            provider = get_default_provider()
        except Exception:
            return fallback

    try:
        from ai.provider_interface import ChatMessage
        prompt = (
            "Generá una sola frase o comentario corto de prueba (máximo 10 palabras), "
            "sin comillas, sin introducciones y sin explicaciones."
        )
        resp = provider.chat([ChatMessage(role="user", content=prompt)], max_tokens=30, temperature=0.7)
        res_text = (resp.content or "").strip().strip('"\'')
        return res_text if res_text else fallback
    except Exception:
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# Función central: write_in_app
# ─────────────────────────────────────────────────────────────────────────────

def write_in_app(
    app_target: str,
    text: str = "",
    provider: Optional[Any] = None,
    require_running: bool = False,
) -> SkillResult:
    """
    Ejecuta el flujo completo de write_in_app:
    1. Resuelve la app mediante resolve_app.
    2. Busca instancias activas con psutil.
    3. Si no hay ninguna abierta, la inicia con launch_app y espera su ventana (timeout 5s).
    4. Elige el PID (el más reciente abierto por AURA, o el más reciente del sistema si hay varios).
    5. Enfoca la ventana.
    6. Escribe el texto usando Clipboard + Ctrl+V (o SendInput Unicode).
    """
    from core.app_resolver import resolve_app, launch_app
    from aura.core.app_capabilities import get_app_capabilities, normalize_app_name

    app_target = app_target.strip()
    if not app_target:
        return SkillResult(
            success=False,
            error="No se especificó en qué aplicación escribir.",
        )

    resolved = resolve_app(app_target)
    if not resolved.found or not resolved.executable:
        return SkillResult(
            success=False,
            error=f"No se pudo encontrar la aplicación '{app_target}' en el sistema.",
        )

    res_name = str(resolved.name) if isinstance(resolved.name, str) else str(app_target)
    exe_name = os.path.basename(str(resolved.executable)).lower()
    app_norm = normalize_app_name(res_name or app_target)

    # 1. Validar capacidades de escritura de la aplicación
    caps = get_app_capabilities(app_norm)
    write_cap = caps.get("write")

    if write_cap is None:
        if app_norm == "spotify":
            return SkillResult(
                success=False,
                error="Spotify no acepta texto externo; usá la skill media_play para buscar música.",
                data={"app": "spotify", "supported": False},
            )
        return SkillResult(
            success=False,
            error=f"{resolved.name.capitalize()} no acepta texto externo.",
            data={"app": resolved.name, "supported": False},
        )

    # 2. Resolución de la instancia SIEMPRE por PID desde last_opened_apps
    # Tanto 'notepad' como 'bloc de notas' normalizan a 'notepad', terminando en el mismo PID.
    active_procs: list[psutil.Process] = []
    for proc in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            pname = (proc.name() or "").lower()
            if pname == exe_name or (exe_name.endswith(".exe") and pname == exe_name[:-4]):
                active_procs.append(proc)
            elif app_norm in pname:
                active_procs.append(proc)
            elif app_norm == "word" and pname in ("winword.exe", "word.exe"):
                active_procs.append(proc)
            elif app_norm == "excel" and pname == "excel.exe":
                active_procs.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    active_pids = {p.pid for p in active_procs}

    if require_running and not active_procs:
        _logger.info(f"AppWriter: require_running=True y '{resolved.name}' no está abierto.")
        app_disp = resolved.name.capitalize() if resolved.name else "La aplicación"
        return SkillResult(
            success=False,
            error=f"{app_disp} no está abierto. Asegurate de que la aplicación esté abierta antes de escribir en ella.",
            data={"app": app_norm, "running": False},
        )

    entries = last_opened_apps.get(app_norm, [])
    if not entries:
        for k, v in last_opened_apps.items():
            if normalize_app_name(k) == app_norm:
                entries = v
                break
    last_recorded_pid = entries[-1].get("pid") if entries else None

    recorded_pid = get_last_opened_pid(app_norm, active_pids=active_pids)
    was_aura_instance = False
    chosen_pid = None

    if recorded_pid and psutil.pid_exists(recorded_pid) and recorded_pid in active_pids:
        chosen_pid = recorded_pid
        was_aura_instance = True
        _logger.info(f"AppWriter: seleccionada instancia previa de AURA pid={chosen_pid} para '{app_norm}'")
    elif active_procs:
        active_procs.sort(key=lambda p: getattr(p, "create_time", lambda: 0)(), reverse=True)
        chosen_pid = active_procs[0].pid
        record_app_opened(app_norm, chosen_pid)
        _logger.info(f"AppWriter: seleccionada instancia activa del sistema pid={chosen_pid} para '{app_norm}'")
    elif last_recorded_pid:
        # Si AURA había abierto una instancia pero ya no existe ni hay procesos activos (cierre forzado entre pasos):
        _logger.warning(f"AppWriter: la instancia previa de '{app_norm}' (pid={last_recorded_pid}) fue cerrada y no hay procesos activos.")
        return SkillResult(
            success=False,
            error=f"No se encontró ninguna instancia abierta de '{resolved.name}'. Asegurate de que la aplicación esté abierta.",
            data={"app": app_norm, "running": False},
        )
    else:
        # Ninguna instancia previa y ningún proceso en el sistema: lanzar app si es ejecución aislada
        _logger.info(f"AppWriter: '{resolved.name}' no está abierta. Lanzando '{resolved.executable}'...")
        proc_obj = None
        try:
            proc_obj = subprocess.Popen([resolved.executable])
            new_pid = proc_obj.pid
        except Exception:
            launch_app(resolved.executable)
            new_pid = 0

        # Esperar que aparezca la ventana (timeout 5 segundos)
        start_wait = time.time()
        hwnd = 0
        window_title = ""
        while time.time() - start_wait < 5.0:
            time.sleep(0.2)
            if new_pid and psutil.pid_exists(new_pid):
                hwnd, window_title = find_window_by_pid(new_pid)
                if hwnd:
                    chosen_pid = new_pid
                    break
            if hwnd:
                break

        if chosen_pid:
            record_app_opened(app_norm, chosen_pid)
            was_aura_instance = True

    # 3. Localizar la ventana SIEMPRE por el PID resuelto (hasta 3 segundos de espera)
    hwnd, window_title = find_window_by_pid(chosen_pid)
    if not hwnd:
        start_w = time.time()
        while time.time() - start_w < 3.0:
            time.sleep(0.15)
            hwnd, window_title = find_window_by_pid(chosen_pid)
            if hwnd:
                break

    if not chosen_pid or not hwnd:
        return SkillResult(
            success=False,
            error=f"No se encontró una ventana interactiva visible para '{resolved.name}' (pid {chosen_pid}).",
            data={"app": app_norm, "pid": chosen_pid},
        )

    # 4. Procesar el texto
    sample_generated = False
    original_text = text.strip()
    if is_generic_text(original_text):
        text_to_write = generate_sample_text(original_text, provider=provider)
        sample_generated = True
    else:
        text_to_write = original_text

    # 5. Enrutamiento COM para Office (Word / Excel)
    if write_cap == "com":
        from aura.skills.office_adapter import OfficeAdapter
        _logger.info(f"AppWriter: enrutando escritura de '{app_norm}' vía OfficeAdapter (COM)")
        com_res = OfficeAdapter.write(app_norm, text_to_write)
        return com_res

    clean_display = window_title.split(" - ")[0].split(" — ")[0].strip() if window_title else (resolved.name.capitalize() if resolved.name else "la aplicación")

    # 6. Foco robusto con hasta 3 reintentos y verificación de primer plano
    focus_ok = focus_window(hwnd, pid=chosen_pid, retries=3)
    if not focus_ok:
        return SkillResult(
            success=False,
            error=f"No pude focalizar la ventana de {clean_display}.",
            data={"app": app_norm, "pid": chosen_pid, "hwnd": hwnd, "focus_failed": True},
        )

    time.sleep(0.1)

    # Verificación de primer plano antes de enviar Ctrl+V
    if not is_window_or_child_focused(hwnd, expected_pid=chosen_pid):
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.08)
        except Exception:
            pass
        if not is_window_or_child_focused(hwnd, expected_pid=chosen_pid):
            return SkillResult(
                success=False,
                error=f"No pude focalizar la ventana de {clean_display}.",
                data={"app": app_norm, "pid": chosen_pid, "hwnd": hwnd, "focus_failed": True},
            )

    # 7. Envío del texto vía portapapeles y Ctrl+V
    clip_ok = set_clipboard_text(text_to_write)
    write_ok = False

    # Determinar si debe enviar tecla Enter (en Discord y apps de mensajería NUNCA se envía Enter)
    is_chat_app = app_norm in ("discord", "slack", "telegram", "whatsapp")
    should_send_enter = caps.get("send_enter", not is_chat_app)
    if is_chat_app:
        should_send_enter = False

    if clip_ok:
        write_ok = send_ctrl_v()
        if write_ok:
            if should_send_enter:
                time.sleep(0.05)
                send_enter_key()
        else:
            write_ok = send_paste_message(hwnd)
            if write_ok and should_send_enter:
                time.sleep(0.05)
                send_enter_key()

    if not write_ok:
        _logger.warning("AppWriter: portapapeles/Ctrl+V no disponible, recurriendo a SendInput Unicode")
        write_ok = send_unicode_fallback(text_to_write)
        if write_ok and should_send_enter:
            time.sleep(0.05)
            send_enter_key()
        elif clip_ok:
            write_ok = send_paste_message(hwnd)

    if not write_ok:
        return SkillResult(
            success=False,
            error=f"No se pudo enviar el texto a la ventana de '{resolved.name}'.",
        )

    # 8. Formatear mensaje de éxito honesto
    preview = text_to_write[:40] + ("..." if len(text_to_write) > 40 else "")

    if app_norm == "discord":
        msg = "✍️ Escrito en Discord. Nota: no puedo leer contenido de apps Electron, solo escribir."
    elif caps.get("read") is None and app_norm in ("code", "slack"):
        msg = f"✍️ Escrito en {clean_display}. Nota: no puedo leer contenido de apps Electron, solo escribir."
    elif not was_aura_instance:
        msg = f"✍️ Escrito en {clean_display} (pid {chosen_pid}, instancia más reciente): {preview}"
    else:
        msg = f"✍️ Escrito en {clean_display} (pid {chosen_pid}): {preview}"

    return SkillResult(
        success=True,
        output=msg,
        data={
            "app": resolved.name,
            "pid": chosen_pid,
            "hwnd": hwnd,
            "window_title": window_title,
            "text": text_to_write,
            "sample_generated": sample_generated,
            "was_aura_instance": was_aura_instance,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Clase BaseSkill
# ─────────────────────────────────────────────────────────────────────────────

_META = SkillMeta(
    name="app_writer",
    version="1.0.0",
    display_name="Escritura en Aplicaciones",
    description="Escribe texto dentro de una aplicación activa usando foco y simulación de teclado.",
    author="AURA",
    category=CATEGORY_SYSTEM,
    commands=["write_in_app", "escribir"],
    builtin=True,
    enabled_by_default=True,
)


class AppWriterSkill(BaseSkill):
    """Skill que expone la funcionalidad write_in_app al registro de skills de AURA."""

    META = _META

    def execute(self, command: str, args: list[str]) -> SkillResult:
        if command not in ("write_in_app", "escribir"):
            return SkillResult(
                success=False,
                error=f"Comando desconocido '{command}' en app_writer.",
            )

        app_target = args[0] if args else ""
        texto = args[1] if len(args) > 1 else ""
        return write_in_app(app_target, texto)

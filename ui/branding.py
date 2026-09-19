"""
AURA — Módulo de Branding y Gestión de Íconos (Fase 65)

Provee utilidades centralizadas para:
  1. Identificador de aplicación en Windows (SetCurrentProcessExplicitAppUserModelID).
  2. Resolución de rutas de assets (logo.png, logo_header.png, logo.ico).
  3. Generación y renderizado de avatar circular in-app para la waifu AURA.
  4. Asignación robusta de íconos de ventana (Flet window.icon + Win32 WM_SETICON Plan B).
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any, Optional
import flet as ft

from utils.logger import get_logger

_logger = get_logger("aura.ui.branding")

APP_USER_MODEL_ID = "aura.orion.desktop"
WINDOW_TITLE = "AURA — Asistente Universal"

# Directorio raíz del proyecto
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(_CURRENT_DIR)
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")


def get_assets_dir() -> str:
    """Retorna la ruta absoluta al directorio de assets."""
    return ASSETS_DIR


def get_logo_png_path() -> str:
    """Retorna la ruta absoluta al logo original del usuario (logo.png — avatar in-app waifu)."""
    return os.path.join(ASSETS_DIR, "logo.png")


def get_logo_header_path() -> str:
    """Retorna la ruta absoluta al logo derivado optimizado para headers (logo_header.png)."""
    return os.path.join(ASSETS_DIR, "logo_header.png")


def get_logo2_png_path() -> str:
    """Retorna la ruta absoluta a assets/logo2.png (fuente del ícono de taskbar/ventana)."""
    return os.path.join(ASSETS_DIR, "logo2.png")


def get_logo2_ico_path() -> str:
    """Retorna la ruta absoluta a assets/logo2.ico (ícono final de ventana/taskbar)."""
    return os.path.join(ASSETS_DIR, "logo2.ico")


def get_window_ico_path() -> str:
    """Retorna la ruta absoluta al ícono final de ventana y taskbar (logo2.ico)."""
    return get_logo2_ico_path()


def get_logo_waifu_ico_path() -> str:
    """Retorna la ruta al ícono de la waifu (assets/logo.ico si es válido, o assets/logo_waifu.ico)."""
    ico_path = os.path.join(ASSETS_DIR, "logo.ico")
    if os.path.exists(ico_path):
        valid, _ = verify_ico_file(ico_path)
        if valid:
            return ico_path
    return os.path.join(ASSETS_DIR, "logo_waifu.ico")


def ensure_logo_waifu_ico() -> str:
    """
    Verifica o genera el ícono de la waifu en formato .ico (Fase 66):
      - Si assets/logo.ico existe y es un ico válido generado desde assets/logo.png, lo reutiliza.
      - Si no, lo genera con Pillow desde assets/logo.png como assets/logo_waifu.ico
        (cuadrado con padding transparente, tamaños 16 a 256, LANCZOS) y verifica encabezado 00 00 01 00.
      - No toca logo2.ico (ícono de ventana/taskbar).

    Retorna la ruta absoluta al .ico válido de la waifu.
    """
    candidate_logo_ico = os.path.join(ASSETS_DIR, "logo.ico")
    if os.path.exists(candidate_logo_ico):
        valid, detail = verify_ico_file(candidate_logo_ico)
        if valid:
            _logger.info("Ícono de waifu reutilizado desde logo.ico: %s", detail)
            return candidate_logo_ico
        else:
            _logger.warning("assets/logo.ico no es válido (%s). Se usará logo_waifu.ico", detail)

    waifu_ico_path = os.path.join(ASSETS_DIR, "logo_waifu.ico")
    if os.path.exists(waifu_ico_path):
        valid, detail = verify_ico_file(waifu_ico_path)
        if valid:
            _logger.info("Ícono de waifu verificado existente (%s): %s", waifu_ico_path, detail)
            return waifu_ico_path
        else:
            _logger.warning("logo_waifu.ico no pasó validación (%s). Regenerando...", detail)

    png_path = get_logo_png_path()
    if not os.path.exists(png_path):
        _logger.error("No se encontró %s para generar logo_waifu.ico", png_path)
        return waifu_ico_path

    try:
        from PIL import Image

        im = Image.open(png_path)
        if im.mode != "RGBA":
            im = im.convert("RGBA")

        w, h = im.size
        max_dim = max(w, h)
        if w == h:
            square_im = im
        else:
            square_im = Image.new("RGBA", (max_dim, max_dim), (0, 0, 0, 0))
            offset = ((max_dim - w) // 2, (max_dim - h) // 2)
            square_im.paste(im, offset)

        ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        square_im.save(waifu_ico_path, format="ICO", sizes=ico_sizes)

        valid, detail = verify_ico_file(waifu_ico_path)
        if valid:
            _logger.info("assets/logo_waifu.ico generado y verificado exitosamente: %s", detail)
        else:
            _logger.error("Fallo en verificación automática de logo_waifu.ico: %s", detail)

    except Exception as e:
        _logger.error("Error generando assets/logo_waifu.ico con Pillow: %s", e, exc_info=True)

    return waifu_ico_path


def ensure_ico_backup() -> None:
    """Asegura el backup del ico trucho anterior como assets/logo.ico.invalid si aún no existe."""
    backup_path = os.path.join(ASSETS_DIR, "logo.ico.invalid")
    if not os.path.exists(backup_path):
        candidate = os.path.join(ASSETS_DIR, "logo.ico")
        if not os.path.exists(candidate):
            candidate = get_logo2_png_path()
        if os.path.exists(candidate):
            try:
                import shutil
                shutil.copyfile(candidate, backup_path)
                _logger.info("Backup de ícono previo creado en: %s", backup_path)
            except Exception as e:
                _logger.debug("No se pudo crear backup logo.ico.invalid: %s", e)


def verify_ico_file(ico_path: str) -> tuple[bool, str]:
    """
    Verificación automática del archivo .ico:
      1. Primeros 4 bytes = 00 00 01 00 (magic bytes de ICO estándar de Windows).
      2. Al menos 5 tamaños presentes en el directorio del archivo.
    Retorna (True, mensaje) si es válido, (False, error) si no.
    """
    if not os.path.exists(ico_path):
        return False, f"Archivo no encontrado: {ico_path}"

    try:
        import struct
        with open(ico_path, "rb") as f:
            data = f.read()

        if len(data) < 6:
            return False, "Archivo demasiado pequeño para contener cabecera ICO válida"

        magic = data[:4]
        if magic != b"\x00\x00\x01\x00":
            return False, f"Cabecera mágica inválida: {magic.hex(' ')} (se esperaba 00 00 01 00)"

        num_images = struct.unpack("<H", data[4:6])[0]
        sizes = []
        for i in range(num_images):
            entry_offset = 6 + i * 16
            if entry_offset + 2 <= len(data):
                w = data[entry_offset] or 256
                h = data[entry_offset + 1] or 256
                sizes.append((w, h))

        if num_images < 5:
            return False, f"Cantidad insuficiente de tamaños: {num_images} (se esperaban al menos 5, tamaños: {sizes})"

        msg = f"magic=00 00 01 00, {num_images} tamaños presentes {sizes}"
        return True, msg
    except Exception as e:
        return False, f"Error leyendo estructura ICO: {e}"


def ensure_logo2_ico() -> str:
    """
    Genera y verifica assets/logo2.ico desde assets/logo2.png usando Pillow:
      - Encerrar en cuadrado con padding transparente, sin deformar.
      - Tamaños: 16, 24, 32, 48, 64, 128 y 256 px.
      - Remuestreo LANCZOS.
      - Verificación automática: primeros 4 bytes = 00 00 01 00 y >= 5 tamaños presentes.
      - Logueo del resultado.

    Retorna la ruta absoluta a assets/logo2.ico.
    """
    ensure_ico_backup()
    ico_path = get_logo2_ico_path()
    png_path = get_logo2_png_path()

    # Si ya existe, verificarlo
    if os.path.exists(ico_path):
        valid, detail = verify_ico_file(ico_path)
        if valid:
            _logger.info(f"Ícono verificado existente ({ico_path}): {detail}")
            return ico_path
        else:
            _logger.warning(f"logo2.ico existente no pasó validación ({detail}). Se regenerará...")

    if not os.path.exists(png_path):
        _logger.warning(f"No se encontró {png_path} para generar logo2.ico.")
        return ico_path

    try:
        from PIL import Image

        im = Image.open(png_path)
        if im.mode != "RGBA":
            im = im.convert("RGBA")

        # Encerrar en cuadrado con padding transparente, sin deformar
        w, h = im.size
        max_dim = max(w, h)
        if w == h:
            square_im = im
        else:
            square_im = Image.new("RGBA", (max_dim, max_dim), (0, 0, 0, 0))
            offset = ((max_dim - w) // 2, (max_dim - h) // 2)
            square_im.paste(im, offset)

        # Tamaños requeridos: 16, 24, 32, 48, 64, 128, 256 px
        ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

        # Guardar con Pillow (aplica LANCZOS para las reducciones del ICO)
        square_im.save(ico_path, format="ICO", sizes=ico_sizes)

        # Verificación automática
        valid, detail = verify_ico_file(ico_path)
        if valid:
            _logger.info(f"assets/logo2.ico generado y verificado exitosamente: {detail}")
        else:
            _logger.error(f"Fallo en la verificación automática de logo2.ico: {detail}")

    except Exception as e:
        _logger.error(f"Error generando assets/logo2.ico con Pillow: {e}", exc_info=True)

    return ico_path


def ensure_header_logo() -> str:
    """
    Verifica si existe logo_header.png (versión optimizada de 128px para headers).
    Si no existe y logo.png > 1MB o > 1024px, genera logo_header.png usando PowerShell / GDI+
    sin tocar nunca el archivo original logo.png ni logo.ico.

    Retorna el nombre relativo del recurso ('logo_header.png' o 'logo.png') para Flet.
    """
    header_path = get_logo_header_path()
    orig_path = get_logo_png_path()

    if os.path.exists(header_path):
        return "logo_header.png"

    if not os.path.exists(orig_path):
        return "logo.png"

    try:
        size_bytes = os.path.getsize(orig_path)
        # Si pesa más de 1 MB, intentar generar copia derivada de 128px
        if size_bytes > 1024 * 1024:
            _logger.info("logo.png supera 1 MB (%d bytes); generando logo_header.png (128x128)...", size_bytes)
            ps_cmd = (
                f'powershell -NoProfile -ExecutionPolicy Bypass -Command "'
                f'Add-Type -AssemblyName System.Drawing; '
                f'$src = [System.Drawing.Image]::FromFile(\'{orig_path}\'); '
                f'$dest = New-Object System.Drawing.Bitmap 128, 128; '
                f'$g = [System.Drawing.Graphics]::FromImage($dest); '
                f'$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic; '
                f'$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality; '
                f'$g.DrawImage($src, 0, 0, 128, 128); '
                f'$dest.Save(\'{header_path}\', [System.Drawing.Imaging.ImageFormat]::Png); '
                f'$g.Dispose(); $dest.Dispose(); $src.Dispose();"'
            )
            import subprocess
            subprocess.run(ps_cmd, shell=True, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(header_path):
                _logger.info("logo_header.png generado exitosamente en assets/")
                return "logo_header.png"
    except Exception as e:
        _logger.debug(f"No se pudo generar logo_header.png derivado: {e}")

    return "logo.png"


def get_header_logo_src() -> str:
    """
    Retorna la ruta relativa que debe recibir ft.Image(src=...) para Flet.
    Si existe logo_header.png usa ese, sino logo.png.
    """
    if os.path.exists(get_logo_header_path()):
        return "logo_header.png"
    return "logo.png"


def create_brand_avatar(
    size: int = 28,
    tooltip: str = "AURA",
    border_color: Optional[str] = "#3A3A5E",
    border_width: int = 1,
) -> ft.Container:
    """
    Crea un contenedor con el avatar circular de la waifu AURA.
    Usa borde redondeado completo (borde = size // 2), fit CONTAIN y anti-alias.
    """
    src = get_header_logo_src()
    img = ft.Image(
        src=src,
        width=size,
        height=size,
        fit=ft.BoxFit.CONTAIN,
    )
    border = ft.Border.all(border_width, border_color) if border_color else None

    return ft.Container(
        content=img,
        width=size,
        height=size,
        border_radius=size // 2,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        border=border,
        tooltip=tooltip,
        alignment=ft.Alignment.CENTER,
    )


def set_taskbar_app_id(app_id: str = APP_USER_MODEL_ID, logger: Any = None) -> bool:
    """
    Fija el identificador de aplicación explícito en Windows
    (SetCurrentProcessExplicitAppUserModelID) dentro de un try/except.
    Permite que la barra de tareas de Windows agrupe la aplicación y
    muestre su propio ícono en vez del ícono genérico de Python/Flet.
    """
    log = logger or _logger
    if sys.platform != "win32":
        return False

    try:
        import ctypes
        hr = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(str(app_id))
        if hr == 0:
            log.info(f"AppUserModelID de Windows fijado exitosamente: '{app_id}'")
            return True
        else:
            log.warning(f"SetCurrentProcessExplicitAppUserModelID retornó código HRESULT: {hr}")
            return False
    except Exception as e:
        log.debug(f"No se pudo fijar AppUserModelID en Windows: {e}")
        return False


def _set_win32_window_icon(window_title: str, ico_path: str, logger: Any = None) -> bool:
    """
    Plan B / Refuerzo Win32: Asigna el ícono de ventana (16x16 pequeño y 32x32 grande)
    a la ventana nativa mediante WM_SETICON y LoadImageW / CreateIconFromResourceEx de user32.dll.
    """
    log = logger or _logger
    if sys.platform != "win32":
        return False

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x00000010

        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
            ctypes.c_int, ctypes.c_int, wintypes.UINT
        ]
        user32.LoadImageW.restype = wintypes.HANDLE

        # 1. Intentar LoadImageW tradicional
        h_small = user32.LoadImageW(None, str(ico_path), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        h_big = user32.LoadImageW(None, str(ico_path), IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        method_name = "LoadImageW"

        # 2. Si LoadImageW devolvió NULL (común en archivos .ico modernos con payload PNG)
        if not h_small or not h_big:
            if os.path.exists(ico_path):
                with open(ico_path, "rb") as f:
                    ico_data = f.read()
                user32.CreateIconFromResourceEx.argtypes = [
                    ctypes.c_char_p, wintypes.DWORD, wintypes.BOOL,
                    wintypes.DWORD, ctypes.c_int, ctypes.c_int, wintypes.UINT
                ]
                user32.CreateIconFromResourceEx.restype = wintypes.HICON
                h_small = user32.CreateIconFromResourceEx(ico_data, len(ico_data), True, 0x00030000, 16, 16, 0)
                h_big = user32.CreateIconFromResourceEx(ico_data, len(ico_data), True, 0x00030000, 32, 32, 0)
                method_name = "CreateIconFromResourceEx (PNG payload)"

        if not h_small and not h_big:
            log.warning("No se pudo instanciar HICON para el archivo de ícono.")
            return False

        # 3. Buscar la ventana por título
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowW.restype = wintypes.HWND
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = wintypes.LPARAM

        hwnd = user32.FindWindowW(None, str(window_title))

        # Si no la encuentra por título exacto, buscar por enumeración de ventanas
        if not hwnd:
            matched_hwnd = None

            def enum_cb(h, _):
                nonlocal matched_hwnd
                length = user32.GetWindowTextLengthW(h)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(h, buff, length + 1)
                    if window_title in buff.value or "AURA" in buff.value:
                        matched_hwnd = h
                        return False
                return True

            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(EnumWindowsProc(enum_cb), 0)
            hwnd = matched_hwnd

        if hwnd:
            if h_small:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_small)
            if h_big:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_big)
            log.info(f"Ícono de ventana asignado exitosamente vía Win32 API ({method_name}) en HWND {hwnd}")
            return True
        else:
            try:
                log.debug(f"Ventana '{window_title}' no encontrada aún por Win32.")
            except Exception:
                pass
            return False
    except Exception as e:
        log.debug(f"Excepción en _set_win32_window_icon: {e}")
        return False


def apply_window_branding(page: ft.Page, app_title: str = WINDOW_TITLE, logger: Any = None) -> None:
    """
    Aplica el ícono de ventana en Flet y, en Windows, ejecuta el plan B (WM_SETICON)
    en un hilo secundario para asegurar que la barra de tareas y el título tomen el ícono.
    """
    log = logger or _logger
    ico_path = ensure_logo2_ico()

    # 1. Asignar ícono vía Flet Window API
    flet_success = False
    try:
        if hasattr(page, "window") and hasattr(page.window, "icon"):
            page.window.icon = str(ico_path)
            flet_success = True
            log.info(f"Ícono de ventana asignado vía Flet window.icon: '{ico_path}'")
    except Exception as e:
        log.debug(f"Flet window.icon no disponible o falló: {e}")

    # 2. Plan B / Refuerzo Win32: polling de hasta 3 segundos para asignar WM_SETICON
    if sys.platform == "win32":
        def _poll_and_set():
            for _ in range(30):
                time.sleep(0.1)
                try:
                    if _set_win32_window_icon(app_title, ico_path, log):
                        break
                except Exception:
                    break

        threading.Thread(target=_poll_and_set, daemon=True, name="aura-set-win32-icon").start()

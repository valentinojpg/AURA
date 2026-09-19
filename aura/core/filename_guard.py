"""
AURA — Guard de Nombres de Archivo y Resolución de Alias de Carpetas (Fase 63)

Provee funciones críticas para garantizar que:
  1. Los nombres de archivos y carpetas sean válidos y NO contengan frases, comandos o verbos.
  2. Los destinos amigables (Escritorio, Descargas, Documentos, etc.) se resuelvan a las rutas
     reales de Windows vía SHGetKnownFolderPath con fallback seguro a USERPROFILE / Path.home().
  3. Las rutas compuestas ("notas.txt en el escritorio", "descargas/test") se descompongan
     correctamente en nombre y carpeta destino real.
"""

from __future__ import annotations

import ctypes
import os
import re
import unicodedata
from ctypes import wintypes
from pathlib import Path
from typing import Optional, Tuple

from utils.logger import get_logger

_logger = get_logger("aura.core.filename_guard")

# ─────────────────────────────────────────────────────────────────────────────
# Constantes de GUIDs para SHGetKnownFolderPath de Windows
# ─────────────────────────────────────────────────────────────────────────────
FOLDERID_Desktop = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"
FOLDERID_Documents = "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"
FOLDERID_Downloads = "{374DE290-123F-4565-9164-39C4925E467B}"
FOLDERID_Music = "{4BD8D570-5699-470A-8E04-05E8CE20E494}"
FOLDERID_Pictures = "{33E28130-4E1E-4676-835A-98395C3BC3BB}"
FOLDERID_Videos = "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}"

class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def get_known_folder_path(guid_str: str) -> Optional[Path]:
    """Obtiene la ruta real de una Known Folder de Windows mediante Win32 API."""
    if os.name != "nt":
        return None
    try:
        guid = _GUID()
        ctypes.windll.ole32.CLSIDFromString(guid_str, ctypes.byref(guid))
        path_ptr = ctypes.c_wchar_p()
        hr = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, 0, ctypes.byref(path_ptr))
        if hr == 0 and path_ptr.value:
            path_val = path_ptr.value
            ctypes.windll.ole32.CoTaskMemFree(path_ptr)
            p = Path(path_val)
            if p.exists():
                return p
    except Exception as e:
        _logger.debug(f"Error obteniendo KnownFolder '{guid_str}': {e}")
    return None


def resolve_folder_alias(raw_dest: str) -> Optional[Path]:
    """
    Resuelve alias en lenguaje natural a rutas de carpetas del sistema:
      - escritorio / desktop
      - documentos / documents / mis documentos
      - descargas / downloads
      - musica / music / mis canciones
      - imagenes / fotos / pictures / mis fotos
      - videos / mis videos
      - Rutas favoritas o alias registrados en UserMemory
      - Rutas existentes en el sistema de archivos
    """
    if not raw_dest or not str(raw_dest).strip():
        return None

    clean = str(raw_dest).strip()

    # Quitar partículas y preposiciones iniciales
    prefixes = [
        "en el ", "en la ", "en los ", "en las ",
        "al ", "a la ", "hacia el ", "hacia la ", "hacia ",
        "dentro de ", "en ", "para el ", "para la ", "para ",
    ]
    clean_lower = clean.lower()
    for prefix in prefixes:
        if clean_lower.startswith(prefix):
            clean = clean[len(prefix):].strip()
            clean_lower = clean.lower()
            break

    # Normalizar diacríticos
    norm = "".join(
        c for c in unicodedata.normalize("NFKD", clean_lower)
        if not unicodedata.combining(c) and ord(c) < 128
    ).strip()

    home = Path.home()

    if norm in ("escritorio", "desktop"):
        return get_known_folder_path(FOLDERID_Desktop) or (home / "Desktop")

    if norm in ("documentos", "documents", "mis documentos"):
        return get_known_folder_path(FOLDERID_Documents) or (home / "Documents")

    if norm in ("descargas", "downloads"):
        return get_known_folder_path(FOLDERID_Downloads) or (home / "Downloads")

    if norm in ("musica", "music", "mis canciones", "mi musica"):
        return get_known_folder_path(FOLDERID_Music) or (home / "Music")

    if norm in ("imagenes", "pictures", "fotos", "mis fotos", "mis imagenes"):
        return get_known_folder_path(FOLDERID_Pictures) or (home / "Pictures")

    if norm in ("videos", "mis videos", "mis peliculas"):
        return get_known_folder_path(FOLDERID_Videos) or (home / "Videos")

    # Consulta a UserMemory (Fase 28)
    try:
        from core.user_memory import user_memory
        p_mem = user_memory.get_path_by_alias(norm) or user_memory.get_path(norm)
        if p_mem:
            p_obj = Path(p_mem)
            if p_obj.exists():
                return p_obj
    except Exception:
        pass

    # Verificación si es una ruta absoluta o relativa existente
    try:
        p_direct = Path(clean).expanduser()
        if p_direct.is_dir():
            return p_direct.resolve()
    except Exception:
        pass

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Palabras y Frases Prohibidas para Nombres de Archivo
# ─────────────────────────────────────────────────────────────────────────────
COMMAND_STOPWORDS = {
    "guarda", "guardar", "guardame", "guardalo", "guardala",
    "salva", "salvar", "salvalo", "salvala",
    "escribe", "escribi", "escribir", "escribime", "redacta", "tipea",
    "abre", "abrir", "abreme", "inicia", "iniciar", "ejecuta", "ejecutar",
    "borra", "borrar", "borrame", "elimina", "eliminar", "eliminame",
    "crea", "crear", "creame",
    "dentro", "ahora", "como", "quiero",
}

COMMAND_PHRASES = [
    "en el", "en la", "en los", "en las",
    "al escritorio", "a descargas", "a documentos",
    "dentro de", "como archivo", "con nombre",
    "lo que escribiste", "la ventana",
    "un nuevo", "una nueva", "archivo nuevo",
]


def is_valid_strict_filename(name: str) -> Tuple[bool, str]:
    """
    Guard estricto de nombres de archivo y carpeta:
      - Máximo 4 palabras en el nombre base.
      - Sin verbos o palabras de comando (guarda, escribir, abre, crea, etc.).
      - Sin frases de comando ('en el', 'dentro de', 'como archivo', etc.).
      - Máximo 80 caracteres.
      - Sin caracteres prohibidos de Windows (< > : " | ? *).

    Returns:
        (True, "") si es válido, o (False, "razón del rechazo").
    """
    if not name or not str(name).strip():
        return False, "Nombre vacío"

    clean = str(name).strip().strip("'\"`´")

    if len(clean) > 80:
        return False, f"Nombre demasiado largo ({len(clean)} caracteres, máximo permitido: 80)"

    invalid_chars = set('<>:"|?*')
    if any(c in invalid_chars for c in clean):
        return False, "Contiene caracteres prohibidos de Windows (< > : \" | ? *)"

    # Normalizar diacríticos
    norm = "".join(
        c for c in unicodedata.normalize("NFKD", clean)
        if not unicodedata.combining(c) and ord(c) < 128
    ).lower()

    # 1. Detección de frases de comando
    for phrase in COMMAND_PHRASES:
        if phrase in norm:
            return False, f"Contiene frase de comando: '{phrase}'"

    # 2. Separar nombre base de extensión
    base = norm.rsplit(".", 1)[0] if "." in norm else norm
    words = re.findall(r"[a-z0-9]+", base)

    # 3. Límite estricto de palabras (ignorando conectores comunes como de, la, el)
    connectors = {"de", "la", "el", "los", "las", "un", "una", "del", "al", "en", "y"}
    significant_words = [w for w in words if w not in connectors]
    if len(significant_words) > 4:
        return False, f"Contiene demasiadas palabras ({len(words)} palabras, máximo permitido: 4)"

    # 4. Verbos y stopwords de comando
    for w in words:
        if w in COMMAND_STOPWORDS:
            return False, f"Contiene palabra de comando prohibida: '{w}'"

    return True, ""


def resolve_path_with_alias(raw_path: str, default_base: Optional[Path] = None) -> Tuple[Path, str]:
    """
    Analiza una ruta o expresión de archivo que puede contener alias de carpetas:
      Ejemplos:
        "notas.txt en el escritorio" -> (Path("C:/Users/.../Desktop/notas.txt"), "notas.txt")
        "el escritorio/ notas.txt"  -> (Path("C:/Users/.../Desktop/notas.txt"), "notas.txt")
        "descargas/test"            -> (Path("C:/Users/.../Downloads/test"), "test")
        "test en descargas"         -> (Path("C:/Users/.../Downloads/test"), "test")
        "notas.txt"                 -> (default_base / "notas.txt", "notas.txt")

    Returns:
        (resolved_full_path, clean_base_name)
    """
    if default_base is None:
        default_base = Path.home() / "Documents"

    raw = raw_path.strip().strip("'\"`´")

    # Caso 1: Conexión con preposiciones ("... en ...", "... al ...", "... hacia ...")
    for sep in [" en el ", " en la ", " en los ", " en las ", " en ", " al ", " a la ", " hacia "]:
        if sep in raw.lower():
            idx = raw.lower().rfind(sep)
            name_part = raw[:idx].strip()
            folder_part = raw[idx + len(sep):].strip()
            folder_res = resolve_folder_alias(folder_part)
            if folder_res:
                clean_name = os.path.basename(name_part)
                return (folder_res / clean_name).resolve(), clean_name

    # Caso 2: Separación tipo carpeta/archivo ("escritorio/notas.txt", "descargas/test")
    norm_slash = raw.replace("\\", "/")
    if "/" in norm_slash:
        dir_part, base_part = norm_slash.rsplit("/", 1)
        dir_part = dir_part.strip()
        base_part = base_part.strip()
        folder_res = resolve_folder_alias(dir_part)
        if folder_res:
            return (folder_res / base_part).resolve(), base_part

    # Caso 3: Es un alias de carpeta directo
    folder_res = resolve_folder_alias(raw)
    if folder_res:
        return folder_res.resolve(), folder_res.name

    # Caso 4: Ruta absoluta
    p = Path(raw)
    if p.is_absolute():
        return p.resolve(), p.name

    # Caso 5: Relativa a la base por defecto
    return (default_base / raw).resolve(), p.name

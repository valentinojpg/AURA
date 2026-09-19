"""
AURA — Motor de Búsqueda Profunda de Aplicaciones y Caché de Índice

Implementa la resolución multinivel de aplicaciones en Windows:
1. Resolución rápida:
   - Favoritos / Memoria (data/programs.json y data/learning/app_index.json)
   - PATH del sistema (shutil.which)
   - App Paths del Registro de Windows (HKCU y HKLM)
   - Registro de Desinstalación (DisplayName, DisplayIcon, InstallLocation)
   - Accesos directos .lnk en Menú Inicio y Escritorio
2. Escaneo profundo en segundo plano:
   - Recorrido recursivo con os.scandir (profundidad máx. 6) en todas las unidades fijas
   - Exclusiones estrictas: C:\\Windows, $Recycle.Bin, ProgramData\\Microsoft,
     node_modules, .git, AppData\\Local\\Temp, caches de navegadores, etc.
   - Búsqueda normalizada: <target>.exe (exacta), <target>*.exe (parcial), <target>.lnk
   - Cancelable y no bloqueante
   - Registro automático en memoria/favoritos de los hallazgos para acceso instantáneo
3. Caché persistente:
   - Persistencia en data/learning/app_index.json
   - Soporte para reconstruir el índice completo ("indexa mis apps")
"""

from __future__ import annotations

import collections
import json
import os
import re
import shutil
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import psutil

from utils.logger import get_logger

_logger = get_logger("aura.core.app_scanner")

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
LEARNING_DIR = DATA_DIR / "learning"
APP_INDEX_FILE = LEARNING_DIR / "app_index.json"
PROGRAMS_FILE = DATA_DIR / "programs.json"


# ──────────────────────────────────────────────────────────────
# Exclusiones de carpetas para el escaneo profundo
# ──────────────────────────────────────────────────────────────

EXCLUDE_EXACT_NAMES: Set[str] = {
    "$recycle.bin",
    "recycle.bin",
    "windows",
    "node_modules",
    ".git",
    "temp",
    "tmp",
    "$windows.~bt",
    "$windows.~ws",
    "system volume information",
    "msdownld.tmp",
}

EXCLUDE_SUBSTRINGS: Tuple[str, ...] = (
    "\\programdata\\microsoft",
    "\\appdata\\local\\temp",
    "\\temp\\",
    "\\tmp\\",
    "\\cache\\",
    "\\code cache\\",
    "\\gpucache\\",
    "\\cache2\\",
    "\\shadercache\\",
    "\\package cache\\",
    "\\service worker\\",
    "\\site-packages\\",
    "\\.vscode\\extensions\\",
    "\\.cache\\",
)


def normalize_name(text: str) -> str:
    """Normaliza texto: minúsculas, sin tildes ni caracteres combinados."""
    if not text:
        return ""
    text_clean = unicodedata.normalize("NFKD", text.strip())
    without_accents = "".join(c for c in text_clean if not unicodedata.combining(c))
    return without_accents.lower().strip()


def should_exclude_dir(dir_name: str, dir_path: str, root_dir: Optional[str] = None) -> bool:
    """Verifica si un directorio debe ser ignorado durante el escaneo."""
    d_name_clean = dir_name.lower()
    if d_name_clean in EXCLUDE_EXACT_NAMES or d_name_clean.startswith("$"):
        return True

    if root_dir:
        try:
            rel = os.path.relpath(dir_path, root_dir)
            check_path = f"\\{rel.lower()}\\"
        except Exception:
            check_path = f"\\{dir_path.lower()}\\"
    else:
        check_path = f"\\{dir_path.lower()}\\"

    for sub in EXCLUDE_SUBSTRINGS:
        if sub in check_path:
            return True
    return False


# ──────────────────────────────────────────────────────────────
# Gestor de Índice Persistente (data/learning/app_index.json)
# ──────────────────────────────────────────────────────────────

@dataclass
class IndexedApp:
    name: str
    path: str
    date: str
    origin: str
    display_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "date": self.date,
            "origin": self.origin,
            "display_name": self.display_name or self.name,
        }


class AppIndexManager:
    """Administra la caché persistente de aplicaciones indexadas."""

    def __init__(self, index_file: Path = APP_INDEX_FILE, programs_file: Path = PROGRAMS_FILE):
        self._index_file = index_file
        self._programs_file = programs_file
        self._lock = threading.RLock()
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        try:
            self._index_file.parent.mkdir(parents=True, exist_ok=True)
            self._programs_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            _logger.warning("No se pudieron asegurar directorios de índice: %s", e)

    def _save_atomic(self, file_path: Path, data: Any) -> bool:
        """Guarda un diccionario o lista JSON de forma atómica escribiendo en un archivo temporal y renombrándolo."""
        tmp_path = file_path.with_name(f"{file_path.name}.tmp.{threading.get_ident()}")
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            tmp_path.replace(file_path)
            return True
        except Exception as e:
            _logger.warning("Error guardando atómicamente en %s: %s", file_path, e)
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass
            return False

    def load_index(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            if not self._index_file.exists():
                return {}
            try:
                with open(self._index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("apps", {}) if isinstance(data, dict) else {}
            except Exception as e:
                _logger.warning("Error leyendo app_index.json: %s", e)
                return {}

    def get(self, app_name: Any) -> Optional[str]:
        """
        Busca una app en el índice. Si la ruta existe en disco, la retorna.
        Si la ruta ya no existe, la ignora.
        """
        if isinstance(app_name, (list, tuple)):
            app_name = " ".join(str(x) for x in app_name).strip()
        else:
            app_name = str(app_name or "").strip()

        norm = normalize_name(app_name)
        index = self.load_index()
        entry = index.get(norm)
        if not entry:
            return None

        path_val = entry.get("path")
        if path_val and os.path.exists(path_val):
            return path_val
        return None

    def register(
        self,
        app_name: Any,
        path: str,
        origin: str = "deep_scan",
        display_name: Optional[str] = None,
    ) -> bool:
        """
        Registra una app en data/learning/app_index.json y la añade
        automáticamente a data/programs.json para acceso directo en memoria.
        """
        if isinstance(app_name, (list, tuple)):
            app_name = " ".join(str(x) for x in app_name).strip()
        else:
            app_name = str(app_name or "").strip()

        if not path or not os.path.exists(path):
            return False

        norm = normalize_name(app_name)
        abs_path = str(Path(path).resolve())
        now_iso = datetime.now().isoformat()

        # 1. Guardar en app_index.json de forma atómica
        with self._lock:
            self._ensure_dirs()
            current_data: Dict[str, Any] = {"apps": {}, "last_updated": now_iso}
            if self._index_file.exists():
                try:
                    with open(self._index_file, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            current_data = loaded
                except Exception:
                    pass

            apps_dict = current_data.setdefault("apps", {})
            apps_dict[norm] = {
                "name": norm,
                "display_name": display_name or app_name,
                "path": abs_path,
                "date": now_iso,
                "origin": origin,
            }
            current_data["last_updated"] = now_iso
            self._save_atomic(self._index_file, current_data)

        # 2. Registrar en data/programs.json (favoritos del usuario) de forma atómica
        try:
            programs_data = {}
            if self._programs_file.exists():
                try:
                    with open(self._programs_file, "r", encoding="utf-8") as f:
                        programs_data = json.load(f)
                        if not isinstance(programs_data, dict):
                            programs_data = {}
                except Exception:
                    programs_data = {}

            programs_data[norm] = abs_path
            self._save_atomic(self._programs_file, programs_data)
            _logger.info(
                "App '%s' registrada exitosamente en app_index.json y programs.json → '%s' (%s)",
                norm,
                abs_path,
                origin,
            )
            return True
        except Exception as e:
            _logger.warning("Error sincronizando con programs.json: %s", e)
            return True

    def count(self) -> int:
        return len(self.load_index())

    def clean_nonexistent(self) -> int:
        """
        Elimina del índice aquellas aplicaciones cuyas rutas ya no existan en disco.
        Retorna el número de entradas eliminadas.
        """
        with self._lock:
            index = self.load_index()
            to_remove = [name for name, data in index.items() if not os.path.exists(data.get("path", ""))]
            if not to_remove:
                return 0

            for name in to_remove:
                del index[name]

            current_data = {"apps": index, "last_updated": datetime.now().isoformat()}
            self._save_atomic(self._index_file, current_data)

            # Sincronizar también con programs.json si existen allí
            if self._programs_file.exists():
                try:
                    with open(self._programs_file, "r", encoding="utf-8") as f:
                        progs = json.load(f)
                    if isinstance(progs, dict):
                        changed = False
                        for name in to_remove:
                            if name in progs and not os.path.exists(progs[name]):
                                del progs[name]
                                changed = True
                        if changed:
                            self._save_atomic(self._programs_file, progs)
                except Exception:
                    pass

            _logger.info("AppIndexManager: %d aplicaciones inexistentes eliminadas del índice", len(to_remove))
            return len(to_remove)

    def index_all_apps(
        self,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None,
        on_progress: Optional[Callable] = None,
    ) -> List[IndexedApp]:
        """
        Reconstruye el índice completo escaneando accesos directos, App Paths,
        registro Uninstall y carpetas de programas en segundo plano.

        Args:
            progress_callback: Callback opcional invocado como (recorridas, encontradas, carpeta_actual).
            cancel_event: Evento cooperativo para cancelar el escaneo.
            on_progress: Alias de compatibilidad hacia atrás para progress_callback.
        """
        cb = progress_callback or on_progress

        def _report_progress(recorridas: int, encontradas: int, carpeta_actual: str) -> None:
            if not cb:
                return
            try:
                cb(recorridas, encontradas, carpeta_actual)
            except TypeError:
                try:
                    cb(encontradas, carpeta_actual)
                except TypeError:
                    try:
                        cb(encontradas)
                    except Exception:
                        pass
                except Exception:
                    pass
            except Exception:
                pass

        discovered: Dict[str, IndexedApp] = {}
        now_iso = datetime.now().isoformat()
        scanned_count = 0

        def _add_cand(name_cand: str, p_cand: str, origin: str, disp_cand: Optional[str] = None) -> bool:
            if cancel_event and cancel_event.is_set():
                return False
            if not p_cand or not os.path.exists(p_cand):
                return False
            clean_name = normalize_name(name_cand)
            if not clean_name or clean_name in discovered:
                return False
            app = IndexedApp(
                name=clean_name,
                path=str(Path(p_cand).resolve()),
                date=now_iso,
                origin=origin,
                display_name=disp_cand or name_cand,
            )
            discovered[clean_name] = app
            _report_progress(scanned_count, len(discovered), app.display_name or app.name)
            return True

        _report_progress(0, 0, "Iniciando escaneo...")

        # 1. Menú Inicio y Escritorio (recursivo)
        lnk_dirs: List[Path] = []
        appdata = os.environ.get("APPDATA")
        if appdata:
            lnk_dirs.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
        progdata = os.environ.get("ProgramData")
        if progdata:
            lnk_dirs.append(Path(progdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
        lnk_dirs.append(Path.home() / "Desktop")
        pub = os.environ.get("PUBLIC", r"C:\Users\Public")
        if os.path.exists(pub):
            lnk_dirs.append(Path(pub) / "Desktop")

        for base_p in lnk_dirs:
            if cancel_event and cancel_event.is_set():
                break
            if not base_p.exists():
                continue
            try:
                for root, _, files in os.walk(base_p):
                    if cancel_event and cancel_event.is_set():
                        break
                    for f in files:
                        if cancel_event and cancel_event.is_set():
                            break
                        scanned_count += 1
                        if f.lower().endswith((".lnk", ".url")):
                            fpath = os.path.join(root, f)
                            stem = Path(f).stem
                            _add_cand(stem, fpath, "start_menu_desktop", stem)
                        if scanned_count % 10 == 0:
                            _report_progress(scanned_count, len(discovered), root)
            except Exception:
                continue

        # 2. App Paths de Windows
        if os.name == "nt":
            try:
                import winreg
                for root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                    if cancel_event and cancel_event.is_set():
                        break
                    for subk in [
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
                        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
                    ]:
                        if cancel_event and cancel_event.is_set():
                            break
                        try:
                            with winreg.OpenKey(root, subk) as k:
                                n_sub, _, _ = winreg.QueryInfoKey(k)
                                for i in range(n_sub):
                                    if cancel_event and cancel_event.is_set():
                                        break
                                    scanned_count += 1
                                    sub_name = winreg.EnumKey(k, i)
                                    try:
                                        with winreg.OpenKey(k, sub_name) as sk:
                                            val, _ = winreg.QueryValueEx(sk, "")
                                            cleaned = _clean_exe_path(str(val))
                                            if cleaned and os.path.isfile(cleaned):
                                                stem = Path(cleaned).stem
                                                _add_cand(stem, cleaned, "app_paths", stem)
                                    except Exception:
                                        continue
                                    if scanned_count % 10 == 0:
                                        _report_progress(scanned_count, len(discovered), "Registro App Paths")
                        except Exception:
                            continue
            except Exception:
                pass

        # 3. Registro Uninstall
        if os.name == "nt":
            try:
                import winreg
                for root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                    if cancel_event and cancel_event.is_set():
                        break
                    for subk in [
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
                    ]:
                        if cancel_event and cancel_event.is_set():
                            break
                        try:
                            with winreg.OpenKey(root, subk) as k:
                                n_sub, _, _ = winreg.QueryInfoKey(k)
                                for i in range(n_sub):
                                    if cancel_event and cancel_event.is_set():
                                        break
                                    scanned_count += 1
                                    sub_name = winreg.EnumKey(k, i)
                                    try:
                                        with winreg.OpenKey(k, sub_name) as sk:
                                            disp_name = ""
                                            try:
                                                disp_val, _ = winreg.QueryValueEx(sk, "DisplayName")
                                                disp_name = str(disp_val)
                                            except Exception:
                                                pass
                                            icon_path = ""
                                            try:
                                                icon_val, _ = winreg.QueryValueEx(sk, "DisplayIcon")
                                                icon_path = _clean_exe_path(str(icon_val)) or ""
                                            except Exception:
                                                pass
                                            if icon_path and os.path.isfile(icon_path):
                                                stem = Path(icon_path).stem
                                                _add_cand(stem, icon_path, "uninstall_registry", disp_name or stem)
                                    except Exception:
                                        continue
                                    if scanned_count % 10 == 0:
                                        _report_progress(scanned_count, len(discovered), "Registro Uninstall")
                        except Exception:
                            continue
            except Exception:
                pass

        # 4. Guardado Atómico en data/learning/app_index.json y sincronización con programs.json
        if cancel_event and cancel_event.is_set():
            _logger.info(
                "index_all_apps cancelado por el usuario (%d apps encontradas, se mantiene el índice anterior intacto)",
                len(discovered),
            )
            _report_progress(scanned_count, len(discovered), "Cancelado")
            return list(discovered.values())

        with self._lock:
            self._ensure_dirs()
            current_data = {"apps": {}, "last_updated": now_iso}
            if self._index_file.exists():
                try:
                    with open(self._index_file, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            current_data = loaded
                except Exception:
                    pass
            apps_dict = current_data.setdefault("apps", {})
            for k, app in discovered.items():
                apps_dict[k] = app.to_dict()
            current_data["last_updated"] = now_iso

            # Guardado atómico
            self._save_atomic(self._index_file, current_data)

            # Sincronizar con programs.json de forma atómica
            try:
                progs_dict = {}
                if self._programs_file.exists():
                    try:
                        with open(self._programs_file, "r", encoding="utf-8") as f:
                            progs_dict = json.load(f)
                            if not isinstance(progs_dict, dict):
                                progs_dict = {}
                    except Exception:
                        progs_dict = {}
                for k, app in discovered.items():
                    if k not in progs_dict:
                        progs_dict[k] = app.path
                self._save_atomic(self._programs_file, progs_dict)
            except Exception as e:
                _logger.warning("Error sincronizando index_all_apps con programs.json: %s", e)

        _report_progress(scanned_count, len(discovered), "Completado")
        _logger.info("index_all_apps finalizado: %d aplicaciones indexadas (%d analizadas)", len(discovered), scanned_count)
        return list(discovered.values())

    def index_app(
        self,
        app_name: str,
        path: str,
        origin: str = "manual",
        display_name: Optional[str] = None,
    ) -> bool:
        """Alias de register() para indexar una aplicación individual."""
        return self.register(app_name=app_name, path=path, origin=origin, display_name=display_name)

    def rebuild(
        self,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> List[IndexedApp]:
        """Alias conveniente de index_all_apps() para reconstruir el índice completo."""
        return self.index_all_apps(progress_callback=progress_callback, cancel_event=cancel_event)

    def search(self, query: str) -> List[IndexedApp]:
        """Busca aplicaciones en el índice cargado que coincidan con la consulta."""
        norm_q = normalize_name(query)
        results: List[IndexedApp] = []
        if not norm_q:
            return results
        index = self.load_index()
        for key, entry in index.items():
            disp = entry.get("display_name", "")
            if norm_q in key or norm_q in normalize_name(disp):
                results.append(
                    IndexedApp(
                        name=key,
                        path=entry.get("path", ""),
                        date=entry.get("date", ""),
                        origin=entry.get("origin", "index"),
                        display_name=disp,
                    )
                )
        return results


app_index_manager = AppIndexManager()


# ──────────────────────────────────────────────────────────────
# Resolución Rápida (Sin Escaneo)
# ──────────────────────────────────────────────────────────────

def _clean_exe_path(raw_path: str) -> Optional[str]:
    """Limpia cadenas de ruta (comillas, parámetros, argumentos de ícono)."""
    if not raw_path:
        return None
    cleaned = raw_path.strip().strip('"')
    # Manejar formatos como 'C:\Program Files\App\app.exe,0'
    if "," in cleaned:
        candidate = cleaned.split(",")[0].strip().strip('"')
        if os.path.isfile(candidate):
            return str(Path(candidate).resolve())
    # Manejar rutas con argumentos 'C:\...\app.exe -arg'
    if ".exe" in cleaned.lower():
        idx = cleaned.lower().find(".exe") + 4
        sub_candidate = cleaned[:idx].strip().strip('"')
        if os.path.isfile(sub_candidate):
            return str(Path(sub_candidate).resolve())
    if os.path.exists(cleaned):
        return str(Path(cleaned).resolve())
    return None


def _find_in_uninstall_registry(target: str) -> Optional[str]:
    """Busca en las claves Uninstall del Registro de Windows."""
    if os.name != "nt":
        return None

    try:
        import winreg

        norm_target = normalize_name(target)
        roots = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]

        for root, subkey in roots:
            try:
                with winreg.OpenKey(root, subkey) as k:
                    num_subkeys, _, _ = winreg.QueryInfoKey(k)
                    for i in range(num_subkeys):
                        sub_name = winreg.EnumKey(k, i)
                        norm_sub = normalize_name(sub_name)

                        try:
                            with winreg.OpenKey(k, sub_name) as app_key:
                                disp_name = ""
                                try:
                                    disp_val, _ = winreg.QueryValueEx(app_key, "DisplayName")
                                    disp_name = str(disp_val)
                                except Exception:
                                    pass

                                norm_disp = normalize_name(disp_name)

                                # Coincidencia por nombre o subkey
                                match = (
                                    norm_target == norm_disp
                                    or norm_target == norm_sub
                                    or (len(norm_target) >= 4 and norm_target in norm_disp)
                                )

                                if not match:
                                    continue

                                # 1. Revisar DisplayIcon
                                try:
                                    icon_val, _ = winreg.QueryValueEx(app_key, "DisplayIcon")
                                    icon_path = _clean_exe_path(str(icon_val))
                                    if icon_path and os.path.isfile(icon_path):
                                        return icon_path
                                except Exception:
                                    pass

                                # 2. Revisar InstallLocation
                                try:
                                    loc_val, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                    loc_str = str(loc_val).strip().strip('"')
                                    if loc_str and os.path.isdir(loc_str):
                                        loc_p = Path(loc_str)
                                        # Buscar <target>.exe
                                        cand_exe = loc_p / f"{norm_target}.exe"
                                        if cand_exe.is_file():
                                            return str(cand_exe.resolve())
                                        # Buscar cualquier .exe en la raíz de instalación
                                        for sub_f in loc_p.iterdir():
                                            if sub_f.is_file() and sub_f.suffix.lower() == ".exe":
                                                if norm_target in normalize_name(sub_f.name):
                                                    return str(sub_f.resolve())
                                except Exception:
                                    pass
                        except Exception:
                            continue
            except Exception:
                continue
    except Exception as e:
        _logger.debug("Error consultando registro Uninstall: %s", e)

    return None


def _find_in_start_menu_and_desktop(target: str) -> Optional[str]:
    """Busca accesos directos .lnk en el Menú Inicio y Escritorio (incluyendo subcarpetas)."""
    norm_target = normalize_name(target)
    if not norm_target:
        return None

    dirs_to_check: List[Path] = []

    # Escritorio del usuario y público
    user_desktop = Path.home() / "Desktop"
    if user_desktop.exists():
        dirs_to_check.append(user_desktop)

    pub_desktop = Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"
    if pub_desktop.exists():
        dirs_to_check.append(pub_desktop)

    # Menú Inicio del usuario y de todos los usuarios
    appdata = os.environ.get("APPDATA")
    if appdata:
        p_user = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if p_user.exists():
            dirs_to_check.append(p_user)

    progdata = os.environ.get("ProgramData")
    if progdata:
        p_common = Path(progdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if p_common.exists():
            dirs_to_check.append(p_common)

    exact_lnk_name = f"{norm_target}.lnk"
    partial_match: Optional[str] = None

    for base in dirs_to_check:
        try:
            for root, _dirs, files in os.walk(str(base)):
                for f in files:
                    if f.lower().endswith(".lnk"):
                        item_norm = normalize_name(f)
                        stem = f[:-4] if f.lower().endswith(".lnk") else f
                        stem_norm = normalize_name(stem)
                        full_p = os.path.join(root, f)

                        # 1. Coincidencia exacta
                        if item_norm == exact_lnk_name or stem_norm == norm_target:
                            return str(Path(full_p).resolve())

                        # 2. Coincidencia por palabra completa (ej: "Steam" en "Steam Client")
                        stem_words = stem_norm.split()
                        if not partial_match and norm_target in stem_words:
                            partial_match = str(Path(full_p).resolve())
        except Exception:
            continue

    return partial_match


def fast_resolve_app(target: Any) -> Optional[str]:
    """
    Ejecuta el orden estricto de resolución rápida (Fase 54):
    1. Favoritos / Memoria (data/programs.json)
    2. Apps indexadas (data/learning/app_index.json)
    3. PATH del sistema (shutil.which)
    4. App Paths del Registro de Windows
    5. Registro de Desinstalación (Uninstall)
    6. Accesos directos .lnk en Menú Inicio y Escritorio

    Retorna la ruta absoluta del ejecutable/.lnk si se encuentra, o None.
    """
    if isinstance(target, (list, tuple)):
        target_str = " ".join(str(x) for x in target).strip()
    elif target is not None:
        target_str = str(target).strip()
    else:
        return None

    if not target_str:
        return None

    norm = normalize_name(target_str)

    # 1. Favoritos / Memoria (data/programs.json)
    if PROGRAMS_FILE.exists():
        try:
            with open(PROGRAMS_FILE, "r", encoding="utf-8") as f:
                progs = json.load(f)
                if isinstance(progs, dict):
                    cand_path = progs.get(norm) or progs.get(target_str.lower())
                    if cand_path and os.path.exists(cand_path):
                        _logger.debug("fast_resolve: '%s' encontrado en programs.json → %s", target_str, cand_path)
                        return str(Path(cand_path).resolve())
        except Exception:
            pass

    # 2. Caché de Índice persistente (app_index.json)
    cached_index = app_index_manager.get(norm)
    if cached_index and os.path.exists(cached_index):
        _logger.debug("fast_resolve: '%s' encontrado en app_index.json → %s", target_str, cached_index)
        return cached_index

    # 3. PATH del sistema
    which_path = shutil.which(target_str) or shutil.which(f"{target_str}.exe")
    if which_path and os.path.isfile(which_path):
        _logger.debug("fast_resolve: '%s' encontrado en PATH → %s", target_str, which_path)
        return str(Path(which_path).resolve())

    # 4. App Paths del Registro
    from core.app_resolver import _find_in_app_paths
    app_path = _find_in_app_paths(f"{norm}.exe") or _find_in_app_paths(target_str)
    if app_path and os.path.isfile(app_path):
        _logger.debug("fast_resolve: '%s' encontrado en App Paths → %s", target_str, app_path)
        return str(Path(app_path).resolve())

    # 5. Registro de Desinstalación (Uninstall)
    uninstall_path = _find_in_uninstall_registry(target_str)
    if uninstall_path and os.path.exists(uninstall_path):
        _logger.debug("fast_resolve: '%s' encontrado en Registro Uninstall → %s", target_str, uninstall_path)
        return uninstall_path

    # 6. Accesos directos .lnk en Menú Inicio y Escritorio
    lnk_path = _find_in_start_menu_and_desktop(target_str)
    if lnk_path and os.path.exists(lnk_path):
        _logger.debug("fast_resolve: '%s' encontrado en accesos directos → %s", target_str, lnk_path)
        return lnk_path

    return None


# ──────────────────────────────────────────────────────────────
# Escáner Profundo (Deep Scanner) en Segundo Plano
# ──────────────────────────────────────────────────────────────

@dataclass
class DeepScanResult:
    target: str
    exact_match: Optional[str] = None
    candidates: List[str] = field(default_factory=list)
    duration_sec: float = 0.0
    scanned_dirs: int = 0
    cancelled: bool = False

    @property
    def has_single_match(self) -> bool:
        if self.exact_match:
            return True
        return len(self.candidates) == 1

    @property
    def best_match(self) -> Optional[str]:
        if self.exact_match:
            return self.exact_match
        if len(self.candidates) == 1:
            return self.candidates[0]
        return None

    @property
    def success(self) -> bool:
        return bool(self.best_match)

    @property
    def chosen_path(self) -> Optional[str]:
        return self.best_match

    @property
    def has_exact_match(self) -> bool:
        return bool(self.exact_match)

    @property
    def scan_time(self) -> float:
        return self.duration_sec


class DeepAppScanner:
    """
    Escanea unidades fijas del sistema buscando aplicaciones de forma rápida,
    segura y no bloqueante.
    """

    def __init__(self, max_depth: int = 6, max_dirs: int = 15000):
        self.max_depth = max_depth
        self.max_dirs = max_dirs

    def get_fixed_drives(self) -> List[str]:
        """Obtiene las unidades fijas del equipo montadas y disponibles."""
        drives: List[str] = []
        try:
            for p in psutil.disk_partitions(all=False):
                if "cdrom" in p.opts or not p.fstype:
                    continue
                d = p.device
                if os.path.exists(d):
                    drives.append(d)
        except Exception:
            pass

        if not drives:
            drives = ["C:\\"]
        return drives

    def scan(
        self,
        target: Any,
        cancel_event: Optional[threading.Event] = None,
        on_progress: Optional[Callable[[int, str], None]] = None,
        search_roots: Optional[List[str]] = None,
        max_depth: Optional[int] = None,
    ) -> DeepScanResult:
        """
        Ejecuta el escaneo profundo en todas las unidades fijas (o raíces especificadas).

        Args:
            target: Nombre de la aplicación a buscar
            cancel_event: Evento para abortar el escaneo en cualquier momento
            on_progress: Callback periódico (dirs_escaneados, ruta_actual)
            search_roots: Lista opcional de raíces a escanear (útil para pruebas)
            max_depth: Profundidad máxima opcional que sobrescribe self.max_depth
        """
        t0 = time.time()
        eff_max_depth = max_depth if max_depth is not None else self.max_depth
        if isinstance(target, (list, tuple)):
            target_str = " ".join(str(x) for x in target).strip()
        else:
            target_str = str(target or "").strip()

        norm_target = normalize_name(target_str)
        exact_exe = f"{norm_target}.exe"
        exact_lnk = f"{norm_target}.lnk"

        exact_matches: List[str] = []
        partial_matches: List[str] = []
        seen_paths: Set[str] = set()

        priority_dirs: List[Tuple[str, int, str]] = []
        root_dirs: List[Tuple[str, int, str]] = []

        if search_roots:
            drives = [str(Path(r).resolve()) for r in search_roots if os.path.exists(r)]
            _logger.info("DeepAppScanner: Iniciando escaneo para '%s' en raíces personalizadas %s", target, drives)
            root_dirs = [(d, 0, d) for d in drives]
        else:
            drives = self.get_fixed_drives()
            _logger.info("DeepAppScanner: Iniciando escaneo para '%s' en unidades %s", target, drives)

            common_subdirs = [
                "Program Files",
                "Program Files (x86)",
                "Games",
                "Juegos",
                "Users",
                "Archivos de programa",
            ]

            for d in drives:
                for sub in common_subdirs:
                    p_cand = os.path.join(d, sub)
                    if os.path.exists(p_cand):
                        priority_dirs.append((p_cand, 1, d))
                root_dirs.append((d, 0, d))

            # Agregar Start Menu explícitamente a alta prioridad
            appdata = os.environ.get("APPDATA")
            if appdata:
                sm_user = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs")
                if os.path.exists(sm_user):
                    priority_dirs.insert(0, (sm_user, 1, drives[0] if drives else "C:\\"))

        queue = collections.deque(priority_dirs + root_dirs)
        visited_dirs: Set[str] = set()
        scanned_count = 0

        while queue and scanned_count < self.max_dirs:
            if cancel_event and cancel_event.is_set():
                dur = time.time() - t0
                _logger.info("DeepAppScanner: Escaneo de '%s' cancelado por el usuario tras %.2fs", target, dur)
                return DeepScanResult(
                    target=target,
                    duration_sec=dur,
                    scanned_dirs=scanned_count,
                    cancelled=True,
                )

            curr_dir, depth, root_d = queue.popleft()
            norm_curr = curr_dir.lower()

            if norm_curr in visited_dirs or depth > eff_max_depth:
                continue
            visited_dirs.add(norm_curr)
            scanned_count += 1

            if on_progress and scanned_count % 100 == 0:
                try:
                    on_progress(scanned_count, curr_dir)
                except Exception:
                    pass

            try:
                with os.scandir(curr_dir) as it:
                    for entry in it:
                        try:
                            if entry.is_file(follow_symlinks=False):
                                e_name_norm = normalize_name(entry.name)
                                full_p = str(Path(entry.path).resolve())

                                if full_p in seen_paths:
                                    continue

                                # 1. Coincidencia exacta de ejecutable (<target>.exe)
                                if e_name_norm == exact_exe:
                                    exact_matches.append(full_p)
                                    seen_paths.add(full_p)
                                    dur = time.time() - t0
                                    _logger.info(
                                        "DeepAppScanner: Coincidencia exacta encontrada para '%s' → '%s' en %.2fs (%d dirs)",
                                        target,
                                        full_p,
                                        dur,
                                        scanned_count,
                                    )
                                    return DeepScanResult(
                                        target=target,
                                        exact_match=full_p,
                                        candidates=[full_p],
                                        duration_sec=dur,
                                        scanned_dirs=scanned_count,
                                    )

                                # 2. Coincidencia exacta de acceso directo (<target>.lnk)
                                elif e_name_norm == exact_lnk:
                                    exact_matches.append(full_p)
                                    seen_paths.add(full_p)

                                # 3. Coincidencia parcial (<target>*.exe o contiene target)
                                elif e_name_norm.endswith(".exe"):
                                    if e_name_norm.startswith(norm_target) or (
                                        len(norm_target) >= 4 and norm_target in e_name_norm
                                    ):
                                        partial_matches.append(full_p)
                                        seen_paths.add(full_p)

                            elif entry.is_dir(follow_symlinks=False):
                                if depth < eff_max_depth and not should_exclude_dir(entry.name, entry.path, root_dir=root_d):
                                    queue.append((entry.path, depth + 1, root_d))
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                continue

        dur = time.time() - t0
        candidates = exact_matches + partial_matches
        best_exact = exact_matches[0] if exact_matches else None

        _logger.info(
            "DeepAppScanner: Finalizado '%s' en %.2fs. Dirs=%d, Exact=%d, Parciales=%d",
            target,
            dur,
            scanned_count,
            len(exact_matches),
            len(partial_matches),
        )

        return DeepScanResult(
            target=target,
            exact_match=best_exact,
            candidates=candidates,
            duration_sec=dur,
            scanned_dirs=scanned_count,
        )


deep_app_scanner = DeepAppScanner()

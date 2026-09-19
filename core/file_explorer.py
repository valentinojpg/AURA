"""
AURA — Motor del Explorador de Archivos (Fase 24)

Provee la lógica central del sistema de archivos para navegación,
inspección de metadatos, formateo de atributos, gestión de historial
y operaciones básicas de apertura para el explorador integrado de AURA.
"""

from __future__ import annotations

import os
import sys
import stat
import shutil
import platform
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import send2trash

from utils.logger import get_logger

_logger = get_logger("aura.core.file_explorer")

_PathBase = type(Path())

class SmartPath(_PathBase):
    """Subclase de Path compatible con comprobación de cadenas ('sub' in path)."""
    def __contains__(self, item: Any) -> bool:
        return str(item) in str(self)


# ──────────────────────────────────────────────
# Mapeo de extensiones a descripciones e íconos
# ──────────────────────────────────────────────
# (descripción legible, clave_icono, color_hex)
_EXTENSION_CATEGORIES: dict[str, tuple[str, str, str]] = {
    # Código y desarrollo
    ".py": ("Script Python", "CODE", "#60A5FA"),
    ".pyw": ("Script Python (GUI)", "CODE", "#60A5FA"),
    ".ipynb": ("Jupyter Notebook", "CODE", "#F97316"),
    ".js": ("Script JavaScript", "CODE", "#FACC15"),
    ".jsx": ("Componente React JSX", "CODE", "#38BDF8"),
    ".ts": ("Script TypeScript", "CODE", "#3B82F6"),
    ".tsx": ("Componente React TSX", "CODE", "#60A5FA"),
    ".html": ("Documento HTML", "HTML", "#F87171"),
    ".htm": ("Documento HTML", "HTML", "#F87171"),
    ".css": ("Hoja de estilos CSS", "CODE", "#38BDF8"),
    ".scss": ("Hoja de estilos SCSS", "CODE", "#EC4899"),
    ".php": ("Script PHP", "CODE", "#818CF8"),
    ".c": ("Código fuente C", "CODE", "#94A3B8"),
    ".cpp": ("Código fuente C++", "CODE", "#38BDF8"),
    ".h": ("Encabezado C/C++", "CODE", "#94A3B8"),
    ".hpp": ("Encabezado C++", "CODE", "#38BDF8"),
    ".cs": ("Código fuente C#", "CODE", "#A855F7"),
    ".java": ("Código fuente Java", "CODE", "#F97316"),
    ".rs": ("Código fuente Rust", "CODE", "#FB923C"),
    ".go": ("Código fuente Go", "CODE", "#22D3EE"),
    ".rb": ("Script Ruby", "CODE", "#EF4444"),
    ".sql": ("Script SQL", "STORAGE", "#60A5FA"),

    # Configuración y datos estructurados
    ".json": ("Archivo JSON", "SETTINGS", "#A78BFA"),
    ".yaml": ("Archivo YAML", "SETTINGS", "#F43F5E"),
    ".yml": ("Archivo YAML", "SETTINGS", "#F43F5E"),
    ".toml": ("Archivo TOML", "SETTINGS", "#A78BFA"),
    ".xml": ("Documento XML", "CODE", "#FB923C"),
    ".env": ("Variables de Entorno", "SETTINGS", "#34D399"),
    ".ini": ("Configuración INI", "SETTINGS", "#94A3B8"),
    ".cfg": ("Archivo de Configuración", "SETTINGS", "#94A3B8"),
    ".conf": ("Archivo de Configuración", "SETTINGS", "#94A3B8"),

    # Documentos y texto
    ".txt": ("Documento de Texto", "DESCRIPTION", "#CBD5E1"),
    ".md": ("Documento Markdown", "DESCRIPTION", "#38BDF8"),
    ".pdf": ("Documento PDF", "PICTURE_AS_PDF", "#EF4444"),
    ".doc": ("Documento Word", "ARTICLE", "#2563EB"),
    ".docx": ("Documento Word", "ARTICLE", "#2563EB"),
    ".xls": ("Hoja de cálculo Excel", "ARTICLE", "#10B981"),
    ".xlsx": ("Hoja de cálculo Excel", "ARTICLE", "#10B981"),
    ".csv": ("Valores separados por coma (CSV)", "ARTICLE", "#10B981"),
    ".ppt": ("Presentación PowerPoint", "ARTICLE", "#F97316"),
    ".pptx": ("Presentación PowerPoint", "ARTICLE", "#F97316"),
    ".log": ("Archivo de Registro / Log", "DESCRIPTION", "#FBBF24"),

    # Imágenes
    ".png": ("Imagen PNG", "IMAGE", "#34D399"),
    ".jpg": ("Imagen JPEG", "IMAGE", "#34D399"),
    ".jpeg": ("Imagen JPEG", "IMAGE", "#34D399"),
    ".gif": ("Imagen GIF", "IMAGE", "#34D399"),
    ".webp": ("Imagen WebP", "IMAGE", "#34D399"),
    ".svg": ("Gráfico vectorial SVG", "IMAGE", "#FBBF24"),
    ".ico": ("Ícono", "IMAGE", "#FBBF24"),
    ".bmp": ("Mapa de bits BMP", "IMAGE", "#34D399"),

    # Audio y Video
    ".mp3": ("Audio MP3", "AUDIO_FILE", "#C084FC"),
    ".wav": ("Audio WAV", "AUDIO_FILE", "#C084FC"),
    ".flac": ("Audio FLAC", "AUDIO_FILE", "#C084FC"),
    ".ogg": ("Audio OGG", "AUDIO_FILE", "#C084FC"),
    ".m4a": ("Audio M4A", "AUDIO_FILE", "#C084FC"),
    ".mp4": ("Video MP4", "MOVIE", "#FB7185"),
    ".mkv": ("Video Matroska MKV", "MOVIE", "#FB7185"),
    ".avi": ("Video AVI", "MOVIE", "#FB7185"),
    ".mov": ("Video QuickTime MOV", "MOVIE", "#FB7185"),
    ".webm": ("Video WebM", "MOVIE", "#FB7185"),

    # Comprimidos y paquetes
    ".zip": ("Archivo Comprimido ZIP", "FOLDER_ZIP", "#FB923C"),
    ".rar": ("Archivo Comprimido RAR", "FOLDER_ZIP", "#FB923C"),
    ".7z": ("Archivo Comprimido 7-Zip", "FOLDER_ZIP", "#FB923C"),
    ".tar": ("Archivo Tarball TAR", "FOLDER_ZIP", "#FB923C"),
    ".gz": ("Archivo Comprimido GZip", "FOLDER_ZIP", "#FB923C"),

    # Ejecutables y scripts de sistema
    ".exe": ("Ejecutable de Windows", "TERMINAL", "#F43F5E"),
    ".msi": ("Instalador de Windows", "TERMINAL", "#F43F5E"),
    ".bat": ("Script Batch", "TERMINAL", "#F43F5E"),
    ".cmd": ("Comando de Windows", "TERMINAL", "#F43F5E"),
    ".ps1": ("Script PowerShell", "TERMINAL", "#38BDF8"),
    ".sh": ("Script Shell", "TERMINAL", "#34D399"),
}


# ──────────────────────────────────────────────
# Funciones auxiliares de formato y metadatos
# ──────────────────────────────────────────────

def format_bytes(size: int) -> str:
    """
    Formatea bytes a una cadena legible por humanos (B, KB, MB, GB, TB).

    Args:
        size: Tamaño en bytes.

    Returns:
        Cadena formateada (ej. '12.4 KB').
    """
    if size < 0:
        return "0 B"
    if size < 1024:
        return f"{size} B"
    val = float(size)
    for unit in ["KB", "MB", "GB", "TB"]:
        val /= 1024.0
        if val < 1024.0 or unit == "TB":
            return f"{val:.1f} {unit}"
    return f"{val:.1f} PB"


def format_datetime(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Formatea un objeto datetime o retorna guión si es None."""
    if dt is None:
        return "-"
    return dt.strftime(fmt)


def get_type_and_icon(path: Path, is_dir: bool) -> tuple[str, str, str]:
    """
    Determina la descripción legible, clave de ícono y color sugerido para un elemento.

    Args:
        path: Ruta al archivo o carpeta.
        is_dir: True si es directorio.

    Returns:
        Tupla `(type_description, icon_key, color_hex)`
    """
    if is_dir:
        return "Carpeta de archivos", "FOLDER", "#FBBF24"

    ext = path.suffix.lower()
    if ext in _EXTENSION_CATEGORIES:
        return _EXTENSION_CATEGORIES[ext]

    if not ext:
        return "Archivo", "INSERT_DRIVE_FILE", "#64748B"

    return f"Archivo {ext.lstrip('.').upper()}", "INSERT_DRIVE_FILE", "#64748B"


# ──────────────────────────────────────────────
# Modelos de datos
# ──────────────────────────────────────────────

@dataclass
class FileItem:
    """Representa un archivo o carpeta en el explorador."""
    name: str
    path: Path
    is_dir: bool
    size_bytes: int = 0
    size_str: str = ""
    modified_at: Optional[datetime] = None
    modified_str: str = ""
    created_at: Optional[datetime] = None
    created_str: str = ""
    extension: str = ""
    type_desc: str = ""
    icon_key: str = "INSERT_DRIVE_FILE"
    icon_color: str = "#64748B"
    is_hidden: bool = False
    is_symlink: bool = False
    is_readonly: bool = False

    def __init__(
        self,
        name: str = "",
        path: Path | str = Path("."),
        is_dir: bool = False,
        size_bytes: int = 0,
        size_str: str = "",
        modified_at: Optional[datetime] = None,
        modified_str: str = "",
        created_at: Optional[datetime] = None,
        created_str: str = "",
        extension: str = "",
        type_desc: str = "",
        icon_key: str = "INSERT_DRIVE_FILE",
        icon_color: str = "#64748B",
        is_hidden: bool = False,
        is_symlink: bool = False,
        is_readonly: bool = False,
        **kwargs: Any,
    ):
        self.name = name
        self.path = Path(path) if isinstance(path, str) else path
        self.is_dir = is_dir
        self.size_bytes = kwargs.get("size", size_bytes)
        self.size_str = kwargs.get("readable_size", size_str)
        self.modified_at = kwargs.get("modified", modified_at)
        self.modified_str = kwargs.get("readable_date", modified_str)
        self.created_at = kwargs.get("created", created_at)
        self.created_str = created_str
        self.extension = extension
        self.type_desc = kwargs.get("item_type", type_desc)
        self.icon_key = kwargs.get("icon_name", icon_key)
        self.icon_color = icon_color
        self.is_hidden = is_hidden
        self.is_symlink = is_symlink
        self.is_readonly = is_readonly


@dataclass
class FolderSummary:
    """Resumen cuantitativo de una carpeta inspeccionada."""
    path: Path
    total_items: int = 0
    folder_count: int = 0
    file_count: int = 0
    total_bytes: int = 0
    total_bytes_str: str = "0 B"


@dataclass
class QuickAccessItem:
    """Acceso rápido a una ubicación o unidad del sistema."""
    label: str
    path: Path
    icon_key: str
    category: str  # 'places' | 'drives'
    info: str = ""


@dataclass
class ProjectInfo:
    """Información sobre un proyecto de desarrollo detectado en una carpeta."""
    name: str
    project_type: str
    icon_key: str
    color: str
    indicators: list[str]
    description: str



# ──────────────────────────────────────────────
# Detección de Proyectos (Fase 25)
# ──────────────────────────────────────────────

def detect_project(target_path: Optional[Path | str] = None) -> Optional[ProjectInfo]:
    """
    Detecta si una carpeta corresponde a un proyecto de desarrollo y su tecnología.

    Busca marcadores estándar (.git, PROMPT_BASE.md, README.md, .vscode, pyproject.toml, etc.)
    en la ruta especificada.

    Args:
        target_path: Ruta a la carpeta a inspeccionar.

    Returns:
        ProjectInfo con los detalles del proyecto detectado, o None si no se detecta proyecto.
    """
    if target_path is None:
        return None
    path = Path(target_path).resolve()
    if not path.is_dir():
        return None

    try:
        entries = set()
        with os.scandir(path) as it:
            for entry in it:
                entries.add(entry.name.lower())
    except (PermissionError, OSError):
        return None

    indicators: list[str] = []
    p_type = "general"
    p_icon = "FOLDER"
    p_color = "#4A9EFF"
    p_desc = "Proyecto general"

    has_git = ".git" in entries
    if has_git:
        indicators.append(".git")

    # 1. Python / AURA
    py_indicators = [
        f for f in [
            "requirements.txt",
            "pyproject.toml",
            "setup.py",
            "pipfile",
            "environment.yml",
            "prompt_base.md",
        ] if f in entries
    ]
    if py_indicators:
        p_type = "python"
        p_icon = "CODE"
        p_color = "#3776AB"
        p_desc = "Proyecto Python"
        for ind in py_indicators:
            if ind == "prompt_base.md":
                indicators.append("PROMPT_BASE.md")
            elif ind == "pyproject.toml":
                indicators.append("pyproject.toml")
            elif ind == "requirements.txt":
                indicators.append("requirements.txt")
            else:
                indicators.append(ind)

    # 2. Node / JS / TS
    elif "package.json" in entries:
        is_ts = "tsconfig.json" in entries
        p_type = "nodejs"
        p_icon = "CODE"
        p_color = "#3B82F6" if is_ts else "#68A063"
        p_desc = "Proyecto Node.js con TypeScript" if is_ts else "Proyecto JavaScript (Node.js)"
        indicators.append("package.json")
        if is_ts:
            indicators.append("tsconfig.json")

    # 3. Rust
    elif "cargo.toml" in entries:
        p_type = "rust"
        p_icon = "CODE"
        p_color = "#DEA584"
        p_desc = "Proyecto Rust (Cargo)"
        indicators.append("Cargo.toml")

    # 4. Go
    elif "go.mod" in entries:
        p_type = "go"
        p_icon = "CODE"
        p_color = "#22D3EE"
        p_desc = "Módulo Go"
        indicators.append("go.mod")

    # 5. Java / Kotlin
    elif any(f in entries for f in ["pom.xml", "build.gradle", "build.gradle.kts"]):
        ind = [f for f in ["pom.xml", "build.gradle", "build.gradle.kts"] if f in entries]
        p_type = "java"
        p_icon = "CODE"
        p_color = "#F97316"
        p_desc = "Proyecto Java / Kotlin"
        indicators.extend(ind)

    # 6. C/C++
    elif any(f in entries for f in ["cmakelists.txt", "makefile"]):
        ind = [f for f in ["cmakelists.txt", "makefile"] if f in entries]
        p_type = "cpp"
        p_icon = "CODE"
        p_color = "#38BDF8"
        p_desc = "Proyecto C / C++"
        indicators.extend(ind)

    # 7. Web Frontend
    elif "index.html" in entries or any(f.startswith("vite.config") for f in entries):
        p_type = "web"
        p_icon = "HTML"
        p_color = "#F87171"
        p_desc = "Proyecto Web Frontend"
        if "index.html" in entries:
            indicators.append("index.html")

    # 8. Git standalone
    elif has_git:
        p_type = "git"
        p_icon = "STORAGE"
        p_color = "#A855F7"
        p_desc = "Repositorio Git"

    # 9. Marcadores adicionales (.vscode, readme.md)
    elif ".vscode" in entries:
        p_type = "vscode"
        p_icon = "CODE"
        p_color = "#007ACC"
        p_desc = "Proyecto VS Code"
        indicators.append(".vscode")

    elif "readme.md" in entries:
        p_type = "general"
        p_icon = "ARTICLE"
        p_color = "#38BDF8"
        p_desc = "Proyecto Documentado"
        indicators.append("README.md")

    # Marcadores complementarios
    if indicators:
        if ".vscode" in entries and ".vscode" not in indicators:
            indicators.append(".vscode")
        if "readme.md" in entries and "README.md" not in indicators:
            indicators.append("README.md")
        if "prompt_base.md" in entries and "PROMPT_BASE.md" not in indicators:
            indicators.append("PROMPT_BASE.md")
        if "pyproject.toml" in entries and "pyproject.toml" not in indicators:
            indicators.append("pyproject.toml")

    if not indicators:
        return None

    return ProjectInfo(
        name=path.name or str(path),
        project_type=p_type,
        icon_key=p_icon,
        color=p_color,
        indicators=indicators,
        description=f"{p_desc} ({', '.join(indicators)})",
    )


# ──────────────────────────────────────────────
# Motor central del explorador
# ──────────────────────────────────────────────

class FileExplorer:
    """
    Controlador y motor de navegación del sistema de archivos de AURA.

    Gestiona:
    - Ruta actual y validación de existencia/permisos
    - Pila de historial atrás/adelante y subir nivel
    - Listado optimizado con ordenamiento por nombre/tamaño/fecha/tipo
    - Extracción de metadatos detallados y resúmenes de carpetas
    - Detección de unidades y lugares de acceso rápido
    - Apertura segura con la aplicación predeterminada del sistema operativo
    """

    def __init__(self, initial_path: Optional[Path | str] = None, root_dir: Optional[Path | str] = None) -> None:
        """
        Inicializa el explorador en una ruta inicial o el workspace por defecto.
        """
        target = initial_path if initial_path is not None else root_dir
        self.current_path: Path = self._resolve_initial_path(target)
        self.root_dir: Path = self.current_path
        self._history: list[Path] = [self.current_path]
        self._history_idx: int = 0
        _logger.info(f"FileExplorer inicializado en: {self.current_path}")

    @staticmethod
    def _resolve_initial_path(custom_path: Optional[Path | str] = None) -> Path:
        """Resuelve la ruta inicial con fallbacks seguros."""
        if custom_path:
            p = Path(custom_path).expanduser().resolve()
            if p.is_dir():
                return p

        # Intentar leer WORKSPACE_PATH de settings
        try:
            from config.settings import settings
            ws = settings.get("WORKSPACE_PATH", "")
            if ws:
                p = Path(ws).expanduser().resolve()
                if p.is_dir():
                    return p
        except Exception as e:
            _logger.debug(f"No se pudo cargar WORKSPACE_PATH de settings: {e}")

        # Fallbacks a Documentos o Home
        doc_dir = Path.home() / "Documents"
        if doc_dir.is_dir():
            return doc_dir

        return Path.home()

    # ──────────────────────────────────────────
    # Propiedades de navegación
    # ──────────────────────────────────────────

    @property
    def can_go_back(self) -> bool:
        """Retorna True si hay rutas previas en el historial."""
        return self._history_idx > 0

    @property
    def can_go_forward(self) -> bool:
        """Retorna True si hay rutas siguientes en el historial."""
        return self._history_idx < len(self._history) - 1

    @property
    def can_go_up(self) -> bool:
        """Retorna True si el directorio actual tiene un directorio padre accesible."""
        try:
            resolved = self.current_path.resolve()
            return resolved.parent != resolved
        except Exception:
            return False

    # ──────────────────────────────────────────
    # Navegación y gestión de historial
    # ──────────────────────────────────────────

    def navigate(self, target: str | Path, record_history: bool = True) -> tuple[bool, str]:
        """
        Navega hacia una carpeta específica.

        Args:
            target: Ruta destino (str o Path).
            record_history: Si es True, registra la ruta en el historial.

        Returns:
            Tupla `(success, message)`
        """
        try:
            target_path = Path(target).expanduser().resolve()
        except Exception as e:
            _logger.warning(f"Ruta inválida '{target}': {e}")
            return False, f"Ruta inválida: {target}"

        if not target_path.exists():
            return False, f"La carpeta '{target_path.name or str(target_path)}' no existe."

        if not target_path.is_dir():
            return False, f"'{target_path.name}' no es un directorio."

        # Verificar permisos de lectura
        try:
            with os.scandir(target_path) as it:
                pass
        except PermissionError:
            _logger.warning(f"Acceso denegado a '{target_path}'.")
            return False, f"Acceso denegado a '{target_path.name or str(target_path)}'."
        except OSError as e:
            _logger.warning(f"Error accediendo a '{target_path}': {e}")
            return False, f"No se pudo acceder a la carpeta: {e}"

        # Actualizar historial
        if record_history and target_path != self.current_path:
            self._history = self._history[: self._history_idx + 1]
            self._history.append(target_path)
            self._history_idx = len(self._history) - 1

        self.current_path = target_path
        try:
            from core.user_memory import user_memory
            user_memory.record_path(self.current_path, category="folder")
        except Exception as _mem_err:
            _logger.debug("FileExplorer: no se pudo registrar ruta en memoria: %s", _mem_err)

        _logger.debug(f"Navegando a: {self.current_path}")
        return True, ""

    def go_back(self) -> Optional[Path]:
        """Retrocede una posición en el historial de navegación."""
        if not self.can_go_back:
            return None
        self._history_idx -= 1
        self.current_path = self._history[self._history_idx]
        _logger.debug(f"Historial atrás -> {self.current_path}")
        return self.current_path

    def go_forward(self) -> Optional[Path]:
        """Avanza una posición en el historial de navegación."""
        if not self.can_go_forward:
            return None
        self._history_idx += 1
        self.current_path = self._history[self._history_idx]
        _logger.debug(f"Historial adelante -> {self.current_path}")
        return self.current_path

    def go_up(self) -> Optional[Path]:
        """Sube un nivel hacia el directorio padre."""
        if not self.can_go_up:
            return None
        parent = self.current_path.resolve().parent
        success, _ = self.navigate(parent)
        return self.current_path if success else None

    # ──────────────────────────────────────────
    # Listado e inspección
    # ──────────────────────────────────────────

    def list_items(
        self,
        show_hidden: bool = False,
        sort_by: str = "name",
        reverse: bool = False,
    ) -> list[FileItem]:
        """
        Lista todos los archivos y carpetas del directorio actual.

        Args:
            show_hidden: Si es False, omite archivos/carpetas ocultos.
            sort_by: Criterio de ordenamiento ('name', 'size', 'date', 'type').
            reverse: Invierte el orden dentro de cada categoría.

        Returns:
            Lista de FileItem, con carpetas primero, luego archivos.
        """
        items: list[FileItem] = []

        try:
            with os.scandir(self.current_path) as it:
                for entry in it:
                    try:
                        item = self._build_file_item(entry)
                    except Exception as e:
                        _logger.debug(f"Error procesando entrada '{entry.name}': {e}")
                        continue

                    if not show_hidden and item.is_hidden:
                        continue

                    items.append(item)
        except (PermissionError, OSError) as e:
            _logger.error(f"Error listando directorio '{self.current_path}': {e}")
            return []

        # Separar carpetas y archivos para que las carpetas siempre queden agrupadas al inicio
        folders = [i for i in items if i.is_dir]
        files = [i for i in items if not i.is_dir]

        # Definir clave de orden
        if sort_by == "size":
            key_func = lambda i: i.size_bytes
        elif sort_by == "date":
            key_func = lambda i: i.modified_at or datetime.min
        elif sort_by == "type":
            key_func = lambda i: (i.type_desc.lower(), i.name.lower())
        else:  # 'name' por defecto
            key_func = lambda i: i.name.lower()

        folders.sort(key=key_func, reverse=reverse)
        files.sort(key=key_func, reverse=reverse)

        return folders + files

    def _build_file_item(self, entry: os.DirEntry) -> FileItem:
        """Construye un FileItem a partir de un DirEntry."""
        try:
            is_dir = entry.is_dir(follow_symlinks=False)
        except (OSError, PermissionError):
            is_dir = False

        try:
            st = entry.stat(follow_symlinks=False)
            size_bytes = 0 if is_dir else st.st_size
            modified_at = datetime.fromtimestamp(st.st_mtime)
            created_at = datetime.fromtimestamp(st.st_ctime)
            is_symlink = entry.is_symlink()
            is_readonly = not bool(st.st_mode & stat.S_IWRITE)
            is_hidden = entry.name.startswith(".") or (
                hasattr(st, "st_file_attributes")
                and hasattr(stat, "FILE_ATTRIBUTE_HIDDEN")
                and bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN)
            )
        except (OSError, PermissionError):
            size_bytes = 0
            modified_at = None
            created_at = None
            is_symlink = False
            is_readonly = False
            is_hidden = entry.name.startswith(".")

        path = SmartPath(entry.path)
        type_desc, icon_key, icon_color = get_type_and_icon(path, is_dir)

        return FileItem(
            name=entry.name,
            path=path,
            is_dir=is_dir,
            size_bytes=size_bytes,
            size_str="<DIR>" if is_dir else format_bytes(size_bytes),
            modified_at=modified_at,
            modified_str=format_datetime(modified_at),
            created_at=created_at,
            created_str=format_datetime(created_at),
            extension=path.suffix.lower() if not is_dir else "",
            type_desc=type_desc,
            icon_key=icon_key,
            icon_color=icon_color,
            is_hidden=is_hidden,
            is_symlink=is_symlink,
            is_readonly=is_readonly,
        )

    def get_item_info(self, target: str | Path) -> Optional[FileItem]:
        """Retorna la información detallada de un archivo o carpeta específico."""
        try:
            path = SmartPath(target).resolve()
            if not path.exists():
                return None

            is_dir = path.is_dir()
            st = path.stat()
            size_bytes = 0 if is_dir else st.st_size
            modified_at = datetime.fromtimestamp(st.st_mtime)
            created_at = datetime.fromtimestamp(st.st_ctime)
            is_symlink = path.is_symlink()
            is_readonly = not bool(st.st_mode & stat.S_IWRITE)
            is_hidden = path.name.startswith(".") or (
                hasattr(st, "st_file_attributes")
                and hasattr(stat, "FILE_ATTRIBUTE_HIDDEN")
                and bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN)
            )

            type_desc, icon_key, icon_color = get_type_and_icon(path, is_dir)

            return FileItem(
                name=path.name or str(path),
                path=path,
                is_dir=is_dir,
                size_bytes=size_bytes,
                size_str="<DIR>" if is_dir else format_bytes(size_bytes),
                modified_at=modified_at,
                modified_str=format_datetime(modified_at),
                created_at=created_at,
                created_str=format_datetime(created_at),
                extension=path.suffix.lower() if not is_dir else "",
                type_desc=type_desc,
                icon_key=icon_key,
                icon_color=icon_color,
                is_hidden=is_hidden,
                is_symlink=is_symlink,
                is_readonly=is_readonly,
            )
        except Exception as e:
            _logger.debug(f"Error obteniendo info de '{target}': {e}")
            return None

    def get_folder_summary(self, target: Optional[Path | str] = None) -> FolderSummary:
        """
        Calcula un resumen de elementos directos de una carpeta.

        Args:
            target: Directorio a resumir (o current_path si es None).

        Returns:
            FolderSummary con totales de subcarpetas, archivos y bytes.
        """
        p = Path(target).resolve() if target else self.current_path
        if not p.is_dir():
            return FolderSummary(path=p)

        total_items = 0
        folder_count = 0
        file_count = 0
        total_bytes = 0

        try:
            with os.scandir(p) as it:
                for entry in it:
                    try:
                        total_items += 1
                        if entry.is_dir(follow_symlinks=False):
                            folder_count += 1
                        else:
                            file_count += 1
                            total_bytes += entry.stat(follow_symlinks=False).st_size
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError) as e:
            _logger.debug(f"Error calculando resumen para '{p}': {e}")

        return FolderSummary(
            path=p,
            total_items=total_items,
            folder_count=folder_count,
            file_count=file_count,
            total_bytes=total_bytes,
            total_bytes_str=format_bytes(total_bytes),
        )

    # ──────────────────────────────────────────
    # Lugares y Unidades de Disco
    # ──────────────────────────────────────────

    def get_quick_access(self) -> list[QuickAccessItem]:
        """
        Retorna la lista de lugares frecuentes del usuario.
        """
        places: list[QuickAccessItem] = []

        # 1. Espacio de trabajo AURA (WORKSPACE_PATH)
        try:
            from config.settings import settings
            ws_str = settings.get("WORKSPACE_PATH", "")
            if ws_str:
                ws_path = Path(ws_str).expanduser().resolve()
                if ws_path.is_dir():
                    places.append(
                        QuickAccessItem(
                            label="Workspace",
                            path=ws_path,
                            icon_key="WORK_OUTLINE",
                            category="places",
                            info="Directorio de trabajo AURA",
                        )
                    )
        except Exception:
            pass

        # 2. Carpetas personales del usuario
        home = Path.home()
        candidates = [
            ("Usuario", home, "HOME", "Carpeta personal"),
            ("Documentos", home / "Documents", "DESCRIPTION", "Documentos"),
            ("Descargas", home / "Downloads", "DOWNLOAD", "Descargas"),
            ("Escritorio", home / "Desktop", "DESKTOP_WINDOWS", "Escritorio"),
        ]

        for label, path, icon, desc in candidates:
            if path.is_dir() and not any(p.path == path for p in places):
                places.append(
                    QuickAccessItem(
                        label=label,
                        path=path,
                        icon_key=icon,
                        category="places",
                        info=desc,
                    )
                )

        return places

    def get_drives(self) -> list[QuickAccessItem]:
        """
        Detecta las unidades de disco montadas en el sistema.
        """
        drives: list[QuickAccessItem] = []

        if platform.system() == "Windows":
            try:
                import psutil
                for part in psutil.disk_partitions(all=False):
                    drive_path = Path(part.mountpoint)
                    if not drive_path.exists():
                        continue
                    try:
                        usage = shutil.disk_usage(part.mountpoint)
                        free_gb = usage.free / (1024 ** 3)
                        total_gb = usage.total / (1024 ** 3)
                        info = f"{free_gb:.1f} GB libres de {total_gb:.1f} GB"
                    except Exception:
                        info = "Unidad local"

                    dev_name = part.device.rstrip("\\")
                    drives.append(
                        QuickAccessItem(
                            label=f"Disco ({dev_name})",
                            path=drive_path,
                            icon_key="STORAGE",
                            category="drives",
                            info=info,
                        )
                    )
            except Exception as e:
                _logger.debug(f"psutil falló al listar discos: {e}")
                # Fallback simple
                import string
                for letter in string.ascii_uppercase:
                    p = Path(f"{letter}:\\")
                    if p.exists():
                        drives.append(
                            QuickAccessItem(
                                label=f"Disco ({letter}:)",
                                path=p,
                                icon_key="STORAGE",
                                category="drives",
                                info="Unidad local",
                            )
                        )
        else:
            root = Path("/")
            drives.append(
                QuickAccessItem(
                    label="Sistema raíz (/)",
                    path=root,
                    icon_key="STORAGE",
                    category="drives",
                    info="Sistema de archivos principal",
                )
            )

        return drives

    # ──────────────────────────────────────────
    # Acciones con el sistema operativo
    # ──────────────────────────────────────────

    def open_item(self, target: str | Path) -> tuple[bool, str]:
        """
        Abre el elemento. Si es directorio navega hacia él;
        si es un archivo lo ejecuta con la aplicación predeterminada del SO.

        Args:
            target: Ruta al elemento.

        Returns:
            Tupla `(success, message)`
        """
        path = Path(target).resolve()
        if not path.exists():
            return False, f"El elemento '{path.name}' no existe."

        if path.is_dir():
            return self.navigate(path)

        # Archivo: abrir con aplicación predeterminada del sistema
        try:
            _logger.info(f"Abriendo archivo con aplicación predeterminada: {path}")
            if platform.system() == "Windows":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            return True, f"Abierto con la aplicación predeterminada: {path.name}"
        except Exception as e:
            _logger.error(f"Error al abrir archivo '{path}': {e}")
            return False, f"No se pudo abrir el archivo: {e}"

    def open_in_file_manager(self, target: str | Path) -> tuple[bool, str]:
        """
        Abre la ubicación en el explorador de archivos del sistema operativo
        (Windows Explorer, Finder, o gestor de archivos XDG).

        Args:
            target: Archivo o carpeta.

        Returns:
            Tupla `(success, message)`
        """
        path = Path(target).resolve()
        if not path.exists():
            return False, f"La ruta '{path.name}' no existe."

        try:
            _logger.info(f"Abriendo ubicación en el explorador del sistema: {path}")
            if platform.system() == "Windows":
                if path.is_dir():
                    os.startfile(str(path))
                else:
                    # Abre Windows Explorer con el archivo preseleccionado
                    subprocess.Popen(["explorer", f"/select,{str(path)}"])
            elif sys.platform == "darwin":
                if path.is_dir():
                    subprocess.Popen(["open", str(path)])
                else:
                    subprocess.Popen(["open", "-R", str(path)])
            else:
                folder = path if path.is_dir() else path.parent
                subprocess.Popen(["xdg-open", str(folder)])

            return True, f"Ubicación abierta en el explorador del sistema: {path.name}"
        except Exception as e:
            _logger.error(f"Error al abrir en explorador del sistema '{path}': {e}")
            return False, f"Error al abrir en el explorador del sistema: {e}"

    # ──────────────────────────────────────────
    # Fase 25: Búsqueda Inteligente
    # ──────────────────────────────────────────

    def search_items(
        self,
        query: str,
        recursive: bool = False,
        max_results: int = 100,
        search_path: Optional[Path | str] = None,
    ) -> list[FileItem]:
        """
        Busca archivos y carpetas por nombre o patrón glob.

        Args:
            query: Término de búsqueda o patrón (ej. 'app', '*.py', 'notas*').
            recursive: Si es True, busca recursivamente en subdirectorios.
            max_results: Límite de resultados retornados.
            search_path: Directorio base de búsqueda (o current_path si es None).

        Returns:
            Lista de FileItem coincidentes.
        """
        base_path = Path(search_path).resolve() if search_path else self.current_path
        if not base_path.is_dir():
            return []

        query = query.strip()
        if not query:
            return []

        import fnmatch
        is_glob = any(c in query for c in "*?[]")
        query_lower = query.lower()

        def _matches(name: str) -> bool:
            if is_glob:
                return fnmatch.fnmatch(name.lower(), query_lower)
            return query_lower in name.lower()

        results: list[FileItem] = []

        if not recursive:
            try:
                with os.scandir(base_path) as it:
                    for entry in it:
                        if _matches(entry.name):
                            try:
                                results.append(self._build_file_item(entry))
                            except Exception:
                                continue
                            if len(results) >= max_results:
                                break
            except (PermissionError, OSError) as e:
                _logger.debug(f"Error en búsqueda no recursiva en '{base_path}': {e}")
        else:
            skip_dirs = {
                ".git", ".env", "env", "venv", ".venv", "__pycache__",
                "node_modules", ".pytest_cache", ".idea", ".vscode",
            }
            try:
                for root, dirs, files in os.walk(base_path, topdown=True):
                    dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
                    root_path = Path(root)

                    for d in dirs:
                        if _matches(d):
                            dir_path = root_path / d
                            info = self.get_item_info(dir_path)
                            if info:
                                results.append(info)
                            if len(results) >= max_results:
                                break

                    if len(results) >= max_results:
                        break

                    for f in files:
                        if _matches(f):
                            file_path = root_path / f
                            info = self.get_item_info(file_path)
                            if info:
                                results.append(info)
                            if len(results) >= max_results:
                                break

                    if len(results) >= max_results:
                        break
            except (PermissionError, OSError) as e:
                _logger.debug(f"Error en búsqueda recursiva en '{base_path}': {e}")

        # Carpetas primero, luego archivos
        folders = [i for i in results if i.is_dir]
        files = [i for i in results if not i.is_dir]
        folders.sort(key=lambda i: i.name.lower())
        files.sort(key=lambda i: i.name.lower())

        return folders + files

    def search_content(
        self,
        query: str,
        max_results: int = 30,
        search_path: Optional[Path | str] = None,
    ) -> list[tuple[FileItem, str]]:
        """
        Busca texto dentro de archivos en el directorio actual (archivos de texto < 5 MB).

        Returns:
            Lista de tuplas (FileItem, primera_línea_coincidente).
        """
        base_path = Path(search_path).resolve() if search_path else self.current_path
        query = query.strip()
        if not base_path.is_dir() or not query:
            return []

        query_lower = query.lower()
        max_file_size = 5 * 1024 * 1024  # 5 MB
        skip_dirs = {
            ".git", ".env", "env", "venv", ".venv", "__pycache__",
            "node_modules", ".pytest_cache", ".idea", ".vscode",
        }
        text_extensions = {
            ".py", ".txt", ".md", ".json", ".yaml", ".yml", ".toml",
            ".js", ".ts", ".html", ".css", ".xml", ".csv", ".ini",
            ".cfg", ".conf", ".env", ".log", ".bat", ".cmd", ".ps1",
            ".sh", ".c", ".cpp", ".h", ".hpp", ".rs", ".go", ".java",
        }

        results: list[tuple[FileItem, str]] = []

        try:
            for root, dirs, files in os.walk(base_path, topdown=True):
                dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
                root_path = Path(root)

                for file_name in files:
                    file_path = root_path / file_name
                    ext = file_path.suffix.lower()
                    if ext not in text_extensions:
                        continue

                    try:
                        if file_path.stat().st_size > max_file_size:
                            continue
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            for line_num, line in enumerate(f, 1):
                                if query_lower in line.lower():
                                    item = self.get_item_info(file_path)
                                    if item:
                                        snippet = line.strip()[:100]
                                        results.append((item, f"L{line_num}: {snippet}"))
                                    break
                    except Exception:
                        continue

                    if len(results) >= max_results:
                        break

                if len(results) >= max_results:
                    break
        except Exception as e:
            _logger.debug(f"Error buscando texto en '{base_path}': {e}")

        return results

    # ──────────────────────────────────────────
    # Fase 25: Detección y Apertura de Proyectos
    # ──────────────────────────────────────────

    def detect_project(self, target_path: Optional[Path | str] = None) -> Optional[ProjectInfo]:
        """Detecta si una carpeta corresponde a un proyecto de desarrollo y su tecnología."""
        path = Path(target_path).resolve() if target_path else self.current_path
        return detect_project(path)

    def open_in_vscode(self, target: Optional[Path | str] = None) -> tuple[bool, str]:
        """Abre el directorio o archivo en Visual Studio Code."""
        path = Path(target).resolve() if target else self.current_path
        if not path.exists():
            return False, f"La ruta '{path.name}' no existe."

        code_exe = shutil.which("code") or shutil.which("code.cmd")
        if not code_exe and platform.system() == "Windows":
            candidates = [
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd",
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe",
                Path(os.environ.get("ProgramFiles", "")) / "Microsoft VS Code" / "bin" / "code.cmd",
                Path(os.environ.get("ProgramFiles", "")) / "Microsoft VS Code" / "Code.exe",
            ]
            for c in candidates:
                if os.path.isfile(str(c)):
                    code_exe = str(c)
                    break

        if not code_exe:
            return False, "Visual Studio Code no encontrado en el sistema o PATH."

        try:
            _logger.info(f"Abriendo en VS Code: '{path}' con '{code_exe}'")
            subprocess.Popen([code_exe, str(path)], shell=(platform.system() == "Windows"))
            return True, f"Abriendo VS Code en '{path.name}'."
        except Exception as e:
            _logger.error(f"Error al abrir VS Code en '{path}': {e}")
            return False, f"No se pudo abrir VS Code: {e}"

    def open_terminal(self, target: Optional[Path | str] = None) -> tuple[bool, str]:
        """Abre una consola/terminal interactiva en la ubicación seleccionada."""
        path = Path(target).resolve() if target else self.current_path
        if not path.exists():
            return False, f"La ruta '{path.name}' no existe."

        folder = path if path.is_dir() else path.parent

        try:
            _logger.info(f"Abriendo terminal en: '{folder}'")
            if platform.system() == "Windows":
                wt_exe = shutil.which("wt") or shutil.which("wt.exe")
                if wt_exe:
                    subprocess.Popen([wt_exe, "-d", str(folder)])
                else:
                    cmd = f"Set-Location -LiteralPath '{str(folder)}'"
                    creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
                    subprocess.Popen(["powershell.exe", "-NoExit", "-Command", cmd], creationflags=creation_flags)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", "Terminal", str(folder)])
            else:
                terms = ["x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "xterm"]
                launched = False
                for t in terms:
                    if shutil.which(t):
                        subprocess.Popen([t, "--working-directory", str(folder)])
                        launched = True
                        break
                if not launched:
                    return False, "No se encontró ningún emulador de terminal compatible."

            return True, f"Terminal abierta en '{folder.name}'."
        except Exception as e:
            _logger.error(f"Error al abrir terminal en '{folder}': {e}")
            return False, f"No se pudo abrir la terminal: {e}"

    # ──────────────────────────────────────────
    # Fase 25: Acciones Contextuales y Operaciones
    # ──────────────────────────────────────────

    def create_folder(self, name: str, parent_path: Optional[Path | str] = None) -> tuple[bool, str, Optional[str]]:
        """Crea una nueva carpeta en la ruta indicada o en current_path."""
        base = Path(parent_path).resolve() if parent_path else self.current_path
        name = name.strip()
        if not name:
            return False, "El nombre de la carpeta no puede estar vacío.", None

        invalid_chars = set('<>:"/\\|?*')
        if any(c in invalid_chars for c in name):
            return False, "El nombre contiene caracteres no permitidos (< > : \" / \\ | ? *).", None

        target = base / name
        if target.exists():
            return False, f"Ya existe un elemento con el nombre '{name}'.", None

        try:
            target.mkdir(parents=False, exist_ok=False)
            _logger.info(f"FileExplorer: carpeta creada '{target}'")
            return True, f"Carpeta '{name}' creada con éxito.", str(target)
        except PermissionError:
            return False, f"Sin permisos para crear carpetas en '{base.name}'.", None
        except Exception as e:
            _logger.error(f"Error creando carpeta '{target}': {e}")
            return False, f"Error al crear la carpeta: {e}", None

    def create_file(self, name: str, content: str = "", parent_path: Optional[Path | str] = None) -> tuple[bool, str, Optional[str]]:
        """Crea un nuevo archivo vacío o con contenido en la ruta indicada o en current_path."""
        base = Path(parent_path).resolve() if parent_path else self.current_path
        name = name.strip()
        if not name:
            return False, "El nombre del archivo no puede estar vacío.", None

        invalid_chars = set('<>:"/\\|?*')
        if any(c in invalid_chars for c in name):
            return False, "El nombre contiene caracteres no permitidos (< > : \" / \\ | ? *).", None

        target = base / name
        if target.exists():
            return False, f"Ya existe un archivo con el nombre '{name}'.", None

        try:
            target.write_text(content, encoding="utf-8")
            _logger.info(f"FileExplorer: archivo creado '{target}'")
            return True, f"Archivo '{name}' creado con éxito.", str(target)
        except PermissionError:
            return False, f"Sin permisos para crear archivos en '{base.name}'.", None
        except Exception as e:
            _logger.error(f"Error creando archivo '{target}': {e}")
            return False, f"Error al crear el archivo: {e}", None

    def rename_item(self, target: Path | str, new_name: str) -> tuple[bool, str, Optional[str]]:
        """Renombra un archivo o carpeta existente."""
        path = Path(target).resolve()
        if not path.exists():
            return False, f"El elemento '{path.name}' no existe.", None

        new_name = new_name.strip()
        if not new_name:
            return False, "El nuevo nombre no puede estar vacío.", None

        if "/" in new_name or "\\" in new_name:
            return False, "El nuevo nombre no debe incluir rutas ni separadores de carpeta.", None

        invalid_chars = set('<>:"/\\|?*')
        if any(c in invalid_chars for c in new_name):
            return False, "El nombre contiene caracteres no permitidos (< > : \" / \\ | ? *).", None

        destination = path.parent / new_name
        if destination.exists() and destination != path:
            return False, f"Ya existe un elemento con el nombre '{new_name}'.", None

        try:
            path.rename(destination)
            _logger.info(f"FileExplorer: renombrado '{path}' -> '{destination}'")
            return True, f"Renombrado a '{new_name}' con éxito.", str(destination)
        except PermissionError:
            return False, f"Sin permisos para renombrar '{path.name}'.", None
        except Exception as e:
            _logger.error(f"Error renombrando '{path}' a '{new_name}': {e}")
            return False, f"Error al renombrar: {e}", None

    def delete_item(self, target: Path | str, dry_run: bool = False) -> tuple[bool, str]:
        """
        Envía un archivo o carpeta a la papelera de reciclaje de forma segura.
        Registra advertencia en el log (acción destructiva).
        """
        path = Path(target).resolve()
        if not path.exists():
            return False, f"El elemento '{path.name}' no existe."

        tipo = "carpeta" if path.is_dir() else "archivo"

        if dry_run:
            _logger.info(f"FileExplorer: [DRY-RUN] Simulación de eliminación: '{path}'")
            return True, f"[DRY-RUN] [SIMULACIÓN] Se enviaría la {tipo} '{path.name}' a la papelera."

        try:
            _logger.warning(f"Acción destructiva ejecutada: enviando {tipo} '{path}' a la papelera.")
            send2trash.send2trash(str(path))
            return True, f"'{path.name}' fue enviado a la papelera de reciclaje."
        except Exception as e:
            _logger.error(f"Error al enviar '{path}' a la papelera: {e}")
            return False, f"Error al eliminar: {e}"

    def duplicate_item(self, target: Path | str) -> tuple[bool, str, Optional[str]]:
        """Crea una copia duplicada del archivo o carpeta."""
        path = Path(target).resolve()
        if not path.exists():
            return False, f"El elemento '{path.name}' no existe.", None

        parent = path.parent
        stem = path.stem
        suffix = path.suffix
        is_dir = path.is_dir()

        counter = 1
        while True:
            suffix_tag = "_copia" if counter == 1 else f"_copia_{counter}"
            if is_dir:
                cand_name = f"{path.name}{suffix_tag}"
            else:
                cand_name = f"{stem}{suffix_tag}{suffix}"
            destination = parent / cand_name
            if not destination.exists():
                break
            counter += 1

        try:
            if is_dir:
                shutil.copytree(path, destination)
            else:
                shutil.copy2(path, destination)
            _logger.info(f"FileExplorer: duplicado '{path}' -> '{destination}'")
            return True, f"Copia creada: '{destination.name}'.", str(destination)
        except PermissionError:
            return False, f"Sin permisos para duplicar '{path.name}'.", None
        except Exception as e:
            _logger.error(f"Error duplicando '{path}': {e}")
            return False, f"Error al duplicar: {e}", None


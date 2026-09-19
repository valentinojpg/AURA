"""
AURA — Módulo de Memoria de Usuario (Fase 28)

Provee el sistema central de memoria persistente y contexto para AURA Orion:
1. Rutas frecuentes y favoritas:
   - Registro de accesos con conteo de frecuencia y última fecha/hora.
   - Alias amigables de rutas (ej: 'proyectos', 'descargas', 'orion').
   - Consulta de rutas más usadas y recientes.
2. Programas usados habitualmente:
   - Seguimiento de ejecuciones, ejecutables asociados y categorías.
   - Métricas de hábitos de uso para sugerencias inteligentes.
3. Preferencias del usuario:
   - Almacenamiento tipado de opciones y configuraciones personalizadas del usuario.
   - Operaciones get/set/delete con valores por defecto y persistencia atómica.
4. Contexto de proyecto activo:
   - Detección automática del stack tecnológico del proyecto (Python, Node, Rust, etc.).
   - Mantenimiento del proyecto actual activo y notas de sesión.
   - Historial de proyectos recientes en los que el usuario trabaja.
5. Memoria de largo plazo y hechos del usuario (User Facts):
   - Almacenamiento de hechos, reglas, preferencias de interacción y notas personales.
   - Búsqueda semántica/por palabras clave y filtrado por categorías.
   - Generación de contexto enriquecido para inyección en el prompt del sistema de IA.

Persistencia:
- Archivo central en data/memory/user_memory.json.
- Operaciones thread-safe con threading.RLock.
- Guardado atómico (.tmp + rename) con codificación obligatoria UTF-8.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from utils.logger import get_logger

_logger = get_logger("aura.core.user_memory")

# ─────────────────────────────────────────────────────────────────────────────
# Rutas y Constantes
# ─────────────────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_MEMORY_DIR = _PROJECT_ROOT / "data" / "memory"
DEFAULT_MEMORY_FILE = DEFAULT_MEMORY_DIR / "user_memory.json"

# Firmas de archivos para auto-detección del tipo de proyecto
_PROJECT_TYPE_SIGNATURES: list[tuple[str, str]] = [
    ("pyproject.toml", "python"),
    ("requirements.txt", "python"),
    ("setup.py", "python"),
    ("Pipfile", "python"),
    ("tsconfig.json", "typescript"),
    ("package.json", "node"),
    ("Cargo.toml", "rust"),
    ("go.mod", "go"),
    ("pom.xml", "java"),
    ("build.gradle", "java"),
    ("composer.json", "php"),
    ("Gemfile", "ruby"),
    ("CMakeLists.txt", "cpp"),
    ("Makefile", "c/cpp"),
    (".git", "git"),
]


def detect_project_type(directory_path: Union[str, Path]) -> str:
    """
    Detecta automáticamente el stack tecnológico o lenguaje de un proyecto
    inspeccionando los archivos de configuración presentes en su raíz.
    """
    try:
        dir_p = Path(directory_path).resolve()
        if not dir_p.is_dir():
            return "unknown"

        for marker_file, proj_type in _PROJECT_TYPE_SIGNATURES:
            marker_path = dir_p / marker_file
            if marker_path.exists():
                return proj_type

        return "generic"
    except Exception as e:
        _logger.debug(f"detect_project_type: error inspeccionando {directory_path}: {e}")
        return "unknown"


def _normalize_path(path_val: Union[str, Path]) -> str:
    """Normaliza una ruta a string absoluto resolviendo símbolos."""
    try:
        return str(Path(path_val).expanduser().resolve())
    except Exception:
        return str(path_val).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Modelos de Datos Tipados
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PathMemoryEntry:
    """Entrada de memoria para una ruta de archivo o carpeta."""
    path: str
    alias: str = ""
    access_count: int = 1
    last_accessed: str = field(default_factory=lambda: datetime.now().isoformat())
    category: str = "folder"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PathMemoryEntry":
        return cls(
            path=data.get("path", ""),
            alias=data.get("alias", ""),
            access_count=data.get("access_count", 1),
            last_accessed=data.get("last_accessed", datetime.now().isoformat()),
            category=data.get("category", "folder"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ProgramUsageEntry:
    """Entrada de memoria para un programa o ejecutable utilizado."""
    name: str
    executable_path: str = ""
    launch_count: int = 1
    last_launched: str = field(default_factory=lambda: datetime.now().isoformat())
    category: str = "app"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProgramUsageEntry":
        return cls(
            name=data.get("name", ""),
            executable_path=data.get("executable_path", ""),
            launch_count=data.get("launch_count", 1),
            last_launched=data.get("last_launched", datetime.now().isoformat()),
            category=data.get("category", "app"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ProjectContextEntry:
    """Entrada de memoria para el contexto de un proyecto de desarrollo."""
    name: str
    path: str
    project_type: str = "generic"
    last_opened: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 1
    session_notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectContextEntry":
        return cls(
            name=data.get("name", ""),
            path=data.get("path", ""),
            project_type=data.get("project_type", "generic"),
            last_opened=data.get("last_opened", datetime.now().isoformat()),
            access_count=data.get("access_count", 1),
            session_notes=data.get("session_notes", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class UserFact:
    """Hecho o información contextual aprendida sobre el usuario."""
    id: str
    content: str
    category: str = "general"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tags: list[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserFact":
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            content=data.get("content", ""),
            category=data.get("category", "general"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            tags=data.get("tags", []),
            confidence=float(data.get("confidence", 1.0)),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Gestor Central de Memoria de Usuario (UserMemory)
# ─────────────────────────────────────────────────────────────────────────────

class UserMemory:
    """
    Gestor integral de la memoria de usuario de AURA (Fase 28).
    Administra rutas, programas, preferencias, proyectos activos y hechos de largo plazo.
    """

    VERSION = "1.0"

    def __init__(
        self,
        memory_file: Optional[Union[str, Path]] = None,
        autosave: bool = True,
    ) -> None:
        self._path = Path(memory_file).resolve() if memory_file else DEFAULT_MEMORY_FILE
        self._autosave = autosave
        self._lock = threading.RLock()

        # Estructuras de almacenamiento en memoria
        self._paths: dict[str, PathMemoryEntry] = {}
        self._programs: dict[str, ProgramUsageEntry] = {}
        self._preferences: dict[str, Any] = {}
        self._projects: dict[str, ProjectContextEntry] = {}
        self._current_project_path: Optional[str] = None
        self._facts: dict[str, UserFact] = {}

        self._load()

    # ─────────────────────────────────────────────────────────────────────────
    # Persistencia y Carga Segura (UTF-8 y Atómica)
    # ─────────────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Carga los datos de memoria desde el archivo JSON si existe."""
        with self._lock:
            if not self._path.exists():
                _logger.debug(f"UserMemory: no existe {self._path}, iniciando memoria vacía.")
                return

            try:
                with open(self._path, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)

                if not isinstance(data, dict):
                    _logger.warning(f"UserMemory: formato inválido en {self._path}, reiniciando.")
                    return

                # Preferencias
                self._preferences = data.get("preferences", {})

                # Rutas
                self._paths.clear()
                for item in data.get("paths", []):
                    entry = PathMemoryEntry.from_dict(item)
                    if entry.path:
                        self._paths[entry.path] = entry

                # Programas
                self._programs.clear()
                for item in data.get("programs", []):
                    entry = ProgramUsageEntry.from_dict(item)
                    if entry.name:
                        self._programs[entry.name.lower()] = entry

                # Proyectos
                self._projects.clear()
                for item in data.get("projects", []):
                    entry = ProjectContextEntry.from_dict(item)
                    if entry.path:
                        self._projects[entry.path] = entry

                self._current_project_path = data.get("current_project")

                # Hechos
                self._facts.clear()
                for item in data.get("facts", []):
                    fact = UserFact.from_dict(item)
                    if fact.id:
                        self._facts[fact.id] = fact

                _logger.debug(
                    f"UserMemory cargada desde {self._path.name}: "
                    f"{len(self._paths)} rutas, {len(self._programs)} programas, "
                    f"{len(self._projects)} proyectos, {len(self._facts)} hechos."
                )

            except Exception as e:
                _logger.error(f"UserMemory: error al cargar {self._path}: {e}", exc_info=True)

    def save(self) -> bool:
        """Guarda atómicamente el estado actual en el archivo JSON con UTF-8."""
        with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                tmp_file = self._path.with_suffix(".tmp")

                payload = {
                    "version": self.VERSION,
                    "updated_at": datetime.now().isoformat(),
                    "preferences": self._preferences,
                    "current_project": self._current_project_path,
                    "paths": [p.to_dict() for p in self._paths.values()],
                    "programs": [pr.to_dict() for pr in self._programs.values()],
                    "projects": [pj.to_dict() for pj in self._projects.values()],
                    "facts": [f.to_dict() for f in self._facts.values()],
                }

                with open(tmp_file, "w", encoding="utf-8", errors="replace") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)

                shutil.move(str(tmp_file), str(self._path))
                return True
            except Exception as e:
                _logger.error(f"UserMemory: error al guardar en {self._path}: {e}", exc_info=True)
                return False

    def _maybe_save(self) -> None:
        """Ejecuta save() si autosave está habilitado."""
        if self._autosave:
            self.save()

    # ─────────────────────────────────────────────────────────────────────────
    # Rutas Frecuentes y Favoritas
    # ─────────────────────────────────────────────────────────────────────────

    def record_path(
        self,
        path: Union[str, Path],
        alias: str = "",
        category: Optional[str] = None,
        **metadata: Any,
    ) -> PathMemoryEntry:
        """
        Registra un acceso a una ruta de archivo o directorio.
        Incrementa el contador de accesos si ya existía y actualiza la fecha.
        """
        norm_path = _normalize_path(path)
        now_str = datetime.now().isoformat()

        with self._lock:
            if norm_path in self._paths:
                entry = self._paths[norm_path]
                entry.access_count += 1
                entry.last_accessed = now_str
                if alias:
                    entry.alias = alias.strip().lower()
                if category is not None:
                    entry.category = category
                entry.metadata.update(metadata)
            else:
                entry = PathMemoryEntry(
                    path=norm_path,
                    alias=alias.strip().lower(),
                    access_count=1,
                    last_accessed=now_str,
                    category=category or "folder",
                    metadata=metadata,
                )
                self._paths[norm_path] = entry

            self._maybe_save()
            return entry

    def get_path(self, path_or_alias: str) -> Optional[PathMemoryEntry]:
        """Obtiene una entrada de ruta por coincidencia exacta de path o por alias."""
        query = path_or_alias.strip()
        query_lower = query.lower()
        norm_query = _normalize_path(query)

        with self._lock:
            # 1. Búsqueda por path normalizado
            if norm_query in self._paths:
                return self._paths[norm_query]

            # 2. Búsqueda por alias
            for entry in self._paths.values():
                if entry.alias and entry.alias.lower() == query_lower:
                    return entry

            return None

    def get_path_by_alias(self, alias: str) -> Optional[str]:
        """Retorna la ruta física asociada a un alias amigable."""
        alias_clean = alias.strip().lower()
        if not alias_clean:
            return None

        with self._lock:
            for entry in self._paths.values():
                if entry.alias.lower() == alias_clean:
                    return entry.path
            return None

    def set_path_alias(self, path: Union[str, Path], alias: str) -> bool:
        """Asigna o actualiza el alias de una ruta registrada."""
        norm_path = _normalize_path(path)
        alias_clean = alias.strip().lower()

        with self._lock:
            if norm_path in self._paths:
                self._paths[norm_path].alias = alias_clean
            else:
                self._paths[norm_path] = PathMemoryEntry(
                    path=norm_path,
                    alias=alias_clean,
                    access_count=1,
                )
            self._maybe_save()
            return True

    def get_frequent_paths(
        self,
        limit: int = 10,
        category: Optional[str] = None,
    ) -> list[PathMemoryEntry]:
        """Retorna las rutas más accedidas ordenadas por frecuencia descendente."""
        with self._lock:
            entries = list(self._paths.values())
            if category:
                entries = [e for e in entries if e.category == category]
            entries.sort(key=lambda x: x.access_count, reverse=True)
            return entries[:limit]

    def get_recent_paths(
        self,
        limit: int = 10,
        category: Optional[str] = None,
    ) -> list[PathMemoryEntry]:
        """Retorna las rutas más recientemente utilizadas."""
        with self._lock:
            entries = list(self._paths.values())
            if category:
                entries = [e for e in entries if e.category == category]
            entries.sort(key=lambda x: x.last_accessed, reverse=True)
            return entries[:limit]

    def list_paths(self, category: Optional[str] = None) -> list[PathMemoryEntry]:
        """Retorna todas las rutas registradas, opcionalmente filtradas por categoría."""
        with self._lock:
            entries = list(self._paths.values())
            if category:
                entries = [e for e in entries if e.category == category]
            return entries

    def remove_path(self, path_or_alias: str) -> bool:
        """Elimina una ruta de la memoria."""
        entry = self.get_path(path_or_alias)
        if not entry:
            return False

        with self._lock:
            if entry.path in self._paths:
                del self._paths[entry.path]
                self._maybe_save()
                return True
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Programas Usados Habitualmente
    # ─────────────────────────────────────────────────────────────────────────

    def record_program(
        self,
        name: str,
        executable_path: str = "",
        category: Optional[str] = None,
        **metadata: Any,
    ) -> ProgramUsageEntry:
        """
        Registra el lanzamiento de un programa o aplicación.
        Incrementa launch_count y actualiza la última fecha de uso.
        """
        clean_name = name.strip().lower()
        now_str = datetime.now().isoformat()

        with self._lock:
            if clean_name in self._programs:
                entry = self._programs[clean_name]
                entry.launch_count += 1
                entry.last_launched = now_str
                if executable_path:
                    entry.executable_path = executable_path
                if category is not None:
                    entry.category = category
                entry.metadata.update(metadata)
            else:
                entry = ProgramUsageEntry(
                    name=clean_name,
                    executable_path=executable_path,
                    launch_count=1,
                    last_launched=now_str,
                    category=category or "app",
                    metadata=metadata,
                )
                self._programs[clean_name] = entry

            self._maybe_save()
            return entry

    def get_program(self, name: str) -> Optional[ProgramUsageEntry]:
        """Obtiene la ficha de uso de un programa registrado."""
        clean_name = name.strip().lower()
        with self._lock:
            return self._programs.get(clean_name)

    def get_frequent_programs(self, limit: int = 10) -> list[ProgramUsageEntry]:
        """Retorna los programas más lanzados ordenados por frecuencia."""
        with self._lock:
            entries = list(self._programs.values())
            entries.sort(key=lambda x: x.launch_count, reverse=True)
            return entries[:limit]

    def get_recent_programs(self, limit: int = 10) -> list[ProgramUsageEntry]:
        """Retorna los programas usados más recientemente."""
        with self._lock:
            entries = list(self._programs.values())
            entries.sort(key=lambda x: x.last_launched, reverse=True)
            return entries[:limit]

    def list_programs(self, category: Optional[str] = None) -> list[ProgramUsageEntry]:
        """Retorna todos los programas registrados, opcionalmente filtrados por categoría."""
        with self._lock:
            entries = list(self._programs.values())
            if category:
                entries = [e for e in entries if e.category == category]
            return entries

    def remove_program(self, name: str) -> bool:
        """Elimina un programa del historial de uso."""
        clean_name = name.strip().lower()
        with self._lock:
            if clean_name in self._programs:
                del self._programs[clean_name]
                self._maybe_save()
                return True
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Preferencias del Usuario
    # ─────────────────────────────────────────────────────────────────────────

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Obtiene una preferencia del usuario por clave."""
        clean_key = key.strip().lower()
        with self._lock:
            return self._preferences.get(clean_key, default)

    def set_preference(self, key: str, value: Any) -> None:
        """Establece una preferencia del usuario y la persiste."""
        clean_key = key.strip().lower()
        with self._lock:
            self._preferences[clean_key] = value
            self._maybe_save()

    def delete_preference(self, key: str) -> bool:
        """Elimina una preferencia específica."""
        clean_key = key.strip().lower()
        with self._lock:
            if clean_key in self._preferences:
                del self._preferences[clean_key]
                self._maybe_save()
                return True
            return False

    def get_all_preferences(self) -> dict[str, Any]:
        """Retorna una copia de todas las preferencias guardadas."""
        with self._lock:
            return dict(self._preferences)

    # ─────────────────────────────────────────────────────────────────────────
    # Contexto de Proyecto Activo
    # ─────────────────────────────────────────────────────────────────────────

    def set_current_project(
        self,
        path: Union[str, Path],
        name: str = "",
        project_type: str = "",
        **metadata: Any,
    ) -> ProjectContextEntry:
        """
        Establece el proyecto activo actual, detectando su stack si no se especifica.
        """
        norm_path = _normalize_path(path)
        proj_name = name.strip() or Path(norm_path).name or "Proyecto"
        detected_type = project_type.strip() or detect_project_type(norm_path)
        now_str = datetime.now().isoformat()

        with self._lock:
            if norm_path in self._projects:
                entry = self._projects[norm_path]
                entry.access_count += 1
                entry.last_opened = now_str
                if name:
                    entry.name = proj_name
                if project_type:
                    entry.project_type = detected_type
                entry.metadata.update(metadata)
            else:
                entry = ProjectContextEntry(
                    name=proj_name,
                    path=norm_path,
                    project_type=detected_type,
                    last_opened=now_str,
                    access_count=1,
                    metadata=metadata,
                )
                self._projects[norm_path] = entry

            self._current_project_path = norm_path

            # También registrar en la memoria de rutas frecuentes
            self.record_path(norm_path, alias=proj_name.lower(), category="project")

            self._maybe_save()
            return entry

    def get_current_project(self) -> Optional[ProjectContextEntry]:
        """Retorna la ficha del proyecto activo actual o None si no hay ninguno fijado."""
        with self._lock:
            if not self._current_project_path:
                return None
            return self._projects.get(self._current_project_path)

    def clear_current_project(self) -> None:
        """Desvincula el proyecto activo actual."""
        with self._lock:
            self._current_project_path = None
            self._maybe_save()

    def get_project(self, path_or_name: str) -> Optional[ProjectContextEntry]:
        """Busca un proyecto por su ruta normalizada o por su nombre."""
        query = path_or_name.strip()
        norm_path = _normalize_path(query)

        with self._lock:
            if norm_path in self._projects:
                return self._projects[norm_path]

            query_lower = query.lower()
            for p in self._projects.values():
                if p.name.lower() == query_lower:
                    return p
            return None

    def list_projects(self, limit: int = 20) -> list[ProjectContextEntry]:
        """Retorna los proyectos registrados ordenados por último acceso."""
        with self._lock:
            entries = list(self._projects.values())
            entries.sort(key=lambda x: x.last_opened, reverse=True)
            return entries[:limit]

    def add_project_note(
        self,
        note: str,
        project_path: Optional[Union[str, Path]] = None,
    ) -> bool:
        """Agrega una nota contextual al proyecto activo o a uno especificado."""
        note_text = note.strip()
        if not note_text:
            return False

        with self._lock:
            target_path = _normalize_path(project_path) if project_path else self._current_project_path
            if not target_path or target_path not in self._projects:
                return False

            project = self._projects[target_path]
            project.session_notes.append(note_text)
            self._maybe_save()
            return True

    def remove_project(self, path_or_name: str) -> bool:
        """Elimina un proyecto de la lista de proyectos conocidos."""
        project = self.get_project(path_or_name)
        if not project:
            return False

        with self._lock:
            if project.path in self._projects:
                del self._projects[project.path]
                if self._current_project_path == project.path:
                    self._current_project_path = None
                self._maybe_save()
                return True
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Hechos y Memoria de Largo Plazo (User Facts)
    # ─────────────────────────────────────────────────────────────────────────

    def remember(
        self,
        content: str,
        category: str = "general",
        tags: Optional[list[str]] = None,
        fact_id: str = "",
    ) -> UserFact:
        """
        Almacena un hecho, regla o nota permanente sobre el usuario o su entorno.
        Si ya existe un hecho con el mismo id, lo actualiza.
        """
        clean_content = content.strip()
        fid = fact_id.strip() or str(uuid.uuid4())[:8]
        now_str = datetime.now().isoformat()
        clean_tags = [t.strip().lower() for t in (tags or []) if t.strip()]

        with self._lock:
            if fid in self._facts:
                fact = self._facts[fid]
                fact.content = clean_content
                fact.category = category.strip().lower()
                fact.updated_at = now_str
                if clean_tags:
                    fact.tags = list(set(fact.tags + clean_tags))
            else:
                fact = UserFact(
                    id=fid,
                    content=clean_content,
                    category=category.strip().lower(),
                    created_at=now_str,
                    updated_at=now_str,
                    tags=clean_tags,
                )
                self._facts[fid] = fact

            self._maybe_save()
            return fact

    def forget(self, fact_id: str) -> bool:
        """Elimina un hecho de la memoria de largo plazo por su ID."""
        fid = fact_id.strip()
        with self._lock:
            if fid in self._facts:
                del self._facts[fid]
                self._maybe_save()
                return True
            return False

    def get_fact(self, fact_id: str) -> Optional[UserFact]:
        """Recupera un hecho específico por ID."""
        with self._lock:
            return self._facts.get(fact_id.strip())

    def list_facts(self, category: Optional[str] = None) -> list[UserFact]:
        """Lista todos los hechos almacenados, opcionalmente filtrados por categoría."""
        with self._lock:
            facts = list(self._facts.values())
            if category:
                cat_clean = category.strip().lower()
                facts = [f for f in facts if f.category == cat_clean]
            facts.sort(key=lambda x: x.created_at, reverse=True)
            return facts

    def search_facts(
        self,
        query: str,
        category: Optional[str] = None,
    ) -> list[UserFact]:
        """
        Busca hechos por palabras clave en su contenido o en sus tags.
        """
        q_lower = query.strip().lower()
        if not q_lower:
            return self.list_facts(category=category)

        with self._lock:
            results = []
            for fact in self._facts.values():
                if category and fact.category != category.strip().lower():
                    continue

                # Coincidencia en contenido o tags
                if q_lower in fact.content.lower():
                    results.append(fact)
                elif any(q_lower in tag for tag in fact.tags):
                    results.append(fact)

            results.sort(key=lambda x: x.updated_at, reverse=True)
            return results

    def clear_facts(self) -> None:
        """Limpia todos los hechos de la memoria."""
        with self._lock:
            self._facts.clear()
            self._maybe_save()

    # ─────────────────────────────────────────────────────────────────────────
    # Generador de Resumen Contextual para IA
    # ─────────────────────────────────────────────────────────────────────────

    def get_context_summary(self, max_items: int = 5) -> str:
        """
        Genera un resumen legible y didáctico del estado de la memoria del usuario.
        """
        with self._lock:
            sections = []

            # 1. Proyecto Actual
            curr_proj = self.get_current_project()
            if curr_proj:
                notes_part = f" (Notas: {len(curr_proj.session_notes)})" if curr_proj.session_notes else ""
                sections.append(f"📁 **Proyecto Activo**: `{curr_proj.name}` ({curr_proj.project_type.upper()}) en `{curr_proj.path}`{notes_part}")

            # 2. Preferencias destacadas
            if self._preferences:
                pref_items = [f"`{k}`: {v}" for k, v in list(self._preferences.items())[:max_items]]
                sections.append(f"⚙️ **Preferencias**: {', '.join(pref_items)}")

            # 3. Programas Frecuentes
            freq_progs = self.get_frequent_programs(limit=max_items)
            if freq_progs:
                prog_items = [f"`{p.name}` ({p.launch_count}x)" for p in freq_progs]
                sections.append(f"🚀 **Programas habituales**: {', '.join(prog_items)}")

            # 4. Rutas Frecuentes
            freq_paths = self.get_frequent_paths(limit=max_items)
            if freq_paths:
                path_items = [f"`{p.alias or Path(p.path).name}`" for p in freq_paths]
                sections.append(f"📌 **Rutas frecuentes**: {', '.join(path_items)}")

            # 5. Hechos Clave
            facts = self.list_facts()[:max_items]
            if facts:
                fact_lines = [f"- {f.content}" for f in facts]
                sections.append("🧠 **Memoria del usuario**:\n" + "\n".join(fact_lines))

            if not sections:
                return "*(Sin contexto o memoria registrada aún)*"

            return "\n\n".join(sections)

    def to_prompt_context(self) -> str:
        """
        Genera un bloque de texto conciso formateado para inyección en el system prompt de la IA.
        """
        with self._lock:
            lines = []
            curr_proj = self.get_current_project()
            if curr_proj:
                lines.append(f"- Proyecto en curso: {curr_proj.name} (tipo: {curr_proj.project_type}, ruta: {curr_proj.path})")
                if curr_proj.session_notes:
                    lines.append(f"  Notas recientes: {'; '.join(curr_proj.session_notes[-3:])}")

            if self._preferences:
                pref_parts = [f"{k}={v}" for k, v in self._preferences.items()]
                lines.append(f"- Preferencias del usuario: {', '.join(pref_parts[:6])}")

            facts = self.list_facts()[:6]
            if facts:
                for f in facts:
                    lines.append(f"- Recordatorio: {f.content}")

            if not lines:
                return ""

            return "CONTEXTO Y MEMORIA DEL USUARIO:\n" + "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────────
    # Métodos de Utilidad e Importación / Exportación
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Exporta todo el contenido de la memoria a un diccionario."""
        with self._lock:
            return {
                "version": self.VERSION,
                "updated_at": datetime.now().isoformat(),
                "preferences": dict(self._preferences),
                "current_project": self._current_project_path,
                "paths": [p.to_dict() for p in self._paths.values()],
                "programs": [pr.to_dict() for pr in self._programs.values()],
                "projects": [pj.to_dict() for pj in self._projects.values()],
                "facts": [f.to_dict() for f in self._facts.values()],
            }

    def export_json(self, indent: int = 2) -> str:
        """Exporta el estado a cadena JSON formateada con UTF-8."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def import_dict(self, data: dict[str, Any], merge: bool = True) -> None:
        """
        Importa un diccionario de memoria.
        Si merge=True, fusiona con los datos existentes; si merge=False, reemplaza.
        """
        with self._lock:
            if not merge:
                self.clear()

            # Preferencias
            self._preferences.update(data.get("preferences", {}))

            # Rutas
            for item in data.get("paths", []):
                p = PathMemoryEntry.from_dict(item)
                if p.path:
                    if p.path in self._paths and merge:
                        self._paths[p.path].access_count += p.access_count
                    else:
                        self._paths[p.path] = p

            # Programas
            for item in data.get("programs", []):
                pr = ProgramUsageEntry.from_dict(item)
                if pr.name:
                    k = pr.name.lower()
                    if k in self._programs and merge:
                        self._programs[k].launch_count += pr.launch_count
                    else:
                        self._programs[k] = pr

            # Proyectos
            for item in data.get("projects", []):
                pj = ProjectContextEntry.from_dict(item)
                if pj.path:
                    self._projects[pj.path] = pj

            if data.get("current_project"):
                self._current_project_path = data.get("current_project")

            # Hechos
            for item in data.get("facts", []):
                f = UserFact.from_dict(item)
                if f.id:
                    self._facts[f.id] = f

            self._maybe_save()

    def clear(self) -> None:
        """Limpia todos los datos en memoria y reinicia el archivo en disco."""
        with self._lock:
            self._paths.clear()
            self._programs.clear()
            self._preferences.clear()
            self._projects.clear()
            self._current_project_path = None
            self._facts.clear()
            self._maybe_save()


# Instancia singleton predeterminada
user_memory = UserMemory()

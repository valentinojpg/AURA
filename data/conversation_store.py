"""
AURA — Servicio de almacenamiento de conversaciones (Fase 8)

Gestiona la persistencia de conversaciones de chat en disco (JSON).

Características:
    - Cada conversación es un archivo JSON en data/conversations/
    - Formato: {id, title, created_at, updated_at, messages: [{role, content, timestamp}]}
    - Auto-genera título a partir del primer mensaje del usuario
    - Métodos: save, load, list_all, delete, rename, get_active, set_active
    - ID de conversación activa se persiste en la sesión (en RAM; Fase 9 mostrará el listado)
    - Límite configurable de conversaciones guardadas (MAX_CONVERSATIONS = 100)

Decisiones de diseño:
    - JSON puro (stdlib) — sin dependencias externas nuevas
    - Archivos nombrados como: YYYYMMDD_HHMMSS_<id_corto>.json
    - El ID es un UUID4 corto (8 hex chars) para legibilidad
    - Operaciones atómicas: escribe a .tmp → mueve a .json (evita corrupción)
    - Ningún método lanza excepciones no manejadas; errores van al log

Integración con ChatPage:
    - Al enviar un mensaje: auto-guarda la conversación activa
    - Al iniciar (on_enter): carga la conversación activa si existe
    - Conversación nueva: se crea al primer mensaje del usuario
"""

from __future__ import annotations

import json
import os
import uuid
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

_logger = get_logger("aura.data.conversation_store")

# ── Constantes ────────────────────────────────────────────────────────────────
_CONVERSATIONS_DIR = Path(__file__).resolve().parent / "conversations"
_MAX_CONVERSATIONS = 100          # Máximo de archivos guardados
_TITLE_MAX_CHARS   = 60           # Truncar título largo
_ID_LENGTH         = 8            # Longitud del ID corto (hex)


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class StoredMessage:
    """
    Mensaje individual tal como se guarda en disco.

    Agrega `timestamp` a la info de ChatMessage para mostrar
    en el historial de conversaciones.
    """
    role: str        # "user" | "assistant" | "system" | "error"
    content: str
    timestamp: str = ""  # "HH:MM" — vacío para mensajes de sistema

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "StoredMessage":
        return cls(
            role=d.get("role", "user"),
            content=d.get("content", ""),
            timestamp=d.get("timestamp", ""),
        )


@dataclass
class Conversation:
    """
    Conversación completa: metadatos + lista de mensajes.

    id:         UUID corto (8 hex chars)
    title:      Título auto-generado o asignado por el usuario
    created_at: ISO 8601 (str) — momento de creación
    updated_at: ISO 8601 (str) — última modificación
    messages:   Lista de StoredMessage
    """
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[StoredMessage] = field(default_factory=list)

    # ── Serialización ─────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Convierte la conversación a dict serializable."""
        return {
            "id":         self.id,
            "title":      self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages":   [m.to_dict() for m in self.messages],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Conversation":
        """Reconstruye una conversación desde un dict (cargado de JSON)."""
        return cls(
            id=d.get("id", ""),
            title=d.get("title", "Sin título"),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            messages=[StoredMessage.from_dict(m) for m in d.get("messages", [])],
        )

    # ── Utilidades ────────────────────────────────────────────────

    @property
    def message_count(self) -> int:
        """Número de mensajes (excluye mensajes de sistema y error)."""
        return sum(1 for m in self.messages if m.role in ("user", "assistant"))

    @property
    def preview(self) -> str:
        """Primeras palabras del primer mensaje de usuario (para listado)."""
        for m in self.messages:
            if m.role == "user" and m.content.strip():
                preview = m.content.strip()
                return preview[:80] + ("…" if len(preview) > 80 else "")
        return "(sin mensajes)"

    def update_timestamp(self) -> None:
        """Actualiza updated_at al momento actual."""
        self.updated_at = datetime.now().isoformat()


# ── Servicio principal ────────────────────────────────────────────────────────

class ConversationStore:
    """
    Servicio de almacenamiento de conversaciones de AURA.

    Gestiona un directorio de archivos JSON donde cada archivo
    representa una conversación guardada.

    Uso típico:
        store = ConversationStore()
        conv = store.new_conversation()
        conv.messages.append(StoredMessage(role="user", content="Hola"))
        store.save(conv)
        convs = store.list_all()     # → [(id, title, updated_at, msg_count), ...]
        loaded = store.load(conv.id) # → Conversation | None
        store.delete(conv.id)

    Nota sobre la conversación activa:
        ConversationStore no mantiene estado de UI.
        La conversación "activa" se controla desde ChatPage.
    """

    def __init__(self, conversations_dir: Path | None = None):
        """
        Inicializa el store y crea el directorio si no existe.

        Args:
            conversations_dir: Directorio alternativo (útil para tests).
        """
        self._dir = conversations_dir or _CONVERSATIONS_DIR
        self._ensure_dir()
        _logger.debug(f"ConversationStore inicializado — dir: {self._dir}")

    # ── Directorio ────────────────────────────────────────────────

    def _ensure_dir(self) -> None:
        """Crea el directorio de conversaciones si no existe."""
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            _logger.error(f"No se pudo crear directorio de conversaciones: {e}")

    # ── Generación de ID y ruta ───────────────────────────────────

    @staticmethod
    def _new_id() -> str:
        """Genera un ID corto de 8 caracteres hex."""
        return uuid.uuid4().hex[:_ID_LENGTH]

    def _path_for(self, conv_id: str) -> Path:
        """Retorna la ruta del archivo JSON para un ID dado."""
        # Busca el archivo que contenga el ID en el nombre
        for f in self._dir.glob(f"*_{conv_id}.json"):
            return f
        # Si no existe, genera un nombre nuevo
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self._dir / f"{ts}_{conv_id}.json"

    # ── CRUD ──────────────────────────────────────────────────────

    def new_conversation(self, title: str = "") -> Conversation:
        """
        Crea una nueva conversación en memoria (sin guardar en disco).

        El guardado en disco ocurre al llamar a save().

        Args:
            title: Título opcional. Si vacío, se auto-asigna al primer mensaje.
        """
        now = datetime.now().isoformat()
        conv = Conversation(
            id=self._new_id(),
            title=title or "Nueva conversación",
            created_at=now,
            updated_at=now,
            messages=[],
        )
        _logger.debug(f"Nueva conversación en memoria: id={conv.id}")
        return conv

    def save(self, conversation: Conversation) -> bool:
        """
        Guarda (o actualiza) una conversación en disco.

        Escritura atómica: escribe a .tmp y luego renombra a .json.

        Args:
            conversation: Conversación a guardar.

        Returns:
            True si se guardó correctamente, False si hubo error.
        """
        try:
            conversation.update_timestamp()
            path = self._path_for(conversation.id)
            tmp_path = path.with_suffix(".tmp")

            data = json.dumps(
                conversation.to_dict(),
                ensure_ascii=False,
                indent=2,
            )
            tmp_path.write_text(data, encoding="utf-8")
            shutil.move(str(tmp_path), str(path))

            _logger.debug(
                f"Conversación guardada: id={conversation.id}, "
                f"msgs={len(conversation.messages)}, path={path.name}"
            )
            self._enforce_limit()
            return True

        except Exception as e:
            _logger.error(
                f"Error guardando conversación {conversation.id}: {e}",
                exc_info=True,
            )
            return False

    def load(self, conv_id: str) -> Optional[Conversation]:
        """
        Carga una conversación desde disco por su ID.

        Args:
            conv_id: ID de 8 chars de la conversación.

        Returns:
            Conversation si se encontró y se pudo leer, None si no.
        """
        try:
            path = self._path_for(conv_id)
            if not path.exists():
                _logger.warning(f"Conversación no encontrada: id={conv_id}")
                return None

            data = json.loads(path.read_text(encoding="utf-8"))
            conv = Conversation.from_dict(data)
            _logger.debug(
                f"Conversación cargada: id={conv.id}, msgs={len(conv.messages)}"
            )
            return conv

        except Exception as e:
            _logger.error(
                f"Error cargando conversación {conv_id}: {e}",
                exc_info=True,
            )
            return None

    def load_latest(self) -> Optional[Conversation]:
        """
        Carga la conversación más reciente (por updated_at).

        Returns:
            La conversación más reciente, o None si no hay ninguna.
        """
        all_convs = self.list_all()
        if not all_convs:
            return None

        # list_all devuelve en orden descendente de updated_at
        latest_id = all_convs[0]["id"]
        return self.load(latest_id)

    def delete(self, conv_id: str) -> bool:
        """
        Elimina una conversación del disco.

        Args:
            conv_id: ID de la conversación a eliminar.

        Returns:
            True si se eliminó, False si no se encontró o hubo error.
        """
        try:
            path = self._path_for(conv_id)
            if not path.exists():
                _logger.warning(f"delete: conversación no encontrada id={conv_id}")
                return False
            path.unlink()
            _logger.info(f"Conversación eliminada: id={conv_id}")
            return True
        except Exception as e:
            _logger.error(f"Error eliminando conversación {conv_id}: {e}")
            return False

    def rename(self, conv_id: str, new_title: str) -> bool:
        """
        Renombra una conversación (cambia su título).

        Args:
            conv_id:   ID de la conversación.
            new_title: Nuevo título (se trunca a _TITLE_MAX_CHARS).

        Returns:
            True si se renombró correctamente, False si hubo error.
        """
        conv = self.load(conv_id)
        if conv is None:
            return False
        conv.title = new_title[:_TITLE_MAX_CHARS].strip() or "Sin título"
        return self.save(conv)

    def list_all(self) -> list[dict]:
        """
        Lista todas las conversaciones guardadas, ordenadas de más
        reciente a más antigua (por updated_at en el archivo).

        Returns:
            Lista de dicts con: id, title, updated_at, created_at,
            message_count, preview.
        """
        result = []
        try:
            for json_file in sorted(
                self._dir.glob("*.json"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            ):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    conv = Conversation.from_dict(data)
                    result.append({
                        "id":            conv.id,
                        "title":         conv.title,
                        "created_at":    conv.created_at,
                        "updated_at":    conv.updated_at,
                        "message_count": conv.message_count,
                        "preview":       conv.preview,
                    })
                except Exception as e:
                    _logger.warning(f"Error leyendo {json_file.name}: {e}")
        except Exception as e:
            _logger.error(f"Error listando conversaciones: {e}")
        return result

    def count(self) -> int:
        """Retorna el número total de conversaciones guardadas."""
        try:
            return len(list(self._dir.glob("*.json")))
        except Exception:
            return 0

    # ── Generación de título automático ───────────────────────────

    @staticmethod
    def auto_title(first_user_message: str) -> str:
        """
        Genera un título corto a partir del primer mensaje del usuario.

        Toma las primeras palabras hasta _TITLE_MAX_CHARS caracteres.

        Args:
            first_user_message: Primer mensaje del usuario en la conversación.

        Returns:
            Título truncado con "…" si fue recortado.
        """
        text = first_user_message.strip()
        if not text:
            return "Nueva conversación"
        if len(text) <= _TITLE_MAX_CHARS:
            return text
        # Truncar en límite de palabra
        truncated = text[:_TITLE_MAX_CHARS].rsplit(" ", 1)[0]
        return truncated + "…"

    # ── Límite de conversaciones ──────────────────────────────────

    def _enforce_limit(self) -> None:
        """
        Elimina las conversaciones más antiguas si se supera el límite.

        Mantiene las _MAX_CONVERSATIONS más recientes (por mtime).
        """
        try:
            files = sorted(
                self._dir.glob("*.json"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            for old_file in files[_MAX_CONVERSATIONS:]:
                old_file.unlink()
                _logger.info(f"Conversación antigua eliminada (límite): {old_file.name}")
        except Exception as e:
            _logger.warning(f"Error aplicando límite de conversaciones: {e}")


# ── Instancia global del store ────────────────────────────────────────────────
conversation_store = ConversationStore()

# -*- coding: utf-8 -*-
"""
================================================================================
AURA — Registro de Capacidades por Aplicación (Fase 72)
================================================================================
Define y consulta qué operaciones de automatización admite cada programa:
- write:      'clipboard' | 'com' | None
- read:       'win32_edit' | 'com' | None
- save_as:    'com' | 'win32_dialog' | None
- focus_hint: teclas/atajos a enviar antes de pegar texto (por defecto "")

Comportamiento:
- App no listada: asumir write="clipboard", read=None, y registrar en el log
  "Capacidad desconocida para '{app}', aprendida por defecto: write=clipboard, read=null".
- Editable por el usuario vía data/app_capabilities.json.
================================================================================
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from utils.logger import get_logger

_logger = get_logger("aura.core.capabilities")

# Ruta canonical por defecto
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CAPABILITIES_PATH = ROOT_DIR / "data" / "app_capabilities.json"

DEFAULT_CAPABILITIES: dict[str, dict[str, Any]] = {
    "notepad": {"write": "clipboard", "read": "win32_edit"},
    "word": {"write": "com", "read": "com", "save_as": "com"},
    "excel": {"write": "com", "read": "com", "save_as": "com"},
    "discord": {"write": "clipboard", "read": None, "focus_hint": ""},
    "code": {"write": "clipboard", "read": None, "focus_hint": ""},
    "spotify": {"write": None, "read": None},
}

APP_ALIASES: dict[str, str] = {
    "bloc de notas": "notepad",
    "block de notas": "notepad",
    "winword": "word",
    "microsoft word": "word",
    "ms word": "word",
    "microsoft excel": "excel",
    "ms excel": "excel",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "spoty": "spotify",
}

_capabilities_cache: Optional[dict[str, dict[str, Any]]] = None


def normalize_app_name(app_name: str) -> str:
    """Normaliza el nombre de una aplicación para buscar en el registro."""
    if not app_name:
        return ""
    clean = str(app_name).strip().lower()
    for prefix in ("el ", "la ", "los ", "las "):
        if clean.startswith(prefix):
            clean = clean[len(prefix):].strip()
            break
    if clean.endswith(".exe"):
        clean = clean[:-4]
    return APP_ALIASES.get(clean, clean)


def load_capabilities(file_path: Optional[Path] = None) -> dict[str, dict[str, Any]]:
    """
    Carga el registro de capacidades desde el archivo JSON.
    Si el archivo no existe, lo crea con los valores por defecto.
    """
    global _capabilities_cache
    target = Path(file_path) if file_path else DEFAULT_CAPABILITIES_PATH

    if not target.exists():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(DEFAULT_CAPABILITIES, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            _logger.info(f"Registro de capacidades inicializado en '{target}'.")
        except Exception as e:
            _logger.warning(f"No se pudo escribir capacidades por defecto en '{target}': {e}")
            _capabilities_cache = dict(DEFAULT_CAPABILITIES)
            return _capabilities_cache

    try:
        content = target.read_text(encoding="utf-8")
        data = json.loads(content)
        if isinstance(data, dict):
            _capabilities_cache = data
            return data
    except Exception as e:
        _logger.warning(f"Error al leer '{target}': {e}. Usando capacidades por defecto.")

    _capabilities_cache = dict(DEFAULT_CAPABILITIES)
    return _capabilities_cache


def save_capabilities(data: dict[str, dict[str, Any]], file_path: Optional[Path] = None) -> None:
    """Guarda las capacidades en disco de manera segura y atómica."""
    global _capabilities_cache
    target = Path(file_path) if file_path else DEFAULT_CAPABILITIES_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    tmp_target = target.with_suffix(".tmp")
    tmp_target.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp_target.replace(target)
    _capabilities_cache = data


def get_app_capabilities(app_name: str, file_path: Optional[Path] = None) -> dict[str, Any]:
    """
    Obtiene el diccionario de capacidades para una aplicación dada.
    Si la aplicación no está registrada, asume write='clipboard', read=None,
    y lo registra en el log como capacidad desconocida, aprendida por defecto.

    Returns:
        dict con llaves 'write', 'read', 'save_as' (opcional), 'focus_hint' (opcional).
    """
    clean = normalize_app_name(app_name)
    data = load_capabilities(file_path=file_path)

    if clean in data:
        return dict(data[clean])

    # App no listada: fallback por defecto
    _logger.info(
        f"Capacidad desconocida para '{app_name}', aprendida por defecto: write=clipboard, read=null"
    )
    default_entry = {
        "write": "clipboard",
        "read": None,
        "focus_hint": "",
    }
    return default_entry


def register_app_capability(
    app_name: str,
    capabilities: dict[str, Any],
    file_path: Optional[Path] = None,
) -> None:
    """Registra o actualiza las capacidades de una aplicación y persiste el cambio."""
    clean = normalize_app_name(app_name)
    data = load_capabilities(file_path=file_path)
    data[clean] = capabilities
    save_capabilities(data, file_path=file_path)
    _logger.info(f"Capacidad actualizada para '{clean}': {capabilities}")


def reset_capabilities_cache() -> None:
    """Limpia la caché en memoria (útil para pruebas unitarias)."""
    global _capabilities_cache
    _capabilities_cache = None

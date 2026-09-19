"""
AURA — Utilidades generales (Fase 2)

Funciones de propósito general reutilizables en toda la aplicación.
Sin dependencias internas de AURA (solo stdlib).
"""

import os
import sys
import platform
from pathlib import Path
from datetime import datetime


# ──────────────────────────────────────────────
# Sistema
# ──────────────────────────────────────────────

def get_system_info() -> dict[str, str]:
    """
    Retorna información básica del sistema.

    Returns:
        Dict con claves: os, os_version, python_version, architecture.
    """
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "python_version": sys.version.split()[0],
        "architecture": platform.machine(),
    }


def is_windows() -> bool:
    """Retorna True si el sistema operativo es Windows."""
    return platform.system() == "Windows"


# ──────────────────────────────────────────────
# Rutas
# ──────────────────────────────────────────────

def ensure_dir(path: str | Path) -> Path:
    """
    Crea un directorio y todos sus padres si no existen.

    Args:
        path: Ruta al directorio.

    Returns:
        Path resuelto del directorio.
    """
    p = Path(path).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_path(path: str | Path) -> Path:
    """
    Retorna un Path expandido y resuelto desde una cadena.

    Expande '~' y variables de entorno.
    """
    return Path(os.path.expandvars(str(path))).expanduser().resolve()


# ──────────────────────────────────────────────
# Timestamps
# ──────────────────────────────────────────────

def now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Retorna la fecha y hora actual como cadena formateada."""
    return datetime.now().strftime(fmt)


def timestamp_id() -> str:
    """
    Retorna un identificador único basado en el timestamp actual.
    Útil para nombrar conversaciones, backups, etc.

    Ejemplo: '20260803_174523'
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ──────────────────────────────────────────────
# Texto
# ──────────────────────────────────────────────

def truncate(text: str, max_len: int = 80, suffix: str = "…") -> str:
    """
    Trunca un texto a max_len caracteres, agregando suffix si es necesario.

    Args:
        text: Texto a truncar.
        max_len: Longitud máxima permitida (incluyendo suffix).
        suffix: Cadena a agregar al final si se trunca.

    Returns:
        Texto truncado.
    """
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix


def bool_to_str(value: bool) -> str:
    """Convierte un booleano a 'true' o 'false' (formato .env)."""
    return "true" if value else "false"

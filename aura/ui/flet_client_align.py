"""
AURA — Flet Client Alignment & Cache Sanitizer (Fase 78 Fix Ronda 2).

Verifica la versión del paquete Flet instalado en Python frente al binario del
cliente desktop (Flutter runner) y limpia cachés obsoletas o corruptas.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Optional

import flet as ft

from utils.logger import get_logger

_logger = get_logger("aura.ui.flet_client_align")


def get_flet_package_version() -> str:
    """Obtiene la versión del paquete flet de Python."""
    version_mod = getattr(ft, "version", None)
    if version_mod:
        ver = getattr(version_mod, "flet_version", None) or getattr(version_mod, "version", None)
        if ver:
            return str(ver)
    return str(getattr(ft, "__version__", "0.86.5"))


def get_flet_client_path(flet_version: Optional[str] = None) -> Optional[str]:
    """
    Resuelve la ruta al ejecutable cliente de Flet en la plataforma actual.
    """
    if flet_version is None:
        flet_version = get_flet_package_version()

    # 1. Variable de entorno de desarrollo FLET_VIEW_PATH
    flet_view_path = os.environ.get("FLET_VIEW_PATH")
    if flet_view_path and os.path.exists(flet_view_path):
        exe = os.path.join(flet_view_path, "flet.exe" if os.name == "nt" else "flet")
        if os.path.isfile(exe):
            return exe

    # 2. Build local de la aplicación si existe
    build_dir = Path.cwd() / "build" / ("windows" if os.name == "nt" else "linux")
    if build_dir.exists():
        for item in build_dir.iterdir():
            if item.is_file() and (item.suffix.lower() == ".exe" or os.access(item, os.X_OK)):
                return str(item)

    # 3. Directorio de caché estándar ~/.flet/client/
    client_base = Path.home() / ".flet" / "client"
    expected_dir_name = f"flet-desktop-full-{flet_version}"
    client_exe = client_base / expected_dir_name / "flet" / ("flet.exe" if os.name == "nt" else "flet")
    if client_exe.is_file():
        return str(client_exe)

    # Buscar cualquier cliente en client_base
    if client_base.exists():
        for d in client_base.iterdir():
            if d.is_dir():
                candidate = d / "flet" / ("flet.exe" if os.name == "nt" else "flet")
                if candidate.is_file():
                    return str(candidate)

    return None


def clean_stale_flet_caches(flet_version: Optional[str] = None) -> list[str]:
    """
    Detecta y elimina cachés de cliente viejos o directorios temporales que no
    coincidan con la versión pinneada activa de Flet.
    """
    if flet_version is None:
        flet_version = get_flet_package_version()

    cleaned: list[str] = []
    client_base = Path.home() / ".flet" / "client"
    expected_dir_name = f"flet-desktop-full-{flet_version}"

    if client_base.exists():
        try:
            for item in client_base.iterdir():
                if item.is_dir() and item.name != expected_dir_name:
                    # Directorio de versión previa o temporal incompleto
                    try:
                        shutil.rmtree(item, ignore_errors=True)
                        cleaned.append(str(item))
                        _logger.info("Caché de cliente Flet obsoleto eliminado: %s", item)
                    except Exception as ex:
                        _logger.warning("No se pudo eliminar caché obsoleto '%s': %s", item, ex)
        except Exception as ex:
            _logger.debug("Error listando ~/.flet/client: %s", ex)

    # Limpiar archivos temporales residuales de PID de Flet
    try:
        temp_dir = Path(tempfile.gettempdir())
        for f in temp_dir.glob("flet_*.pid"):
            try:
                f.unlink(missing_ok=True)
                cleaned.append(str(f))
            except Exception:
                pass
    except Exception:
        pass

    return cleaned


def align_and_log_flet_client(custom_logger: Optional[Any] = None) -> dict[str, Any]:
    """
    Ejecuta el chequeo de alineación, limpia cachés obsoletos y loguea la
    información del runtime de Flet y el cliente desktop.
    """
    log = custom_logger or _logger
    ver = get_flet_package_version()
    client_path = get_flet_client_path(ver)
    cleaned = clean_stale_flet_caches(ver)

    log.info(
        "Flet runtime: versión del paquete=%s, cliente binario=%s (limpiezas=%d)",
        ver,
        client_path or "no detectado en disco",
        len(cleaned),
    )

    return {
        "version": ver,
        "client_path": client_path,
        "cleaned_caches": cleaned,
    }

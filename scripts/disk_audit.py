# -*- coding: utf-8 -*-
"""
================================================================================
AURA (Orion) — Auditoría de Disco y Uso de Almacenamiento (Fase 81)
================================================================================
Calcula y reporta el tamaño en disco de:
1. Carpetas de primer nivel (y archivos en la raíz), ordenadas descendentemente por tamaño (MB).
2. Subcarpetas Top 10 más pesadas de todo el proyecto (rutas relativas), ordenadas descendentemente por tamaño (MB).
3. Resumen total del proyecto.
Guarda el resultado en logs/disk_audit.txt y lo imprime en consola.
================================================================================
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time

# Reconfigurar salida estándar a UTF-8 para consolas de Windows
try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_dir_size(dir_path: Path) -> int:
    """Calcula el tamaño total en bytes de un directorio recursivamente."""
    total = 0
    try:
        with os.scandir(dir_path) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total += get_dir_size(Path(entry.path))
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        pass
    return total


def run_disk_audit(root: Path = PROJECT_ROOT, save_path: Path | None = None) -> str:
    """
    Ejecuta la auditoría de disco y devuelve el texto del reporte.
    Si save_path es provisto, guarda el reporte en ese archivo (UTF-8).
    """
    root = root.resolve()
    if save_path is None:
        save_path = root / "logs" / "disk_audit.txt"

    first_level_items: list[dict[str, object]] = []
    all_subdirs: list[dict[str, object]] = []
    root_files_size = 0
    root_files_count = 0

    # 1. Escaneo de primer nivel
    try:
        with os.scandir(root) as it:
            for entry in it:
                try:
                    entry_path = Path(entry.path)
                    if entry.is_dir(follow_symlinks=False):
                        dir_sz = get_dir_size(entry_path)
                        first_level_items.append({
                            "name": entry.name + "/",
                            "path": entry_path,
                            "size_bytes": dir_sz,
                            "size_mb": dir_sz / (1024 * 1024),
                        })
                    elif entry.is_file(follow_symlinks=False):
                        sz = entry.stat(follow_symlinks=False).st_size
                        root_files_size += sz
                        root_files_count += 1
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError) as e:
        print(f"Error accediendo a {root}: {e}", file=sys.stderr)

    if root_files_count > 0:
        first_level_items.append({
            "name": f"[Archivos en raiz ({root_files_count})]",
            "path": root,
            "size_bytes": root_files_size,
            "size_mb": root_files_size / (1024 * 1024),
        })

    # Ordenar primer nivel descendente
    first_level_items.sort(key=lambda x: int(x["size_bytes"]), reverse=True)

    # 2. Búsqueda de subcarpetas (profundidad >= 2 respecto a root)
    for fl in first_level_items:
        fl_path = fl["path"]
        if isinstance(fl_path, Path) and fl_path != root and fl_path.is_dir():
            for dirpath, dirnames, _ in os.walk(fl_path):
                dp = Path(dirpath)
                try:
                    rel = dp.relative_to(root)
                except ValueError:
                    continue
                # Solo subcarpetas (longitud de partes >= 2)
                if len(rel.parts) >= 2:
                    sz = get_dir_size(dp)
                    all_subdirs.append({
                        "rel_path": str(rel).replace("\\", "/"),
                        "size_bytes": sz,
                        "size_mb": sz / (1024 * 1024),
                    })

    # Ordenar subcarpetas descendente y tomar top 10
    all_subdirs.sort(key=lambda x: int(x["size_bytes"]), reverse=True)
    top_10_subdirs = all_subdirs[:10]

    total_bytes = sum(int(item["size_bytes"]) for item in first_level_items)
    total_mb = total_bytes / (1024 * 1024)
    total_gb = total_bytes / (1024 * 1024 * 1024)

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    # Construir reporte
    lines = [
        "=" * 80,
        f"AURA (Orion) - AUDITORIA DE DISCO ({timestamp})",
        f"Ruta Base: {root}",
        "=" * 80,
        f"PESO TOTAL DEL PROYECTO: {total_mb:,.2f} MB ({total_gb:.3f} GB)",
        "-" * 80,
        "",
        "[CARPETAS DE PRIMER NIVEL] (ordenadas por tamaño descendente):",
        f"{'Carpeta / Elemento':<40} | {'Tamaño (MB)':>15} | {'% del Total':>12}",
        "-" * 73,
    ]

    for item in first_level_items:
        sz_mb = float(item["size_mb"])
        pct = (int(item["size_bytes"]) / total_bytes * 100) if total_bytes > 0 else 0.0
        lines.append(f"{str(item['name']):<40} | {sz_mb:>12,.2f} MB | {pct:>11.2f}%")

    lines.extend([
        "-" * 73,
        "",
        "[TOP 10 SUBCARPETAS MAS PESADAS] (profundidad >= 2):",
        f"{'Subcarpeta (ruta relativa)':<50} | {'Tamaño (MB)':>15}",
        "-" * 69,
    ])

    for sub in top_10_subdirs:
        sz_mb = float(sub["size_mb"])
        lines.append(f"{str(sub['rel_path']):<50} | {sz_mb:>12,.2f} MB")

    lines.extend([
        "-" * 69,
        "=" * 80,
    ])

    report_text = "\n".join(lines) + "\n"

    # Guardar en logs/disk_audit.txt
    try:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(report_text, encoding="utf-8")
    except Exception as e:
        print(f"Error guardando auditoria en {save_path}: {e}", file=sys.stderr)

    return report_text


def main() -> int:
    report = run_disk_audit()
    try:
        print(report)
    except UnicodeEncodeError:
        print(report.encode("ascii", "replace").decode("ascii"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

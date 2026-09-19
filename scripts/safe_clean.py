# -*- coding: utf-8 -*-
"""
================================================================================
AURA (Orion) — Limpieza Segura del Espacio de Disco (Fase 81)
================================================================================
Ejecuta la limpieza segura de elementos regenerables respetando estrictamente
las líneas rojas de datos irremplazables del usuario.

LÍNEAS ROJAS (PROHIBIDO BORRAR BAJO CUALQUIER CIRCUNSTANCIA):
- models/rvc/ (voz waifu del usuario, irreemplazable)
- assets/backgrounds/current.* y el GIF/PNG original normalizado en uso
- assets/logo.png, assets/logo.ico y arte del usuario
- data/ real (fun, learning, memory, conversations, automations, programs), código, scripts
- .env (y jamás incluirlo en ningún zip)

ELEMENTOS REGENERABLES LIMPIADOS:
1. __pycache__ recursivos y .pytest_cache (fuera de env/).
2. logs/*.log rotados viejos (conservando el log actual activo y auditorías).
3. assets/backgrounds/cache/ (frames extraídos y muestras QA: se regeneran del GIF).
4. data/tts_cache/ SOLO si CLEAN_TTS_CACHE=true en .env (default false).
5. Poda de Whisper: conserva SOLO el modelo de WHISPER_MODEL (default tiny) y
   elimina modelos más pesados no utilizados en models/stt/. Loguea cada archivo con su peso.
================================================================================
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import sys

# Reconfigurar salida estándar a UTF-8 para consolas de Windows
try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def format_size(size_in_bytes: int) -> str:
    """Convierte bytes a formato legible para humanos."""
    val = float(size_in_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if val < 1024.0:
            return f"{val:.2f} {unit}"
        val /= 1024.0
    return f"{val:.2f} TB"


def get_env_variable(key: str, default: str = "", root: Path = PROJECT_ROOT) -> str:
    """Lee una variable desde el archivo .env de forma directa sin dependencias complejas."""
    env_file = root / ".env"
    if not env_file.exists():
        return os.environ.get(key, default)
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == key:
                    clean_v = v.strip().strip("'\"")
                    return clean_v
    except Exception:
        pass
    return os.environ.get(key, default)


def safe_delete_file(file_path: Path, dry_run: bool = False) -> tuple[bool, int]:
    """Elimina un archivo si no viola ninguna línea roja."""
    norm_path = str(file_path.resolve()).replace("\\", "/")
    if "/models/rvc/" in norm_path or norm_path.endswith("/models/rvc"):
        raise PermissionError(f"VIOLACIÓN DE LÍNEA ROJA: Intento de borrar en models/rvc: {file_path}")
    if "/assets/backgrounds/current." in norm_path or "/assets/backgrounds/current_" in norm_path:
        raise PermissionError(f"VIOLACIÓN DE LÍNEA ROJA: Intento de borrar fondo activo: {file_path}")
    if norm_path.endswith("/.env"):
        raise PermissionError(f"VIOLACIÓN DE LÍNEA ROJA: Intento de borrar .env: {file_path}")
    if "/assets/logo.png" in norm_path or "/assets/logo.ico" in norm_path:
        raise PermissionError(f"VIOLACIÓN DE LÍNEA ROJA: Intento de borrar logo de usuario: {file_path}")

    try:
        sz = file_path.stat().st_size
    except OSError:
        sz = 0

    if not dry_run:
        try:
            file_path.unlink(missing_ok=True)
        except OSError as e:
            print(f"  [ERROR] No se pudo eliminar {file_path}: {e}", file=sys.stderr)
            return False, 0
    return True, sz


def run_safe_cleanup(
    root: Path = PROJECT_ROOT,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict[str, object]:
    """
    Ejecuta el proceso completo de limpieza segura de la Fase 81.
    Retorna resumen con estadísticas y detalle de archivos eliminados.
    """
    stats = {
        "bytes_freed": 0,
        "files_removed": 0,
        "pycache_dirs_removed": 0,
        "rotated_logs_removed": 0,
        "bg_cache_files_removed": 0,
        "tts_cache_files_removed": 0,
        "whisper_files_removed": 0,
        "deleted_details": [],  # lista de dicts: {"path": str, "size": int, "category": str}
    }

    print("=" * 80)
    print(f"AURA (Orion) — LIMPIEZA SEGURA DE DISCO {'[MODO DRY-RUN]' if dry_run else ''}")
    print(f"Ruta Base: {root}")
    print("=" * 80)

    # 1. Poda de __pycache__ y .pytest_cache (omitiendo env/)
    print("\n[1/5] Limpiando __pycache__ y caches de pruebas...")
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        dp = Path(dirpath)
        try:
            rel = dp.relative_to(root)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in ("env", ".venv", ".git"):
            continue

        if dp.name in ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"):
            for f in filenames:
                fp = dp / f
                ok, sz = safe_delete_file(fp, dry_run=dry_run)
                if ok:
                    stats["bytes_freed"] += sz
                    stats["files_removed"] += 1
                    stats["deleted_details"].append({
                        "path": str(fp.relative_to(root)).replace("\\", "/"),
                        "size": sz,
                        "category": "pycache",
                    })
            if not dry_run:
                try:
                    shutil.rmtree(dp, ignore_errors=True)
                except Exception:
                    pass
            stats["pycache_dirs_removed"] += 1
            if verbose:
                print(f"  - Eliminado directorio cache: {rel}")

    # 2. Limpieza de logs rotados viejos en logs/ (conservar actual aura.log)
    print("\n[2/5] Limpiando logs rotados viejos...")
    logs_dir = root / "logs"
    if logs_dir.is_dir():
        for item in logs_dir.iterdir():
            if not item.is_file():
                continue
            name = item.name
            if name in ("aura.log", "prompt_assembled.log", "disk_audit.txt", ".gitkeep"):
                continue
            if re.search(r"\.log\.\d+$", name) or name.endswith((".log.bak", ".log.old")):
                ok, sz = safe_delete_file(item, dry_run=dry_run)
                if ok:
                    stats["bytes_freed"] += sz
                    stats["files_removed"] += 1
                    stats["rotated_logs_removed"] += 1
                    rel_str = f"logs/{name}"
                    stats["deleted_details"].append({
                        "path": rel_str,
                        "size": sz,
                        "category": "rotated_log",
                    })
                    print(f"  - Eliminado log rotado: {rel_str} ({format_size(sz)})")

    # 3. Limpieza de assets/backgrounds/cache/ (frames y muestras QA regenerables)
    print("\n[3/5] Limpiando assets/backgrounds/cache/ (frames y QA regenerables)...")
    bg_cache_dir = root / "assets" / "backgrounds" / "cache"
    if bg_cache_dir.is_dir():
        for dirpath, dirnames, filenames in os.walk(bg_cache_dir, topdown=False):
            dp = Path(dirpath)
            for f in filenames:
                fp = dp / f
                ok, sz = safe_delete_file(fp, dry_run=dry_run)
                if ok:
                    stats["bytes_freed"] += sz
                    stats["files_removed"] += 1
                    stats["bg_cache_files_removed"] += 1
                    rel_str = str(fp.relative_to(root)).replace("\\", "/")
                    stats["deleted_details"].append({
                        "path": rel_str,
                        "size": sz,
                        "category": "bg_cache",
                    })
                    if verbose:
                        print(f"  - Eliminado frame/QA: {rel_str} ({format_size(sz)})")
            if not dry_run and dp != bg_cache_dir:
                try:
                    dp.rmdir()
                except OSError:
                    pass
        print(f"  [OK] Limpieza de cache de fondos: {stats['bg_cache_files_removed']} archivos eliminados.")
    else:
        print("  [INFO] assets/backgrounds/cache/ no existe o ya estaba limpio.")

    # 4. Limpieza de data/tts_cache/ (SOLO si CLEAN_TTS_CACHE=true)
    clean_tts = get_env_variable("CLEAN_TTS_CACHE", "false", root=root).lower().strip() == "true"
    print(f"\n[4/5] Evaluando data/tts_cache/ (CLEAN_TTS_CACHE={clean_tts})...")
    tts_cache_dir = root / "data" / "tts_cache"
    if clean_tts:
        if tts_cache_dir.is_dir():
            for item in tts_cache_dir.iterdir():
                if item.is_file() and item.suffix.lower() == ".wav":
                    ok, sz = safe_delete_file(item, dry_run=dry_run)
                    if ok:
                        stats["bytes_freed"] += sz
                        stats["files_removed"] += 1
                        stats["tts_cache_files_removed"] += 1
                        rel_str = f"data/tts_cache/{item.name}"
                        stats["deleted_details"].append({
                            "path": rel_str,
                            "size": sz,
                            "category": "tts_cache",
                        })
                        print(f"  - Eliminado WAV en cache TTS: {rel_str} ({format_size(sz)})")
            print(f"  [OK] Cache TTS limpiado ({stats['tts_cache_files_removed']} archivos).")
    else:
        print("  [CONSERVADO] CLEAN_TTS_CACHE no es 'true'. Se preservan los audios en data/tts_cache/ para evitar re-sintesis lenta con RVC.")

    # 5. Poda de Whisper en models/stt/
    whisper_active = get_env_variable("WHISPER_MODEL", "tiny", root=root).lower().strip() or "tiny"
    print(f"\n[5/5] Poda de Whisper en models/stt/ (Modelo conservado: '{whisper_active}')...")
    stt_dir = root / "models" / "stt"
    if stt_dir.is_dir():
        for item in list(stt_dir.iterdir()):
            item_name_lower = item.name.lower()
            if item.is_dir():
                # Subcarpeta .locks
                if item.name == ".locks":
                    for lock_subdir in list(item.iterdir()):
                        if lock_subdir.is_dir() and whisper_active not in lock_subdir.name.lower():
                            for dp, _, fns in os.walk(lock_subdir, topdown=False):
                                p = Path(dp)
                                for fn in fns:
                                    f_lock = p / fn
                                    ok, sz = safe_delete_file(f_lock, dry_run=dry_run)
                                    if ok:
                                        stats["bytes_freed"] += sz
                                        stats["files_removed"] += 1
                                        stats["whisper_files_removed"] += 1
                                        rel_str = str(f_lock.relative_to(root)).replace("\\", "/")
                                        stats["deleted_details"].append({
                                            "path": rel_str,
                                            "size": sz,
                                            "category": "whisper_prune",
                                        })
                                if not dry_run:
                                    try:
                                        p.rmdir()
                                    except OSError:
                                        pass
                            if not dry_run:
                                try:
                                    lock_subdir.rmdir()
                                except OSError:
                                    pass
                            print(f"  [PODANDO] Subcarpeta de lock no utilizada: models/stt/.locks/{lock_subdir.name}")
                    continue

                # Si corresponde al modelo activo, SE CONSERVA ESTRICTAMENTE
                if whisper_active in item_name_lower:
                    print(f"  [CONSERVADO] Modelo activo: models/stt/{item.name}")
                    continue

                # Si es otro modelo de whisper, se poda por completo
                if "faster-whisper" in item_name_lower or "models--" in item_name_lower:
                    print(f"  [PODANDO] Modelo no utilizado: models/stt/{item.name}...")
                    for dirpath, dirnames, filenames in os.walk(item, topdown=False):
                        dp = Path(dirpath)
                        for f in filenames:
                            fp = dp / f
                            ok, sz = safe_delete_file(fp, dry_run=dry_run)
                            if ok:
                                stats["bytes_freed"] += sz
                                stats["files_removed"] += 1
                                stats["whisper_files_removed"] += 1
                                rel_str = str(fp.relative_to(root)).replace("\\", "/")
                                stats["deleted_details"].append({
                                    "path": rel_str,
                                    "size": sz,
                                    "category": "whisper_prune",
                                })
                                print(f"    - Eliminado: {rel_str} ({format_size(sz)})")
                        if not dry_run:
                            try:
                                dp.rmdir()
                            except OSError:
                                pass
            elif item.is_file() and item.name.endswith(".lock"):
                if whisper_active not in item_name_lower:
                    ok, sz = safe_delete_file(item, dry_run=dry_run)
                    if ok:
                        stats["bytes_freed"] += sz
                        stats["files_removed"] += 1
                        stats["whisper_files_removed"] += 1
                        rel_str = str(item.relative_to(root)).replace("\\", "/")
                        stats["deleted_details"].append({
                            "path": rel_str,
                            "size": sz,
                            "category": "whisper_prune",
                        })
                        print(f"    - Eliminado lock: {rel_str}")
        print(f"  [OK] Poda de Whisper finalizada: {stats['whisper_files_removed']} archivos eliminados.")
    else:
        print("  [INFO] models/stt/ no existe o no contiene modelos.")

    print("\n" + "=" * 80)
    print("RESUMEN DE LIMPIEZA SEGURA:")
    print(f"  Total de archivos eliminados: {stats['files_removed']}")
    print(f"  Total de espacio liberado:    {format_size(stats['bytes_freed'])} ({stats['bytes_freed']:,} bytes)")
    print(f"  Detalle:")
    print(f"    - Directorios pycache:       {stats['pycache_dirs_removed']}")
    print(f"    - Logs rotados viejos:       {stats['rotated_logs_removed']}")
    print(f"    - Frames/QA de fondos cache: {stats['bg_cache_files_removed']}")
    print(f"    - Archivos cache TTS:        {stats['tts_cache_files_removed']}")
    print(f"    - Archivos Whisper podados:  {stats['whisper_files_removed']}")
    print("=" * 80 + "\n")

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Limpieza segura de espacio en AURA Orion (Fase 81)")
    parser.add_argument("--dry-run", action="store_true", help="Simular la limpieza sin borrar nada")
    parser.add_argument("--quiet", action="store_true", help="Modo silencioso (menos verbosidad)")
    args = parser.parse_args()

    run_safe_cleanup(dry_run=args.dry_run, verbose=not args.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())

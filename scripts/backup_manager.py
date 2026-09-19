# -*- coding: utf-8 -*-
"""
============================================================
AURA (Orion) — Gestor de Backups y Restauración Portable
Fase 30: Onboarding, portabilidad y pulido final
============================================================
Permite empaquetar de forma segura la carpeta de datos (data/)
y las configuraciones (.env) en archivos ZIP con marca de tiempo,
así como listar y restaurar respaldos previos.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
from pathlib import Path
import sys
import zipfile

logger = logging.getLogger("AURA.BackupManager")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_BACKUP_DIR = DATA_DIR / "backups"

# Carpetas y archivos a excluir del backup
EXCLUDE_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".git",
    "backups",
    "backup_pre_utf8",
    ".mypy_cache",
    ".cache",
}

EXCLUDE_EXTENSIONS = {
    ".tmp",
    ".temp",
    ".pyc",
    ".pyo",
    ".pyd",
    ".lock",
}


def _format_size(size_in_bytes: int) -> str:
    """Convierte bytes a un formato legible (KB, MB, GB)."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.1f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.1f} TB"


def _should_exclude(rel_path: Path) -> bool:
    """Determina si un archivo o directorio debe ser excluido."""
    parts = set(rel_path.parts)
    if any(ex in parts for ex in EXCLUDE_DIRS):
        return True
    if rel_path.suffix.lower() in EXCLUDE_EXTENSIONS:
        return True
    return False


def create_backup(
    target_dir: Path | str | None = None,
    include_env: bool = True,
    tag: str | None = None,
) -> Path:
    """
    Crea un archivo ZIP con el contenido de data/ y opcionalmente .env.

    :param target_dir: Carpeta destino para el ZIP (por defecto data/backups/).
    :param include_env: Si se debe incluir el archivo .env en la raíz del ZIP.
    :param tag: Etiqueta opcional para añadir al nombre del archivo.
    :return: Path al archivo ZIP generado.
    """
    dest_dir = Path(target_dir) if target_dir else DEFAULT_BACKUP_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tag_part = f"_{tag}" if tag else ""
    zip_filename = f"backup_{timestamp}{tag_part}.zip"
    zip_path = dest_dir / zip_filename

    archived_files: list[str] = []
    total_uncompressed_bytes = 0

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. Empaquetar data/
        if DATA_DIR.exists():
            for root, dirs, files in os.walk(DATA_DIR):
                root_path = Path(root)
                rel_to_data = root_path.relative_to(DATA_DIR)

                # Filtrar subdirectorios a excluir
                dirs[:] = [d for d in dirs if not _should_exclude(rel_to_data / d)]

                for file in files:
                    file_path = root_path / file
                    rel_file = file_path.relative_to(DATA_DIR)

                    if _should_exclude(rel_file):
                        continue

                    # Guardar con prefijo data/...
                    arcname = f"data/{rel_file.as_posix()}"
                    zf.write(file_path, arcname=arcname)
                    size = file_path.stat().st_size
                    total_uncompressed_bytes += size
                    archived_files.append(arcname)

        # 2. Empaquetar .env si existe y fue solicitado
        if include_env and ENV_FILE.is_file():
            zf.write(ENV_FILE, arcname=".env")
            env_size = ENV_FILE.stat().st_size
            total_uncompressed_bytes += env_size
            archived_files.append(".env")

        # 3. Añadir manifiesto descriptivo
        manifest = {
            "created_at": datetime.datetime.now().isoformat(),
            "aura_system": "AURA Orion",
            "version": "1.0.0",
            "files_count": len(archived_files),
            "total_uncompressed_bytes": total_uncompressed_bytes,
            "total_uncompressed_human": _format_size(total_uncompressed_bytes),
            "files": archived_files,
        }
        manifest_data = json.dumps(manifest, ensure_ascii=False, indent=2)
        zf.writestr("manifest.json", manifest_data)

    logger.info("Backup creado exitosamente en: %s", zip_path)
    return zip_path


def list_backups(backup_dir: Path | str | None = None) -> list[dict]:
    """
    Lista todos los archivos de respaldo encontrados en backup_dir ordenados cronológicamente.
    """
    search_dir = Path(backup_dir) if backup_dir else DEFAULT_BACKUP_DIR
    if not search_dir.exists():
        return []

    backups: list[dict] = []
    for entry in search_dir.glob("backup_*.zip"):
        if not entry.is_file():
            continue

        stat = entry.stat()
        info: dict = {
            "filename": entry.name,
            "path": str(entry.resolve()),
            "size_bytes": stat.st_size,
            "size_human": _format_size(stat.st_size),
            "created_at": datetime.datetime.fromtimestamp(stat.st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "manifest": None,
        }

        # Intentar leer manifest.json si existe en el ZIP
        try:
            with zipfile.ZipFile(entry, "r") as zf:
                if "manifest.json" in zf.namelist():
                    with zf.open("manifest.json") as mf:
                        info["manifest"] = json.loads(mf.read().decode("utf-8"))
        except Exception:
            pass

        backups.append(info)

    # Ordenar por fecha más reciente primero
    backups.sort(key=lambda b: b["created_at"], reverse=True)
    return backups


def restore_backup(
    zip_path: Path | str,
    target_data_dir: Path | str | None = None,
    restore_env: bool = True,
    dry_run: bool = False,
) -> dict:
    """
    Restaura los archivos de un ZIP de backup hacia la carpeta data/ y .env.

    :param zip_path: Ruta al archivo ZIP de backup.
    :param target_data_dir: Carpeta destino de los datos (por defecto PROJECT_ROOT/data).
    :param restore_env: Si se debe restaurar el archivo .env.
    :param dry_run: Si es True, no escribe ningún archivo en disco y sólo simula.
    :return: Diccionario con el resultado de la restauración.
    """
    source_zip = Path(zip_path)
    if not source_zip.exists():
        raise FileNotFoundError(f"No se encontró el archivo de backup: {zip_path}")

    target_data = Path(target_data_dir) if target_data_dir else DATA_DIR
    restored_items: list[str] = []
    skipped_items: list[str] = []

    with zipfile.ZipFile(source_zip, "r") as zf:
        infolist = zf.infolist()

        for member in infolist:
            filename = member.filename
            # Protección contra Directory Traversal (Zip Slip)
            if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
                skipped_items.append(filename)
                continue

            if filename == "manifest.json":
                continue

            # Archivo .env
            if filename == ".env":
                if restore_env:
                    dest = PROJECT_ROOT / ".env"
                    restored_items.append(".env")
                    if not dry_run:
                        dest.write_bytes(zf.read(filename))
                else:
                    skipped_items.append(".env")
                continue

            # Archivos bajo data/
            if filename.startswith("data/"):
                rel_under_data = filename[len("data/"):]
                if not rel_under_data or rel_under_data.endswith("/"):
                    continue
                dest = target_data / rel_under_data
                restored_items.append(filename)
                if not dry_run:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(filename))
            else:
                # Otros archivos no categorizados
                skipped_items.append(filename)

    return {
        "success": True,
        "dry_run": dry_run,
        "backup_source": str(source_zip),
        "target_data_dir": str(target_data),
        "restored_count": len(restored_items),
        "restored_files": restored_items,
        "skipped_files": skipped_items,
    }


def main() -> None:
    """Punto de entrada CLI para backup_manager."""
    parser = argparse.ArgumentParser(
        description="AURA Orion — Gestor portable de backups y restauracion."
    )
    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar")

    # create
    cmd_create = subparsers.add_parser("create", help="Crear un nuevo backup ZIP")
    cmd_create.add_argument(
        "--out-dir", type=str, default=None, help="Carpeta de salida para el ZIP"
    )
    cmd_create.add_argument(
        "--no-env", action="store_true", help="No incluir el archivo .env"
    )
    cmd_create.add_argument(
        "--tag", type=str, default=None, help="Etiqueta para el nombre del backup"
    )

    # list
    cmd_list = subparsers.add_parser("list", help="Listar backups existentes")
    cmd_list.add_argument(
        "--dir", type=str, default=None, help="Carpeta de backups a explorar"
    )

    # restore
    cmd_restore = subparsers.add_parser("restore", help="Restaurar desde un backup ZIP")
    cmd_restore.add_argument("zip_file", type=str, help="Ruta al archivo ZIP a restaurar")
    cmd_restore.add_argument(
        "--dry-run", action="store_true", help="Simular sin modificar archivos"
    )
    cmd_restore.add_argument(
        "--no-env", action="store_true", help="No sobreescribir el archivo .env"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "create":
        print("\n[AURA Backup] Creando respaldo de datos y configuraciones...")
        zip_path = create_backup(
            target_dir=args.out_dir,
            include_env=not args.no_env,
            tag=args.tag,
        )
        size_human = _format_size(zip_path.stat().st_size)
        print("[OK] Backup creado con exito:")
        print(f"     Archivo: {zip_path.name}")
        print(f"     Ruta:    {zip_path.resolve()}")
        print(f"     Tamano:  {size_human}\n")

    elif args.command == "list":
        backups = list_backups(backup_dir=args.dir)
        print(f"\n[AURA Backup] Backups encontrados: {len(backups)}")
        if not backups:
            print("  (No se encontraron respaldos en data/backups/)\n")
            return

        print(f"{'FECHA':<20} | {'TAMANO':<10} | {'ARCHIVOS':<8} | {'NOMBRE'}")
        print("-" * 75)
        for b in backups:
            files_cnt = b["manifest"]["files_count"] if b.get("manifest") else "?"
            print(
                f"{b['created_at']:<20} | {b['size_human']:<10} | {str(files_cnt):<8} | {b['filename']}"
            )
        print()

    elif args.command == "restore":
        dry_str = " (MODO SIMULACION - DRY RUN)" if args.dry_run else ""
        print(f"\n[AURA Backup] Restaurando respaldo{dry_str}...")
        try:
            res = restore_backup(
                zip_path=args.zip_file,
                restore_env=not args.no_env,
                dry_run=args.dry_run,
            )
            print("[OK] Restauracion completada:")
            print(f"     Archivos restaurados: {res['restored_count']}")
            if res['skipped_files']:
                print(f"     Archivos omitidos:    {len(res['skipped_files'])}")
            print()
        except Exception as e:
            print(f"[ERROR] Error al restaurar: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()

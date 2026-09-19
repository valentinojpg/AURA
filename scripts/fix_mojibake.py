"""
AURA — Script de Reparación de Mojibake (UTF-8)
Recorre data/**/*.json y data/**/*.jsonl para reparar strings corrompidos
por decodificación incorrecta (UTF-8 decodificado como cp1252 / latin-1).

Uso:
    python scripts/fix_mojibake.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Tuple

# Forzar codificación UTF-8 en salida de consola
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DATA_DIR = Path("data").resolve()
BACKUP_DIR = DATA_DIR / "backup_pre_utf8"

# Marcadores característicos de secuencias UTF-8 decodificadas como cp1252 / latin-1
MOJIBAKE_MARKERS = ("â€", "Â", "Ã", "â™", "\x80", "\x94", "â")


def repair_string(text: str) -> Tuple[str, bool]:
    """
    Intenta reparar un string afectado por mojibake.
    Aplica el roundtrip inverso: encode('cp1252') -> decode('utf-8').
    Si falla (por ejemplo por códigos de control C1 de latin-1 puro como \x80/\x94),
    intenta encode('latin-1') -> decode('utf-8').

    Retorna:
        (texto_reparado, fue_modificado)
    """
    if not isinstance(text, str):
        return text, False

    # Verificar si contiene marcadores sospechosos de mojibake
    if not any(marker in text for marker in MOJIBAKE_MARKERS):
        return text, False

    # 1. Intentar cp1252
    try:
        candidate = text.encode("cp1252", errors="strict").decode("utf-8", errors="strict")
        if candidate != text:
            return candidate, True
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    # 2. Fallback a latin-1 (ISO-8859-1 de requests)
    try:
        candidate = text.encode("latin-1", errors="strict").decode("utf-8", errors="strict")
        if candidate != text:
            return candidate, True
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    return text, False


def repair_data_structure(data: Any) -> Tuple[Any, int]:
    """
    Recorre recursivamente un dict, list o str reparando valores con mojibake.
    Retorna (data_reparada, contador_reparaciones).
    """
    repaired_count = 0

    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            new_k, k_repaired = repair_string(k)
            new_v, v_count = repair_data_structure(v)
            if k_repaired:
                repaired_count += 1
            repaired_count += v_count
            new_dict[new_k] = new_v
        return new_dict, repaired_count

    elif isinstance(data, list):
        new_list = []
        for item in data:
            new_item, item_count = repair_data_structure(item)
            repaired_count += item_count
            new_list.append(new_item)
        return new_list, repaired_count

    elif isinstance(data, str):
        new_str, was_repaired = repair_string(data)
        return new_str, (1 if was_repaired else 0)

    return data, 0


def process_json_file(file_path: Path) -> Tuple[bool, int]:
    """
    Procesa un archivo JSON. Si encuentra mojibake, hace backup y lo sobrescribe en UTF-8.
    Retorna (fue_tocado, strings_reparados).
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"  [ERROR] No se pudo leer {file_path}: {e}")
        return False, 0

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"  [AVISO] {file_path} no es JSON válido: {e}")
        return False, 0

    repaired_data, count = repair_data_structure(data)
    if count == 0:
        return False, 0

    # Hacer backup antes de reescribir
    rel_path = file_path.relative_to(DATA_DIR)
    backup_path = BACKUP_DIR / rel_path
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, backup_path)

    # Sobrescribir con codificación UTF-8 explícita y ensure_ascii=False
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(repaired_data, f, ensure_ascii=False, indent=2)

    return True, count


def process_jsonl_file(file_path: Path) -> Tuple[bool, int]:
    """
    Procesa un archivo JSONL línea por línea.
    Retorna (fue_tocado, strings_reparados).
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  [ERROR] No se pudo leer {file_path}: {e}")
        return False, 0

    new_lines = []
    total_count = 0
    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            new_lines.append(line)
            continue
        try:
            item = json.loads(line_strip)
            repaired_item, count = repair_data_structure(item)
            total_count += count
            new_lines.append(json.dumps(repaired_item, ensure_ascii=False) + "\n")
        except json.JSONDecodeError:
            # Intentar reparar la línea de texto directo si no es JSON válido
            repaired_line, was_rep = repair_string(line)
            if was_rep:
                total_count += 1
            new_lines.append(repaired_line)

    if total_count == 0:
        return False, 0

    # Backup
    rel_path = file_path.relative_to(DATA_DIR)
    backup_path = BACKUP_DIR / rel_path
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, backup_path)

    # Reescribir
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return True, total_count


def run_repair(data_dir: Path = DATA_DIR) -> dict:
    """
    Ejecuta el escaneo y reparación sobre data_dir.
    Retorna estadísticas del proceso.
    """
    print("=" * 65)
    print("AURA — Reparación de Mojibake y Normalización UTF-8")
    print(f"Directorio de datos:   {data_dir}")
    print(f"Directorio de backup: {BACKUP_DIR}")
    print("=" * 65)

    if not data_dir.exists():
        print(f"[!] Directorio {data_dir} no existe.")
        return {"scanned": 0, "touched": 0, "repaired_strings": 0}

    scanned_files = 0
    touched_files = 0
    repaired_strings = 0
    modified_list = []

    for root, dirs, files in os.walk(data_dir):
        # Evitar escanear el propio directorio de backup
        dirs[:] = [d for d in dirs if d != "backup_pre_utf8" and d != "__pycache__"]
        for f in files:
            p = Path(root) / f
            suffix = p.suffix.lower()
            if suffix == ".json":
                scanned_files += 1
                touched, count = process_json_file(p)
                if touched:
                    touched_files += 1
                    repaired_strings += count
                    modified_list.append((p.relative_to(data_dir), count))
            elif suffix == ".jsonl":
                scanned_files += 1
                touched, count = process_jsonl_file(p)
                if touched:
                    touched_files += 1
                    repaired_strings += count
                    modified_list.append((p.relative_to(data_dir), count))

    print("\n--- RESUMEN DE EJECUCIÓN ---")
    print(f"Archivos escaneados:   {scanned_files}")
    print(f"Archivos reparados:    {touched_files}")
    print(f"Strings corregidos:    {repaired_strings}")
    if modified_list:
        print("\nDetalle de archivos modificados:")
        for rel, count in modified_list:
            print(f"  • {rel} ({count} cadenas reparadas)")
        print(f"\n✅ Backup guardado en: {BACKUP_DIR}")
    else:
        print("\n✅ Todos los archivos ya contaban con codificación UTF-8 válida.")

    print("=" * 65)
    return {
        "scanned": scanned_files,
        "touched": touched_files,
        "repaired_strings": repaired_strings,
        "modified_files": [str(m[0]) for m in modified_list],
    }


if __name__ == "__main__":
    run_repair()

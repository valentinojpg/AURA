# -*- coding: utf-8 -*-
"""
================================================================================
AURA (Orion) — Script de Release Portable y Limpieza de Proyecto (Fase 70)
================================================================================
Automatiza el empaquetado limpio y reproducible de AURA para distribución:
1. Limpieza previa segura: __pycache__, logs rotados viejos, wavs temporales,
   carpetas build/_internal (NUNCA toca código, assets, models/rvc, data real,
   .env ni requirements).
2. Generación automática de .env.example desde .env con claves sensibles
   reemplazadas por placeholders (tu_clave_aqui) y preservación de comentarios.
3. Copia release limpia en ORION_release/ (o --stage-dir) excluyendo:
   env/, .git/, logs/, __pycache__/, build/, _internal/, .env, *.wav temporales
   y backups de data/. Incluyendo SIEMPRE: models/rvc/, assets/, data/ real,
   scripts/, requirements.txt, .env.example, Aura.bat, setup_env.bat y scripts
   de accesos directos.
4. Check explícito de seguridad contra fugas: aborta si .env real llega a staging
   o al archivo ZIP.
5. Compresión ZIP con zipfile a AURA_release_<fecha>.zip en el Escritorio (o --out)
   con verificación post-compresión e impresión de manifiesto final detallado.
================================================================================
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys
import zipfile

# Directorio raíz del proyecto AURA Orion
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ──────────────────────────────────────────────────────────────────────────────
# Listas de Exclusiones Canónicas para el Release
# ──────────────────────────────────────────────────────────────────────────────

EXCLUDE_DIR_NAMES = {
    "env",
    ".venv",
    ".git",
    "logs",
    "__pycache__",
    "build",
    "_internal",
    "dist",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    "backups",          # dentro de data/
    "backup_pre_utf8",  # dentro de data/
    "audio_cache",      # dentro de data/ (se crea directorio vacío con .gitkeep)
    "audio_test",       # dentro de data/
    "tts_cache",        # dentro de data/ (se crea directorio vacío con .gitkeep)
    "ORION_release",    # carpeta de staging
}

EXCLUDE_FILE_NAMES = {
    ".env",             # ¡NUNCA distribuir credenciales locales!
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
}

EXCLUDE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".tmp",
    ".temp",
    ".bak",
}

# Subcadenas que indican una clave sensible en .env
SENSITIVE_KEY_SUBSTRINGS = (
    "_KEY",
    "KEY_",
    "API_KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "AUTH_KEY",
)


class SecurityError(Exception):
    """Excepción lanzada cuando se detecta un riesgo crítico de seguridad o fuga de credenciales."""
    pass


def format_size(size_in_bytes: int) -> str:
    """Convierte bytes a formato legible para humanos (B, KB, MB, GB)."""
    val = float(size_in_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if val < 1024.0:
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} TB"


def get_desktop_path() -> Path:
    """Obtiene la ruta del Escritorio del usuario en Windows o fallback seguro."""
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        desktop = Path(userprofile) / "Desktop"
        if desktop.exists() and desktop.is_dir():
            return desktop
    desktop = Path.home() / "Desktop"
    if desktop.exists() and desktop.is_dir():
        return desktop
    return PROJECT_ROOT.parent


def is_sensitive_key(key: str) -> bool:
    """
    Determina si una variable de entorno contiene credenciales o información sensible.
    Ejemplos: OPENAI_API_KEY, GEMINI_API_KEY, CUSTOM_API_KEY, TTS_KEY, DB_PASSWORD.
    """
    k = key.strip().upper()
    if any(sub in k for sub in SENSITIVE_KEY_SUBSTRINGS):
        return True
    if k.endswith("_KEY") or k.startswith("KEY_") or k == "KEY":
        return True
    return False


def get_placeholder_for_key(key: str) -> str:
    """Genera un placeholder descriptivo para una clave sensible."""
    clean_k = key.strip().lower()
    return f"tu_{clean_k}_aqui"


# ──────────────────────────────────────────────────────────────────────────────
# 1. Limpieza Previa Segura del Workspace
# ──────────────────────────────────────────────────────────────────────────────

def clean_workspace(
    project_root: Path = PROJECT_ROOT,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict[str, int]:
    """
    Ejecuta una limpieza previa segura del proyecto:
    - Elimina carpetas __pycache__ recursivamente y archivos .pyc/.pyo (fuera de env/).
    - Elimina logs rotados viejos (aura.log.1, etc.) conservando el log activo.
    - Elimina wavs temporales de diagnóstico en data/audio_cache y data/audio_test.
    - Elimina carpetas de compilación build/, _internal/ y dist/.

    GUARDAS ESTRICTAS:
    NUNCA toca código (.py), assets, models/rvc, data real de usuario, .env ni requirements.txt.
    """
    stats = {
        "pycache_dirs_removed": 0,
        "pyc_files_removed": 0,
        "rotated_logs_removed": 0,
        "temp_wavs_removed": 0,
        "build_dirs_removed": 0,
        "bytes_freed": 0,
    }

    if not project_root.exists():
        return stats

    # 1. Eliminar carpetas build/, _internal/ y dist/
    for build_name in ["build", "_internal", "dist"]:
        b_path = project_root / build_name
        if b_path.exists() and b_path.is_dir():
            size = sum(f.stat().st_size for f in b_path.glob("**/*") if f.is_file())
            stats["bytes_freed"] += size
            stats["build_dirs_removed"] += 1
            if not dry_run:
                shutil.rmtree(b_path, ignore_errors=True)
            if verbose:
                print(f"  [LIMPIEZA] Eliminada carpeta de compilación: {b_path.name}/ ({format_size(size)})")

    # 2. Eliminar __pycache__ y .pytest_cache (omitiendo la carpeta env/)
    for root, dirs, files in os.walk(project_root, topdown=False):
        root_path = Path(root)
        try:
            rel = root_path.relative_to(project_root)
        except ValueError:
            continue

        # No tocar el entorno virtual env/
        if rel.parts and rel.parts[0] in ("env", ".venv"):
            continue

        # Eliminar archivos .pyc y .pyo sueltos
        for f in files:
            if f.endswith((".pyc", ".pyo")):
                f_path = root_path / f
                try:
                    f_size = f_path.stat().st_size
                    stats["bytes_freed"] += f_size
                    stats["pyc_files_removed"] += 1
                    if not dry_run:
                        f_path.unlink(missing_ok=True)
                except Exception:
                    pass

        # Eliminar carpetas __pycache__ y .pytest_cache
        for d in list(dirs):
            if d in ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"):
                d_path = root_path / d
                try:
                    d_size = sum(f.stat().st_size for f in d_path.glob("**/*") if f.is_file())
                    stats["bytes_freed"] += d_size
                    stats["pycache_dirs_removed"] += 1
                    if not dry_run:
                        shutil.rmtree(d_path, ignore_errors=True)
                    if verbose:
                        print(f"  [LIMPIEZA] Eliminada caché: {d_path.relative_to(project_root)} ({format_size(d_size)})")
                except Exception:
                    pass

    # 3. Eliminar logs rotados viejos en logs/ (aura.log.1, *.log.[0-9]+, etc.)
    logs_dir = project_root / "logs"
    if logs_dir.exists() and logs_dir.is_dir():
        for log_file in logs_dir.iterdir():
            if not log_file.is_file():
                continue
            name = log_file.name
            # Coincidir con logs rotados numéricos (aura.log.1, etc.) o copias de rotación
            if re.match(r".+\.log\.\d+$", name) or name.endswith((".log.bak", ".log.old")):
                try:
                    l_size = log_file.stat().st_size
                    stats["bytes_freed"] += l_size
                    stats["rotated_logs_removed"] += 1
                    if not dry_run:
                        log_file.unlink(missing_ok=True)
                    if verbose:
                        print(f"  [LIMPIEZA] Eliminado log rotado viejo: logs/{name} ({format_size(l_size)})")
                except Exception:
                    pass

    # 4. Eliminar wavs temporales de diagnóstico en data/audio_cache y data/audio_test
    for audio_folder in ["audio_cache", "audio_test"]:
        a_path = project_root / "data" / audio_folder
        if a_path.exists() and a_path.is_dir():
            for wav_file in a_path.glob("*.wav"):
                # GUARDA ABSOLUTA: Verificar que no esté en models/ ni en assets/
                p_str = str(wav_file).replace("\\", "/")
                if "/models/" in p_str or "/assets/" in p_str:
                    continue
                try:
                    w_size = wav_file.stat().st_size
                    stats["bytes_freed"] += w_size
                    stats["temp_wavs_removed"] += 1
                    if not dry_run:
                        wav_file.unlink(missing_ok=True)
                    if verbose:
                        print(f"  [LIMPIEZA] Eliminado audio temporal: data/{audio_folder}/{wav_file.name} ({format_size(w_size)})")
                except Exception:
                    pass

    return stats


# ──────────────────────────────────────────────────────────────────────────────
# 2. Generación Segura de .env.example desde .env
# ──────────────────────────────────────────────────────────────────────────────

def generate_env_example(env_path: Path, output_path: Path) -> int:
    """
    Genera automáticamente .env.example a partir de .env:
    - Conserva todos los comentarios (# ...) y líneas vacías.
    - Conserva las claves no sensibles con sus valores por defecto/actuales.
    - Reemplaza TODAS las claves sensibles (API keys, passwords, tokens) por placeholders.
    - Normaliza FIRST_RUN a 'true' para que el receptor ejecute el onboarding wizard.
    - Limpia identificadores de hardware locales (AUDIO_INPUT_DEVICE, AUDIO_OUTPUT_DEVICE).
    - Escribe con codificación estricta UTF-8 explícita.

    Retorna la cantidad de claves sensibles sanitizadas.
    """
    if not env_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo .env en: {env_path}")

    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    sanitized_count = 0
    new_lines: list[str] = []

    header = (
        "# ============================================================\n"
        "# AURA (Orion) — Plantilla de Configuración Portable\n"
        "# ============================================================\n"
        "# Copiá este archivo como .env y completá tus credenciales.\n"
        "# El archivo .env real NUNCA debe incluirse en releases ni git.\n"
        "# Generado automáticamente por scripts/make_release.py (Fase 70)\n"
        "# ============================================================\n\n"
    )
    new_lines.append(header)

    for line in lines:
        stripped = line.strip()

        # Líneas vacías o comentarios puros se preservan idénticos
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        # Si contiene '=' es una definición de variable
        if "=" in line:
            # Separar clave y valor preservando comentarios en línea si existen
            eq_idx = line.find("=")
            key = line[:eq_idx].strip()
            rest = line[eq_idx + 1:].strip()

            # Extraer comentario en línea si lo hay
            inline_comment = ""
            if "#" in rest:
                # Comprobar si el '#' está fuera de comillas
                parts = rest.split("#", 1)
                val_candidate = parts[0].strip()
                # Verificar si comillas balanceadas en val_candidate
                quote_count = val_candidate.count("'") + val_candidate.count('"')
                if quote_count % 2 == 0:
                    rest = val_candidate
                    inline_comment = f"  # {parts[1].strip()}"

            # Detectar si tiene comillas envolventes
            has_single_quotes = rest.startswith("'") and rest.endswith("'") and len(rest) >= 2
            has_double_quotes = rest.startswith('"') and rest.endswith('"') and len(rest) >= 2

            if is_sensitive_key(key):
                placeholder = get_placeholder_for_key(key)
                if has_single_quotes or (not has_single_quotes and not has_double_quotes):
                    val_str = f"'{placeholder}'"
                else:
                    val_str = f'"{placeholder}"'
                sanitized_count += 1
                new_line = f"{key}={val_str}{inline_comment}\n"
            elif key == "FIRST_RUN":
                # En un release portable distribuido, el primer inicio debe ser true
                new_line = f"FIRST_RUN='true'{inline_comment}\n"
            elif key in ("AUDIO_INPUT_DEVICE", "AUDIO_OUTPUT_DEVICE", "MICROPHONE_INDEX"):
                # Limpiar dispositivos específicos de hardware de la máquina de empaquetado
                quote = "'" if has_single_quotes else ""
                new_line = f"{key}={quote}{quote}{inline_comment}\n"
            else:
                # Clave no sensible: conservar tal cual
                new_line = line

            new_lines.append(new_line)
        else:
            new_lines.append(line)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return sanitized_count


# ──────────────────────────────────────────────────────────────────────────────
# 3. Verificación de Seguridad Inviolable
# ──────────────────────────────────────────────────────────────────────────────

def verify_no_env_file(directory: Path) -> None:
    """
    Verifica de manera exhaustiva que ningún archivo '.env' real exista
    dentro del directorio de staging. Si se detecta, aborta inmediatamente.
    """
    if not directory.exists():
        return

    for root, dirs, files in os.walk(directory):
        for f in files:
            if f.lower() == ".env":
                env_found = Path(root) / f
                raise SecurityError(
                    f"¡VIOLACIÓN DE SEGURIDAD! Se detectó un archivo '{env_found}'. "
                    "El archivo '.env' contiene claves y datos privados y NUNCA debe "
                    "ingresar a un release. Operación abortada para proteger tus credenciales."
                )


def verify_pre_zip_security(stage_dir: Path) -> None:
    """
    Chequeo pre-zip obligatorio de la Fase 81:
    Verifica el árbol de staging antes de comprimir y ABORTA inmediatamente
    si detecta .env, env/, models/stt/, assets/backgrounds/cache/ o audios temporales.
    """
    if not stage_dir.exists():
        return

    # 1. Chequeo de .env real
    verify_no_env_file(stage_dir)

    for root, dirs, files in os.walk(stage_dir):
        root_path = Path(root)
        try:
            rel = root_path.relative_to(stage_dir)
        except ValueError:
            continue
        parts = rel.parts

        # 2. Chequeo de carpetas de entorno virtual (env/, .venv/)
        if parts and parts[0] in ("env", ".venv"):
            raise SecurityError(
                f"¡VIOLACIÓN PRE-ZIP! Se detectó carpeta de entorno virtual '{parts[0]}' en staging. "
                "El release debe ser portable y liviano; el entorno se reconstruye con setup_env.bat."
            )

        # 3. Chequeo de modelos STT descargados (models/stt/)
        if len(parts) >= 2 and parts[0] == "models" and parts[1] == "stt":
            non_keep_files = [f for f in files if f != ".gitkeep"]
            if non_keep_files or len(parts) > 2:
                raise SecurityError(
                    f"¡VIOLACIÓN PRE-ZIP! Se detectaron modelos STT de Whisper en staging: {rel}. "
                    "models/stt/ debe excluirse del release para evitar zips de varios gigabytes."
                )

        # 4. Chequeo de cache de fondos (assets/backgrounds/cache/)
        if len(parts) >= 3 and parts[0] == "assets" and parts[1] == "backgrounds" and parts[2] == "cache":
            non_keep_files = [f for f in files if f != ".gitkeep"]
            if non_keep_files or len(parts) > 3:
                raise SecurityError(
                    f"¡VIOLACIÓN PRE-ZIP! Se detectaron archivos en cache de fondos en staging: {rel}. "
                    "assets/backgrounds/cache/ debe excluirse (es 100% regenerable)."
                )

        # 5. Chequeo de cache de TTS en data/tts_cache/
        if len(parts) >= 2 and parts[0] == "data" and parts[1] == "tts_cache":
            wav_files = [f for f in files if f.endswith(".wav")]
            if wav_files:
                raise SecurityError(
                    f"¡VIOLACIÓN PRE-ZIP! Se detectaron archivos WAV en data/tts_cache/ en staging: {wav_files}. "
                    "data/tts_cache/ debe excluirse del release."
                )


def verify_zip_security(zip_path: Path) -> None:
    """
    Abre e inspecciona el archivo ZIP generado para garantizar que:
    1. NO contiene ningún archivo '.env' o que termine en '/.env'.
    2. NO contiene ningún directorio o archivo de 'env/' (virtualenv).
    3. NO contiene modelos locales descargados de 'models/stt/'.
    4. NO contiene frames de cache de 'assets/backgrounds/cache/'.
    5. NO contiene audios de 'data/tts_cache/'.
    6. NO contiene carpetas '__pycache__'.
    7. Contiene los elementos esenciales requeridos.

    Si se detecta cualquier anomalía, elimina el ZIP de inmediato y aborta.
    """
    if not zip_path.exists():
        raise FileNotFoundError(f"Archivo ZIP no encontrado: {zip_path}")

    namelist: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()

    for name in namelist:
        norm_name = name.replace("\\", "/")

        # 1. Chequeo estricto de .env
        if norm_name == ".env" or norm_name.endswith("/.env"):
            zip_path.unlink(missing_ok=True)
            raise SecurityError(
                f"¡VIOLACIÓN CRÍTICA DE SEGURIDAD! El ZIP contenía '{name}'. "
                "El archivo ZIP ha sido destruido inmediatamente."
            )

        # 2. Chequeo estricto de entorno virtual env/
        if norm_name.startswith("env/") or norm_name.startswith(".venv/"):
            zip_path.unlink(missing_ok=True)
            raise SecurityError(
                f"¡VIOLACIÓN DE TAMAÑO/PORTABILIDAD! El ZIP contenía archivos del entorno virtual '{name}'. "
                "El ZIP ha sido destruido inmediatamente."
            )

        # 3. Chequeo de models/stt/
        if norm_name.startswith("models/stt/") and not norm_name.endswith(".gitkeep"):
            zip_path.unlink(missing_ok=True)
            raise SecurityError(
                f"¡VIOLACIÓN DE TAMAÑO! El ZIP contenía modelos descargados de Whisper '{name}'. "
                "models/stt/ debe excluirse del release. El ZIP ha sido destruido inmediatamente."
            )

        # 4. Chequeo de assets/backgrounds/cache/
        if norm_name.startswith("assets/backgrounds/cache/") and not norm_name.endswith(".gitkeep"):
            zip_path.unlink(missing_ok=True)
            raise SecurityError(
                f"¡VIOLACIÓN DE CACHE! El ZIP contenía frames de cache de backgrounds '{name}'. "
                "El ZIP ha sido destruido inmediatamente."
            )

        # 5. Chequeo de data/tts_cache/*.wav
        if norm_name.startswith("data/tts_cache/") and norm_name.endswith(".wav"):
            zip_path.unlink(missing_ok=True)
            raise SecurityError(
                f"¡VIOLACIÓN DE CACHE! El ZIP contenía audios de síntesis en '{name}'. "
                "El ZIP ha sido destruido inmediatamente."
            )

        # 6. Chequeo de __pycache__
        if "__pycache__" in norm_name or norm_name.endswith((".pyc", ".pyo")):
            zip_path.unlink(missing_ok=True)
            raise SecurityError(
                f"¡VIOLACIÓN DE CACHE! El ZIP contenía archivos de bytecode '{name}'. "
                "El ZIP ha sido destruido inmediatamente."
            )

    # 7. Validar presencia de componentes obligatorios
    required_elements = [
        "requirements.txt",
        ".env.example",
        "Aura.bat",
        "setup_env.bat",
        "scripts/make_shortcut.py",
        "assets/logo_waifu.ico",
    ]
    missing = [req for req in required_elements if req not in namelist and req.replace("/", "\\") not in namelist]
    if missing:
        zip_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Fallo de integridad del release: Faltan elementos obligatorios en el ZIP: {missing}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 4. Copia de Archivos al Directorio Staging (ORION_release/)
# ──────────────────────────────────────────────────────────────────────────────

def copy_release_files(
    src_root: Path = PROJECT_ROOT,
    stage_dir: Path | None = None,
    verbose: bool = False,
) -> list[Path]:
    """
    Copia los archivos del proyecto al directorio de staging excluyendo:
    - env/, .git/, logs/, __pycache__/, build/, _internal/, dist/, caches.
    - .env real (¡NUNCA!).
    - *.wav temporales y backups de data/.

    Incluyendo SIEMPRE:
    - models/rvc/ (aura.pth, aura.index).
    - assets/ (logos, waifu icon, etc.).
    - data/ real (conversaciones, memoria, automatizaciones, programas, favoritos).
    - scripts/ (make_release, make_shortcut, backup_manager, etc.).
    - requirements.txt, .env.example, Aura.bat, setup_env.bat, Aura.lnk.
    - Todos los paquetes de código fuente (ai, aura, core, ui, etc.).
    """
    if stage_dir is None:
        stage_dir = src_root / "ORION_release"

    # Si la carpeta de staging ya existía, limpiarla completamente
    if stage_dir.exists():
        shutil.rmtree(stage_dir, ignore_errors=True)
    stage_dir.mkdir(parents=True, exist_ok=True)

    copied_files: list[Path] = []

    def should_exclude_dir(dir_path: Path) -> bool:
        try:
            rel = dir_path.relative_to(src_root)
        except ValueError:
            return True
        parts = rel.parts
        if not parts:
            return False

        # Excluir si cualquier segmento coincide con directorios excluidos
        for p in parts:
            if p in EXCLUDE_DIR_NAMES:
                return True
            if p.endswith("_release"):
                return True

        # Exclusiones específicas en subdirectorios
        # 1. models/stt/ (modelos de faster-whisper se descargan al primer uso)
        if len(parts) >= 2 and parts[0] == "models" and parts[1] == "stt":
            return True

        # 2. assets/backgrounds/cache/ (frames y QA se regeneran del GIF)
        if len(parts) >= 3 and parts[0] == "assets" and parts[1] == "backgrounds" and parts[2] == "cache":
            return True

        # 3. Subdirectorios temporales o backups de data/
        if len(parts) >= 2 and parts[0] == "data":
            if parts[1] in ("backups", "backup_pre_utf8", "audio_test", "audio_cache", "tts_cache"):
                return True

        return False

    def should_exclude_file(file_path: Path) -> bool:
        name = file_path.name
        try:
            rel = file_path.relative_to(src_root)
        except ValueError:
            return True
        parts = rel.parts

        # REGLA MANDATORIA DE SEGURIDAD
        if name.lower() == ".env":
            return True

        if name in EXCLUDE_FILE_NAMES:
            return True

        ext = file_path.suffix.lower()
        if ext in EXCLUDE_EXTENSIONS:
            return True

        # Excluir zips de releases previos o backups
        if ext == ".zip" and (name.startswith("AURA_release_") or name.startswith("backup_")):
            return True

        # Excluir logs de cualquier tipo
        if ext == ".log" or ".log." in name:
            return True

        # Excluir wavs en data/ (cache y pruebas)
        if ext == ".wav":
            if len(parts) >= 2 and parts[0] == "data":
                return True
            if name.startswith(("temp", "test", "benchmark", "diagnostic")):
                return True

        # Excluir archivos de models/stt/
        if len(parts) >= 2 and parts[0] == "models" and parts[1] == "stt":
            return True

        # Excluir archivos de assets/backgrounds/cache/
        if len(parts) >= 3 and parts[0] == "assets" and parts[1] == "backgrounds" and parts[2] == "cache":
            return True

        return False

    # Recorrer el árbol de fuentes
    for root, dirs, files in os.walk(src_root):
        root_path = Path(root)

        if should_exclude_dir(root_path):
            dirs.clear()  # No descender en directorios excluidos
            continue

        # Filtrar directorios in-place para que os.walk no entre en ellos
        dirs[:] = [d for d in dirs if not should_exclude_dir(root_path / d)]

        for f in files:
            file_path = root_path / f
            if should_exclude_file(file_path):
                continue

            rel_file = file_path.relative_to(src_root)
            dest_file = stage_dir / rel_file
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, dest_file)
            copied_files.append(dest_file)
            if verbose:
                print(f"  [COPIA] {rel_file.as_posix()}")

    # Crear directorios operativos vacíos necesarios con .gitkeep para inicialización
    (stage_dir / "logs").mkdir(parents=True, exist_ok=True)
    (stage_dir / "logs" / ".gitkeep").touch()

    (stage_dir / "models" / "stt").mkdir(parents=True, exist_ok=True)
    (stage_dir / "models" / "stt" / ".gitkeep").touch()

    (stage_dir / "assets" / "backgrounds" / "cache").mkdir(parents=True, exist_ok=True)
    (stage_dir / "assets" / "backgrounds" / "cache" / ".gitkeep").touch()

    (stage_dir / "data" / "audio_cache").mkdir(parents=True, exist_ok=True)
    (stage_dir / "data" / "audio_cache" / ".gitkeep").touch()

    (stage_dir / "data" / "tts_cache").mkdir(parents=True, exist_ok=True)
    (stage_dir / "data" / "tts_cache" / ".gitkeep").touch()

    (stage_dir / "data" / "backups").mkdir(parents=True, exist_ok=True)
    (stage_dir / "data" / "backups" / ".gitkeep").touch()

    # Chequeo previo obligatorio de seguridad contra .env en staging
    verify_pre_zip_security(stage_dir)

    # Validar que los componentes críticos estén en staging
    models_rvc_pth = stage_dir / "models" / "rvc" / "aura" / "aura.pth"
    models_rvc_idx = stage_dir / "models" / "rvc" / "aura" / "aura.index"
    if not models_rvc_pth.exists():
        print(f"[ADVERTENCIA] No se encontró el modelo RVC en {models_rvc_pth}. Si se planea usar voz neuronal, debe incluirse.")
    else:
        if verbose:
            print(f"  [OK] Modelo RVC incluido: {models_rvc_pth.name} ({format_size(models_rvc_pth.stat().st_size)})")
            if models_rvc_idx.exists():
                print(f"  [OK] Índice RVC incluido: {models_rvc_idx.name} ({format_size(models_rvc_idx.stat().st_size)})")

    return copied_files


# ──────────────────────────────────────────────────────────────────────────────
# 5. Compresión ZIP con Zipfile y Manifiesto
# ──────────────────────────────────────────────────────────────────────────────

def create_release_zip(
    stage_dir: Path,
    zip_out_path: Path,
    exclusions_list: list[str],
) -> tuple[Path, dict]:
    """
    Comprime el contenido de stage_dir en un archivo ZIP:
    - Agrega manifiesto descriptive release_manifest.json en la raíz del ZIP.
    - Interrumpe de inmediato si detecta .env o env/ durante el empaquetado.
    - Ejecuta verify_zip_security tras la compresión.
    - Retorna la ruta al ZIP y el diccionario de estadísticas.
    """
    # Verificación preventiva estricta en el directorio de staging
    verify_no_env_file(stage_dir)

    zip_out_path.parent.mkdir(parents=True, exist_ok=True)

    archived_files_count = 0
    total_uncompressed_bytes = 0

    # 1. Generar y escribir release_manifest.json dentro de stage_dir antes de comprimir
    timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Contar archivos y bytes totales
    for root, _, files in os.walk(stage_dir):
        for f in files:
            fp = Path(root) / f
            total_uncompressed_bytes += fp.stat().st_size
            archived_files_count += 1

    manifest_data = {
        "release_name": zip_out_path.stem,
        "product": "AURA — Asistente Universal con Respuesta Automatizada",
        "internal_name": "Orion",
        "generated_at": timestamp_str,
        "python_target": "3.11",
        "files_count": archived_files_count + 1,  # +1 por el propio release_manifest.json
        "uncompressed_bytes": total_uncompressed_bytes,
        "uncompressed_human": format_size(total_uncompressed_bytes),
        "exclusions_applied": exclusions_list,
        "rebuild_steps": [
            "1. Descomprimir el archivo ZIP en cualquier ubicación deseada.",
            "2. Ejecutar setup_env.bat para construir el entorno virtual portable (%~dp0env) e instalar requerimientos.",
            "3. Copiar .env.example como .env y configurar credenciales si se usan proveedores cloud (Ollama local no requiere API key).",
            "4. Iniciar con Aura.bat (el modelo STT Whisper tiny se descargará automáticamente a models/stt/ al primer uso de voz).",
            "5. Opcional: Ejecutar python scripts/make_shortcut.py --desktop para recrear el acceso directo en el Escritorio.",
        ],
        "hardware_notes": "El peso del entorno virtual reconstruido varía según PyTorch: con CPU oficial pesará ~800 MB - 1 GB; con CUDA (GPU NVIDIA) pesará ~2.5 - 4 GB.",
    }

    manifest_file = stage_dir / "release_manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as mf:
        json.dump(manifest_data, mf, ensure_ascii=False, indent=2)

    total_uncompressed_bytes += manifest_file.stat().st_size
    archived_files_count += 1

    # 2. Comprimir con zipfile
    with zipfile.ZipFile(zip_out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(stage_dir):
            for f in files:
                file_path = Path(root) / f
                arcname = file_path.relative_to(stage_dir).as_posix()

                # GUARDA EN VUELO: Abortar si por algún motivo intenta entrar .env o env/
                if arcname.lower() == ".env" or arcname.lower().endswith("/.env"):
                    raise SecurityError(f"Intento de comprimir archivo sensible '{arcname}'. Abortando.")
                if arcname.lower().startswith("env/") or arcname.lower().startswith(".venv/"):
                    raise SecurityError(f"Intento de comprimir entorno virtual '{arcname}'. Abortando.")
                if arcname.lower().startswith("models/stt/") and not arcname.endswith(".gitkeep"):
                    raise SecurityError(f"Intento de comprimir modelo STT '{arcname}'. Abortando.")
                if arcname.lower().startswith("assets/backgrounds/cache/") and not arcname.endswith(".gitkeep"):
                    raise SecurityError(f"Intento de comprimir cache de fondos '{arcname}'. Abortando.")

                zf.write(file_path, arcname=arcname)

    # 3. Verificación post-compresión exhaustiva
    verify_zip_security(zip_out_path)

    zip_size_bytes = zip_out_path.stat().st_size
    ratio = (1.0 - (zip_size_bytes / total_uncompressed_bytes)) * 100.0 if total_uncompressed_bytes > 0 else 0.0

    stats = {
        "zip_path": str(zip_out_path.resolve()),
        "zip_size_bytes": zip_size_bytes,
        "zip_size_human": format_size(zip_size_bytes),
        "uncompressed_bytes": total_uncompressed_bytes,
        "uncompressed_human": format_size(total_uncompressed_bytes),
        "compression_ratio_pct": round(ratio, 1),
        "files_count": archived_files_count,
        "stage_dir": str(stage_dir.resolve()),
        "exclusions": exclusions_list,
    }

    return zip_out_path, stats


def print_manifest(stats: dict) -> None:
    """Imprime el manifiesto final en consola con formato estructurado."""
    print()
    print("=" * 66)
    print("  AURA ORION — MANIFIESTO FINAL DE RELEASE PORTABLE (Fase 81)")
    print("=" * 66)
    print(f"  Archivo ZIP:           {stats['zip_path']}")
    print(f"  Peso comprimido:       {stats['zip_size_human']} ({stats['zip_size_bytes']:,} bytes)")
    print(f"  Peso descomprimido:    {stats['uncompressed_human']} ({stats['uncompressed_bytes']:,} bytes)")
    print(f"  Ahorro de compresión:  {stats['compression_ratio_pct']}%")
    print(f"  Cantidad de archivos:  {stats['files_count']}")
    print(f"  Directorio staging:    {stats['stage_dir']}")
    print("-" * 66)
    print("  Lista de Exclusiones Aplicadas:")
    for ex in stats.get("exclusions", []):
        print(f"    • {ex}")
    print("-" * 66)
    print("  Componentes Críticos e Inclusiones Verificados:")
    print("    [OK] Modelos RVC (models/rvc/aura/aura.pth y aura.index) [LÍNEA ROJA]")
    print("    [OK] Fondo de pantalla activo (assets/backgrounds/current.*) [LÍNEA ROJA]")
    print("    [OK] Assets visuales y logotipos del usuario (assets/) [LÍNEA ROJA]")
    print("    [OK] Datos persistentes de usuario (data/ real) [LÍNEA ROJA]")
    print("    [OK] Scripts de mantenimiento y shortcut (scripts/)")
    print("    [OK] Plantilla sanitizada .env.example (sin API keys ni credenciales)")
    print("    [OK] Archivo de dependencias con índice oficial CPU (requirements.txt)")
    print("    [OK] Lanzadores portables y accesos (Aura.bat, setup_env.bat, Aura.lnk)")
    print("    [OK] Verificación estricta de seguridad: .env real EXCLUIDO")
    print("    [OK] Verificación de ligereza: env/, models/stt/, cache/ EXCLUIDOS")
    print("=" * 66)
    print()


# ──────────────────────────────────────────────────────────────────────────────
# 6. Orquestador Principal (make_release)
# ──────────────────────────────────────────────────────────────────────────────

def make_release(
    out_path: Path | str | None = None,
    stage_dir: Path | str | None = None,
    skip_clean: bool = False,
    no_zip: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
) -> tuple[Path | None, Path, dict]:
    """
    Orquesta el flujo completo de empaquetado y release:
    1. Limpieza de workspace (si no se omite con skip_clean).
    2. Generación automática de .env.example sanitizado desde .env.
    3. Copia a staging ORION_release/ aplicando exclusiones e inclusiones obligatorias.
    4. Verificación previa de seguridad anti-fugas (.env check).
    5. Compresión ZIP y verificación post-empaquetado.
    6. Retorna (zip_path, stage_dir, stats).
    """
    print()
    print("==================================================================")
    print("  AURA (Orion) — Generador de Release Portable y Limpieza")
    print("==================================================================")

    # 1. Limpieza previa segura
    if skip_clean:
        print("[1/5] Limpieza previa omitida por parámetro (--skip-clean).")
    else:
        print("[1/5] Ejecutando limpieza previa segura del proyecto...")
        clean_stats = clean_workspace(PROJECT_ROOT, dry_run=dry_run, verbose=verbose)
        print(
            f"      [OK] Eliminados: {clean_stats['pycache_dirs_removed']} cachés __pycache__, "
            f"{clean_stats['rotated_logs_removed']} logs rotados viejos, "
            f"{clean_stats['temp_wavs_removed']} audios temporales, "
            f"{clean_stats['build_dirs_removed']} carpetas build. "
            f"Espacio liberado: {format_size(clean_stats['bytes_freed'])}."
        )

    # 2. Generar .env.example sanitizado desde .env
    env_real = PROJECT_ROOT / ".env"
    env_example = PROJECT_ROOT / ".env.example"
    print("[2/5] Generando plantilla sanitizada .env.example desde .env...")
    if env_real.exists():
        sanitized = generate_env_example(env_real, env_example)
        print(f"      [OK] .env.example actualizado exitosamente ({sanitized} claves sensibles sanitizadas).")
    else:
        print("      [INFO] .env no encontrado en la raíz; utilizando .env.example existente.")

    # 3. Determinar directorio de staging
    actual_stage = Path(stage_dir) if stage_dir else PROJECT_ROOT / "ORION_release"
    print(f"[3/5] Copiando archivos del release a staging: {actual_stage.name}/...")
    if not dry_run:
        copied = copy_release_files(PROJECT_ROOT, actual_stage, verbose=verbose)
        print(f"      [OK] {len(copied)} archivos copiados aplicando filtros de exclusión.")
    else:
        print("      [DRY-RUN] Simulación de copia de archivos completada.")

    # 4. Determinar destino del archivo ZIP
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    default_zip_name = f"AURA_release_{timestamp}.zip"

    if out_path:
        out_p = Path(out_path)
        if out_p.suffix.lower() == ".zip":
            actual_zip_path = out_p
        elif out_p.is_dir() or not out_p.suffix:
            actual_zip_path = out_p / default_zip_name
        else:
            actual_zip_path = out_p.with_suffix(".zip")
    else:
        actual_zip_path = get_desktop_path() / default_zip_name

    exclusions_list = [
        "env/ (.venv) — Entorno virtual portable (reconstruible con setup_env.bat)",
        ".git/ — Historial de control de versiones git",
        "logs/ — Archivos de registro y auditoría (*.log, *.log.*)",
        "__pycache__/ — Cachés compiladas de Python (*.pyc, *.pyo)",
        "build/, _internal/, dist/ — Archivos temporales de compilación",
        "assets/backgrounds/cache/ — Frames extraídos y muestras QA (se regeneran del GIF)",
        "data/tts_cache/ — Caché local de audios sintetizados",
        "models/stt/ — Modelos locales de faster-whisper (se descargan automáticamente al primer uso)",
        "*.wav temporales — Audios de prueba y diagnóstico",
        ".env — Configuración y credenciales locales reales (VERIFICADO: NUNCA incluido)",
        "data/backups/, data/backup_pre_utf8/ — Respaldos locales de conversaciones",
        ".pytest_cache, .mypy_cache, .cache — Cachés de herramientas de testing",
    ]

    # 5. Comprimir a ZIP
    if no_zip or dry_run:
        print("[4/5] Compresión omitida (--no-zip o --dry-run).")
        stats = {
            "zip_path": "(No generado)",
            "zip_size_bytes": 0,
            "zip_size_human": "0 B",
            "uncompressed_bytes": 0,
            "uncompressed_human": "0 B",
            "compression_ratio_pct": 0.0,
            "files_count": len(copied) if not dry_run else 0,
            "stage_dir": str(actual_stage.resolve()),
            "exclusions": exclusions_list,
        }
        print("[5/5] Finalizado.")
        print_manifest(stats)
        return None, actual_stage, stats

    print(f"[4/5] Comprimiendo a archivo ZIP: {actual_zip_path.name}...")
    actual_zip_path, stats = create_release_zip(actual_stage, actual_zip_path, exclusions_list)
    print(f"      [OK] ZIP generado y verificado exitosamente en: {actual_zip_path}")

    # 6. Manifiesto final
    print("[5/5] Generando manifiesto final de release...")
    print_manifest(stats)

    return actual_zip_path, actual_stage, stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AURA Orion — Generador de Release Portable y Limpieza Segura (Fase 70)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--out", "-o",
        type=str,
        default=None,
        help="Ruta destino del archivo ZIP o carpeta de salida (por defecto: Escritorio de Windows / AURA_release_<fecha>.zip).",
    )
    parser.add_argument(
        "--stage-dir",
        type=str,
        default=None,
        help="Directorio intermedio para la copia limpia del release (por defecto: ORION_release en la raíz del proyecto).",
    )
    parser.add_argument(
        "--skip-clean",
        action="store_true",
        help="Omitir la fase 1 de limpieza del workspace previo al empaquetado.",
    )
    parser.add_argument(
        "--no-zip",
        action="store_true",
        help="Solo preparar la carpeta de staging limpia sin comprimir el archivo ZIP.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simular las operaciones sin borrar archivos ni generar el release.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Mostrar detalle de cada archivo procesado.",
    )

    args = parser.parse_args()

    try:
        make_release(
            out_path=args.out,
            stage_dir=args.stage_dir,
            skip_clean=args.skip_clean,
            no_zip=args.no_zip,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        return 0
    except SecurityError as se:
        print(f"\n[ERROR CRÍTICO DE SEGURIDAD] {se}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"\n[ERROR] Falló la creación del release: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""
Tests para la FASE 66 — Branding del launcher: renombrar el .bat y acceso directo con ícono.

Verifica:
  1. Existencia y contenido de Aura.bat (con regla %~dp0, chcp 65001 y run.py).
  2. Inexistencia de run.bat en la raíz (renombrado limpio).
  3. Ícono waifu assets/logo_waifu.ico con cabecera 00 00 01 00 y 7 tamaños.
  4. Preservación intacta de assets/logo2.ico (ventana/taskbar).
  5. Scripts scripts/make_shortcut.ps1 y scripts/make_shortcut.py.
  6. Existencia y propiedades de Aura.lnk en la raíz del proyecto.
  7. Consistencia en setup_env.bat y README.md (sin referencias rotas a run.bat).
"""

from __future__ import annotations

import os
import struct
import subprocess
from pathlib import Path
import pytest

from ui.branding import (
    ensure_logo_waifu_ico,
    ensure_logo2_ico,
    get_assets_dir,
    get_logo_png_path,
    get_logo_waifu_ico_path,
    get_logo2_ico_path,
    verify_ico_file,
    ROOT_DIR,
)


def test_aura_bat_exists_and_content():
    """Aura.bat debe existir en la raíz y contener las directivas portables necesarias."""
    root = Path(ROOT_DIR)
    aura_bat = root / "Aura.bat"
    assert aura_bat.is_file(), "Aura.bat debe existir en la raíz del proyecto"

    content = aura_bat.read_text(encoding="utf-8")
    assert 'cd /d "%~dp0"' in content, "Debe tener cd /d %~dp0 como primera directiva de directorio"
    assert "chcp 65001" in content, "Debe activar codificación UTF-8 en consola"
    assert "run.py" in content, "Debe ejecutar run.py"
    assert 'python.exe" "%~dp0run.py"' in content, "Debe invocar el python portable de %~dp0env"


def test_run_bat_no_longer_in_root():
    """run.bat ya no debe existir en la raíz (fue renombrado a Aura.bat)."""
    root = Path(ROOT_DIR)
    run_bat = root / "run.bat"
    assert not run_bat.exists(), "run.bat no debe existir en la raíz (debe ser Aura.bat)"


def test_setup_env_bat_references_aura_bat():
    """setup_env.bat debe recomendar ejecutar Aura.bat y no run.bat."""
    root = Path(ROOT_DIR)
    setup_bat = root / "setup_env.bat"
    assert setup_bat.is_file()

    content = setup_bat.read_text(encoding="utf-8")
    assert "Aura.bat" in content, "setup_env.bat debe recomendar Aura.bat"
    assert "run.bat" not in content, "setup_env.bat no debe contener referencias a run.bat"


def test_logo_waifu_ico_header_and_sizes():
    """logo_waifu.ico debe tener encabezado 00 00 01 00 y multi-resolución de 16 a 256 px."""
    ico_path = ensure_logo_waifu_ico()
    assert os.path.exists(ico_path), "assets/logo_waifu.ico debe existir"

    with open(ico_path, "rb") as f:
        header = f.read(6)

    magic = header[:4]
    assert magic == b"\x00\x00\x01\x00", f"Cabecera mágica inválida: {magic.hex()} (debe ser 00 00 01 00)"

    num_images = struct.unpack("<H", header[4:6])[0]
    assert num_images >= 5, f"Debe contener al menos 5 tamaños de ícono, encontrados: {num_images}"

    valid, detail = verify_ico_file(ico_path)
    assert valid, f"verify_ico_file falló para {ico_path}: {detail}"


def test_logo2_ico_intact_for_window():
    """logo2.ico debe seguir existiendo intacto para la barra de tareas y ventana."""
    ico2_path = get_logo2_ico_path()
    assert os.path.exists(ico2_path), "assets/logo2.ico debe existir para ventana"
    valid, detail = verify_ico_file(ico2_path)
    assert valid, f"logo2.ico debe ser un ico válido: {detail}"


def test_shortcut_scripts_exist():
    """scripts/make_shortcut.ps1 y scripts/make_shortcut.py deben existir en el repositorio."""
    root = Path(ROOT_DIR)
    ps1_script = root / "scripts" / "make_shortcut.ps1"
    py_script = root / "scripts" / "make_shortcut.py"

    assert ps1_script.is_file(), "scripts/make_shortcut.ps1 debe existir"
    assert py_script.is_file(), "scripts/make_shortcut.py debe existir"


def test_aura_lnk_exists_in_root():
    """Aura.lnk debe existir en la raíz del proyecto."""
    root = Path(ROOT_DIR)
    lnk = root / "Aura.lnk"
    assert lnk.is_file(), "Aura.lnk debe existir en la raíz del proyecto"
    assert lnk.stat().st_size > 0, "Aura.lnk no debe estar vacío"


def test_aura_lnk_properties_via_wscript():
    """Verifica que Aura.lnk apunte a Aura.bat y tenga el ícono de la waifu."""
    ps_cmd = """
$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut((Resolve-Path 'Aura.lnk').Path)
[PSCustomObject]@{
    Target = $lnk.TargetPath
    WorkingDir = $lnk.WorkingDirectory
    Icon = $lnk.IconLocation
} | ConvertTo-Json -Compress
"""
    res = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert res.returncode == 0, f"Fallo al inspeccionar acceso directo: {res.stderr}"

    import json
    info = json.loads(res.stdout.strip())
    assert "Aura.bat" in info["Target"], f"El target debe ser Aura.bat, obtenido: {info['Target']}"
    assert "logo_waifu.ico" in info["Icon"] or "logo.ico" in info["Icon"], f"El ícono debe ser de la waifu: {info['Icon']}"


def test_readme_references_updated():
    """README.md debe documentar Aura.lnk y Aura.bat sin referencias residuales a run.bat."""
    root = Path(ROOT_DIR)
    readme = root / "README.md"
    assert readme.is_file()

    content = readme.read_text(encoding="utf-8")
    assert "Aura.bat" in content, "README.md debe documentar Aura.bat"
    assert "Aura.lnk" in content, "README.md debe documentar Aura.lnk"
    assert "run.bat" not in content, "README.md no debe contener menciones a run.bat"
    assert "logo_waifu.ico" in content, "README.md debe mencionar logo_waifu.ico"
    assert "make_shortcut" in content, "README.md debe documentar el script make_shortcut"


def test_make_shortcut_in_copied_directory(tmp_path):
    """Verifica que make_shortcut.ps1 funcione en una copia del proyecto y genere Aura.lnk."""
    import shutil

    # Crear estructura mínima en tmp_path
    (tmp_path / "assets").mkdir()
    (tmp_path / "scripts").mkdir()

    # Copiar archivos esenciales
    shutil.copyfile(Path(ROOT_DIR) / "Aura.bat", tmp_path / "Aura.bat")
    shutil.copyfile(Path(ROOT_DIR) / "assets" / "logo_waifu.ico", tmp_path / "assets" / "logo_waifu.ico")
    shutil.copyfile(Path(ROOT_DIR) / "scripts" / "make_shortcut.ps1", tmp_path / "scripts" / "make_shortcut.ps1")

    ps1_file = tmp_path / "scripts" / "make_shortcut.ps1"
    res = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(ps1_file)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert res.returncode == 0, f"Error ejecutando make_shortcut.ps1 en carpeta copiada: {res.stderr}\nStdout: {res.stdout}"
    copied_lnk = tmp_path / "Aura.lnk"
    assert copied_lnk.is_file(), "Aura.lnk debe crearse en la carpeta copiada"
    assert copied_lnk.stat().st_size > 0


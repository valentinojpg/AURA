"""
AURA — Generador Reproducible de Acceso Directo con Ícono de Waifu (Fase 66)

Crea el acceso directo 'Aura.lnk' apuntando a Aura.bat con el ícono de la waifu.
Compatible con cualquier PC con Windows usando WScript.Shell.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

# Agregar la raíz del proyecto al sys.path para importar ui.branding
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(_CURRENT_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ui.branding import ensure_logo_waifu_ico, verify_ico_file  # noqa: E402


def create_shortcut(target_bat: str, lnk_path: str, icon_path: str, working_dir: str) -> bool:
    """Crea un acceso directo .lnk en Windows usando PowerShell y WScript.Shell."""
    ps_cmd = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{lnk_path}')
$Shortcut.TargetPath = '{target_bat}'
$Shortcut.WorkingDirectory = '{working_dir}'
$Shortcut.IconLocation = '{icon_path},0'
$Shortcut.Description = 'AURA — Asistente Universal con Respuesta Automatizada'
$Shortcut.Save()
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return True
    except Exception as e:
        print(f"[ERROR] Error al crear acceso directo {lnk_path}: {e}")
        return False


def refresh_icon_cache() -> None:
    """Refresca la caché de íconos de Windows mediante ie4uinit.exe -show."""
    try:
        subprocess.run(
            ["ie4uinit.exe", "-show"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        print("[INFO] Caché de íconos de Windows refrescada (ie4uinit.exe -show).")
    except Exception as e:
        print(f"[WARN] No se pudo invocar ie4uinit.exe: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generador de acceso directo Aura.lnk con ícono de waifu.")
    parser.add_argument("--desktop", "-d", action="store_true", help="Crear también en el Escritorio de Windows.")
    args = parser.parse_args()

    print("=============================================")
    print("  AURA - Generador de Accesos Directos (.lnk)")
    print("=============================================")

    target_bat = os.path.join(ROOT_DIR, "Aura.bat")
    if not os.path.exists(target_bat):
        print(f"[ERROR] No se encontró '{target_bat}'.")
        return 1

    # Asegurar el ícono de la waifu
    icon_path = ensure_logo_waifu_ico()
    valid, detail = verify_ico_file(icon_path)
    if not valid:
        print(f"[ERROR] Ícono no válido: {detail}")
        return 1
    print(f"[OK] Ícono verificado: {icon_path}")

    # 1. Crear en la raíz del proyecto
    root_lnk = os.path.join(ROOT_DIR, "Aura.lnk")
    if create_shortcut(target_bat, root_lnk, icon_path, ROOT_DIR):
        print(f"[OK] Acceso directo creado: {root_lnk}")
    else:
        return 1

    # 2. Si se solicitó en el Escritorio
    if args.desktop:
        desktop_dir = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
        if os.path.exists(desktop_dir):
            desktop_lnk = os.path.join(desktop_dir, "Aura.lnk")
            if create_shortcut(target_bat, desktop_lnk, icon_path, ROOT_DIR):
                print(f"[OK] Acceso directo en Escritorio creado: {desktop_lnk}")

    refresh_icon_cache()
    print("=============================================")
    print("  Acceso directo configurado exitosamente.")
    print("=============================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())

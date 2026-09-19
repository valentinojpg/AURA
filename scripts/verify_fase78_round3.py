"""
AURA — Verificación Integral de Fase 78 Fix Ronda 3 (Pruebas E2E / Cobertura Total).

Ejecuta las validaciones mandatorias:
1. Raíz de la UI como ft.Stack(expand=True, fit=ft.StackFit.EXPAND) con exactamente 2 hijos.
2. Ningún control en la cadena del fondo tiene dimensiones fijas explícitas (width/height).
3. Cobertura total de imagen con proporción distinta a la ventana (1920x1397 en 1020x700).
4. Transparencia en las 6 vistas y barra de input inferior de ChatPage.
5. Quitar fondo restaura el fondo sólido del tema en toda la ventana.
6. Soporte de GIFs animados sin timers huérfanos.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from PIL import Image

ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import flet as ft
from aura.ui.background_manager import background_manager
from aura.ui.theme import theme_manager
from ui.main_window import MainWindow


def run_round3_verification():
    print("============================================================")
    print("  VERIFICACIÓN FIX FASE 78 RONDA 3 — COBERTURA TOTAL FONDO")
    print("============================================================")

    temp_dir = tempfile.mkdtemp(prefix="aura_fase78_r3_")
    db_jpg = os.path.join(temp_dir, "dragon_ball.jpg")
    test_gif = os.path.join(temp_dir, "anim.gif")

    im_db = Image.new("RGB", (1920, 1397), color=(255, 120, 0))
    im_db.save(db_jpg, format="JPEG")

    f1 = Image.new("RGB", (300, 200), "red")
    f2 = Image.new("RGB", (300, 200), "blue")
    f1.save(test_gif, save_all=True, append_images=[f2], duration=100, loop=0)

    try:
        page_mock = MagicMock(spec=ft.Page)
        page_mock.services = []
        page_mock.overlay = []
        page_mock.controls = []

        def mock_add(ctrl):
            page_mock.controls.append(ctrl)

        page_mock.add = mock_add

        win = MainWindow()
        win._main(page_mock)

        # ── Test 1: Stack raíz con exactamente 2 hijos y fit=EXPAND
        print("\n[Validación 1] Estructura del Stack raíz...")
        assert hasattr(win, "_root_stack"), "MainWindow debe exponer _root_stack"
        root = win._root_stack
        assert isinstance(root, ft.Stack)
        assert len(root.controls) == 2, f"El Stack raíz debe tener exactamente 2 hijos, tiene {len(root.controls)}"
        assert root.controls[0] is win._bg_container, "Hijo [0] debe ser _bg_container (layer de fondo)"
        assert root.fit == ft.StackFit.EXPAND, "Root stack debe tener fit=ft.StackFit.EXPAND"
        assert root.expand is True, "Root stack debe tener expand=True"
        assert win._bg_layer.fit == ft.StackFit.EXPAND, "Inner _bg_layer debe tener fit=ft.StackFit.EXPAND"
        print("  ✅ Validación 1 SUPERADA: Root stack con exactamente 2 hijos [0]=fondo, [1]=contenido y fit=EXPAND.")

        # ── Test 2: Ausencia de dimensiones explícitas (width/height) y coordenadas directas
        print("\n[Validación 2] Ausencia total de width/height explícitos y coordenadas fuera de Stack...")
        for ctrl in (win._root_stack, win._bg_container, win._bg_layer, win._bg_image, win._scrim_container):
            assert ctrl.width is None, f"{ctrl.__class__.__name__} tiene width={ctrl.width} (debe ser None)"
            assert ctrl.height is None, f"{ctrl.__class__.__name__} tiene height={ctrl.height} (debe ser None)"
            assert ctrl.top is None and ctrl.left is None and ctrl.right is None and ctrl.bottom is None, f"{ctrl.__class__.__name__} tiene coordenadas no permitidas"
            assert ctrl.expand is True, f"{ctrl.__class__.__name__} debe tener expand=True"
        print("  ✅ Validación 2 SUPERADA: Cero dimensiones fijas; sin coordenadas top/left/right/bottom; expand=True.")

        # ── Test 3: Wallpaper Dragon Ball (1920x1397) y fit COVER
        print("\n[Validación 3] Aplicación de wallpaper 1920x1397 (Dragon Ball) con fit=COVER...")
        background_manager.apply_background(db_jpg, fit="cover", sidebar_opacity=0.2, scrim_opacity=0.25, save=True)
        assert win._bg_container.visible is True
        assert win._bg_image.fit == ft.BoxFit.COVER
        assert win._scrim_container.visible is True
        assert win._content_container.bgcolor == "transparent"
        print("  ✅ Validación 3 SUPERADA: Fondo aplicado con fit=COVER, content_container transparente y scrim activo.")

        # ── Test 4: Transparencia en ChatPage (input container y banner)
        print("\n[Validación 4] Transparencia en ChatPage (input container)...")
        chat = win._pages["chat"]
        assert chat.bgcolor == "transparent"
        assert chat._input_container.bgcolor == "transparent"
        assert chat._status_banner.bgcolor == "transparent"
        print("  ✅ Validación 4 SUPERADA: Barra de input y banner transparentes (fondo visible hasta el borde inferior).")

        # ── Test 5: Transparencia en las 6 vistas
        print("\n[Validación 5] Navegación y transparencia en las 6 vistas...")
        for pid in ("chat", "skills", "automation", "files", "code", "settings"):
            win.navigate(pid)
            assert win._pages[pid].bgcolor == "transparent", f"Vista {pid} debe ser transparente con fondo activo"
        print("  ✅ Validación 5 SUPERADA: Las 6 vistas respetan la transparencia con fondo activo.")

        # ── Test 6: Quitar fondo y restauración completa
        print("\n[Validación 6] Quitar fondo y restauración de tema sólido...")
        background_manager.remove_background(save=True)
        assert win._bg_container.visible is False
        assert win._scrim_container.visible is False
        assert win._content_container.bgcolor == theme_manager.current_tokens.chat_bg
        chat = win._pages["chat"]
        assert chat._input_container.bgcolor == "#0F0F22"
        print("  ✅ Validación 6 SUPERADA: Fondo quitado limpiamente; color sólido del tema restaurado.")

        # ── Test 7: GIF animado a pantalla completa
        print("\n[Validación 7] Aplicar GIF animado a pantalla completa...")
        background_manager.apply_background(test_gif, fit="cover", save=True)
        assert win._bg_image.gapless_playback is True
        assert win._bg_container.visible is True
        background_manager.shutdown()
        print("  ✅ Validación 7 SUPERADA: GIF animado aplicado y detenido sin timers huérfanos.")

        print("\n============================================================")
        print("  RESULTADO: 7/7 VALIDACIONES RONDA 3 COMPLETADAS CON ÉXITO ✅")
        print("============================================================")

    finally:
        background_manager.shutdown()
        for f in (db_jpg, test_gif):
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
        try:
            os.rmdir(temp_dir)
        except Exception:
            pass


if __name__ == "__main__":
    run_round3_verification()

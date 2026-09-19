"""
AURA — Smoke Test de Integridad Estructural y Layout (Gate G2).

Instancia la aplicación en memoria (modo headless), monta el árbol de controles
de Flet y valida con validate_layout(root, strict=True) que se cumplan rigurosamente
las reglas R1 (posicionamiento absoluto) y R2 (Stack raíz con fondo y fit=EXPAND).

Salida esperada:
- Éxito: Imprime 'SMOKE TEST OK' y finaliza con código 0.
- Fallo: Imprime la cadena de ancestros y detalle de la violación y finaliza con código 1.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

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
from aura.ui.layout_rules import validate_layout, LayoutRuleViolationError
from aura.ui.background_manager import background_manager
from ui.main_window import MainWindow


def run_smoke_test() -> int:
    """Ejecuta la validación de arranque headless y chequeo de layout en modo estricto."""
    print("============================================================")
    print("  AURA ORION — SMOKE TEST DE INTEGRIDAD DE LAYOUT (GATE G2)")
    print("============================================================")

    # Configurar página headless mock
    page_mock = MagicMock(spec=ft.Page)
    page_mock.services = []
    page_mock.overlay = []
    page_mock.controls = []

    def mock_add(ctrl: ft.Control) -> None:
        page_mock.controls.append(ctrl)

    page_mock.add = mock_add

    try:
        print("[Smoke] Instanciando MainWindow y montando árbol de controles...")
        win = MainWindow()
        win._main(page_mock)

        if not hasattr(win, "_root_stack") or not win._root_stack:
            print("❌ ERROR: MainWindow no montó _root_stack.")
            return 1

        print("[Smoke] Ejecutando validate_layout(win._root_stack, page=page_mock, strict=True)...")
        violations = validate_layout(win._root_stack, page=page_mock, strict=True)

        if violations:
            print(f"❌ VIOLACIÓN DETECTADA ({len(violations)} problemas):")
            for v in violations:
                print(f"  - [{v.get('rule')}] {v.get('message')}")
            return 1

        # Validar también tras alternar navegación y páginas
        for pid in ("chat", "skills", "automation", "files", "code", "settings"):
            win.navigate(pid)
            validate_layout(win._root_stack, page=page_mock, strict=True)

        print("\n============================================================")
        print("  SMOKE TEST OK: Árbol de controles 100% libre de violaciones")
        print("  R1 (Stack directo / overlay) y R2 (Stack raíz expand) cumplidas")
        print("============================================================")
        return 0

    except LayoutRuleViolationError as lve:
        print(f"\n❌ VIOLACIÓN ESTRICTA DE LAYOUT:\n{lve}")
        return 1
    except Exception as ex:
        print(f"\n❌ ERROR INESPERADO DURANTE SMOKE TEST:\n{ex}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        background_manager.shutdown()


if __name__ == "__main__":
    sys.exit(run_smoke_test())

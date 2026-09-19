"""
Tests unitarios y de integración para el Validador de Layout (Fase 78 Fix Ronda 4).

Cubre:
1. Regla R1:
   - Detección de coordenadas absolutas (top/left/right/bottom) fuera de ft.Stack directo o page.overlay.
   - Modo Dev (strict=True): Lanza LayoutRuleViolationError con el control, coordenadas y cadena de padres.
   - Modo Prod (strict=False): Auto-limpia las propiedades a None y permite continuar sin crash.
   - Validez de coordenadas cuando el padre directo ES un ft.Stack o el control está en page.overlay.
2. Regla R2:
   - Validación del Stack raíz (ft.Stack, expand=True, y presencia de hijos).
   - Auto-corrección de expand=False en modo prod.
3. Integración con MainWindow:
   - Verificación de que la UI completa de AURA pasa la validación estricta (strict=True).
   - Ausencia total de coordenadas absolutas en la jerarquía del fondo y layout principal.
"""

from unittest.mock import MagicMock
import pytest
import flet as ft

from aura.ui.layout_rules import (
    LayoutRuleViolationError,
    get_control_children,
    is_strict_mode,
    validate_layout,
)
from aura.ui.background_manager import background_manager
from ui.main_window import MainWindow


@pytest.fixture(autouse=True)
def cleanup_after_test():
    yield
    background_manager.shutdown()


# ── 1. PRUEBAS DE LA REGLA R1: COORDENADAS FUERA DE STACK ────────

def test_r1_violation_in_strict_mode_raises_with_parent_chain():
    """En modo estricto, un control con top=0 dentro de Column debe lanzar LayoutRuleViolationError con su árbol de ancestros."""
    inner_label = ft.Text("Etiqueta", top=10, left=5)
    container = ft.Container(content=inner_label)
    col = ft.Column(controls=[container])
    root = ft.Stack(controls=[col], expand=True)

    with pytest.raises(LayoutRuleViolationError) as exc_info:
        validate_layout(root, strict=True)

    err_str = str(exc_info.value)
    assert "[Regla R1]" in err_str
    assert "Text" in err_str
    assert "top" in err_str
    assert "left" in err_str
    # Cadena de ancestros esperada: Stack -> Column -> Container -> Text
    assert "Stack -> Column -> Container -> Text" in err_str


def test_r1_violation_in_prod_mode_autocleans_coordinates():
    """En modo prod (strict=False), las coordenadas fuera de Stack se limpian a None sin excepción."""
    inner_label = ft.Text("Etiqueta", top=10, left=5, right=20, bottom=0)
    col = ft.Column(controls=[inner_label])
    root = ft.Stack(controls=[col], expand=True)

    violations = validate_layout(root, strict=False)

    assert len(violations) == 1
    v = violations[0]
    assert v["rule"] == "R1"
    assert v["cleaned"] is True
    assert v["coords"] == {"top": 10, "left": 5, "right": 20, "bottom": 0}

    # Comprobar que el control fue limpiado
    assert inner_label.top is None
    assert inner_label.left is None
    assert inner_label.right is None
    assert inner_label.bottom is None


def test_r1_valid_coordinates_inside_direct_stack_parent():
    """Un control con coordenadas cuyo padre directo ES ft.Stack es totalmente válido."""
    floating_widget = ft.Container(bottom=20, right=20)
    root = ft.Stack(controls=[floating_widget], expand=True)

    violations = validate_layout(root, strict=True)
    assert len(violations) == 0
    assert floating_widget.bottom == 20
    assert floating_widget.right == 20


def test_r1_valid_coordinates_inside_page_overlay():
    """Un control con coordenadas dentro de page.overlay es válido."""
    overlay_picker = ft.Container(top=50, left=50)
    page_mock = MagicMock(spec=ft.Page)
    page_mock.overlay = [overlay_picker]

    root = ft.Stack(controls=[ft.Text("Hola")], expand=True)

    violations = validate_layout(root, page=page_mock, strict=True)
    assert len(violations) == 0
    assert overlay_picker.top == 50
    assert overlay_picker.left == 50


# ── 2. PRUEBAS DE LA REGLA R2: STACK RAÍZ ────────────────────────

def test_r2_root_not_stack_raises_in_strict_mode():
    """Si la raíz no es un ft.Stack, en modo estricto lanza LayoutRuleViolationError."""
    invalid_root = ft.Container(content=ft.Text("Sin Stack"))

    with pytest.raises(LayoutRuleViolationError) as exc_info:
        validate_layout(invalid_root, strict=True)

    assert "[Regla R2]" in str(exc_info.value)
    assert "Container" in str(exc_info.value)


def test_r2_root_not_stack_returns_violation_in_prod_mode():
    """Si la raíz no es ft.Stack, en prod retorna violación sin romper."""
    invalid_root = ft.Column(controls=[ft.Text("Hola")])
    violations = validate_layout(invalid_root, strict=False)

    assert any(v["rule"] == "R2" for v in violations)


def test_r2_root_stack_expand_false_is_autofixed_in_prod():
    """Si el Stack raíz tiene expand=False, en modo prod se auto-corrige a expand=True."""
    root = ft.Stack(controls=[ft.Container()], expand=False)

    violations = validate_layout(root, strict=False)
    assert root.expand is True
    assert any(v["rule"] == "R2" and v["cleaned"] is True for v in violations)


def test_r2_root_stack_expand_false_raises_in_strict():
    """Si el Stack raíz tiene expand=False, en modo estricto lanza excepción."""
    root = ft.Stack(controls=[ft.Container()], expand=False)

    with pytest.raises(LayoutRuleViolationError) as exc_info:
        validate_layout(root, strict=True)

    assert "expand=True" in str(exc_info.value)


# ── 3. PRUEBAS DE UTILIDADES Y CONFIGURACIÓN ─────────────────────

def test_is_strict_mode_resolution(monkeypatch):
    """Verifica la resolución de is_strict_mode con argumento, variable de entorno y settings."""
    # Argumento explícito
    assert is_strict_mode(strict=True) is True
    assert is_strict_mode(strict=False) is False

    # Variable de entorno
    monkeypatch.setenv("LAYOUT_STRICT", "1")
    assert is_strict_mode() is True

    monkeypatch.setenv("LAYOUT_STRICT", "true")
    assert is_strict_mode() is True

    monkeypatch.setenv("LAYOUT_STRICT", "0")
    # settings fallback
    assert is_strict_mode() is False


def test_get_control_children_handles_various_containers():
    """Verifica la extracción de hijos en distintos tipos de contenedores."""
    c1 = ft.Text("1")
    c2 = ft.Text("2")
    col = ft.Column(controls=[c1, c2])
    assert get_control_children(col) == [c1, c2]

    cnt = ft.Container(content=c1)
    assert get_control_children(cnt) == [c1]

    assert get_control_children(None) == []


# ── 4. INTEGRACIÓN CON MAINWINDOW ────────────────────────────────

def test_mainwindow_passes_strict_layout_validation():
    """MainWindow montado debe pasar validate_layout(strict=True) sin violaciones R1 ni R2."""
    page_mock = MagicMock(spec=ft.Page)
    page_mock.services = []
    page_mock.overlay = []
    page_mock.controls = []

    def mock_add(ctrl):
        page_mock.controls.append(ctrl)

    page_mock.add = mock_add

    win = MainWindow()
    win._main(page_mock)

    # Validar árbol montado
    violations = validate_layout(win._root_stack, page=page_mock, strict=True)
    assert violations == []

    # Verificar que controles de fondo y layout general NO tienen coordenadas absolutas
    for ctrl in (
        win._root_stack,
        win._bg_container,
        win._bg_layer,
        win._bg_image,
        win._scrim_container,
    ):
        assert ctrl.top is None
        assert ctrl.left is None
        assert ctrl.right is None
        assert ctrl.bottom is None
        assert ctrl.expand is True

    # Cambiar tema y verificar que se mantiene válido
    from aura.ui.theme import theme_manager
    win.apply_theme(theme_manager.current_tokens)
    violations_theme = validate_layout(win._root_stack, page=page_mock, strict=True)
    assert violations_theme == []

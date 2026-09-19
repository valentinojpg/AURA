"""
Tests unitarios y de integración para el Fix de Fase 78 (Ronda 3):
Cobertura total de fondo de pantalla custom (imágenes estáticas y GIFs animados),
anclaje estricto en Stack raíz con exactamente 2 hijos, fit=EXPAND, ausencia
total de dimensiones explícitas (width/height), transparencia en todas las vistas
(incluyendo barra de input inferior de ChatPage) y restauración limpia en 'Quitar fondo'.
"""

import os
import tempfile
from unittest.mock import MagicMock
from PIL import Image
import pytest
import flet as ft

from config.settings import settings
from aura.ui.background_manager import background_manager
from aura.ui.theme import theme_manager
from ui.main_window import MainWindow, _resolve_box_fit
from ui.pages.chat_page import ChatPage


@pytest.fixture(autouse=True)
def reset_background_state():
    """Restaura el estado de settings y background_manager antes y después de cada test."""
    original_bg = settings.get("BG_IMAGE_PATH", "")
    original_fit = settings.get("BG_FIT", "cover")
    original_side_op = settings.get("BG_SIDEBAR_OPACITY", "0.0")
    original_scrim_op = settings.get("BG_SCRIM_OPACITY", "0.25")

    yield

    background_manager.shutdown()
    settings.set("BG_IMAGE_PATH", original_bg)
    settings.set("BG_FIT", original_fit)
    settings.set("BG_SIDEBAR_OPACITY", original_side_op)
    settings.set("BG_SCRIM_OPACITY", original_scrim_op)


def _build_test_window(bg_path: str = "", fit: str = "cover", side_op: float = 0.0, scrim_op: float = 0.25) -> tuple[MainWindow, MagicMock]:
    """Instancia y monta un MainWindow con mocks livianos de ft.Page."""
    settings.set("BG_IMAGE_PATH", bg_path)
    settings.set("BG_FIT", fit)
    settings.set("BG_SIDEBAR_OPACITY", str(side_op))
    settings.set("BG_SCRIM_OPACITY", str(scrim_op))

    page_mock = MagicMock(spec=ft.Page)
    page_mock.services = []
    page_mock.overlay = []
    page_mock.controls = []

    def mock_add(control):
        page_mock.controls.append(control)

    page_mock.add = mock_add

    win = MainWindow()
    win._main(page_mock)
    return win, page_mock


# ── 1. PRUEBAS DE ESTRUCTURA DEL STACK RAÍZ (EXACTAMENTE 2 HIJOS) ─

def test_root_stack_has_exactly_two_children():
    """Verifica que la raíz de la UI es un ft.Stack con exactamente dos hijos: [0] fondo, [1] contenido."""
    win, page_mock = _build_test_window()

    assert hasattr(win, "_root_stack")
    root = win._root_stack
    assert isinstance(root, ft.Stack)
    assert len(root.controls) == 2, f"El Stack raíz debe tener exactamente 2 hijos, tiene {len(root.controls)}"

    # [0] layer de fondo
    bg_child = root.controls[0]
    assert bg_child is win._bg_container
    assert isinstance(bg_child, ft.Container)

    # [1] layer de contenido (sidebar + vistas)
    content_child = root.controls[1]
    assert isinstance(content_child, ft.Column)


def test_root_stack_uses_expand_and_stackfit_expand():
    """Verifica que el Stack raíz y el sub-stack del fondo usan expand=True y fit=StackFit.EXPAND."""
    win, _ = _build_test_window()

    root = win._root_stack
    assert root.expand is True
    assert root.fit == ft.StackFit.EXPAND

    # Sub-stack interno del fondo
    assert hasattr(win, "_bg_layer")
    bg_layer = win._bg_layer
    assert isinstance(bg_layer, ft.Stack)
    assert bg_layer.expand is True
    assert bg_layer.fit == ft.StackFit.EXPAND


def test_no_explicit_dimensions_in_background_chain():
    """Verifica la regla estricta: NINGÚN control en la cadena del fondo tiene width o height explícitos."""
    win, _ = _build_test_window()

    # Controles que participan del fondo
    controls_to_check = [
        win._root_stack,
        win._bg_container,
        win._bg_layer,
        win._bg_image,
        win._scrim_container,
    ]

    for ctrl in controls_to_check:
        name = ctrl.__class__.__name__
        assert ctrl.width is None, f"{name} no debe tener width explícito (tiene {ctrl.width})"
        assert ctrl.height is None, f"{name} no debe tener height explícito (tiene {ctrl.height})"


def test_background_controls_anchors_top_left_right_bottom():
    """Verifica que los controles del fondo NO usen top/left/right/bottom explícitos (deben ser None) y tengan expand=True."""
    win, _ = _build_test_window()

    for ctrl in (win._root_stack, win._bg_container, win._bg_layer, win._bg_image, win._scrim_container):
        name = ctrl.__class__.__name__
        assert ctrl.top is None, f"{name}.top debe ser None"
        assert ctrl.left is None, f"{name}.left debe ser None"
        assert ctrl.right is None, f"{name}.right debe ser None"
        assert ctrl.bottom is None, f"{name}.bottom debe ser None"
        assert ctrl.expand is True, f"{name}.expand debe ser True"


# ── 2. PRUEBA CON IMAGEN REAL DRAGON BALL (1920x1397) ────────────

def test_dragon_ball_image_full_coverage():
    """Verifica la aplicación de imagen similar a la Dragon Ball (1920x1397) cubriendo toda la ventana."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
        db_jpg = tf.name

    try:
        # Generar imagen con resolución exacta del wallpaper del usuario: 1920x1397
        im = Image.new("RGB", (1920, 1397), color=(255, 140, 0))
        im.save(db_jpg, format="JPEG")

        win, _ = _build_test_window()

        # Aplicar el fondo con fit "cover"
        win.apply_background_to_ui(
            bg_path=db_jpg,
            fit="cover",
            sidebar_opacity=0.2,
            scrim_opacity=0.3,
        )

        assert win._bg_container.visible is True
        assert win._bg_image.src == db_jpg
        assert win._bg_image.fit == ft.BoxFit.COVER
        assert win._bg_image.repeat == ft.ImageRepeat.NO_REPEAT

        # Scrim activo sobre la imagen
        assert win._scrim_container.visible is True

        # Verificar que el contenedor de contenido principal es transparente
        assert win._content_container.bgcolor == "transparent"

        # Verificar cambios en caliente de ajuste (fit)
        win.update_fit_in_ui("contain")
        assert win._bg_image.fit == ft.BoxFit.CONTAIN

        win.update_fit_in_ui("stretch")
        assert win._bg_image.fit == ft.BoxFit.FILL

        win.update_fit_in_ui("cover")
        assert win._bg_image.fit == ft.BoxFit.COVER

    finally:
        if os.path.exists(db_jpg):
            os.remove(db_jpg)


# ── 3. COBERTURA DETRÁS DE CHAT Y BARRA DE INPUT INFERIOR ────────

def test_chat_page_input_container_transparency():
    """Verifica que en ChatPage la barra de input y banner no tengan fondo opaco que tape el wallpaper."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        fake_bg = tf.name

    try:
        Image.new("RGB", (100, 100), color="blue").save(fake_bg)
        win, _ = _build_test_window(bg_path=fake_bg)

        chat_page: ChatPage = win._pages["chat"]

        # Con fondo activo, tanto la página como la barra de input son transparentes
        assert chat_page.bgcolor == "transparent"
        assert hasattr(chat_page, "_input_container")
        assert chat_page._input_container.bgcolor == "transparent"
        assert chat_page._status_banner.bgcolor == "transparent"

        # Simular quitar fondo: debe restaurarse el color opaco del tema
        win.apply_background_to_ui(bg_path=None)

        assert chat_page.bgcolor == theme_manager.current_tokens.chat_bg
        assert chat_page._input_container.bgcolor == "#0F0F22"
        assert chat_page._status_banner.bgcolor != "transparent"

    finally:
        if os.path.exists(fake_bg):
            os.remove(fake_bg)


# ── 4. TRANSPARENCIA EN TODAS LAS 6 VISTAS ────────────────────────

def test_all_six_views_transparent_with_background():
    """Verifica que las 6 vistas tengan fondo transparente cuando hay wallpaper activo."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        fake_bg = tf.name

    try:
        Image.new("RGB", (100, 100), color="green").save(fake_bg)
        win, _ = _build_test_window(bg_path=fake_bg)

        page_ids = ["chat", "skills", "automation", "files", "code", "settings"]

        for pid in page_ids:
            win.navigate(pid)
            p = win._pages[pid]
            assert p.bgcolor == "transparent", f"Página '{pid}' debe tener bgcolor='transparent' con fondo activo"

        # Al quitar fondo, todas deben recuperar el chat_bg del tema
        win.apply_background_to_ui(bg_path=None)

        for pid in page_ids:
            win.navigate(pid)
            p = win._pages[pid]
            assert p.bgcolor == theme_manager.current_tokens.chat_bg, f"Página '{pid}' debe restaurar bgcolor del tema"

    finally:
        if os.path.exists(fake_bg):
            os.remove(fake_bg)


# ── 5. RESTAURACIÓN LIMPIA EN 'QUITAR FONDO' ──────────────────────

def test_remove_background_full_restore():
    """Verifica que 'Quitar fondo' restaura el fondo sólido del tema sin dejar artefactos."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        fake_bg = tf.name

    try:
        Image.new("RGB", (100, 100), color="purple").save(fake_bg)
        win, _ = _build_test_window(bg_path=fake_bg, side_op=0.5, scrim_op=0.4)

        assert win._bg_container.visible is True
        assert win._scrim_container.visible is True

        # Quitar fondo
        win.apply_background_to_ui(bg_path=None)

        assert win._bg_container.visible is False
        assert win._scrim_container.visible is False
        assert win._bg_image.src == ""
        assert win._content_container.bgcolor == theme_manager.current_tokens.chat_bg

        tokens = theme_manager.current_tokens
        assert win.page.bgcolor == tokens.app_bg

    finally:
        if os.path.exists(fake_bg):
            os.remove(fake_bg)


# ── 6. GIF ANIMADO A PANTALLA COMPLETA Y REPRODUCCIÓN CONTINUA ────

def test_animated_gif_fullscreen_and_frame_fallback():
    """Verifica que los GIFs animados se asignan con gapless_playback y responden a update_background_frame."""
    with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as tf:
        gif_path = tf.name

    try:
        f1 = Image.new("RGB", (200, 200), "red")
        f2 = Image.new("RGB", (200, 200), "blue")
        f1.save(gif_path, save_all=True, append_images=[f2], duration=100, loop=0)

        win, _ = _build_test_window()
        win.apply_background_to_ui(bg_path=gif_path, fit="cover")

        assert win._bg_image.gapless_playback is True
        assert win._bg_image.src == gif_path
        assert win._bg_container.visible is True

        # Fallback de frame
        win.update_background_frame("assets/backgrounds/cache/frame_0001.png")
        assert win._bg_image.src == "assets/backgrounds/cache/frame_0001.png"

    finally:
        if os.path.exists(gif_path):
            os.remove(gif_path)


# ── 7. RESOLUCIÓN DE BOXFIT ───────────────────────────────────────

def test_resolve_box_fit():
    """Verifica el mapeo robusto de nombres de ajuste a enums ft.BoxFit."""
    assert _resolve_box_fit("cover") == ft.BoxFit.COVER
    assert _resolve_box_fit("COVER") == ft.BoxFit.COVER
    assert _resolve_box_fit("contain") == ft.BoxFit.CONTAIN
    assert _resolve_box_fit("stretch") == ft.BoxFit.FILL
    assert _resolve_box_fit("fill") == ft.BoxFit.FILL
    assert _resolve_box_fit("desconocido") == ft.BoxFit.COVER

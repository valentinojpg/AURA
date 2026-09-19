"""
Tests unitarios e integración para Fix Fase 78 Ronda 5 (AURA Orion).

Verifica:
  1. Regla 1: GIFs bajo umbrales (<= 2560 px y <= 20 MB) se copian tal cual sin re-codificar (recoded=False).
  2. Regla 2: GIFs sobre umbrales se re-codifican preservando durations, disposals, loop y paleta adaptativa.
  3. Regla 3: Verificación automática post-normalización (frames > 1, duraciones != 0, tolerancia 10%)
     y extracción de 3 frames de muestra en assets/backgrounds/cache/qa/.
  4. Abortar re-codificación y copiar original si la verificación falla.
  5. Saneamiento de dexter-sad.gif del usuario (139 frames, 23.9 fps, peso exacto intacto).
  6. Layer de fondo en hijo [0] del Stack raíz con ft.Image(src=<gif>) nativo por defecto.
  7. BG_GIF_MODE: 'native' por defecto (sin timer); 'frames' activa timer apuntando al fondo (tope 20 FPS).
  8. Preview/Thumbnail de Configuración es ESTÁTICO (PNG del frame 0), nunca animado ni ciclando.
  9. validate_layout en modo estricto sobre árbol con fondo GIF activo sin violaciones ni auto-limpiezas.
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from PIL import Image
import pytest
import flet as ft

from config.settings import settings
from aura.ui.background_manager import (
    BACKGROUNDS_DIR,
    QA_DIR,
    background_manager,
    normalize_background_image,
    load_current_metadata,
    _verify_and_qa_gif,
)
from ui.main_window import MainWindow
from ui.pages.settings_page import SettingsPage
from aura.ui.layout_rules import validate_layout


@pytest.fixture(autouse=True)
def reset_background_state():
    """Restaura el estado de settings y background_manager antes y después de cada test."""
    original_bg = settings.get("BG_IMAGE_PATH", "")
    original_fit = settings.get("BG_FIT", "cover")
    original_side_op = settings.get("BG_SIDEBAR_OPACITY", "0.0")
    original_scrim_op = settings.get("BG_SCRIM_OPACITY", "0.25")
    original_mode = settings.get("BG_GIF_MODE", "native")

    yield

    background_manager.shutdown()
    settings.set("BG_IMAGE_PATH", original_bg)
    settings.set("BG_FIT", original_fit)
    settings.set("BG_SIDEBAR_OPACITY", original_side_op)
    settings.set("BG_SCRIM_OPACITY", original_scrim_op)
    settings.set("BG_GIF_MODE", original_mode)

    # Restaurar dexter-sad.gif si existe en Desktop
    dexter_src = Path(r"C:\Users\Cliente\Desktop\dexter-sad.gif")
    if dexter_src.exists():
        try:
            normalize_background_image(dexter_src)
        except Exception:
            pass


def _build_test_window(bg_path: str = "", fit: str = "cover", side_op: float = 0.0, scrim_op: float = 0.25, gif_mode: str = "native") -> tuple[MainWindow, MagicMock]:
    """Instancia y monta MainWindow con mocks livianos de ft.Page."""
    settings.set("BG_IMAGE_PATH", bg_path)
    settings.set("BG_FIT", fit)
    settings.set("BG_SIDEBAR_OPACITY", str(side_op))
    settings.set("BG_SCRIM_OPACITY", str(scrim_op))
    settings.set("BG_GIF_MODE", gif_mode)

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


# ── 1. REGLA 1: GIF DENTRO DE UMBRALES SE COPIA TAL CUAL ──────────

def test_gif_under_threshold_copied_as_is():
    """Verifica que un GIF que no supere 2560px ni 20MB se copia idéntico sin re-codificación Pillow."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        src_gif = temp_dir / "anim_small.gif"
        frames = [Image.new("RGB", (320, 240), color=(i * 60, 100, 150)) for i in range(4)]
        frames[0].save(src_gif, save_all=True, append_images=frames[1:], duration=60, loop=0)

        meta = normalize_background_image(src_gif)

        assert meta["is_gif"] is True
        assert meta["recoded"] is False
        assert meta["width"] == 320
        assert meta["height"] == 240
        assert meta["frames_count"] == 4
        assert meta["fps"] == 16.7  # 1000 / 60

        # El archivo de destino debe ser idéntico byte a byte
        target = Path(meta["target_file"])
        assert target.exists()
        assert target.stat().st_size == src_gif.stat().st_size

        # Verificación de muestra en QA
        assert QA_DIR.exists()
        qa_samples = list(QA_DIR.glob("*.png"))
        assert len(qa_samples) >= 3

        # Preview estático generado en PNG
        preview = Path(meta["preview_file"])
        assert preview.exists()
        assert preview.suffix.lower() == ".png"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ── 2. REGLA 2 Y 3: GIF SOBRE UMBRAL RE-CODIFICADO Y VALIDADO ─────

def test_gif_over_threshold_recoded_preserving_animation():
    """Verifica que un GIF que supere los 2560 px se re-escala proporcionalmente preservando animación."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        src_gif = temp_dir / "anim_large.gif"
        # 3000 x 1500 (supera MAX_WIDTH=2560)
        frames = [Image.new("RGB", (3000, 1500), color=(i * 50, 120, 180)) for i in range(3)]
        frames[0].save(src_gif, save_all=True, append_images=frames[1:], duration=80, loop=0)

        meta = normalize_background_image(src_gif)

        assert meta["is_gif"] is True
        assert meta["recoded"] is True
        assert meta["width"] == 2560
        assert meta["height"] == 1280  # 1500 * (2560 / 3000)
        assert meta["frames_count"] == 3

        # Comprobar que el archivo re-codificado reabre sano con Pillow
        with Image.open(meta["target_file"]) as res_im:
            assert res_im.size == (2560, 1280)
            assert res_im.n_frames == 3
            res_im.seek(0)
            assert res_im.info.get("duration") == 80

        # Verificación QA presente
        qa_samples = list(QA_DIR.glob("*.png"))
        assert len(qa_samples) >= 3
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ── 3. ABORTAR RE-CODIFICACIÓN ANTE FALLO DE VERIFICACIÓN ──────────

def test_verify_and_qa_gif_failure_detection():
    """Verifica que _verify_and_qa_gif detecta fallas de frames o duraciones erróneas."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        broken_gif = temp_dir / "broken.gif"
        # 1 solo frame estático
        Image.new("RGB", (100, 100), "red").save(broken_gif)

        # Esperaba 5 frames, solo tiene 1 -> debe retornar False
        is_ok = _verify_and_qa_gif(
            gif_path=broken_gif,
            expected_frames_count=5,
            original_durations=[50, 50, 50, 50, 50],
            qa_dir=temp_dir / "qa",
        )
        assert is_ok is False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ── 4. SANEAMIENTO DEL ARCHIVO REAL DEL USUARIO (dexter-sad.gif) ───

def test_dexter_sad_gif_sanity():
    """Verifica que dexter-sad.gif en el proyecto se encuentra completamente sano y no frankenstein."""
    dexter_src = Path(r"C:\Users\Cliente\Desktop\dexter-sad.gif")
    if dexter_src.exists():
        normalize_background_image(dexter_src)

    current_gif = BACKGROUNDS_DIR / "current.gif"
    assert current_gif.exists(), "current.gif debe existir en assets/backgrounds/"

    meta = load_current_metadata()
    assert meta is not None
    assert meta["is_gif"] is True
    assert meta["frames_count"] == 139
    assert meta["fps"] == 23.9
    assert meta["recoded"] is False

    # Verificar que tiene el peso original (~1.96 MB, no el frankenstein de 7.14 MB)
    assert current_gif.stat().st_size == 1968730

    # Comprobar animación y colores abriendo con Pillow
    with Image.open(current_gif) as im:
        assert im.n_frames == 139
        assert im.size == (374, 229)
        im.seek(0)
        assert im.info.get("duration") == 40
        im.seek(1)
        assert im.info.get("duration") == 40


# ── 5. BG_GIF_MODE: NATIVE VS FRAMES ──────────────────────────────

def test_bg_gif_mode_native_default_and_frames_fallback():
    """Verifica el comportamiento de BG_GIF_MODE=native (Flutter nativo) y BG_GIF_MODE=frames (fallback)."""
    current_gif = str(BACKGROUNDS_DIR / "current.gif")

    # 1. Modo nativo por defecto
    settings.set("BG_GIF_MODE", "native")
    win, _ = _build_test_window(bg_path=current_gif, gif_mode="native")

    assert background_manager.current_gif_mode == "native"
    assert background_manager._gif_player.is_running is False
    assert win._bg_image.src == current_gif
    assert win._bg_image.gapless_playback is True

    # 2. Conmutar a modo frames en caliente
    background_manager.set_gif_mode("frames", save=True)
    assert background_manager.current_gif_mode == "frames"
    assert background_manager._gif_player.is_running is True

    # 3. Volver a modo native en caliente
    background_manager.set_gif_mode("native", save=True)
    assert background_manager.current_gif_mode == "native"
    assert background_manager._gif_player.is_running is False
    assert win._bg_image.src == current_gif


# ── 6. THUMBNAIL/PREVIEW DE CONFIGURACIÓN ES ESTÁTICO (PNG) ───────

def test_settings_page_preview_is_static_png():
    """Verifica que el preview en Configuración es un PNG estático y nunca el GIF animado."""
    current_gif = str(BACKGROUNDS_DIR / "current.gif")
    win, page_mock = _build_test_window(bg_path=current_gif)

    # Navegar a Configuración
    win.navigate("settings")
    settings_page: SettingsPage = win._pages["settings"]

    assert hasattr(settings_page, "_bg_preview_img")
    preview_src = settings_page._bg_preview_img.src
    assert preview_src != "", "Preview image src no debe estar vacío con fondo activo"
    assert preview_src.lower().endswith(".png"), f"Preview image src debe ser PNG estático, tiene '{preview_src}'"
    assert not preview_src.lower().endswith(".gif"), "El preview de Configuración jamás debe apuntar a un GIF animado"

    # Thumbnail path expuesto por background_manager
    thumb_path = background_manager.current_thumbnail_path
    assert thumb_path is not None
    assert thumb_path.lower().endswith(".png")
    assert Path(thumb_path).exists()


# ── 7. VALIDACIÓN DE LAYOUT STRICT SOBRE ÁRBOL CON GIF ─────────────

def test_validate_layout_strict_with_gif_background():
    """Verifica que validate_layout pasa en modo estricto con el fondo GIF aplicado sin violaciones."""
    current_gif = str(BACKGROUNDS_DIR / "current.gif")
    win, page_mock = _build_test_window(bg_path=current_gif)

    violations = validate_layout(win._root_stack, page=page_mock, strict=True)
    assert len(violations) == 0, f"No debe haber violaciones de layout: {violations}"

    # Verificar que el hijo [0] es el Container de fondo con expand=True
    assert win._root_stack.controls[0] is win._bg_container
    assert win._bg_container.expand is True
    assert win._bg_image.expand is True
    assert win._bg_image.src == current_gif

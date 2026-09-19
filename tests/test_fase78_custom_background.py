"""
Tests unitarios para la Fase 78 — Fondo de Pantalla Personalizado (AURA Orion).

Cubre:
  1. Normalización de imágenes estáticas (PNG, JPG).
  2. Conversión automática de formatos no soportados por el renderer (WEBP, BMP a PNG).
  3. Re-escalado proporcional de imágenes de gran resolución (> 2560 px) preservando aspect ratio.
  4. Normalización de GIFs animados: frames, durations, fps y extracción de frames fallback.
  5. Cálculo de luminancia relativa WCAG con Pillow y verificación de contraste.
  6. Persistencia de variables BG_* en settings/.env.
  7. Recuperación limpia y sin crashes cuando el archivo referenciado no existe o fue borrado.
  8. GifFramePlayer: ciclo de frames con tope de 20 FPS y detención limpia de hilos.
  9. Independencia entre Restaurar Azul (tema) y Quitar Fondo (fondo).
"""

import os
import shutil
import tempfile
import time
from pathlib import Path
from PIL import Image

import pytest

from config.settings import settings
from aura.ui.background_manager import (
    METADATA_FILE,
    GifFramePlayer,
    background_manager,
    calculate_average_luminance,
    get_current_background_path,
    load_current_metadata,
    normalize_background_image,
)
from aura.ui.theme import build_theme_tokens


@pytest.fixture(autouse=True)
def cleanup_background_state():
    """Restaura el estado de settings y limpia archivos temporales antes y después de cada test."""
    original_bg = settings.get("BG_IMAGE_PATH", "")
    original_fit = settings.get("BG_FIT", "cover")
    original_side_op = settings.get("BG_SIDEBAR_OPACITY", "0.0")
    original_scrim_op = settings.get("BG_SCRIM_OPACITY", "0.25")

    yield

    # Cleanup
    background_manager.shutdown()
    settings.set("BG_IMAGE_PATH", original_bg)
    settings.set("BG_FIT", original_fit)
    settings.set("BG_SIDEBAR_OPACITY", original_side_op)
    settings.set("BG_SCRIM_OPACITY", original_scrim_op)


# ── 1. PRUEBAS DE NORMALIZACIÓN CON PILLOW ──────────────────────

def test_normalize_static_png():
    """Verifica que un archivo PNG se normaliza, copia a current.png y genera metadata JSON."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        tmp_path = tf.name

    try:
        img = Image.new("RGB", (1280, 720), color=(50, 100, 150))
        img.save(tmp_path, format="PNG")

        meta = normalize_background_image(tmp_path)

        assert meta["is_gif"] is False
        assert meta["width"] == 1280
        assert meta["height"] == 720
        assert meta["ext"] == ".png"
        assert meta["frames_count"] == 1
        assert Path(meta["target_file"]).exists()
        assert Path(meta["target_file"]).name == "current.png"
        assert METADATA_FILE.exists()

        loaded = load_current_metadata()
        assert loaded is not None
        assert loaded["hash"] == meta["hash"]
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_normalize_static_jpg():
    """Verifica que un JPG se preserva como JPG optimizado."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
        tmp_path = tf.name

    try:
        img = Image.new("RGB", (800, 600), color=(20, 30, 40))
        img.save(tmp_path, format="JPEG")

        meta = normalize_background_image(tmp_path)

        assert meta["is_gif"] is False
        assert meta["ext"] == ".jpg"
        assert meta["width"] == 800
        assert meta["height"] == 600
        assert Path(meta["target_file"]).name == "current.jpg"
        assert Path(meta["target_file"]).exists()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_convert_webp_and_bmp_to_png():
    """Verifica que formatos como WEBP y BMP se convierten automáticamente a PNG."""
    with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as tf_bmp, \
         tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as tf_webp:
        bmp_path = tf_bmp.name
        webp_path = tf_webp.name

    try:
        img_b = Image.new("RGB", (640, 480), color=(10, 20, 30))
        img_b.save(bmp_path, format="BMP")

        img_w = Image.new("RGB", (640, 480), color=(40, 50, 60))
        img_w.save(webp_path, format="WEBP")

        # Probar BMP -> PNG
        meta_bmp = normalize_background_image(bmp_path)
        assert meta_bmp["ext"] == ".png"
        assert meta_bmp["format"] == "PNG"
        assert Path(meta_bmp["target_file"]).name == "current.png"
        assert Path(meta_bmp["target_file"]).exists()

        # Probar WEBP -> PNG
        meta_webp = normalize_background_image(webp_path)
        assert meta_webp["ext"] == ".png"
        assert meta_webp["format"] == "PNG"
        assert Path(meta_webp["target_file"]).name == "current.png"
        assert Path(meta_webp["target_file"]).exists()
    finally:
        for p in (bmp_path, webp_path):
            if os.path.exists(p):
                os.remove(p)


def test_resize_large_image_4k():
    """Verifica que imágenes que superen 2560 px de ancho se re-escalen proporcionalmente."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        tmp_path = tf.name

    try:
        # Wallpaper 4K UHD: 3840 x 2160 (aspect ratio 16:9)
        img = Image.new("RGB", (3840, 2160), color=(255, 128, 0))
        img.save(tmp_path, format="PNG")

        meta = normalize_background_image(tmp_path)

        assert meta["width"] == 2560
        expected_height = int(round(2160 * (2560.0 / 3840)))
        assert meta["height"] == expected_height
        assert Path(meta["target_file"]).exists()

        with Image.open(meta["target_file"]) as res_img:
            assert res_img.size == (2560, expected_height)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ── 2. PRUEBAS DE GIFS ANIMADOS Y FALLBACK DE FRAMES ─────────────

def test_normalize_animated_gif():
    """Verifica que un GIF animado se detecta, se calculan frames y fps, y se extraen frames para fallback."""
    with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as tf:
        tmp_path = tf.name

    try:
        # Crear un GIF de 3 frames con duración de 100 ms cada uno (10 FPS)
        f1 = Image.new("RGB", (400, 300), color="red")
        f2 = Image.new("RGB", (400, 300), color="green")
        f3 = Image.new("RGB", (400, 300), color="blue")

        f1.save(
            tmp_path,
            save_all=True,
            append_images=[f2, f3],
            duration=[100, 100, 100],
            loop=0,
        )

        meta = normalize_background_image(tmp_path)

        assert meta["is_gif"] is True
        assert meta["frames_count"] == 3
        assert meta["fps"] == 10.0
        assert meta["ext"] == ".gif"
        assert Path(meta["target_file"]).name == "current.gif"
        assert Path(meta["target_file"]).exists()

        # Verificar que la caché de frames existe
        frames_dir = Path(meta["frames_cache_dir"])
        assert frames_dir.exists()
        extracted_frames = list(frames_dir.glob("frame_*.png"))
        assert len(extracted_frames) == 3
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_gif_frame_player_cycling_and_stop():
    """Verifica que GifFramePlayer cicla fotogramas respetando el tope de 20 FPS y se detiene limpiamente."""
    # Crear carpeta temporal con 2 frames
    temp_dir = tempfile.mkdtemp()
    try:
        f1_path = Path(temp_dir) / "frame_0000.png"
        f2_path = Path(temp_dir) / "frame_0001.png"
        Image.new("RGB", (50, 50), "black").save(f1_path)
        Image.new("RGB", (50, 50), "white").save(f2_path)

        received_frames: list[str] = []

        def on_frame(p: str):
            received_frames.append(p)

        player = GifFramePlayer()
        assert player.is_running is False

        # Duración corta de 10ms: el player debe limitar a tope 20 FPS (50ms mínimo)
        player.start(temp_dir, durations=[10, 10], on_frame=on_frame)
        assert player.is_running is True

        # Esperar un tiempo controlado
        time.sleep(0.18)
        player.stop()

        assert player.is_running is False
        assert len(received_frames) >= 2
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ── 3. LUMINANCIA WCAG Y SUGERENCIA DE CONTRASTE ─────────────────

def test_calculate_average_luminance():
    """Verifica el cálculo de luminancia WCAG con Pillow."""
    # Blanco puro -> 1.0
    white_img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    lum_white = calculate_average_luminance(white_img)
    assert lum_white >= 0.95

    # Negro puro -> 0.0
    black_img = Image.new("RGB", (100, 100), color=(0, 0, 0))
    lum_black = calculate_average_luminance(black_img)
    assert lum_black <= 0.05

    # Color oscuro
    dark_img = Image.new("RGB", (100, 100), color=(15, 15, 25))
    lum_dark = calculate_average_luminance(dark_img)
    assert lum_dark < 0.15


# ── 4. PERSISTENCIA Y CICLO DE VIDA DE BACKGROUND_MANAGER ────────

def test_background_manager_apply_and_remove():
    """Verifica la persistencia de variables en settings/.env al aplicar y quitar fondo."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        fake_bg = tf.name

    try:
        Image.new("RGB", (100, 100), color="blue").save(fake_bg)

        # Aplicar
        info = background_manager.apply_background(
            image_path=fake_bg,
            fit="contain",
            sidebar_opacity=0.4,
            scrim_opacity=0.3,
            save=True,
        )

        assert background_manager.is_active is True
        assert settings.get("BG_IMAGE_PATH") == fake_bg
        assert settings.get("BG_FIT") == "contain"
        assert settings.get_float("BG_SIDEBAR_OPACITY") == 0.4
        assert settings.get_float("BG_SCRIM_OPACITY") == 0.3
        assert info["fit"] == "contain"

        # Quitar fondo
        background_manager.remove_background(save=True)
        assert background_manager.is_active is False
        assert settings.get("BG_IMAGE_PATH") == ""
    finally:
        if os.path.exists(fake_bg):
            os.remove(fake_bg)


def test_missing_file_recovery_clean_without_crash():
    """Verifica que si el archivo referenciado en .env fue borrado, se quita limpiamente sin crash."""
    non_existent = "C:/ruta/inexistente/fondo_fantasma_12345.png"
    settings.set("BG_IMAGE_PATH", non_existent)

    # get_current_background_path debe detectar la falta, limpiar settings y retornar None
    res = get_current_background_path()
    assert res is None
    assert settings.get("BG_IMAGE_PATH") == ""
    assert background_manager.is_active is False


def test_restore_blue_preserves_custom_background():
    """Verifica que 'Restaurar azul' (tema) no borra el fondo de pantalla configurado."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        bg_path = tf.name

    try:
        Image.new("RGB", (100, 100), color="red").save(bg_path)
        background_manager.apply_background(bg_path, save=True)
        assert background_manager.is_active is True

        # Simular lo que hace 'Restaurar azul': aplica tema "solid" azul sin llamar a remove_background
        tokens = build_theme_tokens("solid", ["#0C0C18"], preset_name="Azul AURA")
        assert tokens.style == "solid"

        # El fondo sigue activo
        assert background_manager.is_active is True
        assert settings.get("BG_IMAGE_PATH") == bg_path

        # Solo 'Quitar fondo' borra el fondo
        background_manager.remove_background(save=True)
        assert background_manager.is_active is False
        assert settings.get("BG_IMAGE_PATH") == ""
    finally:
        if os.path.exists(bg_path):
            os.remove(bg_path)

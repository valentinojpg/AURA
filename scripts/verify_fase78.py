"""
Script de Verificación Integral para Fase 78 — Fondo de Pantalla Personalizado.

Valida:
  1. Selección de PNG grande (4K 3840x2160): re-escalado proporcional exacto a 2560 px.
  2. Selección de GIF animado: metadatos con conteo de frames y fps correctos.
  3. Formatos WEBP y BMP: conversión limpia a PNG.
  4. Persistencia en settings/.env: BG_IMAGE_PATH, BG_FIT, BG_SIDEBAR_OPACITY, BG_SCRIM_OPACITY.
  5. Modo de recuperación si el archivo current.* o BG_IMAGE_PATH se borra a mano: no crashea, loguea aviso y limpia.
  6. Interacción tema: 'Restaurar azul' no borra el fondo; 'Quitar fondo' sí lo limpia.
"""

import os
import sys
import tempfile
from pathlib import Path
from PIL import Image

# Reconfigurar salida de consola a UTF-8 explícito para consolas Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import settings
from aura.ui.background_manager import (
    background_manager,
    normalize_background_image,
    get_current_background_path,
    calculate_average_luminance,
)
from aura.ui.theme import build_theme_tokens


def run_checks():
    print("🚀 Iniciando Verificación de Fase 78...")

    # Guardar estado original
    orig_bg = settings.get("BG_IMAGE_PATH", "")
    orig_fit = settings.get("BG_FIT", "cover")
    orig_side = settings.get("BG_SIDEBAR_OPACITY", "0.0")
    orig_scrim = settings.get("BG_SCRIM_OPACITY", "0.25")

    try:
        # 1. PNG Grande (Wallpaper 4K)
        print("\n[1/7] Probando wallpaper 4K (3840x2160)...")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            p_4k = tf.name
        img_4k = Image.new("RGB", (3840, 2160), color=(30, 60, 120))
        img_4k.save(p_4k, format="PNG")

        meta_4k = normalize_background_image(p_4k)
        assert meta_4k["width"] == 2560, f"Esperado ancho 2560, obtenido {meta_4k['width']}"
        assert meta_4k["height"] == 1440, f"Esperado alto 1440, obtenido {meta_4k['height']}"
        assert Path(meta_4k["target_file"]).exists()
        print(f"  ✅ 4K re-escalado exitosamente a: {meta_4k['width']}x{meta_4k['height']}")
        os.remove(p_4k)

        # 2. GIF Animado
        print("\n[2/7] Probando GIF animado con 4 frames y 10 FPS...")
        with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as tf:
            p_gif = tf.name
        frames = [Image.new("RGB", (300, 200), c) for c in ["red", "yellow", "green", "blue"]]
        frames[0].save(p_gif, save_all=True, append_images=frames[1:], duration=[100, 100, 100, 100], loop=0)

        meta_gif = normalize_background_image(p_gif)
        assert meta_gif["is_gif"] is True
        assert meta_gif["frames_count"] == 4
        assert meta_gif["fps"] == 10.0
        assert Path(meta_gif["target_file"]).exists()
        assert Path(meta_gif["frames_cache_dir"]).exists()
        print(f"  ✅ GIF normalizado: {meta_gif['frames_count']} frames, {meta_gif['fps']} fps, frames extraídos")
        os.remove(p_gif)

        # 3. WEBP y BMP
        print("\n[3/7] Probando conversión de WEBP y BMP a PNG...")
        with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as tf_w, \
             tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as tf_b:
            p_webp = tf_w.name
            p_bmp = tf_b.name
        Image.new("RGB", (200, 200), "purple").save(p_webp, format="WEBP")
        Image.new("RGB", (200, 200), "orange").save(p_bmp, format="BMP")

        m_w = normalize_background_image(p_webp)
        m_b = normalize_background_image(p_bmp)
        assert m_w["ext"] == ".png"
        assert m_b["ext"] == ".png"
        print("  ✅ WEBP y BMP convertidos a PNG correctamente")
        os.remove(p_webp)
        os.remove(p_bmp)

        # 4. Persistencia en Settings (.env)
        print("\n[4/7] Probando persistencia de variables BG_*...")
        background_manager.apply_background(
            image_path=meta_4k["target_file"],
            fit="stretch",
            sidebar_opacity=0.6,
            scrim_opacity=0.5,
            save=True,
        )
        assert settings.get("BG_FIT") == "stretch"
        assert settings.get_float("BG_SIDEBAR_OPACITY") == 0.6
        assert settings.get_float("BG_SCRIM_OPACITY") == 0.5
        assert background_manager.is_active is True
        print(f"  ✅ Persistencia verificada: fit={settings.get('BG_FIT')}, sidebar={settings.get('BG_SIDEBAR_OPACITY')}, scrim={settings.get('BG_SCRIM_OPACITY')}")

        # 5. Luminancia y verificación de contraste
        print("\n[5/7] Probando luminancia con imagen clara...")
        bright_img = Image.new("RGB", (100, 100), (250, 250, 250))
        lum = calculate_average_luminance(bright_img)
        assert lum >= 0.9, f"Luminancia esperada >= 0.9, obtenida {lum}"
        print(f"  ✅ Luminancia de imagen clara calculada: {lum} (activa sugerencia de velado si scrim < 0.15)")

        # 6. Quitar fondo vs Restaurar Azul
        print("\n[6/7] Probando interacción con temas y 'Restaurar azul'...")
        # Simular 'Restaurar azul'
        _ = build_theme_tokens("solid", ["#0C0C18"], preset_name="Azul AURA")
        assert background_manager.is_active is True, "Restaurar azul NO debe tocar el fondo"
        print("  ✅ 'Restaurar azul' no borró el fondo activo")

        # Quitar fondo
        background_manager.remove_background(save=True)
        assert background_manager.is_active is False
        assert settings.get("BG_IMAGE_PATH") == ""
        print("  ✅ 'Quitar fondo' limpió el fondo correctamente")

        # 7. Borrado manual de current.*
        print("\n[7/7] Probando arranque limpio ante archivo borrado a mano...")
        dummy_path = "assets/backgrounds/non_existent_file_test.png"
        settings.set("BG_IMAGE_PATH", dummy_path)
        resolved = get_current_background_path()
        assert resolved is None
        assert settings.get("BG_IMAGE_PATH") == ""
        print("  ✅ Detección de archivo inexistente: limpiado sin crash ni excepciones")

        print("\n🎉 ¡TODAS LAS 7 COMPROBACIONES DE LA FASE 78 PASARON EXITOSAMENTE!")
    finally:
        # Restaurar configuración original
        background_manager.shutdown()
        settings.set("BG_IMAGE_PATH", orig_bg)
        settings.set("BG_FIT", orig_fit)
        settings.set("BG_SIDEBAR_OPACITY", orig_side)
        settings.set("BG_SCRIM_OPACITY", orig_scrim)


if __name__ == "__main__":
    run_checks()

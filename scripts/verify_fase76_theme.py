"""
AURA ORION — Script de Verificación en Vivo Fase 76: Sistema de Temas Visuales

Ejecuta las pruebas obligatorias del sistema de temas:
  1. Aplicación de los 12 estilos visuales con verificación de contraste WCAG
  2. Generación y comprobación de caché persistente de texturas (dithering y halftone)
  3. Verificación de configuración multidireccional orgánica para Mesh
  4. Verificación de sombras y resplandor difuso para Bleeding y Neón
  5. Derivación algorítmica de paletas (mono, analogous, poly con tríada/complementario)
  6. Blindaje ante códigos HEX inválidos y persistencia de tema configurado
  7. Restauración fiel al tema original Azul AURA
  8. Medición de rendimiento en conmutación de estilos (< 1.0 s)
"""

import os
import sys
import time
from pathlib import Path

# Asegurar raíz en PYTHONPATH y salida UTF-8
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from aura.ui.color_utils import (
    contrast_ratio,
    derive_analogous_palette,
    derive_mono_palette,
    derive_poly_palette,
    is_valid_hex,
    relative_luminance,
)
from aura.ui.theme_textures import (
    generate_dithering_tile,
    generate_halftone_tile,
    get_texture_cache_dir,
)
from aura.ui.theme import (
    THEME_PRESETS,
    apply_theme,
    build_theme_tokens,
    theme_manager,
)
from config.settings import settings


def run_verification():
    print("=" * 68)
    print("  AURA ORION — VERIFICACIÓN EN VIVO FASE 76: SISTEMA DE TEMAS")
    print("=" * 68)

    cache_dir = get_texture_cache_dir()
    print(f"Directorio de caché de texturas: {cache_dir} (Existe: {cache_dir.exists()})")

    # ── Test 1: Aplicación secuencial de los 12 estilos y legibilidad WCAG
    print("\n[1] Verificación de los 12 Estilos Obligatorios y Contraste WCAG:")
    styles_to_test = [
        ("solid", ["#0C0C18"]),
        ("gradient", ["#FF6B35", "#FF1493"]),
        ("neon", ["#0A0A12", "#00FFA3"]),
        ("duotone", ["#FF4E50", "#191414"]),
        ("gradientmap", ["#0B1D3A", "#00B4D8", "#90E0EF"]),
        ("mesh", ["#4158D0", "#C850C0", "#FFCC70", "#0093E9"]),
        ("bleeding", ["#121224", "#8A2BE2"]),
        ("mono", ["#1E3A8A"]),
        ("analogous", ["#D97706"]),
        ("poly", ["#EC4899"]),
        ("dithering", ["#2D3748", "#E2E8F0"]),
        ("halftone", ["#F3F4F6", "#1F2937"]),
    ]

    for style_name, colors in styles_to_test:
        tokens = build_theme_tokens(style_name, colors, scheme="triada")
        c_user = contrast_ratio(tokens.user_bubble_bg, tokens.user_bubble_text)
        c_asst = contrast_ratio(tokens.assistant_bubble_bg, tokens.assistant_bubble_text)
        assert c_user >= 3.0, f"Fallo de contraste usuario en estilo {style_name}: {c_user:.2f}"
        assert c_asst >= 3.0, f"Fallo de contraste asistente en estilo {style_name}: {c_asst:.2f}"
        print(f"  • {style_name.ljust(12)} -> User: {tokens.user_bubble_bg} (CR={c_user:.1f}:1), Asst: {tokens.assistant_bubble_bg} (CR={c_asst:.1f}:1) ✅")

    print("  ✅ Los 12 estilos generan tokens válidos con contraste seguro (sin claro sobre claro).")

    # ── Test 2: Dithering y Halftone con caché en disco
    print("\n[2] Comprobación de Texturas y Caché (Dithering & Halftone):")
    d_path1 = generate_dithering_tile("#2D3748", "#E2E8F0", size=128)
    assert os.path.exists(d_path1), "No se generó el tile de dithering"
    mtime_d1 = os.path.getmtime(d_path1)

    d_path2 = generate_dithering_tile("#2D3748", "#E2E8F0", size=128)
    assert d_path1 == d_path2
    assert os.path.getmtime(d_path2) == mtime_d1, "El tile de dithering se regeneró innecesariamente"
    print(f"  • Dithering tile: {Path(d_path1).name} (Caché hit verificado) ✅")

    h_path1 = generate_halftone_tile("#F3F4F6", "#1F2937", size=128)
    assert os.path.exists(h_path1), "No se generó el tile de halftone"
    mtime_h1 = os.path.getmtime(h_path1)

    h_path2 = generate_halftone_tile("#F3F4F6", "#1F2937", size=128)
    assert h_path1 == h_path2
    assert os.path.getmtime(h_path2) == mtime_h1, "El tile de halftone se regeneró innecesariamente"
    print(f"  • Halftone tile:  {Path(h_path1).name} (Caché hit verificado) ✅")

    # ── Test 3: Mesh degradado multidireccional fluido
    print("\n[3] Verificación de Malla Líquida (Mesh Fluid Gradient):")
    mesh_tokens = build_theme_tokens("mesh", ["#4158D0", "#C850C0", "#FFCC70", "#0093E9"])
    assert mesh_tokens.is_mesh is True
    assert len(mesh_tokens.mesh_colors) == 4
    print(f"  • Mesh configurado con 4 centros radiales: {mesh_tokens.mesh_colors} ✅")

    # ── Test 4: Sombras difusas y Glow (Bleeding y Neón)
    print("\n[4] Verificación de Sombras y Efectos (Bleeding & Neón):")
    neon_toks = build_theme_tokens("neon", ["#0A0A12", "#00FFA3"])
    assert neon_toks.bubble_shadow is not None
    assert neon_toks.button_shadow is not None
    print(f"  • Neon glow: blur_radius={neon_toks.bubble_shadow[0].blur_radius}px ✅")

    bleed_toks = build_theme_tokens("bleeding", ["#121224", "#8A2BE2"])
    assert bleed_toks.bubble_shadow is not None
    assert bleed_toks.button_shadow is not None
    print(f"  • Bleeding shadow: blur_radius={bleed_toks.bubble_shadow[0].blur_radius}px ✅")

    # ── Test 5: Paletas derivadas automáticas (Mono, Analogous, Poly)
    print("\n[5] Verificación de Paletas Derivadas Automáticas:")
    mono_pal = derive_mono_palette("#1E3A8A")
    assert len(mono_pal) == 6
    assert relative_luminance(mono_pal[0]) < relative_luminance(mono_pal[-1])
    print(f"  • Monocromático (6 tonos HSL): {mono_pal[0]} ... {mono_pal[-1]} ✅")

    ana_pal = derive_analogous_palette("#D97706")
    assert len(ana_pal) == 4
    print(f"  • Análogo (4 tonos ±25°): {ana_pal} ✅")

    poly_tri = derive_poly_palette("#EC4899", scheme="triada")
    assert len(poly_tri) == 3
    poly_comp = derive_poly_palette("#EC4899", scheme="complementario")
    assert len(poly_comp) == 2
    poly_split = derive_poly_palette("#EC4899", scheme="complementario dividido")
    assert len(poly_split) == 3
    print("  • Policromático (Tríada/Complementario/Dividido verificados) ✅")

    # ── Test 6: Rechazo de HEX inválido y persistencia
    print("\n[6] Blindaje ante HEX Inválido y Persistencia:")
    assert is_valid_hex("#123456") is True
    assert is_valid_hex("#XYZ123") is False
    assert is_valid_hex("azul") is False

    apply_theme("neon", ["#0A0A12", "#00FFA3"], preset_name="Cyberpunk", save=True)
    assert settings.get("THEME_STYLE") == "neon"
    assert settings.get("THEME_COLOR_2") == "#00FFA3"
    print("  • Tema guardado y recargado con éxito desde configuración ✅")

    # ── Test 7: Restauración a Azul AURA
    print("\n[7] Restauración al Tema Original (Azul AURA):")
    apply_theme("solid", ["#0C0C18"], preset_name="Azul AURA", save=True)
    restored = theme_manager.load_from_settings()
    assert restored.style == "solid"
    assert restored.colors[0] == "#0C0C18"
    assert settings.get("THEME_STYLE") == "solid"
    print(f"  • Restaurado fielmente a estilo '{restored.style}' con color {restored.colors[0]} ✅")

    # ── Test 8: Medición de rendimiento en conmutación
    print("\n[8] Medición de Rendimiento en Conmutación de Estilos:")
    t0 = time.perf_counter()
    for name, p_info in THEME_PRESETS.items():
        apply_theme(
            p_info["style"],
            p_info["colors"],
            scheme=p_info.get("scheme", "triada"),
            preset_name=name,
            save=False,
        )
    total_time = (time.perf_counter() - t0) * 1000
    avg_time = total_time / len(THEME_PRESETS)
    print(f"  • 12 temas generados y aplicados en {total_time:.2f} ms ({avg_time:.2f} ms/tema) ✅")
    assert avg_time < 200.0, f"Conmutación lenta: {avg_time:.2f} ms por tema"

    print("=" * 68)
    print("  🎉 TODAS LAS PRUEBAS EN VIVO DE FASE 76 PASARON EXITOSAMENTE")
    print("=" * 68)


if __name__ == "__main__":
    run_verification()

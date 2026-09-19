"""
AURA — Gestor de Fondos de Pantalla Personalizados (Fase 78)

Gestiona la normalización con Pillow, caché en disco, persistencia de variables
BG_*, reproducción de GIFs (nativo y fallback de frames con tope a 20 FPS),
cálculo de luminancia WCAG para sugerencia de contraste, y actualización de
transparencias en caliente para toda la interfaz gráfica de AURA.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import threading
from pathlib import Path
from typing import Any, Callable, Optional
from PIL import Image

from config.settings import settings, ROOT_DIR
from utils.logger import get_logger

_logger = get_logger("aura.ui.background")

# ──────────────────────────────────────────────
# Constantes y Rutas
# ──────────────────────────────────────────────
BACKGROUNDS_DIR = ROOT_DIR / "assets" / "backgrounds"
CACHE_DIR = BACKGROUNDS_DIR / "cache"
QA_DIR = CACHE_DIR / "qa"
METADATA_FILE = BACKGROUNDS_DIR / "current_meta.json"

MAX_WIDTH = 2560
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB
MAX_FPS = 20.0
MIN_FRAME_DURATION_MS = int(1000.0 / MAX_FPS)  # 50 ms (tope 20 fps)

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _ensure_dirs() -> None:
    """Asegura que los directorios de almacenamiento, caché y QA existan."""
    BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    QA_DIR.mkdir(parents=True, exist_ok=True)


def compute_file_hash(path: Path | str) -> str:
    """Calcula el hash SHA-256 de un archivo en bloques."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()[:16]


def calculate_average_luminance(im: Image.Image) -> float:
    """
    Calcula la luminancia relativa WCAG 2.1 promedio (0.0 a 1.0) de una imagen.
    L = 0.2126 * R + 0.7152 * G + 0.0722 * B
    Utiliza muestreo a 100x100 para eficiencia instantánea incluso con imágenes 4K.
    """
    try:
        thumb = im.copy().convert("RGB")
        thumb.thumbnail((100, 100), Image.Resampling.BILINEAR)
        if hasattr(thumb, "get_flattened_data"):
            pixels = thumb.get_flattened_data()
        else:
            pixels = list(thumb.getdata())
        if not pixels:
            return 0.0
        total_lum = sum(
            0.2126 * (r / 255.0) + 0.7152 * (g / 255.0) + 0.0722 * (b / 255.0)
            for r, g, b in pixels
        )
        return round(total_lum / len(pixels), 3)
    except Exception as e:
        _logger.debug("Error calculando luminancia de imagen: %s", e)
        return 0.0


def _extract_qa_samples(gif_path: Path, qa_dir: Path) -> list[str]:
    """
    Extrae 3 frames de muestra a PNG en assets/backgrounds/cache/qa/ para inspección.
    Toma frame inicial (0), intermedio (n // 2) y final (n - 1).
    """
    qa_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    try:
        with Image.open(gif_path) as check_im:
            n = getattr(check_im, "n_frames", 1)
            if n <= 1:
                indices = [0]
            elif n == 2:
                indices = [0, 1]
            else:
                indices = [0, n // 2, n - 1]

            for s_idx, f_idx in enumerate(indices):
                check_im.seek(f_idx)
                out_png = qa_dir / f"qa_sample_{s_idx + 1}_frame_{f_idx:04d}.png"
                check_im.convert("RGBA").save(out_png, format="PNG")
                saved.append(str(out_png))
    except Exception as ex:
        _logger.debug("Error extrayendo frames de muestra QA: %s", ex)
    return saved


def _verify_and_qa_gif(
    gif_path: Path,
    expected_frames_count: int,
    original_durations: list[int],
    qa_dir: Path,
) -> bool:
    """
    Verificación automática post-normalización (Fase 78 Ronda 5):
      1. Reabre el GIF generado con Pillow.
      2. Cuenta frames: si el original tenía > 1 frame y el reabierto tiene <= 1, falla.
      3. Compara duraciones contra el original con tolerancia del 10%.
      4. Si todas las duraciones están en 0 o vacías, falla.
      5. Extrae 3 frames de muestra a PNG en assets/backgrounds/cache/qa/ para inspección.
    Retorna True si es válido; False si se debe abortar re-codificación y copiar el original.
    """
    try:
        with Image.open(gif_path) as check_im:
            n_frames = getattr(check_im, "n_frames", 1)
            if expected_frames_count > 1 and n_frames <= 1:
                _logger.warning(
                    "Verificación QA falló: reabierto tiene %d frame (se esperaban %d).",
                    n_frames,
                    expected_frames_count,
                )
                return False

            durations: list[int] = []
            for idx in range(n_frames):
                check_im.seek(idx)
                d = check_im.info.get("duration", 0)
                durations.append(int(d) if d else 0)

            if all(d <= 0 for d in durations):
                _logger.warning("Verificación QA falló: todas las duraciones del GIF reabierto están en 0.")
                return False

            if original_durations:
                orig_avg = sum(original_durations) / len(original_durations)
                gen_avg = sum(durations) / len(durations)
                if orig_avg > 0:
                    diff_ratio = abs(gen_avg - orig_avg) / orig_avg
                    if diff_ratio > 0.10:
                        _logger.warning(
                            "Verificación QA falló: duración media difiere más del 10%% (orig=%.1f ms, gen=%.1f ms, diff=%.1f%%).",
                            orig_avg,
                            gen_avg,
                            diff_ratio * 100,
                        )
                        return False

        _extract_qa_samples(gif_path, qa_dir)
        return True
    except Exception as ex:
        _logger.warning("Error durante verificación post-normalización de GIF: %s", ex)
        return False


def normalize_background_image(source_path: str | Path) -> dict[str, Any]:
    """
    Normaliza una imagen o GIF con Pillow según las reglas de la Fase 78 (Ronda 5):
      - Extensiones permitidas: png, jpg, jpeg, gif, webp, bmp.
      - Formatos no soportados por renderer (webp, bmp) -> convertir a PNG.
      - Regla GIF 1: Si ancho <= 2560 px y peso <= 20 MB, COPIARLO TAL CUAL sin re-codificar.
      - Regla GIF 2: Re-codificación solo cuando sea inevitable (> 2560 px o > 20 MB):
        preservar duraciones por frame originales, disposal method, loop y cuantizar con FASTOCTREE / ADAPTIVE.
      - Regla GIF 3: Verificación automática post-normalización (frames, duraciones != 0, tolerancia 10%)
        y extracción de 3 frames de muestra a PNG en assets/backgrounds/cache/qa/.
      - Genera preview estático de frame 0 en assets/backgrounds/cache/preview_<hash>.png.
      - Extrae frames de fallback en assets/backgrounds/cache/frames_<hash>/ si es GIF.
      - Guarda assets/backgrounds/current_meta.json.
    """
    _ensure_dirs()
    src = Path(source_path).expanduser().resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"El archivo origen no existe: {src}")

    orig_ext = src.suffix.lower()
    if orig_ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Formato no soportado '{orig_ext}'. Formatos válidos: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    file_hash = compute_file_hash(src)
    file_size = src.stat().st_size
    orig_name = src.name

    with Image.open(src) as im:
        orig_width, orig_height = im.size
        is_animated = bool(getattr(im, "is_animated", False) and getattr(im, "n_frames", 1) > 1)

        needs_resize = bool(orig_width > MAX_WIDTH or file_size > MAX_FILE_SIZE_BYTES)
        if orig_width > MAX_WIDTH:
            scale = MAX_WIDTH / float(orig_width)
        elif file_size > MAX_FILE_SIZE_BYTES:
            scale = 0.85
        else:
            scale = 1.0

        target_width = max(1, int(round(orig_width * scale)))
        target_height = max(1, int(round(orig_height * scale)))

        # ── CASO A: GIF ANIMADO ───────────────────────────────────
        if is_animated or orig_ext == ".gif":
            cached_gif_path = CACHE_DIR / f"bg_{file_hash}.gif"
            current_gif_path = BACKGROUNDS_DIR / "current.gif"
            preview_png_path = CACHE_DIR / f"preview_{file_hash}.png"
            frames_cache_dir = CACHE_DIR / f"frames_{file_hash}"
            frames_cache_dir.mkdir(parents=True, exist_ok=True)

            # Limpiar cualquier current.* previo que no sea .gif ni .json
            for old_file in BACKGROUNDS_DIR.glob("current.*"):
                if old_file.name != "current.gif" and old_file.suffix.lower() != ".json":
                    try:
                        old_file.unlink()
                    except Exception:
                        pass

            n_frames = getattr(im, "n_frames", 1)
            durations: list[int] = []
            disposals: list[int] = []
            orig_loop = im.info.get("loop", 0)

            for idx in range(n_frames):
                im.seek(idx)
                d = im.info.get("duration", 100)
                if not d or d <= 0:
                    d = 100
                durations.append(int(d))
                disp = im.info.get("disposal", getattr(im, "disposal_method", 2))
                disposals.append(int(disp) if disp is not None else 2)

            avg_duration = (sum(durations) / n_frames) if n_frames > 0 else 100.0
            fps = round(1000.0 / avg_duration, 1) if avg_duration > 0 else 10.0

            # Regla 1: si no supera umbrales, copiar tal cual sin re-codificar
            if not needs_resize:
                _logger.info(
                    "GIF dentro de umbrales (%dx%d, %d bytes <= 20 MB). Copiando TAL CUAL sin re-codificar.",
                    orig_width,
                    orig_height,
                    file_size,
                )
                shutil.copyfile(src, cached_gif_path)
                shutil.copyfile(src, current_gif_path)
                recoded = False
                final_width = orig_width
                final_height = orig_height
            else:
                # Regla 2: re-codificación inevitable con Pillow preservando animación
                _logger.info(
                    "GIF supera umbrales (%dx%d o %d bytes > 20 MB). Re-codificando con Pillow a %dx%d.",
                    orig_width,
                    orig_height,
                    file_size,
                    target_width,
                    target_height,
                )
                resized_frames: list[Image.Image] = []
                for idx in range(n_frames):
                    im.seek(idx)
                    f_rgba = im.convert("RGBA").resize((target_width, target_height), Image.Resampling.LANCZOS)
                    f_quantized = f_rgba.quantize(colors=256, method=Image.Quantize.FASTOCTREE)
                    resized_frames.append(f_quantized)

                if resized_frames:
                    resized_frames[0].save(
                        cached_gif_path,
                        save_all=True,
                        append_images=resized_frames[1:],
                        duration=durations,
                        loop=orig_loop if orig_loop is not None else 0,
                        disposal=disposals,
                    )
                    shutil.copyfile(cached_gif_path, current_gif_path)

                # Regla 3: Verificación automática post-normalización
                is_valid = _verify_and_qa_gif(
                    gif_path=cached_gif_path,
                    expected_frames_count=n_frames,
                    original_durations=durations,
                    qa_dir=QA_DIR,
                )
                if not is_valid:
                    _logger.warning(
                        "Verificación post-normalización falló. Abortando re-codificación y copiando original tal cual."
                    )
                    shutil.copyfile(src, cached_gif_path)
                    shutil.copyfile(src, current_gif_path)
                    recoded = False
                    final_width = orig_width
                    final_height = orig_height
                else:
                    recoded = True
                    final_width = target_width
                    final_height = target_height

            # Extraer 3 frames de muestra a QA para inspección visual
            _extract_qa_samples(current_gif_path, QA_DIR)

            # Generar preview estático del frame 0 (PNG) para Configuración (Regla 7)
            im.seek(0)
            frame0 = im.convert("RGBA")
            frame0.save(preview_png_path, format="PNG")

            # Extraer frames para fallback por timer
            for f_idx in range(n_frames):
                frame_out = frames_cache_dir / f"frame_{f_idx:04d}.png"
                if not frame_out.exists():
                    im.seek(f_idx)
                    im.convert("RGBA").save(frame_out, format="PNG")

            frames_meta_file = frames_cache_dir / "meta.json"
            with open(frames_meta_file, "w", encoding="utf-8") as f_meta:
                json.dump(
                    {"durations": durations, "fps": fps, "frames_count": n_frames},
                    f_meta,
                    ensure_ascii=False,
                )

            im.seek(0)
            lum = calculate_average_luminance(im)

            meta: dict[str, Any] = {
                "hash": file_hash,
                "original": orig_name,
                "original_path": str(src),
                "ext": ".gif",
                "target_file": str(current_gif_path),
                "preview_file": str(preview_png_path),
                "thumbnail_file": str(preview_png_path),
                "width": final_width,
                "height": final_height,
                "is_gif": True,
                "frames_count": n_frames,
                "fps": fps,
                "avg_duration_ms": round(avg_duration, 1),
                "luminance": lum,
                "format": "GIF",
                "frames_cache_dir": str(frames_cache_dir),
                "recoded": recoded,
            }

        # ── CASO B: IMAGEN ESTÁTICA (PNG, JPG, WEBP, BMP) ─────────
        else:
            if orig_ext in (".webp", ".bmp"):
                dest_ext = ".png"
                img_format = "PNG"
            elif orig_ext in (".jpg", ".jpeg"):
                dest_ext = ".jpg"
                img_format = "JPEG"
            else:
                dest_ext = ".png"
                img_format = "PNG"

            processed_img = im.copy()
            if needs_resize and scale < 1.0:
                if dest_ext == ".jpg" and processed_img.mode in ("RGBA", "LA", "P"):
                    processed_img = processed_img.convert("RGB")
                processed_img = processed_img.resize((target_width, target_height), Image.Resampling.LANCZOS)
            else:
                if dest_ext == ".jpg" and processed_img.mode in ("RGBA", "LA", "P"):
                    processed_img = processed_img.convert("RGB")

            cached_img_path = CACHE_DIR / f"bg_{file_hash}{dest_ext}"
            current_img_path = BACKGROUNDS_DIR / f"current{dest_ext}"

            # Limpiar cualquier current.* previo de otra extensión
            for old_file in BACKGROUNDS_DIR.glob("current.*"):
                if old_file.suffix.lower() != ".json":
                    try:
                        old_file.unlink()
                    except Exception:
                        pass

            if dest_ext == ".jpg":
                processed_img.save(cached_img_path, format="JPEG", quality=90, optimize=True)
            else:
                processed_img.save(cached_img_path, format="PNG", optimize=True)

            shutil.copyfile(cached_img_path, current_img_path)

            lum = calculate_average_luminance(processed_img)

            meta = {
                "hash": file_hash,
                "original": orig_name,
                "original_path": str(src),
                "ext": dest_ext,
                "target_file": str(current_img_path),
                "preview_file": str(current_img_path),
                "thumbnail_file": str(current_img_path),
                "width": target_width,
                "height": target_height,
                "is_gif": False,
                "frames_count": 1,
                "fps": 0.0,
                "avg_duration_ms": 0.0,
                "luminance": lum,
                "format": img_format,
                "frames_cache_dir": "",
                "recoded": needs_resize,
            }

    # Guardar metadata JSON
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    _logger.info(
        "Fondo normalizado exitosamente: '%s' -> %s (%dx%d, is_gif=%s, recoded=%s, lum=%.2f)",
        orig_name,
        meta["target_file"],
        meta["width"],
        meta["height"],
        meta["is_gif"],
        meta.get("recoded", False),
        meta["luminance"],
    )
    return meta


def load_current_metadata() -> Optional[dict[str, Any]]:
    """Carga los metadatos del fondo actual si el archivo metadata existe."""
    if not METADATA_FILE.exists():
        return None
    try:
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        _logger.debug("No se pudo leer metadata de fondo: %s", e)
        return None


def get_current_background_path() -> Optional[str]:
    """
    Retorna la ruta absoluta del fondo activo según settings.
    Si el archivo referenciado no existe en disco, loguea un aviso,
    restablece BG_IMAGE_PATH="" y retorna None.
    """
    bg_val = settings.get("BG_IMAGE_PATH", "")
    if not bg_val:
        return None
    p = Path(bg_val)
    if not p.is_absolute():
        p = ROOT_DIR / p
    if not p.exists() or not p.is_file():
        _logger.warning(
            "Fondo de pantalla referenciado en .env no existe en disco (%s). Quitando fondo limpiamente.",
            bg_val,
        )
        try:
            settings.set("BG_IMAGE_PATH", "")
        except Exception:
            pass
        return None
    return str(p)


# ──────────────────────────────────────────────
# Reproductor Fallback de Frames para GIFs
# ──────────────────────────────────────────────
class GifFramePlayer:
    """
    Reproductor fallback con Pillow y threading que cicla los frames extraídos
    de un GIF animado respetando la tasa de cuadros con tope estricto a 20 FPS.
    """

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(
        self,
        frames_dir: str | Path,
        durations: list[int],
        on_frame: Callable[[str], None],
    ) -> None:
        """Inicia el ciclo de animación en segundo plano."""
        self.stop()
        f_dir = Path(frames_dir)
        if not f_dir.exists():
            _logger.warning("Directorio de frames no existe para fallback: %s", frames_dir)
            return

        frame_files = sorted(f_dir.glob("frame_*.png"))
        if not frame_files:
            _logger.warning("No se encontraron frames en %s", frames_dir)
            return

        self._stop_event.clear()
        self._is_running = True

        def _loop() -> None:
            _logger.info("Iniciando loop de animación GifFramePlayer (%d frames)", len(frame_files))
            idx = 0
            n = len(frame_files)
            while not self._stop_event.is_set():
                frame_path = str(frame_files[idx])
                raw_dur = durations[idx] if idx < len(durations) else 100
                # Tope a 20 FPS (mínimo 50 ms por frame)
                effective_ms = max(MIN_FRAME_DURATION_MS, raw_dur)
                sleep_sec = effective_ms / 1000.0

                try:
                    on_frame(frame_path)
                except Exception as ex:
                    _logger.debug("Error en callback de frame: %s", ex)

                # Esperar con chequeo frecuente del stop_event
                if self._stop_event.wait(timeout=sleep_sec):
                    break

                idx = (idx + 1) % n
            self._is_running = False
            _logger.debug("Loop GifFramePlayer finalizado")

        self._thread = threading.Thread(target=_loop, daemon=True, name="aura-gif-frame-player")
        self._thread.start()

    def stop(self) -> None:
        """Detiene limpiamente el ciclo de animación si existe."""
        if self._is_running:
            self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=0.3)
            self._is_running = False


# ──────────────────────────────────────────────
# Coordinador Central BackgroundManager
# ──────────────────────────────────────────────
class BackgroundManager:
    """
    Gestor centralizado del fondo de pantalla de AURA.
    Coordina persistencia, normalización, control de opacidades y
    sincronización con la ventana principal.
    """

    def __init__(self) -> None:
        self._window_ref: Any = None
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._gif_player = GifFramePlayer()
        self._use_frames_fallback = False  # Por defecto nativo

    def register_window(self, window: Any) -> None:
        """Registra la ventana principal para sincronización."""
        self._window_ref = window

    def add_listener(self, cb: Callable[[dict[str, Any]], None]) -> None:
        if cb not in self._listeners:
            self._listeners.append(cb)

    def remove_listener(self, cb: Callable[[dict[str, Any]], None]) -> None:
        if cb in self._listeners:
            self._listeners.remove(cb)

    @property
    def is_active(self) -> bool:
        """Indica si hay un fondo de pantalla válido configurado."""
        return bool(get_current_background_path())

    @property
    def current_image_path(self) -> Optional[str]:
        return get_current_background_path()

    @property
    def current_fit(self) -> str:
        return settings.get("BG_FIT", "cover") or "cover"

    @property
    def current_sidebar_opacity(self) -> float:
        return settings.get_float("BG_SIDEBAR_OPACITY", 0.0)

    @property
    def current_scrim_opacity(self) -> float:
        return settings.get_float("BG_SCRIM_OPACITY", 0.25)

    @property
    def metadata(self) -> Optional[dict[str, Any]]:
        return load_current_metadata()

    @property
    def current_gif_mode(self) -> str:
        """Modo de animación para GIFs: 'native' (default) o 'frames' (fallback timer)."""
        mode = settings.get("BG_GIF_MODE", "native") or "native"
        clean = mode.strip().lower()
        return "frames" if clean == "frames" else "native"

    @property
    def current_thumbnail_path(self) -> Optional[str]:
        """
        Retorna la ruta al thumbnail/preview ESTÁTICO en formato PNG/JPG (frame 0 para GIFs).
        Garantiza que la vista de Configuración nunca anime ni parpadee.
        """
        meta = self.metadata
        if meta:
            prev = meta.get("preview_file") or meta.get("thumbnail_file")
            if prev and Path(prev).exists():
                return str(prev)
            frames_cache = meta.get("frames_cache_dir")
            if frames_cache:
                f0 = Path(frames_cache) / "frame_0000.png"
                if f0.exists():
                    return str(f0)

        bg_path = self.current_image_path
        if not bg_path:
            return None

        p = Path(bg_path)
        if not p.exists():
            return None

        if p.suffix.lower() != ".gif":
            return str(p)

        try:
            h = meta.get("hash") if meta else compute_file_hash(p)
            prev_path = CACHE_DIR / f"preview_{h}.png"
            if not prev_path.exists():
                with Image.open(p) as g_im:
                    g_im.seek(0)
                    g_im.convert("RGBA").save(prev_path, format="PNG")
            return str(prev_path)
        except Exception as ex:
            _logger.debug("Error obteniendo preview estático de GIF: %s", ex)
            return None

    def apply_background(
        self,
        image_path: str,
        fit: str = "cover",
        sidebar_opacity: float = 0.0,
        scrim_opacity: float = 0.25,
        save: bool = True,
        use_frames_fallback: Optional[bool] = None,
        gif_mode: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Aplica un nuevo fondo de pantalla, actualiza variables .env y
        notifica a la interfaz gráfica.
        """
        self._gif_player.stop()

        if gif_mode is not None:
            clean_mode = "frames" if gif_mode.strip().lower() == "frames" else "native"
            if save:
                try:
                    settings.set("BG_GIF_MODE", clean_mode)
                except Exception:
                    pass
            effective_frames = (clean_mode == "frames")
        elif use_frames_fallback is not None:
            effective_frames = bool(use_frames_fallback)
            if save:
                try:
                    settings.set("BG_GIF_MODE", "frames" if use_frames_fallback else "native")
                except Exception:
                    pass
        else:
            effective_frames = (self.current_gif_mode == "frames")

        self._use_frames_fallback = effective_frames

        fit_clean = fit.strip().lower() if fit else "cover"
        if fit_clean not in ("cover", "contain", "stretch"):
            fit_clean = "cover"

        side_op = max(0.0, min(1.0, float(sidebar_opacity)))
        scrim_op = max(0.0, min(1.0, float(scrim_opacity)))

        if save:
            try:
                settings.set("BG_IMAGE_PATH", str(image_path))
                settings.set("BG_FIT", fit_clean)
                settings.set("BG_SIDEBAR_OPACITY", str(round(side_op, 2)))
                settings.set("BG_SCRIM_OPACITY", str(round(scrim_op, 2)))
            except Exception as ex:
                _logger.warning("No se pudo persistir configuración de fondo: %s", ex)

        meta = load_current_metadata() or {}
        is_gif = bool(meta.get("is_gif", False) or str(image_path).lower().endswith(".gif"))

        # Notificar a la ventana principal
        if self._window_ref and hasattr(self._window_ref, "apply_background_to_ui"):
            try:
                self._window_ref.apply_background_to_ui(
                    bg_path=str(image_path),
                    fit=fit_clean,
                    sidebar_opacity=side_op,
                    scrim_opacity=scrim_op,
                )
            except Exception as ex:
                _logger.debug("Error aplicando fondo a ventana: %s", ex)

        # Determinar camino de animación para GIF
        if is_gif:
            if effective_frames and meta.get("frames_cache_dir"):
                _logger.info("BG_GIF_MODE=frames: iniciando ciclador de frames por timer (tope 20 FPS)")
                durations = []
                frames_meta_file = Path(meta["frames_cache_dir"]) / "meta.json"
                if frames_meta_file.exists():
                    try:
                        with open(frames_meta_file, "r", encoding="utf-8") as f:
                            durations = json.load(f).get("durations", [])
                    except Exception:
                        pass

                def _on_frame_update(frame_path: str) -> None:
                    if self._window_ref and hasattr(self._window_ref, "update_background_frame"):
                        self._window_ref.update_background_frame(frame_path)

                self._gif_player.start(meta["frames_cache_dir"], durations, _on_frame_update)
            else:
                _logger.info("BG_GIF_MODE=native: animación de GIF nativa por Flutter activada")

        info = {
            "path": str(image_path),
            "fit": fit_clean,
            "sidebar_opacity": side_op,
            "scrim_opacity": scrim_op,
            "is_gif": is_gif,
            "metadata": meta,
        }

        for cb in self._listeners:
            try:
                cb(info)
            except Exception as ex:
                _logger.debug("Error en listener de fondo: %s", ex)

        return info

    def sync_gif_mode(self) -> None:
        """
        Sincroniza el modo de animación del GIF según settings.BG_GIF_MODE.
        Si es 'frames', activa el timer apuntando al Image del fondo.
        Si es 'native', detiene el timer y asegura que el Image del fondo apunte al GIF.
        """
        if not self.is_active:
            self._gif_player.stop()
            return

        bg_path = self.current_image_path
        if not bg_path:
            self._gif_player.stop()
            return

        meta = self.metadata or {}
        is_gif = bool(bg_path.lower().endswith(".gif") or (meta.get("is_gif") and meta.get("target_file") == bg_path))
        if not is_gif:
            self._gif_player.stop()
            return

        mode = self.current_gif_mode
        if mode == "frames":
            frames_dir = meta.get("frames_cache_dir")
            if frames_dir and Path(frames_dir).exists():
                durations = []
                frames_meta = Path(frames_dir) / "meta.json"
                if frames_meta.exists():
                    try:
                        with open(frames_meta, "r", encoding="utf-8") as f:
                            durations = json.load(f).get("durations", [])
                    except Exception:
                        pass

                def _on_frame_update(frame_path: str) -> None:
                    if self._window_ref and hasattr(self._window_ref, "update_background_frame"):
                        self._window_ref.update_background_frame(frame_path)

                if not self._gif_player.is_running:
                    _logger.info("BG_GIF_MODE=frames: iniciando ciclador de frames por timer (tope 20 FPS)")
                    self._gif_player.start(frames_dir, durations, _on_frame_update)
        else:
            if self._gif_player.is_running:
                _logger.info("BG_GIF_MODE=native: volviendo a camino NATIVO Flutter")
                self._gif_player.stop()
            if self._window_ref and hasattr(self._window_ref, "_bg_image") and self._window_ref._bg_image:
                if bg_path and self._window_ref._bg_image.src != bg_path:
                    self._window_ref._bg_image.src = bg_path
                    try:
                        self._window_ref._bg_image.update()
                    except Exception:
                        pass

    def set_gif_mode(self, mode: str, save: bool = True) -> None:
        """Configura el modo de animación de GIF ('native' | 'frames') y sincroniza en caliente."""
        clean = "frames" if str(mode).strip().lower() == "frames" else "native"
        if save:
            try:
                settings.set("BG_GIF_MODE", clean)
            except Exception as ex:
                _logger.warning("No se pudo guardar BG_GIF_MODE: %s", ex)
        self.sync_gif_mode()

    def remove_background(self, save: bool = True) -> None:
        """Quita el fondo de pantalla activo y regresa al color/tema original."""
        self._gif_player.stop()

        if save:
            try:
                settings.set("BG_IMAGE_PATH", "")
            except Exception as ex:
                _logger.warning("No se pudo limpiar BG_IMAGE_PATH en settings: %s", ex)

        if self._window_ref and hasattr(self._window_ref, "apply_background_to_ui"):
            try:
                self._window_ref.apply_background_to_ui(
                    bg_path=None,
                    fit=self.current_fit,
                    sidebar_opacity=self.current_sidebar_opacity,
                    scrim_opacity=self.current_scrim_opacity,
                )
            except Exception as ex:
                _logger.debug("Error quitando fondo de ventana: %s", ex)

        info = {"path": None, "active": False}
        for cb in self._listeners:
            try:
                cb(info)
            except Exception as ex:
                _logger.debug("Error en listener al quitar fondo: %s", ex)

        _logger.info("Fondo de pantalla quitado. Restaurado tema de color estándar.")

    def update_sidebar_opacity(self, opacity: float, save: bool = True) -> None:
        """Actualiza la opacidad de la barra lateral en caliente."""
        val = max(0.0, min(1.0, float(opacity)))
        if save:
            try:
                settings.set("BG_SIDEBAR_OPACITY", str(round(val, 2)))
            except Exception:
                pass
        if self._window_ref and hasattr(self._window_ref, "update_sidebar_opacity_in_ui"):
            self._window_ref.update_sidebar_opacity_in_ui(val)

    def update_scrim_opacity(self, opacity: float, save: bool = True) -> None:
        """Actualiza la opacidad del velado (scrim) en caliente."""
        val = max(0.0, min(1.0, float(opacity)))
        if save:
            try:
                settings.set("BG_SCRIM_OPACITY", str(round(val, 2)))
            except Exception:
                pass
        if self._window_ref and hasattr(self._window_ref, "update_scrim_opacity_in_ui"):
            self._window_ref.update_scrim_opacity_in_ui(val)

    def update_fit(self, fit: str, save: bool = True) -> None:
        """Actualiza el modo de ajuste (cover/contain/stretch) en caliente."""
        f = fit.strip().lower() if fit else "cover"
        if save:
            try:
                settings.set("BG_FIT", f)
            except Exception:
                pass
        if self._window_ref and hasattr(self._window_ref, "update_fit_in_ui"):
            self._window_ref.update_fit_in_ui(f)

    def shutdown(self) -> None:
        """Detiene cualquier proceso en segundo plano (timer GIF) al cerrar la app."""
        self._gif_player.stop()


# Singleton global de Fondo de Pantalla
background_manager = BackgroundManager()

"""
AURA — Motor de Conversión de Voz RVC (Retrieval-based Voice Conversion)

Transforma un audio fuente WAV generado por un TTS base aplicando los timbres
y características del modelo entrenado (ej: aura.pth y aura.index).

Características:
- Detección dinámica de modelos en models/rvc/<voz>/.
- Selección de hardware: auto (detecta CUDA o conmuta a CPU).
- Caché del modelo cargado en memoria para evitar re-cargas lentas.
- Manejo robusto de errores con retorno controlado para fallback.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

from config.settings import settings
from utils.logger import get_logger

_logger = get_logger("aura.voice.tts.rvc")

# Asegurar que env/Scripts esté en PATH
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_SCRIPTS = str(_ROOT_DIR / "env" / "Scripts")
if _ENV_SCRIPTS not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _ENV_SCRIPTS + os.pathsep + os.environ.get("PATH", "")


def get_available_rvc_voices(models_root: Optional[str | Path] = None) -> dict[str, dict[str, Optional[str]]]:
    """
    Escanea models/rvc/ y retorna un diccionario con las voces disponibles:
    {
        'aura': {
            'pth': '.../models/rvc/aura/aura.pth',
            'index': '.../models/rvc/aura/aura.index',
        }
    }
    """
    root = Path(models_root or (_ROOT_DIR / "models" / "rvc")).resolve()
    voices: dict[str, dict[str, Optional[str]]] = {}

    if not root.is_dir():
        return voices

    for child in root.iterdir():
        if child.is_dir():
            voice_name = child.name
            pth_files = list(child.glob("*.pth"))
            if not pth_files:
                continue

            pth_file = str(pth_files[0])
            index_files = list(child.glob("*.index"))
            index_file = str(index_files[0]) if index_files else None

            voices[voice_name] = {
                "pth": pth_file,
                "index": index_file,
            }

    # También verificar si hay un .pth suelto directamente en models/rvc/
    for pth in root.glob("*.pth"):
        voice_name = pth.stem
        if voice_name not in voices:
            idx = root / f"{voice_name}.index"
            voices[voice_name] = {
                "pth": str(pth),
                "index": str(idx) if idx.is_file() else None,
            }

    return voices


def detect_rvc_device(preferred_device: Optional[str] = None) -> str:
    """
    Detecta y retorna el identificador de dispositivo para RVC.
    'auto' -> 'cuda:0' si torch.cuda.is_available(), caso contrario 'cpu:0'.
    """
    pref = (preferred_device or settings.get("RVC_DEVICE", "auto") or "auto").lower().strip()
    if pref in ("cuda", "cuda:0", "gpu"):
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda:0"
        except Exception:
            pass
        _logger.warning("RVC: CUDA solicitado pero no disponible. Usando CPU.")
        return "cpu:0"

    if pref in ("cpu", "cpu:0"):
        return "cpu:0"

    # Modo auto
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda:0"
    except Exception:
        pass
    return "cpu:0"


class RVCConverter:
    """
    Controlador de inferencia RVC con gestión de memoria y reintentos.
    """

    _instance: Optional[RVCConverter] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(RVCConverter, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._rvc_infer = None
        self._current_model_name: Optional[str] = None
        self._current_device: str = detect_rvc_device()
        self._load_lock = threading.RLock()
        self._initialized = True
        _logger.info(f"RVCConverter instanciado (dispositivo: {self._current_device})")

    @property
    def device_info(self) -> str:
        dev = self._current_device
        return "GPU (CUDA)" if "cuda" in dev else "CPU"

    def is_available(self) -> bool:
        """Verifica si rvc_python y fairseq están instalados y hay al menos un modelo .pth."""
        import importlib.util
        if not (importlib.util.find_spec("rvc_python") and importlib.util.find_spec("fairseq")):
            return False
        voices = get_available_rvc_voices()
        return len(voices) > 0

    def list_voices(self) -> list[str]:
        return sorted(list(get_available_rvc_voices().keys()))

    def _get_engine(self):
        if self._rvc_infer is not None:
            return self._rvc_infer

        with self._load_lock:
            if self._rvc_infer is not None:
                return self._rvc_infer

            from rvc_python.infer import RVCInference

            models_root = str(_ROOT_DIR / "models" / "rvc")
            self._current_device = detect_rvc_device()
            _logger.info(f"Inicializando RVCInference con device={self._current_device}...")

            self._rvc_infer = RVCInference(
                models_dir=models_root,
                device=self._current_device,
            )
            return self._rvc_infer

    def load_voice(self, voice_name: str = "aura") -> tuple[bool, str]:
        """Carga el modelo de la voz seleccionada en memoria."""
        with self._load_lock:
            voices = get_available_rvc_voices()
            if voice_name not in voices:
                return False, f"Voz '{voice_name}' no encontrada en models/rvc/"

            voice_data = voices[voice_name]
            pth_path = voice_data["pth"]
            index_path = voice_data["index"] or ""

            if not pth_path or not os.path.isfile(pth_path):
                return False, f"Archivo .pth de la voz '{voice_name}' no encontrado: {pth_path}"

            if self._current_model_name == voice_name and self._rvc_infer is not None:
                return True, ""  # Ya está cargado

            try:
                engine = self._get_engine()
                _logger.info(f"Cargando modelo RVC: {pth_path} (index: {index_path})...")
                engine.load_model(pth_path, version="v2", index_path=index_path)
                self._current_model_name = voice_name
                _logger.info(f"Modelo RVC '{voice_name}' cargado con éxito.")
                return True, ""
            except Exception as e:
                _logger.error(f"Error cargando modelo RVC '{voice_name}': {e}", exc_info=True)
                return False, str(e)

    def convert(
        self,
        input_wav: str,
        output_wav: str,
        voice: Optional[str] = None,
        pitch: Optional[int] = None,
        index_rate: Optional[float] = None,
        f0_method: str = "pm",
    ) -> tuple[bool, str, int]:
        """
        Convierte el archivo input_wav al timbre de voz RVC y lo guarda en output_wav.

        Args:
            input_wav: Ruta al archivo WAV fuente.
            output_wav: Ruta donde guardar el WAV resultante.
            voice: Nombre de la voz (default: RVC_VOZ en settings o 'aura').
            pitch: Variación de tono en semitonos (-12 a 12, default 0).
            index_rate: Tasa de coincidencia de índices (0.0 a 1.0, default 0.6).
            f0_method: Método de estimación de tono ('pm' rápido en CPU, 'harvest', 'rmvpe').

        Returns:
            tuple(success, error_message, target_sample_rate)
        """
        if not os.path.isfile(input_wav):
            return False, f"Archivo de entrada no existe: {input_wav}", 0

        target_voice = voice or settings.get("RVC_VOZ", "aura") or "aura"
        ok, err = self.load_voice(target_voice)
        if not ok:
            return False, err, 0

        # Obtener parámetros de conversión
        if pitch is None:
            pitch = settings.get_int("RVC_PITCH", 0)
        if index_rate is None:
            index_rate = settings.get_float("RVC_INDEX_RATE", 0.6)

        try:
            engine = self._get_engine()
            # 'pm' (pitch-mark) es sumamente rápido y claro en CPU
            engine.set_params(
                f0method=f0_method,
                f0up_key=pitch,
                index_rate=index_rate,
                filter_radius=3,
                rms_mix_rate=1.0,
                protect=0.33,
            )

            os.makedirs(os.path.dirname(os.path.abspath(output_wav)), exist_ok=True)
            _logger.info(f"RVC: convirtiendo {input_wav} -> {output_wav} (pitch={pitch}, index_rate={index_rate}, method={f0_method})")
            engine.infer_file(input_wav, output_wav)

            if not os.path.isfile(output_wav) or os.path.getsize(output_wav) == 0:
                return False, "RVC infer_file no generó archivo de salida", 0

            target_sr = getattr(engine.vc, "tgt_sr", 40000)
            return True, "", target_sr
        except Exception as e:
            _logger.error(f"Error durante conversión RVC: {e}", exc_info=True)
            return False, str(e), 0


# Singleton exportado
rvc_converter = RVCConverter()

"""
AURA — Proveedores de TTS Base (Fase RVC)

Genera audio fuente en formato WAV PCM para ser consumido directamente
o transformado por el motor de conversión de voz RVC:
1. EdgeTTSProvider: Síntesis en la nube de alta calidad (edge-tts).
2. SAPITTSProvider: Síntesis local offline de Windows (pyttsx3).
"""

from __future__ import annotations

import asyncio
import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from config.settings import settings
from utils.logger import get_logger

_logger = get_logger("aura.voice.tts.base")

# Asegurar que env/Scripts esté en PATH para herramientas como ffmpeg
_ENV_SCRIPTS = str(Path(__file__).resolve().parent.parent.parent / "env" / "Scripts")
if _ENV_SCRIPTS not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _ENV_SCRIPTS + os.pathsep + os.environ.get("PATH", "")


# Voces recomendadas en español para Edge-TTS
DEFAULT_EDGE_VOICES = [
    "es-MX-DaliaNeural",
    "es-ES-ElviraNeural",
    "es-AR-ElenaNeural",
    "es-MX-JorgeNeural",
    "es-ES-AlvaroNeural",
    "es-AR-TomasNeural",
]


class BaseTTSProvider(ABC):
    """Interfaz abstracta para proveedores de síntesis de voz base."""

    @abstractmethod
    def synthesize(self, text: str, output_path: str, voice: Optional[str] = None) -> tuple[bool, str]:
        """
        Sintetiza el texto y guarda el archivo de audio en formato WAV PCM.

        Args:
            text: Texto a pronunciar.
            output_path: Ruta del archivo WAV de destino.
            voice: Nombre o ID de la voz a utilizar (opcional).

        Returns:
            tuple(success, error_message)
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Indica si el proveedor está instalado y listo para su uso."""
        pass

    @abstractmethod
    def list_voices(self) -> list[str]:
        """Retorna la lista de identificadores de voces soportadas."""
        pass


class EdgeTTSProvider(BaseTTSProvider):
    """Proveedor TTS basado en edge-tts (Microsoft Cognitive Services)."""

    def __init__(self, default_voice: str = "es-MX-DaliaNeural"):
        self.default_voice = default_voice

    def is_available(self) -> bool:
        import importlib.util
        return importlib.util.find_spec("edge_tts") is not None

    def list_voices(self) -> list[str]:
        return list(DEFAULT_EDGE_VOICES)

    def synthesize(self, text: str, output_path: str, voice: Optional[str] = None) -> tuple[bool, str]:
        if not text or not text.strip():
            return False, "Texto vacío"

        try:
            import edge_tts
            import soundfile as sf
        except ImportError as e:
            return False, f"Dependencias faltantes (edge_tts/soundfile): {e}"

        chosen_voice = voice or settings.get("RVC_TTS_BASE_VOICE", self.default_voice) or self.default_voice
        temp_mp3 = output_path + ".temp.mp3"

        async def _do_synth():
            communicate = edge_tts.Communicate(text, chosen_voice)
            await communicate.save(temp_mp3)

        try:
            # Ejecutar en loop de eventos seguro
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        pool.submit(lambda: asyncio.run(_do_synth())).result(timeout=30)
                else:
                    loop.run_until_complete(_do_synth())
            except RuntimeError:
                asyncio.run(_do_synth())

            if not os.path.isfile(temp_mp3) or os.path.getsize(temp_mp3) == 0:
                return False, "edge-tts no generó archivo de audio"

            # Convertir mp3 a wav PCM 16-bit
            data, sr = sf.read(temp_mp3)
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            sf.write(output_path, data, sr, format="WAV", subtype="PCM_16")

            try:
                os.remove(temp_mp3)
            except Exception:
                pass

            _logger.info(f"EdgeTTS: audio sintetizado exitosamente ({sr} Hz) -> {output_path}")
            return True, ""
        except Exception as e:
            _logger.error(f"EdgeTTS error al sintetizar: {e}", exc_info=True)
            if os.path.exists(temp_mp3):
                try:
                    os.remove(temp_mp3)
                except Exception:
                    pass
            return False, str(e)


class SAPITTSProvider(BaseTTSProvider):
    """Proveedor TTS offline basado en Microsoft SAPI / pyttsx3."""

    def __init__(self):
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        import importlib.util
        return importlib.util.find_spec("pyttsx3") is not None

    def list_voices(self) -> list[str]:
        voices_list: list[str] = []
        try:
            import pyttsx3
            engine = pyttsx3.init()
            for v in engine.getProperty("voices"):
                voices_list.append(v.name or v.id)
            engine.stop()
        except Exception as e:
            _logger.warning(f"SAPITTSProvider: error listando voces: {e}")
        return voices_list or ["SAPI Default"]

    def synthesize(self, text: str, output_path: str, voice: Optional[str] = None) -> tuple[bool, str]:
        if not text or not text.strip():
            return False, "Texto vacío"

        with self._lock:
            try:
                import pyttsx3
                import soundfile as sf

                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                engine = pyttsx3.init()
                engine.setProperty("rate", 160)

                # Si se solicitó voz específica
                if voice:
                    for v in engine.getProperty("voices"):
                        if voice.lower() in (v.name or "").lower() or voice.lower() in (v.id or "").lower():
                            engine.setProperty("voice", v.id)
                            break

                engine.save_to_file(text, output_path)
                engine.runAndWait()
                engine.stop()

                if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
                    return False, "pyttsx3 no generó archivo de audio"

                # Verificar y asegurar formato WAV estándar
                try:
                    data, sr = sf.read(output_path)
                    sf.write(output_path, data, sr, format="WAV", subtype="PCM_16")
                except Exception:
                    pass

                _logger.info(f"SAPITTS: audio generado exitosamente -> {output_path}")
                return True, ""
            except Exception as e:
                _logger.error(f"SAPITTS error al sintetizar: {e}", exc_info=True)
                return False, str(e)


def get_base_tts(engine_name: Optional[str] = None) -> BaseTTSProvider:
    """
    Retorna la instancia del proveedor TTS base configurado.
    Si se solicita 'edge' pero no está disponible o falla la red,
    permite fallback a SAPI.
    """
    eng = (engine_name or settings.get("RVC_TTS_BASE", "edge") or "edge").lower().strip()
    if eng == "sapi":
        return SAPITTSProvider()
    return EdgeTTSProvider()

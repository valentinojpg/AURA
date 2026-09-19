"""
AURA — Benchmark de TTS Base y Conversión de Voz RVC (Fase RVC)

Prueba de extremo a extremo fuera de la UI:
1. Síntesis con TTS base (EdgeTTS con voz es-MX-DaliaNeural).
2. Conversión RVC con models/rvc/aura/aura.pth y models/rvc/aura/aura.index.
3. Medición de tiempos de ejecución y validación de salida de audio.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Reconfigurar stdout/stderr a UTF-8 para evitar errores de codificación en consola Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import soundfile as sf

# Asegurar que el directorio raíz del proyecto esté en sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Asegurar que env/Scripts esté en PATH para que ffmpeg sea encontrado
scripts_dir = str(ROOT_DIR / "env" / "Scripts")
if scripts_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = scripts_dir + os.pathsep + os.environ.get("PATH", "")

TEST_TEXT = "Hola, soy AURA. Este es un test de conversión de voz con RVC."
OUTPUT_DIR = ROOT_DIR / "data" / "audio_test"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_WAV = str(OUTPUT_DIR / "benchmark_base.wav")
FINAL_WAV = str(OUTPUT_DIR / "benchmark_rvc.wav")

MODEL_PTH = str(ROOT_DIR / "models" / "rvc" / "aura" / "aura.pth")
MODEL_INDEX = str(ROOT_DIR / "models" / "rvc" / "aura" / "aura.index")


async def generate_edge_tts(text: str, output_path: str, voice: str = "es-MX-DaliaNeural") -> float:
    import edge_tts
    t0 = time.time()
    communicate = edge_tts.Communicate(text, voice)
    # edge-tts generates mp3 by default, convert to wav using soundfile/av
    temp_mp3 = output_path + ".mp3"
    await communicate.save(temp_mp3)
    t_edge = time.time() - t0

    # Convert mp3 to wav
    data, sr = sf.read(temp_mp3)
    sf.write(output_path, data, sr, format="WAV", subtype="PCM_16")
    try:
        os.remove(temp_mp3)
    except Exception:
        pass

    return t_edge


def run_benchmark():
    print("=" * 60)
    print("AURA — BENCHMARK DE VOZ RVC")
    print("=" * 60)
    print(f"Texto de prueba: '{TEST_TEXT}'")
    print(f"Modelo PTH:   {MODEL_PTH} (existe: {os.path.isfile(MODEL_PTH)})")
    print(f"Modelo INDEX: {MODEL_INDEX} (existe: {os.path.isfile(MODEL_INDEX)})")

    if not os.path.isfile(MODEL_PTH):
        print("ERROR: No se encontró aura.pth")
        sys.exit(1)

    # 1. Generar TTS Base
    print("\n[1/3] Generando audio base con edge-tts (es-MX-DaliaNeural)...")
    t0_edge = time.time()
    asyncio.run(generate_edge_tts(TEST_TEXT, BASE_WAV))
    t_edge = time.time() - t0_edge

    base_info = sf.info(BASE_WAV)
    print(f"  ✓ Audio base generado en {t_edge:.2f}s")
    print(f"    Ruta: {BASE_WAV}")
    print(f"    Duración: {base_info.duration:.2f}s | Sample Rate: {base_info.samplerate} Hz | Canales: {base_info.channels}")

    # 2. Inicializar RVCInference
    print("\n[2/3] Inicializando motor RVC en CPU...")
    t0_init = time.time()
    from rvc_python.infer import RVCInference
    rvc = RVCInference(
        models_dir=str(ROOT_DIR / "models" / "rvc"),
        device="cpu:0",
    )
    rvc.load_model(MODEL_PTH, version="v2", index_path=MODEL_INDEX)
    # Configurar parámetros estándar (pm es rápido y claro en CPU, index_rate 0.6)
    rvc.set_params(
        f0method="pm",
        f0up_key=0,
        index_rate=0.6,
        filter_radius=3,
        rms_mix_rate=1.0,
        protect=0.33,
    )
    t_init = time.time() - t0_init
    print(f"  ✓ Modelo cargado en {t_init:.2f}s")

    # 3. Conversión RVC
    print("\n[3/3] Convirtiendo audio base a voz AURA con RVC...")
    t0_conv = time.time()
    rvc.infer_file(BASE_WAV, FINAL_WAV)
    t_conv = time.time() - t0_conv

    final_info = sf.info(FINAL_WAV)
    print(f"  ✓ Conversión completada en {t_conv:.2f}s")
    print(f"    Ruta: {FINAL_WAV}")
    print(f"    Duración: {final_info.duration:.2f}s | Sample Rate: {final_info.samplerate} Hz | Canales: {final_info.channels}")

    print("\n" + "=" * 60)
    print("RESUMEN DE RENDIMIENTO (BENCHMARK):")
    print(f"  - Tiempo TTS Base:       {t_edge:.2f}s")
    print(f"  - Tiempo Carga Modelo:   {t_init:.2f}s (solo primera vez)")
    print(f"  - Tiempo Conversión RVC: {t_conv:.2f}s (audio de {final_info.duration:.2f}s)")
    rtf = t_conv / max(final_info.duration, 0.001)
    print(f"  - Real-Time Factor (RTF): {rtf:.2f}x (CPU)")
    print(f"  - Latencia Total:        {t_edge + t_conv:.2f}s")
    print("=" * 60)


if __name__ == "__main__":
    run_benchmark()

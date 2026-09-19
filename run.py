"""
AURA — Asistente Universal con Respuesta Automatizada
Nombre interno: Orion
Versión: 0.10.0 (Fase 10 — Manejo de errores y estado)

Punto de entrada principal de la aplicación.
Inicializa logging, configuración y el manejador global de errores
antes de lanzar la interfaz.
"""

import sys
import os

# Forzar codificación UTF-8 en salida estándar y de errores para evitar mojibake en consolas
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Asegurar que el directorio raíz esté en el path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ── Inicializar logging primero (antes de cualquier otro import interno) ──
from utils.logger import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

# ── Verificación de versión de Python [Portabilidad] ──────────────────────
if sys.version_info[:2] != (3, 11):
    current_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    cartel = (
        "\n"
        "╔════════════════════════════════════════════════════════════════════════════════╗\n"
        "║                     ⚠️  ADVERTENCIA DE ENTORNO PYTHON                          ║\n"
        "╠════════════════════════════════════════════════════════════════════════════════╣\n"
        f"║  Versión detectada: Python {current_ver:<51}║\n"
        "║  Versión requerida: Python 3.11.x                                              ║\n"
        "║                                                                                ║\n"
        "║  AURA está optimizado y validado para Python 3.11.                             ║\n"
        "║  La aplicación continuará ejecutándose, pero pueden ocurrir problemas          ║\n"
        "║  de compatibilidad con dependencias nativas en esta versión.                   ║\n"
        "╚════════════════════════════════════════════════════════════════════════════════╝\n"
    )
    print(cartel, file=sys.stderr)
    logger.warning(
        f"Versión de Python no recomendada: {current_ver}. Se requiere Python 3.11.x. "
        "Continuando ejecución sin interrumpir."
    )

# ── Instalar manejador global de errores [FASE 10] ────────────────────────
from core.error_handler import error_handler
error_handler.install()
logger.info("ErrorHandler global instalado.")

# ── Cargar configuración ──────────────────────────────────────────────────
from config.settings import settings
logger.info(f"Configuración cargada — tema={settings.get('APP_THEME')} "
            f"primera_ejecución={settings.is_first_run()}")

# ── Lanzar interfaz ───────────────────────────────────────────────────────
from ui.branding import set_taskbar_app_id
from ui.main_window import MainWindow


def main():
    """Punto de entrada principal de AURA."""
    # Fijar el identificador de aplicación de Windows para agrupación e ícono en taskbar [Fase 65]
    set_taskbar_app_id(logger=logger)

    # ── Alineación y sanitización de Flet runtime [Fase 78 Fix Ronda 2] ────────
    from aura.ui.flet_client_align import align_and_log_flet_client
    align_and_log_flet_client(custom_logger=logger)

    logger.info("Iniciando ventana principal...")
    try:
        app = MainWindow()
        app.run()
        logger.info("AURA cerrado correctamente.")
    except Exception as e:
        logger.critical(f"Error fatal al iniciar la aplicación: {e}", exc_info=True)
        raise
    finally:
        try:
            from voice.message_speaker import message_speaker
            message_speaker.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()


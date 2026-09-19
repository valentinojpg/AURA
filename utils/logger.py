"""
AURA — Sistema de logging (Fase 2)

Configura el sistema de logging de la aplicación:
- Salida a consola (nivel INFO en desarrollo)
- Archivo rotativo en logs/aura.log (máx. 5 MB × 3 backups)
- Formato legible con timestamp, nivel y módulo

Uso:
    from utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Mensaje informativo")
    logger.error("Algo salió mal", exc_info=True)
"""

import logging
import logging.handlers
from pathlib import Path

# ──────────────────────────────────────────────
# Constantes de configuración del logger
# ──────────────────────────────────────────────
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "aura.log"

LOG_FORMAT = "[%(asctime)s] %(levelname)-8s  %(name)s — %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

MAX_BYTES = 5 * 1024 * 1024   # 5 MB por archivo
BACKUP_COUNT = 3               # Mantener hasta 3 archivos históricos

_initialized = False


def setup_logging(level: int = logging.DEBUG) -> None:
    """
    Inicializa el sistema de logging de AURA.

    Debe llamarse una única vez al inicio de la aplicación (en run.py).
    Los llamados subsiguientes son ignorados.

    Args:
        level: Nivel de log para la consola (default: DEBUG en desarrollo).
    """
    global _initialized
    if _initialized:
        return

    # Crear directorio de logs si no existe
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Logger raíz de AURA
    root_logger = logging.getLogger("aura")
    root_logger.setLevel(logging.DEBUG)  # Capturar todo; filtrar por handler

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    # ── Handler de consola ──────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # ── Handler de archivo rotativo ─────────────────────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        filename=LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    _initialized = True

    # Primera entrada en el log
    root_logger.info("=" * 60)
    root_logger.info("AURA iniciado — Sistema de logging activo")
    root_logger.info(f"Archivo de log: {LOG_FILE}")
    root_logger.info("=" * 60)


def get_logger(name: str) -> logging.Logger:
    """
    Retorna un logger hijo del logger raíz 'aura'.

    Si el sistema de logging no fue inicializado, lo inicializa
    con configuración por defecto.

    Args:
        name: Nombre del módulo (usar __name__ como convención).

    Returns:
        Logger configurado bajo el namespace 'aura'.

    Ejemplo:
        logger = get_logger(__name__)
        # En módulo config.settings → logger 'aura.config.settings'
    """
    if not _initialized:
        setup_logging()

    # Normalizar el nombre: si ya empieza con 'aura', usarlo tal cual
    if not name.startswith("aura"):
        logger_name = f"aura.{name}"
    else:
        logger_name = name

    return logging.getLogger(logger_name)

"""
AURA — Manejador global de errores (Fase 10)

Centraliza el manejo de errores no controlados de la aplicación:
  - Instala un hook global para excepciones no capturadas (sys.excepthook)
  - Instala un hook para excepciones en threads de fondo (threading.excepthook)
  - Registra todos los errores en el log con contexto completo
  - Notifica a suscriptores (ej. UI) cuando ocurre un error grave
  - Clasifica errores en: crítico / error / advertencia
  - Provee mensajes amigables para el usuario (sin stacktrace crudo)

Uso:
    from core.error_handler import error_handler
    error_handler.install()
    error_handler.subscribe(callback)   # callback(level, title, msg)
    error_handler.report_error("título", "descripción", exc=e)
"""

from __future__ import annotations

import sys
import threading
import traceback
from typing import Callable

from utils.logger import get_logger

_logger = get_logger("aura.core.error_handler")

# Niveles de severidad
LEVEL_CRITICAL = "critical"   # Excepción no controlada que puede crashear la app
LEVEL_ERROR    = "error"      # Error controlado pero que impide completar la acción
LEVEL_WARNING  = "warning"    # Condición anómala que no impide continuar


# ── Mensajes amigables para el usuario ────────────────────────────────────

_FRIENDLY_MESSAGES: dict[str, str] = {
    "ConnectionRefusedError": (
        "No se pudo conectar con el servicio. "
        "Verificá que Ollama esté corriendo en tu computadora."
    ),
    "FileNotFoundError": (
        "No se encontró un archivo necesario. "
        "Revisá que los archivos de datos no hayan sido movidos o eliminados."
    ),
    "PermissionError": (
        "AURA no tiene permisos para acceder al archivo o carpeta. "
        "Intentá ejecutar como administrador o cambiá los permisos."
    ),
    "MemoryError": (
        "No hay suficiente memoria RAM disponible. "
        "Cerrá otras aplicaciones y volvé a intentarlo."
    ),
    "KeyboardInterrupt": "La aplicación fue interrumpida por el usuario.",
    "SystemExit": "La aplicación se está cerrando.",
}

_DEFAULT_FRIENDLY = (
    "Ocurrió un error inesperado. "
    "Los detalles fueron guardados en logs/aura.log."
)


def _friendly_message(exc: BaseException | None) -> str:
    """Retorna un mensaje amigable según el tipo de excepción."""
    if exc is None:
        return _DEFAULT_FRIENDLY
    exc_type_name = type(exc).__name__
    return _FRIENDLY_MESSAGES.get(exc_type_name, _DEFAULT_FRIENDLY)


class ErrorHandler:
    """
    Manejador global de errores de AURA.

    Instala hooks en sys.excepthook y threading.excepthook para capturar
    cualquier excepción no controlada y registrarla correctamente.

    Notifica a todos los suscriptores registrados con:
        callback(level: str, title: str, message: str)

    Es un singleton: usar la instancia global `error_handler`.
    """

    def __init__(self) -> None:
        self._subscribers: list[Callable[[str, str, str], None]] = []
        self._installed = False
        self._error_count = 0
        self._last_error: str | None = None

    # ──────────────────────────────────────────────
    # Instalación de hooks globales
    # ──────────────────────────────────────────────

    def install(self) -> None:
        """
        Instala los hooks de excepción global.

        Debe llamarse una sola vez al inicio, después de setup_logging().
        Los llamados subsiguientes son ignorados.
        """
        if self._installed:
            return

        # Guardar hooks originales para restaurar si es necesario
        self._original_excepthook = sys.excepthook
        self._original_threading_excepthook = threading.excepthook

        sys.excepthook = self._on_uncaught_exception
        threading.excepthook = self._on_thread_exception

        self._installed = True
        _logger.info("ErrorHandler instalado — hooks globales activos.")

    def uninstall(self) -> None:
        """Restaura los hooks originales. Útil para tests."""
        if not self._installed:
            return
        sys.excepthook = self._original_excepthook
        threading.excepthook = self._original_threading_excepthook
        self._installed = False
        _logger.debug("ErrorHandler desinstalado.")

    # ──────────────────────────────────────────────
    # Hooks de excepción
    # ──────────────────────────────────────────────

    def _on_uncaught_exception(self, exc_type, exc_value, exc_tb) -> None:
        """
        Hook para excepciones no capturadas en el hilo principal.

        No intercepta KeyboardInterrupt ni SystemExit para permitir
        que la app se cierre normalmente.
        """
        # Dejar pasar interrupciones normales de cierre
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            self._original_excepthook(exc_type, exc_value, exc_tb)
            return

        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        title = f"Error no controlado: {exc_type.__name__}"
        friendly = _friendly_message(exc_value)

        _logger.critical(
            f"EXCEPCIÓN NO CONTROLADA [{exc_type.__name__}]: {exc_value}\n{tb_str}"
        )

        self._error_count += 1
        self._last_error = str(exc_value)
        self._notify(LEVEL_CRITICAL, title, friendly)

    def _on_thread_exception(self, args) -> None:
        """
        Hook para excepciones no capturadas en threads de fondo.
        Compatible con threading.excepthook (Python 3.8+).
        """
        exc_type = args.exc_type
        exc_value = args.exc_value
        exc_tb = args.exc_traceback
        thread = args.thread

        # Dejar pasar cierres normales
        if exc_type is None or issubclass(exc_type, SystemExit):
            return

        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        thread_name = thread.name if thread else "desconocido"
        title = f"Error en thread '{thread_name}': {exc_type.__name__}"
        friendly = _friendly_message(exc_value)

        _logger.error(
            f"EXCEPCIÓN EN THREAD '{thread_name}' [{exc_type.__name__}]: "
            f"{exc_value}\n{tb_str}"
        )

        self._error_count += 1
        self._last_error = str(exc_value)
        self._notify(LEVEL_ERROR, title, friendly)

    # ──────────────────────────────────────────────
    # API pública
    # ──────────────────────────────────────────────

    def report_error(
        self,
        title: str,
        message: str,
        exc: BaseException | None = None,
        level: str = LEVEL_ERROR,
    ) -> None:
        """
        Registra un error controlado y notifica a los suscriptores.

        Usar cuando se captura una excepción y se quiere notificar a la UI.

        Args:
            title:   Título breve del error (visible al usuario).
            message: Descripción amigable del problema.
            exc:     Excepción original (para el log, no se muestra al usuario).
            level:   Severidad: LEVEL_ERROR, LEVEL_WARNING, LEVEL_CRITICAL.
        """
        if exc is not None:
            _logger.error(
                f"Error reportado [{level.upper()}] {title}: {exc}",
                exc_info=True,
            )
        else:
            _logger.warning(f"[{level.upper()}] {title}: {message}")

        self._error_count += 1
        self._last_error = message
        self._notify(level, title, message)

    def report_warning(self, title: str, message: str) -> None:
        """Atajo para reportar una advertencia (no bloquea la UI)."""
        _logger.warning(f"[WARNING] {title}: {message}")
        self._notify(LEVEL_WARNING, title, message)

    def subscribe(self, callback: Callable[[str, str, str], None]) -> None:
        """
        Suscribe una función para recibir notificaciones de error.

        Args:
            callback: Función con firma callback(level, title, message).
        """
        self._subscribers.append(callback)
        _logger.debug("ErrorHandler: suscriptor registrado.")

    def unsubscribe(self, callback: Callable[[str, str, str], None]) -> None:
        """Elimina un suscriptor registrado."""
        try:
            self._subscribers.remove(callback)
        except ValueError:
            pass

    # ──────────────────────────────────────────────
    # Estado y métricas
    # ──────────────────────────────────────────────

    @property
    def error_count(self) -> int:
        """Número total de errores registrados desde que se instaló el handler."""
        return self._error_count

    @property
    def last_error(self) -> str | None:
        """Último mensaje de error registrado, o None si no hubo errores."""
        return self._last_error

    @property
    def is_installed(self) -> bool:
        """True si los hooks globales están instalados."""
        return self._installed

    def reset_count(self) -> None:
        """Reinicia el contador de errores (útil para tests)."""
        self._error_count = 0
        self._last_error = None

    # ──────────────────────────────────────────────
    # Notificación interna
    # ──────────────────────────────────────────────

    def _notify(self, level: str, title: str, message: str) -> None:
        """Notifica a todos los suscriptores. Silencia errores en callbacks."""
        for cb in list(self._subscribers):
            try:
                cb(level, title, message)
            except Exception as e:
                _logger.error(f"ErrorHandler: fallo en suscriptor: {e}")

    def __repr__(self) -> str:
        return (
            f"<ErrorHandler installed={self._installed} "
            f"errors={self._error_count}>"
        )


# ──────────────────────────────────────────────
# Instancia global (singleton)
# ──────────────────────────────────────────────

error_handler = ErrorHandler()

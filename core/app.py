"""
AURA — Controlador central de la aplicación (Fase 3)

Coordina la inicialización, navegación entre páginas
y ciclo de vida general de la app.

El App actúa como intermediario entre:
    - La ventana principal (MainWindow)
    - El estado global (AppState)
    - Las páginas de la UI
"""

from utils.logger import get_logger
from core.state import app_state
from config.settings import settings


class App:
    """
    Controlador principal de AURA.

    Gestiona:
        - Inicialización ordenada de módulos
        - Navegación entre páginas
        - Estado global de la aplicación
        - Configuración del tema

    Uso:
        app = App()
        app.navigate_to("chat")
    """

    def __init__(self) -> None:
        self._logger = get_logger("aura.core.app")
        self._logger.info("App controller inicializado.")
        self._load_initial_state()

    # ──────────────────────────────────────────────
    # Inicialización
    # ──────────────────────────────────────────────

    def _load_initial_state(self) -> None:
        """Carga el estado inicial desde la configuración."""
        theme = settings.get("APP_THEME", "dark")
        app_state.set("theme", theme)
        self._logger.debug(f"Estado inicial cargado — tema={theme}")

    # ──────────────────────────────────────────────
    # Navegación
    # ──────────────────────────────────────────────

    def navigate_to(self, page_id: str) -> None:
        """
        Solicita navegar a una página específica.

        Actualiza el estado global y notifica a los suscriptores.

        Args:
            page_id: ID de la página destino.
        """
        current = app_state.current_page
        if current == page_id:
            self._logger.debug(f"Ya en página: {page_id}")
            return

        self._logger.info(f"Navegando: {current} → {page_id}")
        app_state.current_page = page_id

    # ──────────────────────────────────────────────
    # Estado y diagnóstico
    # ──────────────────────────────────────────────

    def get_status(self) -> dict:
        """Retorna un resumen del estado actual de la app."""
        return {
            "page": app_state.current_page,
            "theme": app_state.theme,
            "ai_status": app_state.get("ai_status"),
            "first_run": settings.is_first_run(),
        }

    def __repr__(self) -> str:
        return f"<App page={app_state.current_page!r}>"

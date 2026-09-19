"""
AURA — Estado global de la aplicación (Fase 3)

Provee un estado centralizado y observable para la aplicación.
Permite que distintos módulos compartan información sin acoplamiento directo.

Uso:
    from core.state import app_state

    app_state.set("current_page", "chat")
    page = app_state.get("current_page")

    # Suscribirse a cambios de una clave
    app_state.subscribe("current_page", callback)
"""

from __future__ import annotations
from typing import Any, Callable
from utils.logger import get_logger


class AppState:
    """
    Estado global reactivo de AURA.

    Almacena valores clave y notifica a los suscriptores cuando cambian.
    Es un singleton: usar la instancia global `app_state`.

    Claves iniciales:
        - current_page: str   → ID de la página actualmente visible
        - ai_status: str      → Estado de la conexión con el proveedor IA
        - theme: str          → Tema activo ("dark" | "light")
    """

    # Estado inicial por defecto
    _INITIAL_STATE: dict[str, Any] = {
        "current_page": "chat",
        "ai_status": "desconectado",
        "theme": "dark",
    }

    def __init__(self) -> None:
        """Inicializa el estado con los valores por defecto."""
        self._logger = get_logger("aura.core.state")
        self._data: dict[str, Any] = dict(self._INITIAL_STATE)
        self._subscribers: dict[str, list[Callable[[Any], None]]] = {}
        self._logger.debug("AppState inicializado.")

    # ──────────────────────────────────────────────
    # Lectura y escritura
    # ──────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retorna el valor de una clave del estado.

        Args:
            key: Clave a leer.
            default: Valor por defecto si la clave no existe.

        Returns:
            Valor asociado a la clave, o `default`.
        """
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Actualiza el valor de una clave y notifica a los suscriptores.

        Args:
            key: Clave a actualizar.
            value: Nuevo valor.
        """
        old_value = self._data.get(key)
        self._data[key] = value

        if old_value != value:
            self._logger.debug(f"Estado: {key} = {value!r} (antes: {old_value!r})")
            self._notify(key, value)

    def all(self) -> dict[str, Any]:
        """Retorna una copia de todo el estado actual."""
        return dict(self._data)

    def reset(self) -> None:
        """Reinicia el estado a los valores por defecto."""
        self._data = dict(self._INITIAL_STATE)
        self._logger.info("Estado reseteado a valores por defecto.")

    # ──────────────────────────────────────────────
    # Sistema de suscripciones
    # ──────────────────────────────────────────────

    def subscribe(self, key: str, callback: Callable[[Any], None]) -> None:
        """
        Suscribe una función a los cambios de una clave.

        La función recibirá el nuevo valor cuando la clave cambie.

        Args:
            key: Clave a observar.
            callback: Función a llamar con el nuevo valor.
        """
        if key not in self._subscribers:
            self._subscribers[key] = []
        self._subscribers[key].append(callback)
        self._logger.debug(f"Suscriptor registrado para '{key}'.")

    def unsubscribe(self, key: str, callback: Callable[[Any], None]) -> None:
        """
        Elimina una suscripción a cambios de una clave.

        Args:
            key: Clave observada.
            callback: Función a eliminar.
        """
        if key in self._subscribers:
            try:
                self._subscribers[key].remove(callback)
                self._logger.debug(f"Suscriptor eliminado para '{key}'.")
            except ValueError:
                pass  # Callback no encontrado, ignorar

    def _notify(self, key: str, value: Any) -> None:
        """Notifica a todos los suscriptores de una clave."""
        for callback in self._subscribers.get(key, []):
            try:
                callback(value)
            except Exception as e:
                self._logger.error(
                    f"Error en suscriptor de '{key}': {e}", exc_info=True
                )

    # ──────────────────────────────────────────────
    # Propiedades de conveniencia
    # ──────────────────────────────────────────────

    @property
    def current_page(self) -> str:
        """Página actualmente visible."""
        return self.get("current_page", "chat")

    @current_page.setter
    def current_page(self, value: str) -> None:
        self.set("current_page", value)

    @property
    def theme(self) -> str:
        """Tema de la interfaz activo."""
        return self.get("theme", "dark")

    @theme.setter
    def theme(self, value: str) -> None:
        self.set("theme", value)

    def __repr__(self) -> str:
        return f"<AppState page={self.current_page!r} theme={self.theme!r}>"


# ──────────────────────────────────────────────
# Instancia global (singleton)
# ──────────────────────────────────────────────
app_state = AppState()

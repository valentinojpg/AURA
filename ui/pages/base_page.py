"""
AURA — Clase base para páginas de la interfaz (Flet)

Todas las páginas de la aplicación heredan de BasePage (ft.Container).
Define la interfaz común: on_enter, on_leave, _build.
"""

from __future__ import annotations

import flet as ft
from utils.logger import get_logger


class BasePage(ft.Container):
    """
    Página base abstracta de AURA construida con Flet.

    Todas las páginas heredan de esta clase para tener
    una interfaz uniforme de ciclo de vida (mostrar/ocultar).

    Subclases deben sobrescribir:
        - _build() → construir el contenido visual de la página
        - on_enter() → acciones al entrar a la página (opcional)
        - on_leave() → acciones al salir de la página (opcional)
    """

    PAGE_NAME: str = "Página"

    def __init__(self, page: ft.Page, **kwargs):
        """
        Inicializa el contenedor de la página.

        Args:
            page: Instancia de ft.Page de Flet.
        """
        super().__init__(expand=True, padding=0, margin=0, **kwargs)
        self.app_page = page
        self._logger = get_logger(f"aura.ui.page.{self.PAGE_NAME.lower()}")
        self._build()

    # ──────────────────────────────────────────────
    # Ciclo de vida
    # ──────────────────────────────────────────────

    def on_enter(self) -> None:
        """Llamado al mostrar la página. Sobrescribir si es necesario."""
        pass

    def on_leave(self) -> None:
        """Llamado al ocultar la página. Sobrescribir si es necesario."""
        pass

    # ──────────────────────────────────────────────
    # Construcción (obligatorio sobrescribir)
    # ──────────────────────────────────────────────

    def _build(self) -> None:
        """Construye el contenido de la página. Sobrescribir en subclase."""
        raise NotImplementedError(
            f"La página '{self.__class__.__name__}' debe implementar _build()."
        )

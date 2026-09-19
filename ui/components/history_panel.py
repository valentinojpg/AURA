"""
AURA — Panel de historial de conversaciones (Flet)

Panel lateral que lista las conversaciones guardadas con
opciones para abrir, renombrar, eliminar y crear una nueva conversación.
"""

from __future__ import annotations

from typing import Callable, Optional
import flet as ft
from data.conversation_store import ConversationStore, Conversation
from utils.logger import get_logger


_logger = get_logger("aura.ui.history_panel")

_PANEL_BG    = "#0A0A16"
_ITEM_BG     = "#111124"
_ITEM_ACTIVE = "#1A1A3A"
_PANEL_WIDTH = 260


class HistoryPanel(ft.Container):
    """
    Panel lateral de historial de conversaciones en Flet.

    Integrado dentro de ChatPage como un panel lateral.
    """

    def __init__(
        self,
        store: ConversationStore,
        on_open: Callable[[str], bool],
        on_new: Callable[[], None],
        on_close: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(
            width=_PANEL_WIDTH,
            bgcolor=_PANEL_BG,
            border=ft.Border.only(right=ft.BorderSide(1, "#1A1A2E")),
            visible=False,
            **kwargs,
        )
        self._store = store
        self._on_open = on_open
        self._on_new = on_new
        self._on_close = on_close
        self._active_conv_id: Optional[str] = None
        self._conversations_list = ft.ListView(expand=True, spacing=6, padding=ft.Padding.all(8))
        self._build()

    @property
    def is_visible(self) -> bool:
        return self.visible

    def _build(self) -> None:
        header = ft.Container(
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.HISTORY, size=18, color="#6A6A9A"),
                            ft.Text("Historial", size=13, weight=ft.FontWeight.BOLD, color="#C0C0E0"),
                        ],
                        spacing=6,
                    ),
                    ft.IconButton(
                        ft.Icons.CLOSE,
                        icon_size=16,
                        icon_color="#6A6A9A",
                        tooltip="Cerrar panel",
                        on_click=lambda e: self.dismiss(),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border=ft.Border.only(bottom=ft.BorderSide(1, "#1A1A2E")),
        )

        new_btn = ft.Container(
            content=ft.FilledButton(
                "➕ Nueva conversación",
                on_click=lambda e: self._on_new(),
                style=ft.ButtonStyle(
                    bgcolor="#1E2A4A",
                    color="#E0E8FF",
                    shape=ft.RoundedRectangleBorder(radius=8),
                ),
                height=36,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
        )

        self.content = ft.Column(
            [
                header,
                new_btn,
                self._conversations_list,
            ],
            expand=True,
            spacing=0,
        )

    def show(self, active_conv_id: Optional[str] = None) -> None:
        self._active_conv_id = active_conv_id
        self.visible = True
        self.refresh()
        try:
            self.update()
        except Exception:
            pass

    def dismiss(self) -> None:
        self.visible = False
        if self._on_close:
            self._on_close()
        try:
            self.update()
        except Exception:
            pass

    def toggle(self, active_conv_id: Optional[str] = None) -> None:
        if self.visible:
            self.dismiss()
        else:
            self.show(active_conv_id=active_conv_id)

    def set_active(self, conv_id: Optional[str]) -> None:
        self._active_conv_id = conv_id
        self.refresh()

    def refresh(self) -> None:
        """Carga y renderiza las conversaciones desde disco."""
        self._conversations_list.controls.clear()
        try:
            metas = self._store.list_all()
        except Exception as e:
            _logger.error(f"Error listando conversaciones: {e}")
            metas = []

        if not metas:
            self._conversations_list.controls.append(
                ft.Container(
                    content=ft.Text("No hay conversaciones", size=11, color="#555577"),
                    alignment=ft.Alignment.CENTER,
                    padding=ft.Padding.all(20),
                )
            )
        else:
            for meta in metas:
                card = self._build_item(meta)
                self._conversations_list.controls.append(card)

        try:
            self._conversations_list.update()
        except Exception:
            pass

    def _build_item(self, meta: dict | Conversation) -> ft.Container:
        m_id = meta["id"] if isinstance(meta, dict) else meta.id
        m_title = meta["title"] if isinstance(meta, dict) else meta.title
        m_count = meta["message_count"] if isinstance(meta, dict) else meta.message_count
        m_updated = meta["updated_at"] if isinstance(meta, dict) else meta.updated_at

        is_active = (m_id == self._active_conv_id)

        title_text = m_title if len(m_title) <= 24 else m_title[:21] + "…"

        def on_item_click(e):
            self.set_active(m_id)
            self._on_open(m_id)

        def on_delete_click(e):
            # Diálogo de confirmación
            def confirm_delete(ev):
                if self.page:
                    self.page.pop_dialog()
                self._store.delete(m_id)
                self.refresh()

            def cancel_delete(ev):
                if self.page:
                    self.page.pop_dialog()

            dlg = ft.AlertDialog(
                title=ft.Text("¿Eliminar conversación?"),
                content=ft.Text(f'Se eliminará "{m_title}". Esta acción no se puede deshacer.'),
                actions=[
                    ft.TextButton("Cancelar", on_click=cancel_delete),
                    ft.ElevatedButton("Eliminar", on_click=confirm_delete, bgcolor="#7B2020", color="#FFFFFF"),
                ],
            )
            if self.page:
                self.page.show_dialog(dlg)

        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(title_text, size=12, weight=ft.FontWeight.BOLD, color="#B8B8D8"),
                            ft.Text(f"{m_count} msgs · {str(m_updated)[:10]}", size=10, color="#555577"),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE,
                        icon_size=16,
                        icon_color="#7A3A3A",
                        tooltip="Eliminar",
                        on_click=on_delete_click,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            bgcolor=_ITEM_ACTIVE if is_active else _ITEM_BG,
            border_radius=8,
            border=ft.Border.all(1, "#252545" if is_active else "#16162E"),
            on_click=on_item_click,
            ink=True,
        )

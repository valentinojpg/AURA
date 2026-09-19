"""
AURA — Paquete de componentes UI (Fases 3, 7, 9 y 10)

Exporta los componentes reutilizables de la interfaz.
"""

from ui.components.sidebar import Sidebar
from ui.components.topbar import TopBar
from ui.components.chat_bubble import ChatBubble
from ui.components.history_panel import HistoryPanel
from ui.components.status_bar import StatusBar
from ui.components.audio_panel import AudioPanel
from ui.components.color_picker import ColorPicker, ThemeLivePreview

__all__ = [
    "Sidebar",
    "TopBar",
    "ChatBubble",
    "HistoryPanel",
    "StatusBar",
    "AudioPanel",
    "ColorPicker",
    "ThemeLivePreview",
]

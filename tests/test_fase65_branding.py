"""
Tests para la FASE 65 — Branding: Conectar los íconos reales de assets/
"""

import os
import struct
import sys
from unittest.mock import MagicMock, patch
import flet as ft
import pytest

from ui.branding import (
    APP_USER_MODEL_ID,
    WINDOW_TITLE,
    apply_window_branding,
    create_brand_avatar,
    ensure_header_logo,
    ensure_ico_backup,
    ensure_logo2_ico,
    get_assets_dir,
    get_header_logo_src,
    get_logo2_ico_path,
    get_logo2_png_path,
    get_logo_header_path,
    get_logo_png_path,
    get_window_ico_path,
    set_taskbar_app_id,
    verify_ico_file,
)
from ui.components.chat_bubble import ChatBubble
from ui.components.sidebar import Sidebar
from ui.components.topbar import TopBar
from ui.main_window import MainWindow
from ui.wizard.setup_wizard import SetupWizard


def test_user_assets_exist_and_intact():
    """Verifica que assets/logo.png, assets/logo2.png y assets/logo.ico.invalid existen con sus roles."""
    assets_dir = get_assets_dir()
    png_path = get_logo_png_path()
    logo2_png_path = get_logo2_png_path()
    backup_path = os.path.join(assets_dir, "logo.ico.invalid")

    assert os.path.isdir(assets_dir), f"El directorio {assets_dir} debe existir"
    assert os.path.isfile(png_path), "assets/logo.png (waifu) debe existir"
    assert os.path.isfile(logo2_png_path), "assets/logo2.png (fuente taskbar) debe existir"

    # Asegurar backup
    ensure_ico_backup()
    assert os.path.isfile(backup_path), "assets/logo.ico.invalid (backup del anterior) debe existir"

    # Verificar magic bytes de logo.png y logo2.png (PNG)
    for p in [png_path, logo2_png_path]:
        with open(p, "rb") as f:
            header = f.read(24)
        assert header.startswith(b"\x89PNG\r\n\x1a\n"), f"{p} debe ser un archivo PNG válido"


def test_logo2_ico_generation_and_verification():
    """Verifica que logo2.ico tenga magic bytes 00 00 01 00 y al menos 5 tamaños presentes."""
    ico_path = ensure_logo2_ico()
    assert os.path.isfile(ico_path), "assets/logo2.ico debe existir"

    valid, detail = verify_ico_file(ico_path)
    assert valid, f"Verificación de logo2.ico falló: {detail}"

    with open(ico_path, "rb") as f:
        data = f.read()

    # Primeros 4 bytes = 00 00 01 00
    assert data[:4] == b"\x00\x00\x01\x00", "Los primeros 4 bytes deben ser 00 00 01 00"

    num_sizes = struct.unpack("<H", data[4:6])[0]
    assert num_sizes >= 5, f"Debe contener al menos 5 tamaños, encontrados: {num_sizes}"
    assert num_sizes == 7, f"Se esperaban 7 tamaños (16..256), encontrados: {num_sizes}"


def test_branding_paths_resolution():
    """Verifica que las rutas devueltas por el módulo de branding sean absolutas y correctas."""
    assets_dir = get_assets_dir()
    assert os.path.isabs(assets_dir)
    assert os.path.isabs(get_logo_png_path())
    assert os.path.isabs(get_logo2_png_path())
    assert os.path.isabs(get_logo_header_path())
    assert os.path.isabs(get_window_ico_path())
    assert get_window_ico_path().endswith("logo2.ico")


def test_header_logo_derivative():
    """Verifica que exista la copia derivada logo_header.png (128x128) para el header."""
    src = ensure_header_logo()
    header_path = get_logo_header_path()

    assert os.path.isfile(header_path), "assets/logo_header.png debe existir como copia derivada"
    assert src == "logo_header.png"

    with open(header_path, "rb") as f:
        h_data = f.read(24)
    w, h = struct.unpack(">II", h_data[16:24])
    assert (w, h) == (128, 128), f"logo_header.png debe medir 128x128 px, detectado: {w}x{h}"
    assert os.path.getsize(header_path) < 100 * 1024, "logo_header.png debe ser ligero (< 100 KB)"


def test_create_brand_avatar():
    """Verifica que el avatar circular se construya con fit CONTAIN, border_radius y anti-aliasing."""
    avatar = create_brand_avatar(size=28, tooltip="AURA Test")
    assert isinstance(avatar, ft.Container)
    assert avatar.width == 28
    assert avatar.height == 28
    assert avatar.border_radius == 14
    assert avatar.clip_behavior == ft.ClipBehavior.ANTI_ALIAS

    # Control de imagen interno
    img = avatar.content
    assert isinstance(img, ft.Image)
    assert img.width == 28
    assert img.height == 28
    assert img.fit == ft.BoxFit.CONTAIN
    assert img.src in ["logo_header.png", "logo.png"]


def test_app_user_model_id():
    """Verifica la constante AppUserModelID y su ejecución en Windows."""
    assert APP_USER_MODEL_ID == "aura.orion.desktop"
    if sys.platform == "win32":
        res = set_taskbar_app_id()
        assert res is True


def test_window_title_and_branding_apply():
    """Verifica el título de ventana y la asignación del ícono nativo."""
    assert WINDOW_TITLE == "AURA — Asistente Universal"
    assert MainWindow.APP_NAME == "AURA — Asistente Universal"

    mock_page = MagicMock()
    mock_window = MagicMock()
    mock_page.window = mock_window

    apply_window_branding(mock_page, WINDOW_TITLE)
    assert mock_window.icon == get_window_ico_path()


def test_sidebar_uses_brand_avatar_not_star():
    """Verifica que el Sidebar muestre el avatar circular de AURA y haya eliminado la estrellita."""
    sidebar = Sidebar()
    logo_col = sidebar.content.controls[0].content
    assert isinstance(logo_col, ft.Column)

    header_row = logo_col.controls[0]
    assert isinstance(header_row, ft.Row)

    # El primer elemento debe ser el contenedor del avatar
    first_elem = header_row.controls[0]
    assert isinstance(first_elem, ft.Container)
    assert isinstance(first_elem.content, ft.Image)

    # El segundo elemento debe ser el texto AURA
    second_elem = header_row.controls[1]
    assert isinstance(second_elem, ft.Text)
    assert second_elem.value == "AURA"

    # Ningún control en el header_row debe ser la estrellita "✦"
    for ctrl in header_row.controls:
        if isinstance(ctrl, ft.Text):
            assert ctrl.value != "✦"


def test_topbar_uses_brand_avatar():
    """Verifica que el TopBar contenga el avatar circular de la marca."""
    topbar = TopBar()
    left_row = topbar.content.controls[0]
    assert isinstance(left_row, ft.Row)

    # El primer control debe ser el avatar
    avatar = left_row.controls[0]
    assert isinstance(avatar, ft.Container)
    assert isinstance(avatar.content, ft.Image)

    # El segundo control debe ser el texto AURA
    aura_text = left_row.controls[1]
    assert isinstance(aura_text, ft.Text)
    assert aura_text.value == "AURA"


def test_chat_bubble_assistant_has_avatar():
    """Verifica que la burbuja de respuesta del asistente incluya el avatar circular."""
    bubble_assistant = ChatBubble(role="assistant", content="Hola soy Aura")
    container = bubble_assistant.content
    col = container.content
    header = col.controls[0]

    # En assistant debe ser un Row con avatar e información
    assert isinstance(header, ft.Row)
    avatar = header.controls[0]
    assert isinstance(avatar, ft.Container)
    assert isinstance(avatar.content, ft.Image)
    name_txt = header.controls[1]
    assert name_txt.value == "AURA"

    # En usuario debe ser simplemente el texto "Vos" sin avatar de asistente
    bubble_user = ChatBubble(role="user", content="Hola")
    header_user = bubble_user.content.content.controls[0]
    assert isinstance(header_user, ft.Text)
    assert header_user.value == "Vos"


def test_setup_wizard_step1_has_avatar():
    """Verifica que el diálogo de SetupWizard paso 1 utilice el avatar circular en lugar del ícono genérico."""
    mock_page = MagicMock()
    wizard = SetupWizard(mock_page)
    step1 = wizard._get_step_content()
    assert isinstance(step1, ft.Column)

    first_row = step1.controls[0]
    assert isinstance(first_row, ft.Row)

    first_ctrl = first_row.controls[0]
    # Debe ser el Container del avatar con imagen
    assert isinstance(first_ctrl, ft.Container)
    assert isinstance(first_ctrl.content, ft.Image)


def test_asset_roles_not_mixed():
    """Verifica que los roles de los assets no se mezclen: waifu in-app y logo2 en ventana/taskbar."""
    in_app_src = get_header_logo_src()
    window_ico = get_window_ico_path()

    # El avatar in-app debe apuntar a la waifu (logo.png o su derivado logo_header.png)
    assert in_app_src in ["logo_header.png", "logo.png"]
    assert "logo2" not in in_app_src

    # El ícono de ventana/taskbar debe ser logo2.ico
    assert window_ico.endswith("logo2.ico")
    assert "logo.png" not in window_ico


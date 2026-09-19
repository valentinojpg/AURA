"""
AURA — Tests unitarios para FilePicker Compatibility Layer y Resiliencia (Fix Fase 78 Ronda 2).
"""

from unittest.mock import MagicMock, patch
import flet as ft

from aura.ui.file_picker_compat import (
    CompatibleFilePicker,
    FilePickerCompatFile,
    FilePickerCompatResult,
    TkinterFilePicker,
    diagnose_file_picker_api,
    get_file_picker,
    open_file_picker_dialog,
)
from aura.ui.flet_client_align import (
    align_and_log_flet_client,
    clean_stale_flet_caches,
    get_flet_client_path,
    get_flet_package_version,
)
from ui.pages.settings_page import SettingsPage


def test_diagnose_file_picker_api():
    """Valida que el diagnóstico reporte la versión y firmas reales sin fallar."""
    diag = diagnose_file_picker_api()
    assert isinstance(diag, dict)
    assert diag["flet_version"] == "0.86.5"
    assert diag["has_file_picker"] is True
    assert "pick_files_signature" in diag
    assert diag["pick_files_is_coro"] is True
    assert diag["has_on_result"] is False
    assert diag["has_on_change"] is False


def test_get_file_picker_runtime_selection():
    """Valida que get_file_picker seleccione Estrategia B en Flet 0.86.5."""
    called = []
    def callback(res):
        called.append(res)

    picker = get_file_picker(callback)
    assert picker is not None
    assert isinstance(picker, CompatibleFilePicker)
    assert isinstance(picker, ft.FilePicker)


def test_file_picker_compat_result_structures():
    """Valida normalización de eventos para diferentes entradas (objetos, paths, dicts)."""
    # 1. Lista de paths en string
    res1 = FilePickerCompatResult(["C:/bg.png", "C:/photo.jpg"])
    assert len(res1.files) == 2
    assert res1.files[0].path == "C:/bg.png"
    assert res1.files[0].name == "bg.png"
    assert isinstance(res1.files[0], FilePickerCompatFile)

    # 2. Objeto con atributo path
    class DummyFile:
        def __init__(self, path):
            self.path = path
    res2 = FilePickerCompatResult([DummyFile("C:/anim.gif")])
    assert len(res2.files) == 1
    assert res2.files[0].path == "C:/anim.gif"

    # 3. Diccionario
    res3 = FilePickerCompatResult([{"path": "C:/custom.webp", "name": "custom.webp", "size": 1024}])
    assert len(res3.files) == 1
    assert res3.files[0].path == "C:/custom.webp"
    assert res3.files[0].size == 1024

    # 4. None o lista vacía
    res4 = FilePickerCompatResult(None)
    assert res4.files == []
    res5 = FilePickerCompatResult([])
    assert res5.files == []


def test_strategy_a_fallback():
    """Simula una versión de Flet donde __init__ acepta on_result (Estrategia A)."""
    class MockFilePickerOld:
        def __init__(self, on_result=None):
            self.on_result = on_result

    with patch.object(ft, "FilePicker", MockFilePickerOld):
        cb = MagicMock()
        picker = get_file_picker(cb)
        assert picker is not None
        assert isinstance(picker, MockFilePickerOld)
        assert picker.on_result == cb


def test_strategy_c_fallback():
    """Simula una versión de Flet con on_change / result (Estrategia C)."""
    class MockFilePickerProp:
        def __init__(self):
            self.on_change = None
            self.result = ["C:/test.png"]
        def pick_files(self):
            pass

    with patch.object(ft, "FilePicker", MockFilePickerProp):
        cb = MagicMock()
        picker = get_file_picker(cb)
        assert picker is not None
        assert hasattr(picker, "on_change")
        # Invocar proxy
        picker.on_change(MagicMock())
        cb.assert_called_once()


def test_strategy_d_tkinter_fallback():
    """Simula un entorno donde Flet FilePicker falla y se activa el fallback a Tkinter (Camino C)."""
    class BrokenPicker:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Flet FilePicker no soportado en este cliente")

    with patch.object(ft, "FilePicker", BrokenPicker):
        cb = MagicMock()
        picker = get_file_picker(cb)
        assert picker is not None
        assert isinstance(picker, TkinterFilePicker)


def test_lazy_instantiation_settings_page():
    """
    CAPA 1: Verifica que al inicializar SettingsPage NO se instancie ningún FilePicker
    ni se agregue a services u overlay de la página.
    """
    page_mock = MagicMock(spec=ft.Page)
    page_mock.services = []
    page_mock.overlay = []

    sp = SettingsPage(page_mock)
    assert sp._bg_file_picker is None
    assert len(page_mock.services) == 0
    assert len(page_mock.overlay) == 0


def test_pick_background_file_triggers_dialog():
    """Verifica que el botón de elegir imagen o GIF dispare el diálogo perezoso."""
    page_mock = MagicMock(spec=ft.Page)
    sp = SettingsPage(page_mock)

    with patch("ui.pages.settings_page.open_file_picker_dialog") as mock_open:
        sp._open_background_picker()
        mock_open.assert_called_once()
        kwargs = mock_open.call_args.kwargs
        assert kwargs["on_result_callback"] == sp._on_bg_file_picked
        assert "png" in kwargs["allowed_extensions"]
        assert "gif" in kwargs["allowed_extensions"]


def test_forced_tkinter_fallback_on_flet_failure(monkeypatch):
    """
    CAPA 2: Monkeypatch temporal que hace fallar el FilePicker de Flet y
    valida que el archivo se seleccione y normalice idénticamente vía Tkinter.
    """
    # Hacer que ft.FilePicker lance excepción al instanciarse
    def _broken_picker(*args, **kwargs):
        raise RuntimeError("Unknown control: FilePicker simulado")

    monkeypatch.setattr(ft, "FilePicker", _broken_picker)

    # Mockear pick_file_tkinter para devolver una ruta simulada
    with patch("aura.ui.file_picker_compat.pick_file_tkinter", return_value="C:/assets/fondo.png"):
        received_events = []
        def on_result(res):
            received_events.append(res)

        open_file_picker_dialog(on_result_callback=on_result)

        assert len(received_events) == 1
        assert len(received_events[0].files) == 1
        assert received_events[0].files[0].path == "C:/assets/fondo.png"


def test_dialog_cancel_returns_empty_cleanly():
    """Valida que al cancelar el diálogo (retorno None de Tkinter) no ocurra ningún error."""
    with patch("aura.ui.file_picker_compat.pick_file_tkinter", return_value=None):
        received_events = []
        def on_result(res):
            received_events.append(res)

        open_file_picker_dialog(on_result_callback=on_result)

        assert len(received_events) == 1
        assert len(received_events[0].files) == 0


def test_settings_page_open_close_repeatedly():
    """Valida que abrir y cerrar Configuración 5 veces seguidas no cause fugas ni errores."""
    page_mock = MagicMock(spec=ft.Page)
    sp = SettingsPage(page_mock)

    for _ in range(5):
        sp.on_enter()
        sp.on_leave()


def test_flet_client_alignment():
    """CAPA 3: Valida detección de versión y ruta del cliente."""
    ver = get_flet_package_version()
    assert ver == "0.86.5"

    path = get_flet_client_path(ver)
    assert path is not None
    assert "flet-desktop-full-0.86.5" in path
    assert isinstance(clean_stale_flet_caches(ver), list)

    diag = align_and_log_flet_client()
    assert diag["version"] == "0.86.5"
    assert diag["client_path"] == path

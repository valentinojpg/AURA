"""
AURA — FilePicker Compatibility Layer (Fase 78 Fix Ronda 2).

Provee compatibilidad en tiempo de ejecución para selección de archivos:
- CAPA 1: Instanciación perezosa (bajo demanda en el click).
- CAPA 2: Doble camino de ejecución con fallback transparente a Tkinter (stdlib).
- CAPA 3: Diagnóstico y alineación de API para Flet 0.86.5 pinneada.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import inspect
from pathlib import Path
import threading
from typing import Any, Callable, Optional, Union

import flet as ft

from utils.logger import get_logger

_logger = get_logger("aura.ui.file_picker_compat")


@dataclass
class FilePickerCompatFile:
    """Representación normalizada de un archivo seleccionado."""
    path: str
    name: str = ""
    size: int = 0
    bytes: Optional[bytes] = None

    def __post_init__(self) -> None:
        if not self.name and self.path:
            self.name = Path(self.path).name


class FilePickerCompatResult:
    """Evento normalizado compatible con la API de on_result."""
    def __init__(self, files: Optional[Union[list[Any], Any]] = None, data: Any = None) -> None:
        self.data = data
        self.files: list[Any] = []
        if files is not None:
            if isinstance(files, (list, tuple)):
                for item in files:
                    if hasattr(item, "path") and item.path:
                        self.files.append(item)
                    elif isinstance(item, str) and item:
                        self.files.append(FilePickerCompatFile(path=item))
                    elif isinstance(item, dict) and "path" in item:
                        self.files.append(
                            FilePickerCompatFile(
                                path=str(item.get("path", "")),
                                name=str(item.get("name", "")),
                                size=int(item.get("size", 0)),
                            )
                        )
                    elif item is not None:
                        self.files.append(item)
            elif hasattr(files, "files"):
                raw_list = getattr(files, "files", []) or []
                for item in raw_list:
                    if hasattr(item, "path"):
                        self.files.append(item)
                    elif isinstance(item, str):
                        self.files.append(FilePickerCompatFile(path=item))
                    else:
                        self.files.append(item)
            elif hasattr(files, "path"):
                self.files = [files]
            elif isinstance(files, str) and files:
                self.files = [FilePickerCompatFile(path=files)]

    def __repr__(self) -> str:
        return f"FilePickerCompatResult(files={self.files!r})"


def pick_file_tkinter(
    dialog_title: str = "Seleccionar imagen o GIF",
    filetypes: Optional[tuple] = None,
    allowed_extensions: Optional[list[str]] = None,
) -> Optional[str]:
    """
    Abre un diálogo nativo modal de selección de archivos utilizando tkinter (stdlib).
    Asegura que el root esté oculto, en primer plano y se destruya limpiamente
    sin dejar procesos colgados ni alterar el foco de AURA.
    """
    if filetypes is None:
        if allowed_extensions:
            ext_pattern = " ".join(f"*.{ext.lstrip('.')}" for ext in allowed_extensions)
            filetypes = (
                ("Archivos permitidos", ext_pattern),
                ("Todos los archivos", "*.*"),
            )
        else:
            filetypes = (
                ("Imágenes", "*.png *.jpg *.jpeg *.gif *.webp *.bmp"),
                ("Todos los archivos", "*.*"),
            )

    root = None
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
            root.focus_force()
        except Exception:
            pass

        selected_path = filedialog.askopenfilename(
            parent=root,
            title=dialog_title,
            filetypes=filetypes,
        )
        return selected_path if selected_path else None
    except Exception as ex:
        _logger.warning("Error en diálogo tkinter askopenfilename: %s", ex)
        return None
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass


class TkinterFilePicker:
    """
    Control de selección de archivos basado en tkinter (stdlib).
    Provee una interfaz idéntica a ft.FilePicker para fallback transparente.
    """

    def __init__(
        self,
        on_result: Optional[Callable[[Any], None]] = None,
        page: Optional[ft.Page] = None,
        **_kwargs: Any,
    ) -> None:
        self._on_result_callback = on_result
        self._compat_page = page

    def set_on_result(self, callback: Callable[[Any], None]) -> None:
        self._on_result_callback = callback

    def set_page(self, page: ft.Page) -> None:
        self._compat_page = page

    def pick_files(
        self,
        dialog_title: str = "Seleccionar archivo",
        allowed_extensions: Optional[list[str]] = None,
        filetypes: Optional[tuple] = None,
        **_kwargs: Any,
    ) -> None:
        """Abre diálogo modal usando tkinter y despacha resultado al callback."""
        _logger.info("Diálogo de archivos abierto usando camino: tkinter")
        path = pick_file_tkinter(
            dialog_title=dialog_title,
            allowed_extensions=allowed_extensions,
            filetypes=filetypes,
        )
        if self._on_result_callback:
            if path:
                self._on_result_callback(FilePickerCompatResult(files=[FilePickerCompatFile(path=path)]))
            else:
                self._on_result_callback(FilePickerCompatResult(files=[]))


class CompatibleFilePicker(ft.FilePicker):
    """
    Subclase de ft.FilePicker que reconcilia la API asíncrona basada en corrutinas
    con el patrón tradicional basado en callback síncrono on_result, incorporando
    fallback automático a Tkinter ante cualquier falla del cliente Flet.
    """

    def __init__(
        self,
        on_result: Optional[Callable[[Any], None]] = None,
        page: Optional[ft.Page] = None,
        **kwargs: Any,
    ) -> None:
        super_kwargs: dict[str, Any] = {}
        try:
            sig = inspect.signature(super().__init__)
            for k, v in kwargs.items():
                if k in sig.parameters:
                    super_kwargs[k] = v
        except Exception:
            pass

        super().__init__(**super_kwargs)
        self._on_result_callback = on_result
        self._compat_page = page

    def set_on_result(self, callback: Callable[[Any], None]) -> None:
        """Configura el callback de resultado."""
        self._on_result_callback = callback

    def set_page(self, page: ft.Page) -> None:
        """Asigna la página asociada."""
        self._compat_page = page

    def _fallback_to_tkinter(self, *args: Any, **kwargs: Any) -> None:
        """Ejecuta el selector Tkinter cuando Flet falla o es rechazado por el cliente."""
        _logger.info("FilePicker de Flet no disponible; ejecutando fallback vía camino: tkinter")
        title = kwargs.get("dialog_title", "Seleccionar archivo")
        exts = kwargs.get("allowed_extensions", None)
        path = pick_file_tkinter(dialog_title=title, allowed_extensions=exts)
        if self._on_result_callback:
            if path:
                self._on_result_callback(FilePickerCompatResult(files=[FilePickerCompatFile(path=path)]))
            else:
                self._on_result_callback(FilePickerCompatResult(files=[]))

    def pick_files(self, *args: Any, **kwargs: Any) -> Any:
        """
        Ejecuta la selección de archivos adaptando el retorno al callback on_result.
        Si la versión subyacente es una corrutina async, se ejecuta en el loop de Flet.
        Si falla en cualquier punto, conmuta automáticamente a Tkinter.
        """
        page = getattr(self, "page", None) or self._compat_page

        try:
            super_pick = getattr(super(), "pick_files", None)
            if super_pick:
                sig = inspect.signature(super_pick)
                if "on_result" in sig.parameters and "on_result" not in kwargs:
                    kwargs["on_result"] = self._on_result_callback
                    _logger.info("Diálogo de archivos abierto usando camino: flet")
                    return super().pick_files(*args, **kwargs)
        except Exception as ex:
            _logger.warning("Fallo en super().pick_files: %s", ex)
            return self._fallback_to_tkinter(*args, **kwargs)

        is_coro = False
        try:
            is_coro = inspect.iscoroutinefunction(super().pick_files)
        except Exception:
            pass

        if is_coro:
            async def _coroutine_runner() -> None:
                try:
                    raw_result = await super(CompatibleFilePicker, self).pick_files(*args, **kwargs)
                    _logger.info("Diálogo de archivos completado usando camino: flet")
                    if self._on_result_callback:
                        event = FilePickerCompatResult(files=raw_result)
                        self._on_result_callback(event)
                except Exception as ex:
                    _logger.warning("Excepción en ejecución asíncrona de pick_files: %s; activando fallback tkinter", ex)
                    self._fallback_to_tkinter(*args, **kwargs)

            _logger.info("Diálogo de archivos iniciado usando camino: flet")

            # Intentar ejecutar con page.run_task si está disponible
            if page and hasattr(page, "run_task") and callable(page.run_task):
                try:
                    return page.run_task(_coroutine_runner)
                except Exception as ex:
                    _logger.debug("page.run_task no pudo iniciar la tarea: %s", ex)

            # Intentar ejecutar con loop de conexión Flet
            conn = getattr(getattr(page, "session", None), "connection", None)
            loop = getattr(conn, "loop", None)
            if loop and loop.is_running():
                return asyncio.run_coroutine_threadsafe(_coroutine_runner(), loop)

            # Fallback a hilo en segundo plano con loop propio
            def _thread_target() -> None:
                try:
                    asyncio.run(_coroutine_runner())
                except Exception as ex:
                    _logger.warning("Error en hilo background de pick_files: %s", ex)
                    self._fallback_to_tkinter(*args, **kwargs)

            t = threading.Thread(target=_thread_target, daemon=True)
            t.start()
            return t
        else:
            # Versión síncrona clásica
            try:
                _logger.info("Diálogo de archivos abierto usando camino: flet")
                res = super().pick_files(*args, **kwargs)
                if res is not None and self._on_result_callback:
                    self._on_result_callback(FilePickerCompatResult(files=res))
                return res
            except Exception as ex:
                _logger.warning("Error síncrono en pick_files: %s; activando fallback tkinter", ex)
                return self._fallback_to_tkinter(*args, **kwargs)


def diagnose_file_picker_api() -> dict[str, Any]:
    """
    Inspecciona y loguea la versión de Flet, la firma real de ft.FilePicker.__init__
    y ft.FilePicker.pick_files, y los atributos de eventos disponibles.
    """
    version = getattr(ft, "__version__", "desconocida")
    has_picker = hasattr(ft, "FilePicker")
    info: dict[str, Any] = {
        "flet_version": version,
        "has_file_picker": has_picker,
        "init_signature": None,
        "pick_files_signature": None,
        "pick_files_is_coro": False,
        "has_on_result": False,
        "has_on_change": False,
        "has_result": False,
        "strategy": None,
    }

    if not has_picker:
        _logger.error("Diagnóstico Flet %s: ft.FilePicker NO existe.", version)
        return info

    try:
        sig_init = inspect.signature(ft.FilePicker.__init__)
        info["init_signature"] = str(sig_init)
        info["has_on_result_kwarg"] = "on_result" in sig_init.parameters
    except Exception as ex:
        _logger.warning("Error inspeccionando FilePicker.__init__: %s", ex)

    try:
        sig_pick = inspect.signature(ft.FilePicker.pick_files)
        info["pick_files_signature"] = str(sig_pick)
        info["pick_files_is_coro"] = inspect.iscoroutinefunction(ft.FilePicker.pick_files)
    except Exception as ex:
        _logger.warning("Error inspeccionando FilePicker.pick_files: %s", ex)

    try:
        inst = ft.FilePicker()
        info["has_on_result"] = hasattr(inst, "on_result")
        info["has_on_change"] = hasattr(inst, "on_change")
        info["has_result"] = hasattr(inst, "result")
    except Exception as ex:
        _logger.debug("No se pudo instanciar ft.FilePicker() para diagnosticar atributos: %s", ex)

    _logger.info(
        "Diagnóstico FilePicker: Flet %s | __init__=%s | pick_files=%s (coro=%s) | on_result=%s | on_change=%s | result=%s",
        version,
        info.get("init_signature"),
        info.get("pick_files_signature"),
        info.get("pick_files_is_coro"),
        info.get("has_on_result"),
        info.get("has_on_change"),
        info.get("has_result"),
    )
    return info


def _attach_picker_to_page(picker: Any, page: ft.Page) -> None:
    """
    Adjunta el picker ÚNICAMENTE a la colección de services de la página si es
    compatible. NUNCA a overlay para evitar 'Unknown control: FilePicker' en el cliente.
    """
    if not page or not picker:
        return
    try:
        if hasattr(page, "services") and isinstance(page.services, list):
            if picker not in page.services:
                page.services.append(picker)
    except Exception as ex:
        _logger.debug("Aviso al adjuntar FilePicker a services: %s", ex)


def get_file_picker(
    on_result_callback: Optional[Callable[[Any], None]] = None,
    page: Optional[ft.Page] = None,
) -> Union[ft.FilePicker, TkinterFilePicker]:
    """
    Factory en tiempo de ejecución que detecta y entrega una instancia funcional
    de FilePicker compatible con la versión activa de Flet, con fallback seguro
    a TkinterFilePicker ante cualquier incompatibilidad.

    Estrategias de resolución:
    a. on_result aceptado en el constructor -> instanciar directamente.
    b. pick_files es corrutina o Service -> envolver en CompatibleFilePicker.
    c. on_change / result como atributos -> instanciar y conectar handler.
    d. Fallback Tkinter (Camino C) -> retorna TkinterFilePicker.
    """
    if not hasattr(ft, "FilePicker"):
        _logger.info("ft.FilePicker no existe en Flet; usando fallback TkinterFilePicker.")
        return TkinterFilePicker(on_result=on_result_callback, page=page)

    # Estrategia a: on_result aceptado en el constructor
    try:
        init_sig = inspect.signature(ft.FilePicker.__init__)
        if "on_result" in init_sig.parameters:
            try:
                picker = ft.FilePicker(on_result=on_result_callback)
                if page:
                    _attach_picker_to_page(picker, page)
                _logger.debug("FilePicker creado con Estrategia A (constructor on_result).")
                return picker
            except Exception as ex:
                _logger.warning("Fallo en Estrategia A para FilePicker: %s", ex)
    except Exception as ex:
        _logger.debug("No se pudo validar Estrategia A: %s", ex)

    # Estrategia b: pick_files es corrutina o acepta callback o retorna resultado
    try:
        pick_fn = getattr(ft.FilePicker, "pick_files", None)
        if pick_fn is not None:
            is_coro = inspect.iscoroutinefunction(pick_fn)
            pick_sig = inspect.signature(pick_fn)
            has_cb_param = "on_result" in pick_sig.parameters or "callback" in pick_sig.parameters

            if is_coro or has_cb_param or issubclass(ft.FilePicker, ft.Service):
                try:
                    picker = CompatibleFilePicker(on_result=on_result_callback, page=page)
                    if page:
                        _attach_picker_to_page(picker, page)
                    _logger.debug("FilePicker creado con Estrategia B (CompatibleFilePicker).")
                    return picker
                except Exception as ex:
                    _logger.warning("Fallo en Estrategia B para FilePicker: %s", ex)
    except Exception as ex:
        _logger.debug("No se pudo validar Estrategia B: %s", ex)

    # Estrategia c: atributos on_change / result
    try:
        raw_picker = ft.FilePicker()
        if hasattr(raw_picker, "on_change"):
            def _on_change_proxy(e: Any) -> None:
                files_res = getattr(raw_picker, "result", None) or getattr(e, "files", None) or e
                if on_result_callback:
                    on_result_callback(FilePickerCompatResult(files=files_res))

            setattr(raw_picker, "on_change", _on_change_proxy)
            if page:
                _attach_picker_to_page(raw_picker, page)
            _logger.debug("FilePicker creado con Estrategia C (on_change / result).")
            return raw_picker
    except Exception as ex:
        _logger.debug("No se pudo validar Estrategia C: %s", ex)

    # Fallback transparente a TkinterFilePicker (stdlib)
    _logger.info("Estrategias de Flet no viables; retornando TkinterFilePicker.")
    return TkinterFilePicker(on_result=on_result_callback, page=page)


def open_file_picker_dialog(
    on_result_callback: Callable[[FilePickerCompatResult], None],
    page: Optional[ft.Page] = None,
    dialog_title: str = "Seleccionar imagen o GIF",
    allowed_extensions: Optional[list[str]] = None,
    filetypes: Optional[tuple] = None,
) -> None:
    """
    Función de alto nivel para abrir el diálogo de selección de archivos
    de forma completamente perezosa (CAPA 1) con fallback transparente a Tkinter (CAPA 2).
    """
    picker: Optional[Union[ft.FilePicker, TkinterFilePicker]] = None
    try:
        picker = get_file_picker(on_result_callback=on_result_callback, page=page)
        if isinstance(picker, TkinterFilePicker):
            picker.pick_files(
                dialog_title=dialog_title,
                allowed_extensions=allowed_extensions,
                filetypes=filetypes,
            )
            return

        # Intentar Flet FilePicker
        picker.pick_files(
            dialog_title=dialog_title,
            allowed_extensions=allowed_extensions,
            file_type=ft.FilePickerFileType.CUSTOM if allowed_extensions else ft.FilePickerFileType.ANY,
        )
    except Exception as ex:
        _logger.warning("Fallo al abrir selector de Flet (%s); ejecutando camino: tkinter", ex)
        path = pick_file_tkinter(
            dialog_title=dialog_title,
            allowed_extensions=allowed_extensions,
            filetypes=filetypes,
        )
        if on_result_callback:
            if path:
                on_result_callback(FilePickerCompatResult(files=[FilePickerCompatFile(path=path)]))
            else:
                on_result_callback(FilePickerCompatResult(files=[]))

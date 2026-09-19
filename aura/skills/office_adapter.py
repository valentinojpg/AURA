# -*- coding: utf-8 -*-
"""
================================================================================
AURA — Adapter COM para Office (Word / Excel) (Fase 72)
================================================================================
Proporciona integración nativa por COM con Microsoft Office (Word y Excel):
- Conexión estricta a instancias abiertas en ejecución (GetActiveObject).
  NUNCA crea una segunda instancia invisible de fondo.
- Operaciones soportadas:
  - write: Escribe en la selección actual (Selection.TypeText).
  - read: Lee el texto del documento activo (Content.Text / ActiveCell).
  - save_as: Guarda en ruta absoluta con formato nativo (SaveAs2 / SaveAs).
  - close: Cierra el documento/libro opcionalmente.
- Manejo de errores amigable:
  Convierte códigos de error COM en mensajes claros para el usuario sin stacktrace.
================================================================================
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional, Tuple

from skills.skill_base import SkillResult
from utils.logger import get_logger

_logger = get_logger("aura.skills.office_adapter")

try:
    import win32com.client
    import pywintypes
except ImportError:
    win32com = None
    pywintypes = None


def _format_com_error(err: Exception, action_desc: str) -> str:
    """Formatea un error COM de forma legible sin volcar stacktraces crudos."""
    err_str = str(err)
    if "RPC_E_CALL_REJECTED" in err_str or "-2147418111" in err_str:
        return f"La aplicación Office está ocupada o tiene un cuadro de diálogo abierto al intentar {action_desc}."
    if "Documento protegido" in err_str or "protect" in err_str.lower():
        return f"El documento está protegido contra escritura o es de solo lectura al intentar {action_desc}."
    if "-2147221021" in err_str or "MK_E_UNAVAILABLE" in err_str:
        return f"La aplicación Office no se encuentra activa en el sistema para {action_desc}."
    if "Command failed" in err_str:
        return f"No se pudo completar la acción de {action_desc} en Office."
    
    clean_msg = err_str.split("\n")[0].strip("()[], ")
    return f"Error de comunicación COM al {action_desc}: {clean_msg}"


class OfficeAdapter:
    """Adaptador de operaciones COM para Microsoft Word y Excel."""

    # ─────────────────────────────────────────────────────────────────────────
    # Conexión a Instancias Activas (GetActiveObject)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_active_word_app(retries: int = 5, delay: float = 0.5) -> Tuple[Optional[Any], Optional[str]]:
        """
        Obtiene la instancia activa de Word registrada en la Running Object Table (ROT).
        NUNCA llama a Dispatch() para evitar crear instancias invisibles en segundo plano.
        """
        if win32com is None:
            return None, "La librería pywin32 no está disponible en el entorno."

        for attempt in range(retries):
            try:
                app = win32com.client.GetActiveObject("Word.Application")
                return app, None
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(delay)
                else:
                    _logger.debug(f"GetActiveObject Word no disponible tras {retries} intentos: {e}")
                    return None, "No se encontró ninguna instancia activa de Microsoft Word en ejecución. Asegurate de que Word esté abierto."

    @staticmethod
    def get_active_excel_app(retries: int = 5, delay: float = 0.5) -> Tuple[Optional[Any], Optional[str]]:
        """
        Obtiene la instancia activa de Excel registrada en la Running Object Table (ROT).
        NUNCA llama a Dispatch() para evitar crear instancias invisibles en segundo plano.
        """
        if win32com is None:
            return None, "La librería pywin32 no está disponible en el entorno."

        for attempt in range(retries):
            try:
                app = win32com.client.GetActiveObject("Excel.Application")
                return app, None
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(delay)
                else:
                    _logger.debug(f"GetActiveObject Excel no disponible tras {retries} intentos: {e}")
                    return None, "No se encontró ninguna instancia activa de Microsoft Excel en ejecución. Asegurate de que Excel esté abierto."

    # ─────────────────────────────────────────────────────────────────────────
    # Escritura (write)
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def write(cls, app_name: str, text: str) -> SkillResult:
        """Escribe texto dentro de la aplicación Office activa."""
        target = app_name.lower().strip()
        if "word" in target or target == "winword":
            return cls.write_word(text)
        elif "excel" in target:
            return cls.write_excel(text)
        else:
            return SkillResult(
                success=False,
                error=f"OfficeAdapter no soporta la aplicación '{app_name}'.",
            )

    @classmethod
    def write_word(cls, text: str, app: Optional[Any] = None) -> SkillResult:
        """Escribe texto en la instancia activa de Microsoft Word."""
        if app is None:
            app, err = cls.get_active_word_app()
            if not app:
                return SkillResult(success=False, error=err or "Word no disponible.")

        try:
            app.Visible = True
            # Si no hay documento abierto, crear uno en blanco
            if app.Documents.Count == 0:
                app.Documents.Add()

            app.Selection.TypeText(text)
            preview = text[:40] + ("..." if len(text) > 40 else "")
            return SkillResult(
                success=True,
                output=f"✍️ Escrito vía COM en Word: {preview}",
                data={"app": "word", "text": text},
            )
        except Exception as e:
            msg = _format_com_error(e, "escribir en Word")
            return SkillResult(success=False, error=msg)

    @classmethod
    def write_excel(cls, text: str, app: Optional[Any] = None) -> SkillResult:
        """Escribe texto en la celda activa de Microsoft Excel."""
        if app is None:
            app, err = cls.get_active_excel_app()
            if not app:
                return SkillResult(success=False, error=err or "Excel no disponible.")

        try:
            app.Visible = True
            if app.Workbooks.Count == 0:
                app.Workbooks.Add()

            app.ActiveCell.Value = text
            preview = text[:40] + ("..." if len(text) > 40 else "")
            return SkillResult(
                success=True,
                output=f"✍️ Escrito vía COM en Excel: {preview}",
                data={"app": "excel", "text": text},
            )
        except Exception as e:
            msg = _format_com_error(e, "escribir en Excel")
            return SkillResult(success=False, error=msg)

    # ─────────────────────────────────────────────────────────────────────────
    # Lectura (read)
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def read(cls, app_name: str) -> SkillResult:
        """Lee el contenido de texto de la aplicación Office activa."""
        target = app_name.lower().strip()
        if "word" in target or target == "winword":
            return cls.read_word()
        elif "excel" in target:
            return cls.read_excel()
        else:
            return SkillResult(
                success=False,
                error=f"OfficeAdapter no soporta la aplicación '{app_name}'.",
            )

    @classmethod
    def read_word(cls, app: Optional[Any] = None) -> SkillResult:
        """Lee el contenido completo del documento activo de Word."""
        if app is None:
            app, err = cls.get_active_word_app()
            if not app:
                return SkillResult(success=False, error=err or "Word no disponible.")

        try:
            if app.Documents.Count == 0:
                return SkillResult(
                    success=False,
                    error="Word no tiene ningún documento abierto para leer.",
                )
            doc = app.ActiveDocument
            content_text = doc.Content.Text
            return SkillResult(
                success=True,
                output=content_text,
                data={"app": "word", "text": content_text},
            )
        except Exception as e:
            msg = _format_com_error(e, "leer documento de Word")
            return SkillResult(success=False, error=msg)

    @classmethod
    def read_excel(cls, app: Optional[Any] = None) -> SkillResult:
        """Lee el contenido de la celda activa de Excel."""
        if app is None:
            app, err = cls.get_active_excel_app()
            if not app:
                return SkillResult(success=False, error=err or "Excel no disponible.")

        try:
            if app.Workbooks.Count == 0:
                return SkillResult(
                    success=False,
                    error="Excel no tiene ningún libro abierto para leer.",
                )
            val = str(app.ActiveCell.Value or "")
            return SkillResult(
                success=True,
                output=val,
                data={"app": "excel", "text": val},
            )
        except Exception as e:
            msg = _format_com_error(e, "leer libro de Excel")
            return SkillResult(success=False, error=msg)

    # ─────────────────────────────────────────────────────────────────────────
    # Guardar como (save_as)
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def save_as(cls, app_name: str, target_path: Path | str) -> SkillResult:
        """Guarda el documento o libro activo en la ruta indicada vía COM."""
        target = app_name.lower().strip()
        if "word" in target or target == "winword":
            return cls.save_as_word(target_path)
        elif "excel" in target:
            return cls.save_as_excel(target_path)
        else:
            return SkillResult(
                success=False,
                error=f"OfficeAdapter no soporta guardado para '{app_name}'.",
            )

    @classmethod
    def save_as_word(cls, target_path: Path | str, app: Optional[Any] = None) -> SkillResult:
        """Guarda el documento activo de Word como archivo .docx mediante SaveAs2."""
        if app is None:
            app, err = cls.get_active_word_app()
            if not app:
                return SkillResult(success=False, error=err or "Word no disponible.")

        try:
            if app.Documents.Count == 0:
                return SkillResult(
                    success=False,
                    error="No hay ningún documento abierto en Word para guardar.",
                )

            doc = app.ActiveDocument
            path_obj = Path(target_path).resolve()
            if not path_obj.suffix:
                path_obj = path_obj.with_suffix(".docx")

            path_obj.parent.mkdir(parents=True, exist_ok=True)

            # wdFormatXMLDocument = 16 (formato estándar .docx)
            doc.SaveAs2(FileName=str(path_obj), FileFormat=16)

            return SkillResult(
                success=True,
                output=f"💾 Guardado vía COM en Word: {path_obj}",
                data={"app": "word", "path": str(path_obj)},
            )
        except Exception as e:
            msg = _format_com_error(e, "guardar documento de Word")
            return SkillResult(success=False, error=msg)

    @classmethod
    def save_as_excel(cls, target_path: Path | str, app: Optional[Any] = None) -> SkillResult:
        """Guarda el libro activo de Excel como archivo .xlsx mediante SaveAs."""
        if app is None:
            app, err = cls.get_active_excel_app()
            if not app:
                return SkillResult(success=False, error=err or "Excel no disponible.")

        try:
            if app.Workbooks.Count == 0:
                return SkillResult(
                    success=False,
                    error="No hay ningún libro abierto en Excel para guardar.",
                )

            wb = app.ActiveWorkbook
            path_obj = Path(target_path).resolve()
            if not path_obj.suffix:
                path_obj = path_obj.with_suffix(".xlsx")

            path_obj.parent.mkdir(parents=True, exist_ok=True)

            # xlOpenXMLWorkbook = 51 (formato estándar .xlsx)
            wb.SaveAs(Filename=str(path_obj), FileFormat=51)

            return SkillResult(
                success=True,
                output=f"💾 Guardado vía COM en Excel: {path_obj}",
                data={"app": "excel", "path": str(path_obj)},
            )
        except Exception as e:
            msg = _format_com_error(e, "guardar libro de Excel")
            return SkillResult(success=False, error=msg)

    # ─────────────────────────────────────────────────────────────────────────
    # Cierre (close)
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def close(cls, app_name: str, save_changes: bool = False) -> SkillResult:
        """Cierra el documento o libro activo de la aplicación Office."""
        target = app_name.lower().strip()
        if "word" in target or target == "winword":
            return cls.close_word(save_changes=save_changes)
        elif "excel" in target:
            return cls.close_excel(save_changes=save_changes)
        else:
            return SkillResult(
                success=False,
                error=f"OfficeAdapter no soporta cierre para '{app_name}'.",
            )

    @classmethod
    def close_word(cls, save_changes: bool = False, app: Optional[Any] = None) -> SkillResult:
        """Cierra el documento activo de Word."""
        if app is None:
            app, err = cls.get_active_word_app()
            if not app:
                return SkillResult(success=False, error=err or "Word no disponible.")

        try:
            if app.Documents.Count > 0:
                app.ActiveDocument.Close(SaveChanges=save_changes)
            return SkillResult(
                success=True,
                output="Documento de Word cerrado correctamente vía COM.",
                data={"app": "word"},
            )
        except Exception as e:
            msg = _format_com_error(e, "cerrar documento de Word")
            return SkillResult(success=False, error=msg)

    @classmethod
    def close_excel(cls, save_changes: bool = False, app: Optional[Any] = None) -> SkillResult:
        """Cierra el libro activo de Excel."""
        if app is None:
            app, err = cls.get_active_excel_app()
            if not app:
                return SkillResult(success=False, error=err or "Excel no disponible.")

        try:
            if app.Workbooks.Count > 0:
                app.ActiveWorkbook.Close(SaveChanges=save_changes)
            return SkillResult(
                success=True,
                output="Libro de Excel cerrado correctamente vía COM.",
                data={"app": "excel"},
            )
        except Exception as e:
            msg = _format_com_error(e, "cerrar libro de Excel")
            return SkillResult(success=False, error=msg)

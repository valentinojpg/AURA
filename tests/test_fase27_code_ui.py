"""
AURA — Pruebas Automatizadas de la Fase 27 (UI del Asistente de Programación)

Verifica la interfaz gráfica interactiva de CodePage en Flet:
1. Inicialización y construcción del layout dividido (editor y resultados).
2. Selección interactiva de las 9 acciones de programación y adaptación dinámica de inputs.
3. Carga de código desde archivos locales con codificación explícita UTF-8.
4. Carga de ejemplos didácticos y limpieza de estados.
5. Análisis estático AST en vivo (sintaxis válida, error sintáctico y no Python).
6. Ejecución sincrónica y streaming reactivo con Mock AI Provider.
7. Cancelación no bloqueante de streaming.
8. Operaciones de portapapeles, reemplazo en editor y guardado en disco con UTF-8.
9. Integración en MainWindow y Sidebar de navegación.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import flet as ft
import pytest

from ai.provider_interface import AIProvider, ChatMessage, ChatResponse
from core.code_assistant import CodeAction, CodeAssistant, CodeTaskResult
from ui.components.sidebar import NAV_ITEMS, Sidebar
from ui.main_window import MainWindow, PAGE_TITLES
from ui.pages.code_page import ACTION_METADATA, CodeAssistantPage, CodePage


class FakeAIProvider(AIProvider):
    """Proveedor simulado para pruebas de la UI de código."""
    PROVIDER_NAME = "mock_provider"

    def __init__(self, response_text: str = "```python\ndef solucion():\n    return 42\n```"):
        self.response_text = response_text
        self.model = "mock:code"
        self.chat_calls = []

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    def check_status(self):
        return MagicMock(available=True)

    def list_models(self):
        return ["mock:code"]

    def chat(self, messages: list[ChatMessage], model: str | None = None, **kwargs) -> ChatResponse:
        self.chat_calls.append(messages)
        return ChatResponse(
            content=self.response_text,
            model=self.model,
            provider=self.PROVIDER_NAME,
        )

    def chat_stream(self, messages: list[ChatMessage], model: str | None = None, **kwargs):
        self.chat_calls.append(messages)
        chunks = ["### Explicación\n\n", "Acá está el código:\n\n", "```python\n", "def solucion():\n", "    return 42\n", "```\n"]
        for c in chunks:
            yield c


@pytest.fixture
def mock_page():
    page = MagicMock(spec=ft.Page)
    page.window = MagicMock()
    page.clipboard = ""
    return page


@pytest.fixture
def fake_assistant():
    provider = FakeAIProvider()
    return CodeAssistant(provider=provider)


@pytest.fixture
def code_page(mock_page, fake_assistant):
    page = CodePage(page=mock_page, assistant=fake_assistant)
    return page


class TestCodePageUIPhase27:
    """Suite de pruebas unitarias y de integración para la UI del Asistente de Programación."""

    def test_code_page_initialization(self, code_page, mock_page):
        """Verifica la correcta inicialización y presencia de todos los controles clave."""
        assert code_page is not None
        assert code_page.PAGE_NAME == "Código"
        assert code_page._selected_action == CodeAction.EXPLAIN
        assert code_page._code_editor is not None
        assert code_page._context_input is not None
        assert code_page._btn_execute is not None
        assert code_page._btn_cancel is not None
        assert code_page._result_markdown is not None
        assert code_page._streaming_switch is not None
        assert len(code_page._action_chips) == len(CodeAction)
        assert CodeAssistantPage is CodePage

    def test_code_page_action_selection(self, code_page):
        """Verifica que cambiar de acción adapte los chips, labels y botones."""
        for action in CodeAction:
            code_page._select_action(action)
            assert code_page._selected_action == action
            meta = ACTION_METADATA[action]
            assert meta["btn_label"] in code_page._btn_execute.content
            assert code_page._context_title_text.value == meta["context_label"]

    def test_code_page_load_sample_code(self, code_page):
        """Verifica la carga del código de ejemplo y su análisis."""
        code_page._load_sample_code()
        assert "def calculate_discount" in code_page._code_editor.value
        assert "class ShoppingCart" in code_page._code_editor.value
        assert code_page._detected_language == "python"
        assert "🟢 Sintaxis Python OK" in code_page._ast_badge_text.value
        assert "líneas" in code_page._stats_badge_text.value

    def test_code_page_clear_all(self, code_page):
        """Verifica que limpiar borre editor, contexto, ruta y resultados."""
        code_page._load_sample_code()
        code_page._context_input.value = "Algún error previo"
        code_page._result_markdown.value = "Resultado previo"

        code_page.clear_all()
        assert code_page._code_editor.value == ""
        assert code_page._context_input.value == ""
        assert code_page._file_path_field.value == ""
        assert code_page._result_markdown.value == ""
        assert code_page._ast_badge_text.value == "AST: Listo"

    def test_code_page_ast_analysis_syntax_error(self, code_page):
        """Verifica detección y reporte de errores sintácticos en el badge AST."""
        bad_code = "def foo(\n    print('error sin cerrar paréntesis'"
        code_page._code_editor.value = bad_code
        code_page._refresh_ast_analysis()

        assert "🔴 Error sintaxis" in code_page._ast_badge_text.value
        assert code_page._ast_badge_text.color == "#F87171"

    def test_code_page_ast_analysis_non_python(self, code_page):
        """Verifica comportamiento ante lenguajes que no son Python."""
        js_code = "function sumar(a, b) { return a + b; }"
        code_page._code_editor.value = js_code
        code_page._language_dropdown.value = "javascript"
        code_page._refresh_ast_analysis()

        assert "🔵 Lenguaje: JAVASCRIPT" in code_page._ast_badge_text.value
        assert code_page._ast_badge_text.color == "#4A9EFF"

    def test_code_page_load_file_utf8_success(self, code_page, tmp_path):
        """Verifica lectura de archivo en disco usando UTF-8 explícito."""
        test_file = tmp_path / "modulo_acentos.py"
        test_code = "# Código con tildes: función ágil, verificación rápida\ndef test_utf8():\n    return 'éxito 🚀'\n"
        test_file.write_text(test_code, encoding="utf-8")

        success = code_page.load_file(str(test_file))
        assert success is True
        assert code_page._code_editor.value == test_code
        assert code_page._detected_language == "python"
        assert "modulo_acentos.py" in code_page._feedback_status_text.value

    def test_code_page_load_file_nonexistent(self, code_page):
        """Verifica manejo seguro y amigable si el archivo no existe."""
        success = code_page.load_file("C:/ruta/inexistente/no_existe.py")
        assert success is False
        assert "Error" in code_page._feedback_status_text.value

    def test_code_page_empty_input_warning(self, code_page):
        """Verifica que no intente procesar si el editor está vacío."""
        code_page._code_editor.value = ""
        code_page._context_input.value = ""
        code_page.execute_current_action()

        assert code_page._is_running is False
        assert "ingresá código" in code_page._feedback_status_text.value

    def test_code_page_local_ast_action_execution(self, code_page):
        """Verifica que la acción ANALYZE se resuelva 100% de forma local en 0ms."""
        code_page._select_action(CodeAction.ANALYZE)
        code_page._code_editor.value = "class MiClase:\n    def mi_metodo(self):\n        pass\n"
        code_page.execute_current_action()

        assert code_page._is_running is False
        assert "Reporte de Análisis Estático Local" in code_page._result_markdown.value
        assert "🟢 Sintaxis Python Válida" in code_page._result_markdown.value
        assert "MiClase" in code_page._result_markdown.value
        assert "mi_metodo" in code_page._result_markdown.value
        assert "0ms" in code_page._result_meta_text.value

    def test_code_page_execute_action_streaming(self, code_page):
        """Verifica ejecución de streaming con actualización del buffer y markdown."""
        code_page._select_action(CodeAction.EXPLAIN)
        code_page._code_editor.value = "def suma(a, b): return a + b"
        code_page._streaming_switch.value = True

        # Ejecución directa del hilo para prueba síncrona
        code_page._run_action_thread(
            action=CodeAction.EXPLAIN,
            code=code_page._code_editor.value,
            language="python",
            context="",
            use_stream=True,
        )

        assert "Explicación" in code_page._result_markdown.value
        assert "def solucion():" in code_page._result_markdown.value
        assert code_page._last_result is not None
        assert code_page._last_result.extracted_code is not None
        assert "def solucion():" in code_page._last_result.extracted_code
        assert code_page._is_running is False

    def test_code_page_execute_action_non_streaming(self, code_page):
        """Verifica ejecución sin streaming llamando a chat()."""
        code_page._select_action(CodeAction.GENERATE_TESTS)
        code_page._code_editor.value = "def suma(a, b): return a + b"
        code_page._streaming_switch.value = False

        code_page._run_action_thread(
            action=CodeAction.GENERATE_TESTS,
            code=code_page._code_editor.value,
            language="python",
            context="",
            use_stream=False,
        )

        assert "def solucion():" in code_page._result_markdown.value
        assert code_page._last_result.success is True
        assert "mock_provider" in code_page._last_result.provider

    def test_code_page_cancel_streaming(self, code_page):
        """Verifica la solicitud de cancelación."""
        code_page._cancel_execution()
        assert code_page._cancel_requested is True
        assert "Deteniendo" in code_page._feedback_status_text.value

    def test_code_page_clipboard_operations(self, code_page, mock_page):
        """Verifica copiado de código y copiado total al portapapeles."""
        code_page._result_markdown.value = "### Código\n```python\nprint('hola mundo')\n```"
        code_page._last_result = CodeTaskResult(
            action="explain",
            language="python",
            content=code_page._result_markdown.value,
            success=True,
            extracted_code="print('hola mundo')",
        )

        # Copiar solo código
        code_page._copy_code_to_clipboard()
        assert mock_page.clipboard == "print('hola mundo')"
        assert "copiado al portapapeles" in code_page._feedback_status_text.value

        # Copiar todo
        code_page._copy_all_to_clipboard()
        assert mock_page.clipboard == code_page._result_markdown.value

    def test_code_page_load_result_into_editor(self, code_page):
        """Verifica reemplazo del editor con el código generado."""
        code_page._code_editor.value = "# Código viejo"
        code_page._last_result = CodeTaskResult(
            action="refactor",
            language="python",
            content="```python\ndef codigo_refactorizado():\n    pass\n```",
            success=True,
            extracted_code="def codigo_refactorizado():\n    pass",
        )

        code_page._load_result_into_editor()
        assert code_page._code_editor.value == "def codigo_refactorizado():\n    pass"
        assert "cargado en el editor" in code_page._feedback_status_text.value

    def test_code_page_save_result_to_file(self, code_page, tmp_path):
        """Verifica guardado en disco con codificación UTF-8."""
        target_file = tmp_path / "resultado.py"
        code_text = "# Salida generada con UTF-8: ñandú y café\ndef test(): pass\n"

        success = code_page.save_result_to_file(str(target_file), code_text)
        assert success is True
        assert target_file.exists()
        assert target_file.read_text(encoding="utf-8") == code_text

    def test_code_page_lifecycle(self, code_page):
        """Verifica ciclo de vida on_enter y on_leave."""
        code_page.on_enter()
        assert "IA:" in code_page._provider_badge_text.value

        code_page._cancel_requested = False
        code_page.on_leave()
        assert code_page._cancel_requested is True

    def test_main_window_and_sidebar_integration(self, mock_page):
        """Verifica que MainWindow registre CodePage y que Sidebar incluya la ruta de navegación."""
        # 1. Sidebar NAV_ITEMS incluye código
        nav_keys = [item[0] for item in NAV_ITEMS]
        assert "code" in nav_keys

        # 2. PAGE_TITLES incluye código
        assert "code" in PAGE_TITLES
        assert PAGE_TITLES["code"] == "Asistente de Programación"

        # 3. MainWindow registra CodePage
        mw = MainWindow()
        mw._main(mock_page)
        assert "code" in mw._pages
        assert isinstance(mw._pages["code"], CodePage)

        # 4. Navegación hacia code
        mw.navigate("code")
        assert mw._current_page_id == "code"
        assert mw._content_container.content is mw._pages["code"]

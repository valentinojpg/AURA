"""
AURA — Tests de Fase 26: Núcleo del Asistente de Programación

Valida todas las capacidades del motor central de asistencia de código:
1. Detección automática de lenguajes por extensión y heurística sintáctica.
2. Extracción precisa de bloques de código en Markdown.
3. Análisis estático local ultrarrápido (AST para Python y métricas generales).
4. Construcción de prompts especializados para estudiantes y desarrolladores.
5. Ejecución sincrónica y en streaming de todas las acciones:
   - Explicar código
   - Explicar errores / stacktraces
   - Detectar bugs y vulnerabilidades
   - Generar documentación y docstrings
   - Generar README.md para repositorios
   - Añadir comentarios explicativos
   - Generar tests unitarios
   - Refactorizar código
   - Análisis local
6. Procesamiento de archivos de código en disco con codificación UTF-8 explícita.
"""

from __future__ import annotations

import json
import tempfile
import shutil
import unittest
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock

from core.code_assistant import (
    CodeAction,
    CodeAnalysis,
    CodeTaskResult,
    CodeAssistant,
    code_assistant,
    detect_language,
    extract_code_blocks,
    extract_first_code_block,
    analyze_code,
    build_prompt,
)
from ai.provider_interface import AIProvider, ChatMessage, ChatResponse


class MockAIProvider(AIProvider):
    """Proveedor mock tipado para pruebas del asistente de programación."""
    PROVIDER_NAME = "mock"

    def __init__(self, response_text: str = "Respuesta mock"):
        self.response_text = response_text
        self.calls: list[list[ChatMessage]] = []

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    def check_status(self):
        return MagicMock(available=True)

    def list_models(self):
        return ["mock:default"]

    def chat(self, messages: list[ChatMessage], model: str | None = None, **kwargs) -> ChatResponse:
        self.calls.append(messages)
        return ChatResponse(
            content=self.response_text,
            model="mock:test",
            provider="mock",
            tokens_prompt=10,
            tokens_response=20,
        )

    def chat_stream(self, messages: list[ChatMessage], model: str | None = None, **kwargs) -> Iterator[str]:
        self.calls.append(messages)
        # Yield en fragmentos
        parts = self.response_text.split(" ")
        for p in parts:
            yield p + " "


class TestCodeAssistantPhase26(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="aura_code_test_")
        self.mock_provider = MockAIProvider(
            "Aquí está la explicación:\n```python\ndef saludar():\n    return 'hola'\n```"
        )
        self.assistant = CodeAssistant(provider=self.mock_provider)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ── 1. Detección de Lenguaje ─────────────────────────────────────────────

    def test_detect_language_by_filename(self):
        """Detecta lenguaje correctamente basándose en la extensión."""
        self.assertEqual(detect_language("", "main.py"), "python")
        self.assertEqual(detect_language("", "app.js"), "javascript")
        self.assertEqual(detect_language("", "types.ts"), "typescript")
        self.assertEqual(detect_language("", "Component.tsx"), "typescript")
        self.assertEqual(detect_language("", "index.html"), "html")
        self.assertEqual(detect_language("", "styles.css"), "css")
        self.assertEqual(detect_language("", "schema.sql"), "sql")
        self.assertEqual(detect_language("", "main.rs"), "rust")
        self.assertEqual(detect_language("", "server.go"), "go")
        self.assertEqual(detect_language("", "Main.java"), "java")
        self.assertEqual(detect_language("", "script.sh"), "bash")
        self.assertEqual(detect_language("", "Aura.bat"), "batch")
        self.assertEqual(detect_language("", "data.json"), "json")
        self.assertEqual(detect_language("", "config.yaml"), "yaml")

    def test_detect_language_by_content_heuristics(self):
        """Detecta lenguaje analizando fragmentos de código sin nombre de archivo."""
        py_code = "def calcular_suma(a, b):\n    return a + b\n\nimport os"
        self.assertEqual(detect_language(py_code), "python")

        js_code = "const valor = 42;\nfunction saludo() {\n  console.log('hola');\n}"
        self.assertEqual(detect_language(js_code), "javascript")

        ts_code = "interface Usuario {\n  nombre: string;\n  edad: number;\n}"
        self.assertEqual(detect_language(ts_code), "typescript")

        html_code = "<!DOCTYPE html>\n<html><body><h1>AURA</h1></body></html>"
        self.assertEqual(detect_language(html_code), "html")

        rust_code = "fn main() {\n    let mut x = 5;\n    println!('{}', x);\n}"
        self.assertEqual(detect_language(rust_code), "rust")

        sql_code = "SELECT id, nombre, email FROM usuarios WHERE activo = 1;"
        self.assertEqual(detect_language(sql_code), "sql")

        json_code = '{"nombre": "Orion", "version": "0.56.2"}'
        self.assertEqual(detect_language(json_code), "json")

        self.assertEqual(detect_language(""), "plaintext")
        self.assertEqual(detect_language("Texto común y corriente sin código"), "plaintext")

    # ── 2. Extracción de Bloques de Código ────────────────────────────────────

    def test_extract_code_blocks(self):
        """Extrae bloques de código en Markdown identificando su lenguaje."""
        md = (
            "Texto explicativo antes.\n\n"
            "```python\n"
            "def suma(a, b):\n"
            "    return a + b\n"
            "```\n\n"
            "Texto intermedio.\n\n"
            "```javascript\n"
            "const saludo = () => console.log('hola');\n"
            "```\n"
        )
        blocks = extract_code_blocks(md)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0][0], "python")
        self.assertIn("def suma", blocks[0][1])
        self.assertEqual(blocks[1][0], "javascript")
        self.assertIn("const saludo", blocks[1][1])

        # Extraer primer bloque
        first = extract_first_code_block(md)
        self.assertIsNotNone(first)
        self.assertIn("def suma", first)

        # Sin bloques de código
        self.assertEqual(extract_code_blocks("Solo texto plano"), [])
        self.assertIsNone(extract_first_code_block("Solo texto plano"))

    # ── 3. Análisis Estático Local (AST) ──────────────────────────────────────

    def test_analyze_valid_python_code(self):
        """Analiza sintaxis y extrae funciones, clases e imports con AST de Python."""
        code = (
            "import os\n"
            "from math import sqrt\n\n"
            "class Calculadora:\n"
            "    def raiz(self, n):\n"
            "        return sqrt(n)\n\n"
            "def principal():\n"
            "    c = Calculadora()\n"
            "    return c.raiz(16)\n"
        )
        analysis = analyze_code(code, "python")
        self.assertTrue(analysis.is_syntax_valid)
        self.assertIsNone(analysis.syntax_error)
        self.assertIn("raiz", analysis.functions)
        self.assertIn("principal", analysis.functions)
        self.assertIn("Calculadora", analysis.classes)
        self.assertIn("os", analysis.imports)
        self.assertIn("math", analysis.imports)
        self.assertTrue(analysis.lines_count > 0)
        self.assertIn("líneas", analysis.summary)

    def test_analyze_python_syntax_error(self):
        """Detecta error de sintaxis en Python indicando número de línea exacto."""
        bad_code = "def funcion_invalida(:\n    pass"
        analysis = analyze_code(bad_code, "python")
        self.assertFalse(analysis.is_syntax_valid)
        self.assertIsNotNone(analysis.syntax_error)
        self.assertEqual(analysis.syntax_error_line, 1)
        self.assertIn("Error de sintaxis", analysis.summary)

    def test_analyze_non_python_code(self):
        """Analiza código de otros lenguajes proveyendo métricas cuantitativas."""
        js_code = "function test() { return 123; }"
        analysis = analyze_code(js_code, "javascript")
        self.assertTrue(analysis.is_syntax_valid)
        self.assertEqual(analysis.language, "javascript")
        self.assertEqual(analysis.lines_count, 1)
        self.assertTrue(analysis.char_count > 0)

    # ── 4. Construcción de Prompts ────────────────────────────────────────────

    def test_build_prompt_all_actions(self):
        """Verifica la generación adecuada de system y user prompts para todas las acciones."""
        for action in CodeAction:
            sys_p, user_p = build_prompt(
                action=action,
                code="print('hola mundo')",
                language="python",
                context="Contexto opcional",
                error_trace="Traceback: NameError: name 'x' is not defined",
                instruction="Hacerlo más rápido",
                style="google",
                framework="pytest",
            )
            self.assertIn("Asistente de Programación", sys_p)
            self.assertIn("print('hola mundo')", user_p)
            self.assertTrue(len(sys_p) > 20)
            self.assertTrue(len(user_p) > 10)

    # ── 5. Ejecución de Acciones con CodeAssistant ─────────────────────────────

    def test_explain_code(self):
        """Ejecuta la acción explain retornando un CodeTaskResult completo."""
        code = "def fib(n):\n    return n if n <= 1 else fib(n-1) + fib(n-2)"
        res = self.assistant.explain(code)
        self.assertTrue(res.success)
        self.assertEqual(res.action, CodeAction.EXPLAIN.value)
        self.assertEqual(res.language, "python")
        self.assertIn("Aquí está la explicación", res.content)
        self.assertTrue(res.has_code)
        self.assertIsNotNone(res.extracted_code)
        self.assertEqual(len(self.mock_provider.calls), 1)

    def test_explain_error(self):
        """Analiza un stacktrace y retorna solución."""
        trace = "ZeroDivisionError: division by zero en linea 5"
        code = "def dividir(a, b): return a / b"
        res = self.assistant.explain_error(error_trace=trace, code=code)
        self.assertTrue(res.success)
        self.assertEqual(res.action, CodeAction.EXPLAIN_ERROR.value)
        self.assertIn("Aquí está la explicación", res.content)

    def test_detect_bugs(self):
        """Audita el código buscando bugs."""
        buggy_code = "def get_item(lst, idx):\n    return lst[idx] # puede dar IndexError"
        res = self.assistant.detect_bugs(buggy_code)
        self.assertTrue(res.success)
        self.assertEqual(res.action, CodeAction.DETECT_BUGS.value)

    def test_generate_docs(self):
        """Genera documentación y docstrings."""
        code = "def procesar_pago(monto, cliente): pass"
        res = self.assistant.generate_docs(code, style="google")
        self.assertTrue(res.success)
        self.assertEqual(res.action, CodeAction.GENERATE_DOCS.value)

    def test_generate_readme(self):
        """Genera un README.md estructurado."""
        summary = "AURA: Asistente virtual modular para estudiantes."
        res = self.assistant.generate_readme(summary, files=["run.py", "PROMPT_BASE.md"], project_name="AURA")
        self.assertTrue(res.success)
        self.assertEqual(res.action, CodeAction.GENERATE_README.value)

    def test_generate_comments(self):
        """Inserta comentarios en código."""
        code = "def quicksort(arr): pass"
        res = self.assistant.generate_comments(code)
        self.assertTrue(res.success)
        self.assertEqual(res.action, CodeAction.GENERATE_COMMENTS.value)

    def test_generate_tests(self):
        """Genera tests unitarios con framework especificado."""
        code = "def factorial(n): return 1 if n <= 1 else n * factorial(n-1)"
        res = self.assistant.generate_tests(code, framework="pytest")
        self.assertTrue(res.success)
        self.assertEqual(res.action, CodeAction.GENERATE_TESTS.value)

    def test_refactor_code(self):
        """Refactoriza código según instrucción dada."""
        code = "def f(x):\n a = x * 2\n b = a + 1\n return b"
        res = self.assistant.refactor(code, instruction="Simplificar en una sola expresión")
        self.assertTrue(res.success)
        self.assertEqual(res.action, CodeAction.REFACTOR.value)

    def test_analyze_local_action_no_llm_call(self):
        """La acción 'analyze' se ejecuta 100% de forma local en 0ms sin requerir llamada LLM."""
        code = "import sys\ndef fn(): pass"
        res = self.assistant.execute_action(CodeAction.ANALYZE, code)
        self.assertTrue(res.success)
        self.assertEqual(res.provider, "local")
        self.assertEqual(res.model, "local:ast")
        self.assertIsNotNone(res.analysis)
        self.assertIn("fn", res.analysis.functions)
        # Verificar que el mock provider NO fue llamado
        self.assertEqual(len(self.mock_provider.calls), 0)

    def test_streaming_execution(self):
        """Verifica la generación incremental de chunks mediante execute_action_stream."""
        code = "def test(): return True"
        chunks = list(self.assistant.explain_stream(code))
        self.assertTrue(len(chunks) > 1)
        full = "".join(chunks).strip()
        self.assertIn("Aquí está la explicación", full)

    def test_provider_error_handling(self):
        """Si el proveedor lanza una excepción, CodeAssistant retorna un resultado fallido seguro."""
        failing_provider = MagicMock(spec=AIProvider)
        failing_provider.chat.side_effect = RuntimeError("Fallo de conexión o timeout simulado")
        bad_assistant = CodeAssistant(provider=failing_provider)

        res = bad_assistant.explain("print('error test')")
        self.assertFalse(res.success)
        self.assertIn("Fallo de conexión", res.error_message)
        self.assertEqual(res.content, "")
        self.assertIsNotNone(res.analysis)

    # ── 6. Operaciones con Archivos Locales UTF-8 ─────────────────────────────

    def test_read_code_file_utf8_and_process(self):
        """Lee un archivo de código UTF-8 con caracteres complejos y ejecuta la tarea."""
        test_file = Path(self.temp_dir) / "modulo_estudiante.py"
        content_with_accents = (
            "# Archivo de prueba con acentos: áéíóú, ñ, «comillas» y emoji 🎉\n"
            "def calcular_promedio(notas):\n"
            "    \"\"\"Calcula el promedio de la calificación académica.\"\"\"\n"
            "    if not notas:\n"
            "        return 0.0\n"
            "    return sum(notas) / len(notas)\n"
        )
        test_file.write_text(content_with_accents, encoding="utf-8")

        # 1. Leer archivo
        read_content, detected_lang = self.assistant.read_code_file(test_file)
        self.assertEqual(detected_lang, "python")
        self.assertIn("áéíóú", read_content)
        self.assertIn("🎉", read_content)

        # 2. Procesar archivo con acción
        res = self.assistant.process_file(test_file, action=CodeAction.GENERATE_DOCS)
        self.assertTrue(res.success)
        self.assertEqual(res.language, "python")
        self.assertIn("calcular_promedio", res.analysis.functions)

    def test_read_nonexistent_file_raises_error(self):
        """Verifica que intentar leer un archivo inexistente levante FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            self.assistant.read_code_file(Path(self.temp_dir) / "no_existe.py")

    def test_to_dict_serialization(self):
        """Verifica que CodeTaskResult pueda serializarse a dict / JSON sin errores."""
        code = "def foo(): pass"
        res = self.assistant.explain(code)
        d = res.to_dict()
        self.assertEqual(d["action"], "explain")
        self.assertEqual(d["language"], "python")
        self.assertTrue(d["success"])
        # Debe ser serializable a JSON
        json_str = json.dumps(d, ensure_ascii=False)
        self.assertIn("python", json_str)


if __name__ == "__main__":
    unittest.main()

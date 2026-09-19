"""
AURA — Núcleo del Asistente de Programación (Fase 26)

Provee el motor central de asistencia de código para estudiantes y desarrolladores:
1. Explicar fragmentos de código de forma didáctica y paso a paso.
2. Analizar stacktraces y mensajes de error, detectando la causa raíz y proponiendo soluciones.
3. Detectar bugs potenciales, vulnerabilidades y malas prácticas.
4. Generar documentación estructurada y docstrings (Google, NumPy, JSDoc).
5. Generar archivos README.md profesionales para proyectos.
6. Añadir comentarios explicativos en líneas clave sin redundancia trivial.
7. Generar suites de tests unitarios (pytest, unittest, jest, etc.).
8. Refactorizar código para mejorar legibilidad, rendimiento y apego a estándares.
9. Análisis estático local de sintaxis y estructura (AST para Python).
"""

from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple

from ai.provider_factory import get_default_provider
from ai.provider_interface import AIProvider, ChatMessage, ChatResponse
from utils.logger import get_logger

_logger = get_logger("aura.core.code_assistant")


# ─────────────────────────────────────────────────────────────────────────────
# Enums y Constantes de Acciones
# ─────────────────────────────────────────────────────────────────────────────

class CodeAction(str, Enum):
    """Acciones soportadas por el núcleo del asistente de programación."""
    EXPLAIN = "explain"
    EXPLAIN_ERROR = "explain_error"
    DETECT_BUGS = "detect_bugs"
    GENERATE_DOCS = "generate_docs"
    GENERATE_README = "generate_readme"
    GENERATE_COMMENTS = "generate_comments"
    GENERATE_TESTS = "generate_tests"
    REFACTOR = "refactor"
    ANALYZE = "analyze"


# Mapeo de extensiones comunes a nombres de lenguajes normalizados
_EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".ipynb": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "css",
    ".sass": "css",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sql": "sql",
    ".rs": "rust",
    ".go": "go",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".php": "php",
    ".rb": "ruby",
    ".sh": "bash",
    ".bash": "bash",
    ".bat": "batch",
    ".cmd": "batch",
    ".ps1": "powershell",
    ".md": "markdown",
    ".xml": "xml",
}


# ─────────────────────────────────────────────────────────────────────────────
# Modelos de Datos Tipados
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CodeAnalysis:
    """Resultado del análisis sintáctico y estructural local."""
    language: str
    lines_count: int = 0
    char_count: int = 0
    is_syntax_valid: bool = True
    syntax_error: Optional[str] = None
    syntax_error_line: Optional[int] = None
    syntax_error_offset: Optional[int] = None
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "lines_count": self.lines_count,
            "char_count": self.char_count,
            "is_syntax_valid": self.is_syntax_valid,
            "syntax_error": self.syntax_error,
            "syntax_error_line": self.syntax_error_line,
            "syntax_error_offset": self.syntax_error_offset,
            "functions": self.functions,
            "classes": self.classes,
            "imports": self.imports,
            "summary": self.summary,
        }


@dataclass
class CodeTaskResult:
    """Resultado integral de una tarea del asistente de programación."""
    action: str
    language: str
    content: str
    success: bool
    model: str = ""
    provider: str = ""
    extracted_code: Optional[str] = None
    all_code_blocks: list[tuple[str, str]] = field(default_factory=list)
    error_message: Optional[str] = None
    analysis: Optional[CodeAnalysis] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_code(self) -> bool:
        """True si el resultado incluye al menos un bloque de código extraído."""
        return bool(self.extracted_code or self.all_code_blocks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "language": self.language,
            "content": self.content,
            "success": self.success,
            "model": self.model,
            "provider": self.provider,
            "extracted_code": self.extracted_code,
            "has_code": self.has_code,
            "error_message": self.error_message,
            "analysis": self.analysis.to_dict() if self.analysis else None,
            "metadata": self.metadata,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades de Detección, Extracción y Análisis Estático
# ─────────────────────────────────────────────────────────────────────────────

def detect_language(code: str, filename: str = "") -> str:
    """
    Detecta el lenguaje de programación basándose en el nombre de archivo o heurística de contenido.
    """
    # 1. Detección por extensión si se provee nombre de archivo
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in _EXTENSION_MAP:
            return _EXTENSION_MAP[ext]

    if not code or not code.strip():
        return "plaintext"

    snippet = code.strip()

    # 2. Heurística por Shebang
    if snippet.startswith("#!"):
        first_line = snippet.splitlines()[0].lower()
        if "python" in first_line:
            return "python"
        elif "node" in first_line or "javascript" in first_line:
            return "javascript"
        elif "bash" in first_line or "sh" in first_line:
            return "bash"
        elif "perl" in first_line:
            return "perl"

    # 3. Heurística sintáctica por palabras clave
    if re.search(r"^\s*import\s+[a-zA-Z0-9_.]+|^\s*from\s+[a-zA-Z0-9_.]+\s+import|^\s*def\s+[a-zA-Z0-9_]+\s*\(|^\s*class\s+[a-zA-Z0-9_]+.*:", code, re.MULTILINE):
        return "python"

    if re.search(r"^\s*(const|let|var)\s+[a-zA-Z0-9_$]+\s*=|console\.log\(|function\s+[a-zA-Z0-9_$]*\s*\(|export\s+(default|const|class)", code, re.MULTILINE):
        return "javascript"

    if re.search(r":\s*(string|number|boolean|any|void)\b|<[A-Z][a-zA-Z0-9_]*>|interface\s+[A-Z][a-zA-Z0-9_]*\s*\{", code):
        return "typescript"

    if re.search(r"^\s*<!DOCTYPE\s+html>|^\s*<html\b|^\s*<div\b|^\s*<body\b", code, re.IGNORECASE | re.MULTILINE):
        return "html"

    if re.search(r"^\s*fn\s+[a-zA-Z0-9_]+\s*\(|let\s+mut\s+|impl\s+[A-Z]|use\s+std::", code, re.MULTILINE):
        return "rust"

    if re.search(r"^\s*package\s+[a-zA-Z0-9_]+|func\s+[a-zA-Z0-9_]+\s*\(|fmt\.Print", code, re.MULTILINE):
        return "go"

    if re.search(r"^\s*#include\s*<|std::cout|int\s+main\s*\(", code, re.MULTILINE):
        return "cpp"

    if re.search(r"public\s+class\s+[A-Za-z0-9_]+|public\s+static\s+void\s+main|System\.out\.print", code):
        return "java"

    if re.search(r"^\s*(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+TABLE|ALTER\s+TABLE)\b", code, re.IGNORECASE | re.MULTILINE):
        return "sql"

    # 4. JSON válido
    if (snippet.startswith("{") and snippet.endswith("}")) or (snippet.startswith("[") and snippet.endswith("]")):
        try:
            json.loads(snippet)
            return "json"
        except Exception:
            pass

    return "python" if ("print(" in snippet or ":" in snippet) else "plaintext"


def extract_code_blocks(markdown_text: str) -> list[tuple[str, str]]:
    """
    Extrae todos los bloques de código delimitados por triple comilla invertida (```lang ... ```).
    Retorna una lista de tuplas (lenguaje, código_limpio).
    """
    if not markdown_text:
        return []

    pattern = r"```([a-zA-Z0-9_+-]*)\r?\n(.*?)```"
    matches = re.findall(pattern, markdown_text, re.DOTALL)
    blocks = []
    for lang, code_content in matches:
        blocks.append((lang.strip().lower() or "plaintext", code_content.strip()))
    return blocks


def extract_first_code_block(markdown_text: str) -> Optional[str]:
    """
    Retorna el código contenido en el primer bloque de código de un texto markdown.
    Si no hay bloques delimitados por ```, retorna None.
    """
    blocks = extract_code_blocks(markdown_text)
    if blocks:
        return blocks[0][1]
    return None


def analyze_code(code: str, language: str = "") -> CodeAnalysis:
    """
    Ejecuta un análisis estático local ultrarrápido (en memoria, 0ms) sobre el fragmento de código.
    Si es Python, utiliza el módulo ast de la librería estándar para detectar errores de sintaxis,
    definiciones de funciones, clases e importaciones.
    """
    clean_code = code or ""
    detected_lang = language or detect_language(clean_code)
    lines = clean_code.splitlines()
    lines_count = len(lines)
    char_count = len(clean_code)

    analysis = CodeAnalysis(
        language=detected_lang,
        lines_count=lines_count,
        char_count=char_count,
        is_syntax_valid=True,
    )

    if detected_lang.lower() == "python" and clean_code.strip():
        try:
            tree = ast.parse(clean_code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    analysis.functions.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    analysis.classes.append(node.name)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        analysis.imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    analysis.imports.append(mod)

            parts = [f"{lines_count} líneas"]
            if analysis.functions:
                parts.append(f"{len(analysis.functions)} funciones ({', '.join(analysis.functions[:3])})")
            if analysis.classes:
                parts.append(f"{len(analysis.classes)} clases ({', '.join(analysis.classes[:2])})")
            analysis.summary = ", ".join(parts)

        except SyntaxError as e:
            analysis.is_syntax_valid = False
            analysis.syntax_error = e.msg
            analysis.syntax_error_line = e.lineno
            analysis.syntax_error_offset = e.offset
            analysis.summary = f"Error de sintaxis en línea {e.lineno}: {e.msg}"
        except Exception as e:
            analysis.summary = f"Análisis parcial: {e}"
    else:
        analysis.summary = f"{detected_lang.upper()} — {lines_count} líneas, {char_count} caracteres"

    return analysis


# ─────────────────────────────────────────────────────────────────────────────
# Constructor de Prompts Especializados para Estudiantes
# ─────────────────────────────────────────────────────────────────────────────

from aura.ai.prompt_assembler import assemble_prompt


def _get_programming_base_prompt(provider: Optional[str] = None, model: Optional[str] = None) -> str:
    return assemble_prompt(context="programacion", provider=provider, model=model)


def build_prompt(
    action: CodeAction | str,
    code: str,
    language: str = "",
    context: str = "",
    **kwargs: Any,
) -> tuple[str, str]:
    """
    Construye la tupla (system_prompt, user_prompt) adaptada a cada acción de programación.
    """
    act = CodeAction(action) if isinstance(action, str) and action in [a.value for a in CodeAction] else action
    detected_lang = language or detect_language(code)
    lang_header = f"Lenguaje: {detected_lang.upper()}\n\n" if detected_lang != "plaintext" else ""

    base_sys = _get_programming_base_prompt()

    if act == CodeAction.EXPLAIN:
        sys_p = base_sys + "\n[Asistente de Programación] Tu rol en esta tarea es EXPLICAR el código de forma didáctica a un estudiante: qué hace, cómo funciona paso a paso, componentes principales y qué lógica sigue."
        ctx_text = f"\nContexto adicional provisto por el usuario: {context}\n" if context else ""
        user_p = f"{lang_header}Por favor explicame este código paso a paso:{ctx_text}\n\n```{detected_lang}\n{code}\n```"

    elif act == CodeAction.EXPLAIN_ERROR:
        sys_p = base_sys + "\n[Asistente de Programación] Tu rol en esta tarea es ANALIZAR Y RESOLVER UN ERROR O STACKTRACE: identificá la causa raíz, la línea exacta del fallo, explicá por qué ocurrió y mostrá cómo solucionarlo con el código corregido."
        code_part = f"\nCódigo involucrado:\n```{detected_lang}\n{code}\n```\n" if code and code.strip() else ""
        user_p = f"{lang_header}Tengo el siguiente error/stacktrace:\n\n```text\n{context or kwargs.get('error_trace', code)}\n```{code_part}\nPor favor analizá qué causó el error y cómo resolverlo."

    elif act == CodeAction.DETECT_BUGS:
        sys_p = base_sys + "\n[Asistente de Programación] Tu rol en esta tarea es AUDITAR BUGS Y VULNERABILIDADES: revisá el código buscando errores lógicos, casos borde (edge cases) no contemplados, excepciones no capturadas, problemas de concurrencia o malas prácticas, y proveé las soluciones."
        user_p = f"{lang_header}Revisá el siguiente código en busca de bugs, problemas potenciales o malas prácticas, y mostrá cómo solucionarlos:\n\n```{detected_lang}\n{code}\n```"

    elif act == CodeAction.GENERATE_DOCS:
        style = kwargs.get("style", "google")
        sys_p = base_sys + f"\n[Asistente de Programación] Tu rol en esta tarea es GENERAR DOCUMENTACIÓN técnica y docstrings completos siguiendo el estándar '{style}'. Incluí descripción, parámetros (Args), tipos, valores de retorno (Returns) y excepciones (Raises)."
        user_p = f"{lang_header}Generá la documentación y docstrings correspondientes para el siguiente código (estilo {style}):\n\n```{detected_lang}\n{code}\n```"

    elif act == CodeAction.GENERATE_README:
        project_name = kwargs.get("project_name", "")
        if not project_name:
            try:
                from core.user_memory import user_memory
                curr = user_memory.get_current_project()
                project_name = curr.name if curr and curr.name else "Proyecto"
            except Exception:
                project_name = "Proyecto"

        files_list = kwargs.get("files", [])
        files_info = f"\nArchivos clave del proyecto:\n- " + "\n- ".join(files_list) if files_list else ""
        sys_p = base_sys + "\n[Asistente de Programación] Tu rol en esta tarea es GENERAR UN ARCHIVO README.md profesional, ordenado y completo para un repositorio de software."
        user_p = f"Generá un README.md profesional para el proyecto '{project_name}'.\n\nResumen o código base provisto:\n{code}{files_info}\n\nEstructura deseada: Título, Descripción, Características, Requisitos, Instalación, Uso rápido y Estructura del proyecto."

    elif act == CodeAction.GENERATE_COMMENTS:
        sys_p = base_sys + "\n[Asistente de Programación] Tu rol en esta tarea es AÑADIR COMENTARIOS EXPLICATIVOS útiles en el código. Comentá qué hace cada sección clave sin añadir comentarios redundantes u obvios. Devolvé el código completo comentado."
        user_p = f"{lang_header}Añadí comentarios claros y didácticos al siguiente código:\n\n```{detected_lang}\n{code}\n```"

    elif act == CodeAction.GENERATE_TESTS:
        framework = kwargs.get("framework", "pytest" if detected_lang == "python" else "jest")
        sys_p = base_sys + f"\n[Asistente de Programación] Tu rol en esta tarea es ESCRIBIR UNA SUITE DE TESTS UNITARIOS usando '{framework}'. Incluí casos normales (happy path), casos límite (edge cases) y validaciones de errores/excepciones esperadas."
        user_p = f"{lang_header}Escribí tests unitarios completos con '{framework}' para el siguiente código:\n\n```{detected_lang}\n{code}\n```"

    elif act == CodeAction.REFACTOR:
        instruction = kwargs.get("instruction", context or "Mejorar legibilidad, eficiencia y buenas prácticas")
        sys_p = base_sys + "\n[Asistente de Programación] Tu rol en esta tarea es REFACTORIZAR EL CÓDIGO: mejorá su diseño, eficiencia, legibilidad y modularidad según las pautas dadas, explicando brevemente qué cambiaste y por qué."
        user_p = f"{lang_header}Refactorizá el siguiente código siguiendo esta instrucción: '{instruction}':\n\n```{detected_lang}\n{code}\n```"

    else:  # General / ANALYZE
        sys_p = base_sys + "\n[Asistente de Programación] Analizá el siguiente código."
        user_p = f"{lang_header}Analizá el siguiente código:\n\n```{detected_lang}\n{code}\n```"

    return sys_p, user_p



# ─────────────────────────────────────────────────────────────────────────────
# Clase Principal del Asistente de Programación (Core Engine)
# ─────────────────────────────────────────────────────────────────────────────

class CodeAssistant:
    """
    Controlador central del Asistente de Programación (Fase 26).
    Gestiona la ejecución de tareas de código, análisis local estático y
    comunicación fluida con la capa de inteligencia artificial.
    """

    def __init__(self, provider: Optional[AIProvider] = None):
        self._custom_provider = provider

    @property
    def provider(self) -> AIProvider:
        """Retorna el proveedor de IA configurado o el predeterminado del sistema."""
        if self._custom_provider is not None:
            return self._custom_provider
        return get_default_provider()

    # ── Ejecución de Acciones ─────────────────────────────────────────────────

    def execute_action(
        self,
        action: CodeAction | str,
        code: str,
        language: str = "",
        provider: Optional[AIProvider] = None,
        **kwargs: Any,
    ) -> CodeTaskResult:
        """
        Ejecuta una acción sincrónica del asistente de programación y retorna un CodeTaskResult.
        """
        clean_code = (code or "").strip()
        action_val = action.value if isinstance(action, CodeAction) else str(action)
        detected_lang = language or detect_language(clean_code)

        _logger.info(f"CodeAssistant: ejecutando acción '{action_val}' (lenguaje='{detected_lang}')")

        # 1. Ejecutar análisis estático local
        local_analysis = analyze_code(clean_code, detected_lang)

        # Si la acción es exclusivamente 'analyze', retornamos el análisis sin necesidad de LLM
        if action_val == CodeAction.ANALYZE.value:
            return CodeTaskResult(
                action=action_val,
                language=detected_lang,
                content=local_analysis.summary,
                success=True,
                model="local:ast",
                provider="local",
                analysis=local_analysis,
                metadata={"local_only": True},
            )

        # 2. Construir prompts
        system_prompt, user_prompt = build_prompt(
            action=action_val,
            code=clean_code,
            language=detected_lang,
            **kwargs,
        )

        active_provider = provider or self.provider
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]

        try:
            chat_resp: ChatResponse = active_provider.chat(messages)
            raw_content = chat_resp.content or ""
            all_blocks = extract_code_blocks(raw_content)
            first_code = extract_first_code_block(raw_content)

            return CodeTaskResult(
                action=action_val,
                language=detected_lang,
                content=raw_content,
                success=True,
                model=chat_resp.model,
                provider=chat_resp.provider or getattr(active_provider, "provider_name", "ai"),
                extracted_code=first_code,
                all_code_blocks=all_blocks,
                analysis=local_analysis,
                metadata={"raw_response": chat_resp.raw},
            )

        except Exception as e:
            _logger.error(f"CodeAssistant: error al procesar acción '{action_val}': {e}", exc_info=True)
            return CodeTaskResult(
                action=action_val,
                language=detected_lang,
                content="",
                success=False,
                error_message=str(e),
                analysis=local_analysis,
                metadata={"exception": type(e).__name__},
            )

    def execute_action_stream(
        self,
        action: CodeAction | str,
        code: str,
        language: str = "",
        provider: Optional[AIProvider] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """
        Ejecuta una acción en modo streaming, generando fragmentos de texto conforme se reciben.
        """
        clean_code = (code or "").strip()
        action_val = action.value if isinstance(action, CodeAction) else str(action)
        detected_lang = language or detect_language(clean_code)

        system_prompt, user_prompt = build_prompt(
            action=action_val,
            code=clean_code,
            language=detected_lang,
            **kwargs,
        )

        active_provider = provider or self.provider
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]

        _logger.info(f"CodeAssistant: iniciando stream para '{action_val}'")
        for chunk in active_provider.chat_stream(messages):
            yield chunk

    # ── Métodos de Conveniencia Especializados ───────────────────────────────

    def explain(
        self,
        code: str,
        language: str = "",
        context: str = "",
        provider: Optional[AIProvider] = None,
    ) -> CodeTaskResult:
        """Explica un fragmento de código paso a paso."""
        return self.execute_action(CodeAction.EXPLAIN, code, language=language, context=context, provider=provider)

    def explain_stream(
        self,
        code: str,
        language: str = "",
        context: str = "",
        provider: Optional[AIProvider] = None,
    ) -> Iterator[str]:
        """Versión streaming de explain."""
        return self.execute_action_stream(CodeAction.EXPLAIN, code, language=language, context=context, provider=provider)

    def explain_error(
        self,
        error_trace: str,
        code: str = "",
        language: str = "",
        provider: Optional[AIProvider] = None,
    ) -> CodeTaskResult:
        """Explica un mensaje de error o stacktrace y provee la solución correspondiente."""
        return self.execute_action(
            CodeAction.EXPLAIN_ERROR,
            code=code,
            language=language,
            error_trace=error_trace,
            provider=provider,
        )

    def explain_error_stream(
        self,
        error_trace: str,
        code: str = "",
        language: str = "",
        provider: Optional[AIProvider] = None,
    ) -> Iterator[str]:
        """Versión streaming de explain_error."""
        return self.execute_action_stream(
            CodeAction.EXPLAIN_ERROR,
            code=code,
            language=language,
            error_trace=error_trace,
            provider=provider,
        )

    def detect_bugs(
        self,
        code: str,
        language: str = "",
        provider: Optional[AIProvider] = None,
    ) -> CodeTaskResult:
        """Detecta bugs potenciales, vulnerabilidades y malas prácticas."""
        return self.execute_action(CodeAction.DETECT_BUGS, code, language=language, provider=provider)

    def detect_bugs_stream(
        self,
        code: str,
        language: str = "",
        provider: Optional[AIProvider] = None,
    ) -> Iterator[str]:
        """Versión streaming de detect_bugs."""
        return self.execute_action_stream(CodeAction.DETECT_BUGS, code, language=language, provider=provider)

    def generate_docs(
        self,
        code: str,
        language: str = "",
        style: str = "google",
        provider: Optional[AIProvider] = None,
    ) -> CodeTaskResult:
        """Genera docstrings y documentación formal para el código."""
        return self.execute_action(CodeAction.GENERATE_DOCS, code, language=language, style=style, provider=provider)

    def generate_docs_stream(
        self,
        code: str,
        language: str = "",
        style: str = "google",
        provider: Optional[AIProvider] = None,
    ) -> Iterator[str]:
        """Versión streaming de generate_docs."""
        return self.execute_action_stream(CodeAction.GENERATE_DOCS, code, language=language, style=style, provider=provider)

    def generate_readme(
        self,
        project_summary: str,
        files: Optional[list[str]] = None,
        project_name: str = "Proyecto",
        language: str = "",
        provider: Optional[AIProvider] = None,
    ) -> CodeTaskResult:
        """Genera un archivo README.md profesional."""
        return self.execute_action(
            CodeAction.GENERATE_README,
            code=project_summary,
            language=language,
            files=files,
            project_name=project_name,
            provider=provider,
        )

    def generate_readme_stream(
        self,
        project_summary: str,
        files: Optional[list[str]] = None,
        project_name: str = "Proyecto",
        language: str = "",
        provider: Optional[AIProvider] = None,
    ) -> Iterator[str]:
        """Versión streaming de generate_readme."""
        return self.execute_action_stream(
            CodeAction.GENERATE_README,
            code=project_summary,
            language=language,
            files=files,
            project_name=project_name,
            provider=provider,
        )

    def generate_comments(
        self,
        code: str,
        language: str = "",
        provider: Optional[AIProvider] = None,
    ) -> CodeTaskResult:
        """Inserta comentarios claros en secciones clave del código."""
        return self.execute_action(CodeAction.GENERATE_COMMENTS, code, language=language, provider=provider)

    def generate_comments_stream(
        self,
        code: str,
        language: str = "",
        provider: Optional[AIProvider] = None,
    ) -> Iterator[str]:
        """Versión streaming de generate_comments."""
        return self.execute_action_stream(CodeAction.GENERATE_COMMENTS, code, language=language, provider=provider)

    def generate_tests(
        self,
        code: str,
        language: str = "",
        framework: str = "pytest",
        provider: Optional[AIProvider] = None,
    ) -> CodeTaskResult:
        """Genera una suite de tests unitarios."""
        return self.execute_action(CodeAction.GENERATE_TESTS, code, language=language, framework=framework, provider=provider)

    def generate_tests_stream(
        self,
        code: str,
        language: str = "",
        framework: str = "pytest",
        provider: Optional[AIProvider] = None,
    ) -> Iterator[str]:
        """Versión streaming de generate_tests."""
        return self.execute_action_stream(CodeAction.GENERATE_TESTS, code, language=language, framework=framework, provider=provider)

    def refactor(
        self,
        code: str,
        instruction: str = "",
        language: str = "",
        provider: Optional[AIProvider] = None,
    ) -> CodeTaskResult:
        """Refactoriza el código optimizando su legibilidad y buenas prácticas."""
        return self.execute_action(CodeAction.REFACTOR, code, language=language, instruction=instruction, provider=provider)

    def refactor_stream(
        self,
        code: str,
        instruction: str = "",
        language: str = "",
        provider: Optional[AIProvider] = None,
    ) -> Iterator[str]:
        """Versión streaming de refactor."""
        return self.execute_action_stream(CodeAction.REFACTOR, code, language=language, instruction=instruction, provider=provider)

    # ── Operaciones con Archivos Locales ─────────────────────────────────────

    def read_code_file(self, file_path: Path | str) -> tuple[str, str]:
        """
        Lee de forma segura un archivo de código desde disco con codificación UTF-8 explícita
        y detecta su lenguaje basándose en la extensión.
        Retorna (contenido_codigo, lenguaje_detectado).
        """
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {path}")
        if not path.is_file():
            raise ValueError(f"La ruta no es un archivo: {path}")

        # Regla global mandatoria: UTF-8 explícito con fallback seguro ignore para binarios accidentales
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        lang = detect_language(content, filename=path.name)
        return content, lang

    def process_file(
        self,
        file_path: Path | str,
        action: CodeAction | str,
        provider: Optional[AIProvider] = None,
        **kwargs: Any,
    ) -> CodeTaskResult:
        """
        Lee un archivo desde disco y ejecuta la acción solicitada sobre su contenido.
        """
        content, lang = self.read_code_file(file_path)
        return self.execute_action(
            action=action,
            code=content,
            language=kwargs.pop("language", lang),
            provider=provider,
            **kwargs,
        )


# Singleton predeterminado para el sistema
code_assistant = CodeAssistant()

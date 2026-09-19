"""
AURA — Paquete de nucleo de la aplicacion (Fases 3, 10 y 13)

Exporta el controlador, estado global, manejador de errores,
utilidad de diagnostico y router de comandos de AURA.
"""

from core.app import App
from core.state import app_state
from core.error_handler import error_handler, LEVEL_CRITICAL, LEVEL_ERROR, LEVEL_WARNING
from core.diagnostics import run_diagnostics, DiagsResult, run_self_test, SelfTestItem, self_test_to_text
from core.command_router import CommandRouter, RouteResult, command_router
from aura.core.intent_router import Intent, IntentRouter, intent_router
from aura.core.filename_guard import (
    is_valid_strict_filename,
    resolve_folder_alias,
    resolve_path_with_alias,
    get_known_folder_path,
)
from aura.core.entity_resolver import EntityResolver, ResolvedEntity, entity_resolver, resolve
from core.app_resolver import (
    ResolvedApp,
    resolve_app,
    launch_app,
    detect_default_browser,
    get_preferred_browser_name,
    get_installed_browsers,
    SUPPORTED_BROWSERS,
    BROWSER_DISPLAY_NAMES,
)
from core.app_scanner import (
    AppIndexManager,
    DeepAppScanner,
    DeepScanResult,
    IndexedApp,
    app_index_manager,
    deep_app_scanner,
    fast_resolve_app,
)
from core.file_explorer import (
    FileExplorer,
    FileItem,
    FolderSummary,
    QuickAccessItem,
    ProjectInfo,
    detect_project,
    format_bytes,
    get_type_and_icon,
)
from core.fuzzy_interpreter import (
    InterpretationResult,
    TypoMemory,
    typo_memory,
    normalize_aggressive,
    generate_target_variants,
    FuzzyInterpreter,
    fuzzy_interpreter,
)
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
)
from core.user_memory import (
    PathMemoryEntry,
    ProgramUsageEntry,
    ProjectContextEntry,
    UserFact,
    UserMemory,
    detect_project_type,
    user_memory,
)
from core.ollama_helper import (
    RECOMMENDED_MODELS,
    is_ollama_installed,
    check_ollama_service,
    get_installation_instructions,
    format_ollama_guide_text,
)

__all__ = [
    "RECOMMENDED_MODELS",
    "is_ollama_installed",
    "check_ollama_service",
    "get_installation_instructions",
    "format_ollama_guide_text",
    "AppIndexManager",
    "DeepAppScanner",
    "DeepScanResult",
    "IndexedApp",
    "app_index_manager",
    "deep_app_scanner",
    "fast_resolve_app",
    "detect_project",
    "App",
    "app_state",
    "error_handler",
    "LEVEL_CRITICAL",
    "LEVEL_ERROR",
    "LEVEL_WARNING",
    "run_diagnostics",
    "DiagsResult",
    "run_self_test",
    "SelfTestItem",
    "self_test_to_text",
    "CommandRouter",
    "RouteResult",
    "command_router",
    "Intent",
    "IntentRouter",
    "intent_router",
    "is_valid_strict_filename",
    "resolve_folder_alias",
    "resolve_path_with_alias",
    "get_known_folder_path",
    "EntityResolver",
    "ResolvedEntity",
    "entity_resolver",
    "resolve",
    "ResolvedApp",
    "resolve_app",
    "launch_app",
    "detect_default_browser",
    "get_preferred_browser_name",
    "get_installed_browsers",
    "SUPPORTED_BROWSERS",
    "BROWSER_DISPLAY_NAMES",
    "FileExplorer",
    "FileItem",
    "FolderSummary",
    "QuickAccessItem",
    "ProjectInfo",
    "format_bytes",
    "get_type_and_icon",
    "InterpretationResult",
    "TypoMemory",
    "typo_memory",
    "normalize_aggressive",
    "generate_target_variants",
    "FuzzyInterpreter",
    "fuzzy_interpreter",
    "CodeAction",
    "CodeAnalysis",
    "CodeTaskResult",
    "CodeAssistant",
    "code_assistant",
    "detect_language",
    "extract_code_blocks",
    "extract_first_code_block",
    "analyze_code",
    "PathMemoryEntry",
    "ProgramUsageEntry",
    "ProjectContextEntry",
    "UserFact",
    "UserMemory",
    "detect_project_type",
    "user_memory",
]



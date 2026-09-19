"""
AURA — Utilidad de diagnóstico del sistema (Fase 10)

Reúne información de diagnóstico sobre el entorno de la aplicación:
  - Versión de Python y plataforma
  - Estado de Ollama (conectividad HTTP)
  - Modelo de IA configurado
  - Espacio en disco (carpeta de datos y logs)
  - Variables de configuración relevantes (sin valores sensibles)
  - Conteo de conversaciones guardadas
  - Última entrada del log (resumen)

Uso:
    from core.diagnostics import run_diagnostics
    result = run_diagnostics()  # DiagsResult con todos los campos
"""

from __future__ import annotations

import os
import platform
import sys
import urllib.request
import urllib.error
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

_logger = get_logger("aura.core.diagnostics")

# Directorio raíz del proyecto
_ROOT = Path(__file__).resolve().parent.parent


# ──────────────────────────────────────────────────────────────────
# Dataclasses de resultado
# ──────────────────────────────────────────────────────────────────

@dataclass
class OllamaDiag:
    """Diagnóstico de conectividad con Ollama."""
    reachable: bool = False
    url: str = ""
    models: list[str] = field(default_factory=list)
    configured_model: str = ""
    model_available: bool = False
    error: str = ""
    latency_ms: float = 0.0


@dataclass
class DiskDiag:
    """Diagnóstico de espacio en disco."""
    total_gb: float = 0.0
    free_gb: float = 0.0
    used_percent: float = 0.0
    conversations_count: int = 0
    log_size_kb: float = 0.0
    data_dir_exists: bool = False
    logs_dir_exists: bool = False


@dataclass
class SystemDiag:
    """Diagnóstico de entorno del sistema."""
    python_version: str = ""
    os_name: str = ""
    os_version: str = ""
    architecture: str = ""
    hostname: str = ""
    timestamp: str = ""


@dataclass
class ConfigDiag:
    """Diagnóstico de configuración de la app."""
    ai_provider: str = ""
    ai_model: str = ""
    ollama_url: str = ""
    app_theme: str = ""
    app_language: str = ""
    confirm_destructive: str = ""
    workspace_path: str = ""
    env_file_exists: bool = False


@dataclass
class DiagsResult:
    """Resultado completo del diagnóstico de AURA."""
    system: SystemDiag = field(default_factory=SystemDiag)
    config: ConfigDiag = field(default_factory=ConfigDiag)
    ollama: OllamaDiag = field(default_factory=OllamaDiag)
    disk: DiskDiag = field(default_factory=DiskDiag)
    overall_ok: bool = False
    summary: str = ""
    issues: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        """Genera un reporte de texto legible para mostrar en la UI."""
        lines = [
            "═" * 52,
            "  DIAGNÓSTICO DE AURA",
            f"  {self.system.timestamp}",
            "═" * 52,
            "",
            "── SISTEMA ──────────────────────────────",
            f"  Python:        {self.system.python_version}",
            f"  SO:            {self.system.os_name} {self.system.os_version}",
            f"  Arquitectura:  {self.system.architecture}",
            "",
            "── CONFIGURACIÓN ────────────────────────",
            f"  Proveedor IA:  {self.config.ai_provider}",
            f"  Modelo:        {self.config.ai_model}",
            f"  Ollama URL:    {self.config.ollama_url}",
            f"  Tema:          {self.config.app_theme}",
            f"  Idioma:        {self.config.app_language}",
            f"  Workspace:     {self.config.workspace_path}",
            f"  .env:          {'✓ encontrado' if self.config.env_file_exists else '✗ no encontrado'}",
            "",
            "── OLLAMA ───────────────────────────────",
        ]

        if self.ollama.reachable:
            lines += [
                f"  Estado:        ✓ Disponible ({self.ollama.latency_ms:.0f} ms)",
                f"  Modelos:       {', '.join(self.ollama.models) if self.ollama.models else '(ninguno)'}",
                f"  Modelo config: {self.ollama.configured_model}",
                f"  Modelo OK:     {'✓ Disponible' if self.ollama.model_available else '✗ No encontrado'}",
            ]
        else:
            lines += [
                f"  Estado:        ✗ No disponible",
                f"  URL:           {self.ollama.url}",
                f"  Error:         {self.ollama.error}",
            ]

        lines += [
            "",
            "── DISCO ────────────────────────────────",
            f"  Espacio libre: {self.disk.free_gb:.1f} GB de {self.disk.total_gb:.1f} GB",
            f"  Uso disco:     {self.disk.used_percent:.0f}%",
            f"  Conversaciones:{self.disk.conversations_count}",
            f"  Tamaño log:    {self.disk.log_size_kb:.1f} KB",
            "",
        ]

        if self.issues:
            lines.append("── PROBLEMAS DETECTADOS ─────────────────")
            for issue in self.issues:
                lines.append(f"  ⚠ {issue}")
            lines.append("")

        lines += [
            "── RESUMEN ──────────────────────────────",
            f"  Estado general: {'✓ OK' if self.overall_ok else '✗ Con problemas'}",
            f"  {self.summary}",
            "═" * 52,
        ]

        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────
# Funciones de diagnóstico individuales
# ──────────────────────────────────────────────────────────────────

def _diag_system() -> SystemDiag:
    """Recopila información del sistema operativo y Python."""
    try:
        hostname = platform.node()
    except Exception:
        hostname = "desconocido"

    return SystemDiag(
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        os_name=platform.system(),
        os_version=platform.release(),
        architecture=platform.machine(),
        hostname=hostname,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def _diag_config() -> ConfigDiag:
    """Lee la configuración de la app desde settings."""
    try:
        from config.settings import settings
        env_file = _ROOT / ".env"
        return ConfigDiag(
            ai_provider=settings.get("AI_PROVIDER", "(no configurado)"),
            ai_model=settings.get("AI_MODEL", "(no configurado)"),
            ollama_url=settings.get("OLLAMA_URL", "http://localhost:11434"),
            app_theme=settings.get("APP_THEME", "dark"),
            app_language=settings.get("APP_LANGUAGE", "es"),
            confirm_destructive=settings.get("CONFIRM_DESTRUCTIVE", "true"),
            workspace_path=settings.get("WORKSPACE_PATH", "(no configurado)"),
            env_file_exists=env_file.exists(),
        )
    except Exception as e:
        _logger.warning(f"Error leyendo config en diagnóstico: {e}")
        return ConfigDiag()


def _diag_ollama(url: str, model: str) -> OllamaDiag:
    """Verifica la conectividad con Ollama y lista los modelos disponibles."""
    diag = OllamaDiag(url=url, configured_model=model)

    try:
        import time
        t0 = time.monotonic()

        # Verificar que Ollama responde
        req = urllib.request.Request(
            f"{url}/api/tags",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        diag.latency_ms = (time.monotonic() - t0) * 1000
        diag.reachable = True

        # Parsear lista de modelos
        raw_models = data.get("models", [])
        diag.models = [m.get("name", "") for m in raw_models if m.get("name")]
        diag.model_available = any(
            m == model or m.startswith(model.split(":")[0])
            for m in diag.models
        )

    except urllib.error.URLError as e:
        diag.error = f"No se pudo conectar: {e.reason}"
    except Exception as e:
        diag.error = str(e)

    return diag


def _diag_disk() -> DiskDiag:
    """Recopila información de disco y archivos de la app."""
    diag = DiskDiag()

    # Espacio en disco
    try:
        import shutil
        total, used, free = shutil.disk_usage(_ROOT)
        diag.total_gb = total / (1024 ** 3)
        diag.free_gb = free / (1024 ** 3)
        diag.used_percent = (used / total) * 100 if total > 0 else 0
    except Exception as e:
        _logger.warning(f"Error obteniendo espacio en disco: {e}")

    # Carpeta de conversaciones
    conv_dir = _ROOT / "data" / "conversations"
    diag.data_dir_exists = conv_dir.exists()
    if diag.data_dir_exists:
        try:
            diag.conversations_count = len(list(conv_dir.glob("*.json")))
        except Exception:
            pass

    # Tamaño del log
    logs_dir = _ROOT / "logs"
    diag.logs_dir_exists = logs_dir.exists()
    log_file = logs_dir / "aura.log"
    if log_file.exists():
        try:
            diag.log_size_kb = log_file.stat().st_size / 1024
        except Exception:
            pass

    return diag


def _compute_summary(diag: DiagsResult) -> None:
    """Evalúa el estado general y genera el resumen y lista de problemas."""
    issues = []

    if not diag.ollama.reachable:
        issues.append(
            "Ollama no está disponible. "
            "Ejecutá 'ollama serve' para iniciarlo."
        )
    elif not diag.ollama.model_available:
        issues.append(
            f"El modelo '{diag.ollama.configured_model}' no está descargado. "
            f"Ejecutá: ollama pull {diag.ollama.configured_model}"
        )

    if not diag.config.env_file_exists:
        issues.append(
            "El archivo .env no fue encontrado. "
            "Ejecutá la app una vez para que se genere automáticamente."
        )

    if diag.disk.free_gb < 0.5:
        issues.append(
            f"Espacio libre en disco muy bajo ({diag.disk.free_gb:.1f} GB). "
            "Liberá espacio para evitar errores."
        )

    if diag.disk.log_size_kb > 4 * 1024:  # 4 MB
        issues.append(
            f"El archivo de log es grande ({diag.disk.log_size_kb:.0f} KB). "
            "Se rotará automáticamente al superar 5 MB."
        )

    diag.issues = issues
    diag.overall_ok = len(issues) == 0

    if diag.overall_ok:
        diag.summary = "Todo funciona correctamente."
    else:
        diag.summary = f"{len(issues)} problema(s) detectado(s). Revisá la sección de problemas."


# ──────────────────────────────────────────────────────────────────
# Función principal
# ──────────────────────────────────────────────────────────────────

def run_diagnostics() -> DiagsResult:
    """
    Ejecuta el diagnóstico completo de AURA.

    Realiza verificaciones de sistema, configuración, Ollama y disco.
    No lanza excepciones — cualquier error interno queda en el log.

    Returns:
        DiagsResult con todos los resultados del diagnóstico.
    """
    _logger.info("Ejecutando diagnóstico de AURA...")

    result = DiagsResult()

    try:
        result.system = _diag_system()
    except Exception as e:
        _logger.error(f"Error en diagnóstico de sistema: {e}")

    try:
        result.config = _diag_config()
    except Exception as e:
        _logger.error(f"Error en diagnóstico de config: {e}")

    try:
        ollama_url = result.config.ollama_url or "http://localhost:11434"
        model = result.config.ai_model or "qwen2.5:3b"
        result.ollama = _diag_ollama(ollama_url, model)
    except Exception as e:
        _logger.error(f"Error en diagnóstico de Ollama: {e}")
        result.ollama = OllamaDiag(error=str(e))

    try:
        result.disk = _diag_disk()
    except Exception as e:
        _logger.error(f"Error en diagnóstico de disco: {e}")

    try:
        _compute_summary(result)
    except Exception as e:
        _logger.error(f"Error calculando resumen: {e}")
        result.summary = "No se pudo calcular el resumen."

    _logger.info(
        f"Diagnóstico completado — OK={result.overall_ok}, "
        f"problemas={len(result.issues)}"
    )
    return result


# ──────────────────────────────────────────────────────────────────
# Autochequeo y Pruebas del Sistema (Self-Test)
# ──────────────────────────────────────────────────────────────────

@dataclass
class SelfTestItem:
    """Resultado individual de una prueba de autochequeo del sistema."""
    name: str
    passed: bool
    detail: str
    latency_ms: float = 0.0


def run_self_test() -> list[SelfTestItem]:
    """
    Ejecuta un conjunto de pruebas automatizadas y rápidas sobre los componentes clave de AURA.
    Retorna una lista de SelfTestItem.
    """
    import time
    items: list[SelfTestItem] = []

    # 1. Configuración (.env)
    t0 = time.perf_counter()
    try:
        from config.settings import settings
        all_cfg = settings.all()
        env_ok = settings.env_file.exists()
        dt = (time.perf_counter() - t0) * 1000
        items.append(SelfTestItem(
            name="Configuración (.env)",
            passed=env_ok and len(all_cfg) >= 5,
            detail=f"{len(all_cfg)} claves cargadas desde {settings.env_file.name}",
            latency_ms=dt,
        ))
    except Exception as e:
        items.append(SelfTestItem("Configuración (.env)", False, f"Error: {e}"))

    # 2. Proveedor de IA Activo
    t0 = time.perf_counter()
    try:
        from ai.provider_factory import get_default_provider
        prov = get_default_provider()
        ok, msg = prov.health_check()
        dt = (time.perf_counter() - t0) * 1000
        items.append(SelfTestItem(
            name=f"Proveedor IA ({prov.name.upper()})",
            passed=ok,
            detail=msg,
            latency_ms=dt,
        ))
    except Exception as e:
        items.append(SelfTestItem("Proveedor IA", False, f"Error: {e}"))

    # 3. Subsistema de Audio
    t0 = time.perf_counter()
    try:
        from voice.audio_manager import list_audio_devices
        devs = list_audio_devices()
        dt = (time.perf_counter() - t0) * 1000
        items.append(SelfTestItem(
            name="Subsistema de Audio",
            passed=True,
            detail=f"{len(devs)} dispositivo(s) detectado(s)",
            latency_ms=dt,
        ))
    except Exception as e:
        items.append(SelfTestItem("Subsistema de Audio", False, f"Error: {e}"))

    # 4. Memoria de Usuario (Fase 28)
    t0 = time.perf_counter()
    try:
        from core.user_memory import user_memory
        p_count = len(user_memory.list_paths())
        pr_count = len(user_memory.list_programs())
        f_count = len(user_memory.list_facts())
        dt = (time.perf_counter() - t0) * 1000
        items.append(SelfTestItem(
            name="Memoria de Usuario",
            passed=True,
            detail=f"{p_count} rutas, {pr_count} programas, {f_count} hechos recordados",
            latency_ms=dt,
        ))
    except Exception as e:
        items.append(SelfTestItem("Memoria de Usuario", False, f"Error: {e}"))

    # 5. Carpeta Workspace
    t0 = time.perf_counter()
    try:
        from config.settings import settings
        ws = settings.get_path("WORKSPACE_PATH")
        dt = (time.perf_counter() - t0) * 1000
        if ws and ws.exists():
            items.append(SelfTestItem(
                name="Carpeta Workspace",
                passed=True,
                detail=f"Existe y accesible: {ws}",
                latency_ms=dt,
            ))
        else:
            items.append(SelfTestItem(
                name="Carpeta Workspace",
                passed=False,
                detail=f"No encontrada o no creada: {ws}",
                latency_ms=dt,
            ))
    except Exception as e:
        items.append(SelfTestItem("Carpeta Workspace", False, f"Error: {e}"))

    # 6. Directorio de Logs
    t0 = time.perf_counter()
    try:
        from config.settings import settings
        log_dir = settings.logs_dir
        log_file = log_dir / "aura.log"
        dt = (time.perf_counter() - t0) * 1000
        items.append(SelfTestItem(
            name="Directorio de Logs",
            passed=log_dir.exists(),
            detail=f"Ruta: {log_file} ({log_file.stat().st_size / 1024:.1f} KB)" if log_file.exists() else f"Directorio OK: {log_dir}",
            latency_ms=dt,
        ))
    except Exception as e:
        items.append(SelfTestItem("Directorio de Logs", False, f"Error: {e}"))

    # 7. Índice de Aplicaciones
    t0 = time.perf_counter()
    try:
        from core.app_scanner import app_index_manager
        count = app_index_manager.count()
        dt = (time.perf_counter() - t0) * 1000
        items.append(SelfTestItem(
            name="Índice de Aplicaciones",
            passed=True,
            detail=f"{count} aplicación(es) indexada(s)",
            latency_ms=dt,
        ))
    except Exception as e:
        items.append(SelfTestItem("Índice de Aplicaciones", False, f"Error: {e}"))

    return items


def self_test_to_text(items: list[SelfTestItem]) -> str:
    """Genera un reporte formateado en texto para las pruebas de autochequeo."""
    lines = [
        "=" * 52,
        "  AUTOCHEQUEO DE COMPONENTES (AURA SELF-TEST)",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 52,
        "",
    ]
    passed_count = sum(1 for item in items if item.passed)
    total_count = len(items)

    for item in items:
        status_tag = "[PASS]" if item.passed else "[FAIL]"
        time_tag = f" ({item.latency_ms:.0f} ms)" if item.latency_ms > 0 else ""
        lines.append(f"  {status_tag:6} {item.name}{time_tag}")
        lines.append(f"         |-- {item.detail}")

    lines.append("")
    lines.append("-" * 52)
    lines.append(f"  Resumen: {passed_count}/{total_count} pruebas superadas.")
    if passed_count == total_count:
        lines.append("  Estado:  OK - Todos los subsistemas operativos.")
    else:
        lines.append(f"  Estado:  [!] {total_count - passed_count} componente(s) requieren atencion.")
    lines.append("=" * 52)

    return "\n".join(lines)

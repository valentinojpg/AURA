"""
AURA — Asistente y Diagnóstico de Ollama (Fase 30)

Provee utilidades para verificar el estado del servidor Ollama en Windows,
listar modelos descargados, sugerir comandos de instalación y asistir
al usuario durante el proceso de onboarding y configuración inicial.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any, Optional

from config.settings import settings
from utils.logger import get_logger

_logger = get_logger("aura.core.ollama_helper")

# Modelos locales recomendados para estudiantes y hardware estándar
RECOMMENDED_MODELS: list[dict[str, str]] = [
    {
        "name": "qwen2.5:3b",
        "size": "2.0 GB",
        "description": "Recomendado para AURA. Muy rápido, excelente en español, código y comandos.",
        "pull_cmd": "ollama pull qwen2.5:3b",
    },
    {
        "name": "llama3.2:3b",
        "size": "2.2 GB",
        "description": "Modelo ligero de Meta AI. Muy capaz para razonamiento y respuestas generales.",
        "pull_cmd": "ollama pull llama3.2:3b",
    },
    {
        "name": "deepseek-r1:1.5b",
        "size": "1.1 GB",
        "description": "Ultra liviano para razonamiento paso a paso en computadoras con recursos limitados.",
        "pull_cmd": "ollama pull deepseek-r1:1.5b",
    },
    {
        "name": "qwen2.5-coder:3b",
        "size": "2.0 GB",
        "description": "Especializado en programación, debugging, refactorización y tests.",
        "pull_cmd": "ollama pull qwen2.5-coder:3b",
    },
]


def is_ollama_installed() -> bool:
    """Verifica si el ejecutable de ollama está disponible en el PATH del sistema."""
    return shutil.which("ollama") is not None


def check_ollama_service(url: Optional[str] = None, timeout: float = 2.5) -> tuple[bool, str, list[str]]:
    """
    Comprueba si el servicio HTTP de Ollama está activo y respondiendo.

    Returns:
        (is_running, status_message, installed_models_list)
    """
    base_url = (url or settings.get("OLLAMA_URL", "http://localhost:11434") or "http://localhost:11434").rstrip("/")
    tags_url = f"{base_url}/api/tags"

    try:
        req = urllib.request.Request(tags_url, headers={"User-Agent": "AURA-Orion/0.56"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
                return True, f"Ollama activo ({len(models)} modelos instalados)", models
            return False, f"Respuesta HTTP inesperada: {resp.status}", []
    except urllib.error.URLError as e:
        return False, f"Servidor Ollama no detectado en {base_url} ({e.reason})", []
    except Exception as e:
        return False, f"Error conectando con Ollama: {e}", []


def get_installation_instructions() -> dict[str, Any]:
    """
    Retorna los pasos y comandos para instalar Ollama en Windows.
    """
    return {
        "is_installed": is_ollama_installed(),
        "download_url": "https://ollama.com/download/windows",
        "winget_command": "winget install Ollama.Ollama",
        "start_command": "ollama serve",
        "recommended_model": "qwen2.5:3b",
        "pull_command": "ollama pull qwen2.5:3b",
        "models": RECOMMENDED_MODELS,
        "tips": [
            "Descargá e instalá Ollama desde https://ollama.com o mediante winget.",
            "Una vez instalado, abrí una consola y ejecutá 'ollama pull qwen2.5:3b'.",
            "Asegurate de que el ícono de Ollama aparezca en la bandeja del sistema de Windows.",
            "Si no tenés GPU dedicada, los modelos de 3B o 1.5B funcionan fluidamente en CPU.",
        ],
    }


def format_ollama_guide_text() -> str:
    """Genera una guía explicativa en texto plano para el usuario o logs."""
    info = get_installation_instructions()
    lines = [
        "============================================================",
        "  GUÍA DE INSTALACIÓN Y CONFIGURACIÓN DE OLLAMA EN WINDOWS",
        "============================================================",
        "",
        f"1. Estado en el sistema: {'Instalado en PATH' if info['is_installed'] else 'No detectado en PATH'}",
        "2. Instalación rápida con Windows Package Manager (Winget):",
        f"   > {info['winget_command']}",
        "3. O descarga el instalador oficial desde:",
        f"   {info['download_url']}",
        "",
        "4. Descarga del modelo recomendado para AURA:",
        f"   > {info['pull_command']}",
        "",
        "5. Iniciar servicio local (si no inicia automáticamente):",
        f"   > {info['start_command']}",
        "",
        "Modelos recomendados:",
    ]
    for m in info["models"]:
        lines.append(f"  • {m['name']} ({m['size']}): {m['description']}")

    lines.append("============================================================")
    return "\n".join(lines)

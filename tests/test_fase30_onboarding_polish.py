# -*- coding: utf-8 -*-
"""
============================================================
AURA (Orion) — Pruebas Automatizadas: Fase 30
Onboarding, portabilidad y pulido final
============================================================
Valida:
1. ollama_helper (detección, modelos recomendados, guía interactiva).
2. backup_manager (creación ZIP, manifiesto, listado, restauración, dry-run).
3. SetupWizard (navegación de 5 pasos, configuración multi-proveedor, callback).
4. Scripts portables (.bat) y documentación completa (README.md).
"""

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error
import zipfile
import pytest

from core.ollama_helper import (
    RECOMMENDED_MODELS,
    check_ollama_service,
    format_ollama_guide_text,
    get_installation_instructions,
    is_ollama_installed,
)
import aura.core.ollama_helper as reexported_ollama_helper
from scripts.backup_manager import (
    create_backup,
    list_backups,
    restore_backup,
    _format_size,
)
from ui.wizard.setup_wizard import SetupWizard


# ============================================================
# 1. PRUEBAS DE OLLAMA_HELPER
# ============================================================

def test_ollama_recommended_models_structure():
    """Verifica que la lista de modelos recomendados tenga los campos esperados."""
    assert len(RECOMMENDED_MODELS) >= 3
    for model in RECOMMENDED_MODELS:
        assert "name" in model
        assert "size" in model
        assert "description" in model
        assert "pull_cmd" in model
        assert ":" in model["name"]  # formato tag:versión


def test_ollama_installation_instructions():
    """Verifica las instrucciones estructuradas de instalación de Ollama."""
    instr = get_installation_instructions()
    assert "winget_command" in instr
    assert "winget install" in instr["winget_command"]
    assert "download_url" in instr
    assert "ollama.com" in instr["download_url"]
    assert "recommended_model" in instr
    assert "qwen2.5:3b" in instr["recommended_model"]


def test_ollama_guide_text_formatting():
    """Verifica que el texto de ayuda incluya comandos e instrucciones."""
    guide = format_ollama_guide_text()
    assert isinstance(guide, str)
    assert "winget install Ollama.Ollama" in guide
    assert "qwen2.5:3b" in guide
    assert "https://ollama.com" in guide


def test_ollama_is_installed_boolean():
    """Verifica que is_ollama_installed retorne un booleano sin lanzar errores."""
    installed = is_ollama_installed()
    assert isinstance(installed, bool)


def test_ollama_service_check_mock_running():
    """Verifica la detección exitosa del servicio Ollama con mock de API."""
    mock_payload = json.dumps({
        "models": [{"name": "qwen2.5:3b"}, {"name": "llama3.2:3b"}]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = mock_payload
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        running, msg, models = check_ollama_service("http://localhost:11434")
        assert running is True
        assert "Ollama activo" in msg
        assert "qwen2.5:3b" in models


def test_ollama_service_check_mock_offline():
    """Verifica la respuesta segura cuando el servicio Ollama está inactivo."""
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        running, msg, models = check_ollama_service("http://localhost:11434")
        assert running is False
        assert models == []
        assert "no detectado" in msg.lower() or "error" in msg.lower()


def test_reexported_ollama_helper_symbols():
    """Verifica compatibilidad con aura.core.ollama_helper."""
    assert reexported_ollama_helper.check_ollama_service is check_ollama_service
    assert reexported_ollama_helper.RECOMMENDED_MODELS is RECOMMENDED_MODELS


# ============================================================
# 2. PRUEBAS DE BACKUP_MANAGER
# ============================================================

def test_format_size_utility():
    """Verifica el formateo de tamaños legibles."""
    assert _format_size(500) == "500.0 B"
    assert "KB" in _format_size(2048)
    assert "MB" in _format_size(1024 * 1024 * 5)


def test_create_list_and_restore_backup(tmp_path, monkeypatch):
    """Crea un backup en carpeta temporal, lo lista y lo restaura verificando integridad."""
    # Preparar entorno simulado
    fake_project = tmp_path / "fake_aura"
    fake_project.mkdir()
    fake_data = fake_project / "data"
    fake_data.mkdir()
    fake_env = fake_project / ".env"
    fake_env.write_text("AI_PROVIDER=ollama\nTHEME=dark\n", encoding="utf-8")

    # Archivo en data
    sub_data = fake_data / "conversations"
    sub_data.mkdir()
    test_conv = sub_data / "conv_123.json"
    test_conv.write_text('{"messages": ["Hola AURA", "¡Hola!"]}', encoding="utf-8")

    backup_dir = fake_project / "backups"

    # Redirigir constantes en backup_manager
    monkeypatch.setattr("scripts.backup_manager.PROJECT_ROOT", fake_project)
    monkeypatch.setattr("scripts.backup_manager.DATA_DIR", fake_data)
    monkeypatch.setattr("scripts.backup_manager.ENV_FILE", fake_env)
    monkeypatch.setattr("scripts.backup_manager.DEFAULT_BACKUP_DIR", backup_dir)

    # 1. Crear backup
    zip_result = create_backup(target_dir=backup_dir, include_env=True, tag="unit_test")
    assert zip_result.exists()
    assert zip_result.name.endswith("_unit_test.zip")

    # Verificar contenido interno del ZIP
    with zipfile.ZipFile(zip_result, "r") as zf:
        namelist = zf.namelist()
        assert "manifest.json" in namelist
        assert ".env" in namelist
        assert "data/conversations/conv_123.json" in namelist

        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest["aura_system"] == "AURA Orion"
        assert manifest["files_count"] >= 2

    # 2. Listar backups
    backups = list_backups(backup_dir=backup_dir)
    assert len(backups) == 1
    assert backups[0]["filename"] == zip_result.name
    assert backups[0]["manifest"] is not None
    assert backups[0]["manifest"]["files_count"] >= 2

    # 3. Restaurar en carpeta limpia
    restore_target_data = fake_project / "restored_data"
    restore_target_data.mkdir()

    # Dry run primero
    dry_res = restore_backup(
        zip_path=zip_result,
        target_data_dir=restore_target_data,
        restore_env=False,
        dry_run=True,
    )
    assert dry_res["success"] is True
    assert dry_res["dry_run"] is True
    assert not (restore_target_data / "conversations" / "conv_123.json").exists()

    # Restauración real
    real_res = restore_backup(
        zip_path=zip_result,
        target_data_dir=restore_target_data,
        restore_env=False,
        dry_run=False,
    )
    assert real_res["success"] is True
    assert (restore_target_data / "conversations" / "conv_123.json").exists()
    restored_content = (restore_target_data / "conversations" / "conv_123.json").read_text(
        encoding="utf-8"
    )
    assert "¡Hola!" in restored_content


# ============================================================
# 3. PRUEBAS DE SETUP_WIZARD
# ============================================================

def test_setup_wizard_initialization_and_navigation():
    """Verifica que el SetupWizard se instancie y permita navegar entre sus 5 pasos."""
    on_complete_called = False

    def mock_on_complete():
        nonlocal on_complete_called
        on_complete_called = True

    mock_page = MagicMock()

    wizard = SetupWizard(
        page=mock_page,
        on_complete=mock_on_complete,
    )

    assert wizard._step == 1
    assert wizard._total_steps == 5
    assert wizard._provider in ["ollama", "gemini", "openai", "anthropic", "mock"]

    # Generar contenido de cada paso
    for step_num in range(1, 6):
        wizard._step = step_num
        content = wizard._get_step_content()
        assert content is not None

    # Probar navegación adelante y atrás
    wizard._step = 1
    wizard._btn_prev = MagicMock()
    wizard._btn_next = MagicMock()
    wizard._dialog_content = MagicMock()
    wizard._dialog = MagicMock()

    wizard._next_step()
    assert wizard._step == 2

    wizard._provider = "gemini"

    wizard._next_step()
    assert wizard._step == 3

    wizard._prev_step()
    assert wizard._step == 2

    # Ir hasta el último paso
    wizard._step = 5
    with patch.object(wizard, "_close"), \
         patch("config.settings.settings.set") as mock_set, \
         patch("config.settings.settings.mark_first_run_done") as mock_first_run, \
         patch("ui.wizard.setup_wizard.reset_default_provider"):
        wizard._finish()
        assert on_complete_called is True
        assert mock_set.called
        assert mock_first_run.called


# ============================================================
# 4. PRUEBAS DE SCRIPTS PORTABLES Y DOCUMENTACIÓN
# ============================================================

def test_portable_scripts_exist_and_utf8():
    """Verifica que existan los 4 scripts .bat portables y usen codificación UTF-8 en consola."""
    root = Path(__file__).resolve().parent.parent

    aura_bat = root / "Aura.bat"
    setup_bat = root / "setup_env.bat"
    backup_bat = root / "backup.bat"
    test_bat = root / "test.bat"

    assert aura_bat.is_file(), "Aura.bat debe existir en la raíz"
    assert setup_bat.is_file(), "setup_env.bat debe existir en la raíz"
    assert backup_bat.is_file(), "backup.bat debe existir en la raíz"
    assert test_bat.is_file(), "test.bat debe existir en la raíz"

    aura_content = aura_bat.read_text(encoding="utf-8")
    assert "chcp 65001" in aura_content
    assert "run.py" in aura_content

    backup_content = backup_bat.read_text(encoding="utf-8")
    assert "chcp 65001" in backup_content
    assert "backup_manager.py" in backup_content

    test_content = test_bat.read_text(encoding="utf-8")
    assert "chcp 65001" in test_content
    assert "pytest" in test_content


def test_readme_comprehensive_content():
    """Verifica que README.md contenga las secciones clave actualizadas."""
    root = Path(__file__).resolve().parent.parent
    readme = root / "README.md"
    assert readme.is_file()

    content = readme.read_text(encoding="utf-8")
    assert "AURA — Orion" in content
    assert "Ollama" in content
    assert "backup.bat" in content
    assert "setup_env.bat" in content
    assert "Aura.bat" in content
    assert "test.bat" in content
    assert "qwen2.5:3b" in content

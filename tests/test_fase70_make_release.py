# -*- coding: utf-8 -*-
"""
================================================================================
AURA (Orion) — Tests de Regresión para Fase 70: Script de Release Portable
================================================================================
Valida:
1. Clasificación y sanitización de claves sensibles (API keys, tokens, passwords).
2. Generación automática y segura de .env.example desde .env preservando comentarios.
3. Limpieza previa segura: __pycache__, logs rotados viejos, wavs temporales, build/.
   Guardas estrictas: NUNCA toca código, assets, models/rvc, data real, .env ni requirements.
4. Verificación de seguridad anti-fugas: aborta si .env real existe en staging o en zip.
5. Copia a staging con exclusiones canónicas (env/, .git/, logs/, .env, backups)
   e inclusiones obligatorias (models/rvc/, assets/, data/ real, scripts/, bat, etc.).
6. Generación y verificación del archivo ZIP con manifiesto final.
================================================================================
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import zipfile
import pytest

from scripts.make_release import (
    clean_workspace,
    copy_release_files,
    create_release_zip,
    format_size,
    generate_env_example,
    is_sensitive_key,
    SecurityError,
    verify_no_env_file,
    verify_zip_security,
)


class TestFase70SensitiveKeys:
    """Pruebas para la detección y clasificación de claves sensibles."""

    def test_sensitive_keys_detection(self):
        # Claves sensibles deben retornar True
        assert is_sensitive_key("OPENAI_API_KEY") is True
        assert is_sensitive_key("ANTHROPIC_API_KEY") is True
        assert is_sensitive_key("GEMINI_API_KEY") is True
        assert is_sensitive_key("XAI_API_KEY") is True
        assert is_sensitive_key("CUSTOM_API_KEY") is True
        assert is_sensitive_key("ELEVENLABS_API_KEY") is True
        assert is_sensitive_key("RVC_KEY") is True
        assert is_sensitive_key("DB_PASSWORD") is True
        assert is_sensitive_key("AUTH_TOKEN") is True
        assert is_sensitive_key("SECRET_ACCESS_KEY") is True
        assert is_sensitive_key("MY_SECRET") is True

    def test_non_sensitive_keys_detection(self):
        # Claves públicas o de configuración general deben retornar False
        assert is_sensitive_key("AI_PROVIDER") is False
        assert is_sensitive_key("AI_MODEL") is False
        assert is_sensitive_key("OLLAMA_URL") is False
        assert is_sensitive_key("APP_LANGUAGE") is False
        assert is_sensitive_key("APP_THEME") is False
        assert is_sensitive_key("FIRST_RUN") is False
        assert is_sensitive_key("CONFIRM_DESTRUCTIVE") is False
        assert is_sensitive_key("CONFIRM_SHUTDOWN") is False
        assert is_sensitive_key("ROUTER_FIRST") is False
        assert is_sensitive_key("BROWSER_PREFERIDO") is False
        assert is_sensitive_key("AURA_PERSONALITY") is False
        assert is_sensitive_key("TTS_PROVIDER") is False
        assert is_sensitive_key("RVC_VOZ") is False
        assert is_sensitive_key("RVC_TTS_BASE") is False
        assert is_sensitive_key("PROMPT_MAESTRO") is False


class TestFase70EnvExampleGeneration:
    """Pruebas para la generación y sanitización de .env.example desde .env."""

    @pytest.fixture
    def sample_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        content = (
            "# Archivo de configuracion local de prueba\n"
            "# ── Proveedor ──\n"
            "AI_PROVIDER='openai'\n"
            "AI_MODEL='gpt-4o'\n"
            "OLLAMA_URL='http://localhost:11434'\n\n"
            "# ── Credenciales Secretas ──\n"
            "OPENAI_API_KEY='sk-proj-super-secret-1234567890'\n"
            "ANTHROPIC_API_KEY='sk-ant-api03-private-token'\n"
            "GEMINI_API_KEY='AIzaSyDummySecretKey'\n"
            "CUSTOM_API_KEY=''  # Clave custom vacia\n\n"
            "# ── Interfaz y Hardware ──\n"
            "FIRST_RUN='false'\n"
            "AUDIO_INPUT_DEVICE='Microfono de Estudio (USB Audio)'\n"
            "WORKSPACE_PATH='C:\\Users\\Cliente\\Documents'\n"
            "TTS_PROVIDER='rvc'\n"
        )
        env_file.write_text(content, encoding="utf-8")
        return env_file

    def test_generate_env_example_sanitization(self, sample_env_file, tmp_path):
        out_example = tmp_path / ".env.example"
        sanitized_count = generate_env_example(sample_env_file, out_example)

        assert out_example.exists()
        assert sanitized_count >= 3

        result_text = out_example.read_text(encoding="utf-8")

        # 1. Comprobar que NINGUNA clave secreta real sobrevivió
        assert "sk-proj-super-secret-1234567890" not in result_text
        assert "sk-ant-api03-private-token" not in result_text
        assert "AIzaSyDummySecretKey" not in result_text

        # 2. Comprobar placeholders
        assert "OPENAI_API_KEY='tu_openai_api_key_aqui'" in result_text
        assert "ANTHROPIC_API_KEY='tu_anthropic_api_key_aqui'" in result_text
        assert "GEMINI_API_KEY='tu_gemini_api_key_aqui'" in result_text
        assert "CUSTOM_API_KEY='tu_custom_api_key_aqui'" in result_text

        # 3. Comprobar que los comentarios y variables no sensibles se conservaron
        assert "# ── Proveedor ──" in result_text
        assert "AI_PROVIDER='openai'" in result_text
        assert "AI_MODEL='gpt-4o'" in result_text
        assert "OLLAMA_URL='http://localhost:11434'" in result_text
        assert "TTS_PROVIDER='rvc'" in result_text

        # 4. Comprobar que FIRST_RUN se normalizó a 'true' para la nueva máquina
        assert "FIRST_RUN='true'" in result_text

        # 5. Comprobar que dispositivos específicos de hardware fueron limpiados
        assert "AUDIO_INPUT_DEVICE=''" in result_text
        assert "Microfono de Estudio" not in result_text


class TestFase70WorkspaceCleanSafe:
    """Pruebas de la función clean_workspace y sus guardas inviolables."""

    @pytest.fixture
    def mock_workspace(self, tmp_path):
        ws = tmp_path / "mock_project"
        ws.mkdir()

        # Carpetas a limpiar
        pycache_dir = ws / "core" / "__pycache__"
        pycache_dir.mkdir(parents=True)
        (pycache_dir / "app.cpython-311.pyc").write_bytes(b"\x00" * 200)

        loose_pyc = ws / "skills" / "temp.pyc"
        loose_pyc.parent.mkdir(parents=True)
        loose_pyc.write_bytes(b"\x00" * 150)

        logs_dir = ws / "logs"
        logs_dir.mkdir()
        (logs_dir / "aura.log").write_text("Active log line 1\n", encoding="utf-8")
        (logs_dir / "aura.log.1").write_text("Old rotated log\n", encoding="utf-8")
        (logs_dir / "aura.log.2").write_text("Older rotated log\n", encoding="utf-8")

        audio_cache = ws / "data" / "audio_cache"
        audio_cache.mkdir(parents=True)
        (audio_cache / "tts_base_12345.wav").write_bytes(b"RIFF" + b"\x00" * 500)

        audio_test = ws / "data" / "audio_test"
        audio_test.mkdir(parents=True)
        (audio_test / "benchmark_base.wav").write_bytes(b"RIFF" + b"\x00" * 500)

        build_dir = ws / "build"
        build_dir.mkdir()
        (build_dir / "temp_build.obj").write_bytes(b"\x00" * 300)

        internal_dir = ws / "_internal"
        internal_dir.mkdir()
        (internal_dir / "temp_internal.dll").write_bytes(b"\x00" * 400)

        # ARCHIVOS CRÍTICOS QUE NUNCA DEBEN TOCARSE
        (ws / ".env").write_text("SECRET=123\n", encoding="utf-8")
        (ws / "requirements.txt").write_text("flet==0.86.5\n", encoding="utf-8")
        (ws / "run.py").write_text("print('AURA')\n", encoding="utf-8")
        (ws / "Aura.bat").write_text("@echo off\n", encoding="utf-8")

        models_dir = ws / "models" / "rvc" / "aura"
        models_dir.mkdir(parents=True)
        (models_dir / "aura.pth").write_bytes(b"MODEL_WEIGHTS" * 100)
        (models_dir / "aura.index").write_bytes(b"INDEX_DATA" * 50)

        assets_dir = ws / "assets"
        assets_dir.mkdir()
        (assets_dir / "logo_waifu.ico").write_bytes(b"\x00\x00\x01\x00" + b"\x00" * 100)

        data_real = ws / "data" / "conversations"
        data_real.mkdir(parents=True)
        (data_real / "session1.json").write_text('{"messages": []}', encoding="utf-8")

        return ws

    def test_clean_workspace_removes_caches_and_preserves_code(self, mock_workspace):
        stats = clean_workspace(mock_workspace, dry_run=False, verbose=False)

        assert stats["pycache_dirs_removed"] >= 1
        assert stats["pyc_files_removed"] >= 1
        assert stats["rotated_logs_removed"] == 2
        assert stats["temp_wavs_removed"] == 2
        assert stats["build_dirs_removed"] == 2
        assert stats["bytes_freed"] > 0

        # Verificaciones de elementos eliminados
        assert not (mock_workspace / "core" / "__pycache__").exists()
        assert not (mock_workspace / "skills" / "temp.pyc").exists()
        assert not (mock_workspace / "logs" / "aura.log.1").exists()
        assert not (mock_workspace / "logs" / "aura.log.2").exists()
        assert not (mock_workspace / "data" / "audio_cache" / "tts_base_12345.wav").exists()
        assert not (mock_workspace / "data" / "audio_test" / "benchmark_base.wav").exists()
        assert not (mock_workspace / "build").exists()
        assert not (mock_workspace / "_internal").exists()

        # VERIFICACIONES DE INTEGRIDAD: ARCHIVOS CRÍTICOS INTACTOS
        assert (mock_workspace / "logs" / "aura.log").exists()  # Log activo intacto
        assert (mock_workspace / ".env").exists()               # .env real intacto
        assert (mock_workspace / "requirements.txt").exists()   # requirements intacto
        assert (mock_workspace / "run.py").exists()             # código intacto
        assert (mock_workspace / "Aura.bat").exists()           # script portable intacto
        assert (mock_workspace / "models" / "rvc" / "aura" / "aura.pth").exists()    # modelo RVC intacto
        assert (mock_workspace / "models" / "rvc" / "aura" / "aura.index").exists()  # índice RVC intacto
        assert (mock_workspace / "assets" / "logo_waifu.ico").exists()               # icono waifu intacto
        assert (mock_workspace / "data" / "conversations" / "session1.json").exists() # historial intacto


class TestFase70SecurityVerification:
    """Pruebas exhaustivas para la verificación y detección de .env."""

    def test_verify_no_env_file_detects_env_in_root(self, tmp_path):
        staging = tmp_path / "staging_with_env"
        staging.mkdir()
        (staging / ".env").write_text("SECRET=1", encoding="utf-8")

        with pytest.raises(SecurityError, match="VIOLACIÓN DE SEGURIDAD"):
            verify_no_env_file(staging)

    def test_verify_no_env_file_detects_env_in_subfolder(self, tmp_path):
        staging = tmp_path / "staging_nested"
        sub = staging / "deep" / "nested"
        sub.mkdir(parents=True)
        (sub / ".env").write_text("SECRET=1", encoding="utf-8")

        with pytest.raises(SecurityError, match="VIOLACIÓN DE SEGURIDAD"):
            verify_no_env_file(staging)

    def test_verify_no_env_file_passes_with_env_example(self, tmp_path):
        staging = tmp_path / "staging_clean"
        staging.mkdir()
        (staging / ".env.example").write_text("AI_PROVIDER=ollama", encoding="utf-8")
        # No debe lanzar excepción
        verify_no_env_file(staging)

    def test_verify_zip_security_rejects_and_destroys_infected_zip(self, tmp_path):
        bad_zip = tmp_path / "corrupted_release.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr(".env", "SECRET=leaked")
            zf.writestr("requirements.txt", "flet")

        assert bad_zip.exists()
        with pytest.raises(SecurityError, match="El ZIP contenía '.env'"):
            verify_zip_security(bad_zip)

        # El ZIP debe haber sido eliminado automáticamente
        assert not bad_zip.exists()

    def test_verify_zip_security_rejects_env_directory_in_zip(self, tmp_path):
        bad_zip = tmp_path / "heavy_release.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr("env/Scripts/python.exe", b"MZ\x00")
            zf.writestr("requirements.txt", "flet")

        assert bad_zip.exists()
        with pytest.raises(SecurityError, match="entorno virtual"):
            verify_zip_security(bad_zip)

        assert not bad_zip.exists()


class TestFase70PackagingAndStaging:
    """Pruebas de la copia a staging y compresión ZIP completa."""

    @pytest.fixture
    def complete_mock_project(self, tmp_path):
        ws = tmp_path / "complete_project"
        ws.mkdir()

        # 1. Elementos que DEBEN excluirse
        env_dir = ws / "env" / "Lib" / "site-packages"
        env_dir.mkdir(parents=True)
        (env_dir / "torch.py").write_text("print('torch')", encoding="utf-8")

        git_dir = ws / ".git" / "objects"
        git_dir.mkdir(parents=True)
        (git_dir / "commit.pack").write_bytes(b"\x00" * 50)

        logs_dir = ws / "logs"
        logs_dir.mkdir()
        (logs_dir / "aura.log").write_text("log", encoding="utf-8")

        (ws / ".env").write_text("SECRET_KEY='mysecret'\n", encoding="utf-8")

        data_backups = ws / "data" / "backups"
        data_backups.mkdir(parents=True)
        (data_backups / "backup_old.zip").write_bytes(b"ZIP")

        data_audio_cache = ws / "data" / "audio_cache"
        data_audio_cache.mkdir(parents=True)
        (data_audio_cache / "temp.wav").write_bytes(b"WAV")

        # 2. Elementos que DEBEN incluirse
        (ws / ".env.example").write_text("AI_PROVIDER=ollama\n", encoding="utf-8")
        (ws / "requirements.txt").write_text("flet==0.86.5\n", encoding="utf-8")
        (ws / "Aura.bat").write_text("@echo off\n", encoding="utf-8")
        (ws / "setup_env.bat").write_text("@echo off\n", encoding="utf-8")
        (ws / "run.py").write_text("print('AURA')\n", encoding="utf-8")

        models_dir = ws / "models" / "rvc" / "aura"
        models_dir.mkdir(parents=True)
        (models_dir / "aura.pth").write_bytes(b"WEIGHTS" * 10)
        (models_dir / "aura.index").write_bytes(b"INDEX" * 5)

        assets_dir = ws / "assets"
        assets_dir.mkdir()
        (assets_dir / "logo_waifu.ico").write_bytes(b"\x00\x00\x01\x00" + b"\x00" * 10)

        scripts_dir = ws / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "make_shortcut.py").write_text("print('shortcut')", encoding="utf-8")

        data_conversations = ws / "data" / "conversations"
        data_conversations.mkdir(parents=True)
        (data_conversations / "chat1.json").write_text("{}", encoding="utf-8")
        (ws / "data" / "conversation_store.py").write_text("class ConversationStore: pass", encoding="utf-8")

        return ws

    def test_copy_release_files_creates_clean_staging(self, complete_mock_project, tmp_path):
        stage_dir = tmp_path / "ORION_release"
        copied = copy_release_files(complete_mock_project, stage_dir, verbose=False)

        assert len(copied) > 0

        # Verificaciones de exclusión
        assert not (stage_dir / "env").exists()
        assert not (stage_dir / ".git").exists()
        assert not (stage_dir / ".env").exists()
        assert not (stage_dir / "logs" / "aura.log").exists()
        assert not (stage_dir / "data" / "backups" / "backup_old.zip").exists()
        assert not (stage_dir / "data" / "audio_cache" / "temp.wav").exists()

        # Verificaciones de inclusión
        assert (stage_dir / "models" / "rvc" / "aura" / "aura.pth").exists()
        assert (stage_dir / "models" / "rvc" / "aura" / "aura.index").exists()
        assert (stage_dir / "assets" / "logo_waifu.ico").exists()
        assert (stage_dir / "data" / "conversation_store.py").exists()
        assert (stage_dir / "data" / "conversations" / "chat1.json").exists()
        assert (stage_dir / "scripts" / "make_shortcut.py").exists()
        assert (stage_dir / "requirements.txt").exists()
        assert (stage_dir / ".env.example").exists()
        assert (stage_dir / "Aura.bat").exists()
        assert (stage_dir / "setup_env.bat").exists()

        # Verificaciones de directorios operativos con .gitkeep
        assert (stage_dir / "logs" / ".gitkeep").exists()
        assert (stage_dir / "data" / "audio_cache" / ".gitkeep").exists()
        assert (stage_dir / "data" / "backups" / ".gitkeep").exists()

    def test_create_release_zip_manifest_and_namelist(self, complete_mock_project, tmp_path):
        stage_dir = tmp_path / "ORION_release"
        copy_release_files(complete_mock_project, stage_dir, verbose=False)

        zip_out = tmp_path / "AURA_release_test.zip"
        exclusions = ["env/", ".git/", ".env", "logs/"]
        created_zip, stats = create_release_zip(stage_dir, zip_out, exclusions)

        assert created_zip.exists()
        assert stats["files_count"] > 0
        assert stats["zip_size_bytes"] > 0

        # Validar contenido interno del ZIP
        with zipfile.ZipFile(created_zip, "r") as zf:
            namelist = zf.namelist()

            # Chequeos de exclusión en namelist
            assert ".env" not in namelist
            assert not any(n.startswith("env/") or n.startswith("env\\") for n in namelist)
            assert not any(n.startswith(".git/") or n.startswith(".git\\") for n in namelist)

            # Chequeos de inclusión en namelist
            assert "requirements.txt" in namelist
            assert ".env.example" in namelist
            assert "Aura.bat" in namelist
            assert "setup_env.bat" in namelist
            assert "release_manifest.json" in namelist

            # Validar contenido del manifiesto
            manifest_bytes = zf.read("release_manifest.json")
            manifest = json.loads(manifest_bytes.decode("utf-8"))
            assert manifest["product"].startswith("AURA")
            assert manifest["python_target"] == "3.11"
            assert "rebuild_steps" in manifest

    def test_extract_release_and_bootstrap_from_zero(self, complete_mock_project, tmp_path):
        # 1. Preparar staging y crear ZIP
        stage_dir = tmp_path / "ORION_release"
        copy_release_files(complete_mock_project, stage_dir, verbose=False)
        zip_out = tmp_path / "AURA_release_clean.zip"
        exclusions = ["env/", ".git/", ".env", "logs/"]
        created_zip, stats = create_release_zip(stage_dir, zip_out, exclusions)

        # 2. Descomprimir en una carpeta completamente nueva
        unzip_dir = tmp_path / "fresh_extracted_aura"
        unzip_dir.mkdir()
        with zipfile.ZipFile(created_zip, "r") as zf:
            zf.extractall(unzip_dir)

        # 3. Comprobar que en la carpeta extraída NO existen .env ni env/
        assert not (unzip_dir / ".env").exists()
        assert not (unzip_dir / "env").exists()

        # 4. Comprobar presencia de archivos de inicio
        assert (unzip_dir / ".env.example").exists()
        assert (unzip_dir / "setup_env.bat").exists()
        assert (unzip_dir / "Aura.bat").exists()
        assert (unzip_dir / "requirements.txt").exists()
        assert (unzip_dir / "models" / "rvc" / "aura" / "aura.pth").exists()
        assert (unzip_dir / "assets" / "logo_waifu.ico").exists()

        # 5. Simular creación de .env desde .env.example (como hace setup_env.bat)
        shutil.copy(unzip_dir / ".env.example", unzip_dir / ".env")
        assert (unzip_dir / ".env").exists()

        # 6. Leer y validar que .env tiene variables válidas para arrancar
        env_content = (unzip_dir / ".env").read_text(encoding="utf-8")
        assert "AI_PROVIDER=ollama" in env_content


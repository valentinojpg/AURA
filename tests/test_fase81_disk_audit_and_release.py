# -*- coding: utf-8 -*-
"""
================================================================================
AURA (Orion) — Tests de Regresión para Fase 81:
Auditoría de disco, limpieza segura y release actualizado.
================================================================================
Valida:
1. Auditoría de disco (scripts/disk_audit.py):
   - Formato descendente, cálculo en MB, escritura en logs/disk_audit.txt UTF-8.
2. Limpieza segura y líneas rojas (scripts/safe_clean.py):
   - Preservación estricta de: models/rvc/, assets/backgrounds/current.*, logo, data/ real, .env.
   - Eliminación de: __pycache__, logs rotados viejos, assets/backgrounds/cache/.
   - Respeto del flag CLEAN_TTS_CACHE (opt-in).
   - Poda de Whisper conservando únicamente WHISPER_MODEL y podando tamaños extras.
3. Empaquetado Release Fase 81 (scripts/make_release.py):
   - Exclusiones obligatorias: env/, .git/, logs/, __pycache__/, build/, _internal/,
     assets/backgrounds/cache/, data/tts_cache/, models/stt/, *.wav temporales, .env, backups.
   - Inclusiones obligatorias: código, scripts, assets (fondo en uso), models/rvc/,
     data/ real, requirements.txt, .env.example, Aura.bat, Aura.lnk, make_shortcut.py.
   - Check pre-zip que aborta si detecta .env o env/ en staging.
   - Manifiesto con verificación de exclusiones y pasos de restauración.
================================================================================
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import zipfile
import pytest

from scripts.disk_audit import get_dir_size, run_disk_audit
from scripts.safe_clean import run_safe_cleanup, safe_delete_file
from scripts.make_release import (
    copy_release_files,
    create_release_zip,
    SecurityError,
    verify_pre_zip_security,
    verify_zip_security,
)


class TestFase81DiskAudit:
    """Pruebas para el script de auditoría de disco."""

    def test_get_dir_size_calculates_correctly(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "file1.bin").write_bytes(b"A" * 1024)
        (sub / "file2.bin").write_bytes(b"B" * 2048)

        total = get_dir_size(sub)
        assert total == 3072

    def test_run_disk_audit_generates_report_and_file(self, tmp_path):
        root = tmp_path / "mock_project"
        root.mkdir()
        (root / "folder_a").mkdir()
        (root / "folder_a" / "test.bin").write_bytes(b"X" * 1024 * 1024)  # 1 MB
        (root / "folder_b").mkdir()
        (root / "folder_b" / "test2.bin").write_bytes(b"Y" * 512 * 1024)  # 0.5 MB

        log_file = root / "logs" / "disk_audit.txt"
        report = run_disk_audit(root=root, save_path=log_file)

        assert log_file.exists()
        saved_text = log_file.read_text(encoding="utf-8")
        assert "AUDITORIA DE DISCO" in saved_text
        assert "folder_a/" in saved_text
        assert "folder_b/" in saved_text
        # folder_a debe aparecer antes que folder_b por ser más grande
        assert saved_text.index("folder_a/") < saved_text.index("folder_b/")


class TestFase81SafeCleanAndRedLines:
    """Pruebas para la limpieza segura y protección de líneas rojas."""

    def test_red_lines_violation_raises_error(self, tmp_path):
        # 1. models/rvc/
        rvc_file = tmp_path / "models" / "rvc" / "aura" / "aura.pth"
        rvc_file.parent.mkdir(parents=True)
        rvc_file.write_bytes(b"VOICE")
        with pytest.raises(PermissionError, match="LÍNEA ROJA.*models/rvc"):
            safe_delete_file(rvc_file)

        # 2. assets/backgrounds/current.gif
        bg_file = tmp_path / "assets" / "backgrounds" / "current.gif"
        bg_file.parent.mkdir(parents=True)
        bg_file.write_bytes(b"GIF")
        with pytest.raises(PermissionError, match="LÍNEA ROJA.*fondo activo"):
            safe_delete_file(bg_file)

        # 3. .env
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET=123", encoding="utf-8")
        with pytest.raises(PermissionError, match="LÍNEA ROJA.*.env"):
            safe_delete_file(env_file)

        # 4. assets/logo.png
        logo_file = tmp_path / "assets" / "logo.png"
        logo_file.write_bytes(b"LOGO")
        with pytest.raises(PermissionError, match="LÍNEA ROJA.*logo"):
            safe_delete_file(logo_file)

    def test_safe_clean_cleans_cache_and_preserves_actives(self, tmp_path, monkeypatch):
        root = tmp_path / "project"
        root.mkdir()

        # Configurar .env con WHISPER_MODEL=tiny y CLEAN_TTS_CACHE=false
        env_content = (
            "WHISPER_MODEL='tiny'\n"
            "CLEAN_TTS_CACHE='false'\n"
        )
        (root / ".env").write_text(env_content, encoding="utf-8")

        # Carpetas regenerables
        pycache = root / "aura" / "__pycache__"
        pycache.mkdir(parents=True)
        (pycache / "core.cpython-311.pyc").write_bytes(b"PYC")

        logs_dir = root / "logs"
        logs_dir.mkdir()
        (logs_dir / "aura.log").write_text("ACTIVE LOG", encoding="utf-8")
        (logs_dir / "aura.log.1").write_text("OLD ROTATED LOG", encoding="utf-8")

        bg_cache = root / "assets" / "backgrounds" / "cache"
        bg_cache.mkdir(parents=True)
        (bg_cache / "frame_0001.png").write_bytes(b"PNG")

        tts_cache = root / "data" / "tts_cache"
        tts_cache.mkdir(parents=True)
        (tts_cache / "voice_cached.wav").write_bytes(b"WAV")

        # Whisper models: tiny (conservar) y medium (podar)
        stt_dir = root / "models" / "stt"
        whisper_tiny = stt_dir / "models--Systran--faster-whisper-tiny"
        whisper_tiny.mkdir(parents=True)
        (whisper_tiny / "model.bin").write_bytes(b"TINY")

        whisper_med = stt_dir / "models--Systran--faster-whisper-medium"
        whisper_med.mkdir(parents=True)
        (whisper_med / "model.bin").write_bytes(b"MEDIUM" * 100)

        # Ejecutar limpieza
        stats = run_safe_cleanup(root=root, dry_run=False, verbose=False)

        # Verificaciones
        assert not (pycache / "core.cpython-311.pyc").exists()
        assert not (logs_dir / "aura.log.1").exists()
        assert (logs_dir / "aura.log").exists()  # Log activo conservado
        assert not (bg_cache / "frame_0001.png").exists()

        # TTS cache preservado porque CLEAN_TTS_CACHE=false
        assert (tts_cache / "voice_cached.wav").exists()

        # Whisper poda: tiny conservado, medium eliminado
        assert (whisper_tiny / "model.bin").exists()
        assert not (whisper_med / "model.bin").exists()
        assert stats["whisper_files_removed"] > 0
        assert stats["bytes_freed"] > 0

    def test_safe_clean_cleans_tts_cache_when_opt_in(self, tmp_path):
        root = tmp_path / "project_opt_in"
        root.mkdir()

        (root / ".env").write_text("CLEAN_TTS_CACHE='true'\nWHISPER_MODEL='tiny'\n", encoding="utf-8")
        tts_cache = root / "data" / "tts_cache"
        tts_cache.mkdir(parents=True)
        (tts_cache / "audio1.wav").write_bytes(b"WAV1")

        run_safe_cleanup(root=root, dry_run=False, verbose=False)

        # Ahora sí debe haber sido eliminado
        assert not (tts_cache / "audio1.wav").exists()


class TestFase81ReleaseUpdated:
    """Pruebas para el generador de release y verificaciones pre/post-zip."""

    @pytest.fixture
    def full_mock_workspace(self, tmp_path):
        ws = tmp_path / "aura_workspace"
        ws.mkdir()

        # Inclusiones obligatorias
        (ws / "run.py").write_text("print('AURA')", encoding="utf-8")
        (ws / "Aura.bat").write_text("@echo off", encoding="utf-8")
        (ws / "Aura.lnk").write_bytes(b"SHORTCUT")
        (ws / "setup_env.bat").write_text("@echo off", encoding="utf-8")
        (ws / "requirements.txt").write_text("flet==0.86.5\n", encoding="utf-8")
        (ws / ".env.example").write_text("AI_PROVIDER=ollama\n", encoding="utf-8")

        scripts_dir = ws / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "make_shortcut.py").write_text("print('shortcut')", encoding="utf-8")

        models_rvc = ws / "models" / "rvc" / "aura"
        models_rvc.mkdir(parents=True)
        (models_rvc / "aura.pth").write_bytes(b"RVC_MODEL")
        (models_rvc / "aura.index").write_bytes(b"RVC_INDEX")

        assets_dir = ws / "assets" / "backgrounds"
        assets_dir.mkdir(parents=True)
        (assets_dir / "current.gif").write_bytes(b"GIF")
        (assets_dir / "current_meta.json").write_text("{}", encoding="utf-8")
        (ws / "assets" / "logo_waifu.ico").write_bytes(b"ICO")

        data_dir = ws / "data" / "conversations"
        data_dir.mkdir(parents=True)
        (data_dir / "chat1.json").write_text("{}", encoding="utf-8")

        # Exclusiones obligatorias
        (ws / ".env").write_text("SECRET=mysecret", encoding="utf-8")

        env_dir = ws / "env" / "Lib"
        env_dir.mkdir(parents=True)
        (env_dir / "torch.py").write_bytes(b"HEAVY")

        git_dir = ws / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_bytes(b"GIT")

        stt_dir = ws / "models" / "stt" / "models--Systran--faster-whisper-tiny"
        stt_dir.mkdir(parents=True)
        (stt_dir / "model.bin").write_bytes(b"WHISPER")

        bg_cache = ws / "assets" / "backgrounds" / "cache"
        bg_cache.mkdir(parents=True)
        (bg_cache / "frame_0000.png").write_bytes(b"CACHE")

        tts_cache = ws / "data" / "tts_cache"
        tts_cache.mkdir(parents=True)
        (tts_cache / "temp.wav").write_bytes(b"WAV")

        backups_dir = ws / "data" / "backups"
        backups_dir.mkdir(parents=True)
        (backups_dir / "backup.zip").write_bytes(b"BACKUP")

        return ws

    def test_pre_zip_security_check_aborts_on_env_or_models_stt(self, tmp_path):
        staging = tmp_path / "infected_staging"
        staging.mkdir()

        # 1. Con .env
        (staging / ".env").write_text("KEY=1", encoding="utf-8")
        with pytest.raises(SecurityError, match="VIOLACIÓN DE SEGURIDAD"):
            verify_pre_zip_security(staging)
        (staging / ".env").unlink()

        # 2. Con env/
        (staging / "env").mkdir()
        (staging / "env" / "file.txt").write_text("venv", encoding="utf-8")
        with pytest.raises(SecurityError, match="carpeta de entorno virtual"):
            verify_pre_zip_security(staging)
        shutil.rmtree(staging / "env")

        # 3. Con models/stt/
        stt_p = staging / "models" / "stt"
        stt_p.mkdir(parents=True)
        (stt_p / "model.bin").write_bytes(b"MODEL")
        with pytest.raises(SecurityError, match="modelos STT de Whisper"):
            verify_pre_zip_security(staging)

    def test_copy_release_files_and_create_zip_full_pipeline(self, full_mock_workspace, tmp_path):
        stage_dir = tmp_path / "ORION_release"
        copied = copy_release_files(full_mock_workspace, stage_dir, verbose=False)
        assert len(copied) > 0

        # Verificación en staging
        assert not (stage_dir / ".env").exists()
        assert not (stage_dir / "env").exists()
        assert not (stage_dir / ".git").exists()
        assert not (stage_dir / "models" / "stt" / "models--Systran--faster-whisper-tiny").exists()
        assert not (stage_dir / "assets" / "backgrounds" / "cache" / "frame_0000.png").exists()
        assert not (stage_dir / "data" / "tts_cache" / "temp.wav").exists()
        assert not (stage_dir / "data" / "backups" / "backup.zip").exists()

        # Inclusiones
        assert (stage_dir / "models" / "rvc" / "aura" / "aura.pth").exists()
        assert (stage_dir / "assets" / "backgrounds" / "current.gif").exists()
        assert (stage_dir / "assets" / "logo_waifu.ico").exists()
        assert (stage_dir / "data" / "conversations" / "chat1.json").exists()
        assert (stage_dir / "Aura.bat").exists()
        assert (stage_dir / "Aura.lnk").exists()
        assert (stage_dir / "setup_env.bat").exists()
        assert (stage_dir / "requirements.txt").exists()
        assert (stage_dir / ".env.example").exists()

        # Comprimir a ZIP
        zip_out = tmp_path / "AURA_release_test.zip"
        exclusions = [
            "env/", ".git/", "logs/", "__pycache__/", "build/", "_internal/",
            "assets/backgrounds/cache/", "data/tts_cache/", "models/stt/",
            "*.wav temporales", ".env", "data/backups/"
        ]
        created_zip, stats = create_release_zip(stage_dir, zip_out, exclusions)

        assert created_zip.exists()
        assert stats["zip_size_bytes"] > 0

        # Inspección del ZIP
        with zipfile.ZipFile(created_zip, "r") as zf:
            namelist = zf.namelist()
            # Prohibidos
            assert ".env" not in namelist
            assert not any(n.startswith("env/") for n in namelist)
            assert not any(n.startswith(".git/") for n in namelist)
            assert not any(n.startswith("models/stt/") and not n.endswith(".gitkeep") for n in namelist)
            assert not any(n.startswith("assets/backgrounds/cache/") and not n.endswith(".gitkeep") for n in namelist)
            assert not any(n.startswith("data/tts_cache/") and n.endswith(".wav") for n in namelist)

            # Requeridos
            assert "Aura.bat" in namelist
            assert "Aura.lnk" in namelist
            assert "setup_env.bat" in namelist
            assert "requirements.txt" in namelist
            assert ".env.example" in namelist
            assert "models/rvc/aura/aura.pth" in namelist
            assert "assets/backgrounds/current.gif" in namelist
            assert "release_manifest.json" in namelist

            # Validar manifiesto
            manifest = json.loads(zf.read("release_manifest.json").decode("utf-8"))
            assert "rebuild_steps" in manifest
            assert any("Whisper" in s for s in manifest["rebuild_steps"])
            assert any("setup_env.bat" in s for s in manifest["rebuild_steps"])

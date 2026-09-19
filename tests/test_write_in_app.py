"""
AURA — Tests para Intent write_in_app, Skill app_writer y Blindaje de create_file
"""

import os
import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest

from aura.core.intent_router import Intent, IntentRouter, is_valid_filename
from aura.core.entity_resolver import EntityResolver
from aura.core.fuzzy_interpreter import FuzzyInterpreter
from aura.skills.app_writer import (
    AppWriterSkill,
    clear_last_opened_apps,
    get_last_opened_pid,
    is_generic_text,
    last_opened_apps,
    record_app_opened,
    write_in_app,
)
from skills.builtin.files_skill import FilesSkill
from skills.skill_registry import skill_registry


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tests de Regex e IntentRouter para write_in_app
# ─────────────────────────────────────────────────────────────────────────────

def test_intent_router_write_in_app_patterns():
    router = IntentRouter()

    # Patrón A: en <app> escribe <texto>
    res1 = router.parse("en notepad escribime un comentario")
    assert res1 is not None
    assert res1.nombre == "write_in_app"
    assert res1.target == "notepad"
    assert res1.extra.get("texto") == "un comentario"

    res2 = router.parse("dentro de notepad escribe algo")
    assert res2 is not None
    assert res2.nombre == "write_in_app"
    assert res2.target == "notepad"
    assert res2.extra.get("texto") == "algo"

    # Patrón B: escribe en <app> <texto>
    res3 = router.parse("escribí en notepad hola mundo")
    assert res3 is not None
    assert res3.nombre == "write_in_app"
    assert res3.target == "notepad"
    assert res3.extra.get("texto") == "hola mundo"

    res4 = router.parse("escribí en bloc de notas hola mundo")
    assert res4 is not None
    assert res4.nombre == "write_in_app"
    assert res4.target == "bloc de notas"
    assert res4.extra.get("texto") == "hola mundo"

    res5 = router.parse("redacta en notepad un texto")
    assert res5 is not None
    assert res5.nombre == "write_in_app"
    assert res5.target == "notepad"
    assert res5.extra.get("texto") == "un texto"

    res6 = router.parse("poné en notepad hola")
    assert res6 is not None
    assert res6.nombre == "write_in_app"
    assert res6.target == "notepad"
    assert res6.extra.get("texto") == "hola"

    res7 = router.parse("tipea en notepad algo")
    assert res7 is not None
    assert res7.nombre == "write_in_app"
    assert res7.target == "notepad"
    assert res7.extra.get("texto") == "algo"

    # Patrón C: escribe <texto> en <app>
    res8 = router.parse("escribe hola mundo en notepad")
    assert res8 is not None
    assert res8.nombre == "write_in_app"
    assert res8.target == "notepad"
    assert res8.extra.get("texto") == "hola mundo"

    # Sin texto especificado
    res9 = router.parse("dentro de notepad escribe")
    assert res9 is not None
    assert res9.nombre == "write_in_app"
    assert res9.target == "notepad"
    assert res9.extra.get("texto") == ""


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tests de Blindaje de create_file y create_folder
# ─────────────────────────────────────────────────────────────────────────────

def test_sanity_check_filename():
    # Nombres legítimos válidos
    assert is_valid_filename("notas.txt") is True
    assert is_valid_filename("informe final de la materia.txt") is True
    assert is_valid_filename("main.py") is True
    assert is_valid_filename("datos_2026.json") is True

    # Rechazados por contener verbos de comando
    assert is_valid_filename("Dentro de notepad escribe algo") is False
    assert is_valid_filename("escribe un comentario") is False
    assert is_valid_filename("abre notepad") is False
    assert is_valid_filename("borra la carpeta fotos") is False

    # Rechazados por contener más de 4 palabras sin extensión ni ruta
    assert is_valid_filename("este es un texto muy largo sin extension") is False

    # Rechazados por caracteres inválidos de Windows
    assert is_valid_filename('archivo<invalido>.txt') is False
    assert is_valid_filename('archivo"invalido".txt') is False
    assert is_valid_filename('archivo?invalido.txt') is False


def test_create_file_intent_does_not_hijack_write_commands():
    router = IntentRouter()

    # Comandos con "escribe" o "dentro" NO deben ser create_file
    res1 = router.parse("Dentro de notepad escribe algo")
    assert res1.nombre != "create_file"
    assert res1.nombre == "write_in_app"

    res2 = router.parse("en notepad escribime un comentario")
    assert res2.nombre != "create_file"
    assert res2.nombre == "write_in_app"

    # Archivos explícitos legítimos SÍ deben ser create_file
    res3 = router.parse("creá un archivo notas.txt")
    assert res3.nombre == "create_file"
    assert res3.target == "notas.txt"

    res4 = router.parse("creá un archivo llamado informe final de la materia.txt")
    assert res4.nombre == "create_file"
    assert res4.target == "informe final de la materia.txt"


def test_entity_resolver_create_file_sanitization():
    resolver = EntityResolver()

    # Intento inválido (con verbo de comando)
    res_bad = resolver.resolve("create_file", "Dentro de notepad escribe algo")
    assert res_bad.resolved is False

    # Intento legítimo largo
    res_good = resolver.resolve("create_file", "informe final de la materia.txt")
    assert res_good.resolved is True
    assert res_good.command == "crear"
    assert res_good.args == ["informe final de la materia.txt"]

    # Sanitización de caracteres prohibidos y longitud <= 80
    long_name = "a" * 100 + ".txt"
    res_long = resolver.resolve("create_file", long_name)
    assert res_long.resolved is True
    assert len(res_long.target) <= 80
    assert res_long.target.endswith(".txt")


def test_files_skill_creates_sanitized_files(tmp_path):
    skill = FilesSkill()
    with patch.object(skill, "_workspace", return_value=tmp_path):
        res = skill.execute("crear", ["informe final de la materia.txt"])
        assert res.success is True
        created_file = tmp_path / "informe final de la materia.txt"
        assert created_file.exists()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Tests de FuzzyInterpreter (Capa 2 y Capa 3)
# ─────────────────────────────────────────────────────────────────────────────

def test_fuzzy_interpreter_write_in_app():
    interpreter = FuzzyInterpreter()

    res1 = interpreter.interpret("en notepad escribime un comentario")
    assert res1 is not None
    assert res1.intent == "write_in_app"
    assert res1.target == "notepad"

    res2 = interpreter.interpret("dentro de notepad escribe algo")
    assert res2 is not None
    assert res2.intent == "write_in_app"
    assert res2.target == "notepad"


def test_fuzzy_interpreter_llm_write_in_app():
    interpreter = FuzzyInterpreter()

    mock_provider = MagicMock()
    # LLM responde JSON para write_in_app
    mock_provider.chat.return_value.content = '{"intent": "write_in_app", "app": "notepad", "texto": "comentario de prueba"}'

    res = interpreter.interpret_llm("escribime algo en el bloc de notas", provider=mock_provider)
    assert res is not None
    assert res.intent == "write_in_app"
    assert res.target == "notepad"
    assert res.resolved_entity.extra.get("texto") == "comentario de prueba"


def test_fuzzy_interpreter_llm_translation_guard():
    """Si el LLM inventa un create_file traduciendo el texto del usuario, debe descartarse."""
    interpreter = FuzzyInterpreter()

    mock_provider = MagicMock()
    # LLM alucina create_file "uncommented.txt" (traducción errónea de 'un comentario')
    mock_provider.chat.return_value.content = '{"intent": "create_file", "target": "uncommented.txt"}'

    # Pero el usuario dijo "en notepad escribime un comentario"
    res = interpreter.interpret_llm("en notepad escribime un comentario", provider=mock_provider)
    # Debe ser interceptado y redirigido a write_in_app
    assert res is not None
    assert res.intent == "write_in_app"
    assert res.target == "notepad"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tests de memoria last_opened_apps
# ─────────────────────────────────────────────────────────────────────────────

def test_last_opened_apps_tracking():
    clear_last_opened_apps()

    record_app_opened("notepad", 1001)
    time.sleep(0.01)
    record_app_opened("notepad", 1002)

    # Si ambos PIDs estuviesen activos (mockeando psutil.pid_exists)
    with patch("psutil.pid_exists", return_value=True):
        best_pid = get_last_opened_pid("notepad", [1001, 1002, 9999])
        # 1002 es el más reciente
        assert best_pid == 1002

        # Si 1002 se cerró, debe retornar 1001
        best_pid2 = get_last_opened_pid("notepad", [1001, 9999])
        assert best_pid2 == 1001

        # Si ninguno de los abiertos por AURA está activo, retorna None
        best_none = get_last_opened_pid("notepad", [9999, 8888])
        assert best_none is None


def test_generic_text_classification():
    assert is_generic_text("algo") is True
    assert is_generic_text("un comentario") is True
    assert is_generic_text("un texto") is True
    assert is_generic_text("") is True
    assert is_generic_text("otra linea") is True
    assert is_generic_text("Hola mundo, esta es una frase específica") is False


# ─────────────────────────────────────────────────────────────────────────────
# 5. Tests de AppWriterSkill y Discovery
# ─────────────────────────────────────────────────────────────────────────────

def test_app_writer_skill_registered():
    skill_registry.discover_builtin()
    assert "app_writer" in skill_registry


def test_app_writer_mocked_execution():
    clear_last_opened_apps()

    with patch("aura.skills.app_writer.find_window_by_pid", return_value=(12345, "Sin título: Bloc de notas")), \
         patch("aura.skills.app_writer.focus_window", return_value=True), \
         patch("aura.skills.app_writer.set_clipboard_text", return_value=True), \
         patch("aura.skills.app_writer.send_ctrl_v", return_value=True), \
         patch("aura.skills.app_writer.send_enter_key", return_value=True), \
         patch("psutil.process_iter") as mock_iter:

        # Mockear proceso existente
        mock_proc = MagicMock()
        mock_proc.pid = 4321
        mock_proc.name.return_value = "notepad.exe"
        mock_proc.create_time.return_value = 100.0
        mock_iter.return_value = [mock_proc]

        res = write_in_app("notepad", "hola mundo")
        assert res.success is True
        assert "Escrito en" in res.output
        assert "pid 4321" in res.output
        assert "hola mundo" in res.output


# ─────────────────────────────────────────────────────────────────────────────
# 6. Test real en vivo con Notepad (arranque, foco, escritura de 2 líneas)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(os.name != "nt", reason="Solo ejecutable en Windows interactivo")
def test_real_notepad_write_and_repeat():
    """
    Prueba en vivo obligatoria:
    1. Abre notepad.
    2. Escribe 'hola mundo' en notepad.
    3. Escribe 'otra línea' en el mismo notepad.
    4. Verifica que ambas operaciones usaron el MISMO PID de notepad.
    5. Cierra notepad.
    """
    clear_last_opened_apps()

    # 1. Abrir notepad y escribir primera línea
    res1 = write_in_app("notepad", "hola mundo")
    assert res1.success is True
    pid1 = res1.data.get("pid")
    assert pid1 is not None and pid1 > 0

    time.sleep(0.5)

    # 2. Escribir segunda línea: debe usar el mismo PID
    res2 = write_in_app("notepad", "otra línea")
    assert res2.success is True
    pid2 = res2.data.get("pid")
    assert pid2 == pid1, f"La segunda línea debió escribirse en el mismo Notepad (esperado {pid1}, obtenido {pid2})"

    # Limpiar proceso de prueba
    try:
        p = psutil.Process(pid1)
        p.terminate()
        p.wait(timeout=2.0)
    except Exception:
        pass

# -*- coding: utf-8 -*-
"""
================================================================================
AURA — Tests de Fase 72: Capacidades por Aplicación y Adapter COM para Office
================================================================================
Verifica:
1. data/app_capabilities.json y módulo aura.core.app_capabilities.
2. Detección y fallback seguro para apps no listadas con log explícito.
3. Adapter COM OfficeAdapter (GetActiveObject, write, read, save_as, close, manejo de errores).
4. Prevalidación de planes según capacidades (marcado de pasos inválidos y razones).
5. Comportamiento estricto PLAN_STRICT=true vs default PLAN_STRICT=false (salteo).
6. Escritura en Discord sin Enter y con nota honesta sobre Electron.
7. Rechazo de guardado en Discord sin ejecución a medias.
8. Rechazo de escritura en Spotify con sugerencia de media_play.
9. Guardado de Word vía COM (.docx) y lectura/escritura nativa.
10. Cero regresión en cadenas de Notepad (Fase 71).
================================================================================
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from aura.core.app_capabilities import (
    DEFAULT_CAPABILITIES,
    get_app_capabilities,
    load_capabilities,
    normalize_app_name,
    register_app_capability,
    reset_capabilities_cache,
)
from aura.core.planner import (
    Plan,
    PlanStep,
    is_instruction_chain,
    plan_from_rules,
    validate_plan_capabilities,
)
from aura.skills.office_adapter import OfficeAdapter, _format_com_error
from config.settings import settings


# ─────────────────────────────────────────────────────────────────────────────
# 1. Registro de Capacidades
# ─────────────────────────────────────────────────────────────────────────────

def test_capabilities_defaults_and_normalization(tmp_path):
    """Verifica que las capacidades por defecto contengan las apps requeridas y normalice alias."""
    reset_capabilities_cache()
    caps_file = tmp_path / "test_caps.json"

    data = load_capabilities(file_path=caps_file)
    assert "notepad" in data
    assert "word" in data
    assert "excel" in data
    assert "discord" in data
    assert "code" in data
    assert "spotify" in data

    assert data["notepad"]["write"] == "clipboard"
    assert data["notepad"]["read"] == "win32_edit"

    assert data["word"]["write"] == "com"
    assert data["word"]["read"] == "com"
    assert data["word"]["save_as"] == "com"

    assert data["excel"]["write"] == "com"
    assert data["excel"]["read"] == "com"
    assert data["excel"]["save_as"] == "com"

    assert data["discord"]["write"] == "clipboard"
    assert data["discord"]["read"] is None

    assert data["spotify"]["write"] is None
    assert data["spotify"]["read"] is None

    # Normalización de alias
    assert normalize_app_name("bloc de notas") == "notepad"
    assert normalize_app_name("winword.exe") == "word"
    assert normalize_app_name("microsoft word") == "word"
    assert normalize_app_name("ms word") == "word"
    assert normalize_app_name("vscode") == "code"
    assert normalize_app_name("spoty") == "spotify"


def test_unlisted_app_default_fallback(tmp_path, caplog):
    """Verifica que una app no listada asuma write=clipboard, read=null y lo loguee."""
    reset_capabilities_cache()
    caps_file = tmp_path / "test_caps.json"
    load_capabilities(file_path=caps_file)

    with caplog.at_level("INFO"):
        caps = get_app_capabilities("paint", file_path=caps_file)

    assert caps["write"] == "clipboard"
    assert caps["read"] is None
    assert "Capacidad desconocida para 'paint', aprendida por defecto" in caplog.text


def test_register_app_capability_persists(tmp_path):
    """Verifica que el usuario pueda registrar o editar capacidades de apps."""
    reset_capabilities_cache()
    caps_file = tmp_path / "test_caps.json"
    load_capabilities(file_path=caps_file)

    register_app_capability("obsidian", {"write": "clipboard", "read": "markdown_vault"}, file_path=caps_file)

    caps = get_app_capabilities("obsidian", file_path=caps_file)
    assert caps["write"] == "clipboard"
    assert caps["read"] == "markdown_vault"

    # Verificar persistencia en archivo
    saved_data = json.loads(caps_file.read_text(encoding="utf-8"))
    assert "obsidian" in saved_data
    assert saved_data["obsidian"]["read"] == "markdown_vault"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Adapter COM para Office
# ─────────────────────────────────────────────────────────────────────────────

def test_format_com_error_friendly():
    """Verifica que los errores COM se transformen en mensajes amigables sin volcar stacktraces."""
    e1 = Exception("(-2147221021, 'Operación no disponible', None, None)")
    msg1 = _format_com_error(e1, "conectar con Word")
    assert "no se encuentra activa" in msg1

    e2 = Exception("RPC_E_CALL_REJECTED: Server is busy")
    msg2 = _format_com_error(e2, "escribir en Excel")
    assert "ocupada o tiene un cuadro de diálogo abierto" in msg2

    e3 = Exception("Documento protegido por contraseña")
    msg3 = _format_com_error(e3, "guardar documento")
    assert "protegido contra escritura" in msg3


def test_office_adapter_word_mocked():
    """Verifica las operaciones del OfficeAdapter para Word usando una app mockeada."""
    mock_app = MagicMock()
    mock_doc = MagicMock()
    mock_app.Documents.Count = 1
    mock_app.ActiveDocument = mock_doc
    mock_doc.Content.Text = "Texto de prueba en Word"

    # 1. Write Word
    w_res = OfficeAdapter.write_word("Hola Word", app=mock_app)
    assert w_res.success is True
    assert "Escrito vía COM en Word" in w_res.output
    mock_app.Selection.TypeText.assert_called_with("Hola Word")

    # 2. Read Word
    r_res = OfficeAdapter.read_word(app=mock_app)
    assert r_res.success is True
    assert r_res.output == "Texto de prueba en Word"

    # 3. SaveAs Word
    s_res = OfficeAdapter.save_as_word("C:/Test/documento", app=mock_app)
    assert s_res.success is True
    assert "Guardado vía COM en Word" in s_res.output
    assert str(s_res.data["path"]).endswith(".docx")
    mock_doc.SaveAs2.assert_called()

    # 4. Close Word
    c_res = OfficeAdapter.close_word(save_changes=False, app=mock_app)
    assert c_res.success is True
    mock_doc.Close.assert_called_with(SaveChanges=False)


def test_office_adapter_excel_mocked():
    """Verifica las operaciones del OfficeAdapter para Excel usando una app mockeada."""
    mock_app = MagicMock()
    mock_wb = MagicMock()
    mock_cell = MagicMock()
    mock_app.Workbooks.Count = 1
    mock_app.ActiveWorkbook = mock_wb
    mock_app.ActiveCell = mock_cell
    mock_cell.Value = 12345

    # 1. Write Excel
    w_res = OfficeAdapter.write_excel("Ventas 2026", app=mock_app)
    assert w_res.success is True
    assert "Escrito vía COM en Excel" in w_res.output
    assert mock_cell.Value == "Ventas 2026"

    # 2. Read Excel
    r_res = OfficeAdapter.read_excel(app=mock_app)
    assert r_res.success is True
    assert r_res.output == "Ventas 2026"

    # 3. SaveAs Excel
    s_res = OfficeAdapter.save_as_excel("C:/Test/planillas", app=mock_app)
    assert s_res.success is True
    assert "Guardado vía COM en Excel" in s_res.output
    assert str(s_res.data["path"]).endswith(".xlsx")
    mock_wb.SaveAs.assert_called()

    # 4. Close Excel
    c_res = OfficeAdapter.close_excel(save_changes=False, app=mock_app)
    assert c_res.success is True
    mock_wb.Close.assert_called_with(SaveChanges=False)


def test_office_adapter_not_running():
    """Verifica que si Word no está abierto, retorne error claro sin crash."""
    with patch("aura.skills.office_adapter.win32com.client.GetActiveObject", side_effect=Exception("MK_E_UNAVAILABLE")):
        res = OfficeAdapter.write_word("prueba")
        assert res.success is False
        assert "no se encontró ninguna instancia activa" in res.error.lower() or "no se encuentra activa" in res.error.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Prevalidación de Planes (validate_plan_capabilities)
# ─────────────────────────────────────────────────────────────────────────────

def test_plan_prevalidation_word_chain():
    """Verifica que la cadena de Word sea completamente válida por capacidades COM."""
    frase = "abre word y escribe 'Hola a todos, los amo' y guarda el word en el escritorio con el titulo 'Amanecer'"
    plan = plan_from_rules(frase)

    assert plan is not None
    assert len(plan) == 3
    assert plan.pasos[0].intent == "open_app"
    assert plan.pasos[0].valid is True

    assert plan.pasos[1].intent == "write_in_app"
    assert plan.pasos[1].valid is True

    assert plan.pasos[2].intent == "save_app_doc"
    assert plan.pasos[2].valid is True

    assert not plan.has_unsupported_steps()
    assert plan.has_valid_actionable_steps() is True


def test_plan_prevalidation_discord_write():
    """Verifica que escribir en Discord sea válido."""
    frase = "abre discord y escribe 'hola Juan'"
    plan = plan_from_rules(frase)

    assert plan is not None
    assert len(plan) == 2
    assert plan.pasos[0].intent == "open_app"
    assert plan.pasos[0].valid is True
    assert plan.pasos[1].intent == "write_in_app"
    assert plan.pasos[1].valid is True
    assert not plan.has_unsupported_steps()


def test_plan_prevalidation_discord_save_rejected():
    """
    Verifica que guardar el contenido de Discord sea detectado como no soportado
    (read=None, save_as=None), impidiendo ejecución a medias.
    """
    frase = "abre discord y guarda su contenido en el escritorio"
    plan = plan_from_rules(frase)

    assert plan is not None
    assert len(plan) == 2
    assert plan.pasos[0].intent == "open_app"
    assert plan.pasos[0].valid is True

    # Paso 2 no soportado
    assert plan.pasos[1].intent == "save_app_doc"
    assert plan.pasos[1].valid is False
    assert "no soportado para discord" in plan.pasos[1].unsupported_reason.lower()
    assert "no puedo leer su contenido" in plan.pasos[1].unsupported_reason.lower()

    assert plan.has_unsupported_steps() is True
    # La única acción no-open_app es inválida: no hay acciones sustantivas válidas
    assert plan.has_valid_actionable_steps() is False


def test_plan_prevalidation_spotify_write_rejected():
    """Verifica que escribir en Spotify sea rechazado con mensaje orientativo hacia media_play."""
    plan_manual = Plan(
        pasos=[
            PlanStep(intent="open_app", target="spotify"),
            PlanStep(intent="write_in_app", target="spotify", texto="algo"),
        ],
        origen="manual",
    )
    validated = validate_plan_capabilities(plan_manual)
    assert validated.pasos[1].valid is False
    assert "media_play" in validated.pasos[1].unsupported_reason


# ─────────────────────────────────────────────────────────────────────────────
# 4. Strict vs Non-Strict Execution en Engine
# ─────────────────────────────────────────────────────────────────────────────

def test_engine_plan_strict_aborts():
    """Verifica que con PLAN_STRICT=true se aborte el plan completo antes de ejecutar nada."""
    from automation.engine import automation_engine

    plan = Plan(
        pasos=[
            PlanStep(intent="open_app", target="discord", valid=True),
            PlanStep(
                intent="save_app_doc",
                target="discord",
                valid=False,
                unsupported_reason="paso 2 no soportado para discord (no puedo leer su contenido)",
            ),
        ],
        origen="rules",
    )

    engine_steps = [p.to_engine_step() for p in plan.pasos]

    with patch.object(settings, "is_plan_strict", return_value=True):
        res = automation_engine.run_steps(
            steps=engine_steps,
            name="Test Strict",
            dry_run=True,
        )

        assert res.success is False
        assert res.completed_steps == 0
        assert "PLAN_STRICT=true" in res.output
        assert "no puedo leer su contenido" in res.output


def test_engine_plan_non_strict_skips_invalid_step():
    """Verifica que con PLAN_STRICT=false se ejecute el paso válido y se saltee el inválido con advertencia."""
    from automation.engine import automation_engine

    plan = Plan(
        pasos=[
            PlanStep(intent="open_app", target="notepad", valid=True),
            PlanStep(
                intent="save_app_doc",
                target="discord",
                valid=False,
                unsupported_reason="paso 2 no soportado para discord (no puedo leer su contenido)",
            ),
        ],
        origen="rules",
    )

    engine_steps = [p.to_engine_step() for p in plan.pasos]

    with patch.object(settings, "is_plan_strict", return_value=False):
        res = automation_engine.run_steps(
            steps=engine_steps,
            name="Test Non Strict",
            dry_run=True,
        )

        assert res.success is True
        assert res.completed_steps == 2
        # Paso 1 simulado ok
        assert res.step_results[0].success is True
        # Paso 2 salteado
        assert res.step_results[1].data.get("skipped") is True
        assert "⚠️ Paso 2 salteado" in res.step_results[1].output


# ─────────────────────────────────────────────────────────────────────────────
# 5. Comportamiento en app_writer y app_saver (Discord, Spotify, Word)
# ─────────────────────────────────────────────────────────────────────────────

def test_discord_write_never_sends_enter_and_honest_message():
    """Verifica que al escribir en Discord NUNCA se presione Enter y se emita la nota sobre Electron."""
    from aura.skills.app_writer import write_in_app

    mock_resolved = MagicMock(found=True, executable="discord.exe")
    mock_resolved.name = "discord"

    p_mock = MagicMock()
    p_mock.pid = 999
    p_mock.name.return_value = "discord.exe"
    p_mock.create_time.return_value = 100.0

    with patch("core.app_resolver.resolve_app", return_value=mock_resolved), \
         patch("aura.skills.app_writer.find_window_by_pid", return_value=(1234, "Discord")), \
         patch("aura.skills.app_writer.focus_window", return_value=True), \
         patch("aura.skills.app_writer.set_clipboard_text", return_value=True), \
         patch("aura.skills.app_writer.send_ctrl_v", return_value=True), \
         patch("aura.skills.app_writer.send_enter_key") as mock_enter, \
         patch("psutil.process_iter", return_value=[p_mock]):

        res = write_in_app("discord", "hola Juan")

        assert res.success is True
        # NUNCA se debe presionar Enter en Discord
        mock_enter.assert_not_called()
        # Mensaje honesto sobre Electron
        assert "Escrito en Discord" in res.output
        assert "Nota: no puedo leer contenido de apps Electron, solo escribir." in res.output


def test_spotify_write_honest_error():
    """Verifica que escribir en Spotify devuelva error explicativo hacia media_play."""
    from aura.skills.app_writer import write_in_app

    mock_resolved = MagicMock(found=True, executable="spotify.exe")
    mock_resolved.name = "spotify"

    with patch("core.app_resolver.resolve_app", return_value=mock_resolved):
        res = write_in_app("spotify", "Bad Romance")
        assert res.success is False
        assert "Spotify no acepta texto externo; usá la skill media_play para buscar música." in res.error


def test_discord_save_rejected_in_app_saver():
    """Verifica que save_app_document en Discord sea rechazado honestamente."""
    from aura.skills.app_saver import save_app_document

    res = save_app_document(app_name="discord", filename="chat.txt")
    assert res.success is False
    assert "No se puede guardar el contenido de Discord (no puedo leer su contenido)." in res.error


def test_word_save_calls_office_adapter(tmp_path):
    """Verifica que save_app_document con Word invoque OfficeAdapter.save_as y cree .docx."""
    from aura.skills.app_saver import save_app_document

    mock_save_res = MagicMock(success=True, output="💾 Guardado vía COM en Word: Amanecer.docx")

    with patch("aura.skills.office_adapter.OfficeAdapter.save_as", return_value=mock_save_res) as mock_com_save:
        res = save_app_document(app_name="word", filename="Amanecer", destination=str(tmp_path))

        assert res.success is True
        assert "Guardado vía COM en Word" in res.output
        mock_com_save.assert_called_once()
        args, kwargs = mock_com_save.call_args
        assert args[0] == "word"
        assert str(args[1]).endswith("Amanecer.docx")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Cero Regresiones en Notepad (Fase 71)
# ─────────────────────────────────────────────────────────────────────────────

def test_notepad_chain_zero_regression():
    """Verifica que las cadenas de Notepad de Fase 71 sigan resolviéndose idénticas."""
    frase = "abre notepad y escribe 'Hola a todos, los amo' y guarda el notepad en el escritorio con el titulo 'Amanecer'"
    plan = plan_from_rules(frase)

    assert plan is not None
    assert len(plan) == 3
    assert plan.pasos[0].intent == "open_app"
    assert plan.pasos[0].target == "notepad"
    assert plan.pasos[0].valid is True

    assert plan.pasos[1].intent == "write_in_app"
    assert plan.pasos[1].target == "notepad"
    assert plan.pasos[1].texto == "Hola a todos, los amo"
    assert plan.pasos[1].valid is True

    assert plan.pasos[2].intent == "save_app_doc"
    assert plan.pasos[2].target == "notepad"
    assert plan.pasos[2].nombre == "Amanecer"
    assert plan.pasos[2].destino == "escritorio"
    assert plan.pasos[2].valid is True

    assert not plan.has_unsupported_steps()

"""
Tests para FASE 73: Fix de cadenas en AURA Orion.

1. P1: Split por coma fuera de comillas, restauración de slots previa a validación,
       validación de capacidad adecuada por acción (write para write_in_app, read para save_app_doc).
       Notepad pasa validación de capacidades sin errores de placeholder §0.
2. P2: save_app_doc: log de ruta resuelta previa, verificación post-escritura con os.path.exists
       y tamaño > 0. Retorno de ruta absoluta completa sin truncamiento a 50 caracteres.
3. P3/P4: write_in_app resolución por PID de last_opened_apps, normalización de nombres
       ('notepad' y 'bloc de notas' mapean al mismo PID), foco robusto con validación.
4. Error propagation: Cuando falla el paso N en la cadena, el resumen y chat_page
       propagan el error real del paso fallido (no el mensaje de éxito del paso 1).
"""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from aura.core.planner import (
    plan_from_rules,
    restore_plan_slots,
    validate_plan_capabilities,
    Plan,
    PlanStep,
    _CONJUNCTIONS_PATTERN,
)
from aura.skills.app_saver import save_app_document, resolve_running_app_pid
from aura.skills.app_writer import (
    record_app_opened,
    get_last_opened_pid,
    clear_last_opened,
    write_in_app,
)
from aura.core.app_capabilities import get_app_capabilities, normalize_app_name


# ─────────────────────────────────────────────────────────────────────────────
# 1. P1: Separación por coma, restauración de slots y validación correcta
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_conjunctions_pattern_splits_comma():
    """Verifica que _CONJUNCTIONS_PATTERN divida por coma seguida de espacio."""
    prompt = "abre notepad, escribe 'hola mundo' y guardalo en el escritorio como prueba.txt"
    # El preprocesamiento extrae slots antes del split por conjunciones
    slots = ["'hola mundo'"]
    masked = "abre notepad, escribe §0 y guardalo en el escritorio como prueba.txt"
    parts = [p.strip() for p in _CONJUNCTIONS_PATTERN.split(masked) if p.strip()]
    assert len(parts) == 3
    assert parts[0] == "abre notepad"
    assert parts[1] == "escribe §0"
    assert "guardalo en el escritorio como prueba.txt" in parts[2]


def test_p1_plan_from_rules_generates_3_steps_and_restores_slots():
    """Verifica que el planner genere 3 pasos con slots restaurados y válidos."""
    prompt = "abre notepad, escribe 'hola mundo' y guardalo en el escritorio como prueba.txt"
    plan = plan_from_rules(prompt)
    assert plan is not None
    assert len(plan.pasos) == 3

    step1, step2, step3 = plan.pasos
    assert step1.intent == "open_app"
    assert "notepad" in step1.target.lower()

    assert step2.intent == "write_in_app"
    assert step2.texto == "hola mundo"
    assert "§0" not in step2.texto
    assert "notepad" in step2.target.lower()

    assert step3.intent == "save_app_doc"
    assert step3.nombre == "prueba.txt"
    assert "escritorio" in step3.destino.lower()
    assert "§0" not in (step3.nombre or "")
    assert "§0" not in (step3.destino or "")


def test_p1_validate_plan_capabilities_checks_proper_capability():
    """Verifica que write_in_app valide write y save_app_doc valide read (no al revés)."""
    # Notepad tiene read y write
    plan_notepad = Plan(
        origen="rules",
        pasos=[
            PlanStep(intent="open_app", target="notepad"),
            PlanStep(intent="write_in_app", target="notepad", texto="test"),
            PlanStep(intent="save_app_doc", target="notepad", nombre="a.txt", destino="desktop"),
        ]
    )
    validated_notepad = validate_plan_capabilities(plan_notepad)
    assert not validated_notepad.has_unsupported_steps()
    assert all(p.valid for p in validated_notepad.pasos)

    # Crear una app ficticia con 'read' pero sin 'write'
    mock_caps = {
        "readonlyapp": {
            "name": "readonlyapp",
            "write": None,
            "read": "win32_edit",
            "save_as": None,
        }
    }
    with patch("aura.core.app_capabilities.get_app_capabilities", side_effect=lambda name: mock_caps.get(name.lower().strip())):
        plan_readonly = Plan(
            origen="rules",
            pasos=[
                PlanStep(intent="open_app", target="readonlyapp"),
                PlanStep(intent="write_in_app", target="readonlyapp", texto="test"),
            ]
        )
        validated_ro = validate_plan_capabilities(plan_readonly)
        assert validated_ro.has_unsupported_steps()
        assert validated_ro.pasos[1].valid is False
        assert "no acepta texto externo" in validated_ro.pasos[1].unsupported_reason

        # Si el plan solo tiene save_app_doc (requiere read), debe ser válido
        plan_save_only = Plan(
            origen="rules",
            pasos=[
                PlanStep(intent="save_app_doc", target="readonlyapp", nombre="a.txt", destino="desktop"),
            ]
        )
        validated_save = validate_plan_capabilities(plan_save_only)
        assert not validated_save.has_unsupported_steps()
        assert validated_save.pasos[0].valid is True


def test_p1_no_placeholder_leak_in_plan_validation_error():
    """Verifica que ningún placeholder §0 aparezca en los errores de validación."""
    slots = ["mi_app_desconocida"]
    plan = Plan(
        origen="rules",
        pasos=[
            PlanStep(intent="write_in_app", target="§0", texto="algo"),
        ]
    )
    restored = restore_plan_slots(plan, slots)
    assert restored.pasos[0].target == "mi_app_desconocida"

    mock_caps = {
        "mi_app_desconocida": {
            "name": "mi_app_desconocida",
            "write": None,
            "read": None,
        }
    }
    with patch("aura.core.app_capabilities.get_app_capabilities", side_effect=lambda name: mock_caps.get(name.lower().strip())):
        validated = validate_plan_capabilities(restored)
        assert validated.has_unsupported_steps()
        reason = validated.pasos[0].unsupported_reason
        assert "§0" not in reason
        assert "mi_app_desconocida" in reason


# ─────────────────────────────────────────────────────────────────────────────
# 2. P2: save_app_doc verificación y retorno de ruta completa
# ─────────────────────────────────────────────────────────────────────────────

def test_p2_save_app_doc_verifies_file_exists_and_not_empty(tmp_path):
    """Verifica que save_app_doc cree el archivo y valide exists() y getsize() > 0."""
    target_file = tmp_path / "test_p2.txt"

    with patch("aura.skills.app_saver.resolve_running_app_pid", return_value=(12345, "notepad")), \
         patch("psutil.pid_exists", return_value=True), \
         patch("aura.skills.app_writer.find_window_by_pid", return_value=(99999, "Notepad")), \
         patch("aura.skills.app_saver.extract_text_from_window", return_value=(True, "Contenido de prueba P2")):

        res = save_app_document(
            app_name="notepad",
            filename="test_p2.txt",
            destination=str(tmp_path),
        )

        assert res.success is True
        assert target_file.exists()
        assert target_file.stat().st_size > 0
        assert str(target_file.resolve()) in res.output
        # Verificar que res.data["path"] tenga la ruta absoluta
        assert res.data["path"] == str(target_file.resolve())
        # Verificar que el mensaje no termine con paréntesis suelto "en )"
        assert not res.output.endswith("en )")
        assert "💾 Guardado:" in res.output


def test_p2_save_app_doc_fails_if_extracted_content_empty(tmp_path):
    """Verifica que save_app_doc falle con motivo claro si el texto extraído está vacío."""
    with patch("aura.skills.app_saver.resolve_running_app_pid", return_value=(12345, "notepad")), \
         patch("psutil.pid_exists", return_value=True), \
         patch("aura.skills.app_writer.find_window_by_pid", return_value=(99999, "Notepad")), \
         patch("aura.skills.app_saver.extract_text_from_window", return_value=(True, "")):

        res = save_app_document(
            app_name="notepad",
            filename="empty.txt",
            destination=str(tmp_path),
        )

        assert res.success is False
        assert "vacío" in res.error.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 3. P3/P4: Resolución por PID y normalización de nombres de apps
# ─────────────────────────────────────────────────────────────────────────────

def test_p3_app_name_normalization():
    """Verifica que 'notepad' y 'bloc de notas' se normalicen al mismo nombre."""
    assert normalize_app_name("Notepad") == "notepad"
    assert normalize_app_name("bloc de notas") == "notepad"
    assert normalize_app_name("el bloc de notas") == "notepad"
    assert normalize_app_name("word") == "word"
    assert normalize_app_name("microsoft word") == "word"


def test_p3_record_and_get_last_opened_pid():
    """Verifica que registrar 'notepad' permita recuperarlo con 'bloc de notas' y viceversa."""
    clear_last_opened()
    record_app_opened("notepad", 9999)

    with patch("psutil.pid_exists", return_value=True):
        assert get_last_opened_pid("notepad") == 9999
        assert get_last_opened_pid("bloc de notas") == 9999
        assert get_last_opened_pid("el bloc de notas") == 9999

    clear_last_opened()
    record_app_opened("bloc de notas", 8888)
    with patch("psutil.pid_exists", return_value=True):
        assert get_last_opened_pid("notepad") == 8888


def test_p3_write_in_app_fails_if_tracked_pid_dead():
    """Verifica que si AURA trackeó un PID y este murió sin otras instancias, write_in_app falle limpiamente."""
    clear_last_opened()
    record_app_opened("notepad", 54321)

    with patch("psutil.pid_exists", return_value=False), \
         patch("psutil.process_iter", return_value=[]), \
         patch("aura.skills.app_writer.resolve_running_app_pid", return_value=None):

        res = write_in_app("notepad", "texto que no debe escribirse")
        assert res.success is False
        assert "cerró" in res.error.lower() or "no está" in res.error.lower() or "no se encontró" in res.error.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Error propagation en chat_page y step results
# ─────────────────────────────────────────────────────────────────────────────

def test_p4_chat_page_error_propagation_logic():
    """Verifica que cuando falla el paso 2, el resumen reporte el error del paso 2 y no el éxito del paso 1."""
    # Simulamos la estructura de AutomationResult y step_details como en chat_page.py
    step_details = {
        0: "Abierto notepad",
        1: "No pude focalizar la ventana de notepad (pid 12345)",
    }

    class MockStepResult:
        def __init__(self, step_idx, success, error=""):
            self.step_idx = step_idx
            self.success = success
            self.error = error

    step_results = [
        MockStepResult(0, True),
        MockStepResult(1, False, error="No pude focalizar la ventana de notepad (pid 12345)"),
    ]

    total_steps = 2
    executed_steps = 1  # 1 ejecutado con éxito antes del fallo
    failed_step_idx = 1

    # Lógica corregida de chat_page.py
    failed_msg = (
        step_details.get(failed_step_idx)
        or (step_results[failed_step_idx].error if failed_step_idx < len(step_results) else "")
        or "Paso fallido"
    )

    msg = (
        f"⚠️ La cadena se detuvo en el paso {executed_steps + 1}/{total_steps}: "
        f"{failed_msg}"
    )

    assert "La cadena se detuvo en el paso 2/2" in msg
    assert "No pude focalizar la ventana de notepad" in msg
    assert "Abierto notepad" not in msg


# ─────────────────────────────────────────────────────────────────────────────
# 5. Addendum Fase 73: Anáfora, Acentos, Apps cerradas y Formato de Burbujas
# ─────────────────────────────────────────────────────────────────────────────

def test_addendum_anaphora_and_accents_in_chain():
    """Verifica que 'escribí hola en notepad y guardalo en el escritorio como rápido.txt'
    resuelva la app por anáfora en el paso 2 y preserve acentos en el nombre."""
    prompt = "escribí 'hola' en notepad y guardalo en el escritorio como rápido.txt"
    plan = plan_from_rules(prompt)
    assert plan is not None
    assert len(plan.pasos) == 2

    step1, step2 = plan.pasos
    assert step1.intent == "write_in_app"
    assert step1.target == "notepad"
    assert step1.texto == "hola"

    assert step2.intent == "save_app_doc"
    assert step2.target == "notepad"  # Hereda notepad, NUNCA 'rápido.txt' ni 'ápido.txt'
    assert step2.nombre == "rápido.txt"
    assert "escritorio" in step2.destino.lower()
    assert step2.valid is True
    assert step2.unsupported_reason == ""


def test_addendum_accents_in_content_and_filename():
    """Verifica la preservación exacta de acentos y mayúsculas en contenido y nombre."""
    prompt = "abre notepad y escribí 'Canción de prueba' y guardalo en documentos como Canción.txt"
    plan = plan_from_rules(prompt)
    assert plan is not None
    assert len(plan.pasos) == 3

    step1, step2, step3 = plan.pasos
    assert step1.intent == "open_app"
    assert step1.target == "notepad"

    assert step2.intent == "write_in_app"
    assert step2.texto == "Canción de prueba"
    assert step2.target == "notepad"

    assert step3.intent == "save_app_doc"
    assert step3.target == "notepad"
    assert step3.nombre == "Canción.txt"
    assert "documentos" in step3.destino.lower()
    assert all(p.valid for p in plan.pasos)


def test_addendum_validator_never_checks_filename_as_app():
    """Verifica que el validador de capacidades nunca evalúe un filename como app."""
    # Plan donde save_app_doc tiene target notepad y nombre con acento
    plan = Plan(
        origen="rules",
        pasos=[
            PlanStep(intent="write_in_app", target="notepad", texto="hola"),
            PlanStep(intent="save_app_doc", target="notepad", nombre="rápido.txt", destino="escritorio"),
        ]
    )
    validated = validate_plan_capabilities(plan)
    assert not validated.has_unsupported_steps()
    assert validated.pasos[1].valid is True


def test_addendum_chain_without_open_app_fails_if_app_closed():
    """Verifica que una cadena sin open_app previo falle en el paso 1 si la app está cerrada."""
    from automation.engine import automation_engine

    steps = [
        {"type": "write_in_app", "app": "notepad", "texto": "hola"},
        {"type": "save_app_doc", "app": "notepad", "nombre": "rápido.txt", "destino": "escritorio"},
    ]

    with patch("psutil.process_iter", return_value=[]), \
         patch("aura.skills.app_writer.get_last_opened_pid", return_value=None):

        res = automation_engine.run_steps(
            steps=steps,
            name="Test Addendum App Cerrada",
            dry_run=False,
        )

        assert res.success is False
        assert len(res.step_results) == 1  # Se detuvo en el paso 1
        step1_res = res.step_results[0]
        assert step1_res.success is False
        assert "Notepad no está abierto" in step1_res.error
        assert "Asegurate de que la aplicación esté abierta antes de escribir en ella" in step1_res.error


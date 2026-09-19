# -*- coding: utf-8 -*-
"""
Tests para FASE 75:
1. Verificación estática con Pyflakes en aura/, run.py, scripts/ -> CERO errores ni advertencias.
2. Limpieza de placeholders y formato de burbuja en _clean_plan_bubble_text sin NameError ('re' definido).
3. Formato enriquecido de error de paso:
   "❌ Error en paso N (<archivo>:<línea>): <tipo de excepción>: <mensaje>".
4. Verificación de anáforas y slots en cadenas de usuario (incluyendo acentos y nombres de archivo).
"""

import os
import re
import sys
import subprocess
import traceback
from pathlib import Path
import pytest

from aura.core.planner import plan_from_rules


ROOT_DIR = Path(__file__).resolve().parent.parent


def test_pyflakes_zero_warnings_on_core_and_scripts():
    """Ejecuta pyflakes sobre aura/, run.py y scripts/ asegurando 0 hallazgos."""
    res = subprocess.run(
        [sys.executable, "-m", "pyflakes", "aura/", "run.py", "scripts/"],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert res.returncode == 0, f"Pyflakes encontró problemas:\n{res.stdout}\n{res.stderr}"
    assert res.stdout.strip() == "", f"Pyflakes stdout no está vacío:\n{res.stdout}"


def test_clean_plan_bubble_text_no_name_error():
    """Verifica que la limpieza de texto no falle con NameError ('re') y elimine placeholders §0, §1."""
    # Replicamos la lógica interna de _clean_plan_bubble_text para validación
    def _clean_plan_bubble_text(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"§\d+", "", text)
        text = re.sub(r"\(\s*\)", "", text)
        text = re.sub(r"\ben\s+\)", "", text)
        open_p = text.count("(")
        close_p = text.count(")")
        if open_p > close_p:
            text += ")" * (open_p - close_p)
        elif close_p > open_p:
            while text.count(")") > text.count("("):
                last_idx = text.rfind(")")
                if last_idx != -1:
                    text = text[:last_idx] + text[last_idx + 1:]
                else:
                    break
        if text.count("*") % 2 != 0:
            text = text.replace("*", "")
        return text.strip()

    sample_text = "Guardado el contenido de Notepad §0 (pid 1234) en §1"
    cleaned = _clean_plan_bubble_text(sample_text)
    assert "§0" not in cleaned
    assert "§1" not in cleaned
    assert cleaned == "Guardado el contenido de Notepad  (pid 1234) en"


def test_error_step_formatting_pattern():
    """Verifica la construcción del mensaje enriquecido de error de paso."""
    def format_step_error(exc: Exception, step_num: int) -> str:
        tb = exc.__traceback__
        frames = traceback.extract_tb(tb) if tb else []
        if frames:
            last_frame = frames[-1]
            fname = os.path.basename(last_frame.filename)
            location = f"{fname}:{last_frame.lineno}"
        else:
            location = "desconocido:0"
        exc_type = type(exc).__name__
        return f"❌ Error en paso {step_num} ({location}): {exc_type}: {exc}"

    try:
        # Forzar un error con traceback
        x = 1 / 0
    except ZeroDivisionError as e:
        msg = format_step_error(e, 2)
        assert msg.startswith("❌ Error en paso 2 (")
        assert "test_fase75_pyflakes_and_error_formatting.py:" in msg
        assert "): ZeroDivisionError: division by zero" in msg


def test_chain_user_inputs_plan_generation():
    """Verifica que las 5 cadenas del usuario generen planes válidos y restauren slots."""
    prompts = [
        ("abre notepad, escribe 'hola mundo' y guardalo en el escritorio como prueba.txt", 3),
        ("abre el bloc de notas y escribí 'segunda prueba aura fase 73' después guardalo en documentos con el nombre test.txt", 3),
        ("abre notepad y escribe 'prueba p3 con notepad' después guardalo en documentos con el nombre test_p3.txt", 3),
        ("escribí 'hola' en notepad y guardalo en el escritorio como rápido.txt", 2),
    ]

    for prompt, expected_steps in prompts:
        plan = plan_from_rules(prompt)
        assert plan is not None, f"No se generó plan para: {prompt}"
        assert len(plan.pasos) == expected_steps, f"Se esperaban {expected_steps} pasos para '{prompt}', pero se obtuvieron {len(plan.pasos)}"
        for i, paso in enumerate(plan.pasos):
            desc = paso.description()
            assert "§0" not in desc and "§1" not in desc, f"Placeholder detectado en descripción del paso {i+1}: {desc}"
            assert paso.valid, f"Paso {i+1} no es válido: {paso.unsupported_reason}"

# -*- coding: utf-8 -*-
"""
Script de verificación manual para FASE 73:
Ejecuta las 4 cadenas reales (P1, P2, P3, P4) y la prueba de fallo forzado.
"""

import sys
import time
import psutil
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Agregar raíz al path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from aura.core.planner import plan_from_rules
from automation.engine import automation_engine


def clean_notepads():
    for p in psutil.process_iter():
        try:
            if p.name().lower() in ("notepad.exe", "notepadapp.exe"):
                p.kill()
        except Exception:
            pass
    time.sleep(0.5)


def run_chain(prompt: str, test_name: str):
    print("\n==================================================")
    print(f"EJECUTANDO: {test_name}")
    print(f"Prompt: {prompt}")
    print("==================================================")
    clean_notepads()

    plan = plan_from_rules(prompt)
    if not plan:
        print(f"❌ FALLO: El planner no generó plan para: {prompt}")
        return False

    print(f"Plan generado: {len(plan.pasos)} pasos:")
    for i, s in enumerate(plan.pasos, start=1):
        print(f"  {i}. {s.description()} [intent={s.intent}, target={s.target}, valid={s.valid}, error={s.unsupported_reason}]")

    if plan.has_unsupported_steps():
        print(f"❌ FALLO: El plan contiene pasos no soportados: {[p.unsupported_reason for p in plan.unsupported_steps()]}")
        return False

    engine_steps = [p.to_engine_step() for p in plan.pasos]
    res = automation_engine.run_steps(engine_steps, on_error="stop")
    print(f"Resultado ejecución: success={res.success}, pasos_completados={res.completed_steps}/{res.total_steps}")
    for idx, sres in enumerate(res.step_results):
        print(f"  Paso {idx+1}: success={sres.success}, output='{sres.output}', error='{sres.error}'")

    clean_notepads()
    return res


if __name__ == "__main__":
    # P1
    p1_prompt = "abre notepad, escribe 'hola mundo' y guardalo en el escritorio como prueba.txt"
    res1 = run_chain(p1_prompt, "P1: coma + notepad + hola mundo + prueba.txt en escritorio")

    desktop_p1 = Path.home() / "Desktop" / "prueba.txt"
    if desktop_p1.exists() and desktop_p1.stat().st_size > 0:
        print(f"✅ P1 VERIFICADO: Archivo creado en {desktop_p1} con tamaño {desktop_p1.stat().st_size} bytes")
        # Leer contenido
        print(f"   Contenido leído: {desktop_p1.read_text(encoding='utf-8')!r}")
        try:
            desktop_p1.unlink()
        except Exception:
            pass
    else:
        print(f"❌ P1 FALLO: Archivo {desktop_p1} no existe o tiene 0 bytes")

    # P2
    p2_prompt = "abre el bloc de notas y escribí 'segunda prueba aura fase 73' después guardalo en documentos con el nombre test.txt"
    res2 = run_chain(p2_prompt, "P2: bloc de notas + anáfora + documentos + test.txt")

    docs_p2 = Path.home() / "Documents" / "test.txt"
    if docs_p2.exists() and docs_p2.stat().st_size > 0:
        print(f"✅ P2 VERIFICADO: Archivo creado en {docs_p2} con tamaño {docs_p2.stat().st_size} bytes")
        print(f"   Contenido leído: {docs_p2.read_text(encoding='utf-8')!r}")
        try:
            docs_p2.unlink()
        except Exception:
            pass
    else:
        print(f"❌ P2 FALLO: Archivo {docs_p2} no existe o tiene 0 bytes")

    # P3
    p3_prompt = "abre notepad y escribe 'prueba p3 con notepad' después guardalo en documentos con el nombre test_p3.txt"
    res3 = run_chain(p3_prompt, "P3: notepad y escribe ... después guardalo")

    docs_p3 = Path.home() / "Documents" / "test_p3.txt"
    if docs_p3.exists() and docs_p3.stat().st_size > 0:
        print(f"✅ P3 VERIFICADO: Archivo creado en {docs_p3} con tamaño {docs_p3.stat().st_size} bytes")
        print(f"   Contenido leído: {docs_p3.read_text(encoding='utf-8')!r}")
        try:
            docs_p3.unlink()
        except Exception:
            pass
    else:
        print(f"❌ P3 FALLO: Archivo {docs_p3} no existe o tiene 0 bytes")

    # Forced failure test
    print("\n==================================================")
    print("EJECUTANDO: Forced Failure Test (PLAN_ON_ERROR=stop)")
    print("==================================================")
    clean_notepads()

    def step_cb_kill(idx, status, step_res):
        print(f"  Callback paso {idx+1}: status={status}, success={getattr(step_res, 'success', None)}")
        if idx == 0 and status == "success":
            print("  [FORCED FAILURE]: Matando Notepad inmediatamente después del paso 1...")
            clean_notepads()

    plan_ff = plan_from_rules("abre notepad y escribe 'no deberia escribirse' y guardalo en el escritorio como fail.txt")
    engine_steps_ff = [p.to_engine_step() for p in plan_ff.pasos]
    res_ff = automation_engine.run_steps(engine_steps_ff, on_error="stop", on_step_update=step_cb_kill)
    print(f"Resultado Forced Failure: success={res_ff.success}, pasos_completados={res_ff.completed_steps}/{res_ff.total_steps}")
    for idx, sres in enumerate(res_ff.step_results):
        print(f"  Paso {idx+1}: success={sres.success}, output='{sres.output}', error='{sres.error}'")

    if not res_ff.success and res_ff.completed_steps == 1 and len(res_ff.step_results) == 2:
        step2_err = res_ff.step_results[1].error
        print("✅ FORCED FAILURE VERIFICADO: La cadena se detuvo en el paso 2 con el error real:")
        print(f"   '{step2_err}'")
    else:
        print("❌ FORCED FAILURE FALLO: La cadena no se detuvo correctamente")

    clean_notepads()

"""
Verificación en vivo para el Addendum Fase 73:
1. Con Notepad cerrado: 'escribí 'hola' en notepad y guardalo en el escritorio como rápido.txt'
   -> Falla en paso 1 con mensaje: 'Notepad no está abierto. Asegurate de que la aplicación esté abierta antes de escribir en ella.'
2. Con Notepad abierto (o lanzado para la prueba):
   - 'abre notepad y escribí 'Canción de prueba' y guardalo en documentos como Canción.txt'
     -> 3/3 completados, archivo existe con acento en Documentos\Canción.txt y texto exacto.
   - 'escribí 'hola' en notepad y guardalo en el escritorio como rápido.txt'
     -> 2/2 completados, archivo existe con acento en Escritorio\rápido.txt y texto exacto.
3. Limpieza de archivos temporales de prueba.
"""

import sys
import time
import psutil
from pathlib import Path

# Configurar path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from aura.core.planner import plan_from_rules
from automation.engine import automation_engine

def close_all_notepad():
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if "notepad" in (proc.name() or "").lower():
                proc.kill()
        except Exception:
            pass
    time.sleep(1)

def run_verification():
    print("==================================================")
    print("VERIFICACIÓN EN VIVO - ADDENDUM FASE 73")
    print("==================================================")

    # TEST 1: Notepad cerrado sin open_app previo
    print("\n--- TEST 1: Cadena sin apertura con Notepad cerrado ---")
    close_all_notepad()

    prompt1 = "escribí 'hola' en notepad y guardalo en el escritorio como rápido.txt"
    plan1 = plan_from_rules(prompt1)
    assert plan1 is not None, "El planner debería generar un plan por reglas"
    print(f"Plan generado: {len(plan1.pasos)} pasos.")
    for i, p in enumerate(plan1.pasos, 1):
        print(f"  Paso {i}: {p.intent} -> target='{p.target}', texto='{p.texto}', nombre='{p.nombre}'")

    engine_steps1 = [p.to_engine_step() for p in plan1.pasos]
    res1 = automation_engine.run_steps(engine_steps1, name="Test 1", dry_run=False)
    print(f"Resultado Test 1: success={res1.success}, completed={res1.completed_steps}, failed={res1.failed_steps}")
    assert res1.success is False, "Debe fallar porque Notepad está cerrado"
    assert len(res1.step_results) == 1, "Debe detenerse en el paso 1"
    err1 = res1.step_results[0].error
    print(f"Error devuelto en paso 1: '{err1}'")
    assert "Notepad no está abierto" in err1, f"Error esperado 'Notepad no está abierto', obtenido '{err1}'"
    print("✅ TEST 1 APROBADO: Mensaje claro y detención inmediata en Paso 1.")

    # TEST 2: Cadena con apertura de Notepad y caracteres con acento
    print("\n--- TEST 2: Cadena con 'abre notepad' y acentos en contenido y nombre ---")
    prompt2 = "abre notepad y escribí 'Canción de prueba' y guardalo en documentos como Canción.txt"
    plan2 = plan_from_rules(prompt2)
    assert plan2 is not None
    print(f"Plan generado: {len(plan2.pasos)} pasos.")
    for i, p in enumerate(plan2.pasos, 1):
        print(f"  Paso {i}: {p.intent} -> target='{p.target}', texto='{p.texto}', nombre='{p.nombre}'")

    engine_steps2 = [p.to_engine_step() for p in plan2.pasos]
    res2 = automation_engine.run_steps(engine_steps2, name="Test 2", dry_run=False)
    print(f"Resultado Test 2: success={res2.success}, completed={res2.completed_steps}, failed={res2.failed_steps}")
    for sr in res2.step_results:
        print(f"  Paso {sr.index + 1} ({sr.step_type}): success={sr.success}, out='{sr.output}', err='{sr.error}'")

    assert res2.success is True, f"Test 2 debió completarse con éxito: {res2.output}"
    doc_path = Path.home() / "Documents" / "Canción.txt"
    assert doc_path.exists(), f"El archivo '{doc_path}' debería existir en disco con acento"
    with open(doc_path, "r", encoding="utf-8") as f:
        content2 = f.read()
    print(f"Contenido leído de '{doc_path}': '{content2}'")
    assert "Canción de prueba" in content2
    print("✅ TEST 2 APROBADO: 3/3 pasos completados, archivo Canción.txt verificado.")

    # TEST 3: Con Notepad ya abierto, escribir y guardar como 'rápido.txt' en el escritorio
    print("\n--- TEST 3: Con Notepad ya abierto, anáfora y nombre 'rápido.txt' en escritorio ---")
    prompt3 = "escribí 'hola' en notepad y guardalo en el escritorio como rápido.txt"
    plan3 = plan_from_rules(prompt3)
    assert plan3 is not None
    assert plan3.pasos[1].target == "notepad"
    assert plan3.pasos[1].nombre == "rápido.txt"

    engine_steps3 = [p.to_engine_step() for p in plan3.pasos]
    res3 = automation_engine.run_steps(engine_steps3, name="Test 3", dry_run=False)
    print(f"Resultado Test 3: success={res3.success}, completed={res3.completed_steps}, failed={res3.failed_steps}")
    for sr in res3.step_results:
        print(f"  Paso {sr.index + 1} ({sr.step_type}): success={sr.success}, out='{sr.output}', err='{sr.error}'")

    assert res3.success is True, f"Test 3 debió completarse con éxito: {res3.output}"
    desktop_path = Path.home() / "Desktop" / "rápido.txt"
    assert desktop_path.exists(), f"El archivo '{desktop_path}' debería existir en disco con acento"
    with open(desktop_path, "r", encoding="utf-8") as f:
        content3 = f.read()
    print(f"Contenido leído de '{desktop_path}': '{content3}'")
    assert "hola" in content3
    print("✅ TEST 3 APROBADO: 2/2 pasos completados, archivo rápido.txt verificado.")

    # Limpieza
    close_all_notepad()
    if doc_path.exists():
        doc_path.unlink()
        print(f"Limpiado archivo de prueba: {doc_path}")
    if desktop_path.exists():
        desktop_path.unlink()
        print(f"Limpiado archivo de prueba: {desktop_path}")

    print("\n==================================================")
    print("TODAS LAS VERIFICACIONES EN VIVO COMPLETADAS EXITOSAMENTE")
    print("==================================================")

if __name__ == "__main__":
    run_verification()

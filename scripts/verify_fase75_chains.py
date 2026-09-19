# -*- coding: utf-8 -*-
"""
Verificación completa de las 5 cadenas reales para FASE 75:
1. P1: "abre notepad, escribe 'hola mundo' y guardalo en el escritorio como prueba.txt"
2. P2: "abre el bloc de notas y escribí 'segunda prueba aura fase 73' después guardalo en documentos con el nombre test.txt"
3. P3: "abre notepad y escribe 'prueba p3 con notepad' después guardalo en documentos con el nombre test_p3.txt"
4. P4 (Notepad cerrado): "escribí 'hola' en notepad y guardalo en el escritorio como rápido.txt"
5. P5 (Notepad abierto previamente): "escribí 'hola' en notepad y guardalo en el escritorio como rápido.txt"
"""

import sys
import time
import psutil
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

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


def run_chain(prompt: str, test_name: str, check_file: Path = None, expected_content: str = None) -> bool:
    print("\n" + "=" * 60)
    print(f"EJECUTANDO: {test_name}")
    print(f"Prompt: {prompt}")
    print("=" * 60)

    plan = plan_from_rules(prompt)
    if not plan:
        print(f"❌ FALLO: El planner no generó plan para: {prompt}")
        return False

    print(f"Plan generado ({len(plan.pasos)} pasos):")
    for i, s in enumerate(plan.pasos, start=1):
        print(f"  {i}. {s.description()} [intent={s.intent}, target={s.target}]")

    engine_steps = [p.to_engine_step() for p in plan.pasos]
    res = automation_engine.run_steps(engine_steps, on_error="stop")
    print(f"Resultado: success={res.success}, pasos_completados={res.completed_steps}/{res.total_steps}")
    for idx, sres in enumerate(res.step_results):
        print(f"  Paso {idx+1}: success={sres.success}, output='{sres.output}', error='{sres.error}'")

    if check_file:
        if check_file.exists():
            content = check_file.read_text(encoding="utf-8", errors="replace")
            print(f"✅ Archivo creado: {check_file} (tamaño: {len(content)} chars)")
            if expected_content and expected_content in content:
                print(f"✅ Contenido coincide: '{expected_content}'")
            elif expected_content:
                print(f"⚠️ Contenido no coincide. Esperado: '{expected_content}', Leído: '{content}'")
                return False
        else:
            print(f"❌ Archivo no encontrado: {check_file}")
            return False

    return res.success


def main():
    desktop = Path(Path.home()) / "Desktop"
    docs = Path(Path.home()) / "Documents"

    f_p1 = desktop / "prueba.txt"
    f_p2 = docs / "test.txt"
    f_p3 = docs / "test_p3.txt"
    f_rapido = desktop / "rápido.txt"

    # Limpiar archivos previos
    for f in (f_p1, f_p2, f_p3, f_rapido):
        if f.exists():
            try:
                f.unlink()
            except Exception:
                pass

    all_ok = True

    # 1. P1
    clean_notepads()
    p1_ok = run_chain(
        "abre notepad, escribe 'hola mundo' y guardalo en el escritorio como prueba.txt",
        "P1: Abre notepad + escribe 'hola mundo' + guarda como prueba.txt",
        check_file=f_p1,
        expected_content="hola mundo",
    )
    all_ok = all_ok and p1_ok
    clean_notepads()

    # 2. P2
    clean_notepads()
    p2_ok = run_chain(
        "abre el bloc de notas y escribí 'segunda prueba aura fase 73' después guardalo en documentos con el nombre test.txt",
        "P2: Bloc de notas + segunda prueba + documentos test.txt",
        check_file=f_p2,
        expected_content="segunda prueba aura fase 73",
    )
    all_ok = all_ok and p2_ok
    clean_notepads()

    # 3. P3
    clean_notepads()
    p3_ok = run_chain(
        "abre notepad y escribe 'prueba p3 con notepad' después guardalo en documentos con el nombre test_p3.txt",
        "P3: Notepad + prueba p3 + documentos test_p3.txt",
        check_file=f_p3,
        expected_content="prueba p3 con notepad",
    )
    all_ok = all_ok and p3_ok
    clean_notepads()

    # 4. P4 (Notepad cerrado)
    clean_notepads()
    print("\n" + "=" * 60)
    print("EJECUTANDO P4: Notepad cerrado previamente")
    print("Prompt: escribí 'hola' en notepad y guardalo en el escritorio como rápido.txt")
    print("=" * 60)
    plan_p4 = plan_from_rules("escribí 'hola' en notepad y guardalo en el escritorio como rápido.txt")
    engine_steps_p4 = [p.to_engine_step() for p in plan_p4.pasos]
    res_p4 = automation_engine.run_steps(engine_steps_p4, on_error="stop")
    print(f"Resultado P4: success={res_p4.success}, completados={res_p4.completed_steps}/{res_p4.total_steps}")
    p4_stopped = False
    if not res_p4.success and res_p4.completed_steps == 0 and len(res_p4.step_results) == 1:
        err = res_p4.step_results[0].error
        if "no está abierto" in err:
            print(f"✅ P4 DETENIDO CORRECTAMENTE: '{err}'")
            p4_stopped = True
        else:
            print(f"⚠️ Error inesperado en P4: '{err}'")
    else:
        print("❌ P4 no se detuvo en el paso 1")
    all_ok = all_ok and p4_stopped

    # 5. P5 (Notepad abierto previamente)
    clean_notepads()
    print("\n" + "=" * 60)
    print("EJECUTANDO P5: Notepad abierto previamente + rápido.txt con acento")
    print("Prompt: escribí 'hola' en notepad y guardalo en el escritorio como rápido.txt")
    print("=" * 60)
    # Abrir notepad
    import subprocess
    subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)

    p5_ok = run_chain(
        "escribí 'hola' en notepad y guardalo en el escritorio como rápido.txt",
        "P5: Notepad abierto previamente + rápido.txt",
        check_file=f_rapido,
        expected_content="hola",
    )
    all_ok = all_ok and p5_ok
    clean_notepads()

    # Limpieza final de archivos de prueba
    for f in (f_p1, f_p2, f_p3, f_rapido):
        if f.exists():
            try:
                f.unlink()
            except Exception:
                pass

    print("\n" + "=" * 60)
    if all_ok:
        print("🎉 TODAS LAS 5 PRUEBAS DE CADENA PASARON EXITOSAMENTE (SIN NAMEERROR)")
    else:
        print("❌ ALGUNAS PRUEBAS FALLARON")
    print("=" * 60)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

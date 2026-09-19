# -*- coding: utf-8 -*-
import sys
import re

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def parse_save_remainder(remainder: str, slots: list[str], last_app: str = "") -> dict:
    remainder = remainder.strip()
    dest = ""
    filename = ""
    app_found = ""

    title_pattern = r"\b(?:con\s+el\s+t[ií]tulo|con\s+t[ií]tulo|con\s+el\s+nombre|con\s+nombre|como)\s+"
    dest_pattern = r"\b(?:en\s+el|en\s+la|en\s+los|en\s+las|en)\s+([a-zA-Z0-9_áéíóúÁÉÍÓÚñÑ-]+)"

    m_title = re.search(title_pattern, remainder, re.IGNORECASE)
    m_dest = re.search(dest_pattern, remainder, re.IGNORECASE)

    if m_title and m_dest:
        if m_dest.start() < m_title.start():
            # Destino antes del título: e.g. 'en el escritorio como rápido.txt'
            dest = m_dest.group(1).strip()
            app_part = remainder[:m_dest.start()].strip()
            raw_fn = remainder[m_title.end():].strip()
        else:
            # Título antes del destino: e.g. 'como rápido.txt en el escritorio'
            dest = m_dest.group(1).strip()
            app_part = remainder[:m_title.start()].strip()
            raw_fn = remainder[m_title.end():m_dest.start()].strip()
        filename = raw_fn.strip("'\"`´")
    elif m_title:
        app_part = remainder[:m_title.start()].strip()
        filename = remainder[m_title.end():].strip().strip("'\"`´")
    elif m_dest:
        dest = m_dest.group(1).strip()
        app_part = (remainder[:m_dest.start()].strip() + " " + remainder[m_dest.end():].strip()).strip()
    else:
        app_part = remainder

    # Sanitizar app_part vs anáforas
    ANAPHORA_TOKENS = {
        "", "lo", "la", "los", "las", "el", "ahí", "ahi", "allí", "alli", "acá", "aca",
        "su contenido", "el contenido", "contenido", "ventana", "la ventana",
        "lo que escribiste", "documento", "el documento", "archivo", "el archivo",
        "esto", "eso", "todo", "guardalo", "guardala", "salvalo", "salvala",
        "después", "despues", "luego", "ahora",
    }
    clean_app = app_part.lower().strip()
    for prefix in ("el ", "la ", "los ", "las "):
        if clean_app.startswith(prefix):
            clean_app = clean_app[len(prefix):].strip()
            break

    if clean_app in ANAPHORA_TOKENS:
        app_found = last_app or "notepad"
    elif any(clean_app.endswith(ext) for ext in (".txt", ".docx", ".xlsx", ".pdf", ".py", ".md")):
        if not filename:
            filename = app_part.strip("'\"`´")
        app_found = last_app or "notepad"
    elif clean_app in ("notepad", "bloc", "bloc de notas"):
        app_found = "notepad"
    elif clean_app in ("word", "winword", "microsoft word"):
        app_found = "word"
    elif clean_app in ("excel", "microsoft excel"):
        app_found = "excel"
    else:
        app_found = clean_app or last_app or "notepad"

    return {"app": app_found, "filename": filename, "dest": dest}

tests = [
    ("en el escritorio como rápido.txt", "notepad"),
    ("como rápido.txt en el escritorio", "notepad"),
    ("el notepad en el escritorio como rápido.txt", ""),
    ("notepad como Canción.txt en documentos", ""),
    ("en documentos con el nombre test.txt", "word"),
    ("guardalo en el escritorio", "notepad"),
    ("como Canción de prueba.txt", "notepad"),
    ("en el escritorio con el titulo 'Amanecer'", "notepad"),
]

for t, la in tests:
    res = parse_save_remainder(t, [], la)
    print(f"{t!r:45} (last_app={la!r}) -> {res}")

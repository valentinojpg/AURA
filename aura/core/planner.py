# -*- coding: utf-8 -*-
"""
================================================================================
AURA — Planificador de Cadenas de Instrucciones Multi-Paso (Fase 71)
================================================================================
Permite que una sola frase con varias acciones encadenadas se ejecute
completa y en orden reutilizando el motor de automatizaciones existente.

Características:
  1. extract_slots: Protege cadenas entre comillas (§0, §1...) antes de cortar.
  2. split_steps: Corta por conjunciones (" y ", " luego ", " después ", etc.).
  3. is_instruction_chain: Detecta si hay >= 2 pasos accionables.
  4. plan_from_rules: Planificación determinista por reglas, anáfora y roles.
  5. plan_from_ai: Fallback al LLM usando [MODULO_PLAN].
  6. Límite de seguridad PLAN_MAX_STEPS (default 8).
================================================================================
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from config.settings import settings
from utils.logger import get_logger

_logger = get_logger("aura.core.planner")

# Límite por defecto de pasos por cadena
DEFAULT_MAX_STEPS = 8

# ─────────────────────────────────────────────────────────────────────────────
# 1. Extracción y Restauración de Slots (Texto entre comillas)
# ─────────────────────────────────────────────────────────────────────────────

# Expresión regular para capturar cualquier tipo de comillas:
# "...", '...', “...”, ‘...’, `...`
_QUOTES_REGEX = re.compile(
    r'(?:"([^"]*)"|\'([^\']*)\'|“([^”]*)”|‘([^’]*)’|`([^`]*)`)',
    re.UNICODE,
)


def extract_slots(text: str) -> tuple[str, list[str]]:
    """
    Extrae todo texto entre comillas como slots ordenados y los reemplaza
    por placeholders §0, §1, §2... antes de cualquier corte.
    Garantiza que nunca se corte dentro de un slot (ej: 'pan y queso').

    Args:
        text: Texto original del usuario.

    Returns:
        (texto_con_placeholders, lista_de_slots_extraidos)
    """
    if not text:
        return "", []

    slots: list[str] = []

    def _replace_match(m: re.Match) -> str:
        # Encontrar cuál grupo capturó el contenido dentro de las comillas
        content = next((g for g in m.groups() if g is not None), "")
        idx = len(slots)
        slots.append(content)
        return f"§{idx}"

    text_placeholder = _QUOTES_REGEX.sub(_replace_match, text)
    return text_placeholder, slots


def restore_slots(text: str, slots: list[str]) -> str:
    """
    Restaura los placeholders §0, §1, etc. con sus valores originales en slots.
    """
    if not text or not slots:
        return text

    result = text
    for i, slot_val in enumerate(slots):
        result = result.replace(f"§{i}", slot_val)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 2. División en Pasos por Conjunciones
# ─────────────────────────────────────────────────────────────────────────────

# Conjunciones ordenadas por longitud decreciente para evitar que "y" corte
# prefijos como "y después" o "y luego". También admite comas y puntos y comas
# como delimitadores de cláusulas independientes.
_CONJUNCTIONS_PATTERN = re.compile(
    r"(?:"
    r"(?:\s*,\s*|\s+)(?:"
    r"y\s+por\s+último|y\s+por\s+ultimo|y\s+después|y\s+despues|y\s+luego|y\s+por\s+fin|"
    r"luego|después|despues|entonces|también|tambien|"
    r"y|e"
    r")(?:\s*,\s*|\s+)"
    r"|"
    r"\s*[,;]\s+"
    r")",
    re.IGNORECASE,
)


def split_steps(text: str) -> list[str]:
    """
    Corta el texto en fragmentos secuenciales basándose en conjunciones
    fuera de slots. Limpia espacios y puntuación en los extremos.

    Args:
        text: Texto (idealmente procesado previamente con extract_slots).

    Returns:
        Lista de fragmentos limpios y no vacíos.
    """
    if not text or not text.strip():
        return []

    raw_fragments = _CONJUNCTIONS_PATTERN.split(text.strip())
    clean_fragments: list[str] = []

    for frag in raw_fragments:
        f = frag.strip().strip(" ,;.-")
        if f:
            clean_fragments.append(f)

    return clean_fragments


# ─────────────────────────────────────────────────────────────────────────────
# 3. Detección de Cadenas de Instrucciones
# ─────────────────────────────────────────────────────────────────────────────

_ACTION_VERBS = {
    # Apps
    "abre", "abrir", "abra", "abreme", "abri", "inicia", "iniciar", "ejecuta", "ejecutar", "lanza", "lanzar",
    "cierra", "cerrar", "cerra", "mata", "matar", "finaliza", "finalizar",
    # Web & Navegación
    "entra", "entrar", "navega", "navegar", "visita", "visitar",
    # Escritura
    "escribe", "escribi", "escribí", "escribir", "escribime", "redacta", "redactar", "tipea", "tipear",
    "pone", "poné", "poner", "poneme", "anota", "anotar",
    # Guardado
    "guarda", "guardar", "guardame", "guardate", "guardalo", "guardala",
    "salva", "salvar", "salvame", "salvate", "salvalo", "salvala",
    # Música & Media
    "pon", "reproduce", "reproducir", "reproducime", "escucha", "escuchar", "toca", "tocar",
    # Archivos
    "crea", "crear", "creame", "elimina", "eliminar", "borra", "borrar",
    "mueve", "mover", "traslada", "trasladar",
    "renombra", "renombrar",
    "busca", "buscar", "encuentra", "encontrar",
}

_POLITE_PREFIX_RE = re.compile(
    r"^(?:por favor\s+|podes\s+|puedes\s+|podrias\s+)?",
    re.IGNORECASE,
)


def _is_actionable_fragment(fragment: str, slots: list[str]) -> bool:
    """Verifica si un fragmento contiene un verbo de acción o comando ejecutable."""
    frag = fragment.strip().lower()
    if not frag:
        return False

    frag_clean = _POLITE_PREFIX_RE.sub("", frag).strip()
    first_word = frag_clean.split()[0] if frag_clean.split() else ""

    if first_word in _ACTION_VERBS:
        return True

    # Comprobar verbos compuestos como "cambia el nombre", "entra a", etc.
    if frag_clean.startswith(("cambia el nombre", "cambiar el nombre", "entra a", "entra en")):
        return True

    # Comprobar si coincide con el IntentRouter
    try:
        from aura.core.intent_router import parse as router_parse
        restored = restore_slots(fragment, slots)
        intent = router_parse(restored)
        if intent is not None and intent.nombre not in ("roast", "pedir_chiste", "queja_chiste"):
            return True
    except Exception:
        pass

    return False


def is_instruction_chain(text: str) -> bool:
    """
    Determina si un texto contiene una cadena de instrucciones de múltiples pasos.

    Reglas estrictas:
      - Al menos 2 fragmentos (>= 2).
      - Al menos 2 fragmentos deben ser comandos ejecutables con verbos de acción.
      - Si solo hay 1 fragmento ejecutable, retorna False para preservar el fast-path
        directo sin ninguna regresión.
    """
    if not text or not text.strip():
        return False

    placeholder_text, slots = extract_slots(text)
    fragments = split_steps(placeholder_text)

    if len(fragments) < 2:
        return False

    actionable_count = sum(1 for frag in fragments if _is_actionable_fragment(frag, slots))
    return actionable_count >= 2


# ─────────────────────────────────────────────────────────────────────────────
# 4. Estructuras de Datos del Plan
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PlanStep:
    """Representa un paso individual dentro de un plan multi-acción."""
    intent: str
    target: str = ""
    texto: str = ""
    nombre: str = ""
    destino: str = ""
    query: str = ""
    service: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    valid: bool = True
    unsupported_reason: str = ""

    def to_engine_step(self) -> dict[str, Any]:
        """Convierte este PlanStep al diccionario consumible por AutomationEngine."""
        stype = self.intent
        d: dict[str, Any] = {
            "type": stype,
            "valid": self.valid,
            "unsupported_reason": self.unsupported_reason,
        }

        if stype == "open_app":
            d["app"] = self.target
        elif stype == "open_url":
            d["url"] = self.target or self.extra.get("url", "")
        elif stype == "write_in_app":
            d["app"] = self.target
            d["texto"] = self.texto
        elif stype == "save_app_doc":
            d["app"] = self.target
            d["nombre"] = self.nombre
            d["destino"] = self.destino
        elif stype == "media_play":
            d["query"] = self.query or self.target
            d["service"] = self.service
        elif stype in ("create_file", "create_folder", "delete_file"):
            d["nombre"] = self.nombre or self.target
        elif stype in ("move_file", "rename_file"):
            d["origen"] = self.target
            d["destino"] = self.destino or self.nombre
        elif stype == "search_file":
            d["target"] = self.query or self.target
        elif stype == "close_app":
            d["app"] = self.target

        d.update(self.extra)
        return d

    def description(self) -> str:
        """Descripción legible en lenguaje natural para la checklist."""
        stype = self.intent
        if stype == "open_app":
            return f"Abrir {self.target}"
        elif stype == "open_url":
            site = self.extra.get("site", self.target)
            return f"Abrir {site}"
        elif stype == "write_in_app":
            preview = self.texto[:30] + "…" if len(self.texto) > 30 else self.texto
            return f"Escribir '{preview}' en {self.target}"
        elif stype == "save_app_doc":
            nom = f" con título '{self.nombre}'" if self.nombre else ""
            dest = f" en {self.destino}" if self.destino else ""
            return f"Guardar {self.target}{dest}{nom}"
        elif stype == "media_play":
            svc = f" en {self.service}" if self.service else ""
            return f"Reproducir '{self.query}'{svc}"
        elif stype == "create_file":
            return f"Crear archivo '{self.nombre or self.target}'"
        elif stype == "create_folder":
            return f"Crear carpeta '{self.nombre or self.target}'"
        elif stype == "delete_file":
            return f"Eliminar '{self.nombre or self.target}'"
        elif stype == "move_file":
            return f"Mover '{self.target}' a '{self.destino}'"
        elif stype == "rename_file":
            return f"Renombrar '{self.target}' a '{self.destino}'"
        elif stype == "search_file":
            return f"Buscar '{self.target}'"
        elif stype == "close_app":
            return f"Cerrar {self.target}"
        return f"{stype} {self.target}"


@dataclass
class Plan:
    """Plan de ejecución multi-paso."""
    pasos: list[PlanStep]
    origen: str  # "rules" | "ai"
    confianza: float = 1.0
    raw: str = ""

    def __len__(self) -> int:
        return len(self.pasos)

    def has_unsupported_steps(self) -> bool:
        """Indica si algún paso del plan fue marcado como no soportado."""
        return any(not p.valid for p in self.pasos)

    def unsupported_steps(self) -> list[PlanStep]:
        """Retorna la lista de pasos que no son soportados."""
        return [p for p in self.pasos if not p.valid]

    def actionable_steps(self) -> list[PlanStep]:
        """Pasos que realizan una acción sustantiva (no solo abrir/cerrar o setups)."""
        return [p for p in self.pasos if p.intent not in ("open_app", "open_url")]

    def has_valid_actionable_steps(self) -> bool:
        """Indica si hay al menos un paso de acción sustantiva que sea válido."""
        actions = self.actionable_steps()
        if not actions:
            return True
        return any(p.valid for p in actions)


def restore_plan_slots(plan: Plan, slots: list[str]) -> Plan:
    """
    Restaura todos los placeholders §0, §1... en cada campo del plan y sus pasos.
    Garantiza que ningún placeholder (§N) llegue a la validación, logs,
    mensajes de usuario ni resúmenes del plan.
    """
    if not plan or not slots:
        return plan

    if plan.raw:
        plan.raw = restore_slots(plan.raw, slots)

    for step in plan.pasos:
        step.target = restore_slots(step.target, slots)
        step.texto = restore_slots(step.texto, slots)
        step.nombre = restore_slots(step.nombre, slots)
        step.destino = restore_slots(step.destino, slots)
        step.query = restore_slots(step.query, slots)
        step.service = restore_slots(step.service, slots)
        step.unsupported_reason = restore_slots(step.unsupported_reason, slots)
        if step.extra:
            for k, v in list(step.extra.items()):
                if isinstance(v, str):
                    step.extra[k] = restore_slots(v, slots)
    return plan


def validate_plan_capabilities(plan: Plan) -> Plan:
    """
    Prevalidación de capacidades por aplicación sobre el plan generado (Fase 72/73).
    Verifica cada paso contra el registro data/app_capabilities.json:
      - write_in_app: capabilities.write
      - save_app_doc: capabilities.read (o save_as)
      - open_app, close_app, open_url, media_play: sin chequeo de capacidades.
    Si un paso no es posible según las capacidades de la app objetivo:
      - Marca step.valid = False
      - Enriquece el paso con step.unsupported_reason
    """
    from aura.core.app_capabilities import get_app_capabilities, normalize_app_name

    current_app = ""

    for idx, step in enumerate(plan.pasos, start=1):
        target_app = step.target or step.extra.get("app", "")
        if not target_app and current_app:
            target_app = current_app

        if step.intent in ("open_app", "close_app", "open_url", "media_play"):
            if step.intent == "open_app":
                current_app = target_app
            step.valid = True

        elif step.intent == "write_in_app":
            app_to_check = target_app or current_app
            if app_to_check:
                current_app = app_to_check
            norm_check = normalize_app_name(app_to_check)
            caps = get_app_capabilities(app_to_check)
            write_cap = caps.get("write")

            if write_cap is None:
                step.valid = False
                if norm_check == "spotify":
                    step.unsupported_reason = f"paso {idx} no soportado para {app_to_check} (Spotify no acepta texto externo; usá la skill media_play para buscar música)"
                else:
                    step.unsupported_reason = f"paso {idx} no soportado para {app_to_check} (no acepta texto externo)"
            else:
                step.valid = True

        elif step.intent == "save_app_doc":
            app_to_check = target_app or current_app
            if app_to_check:
                current_app = app_to_check
            caps = get_app_capabilities(app_to_check)
            read_cap = caps.get("read")
            save_cap = caps.get("save_as")

            if save_cap is None and read_cap is None:
                step.valid = False
                step.unsupported_reason = f"paso {idx} no soportado para {app_to_check} (no puedo leer su contenido)"
            else:
                step.valid = True

        else:
            step.valid = True

    return plan


# ─────────────────────────────────────────────────────────────────────────────
# 5. Planificación por Reglas (Determinista)
# ─────────────────────────────────────────────────────────────────────────────

# Mapeo de alias de sitios web y sus URLs
_SITE_ALIASES_MAP: dict[str, str] = {
    "youtube music": "https://music.youtube.com",
    "yt music": "https://music.youtube.com",
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "wikipedia": "https://es.wikipedia.org",
    "gmail": "https://mail.google.com",
    "calendar": "https://calendar.google.com",
    "drive": "https://drive.google.com",
    "whatsapp web": "https://web.whatsapp.com",
    "whatsapp": "https://web.whatsapp.com",
    "chatgpt": "https://chatgpt.com",
}


def _clean_app_name(app_str: str) -> str:
    """Limpia artículos y palabras sobrantes en nombres de aplicación."""
    a = app_str.strip().lower()
    for art in ("el ", "la ", "los ", "las ", "un ", "una ", "ese ", "este "):
        if a.startswith(art):
            a = a[len(art):].strip()
            break
    if a in ("bloc", "bloc de notas"):
        return "notepad"
    return a


def _get_fallback_app() -> str:
    """Retorna la app más reciente registrada en last_opened_apps o activa en el sistema."""
    try:
        from aura.skills.app_writer import last_opened_apps
        import psutil
        best_app = ""
        best_time = 0.0
        for app_name, entries in last_opened_apps.items():
            for entry in entries:
                pid = entry.get("pid")
                ts = entry.get("timestamp", 0)
                if pid and psutil.pid_exists(pid) and ts > best_time:
                    best_time = ts
                    best_app = app_name
        if best_app:
            return best_app
        # Si no hay registros previos de AURA, buscar procesos activos conocidos
        for proc in psutil.process_iter(["name"]):
            try:
                pname = (proc.name() or "").lower()
                if pname in ("notepad.exe", "notepadapp.exe"):
                    return "notepad"
                if pname in ("winword.exe", "word.exe"):
                    return "word"
                if pname == "excel.exe":
                    return "excel"
            except Exception:
                pass
    except Exception:
        pass
    return "notepad"


def plan_from_rules(text: str) -> Optional[Plan]:
    """
    Construye un Plan determinista a partir de reglas gramaticales y semánticas
    sin invocar al LLM.

    Resuelve:
      - Asignación de slots por rol:
          write_in_app -> texto
          save_app_doc / create_* -> nombre
          media_play -> query
      - Anáfora y seguimiento de referencia:
          Rastrea last_opened_apps / last_app para pasos implícitos
          (ej: 'abre notepad y escribe ... y guarda ...').
      - Límite de seguridad PLAN_MAX_STEPS.

    Returns:
        Plan si todos los pasos fueron resueltos con éxito por reglas, o None si
        se requiere recurrir a la IA.
    """
    if not text or not text.strip():
        return None

    placeholder_text, slots = extract_slots(text)
    fragments = split_steps(placeholder_text)

    if len(fragments) < 2:
        return None

    max_steps = int(settings.get("PLAN_MAX_STEPS", DEFAULT_MAX_STEPS))
    if len(fragments) > max_steps:
        _logger.warning("Cadena supera PLAN_MAX_STEPS (%d > %d). Truncando.", len(fragments), max_steps)
        fragments = fragments[:max_steps]

    pasos: list[PlanStep] = []
    last_opened_apps: list[str] = []
    last_app = ""
    last_web_site = ""

    from aura.core.intent_router import IntentRouter, _clean_target, normalize
    router = IntentRouter()

    for idx, frag in enumerate(fragments):
        norm_frag = normalize(frag)
        restored_frag = restore_slots(frag, slots)

        # A) write_in_app
        # Casos: "escribe §0", "escribe en notepad §0", "escribe 'hola' en notepad"
        write_re = re.compile(r"^(?:escribe|escribi|escribí|escribir|escribime|redacta|tipea|pone|poné|poner|anota)\s+(.+)$", re.IGNORECASE)
        m_write = write_re.search(frag) or write_re.search(norm_frag)
        if m_write:
            # Siempre extraer remainder del fragmento original para preservar mayúsculas y acentos
            if m_write.string is not frag:
                verb_len = len(frag.split()[0])
                remainder = frag[verb_len:].strip()
            else:
                remainder = m_write.group(1).strip()

            app_found = ""
            text_extracted = ""

            # Verificar si menciona "en <app>"
            m_prep = re.search(r"\s+en\s+([a-zA-Z0-9_-]+)$", remainder, re.IGNORECASE)
            m_prep_start = re.search(r"^en\s+([a-zA-Z0-9_-]+)\s+(.+)$", remainder, re.IGNORECASE)

            if m_prep_start:
                app_found = _clean_app_name(m_prep_start.group(1))
                text_extracted = m_prep_start.group(2).strip()
            elif m_prep:
                app_found = _clean_app_name(m_prep.group(1))
                text_extracted = remainder[:m_prep.start()].strip()
            else:
                # No menciona app -> Anáfora (usar last_app o fallback de apps activas)
                app_found = last_app or _get_fallback_app()
                text_extracted = remainder

            if app_found:
                last_app = app_found

            # Asignación de slot por rol (write_in_app -> texto)
            texto_final = restore_slots(text_extracted, slots).strip().strip("'\"`´")
            pasos.append(
                PlanStep(
                    intent="write_in_app",
                    target=app_found,
                    texto=texto_final,
                    extra={"app": app_found},
                )
            )
            continue

        # B) save_app_doc
        # Casos: "guarda el notepad en el escritorio con el titulo §1"
        #        "guarda en el escritorio con el titulo 'Amanecer'"
        #        "guardalo en el escritorio como rápido.txt"
        #        "guardalo como rápido.txt en el escritorio"
        #        "guardalo en documentos como Canción.txt"
        #        "guardalo en el escritorio"
        save_re = re.compile(
            r"^(?:guarda|guardar|guardame|guardate|guardalo|guardala|guardá|guardálo|guardála|salva|salvar|salvame|salvate|salvalo|salvala|salvá|salválo|salvála)\b(?:\s+(.+))?$",
            re.IGNORECASE,
        )
        m_save = save_re.search(frag) or save_re.search(norm_frag)
        if m_save:
            # Siempre extraer remainder del fragmento original para preservar mayúsculas y acentos
            if m_save.string is not frag:
                verb_len = len(frag.split()[0])
                remainder = frag[verb_len:].strip()
            else:
                remainder = (m_save.group(1) or "").strip()

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
                filename = restore_slots(raw_fn, slots).strip().strip("'\"`´")
            elif m_title:
                app_part = remainder[:m_title.start()].strip()
                raw_fn = remainder[m_title.end():].strip()
                filename = restore_slots(raw_fn, slots).strip().strip("'\"`´")
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
                "después", "despues", "luego", "ahora", "de nuevo", "otra vez",
            }
            clean_app = app_part.lower().strip()
            for prefix in ("el ", "la ", "los ", "las "):
                if clean_app.startswith(prefix):
                    clean_app = clean_app[len(prefix):].strip()
                    break

            COMMON_EXTENSIONS = (".txt", ".docx", ".xlsx", ".doc", ".xls", ".pdf", ".py", ".md", ".csv", ".json", ".log")
            if clean_app in ANAPHORA_TOKENS:
                app_found = last_app or _get_fallback_app()
            elif any(clean_app.endswith(ext) for ext in COMMON_EXTENSIONS):
                # Regla Mandatoria: NUNCA debe quedar un filename en el campo app/target
                if not filename:
                    filename = app_part.strip("'\"`´")
                app_found = last_app or _get_fallback_app()
            elif clean_app in ("notepad", "bloc", "bloc de notas"):
                app_found = "notepad"
            elif clean_app in ("word", "winword", "microsoft word"):
                app_found = "word"
            elif clean_app in ("excel", "microsoft excel"):
                app_found = "excel"
            else:
                app_found = _clean_app_name(clean_app) or last_app or _get_fallback_app()

            if app_found:
                last_app = app_found

            pasos.append(
                PlanStep(
                    intent="save_app_doc",
                    target=app_found,
                    nombre=filename,
                    destino=dest,
                    extra={"app": app_found, "filename": filename, "destination": dest},
                )
            )
            continue

        # C) media_play
        # Casos: "pon 'Bad Romance' de Lady Gaga", "pon §0 de Lady Gaga", "reproduce Bohemian Rhapsody"
        media_re = re.compile(
            r"^(?:pon|pone|poné|poner|poneme|reproduce|reproducir|reproducime|reproducí|escuchar|escucha|toca|tocar)\s+(?:la\s+cancion\s+|el\s+tema\s+|la\s+pista\s+|el\s+video\s+|musica\s+de\s+|música\s+de\s+|a\s+)?(.+)$",
            re.IGNORECASE,
        )
        m_media = media_re.search(frag) or media_re.search(norm_frag)
        if m_media:
            raw_query = m_media.group(1).strip()
            query_val = restore_slots(raw_query, slots).strip().strip("'\"`´")

            # Detectar servicio ("en youtube music", "en spotify", "en youtube")
            service_found = ""
            m_svc = re.search(r"\s+en\s+(youtube\s+music|yt\s+music|spotify|youtube)$", query_val, re.IGNORECASE)
            if m_svc:
                service_found = m_svc.group(1).strip()
                query_val = query_val[:m_svc.start()].strip()
            elif last_web_site in ("youtube music", "yt music"):
                service_found = "youtube_music"
            elif last_web_site == "youtube":
                service_found = "youtube"
            elif last_web_site == "spotify":
                service_found = "spotify"
            else:
                service_found = settings.get("MEDIA_SERVICE", "youtube_music")

            from skills.builtin.media_play_skill import normalize_service_name
            norm_svc = normalize_service_name(service_found)

            pasos.append(
                PlanStep(
                    intent="media_play",
                    target=query_val,
                    query=query_val,
                    service=norm_svc,
                    extra={"query": query_val, "service": norm_svc},
                )
            )
            continue

        # D) open_url / navegación web
        # Casos: "entra a youtube music", "entra a youtube", "abre https://..."
        m_url = re.search(
            r"^(?:entra|entrar|navega|navegar|visita|visitar|abre|abrir)\s+(?:a\s+|en\s+|al\s+sitio\s+|a\s+la\s+web\s+|la\s+pagina\s+de\s+|la\s+página\s+de\s+)?(.+)$",
            norm_frag,
            re.IGNORECASE,
        )
        if m_url:
            raw_site = m_url.group(1).strip().lower()
            if raw_site in _SITE_ALIASES_MAP:
                url_resolved = _SITE_ALIASES_MAP[raw_site]
                last_web_site = raw_site
                pasos.append(
                    PlanStep(
                        intent="open_url",
                        target=url_resolved,
                        extra={"url": url_resolved, "site": raw_site},
                    )
                )
                continue
            elif raw_site.startswith("http://") or raw_site.startswith("https://") or raw_site.startswith("www."):
                target_url = "https://" + raw_site if raw_site.startswith("www.") else raw_site
                pasos.append(
                    PlanStep(
                        intent="open_url",
                        target=target_url,
                        extra={"url": target_url},
                    )
                )
                continue

        # E) open_app
        # Casos: "abre notepad", "inicia discord", "ejecuta firefox"
        m_open = re.search(
            r"^(?:abre|abrir|abra|abreme|abri|inicia|iniciar|ejecuta|ejecutar|lanza|lanzar)\s+(?:la\s+app\s+|el\s+programa\s+|la\s+aplicacion\s+)?(.+)$",
            norm_frag,
            re.IGNORECASE,
        )
        if m_open:
            app_target = _clean_target(m_open.group(1))
            # Descartar si era un alias web ya manejado
            if app_target.lower() not in _SITE_ALIASES_MAP:
                last_opened_apps.append(app_target)
                last_app = app_target
                pasos.append(
                    PlanStep(
                        intent="open_app",
                        target=app_target,
                        extra={"app": app_target},
                    )
                )
                continue

        # F) close_app
        m_close = re.search(
            r"^(?:cierra|cerrar|cerra|mata|matar|finaliza|finalizar)\s+(?:la\s+app\s+|el\s+programa\s+|la\s+aplicacion\s+)?(.+)$",
            norm_frag,
            re.IGNORECASE,
        )
        if m_close:
            app_target = _clean_target(m_close.group(1))
            pasos.append(
                PlanStep(
                    intent="close_app",
                    target=app_target,
                    extra={"app": app_target},
                )
            )
            continue

        # G) IntentRouter genérico para acciones de archivos u otras intenciones soportadas
        intent = router.parse(restored_frag)
        if intent is not None:
            stype = intent.nombre
            if stype in ("create_file", "create_folder", "delete_file", "move_file", "rename_file", "search_file"):
                nombre_val = restore_slots(intent.extra.get("nombre", intent.target), slots)
                destino_val = restore_slots(intent.extra.get("destino", ""), slots)
                pasos.append(
                    PlanStep(
                        intent=stype,
                        target=intent.target,
                        nombre=nombre_val,
                        destino=destino_val,
                        extra=intent.extra,
                    )
                )
                continue

        # Si un fragmento no pudo resolverse mediante reglas, salir y permitir fallback a IA
        _logger.debug("plan_from_rules: fragmento '%s' no pudo ser resuelto por reglas.", frag)
        return None

    if len(pasos) >= 2:
        p = Plan(pasos=pasos, origen="rules", confianza=1.0, raw=text)
        restore_plan_slots(p, slots)
        return validate_plan_capabilities(p)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# 6. Planificación con IA (Fallback)
# ─────────────────────────────────────────────────────────────────────────────

def plan_from_ai(text: str, provider: Any = None) -> Optional[Plan]:
    """
    Descompone y planifica la cadena de instrucciones usando el modelo de IA
    y el módulo canónico [MODULO_PLAN] del Prompt Maestro.

    Args:
        text: Texto del usuario.
        provider: Proveedor de IA activo (opcional).

    Returns:
        Plan si el modelo retornó un JSON estructurado válido con >= 2 pasos,
        o None si falló.
    """
    if not text or not text.strip():
        return None

    if provider is None:
        try:
            from ai.provider_factory import get_default_provider
            provider = get_default_provider()
        except Exception as e:
            _logger.warning("plan_from_ai: no se pudo obtener proveedor de IA: %s", e)
            return None

    try:
        from ai.provider_interface import ChatMessage
        from aura.ai.prompt_assembler import assemble_prompt
        from aura.personality import get_current_personality

        sys_prompt = assemble_prompt(
            context="plan",
            personality=get_current_personality(),
            provider=getattr(provider, "name", "ollama"),
            model=getattr(provider, "model", None),
        )

        messages = [
            ChatMessage(role="system", content=sys_prompt),
            ChatMessage(role="user", content=text),
        ]

        response = provider.chat(messages, temperature=0.1, max_tokens=300)
        raw_content = response.content.strip() if hasattr(response, "content") else str(response).strip()

        # Limpiar posibles bloques markdown ```json ... ```
        if "```" in raw_content:
            raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content, flags=re.MULTILINE)
            raw_content = re.sub(r"\s*```$", "", raw_content, flags=re.MULTILINE).strip()

        data = json.loads(raw_content)
        if not isinstance(data, dict):
            return None

        raw_pasos = data.get("pasos", [])
        if not isinstance(raw_pasos, list) or len(raw_pasos) < 2:
            return None

        max_steps = int(settings.get("PLAN_MAX_STEPS", DEFAULT_MAX_STEPS))
        raw_pasos = raw_pasos[:max_steps]

        COMMON_EXTENSIONS = (".txt", ".docx", ".xlsx", ".doc", ".xls", ".pdf", ".py", ".md", ".csv", ".json", ".log")
        last_app_ai = ""
        pasos: list[PlanStep] = []
        for p in raw_pasos:
            if not isinstance(p, dict):
                continue
            intent = str(p.get("intent", "")).strip()
            if not intent:
                continue
            target_val = str(p.get("target", "")).strip()
            nom_val = str(p.get("nombre", "")).strip()
            dest_val = str(p.get("destino", "")).strip()
            txt_val = str(p.get("texto", "")).strip()
            query_val = str(p.get("query", "")).strip()
            service_val = str(p.get("service", "")).strip()

            if intent in ("open_app", "write_in_app"):
                if target_val and not any(target_val.lower().endswith(ext) for ext in COMMON_EXTENSIONS):
                    last_app_ai = target_val
            elif intent == "save_app_doc":
                if any(target_val.lower().endswith(ext) for ext in COMMON_EXTENSIONS):
                    if not nom_val:
                        nom_val = target_val
                    target_val = last_app_ai or _get_fallback_app()
                elif not target_val or target_val.lower() in ("lo", "la", "ahí", "ahi", "archivo", "documento", "guardalo", "guardala"):
                    target_val = last_app_ai or _get_fallback_app()
                last_app_ai = target_val

            pasos.append(
                PlanStep(
                    intent=intent,
                    target=target_val,
                    texto=txt_val,
                    nombre=nom_val,
                    destino=dest_val,
                    query=query_val,
                    service=service_val,
                    extra={k: v for k, v in p.items() if k not in ("intent", "target", "texto", "nombre", "destino", "query", "service")},
                )
            )

        if len(pasos) >= 2:
            conf = float(data.get("confianza", 0.9))
            p_obj = Plan(pasos=pasos, origen="ai", confianza=conf, raw=text)
            _, slots = extract_slots(text)
            restore_plan_slots(p_obj, slots)
            return validate_plan_capabilities(p_obj)

    except Exception as exc:
        _logger.warning("plan_from_ai: error generando plan con IA: %s", exc)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# 7. Seguridad: Chequeo de Acciones Destructivas
# ─────────────────────────────────────────────────────────────────────────────

def is_destructive_plan(plan: Plan) -> tuple[bool, str]:
    """
    Verifica si algún paso del plan implica una acción destructiva o irreversible
    (ej: eliminar archivos o carpetas, apagar el sistema).

    Returns:
        (es_destructivo, descripcion_del_motivo)
    """
    if not plan or not plan.pasos:
        return False, ""

    for paso in plan.pasos:
        if paso.intent == "delete_file":
            target = paso.nombre or paso.target or "archivo o carpeta"
            return True, f"Eliminación de '{target}'"

        # Detección de comandos peligrosos en targets
        low_t = (paso.target or "").lower()
        if any(w in low_t for w in ("apagar", "reiniciar", "shutdown", "format", "rmdir /s")):
            return True, f"Comando crítico del sistema en '{paso.target}'"

    return False, ""

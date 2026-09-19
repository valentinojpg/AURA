"""
AURA — Motor de Comprensión de Comandos con Errores de Tipeo (Fase 54).

Implementa 3 capas de comprensión en orden estricto antes de enviar al chat normal:
1. CAPA 1 - Normalización agresiva:
   - Minúsculas, sin tildes, sin signos de puntuación.
   - Colapsar espacios múltiples.
   - Generación de variantes: tokens separados, tokens unidos ("notepa d" -> "notepad"),
     sin último token si es ruido.
2. CAPA 2 - Fuzzy matching con lógica (stdlib difflib):
   - Verbos e intents conocidos con cutoff 0.75 ("cierrra" -> "cerrar").
   - Targets contra built-in, favoritos, procesos corrientes, app_index.json y .lnk.
   - Confianza:
     * >= 0.85 con un solo candidato: ejecutar directo con "Entendí: <acción>".
     * 0.60 - 0.85 con un solo candidato claro: ejecutar mostrando corrección entre paréntesis.
     * 0.60 - 0.85 con varios candidatos: preguntar cuál listando opciones.
     * < 0.60: pasar a Capa 3.
3. CAPA 3 - Intérprete IA local (Ollama qwen2.5:3b):
   - System prompt estricto con salida JSON pura.
   - Si intent != null y target resuelve: ejecutar con "Interpreté: <intent> <target>".
   - Si intent == null o JSON inválido: derivar a chat conversacional normal.
4. APRENDIZAJE:
   - Memoria persistente de typos aprendidos en data/learning/typo_memory.json.
   - Registro de mapeos typo -> target para resolución instantánea en Capa 2.
"""

from __future__ import annotations

import difflib
import json
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Set, Tuple

import psutil

from utils.logger import get_logger
from config.settings import settings
from aura.core.entity_resolver import entity_resolver, ResolvedEntity, BUILTIN_ALIASES, is_url_or_domain

_logger = get_logger("aura.core.fuzzy_interpreter")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
LEARNING_DIR = DATA_DIR / "learning"
TYPO_MEMORY_FILE = LEARNING_DIR / "typo_memory.json"
PROGRAMS_FILE = DATA_DIR / "programs.json"

# ─────────────────────────────────────────────────────────────────────────────
# Estructuras de Datos
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class InterpretationResult:
    """
    Resultado de la interpretación de un comando con o sin errores de tipeo.
    """
    status: str             # "execute_direct" | "execute_with_note" | "ask_user" | "execute_ai" | "needs_deep_scan" | "none"
    intent: str = ""
    target: str = ""
    raw_target: str = ""
    raw_text: str = ""
    canon_verb: str = ""
    display_message: str = ""
    resolved_entity: Optional[ResolvedEntity] = None
    candidates: list[str] = field(default_factory=list)
    confidence: float = 0.0
    layer: int = 1          # 1: Normalización, 2: Fuzzy difflib, 3: Intérprete IA
    extra: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Memoria de Aprendizaje de Typos
# ─────────────────────────────────────────────────────────────────────────────

class TypoMemory:
    """
    Gestor de memoria persistente de errores de tipeo corregidos exitosamente.
    Almacena mapeos typo -> target en data/learning/typo_memory.json.
    """

    def __init__(self, file_path: Optional[Path] = None) -> None:
        self._path = file_path or TYPO_MEMORY_FILE
        self._lock = threading.RLock()
        self._cache: Optional[dict[str, dict[str, Any]]] = None

    def _ensure_loaded(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            if self._cache is not None:
                return self._cache

            if not self._path.exists():
                self._cache = {}
                return self._cache

            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._cache = data.get("typos", {})
                    else:
                        self._cache = {}
            except Exception as e:
                _logger.warning(f"TypoMemory: error leyendo {self._path}: {e}")
                self._cache = {}

            return self._cache

    def _save(self) -> None:
        with self._lock:
            if self._cache is None:
                return
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "version": "1.0",
                    "updated_at": datetime.now().isoformat(),
                    "typos": self._cache,
                }
                temp_path = self._path.with_suffix(".tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                temp_path.replace(self._path)
            except Exception as e:
                _logger.error(f"TypoMemory: error guardando {self._path}: {e}")

    def lookup(self, raw_typo: str) -> Optional[dict[str, Any]]:
        """Busca un typo normalizado en la memoria de aprendizaje."""
        key = normalize_aggressive(raw_typo)
        if not key:
            return None
        with self._lock:
            store = self._ensure_loaded()
            return store.get(key)

    def learn(
        self,
        raw_typo: str,
        target: str,
        intent: str,
        confidence: float = 1.0,
        layer: int = 2,
    ) -> None:
        """Guarda un nuevo mapeo typo -> target."""
        key = normalize_aggressive(raw_typo)
        if not key or not target:
            return
        with self._lock:
            store = self._ensure_loaded()
            store[key] = {
                "target": target,
                "intent": intent,
                "confidence": float(confidence),
                "layer": int(layer),
                "timestamp": datetime.now().isoformat(),
            }
            self._save()
            _logger.info(
                f"TypoMemory: Aprendido '{key}' -> '{target}' (intent='{intent}', layer={layer})"
            )

    def clear(self) -> None:
        """Limpia la memoria (para pruebas unitarias)."""
        with self._lock:
            self._cache = {}
            if self._path.exists():
                try:
                    self._path.unlink()
                except Exception:
                    pass

    def all_mappings(self) -> dict[str, str]:
        """Retorna todos los mapeos {typo: target}."""
        with self._lock:
            store = self._ensure_loaded()
            return {k: v.get("target", "") for k, v in store.items() if v.get("target")}


# Singleton de memoria
typo_memory = TypoMemory()


# ─────────────────────────────────────────────────────────────────────────────
# CAPA 1: Normalización Agresiva y Generador de Variantes
# ─────────────────────────────────────────────────────────────────────────────

def normalize_aggressive(text: str) -> str:
    """
    CAPA 1: Normalización agresiva del texto:
      - Minúsculas
      - Sin tildes / diacríticos (á->a, é->e, etc.)
      - Sin signos de puntuación (reemplaza cualquier carácter no alfanumérico por espacio)
      - Espacios múltiples colapsados a uno solo
    """
    if not text:
        return ""
    # Quitar tildes y diacríticos sin round-trips encode/decode
    norm = "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c) and ord(c) < 128
    )
    norm = norm.lower()
    # Reemplazar cualquier puntuación por espacio (incluyendo _)
    norm = re.sub(r"[^a-z0-9\s]", " ", norm)
    # Colapsar espacios múltiples
    norm = re.sub(r"\s+", " ", norm).strip()
    return norm


def generate_target_variants(target_text: str) -> list[str]:
    """
    CAPA 1: Genera variantes del target para contemplar errores de tipeo comunes:
      1. Tokens separados originales (ej: "notepa d")
      2. Tokens unidos sin espacios (ej: "notepad")
      3. Sin el último token si es ruido (longitud <= 2 caracteres)
      4. Merges de pares adyacentes de tokens
      5. Variante sin artículos iniciales ("el ", "la ", "un ", "una ")
    """
    norm = normalize_aggressive(target_text)
    if not norm:
        return []

    tokens = norm.split()
    variants: list[str] = []

    def _add(v: str) -> None:
        v_clean = v.strip()
        if v_clean and v_clean not in variants:
            variants.append(v_clean)

    # 1. Tokens separados originales
    _add(norm)

    # 2. Tokens unidos (ej: "notepa d" -> "notepad")
    if len(tokens) >= 2:
        _add("".join(tokens))

    # 3. Sin el último token si es ruido (1 o 2 caracteres)
    if len(tokens) >= 2 and len(tokens[-1]) <= 2:
        _add(" ".join(tokens[:-1]))
        _add("".join(tokens[:-1]))

    # 4. Si hay 3 o más tokens, probar unión de los dos primeros
    if len(tokens) >= 3:
        _add(tokens[0] + tokens[1] + " " + " ".join(tokens[2:]))
        _add(" ".join(tokens[:-2]) + " " + tokens[-2] + tokens[-1])

    # 5. Descarte de artículos iniciales
    articles = ["el", "la", "los", "las", "un", "una", "de", "del"]
    for v in list(variants):
        parts = v.split()
        if len(parts) >= 2 and parts[0] in articles:
            _add(" ".join(parts[1:]))
            _add("".join(parts[1:]))

    return variants


# ─────────────────────────────────────────────────────────────────────────────
# CAPA 2: Fuzzy Matching con Lógica (difflib)
# ─────────────────────────────────────────────────────────────────────────────

# Tabla de verbos e intenciones conocidas
KNOWN_VERBS_CONFIG: list[dict[str, Any]] = [
    {
        "intent": "open_url",
        "canon": "abrir url",
        "forms": ["abrir url", "abre url", "navegar a", "navega a", "entrar a", "entra a", "visitar", "visita"],
        "multiword": True,
    },
    {
        "intent": "create_folder",
        "canon": "crear carpeta",
        "forms": [
            "crear carpeta", "crea carpeta", "crear una carpeta", "crea una carpeta",
            "crear directorio", "crea directorio", "carpeta nueva", "nueva carpeta",
            "hacer carpeta", "hace carpeta"
        ],
        "multiword": True,
    },
    {
        "intent": "create_file",
        "canon": "crear archivo",
        "forms": [
            "crear archivo", "crea archivo", "crear un archivo", "crea un archivo",
            "crear fichero", "crea fichero", "archivo nuevo", "nuevo archivo",
            "hacer archivo", "hace archivo"
        ],
        "multiword": True,
    },
    {
        "intent": "close_app",
        "canon": "cerrar",
        "forms": [
            "cerrar", "cierra", "cierre", "cierrame", "cierrra", "cerra", "serrar",
            "matar", "mata", "finalizar", "finaliza", "terminar", "termina"
        ],
        "multiword": False,
    },
    {
        "intent": "open_app",
        "canon": "abrir",
        "forms": [
            "abrir", "abre", "abra", "abreme", "abrirr", "abri", "habrir",
            "ejecutar", "ejecuta", "iniciar", "inicia", "lanzar", "lanza"
        ],
        "multiword": False,
    },
    {
        "intent": "search_file",
        "canon": "buscar",
        "forms": [
            "buscar", "busca", "busque", "buscame", "encuentra", "encontrar",
            "localizar", "localiza"
        ],
        "multiword": False,
    },
    {
        "intent": "move_file",
        "canon": "mover",
        "forms": ["mover", "mueve", "mueva", "move", "trasladar", "traslada"],
        "multiword": False,
    },
    {
        "intent": "rename_file",
        "canon": "renombrar",
        "forms": ["renombrar", "renombra", "renombre", "cambiar nombre", "cambia el nombre"],
        "multiword": False,
    },
    {
        "intent": "delete_file",
        "canon": "eliminar",
        "forms": ["eliminar", "elimina", "elimine", "borrar", "borra", "borre", "remover", "remueve"],
        "multiword": False,
    },
    {
        "intent": "roast",
        "canon": "insultame",
        "forms": [
            "insultame", "insultamee", "insultame por favor", "insultame un poco",
            "insultame fuerte", "insultame bien", "insultame mas", "insultame posta",
            "roasteame", "roasteamee", "roast", "roastear", "dame un roast", "dame un insulto",
            "tirame un palo", "tirame un bife", "tírame un palo", "tirame un paloo",
            "bardeame", "bardear", "bardea", "haceme mierda"
        ],
        "multiword": True,
    },
    {
        "intent": "write_in_app",
        "canon": "escribir en",
        "forms": [
            "escribir en", "escribe en", "escribi en", "escribime en",
            "redacta en", "redactar en", "pone en", "poné en", "tipea en", "tipear en",
            "manda en", "mandar en", "dentro de", "escribe dentro de",
            "escribi dentro de", "escribir dentro de", "escribime dentro de",
            "anota en", "anotame en"
        ],
        "multiword": True,
    },
    {
        "intent": "save_app_doc",
        "canon": "guardar",
        "forms": [
            "guardar en", "guarda en", "guardá en", "guardar el", "guarda el", "guardá el",
            "guardar ese", "guarda ese", "guardá ese", "guardar lo que", "guarda lo que",
            "guardar la ventana", "guarda la ventana", "guardar", "guarda", "guardá",
            "salvar", "salva", "salvá"
        ],
        "multiword": True,
    },
    {
        "intent": "queja_chiste",
        "canon": "queja chiste",
        "forms": [
            "no es un chiste", "eso no fue un chiste", "me estas contando datos",
            "no me hiciste reir", "que mal chiste", "eso no es gracioso",
            "te pedi un chiste", "eso no era un chiste", "eso es un dato"
        ],
        "multiword": True,
    },
    {
        "intent": "pedir_chiste",
        "canon": "chiste",
        "forms": [
            "chiste", "un chiste", "contame un chiste", "contate un chiste",
            "tirate un chiste", "decime un chiste", "humor negro", "haceme reir",
            "contame algo gracioso", "algo oscuro y gracioso", "joke", "tell me a joke"
        ],
        "multiword": True,
    },
]

# Palabras clave y términos comunes para búsqueda y archivos
COMMON_DOC_KEYWORDS = [
    "informe", "documento", "proyecto", "notas", "archivo", "reporte",
    "tarea", "datos", "presupuesto", "resumen", "manual", "codigo", "test"
]


class FuzzyInterpreter:
    """
    Intérprete multinivel de intenciones y comandos con tolerancia a errores de tipeo.
    """

    def __init__(self, memory: Optional[TypoMemory] = None) -> None:
        self.memory = memory or typo_memory
        self._verb_cutoff = 0.75

    def match_verb(self, norm_text: str) -> Optional[Tuple[str, str, str, float]]:
        """
        Matchea el inicio del texto contra verbos conocidos con cutoff 0.75.

        Returns:
            (intent, canon_verb, target_remainder, confidence) o None si no coincide.
        """
        if not norm_text:
            return None

        tokens = norm_text.split()
        if not tokens:
            return None

        best_match: Optional[Tuple[str, str, str, float]] = None
        best_ratio = 0.0

        # Evaluación de todas las formas (de 1 palabra o multi-palabra)
        for cfg in KNOWN_VERBS_CONFIG:
            intent = cfg["intent"]
            canon = cfg["canon"]
            for form in cfg["forms"]:
                form_tokens = form.split()
                if len(form_tokens) == 1:
                    ratio = difflib.SequenceMatcher(None, tokens[0], form).ratio()
                    if ratio >= self._verb_cutoff and ratio > best_ratio:
                        remainder = " ".join(tokens[1:])
                        best_ratio = ratio
                        best_match = (intent, canon, remainder, ratio)
                elif len(tokens) >= len(form_tokens):
                    test_prefix = " ".join(tokens[: len(form_tokens)])
                    ratio = difflib.SequenceMatcher(None, test_prefix, form).ratio()
                    if ratio >= self._verb_cutoff and ratio > best_ratio:
                        remainder = " ".join(tokens[len(form_tokens) :])
                        best_ratio = ratio
                        best_match = (intent, canon, remainder, ratio)

        return best_match

    def build_target_corpus(self, intent: str) -> Set[str]:
        """
        Construye el universo de targets válidos para matchear con difflib:
        - Alias built-in
        - Typos aprendidos en memoria
        - Favoritos en data/programs.json
        - Procesos del sistema actualmente en ejecución
        - Aplicaciones indexadas en app_index.json
        - Nombres de archivos y carpetas del workspace (para búsqueda y archivos)
        """
        corpus: Set[str] = set()

        # a) Alias built-in
        for k in BUILTIN_ALIASES.keys():
            corpus.add(normalize_aggressive(k))

        # b) Memoria de typos
        for learned_target in self.memory.all_mappings().values():
            corpus.add(normalize_aggressive(learned_target))

        # c) Favoritos de usuario (programs.json)
        if PROGRAMS_FILE.exists():
            try:
                with open(PROGRAMS_FILE, "r", encoding="utf-8") as f:
                    favs = json.load(f)
                    if isinstance(favs, dict):
                        for k in favs.keys():
                            corpus.add(normalize_aggressive(k))
            except Exception:
                pass

        # d) Procesos del sistema en ejecución (psutil)
        try:
            for proc in psutil.process_iter(["name"]):
                try:
                    pname = proc.name()
                    if pname:
                        clean_pname = pname[:-4] if pname.lower().endswith(".exe") else pname
                        corpus.add(normalize_aggressive(clean_pname))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass

        # e) Aplicaciones indexadas en app_index.json
        try:
            from core.app_scanner import app_index_manager
            cached = app_index_manager.load_index()
            apps_dict = cached.get("apps", {})
            for app_name, app_info in apps_dict.items():
                corpus.add(normalize_aggressive(app_name))
                disp = app_info.get("display_name")
                if disp:
                    corpus.add(normalize_aggressive(disp))
        except Exception:
            pass

        # f) Términos de archivos y workspace
        if intent in ("search_file", "delete_file", "create_file", "create_folder"):
            for kw in COMMON_DOC_KEYWORDS:
                corpus.add(kw)
            try:
                ws_path_str = settings.get("WORKSPACE_PATH", "")
                ws = Path(ws_path_str) if ws_path_str else (Path.home() / "Documents")
                if ws.exists():
                    for item in ws.iterdir():
                        corpus.add(normalize_aggressive(item.name))
                        corpus.add(normalize_aggressive(item.stem))
            except Exception:
                pass

        corpus.discard("")
        return corpus

    def match_target(
        self,
        intent: str,
        target_raw: str,
        corpus: Optional[Set[str]] = None,
    ) -> List[Tuple[str, float]]:
        """
        Matchea el target y sus variantes de Capa 1 contra el corpus de targets.

        Returns:
            Lista de (candidato, similitud) ordenados de mayor a menor confianza.
        """
        norm_target = normalize_aggressive(target_raw)
        if not norm_target:
            return []

        # 1. Consulta directa a la memoria de typos aprendidos
        learned = self.memory.lookup(norm_target)
        if learned and learned.get("target"):
            return [(learned["target"], 1.0)]

        # 2. Generar variantes de Capa 1
        variants = generate_target_variants(target_raw)
        if corpus is None:
            corpus = self.build_target_corpus(intent)

        ask_threshold = settings.get_float("FUZZY_ASK_THRESHOLD", 0.60)
        candidates: list[Tuple[str, float]] = []

        for cand in corpus:
            best_s = 0.0
            for v in variants:
                if v == cand:
                    s = 1.0
                else:
                    s = difflib.SequenceMatcher(None, v, cand).ratio()
                if s > best_s:
                    best_s = s
            if best_s >= ask_threshold:
                candidates.append((cand, best_s))

        # Ordenar por puntaje descendente
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates

    def interpret_fuzzy(self, raw_text: str) -> Optional[InterpretationResult]:
        """
        Ejecuta CAPA 1 y CAPA 2:
        - Normalización agresiva
        - Detección difflib de verbo (cutoff 0.75)
        - Detección difflib de target con variantes
        - Evaluación de confianza y desambiguación

        Returns:
            InterpretationResult si resolvió en Capa 2, o None para pasar a Capa 3.
        """
        norm_text = normalize_aggressive(raw_text)
        if not norm_text:
            return None

        # Chequeo directo de write_in_app vía IntentRouter si corresponde
        from aura.core.intent_router import intent_router, is_valid_filename
        router_intent = intent_router.parse(raw_text)
        if router_intent and router_intent.nombre == "write_in_app":
            app = router_intent.target
            texto = router_intent.extra.get("texto", "")
            resolved = entity_resolver.resolve("write_in_app", app)
            resolved.extra["texto"] = texto
            resolved.args = [app, texto]
            return InterpretationResult(
                status="execute_direct",
                intent="write_in_app",
                target=app,
                raw_target=app,
                raw_text=raw_text,
                canon_verb="escribir en",
                display_message=f"Entendí: escribir en {app}",
                resolved_entity=resolved,
                confidence=1.0,
                layer=1,
            )

        if router_intent and router_intent.nombre == "save_app_doc":
            app = router_intent.target
            extra = router_intent.extra or {}
            resolved = entity_resolver.resolve(router_intent)
            resolved.extra.update(extra)
            display_name = app or "el documento"
            return InterpretationResult(
                status="execute_direct",
                intent="save_app_doc",
                target=app,
                raw_target=app,
                raw_text=raw_text,
                canon_verb="guardar",
                display_message=f"Entendí: guardar {display_name}",
                resolved_entity=resolved,
                confidence=1.0,
                layer=1,
                extra=extra,
            )

        if router_intent and router_intent.nombre == "queja_chiste":
            return InterpretationResult(
                status="execute_direct",
                intent="queja_chiste",
                target="",
                raw_target="",
                raw_text=raw_text,
                canon_verb="queja chiste",
                display_message="",
                confidence=1.0,
                layer=1,
            )

        if router_intent and router_intent.nombre == "pedir_chiste":
            estilo = router_intent.extra.get("estilo", "")
            tema = router_intent.extra.get("tema", "")
            return InterpretationResult(
                status="execute_direct",
                intent="pedir_chiste",
                target=estilo,
                raw_target=router_intent.target,
                raw_text=raw_text,
                canon_verb="chiste",
                display_message="",
                extra={"estilo": estilo, "tema": tema},
                confidence=1.0,
                layer=1,
            )

        if router_intent and router_intent.nombre == "roast":
            return InterpretationResult(
                status="execute_direct",
                intent="roast",
                target="",
                raw_target="",
                raw_text=raw_text,
                canon_verb="roast",
                display_message="",
                confidence=1.0,
                layer=1,
            )

        verb_match = self.match_verb(norm_text)
        if not verb_match:
            return None

        intent, canon_verb, target_remainder, verb_conf = verb_match
        target_remainder = target_remainder.strip()

        if intent == "queja_chiste":
            return InterpretationResult(
                status="execute_direct",
                intent="queja_chiste",
                target="",
                raw_target="",
                raw_text=raw_text,
                canon_verb="queja chiste",
                display_message="",
                confidence=verb_conf,
                layer=2,
            )

        if intent == "pedir_chiste":
            from aura.personality.jokes import resolve_joke_style
            estilo, tema = resolve_joke_style(user_text=raw_text, explicit_style=target_remainder)
            return InterpretationResult(
                status="execute_direct",
                intent="pedir_chiste",
                target=estilo,
                raw_target=target_remainder,
                raw_text=raw_text,
                canon_verb="chiste",
                display_message="",
                extra={"estilo": estilo, "tema": tema},
                confidence=verb_conf,
                layer=2,
            )

        if intent == "roast":
            return InterpretationResult(
                status="execute_direct",
                intent="roast",
                target="",
                raw_target="",
                raw_text=raw_text,
                canon_verb="roast",
                display_message="",
                confidence=verb_conf,
                layer=2,
            )

        if intent == "write_in_app":
            parts = target_remainder.split(maxsplit=1)
            app_cand = parts[0] if parts else "notepad"
            text_cand = parts[1] if len(parts) > 1 else ""
            resolved = entity_resolver.resolve("write_in_app", app_cand)
            resolved.extra["texto"] = text_cand
            resolved.args = [app_cand, text_cand]
            return InterpretationResult(
                status="execute_direct",
                intent="write_in_app",
                target=app_cand,
                raw_target=target_remainder,
                raw_text=raw_text,
                canon_verb="escribir en",
                display_message=f"Entendí: escribir en {app_cand}",
                resolved_entity=resolved,
                confidence=verb_conf,
                layer=2,
            )

        if intent == "save_app_doc":
            from aura.core.intent_router import intent_router
            intent_save = intent_router._match_save_app_doc(raw_text, raw_text)
            if intent_save:
                app = intent_save.target
                extra = intent_save.extra or {}
            else:
                app = target_remainder
                extra = {"app": app, "filename": "", "destination": ""}
            resolved = entity_resolver.resolve("save_app_doc", app)
            resolved.extra.update(extra)
            resolved.args = [app, extra.get("filename", ""), extra.get("destination", "")]
            display_name = app or "el documento"
            return InterpretationResult(
                status="execute_direct",
                intent="save_app_doc",
                target=app,
                raw_target=target_remainder,
                raw_text=raw_text,
                canon_verb="guardar",
                display_message=f"Entendí: guardar {display_name}",
                resolved_entity=resolved,
                confidence=verb_conf,
                layer=2,
                extra=extra,
            )

        if intent == "create_file":
            if not is_valid_filename(target_remainder):
                _logger.info(f"FuzzyInterpreter: target '{target_remainder}' descartado por sanity check de filename.")
                return None

        if not target_remainder:
            return None

        # Redirigir a open_url si el target luce como URL o dominio
        if intent == "open_app" and is_url_or_domain(target_remainder):
            resolved = entity_resolver.resolve("open_url", target_remainder)
            return InterpretationResult(
                status="execute_direct",
                intent="open_url",
                target=target_remainder,
                raw_target=target_remainder,
                raw_text=raw_text,
                canon_verb="abrir url",
                display_message=f"Entendí: abrir {target_remainder}",
                resolved_entity=resolved,
                confidence=verb_conf,
                layer=2,
            )

        corpus = self.build_target_corpus(intent)
        candidates = self.match_target(intent, target_remainder, corpus)

        fuzzy_threshold = settings.get_float("FUZZY_THRESHOLD", 0.85)
        ask_threshold = settings.get_float("FUZZY_ASK_THRESHOLD", 0.60)

        # Verificar si la aplicación requiere escaneo profundo en toda la PC (ej: "steam")
        tentative = entity_resolver.resolve(intent, target_remainder)
        if intent == "open_app" and tentative.extra.get("needs_deep_scan"):
            if not candidates or candidates[0][1] < fuzzy_threshold:
                return InterpretationResult(
                    status="needs_deep_scan",
                    intent=intent,
                    target=target_remainder,
                    raw_target=target_remainder,
                    raw_text=raw_text,
                    canon_verb=canon_verb,
                    display_message=f"🔍 Buscando '{target_remainder}' en toda la PC...",
                    resolved_entity=tentative,
                    confidence=verb_conf,
                    layer=2,
                )

        # Si no hay candidatos con puntaje >= ask_threshold:
        if not candidates:
            return None

        top_cand, top_score = candidates[0]
        # Ponderación combinada de confianza
        combined_conf = (verb_conf * 0.4) + (top_score * 0.6)

        second_score = candidates[1][1] if len(candidates) > 1 else 0.0
        score_diff = top_score - second_score

        # Resolver la entidad con el target corregido
        resolved_ent = entity_resolver.resolve(intent, top_cand)

        # Regla 1: Confianza >= FUZZY_THRESHOLD (0.85) con un solo candidato claro
        if top_score >= fuzzy_threshold and (len(candidates) == 1 or score_diff >= 0.08):
            return InterpretationResult(
                status="execute_direct",
                intent=intent,
                target=top_cand,
                raw_target=target_remainder,
                raw_text=raw_text,
                canon_verb=canon_verb,
                display_message=f"Entendí: {canon_verb} {top_cand}",
                resolved_entity=resolved_ent,
                confidence=combined_conf,
                layer=2,
            )

        # Regla 2: Confianza 0.60 - 0.85 con un solo candidato claro
        if ask_threshold <= top_score and (len(candidates) == 1 or score_diff >= 0.12):
            return InterpretationResult(
                status="execute_with_note",
                intent=intent,
                target=top_cand,
                raw_target=target_remainder,
                raw_text=raw_text,
                canon_verb=canon_verb,
                display_message=f"(Corregido: '{raw_text}' -> '{canon_verb} {top_cand}')",
                resolved_entity=resolved_ent,
                confidence=combined_conf,
                layer=2,
            )

        # Regla 3: Confianza 0.60 - 0.85 con varios candidatos cercanos
        if ask_threshold <= top_score:
            options = [c[0] for c in candidates[:4]]
            return InterpretationResult(
                status="ask_user",
                intent=intent,
                target=top_cand,
                raw_target=target_remainder,
                raw_text=raw_text,
                canon_verb=canon_verb,
                candidates=options,
                confidence=combined_conf,
                layer=2,
            )

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # CAPA 3: Intérprete IA Local (Ollama qwen2.5:3b)
    # ─────────────────────────────────────────────────────────────────────────

    def interpret_llm(self, raw_text: str, provider: Optional[Any] = None) -> Optional[InterpretationResult]:
        """
        CAPA 3: Intérprete IA local como último recurso antes del chat normal.
        Envía un system prompt estricto a Ollama pidiendo SOLO JSON.
        """
        if not settings.get_bool("USE_LLM_INTERPRETER", True):
            return None

        if not raw_text or not raw_text.strip():
            return None

        if provider is None:
            try:
                from ai.provider_factory import get_default_provider
                provider = get_default_provider()
            except Exception as e:
                _logger.warning(f"TypoInterpreter: no se pudo obtener proveedor IA: {e}")
                return None

        from aura.ai.prompt_assembler import assemble_prompt

        system_prompt = assemble_prompt(
            context="interprete",
            provider=provider.name if provider else None,
            model=getattr(provider, "model", None),
        )

        from ai.provider_interface import ChatMessage

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=raw_text),
        ]

        try:
            response = provider.chat(messages)
            content = (response.content or "").strip()
            _logger.debug(f"TypoInterpreter Capa 3 respuesta LLM: {content}")

            # Extraer bloque JSON con tolerancia a markdown fences y texto circundante
            json_text = ""
            fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if fence_match:
                json_text = fence_match.group(1).strip()
            else:
                first_brace = content.find("{")
                last_brace = content.rfind("}")
                if first_brace != -1 and last_brace > first_brace:
                    json_text = content[first_brace : last_brace + 1].strip()

            if not json_text:
                return None

            try:
                data = json.loads(json_text)
            except Exception as e:
                _logger.debug(f"TypoInterpreter Capa 3: error parseando JSON '{json_text}': {e}")
                return None


            # Si el modelo clasifica como conversación, pasar a conversacional
            tipo = str(data.get("tipo") or "").strip().lower()
            if tipo == "conversacion":
                _logger.info(f"TypoInterpreter Capa 3: clasificado como conversación (tipo='{tipo}').")
                return None

            intent = data.get("intent")
            if not intent or str(intent).strip().lower() in ("null", "none"):
                return None

            valid_intents = {
                "open_app", "close_app", "open_url", "create_folder",
                "create_file", "search_file", "delete_file", "write_in_app",
                "save_app_doc", "move_file", "rename_file", "run_automation",
                "pedir_chiste", "roast", "queja_chiste"
            }
            if intent not in valid_intents:
                return None

            # Descarte si confianza reportada es inferior a 0.60 (PASO 5 del Núcleo)
            raw_conf = data.get("confianza")
            conf_val = 0.88
            if raw_conf is not None:
                try:
                    conf_val = float(raw_conf)
                    if conf_val < 0.60:
                        _logger.info(f"TypoInterpreter Capa 3: descarte por confianza baja ({conf_val} < 0.60).")
                        return None
                except (ValueError, TypeError):
                    conf_val = 0.88

            norm_input = raw_text.lower()
            # Guard de no contaminación cruzada: insultos nunca a pedir_chiste, chistes nunca a roast
            if intent == "pedir_chiste" and any(k in norm_input for k in ("insult", "roast", "bardea", "palo", "bife", "mierda")):
                _logger.info("TypoInterpreter Capa 3: override preventivo pedir_chiste -> roast por presencia de términos de insulto.")
                intent = "roast"
            elif intent == "roast" and any(k in norm_input for k in ("chiste", "chistecito", "broma")):
                _logger.info("TypoInterpreter Capa 3: override preventivo roast -> pedir_chiste por presencia de términos de chiste.")
                intent = "pedir_chiste"

            if intent == "roast":
                return InterpretationResult(
                    status="execute_direct",
                    intent="roast",
                    target="",
                    raw_target="",
                    raw_text=raw_text,
                    canon_verb="roast",
                    display_message="",
                    confidence=0.90,
                    layer=3,
                )

            if intent == "queja_chiste":
                return InterpretationResult(
                    status="execute_direct",
                    intent="queja_chiste",
                    target="",
                    raw_target="",
                    raw_text=raw_text,
                    canon_verb="queja chiste",
                    display_message="",
                    confidence=0.90,
                    layer=3,
                )

            if intent == "pedir_chiste":
                estilo_val = str(data.get("estilo") or "").strip()
                tema_val = str(data.get("tema") or "").strip()
                from aura.personality.jokes import resolve_joke_style
                estilo_res, tema_res = resolve_joke_style(user_text=raw_text, explicit_style=estilo_val, explicit_tema=tema_val)
                return InterpretationResult(
                    status="execute_direct",
                    intent="pedir_chiste",
                    target=estilo_res,
                    raw_target=estilo_val,
                    raw_text=raw_text,
                    canon_verb="chiste",
                    display_message="",
                    extra={"estilo": estilo_res, "tema": tema_res},
                    confidence=0.90,
                    layer=3,
                )

            if intent == "write_in_app":
                app = str(data.get("app") or data.get("target") or "").strip().strip("'\"`")
                texto = str(data.get("texto") or "").strip()
                if not app:
                    return None
                resolved = entity_resolver.resolve("write_in_app", app)
                resolved.extra["texto"] = texto
                resolved.args = [app, texto]
                return InterpretationResult(
                    status="execute_direct",
                    intent="write_in_app",
                    target=app,
                    raw_target=app,
                    raw_text=raw_text,
                    canon_verb="escribir en",
                    display_message=f"Interpreté: escribir en {app}",
                    resolved_entity=resolved,
                    confidence=0.88,
                    layer=3,
                )

            if intent == "save_app_doc":
                app = str(data.get("app") or data.get("target") or "").strip().strip("'\"`")
                nombre = str(data.get("nombre") or data.get("filename") or "").strip()
                destino = str(data.get("destino") or data.get("destination") or "").strip()
                resolved = entity_resolver.resolve("save_app_doc", app)
                extra = {"app": app, "filename": nombre, "destination": destino}
                resolved.extra.update(extra)
                resolved.args = [app, nombre, destino]
                display_name = app or "el documento"
                return InterpretationResult(
                    status="execute_direct",
                    intent="save_app_doc",
                    target=app,
                    raw_target=app,
                    raw_text=raw_text,
                    canon_verb="guardar",
                    display_message=f"Interpreté: guardar {display_name}",
                    resolved_entity=resolved,
                    confidence=0.88,
                    layer=3,
                    extra=extra,
                )

            target = data.get("target")
            if not target or not isinstance(target, str):
                return None

            target_clean = target.strip().strip("'\"`")
            if not target_clean:
                return None

            if intent == "create_file":
                from aura.core.intent_router import is_valid_filename
                raw_norm = normalize_aggressive(raw_text)

                # Chequeo 1: ¿la frase original tiene indicios de escribir en una app?
                has_app_mention = any(a in raw_norm for a in ["notepad", "bloc", "wordpad", "code", "consola", "terminal"])
                has_write_mention = any(w in raw_norm for w in ["escribe", "escribi", "escribime", "redacta", "tipea", "pone", "manda", "anota", "dentro"])

                # Chequeo 2: ¿el target devuelto por el LLM fue traducido/inventado o no aparece en la frase?
                target_base = target_clean.rsplit(".", 1)[0].lower() if "." in target_clean else target_clean.lower()
                target_tokens = [t for t in re.findall(r"\w+", target_base) if len(t) >= 3]
                target_hallucinated = bool(target_tokens and not any(t in raw_norm for t in target_tokens))

                if (has_app_mention and has_write_mention) or target_hallucinated or not is_valid_filename(target_clean):
                    _logger.warning(
                        f"TypoInterpreter: LLM propuso create_file '{target_clean}' pero la frase tiene señales de write_in_app o target alucinado/traducido. Descartando create_file."
                    )
                    if has_app_mention or ("en" in raw_norm or "dentro" in raw_norm):
                        app_detected = "notepad"
                        for app_cand in ["notepad", "bloc", "wordpad", "code"]:
                            if app_cand in raw_norm:
                                app_detected = "notepad" if app_cand in ("notepad", "bloc") else app_cand
                                break
                        resolved = entity_resolver.resolve("write_in_app", app_detected)
                        resolved.extra["texto"] = ""
                        resolved.args = [app_detected, ""]
                        return InterpretationResult(
                            status="execute_direct",
                            intent="write_in_app",
                            target=app_detected,
                            raw_target=app_detected,
                            raw_text=raw_text,
                            canon_verb="escribir en",
                            display_message=f"Interpreté: escribir en {app_detected}",
                            resolved_entity=resolved,
                            confidence=0.85,
                            layer=3,
                        )
                    return None

            # Intentar resolver normal o fuzzy el target devuelto por el LLM
            resolved = entity_resolver.resolve(intent, target_clean)
            if not resolved.resolved:
                # Probar matching difflib para el target
                fuzzy_cands = self.match_target(intent, target_clean)
                if fuzzy_cands and fuzzy_cands[0][1] >= 0.70:
                    target_clean = fuzzy_cands[0][0]
                    resolved = entity_resolver.resolve(intent, target_clean)

            if resolved.resolved or (intent == "open_app" and resolved.extra.get("needs_deep_scan")):
                status = "needs_deep_scan" if resolved.extra.get("needs_deep_scan") else "execute_ai"
                return InterpretationResult(
                    status=status,
                    intent=intent,
                    target=target_clean,
                    raw_target=target_clean,
                    raw_text=raw_text,
                    canon_verb=intent,
                    display_message=f"Interpreté: {intent} {target_clean}",
                    resolved_entity=resolved,
                    confidence=0.85,
                    layer=3,
                )

        except Exception as e:
            _logger.warning(f"TypoInterpreter: error en Capa 3 LLM: {e}")

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Pipeline Completo de Interpretación
    # ─────────────────────────────────────────────────────────────────────────

    def interpret(self, raw_text: str, provider: Optional[Any] = None) -> Optional[InterpretationResult]:
        """
        Ejecuta las 3 capas de comprensión en orden:
          1. Capa 1 y Capa 2 (Normalización + Fuzzy difflib)
          2. Capa 3 (Intérprete IA con Ollama qwen2.5:3b)
          3. Si ninguna resuelve, retorna None para pasar al chat normal.
        """
        if not raw_text or not raw_text.strip():
            return None

        # 1. Intentar Capa 2 (con Capa 1 integrada)
        res_fuzzy = self.interpret_fuzzy(raw_text)
        if res_fuzzy is not None:
            _logger.info(
                f"TypoInterpreter: Capa 2 resuelta | raw='{raw_text}' | "
                f"intent='{res_fuzzy.intent}' | target='{res_fuzzy.target}' | "
                f"status='{res_fuzzy.status}' | conf={res_fuzzy.confidence:.2f}"
            )
            return res_fuzzy

        # 2. Intentar Capa 3 (Intérprete IA)
        res_llm = self.interpret_llm(raw_text, provider=provider)
        if res_llm is not None:
            _logger.info(
                f"TypoInterpreter: Capa 3 resuelta | raw='{raw_text}' | "
                f"intent='{res_llm.intent}' | target='{res_llm.target}' | "
                f"status='{res_llm.status}' | conf={res_llm.confidence:.2f}"
            )
            return res_llm

        _logger.debug(f"TypoInterpreter: Ninguna capa resolvió '{raw_text}' -> derivando a chat normal")
        return None


# Singleton global del intérprete
fuzzy_interpreter = FuzzyInterpreter()

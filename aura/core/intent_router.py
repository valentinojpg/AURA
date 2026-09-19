"""
AURA — IntentRouter: Enrutador de Intenciones en Lenguaje Natural (Español).

Analiza mensajes del usuario mediante normalización y expresiones regulares
en español (case-insensitive) para detectar intenciones de acción del sistema
(abrir apps, cerrar procesos, abrir URLs, manejo de archivos y carpetas).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Any

from utils.logger import get_logger

_logger = get_logger("aura.core.intent_router")


@dataclass
class Intent:
    """
    Representa una intención detectada a partir del texto del usuario.

    Attributes:
        nombre: Nombre de la intención (ej: 'open_app', 'close_app', 'write_in_app')
        target: Objetivo o entidad extraída (ej: 'notepad', 'chrome', 'pruebas')
        raw:    Texto original exacto proporcionado por el usuario
        extra:  Datos complementarios opcionales (ej: {'app': 'notepad', 'texto': 'hola'})
    """

    nombre: str
    target: str
    raw: str
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        """Alias para compatibilidad con código en inglés."""
        return self.nombre

    def __repr__(self) -> str:
        return f"Intent(nombre='{self.nombre}', target='{self.target}', raw='{self.raw}', extra={self.extra})"


_COMMAND_VERBS_FOR_FILENAME = {
    "escribe", "escribi", "escribime", "redacta", "pone", "tipea", "manda", "anota",
    "abre", "abrir", "cierra", "cerrar", "dentro", "borra", "borrar", "elimina",
    "eliminar", "busca", "buscar", "mover", "mueve", "crea", "crear", "hace", "hacer"
}


def is_valid_filename(target: str) -> bool:
    """
    Sanity check para nombres de archivo:
    - Rechaza si contiene verbos de comando (escribe, abre, dentro, etc.)
    - Rechaza si no tiene extensión y tiene más de 4 palabras
    - Rechaza si contiene caracteres no permitidos en Windows
    """
    if not target or not target.strip():
        return False
    t = target.strip()

    # Si contiene caracteres no permitidos en nombres de Windows (excepto / o \ si es ruta)
    invalid_chars = set('<>:"|?*')
    if any(c in invalid_chars for c in t):
        return False

    norm_words = [normalize(w).strip(".,:;?!\"'()") for w in t.split()]
    for w in norm_words:
        if w in _COMMAND_VERBS_FOR_FILENAME:
            return False

    has_ext = "." in t and len(t.rsplit(".", 1)[-1].strip()) >= 1
    has_slash = "/" in t or "\\" in t

    # Si tiene más de 4 palabras y no tiene extensión ni ruta
    if len(norm_words) > 4 and not has_ext and not has_slash:
        return False

    return True


def normalize(text: str) -> str:
    """
    Normaliza el texto a minúsculas y elimina tildes/acentos de vocales.

    Args:
        text: Cadena de texto a normalizar.

    Returns:
        Texto en minúsculas sin tildes ni caracteres diacríticos comunes.
    """
    if not text:
        return ""
    text = text.lower().strip()
    tildes = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "à": "a",
        "è": "e",
        "ì": "i",
        "ò": "o",
        "ù": "u",
        "ü": "u",
        "â": "a",
        "ê": "e",
        "î": "i",
        "ô": "o",
        "û": "u",
    }
    for k, v in tildes.items():
        text = text.replace(k, v)
    return text


def _clean_target(target: str) -> str:
    """Limpia puntuación y artículos sobrantes del target extraído."""
    if not target:
        return ""
    target = target.strip().strip("'\"`´")
    # Quitar signos de puntuación finales comunes
    target = target.rstrip(".?!,;:").strip()

    # Quitar artículos y partículas iniciales como 'el ', 'la ', 'los ', 'las ', 'un ', 'una '
    articulos = ["el ", "la ", "los ", "las ", "un ", "una ", "de "]
    target_lower = target.lower()
    for art in articulos:
        if target_lower.startswith(art):
            target = target[len(art) :].strip()
            break
    return target


class IntentRouter:
    """
    Router de intenciones en lenguaje natural para AURA.

    Detecta las siguientes 9 intenciones de acción:
      - open_url: Abrir páginas web o dominios
      - create_folder: Crear directorios
      - create_file: Crear archivos
      - rename_file: Renombrar archivos o carpetas
      - move_file: Mover archivos o carpetas
      - delete_file: Eliminar archivos o carpetas
      - search_file: Buscar archivos por nombre o patrón
      - close_app: Cerrar procesos o aplicaciones
      - open_app: Abrir programas o herramientas del sistema
    """

    # Prefijo opcional de cortesía / pregunta
    _POLITE_PREFIX = r"(?:por favor\s+|podes\s+|puedes\s+|podrias\s+)?"

    # Expresión para URLs y dominios conocidos
    _DOMAIN_REGEX = (
        r"(?:https?://\S+|www\.\S+|[\w-]+\.(?:com|org|net|io|edu|gov|es|ar|co|mx|cl|dev|ai|app|info|biz|xyz)(?:/\S*)?)"
    )
    # Alias de sitios web populares (Fase 71)
    _SITE_ALIASES_REGEX = (
        r"(?:youtube\s+music|yt\s+music|youtube|google|github|wikipedia|gmail|calendar|drive|"
        r"whatsapp\s+web|whatsapp|chatgpt)"
    )

    def __init__(self) -> None:
        self._init_rules()

    def _init_rules(self) -> None:
        """Inicializa las reglas regex en orden de prioridad."""
        # 1. open_url: apertura explícita de URL, navegación o alias web
        url_verb = r"(?:abre|abrir|abra|abreme|abri|entra\s+a|entra\s+en|entrar\s+a|navega\s+a|navegar\s+a|visita|visitar)"
        self._re_open_url = re.compile(
            rf"^{self._POLITE_PREFIX}{url_verb}\s+(?:la\s+)?(?:pagina\s+|web\s+|sitio\s+)?({self._DOMAIN_REGEX}|{self._SITE_ALIASES_REGEX})$",
            re.IGNORECASE,
        )
        self._re_direct_url = re.compile(
            r"^(https?://\S+|www\.\S+)$",
            re.IGNORECASE,
        )

        # 1b. media_play: reproducción o búsqueda de música / video (Fase 71)
        media_verbs = r"(?:pon|pone|poné|poner|poneme|reproduce|reproducir|reproducime|reproducí|escuchar|escucha|reproduceme|toca|tocar|tocame)"
        media_service_suffix = r"(?:\s+en\s+(youtube\s+music|yt\s+music|youtube|spotify))?"
        self._re_media_play = re.compile(
            rf"^{self._POLITE_PREFIX}{media_verbs}\s+(?:la\s+cancion\s+|el\s+tema\s+|la\s+pista\s+|el\s+video\s+|musica\s+de\s+|música\s+de\s+|a\s+)?(.+?){media_service_suffix}$",
            re.IGNORECASE,
        )

        # 2. create_folder: crear carpeta/directorio
        folder_verbs = r"(?:crea|crear|creame|hace|hacer|nueva)"
        self._re_create_folder = re.compile(
            rf"^{self._POLITE_PREFIX}{folder_verbs}\s+(?:una\s+)?(?:carpeta|directorio)(?:\s+(?:llamada|llamado|de\s+nombre))?\s+(.+)$",
            re.IGNORECASE,
        )
        self._re_create_folder_alt = re.compile(
            rf"^{self._POLITE_PREFIX}(?:carpeta|directorio)\s+nueva\s+(.+)$",
            re.IGNORECASE,
        )

        # 3. create_file: crear archivo/fichero
        file_verbs = r"(?:crea|crear|creame|nuevo)"
        self._re_create_file = re.compile(
            rf"^{self._POLITE_PREFIX}{file_verbs}\s+(?:un\s+)?(?:archivo|fichero|documento)(?:\s+(?:llamado|llamada|de\s+nombre))?\s+(.+)$",
            re.IGNORECASE,
        )
        self._re_create_file_alt = re.compile(
            rf"^{self._POLITE_PREFIX}(?:archivo|fichero)\s+nuevo\s+(.+)$",
            re.IGNORECASE,
        )

        # 4. rename_file: renombrar archivo o carpeta
        rename_verbs = r"(?:renombra|renombrar|renombre|renombrame|cambia\s+el\s+nombre\s+de|cambiar\s+el\s+nombre\s+de)"
        self._re_rename_file = re.compile(
            rf"^{self._POLITE_PREFIX}{rename_verbs}\s+(?:el\s+|un\s+)?(?:archivo|fichero|carpeta)?\s*(.+?)\s+(?:a|como|por)\s+(.+)$",
            re.IGNORECASE,
        )

        # 5. move_file: mover archivo o carpeta
        move_verbs = r"(?:mueve|mover|mueva|move|traslada|trasladar|trasladame)"
        self._re_move_file = re.compile(
            rf"^{self._POLITE_PREFIX}{move_verbs}\s+(?:el\s+|un\s+)?(?:archivo|fichero|carpeta)?\s*(.+?)\s+(?:a|hacia|en)\s+(.+)$",
            re.IGNORECASE,
        )

        # 6. delete_file: eliminar / borrar archivo o carpeta
        delete_verbs = r"(?:elimina|eliminar|elimine|eliminame|borra|borrar|borre|borrame|remueve|remover)"
        self._re_delete_file = re.compile(
            rf"^{self._POLITE_PREFIX}{delete_verbs}\s+(?:el\s+|la\s+|un\s+|una\s+)?(?:archivo|fichero|carpeta|directorio)\s+(.+)$",
            re.IGNORECASE,
        )
        self._re_delete_file_alt = re.compile(
            rf"^{self._POLITE_PREFIX}{delete_verbs}\s+([\w\*\?.-]+\.(?:[a-zA-Z0-9]+))(?:\s+--ahora)?$",
            re.IGNORECASE,
        )

        # 7. search_file: buscar archivos
        search_verbs = r"(?:busca|buscar|busque|buscame|encuentra|encontrar|localiza|localizar)"
        self._re_search_file = re.compile(
            rf"^{self._POLITE_PREFIX}{search_verbs}\s+(?:el\s+|un\s+)?(?:archivo|fichero|documento|carpeta)\s+(.+)$",
            re.IGNORECASE,
        )
        self._re_search_file_ext = re.compile(
            rf"^{self._POLITE_PREFIX}{search_verbs}\s+([\w\*\?.-]+\.(?:py|txt|json|pdf|docx|xlsx|csv|log|md|png|jpg|exe|zip|rar|html|css|js|ts|yaml|yml)(?:\s+en\s+.+)?)$",
            re.IGNORECASE,
        )
        self._re_search_file_wildcard = re.compile(
            rf"^{self._POLITE_PREFIX}{search_verbs}\s+(\*[\w.-]*(?:\s+en\s+.+)?)$",
            re.IGNORECASE,
        )

        # 8. close_app: cerrar proceso o app
        close_verbs = r"(?:cierra|cerrar|cierre|cierrame|cerra|mata|matar|finaliza|finalizar|termina|terminar)"
        self._re_close_app = re.compile(
            rf"^{self._POLITE_PREFIX}{close_verbs}\s+(?:la\s+app\s+|el\s+programa\s+|el\s+proceso\s+|la\s+aplicacion\s+)?(.+)$",
            re.IGNORECASE,
        )

        # 9. open_app: abrir app o programa
        open_verbs = r"(?:abre|abrir|abra|abreme|abri|ejecuta|ejecutar|ejecute|inicia|iniciar|inicie|lanza|lanzar|lance)"
        self._re_open_app = re.compile(
            rf"^{self._POLITE_PREFIX}{open_verbs}\s+(?:la\s+app\s+|el\s+programa\s+|la\s+aplicacion\s+)?(.+)$",
            re.IGNORECASE,
        )

        # 10. roast: insultame, roasteame, tirame un palo, insultame fuerte, etc.
        roast_verbs = (
            r"(?:"
            r"insultame|insúltame|insultar|insultamee|insultanos|insulta"
            r"|roasteame|roastéame|roastear|roasteamee|roast"
            r"|tirame\s+un\s+palo|tírame\s+un\s+palo|tirame\s+un\s+bife|tirame\s+un\s+insulto"
            r"|dame\s+un\s+roast|dame\s+un\s+insulto|dame\s+con\s+un\s+cano|dame\s+con\s+un\s+tubo"
            r"|haceme\s+un\s+roast|hace\s+un\s+roast|haceme\s+mierda|haceme\s+bosta|haceme\s+pedazos"
            r"|bardeame|bardéame|bardear|bardea"
            r"|quiero\s+que\s+me\s+insultes"
            r")"
        )
        roast_modifiers = (
            r"(?:"
            r"\s+(?:fuerte|mas\s+fuerte|muy\s+fuerte|con\s+todo|posta|bien|de\s+verdad|en\s+serio"
            r"|sin\s+piedad|a\s+fondo|pesado|duro|mas|un\s+poco|a\s+mi|por\s+favor|dale|ya|ahora)"
            r")*"
        )
        self._re_roast = re.compile(
            rf"^{self._POLITE_PREFIX}{roast_verbs}{roast_modifiers}$",
            re.IGNORECASE,
        )

        # 11. write_in_app: escribir dentro de una aplicación
        write_verbs = r"(?:escribi|escribe|escribir|escribime|redacta|redactar|redactame|pone|poné|poner|poneme|tipea|tipear|tipeame|manda|mandá|mandar|mandame|anota|anotar|anotame)"
        prep = r"(?:en|dentro\s+de)"

        # Patrón A: (en|dentro de) <app> <verbo> [que/:]? <texto>
        # Ej: "en notepad escribime un comentario", "dentro de notepad escribe algo"
        self._re_write_in_app_A = re.compile(
            rf"^{self._POLITE_PREFIX}{prep}\s+(.+?)\s+{write_verbs}(?:\s*:\s*|\s+que\s+|\s+)(.+)$",
            re.IGNORECASE,
        )
        self._re_write_in_app_A_notext = re.compile(
            rf"^{self._POLITE_PREFIX}{prep}\s+(.+?)\s+{write_verbs}$",
            re.IGNORECASE,
        )

        # Patrón B: <verbo> (en|dentro de) <app> <texto>
        # Ej: "escribí en notepad hola mundo", "escribí en bloc de notas hola mundo"
        self._re_write_in_app_B = re.compile(
            rf"^{self._POLITE_PREFIX}{write_verbs}\s+{prep}\s+(\S+(?:\s+de\s+\S+)?)\s+(.+)$",
            re.IGNORECASE,
        )
        self._re_write_in_app_B_notext = re.compile(
            rf"^{self._POLITE_PREFIX}{write_verbs}\s+{prep}\s+(\S+(?:\s+de\s+\S+)?)$",
            re.IGNORECASE,
        )

        # Patrón C: <verbo> <texto> (en|dentro de) <app>
        # Ej: "escribe hola mundo en notepad"
        self._re_write_in_app_C = re.compile(
            rf"^{self._POLITE_PREFIX}{write_verbs}\s+(.+?)\s+{prep}\s+(\S+(?:\s+de\s+\S+)?)$",
            re.IGNORECASE,
        )

        # 12. queja_chiste: reclamo o queja ante chiste malo o reclamo tras roast
        complaint_patterns = (
            r"(?:pero\s+|che\s+|ey\s+)?"
            r"(?:"
            r"(?:eso|esto)\s+no\s+(?:es|era|fue)\s+(?:un\s+)?chiste"
            r"|no\s+(?:es|era|fue)\s+(?:un\s+)?chiste"
            r"|(?:pero\s+)?me\s+estas\s+contando\s+datos(?:\s*,?\s*no\s+chistes?)?"
            r"|no\s+me\s+hiciste\s+reir"
            r"|(?:que\s+)?mal\s+chiste"
            r"|(?:eso|esto)\s+no\s+es\s+gracioso"
            r"|no\s+es\s+gracioso"
            r"|te\s+pedi\s+un\s+chiste"
            r"|(?:eso|esto)\s+es\s+un\s+dato"
            r"|eso\s+no\s+da\s+risa"
            r"|no\s+dio\s+risa"
            r"|te\s+pedi\s+que\s+me\s+insultaras"
            r"|te\s+pedi\s+un\s+insulto"
            r"|te\s+pedi\s+un\s+roast"
            r"|(?:eso|esto)\s+no\s+(?:es|era|fue)\s+(?:un\s+)?insulto"
            r"|no\s+(?:me\s+)?insultaste"
            r"|(?:eso|esto)\s+no\s+(?:es|era|fue)\s+(?:un\s+)?roast"
            r"|eso\s+no\s+me\s+dolio"
            r"|eso\s+fue\s+(?:re\s+|muy\s+)?suave"
            r"|insultame\s+en\s+serio"
            r"|insultame\s+de\s+verdad"
            r")"
        )
        self._re_queja_chiste = re.compile(
            rf"^{self._POLITE_PREFIX}{complaint_patterns}(?:\s+loco|\s+che|\s+boludo)?$",
            re.IGNORECASE,
        )

        # 13. pedir_chiste: solicitud de chiste o humor estructurado
        joke_verbs = r"(?:(?:me\s+)?(?:contame|conta|contate|contar|contarme|contas|tira|tirame|tirate|tirar|tirarte|decime|deci|decir|decirme|haceme|hacer|hacerme|dame|dar|darme))"
        joke_nouns = r"(?:chiste|chistes|chistecito)"
        self._re_pedir_chiste_direct = re.compile(
            rf"^{self._POLITE_PREFIX}(?:{joke_verbs}\s+)?(?:un\s+|el\s+|otro\s+)?{joke_nouns}(?:\s+(?:de|sobre)\s+(.+))?$",
            re.IGNORECASE,
        )
        self._re_pedir_chiste_type = re.compile(
            rf"^{self._POLITE_PREFIX}(?:{joke_verbs}\s+)?(?:un\s+|el\s+|otro\s+)?{joke_nouns}\s+([a-zA-Záéíóúñ]+)$",
            re.IGNORECASE,
        )
        self._re_pedir_chiste_alt = re.compile(
            rf"^{self._POLITE_PREFIX}(?:humor\s+negro|un\s+poco\s+de\s+humor\s+negro|algo\s+de\s+humor\s+negro|haceme\s+reir|contame\s+algo\s+gracioso|conta\s+algo\s+gracioso|algo\s+oscuro\s+y\s+gracioso|algo\s+gracioso\s+y\s+oscuro|joke|tell\s+me\s+a\s+joke|otro\s+chiste|contate\s+otro|tirate\s+otro)$",
            re.IGNORECASE,
        )

    def _match_save_app_doc(self, norm: str, raw: str) -> Optional[Intent]:
        """
        Detecta la intención save_app_doc para guardar el contenido de una aplicación abierta.
        Soporta:
          - Verbos: guarda, guardar, guardame, salva, salvar, etc.
          - App: el notepad, ese notepad, el bloc de notas, lo que escribiste, la ventana, etc.
          - Opcional 'como <nombre>' o 'con nombre <nombre>'
          - Opcional 'en <destino>' o 'dentro de <destino>'
        """
        save_verbs = r"(?:guarda|guardar|guardame|guardate|guardalo|guardala|salva|salvar|salvame|salvate|salvalo|salvala)"

        prefix_dest_re = re.compile(
            rf"^{self._POLITE_PREFIX}(?:en|dentro\s+de)\s+(.+?)\s+{save_verbs}\s+(.+)$",
            re.IGNORECASE,
        )
        standard_re = re.compile(
            rf"^{self._POLITE_PREFIX}{save_verbs}\s+(.+)$",
            re.IGNORECASE,
        )

        dest = ""
        filename = ""
        remainder = ""

        m_pref = prefix_dest_re.match(norm)
        if m_pref:
            dest = m_pref.group(1).strip()
            remainder = m_pref.group(2).strip()
        else:
            m_std = standard_re.match(norm)
            if not m_std:
                return None
            remainder = m_std.group(1).strip()

        # Extraer 'como <nombre>' o 'con nombre <nombre>'
        como_re = re.compile(r"(?:\s+como|\s+con\s+nombre|\s+de\s+nombre)\s+([a-zA-Z0-9_.-]+)", re.IGNORECASE)
        m_como = como_re.search(remainder)
        if m_como:
            filename = m_como.group(1).strip()
            remainder = remainder[:m_como.start()] + remainder[m_como.end():]
            remainder = remainder.strip()

        # Extraer 'en <destino>' si no se extrajo prefijo
        if not dest:
            dest_re = re.compile(r"(?:\s+en|\s+dentro\s+de|\s+hacia)\s+(.+)$", re.IGNORECASE)
            m_dest = dest_re.search(remainder)
            if m_dest:
                dest = m_dest.group(1).strip()
                remainder = remainder[:m_dest.start()].strip()

        # Si había 'como <nombre>' dentro del bloque de destino
        if not filename and dest:
            m_como_post = como_re.search(dest)
            if m_como_post:
                filename = m_como_post.group(1).strip()
                dest = dest[:m_como_post.start()].strip()

        app_ref = remainder.strip()
        clean_app = _clean_target(app_ref)

        known_keywords = {
            "notepad", "bloc de notas", "bloc", "ventana", "la ventana",
            "esta ventana", "lo que escribiste", "lo escrito", "lo que escribi",
            "documento", "archivo", "ese notepad", "este notepad", "el notepad",
            "el bloc de notas", "el bloc",
        }

        from aura.core.entity_resolver import BUILTIN_ALIASES

        is_valid_app = (
            clean_app in known_keywords
            or clean_app in BUILTIN_ALIASES
            or app_ref in known_keywords
            or any(clean_app.startswith(k) for k in ("notepad", "bloc", "ventana", "lo que"))
        )

        if not is_valid_app:
            return None

        target_name = clean_app
        if any(w in clean_app for w in ("lo que", "ventana", "documento", "archivo")):
            target_name = "notepad"

        return Intent(
            nombre="save_app_doc",
            target=target_name,
            raw=raw,
            extra={
                "app": clean_app,
                "filename": filename,
                "nombre": filename,
                "destination": dest,
                "destino": dest,
            },
        )

    def parse(self, text: str) -> Optional[Intent]:
        """
        Analiza el texto y retorna el Intent detectado o None si no corresponde a una acción.

        Args:
            text: Mensaje escrito o transcrito por voz.

        Returns:
            Intent(nombre, target, raw) si se detectó una intención, o None si debe ir al LLM.
        """
        if not text or not text.strip():
            return None

        raw = text.strip()
        # Quitar signos iniciales de interrogación o exclamación
        clean_text = raw.lstrip("¿¡").rstrip("?!.,;").strip()
        norm = normalize(clean_text)

        if not norm:
            return None

        # 0. write_in_app (alta prioridad para no confundir con creación de archivos)
        m = (
            self._re_write_in_app_A.match(norm)
            or self._re_write_in_app_B.match(norm)
            or self._re_write_in_app_C.match(norm)
        )
        if m:
            if m.re == self._re_write_in_app_C:
                app = _clean_target(m.group(2))
                text_part = m.group(1).strip()
            else:
                app = _clean_target(m.group(1))
                text_part = m.group(2).strip()
            return Intent(nombre="write_in_app", target=app, raw=raw, extra={"app": app, "texto": text_part})

        m_notext = self._re_write_in_app_A_notext.match(norm) or self._re_write_in_app_B_notext.match(norm)
        if m_notext:
            app = _clean_target(m_notext.group(1))
            return Intent(nombre="write_in_app", target=app, raw=raw, extra={"app": app, "texto": ""})

        # save_app_doc: guardar contenido de una app/ventana abierta (Fase 63 / 68)
        intent_save = self._match_save_app_doc(norm, raw)
        if intent_save is not None:
            return intent_save

        # queja_chiste (prioridad antes de pedir_chiste para quejas como "eso no es un chiste" o "te pedí un chiste")
        m_queja = self._re_queja_chiste.match(norm)
        if m_queja:
            return Intent(nombre="queja_chiste", target="", raw=raw, extra={})

        # roast: insultame, roasteame, tirame un palo, insultame fuerte, etc.
        m_roast = self._re_roast.match(norm)
        if m_roast:
            return Intent(nombre="roast", target="", raw=raw)

        # pedir_chiste (solicitud de humor estructurado)
        m_joke = (
            self._re_pedir_chiste_direct.match(norm)
            or self._re_pedir_chiste_type.match(norm)
            or self._re_pedir_chiste_alt.match(norm)
        )
        if m_joke:
            target_str = ""
            if m_joke.lastindex and m_joke.lastindex >= 1:
                target_str = m_joke.group(1) or ""
            target_str = _clean_target(target_str)
            from aura.personality.jokes import resolve_joke_style
            estilo, tema = resolve_joke_style(user_text=norm, explicit_style=target_str)
            return Intent(
                nombre="pedir_chiste",
                target=estilo or target_str,
                raw=raw,
                extra={"estilo": estilo, "tema": tema},
            )

        # 0b. media_play: reproducción o búsqueda multimedia (Fase 71)
        m_media = self._re_media_play.match(norm)
        if m_media:
            query = _clean_target(m_media.group(1))
            service = (m_media.group(2) or "").strip()
            if query:
                from skills.builtin.media_play_skill import normalize_service_name
                norm_service = normalize_service_name(service) if service else ""
                return Intent(
                    nombre="media_play",
                    target=query,
                    raw=raw,
                    extra={"query": query, "service": norm_service},
                )

        # 1. open_url (prioridad antes de open_app si coincide patrón de URL)
        m = self._re_open_url.match(norm) or self._re_direct_url.match(norm)
        if m:
            target = _clean_target(m.group(1))
            return Intent(nombre="open_url", target=target, raw=raw)

        # 2. create_folder
        m = self._re_create_folder.match(norm) or self._re_create_folder_alt.match(norm)
        if m:
            target = _clean_target(m.group(1))
            if is_valid_filename(target):
                return Intent(nombre="create_folder", target=target, raw=raw)
            else:
                _logger.info(f"IntentRouter: carpeta '{target}' descartada por sanity check.")

        # 3. create_file
        m = self._re_create_file.match(norm) or self._re_create_file_alt.match(norm)
        if m:
            target = _clean_target(m.group(1))
            if is_valid_filename(target):
                return Intent(nombre="create_file", target=target, raw=raw)
            else:
                _logger.info(f"IntentRouter: target '{target}' descartado por sanity check de filename.")

        # 4. rename_file
        m = self._re_rename_file.match(norm)
        if m:
            orig = _clean_target(m.group(1))
            dest = _clean_target(m.group(2))
            return Intent(nombre="rename_file", target=f"{orig} a {dest}", raw=raw)

        # 5. move_file
        m = self._re_move_file.match(norm)
        if m:
            orig = _clean_target(m.group(1))
            dest = _clean_target(m.group(2))
            return Intent(nombre="move_file", target=f"{orig} a {dest}", raw=raw)

        # 6. delete_file
        m = self._re_delete_file.match(norm) or self._re_delete_file_alt.match(norm)
        if m:
            target = _clean_target(m.group(1))
            return Intent(nombre="delete_file", target=target, raw=raw)

        # 7. search_file
        m = (
            self._re_search_file.match(norm)
            or self._re_search_file_ext.match(norm)
            or self._re_search_file_wildcard.match(norm)
        )
        if m:
            target = _clean_target(m.group(1))
            return Intent(nombre="search_file", target=target, raw=raw)

        # 8. close_app
        m = self._re_close_app.match(norm)
        if m:
            target = _clean_target(m.group(1))
            return Intent(nombre="close_app", target=target, raw=raw)

        # 9. open_app
        m = self._re_open_app.match(norm)
        if m:
            target = _clean_target(m.group(1))
            return Intent(nombre="open_app", target=target, raw=raw)

        return None


# Singleton global
intent_router = IntentRouter()


def parse(text: str) -> Optional[Intent]:
    """Función de conveniencia para parsear texto con el IntentRouter singleton."""
    return intent_router.parse(text)

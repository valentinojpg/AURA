"""
AURA — WebSkill: Skill de acceso web (Fase 18)

Permite abrir URLs, buscar en el navegador y gestionar favoritos web
directamente desde el chat de AURA.

Comandos disponibles:
  abrir-url <url>                      → Abre la URL en el navegador por defecto
  buscar-web <términos>                → Busca en Google (o motor configurado)
  favoritos-web                        → Lista los favoritos web guardados
  agregar-favorito <nombre> <url>      → Guarda un favorito web
  quitar-favorito <nombre>             → Elimina un favorito web guardado

Motores de búsqueda disponibles:
  google    → https://www.google.com/search?q=
  bing      → https://www.bing.com/search?q=
  duckduckgo → https://duckduckgo.com/?q=
  youtube   → https://www.youtube.com/results?search_query=
  github    → https://github.com/search?q=

Persistencia:
  Los favoritos del usuario se guardan en data/web_favorites.json.

Seguridad:
  - Solo se abren URLs con esquemas permitidos (http/https/ftp).
  - Se valida la URL antes de abrirla.
  - Todas las aperturas se registran en el log.
  - No se ejecutan JavaScript URIs ni esquemas arbitrarios.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import webbrowser

from pathlib import Path
from typing import Any

from skills.skill_base import (
    BaseSkill,
    SkillMeta,
    SkillResult,
    CATEGORY_WEB,
)
from utils.logger import get_logger

_logger = get_logger("aura.skills.web")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Esquemas de URL permitidos (seguridad)
_ALLOWED_SCHEMES = {"http", "https", "ftp"}

# Motores de búsqueda disponibles
_SEARCH_ENGINES: dict[str, str] = {
    "google":     "https://www.google.com/search?q=",
    "bing":       "https://www.bing.com/search?q=",
    "duckduckgo": "https://duckduckgo.com/?q=",
    "ddg":        "https://duckduckgo.com/?q=",
    "youtube":    "https://www.youtube.com/results?search_query=",
    "yt":         "https://www.youtube.com/results?search_query=",
    "github":     "https://github.com/search?q=",
    "gh":         "https://github.com/search?q=",
}

# Motor de búsqueda por defecto
_DEFAULT_ENGINE = "google"

# Ruta de persistencia de favoritos
_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_FAVORITES_FILE = _DATA_DIR / "web_favorites.json"

# Favoritos web predefinidos (builtin)
_BUILTIN_FAVORITES: dict[str, str] = {
    "google":        "https://www.google.com",
    "youtube":       "https://www.youtube.com",
    "youtube music": "https://music.youtube.com",
    "yt music":      "https://music.youtube.com",
    "github":        "https://github.com",
    "wikipedia":     "https://es.wikipedia.org",
    "gmail":         "https://mail.google.com",
    "calendar":      "https://calendar.google.com",
    "drive":         "https://drive.google.com",
    "whatsapp web":  "https://web.whatsapp.com",
    "whatsapp":      "https://web.whatsapp.com",
    "chatgpt":       "https://chatgpt.com",
}


# ---------------------------------------------------------------------------
# Metadatos de la skill
# ---------------------------------------------------------------------------

_META = SkillMeta(
    name="web_skill",
    version="1.0.0",
    display_name="Web",
    description=(
        "Acceso web desde el chat: abrir URLs, buscar en Google/Bing/YouTube, "
        "y gestionar favoritos web personalizados."
    ),
    author="AURA",
    category=CATEGORY_WEB,
    commands=[
        "abrir-url",
        "buscar-web",
        "favoritos-web",
        "agregar-favorito",
        "quitar-favorito",
    ],
    builtin=True,
    enabled_by_default=True,
)


# ---------------------------------------------------------------------------
# Implementación
# ---------------------------------------------------------------------------

class WebSkill(BaseSkill):
    """
    Skill de acceso web para AURA.

    Permite abrir URLs en el navegador por defecto, buscar con distintos
    motores, y gestionar una lista de favoritos web personalizados.
    """

    META = _META

    # ── Ciclo de vida ──────────────────────────────────────────────────────

    def setup(self) -> None:
        """Carga los favoritos del usuario desde disco."""
        super().setup()
        self._user_favorites: dict[str, str] = {}
        self._load_favorites()
        _logger.debug(
            "WebSkill inicializada con %d favoritos del usuario.",
            len(self._user_favorites),
        )

    def teardown(self) -> None:
        """Persiste los favoritos antes de cerrar."""
        self._save_favorites()
        super().teardown()

    # ── Ejecución ──────────────────────────────────────────────────────────

    def execute(self, command: str, args: list[str]) -> SkillResult:
        """Despacha el comando al método correspondiente."""
        cmd = command.lower().strip()

        if cmd == "abrir-url":
            return self._cmd_abrir_url(args)
        if cmd == "buscar-web":
            return self._cmd_buscar_web(args)
        if cmd == "favoritos-web":
            return self._cmd_listar_favoritos(args)
        if cmd == "agregar-favorito":
            return self._cmd_agregar_favorito(args)
        if cmd == "quitar-favorito":
            return self._cmd_quitar_favorito(args)

        return SkillResult(
            success=False,
            error=f"Comando desconocido: '{command}'.",
        )

    # ── Comandos ───────────────────────────────────────────────────────────

    def _cmd_abrir_url(self, args: list[str]) -> SkillResult:
        """
        abrir-url <url>

        Abre la URL dada en el navegador por defecto del sistema.
        Acepta URLs con o sin esquema (agrega https:// si falta).
        También puede abrir un favorito por nombre.
        """
        if not args:
            return SkillResult(
                success=False,
                error=(
                    "Uso: abrir-url <url>\n"
                    "Ejemplo: abrir-url https://www.google.com\n"
                    "         abrir-url github\n"
                    "         abrir-url www.python.org\n"
                    "Usa 'favoritos-web' para ver tus favoritos guardados."
                ),
            )

        entrada = " ".join(args).strip()

        # Intentar resolver como favorito primero
        url_favorita = self._resolver_favorito(entrada.lower())
        if url_favorita:
            return self._abrir_en_navegador(entrada.lower(), url_favorita)

        # Normalizar URL: agregar https:// si no tiene esquema
        url = self._normalizar_url(entrada)

        # Validar esquema
        error_esquema = self._validar_esquema(url)
        if error_esquema:
            return SkillResult(success=False, error=error_esquema)

        return self._abrir_en_navegador(entrada, url)

    def _cmd_buscar_web(self, args: list[str]) -> SkillResult:
        """
        buscar-web <términos> [--motor <motor>]

        Busca los términos en el motor configurado (por defecto: Google).
        Motores disponibles: google, bing, duckduckgo, youtube, github.
        """
        if not args:
            motores = ", ".join(sorted(set(_SEARCH_ENGINES.keys())))
            return SkillResult(
                success=False,
                error=(
                    "Uso: buscar-web <términos> [--motor <motor>]\n"
                    "Ejemplo: buscar-web Python tutorial\n"
                    "         buscar-web AURA AI --motor bing\n"
                    f"Motores disponibles: {motores}"
                ),
            )

        # Extraer flag --motor si está presente
        motor = _DEFAULT_ENGINE
        terminos_args = list(args)

        if "--motor" in terminos_args:
            idx = terminos_args.index("--motor")
            if idx + 1 < len(terminos_args):
                motor_candidato = terminos_args[idx + 1].lower()
                if motor_candidato in _SEARCH_ENGINES:
                    motor = motor_candidato
                    # Remover --motor y su valor de los términos
                    terminos_args = terminos_args[:idx] + terminos_args[idx + 2:]
                else:
                    motores_validos = ", ".join(sorted(set(_SEARCH_ENGINES.keys())))
                    return SkillResult(
                        success=False,
                        error=(
                            f"Motor '{motor_candidato}' no reconocido.\n"
                            f"Motores disponibles: {motores_validos}"
                        ),
                    )
            else:
                return SkillResult(
                    success=False,
                    error="Falta el nombre del motor después de '--motor'.",
                )

        terminos = " ".join(terminos_args).strip()
        if not terminos:
            return SkillResult(
                success=False,
                error="Debes proporcionar términos de búsqueda.",
            )

        base_url = _SEARCH_ENGINES[motor]
        query_encoded = urllib.parse.quote_plus(terminos)
        url_busqueda = base_url + query_encoded

        _logger.info(
            "Búsqueda web: motor='%s' términos='%s'", motor, terminos
        )

        resultado = self._abrir_en_navegador(terminos, url_busqueda)

        if resultado.success:
            nombre_motor = motor.capitalize()
            return SkillResult(
                success=True,
                output=(
                    f"🔍 Buscando en {nombre_motor}: \"{terminos}\"\n"
                    f"   URL: {url_busqueda}"
                ),
                data={
                    "terminos": terminos,
                    "motor": motor,
                    "url": url_busqueda,
                },
            )
        return resultado

    def _cmd_listar_favoritos(self, args: list[str]) -> SkillResult:
        """
        favoritos-web

        Lista todos los favoritos web (predefinidos + del usuario).
        """
        todos = self._todos_los_favoritos()

        if not todos:
            return SkillResult(
                success=True,
                output="No hay favoritos web guardados.",
            )

        user_favs = {k: v for k, v in todos.items() if k in self._user_favorites}
        builtin_favs = {k: v for k, v in todos.items() if k not in self._user_favorites}

        lineas: list[str] = []

        if user_favs:
            lineas.append("📌 Mis favoritos:")
            for nombre, url in sorted(user_favs.items()):
                lineas.append(f"  ⭐ {nombre:<20} → {url}")
            lineas.append("")

        if builtin_favs:
            lineas.append("🌐 Favoritos predefinidos:")
            for nombre, url in sorted(builtin_favs.items()):
                lineas.append(f"  🔖 {nombre:<20} → {url}")

        total = len(todos)
        lineas.append(f"\nTotal: {total} favoritos")
        lineas.append("Para abrir: abrir-url <nombre>  |  Para agregar: agregar-favorito <nombre> <url>")

        return SkillResult(
            success=True,
            output="\n".join(lineas),
            data={"total": total, "favoritos": todos},
        )

    def _cmd_agregar_favorito(self, args: list[str]) -> SkillResult:
        """
        agregar-favorito <nombre> <url>

        Agrega un nuevo favorito web con el nombre dado.
        La URL puede tener o no esquema (se normaliza automáticamente).
        """
        if len(args) < 2:
            return SkillResult(
                success=False,
                error=(
                    "Uso: agregar-favorito <nombre> <url>\n"
                    "Ejemplo: agregar-favorito python https://www.python.org\n"
                    "         agregar-favorito trabajo www.miempresa.com/portal"
                ),
            )

        nombre = args[0].strip().lower()
        url_raw = " ".join(args[1:]).strip()

        # Validar nombre
        if not nombre or " " in nombre:
            return SkillResult(
                success=False,
                error=(
                    f"El nombre '{nombre}' no es válido. "
                    "Los nombres de favoritos no pueden contener espacios."
                ),
            )

        # Normalizar y validar URL
        url = self._normalizar_url(url_raw)
        error_esquema = self._validar_esquema(url)
        if error_esquema:
            return SkillResult(success=False, error=error_esquema)

        existia = nombre in self._user_favorites
        self._user_favorites[nombre] = url
        self._save_favorites()

        accion = "actualizado" if existia else "agregado"
        _logger.info("Favorito web '%s' %s → '%s'", nombre, accion, url)

        return SkillResult(
            success=True,
            output=(
                f"✅ Favorito '{nombre}' {accion} correctamente.\n"
                f"   URL: {url}\n"
                f"Para abrir: abrir-url {nombre}"
            ),
            data={"nombre": nombre, "url": url, "action": accion},
        )

    def _cmd_quitar_favorito(self, args: list[str]) -> SkillResult:
        """
        quitar-favorito <nombre>

        Elimina un favorito del usuario. No elimina los predefinidos.
        """
        if not args:
            return SkillResult(
                success=False,
                error=(
                    "Uso: quitar-favorito <nombre>\n"
                    "Ejemplo: quitar-favorito mi-trabajo\n"
                    "Nota: Solo se pueden quitar favoritos agregados por el usuario."
                ),
            )

        nombre = args[0].strip().lower()

        if nombre not in self._user_favorites:
            if nombre in _BUILTIN_FAVORITES:
                return SkillResult(
                    success=False,
                    error=(
                        f"'{nombre}' es un favorito predefinido de AURA y no se puede eliminar.\n"
                        "Solo puedes quitar favoritos que hayas agregado con 'agregar-favorito'."
                    ),
                )
            return SkillResult(
                success=False,
                error=(
                    f"No se encontró el favorito '{nombre}'.\n"
                    "Usa 'favoritos-web' para ver los favoritos que puedes eliminar."
                ),
            )

        url_eliminada = self._user_favorites.pop(nombre)
        self._save_favorites()
        _logger.info(
            "Favorito web '%s' eliminado (era → '%s')", nombre, url_eliminada
        )

        return SkillResult(
            success=True,
            output=(
                f"🗑️ Favorito '{nombre}' eliminado correctamente.\n"
                f"   (Era: {url_eliminada})"
            ),
            data={"nombre": nombre, "url_eliminada": url_eliminada},
        )

    # ── Helpers internos ───────────────────────────────────────────────────

    def _abrir_en_navegador(self, etiqueta: str, url: str) -> SkillResult:
        """
        Abre la URL en el navegador por defecto del sistema.

        Args:
            etiqueta: Nombre legible para el log/output (alias, términos, etc.)
            url:      URL completa y validada a abrir.

        Returns:
            SkillResult con success=True si el navegador fue invocado.
        """
        _logger.info("Abriendo en navegador: '%s' → '%s'", etiqueta, url)
        try:
            from core.app_resolver import resolve_app, launch_app, get_preferred_browser_name, BROWSER_DISPLAY_NAMES
            pref_name = get_preferred_browser_name()
            disp_name = BROWSER_DISPLAY_NAMES.get(pref_name.lower(), pref_name.title())
            browser_res = resolve_app("navegador")

            if browser_res.success and browser_res.executable and os.path.isfile(browser_res.executable):
                _logger.info("WebSkill: abriendo '%s' con BROWSER_PREFERIDO '%s' (%s)", url, disp_name, browser_res.executable)
                launch_app(browser_res.executable, [url])
                return SkillResult(
                    success=True,
                    output=f"🌐 Abriendo en {disp_name}...\n   {url}",
                    data={"etiqueta": etiqueta, "url": url, "browser": pref_name, "executable": browser_res.executable},
                )

            # Fallback a webbrowser si no hay ejecutable específico resuelto
            abierto = webbrowser.open(url, new=2)  # new=2 = nueva pestaña si es posible
            if abierto:
                return SkillResult(
                    success=True,
                    output=f"🌐 Abriendo en el navegador...\n   {url}",
                    data={"etiqueta": etiqueta, "url": url},
                )
            # webbrowser.open retorna False si no encontró navegador
            _logger.warning("webbrowser.open retornó False para '%s'", url)
            return SkillResult(
                success=False,
                error=(
                    "No se encontró un navegador web instalado.\n"
                    f"Puedes copiar y abrir esta URL manualmente:\n   {url}"
                ),
            )
        except Exception as exc:  # pylint: disable=broad-except
            _logger.exception("Error al abrir el navegador para '%s'", url)
            return SkillResult(
                success=False,
                error=f"Error al abrir el navegador: {exc}",
            )


    def _normalizar_url(self, url: str) -> str:
        """
        Normaliza una URL agregando https:// si no tiene esquema.

        También detecta esquemas peligrosos sin '//' (javascript:, data:, vbscript:)
        y los devuelve sin modificar para que _validar_esquema los rechace.

        Args:
            url: URL cruda del usuario (puede tener o no esquema).

        Returns:
            URL con esquema garantizado (o url original si tiene esquema inválido).
        """
        url = url.strip()
        # Si ya tiene un esquema con :// (http://, https://, ftp://, etc.), no tocar
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+\-.]*://", url):
            return url
        # Detectar esquemas peligrosos sin // (javascript:, data:, vbscript:, etc.)
        # Estos tienen formato "esquema:algo" sin barras — devolver tal cual para validación
        dangerous_match = re.match(r"^([a-zA-Z][a-zA-Z0-9+\-.]*):", url)
        if dangerous_match:
            esquema = dangerous_match.group(1).lower()
            if esquema not in _ALLOWED_SCHEMES:
                return url  # devolver sin modificar → _validar_esquema lo rechazará
        # Si empieza con www. o tiene dominio claro, agregar https://
        return "https://" + url

    def _validar_esquema(self, url: str) -> str | None:
        """
        Valida que la URL tenga un esquema permitido.

        Returns:
            Mensaje de error si es inválida, None si es válida.
        """
        try:
            parsed = urllib.parse.urlparse(url)
            esquema = parsed.scheme.lower()
        except Exception:
            return f"URL inválida: '{url}'"

        if esquema not in _ALLOWED_SCHEMES:
            esquemas_ok = ", ".join(sorted(_ALLOWED_SCHEMES))
            return (
                f"Esquema '{esquema}' no permitido por seguridad.\n"
                f"Esquemas permitidos: {esquemas_ok}"
            )
        return None

    def _resolver_favorito(self, nombre: str) -> str | None:
        """
        Busca la URL de un favorito por nombre.
        Prioridad: favoritos del usuario > favoritos builtin.

        Returns:
            URL del favorito, o None si no existe.
        """
        if nombre in self._user_favorites:
            return self._user_favorites[nombre]
        if nombre in _BUILTIN_FAVORITES:
            return _BUILTIN_FAVORITES[nombre]
        return None

    def _todos_los_favoritos(self) -> dict[str, str]:
        """
        Retorna todos los favoritos combinados (builtin + usuario).
        Los favoritos del usuario sobreescriben los builtin.
        """
        combined = dict(_BUILTIN_FAVORITES)
        combined.update(self._user_favorites)
        return combined

    # ── Persistencia ───────────────────────────────────────────────────────

    def _load_favorites(self) -> None:
        """Carga los favoritos del usuario desde data/web_favorites.json."""
        if not _FAVORITES_FILE.exists():
            self._user_favorites = {}
            return
        try:
            with open(_FAVORITES_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._user_favorites = {
                    k.lower(): v
                    for k, v in data.items()
                    if isinstance(k, str) and isinstance(v, str)
                }
            else:
                self._user_favorites = {}
            _logger.debug(
                "Cargados %d favoritos web del usuario desde '%s'.",
                len(self._user_favorites),
                _FAVORITES_FILE,
            )
        except (json.JSONDecodeError, OSError) as exc:
            _logger.warning(
                "No se pudo cargar '%s': %s. Usando favoritos vacíos.",
                _FAVORITES_FILE,
                exc,
            )
            self._user_favorites = {}

    def _save_favorites(self) -> None:
        """Persiste los favoritos del usuario en data/web_favorites.json."""
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = _FAVORITES_FILE.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._user_favorites, f, ensure_ascii=False, indent=2)
            tmp.replace(_FAVORITES_FILE)
            _logger.debug(
                "Guardados %d favoritos web en '%s'.",
                len(self._user_favorites),
                _FAVORITES_FILE,
            )
        except OSError as exc:
            _logger.error(
                "No se pudo guardar '%s': %s", _FAVORITES_FILE, exc
            )

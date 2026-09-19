"""
AURA — SearchSkill: Skill de búsqueda de archivos (Fase 16)

Permite buscar archivos y carpetas por nombre, extensión o patrón glob
dentro del WORKSPACE_PATH o de cualquier carpeta indicada por el usuario.

Comandos disponibles:
  buscar <patrón> [en <carpeta>]      → Busca archivos/carpetas por nombre o glob
  buscar-ext <extensión> [en <carpeta>] → Busca por extensión (ej: .py, .txt)
  buscar-texto <texto> [en <carpeta>] → Busca archivos que contienen el texto

Opciones:
  --recursivo       → Busca en subcarpetas (activado por defecto)
  --no-recursivo    → Solo en la carpeta indicada (sin subcarpetas)
  --max <N>         → Máximo de resultados (por defecto: 50)
  --tipo archivo    → Solo archivos
  --tipo carpeta    → Solo carpetas

Seguridad:
  - La búsqueda nunca modifica archivos.
  - Las rutas relativas se resuelven contra WORKSPACE_PATH del .env.
  - Errores de acceso capturados sin interrumpir la búsqueda.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

from skills.skill_base import BaseSkill, SkillMeta, SkillResult, CATEGORY_SEARCH
from utils.logger import get_logger

_logger = get_logger("aura.skills.search")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_DEFAULT_MAX_RESULTS = 50
_CONTENT_SEARCH_MAX_SIZE_MB = 5   # No buscar dentro de archivos > 5 MB
_CONTENT_SEARCH_MAX_SIZE = _CONTENT_SEARCH_MAX_SIZE_MB * 1024 * 1024

# ---------------------------------------------------------------------------
# Metadatos de la skill
# ---------------------------------------------------------------------------

_META = SkillMeta(
    name="search_skill",
    version="1.0.0",
    display_name="Búsqueda",
    description=(
        "Búsqueda de archivos y carpetas por nombre, extensión o patrón. "
        "Soporta búsqueda recursiva, filtros por tipo y búsqueda de texto dentro de archivos."
    ),
    author="AURA",
    category=CATEGORY_SEARCH,
    commands=[
        "buscar",
        "buscar-ext",
        "buscar-texto",
    ],
    builtin=True,
    enabled_by_default=True,
)


# ---------------------------------------------------------------------------
# Implementación
# ---------------------------------------------------------------------------

class SearchSkill(BaseSkill):
    """
    Skill de búsqueda de archivos y carpetas para AURA.

    Permite buscar por nombre (glob), extensión o contenido de texto
    dentro del workspace configurado o de cualquier carpeta dada.
    """

    META = _META

    # ── Resolución de rutas ────────────────────────────────────────────────

    def _workspace(self) -> Path:
        """Retorna el directorio de trabajo configurado en .env."""
        try:
            from config import settings
            ws = settings.get("WORKSPACE_PATH", "")
            if ws:
                p = Path(ws)
                if p.exists():
                    return p
        except Exception:
            pass
        return Path.home() / "Documents"

    def _resolve(self, raw: str) -> Path:
        """
        Convierte una ruta relativa o absoluta en Path absoluto.
        Las rutas relativas se resuelven contra WORKSPACE_PATH.
        """
        p = Path(raw)
        if p.is_absolute():
            return p.resolve()
        return (self._workspace() / p).resolve()

    def _fmt_size(self, size_bytes: int) -> str:
        """Formatea un tamaño en bytes a unidad legible."""
        for unit in ("B", "KB", "MB", "GB"):
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024  # type: ignore[assignment]
        return f"{size_bytes:.1f} TB"

    # ── Parsing de argumentos ──────────────────────────────────────────────

    def _parse_common_flags(
        self, args: list[str]
    ) -> tuple[list[str], Path, bool, int, str | None]:
        """
        Parsea flags comunes a todos los comandos de búsqueda.

        Returns:
            (args_limpios, carpeta_base, recursivo, max_resultados, tipo)
            donde tipo es None | 'archivo' | 'carpeta'
        """
        args_restantes: list[str] = []
        carpeta_base: Path | None = None
        recursivo: bool = True
        max_resultados: int = _DEFAULT_MAX_RESULTS
        tipo: str | None = None

        i = 0
        while i < len(args):
            tok = args[i].lower()
            if tok == "--no-recursivo":
                recursivo = False
            elif tok == "--recursivo":
                recursivo = True
            elif tok == "--max" and i + 1 < len(args):
                i += 1
                try:
                    max_resultados = max(1, int(args[i]))
                except ValueError:
                    pass
            elif tok == "--tipo" and i + 1 < len(args):
                i += 1
                t = args[i].lower()
                if t in ("archivo", "carpeta"):
                    tipo = t
            elif tok == "en" and i + 1 < len(args):
                # Siguiente argumento es la carpeta base
                i += 1
                carpeta_base = self._resolve(args[i])
            else:
                args_restantes.append(args[i])
            i += 1

        if carpeta_base is None:
            carpeta_base = self._workspace()

        return args_restantes, carpeta_base, recursivo, max_resultados, tipo

    # ── Ejecución principal ────────────────────────────────────────────────

    def execute(self, command: str, args: list[str]) -> SkillResult:
        """
        Despacha el comando al método correspondiente.

        Args:
            command: Uno de los comandos definidos en META.commands.
            args:    Argumentos adicionales del comando.

        Returns:
            SkillResult con los resultados de la búsqueda.
        """
        self._logger.debug(f"SearchSkill.execute: command='{command}' args={args}")

        dispatch = {
            "buscar":       self._cmd_buscar,
            "buscar-ext":   self._cmd_buscar_ext,
            "buscar-texto": self._cmd_buscar_texto,
        }

        handler = dispatch.get(command)
        if handler is None:
            return SkillResult(
                success=False,
                error=(
                    f"Comando desconocido: '{command}'.\n"
                    "Comandos disponibles: buscar, buscar-ext, buscar-texto"
                ),
            )

        return handler(args)

    # ── Comando: buscar ───────────────────────────────────────────────────

    def _cmd_buscar(self, args: list[str]) -> SkillResult:
        """
        Busca archivos/carpetas por nombre o patrón glob.

        Uso:
            buscar <patrón>
            buscar <patrón> en <carpeta>
            buscar <patrón> --recursivo --max 20 --tipo archivo
        """
        if not args:
            ws = self._workspace()
            return SkillResult(
                success=False,
                error=(
                    "Especificá qué buscar. Ejemplos:\n"
                    "  buscar *.py\n"
                    "  buscar notas en Documentos\n"
                    "  buscar reporte*.xlsx --max 10\n"
                    f"\nCarpeta base: {ws}"
                ),
            )

        args_limpios, carpeta_base, recursivo, max_res, tipo = self._parse_common_flags(args)

        if not args_limpios:
            return SkillResult(
                success=False,
                error="Especificá el patrón de búsqueda.",
            )

        patron = " ".join(args_limpios).strip()

        if not carpeta_base.exists():
            return SkillResult(
                success=False,
                error=f"La carpeta de búsqueda no existe: {carpeta_base}",
            )
        if not carpeta_base.is_dir():
            return SkillResult(
                success=False,
                error=f"No es una carpeta: {carpeta_base}",
            )

        _logger.info(
            f"SearchSkill: buscando '{patron}' en '{carpeta_base}' "
            f"(recursivo={recursivo}, max={max_res}, tipo={tipo})"
        )

        resultados = self._buscar_por_patron(
            patron, carpeta_base, recursivo, max_res, tipo
        )

        return self._formatear_resultados(
            resultados=resultados,
            criterio=f"patrón '{patron}'",
            carpeta_base=carpeta_base,
            recursivo=recursivo,
            max_res=max_res,
            tipo=tipo,
        )

    # ── Comando: buscar-ext ───────────────────────────────────────────────

    def _cmd_buscar_ext(self, args: list[str]) -> SkillResult:
        """
        Busca archivos por extensión.

        Uso:
            buscar-ext .py
            buscar-ext txt en mis_documentos
            buscar-ext .xlsx --max 20
        """
        if not args:
            ws = self._workspace()
            return SkillResult(
                success=False,
                error=(
                    "Especificá la extensión a buscar. Ejemplos:\n"
                    "  buscar-ext .py\n"
                    "  buscar-ext txt en mis_documentos\n"
                    "  buscar-ext .xlsx --max 20\n"
                    f"\nCarpeta base: {ws}"
                ),
            )

        args_limpios, carpeta_base, recursivo, max_res, tipo = self._parse_common_flags(args)

        if not args_limpios:
            return SkillResult(
                success=False,
                error="Especificá la extensión a buscar.",
            )

        # Normalizar la extensión: .py → .py, py → .py
        ext_raw = args_limpios[0].strip().lower()
        if not ext_raw.startswith("."):
            ext_raw = "." + ext_raw

        if not carpeta_base.exists():
            return SkillResult(
                success=False,
                error=f"La carpeta de búsqueda no existe: {carpeta_base}",
            )

        # Para buscar-ext siempre tipo=archivo (extensiones son de archivos)
        tipo_efectivo = "archivo"

        _logger.info(
            f"SearchSkill: buscando extensión '{ext_raw}' en '{carpeta_base}' "
            f"(recursivo={recursivo}, max={max_res})"
        )

        patron = f"*{ext_raw}"
        resultados = self._buscar_por_patron(
            patron, carpeta_base, recursivo, max_res, tipo_efectivo
        )

        return self._formatear_resultados(
            resultados=resultados,
            criterio=f"extensión '{ext_raw}'",
            carpeta_base=carpeta_base,
            recursivo=recursivo,
            max_res=max_res,
            tipo=tipo_efectivo,
        )

    # ── Comando: buscar-texto ─────────────────────────────────────────────

    def _cmd_buscar_texto(self, args: list[str]) -> SkillResult:
        """
        Busca archivos que contienen el texto dado.

        Solo busca en archivos de texto (< 5 MB).

        Uso:
            buscar-texto <texto>
            buscar-texto <texto> en <carpeta>
            buscar-texto TODO --max 20 --no-recursivo
        """
        if not args:
            ws = self._workspace()
            return SkillResult(
                success=False,
                error=(
                    "Especificá el texto a buscar dentro de archivos. Ejemplos:\n"
                    "  buscar-texto TODO\n"
                    "  buscar-texto 'import pandas' en mi_proyecto\n"
                    "  buscar-texto error --max 10\n"
                    f"\nCarpeta base: {ws}"
                ),
            )

        args_limpios, carpeta_base, recursivo, max_res, _tipo = self._parse_common_flags(args)

        if not args_limpios:
            return SkillResult(
                success=False,
                error="Especificá el texto a buscar.",
            )

        texto = " ".join(args_limpios).strip()

        if not carpeta_base.exists():
            return SkillResult(
                success=False,
                error=f"La carpeta de búsqueda no existe: {carpeta_base}",
            )

        _logger.info(
            f"SearchSkill: buscando texto '{texto}' en '{carpeta_base}' "
            f"(recursivo={recursivo}, max={max_res})"
        )

        resultados = self._buscar_por_contenido(texto, carpeta_base, recursivo, max_res)

        return self._formatear_resultados_texto(
            resultados=resultados,
            texto=texto,
            carpeta_base=carpeta_base,
            recursivo=recursivo,
            max_res=max_res,
        )

    # ── Lógica de búsqueda ────────────────────────────────────────────────

    def _buscar_por_patron(
        self,
        patron: str,
        carpeta_base: Path,
        recursivo: bool,
        max_res: int,
        tipo: str | None,
    ) -> list[Path]:
        """
        Busca archivos/carpetas que coincidan con el patrón glob.

        Args:
            patron:      Patrón glob (ej: "*.py", "reporte*").
            carpeta_base: Carpeta raíz de la búsqueda.
            recursivo:   Si buscar en subcarpetas.
            max_res:     Máximo número de resultados.
            tipo:        None | 'archivo' | 'carpeta'

        Returns:
            Lista de Paths que coinciden.
        """
        resultados: list[Path] = []

        try:
            # Usar ** para búsqueda recursiva
            glob_pattern = f"**/{patron}" if recursivo else patron
            candidatos = carpeta_base.glob(glob_pattern)

            for candidato in candidatos:
                if len(resultados) >= max_res:
                    break

                # Filtro por tipo
                if tipo == "archivo" and not candidato.is_file():
                    continue
                if tipo == "carpeta" and not candidato.is_dir():
                    continue

                resultados.append(candidato)

        except (PermissionError, OSError) as e:
            _logger.warning(f"SearchSkill: error en búsqueda por patrón: {e}")

        return resultados

    def _buscar_por_contenido(
        self,
        texto: str,
        carpeta_base: Path,
        recursivo: bool,
        max_res: int,
    ) -> list[dict[str, Any]]:
        """
        Busca texto dentro de archivos de texto.

        Args:
            texto:       Texto a buscar (case-insensitive).
            carpeta_base: Carpeta raíz de la búsqueda.
            recursivo:   Si buscar en subcarpetas.
            max_res:     Máximo número de resultados.

        Returns:
            Lista de dicts: {'path': Path, 'linea': int, 'linea_texto': str}
        """
        resultados: list[dict[str, Any]] = []
        texto_lower = texto.lower()

        try:
            if recursivo:
                candidatos = carpeta_base.rglob("*")
            else:
                candidatos = carpeta_base.iterdir()

            for ruta in candidatos:
                if len(resultados) >= max_res:
                    break

                # Solo archivos de texto
                if not ruta.is_file():
                    continue

                # Saltar archivos muy grandes
                try:
                    if ruta.stat().st_size > _CONTENT_SEARCH_MAX_SIZE:
                        continue
                except OSError:
                    continue

                # Intentar leer como texto
                try:
                    contenido = ruta.read_text(encoding="utf-8", errors="ignore")
                except (PermissionError, OSError):
                    continue
                except Exception:
                    continue

                # Buscar el texto (case-insensitive)
                if texto_lower in contenido.lower():
                    # Encontrar la primera línea que contiene el texto
                    primera_linea = 0
                    linea_texto = ""
                    for num, linea in enumerate(contenido.splitlines(), 1):
                        if texto_lower in linea.lower():
                            primera_linea = num
                            linea_texto = linea.strip()[:80]  # Máx 80 chars
                            break

                    resultados.append({
                        "path": ruta,
                        "linea": primera_linea,
                        "linea_texto": linea_texto,
                    })

        except (PermissionError, OSError) as e:
            _logger.warning(f"SearchSkill: error en búsqueda por contenido: {e}")

        return resultados

    # ── Formateo de resultados ─────────────────────────────────────────────

    def _formatear_resultados(
        self,
        resultados: list[Path],
        criterio: str,
        carpeta_base: Path,
        recursivo: bool,
        max_res: int,
        tipo: str | None,
    ) -> SkillResult:
        """Formatea los resultados de búsqueda por nombre/patrón/extensión."""

        tipo_str = ""
        if tipo == "archivo":
            tipo_str = " (solo archivos)"
        elif tipo == "carpeta":
            tipo_str = " (solo carpetas)"

        modo = "recursiva" if recursivo else "solo en carpeta raíz"

        if not resultados:
            return SkillResult(
                success=True,
                output=(
                    f"🔍 Sin resultados para {criterio}\n"
                    f"   Búsqueda {modo} en: {carpeta_base}{tipo_str}"
                ),
                data={
                    "count": 0,
                    "patron": criterio,
                    "carpeta": str(carpeta_base),
                    "resultados": [],
                },
            )

        lines = [
            f"🔍 Resultados para {criterio}{tipo_str}",
            f"   Búsqueda {modo} en: {carpeta_base}",
            f"   Encontrados: {len(resultados)} resultado(s)",
            "",
        ]

        archivos_encontrados = [r for r in resultados if r.is_file()]
        carpetas_encontradas = [r for r in resultados if r.is_dir()]
        otros = [r for r in resultados if not r.is_file() and not r.is_dir()]

        if carpetas_encontradas:
            lines.append(f"  📁 Carpetas ({len(carpetas_encontradas)}):")
            for c in carpetas_encontradas:
                try:
                    ruta_rel = c.relative_to(carpeta_base)
                except ValueError:
                    ruta_rel = c
                lines.append(f"     {ruta_rel}/")

        if archivos_encontrados:
            if carpetas_encontradas:
                lines.append("")
            lines.append(f"  📄 Archivos ({len(archivos_encontrados)}):")
            for f in archivos_encontrados:
                try:
                    ruta_rel = f.relative_to(carpeta_base)
                except ValueError:
                    ruta_rel = f
                try:
                    size = self._fmt_size(f.stat().st_size)
                    lines.append(f"     {ruta_rel}  [{size}]")
                except OSError:
                    lines.append(f"     {ruta_rel}")

        if otros:
            for o in otros:
                try:
                    ruta_rel = o.relative_to(carpeta_base)
                except ValueError:
                    ruta_rel = o
                lines.append(f"     {ruta_rel}")

        if len(resultados) >= max_res:
            lines.append(
                f"\n  ⚠️ Se mostraron los primeros {max_res} resultados. "
                f"Usá --max <N> para cambiar el límite."
            )

        return SkillResult(
            success=True,
            output="\n".join(lines),
            data={
                "count": len(resultados),
                "patron": criterio,
                "carpeta": str(carpeta_base),
                "resultados": [str(r) for r in resultados],
            },
        )

    def _formatear_resultados_texto(
        self,
        resultados: list[dict[str, Any]],
        texto: str,
        carpeta_base: Path,
        recursivo: bool,
        max_res: int,
    ) -> SkillResult:
        """Formatea los resultados de búsqueda por contenido de texto."""

        modo = "recursiva" if recursivo else "solo en carpeta raíz"

        if not resultados:
            return SkillResult(
                success=True,
                output=(
                    f"🔍 Sin resultados para texto '{texto}'\n"
                    f"   Búsqueda {modo} en: {carpeta_base}\n"
                    f"   (Solo se busca en archivos de texto < {_CONTENT_SEARCH_MAX_SIZE_MB} MB)"
                ),
                data={
                    "count": 0,
                    "texto": texto,
                    "carpeta": str(carpeta_base),
                    "resultados": [],
                },
            )

        lines = [
            f"🔍 Archivos que contienen '{texto}'",
            f"   Búsqueda {modo} en: {carpeta_base}",
            f"   Encontrados: {len(resultados)} archivo(s)",
            "",
        ]

        for item in resultados:
            ruta: Path = item["path"]
            linea: int = item["linea"]
            linea_texto: str = item["linea_texto"]

            try:
                ruta_rel = ruta.relative_to(carpeta_base)
            except ValueError:
                ruta_rel = ruta

            try:
                size = self._fmt_size(ruta.stat().st_size)
                header = f"  📄 {ruta_rel}  [{size}]"
            except OSError:
                header = f"  📄 {ruta_rel}"

            lines.append(header)
            if linea > 0 and linea_texto:
                lines.append(f"     → Línea {linea}: {linea_texto}")

        if len(resultados) >= max_res:
            lines.append(
                f"\n  ⚠️ Se mostraron los primeros {max_res} resultados. "
                f"Usá --max <N> para cambiar el límite."
            )

        lines.append(
            f"\n  ℹ️ Solo se buscó en archivos de texto < {_CONTENT_SEARCH_MAX_SIZE_MB} MB."
        )

        return SkillResult(
            success=True,
            output="\n".join(lines),
            data={
                "count": len(resultados),
                "texto": texto,
                "carpeta": str(carpeta_base),
                "resultados": [str(item["path"]) for item in resultados],
            },
        )

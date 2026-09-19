"""
AURA — FilesSkill: Skill de manejo de archivos (Fase 15)

Permite crear, copiar, mover, renombrar y eliminar archivos y carpetas
desde el chat de AURA.

Comandos disponibles:
  crear <ruta>                     → Crea un archivo vacío o una carpeta
  copiar <origen> <destino>        → Copia un archivo o carpeta
  mover <origen> <destino>         → Mueve un archivo o carpeta
  renombrar <ruta> <nuevo_nombre>  → Renombra un archivo o carpeta
  eliminar <ruta>                  → Envía a la papelera (seguro)
  info <ruta>                      → Muestra información de un archivo/carpeta
  listar [ruta]                    → Lista el contenido de una carpeta

Seguridad:
  - 'eliminar' usa send2trash (papelera) por defecto, nunca borrado permanente.
  - Las rutas relativas se resuelven contra WORKSPACE_PATH del .env.
  - Todas las acciones destructivas se registran en el log.
  - Protección contra escribir/borrar fuera del workspace (opcional, vía config).
"""

from __future__ import annotations

import os
import shutil
import stat
from datetime import datetime
from pathlib import Path
from typing import Any

from skills.skill_base import BaseSkill, SkillMeta, SkillResult, CATEGORY_FILES
from utils.logger import get_logger

_logger = get_logger("aura.skills.files")

# ---------------------------------------------------------------------------
# Helpers de dependencias opcionales
# ---------------------------------------------------------------------------

def _has_send2trash() -> bool:
    try:
        import send2trash  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Metadatos de la skill
# ---------------------------------------------------------------------------

_META = SkillMeta(
    name="files_skill",
    version="1.0.0",
    display_name="Archivos",
    description=(
        "Gestión de archivos y carpetas: crear, copiar, mover, renombrar, "
        "eliminar (a papelera) y listar contenido de directorios."
    ),
    author="AURA",
    category=CATEGORY_FILES,
    commands=[
        "crear",
        "guardar",
        "escribir",
        "copiar",
        "mover",
        "renombrar",
        "eliminar",
        "info",
        "listar",
    ],
    builtin=True,
    enabled_by_default=True,
)


# ---------------------------------------------------------------------------
# Implementación
# ---------------------------------------------------------------------------

class FilesSkill(BaseSkill):
    """
    Skill de gestión de archivos y carpetas para AURA.

    Permite crear, copiar, mover, renombrar y eliminar archivos
    de forma segura. La eliminación siempre usa la papelera de
    reciclaje (send2trash) para permitir recuperación.

    Las rutas relativas se resuelven contra WORKSPACE_PATH del .env.
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
        # Fallback: carpeta Documents del usuario
        return Path.home() / "Documents"

    def _resolve(self, raw: str) -> Path:
        """
        Convierte una ruta relativa o absoluta en Path absoluto.

        Si la ruta es relativa, se resuelve contra WORKSPACE_PATH.
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

    def _fmt_time(self, ts: float) -> str:
        """Formatea un timestamp Unix a cadena legible."""
        return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")

    # ── Ejecución principal ────────────────────────────────────────────────

    def execute(self, command: str, args: list[str]) -> SkillResult:
        """
        Despacha el comando al método correspondiente.

        Args:
            command: Uno de los comandos definidos en META.commands.
            args:    Argumentos adicionales del comando.

        Returns:
            SkillResult con el resultado de la operación.
        """
        self._logger.debug(f"FilesSkill.execute: command='{command}' args={args}")

        dispatch = {
            "crear":     self._cmd_crear,
            "guardar":   self._cmd_guardar,
            "escribir":  self._cmd_guardar,
            "copiar":    self._cmd_copiar,
            "mover":     self._cmd_mover,
            "renombrar": self._cmd_renombrar,
            "eliminar":  self._cmd_eliminar,
            "info":      self._cmd_info,
            "listar":    self._cmd_listar,
        }

        handler = dispatch.get(command)
        if handler is None:
            return SkillResult(
                success=False,
                error=(
                    f"Comando desconocido: '{command}'.\\n"
                    "Comandos disponibles: crear, guardar, escribir, copiar, mover, renombrar, "
                    "eliminar, info, listar"
                ),
            )

        return handler(args)

    def write_file(self, target_path: Any, content: str) -> SkillResult:
        """
        Escribe contenido textual en un archivo con codificación UTF-8 explícita.
        Aplica el guard estricto de nombres de archivo de Fase 63 y retorna la ruta completa.
        """
        p = Path(target_path).resolve() if Path(target_path).is_absolute() else self._resolve(str(target_path))
        base_name = p.name

        from aura.core.filename_guard import is_valid_strict_filename
        valid, reason = is_valid_strict_filename(base_name)
        if not valid:
            return SkillResult(
                success=False,
                error=f"Nombre de archivo inválido ({reason}): '{base_name}'",
            )

        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            return SkillResult(
                success=True,
                output=f"📄 Archivo guardado: {p}",
                data={"path": str(p), "type": "file", "size": len(content)},
            )
        except Exception as e:
            self._logger.error(f"FilesSkill: error al escribir en '{p}': {e}")
            return SkillResult(
                success=False,
                error=f"Error al escribir en '{p}': {e}",
            )

    def _cmd_guardar(self, args: list[str]) -> SkillResult:
        """
        Guarda contenido textual en un archivo.
        Uso:
            guardar <ruta> <contenido...>
        """
        if not args:
            return SkillResult(
                success=False,
                error="Especificá la ruta del archivo a guardar.",
            )
        target_path = args[0]
        content = " ".join(args[1:]) if len(args) > 1 else ""
        return self.write_file(target_path, content)

    # ── Comando: crear ────────────────────────────────────────────────────

    def _cmd_crear(self, args: list[str]) -> SkillResult:
        """
        Crea un archivo vacío o una carpeta.

        Uso:
            crear <ruta>           → archivo vacío
            crear <ruta> --carpeta → directorio
        """
        if not args:
            ws = self._workspace()
            return SkillResult(
                success=False,
                error=(
                    "Especificá qué crear. Ejemplos:\\n"
                    "  crear notas.txt\\n"
                    "  crear mi_proyecto --carpeta\\n"
                    f"\\nDirectorio base: {ws}"
                ),
            )

        es_carpeta = "--carpeta" in [a.lower() for a in args]
        # Filtrar el flag de la lista de argumentos de ruta
        ruta_args = [a for a in args if a.lower() != "--carpeta"]
        ruta_str = " ".join(ruta_args).strip()

        # Sanitizar nombre: eliminar caracteres no válidos de Windows (< > : " | ? *) y recortar a 80 chars
        import re
        base_name = os.path.basename(ruta_str)
        clean_base = re.sub(r'[<>:"|?*]', '_', base_name)
        if len(clean_base) > 80:
            if "." in clean_base:
                b, ext = clean_base.rsplit(".", 1)
                clean_base = b[: 80 - len(ext) - 1] + "." + ext
            else:
                clean_base = clean_base[:80]

        # Guard de filenames dentro de files_skill según Fase 63 (una frase no puede ser nombre de archivo, desde ningún camino)
        from aura.core.filename_guard import is_valid_strict_filename
        valid, reason = is_valid_strict_filename(clean_base)
        if not valid:
            return SkillResult(
                success=False,
                error=f"Nombre de archivo inválido ({reason}): '{clean_base}'",
            )

        dir_part = os.path.dirname(ruta_str)
        if dir_part:
            ruta_str = os.path.join(dir_part, clean_base)
        else:
            ruta_str = clean_base

        target = self._resolve(ruta_str)

        if target.exists():
            tipo = "Carpeta" if target.is_dir() else "Archivo"
            return SkillResult(
                success=False,
                error=f"{tipo} ya existe: {target}",
            )

        _logger.info(f"FilesSkill: creando {'carpeta' if es_carpeta else 'archivo'} '{target}'")

        try:
            if es_carpeta:
                target.mkdir(parents=True, exist_ok=False)
                return SkillResult(
                    success=True,
                    output=f"📁 Carpeta creada: {target}",
                    data={"path": str(target), "type": "directory"},
                )
            else:
                # Crear directorios padre si no existen
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
                return SkillResult(
                    success=True,
                    output=f"📄 Archivo creado: {target}",
                    data={"path": str(target), "type": "file"},
                )
        except PermissionError:
            return SkillResult(
                success=False,
                error=f"Sin permisos para crear en: {target.parent}",
            )
        except Exception as e:
            _logger.error(f"FilesSkill: error creando '{target}': {e}")
            return SkillResult(
                success=False,
                error=f"Error al crear '{ruta_str}': {e}",
            )

    # ── Comando: copiar ───────────────────────────────────────────────────

    def _cmd_copiar(self, args: list[str]) -> SkillResult:
        """
        Copia un archivo o carpeta.

        Uso:
            copiar <origen> <destino>
        """
        if len(args) < 2:
            return SkillResult(
                success=False,
                error=(
                    "Especificá origen y destino. Ejemplos:\\n"
                    "  copiar notas.txt notas_backup.txt\\n"
                    "  copiar mi_carpeta mi_carpeta_backup"
                ),
            )

        # Dividir: último arg es destino, el resto es origen
        origen_str = " ".join(args[:-1]).strip()
        destino_str = args[-1].strip()

        origen = self._resolve(origen_str)
        destino = self._resolve(destino_str)

        if not origen.exists():
            return SkillResult(
                success=False,
                error=f"No existe el origen: {origen}",
            )

        _logger.info(f"FilesSkill: copiando '{origen}' → '{destino}'")

        try:
            if origen.is_dir():
                # Si el destino existe y es carpeta, copiar dentro de ella
                if destino.is_dir():
                    destino = destino / origen.name
                shutil.copytree(str(origen), str(destino))
                return SkillResult(
                    success=True,
                    output=f"📁 Carpeta copiada:\\n  Origen:  {origen}\\n  Destino: {destino}",
                    data={"origen": str(origen), "destino": str(destino), "type": "directory"},
                )
            else:
                # Si el destino es carpeta, copiar el archivo dentro
                if destino.is_dir():
                    destino = destino / origen.name
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(origen), str(destino))
                return SkillResult(
                    success=True,
                    output=f"📄 Archivo copiado:\\n  Origen:  {origen}\\n  Destino: {destino}",
                    data={"origen": str(origen), "destino": str(destino), "type": "file"},
                )
        except shutil.Error as e:
            return SkillResult(
                success=False,
                error=f"Error al copiar: {e}",
            )
        except PermissionError:
            return SkillResult(
                success=False,
                error=f"Sin permisos para copiar a: {destino.parent}",
            )
        except Exception as e:
            _logger.error(f"FilesSkill: error copiando '{origen}' → '{destino}': {e}")
            return SkillResult(
                success=False,
                error=f"Error al copiar '{origen_str}': {e}",
            )

    # ── Comando: mover ────────────────────────────────────────────────────

    def _cmd_mover(self, args: list[str]) -> SkillResult:
        """
        Mueve un archivo o carpeta a otra ubicación.

        Uso:
            mover <origen> <destino>
        """
        if len(args) < 2:
            return SkillResult(
                success=False,
                error=(
                    "Especificá origen y destino. Ejemplos:\\n"
                    "  mover notas.txt documentos/notas.txt\\n"
                    "  mover mi_carpeta nueva_ubicacion"
                ),
            )

        origen_str = " ".join(args[:-1]).strip()
        destino_str = args[-1].strip()

        origen = self._resolve(origen_str)
        destino = self._resolve(destino_str)

        if not origen.exists():
            return SkillResult(
                success=False,
                error=f"No existe el origen: {origen}",
            )

        _logger.info(f"FilesSkill: moviendo '{origen}' → '{destino}'")

        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(origen), str(destino))
            tipo = "Carpeta" if destino.is_dir() or origen.suffix == "" else "Archivo"
            return SkillResult(
                success=True,
                output=f"✅ {tipo} movido:\\n  Origen:  {origen}\\n  Destino: {destino}",
                data={"origen": str(origen), "destino": str(destino)},
            )
        except shutil.Error as e:
            return SkillResult(
                success=False,
                error=f"Error al mover: {e}",
            )
        except PermissionError:
            return SkillResult(
                success=False,
                error=f"Sin permisos para mover a: {destino.parent}",
            )
        except Exception as e:
            _logger.error(f"FilesSkill: error moviendo '{origen}' → '{destino}': {e}")
            return SkillResult(
                success=False,
                error=f"Error al mover '{origen_str}': {e}",
            )

    # ── Comando: renombrar ────────────────────────────────────────────────

    def _cmd_renombrar(self, args: list[str]) -> SkillResult:
        """
        Renombra un archivo o carpeta.

        Uso:
            renombrar <ruta_actual> <nuevo_nombre>

        Nota: <nuevo_nombre> es solo el nombre (sin ruta), no una ruta completa.
        """
        if len(args) < 2:
            return SkillResult(
                success=False,
                error=(
                    "Especificá la ruta actual y el nuevo nombre. Ejemplos:\\n"
                    "  renombrar notas.txt apuntes.txt\\n"
                    "  renombrar mi_carpeta proyecto_final"
                ),
            )

        origen_str = " ".join(args[:-1]).strip()
        nuevo_nombre = args[-1].strip()

        origen = self._resolve(origen_str)

        if not origen.exists():
            return SkillResult(
                success=False,
                error=f"No existe: {origen}",
            )

        # Evitar rutas en el nuevo nombre (solo nombre simple)
        if os.sep in nuevo_nombre or "/" in nuevo_nombre:
            return SkillResult(
                success=False,
                error=(
                    f"'{nuevo_nombre}' parece una ruta completa.\\n"
                    "Para renombrar usá solo el nuevo nombre (sin barra).\\n"
                    "Para mover usá el comando 'mover'."
                ),
            )

        # Guard de filenames dentro de files_skill según Fase 63 (una frase no puede ser nombre de archivo, desde ningún camino)
        from aura.core.filename_guard import is_valid_strict_filename
        valid, reason = is_valid_strict_filename(nuevo_nombre)
        if not valid:
            return SkillResult(
                success=False,
                error=f"Nuevo nombre de archivo inválido ({reason}): '{nuevo_nombre}'",
            )

        destino = origen.parent / nuevo_nombre

        if destino.exists():
            return SkillResult(
                success=False,
                error=f"Ya existe un archivo/carpeta con ese nombre: {destino}",
            )

        _logger.info(f"FilesSkill: renombrando '{origen}' → '{destino}'")

        try:
            origen.rename(destino)
            return SkillResult(
                success=True,
                output=(
                    f"✏️ Renombrado correctamente:\\n"
                    f"  Antes:  {origen.name}\\n"
                    f"  Ahora:  {destino.name}\\n"
                    f"  En:     {destino.parent}"
                ),
                data={"origen": str(origen), "destino": str(destino)},
            )
        except PermissionError:
            return SkillResult(
                success=False,
                error=f"Sin permisos para renombrar: {origen}",
            )
        except Exception as e:
            _logger.error(f"FilesSkill: error renombrando '{origen}': {e}")
            return SkillResult(
                success=False,
                error=f"Error al renombrar '{origen_str}': {e}",
            )

    # ── Comando: eliminar ─────────────────────────────────────────────────

    def _cmd_eliminar(self, args: list[str]) -> SkillResult:
        """
        Elimina un archivo o carpeta enviándolo a la papelera de reciclaje.

        Por defecto opera en modo dry-run (simulación).
        Requiere '--ahora' para eliminar realmente.

        Uso:
            eliminar <ruta>          → muestra qué se eliminaría
            eliminar <ruta> --ahora  → envía a papelera
        """
        if not args:
            return SkillResult(
                success=False,
                error=(
                    "Especificá qué eliminar. Ejemplos:\\n"
                    "  eliminar notas.txt\\n"
                    "  eliminar mi_carpeta\\n"
                    "\\nUsá '--ahora' para confirmar la eliminación."
                ),
            )

        ahora = "--ahora" in [a.lower() for a in args]
        ruta_args = [a for a in args if a.lower() != "--ahora"]
        ruta_str = " ".join(ruta_args).strip()

        target = self._resolve(ruta_str)

        if not target.exists():
            return SkillResult(
                success=False,
                error=f"No existe: {target}",
            )

        tipo = "carpeta" if target.is_dir() else "archivo"

        # Calcular tamaño para el informe
        try:
            if target.is_dir():
                total = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
                tamanio = self._fmt_size(total)
                n_archivos = sum(1 for f in target.rglob("*") if f.is_file())
                detalle = f"{n_archivos} archivo(s), {tamanio}"
            else:
                tamanio = self._fmt_size(target.stat().st_size)
                detalle = tamanio
        except Exception:
            detalle = "tamaño desconocido"

        # Modo dry-run
        if not ahora:
            _logger.info(f"FilesSkill: simulación de eliminación (dry-run): '{target}'")
            return SkillResult(
                success=True,
                output=(
                    f"🗑️ [SIMULACIÓN] Se enviaría a la papelera:\\n"
                    f"  Tipo:    {tipo.capitalize()}\\n"
                    f"  Ruta:    {target}\\n"
                    f"  Tamaño:  {detalle}\\n"
                    f"\\n"
                    f"Para eliminar realmente, escribí:\\n"
                    f"  eliminar {ruta_str} --ahora\\n"
                    f"\\n"
                    f"ℹ️ El archivo se enviará a la papelera de reciclaje "
                    f"(puede recuperarse)."
                ),
                data={"path": str(target), "dry_run": True, "type": tipo},
            )

        # Verificar que send2trash esté disponible
        if not _has_send2trash():
            return SkillResult(
                success=False,
                error=(
                    "send2trash no está disponible.\\n"
                    "Instalalo con: .\\\\env\\\\Scripts\\\\pip.exe install send2trash"
                ),
            )

        _logger.warning(f"FilesSkill: enviando a papelera '{target}'")

        try:
            import send2trash
            send2trash.send2trash(str(target))
            return SkillResult(
                success=True,
                output=(
                    f"🗑️ Enviado a la papelera de reciclaje:\\n"
                    f"  Tipo:   {tipo.capitalize()}\\n"
                    f"  Ruta:   {target}\\n"
                    f"  Tamaño: {detalle}\\n"
                    f"\\n"
                    f"Podés recuperarlo desde la Papelera de Reciclaje de Windows."
                ),
                data={"path": str(target), "dry_run": False, "type": tipo},
            )
        except Exception as e:
            _logger.error(f"FilesSkill: error eliminando '{target}': {e}")
            return SkillResult(
                success=False,
                error=f"Error al enviar a papelera '{ruta_str}': {e}",
            )

    # ── Comando: info ─────────────────────────────────────────────────────

    def _cmd_info(self, args: list[str]) -> SkillResult:
        """
        Muestra información detallada de un archivo o carpeta.

        Uso:
            info <ruta>
        """
        if not args:
            return SkillResult(
                success=False,
                error=(
                    "Especificá la ruta del archivo o carpeta. Ejemplos:\\n"
                    "  info notas.txt\\n"
                    "  info mi_carpeta"
                ),
            )

        ruta_str = " ".join(args).strip()
        target = self._resolve(ruta_str)

        if not target.exists():
            return SkillResult(
                success=False,
                error=f"No existe: {target}",
            )

        try:
            st = target.stat()
            lines = []

            if target.is_dir():
                # Contar contenido
                try:
                    hijos = list(target.iterdir())
                    n_archivos = sum(1 for h in hijos if h.is_file())
                    n_carpetas = sum(1 for h in hijos if h.is_dir())
                    total_size = sum(
                        f.stat().st_size for f in target.rglob("*") if f.is_file()
                    )
                    contenido = (
                        f"{n_archivos} archivo(s), {n_carpetas} carpeta(s)"
                        f" | Total: {self._fmt_size(total_size)}"
                    )
                except PermissionError:
                    contenido = "(sin acceso al contenido)"

                lines = [
                    f"📁 Carpeta: {target.name}",
                    f"   Ruta completa: {target}",
                    f"   Contenido:     {contenido}",
                    f"   Creado:        {self._fmt_time(st.st_ctime)}",
                    f"   Modificado:    {self._fmt_time(st.st_mtime)}",
                ]
            else:
                lines = [
                    f"📄 Archivo: {target.name}",
                    f"   Ruta completa: {target}",
                    f"   Tamaño:        {self._fmt_size(st.st_size)}",
                    f"   Extensión:     {target.suffix or '(sin extensión)'}",
                    f"   Creado:        {self._fmt_time(st.st_ctime)}",
                    f"   Modificado:    {self._fmt_time(st.st_mtime)}",
                ]

            return SkillResult(
                success=True,
                output="\\n".join(lines),
                data={"path": str(target), "size": st.st_size, "is_dir": target.is_dir()},
            )

        except PermissionError:
            return SkillResult(
                success=False,
                error=f"Sin permisos para acceder a: {target}",
            )
        except Exception as e:
            _logger.error(f"FilesSkill: error obteniendo info de '{target}': {e}")
            return SkillResult(
                success=False,
                error=f"Error al obtener información de '{ruta_str}': {e}",
            )

    # ── Comando: listar ───────────────────────────────────────────────────

    def _cmd_listar(self, args: list[str]) -> SkillResult:
        """
        Lista el contenido de una carpeta.

        Uso:
            listar              → lista el WORKSPACE_PATH
            listar <ruta>       → lista la carpeta indicada
        """
        if args:
            ruta_str = " ".join(args).strip()
            target = self._resolve(ruta_str)
        else:
            target = self._workspace()
            ruta_str = str(target)

        if not target.exists():
            return SkillResult(
                success=False,
                error=f"No existe la carpeta: {target}",
            )

        if not target.is_dir():
            return SkillResult(
                success=False,
                error=(
                    f"'{target.name}' es un archivo, no una carpeta.\\n"
                    f"Usá 'info {ruta_str}' para ver información del archivo."
                ),
            )

        try:
            hijos = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return SkillResult(
                success=False,
                error=f"Sin permisos para listar: {target}",
            )

        if not hijos:
            return SkillResult(
                success=True,
                output=f"📂 Carpeta vacía: {target}",
                data={"path": str(target), "count": 0},
            )

        MAX_ITEMS = 40
        lines = [f"📂 Contenido de: {target}", ""]

        carpetas = [h for h in hijos if h.is_dir()]
        archivos = [h for h in hijos if h.is_file()]

        if carpetas:
            lines.append(f"  📁 Carpetas ({len(carpetas)}):")
            for c in carpetas[:MAX_ITEMS]:
                try:
                    n = sum(1 for _ in c.iterdir())
                    lines.append(f"     {c.name}/  ({n} elementos)")
                except PermissionError:
                    lines.append(f"     {c.name}/  (sin acceso)")

        if archivos:
            if carpetas:
                lines.append("")
            lines.append(f"  📄 Archivos ({len(archivos)}):")
            for f in archivos[:MAX_ITEMS]:
                try:
                    size = self._fmt_size(f.stat().st_size)
                    lines.append(f"     {f.name}  [{size}]")
                except Exception:
                    lines.append(f"     {f.name}")

        total = len(hijos)
        if total > MAX_ITEMS:
            lines.append(f"\\n  ... y {total - MAX_ITEMS} elemento(s) más.")

        lines.append(f"\\nTotal: {len(carpetas)} carpeta(s), {len(archivos)} archivo(s)")

        return SkillResult(
            success=True,
            output="\\n".join(lines),
            data={"path": str(target), "count": total},
        )

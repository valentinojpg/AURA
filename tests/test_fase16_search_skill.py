"""
AURA — Tests de la Fase 16: SearchSkill

Suite completa de tests automatizados para la Skill de Búsqueda de Archivos.

Cubre:
  - Importación y metadatos
  - Comando 'buscar' (por nombre/patrón glob)
  - Comando 'buscar-ext' (por extensión)
  - Comando 'buscar-texto' (por contenido)
  - Flags: --recursivo, --no-recursivo, --max, --tipo, en <carpeta>
  - Manejo de errores (args faltantes, carpeta inexistente)
  - Integración con SkillRegistry (register, find_by_command, execute, discover)

Ejecutar con:
    .\\env\\Scripts\\python.exe -m pytest tests/test_fase16_search_skill.py -v
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Asegurar que el proyecto esté en el path
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ===========================================================================
# 1. IMPORTACIÓN Y ESTRUCTURA DEL MÓDULO
# ===========================================================================

class TestImportacion:
    """La SearchSkill debe poder importarse sin errores."""

    def test_importa_search_skill(self):
        from skills.builtin.search_skill import SearchSkill
        assert SearchSkill is not None

    def test_importa_desde_builtin_init(self):
        from skills.builtin import SearchSkill
        assert SearchSkill is not None

    def test_search_skill_es_subclase_de_baseskill(self):
        from skills.builtin.search_skill import SearchSkill
        from skills.skill_base import BaseSkill
        assert issubclass(SearchSkill, BaseSkill)

    def test_search_skill_tiene_meta(self):
        from skills.builtin.search_skill import SearchSkill
        assert hasattr(SearchSkill, "META")

    def test_search_skill_instanciable(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        assert skill is not None

    def test_setup_y_teardown_funcionan(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        skill.setup()
        assert skill.is_setup
        skill.teardown()
        assert not skill.is_setup


# ===========================================================================
# 2. METADATOS (META)
# ===========================================================================

class TestMetadatos:
    """Los metadatos de SearchSkill deben ser correctos."""

    @pytest.fixture(autouse=True)
    def skill(self):
        from skills.builtin.search_skill import SearchSkill
        self._skill = SearchSkill()
        return self._skill

    def test_meta_name(self):
        assert self._skill.META.name == "search_skill"

    def test_meta_version(self):
        assert self._skill.META.version == "1.0.0"

    def test_meta_display_name(self):
        assert self._skill.META.display_name == "Búsqueda"

    def test_meta_author(self):
        assert self._skill.META.author == "AURA"

    def test_meta_category(self):
        from skills.skill_base import CATEGORY_SEARCH
        assert self._skill.META.category == CATEGORY_SEARCH

    def test_meta_builtin(self):
        assert self._skill.META.builtin is True

    def test_meta_enabled_by_default(self):
        assert self._skill.META.enabled_by_default is True

    def test_meta_commands_tiene_3_comandos(self):
        assert len(self._skill.META.commands) == 3

    def test_meta_commands_contiene_buscar(self):
        assert "buscar" in self._skill.META.commands

    def test_meta_commands_contiene_buscar_ext(self):
        assert "buscar-ext" in self._skill.META.commands

    def test_meta_commands_contiene_buscar_texto(self):
        assert "buscar-texto" in self._skill.META.commands


# ===========================================================================
# 3. COMANDO BUSCAR — SIN ARGUMENTOS / ERRORES
# ===========================================================================

class TestBuscarSinArgs:
    """'buscar' sin argumentos debe retornar error descriptivo."""

    @pytest.fixture(autouse=True)
    def skill(self):
        from skills.builtin.search_skill import SearchSkill
        self._skill = SearchSkill()

    def test_buscar_sin_args_retorna_error(self):
        result = self._skill.execute("buscar", [])
        assert result.success is False

    def test_buscar_sin_args_menciona_ejemplos(self):
        result = self._skill.execute("buscar", [])
        assert "buscar" in result.error.lower() or len(result.error) > 0

    def test_buscar_carpeta_inexistente_retorna_error(self):
        result = self._skill.execute("buscar", ["*.py", "en", "/ruta/que/no/existe/para/aura"])
        assert result.success is False
        assert "no existe" in result.error.lower()

    def test_buscar_en_archivo_en_vez_de_carpeta(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"contenido")
            ruta = f.name
        try:
            result = self._skill.execute("buscar", ["*.py", "en", ruta])
            assert result.success is False
        finally:
            Path(ruta).unlink(missing_ok=True)

    def test_comando_desconocido_retorna_error(self):
        result = self._skill.execute("comando_que_no_existe", [])
        assert result.success is False
        assert "desconocido" in result.error.lower()


# ===========================================================================
# 4. COMANDO BUSCAR — BÚSQUEDA POR NOMBRE/PATRÓN
# ===========================================================================

class TestBuscarPorPatron:
    """'buscar' debe encontrar archivos/carpetas que coincidan con el patrón."""

    @pytest.fixture(autouse=True)
    def workspace_tmp(self):
        """Crea un directorio temporal como workspace con archivos de prueba."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            # Crear estructura de archivos de prueba
            (base / "notas.txt").write_text("texto de prueba")
            (base / "reporte_enero.xlsx").write_bytes(b"")
            (base / "reporte_febrero.xlsx").write_bytes(b"")
            (base / "script.py").write_text("print('hola')")
            (base / "README.md").write_text("# Readme")
            sub = base / "subcarpeta"
            sub.mkdir()
            (sub / "notas_sub.txt").write_text("texto sub")
            (sub / "deep_script.py").write_text("# deep")
            self._base = base
            self._sub = sub
            yield base

    def _skill_con_workspace(self, ws: Path):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=ws):
            yield skill

    def test_buscar_patron_exacto_encuentra_archivo(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar", ["notas.txt"])
        assert result.success is True
        assert result.data["count"] >= 1

    def test_buscar_glob_wildcard_encuentra_multiples(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar", ["reporte*.xlsx"])
        assert result.success is True
        assert result.data["count"] >= 2

    def test_buscar_sin_coincidencias_retorna_success_count_0(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar", ["archivo_que_no_existe_xyz_aura.txt"])
        assert result.success is True
        assert result.data["count"] == 0

    def test_buscar_sin_coincidencias_output_sin_resultados(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar", ["xyz_nada_123.txt"])
        assert "sin resultados" in result.output.lower()

    def test_buscar_recursivo_encuentra_en_subcarpetas(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar", ["notas_sub.txt"])
        assert result.success is True
        assert result.data["count"] >= 1

    def test_buscar_no_recursivo_no_encuentra_en_subcarpetas(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar", ["notas_sub.txt", "--no-recursivo"])
        assert result.success is True
        assert result.data["count"] == 0

    def test_buscar_max_limita_resultados(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar", ["*.py", "--max", "1"])
        assert result.success is True
        assert result.data["count"] <= 1

    def test_buscar_tipo_archivo_excluye_carpetas(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar", ["subcarpeta", "--tipo", "archivo"])
        # La carpeta "subcarpeta" NO debe aparecer con --tipo archivo
        assert result.success is True
        for ruta in result.data.get("resultados", []):
            assert not Path(ruta).is_dir()

    def test_buscar_tipo_carpeta_excluye_archivos(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar", ["*", "--tipo", "carpeta"])
        # Solo deben aparecer carpetas
        assert result.success is True
        for ruta in result.data.get("resultados", []):
            assert Path(ruta).is_dir()

    def test_buscar_con_carpeta_en(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar", ["*.py", "en", str(self._sub)])
        assert result.success is True
        assert result.data["count"] >= 1

    def test_buscar_output_contiene_carpeta_base(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar", ["*.txt"])
        assert str(self._base) in result.output

    def test_buscar_data_tiene_campos_esperados(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar", ["*.txt"])
        assert "count" in result.data
        assert "patron" in result.data
        assert "carpeta" in result.data
        assert "resultados" in result.data

    def test_buscar_data_resultados_es_lista(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar", ["*.txt"])
        assert isinstance(result.data["resultados"], list)


# ===========================================================================
# 5. COMANDO BUSCAR-EXT — BÚSQUEDA POR EXTENSIÓN
# ===========================================================================

class TestBuscarExt:
    """'buscar-ext' debe encontrar archivos por extensión."""

    @pytest.fixture(autouse=True)
    def workspace_tmp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "script1.py").write_text("print(1)")
            (base / "script2.py").write_text("print(2)")
            (base / "notas.txt").write_text("notas")
            (base / "datos.csv").write_bytes(b"a,b,c")
            sub = base / "sub"
            sub.mkdir()
            (sub / "script3.py").write_text("print(3)")
            self._base = base
            yield base

    def test_buscar_ext_sin_args_retorna_error(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        result = skill.execute("buscar-ext", [])
        assert result.success is False

    def test_buscar_ext_py_encuentra_py(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-ext", [".py"])
        assert result.success is True
        assert result.data["count"] >= 2  # script1.py y script2.py

    def test_buscar_ext_sin_punto_normaliza(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-ext", ["py"])  # sin punto
        assert result.success is True
        assert result.data["count"] >= 2

    def test_buscar_ext_txt_encuentra_txt(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-ext", [".txt"])
        assert result.success is True
        assert result.data["count"] >= 1

    def test_buscar_ext_inexistente_count_0(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-ext", [".xyz_no_existe"])
        assert result.success is True
        assert result.data["count"] == 0

    def test_buscar_ext_recursivo_incluye_subcarpetas(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-ext", [".py"])
        # Debe incluir script3.py de la subcarpeta
        assert result.success is True
        assert result.data["count"] >= 3

    def test_buscar_ext_no_recursivo_excluye_subcarpetas(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-ext", [".py", "--no-recursivo"])
        # Solo script1.py y script2.py
        assert result.success is True
        assert result.data["count"] == 2

    def test_buscar_ext_max_funciona(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-ext", [".py", "--max", "1"])
        assert result.success is True
        assert result.data["count"] <= 1

    def test_buscar_ext_solo_retorna_archivos(self):
        """buscar-ext siempre filtra solo archivos, no carpetas."""
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-ext", [".py"])
        for ruta in result.data.get("resultados", []):
            assert Path(ruta).is_file()

    def test_buscar_ext_data_tiene_campos(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-ext", [".py"])
        assert "count" in result.data
        assert "carpeta" in result.data
        assert "resultados" in result.data


# ===========================================================================
# 6. COMANDO BUSCAR-TEXTO — BÚSQUEDA POR CONTENIDO
# ===========================================================================

class TestBuscarTexto:
    """'buscar-texto' debe encontrar archivos que contengan el texto dado."""

    @pytest.fixture(autouse=True)
    def workspace_tmp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            # Archivos con distintos contenidos
            (base / "a.py").write_text("import os\nimport sys\n# TODO: refactorizar")
            (base / "b.py").write_text("def hola():\n    print('hola mundo')")
            (base / "c.txt").write_text("Este archivo contiene TODO y notas")
            (base / "d.txt").write_text("Sin palabras especiales aquí")
            sub = base / "sub"
            sub.mkdir()
            (sub / "e.py").write_text("# TODO: implementar función")
            self._base = base
            yield base

    def test_buscar_texto_sin_args_retorna_error(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        result = skill.execute("buscar-texto", [])
        assert result.success is False

    def test_buscar_texto_encuentra_archivos_con_texto(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-texto", ["TODO"])
        assert result.success is True
        assert result.data["count"] >= 2  # a.py, c.txt y e.py

    def test_buscar_texto_case_insensitive(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-texto", ["todo"])
        assert result.success is True
        assert result.data["count"] >= 2

    def test_buscar_texto_no_existe_count_0(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-texto", ["TEXTO_QUE_NO_EXISTE_XYZ_AURA"])
        assert result.success is True
        assert result.data["count"] == 0

    def test_buscar_texto_sin_resultados_output_sin_resultados(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-texto", ["NADA_XYZ_AURA"])
        assert "sin resultados" in result.output.lower()

    def test_buscar_texto_recursivo_incluye_subcarpetas(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-texto", ["TODO"])
        # e.py en subcarpeta también tiene TODO
        assert result.success is True
        rutas = result.data.get("resultados", [])
        nombres = [Path(r).name for r in rutas]
        assert "e.py" in nombres

    def test_buscar_texto_no_recursivo_excluye_subcarpetas(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-texto", ["TODO", "--no-recursivo"])
        # e.py en subcarpeta NO debe aparecer
        rutas = result.data.get("resultados", [])
        nombres = [Path(r).name for r in rutas]
        assert "e.py" not in nombres

    def test_buscar_texto_max_limita_resultados(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-texto", ["TODO", "--max", "1"])
        assert result.success is True
        assert result.data["count"] <= 1

    def test_buscar_texto_data_tiene_campos(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-texto", ["TODO"])
        assert "count" in result.data
        assert "texto" in result.data
        assert "carpeta" in result.data
        assert "resultados" in result.data

    def test_buscar_texto_output_contiene_linea(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-texto", ["TODO"])
        # El output debe mencionar el número de línea
        assert "línea" in result.output.lower() or "linea" in result.output.lower()

    def test_buscar_texto_output_contiene_nombre_archivo(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-texto", ["import"])
        # a.py tiene "import os" — debe aparecer en el output
        assert "a.py" in result.output

    def test_buscar_texto_output_menciona_limite_mb(self):
        from skills.builtin.search_skill import SearchSkill
        skill = SearchSkill()
        with patch.object(skill, "_workspace", return_value=self._base):
            result = skill.execute("buscar-texto", ["TODO"])
        assert "mb" in result.output.lower() or "MB" in result.output


# ===========================================================================
# 7. PARSING DE FLAGS COMUNES
# ===========================================================================

class TestParsingFlags:
    """Los flags comunes deben parsearse correctamente."""

    @pytest.fixture(autouse=True)
    def skill(self):
        from skills.builtin.search_skill import SearchSkill
        self._skill = SearchSkill()

    def test_default_recursivo_es_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            with patch.object(self._skill, "_workspace", return_value=base):
                args_limpios, carpeta, recursivo, max_res, tipo = \
                    self._skill._parse_common_flags(["*.py"])
        assert recursivo is True

    def test_no_recursivo_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            with patch.object(self._skill, "_workspace", return_value=base):
                _, _, recursivo, _, _ = self._skill._parse_common_flags(["*.py", "--no-recursivo"])
        assert recursivo is False

    def test_max_flag_numerico(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            with patch.object(self._skill, "_workspace", return_value=base):
                _, _, _, max_res, _ = self._skill._parse_common_flags(["*.py", "--max", "5"])
        assert max_res == 5

    def test_max_invalido_usa_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            with patch.object(self._skill, "_workspace", return_value=base):
                _, _, _, max_res, _ = self._skill._parse_common_flags(["*.py", "--max", "abc"])
        assert max_res == 50  # default

    def test_tipo_archivo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            with patch.object(self._skill, "_workspace", return_value=base):
                _, _, _, _, tipo = self._skill._parse_common_flags(["*.py", "--tipo", "archivo"])
        assert tipo == "archivo"

    def test_tipo_carpeta(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            with patch.object(self._skill, "_workspace", return_value=base):
                _, _, _, _, tipo = self._skill._parse_common_flags(["*", "--tipo", "carpeta"])
        assert tipo == "carpeta"

    def test_tipo_invalido_es_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            with patch.object(self._skill, "_workspace", return_value=base):
                _, _, _, _, tipo = self._skill._parse_common_flags(["*", "--tipo", "invalido"])
        assert tipo is None

    def test_en_flag_establece_carpeta(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            sub = base / "sub"
            sub.mkdir()
            with patch.object(self._skill, "_workspace", return_value=base):
                _, carpeta, _, _, _ = self._skill._parse_common_flags(
                    ["*.py", "en", str(sub)]
                )
        assert carpeta == sub

    def test_args_limpios_excluye_flags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            with patch.object(self._skill, "_workspace", return_value=base):
                args_limpios, _, _, _, _ = self._skill._parse_common_flags(
                    ["*.py", "--max", "10", "--no-recursivo"]
                )
        assert args_limpios == ["*.py"]


# ===========================================================================
# 8. HELPERS INTERNOS
# ===========================================================================

class TestHelpers:
    """Los helpers internos deben funcionar correctamente."""

    @pytest.fixture(autouse=True)
    def skill(self):
        from skills.builtin.search_skill import SearchSkill
        self._skill = SearchSkill()

    def test_workspace_retorna_path(self):
        result = self._skill._workspace()
        assert isinstance(result, Path)

    def test_resolve_ruta_absoluta(self):
        ruta = "/tmp/test.txt"
        resultado = self._skill._resolve(ruta)
        assert resultado.is_absolute()

    def test_resolve_ruta_relativa_usa_workspace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            with patch.object(self._skill, "_workspace", return_value=base):
                resultado = self._skill._resolve("subdir/archivo.txt")
        assert str(base) in str(resultado)

    def test_fmt_size_bytes(self):
        assert "B" in self._skill._fmt_size(500)

    def test_fmt_size_kb(self):
        assert "KB" in self._skill._fmt_size(2048)

    def test_fmt_size_mb(self):
        assert "MB" in self._skill._fmt_size(2 * 1024 * 1024)


# ===========================================================================
# 9. HANDLES Y COMPATIBILIDAD CON BASESKILL
# ===========================================================================

class TestHandles:
    """Los métodos heredados de BaseSkill deben funcionar."""

    @pytest.fixture(autouse=True)
    def skill(self):
        from skills.builtin.search_skill import SearchSkill
        self._skill = SearchSkill()

    def test_handles_buscar(self):
        assert self._skill.handles("buscar") is True

    def test_handles_buscar_ext(self):
        assert self._skill.handles("buscar-ext") is True

    def test_handles_buscar_texto(self):
        assert self._skill.handles("buscar-texto") is True

    def test_handles_desconocido_false(self):
        assert self._skill.handles("comando_que_no_existe") is False

    def test_name_property(self):
        assert self._skill.name == "search_skill"

    def test_display_name_property(self):
        assert self._skill.display_name == "Búsqueda"

    def test_version_property(self):
        assert self._skill.version == "1.0.0"

    def test_commands_property_es_lista(self):
        assert isinstance(self._skill.commands, list)

    def test_repr_contiene_nombre(self):
        assert "search_skill" in repr(self._skill)


# ===========================================================================
# 10. INTEGRACIÓN CON SKILLREGISTRY
# ===========================================================================

class TestIntegracionRegistry:
    """SearchSkill debe integrarse correctamente con el SkillRegistry."""

    def test_search_skill_registrable(self):
        from skills.skill_registry import SkillRegistry
        from skills.builtin.search_skill import SearchSkill
        reg = SkillRegistry()
        skill = SearchSkill()
        reg.register(skill)
        assert reg.get("search_skill") is not None

    def test_find_by_command_buscar(self):
        from skills.skill_registry import SkillRegistry
        from skills.builtin.search_skill import SearchSkill
        reg = SkillRegistry()
        reg.register(SearchSkill())
        entry = reg.find_by_command("buscar")
        assert entry is not None
        assert entry.name == "search_skill"

    def test_find_by_command_buscar_ext(self):
        from skills.skill_registry import SkillRegistry
        from skills.builtin.search_skill import SearchSkill
        reg = SkillRegistry()
        reg.register(SearchSkill())
        entry = reg.find_by_command("buscar-ext")
        assert entry is not None

    def test_find_by_command_buscar_texto(self):
        from skills.skill_registry import SkillRegistry
        from skills.builtin.search_skill import SearchSkill
        reg = SkillRegistry()
        reg.register(SearchSkill())
        entry = reg.find_by_command("buscar-texto")
        assert entry is not None

    def test_disable_enable_funciona(self):
        from skills.skill_registry import SkillRegistry
        from skills.builtin.search_skill import SearchSkill
        reg = SkillRegistry()
        reg.register(SearchSkill())
        reg.disable("search_skill")
        assert reg.find_by_command("buscar") is None
        reg.enable("search_skill")
        assert reg.find_by_command("buscar") is not None

    def test_execute_via_registry(self):
        from skills.skill_registry import SkillRegistry
        from skills.builtin.search_skill import SearchSkill
        reg = SkillRegistry()
        reg.register(SearchSkill())
        # buscar sin args → debe retornar error (pero no lanzar excepción)
        result = reg.execute("search_skill", "buscar", [])
        assert result is not None
        assert result.success is False

    def test_discover_builtin_incluye_search_skill(self):
        from skills.skill_registry import SkillRegistry
        reg = SkillRegistry()
        reg.discover_builtin()
        assert reg.get("search_skill") is not None

    def test_discover_builtin_idempotente(self):
        from skills.skill_registry import SkillRegistry
        reg = SkillRegistry()
        reg.discover_builtin()
        count_1 = len(reg.list_all())
        reg.discover_builtin()
        count_2 = len(reg.list_all())
        assert count_1 == count_2

    def test_discover_incluye_todas_las_skills_builtin(self):
        from skills.skill_registry import SkillRegistry
        reg = SkillRegistry()
        reg.discover_builtin()
        nombres = [e.skill.name for e in reg.list_all()]
        assert "demo_skill" in nombres
        assert "system_skill" in nombres
        assert "files_skill" in nombres
        assert "search_skill" in nombres

    def test_execute_buscar_via_registry_con_workspace_tmp(self):
        from skills.skill_registry import SkillRegistry
        from skills.builtin.search_skill import SearchSkill
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "test.py").write_text("print('ok')")

            reg = SkillRegistry()
            skill = SearchSkill()
            with patch.object(skill, "_workspace", return_value=base):
                reg.register(skill)
                result = reg.execute("search_skill", "buscar", ["*.py"])

        assert result is not None
        assert result.success is True
        assert result.data["count"] >= 1


# ===========================================================================
# 11. SINTAXIS Y COMPILACIÓN
# ===========================================================================

class TestSintaxis:
    """El archivo debe tener sintaxis Python válida."""

    def test_sintaxis_search_skill(self):
        import py_compile
        ruta = PROJECT_ROOT / "skills" / "builtin" / "search_skill.py"
        py_compile.compile(str(ruta), doraise=True)

    def test_sintaxis_builtin_init(self):
        import py_compile
        ruta = PROJECT_ROOT / "skills" / "builtin" / "__init__.py"
        py_compile.compile(str(ruta), doraise=True)

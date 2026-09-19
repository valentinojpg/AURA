"""
AURA — Tests automáticos Fase 18: WebSkill

Suite de tests para verificar la implementación completa de WebSkill:
  - Metadatos y estructura de la skill
  - Comando 'abrir-url'
  - Comando 'buscar-web'
  - Comando 'favoritos-web' (listar)
  - Comando 'agregar-favorito'
  - Comando 'quitar-favorito'
  - Validación de URLs y esquemas
  - Persistencia JSON
  - Favoritos builtin predefinidos
  - Prioridad usuario > builtin
  - Casos de error y validaciones
  - Regresión de imports
"""

from __future__ import annotations

import json
import py_compile
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Asegurar root del proyecto en sys.path ────────────────────────────────

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Importaciones bajo prueba ─────────────────────────────────────────────

from skills.builtin.web_skill import (
    WebSkill,
    _BUILTIN_FAVORITES,
    _SEARCH_ENGINES,
    _ALLOWED_SCHEMES,
    _FAVORITES_FILE,
)
from skills.skill_base import SkillMeta, SkillResult, CATEGORY_WEB


# ── Helper: instancia aislada ──────────────────────────────────────────────

def _make_skill(tmp_dir: Path | None = None) -> WebSkill:
    """
    Retorna una instancia de WebSkill con el archivo de persistencia
    apuntando a un directorio temporal.
    """
    import skills.builtin.web_skill as mod
    orig_file = mod._FAVORITES_FILE
    if tmp_dir is not None:
        mod._FAVORITES_FILE = tmp_dir / "web_favorites.json"
    skill = WebSkill()
    skill.setup()
    mod._FAVORITES_FILE = orig_file
    return skill


# ===========================================================================
# 1. Sintaxis y estructura estática
# ===========================================================================

class TestSintaxis(unittest.TestCase):

    def test_sintaxis_valida(self):
        path = _ROOT / "skills" / "builtin" / "web_skill.py"
        py_compile.compile(str(path), doraise=True)

    def test_importable(self):
        from skills.builtin.web_skill import WebSkill  # noqa: F401


class TestMetadatos(unittest.TestCase):

    def test_meta_existe(self):
        self.assertTrue(hasattr(WebSkill, "META"))

    def test_meta_es_skillmeta(self):
        self.assertIsInstance(WebSkill.META, SkillMeta)

    def test_meta_name(self):
        self.assertEqual(WebSkill.META.name, "web_skill")

    def test_meta_version(self):
        self.assertRegex(WebSkill.META.version, r"^\d+\.\d+\.\d+$")

    def test_meta_display_name(self):
        self.assertEqual(WebSkill.META.display_name, "Web")

    def test_meta_description_no_vacia(self):
        self.assertTrue(len(WebSkill.META.description) > 10)

    def test_meta_category(self):
        self.assertEqual(WebSkill.META.category, CATEGORY_WEB)

    def test_meta_builtin(self):
        self.assertTrue(WebSkill.META.builtin)

    def test_meta_enabled_by_default(self):
        self.assertTrue(WebSkill.META.enabled_by_default)

    def test_meta_commands_correctos(self):
        esperados = {
            "abrir-url",
            "buscar-web",
            "favoritos-web",
            "agregar-favorito",
            "quitar-favorito",
        }
        self.assertEqual(set(WebSkill.META.commands), esperados)

    def test_meta_exactamente_5_comandos(self):
        self.assertEqual(len(WebSkill.META.commands), 5)


class TestHerencia(unittest.TestCase):

    def test_hereda_base_skill(self):
        from skills.skill_base import BaseSkill
        self.assertTrue(issubclass(WebSkill, BaseSkill))

    def test_instanciable(self):
        self.assertIsNotNone(WebSkill())

    def test_execute_callable(self):
        self.assertTrue(callable(WebSkill.execute))

    def test_handles_abrir_url(self):
        self.assertTrue(WebSkill().handles("abrir-url"))

    def test_handles_buscar_web(self):
        self.assertTrue(WebSkill().handles("buscar-web"))

    def test_handles_favoritos_web(self):
        self.assertTrue(WebSkill().handles("favoritos-web"))

    def test_handles_agregar_favorito(self):
        self.assertTrue(WebSkill().handles("agregar-favorito"))

    def test_handles_quitar_favorito(self):
        self.assertTrue(WebSkill().handles("quitar-favorito"))

    def test_no_handles_desconocido(self):
        self.assertFalse(WebSkill().handles("xyz_inexistente"))


# ===========================================================================
# 2. Ciclo de vida
# ===========================================================================

class TestCicloDeVida(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self) -> WebSkill:
        import skills.builtin.web_skill as mod
        orig = mod._FAVORITES_FILE
        mod._FAVORITES_FILE = self.tmp / "web_favorites.json"
        skill = WebSkill()
        skill.setup()
        mod._FAVORITES_FILE = orig
        return skill

    def test_setup_inicializa_user_favorites(self):
        skill = self._make()
        self.assertIsInstance(skill._user_favorites, dict)

    def test_setup_is_setup_true(self):
        skill = self._make()
        self.assertTrue(skill.is_setup)

    def test_teardown_is_setup_false(self):
        skill = self._make()
        skill.teardown()
        self.assertFalse(skill.is_setup)

    def test_setup_carga_favoritos_existentes(self):
        fav_file = self.tmp / "web_favorites.json"
        fav_file.write_text(
            json.dumps({"mi-sitio": "https://ejemplo.com"}),
            encoding="utf-8",
        )
        import skills.builtin.web_skill as mod
        orig = mod._FAVORITES_FILE
        mod._FAVORITES_FILE = fav_file
        skill = WebSkill()
        skill.setup()
        mod._FAVORITES_FILE = orig
        self.assertIn("mi-sitio", skill._user_favorites)

    def test_setup_json_invalido_no_falla(self):
        fav_file = self.tmp / "web_favorites.json"
        fav_file.write_text("{no es json}", encoding="utf-8")
        import skills.builtin.web_skill as mod
        orig = mod._FAVORITES_FILE
        mod._FAVORITES_FILE = fav_file
        skill = WebSkill()
        skill.setup()
        mod._FAVORITES_FILE = orig
        self.assertEqual(skill._user_favorites, {})


# ===========================================================================
# 3. Comando 'abrir-url'
# ===========================================================================

class TestCmdAbrirUrl(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        import skills.builtin.web_skill as mod
        self._orig = mod._FAVORITES_FILE
        mod._FAVORITES_FILE = self.tmp / "web_favorites.json"
        self.mod = mod
        self._res_patcher = patch("core.app_resolver.resolve_app", return_value=MagicMock(success=False))
        self._res_patcher.start()
        self.skill = WebSkill()
        self.skill.setup()

    def tearDown(self):
        self._res_patcher.stop()
        self.mod._FAVORITES_FILE = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sin_args_retorna_error(self):
        r = self.skill.execute("abrir-url", [])
        self.assertFalse(r.success)
        self.assertIn("Uso:", r.error)

    def test_url_invalida_esquema_retorna_error(self):
        r = self.skill.execute("abrir-url", ["javascript:alert(1)"])
        self.assertFalse(r.success)

    def test_url_http_valida(self):
        with patch("webbrowser.open", return_value=True):
            r = self.skill.execute("abrir-url", ["http://ejemplo.com"])
        self.assertTrue(r.success)

    def test_url_https_valida(self):
        with patch("webbrowser.open", return_value=True):
            r = self.skill.execute("abrir-url", ["https://www.google.com"])
        self.assertTrue(r.success)

    def test_url_sin_esquema_se_normaliza(self):
        """www.python.org → https://www.python.org"""
        with patch("webbrowser.open", return_value=True) as mock_wb:
            r = self.skill.execute("abrir-url", ["www.python.org"])
        self.assertTrue(r.success)
        # Verificar que se llamó con https://
        call_args = mock_wb.call_args[0][0]
        self.assertTrue(call_args.startswith("https://"))

    def test_url_sin_www_se_normaliza(self):
        """python.org → https://python.org"""
        with patch("webbrowser.open", return_value=True) as mock_wb:
            r = self.skill.execute("abrir-url", ["python.org"])
        call_args = mock_wb.call_args[0][0]
        self.assertTrue(call_args.startswith("https://"))

    def test_abrir_por_nombre_de_favorito_builtin(self):
        """abrir-url google → abre https://www.google.com"""
        with patch("webbrowser.open", return_value=True) as mock_wb:
            r = self.skill.execute("abrir-url", ["google"])
        self.assertTrue(r.success)
        call_args = mock_wb.call_args[0][0]
        self.assertIn("google.com", call_args)

    def test_abrir_por_nombre_de_favorito_usuario(self):
        self.skill._user_favorites["mi-sitio"] = "https://ejemplo.com"
        with patch("webbrowser.open", return_value=True) as mock_wb:
            r = self.skill.execute("abrir-url", ["mi-sitio"])
        self.assertTrue(r.success)
        call_args = mock_wb.call_args[0][0]
        self.assertIn("ejemplo.com", call_args)

    def test_webbrowser_false_retorna_error(self):
        with patch("webbrowser.open", return_value=False):
            r = self.skill.execute("abrir-url", ["https://ejemplo.com"])
        self.assertFalse(r.success)
        self.assertIn("navegador", r.error.lower())

    def test_webbrowser_excepcion_retorna_error(self):
        with patch("webbrowser.open", side_effect=OSError("no navegador")):
            r = self.skill.execute("abrir-url", ["https://ejemplo.com"])
        self.assertFalse(r.success)

    def test_data_contiene_url(self):
        with patch("webbrowser.open", return_value=True):
            r = self.skill.execute("abrir-url", ["https://ejemplo.com"])
        self.assertIn("url", r.data)

    def test_resultado_es_skill_result(self):
        r = self.skill.execute("abrir-url", [])
        self.assertIsInstance(r, SkillResult)

    def test_esquema_ftp_permitido(self):
        with patch("webbrowser.open", return_value=True):
            r = self.skill.execute("abrir-url", ["ftp://archivos.ejemplo.com"])
        self.assertTrue(r.success)

    def test_esquema_file_no_permitido(self):
        r = self.skill.execute("abrir-url", ["file:///etc/passwd"])
        self.assertFalse(r.success)
        self.assertIn("permitido", r.error.lower())


# ===========================================================================
# 4. Comando 'buscar-web'
# ===========================================================================

class TestCmdBuscarWeb(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        import skills.builtin.web_skill as mod
        self._orig = mod._FAVORITES_FILE
        mod._FAVORITES_FILE = self.tmp / "web_favorites.json"
        self.mod = mod
        self._res_patcher = patch("core.app_resolver.resolve_app", return_value=MagicMock(success=False))
        self._res_patcher.start()
        self.skill = WebSkill()
        self.skill.setup()

    def tearDown(self):
        self._res_patcher.stop()
        self.mod._FAVORITES_FILE = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sin_args_retorna_error(self):
        r = self.skill.execute("buscar-web", [])
        self.assertFalse(r.success)
        self.assertIn("Uso:", r.error)

    def test_busqueda_simple_abre_google_por_defecto(self):
        with patch("webbrowser.open", return_value=True) as mock_wb:
            r = self.skill.execute("buscar-web", ["python tutorial"])
        self.assertTrue(r.success)
        url_abierta = mock_wb.call_args[0][0]
        self.assertIn("google.com", url_abierta)

    def test_busqueda_con_motor_bing(self):
        with patch("webbrowser.open", return_value=True) as mock_wb:
            r = self.skill.execute("buscar-web", ["python", "--motor", "bing"])
        self.assertTrue(r.success)
        url_abierta = mock_wb.call_args[0][0]
        self.assertIn("bing.com", url_abierta)

    def test_busqueda_con_motor_youtube(self):
        with patch("webbrowser.open", return_value=True) as mock_wb:
            r = self.skill.execute("buscar-web", ["musica", "--motor", "youtube"])
        self.assertTrue(r.success)
        url_abierta = mock_wb.call_args[0][0]
        self.assertIn("youtube.com", url_abierta)

    def test_busqueda_con_motor_duckduckgo(self):
        with patch("webbrowser.open", return_value=True) as mock_wb:
            r = self.skill.execute("buscar-web", ["privacidad", "--motor", "duckduckgo"])
        self.assertTrue(r.success)
        url_abierta = mock_wb.call_args[0][0]
        self.assertIn("duckduckgo.com", url_abierta)

    def test_busqueda_con_motor_github(self):
        with patch("webbrowser.open", return_value=True) as mock_wb:
            r = self.skill.execute("buscar-web", ["aura ai", "--motor", "github"])
        self.assertTrue(r.success)
        url_abierta = mock_wb.call_args[0][0]
        self.assertIn("github.com", url_abierta)

    def test_motor_invalido_retorna_error(self):
        r = self.skill.execute("buscar-web", ["algo", "--motor", "baidú"])
        self.assertFalse(r.success)
        self.assertIn("reconocido", r.error.lower())

    def test_motor_sin_nombre_retorna_error(self):
        r = self.skill.execute("buscar-web", ["algo", "--motor"])
        self.assertFalse(r.success)

    def test_terminos_codificados_en_url(self):
        """Los espacios y caracteres especiales deben estar URL-encoded."""
        with patch("webbrowser.open", return_value=True) as mock_wb:
            r = self.skill.execute("buscar-web", ["hola mundo"])
        url = mock_wb.call_args[0][0]
        # El espacio debe codificarse como + o %20
        self.assertTrue("hola" in url and "mundo" in url)

    def test_data_contiene_terminos_motor_url(self):
        with patch("webbrowser.open", return_value=True):
            r = self.skill.execute("buscar-web", ["python"])
        self.assertIn("terminos", r.data)
        self.assertIn("motor", r.data)
        self.assertIn("url", r.data)

    def test_output_menciona_terminos(self):
        with patch("webbrowser.open", return_value=True):
            r = self.skill.execute("buscar-web", ["python tutorial"])
        self.assertIn("python tutorial", r.output)

    def test_alias_ddg_equivale_a_duckduckgo(self):
        with patch("webbrowser.open", return_value=True) as mock_wb:
            r = self.skill.execute("buscar-web", ["privacidad", "--motor", "ddg"])
        self.assertTrue(r.success)
        url = mock_wb.call_args[0][0]
        self.assertIn("duckduckgo.com", url)

    def test_alias_yt_equivale_a_youtube(self):
        with patch("webbrowser.open", return_value=True) as mock_wb:
            r = self.skill.execute("buscar-web", ["musica", "--motor", "yt"])
        self.assertTrue(r.success)
        url = mock_wb.call_args[0][0]
        self.assertIn("youtube.com", url)


# ===========================================================================
# 5. Comando 'favoritos-web' (listar)
# ===========================================================================

class TestCmdListarFavoritos(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        import skills.builtin.web_skill as mod
        self._orig = mod._FAVORITES_FILE
        mod._FAVORITES_FILE = self.tmp / "web_favorites.json"
        self.mod = mod
        self.skill = WebSkill()
        self.skill.setup()

    def tearDown(self):
        self.mod._FAVORITES_FILE = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_listar_success_true(self):
        r = self.skill.execute("favoritos-web", [])
        self.assertTrue(r.success)

    def test_listar_retorna_skill_result(self):
        r = self.skill.execute("favoritos-web", [])
        self.assertIsInstance(r, SkillResult)

    def test_listar_contiene_favoritos_builtin(self):
        r = self.skill.execute("favoritos-web", [])
        self.assertIn("google", r.output)

    def test_listar_data_tiene_total(self):
        r = self.skill.execute("favoritos-web", [])
        self.assertIn("total", r.data)
        self.assertGreater(r.data["total"], 0)

    def test_listar_data_tiene_favoritos(self):
        r = self.skill.execute("favoritos-web", [])
        self.assertIn("favoritos", r.data)
        self.assertIsInstance(r.data["favoritos"], dict)

    def test_listar_muestra_favorito_usuario(self):
        self.skill._user_favorites["mi-sitio"] = "https://ejemplo.com"
        r = self.skill.execute("favoritos-web", [])
        self.assertIn("mi-sitio", r.output)

    def test_listar_seccion_predefinidos(self):
        r = self.skill.execute("favoritos-web", [])
        self.assertIn("predefinidos", r.output.lower())

    def test_listar_seccion_mis_favoritos_cuando_hay(self):
        self.skill._user_favorites["mi-sitio"] = "https://ejemplo.com"
        r = self.skill.execute("favoritos-web", [])
        self.assertIn("favoritos", r.output.lower())

    def test_listar_instruccion_agregar(self):
        r = self.skill.execute("favoritos-web", [])
        self.assertIn("agregar-favorito", r.output)


# ===========================================================================
# 6. Comando 'agregar-favorito'
# ===========================================================================

class TestCmdAgregarFavorito(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        import skills.builtin.web_skill as mod
        self._orig = mod._FAVORITES_FILE
        mod._FAVORITES_FILE = self.tmp / "web_favorites.json"
        self.mod = mod
        self.skill = WebSkill()
        self.skill.setup()

    def tearDown(self):
        self.mod._FAVORITES_FILE = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sin_args_retorna_error(self):
        r = self.skill.execute("agregar-favorito", [])
        self.assertFalse(r.success)
        self.assertIn("Uso:", r.error)

    def test_con_solo_nombre_retorna_error(self):
        r = self.skill.execute("agregar-favorito", ["mi-sitio"])
        self.assertFalse(r.success)

    def test_agregar_valido_success(self):
        r = self.skill.execute(
            "agregar-favorito", ["mi-sitio", "https://ejemplo.com"]
        )
        self.assertTrue(r.success)

    def test_agregar_almacena_en_user_favorites(self):
        self.skill.execute("agregar-favorito", ["mi-sitio", "https://ejemplo.com"])
        self.assertIn("mi-sitio", self.skill._user_favorites)
        self.assertEqual(self.skill._user_favorites["mi-sitio"], "https://ejemplo.com")

    def test_agregar_persiste_en_json(self):
        import skills.builtin.web_skill as mod
        self.skill.execute("agregar-favorito", ["mi-sitio", "https://ejemplo.com"])
        fav_file = mod._FAVORITES_FILE
        self.assertTrue(fav_file.exists())
        data = json.loads(fav_file.read_text(encoding="utf-8"))
        self.assertIn("mi-sitio", data)

    def test_agregar_nombre_con_espacio_retorna_error(self):
        r = self.skill.execute("agregar-favorito", ["mi sitio", "https://ejemplo.com"])
        self.assertFalse(r.success)
        self.assertIn("espacio", r.error.lower())

    def test_agregar_url_sin_esquema_normaliza(self):
        r = self.skill.execute("agregar-favorito", ["mi-sitio", "ejemplo.com"])
        self.assertTrue(r.success)
        self.assertEqual(self.skill._user_favorites["mi-sitio"], "https://ejemplo.com")

    def test_agregar_url_esquema_invalido_retorna_error(self):
        r = self.skill.execute(
            "agregar-favorito", ["mal", "javascript:void(0)"]
        )
        self.assertFalse(r.success)

    def test_agregar_sobreescribe_existente(self):
        self.skill.execute("agregar-favorito", ["mi-sitio", "https://viejo.com"])
        r = self.skill.execute("agregar-favorito", ["mi-sitio", "https://nuevo.com"])
        self.assertTrue(r.success)
        self.assertIn("actualizado", r.output.lower())
        self.assertEqual(self.skill._user_favorites["mi-sitio"], "https://nuevo.com")

    def test_agregar_nuevo_dice_agregado(self):
        r = self.skill.execute("agregar-favorito", ["nuevo", "https://nuevo.com"])
        self.assertIn("agregado", r.output.lower())

    def test_data_contiene_nombre_y_url(self):
        r = self.skill.execute("agregar-favorito", ["mi-sitio", "https://ejemplo.com"])
        self.assertEqual(r.data["nombre"], "mi-sitio")
        self.assertEqual(r.data["url"], "https://ejemplo.com")

    def test_nombre_guardado_en_minusculas(self):
        self.skill.execute("agregar-favorito", ["MI-SITIO", "https://ejemplo.com"])
        self.assertIn("mi-sitio", self.skill._user_favorites)

    def test_escritura_atomica_no_deja_tmp(self):
        self.skill.execute("agregar-favorito", ["mi-sitio", "https://ejemplo.com"])
        import skills.builtin.web_skill as mod
        tmp_file = mod._FAVORITES_FILE.with_suffix(".tmp")
        self.assertFalse(tmp_file.exists())


# ===========================================================================
# 7. Comando 'quitar-favorito'
# ===========================================================================

class TestCmdQuitarFavorito(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        import skills.builtin.web_skill as mod
        self._orig = mod._FAVORITES_FILE
        mod._FAVORITES_FILE = self.tmp / "web_favorites.json"
        self.mod = mod
        self.skill = WebSkill()
        self.skill.setup()
        self.skill._user_favorites["mi-sitio"] = "https://ejemplo.com"

    def tearDown(self):
        self.mod._FAVORITES_FILE = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sin_args_retorna_error(self):
        r = self.skill.execute("quitar-favorito", [])
        self.assertFalse(r.success)
        self.assertIn("Uso:", r.error)

    def test_quitar_usuario_success(self):
        r = self.skill.execute("quitar-favorito", ["mi-sitio"])
        self.assertTrue(r.success)

    def test_quitar_elimina_de_user_favorites(self):
        self.skill.execute("quitar-favorito", ["mi-sitio"])
        self.assertNotIn("mi-sitio", self.skill._user_favorites)

    def test_quitar_persiste_eliminacion(self):
        import skills.builtin.web_skill as mod
        self.skill._save_favorites()  # Guardar primero
        self.skill.execute("quitar-favorito", ["mi-sitio"])
        fav_file = mod._FAVORITES_FILE
        data = json.loads(fav_file.read_text(encoding="utf-8"))
        self.assertNotIn("mi-sitio", data)

    def test_quitar_favorito_builtin_retorna_error(self):
        r = self.skill.execute("quitar-favorito", ["google"])
        self.assertFalse(r.success)
        self.assertIn("predefinido", r.error.lower())

    def test_quitar_favorito_inexistente_retorna_error(self):
        r = self.skill.execute("quitar-favorito", ["no-existe"])
        self.assertFalse(r.success)

    def test_data_contiene_nombre_y_url_eliminada(self):
        r = self.skill.execute("quitar-favorito", ["mi-sitio"])
        self.assertEqual(r.data["nombre"], "mi-sitio")
        self.assertEqual(r.data["url_eliminada"], "https://ejemplo.com")

    def test_output_menciona_nombre(self):
        r = self.skill.execute("quitar-favorito", ["mi-sitio"])
        self.assertIn("mi-sitio", r.output)


# ===========================================================================
# 8. Validación de URLs
# ===========================================================================

class TestValidacionURL(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        import skills.builtin.web_skill as mod
        self._orig = mod._FAVORITES_FILE
        mod._FAVORITES_FILE = self.tmp / "web_favorites.json"
        self.mod = mod
        self.skill = WebSkill()
        self.skill.setup()

    def tearDown(self):
        self.mod._FAVORITES_FILE = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_normalizar_url_sin_esquema(self):
        resultado = self.skill._normalizar_url("www.ejemplo.com")
        self.assertTrue(resultado.startswith("https://"))

    def test_normalizar_url_con_https_no_cambia(self):
        url = "https://www.ejemplo.com"
        self.assertEqual(self.skill._normalizar_url(url), url)

    def test_normalizar_url_con_http_no_cambia(self):
        url = "http://www.ejemplo.com"
        self.assertEqual(self.skill._normalizar_url(url), url)

    def test_validar_esquema_https_ok(self):
        self.assertIsNone(self.skill._validar_esquema("https://ejemplo.com"))

    def test_validar_esquema_http_ok(self):
        self.assertIsNone(self.skill._validar_esquema("http://ejemplo.com"))

    def test_validar_esquema_ftp_ok(self):
        self.assertIsNone(self.skill._validar_esquema("ftp://ejemplo.com"))

    def test_validar_esquema_javascript_no_ok(self):
        self.assertIsNotNone(self.skill._validar_esquema("javascript:alert(1)"))

    def test_validar_esquema_file_no_ok(self):
        self.assertIsNotNone(self.skill._validar_esquema("file:///etc/passwd"))

    def test_validar_esquema_data_no_ok(self):
        self.assertIsNotNone(self.skill._validar_esquema("data:text/html,<h1>"))

    def test_allowed_schemes_contiene_https(self):
        self.assertIn("https", _ALLOWED_SCHEMES)

    def test_allowed_schemes_contiene_http(self):
        self.assertIn("http", _ALLOWED_SCHEMES)

    def test_allowed_schemes_contiene_ftp(self):
        self.assertIn("ftp", _ALLOWED_SCHEMES)

    def test_allowed_schemes_no_contiene_javascript(self):
        self.assertNotIn("javascript", _ALLOWED_SCHEMES)

    def test_allowed_schemes_no_contiene_file(self):
        self.assertNotIn("file", _ALLOWED_SCHEMES)


# ===========================================================================
# 9. Motores de búsqueda
# ===========================================================================

class TestMotoresBusqueda(unittest.TestCase):

    def test_search_engines_no_vacio(self):
        self.assertGreater(len(_SEARCH_ENGINES), 0)

    def test_contiene_google(self):
        self.assertIn("google", _SEARCH_ENGINES)

    def test_contiene_bing(self):
        self.assertIn("bing", _SEARCH_ENGINES)

    def test_contiene_duckduckgo(self):
        self.assertIn("duckduckgo", _SEARCH_ENGINES)

    def test_contiene_youtube(self):
        self.assertIn("youtube", _SEARCH_ENGINES)

    def test_contiene_github(self):
        self.assertIn("github", _SEARCH_ENGINES)

    def test_todas_las_urls_tienen_esquema_https(self):
        for motor, url in _SEARCH_ENGINES.items():
            with self.subTest(motor=motor):
                self.assertTrue(
                    url.startswith("https://"),
                    f"Motor '{motor}' no usa HTTPS: {url}",
                )

    def test_todas_las_urls_son_strings_no_vacios(self):
        for motor, url in _SEARCH_ENGINES.items():
            with self.subTest(motor=motor):
                self.assertIsInstance(url, str)
                self.assertTrue(len(url) > 10)


# ===========================================================================
# 10. Favoritos builtin predefinidos
# ===========================================================================

class TestFavoritosBuiltin(unittest.TestCase):

    def test_builtin_no_vacio(self):
        self.assertGreater(len(_BUILTIN_FAVORITES), 0)

    def test_contiene_google(self):
        self.assertIn("google", _BUILTIN_FAVORITES)

    def test_contiene_youtube(self):
        self.assertIn("youtube", _BUILTIN_FAVORITES)

    def test_contiene_github(self):
        self.assertIn("github", _BUILTIN_FAVORITES)

    def test_todas_las_urls_son_strings(self):
        for nombre, url in _BUILTIN_FAVORITES.items():
            with self.subTest(nombre=nombre):
                self.assertIsInstance(url, str)
                self.assertTrue(url.startswith("https://"))

    def test_todos_los_nombres_minusculas(self):
        for nombre in _BUILTIN_FAVORITES:
            with self.subTest(nombre=nombre):
                self.assertEqual(nombre, nombre.lower())


# ===========================================================================
# 11. Prioridad usuario > builtin
# ===========================================================================

class TestPrioridadFavoritos(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        import skills.builtin.web_skill as mod
        self._orig = mod._FAVORITES_FILE
        mod._FAVORITES_FILE = self.tmp / "web_favorites.json"
        self.mod = mod
        self.skill = WebSkill()
        self.skill.setup()

    def tearDown(self):
        self.mod._FAVORITES_FILE = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_usuario_sobreescribe_builtin(self):
        self.skill._user_favorites["google"] = "https://mi-google-custom.com"
        url = self.skill._resolver_favorito("google")
        self.assertEqual(url, "https://mi-google-custom.com")

    def test_builtin_accesible_sin_sobreescritura(self):
        url = self.skill._resolver_favorito("google")
        self.assertIn("google.com", url)

    def test_favorito_inexistente_retorna_none(self):
        self.assertIsNone(self.skill._resolver_favorito("xyz_no_existe"))

    def test_todos_combina_builtin_y_usuario(self):
        self.skill._user_favorites["mi-sitio"] = "https://ejemplo.com"
        todos = self.skill._todos_los_favoritos()
        self.assertIn("mi-sitio", todos)
        self.assertIn("google", todos)


# ===========================================================================
# 12. Persistencia JSON
# ===========================================================================

class TestPersistencia(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self) -> WebSkill:
        import skills.builtin.web_skill as mod
        mod._FAVORITES_FILE = self.tmp / "web_favorites.json"
        skill = WebSkill()
        skill.setup()
        return skill

    def test_guardar_y_recargar(self):
        import skills.builtin.web_skill as mod
        s1 = self._make()
        s1.execute("agregar-favorito", ["test-sitio", "https://test.com"])
        s2 = self._make()
        self.assertIn("test-sitio", s2._user_favorites)

    def test_archivo_json_valido(self):
        import skills.builtin.web_skill as mod
        s = self._make()
        s.execute("agregar-favorito", ["test", "https://test.com"])
        data = json.loads(mod._FAVORITES_FILE.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)

    def test_archivo_no_existe_no_falla(self):
        import skills.builtin.web_skill as mod
        mod._FAVORITES_FILE = self.tmp / "no_existe.json"
        skill = WebSkill()
        skill.setup()
        self.assertEqual(skill._user_favorites, {})

    def test_escritura_atomica_no_deja_tmp(self):
        import skills.builtin.web_skill as mod
        s = self._make()
        s.execute("agregar-favorito", ["test", "https://test.com"])
        tmp_file = mod._FAVORITES_FILE.with_suffix(".tmp")
        self.assertFalse(tmp_file.exists())


# ===========================================================================
# 13. Comando desconocido y casos borde
# ===========================================================================

class TestCasosBorde(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        import skills.builtin.web_skill as mod
        self._orig = mod._FAVORITES_FILE
        mod._FAVORITES_FILE = self.tmp / "web_favorites.json"
        self.mod = mod
        self.skill = WebSkill()
        self.skill.setup()

    def tearDown(self):
        self.mod._FAVORITES_FILE = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_comando_desconocido_retorna_error(self):
        r = self.skill.execute("xyz_desconocido", [])
        self.assertFalse(r.success)
        self.assertIn("xyz_desconocido", r.error)

    def test_resultado_booleano_false(self):
        r = self.skill.execute("abrir-url", [])
        self.assertFalse(bool(r))

    def test_resultado_booleano_true(self):
        r = self.skill.execute("favoritos-web", [])
        self.assertTrue(bool(r))

    def test_buscar_web_con_caracteres_especiales(self):
        with patch("webbrowser.open", return_value=True):
            r = self.skill.execute("buscar-web", ["c++ tutorial"])
        self.assertTrue(r.success)

    def test_buscar_web_con_tildes(self):
        with patch("webbrowser.open", return_value=True):
            r = self.skill.execute("buscar-web", ["programacion en español"])
        self.assertTrue(r.success)


# ===========================================================================
# 14. Exportaciones del paquete builtin
# ===========================================================================

class TestExportaciones(unittest.TestCase):

    def test_importable_desde_skills_builtin(self):
        from skills.builtin import WebSkill  # noqa: F401

    def test_en_all_de_builtin(self):
        import skills.builtin as pkg
        self.assertIn("WebSkill", pkg.__all__)

    def test_sintaxis_init_builtin(self):
        init_path = _ROOT / "skills" / "builtin" / "__init__.py"
        py_compile.compile(str(init_path), doraise=True)


# ===========================================================================
# 15. Regresión: skills previas siguen funcionando
# ===========================================================================

class TestRegresion(unittest.TestCase):

    def test_demo_skill_importable(self):
        from skills.builtin.demo_skill import DemoSkill  # noqa: F401

    def test_system_skill_importable(self):
        from skills.builtin.system_skill import SystemSkill  # noqa: F401

    def test_files_skill_importable(self):
        from skills.builtin.files_skill import FilesSkill  # noqa: F401

    def test_search_skill_importable(self):
        from skills.builtin.search_skill import SearchSkill  # noqa: F401

    def test_programs_skill_importable(self):
        from skills.builtin.programs_skill import ProgramsSkill  # noqa: F401

    def test_skills_init_importable(self):
        from skills import SkillRegistry, BaseSkill  # noqa: F401

    def test_skill_registry_puede_registrar_web_skill(self):
        from skills.skill_registry import SkillRegistry
        tmp = Path(tempfile.mkdtemp())
        try:
            import skills.builtin.web_skill as mod
            orig = mod._FAVORITES_FILE
            mod._FAVORITES_FILE = tmp / "web_favorites.json"
            reg = SkillRegistry()
            instance = WebSkill()
            reg.register(instance)
            entry = reg.get("web_skill")
            self.assertIsNotNone(entry)
            reg.unregister("web_skill")
            mod._FAVORITES_FILE = orig
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

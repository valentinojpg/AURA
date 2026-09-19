"""
Tests para el IntentRouter, EntityResolver y el Pipeline Único de Mensajes de AURA.

Verifica:
  1. normalización (minúsculas, sin tildes).
  2. Parseo de 9 intenciones de acción en español y descarte de preguntas al LLM.
  3. Precedencia y resolución en EntityResolver (URL, alias, programas.json, which, psutil, rutas comunes).
  4. targets no resueltos con intent claro devuelven resolved=False.
  5. Pipeline único handle_user_message(texto, origen) para chat y voz.
  6. Confirmación de close_app.
  7. Flag ROUTER_FIRST en settings.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Asegurar que el directorio raíz del proyecto esté en sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from aura.core.entity_resolver import (
    BUILTIN_ALIASES,
    EntityResolver,
    ResolvedEntity,
    entity_resolver,
    is_url_or_domain,
    resolve,
)
from aura.core.intent_router import (
    Intent,
    IntentRouter,
    intent_router,
    normalize,
    parse,
)
from config.settings import settings


# ───────────────────────────────────────────────────────────────────────────
# 1. Tests de normalización
# ───────────────────────────────────────────────────────────────────────────

class TestNormalize:
    def test_normalize_lowercase(self):
        assert normalize("NOTEPAD") == "notepad"
        assert normalize("ChRoMe") == "chrome"

    def test_normalize_tildes(self):
        assert normalize("cerrá") == "cerra"
        assert normalize("creá") == "crea"
        assert normalize("canción") == "cancion"
        assert normalize("último") == "ultimo"
        assert normalize("página") == "pagina"
        assert normalize("vídeo") == "video"
        assert normalize("vergüenza") == "verguenza"

    def test_normalize_empty_and_whitespace(self):
        assert normalize("") == ""
        assert normalize("   ") == ""
        assert normalize("  Abre Notepad  ") == "abre notepad"


# ───────────────────────────────────────────────────────────────────────────
# 2. Tests de parseo de intenciones (IntentRouter)
# ───────────────────────────────────────────────────────────────────────────

class TestIntentRouter:
    @pytest.fixture
    def router(self):
        return IntentRouter()

    def test_open_app(self, router):
        res = router.parse("abre notepad")
        assert res is not None
        assert res.nombre == "open_app"
        assert res.target == "notepad"
        assert res.raw == "abre notepad"

        res2 = router.parse("abre Notepad")
        assert res2 is not None
        assert res2.nombre == "open_app"
        assert res2.target == "notepad"

        res3 = router.parse("abrí la app spotify")
        assert res3 is not None
        assert res3.nombre == "open_app"
        assert res3.target == "spotify"

        res4 = router.parse("ejecuta calc")
        assert res4 is not None
        assert res4.nombre == "open_app"
        assert res4.target == "calc"

    def test_close_app(self, router):
        res = router.parse("cerrá chrome")
        assert res is not None
        assert res.nombre == "close_app"
        assert res.target == "chrome"

        res2 = router.parse("cierra el proceso notepad")
        assert res2 is not None
        assert res2.nombre == "close_app"
        assert res2.target == "notepad"

        res3 = router.parse("matar spotify")
        assert res3 is not None
        assert res3.nombre == "close_app"
        assert res3.target == "spotify"

    def test_open_url(self, router):
        res = router.parse("abre youtube.com")
        assert res is not None
        assert res.nombre == "open_url"
        assert res.target == "youtube.com"

        res2 = router.parse("abrir https://google.com")
        assert res2 is not None
        assert res2.nombre == "open_url"
        assert res2.target == "https://google.com"

        res3 = router.parse("navega a www.clarin.com")
        assert res3 is not None
        assert res3.nombre == "open_url"
        assert res3.target == "www.clarin.com"

    def test_create_folder(self, router):
        res = router.parse("creá carpeta pruebas")
        assert res is not None
        assert res.nombre == "create_folder"
        assert res.target == "pruebas"

        res2 = router.parse("crear una carpeta llamada proyectos")
        assert res2 is not None
        assert res2.nombre == "create_folder"
        assert res2.target == "proyectos"

        res3 = router.parse("nueva carpeta fotos")
        assert res3 is not None
        assert res3.nombre == "create_folder"
        assert res3.target == "fotos"

    def test_create_file(self, router):
        res = router.parse("creá archivo notas.txt")
        assert res is not None
        assert res.nombre == "create_file"
        assert res.target == "notas.txt"

        res2 = router.parse("crear archivo script.py")
        assert res2 is not None
        assert res2.nombre == "create_file"
        assert res2.target == "script.py"

    def test_search_file(self, router):
        res = router.parse("buscar archivo reporte.pdf")
        assert res is not None
        assert res.nombre == "search_file"
        assert res.target == "reporte.pdf"

        res2 = router.parse("busca *.py")
        assert res2 is not None
        assert res2.nombre == "search_file"
        assert res2.target == "*.py"

    def test_delete_file(self, router):
        res = router.parse("elimina archivo viejo.txt")
        assert res is not None
        assert res.nombre == "delete_file"
        assert res.target == "viejo.txt"

        res2 = router.parse("borrá carpeta pruebas")
        assert res2 is not None
        assert res2.nombre == "delete_file"
        assert res2.target == "pruebas"

    def test_move_file(self, router):
        res = router.parse("mover notas.txt a documentos")
        assert res is not None
        assert res.nombre == "move_file"
        assert "notas.txt" in res.target
        assert "documentos" in res.target

    def test_rename_file(self, router):
        res = router.parse("renombra notas.txt a apuntes.txt")
        assert res is not None
        assert res.nombre == "rename_file"
        assert "notas.txt" in res.target
        assert "apuntes.txt" in res.target

    def test_llm_questions_return_none(self, router):
        # Preguntas generales y conversación que deben ir al LLM
        assert router.parse("¿cómo funciona un dict?") is None
        assert router.parse("como funciona un diccionario") is None
        assert router.parse("hola, cómo estás?") is None
        assert router.parse("explicame la diferencia entre lista y tupla") is None
        assert router.parse("dame una receta de pastas") is None
        assert router.parse("quién sos?") is None
        assert router.parse("qué podés hacer?") is None
        assert router.parse("") is None


# ───────────────────────────────────────────────────────────────────────────
# 3. Tests de resolución de entidades (EntityResolver)
# ───────────────────────────────────────────────────────────────────────────

class TestEntityResolver:
    @pytest.fixture
    def resolver(self):
        return EntityResolver()

    def test_resolve_url(self, resolver):
        res = resolver.resolve("open_app", "youtube.com")
        assert res.resolved is True
        assert res.intent == "open_url"
        assert res.executable == "https://youtube.com"
        assert res.skill_name == "web_skill"
        assert res.command == "abrir-url"
        assert res.args == ["https://youtube.com"]

    def test_resolve_builtin_alias(self, resolver):
        res = resolver.resolve("open_app", "notepad")
        assert res.resolved is True
        assert res.intent == "open_app"
        assert res.executable == "notepad.exe"
        assert res.skill_name == "system_skill"
        assert res.command == "abrir"
        assert res.args == ["notepad.exe"]

        res_calc = resolver.resolve("open_app", "calc")
        assert res_calc.resolved is True
        assert res_calc.executable == "calc.exe"

    def test_resolve_builtin_alias_close_app(self, resolver):
        res = resolver.resolve("close_app", "chrome")
        assert res.resolved is True
        assert res.intent == "close_app"
        assert res.executable == "chrome.exe"
        assert res.skill_name == "system_skill"
        assert res.command == "cerrar"
        assert res.args == ["chrome.exe"]

    def test_resolve_user_favorites(self, resolver, tmp_path):
        # Simular lectura de data/programs.json
        mock_data = {"mi-app": r"C:\Custom\app.exe"}
        with patch("aura.core.entity_resolver._load_user_favorites", return_value=mock_data):
            res = resolver.resolve("open_app", "mi-app")
            assert res.resolved is True
            assert res.executable == r"C:\Custom\app.exe"
            assert res.skill_name == "programs_skill"

    def test_resolve_shutil_which(self, resolver):
        with patch("shutil.which", return_value=r"C:\Windows\System32\cmd.exe"):
            res = resolver.resolve("open_app", "cmd")
            assert res.resolved is True
            assert "cmd.exe" in res.executable

    def test_resolve_running_process_for_close(self, resolver):
        with patch("aura.core.entity_resolver._search_running_process", return_value="custom_worker.exe"):
            res = resolver.resolve("close_app", "custom_worker")
            assert res.resolved is True
            assert res.executable == "custom_worker.exe"
            assert res.command == "cerrar"

    def test_unresolved_target_returns_false(self, resolver):
        # target completamente desconocido
        with patch("shutil.which", return_value=None), \
             patch("aura.core.entity_resolver._search_running_process", return_value=None), \
             patch("aura.core.entity_resolver._search_common_program_paths", return_value=None), \
             patch("aura.core.entity_resolver._load_user_favorites", return_value={}):
            res = resolver.resolve("open_app", "aplicacion_fantasma_1234")
            assert res.resolved is False
            assert res.intent == "open_app"
            assert res.target == "aplicacion_fantasma_1234"

    def test_file_operations_resolve(self, resolver):
        res_folder = resolver.resolve("create_folder", "pruebas")
        assert res_folder.resolved is True
        assert res_folder.skill_name == "files_skill"
        assert res_folder.command == "crear"
        assert res_folder.args == ["pruebas", "--carpeta"]

        res_file = resolver.resolve("create_file", "notas.txt")
        assert res_file.resolved is True
        assert res_file.skill_name == "files_skill"
        assert res_file.command == "crear"
        assert res_file.args == ["notas.txt"]

        res_search = resolver.resolve("search_file", "reporte.pdf")
        assert res_search.resolved is True
        assert res_search.skill_name == "search_skill"
        assert res_search.command == "buscar"
        assert res_search.args == ["reporte.pdf"]

        res_del = resolver.resolve("delete_file", "viejo.txt")
        assert res_del.resolved is True
        assert res_del.skill_name == "files_skill"
        assert res_del.command == "eliminar"
        assert res_del.args == ["viejo.txt"]


# ───────────────────────────────────────────────────────────────────────────
# 4. Tests del pipeline único en ChatPage
# ───────────────────────────────────────────────────────────────────────────

class TestChatPagePipeline:
    @pytest.fixture
    def chat_page(self):
        import flet as ft
        from ui.pages.chat_page import ChatPage

        mock_page = MagicMock(spec=ft.Page)
        chat = ChatPage(page=mock_page)
        return chat

    def test_open_notepad_action_pipeline(self, chat_page):
        # "abre notepad" -> ejecuta system_skill abrir notepad.exe, no LLM
        with patch.object(chat_page, "_execute_resolved_skill_async") as mock_exec, \
             patch.object(chat_page, "_send_to_ai") as mock_ai:
            chat_page.handle_user_message("abre notepad", origen="chat")

            mock_exec.assert_called_once()
            entity = mock_exec.call_args[0][0]
            assert entity.resolved is True
            assert entity.intent == "open_app"
            assert entity.executable == "notepad.exe"
            mock_ai.assert_not_called()

    def test_open_notepad_by_voice(self, chat_page):
        # "abre Notepad" por voz -> origen="voz", burbuja con microfono, no LLM
        with patch.object(chat_page, "_execute_resolved_skill_async") as mock_exec, \
             patch.object(chat_page, "_send_to_ai") as mock_ai, \
             patch.object(chat_page, "_add_user_message") as mock_user_msg:
            chat_page.handle_user_message("abre Notepad", origen="voz")

            mock_user_msg.assert_called_once()
            bubble_content = mock_user_msg.call_args[0][0]
            assert "🎤 abre Notepad" in bubble_content

            mock_exec.assert_called_once()
            entity = mock_exec.call_args[0][0]
            assert entity.resolved is True
            assert entity.intent == "open_app"
            mock_ai.assert_not_called()

    def test_close_chrome_direct_and_with_confirmation(self, chat_page):
        # 1. Por defecto CONFIRMAR_CIERRE_APP=false -> ejecuta directo sin modal
        with patch.object(chat_page, "_handle_close_app_direct") as mock_direct, \
             patch.object(chat_page, "_send_to_ai") as mock_ai:
            chat_page.handle_user_message("cerrá chrome", origen="chat")
            mock_direct.assert_called_once()
            entity = mock_direct.call_args[0][0]
            assert entity.intent == "close_app"
            assert entity.executable == "chrome.exe"
            assert chat_page._pending_confirm_action is None
            mock_ai.assert_not_called()

        # 2. Con CONFIRMAR_CIERRE_APP=true -> pide confirmación modal
        with patch.object(settings, "get_bool", side_effect=lambda k, *a, **kw: True if k in ("CONFIRMAR_CIERRE_APP", "ROUTER_FIRST") else False), \
             patch.object(chat_page, "_handle_close_app_direct") as mock_direct, \
             patch.object(chat_page, "_send_to_ai") as mock_ai:
            chat_page.handle_user_message("cerrá chrome", origen="chat")
            assert chat_page._pending_confirm_action is not None
            mock_ai.assert_not_called()

            # Confirmar acción
            chat_page._pending_confirm_action()
            mock_direct.assert_called_once()

    def test_open_youtube_url(self, chat_page):
        # "abre youtube.com" -> web_skill abrir-url https://youtube.com
        with patch.object(chat_page, "_execute_resolved_skill_async") as mock_exec, \
             patch.object(chat_page, "_send_to_ai") as mock_ai:
            chat_page.handle_user_message("abre youtube.com", origen="chat")

            mock_exec.assert_called_once()
            entity = mock_exec.call_args[0][0]
            assert entity.resolved is True
            assert entity.intent == "open_url"
            assert entity.executable == "https://youtube.com"
            assert entity.command == "abrir-url"
            mock_ai.assert_not_called()

    def test_create_folder_action(self, chat_page):
        # "creá carpeta pruebas" -> files_skill crear pruebas --carpeta
        with patch.object(chat_page, "_execute_resolved_skill_async") as mock_exec, \
             patch.object(chat_page, "_send_to_ai") as mock_ai:
            chat_page.handle_user_message("creá carpeta pruebas", origen="chat")

            mock_exec.assert_called_once()
            entity = mock_exec.call_args[0][0]
            assert entity.resolved is True
            assert entity.intent == "create_folder"
            assert entity.args == ["pruebas", "--carpeta"]
            mock_ai.assert_not_called()

    def test_llm_question_goes_to_ai(self, chat_page):
        # "¿cómo funciona un dict?" -> sin intent de comando, va a IA
        with patch.object(chat_page, "_execute_resolved_skill_async") as mock_exec, \
             patch.object(chat_page, "_send_to_ai") as mock_ai:
            chat_page.handle_user_message("¿cómo funciona un dict?", origen="chat")

            mock_exec.assert_not_called()
            mock_ai.assert_called_once()
            args = mock_ai.call_args[0]
            assert "¿cómo funciona un dict?" in args[0]

    def test_unresolved_intent_asks_clarification_no_ai(self, chat_page):
        # "abre aplicacion_inexistente" -> intent claro pero no resuelve: inicia escaneo profundo sin ir a IA
        with patch.object(chat_page, "_execute_resolved_skill_async") as mock_exec, \
             patch.object(chat_page, "_send_to_ai") as mock_ai, \
             patch.object(chat_page, "_add_system_message") as mock_sys_msg:
            chat_page.handle_user_message("abre aplicacion_inexistente_99", origen="chat")

            mock_exec.assert_not_called()
            mock_ai.assert_not_called()
            mock_sys_msg.assert_called_once()
            sys_text = mock_sys_msg.call_args[0][0]
            assert "Buscando 'aplicacion_inexistente_99' en toda la PC" in sys_text

    def test_router_first_false_sends_everything_to_ai(self, chat_page):
        # Si ROUTER_FIRST=false, incluso "abre notepad" va directo a la IA
        with patch.object(settings, "get_bool", return_value=False), \
             patch.object(chat_page, "_execute_resolved_skill_async") as mock_exec, \
             patch.object(chat_page, "_send_to_ai") as mock_ai:
            chat_page.handle_user_message("abre notepad", origen="chat")

            mock_exec.assert_not_called()
            mock_ai.assert_called_once()

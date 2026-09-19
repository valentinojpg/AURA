"""
AURA — Página de Chat (Flet)

Pantalla de chat funcional con persistencia de conversaciones,
soporte para comandos de texto, streaming de IA y comandos de voz (Fases 7, 8, 9, 13, 22, 23).
"""

from __future__ import annotations

import json
import os
import re
import threading
import traceback
from datetime import datetime
from typing import Any, Iterator, Optional
import flet as ft

from ai import (
    ChatMessage,
    get_default_provider,
)
from core.command_router import command_router
from config.settings import settings
from aura.core.intent_router import intent_router, Intent
from aura.core.entity_resolver import entity_resolver, ResolvedEntity
from aura.core.planner import (
    Plan,
    is_destructive_plan,
    is_instruction_chain,
    plan_from_ai,
    plan_from_rules,
)
from data.conversation_store import ConversationStore, Conversation, StoredMessage
from ui.pages.base_page import BasePage
from ui.components.chat_bubble import ChatBubble
from ui.components.history_panel import HistoryPanel
from ui.components.audio_panel import AudioPanel
from aura.personality import (
    filter_content,
    sanitize_output,
    get_context_phrase,
    get_current_personality,
    get_generation_parameters,
    is_tone_request,
    apply_anti_loop,
)
from utils.logger import get_logger

_logger = get_logger("aura.ui.chat_page")

# Paleta
_BG_DARK        = "#0C0C18"
_INPUT_BG       = "#12122A"
_INPUT_BORDER   = "#1E1E3A"
_SEND_BTN_BG    = "#3B4FC8"
_CLEAR_BG       = "#1A1A30"
_MIC_BTN_BG     = "#1A1A30"
_MIC_ACTIVE_BG  = "#4A1A1A"
_STATUS_OK      = "#4CAF50"
_STATUS_WARN    = "#FBBF24"
_STATUS_ERR     = "#F87171"
_STATUS_MOCK    = "#A78BFA"

_MAX_INPUT_LEN = 4000
_MAX_CONTEXT_MESSAGES = 20
_TYPING_BLINK_MS = 500

_store = ConversationStore()


class _StatusBanner(ft.Container):
    """
    Banner de estado del proveedor de IA (compatible con tests de Fase 7).
    """

    def __init__(self, parent=None, **kwargs):
        super().__init__(**kwargs)
        self._dot = ft.Text("●", size=10, color="#555577")
        self._label = ft.Text("Conectando...", size=12, color="#555577")
        self.content = ft.Row([self._dot, self._label], spacing=6)

    def set_loading(self) -> None:
        self._dot.color = "#555577"
        self._label.value = "Conectando con el proveedor de IA..."
        self._label.color = "#555577"

    def set_ok(self, message: str) -> None:
        self._dot.color = _STATUS_OK
        self._label.value = f"✓  {message}"
        self._label.color = "#3A8A3A"

    def set_warning(self, message: str) -> None:
        self._dot.color = _STATUS_WARN
        self._label.value = f"⚠  {message}"
        self._label.color = "#A07A20"

    def set_error(self, message: str) -> None:
        self._dot.color = _STATUS_ERR
        self._label.value = f"✗  {message}"
        self._label.color = "#8A3A3A"

    def set_mock(self, message: str) -> None:
        self._dot.color = _STATUS_MOCK
        self._label.value = f"◆  {message}"
        self._label.color = "#6A5A9A"



class ChatPage(BasePage):
    """
    Página de Chat de AURA en Flet.
    """

    PAGE_NAME = "Chat"

    def __init__(self, page: ft.Page, **kwargs):
        self._provider = None
        self._messages: list[ChatMessage] = []
        self._is_thinking = False
        self._typing_bubble: Optional[ChatBubble] = None
        self._conversation: Optional[Conversation] = None
        self._is_listening = False
        self._pending_confirm_action = None
        self._active_scan_cancel_event: Optional[threading.Event] = None
        self._active_scan_target: Optional[str] = None
        self._pending_app_candidates: Optional[dict] = None
        self._pending_clarification: Optional[dict] = None
        super().__init__(page, **kwargs)

    def _build(self) -> None:
        from aura.ui.background_manager import background_manager
        has_bg = background_manager.is_active

        self.bgcolor = "transparent" if has_bg else _BG_DARK

        # ── Banner de estado superior ──────────────────────────────
        self._status_dot = ft.Icon(ft.Icons.CIRCLE, size=8, color="#555577")
        self._status_text = ft.Text("Conectando con el proveedor de IA...", size=11, color="#777799")
        self._status_banner = ft.Container(
            content=ft.Row([self._status_dot, self._status_text], spacing=8),
            bgcolor="transparent" if has_bg else "#0A0A1A",
            padding=ft.Padding.symmetric(horizontal=16, vertical=6),
            border=ft.Border.only(bottom=ft.BorderSide(1, "#1A1A2E")),
        )

        # ── Área de mensajes ──────────────────────────────────────
        self._messages_list = ft.ListView(
            expand=True,
            spacing=8,
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            auto_scroll=True,
        )

        # ── Panel lateral de historial ────────────────────────────
        self._history_panel = HistoryPanel(
            store=_store,
            on_open=self.load_conversation,
            on_new=self.new_conversation_action,
            on_close=self._on_history_closed,
        )

        # ── Controles inferiores ──────────────────────────────────
        self._clear_btn = ft.TextButton(
            "🗑 Limpiar",
            on_click=lambda e: self._on_clear(),
            style=ft.ButtonStyle(
                color="#777799",
                bgcolor=_CLEAR_BG,
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )

        self._history_btn = ft.TextButton(
            "📋 Historial",
            on_click=lambda e: self._on_toggle_history(),
            style=ft.ButtonStyle(
                color="#777799",
                bgcolor=_CLEAR_BG,
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )

        self._audio_btn = ft.TextButton(
            "✕ Audio",
            on_click=lambda e: self._on_toggle_audio(),
            style=ft.ButtonStyle(
                color="#777799",
                bgcolor=_CLEAR_BG,
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )

        self._mic_btn = ft.IconButton(
            icon=ft.Icons.MIC_NONE,
            icon_color="#8888AA",
            bgcolor=_MIC_BTN_BG,
            tooltip="Dictar comando por voz (VAD)",
            on_click=lambda e: self._on_mic_click(),
        )

        self._conv_label = ft.Text("", size=11, color="#555577")
        self._char_count_label = ft.Text("", size=10, color="#444466")

        controls_row = ft.Row(
            [
                ft.Row([self._clear_btn, self._history_btn, self._audio_btn, self._mic_btn, self._conv_label], spacing=8),
                self._char_count_label,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # ── Input Row ─────────────────────────────────────────────
        self._input_box = ft.TextField(
            hint_text="Escribí un mensaje o comando (/ayuda)...",
            hint_style=ft.TextStyle(size=12, color="#555577"),
            bgcolor=_INPUT_BG,
            border_color=_INPUT_BORDER,
            color="#E0E0FF",
            text_size=13,
            multiline=True,
            min_lines=1,
            max_lines=3,
            expand=True,
            shift_enter=True,
            on_submit=lambda e: self._on_send(),
            on_change=lambda e: self._on_input_change(),
        )

        self._send_btn = ft.FilledButton(
            "➤ Enviar",
            on_click=lambda e: self._on_send(),
            style=ft.ButtonStyle(
                bgcolor=_SEND_BTN_BG,
                color="#FFFFFF",
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            height=44,
        )

        input_row = ft.Row([self._input_box, self._send_btn], spacing=8)

        self._input_container = ft.Container(
            content=ft.Column(
                [
                    controls_row,
                    input_row,
                    ft.Text("Enter para enviar · Shift+Enter para nueva línea", size=10, color="#353555"),
                ],
                spacing=6,
            ),
            bgcolor="transparent" if has_bg else "#0F0F22",
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            border=ft.Border.only(top=ft.BorderSide(1, "#1A1A2E")),
        )

        # ── Panel de Audio & Voz ──────────────────────────────────
        self._audio_panel = AudioPanel(
            page=self.app_page,
            on_send_message=lambda txt: self.handle_user_message(txt, origen="voz"),
            on_status_message=self._add_system_message,
            on_error_message=self._add_error_message,
            visible=True,
        )

        # ── Cuerpo Central (Historial + Chat) ─────────────────────
        chat_column = ft.Column([self._messages_list, self._audio_panel, self._input_container], expand=True, spacing=0)
        self._chat_body = ft.Row([self._history_panel, chat_column], expand=True, spacing=0)

        self.content = ft.Column([self._status_banner, self._chat_body], expand=True, spacing=0)

        # Mensaje de bienvenida
        self._add_system_message("¡Hola! Soy AURA. Escribí tu mensaje y presioná Enter para chatear.")

        # Notificación de fallback TTS/RVC en el chat
        from voice.tts import tts_manager
        self._tts_fallback_handler = lambda msg: self._add_system_message(msg)
        tts_manager.register_fallback_callback(self._tts_fallback_handler)

    # ──────────────────────────────────────────────────────────────
    # Ciclo de vida
    # ──────────────────────────────────────────────────────────────

    def on_enter(self) -> None:
        _logger.info("ChatPage: entrando.")
        self._init_provider()

        # Descubrir skills builtin
        threading.Thread(target=self._discover_skills, daemon=True).start()

        # Cargar historial si no hay mensajes en RAM
        if not self._messages:
            self._load_latest_conversation()

    def on_leave(self) -> None:
        super().on_leave()
        try:
            from voice.tts import tts_manager
            tts_manager.stop()
        except Exception:
            pass
        try:
            from voice.message_speaker import message_speaker
            message_speaker.stop()
        except Exception:
            pass

    def _discover_skills(self) -> None:
        try:
            from skills.skill_registry import skill_registry
            skill_registry.discover_builtin()
        except Exception as e:
            _logger.error(f"ChatPage: error al descubrir skills: {e}")

    # ──────────────────────────────────────────────────────────────
    # Inicialización del proveedor
    # ──────────────────────────────────────────────────────────────

    def _init_provider(self) -> None:
        def _load():
            try:
                provider = get_default_provider(fallback_to_mock=False)
                status = provider.check_status()
                self._provider = provider
                self._update_banner(provider, status)
            except Exception as e:
                _logger.error(f"Error inicializando proveedor: {e}")
                self._set_banner_status("Sin proveedor de IA disponible", _STATUS_ERR)

        threading.Thread(target=_load, daemon=True).start()

    def _update_banner(self, provider, status) -> None:
        p_name = getattr(provider, "name", provider.provider_name).upper()
        if provider.provider_name == "mock":
            self._set_banner_status("Modo demostración (MockProvider) — Sin IA conectada", _STATUS_MOCK)
        elif status.available:
            configured_model = getattr(provider, "default_model", None) or settings.get("AI_MODEL", "")
            model = configured_model or (status.models[0] if status.models else "qwen2.5:3b")
            if "Fallback" in type(provider).__name__ and "Falló" in status.message:
                self._set_banner_status(f"☁️ Fallback local activo ({model})", _STATUS_WARN)
            else:
                self._set_banner_status(f"{p_name} conectado — Modelo: {model}", _STATUS_OK)
        else:
            self._set_banner_status(f"{p_name} no disponible: {status.message}", _STATUS_WARN)

    def _set_banner_status(self, text: str, color: str) -> None:
        self._status_text.value = text
        self._status_text.color = color
        self._status_dot.color = color
        try:
            self._status_text.update()
            self._status_dot.update()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────
    # Manejo de Conversaciones
    # ──────────────────────────────────────────────────────────────

    def _load_latest_conversation(self) -> None:
        try:
            conv = _store.load_latest()
            if conv and conv.messages:
                self._conversation = conv
                self._render_conversation(conv)
        except Exception as e:
            _logger.error(f"Error cargando conversación: {e}")

    @property
    def conversation_store(self) -> ConversationStore:
        return _store

    def _render_conversation(self, conv: Conversation) -> None:
        self._messages_list.controls.clear()
        self._messages.clear()
        self._add_system_message(f"📂 Conversación restaurada: {conv.title}")

        for m in conv.messages:
            _logger.debug(f"[UTF8_TRACE:reload_history] role={m.role} repr={repr(m.content)}")
            if m.role == "user":
                self._add_user_message(m.content, m.timestamp)
                self._messages.append(ChatMessage(role="user", content=m.content))
            elif m.role == "assistant":
                self._add_assistant_message(m.content, m.timestamp)
                self._messages.append(ChatMessage(role="assistant", content=m.content))

        self._update_conv_label()
        try:
            self._messages_list.update()
        except Exception:
            pass

    def load_conversation(self, conv_id: str) -> bool:
        if self._is_thinking:
            return False
        conv = _store.load(conv_id)
        if conv:
            self._conversation = conv
            self._render_conversation(conv)
            return True
        return False

    def new_conversation_action(self) -> None:
        if not self._is_thinking:
            self._on_clear()

    def _update_conv_label(self) -> None:
        if self._conversation:
            short = self._conversation.title[:24] + "…" if len(self._conversation.title) > 24 else self._conversation.title
            self._conv_label.value = f"💾 {short}"
            try:
                self._conv_label.update()
            except Exception:
                pass

    def _on_clear(self) -> None:
        if self._is_thinking:
            return
        self._messages_list.controls.clear()
        self._messages.clear()
        self._conversation = _store.new_conversation()
        self._conv_label.value = ""
        self._add_system_message("Conversación limpiada. Podés empezar de nuevo.")
        try:
            self._messages_list.update()
            self._conv_label.update()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────
    # Historial toggle
    # ──────────────────────────────────────────────────────────────

    def _on_toggle_history(self) -> None:
        active_id = self._conversation.id if self._conversation else None
        self._history_panel.toggle(active_conv_id=active_id)
        if self._history_panel.is_visible:
            self._history_btn.text = "✕ Historial"
        else:
            self._history_btn.text = "📋 Historial"
        try:
            self._history_btn.update()
        except Exception:
            pass

    def _on_history_closed(self) -> None:
        self._history_btn.text = "📋 Historial"
        try:
            self._history_btn.update()
        except Exception:
            pass

    def _on_toggle_audio(self) -> None:
        self._audio_panel.visible = not self._audio_panel.visible
        self._audio_btn.text = "✕ Audio" if self._audio_panel.visible else "🔊 Audio"
        try:
            self._audio_panel.update()
            self._audio_btn.update()
        except Exception:
            pass


    # ──────────────────────────────────────────────────────────────
    # Envío de Mensajes y Router
    # ──────────────────────────────────────────────────────────────

    def _on_input_change(self) -> None:
        val = self._input_box.value or ""
        self._char_count_label.value = f"{len(val)}/{_MAX_INPUT_LEN}" if len(val) > 0 else ""
        try:
            self._char_count_label.update()
        except Exception:
            pass

    def _on_send(self) -> None:
        if self._is_thinking:
            return

        user_text = (self._input_box.value or "").strip()
        if not user_text:
            return

        self._input_box.value = ""
        self._char_count_label.value = ""
        try:
            self._input_box.update()
            self._char_count_label.update()
        except Exception:
            pass

        self.handle_user_message(user_text, origen="chat")

    def send_message_text(self, text: str, origen: str = "chat") -> None:
        """
        Envía un mensaje de texto al flujo de chat.
        Delega en handle_user_message para mantener compatibilidad con versiones previas.
        """
        self.handle_user_message(text, origen=origen)

    def handle_user_message(self, texto: str, origen: str = "chat") -> None:
        """
        Pipeline único de procesamiento de mensajes del usuario (chat y voz).

        Flujo:
          a) Mostrar la burbuja del usuario (origen: chat | voz).
          b) Pasar por IntentRouter + EntityResolver (si ROUTER_FIRST=true).
          c) Si resuelve: ejecutar la skill (con confirmación para close_app) y mostrar resultado.
          d) Si intent claro sin resolver: pedir aclaración o sugerir registrar (NO ir al LLM).
          e) Solo si no hay intent: verificar comandos directos de CommandRouter o enviar a IA.
        """
        user_text = (texto or "").strip()
        if not user_text:
            return

        from voice.tts import tts_manager
        tts_manager.stop()

        if self._is_thinking:
            self._add_error_message("AURA está procesando una respuesta. Por favor esperá.")
            return

        if len(user_text) > _MAX_INPUT_LEN:
            self._add_error_message(f"Mensaje demasiado largo ({len(user_text)}/{_MAX_INPUT_LEN})")
            return

        ts = datetime.now().strftime("%H:%M")

        # a) Mostrar la burbuja del usuario (origen: chat | voz)
        bubble_text = f"🎤 {user_text}" if origen == "voz" else user_text
        self._add_user_message(bubble_text, ts)

        # ── Controles interactivos de escaneo e indexación ────────────
        # 1. Cancelar escaneo activo
        if self._active_scan_cancel_event is not None and user_text.strip().lower() in (
            "cancelar", "cancelar busqueda", "cancelar búsqueda", "stop", "parar"
        ):
            self._active_scan_cancel_event.set()
            self._add_system_message(f"Deteniendo búsqueda de '{self._active_scan_target or 'la aplicación'}'...")
            return

        # 2. Selección de candidatos ambiguos de escaneo
        if self._pending_app_candidates:
            pend = self._pending_app_candidates
            choice = (
                user_text.strip().lower()
                .replace("opcion", "")
                .replace("opción", "")
                .replace("abrir", "")
                .strip()
            )
            if choice.isdigit():
                idx = int(choice) - 1
                cands = pend.get("candidates", [])
                if 0 <= idx < len(cands):
                    chosen_path = cands[idx]
                    target_name = pend.get("target", "app")
                    self._pending_app_candidates = None
                    from core.app_scanner import app_index_manager
                    from core.app_resolver import launch_app
                    from aura.personality import get_context_phrase, get_current_personality

                    app_index_manager.register(target_name, chosen_path, origin="deep_scan_user_choice")
                    curr_mode = get_current_personality()
                    phrase = get_context_phrase("open", personality=curr_mode, target=target_name)
                    msg = (
                        f"✅ Abriendo opción {idx + 1}: {chosen_path}\n"
                        f"💾 Registrado como favorito para la próxima vez.\n"
                        f"{phrase}"
                    )
                    self._add_system_message(msg)
                    self._auto_save(user_text, msg, ts)
                    launch_app(chosen_path)
                    return

        # 3. Comando indexar apps
        norm_cmd = user_text.strip().lower()
        if norm_cmd in (
            "indexa mis apps", "indexar apps", "indexa apps", "/indexar-apps", "actualizar indice", "actualizar índice"
        ):
            self._start_index_all_apps_workflow(user_text, ts)
            return

        # 4. Selección de opciones de clarificación de comandos difusos
        if self._pending_clarification:
            pend = self._pending_clarification
            raw_choice = user_text.strip().lower()
            selected_cand = None
            choice_clean = (
                raw_choice.replace("opcion", "")
                .replace("opción", "")
                .replace("abrir", "")
                .replace("cerrar", "")
                .strip()
            )
            cands = pend.get("candidates", [])
            if choice_clean.isdigit():
                idx = int(choice_clean) - 1
                if 0 <= idx < len(cands):
                    selected_cand = cands[idx]
            else:
                for c in cands:
                    if c == choice_clean or c in raw_choice:
                        selected_cand = c
                        break

            if selected_cand:
                self._pending_clarification = None
                intent = pend["intent"]
                canon_verb = pend.get("canon_verb", intent)
                raw_typo = pend.get("raw_typo", "")
                from aura.core.fuzzy_interpreter import typo_memory
                if raw_typo:
                    typo_memory.learn(raw_typo, selected_cand, intent, confidence=1.0, layer=2)

                self._add_system_message(f"✅ Entendido: {canon_verb} {selected_cand}")
                res_ent = entity_resolver.resolve(intent, selected_cand)
                res_ent.extra["raw_typo"] = raw_typo
                res_ent.extra["layer"] = 2
                if intent == "close_app":
                    confirm_close = settings.get_bool("CONFIRMAR_CIERRE_APP", False)
                    if confirm_close:
                        self._handle_close_app_with_confirm(res_ent, user_text, ts)
                    else:
                        self._handle_close_app_direct(res_ent, user_text, ts)
                else:
                    self._execute_resolved_skill_async(res_ent, user_text, ts)
                return
            elif raw_choice in ("cancelar", "cancel", "ninguna", "ninguno", "no"):
                self._pending_clarification = None
                self._add_system_message("Operación cancelada.")
                return

        # Configuración .env: si ROUTER_FIRST=false, va directo a la IA
        router_first = settings.get_bool("ROUTER_FIRST", fallback=True)
        if not router_first:
            _logger.info(f"Pipeline: ROUTER_FIRST=false -> enviando '{user_text}' directamente a la IA.")
            self._send_to_ai(user_text, ts)
            return

        # b0) Planificador de cadenas de instrucciones (Fase 71)
        if is_instruction_chain(user_text):
            _logger.info("Pipeline: detectada cadena de instrucciones en '%s'", user_text)
            plan = plan_from_rules(user_text)
            if plan is None or not plan.pasos:
                plan = plan_from_ai(user_text, provider=self._provider)
            if plan and len(plan.pasos) >= 2:
                self._handle_instruction_chain(plan, user_text, ts)
                return

        # b) Fast-path con IntentRouter + EntityResolver
        intent = intent_router.parse(user_text)

        if intent is not None:
            if intent.nombre == "queja_chiste":
                _logger.info("Pipeline: intent='queja_chiste' directo -> ejecutando handler dedicado de queja.")
                self._handle_joke_complaint(user_text, ts)
                return

            if intent.nombre == "pedir_chiste":
                _logger.info("Pipeline: intent='pedir_chiste' directo -> ejecutando handler dedicado de chiste.")
                estilo = intent.extra.get("estilo", "")
                tema = intent.extra.get("tema", "")
                self._handle_joke(user_text, ts, estilo=estilo, tema=tema)
                return

            if intent.nombre == "roast":
                _logger.info("Pipeline: intent='roast' directo -> ejecutando handler dedicado de roast.")
                self._handle_roast(user_text, ts)
                return

            resolved_entity = entity_resolver.resolve(intent)
            if resolved_entity.resolved:
                action_desc = f"{resolved_entity.skill_name}.{resolved_entity.command} {resolved_entity.args}"
                _logger.info(
                    f"Pipeline: texto='{user_text}' | origen='{origen}' | intent='{intent.nombre}' | "
                    f"resolved=True | accion='{action_desc}'"
                )
                if resolved_entity.intent == "close_app":
                    confirm_close = settings.get_bool("CONFIRMAR_CIERRE_APP", False)
                    if confirm_close:
                        self._handle_close_app_with_confirm(resolved_entity, user_text, ts)
                    else:
                        self._handle_close_app_direct(resolved_entity, user_text, ts)
                else:
                    self._execute_resolved_skill_async(resolved_entity, user_text, ts)
                return
            elif not self._is_fuzzy_typo(intent.nombre, intent.target):
                # Si no es un error de tipeo de otra entidad, manejar según el intent (deep scan para open_app, no en ejecución para close_app)
                _logger.info(f"Pipeline: intent='{intent.nombre}' target='{intent.target}' no es typo -> _handle_unresolved_intent")
                self._handle_unresolved_intent(intent, user_text, ts)
                return

        # c) Comprensión de comandos con errores de tipeo (Fuzzy + LLM Interpreter: Capas 1, 2 y 3)
        from aura.core.fuzzy_interpreter import fuzzy_interpreter
        interp = fuzzy_interpreter.interpret(user_text, provider=self._provider)

        if interp is not None:
            if interp.intent == "queja_chiste":
                _logger.info("Pipeline: interp='queja_chiste' por fuzzy matching -> ejecutando handler dedicado.")
                self._handle_joke_complaint(user_text, ts)
                return

            if interp.intent == "pedir_chiste":
                _logger.info("Pipeline: interp='pedir_chiste' por fuzzy matching -> ejecutando handler dedicado.")
                estilo = interp.extra.get("estilo", "") if hasattr(interp, "extra") else ""
                tema = interp.extra.get("tema", "") if hasattr(interp, "extra") else ""
                self._handle_joke(user_text, ts, estilo=estilo, tema=tema)
                return

            if interp.intent == "roast":
                _logger.info("Pipeline: interp='roast' por fuzzy matching -> ejecutando handler dedicado de roast.")
                self._handle_roast(user_text, ts)
                return
            _logger.info(
                f"Pipeline: interpretado por FuzzyInterpreter | status='{interp.status}' | "
                f"intent='{interp.intent}' | target='{interp.target}' | layer={interp.layer} | conf={interp.confidence:.2f}"
            )

            if interp.status in ("execute_direct", "execute_with_note"):
                if interp.display_message:
                    self._add_system_message(interp.display_message)

                res_ent = interp.resolved_entity or entity_resolver.resolve(interp.intent, interp.target)
                res_ent.extra["raw_typo"] = interp.raw_target
                res_ent.extra["layer"] = interp.layer

                if interp.intent == "close_app":
                    confirm_close = settings.get_bool("CONFIRMAR_CIERRE_APP", False)
                    if confirm_close:
                        self._handle_close_app_with_confirm(res_ent, user_text, ts)
                    else:
                        self._handle_close_app_direct(res_ent, user_text, ts)
                else:
                    self._execute_resolved_skill_async(res_ent, user_text, ts)
                return

            elif interp.status == "ask_user":
                lines = ["¿Quisiste decir alguna de estas opciones?"]
                for i, opt in enumerate(interp.candidates, 1):
                    lines.append(f"  {i}) {interp.canon_verb} {opt}")
                lines.append("Respondé con el número o el nombre.")
                self._add_system_message("\n".join(lines))
                self._pending_clarification = {
                    "intent": interp.intent,
                    "canon_verb": interp.canon_verb,
                    "candidates": interp.candidates,
                    "raw_typo": interp.raw_target,
                }
                return

            elif interp.status == "execute_ai":
                if interp.display_message:
                    self._add_system_message(interp.display_message)

                res_ent = interp.resolved_entity or entity_resolver.resolve(interp.intent, interp.target)
                res_ent.extra["raw_typo"] = interp.raw_target
                res_ent.extra["layer"] = 3

                if interp.intent == "close_app":
                    confirm_close = settings.get_bool("CONFIRMAR_CIERRE_APP", False)
                    if confirm_close:
                        self._handle_close_app_with_confirm(res_ent, user_text, ts)
                    else:
                        self._handle_close_app_direct(res_ent, user_text, ts)
                else:
                    self._execute_resolved_skill_async(res_ent, user_text, ts)
                return

            elif interp.status == "needs_deep_scan":
                self._start_deep_scan_for_app(interp.target, user_text, ts)
                return

        # d) Solo si no hay intent interpretado: verificar comandos de CommandRouter o enviar a la IA
        route_result = command_router.route(user_text)
        if route_result is not None:
            _logger.info(f"Pipeline: texto='{user_text}' | comando detectado por CommandRouter")
            threading.Thread(
                target=self._handle_skill_result,
                args=(route_result, user_text, ts),
                daemon=True,
            ).start()
            return

        # Sin intent y sin comando de skill -> enviar a IA
        _logger.info(f"Pipeline: texto='{user_text}' | origen='{origen}' | sin intent -> enviando al proveedor de IA")
        self._send_to_ai(user_text, ts)

    def _is_fuzzy_typo(self, intent_name: str, target: str) -> bool:
        """Verifica si target parece ser un error de tipeo de una entidad existente."""
        try:
            from aura.core.fuzzy_interpreter import fuzzy_interpreter
            fuzzy_threshold = settings.get_float("FUZZY_THRESHOLD", 0.85)
            cands = fuzzy_interpreter.match_target(intent_name, target)
            if cands and cands[0][1] >= fuzzy_threshold and cands[0][0] != target.lower():
                return True
        except Exception:
            pass
        return False

    def _handle_close_app_direct(self, entity: ResolvedEntity, user_text: str, ts: str) -> None:
        """Cierra el proceso inmediatamente sin confirmación modal y reporta el estado real."""
        target_display = entity.executable or entity.target
        self._add_system_message(f"✅ Cerrando '{target_display}'...")

        def _worker():
            try:
                from skills.skill_registry import skill_registry
                if not skill_registry.list_all():
                    skill_registry.discover_builtin()

                result = skill_registry.execute("system_skill", "cerrar", entity.args or [target_display])

                if result.success:
                    raw_typo = entity.extra.get("raw_typo")
                    if raw_typo and raw_typo.lower() != entity.target.lower():
                        from aura.core.fuzzy_interpreter import typo_memory
                        typo_memory.learn(raw_typo, entity.target, entity.intent, confidence=1.0, layer=entity.extra.get("layer", 2))

                    if result.data.get("running") is False:
                        out = f"ℹ️ '{entity.target}' no estaba en ejecución."
                        self._add_system_message(out)
                    else:
                        out = result.output or "✅ Proceso cerrado."
                        self._add_system_message(out)
                    self._auto_save(user_text, out, ts)
                else:
                    err_detail = result.error or "Error desconocido"
                    if "no estaba en ejecución" in err_detail:
                        out = f"ℹ️ '{entity.target}' no estaba en ejecución."
                        self._add_system_message(out)
                    elif err_detail.startswith("❌"):
                        out = err_detail
                        self._add_error_message(out)
                    else:
                        out = f"❌ No pude cerrarlo: {err_detail}."
                        self._add_error_message(out)
                    self._auto_save(user_text, out, ts)
            except Exception as e:
                _logger.error(f"Error cerrando aplicación '{target_display}': {e}", exc_info=True)
                err_msg = f"❌ No pude cerrarlo: {e}."
                self._add_error_message(err_msg)
                self._auto_save(user_text, err_msg, ts)

        threading.Thread(target=_worker, daemon=True).start()

    def _handle_close_app_with_confirm(self, entity: ResolvedEntity, user_text: str, ts: str) -> None:
        """Pide confirmación modal al usuario antes de cerrar un proceso cuando CONFIRMAR_CIERRE_APP=true."""
        target_name = entity.executable or entity.target

        # Si el usuario ya pasó explícitamente el flag --ahora
        if "--ahora" in user_text.lower() or "-f" in user_text.lower():
            self._handle_close_app_direct(entity, user_text, ts)
            return

        def on_confirm(e=None):
            if hasattr(self.app_page, "pop_dialog"):
                try:
                    self.app_page.pop_dialog()
                except Exception:
                    pass
            _logger.info(f"Pipeline: cierre de '{target_name}' confirmado por el usuario.")
            self._handle_close_app_direct(entity, user_text, ts)

        def on_cancel(e=None):
            if hasattr(self.app_page, "pop_dialog"):
                try:
                    self.app_page.pop_dialog()
                except Exception:
                    pass
            self._add_system_message("🚫 Cierre de aplicación cancelado.")
            _logger.info(f"Pipeline: cierre de '{target_name}' cancelado por el usuario.")

        dlg = ft.AlertDialog(
            title=ft.Text("Confirmar cierre de aplicación"),
            content=ft.Column(
                [
                    ft.Text(f"⚠️ ¿Confirmás que querés cerrar '{target_name}'?", color="#F8D57E", size=13),
                    ft.Text(f'Comando: "{user_text}"', color="#7A7A9A", size=11),
                ],
                tight=True,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=on_cancel),
                ft.FilledButton("Confirmar", on_click=on_confirm, bgcolor="#8B2020", color="#FFFFFF"),
            ],
        )
        self._pending_confirm_action = on_confirm

        try:
            if hasattr(self.app_page, "show_dialog"):
                self.app_page.show_dialog(dlg)
            else:
                on_confirm()
        except Exception as ex:
            _logger.warning(f"No se pudo mostrar diálogo modal ({ex}). Ejecutando con confirmación directa.")
            on_confirm()

    def _execute_resolved_skill_async(self, entity: ResolvedEntity, user_text: str, ts: str) -> None:
        """Ejecuta la skill resuelta en un hilo de fondo y reporta el resultado con tono de personalidad."""
        def _worker():
            try:
                from skills.skill_registry import skill_registry
                if not skill_registry.list_all():
                    skill_registry.discover_builtin()
                result = skill_registry.execute(entity.skill_name, entity.command, entity.args)
                curr_mode = get_current_personality()
                if isinstance(entity.target, str) and entity.target:
                    target_name = entity.target
                elif isinstance(entity.args, list) and entity.args:
                    target_name = " ".join(str(a) for a in entity.args).strip()
                elif isinstance(entity.args, str) and entity.args:
                    target_name = entity.args
                else:
                    target_name = entity.skill_name or "la acción"

                if result.success:
                    raw_typo = entity.extra.get("raw_typo")
                    if raw_typo and raw_typo.lower() != entity.target.lower():
                        from aura.core.fuzzy_interpreter import typo_memory
                        typo_memory.learn(raw_typo, entity.target, entity.intent, confidence=1.0, layer=entity.extra.get("layer", 2))

                    skill = entity.skill_name or "skill"
                    if skill in ("app_writer", "app_saver"):
                        out = result.output
                    else:
                        ctx = "open" if "open" in (entity.command or "") else ("close" if "close" in (entity.command or "") else "success")
                        phrase = get_context_phrase(ctx, personality=curr_mode, target=target_name)
                        out = f"[{skill}] {phrase}\n{result.output}" if result.output else f"[{skill}] {phrase}"
                    self._add_system_message(out)
                    self._auto_save(user_text, out, ts)
                else:
                    err = result.error or "Error ejecutando el comando."
                    err_phrase = get_context_phrase("error", personality=curr_mode, target=target_name)
                    self._add_error_message(f"⚠️ {err_phrase}\nDetalle: {err}")
            except Exception as e:
                _logger.error(f"Error ejecutando skill '{entity.skill_name}': {e}", exc_info=True)
                self._add_error_message(f"Error inesperado ejecutando acción: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def _handle_unresolved_intent(self, intent: Intent, user_text: str, ts: str) -> None:
        """Informa al usuario que la entidad no se pudo resolver o ejecuta búsqueda profunda."""
        if intent.nombre == "open_app":
            self._start_deep_scan_for_app(intent.target, user_text, ts)
            return
        elif intent.nombre == "close_app":
            msg = f"ℹ️ '{intent.target}' no estaba en ejecución."
            self._add_system_message(msg)
            self._auto_save(user_text, msg, ts)
            return
        elif intent.nombre == "open_url":
            msg = (
                f"⚠️ No pude interpretar la dirección web '{intent.target}'.\n"
                "Asegurate de indicar un dominio válido (ej: youtube.com o https://...)."
            )
        elif intent.nombre in ("create_folder", "create_file"):
            tipo = "la carpeta" if "folder" in intent.nombre else "el archivo"
            msg = f"⚠️ ¿Cómo querés que se llame {tipo}?"
        elif intent.nombre == "write_in_app":
            msg = f"⚠️ No pude identificar en qué aplicación escribir '{intent.target}'. Asegurate de indicar la aplicación (ej: 'en notepad escribí hola')."
        elif intent.nombre == "save_app_doc":
            msg = "⚠️ No pude identificar qué aplicación guardar. Asegurate de tener la aplicación abierta (ej: 'guardá el notepad en el escritorio')."
        elif intent.nombre == "delete_file":
            msg = "⚠️ Por favor indicá el nombre del archivo o carpeta que querés eliminar."
        elif intent.nombre in ("move_file", "rename_file"):
            msg = "⚠️ Por favor indicá el origen y el destino (ej: 'mover notas.txt a documentos')."
        else:
            msg = f"⚠️ No pude resolver la entidad '{intent.target}'. Por favor verificá los datos."

        self._add_system_message(msg)

    def _start_deep_scan_for_app(self, target: Any, user_text: str, ts: str) -> None:
        """
        Ejecuta la búsqueda profunda de una aplicación en segundo plano sin bloquear la UI.
        """
        from core.app_scanner import deep_app_scanner, app_index_manager, PROGRAMS_FILE
        from core.app_resolver import launch_app
        from aura.personality import get_context_phrase, get_current_personality

        if isinstance(target, (list, tuple)):
            target = " ".join(str(x) for x in target).strip()
        else:
            target = str(target or "").strip()

        self._active_scan_cancel_event = threading.Event()
        self._active_scan_target = target

        # Mensaje requerido obligatorio
        self._add_system_message(f"🔍 Buscando '{target}' en toda la PC...")

        def _worker():
            try:
                res = deep_app_scanner.scan(
                    target=target,
                    cancel_event=self._active_scan_cancel_event,
                )

                if res.cancelled:
                    self._add_system_message(f"🚫 Búsqueda de '{target}' cancelada.")
                    _logger.info("DeepScan: Búsqueda de '%s' cancelada por el usuario.", target)
                    return

                curr_mode = get_current_personality()

                # Caso 1: Un candidato claro o coincidencia exacta
                if res.has_single_match or res.exact_match:
                    found_path = res.best_match or (res.candidates[0] if res.candidates else "")
                    if found_path and os.path.exists(found_path):
                        # Registrar automáticamente en memoria y app_index.json
                        app_index_manager.register(target, found_path, origin="deep_scan")
                        phrase = get_context_phrase("open", personality=curr_mode, target=target)

                        out_msg = (
                            f"✅ Encontré '{target}' en:\n   {found_path}\n"
                            f"💾 Registrado en tus favoritos para abrirlo al instante la próxima vez.\n"
                            f"{phrase}"
                        )
                        self._add_system_message(out_msg)
                        self._auto_save(user_text, out_msg, ts)

                        # Abrir la aplicación
                        launch_app(found_path)
                        _logger.info(
                            "DeepScan: target='%s' | candidatos=%d | tiempo=%.2fs | ruta_elegida='%s'",
                            target,
                            len(res.candidates),
                            res.duration_sec,
                            found_path,
                        )
                        return

                # Caso 2: Varios candidatos ambiguos sin coincidencia exacta
                if len(res.candidates) > 1:
                    top_candidates = res.candidates[:5]
                    self._pending_app_candidates = {
                        "target": target,
                        "candidates": top_candidates,
                    }
                    cand_lines = [
                        f"🔍 Encontré varias opciones para '{target}' en {res.duration_sec:.2f}s:",
                    ]
                    for idx, cand in enumerate(top_candidates, 1):
                        cand_lines.append(f"  {idx}. {cand}")
                    cand_lines.append("\nPor favor respondé con el número (ej: '1') de la aplicación que querés abrir.")
                    out_msg = "\n".join(cand_lines)
                    self._add_system_message(out_msg)
                    self._auto_save(user_text, out_msg, ts)
                    _logger.info(
                        "DeepScan: target='%s' | candidatos=%d (ambiguos) | tiempo=%.2fs | ruta_elegida=None (esperando usuario)",
                        target,
                        len(res.candidates),
                        res.duration_sec,
                    )
                    return

                # Caso 3: Nada encontrado tras el escaneo exhaustivo
                import difflib
                known_apps: set[str] = set()
                try:
                    idx = app_index_manager.load_index()
                    for k, v in idx.items():
                        known_apps.add(k.lower())
                        if isinstance(v, dict) and v.get("display_name"):
                            known_apps.add(v["display_name"].lower())
                    if PROGRAMS_FILE.exists():
                        with open(PROGRAMS_FILE, "r", encoding="utf-8") as f:
                            progs = json.load(f)
                            if isinstance(progs, dict):
                                known_apps.update(k.lower() for k in progs.keys())
                except Exception:
                    pass

                suggs = difflib.get_close_matches(target.lower(), list(known_apps), n=3, cutoff=0.5)
                msg_not_found = f"No encontré '{target}' en toda la PC. ¿Querés registrar la ruta manual?"
                if suggs:
                    msg_not_found += f"\n\n¿Quisiste decir: {', '.join(suggs)}?"
                msg_not_found += f"\n\nPodés registrarla manualmente con el comando:\n  agregar-programa {target} <ruta_al_ejecutable>"
                self._add_system_message(msg_not_found)
                self._auto_save(user_text, msg_not_found, ts)
                _logger.info(
                    "DeepScan: target='%s' | candidatos=0 | tiempo=%.2fs | ruta_elegida=None",
                    target,
                    res.duration_sec,
                )

            except Exception as e:
                _logger.error("Error en escaneo profundo de '%s': %s", target, e, exc_info=True)
                self._add_error_message(f"Error inesperado buscando '{target}': {e}")
            finally:
                self._active_scan_cancel_event = None
                self._active_scan_target = None

        threading.Thread(target=_worker, daemon=True).start()

    def _start_index_all_apps_workflow(self, user_text: str, ts: str) -> None:
        """Reconstruye el índice de aplicaciones en segundo plano y reporta al usuario."""
        self._add_system_message("⚙️ Indexando aplicaciones en tu PC... Esto puede tardar unos momentos.")

        def _worker():
            try:
                from core.app_scanner import app_index_manager
                apps = app_index_manager.index_all_apps()
                msg = (
                    f"✅ Índice de aplicaciones actualizado exitosamente.\n"
                    f"📊 Total: {len(apps)} aplicaciones registradas en 'data/learning/app_index.json'.\n"
                    f"Ahora podés abrir cualquiera diciendo 'abre <nombre>' sin esperas."
                )
                self._add_system_message(msg)
                self._auto_save(user_text, msg, ts)
            except Exception as e:
                self._add_error_message(f"Error indexando aplicaciones: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def _send_to_ai(self, user_text: str, ts: str) -> None:
        """Envía el mensaje al proveedor de IA con contexto y streaming."""
        if self._provider is None:
            self._add_error_message(
                "❌ No hay proveedor de IA disponible. Ollama no responde en localhost:11434 "
                "(inicialo con 'ollama serve') o configurá un proveedor con API key en Configuración."
            )
            return

        self._messages.append(ChatMessage(role="user", content=user_text))
        self._set_thinking(True)
        from aura.personality.humor_tracker import set_last_humor_intent
        set_last_humor_intent("ninguno")

        context = list(self._messages[-_MAX_CONTEXT_MESSAGES:])
        threading.Thread(
            target=self._call_ai,
            args=(self._provider, context, user_text, ts),
            daemon=True,
        ).start()

    def _handle_skill_result(self, route_result, user_text: str, ts: str) -> None:
        from aura.personality.humor_tracker import set_last_humor_intent
        set_last_humor_intent("ninguno")
        curr_mode = get_current_personality()
        target_name = route_result.skill_name or "el comando"
        if route_result.success:
            skill = route_result.skill_name or "skill"
            phrase = get_context_phrase("success", personality=curr_mode, target=target_name)
            out = f"[{skill}] {phrase}\n{route_result.output}" if route_result.output else f"[{skill}] {phrase}"
            self._add_system_message(out)
            self._auto_save(user_text, out, ts)
        else:
            err = route_result.error or "Error ejecutando el comando."
            err_phrase = get_context_phrase("error", personality=curr_mode, target=target_name)
            self._add_error_message(f"⚠️ {err_phrase}\nDetalle: {err}")

    def _handle_roast(self, user_text: str, ts: str) -> None:
        """Handler dedicado para solicitudes de roast/insulto con estilo estructurado y contexto."""
        self._messages.append(ChatMessage(role="user", content=user_text))
        self._set_thinking(True)

        def _worker():
            try:
                from aura.personality.humor_provider import get_humor_provider
                from aura.personality.humor_tracker import strip_humor_labels
                humor_prov = get_humor_provider(default_provider=self._provider)
                from aura.personality.roast_handler import generate_roast
                roast_text = generate_roast(user_text, provider=humor_prov)
                roast_clean = strip_humor_labels(roast_text)
                self._messages.append(ChatMessage(role="assistant", content=roast_clean))
                self._set_thinking(False)
                self._add_assistant_message(roast_clean, ts)
                self._auto_save(user_text, roast_clean, ts)
                self._speak_if_enabled(roast_clean)
            except Exception as e:
                self._set_thinking(False)
                _logger.error("Error generando roast: %s", e, exc_info=True)
                self._add_error_message(f"Error generando roast: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def _handle_joke(self, user_text: str, ts: str, estilo: str = "", tema: str = "") -> None:
        """Handler dedicado para solicitudes de chiste estructurado con guard y fallback local."""
        self._messages.append(ChatMessage(role="user", content=user_text))
        self._set_thinking(True)

        def _worker():
            try:
                from aura.personality.humor_provider import get_humor_provider
                from aura.personality.humor_tracker import strip_humor_labels
                humor_prov = get_humor_provider(default_provider=self._provider)
                from aura.personality.jokes import generate_joke
                joke_text = generate_joke(user_text, estilo=estilo, tema=tema, provider=humor_prov)
                joke_clean = strip_humor_labels(joke_text)
                self._messages.append(ChatMessage(role="assistant", content=joke_clean))
                self._set_thinking(False)
                self._add_assistant_message(joke_clean, ts)
                self._auto_save(user_text, joke_clean, ts)
                self._speak_if_enabled(joke_clean)
            except Exception as e:
                self._set_thinking(False)
                _logger.error("Error generando chiste: %s", e, exc_info=True)
                self._add_error_message(f"Error generando chiste: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def _handle_instruction_chain(self, plan: Plan, user_text: str, ts: str) -> None:
        """Gestiona la prevalidación de capacidades, confirmación previa y despacha la cadena (Fase 71 & 72)."""
        # 1. Prevalidación de capacidades y PLAN_STRICT (Fase 72)
        if plan.has_unsupported_steps():
            unsupported = plan.unsupported_steps()
            reason = unsupported[0].unsupported_reason if unsupported else "Paso no soportado"

            is_strict = getattr(settings, "is_plan_strict", lambda: False)() or settings.get("PLAN_STRICT", "false").lower() in ("true", "1", "yes")
            if is_strict:
                msg = f"🚫 Plan cancelado por PLAN_STRICT: {reason}."
                _logger.warning("Cadena rechazada por PLAN_STRICT: %s", reason)
                self._add_system_message(msg)
                self._messages.append(ChatMessage(role="assistant", content=msg))
                self._auto_save(user_text, msg, ts)
                return

            # Si ninguna acción sustantiva es válida (evitar abrir la app para nada: 'sin ejecución a medias')
            if not plan.has_valid_actionable_steps():
                msg = f"⚠️ No se puede completar el plan: {reason}. No se iniciará la ejecución para evitar acciones a medias."
                _logger.warning("Cadena no iniciada para evitar ejecución a medias: %s", reason)
                self._add_system_message(msg)
                self._messages.append(ChatMessage(role="assistant", content=msg))
                self._auto_save(user_text, msg, ts)
                return

        # 2. Chequeo de pasos destructivos
        is_destr, desc_destr = is_destructive_plan(plan)
        confirm_destructive = settings.get_bool("CONFIRM_DESTRUCTIVE", True)

        if is_destr and confirm_destructive:
            _logger.info("Cadena de instrucciones contiene paso destructivo: '%s'. Solicitando confirmación previa.", desc_destr)

            def on_confirm(e=None):
                if hasattr(self.app_page, "pop_dialog"):
                    try:
                        self.app_page.pop_dialog()
                    except Exception:
                        pass
                self._execute_instruction_chain_async(plan, user_text, ts)

            def on_cancel(e=None):
                if hasattr(self.app_page, "pop_dialog"):
                    try:
                        self.app_page.pop_dialog()
                    except Exception:
                        pass
                self._add_system_message("🚫 Cadena de instrucciones cancelada por el usuario.")

            dlg = ft.AlertDialog(
                title=ft.Text("Confirmar cadena de instrucciones"),
                content=ft.Column(
                    [
                        ft.Text(f"⚠️ La cadena contiene una acción destructiva:\n   {desc_destr}", color="#F8D57E", size=13),
                        ft.Text(f"Total: {len(plan.pasos)} pasos encadenados.", color="#E0E0E0", size=12),
                        ft.Text(f'Instrucción: "{user_text}"', color="#7A7A9A", size=11),
                    ],
                    tight=True,
                ),
                actions=[
                    ft.TextButton("Cancelar", on_click=on_cancel),
                    ft.FilledButton("Confirmar y ejecutar", on_click=on_confirm, bgcolor="#8B2020", color="#FFFFFF"),
                ],
            )
            self._pending_confirm_action = on_confirm
            try:
                if hasattr(self.app_page, "show_dialog"):
                    self.app_page.show_dialog(dlg)
                else:
                    on_confirm()
            except Exception as ex:
                _logger.warning("No se pudo mostrar diálogo modal (%s). Ejecutando directamente.", ex)
                on_confirm()
        else:
            self._execute_instruction_chain_async(plan, user_text, ts)

    def _execute_instruction_chain_async(self, plan: Plan, user_text: str, ts: str) -> None:
        """Ejecuta los pasos de la cadena en segundo plano actualizando la checklist en vivo (Fase 71 & 72)."""
        def _worker():
            try:
                from automation.engine import automation_engine

                step_statuses = ["pending"] * len(plan.pasos)
                step_details = [""] * len(plan.pasos)

                def _clean_plan_bubble_text(text: str) -> str:
                    if not text:
                        return ""
                    text = re.sub(r"§\d+", "", text)
                    text = re.sub(r"\(\s*\)", "", text)
                    text = re.sub(r"\ben\s+\)", "", text)
                    open_p = text.count("(")
                    close_p = text.count(")")
                    if open_p > close_p:
                        text += ")" * (open_p - close_p)
                    elif close_p > open_p:
                        while text.count(")") > text.count("("):
                            last_idx = text.rfind(")")
                            if last_idx != -1:
                                text = text[:last_idx] + text[last_idx + 1:]
                            else:
                                break
                    if text.count("*") % 2 != 0:
                        text = text.replace("*", "")
                    return text.strip()

                def build_checklist_content() -> str:
                    lines = [f"📋 Plan de {len(plan.pasos)} pasos:\n"]
                    for i, paso in enumerate(plan.pasos):
                        st = step_statuses[i]
                        desc = _clean_plan_bubble_text(paso.description())
                        det = _clean_plan_bubble_text(step_details[i])
                        if st == "pending":
                            icon = "⚪"
                            suffix = ""
                        elif st == "running":
                            icon = "⏳"
                            suffix = "..."
                        elif st == "success":
                            icon = "✅"
                            suffix = f" — {det}" if det else ""
                        elif st == "skipped":
                            icon = "⚠️"
                            suffix = f" — {det}" if det else " — Salteado (no soportado)"
                        else:
                            icon = "❌"
                            suffix = f" — {det}" if det else ""
                        lines.append(f"{icon} Paso {i + 1}: {desc}{suffix}")
                    return "\n".join(lines)

                bubble = ChatBubble("assistant", build_checklist_content(), ts)
                self._messages_list.controls.append(bubble)
                try:
                    self._messages_list.update()
                except Exception:
                    pass

                def on_step_update(idx: int, status: str, result: Any):
                    if 0 <= idx < len(step_statuses):
                        step_statuses[idx] = status
                        if result:
                            if status == "success":
                                if getattr(result, "data", None) and "path" in result.data:
                                    step_details[idx] = str(result.data["path"])
                                elif result.output:
                                    out_clean = result.output.strip()
                                    step_details[idx] = out_clean if len(out_clean) <= 90 else out_clean[:87] + "..."
                                else:
                                    step_details[idx] = ""
                            elif status == "skipped":
                                step_details[idx] = result.output if result.output else "Salteado"
                            elif status == "error":
                                step_details[idx] = result.error or "Error"
                        bubble.update_content(build_checklist_content())

                engine_steps = [p.to_engine_step() for p in plan.pasos]
                res = automation_engine.run_steps(
                    steps=engine_steps,
                    name=f"Cadena ({len(plan.pasos)} pasos)",
                    dry_run=False,
                    on_step_update=on_step_update,
                )

                final_lines = [build_checklist_content(), ""]
                skipped_count = sum(1 for s in step_statuses if s == "skipped")
                if res.success:
                    if skipped_count > 0:
                        final_lines.append(f"✨ {res.completed_steps - skipped_count}/{res.total_steps} pasos completados ({skipped_count} salteado(s) por capacidades).")
                    else:
                        final_lines.append(f"✨ {res.completed_steps}/{res.total_steps} pasos completados con éxito.")
                else:
                    failed_step_idx = next((i for i, s in enumerate(step_statuses) if s == "error"), None)
                    if failed_step_idx is not None:
                        failed_num = failed_step_idx + 1
                        err_msg = step_details[failed_step_idx]
                        if not err_msg and failed_step_idx < len(res.step_results):
                            err_msg = res.step_results[failed_step_idx].error
                        if not err_msg:
                            err_msg = "Causa no especificada"
                    else:
                        failed_num = res.failed_steps
                        err_msg = "Causa no especificada"
                    clean_err = _clean_plan_bubble_text(err_msg)
                    final_lines.append(f"⚠️ La cadena falló en el paso {failed_num}: {clean_err}")

                final_text = "\n".join(final_lines)
                bubble.update_content(final_text)
                self._messages.append(ChatMessage(role="assistant", content=final_text))
                self._auto_save(user_text, final_text, ts)


            except Exception as e:
                _logger.error("Error ejecutando cadena de instrucciones: %s", e, exc_info=True)
                tb = e.__traceback__
                frames = traceback.extract_tb(tb) if tb else []
                if frames:
                    last_frame = frames[-1]
                    fname = os.path.basename(last_frame.filename)
                    location = f"{fname}:{last_frame.lineno}"
                else:
                    location = "desconocido:0"

                running_idx = 0
                if "step_statuses" in locals():
                    for i, s in enumerate(step_statuses):
                        if s in ("running", "error"):
                            running_idx = i
                            break
                        elif s == "pending":
                            running_idx = i
                            break
                step_num = running_idx + 1
                exc_type = type(e).__name__
                err_bubble = f"❌ Error en paso {step_num} ({location}): {exc_type}: {e}"

                if "bubble" in locals() and bubble is not None:
                    bubble.update_content(err_bubble)
                else:
                    self._add_error_message(err_bubble)
                self._messages.append(ChatMessage(role="assistant", content=err_bubble))
                self._auto_save(user_text, err_bubble, ts)

        threading.Thread(target=_worker, daemon=True).start()

    def _handle_joke_complaint(self, user_text: str, ts: str) -> None:
        """Handler dedicado para quejas sobre humor (chiste o roast), según last_humor_intent."""
        self._messages.append(ChatMessage(role="user", content=user_text))
        self._set_thinking(True)

        def _worker():
            try:
                from aura.personality.humor_tracker import get_last_humor_intent, strip_humor_labels
                from aura.personality.humor_provider import get_humor_provider
                humor_prov = get_humor_provider(default_provider=self._provider)

                last_intent = get_last_humor_intent()
                norm = user_text.lower()
                is_roast_complaint = any(w in norm for w in ("insult", "roast", "palo", "bife", "bardea", "mierda"))
                is_joke_complaint = any(w in norm for w in ("chiste", "chistecito", "dato", "gracioso", "reir", "risa"))

                if is_roast_complaint or (last_intent == "roast" and not is_joke_complaint):
                    _logger.info("Meta-corrección: queja tras roast ('%s') -> regenerando roast correctivo.", user_text)
                    from aura.personality.roast_handler import handle_roast_complaint
                    response_text = handle_roast_complaint(user_text, provider=humor_prov)
                else:
                    _logger.info("Meta-corrección: queja tras chiste ('%s') -> regenerando chiste correctivo.", user_text)
                    from aura.personality.jokes import handle_joke_complaint
                    response_text = handle_joke_complaint(user_text, provider=humor_prov)

                response_clean = strip_humor_labels(response_text)
                self._messages.append(ChatMessage(role="assistant", content=response_clean))
                self._set_thinking(False)
                self._add_assistant_message(response_clean, ts)
                self._auto_save(user_text, response_clean, ts)
                self._speak_if_enabled(response_clean)
            except Exception as e:
                self._set_thinking(False)
                _logger.error("Error procesando queja de humor: %s", e, exc_info=True)
                self._add_error_message(f"Error procesando queja de humor: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def _call_ai(self, provider, context: list[ChatMessage], user_text: str, ts: str) -> None:
        try:
            # 1. Chequeo de seguridad de la entrada del usuario
            user_safety = filter_content(user_text)
            if not user_safety.is_safe:
                self._add_assistant_message(user_safety.message, ts)
                self._set_thinking(False)
                self._auto_save(user_text, user_safety.message, ts)
                return

            # 2. Inyección dinámica del system prompt según personalidad activa y Prompt Maestro ensamblado
            curr_mode = get_current_personality()
            from aura.ai.prompt_assembler import assemble_prompt
            system_prompt = assemble_prompt(
                context="chat",
                personality=curr_mode,
                provider=self._provider.name if self._provider else None,
                model=getattr(self._provider, "model", None),
            )
            ai_messages = [ChatMessage(role="system", content=system_prompt)]
            for m in context:
                if m.role != "system":
                    ai_messages.append(m)

            # 3. Parámetros de generación adaptados al nivel y tipo de mensaje
            is_tone = is_tone_request(user_text)
            gen_params = get_generation_parameters(level=curr_mode.level, is_tone=is_tone)
            call_kwargs = {
                "temperature": gen_params["temperature"],
                "max_tokens": gen_params["max_tokens"],
                "repeat_penalty": gen_params.get("repeat_penalty", 1.2),
                "frequency_penalty": gen_params.get("frequency_penalty", 0.6),
                "presence_penalty": gen_params.get("presence_penalty", 0.6),
            }

            full_response = ""
            # Burbuja de streaming
            bubble = ChatBubble(role="assistant", content="●")
            self._messages_list.controls.append(bubble)
            try:
                self._messages_list.update()
            except Exception:
                pass

            try:
                stream: Iterator[str] = provider.chat_stream(ai_messages, **call_kwargs)
                for chunk in stream:
                    _logger.debug(f"[UTF8_TRACE:provider_chunk] repr={repr(chunk)}")
                    full_response += chunk
                    bubble.update_content(full_response)
            except Exception:
                resp = provider.chat(ai_messages, **call_kwargs)
                full_response = resp.content
                _logger.info(f"[UTF8_TRACE:provider_chat] repr={repr(full_response)}")
                bubble.update_content(full_response)

            _logger.info(f"[UTF8_TRACE:provider_full] repr={repr(full_response)}")

            # 4. Guard anti-loop y recorte / regeneración si es necesario
            def _regen_anti_loop(new_rep_pen: float, new_max_tok: int) -> str:
                regen_kwargs = dict(call_kwargs)
                regen_kwargs["repeat_penalty"] = new_rep_pen
                regen_kwargs["max_tokens"] = new_max_tok
                return provider.chat(ai_messages, **regen_kwargs).content

            clean_response = apply_anti_loop(
                full_response,
                regenerator=_regen_anti_loop,
                current_repeat_penalty=call_kwargs.get("repeat_penalty", 1.2),
                current_max_tokens=call_kwargs.get("max_tokens", 150),
            )
            if clean_response != full_response:
                full_response = clean_response
                bubble.update_content(full_response)

            # 5. Sanitización y validación de seguridad de la salida
            safe_response = sanitize_output(full_response)
            _logger.info(f"[UTF8_TRACE:post_tone_filter] repr={repr(safe_response)}")
            if safe_response != full_response:
                full_response = safe_response
                bubble.update_content(full_response)

            _logger.info(f"[UTF8_TRACE:add_bubble] repr={repr(full_response)}")

            self._messages.append(ChatMessage(role="assistant", content=full_response))
            self._set_thinking(False)

            # Auto-guardado
            self._auto_save(user_text, full_response, ts)
            self._speak_if_enabled(full_response)

        except Exception as e:
            self._set_thinking(False)
            if 'bubble' in locals() and not full_response:
                try:
                    if bubble in self._messages_list.controls:
                        self._messages_list.controls.remove(bubble)
                        self._messages_list.update()
                except Exception:
                    pass

            err_str = str(e)
            if err_str.startswith("[") and "] " in err_str:
                err_str = err_str.split("] ", 1)[1]

            if (
                "10061" in err_str
                or "conexión denegada" in err_str.lower()
                or "connection refused" in err_str.lower()
                or "no se pudo conectar con ollama" in err_str.lower()
                or "no hay proveedor de ia disponible" in err_str.lower()
            ):
                msg = (
                    "❌ No hay proveedor de IA disponible. Ollama no responde en "
                    "localhost:11434 (inicialo con 'ollama serve') o configurá un "
                    "proveedor con API key en Configuración."
                )
            elif err_str.startswith("❌"):
                msg = err_str
            else:
                msg = f"❌ {err_str}"
            self._add_error_message(msg)

    def _speak_if_enabled(self, text: str) -> None:
        """Reproduce la respuesta del asistente mediante el pipeline TTS/RVC configurado."""
        if not text or not text.strip():
            return
        if not settings.get_bool("TTS_AUTO_PLAY", True):
            return
        prov = (settings.get("TTS_PROVIDER", "rvc") or "rvc").lower().strip()
        if prov in ("none", "disabled", "off"):
            return
        from voice.tts import tts_manager
        tts_manager.speak(text, async_play=True)

    def _auto_save(self, user_text: str, assistant_text: str, ts: str) -> None:
        try:
            if self._conversation is None:
                self._conversation = _store.new_conversation()

            conv = self._conversation
            if conv.title in ("Nueva conversación", "") and user_text:
                conv.title = _store.auto_title(user_text)

            conv.messages.append(StoredMessage(role="user", content=user_text, timestamp=ts))
            conv.messages.append(StoredMessage(role="assistant", content=assistant_text, timestamp=ts))
            _store.save(conv)
            self._update_conv_label()
        except Exception as e:
            _logger.error(f"Error auto-guardando conversación: {e}")

    def _set_thinking(self, thinking: bool) -> None:
        self._is_thinking = thinking
        self._send_btn.text = "⏳ ..." if thinking else "➤ Enviar"
        self._send_btn.disabled = thinking
        self._input_box.disabled = thinking
        try:
            self._send_btn.update()
            self._input_box.update()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────
    # Inserción de Burbujas
    # ──────────────────────────────────────────────────────────────

    def _add_user_message(self, text: str, timestamp: str = "") -> None:
        self._messages_list.controls.append(ChatBubble("user", text, timestamp))
        try:
            self._messages_list.update()
        except Exception:
            pass

    def _add_assistant_message(self, text: str, timestamp: str = "") -> None:
        self._messages_list.controls.append(ChatBubble("assistant", text, timestamp))
        try:
            self._messages_list.update()
        except Exception:
            pass

    def _add_system_message(self, text: str) -> None:
        self._messages_list.controls.append(ChatBubble("system", text))
        try:
            self._messages_list.update()
        except Exception:
            pass

    def _add_error_message(self, text: str) -> None:
        self._messages_list.controls.append(ChatBubble("error", text))
        try:
            self._messages_list.update()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────
    # Voz (Fase 22 & Fase 23)
    # ──────────────────────────────────────────────────────────────

    def _on_mic_click(self) -> None:
        if self._audio_panel:
            if not self._audio_panel.visible:
                self._audio_panel.visible = True
                self._audio_btn.text = "✕ Audio"
                try:
                    self._audio_panel.update()
                    self._audio_btn.update()
                except Exception:
                    pass
            self._audio_panel.toggle_talk()
            return

        if self._is_listening:
            return

        self._is_listening = True
        self._mic_btn.icon = ft.Icons.MIC
        self._mic_btn.icon_color = "#FF4444"
        self._mic_btn.bgcolor = _MIC_ACTIVE_BG
        try:
            self._mic_btn.update()
        except Exception:
            pass

        self._add_system_message("🎤 Escuchando... hablá ahora.")

        def _listen_worker():
            try:
                from voice.voice_controller import get_voice_controller
                vc = get_voice_controller()
                stt_result = vc.provider.transcribe_once(
                    mic_index=vc.mic_index,
                    timeout_s=6.0,
                    phrase_timeout_s=4.0,
                )
            except Exception as e:
                from voice.voice_interface import STTResult
                stt_result = STTResult(success=False, error=str(e), provider="error")

            try:
                from voice.voice_command_handler import get_voice_command_handler
                handler = get_voice_command_handler()
                cmd_result = handler.process_transcription(stt_result)
            except Exception as e:
                from voice.voice_command_handler import VoiceCommandResult
                cmd_result = VoiceCommandResult(
                    success=False,
                    transcribed=getattr(stt_result, "text", ""),
                    error=f"Error en comando de voz: {e}",
                )

            self._on_voice_done(cmd_result)

        threading.Thread(target=_listen_worker, daemon=True).start()

    def _on_voice_done(self, result) -> None:
        self._is_listening = False
        self._mic_btn.icon = ft.Icons.MIC_NONE
        self._mic_btn.icon_color = "#8888AA"
        self._mic_btn.bgcolor = _MIC_BTN_BG
        try:
            self._mic_btn.update()
        except Exception:
            pass

        if result.is_stt_error:
            self._add_system_message(f"🎤 {result.error}")
            return

        if result.transcribed:
            self.handle_user_message(result.transcribed, origen="voz")
            return

    def _show_voice_confirm_dialog(self, transcribed: str, message: str) -> None:
        def on_confirm(e):
            self.app_page.pop_dialog()
            self._execute_confirmed_voice_command(transcribed)

        def on_cancel(e):
            self.app_page.pop_dialog()
            self._add_system_message("🚫 Comando cancelado.")

        dlg = ft.AlertDialog(
            title=ft.Text("Confirmar acción peligrosa de voz"),
            content=ft.Column(
                [
                    ft.Text(message, color="#F8D57E", size=13),
                    ft.Text(f'Comando: "{transcribed}"', color="#7A7A9A", size=11),
                ],
                tight=True,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=on_cancel),
                ft.ElevatedButton("Confirmar", on_click=on_confirm, bgcolor="#8B2020", color="#FFFFFF"),
            ],
        )
        self.app_page.show_dialog(dlg)

    def _execute_confirmed_voice_command(self, text: str) -> None:
        self._add_system_message(f"✓ Ejecutando: {text}")

        def _worker():
            try:
                from voice.voice_command_handler import get_voice_command_handler
                result = get_voice_command_handler().execute_confirmed(text)
                if result.success:
                    skill = result.skill_name or "skill"
                    self._add_system_message(f"[{skill}]\n{result.output}")
                else:
                    self._add_error_message(result.error or "Error ejecutando comando.")
            except Exception as e:
                self._add_error_message(f"Error ejecutando acción: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def apply_background_mode(self, has_bg: bool, tokens: Any = None) -> None:
        """Adapta la transparencia de ChatPage cuando hay fondo de pantalla activo."""
        if has_bg:
            self.bgcolor = "transparent"
            self.image = None
            if hasattr(self, "_input_container") and self._input_container:
                self._input_container.bgcolor = "transparent"
            if hasattr(self, "_status_banner") and self._status_banner:
                self._status_banner.bgcolor = "transparent"
        else:
            chat_bg = getattr(tokens, "chat_bg", _BG_DARK) if tokens else _BG_DARK
            self.bgcolor = chat_bg
            bg_img = getattr(tokens, "background_image", None) if tokens else None
            if bg_img:
                self.image = ft.DecorationImage(src=bg_img, repeat=ft.ImageRepeat.REPEAT)
            else:
                self.image = None
            if hasattr(self, "_input_container") and self._input_container:
                self._input_container.bgcolor = "#0F0F22"
            if hasattr(self, "_status_banner") and self._status_banner:
                card_bg = getattr(tokens, "card_bg", "#0A0A1A") if tokens else "#0A0A1A"
                self._status_banner.bgcolor = card_bg

    def apply_theme(self, tokens: Any) -> None:
        """Aplica los tokens de tema visual al fondo y controles del chat respetando fondo activo."""
        from aura.ui.background_manager import background_manager
        if background_manager.is_active:
            self.apply_background_mode(True, tokens)
        else:
            self.apply_background_mode(False, tokens)
        try:
            self.update()
        except Exception:
            pass


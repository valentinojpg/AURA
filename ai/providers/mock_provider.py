"""
AURA — Proveedor Mock de IA (Fase 5)

Proveedor de IA simulado para desarrollo y pruebas.
No requiere Ollama ni ningún servicio externo.
Responde con texto predefinido que simula el comportamiento de un LLM real.

Útil para:
- Desarrollo de la UI de chat (Fase 7) sin necesitar Ollama
- Tests automatizados que no deben depender de un servicio externo
- Demostraciones de la app cuando Ollama no está disponible

El proveedor mock puede configurarse con:
- simulate_delay: agrega un delay artificial (ms) para simular latencia
- simulate_error: fuerza un error en el próximo chat() (útil para testear manejo de errores)
- custom_responses: diccionario keyword → respuesta para respuestas contextuales
"""

from __future__ import annotations

import time
import random
from typing import Iterator

from ai.provider_interface import (
    AIProvider,
    ChatMessage,
    ChatResponse,
    ProviderStatus,
)
from ai.errors import ProviderNotAvailableError
from utils.logger import get_logger


# ── Respuestas predefinidas del mock ──────────────────────────────────────────

_GREETINGS = [
    "¡Hola! Soy AURA, tu asistente de IA. ¿En qué puedo ayudarte hoy?",
    "¡Hola! Estoy listo para ayudarte. ¿Qué necesitás?",
    "¡Buenas! Soy AURA. Podés preguntarme lo que quieras.",
]

_FAREWELLS = [
    "¡Hasta luego! Fue un placer ayudarte.",
    "¡Chau! Cualquier cosa que necesites, acá estoy.",
    "¡Hasta pronto! Que tengas un gran día.",
]

_DEFAULT_RESPONSES = [
    "Entendido. Eso es algo que puedo ayudarte a resolver. Dame un momento para procesar tu consulta.",
    "Interesante pregunta. Basándome en lo que me contás, te puedo dar una respuesta inicial.",
    "Claro, con gusto te ayudo con eso. Aquí va mi análisis:",
    "Buena pregunta. Déjame darte información útil al respecto.",
    "Por supuesto. Voy a responder lo que me preguntás de la mejor manera posible.",
]

# Respuestas contextuales según palabras clave
_KEYWORD_RESPONSES: dict[str, str] = {
    "python": (
        "Python es un lenguaje de programación excelente para principiantes y expertos. "
        "Es conocido por su legibilidad y versatilidad. ¿Querés que te ayude con algo específico en Python?"
    ),
    "error": (
        "Parece que estás teniendo un problema. Para ayudarte mejor, "
        "¿podrías compartirme el mensaje de error completo y el código donde ocurre?"
    ),
    "ayuda": (
        "Estoy acá para ayudarte. Soy AURA, tu asistente de IA. "
        "Puedo ayudarte con programación, preguntas generales, análisis de texto y más. ¿Qué necesitás?"
    ),
    "ollama": (
        "Ollama es la herramienta que me conecta con modelos de IA locales. "
        "Para usarlo, asegurate de tenerlo instalado y corriendo en tu computadora. "
        "Podés descargarlo desde ollama.com"
    ),
    "hola": None,  # Usa _GREETINGS
    "chau": None,  # Usa _FAREWELLS
    "bye": None,   # Usa _FAREWELLS
    "adiós": None, # Usa _FAREWELLS
}

# Modelos ficticios disponibles en el mock
_MOCK_MODELS = [
    "mock:instant",
    "mock:slow",
    "mock:verbose",
]


class MockProvider(AIProvider):
    """
    Proveedor de IA simulado para desarrollo y pruebas (Fase 5).

    No realiza llamadas HTTP reales. Responde con texto predefinido
    para permitir el desarrollo de la interfaz de chat sin Ollama.

    Args:
        simulate_delay_ms: Delay artificial en ms para simular latencia.
                           Default: 200ms. Set a 0 para respuesta instantánea.
        fail_next: Si True, el próximo chat() lanza ProviderNotAvailableError.
                   Se resetea automáticamente después de usarse.
    """

    PROVIDER_NAME = "mock"

    def __init__(
        self,
        simulate_delay_ms: int = 200,
        fail_next: bool = False,
    ):
        self._delay_ms = simulate_delay_ms
        self._fail_next = fail_next
        self._call_count = 0
        self._logger = get_logger("aura.ai.mock")
        self._logger.info(
            f"MockProvider inicializado (delay={simulate_delay_ms}ms, fail_next={fail_next})"
        )

    # ── Propiedad ──────────────────────────────

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    @property
    def fail_next(self) -> bool:
        """Retorna el estado de fail_next."""
        return self._fail_next

    @fail_next.setter
    def fail_next(self, value: bool) -> None:
        """Permite activar o desactivar fail_next externamente."""
        self._fail_next = bool(value)

    # ── Métodos abstractos implementados ──────

    def check_status(self) -> ProviderStatus:
        """
        El mock siempre está disponible (a menos que fail_next esté activo).
        """
        self._logger.debug("MockProvider.check_status() llamado.")
        if self._fail_next:
            return ProviderStatus(
                available=False,
                message="Mock configurado para simular fallo.",
                provider=self.PROVIDER_NAME,
                models=[],
            )
        return ProviderStatus(
            available=True,
            message="Mock activo — No se usa Ollama en este modo.",
            provider=self.PROVIDER_NAME,
            models=list(_MOCK_MODELS),
        )

    def list_models(self) -> list[str]:
        """Retorna los modelos ficticios del mock."""
        self._logger.debug("MockProvider.list_models() llamado.")
        return list(_MOCK_MODELS)

    def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        system: str | None = None,
        **kwargs,
    ) -> ChatResponse:
        """
        Simula una respuesta de IA con texto predefinido.

        Args:
            messages: Historial de mensajes (solo se usa el último mensaje del usuario).
            model: Ignorado en el mock (siempre usa 'mock:instant').
            temperature: Ignorado en el mock.
            max_tokens: Ignorado en el mock.

        Returns:
            ChatResponse con texto simulado.

        Raises:
            ProviderNotAvailableError: Si fail_next estaba en True.
        """
        self._call_count += 1
        self._logger.debug(
            f"MockProvider.chat() llamado — call #{self._call_count}, "
            f"mensajes={len(messages)}"
        )

        # Simular fallo si está configurado
        if self._fail_next:
            self._fail_next = False
            self._logger.warning("MockProvider: simulando fallo de proveedor.")
            raise ProviderNotAvailableError(
                "Mock configurado para simular fallo (fail_next=True).",
                provider=self.PROVIDER_NAME,
            )

        # Simular delay de red
        if self._delay_ms > 0:
            time.sleep(self._delay_ms / 1000)

        # Obtener el último mensaje del usuario
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.role == "user":
                last_user_msg = msg.content.strip().lower()
                break

        response_text = self._generate_response(last_user_msg)
        used_model = model or "mock:instant"

        self._logger.info(
            f"MockProvider: respuesta generada para call #{self._call_count} "
            f"(model={used_model})"
        )

        return ChatResponse(
            content=response_text,
            model=used_model,
            provider=self.PROVIDER_NAME,
            done=True,
            tokens_prompt=len(last_user_msg.split()),
            tokens_response=len(response_text.split()),
            raw={"mock": True, "call_count": self._call_count},
        )

    def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        system: str | None = None,
        **kwargs,
    ) -> Iterator[str]:
        """
        Streaming simulado: emite la respuesta palabra por palabra con delay.

        Simula el efecto de streaming real para que la UI pueda
        desarrollar su lógica de actualización incremental.

        Yields:
            Fragmentos de texto de la respuesta.
        """
        response = self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens, system=system, **kwargs)
        words = response.content.split(" ")

        for i, word in enumerate(words):
            # Agregar espacio entre palabras (no al final)
            chunk = word if i == len(words) - 1 else word + " "
            yield chunk
            # Pequeño delay entre palabras para simular streaming
            if self._delay_ms > 0:
                time.sleep(self._delay_ms / 1000 / max(len(words), 1))

    # ── Configuración dinámica ─────────────────

    def set_delay(self, ms: int) -> None:
        """Ajusta el delay de simulación en milisegundos."""
        self._delay_ms = max(0, ms)
        self._logger.debug(f"MockProvider: delay ajustado a {self._delay_ms}ms")

    def set_fail_next(self, fail: bool = True) -> None:
        """Configura si el próximo chat() debe lanzar un error."""
        self._fail_next = fail
        self._logger.debug(f"MockProvider: fail_next={fail}")

    @property
    def call_count(self) -> int:
        """Número total de llamadas a chat() realizadas."""
        return self._call_count

    def reset(self) -> None:
        """Resetea el contador de llamadas y el estado de fallo."""
        self._call_count = 0
        self._fail_next = False
        self._logger.debug("MockProvider: estado reseteado.")

    # ── Lógica de respuestas ───────────────────

    def _generate_response(self, user_input: str) -> str:
        """
        Genera una respuesta simulada basada en el input del usuario.

        Busca palabras clave en el input para dar respuestas contextuales.
        Si no hay coincidencia, elige una respuesta genérica al azar.
        """
        # Saludo
        for keyword in ("hola", "buenos", "buenas", "hey", "hi"):
            if keyword in user_input:
                return random.choice(_GREETINGS)

        # Despedida
        for keyword in ("chau", "bye", "adiós", "adios", "hasta luego", "ciao"):
            if keyword in user_input:
                return random.choice(_FAREWELLS)

        # Respuestas por palabra clave
        for keyword, response in _KEYWORD_RESPONSES.items():
            if keyword in user_input and response is not None:
                return response

        # Respuesta genérica aleatoria
        base = random.choice(_DEFAULT_RESPONSES)

        # Agregar contexto del mensaje si es corto
        if len(user_input) < 100:
            return f"{base}\n\n[Mock] Recibí tu mensaje: \"{user_input[:60]}{'...' if len(user_input) > 60 else ''}\""

        return base

    def __repr__(self) -> str:
        return (
            f"MockProvider(delay={self._delay_ms}ms, "
            f"fail_next={self._fail_next}, calls={self._call_count})"
        )

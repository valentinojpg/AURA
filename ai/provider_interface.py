"""
AURA — Interfaz abstracta del proveedor de IA (Fase 5)

Define el contrato que deben cumplir todos los proveedores de IA.
Cualquier proveedor (Ollama, OpenAI, mock, etc.) debe heredar de
AIProvider e implementar sus métodos abstractos.

Principios de diseño:
- Los métodos de I/O son síncronos en Fase 5.
  (Streaming asíncrono se agregará en Fase 7 si se necesita.)
- Cada proveedor expone: nombre, estado, modelos y chat.
- Los errores deben mapearse a las excepciones de ai/errors.py.
- La interfaz NO depende de ninguna librería externa; solo stdlib.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator


# ──────────────────────────────────────────────
# Tipos de datos compartidos
# ──────────────────────────────────────────────

@dataclass
class ChatMessage:
    """
    Representa un mensaje en una conversación de chat.

    Attributes:
        role: Rol del emisor. Valores válidos: "user", "assistant", "system".
        content: Contenido textual del mensaje.
    """
    role: str    # "user" | "assistant" | "system"
    content: str

    def to_dict(self) -> dict:
        """Convierte el mensaje a diccionario (útil para serializar a JSON)."""
        return {"role": self.role, "content": self.content}

    @classmethod
    def from_dict(cls, data: dict) -> "ChatMessage":
        """Crea un ChatMessage desde un diccionario."""
        return cls(role=data["role"], content=data["content"])

    def __repr__(self) -> str:
        preview = self.content[:40] + "..." if len(self.content) > 40 else self.content
        return f"ChatMessage(role={self.role!r}, content={preview!r})"


@dataclass
class ChatResponse:
    """
    Respuesta de un proveedor de IA a un chat request.

    Attributes:
        content: Texto completo de la respuesta del asistente.
        model: Nombre del modelo que generó la respuesta.
        provider: Nombre del proveedor que procesó la solicitud.
        done: True si la respuesta está completa (no es streaming parcial).
        tokens_prompt: Tokens usados en el prompt (si el proveedor lo informa).
        tokens_response: Tokens generados en la respuesta (si disponible).
        raw: Respuesta original del proveedor (para diagnóstico).
    """
    content: str
    model: str
    provider: str
    done: bool = True
    tokens_prompt: int = 0
    tokens_response: int = 0
    raw: dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        """Total de tokens usados en la interacción."""
        return self.tokens_prompt + self.tokens_response

    def __str__(self) -> str:
        return self.content

    def strip(self, *args, **kwargs) -> str:
        return self.content.strip(*args, **kwargs)

    def lower(self) -> str:
        return self.content.lower()

    def upper(self) -> str:
        return self.content.upper()

    def startswith(self, *args, **kwargs) -> bool:
        return self.content.startswith(*args, **kwargs)

    def endswith(self, *args, **kwargs) -> bool:
        return self.content.endswith(*args, **kwargs)

    def split(self, *args, **kwargs) -> list[str]:
        return self.content.split(*args, **kwargs)

    def replace(self, *args, **kwargs) -> str:
        return self.content.replace(*args, **kwargs)

    def __contains__(self, item) -> bool:
        return item in self.content

    def __len__(self) -> int:
        return len(self.content)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.content == other
        return super().__eq__(other)

    def __repr__(self) -> str:
        preview = self.content[:40] + "..." if len(self.content) > 40 else self.content
        return (
            f"ChatResponse(provider={self.provider!r}, model={self.model!r}, "
            f"done={self.done}, content={preview!r})"
        )


@dataclass
class ProviderStatus:
    """
    Estado de conectividad y disponibilidad de un proveedor.

    Attributes:
        available: True si el proveedor está accesible y listo.
        message: Descripción del estado (para mostrar en UI).
        models: Lista de nombres de modelos disponibles en el proveedor.
        provider: Nombre del proveedor.
    """
    available: bool
    message: str
    provider: str
    models: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"ProviderStatus(provider={self.provider!r}, "
            f"available={self.available}, models={len(self.models)})"
        )


# ──────────────────────────────────────────────
# Interfaz abstracta
# ──────────────────────────────────────────────

class AIProvider(ABC):
    """
    Interfaz abstracta que deben implementar todos los proveedores de IA.

    Contrato:
    - name / provider_name: propiedad con el nombre identificador del proveedor.
    - requires_api_key: indica si el proveedor requiere clave de API.
    - health_check(): verifica conectividad y retorna (ok, detalle).
    - check_status(): verifica disponibilidad y retorna ProviderStatus.
    - list_models(): retorna lista de modelos disponibles.
    - chat(): envía una conversación y retorna ChatResponse (compatible con str).
    - chat_stream(): versión generadora del chat.

    Manejo de errores:
    - Todos los métodos deben capturar errores del proveedor
      y relanzarlos como excepciones de ai/errors.py.
    """

    # ── Propiedades ────────────────────────────

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Nombre único del proveedor (ej: 'ollama', 'mock', 'openai')."""
        ...

    @property
    def name(self) -> str:
        """Alias de provider_name para el contrato BaseAIProvider."""
        return self.provider_name

    @property
    def requires_api_key(self) -> bool:
        """Indica si el proveedor requiere una API Key para funcionar."""
        return False

    # ── Métodos de normalización y diagnóstico ─

    @staticmethod
    def normalize_messages(
        messages: list[ChatMessage] | list[dict] | list[str] | str,
        system: str | None = None,
    ) -> list[ChatMessage]:
        """Normaliza cualquier formato de mensajes a list[ChatMessage]."""
        result: list[ChatMessage] = []
        if system:
            result.append(ChatMessage(role="system", content=str(system)))

        if isinstance(messages, str):
            result.append(ChatMessage(role="user", content=messages))
        elif isinstance(messages, list):
            for m in messages:
                if isinstance(m, ChatMessage):
                    result.append(m)
                elif isinstance(m, dict):
                    result.append(ChatMessage(role=m.get("role", "user"), content=m.get("content", "")))
                elif isinstance(m, str):
                    result.append(ChatMessage(role="user", content=m))
                else:
                    result.append(ChatMessage(role="user", content=str(m)))
        return result

    def health_check(self) -> tuple[bool, str]:
        """
        Verifica conectividad y disponibilidad del proveedor.

        Returns:
            Tuple (ok, detalle): (True, "mensaje") si está operativo, (False, "error") si no.
        """
        try:
            status = self.check_status()
            return (status.available, status.message)
        except Exception as e:
            return (False, str(e))


    # ── Métodos abstractos ─────────────────────

    @abstractmethod
    def check_status(self) -> ProviderStatus:
        """
        Verifica si el proveedor está disponible.

        Returns:
            ProviderStatus con available=True si el proveedor responde,
            False en caso contrario.

        Note:
            Este método NO debe lanzar excepciones; en cambio,
            retorna ProviderStatus con available=False y el mensaje de error.
        """
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        """
        Retorna la lista de modelos disponibles en el proveedor.

        Returns:
            Lista de nombres de modelos (strings).

        Raises:
            ProviderNotAvailableError: Si el proveedor no está accesible.
        """
        ...

    @abstractmethod
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
        Envía una conversación al proveedor y retorna la respuesta completa.

        Args:
            messages: Historial de mensajes (sistema + usuario + asistente).
            model: Nombre del modelo a usar. Si es None, usa el configurado.
            temperature: Control de creatividad [0.0 - 1.0]. Default 0.7.
            max_tokens: Límite de tokens en la respuesta. None = sin límite.
            system: Instrucción de sistema opcional (se antepone a los mensajes).
            **kwargs: Parámetros adicionales (repeat_penalty, frequency_penalty, presence_penalty, etc.).

        Returns:
            ChatResponse con la respuesta completa del asistente.
        """
        ...

    # ── Método con implementación por defecto ──

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
        Versión streaming del chat: genera fragmentos de texto incrementalmente.

        Implementación por defecto: delega a chat() y retorna la respuesta completa
        en un solo yield. Los proveedores que soportan streaming real deben
        sobreescribir este método.

        Args:
            messages: Historial de mensajes.
            model: Nombre del modelo a usar.
            temperature: Control de creatividad.
            max_tokens: Límite de tokens en la respuesta.
            system: Instrucción de sistema opcional.
            **kwargs: Parámetros adicionales.

        Yields:
            Fragmentos de texto (str) de la respuesta del asistente.
        """
        response = self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens, system=system, **kwargs)
        yield response.content

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} provider={self.provider_name!r}>"


# Alias para compatibilidad con contrato BaseAIProvider
BaseAIProvider = AIProvider

__all__ = [
    "AIProvider",
    "BaseAIProvider",
    "ChatMessage",
    "ChatResponse",
    "ProviderStatus",
]

"""
AURA — Manejador de Comandos de Voz (Fase 23 — Comandos de voz)

VoiceCommandHandler conecta el stack de STT (Fase 22) con el CommandRouter
(Fase 13) para que el usuario pueda dictar comandos en lugar de escribirlos.

Funcionalidades:
    - Transcribe el audio del micrófono con el proveedor STT activo
    - Detecta si el texto transcrito es un comando peligroso
    - Para acciones peligrosas, requiere confirmación explícita antes de ejecutar
    - Para acciones normales, enruta directamente al CommandRouter
    - Retorna VoiceCommandResult con toda la información del flujo

Acciones peligrosas (requieren confirmación):
    - apagar [--ahora]
    - reiniciar [--ahora]
    - eliminar <ruta> --ahora
    - papelera --ahora
    - cerrar <proceso_critico>

Flujo push-to-talk:
    1. Usuario hace clic en 🎤
    2. STT captura audio → texto
    3. VoiceCommandHandler analiza si es peligroso
       a) Si es peligroso → retorna VoiceCommandResult(needs_confirm=True)
          La UI muestra diálogo de confirmación modal
          Si confirma → ejecuta; si cancela → descarta
       b) Si es normal → enruta al CommandRouter y retorna resultado
    4. UI muestra resultado (igual que un comando de texto)

Diseño:
    - Sin estado interno mutable (cada llamada es independiente)
    - No lanza excepciones: todos los errores quedan en VoiceCommandResult.error
    - VoiceCommandResult es serializable y tiene __bool__
    - DANGEROUS_PREFIXES es configurable para tests
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from utils.logger import get_logger

_logger = get_logger("aura.voice.command_handler")

# Importación lazy del singleton: se resuelve en tiempo de uso para evitar
# ciclos de importación con core.command_router → skills → voice.
# El objeto se establece en _get_command_router() la primera vez que se usa.
try:
    from core.command_router import command_router as _cr_import
    command_router = _cr_import
except Exception:  # pragma: no cover
    command_router = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Comandos que requieren confirmación explícita cuando vienen de voz
# ---------------------------------------------------------------------------

#: Primeras palabras que indican una acción potencialmente destructiva.
#: Se comparan con el primer token del texto transcrito (case-insensitive).
DANGEROUS_COMMAND_PREFIXES: frozenset[str] = frozenset({
    "apagar",
    "reiniciar",
    "papelera",
    "bloquear",
})

#: Pares (comando, flag) que son peligrosos solo si incluyen el flag --ahora.
#: El texto debe contener AMBOS para considerarse peligroso.
DANGEROUS_WITH_FLAG: tuple[tuple[str, str], ...] = (
    ("eliminar",  "--ahora"),
    ("cerrar",    "--ahora"),
)

#: Mensajes de confirmación por tipo de comando peligroso.
_CONFIRM_MESSAGES: dict[str, str] = {
    "apagar":    "⚠️ ¿Confirmas que querés apagar el equipo?",
    "reiniciar": "⚠️ ¿Confirmas que querés reiniciar el equipo?",
    "papelera":  "⚠️ ¿Confirmas que querés vaciar la papelera de reciclaje?",
    "eliminar":  "⚠️ ¿Confirmas que querés eliminar el archivo ahora?",
    "cerrar":    "⚠️ ¿Confirmas que querés cerrar ese proceso?",
    "bloquear":  "⚠️ ¿Confirmás que querés bloquear la sesión de Windows?",
}

_DEFAULT_CONFIRM_MSG = "⚠️ Esta acción puede ser peligrosa. ¿Confirmás?"


# ---------------------------------------------------------------------------
# Resultado del manejador
# ---------------------------------------------------------------------------

@dataclass
class VoiceCommandResult:
    """
    Resultado del procesamiento de un comando de voz.

    Attributes:
        success:        True si la operación fue exitosa.
        transcribed:    Texto transcrito del audio (vacío si falló la transcripción).
        output:         Texto de respuesta para mostrar al usuario.
        error:          Mensaje de error (vacío si success=True).
        skill_name:     Nombre de la skill que procesó el comando (si aplica).
        command:        Primer token del texto transcrito.
        needs_confirm:  True si se necesita confirmación del usuario antes de ejecutar.
        confirm_msg:    Mensaje a mostrar en el diálogo de confirmación.
        routed_to_ai:   True si el texto fue enviado a la IA (no a una skill).
        is_stt_error:   True si el error fue en la transcripción (no en la ejecución).
    """

    success:       bool  = False
    transcribed:   str   = ""
    output:        str   = ""
    error:         str   = ""
    skill_name:    str   = ""
    command:       str   = ""
    needs_confirm: bool  = False
    confirm_msg:   str   = ""
    routed_to_ai:  bool  = False
    is_stt_error:  bool  = False

    def __bool__(self) -> bool:
        """True si fue exitoso y no requiere confirmación pendiente."""
        return self.success and not self.needs_confirm

    def __repr__(self) -> str:
        if self.needs_confirm:
            return f"VoiceCommandResult(needs_confirm, cmd={self.command!r})"
        if self.success:
            return f"VoiceCommandResult(ok, cmd={self.command!r}, text={self.transcribed[:30]!r})"
        return f"VoiceCommandResult(err={self.error!r})"


# ---------------------------------------------------------------------------
# Manejador principal
# ---------------------------------------------------------------------------

class VoiceCommandHandler:
    """
    Conecta el STT con el CommandRouter para manejar comandos de voz.

    No gestiona threads ni UI: eso lo hace la capa superior (ChatPage).
    Es stateless: cada llamada es independiente.

    Uso básico:
        handler = VoiceCommandHandler()

        # 1. Transcribir audio → texto
        stt_result = voice_controller.provider.transcribe_once(...)

        # 2. Procesar el texto transcrito
        result = handler.process_transcription(stt_result)

        if result.needs_confirm:
            # Mostrar diálogo de confirmación en la UI
            confirmed = show_confirm_dialog(result.confirm_msg)
            if confirmed:
                result = handler.execute_confirmed(result.transcribed)
        elif result.routed_to_ai:
            # Enviar a la IA normal
            pass
        else:
            # Mostrar result.output en el chat
            pass
    """

    def __init__(
        self,
        dangerous_prefixes: Optional[frozenset[str]] = None,
        dangerous_with_flag: Optional[tuple] = None,
    ) -> None:
        """
        Inicializa el manejador.

        Args:
            dangerous_prefixes:  Conjunto de prefijos peligrosos (override para tests).
            dangerous_with_flag: Pares (cmd, flag) peligrosos con flag (override para tests).
        """
        self._dangerous_prefixes = (
            dangerous_prefixes if dangerous_prefixes is not None
            else DANGEROUS_COMMAND_PREFIXES
        )
        self._dangerous_with_flag = (
            dangerous_with_flag if dangerous_with_flag is not None
            else DANGEROUS_WITH_FLAG
        )

    # ── API pública ────────────────────────────────────────────────────────

    def process_transcription(self, stt_result) -> VoiceCommandResult:
        """
        Procesa el resultado de una transcripción STT.

        Args:
            stt_result: STTResult del proveedor de voz.

        Returns:
            VoiceCommandResult con el resultado del procesamiento.
        """
        # --- Error de transcripción ---
        if not stt_result.success or not stt_result.text.strip():
            error = stt_result.error or "No se detectó audio."
            _logger.warning(f"VoiceCommandHandler: STT falló — {error}")
            return VoiceCommandResult(
                success=False,
                transcribed="",
                error=error,
                is_stt_error=True,
            )

        text = stt_result.text.strip()
        _logger.info(f"VoiceCommandHandler: texto transcrito = {text!r}")

        # --- Detectar si es un comando peligroso ---
        if self.is_dangerous(text):
            command = text.split()[0].lower()
            confirm_msg = _CONFIRM_MESSAGES.get(command, _DEFAULT_CONFIRM_MSG)
            _logger.info(
                f"VoiceCommandHandler: comando peligroso detectado — {command!r}"
            )
            return VoiceCommandResult(
                success=False,
                transcribed=text,
                command=command,
                needs_confirm=True,
                confirm_msg=confirm_msg,
            )

        # --- Enrutar al CommandRouter ---
        return self._route_text(text)

    def execute_confirmed(self, text: str) -> VoiceCommandResult:
        """
        Ejecuta un comando que fue confirmado por el usuario.

        Se llama después de que el usuario confirmó una acción peligrosa
        en el diálogo de confirmación.

        Args:
            text: Texto original del comando (ya transcrito y confirmado).

        Returns:
            VoiceCommandResult con el resultado de la ejecución.
        """
        _logger.info(f"VoiceCommandHandler: ejecutando comando confirmado — {text!r}")
        return self._route_text(text)

    def is_dangerous(self, text: str) -> bool:
        """
        Determina si un texto transcrito corresponde a un comando peligroso.

        Args:
            text: Texto transcrito a analizar.

        Returns:
            True si el comando requiere confirmación explícita.
        """
        if not text or not text.strip():
            return False

        tokens = text.strip().lower().split()
        if not tokens:
            return False

        first = tokens[0]

        # Prefijos siempre peligrosos
        if first in self._dangerous_prefixes:
            return True

        # Pares (comando, flag) peligrosos
        text_lower = text.strip().lower()
        for cmd, flag in self._dangerous_with_flag:
            if first == cmd and flag in text_lower:
                return True

        return False

    def get_confirm_message(self, text: str) -> str:
        """
        Retorna el mensaje de confirmación para un comando peligroso.

        Args:
            text: Texto del comando peligroso.

        Returns:
            Mensaje de confirmación localizado en español.
        """
        if not text:
            return _DEFAULT_CONFIRM_MSG
        tokens = text.strip().lower().split()
        cmd = tokens[0] if tokens else ""
        return _CONFIRM_MESSAGES.get(cmd, _DEFAULT_CONFIRM_MSG)

    # ── Helpers privados ───────────────────────────────────────────────────

    def _route_text(self, text: str) -> VoiceCommandResult:
        """
        Enruta el texto al CommandRouter.

        Args:
            text: Texto a enrutar.

        Returns:
            VoiceCommandResult con el resultado del router.
        """
        # Usar el command_router a nivel de módulo (patcheable en tests).
        # Si no pudo importarse al inicio, intentar de nuevo ahora.
        router = command_router
        if router is None:
            try:
                from core.command_router import command_router as _cr
                router = _cr
            except ImportError as e:
                _logger.error(f"VoiceCommandHandler: no se pudo importar command_router: {e}")
                return VoiceCommandResult(
                    success=False,
                    transcribed=text,
                    error="Error interno: no se pudo acceder al router de comandos.",
                    command=text.split()[0].lower() if text.split() else "",
                )

        tokens = text.split()
        command = tokens[0].lower() if tokens else ""

        try:
            route_result = router.route(text)
        except Exception as e:
            _logger.error(
                f"VoiceCommandHandler: error al enrutar '{text}': {e}",
                exc_info=True,
            )
            return VoiceCommandResult(
                success=False,
                transcribed=text,
                error=f"Error al ejecutar el comando: {e}",
                command=command,
            )

        if route_result is None:
            # El texto no es un comando → debe ir a la IA
            _logger.debug(
                f"VoiceCommandHandler: '{text}' no es comando — marcar para IA."
            )
            return VoiceCommandResult(
                success=True,
                transcribed=text,
                command=command,
                routed_to_ai=True,
            )

        # El router procesó el texto
        return VoiceCommandResult(
            success=route_result.success,
            transcribed=text,
            output=route_result.output,
            error=route_result.error,
            skill_name=route_result.skill_name,
            command=route_result.command or command,
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_handler_instance: Optional[VoiceCommandHandler] = None


def get_voice_command_handler() -> VoiceCommandHandler:
    """
    Retorna el singleton de VoiceCommandHandler.

    La primera llamada crea la instancia con la configuración por defecto.
    """
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = VoiceCommandHandler()
    return _handler_instance

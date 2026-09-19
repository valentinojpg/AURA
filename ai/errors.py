"""
AURA — Errores específicos del módulo de IA (Fase 5)

Define la jerarquía de excepciones para todo el módulo ai/.
Permite capturar errores de IA de forma precisa sin exponer
detalles de implementación del proveedor al resto de la app.

Jerarquía:
    AuraAIError
    ├── ProviderNotAvailableError   (servicio no accesible)
    ├── ProviderConfigError         (configuración inválida)
    ├── ModelNotFoundError          (modelo no instalado/disponible)
    ├── RequestTimeoutError         (timeout en solicitud)
    └── ResponseParseError          (respuesta con formato inesperado)
"""


class AuraAIError(Exception):
    """
    Clase base para todos los errores del módulo de IA de AURA.

    Atributos:
        message: Descripción legible del error.
        provider: Nombre del proveedor que generó el error (opcional).
        status_code: Código HTTP numérico asociado (si aplica).
        detail: Detalle específico de la causa o cuerpo del error.
    """

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        status_code: int | None = None,
        detail: str = "",
    ):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.status_code = status_code
        self.detail = detail

    @property
    def reason(self) -> str:
        """Retorna una causa corta y limpia formateada para avisos de fallback."""
        if self.status_code:
            det = self.detail or self.message
            if det.startswith(f"{self.status_code}:"):
                return det
            return f"{self.status_code}: {det}"
        return self.detail or self.message

    def __str__(self) -> str:
        prefix = f"[{self.provider}] " if self.provider else ""
        return f"{prefix}{self.message}"

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(message={self.message!r}, "
            f"provider={self.provider!r}, status_code={self.status_code!r})"
        )


class ProviderNotAvailableError(AuraAIError):
    """
    El servicio del proveedor de IA no está accesible.

    Se lanza cuando:
    - Ollama no está corriendo
    - La URL del proveedor no responde
    - El servicio está caído o bloqueado por firewall
    """


class ProviderConfigError(AuraAIError):
    """
    La configuración del proveedor es inválida.

    Se lanza cuando:
    - La URL tiene formato incorrecto
    - Faltan claves de API requeridas
    - El proveedor especificado no existe
    """


class AuthenticationError(AuraAIError):
    """
    Error de autenticación con el proveedor de IA.

    Se lanza cuando:
    - La API Key es inválida, expiró o no tiene permisos.
    - El proveedor retorna código HTTP 401 o 403.
    """


class ModelNotFoundError(AuraAIError):
    """
    El modelo solicitado no está disponible en el proveedor.

    Se lanza cuando:
    - El modelo no está descargado en Ollama
    - El nombre del modelo es incorrecto
    - El proveedor no tiene acceso al modelo
    """

    def __init__(
        self,
        message: str,
        model: str | None = None,
        provider: str | None = None,
        status_code: int | None = 404,
        detail: str = "",
    ):
        super().__init__(message, provider=provider, status_code=status_code, detail=detail)
        self.model = model

    def __repr__(self) -> str:
        return (
            f"ModelNotFoundError(message={self.message!r}, "
            f"model={self.model!r}, provider={self.provider!r}, status_code={self.status_code!r})"
        )


class RequestTimeoutError(AuraAIError):
    """
    La solicitud al proveedor de IA superó el tiempo de espera.

    Se lanza cuando:
    - El proveedor tarda más del timeout configurado
    - La conexión se cuelga sin respuesta
    """


class ResponseParseError(AuraAIError):
    """
    La respuesta del proveedor no pudo ser interpretada.

    Se lanza cuando:
    - El JSON de respuesta tiene formato inesperado
    - Falta un campo esperado en la respuesta
    - El contenido de la respuesta está vacío o malformado
    """

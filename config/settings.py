"""
AURA — Servicio de configuración (Fase 2)

Gestiona la carga, validación y acceso a la configuración del proyecto.
Lee el archivo .env desde la raíz del proyecto.
Provee valores por defecto para todas las claves conocidas.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv, set_key, dotenv_values

# Directorio raíz del proyecto (dos niveles arriba de este archivo)
ROOT_DIR = Path(__file__).resolve().parent.parent

# Ruta al archivo .env
ENV_FILE = ROOT_DIR / ".env"

# ──────────────────────────────────────────────
# Valores por defecto de todas las claves .env
# ──────────────────────────────────────────────
DEFAULTS: dict[str, str] = {
    # Proveedor de IA
    "AI_PROVIDER": "ollama",
    "AI_MODEL": "qwen2.5:3b",
    "OLLAMA_URL": "http://localhost:11434",
    # Idioma
    "APP_LANGUAGE": "es",
    # Micrófono
    "MICROPHONE_INDEX": "0",
    # Carpeta de trabajo
    "WORKSPACE_PATH": str(Path.home() / "Documents"),
    # Interfaz
    "APP_THEME": "dark",
    # Seguridad
    "CONFIRM_DESTRUCTIVE": "true",
    "CONFIRM_SHUTDOWN": "true",
    "CONFIRMAR_CIERRE_APP": "false",
    # Primera ejecución
    "FIRST_RUN": "true",
    # Audio y Dispositivos de Voz
    "AUDIO_INPUT_DEVICE": "",
    "AUDIO_OUTPUT_DEVICE": "",
    "VOICE_SILENCE_RMS": "0.02",
    "VOICE_SILENCE_SECONDS": "1.5",
    "VOICE_WAIT_SPEECH_SECONDS": "5.0",
    "VOICE_AUTO_SEND": "true",
    # Síntesis y Conversión de Voz (TTS & RVC)
    "TTS_PROVIDER": "rvc",
    "RVC_VOZ": "aura",
    "RVC_TTS_BASE": "edge",
    "RVC_TTS_BASE_VOICE": "es-MX-DaliaNeural",
    "RVC_PITCH": "0",
    "RVC_INDEX_RATE": "0.6",
    "RVC_DEVICE": "auto",
    "TTS_AUTO_PLAY": "true",
    # Locución de Mensajes y Caché TTS (Fase 77)
    "SPEAK_BUTTON": "true",
    "TTS_MSG_CACHE": "true",
    "TTS_CACHE_MAX_MB": "200",
    # Pipeline y Router de Comandos
    "ROUTER_FIRST": "true",
    # Navegador Web Preferido
    "BROWSER_PREFERIDO": "firefox",
    # Personalidad y Tono (Fase 51)
    "AURA_PERSONALITY": "profesional",
    "AURA_RUDE_LEVEL": "0",
    "AURA_ALLOW_DARK_HUMOR": "false",
    "AURA_ALLOW_INSULTS": "false",
    "AURA_TEMP": "",
    "AURA_REPEAT_PENALTY": "",
    "AURA_MAX_TOKENS_TONO": "",
    # Humor y Respuestas Cómicas (Fase 64)
    "HUMOR_SOURCE": "hybrid",
    "HUMOR_PROVIDER": "auto",
    # Comprensión de comandos con errores de tipeo (Fuzzy + LLM)
    "FUZZY_THRESHOLD": "0.85",
    "FUZZY_ASK_THRESHOLD": "0.60",
    "USE_LLM_INTERPRETER": "true",
    # Núcleo Multi-proveedor de IA (Fase 55)
    "AI_FALLBACK_OLLAMA": "true",
    "AI_HTTP_TIMEOUT": "30",
    "OPENAI_API_KEY": "",
    "ANTHROPIC_API_KEY": "",
    "GEMINI_API_KEY": "",
    "XAI_API_KEY": "",
    "CUSTOM_BASE_URL": "",
    "CUSTOM_API_KEY": "",
    "CUSTOM_MODEL": "",
    # Modo desarrollo / tests: permite MockProvider
    "AI_ALLOW_MOCK": "false",
    # Prompt Maestro (Fase 69)
    "PROMPT_MAESTRO": "true",
    "PROMPT_DEBUG": "false",
    # Multi-step Planner & Media Play (Fases 71 & 72)
    "PLAN_MAX_STEPS": "8",
    "PLAN_WAIT_APP_SECONDS": "5",
    "PLAN_WAIT_PAGE_SECONDS": "2",
    "PLAN_ON_ERROR": "stop",
    "MEDIA_SERVICE": "youtube_music",
    "MEDIA_YT_API_KEY": "",
    "PLAN_STRICT": "false",
    # Proveedor STT y Parámetros Faster-Whisper (Fase 74)
    "STT_PROVIDER": "whisper",
    "WHISPER_MODEL": "small",
    "WHISPER_COMPUTE": "auto",
    "WHISPER_LANGUAGE": "es",
    "WHISPER_VAD": "true",
    # Personalización Visual y Temas (Fase 76)
    "THEME_STYLE": "solid",
    "THEME_COLOR_1": "#0C0C18",
    "THEME_COLOR_2": "#1A1A36",
    "THEME_COLOR_3": "#3B4FC8",
    "THEME_COLOR_4": "#60A5FA",
    "THEME_SCHEME": "triada",
    "THEME_PRESET": "Azul AURA",
    # Fondo de Pantalla Personalizado (Fase 78)
    "BG_IMAGE_PATH": "",
    "BG_FIT": "cover",
    "BG_SIDEBAR_OPACITY": "0.0",
    "BG_SCRIM_OPACITY": "0.25",
    "BG_GIF_MODE": "native",
}



def mask_api_key(key: str | None) -> str:
    """Enmascara una API key para logs y UI (ej: sk-...1234 o ***)."""
    if not key:
        return ""
    k = str(key).strip()
    if len(k) <= 8:
        return "***"
    return f"{k[:3]}...{k[-4:]}"


def format_key_loaded(key: str | None) -> str:
    """Formatea la confirmación de key cargada para la UI (ej: 'key cargada: ...abcd')."""
    if not key:
        return ""
    k = str(key).strip()
    if len(k) <= 4:
        return "key cargada: ****"
    return f"key cargada: ...{k[-4:]}"




class Settings:
    """
    Servicio de configuración de AURA.

    Carga el archivo .env al instanciarse.
    Si el archivo no existe, lo crea con los valores por defecto.
    Provee métodos get/set para leer y escribir claves de forma segura.

    Uso:
        from config.settings import settings
        theme = settings.get("APP_THEME")
        settings.set("APP_THEME", "light")
    """

    ROOT_DIR: Path = ROOT_DIR

    def __init__(self):
        self._logger = logging.getLogger("aura.config")
        self._ensure_env_file()
        self._load()

    # ──────────────────────────────────────────────
    # Inicialización
    # ──────────────────────────────────────────────

    def _ensure_env_file(self) -> None:
        """Crea el archivo .env con valores por defecto si no existe."""
        if not ENV_FILE.exists():
            self._logger.info(".env no encontrado. Creando con valores por defecto.")
            ENV_FILE.touch()
            for key, value in DEFAULTS.items():
                set_key(str(ENV_FILE), key, value)
            self._logger.info(f".env creado en: {ENV_FILE}")

    def _load(self) -> None:
        """Carga las variables del archivo .env en el entorno."""
        load_dotenv(dotenv_path=ENV_FILE, override=True)
        self._logger.debug(f"Configuración cargada desde {ENV_FILE}")

    # ──────────────────────────────────────────────
    # Lectura
    # ──────────────────────────────────────────────

    def get(self, key: str, fallback: str | None = None) -> str | None:
        """
        Retorna el valor de una clave de configuración.

        Prioridad: variable de entorno cargada > valor por defecto > fallback.
        """
        value = os.environ.get(key)
        if value is not None:
            return value
        if key in DEFAULTS:
            return DEFAULTS[key]
        return fallback

    def get_bool(self, key: str, fallback: bool = False) -> bool:
        """Retorna el valor de una clave como booleano."""
        val = self.get(key, str(fallback)).strip().lower()
        return val in ("true", "1", "yes", "on")

    def get_int(self, key: str, fallback: int = 0) -> int:
        """Retorna el valor de una clave como entero."""
        try:
            return int(self.get(key, str(fallback)))
        except (ValueError, TypeError):
            return fallback

    def get_float(self, key: str, fallback: float = 0.0) -> float:
        """Retorna el valor de una clave como flotante (float)."""
        try:
            return float(self.get(key, str(fallback)))
        except (ValueError, TypeError):
            return fallback

    def get_path(self, key: str, fallback: str | None = None) -> Path | None:
        """Retorna el valor de una clave como objeto Path."""
        raw = self.get(key, fallback)
        if raw is None:
            return None
        return Path(raw).expanduser().resolve()

    def all(self) -> dict[str, str]:
        """Retorna todas las claves actualmente cargadas desde el .env."""
        return dict(dotenv_values(ENV_FILE))

    def is_first_run(self) -> bool:
        """Retorna True si es la primera vez que se ejecuta la aplicación."""
        return self.get_bool("FIRST_RUN", fallback=True)

    # ──────────────────────────────────────────────
    # Escritura
    # ──────────────────────────────────────────────

    def set(self, key: str, value: str) -> None:
        """
        Guarda una clave en el archivo .env y actualiza el entorno actual.
        """
        import time
        for attempt in range(4):
            try:
                set_key(str(ENV_FILE), key, str(value))
                break
            except (PermissionError, OSError):
                if attempt == 3:
                    self._logger.warning(f"No se pudo escribir en {ENV_FILE} tras varios intentos.")
                else:
                    time.sleep(0.05)
            except Exception as e:
                self._logger.warning(f"Error guardando clave {key} en .env: {e}")
                break

        os.environ[key] = str(value)
        log_val = mask_api_key(str(value)) if any(s in key.upper() for s in ("KEY", "SECRET", "TOKEN", "PASSWORD")) else str(value)
        self._logger.debug(f"Configuración guardada: {key}={log_val}")


    def mark_first_run_done(self) -> None:
        """Marca que la primera ejecución ya fue completada."""
        self.set("FIRST_RUN", "false")
        self._logger.info("Primera ejecución completada — FIRST_RUN=false")

    def is_plan_strict(self) -> bool:
        """Retorna True si el planificador debe abortar ante pasos imposibles."""
        return self.get("PLAN_STRICT", "false").lower() in ("true", "1", "yes")

    # ──────────────────────────────────────────────
    # Utilidades
    # ──────────────────────────────────────────────

    @property
    def root_dir(self) -> Path:
        """Directorio raíz del proyecto."""
        return ROOT_DIR

    @property
    def data_dir(self) -> Path:
        """Directorio de datos persistentes."""
        return ROOT_DIR / "data"

    @property
    def logs_dir(self) -> Path:
        """Directorio de logs."""
        return ROOT_DIR / "logs"

    @property
    def env_file(self) -> Path:
        """Ruta al archivo .env."""
        return ENV_FILE

    def __repr__(self) -> str:
        return f"<Settings env={ENV_FILE} first_run={self.is_first_run()}>"


# ──────────────────────────────────────────────
# Instancia global (singleton)
# ──────────────────────────────────────────────
settings = Settings()

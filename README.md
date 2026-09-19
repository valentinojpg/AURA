# AURA — Orion
> **Asistente Universal con Respuesta Automatizada**

[![Python Version](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://python.org)
[![UI Framework](https://img.shields.io/badge/UI-Flet_0.86-purple.svg)](https://flet.dev)
[![Architecture](https://img.shields.io/badge/Roadmap-30%2F30_Completado-success.svg)](PROMPT_BASE.md)
[![Privacy](https://img.shields.io/badge/Privacidad-Local_First_(Ollama)-orange.svg)](https://ollama.com)
[![Encoding](https://img.shields.io/badge/Encoding-UTF--8_Strict-brightgreen.svg)](#)

---

**AURA Orion** es un asistente de escritorio modular, inteligente y portable, diseñado para brindar asistencia personalizada a estudiantes, investigadores y desarrolladores con un enfoque prioritario en la privacidad, la autonomía local y la extensibilidad.

---

## ✨ Características Principales

- 🤖 **Arquitectura Multi-Proveedor:**
  - **Ollama:** Ejecución 100% local, privada y sin conexión a internet (modelos como `qwen2.5:3b`, `llama3.2:3b`, `phi3:mini`, `mistral`).
  - **Nube:** Soporte para Google Gemini, OpenAI (GPT-4o), Anthropic (Claude 3.5 Sonnet), xAI (Grok), Custom endpoints y Mock simulado para desarrollo.
- 🚀 **Onboarding Interactivo (Setup Wizard):**
  - Asistente de bienvenida en 5 pasos que guía al usuario en la selección de idioma, tema visual, proveedor de IA, verificación de Ollama en tiempo real, credenciales y políticas de confirmación de seguridad.
- 💬 **Chat Inteligente & Experiencia de Usuario:**
  - Streaming fluido de tokens, renderizado de Markdown enriquecido, sintaxis resaltada y bloques de código con botón de copia rápida.
  - Gestión integral de sesiones e historial persistente en JSON UTF-8.
- 🧠 **Memoria de Usuario & Contexto RAG:**
  - Perfil de usuario persistente (`UserMemoryManager`) con extracción automática de preferencias, directivas de sistema y soporte para recuperación semántica (RAG).
- 🛠️ **Sistema de Herramientas & Automatizaciones:**
  - Búsqueda web (DuckDuckGo, Wikipedia), scraping limpio de contenido, ejecución controlada de scripts, gestión de archivos locales y automatizaciones programables.
- 📋 **Planificador de Cadenas Multi-Step (Multi-Step Planning):**
  - Ejecución fluida de instrucciones compuestas chat/voz (*"abre firefox y entra a youtube music y pon 'Bad Romance' de Lady Gaga"* o *"abre notepad y escribe 'Hola a todos' y guarda en el escritorio como 'Amanecer'"*).
  - Extracción robusta de slots entre comillas (`§0`, `§1`...) previa a cortes por conjunciones (`y`, `luego`, `después`, `entonces`), resolución determinista y fallback estructurado a IA con `[MODULO_PLAN]`.
  - Generación de automatizaciones temporales al vuelo con checklist dinámico en vivo en chat (⚪, ⏳, ✅, ❌) y confirmación modal de seguridad ante operaciones destructivas.
- 🏢 **Registro de Capacidades por App & Adapter COM para Office (Fase 72):**
  - Registro de capacidades extensible (`data/app_capabilities.json`, `aura.core.app_capabilities`) con prevalidación previa de viabilidad para cada paso.
  - Integración nativa por COM con Microsoft Word y Excel (`aura.skills.office_adapter`) mediante conexión estricta a la ROT (`GetActiveObject`, sin instancias invisibles) y guardado nativo `.docx`/`.xlsx`.
  - Política de rigor configurable (`PLAN_STRICT=true|false`) para aborto temprano o salteo con advertencia `⚠️` en la checklist.
  - Comportamiento consciente para apps de mensajería (Discord no presiona Enter automáticamente y previene ejecuciones a medias) y de audio (Spotify sugiere `media_play`).
- 🎵 **Reproductor Multimedia Universal (`MediaPlaySkill`):**
  - Búsqueda y streaming directo en YouTube Music, Spotify y YouTube, abriendo en el navegador preferido (`BROWSER_PREFERIDO`).
- 🧩 **Ecosistema de Plugins & Event Bus:**
  - Carga dinámica de plugins en caliente desacoplados del núcleo mediante un bus de eventos unificado.
- 🎨 **Interfaz de Usuario Moderna con Flet:**
  - Temas oscuro y claro, barra lateral colapsable, vista de ajustes con filtros por pestaña, minimizado a bandeja del sistema (System Tray) y atajos de teclado configurables.
- 🛡️ **Portabilidad & Respaldo Integral:**
  - Scripts `.bat` portables (`setup_env.bat`, `Aura.bat`, `backup.bat`, `test.bat`) y acceso directo oficial `Aura.lnk` con ícono de la waifu.
  - Gestor de copias de seguridad (`scripts/backup_manager.py`) con empaquetado ZIP con marca de tiempo y prevención de ataques de ruta.
  - Enfoque estricto UTF-8 para prevenir problemas de codificación (mojibake) en sistemas Windows.

---

## 🖥️ Requisitos de hardware

Los requisitos dependen de si la IA corre local (Ollama) o en la nube (API keys).

| Componente | 🔻 Mínimo (IA local Qwen2.5:3B) | ✅ Recomendado | ☁️ Solo nube (Gemini/GPT/Claude/Grok) |
|---|---|---|---|
| **SO** | Windows 10/11 64-bit | Windows 11 64-bit | Windows 10/11 64-bit |
| **CPU** | 4 núcleos / 8 hilos (i5 8va gen / Ryzen 3 3000+) | 6-8 núcleos (i5/Ryzen 5 5000+) | 2 núcleos |
| **RAM** | 8 GB | 16 GB | 4-8 GB |
| **GPU** | No obligatoria (gráfica integrada) | NVIDIA con 4-6 GB VRAM (RTX 3050/3060/4060) | No obligatoria |
| **Disco** | 10 GB libres (SSD fuertemente recomendado) | 20 GB libres NVMe | 3-4 GB libres |
| **Audio** | Micrófono y salida básicos | Headset USB/Bluetooth decente para VAD | Idem |
| **Internet** | No (modo 100% local) | Opcional | **Obligatorio** |

> 💡 El proyecto apunta a **Windows**: las skills de sistema, el registro
> (App Paths), WDM-KS/WASAPI y el lock/shutdown son de Windows.
> En Linux/macOS la UI y el chat andarían, pero las skills de sistema no.

---

## ⚡ Inicio Rápido (Quickstart en Windows)

AURA está diseñado para ejecutarse en Windows sin necesidad de configuraciones complejas globales.

### 1. Configurar el entorno portable (sólo la primera vez)
Haz doble clic en:
```bat
setup_env.bat
```
*(Crea el entorno virtual en `./env` e instala las dependencias de `requirements.txt`).*

### 2. Iniciar AURA
Haz doble clic en el acceso directo oficial:
```cmd
Aura.lnk
```
*(O directamente en el lanzador portable `Aura.bat`). Si es la primera vez que se ejecuta, AURA abrirá automáticamente el Asistente de Configuración Inicial.*

> 💡 **¿Por qué el lanzador visible es `Aura.lnk` y no directamente `Aura.bat`?**
> En Windows, los archivos de comandos por lotes (`.bat`) son scripts de texto plano y el sistema operativo no permite incrustarles un recurso de ícono propio; Windows siempre les asigna el ícono genérico de consola/engranajes. El ícono personalizado solo puede residir en un **acceso directo (`.lnk`)** o en un ejecutable binario (`.exe`). Por ello, el lanzador visible para el usuario es `Aura.lnk`, el cual apunta a `Aura.bat`, establece la carpeta del proyecto como directorio de trabajo y luce la imagen de la waifu Aura (`assets/logo_waifu.ico`).

> 🔄 **Cómo regenerar el acceso directo en otra máquina o carpeta**:
> Si clonas o mueves el proyecto a otra PC, puedes recrear los accesos directos (en la raíz del proyecto y opcionalmente en el Escritorio) ejecutando en PowerShell:
> ```powershell
> powershell -ExecutionPolicy Bypass -File scripts\make_shortcut.ps1 -Desktop
> ```
> O desde Python:
> ```cmd
> .\env\Scripts\python.exe scripts\make_shortcut.py --desktop
> ```

> 🎨 **Branding y Roles de Assets (`assets/`)**:
> - `assets/logo.png`: Arte original y avatar in-app de la waifu Aura (para header, sidebar, topbar, wizard y chat bubbles).
> - `assets/logo_waifu.ico`: Ícono multipágina de Windows (16 a 256 px, remuestreo Lanczos, cabecera `00 00 01 00`) de la waifu Aura para el lanzador `Aura.lnk`.
> - `assets/logo2.png`: Arte fuente en alta resolución para el ícono de ventana y barra de tareas.
> - `assets/logo2.ico`: Ícono multipágina final de Windows (16 a 256 px, remuestreo Lanczos) asignado a la ventana y taskbar.
> - `assets/logo.ico.invalid`: Copia de respaldo del archivo .ico anterior con cabecera PNG.
>
> 💡 **Nota sobre la caché de íconos en Windows**:
> Windows almacena en caché los íconos de la barra de tareas y accesos directos. Si el Explorador de Windows tarda en reflejar el ícono de la waifu, se puede invalidar y refrescar la caché ejecutando en CMD o PowerShell:
> ```cmd
> ie4uinit.exe -show
> ```
> ```

---

## 🦙 Uso con Ollama (100% Local y Privado)

Recomendamos usar **Ollama** para contar con un asistente completamente privado y sin costos de API.

1. **Instalación de Ollama:**
   - Desde PowerShell o CMD:
     ```powershell
     winget install Ollama.Ollama
     ```
   - O descargando el instalador oficial desde [https://ollama.com/download](https://ollama.com/download).
2. **Descargar un modelo ligero recomendado:**
   ```bash
   ollama pull qwen2.5:3b
   ```
   *(Excelente rendimiento en español y consumo moderado de RAM / VRAM).*
3. **Modelos alternativos populares:**
   - `llama3.2:3b`: Rápido y versátil.
   - `phi3:mini`: Ultraligero para equipos modestos.
   - `qwen2.5:7b` o `llama3.1:8b`: Máxima capacidad de razonamiento.
4. En el asistente de AURA, selecciona **Ollama Local**; el sistema detectará el servicio automáticamente si está activo en `http://localhost:11434`.

---

## 💾 Respaldo y Restauración de Datos

AURA incluye un gestor portable de copias de seguridad para resguardar tus conversaciones, configuraciones y memoria.

### Crear un respaldo rápido
Haz doble clic en:
```bat
backup.bat
```
O desde la terminal:
```bash
python scripts/backup_manager.py create
```
El archivo se guardará automáticamente en `data/backups/backup_YYYYMMDD_HHMMSS.zip`.

### Listar respaldos existentes
```bash
python scripts/backup_manager.py list
```

### Restaurar un respaldo
```bash
# Simular restauración sin modificar archivos:
python scripts/backup_manager.py restore data/backups/backup_ejemplo.zip --dry-run

# Restaurar efectivamente:
python scripts/backup_manager.py restore data/backups/backup_ejemplo.zip
```

---

## 📦 Empaquetado y Releases Portables 

El proyecto AURA Orion en desarrollo activo pesa alrededor de **~2 GB**, principalmente debido al entorno virtual (`env/` con librerías de Deep Learning como PyTorch, cuDNN y Flet) y a las cachés locales (`__pycache__`, logs rotados y archivos de audio de síntesis).

Para distribuir AURA de forma limpia, ultra ligera (~60 a 70 MB) y 100% portable a otra máquina con Windows, se utiliza el script automatizado:
```cmd
.\env\Scripts\python.exe scripts\make_release.py
```

### 🚀 Cómo generar un release portable
Ejecutando el comando anterior (o `python scripts/make_release.py`), el sistema realiza automáticamente:
1. **Limpieza previa segura**: Elimina cachés recursivas `__pycache__`, archivos `.pyc`/`.pyo`, logs rotados viejos (`aura.log.1`, etc.), audios temporales de diagnóstico (`data/audio_cache/*.wav`, `data/audio_test/*.wav`) y directorios de compilación `build/`, `_internal/` o `dist/`. *(NUNCA toca código, assets, modelos RVC, data real, `.env` ni `requirements.txt`)*.
2. **Generación automática de `.env.example`**: Lee el archivo `.env` local y reemplaza todas las credenciales sensibles (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY`, `CUSTOM_API_KEY`, etc.) por placeholders (`'tu_<key>_aqui'`), preservando comentarios, secciones y variables no sensibles.
3. **Copia limpia a staging (`ORION_release/`)**: Excluye estrictamente `env/`, `.git/`, `logs/`, `__pycache__/`, `build/`, `_internal/`, `.env` real, audios temporales y backups. Incluye obligatoriamente: `models/rvc/` (modelos de voz neuronal `aura.pth` e índice `aura.index`), `assets/` (logos e ícono waifu), `data/` real (conversaciones, memoria, programas, automatizaciones), `scripts/`, `requirements.txt`, `.env.example`, `Aura.bat` y `setup_env.bat`.
4. **Verificación inviolable de seguridad**: Un check previo aborta y destruye el release si detecta que el archivo `.env` real (con claves privadas) se encuentra en la carpeta de staging o dentro del archivo ZIP.
5. **Compresión ZIP y manifiesto final**: Empaqueta el release en `AURA_release_<fecha>.zip` en el Escritorio de Windows (o en la ruta configurada con `--out`), genera un archivo `release_manifest.json` e imprime en consola el resumen de compresión, peso y exclusiones.

#### Opciones de línea de comandos:
- `--out <ruta>`: Especifica la ruta destino para el archivo `.zip` o la carpeta de salida.
- `--stage-dir <dir>`: Define el directorio intermedio para la copia limpia (por defecto: `ORION_release/`).
- `--skip-clean`: Omite la fase de limpieza previa de cachés del workspace.
- `--no-zip`: Solo prepara la carpeta de staging limpia sin comprimir a `.zip`.
- `--dry-run`: Simula todo el proceso sin modificar archivos ni generar el release.

### 🔄 Cómo reconstruir el entorno en una máquina limpia
Cuando el usuario recibe el archivo ZIP en una computadora nueva:
1. **Descomprimir el ZIP**: Extraer el contenido de `AURA_release_<fecha>.zip` en cualquier carpeta (ej: `C:\AURA`).
2. **Construir el entorno virtual**: Hacer doble clic en:
   ```bat
   setup_env.bat
   ```
   *El script verificará la presencia de Python 3.11, creará automáticamente el entorno virtual portable en `%~dp0env`, instalará todas las dependencias de `requirements.txt` y, si no existe `.env`, creará automáticamente una copia inicial limpia desde `.env.example`.*
3. **Configurar claves (opcional)**: Si el usuario desea utilizar proveedores de IA en la nube (OpenAI, Anthropic, Gemini, Groq), abrir `.env` y completar las API keys correspondientes.
4. **Iniciar AURA**:
   - Iniciar directamente con:
     ```cmd
     Aura.bat
     ```
   - O recrear el acceso directo oficial con el ícono de la waifu en el Escritorio ejecutando:
     ```cmd
     .\env\Scripts\python.exe scripts\make_shortcut.py --desktop
     ```

### ⚡ Nota sobre el peso de PyTorch (CUDA vs CPU)
El entorno virtual reconstruido en destino variará de tamaño según el hardware del usuario:
- **PyTorch con soporte CUDA (GPU NVIDIA)**: Permite acelerar por hardware la conversión de voz RVC (`rvc-python`). En este modo, `env/` pesará entre **2.5 GB y 4.0 GB** debido a los runtimes de CUDA, cuDNN y kernels compilados.
- **PyTorch para CPU (Modo Ligero)**: Para laptops o PCs sin GPU NVIDIA dedicada, se puede instalar PyTorch CPU (`pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu`), reduciendo el tamaño del entorno reconstruido a solo **~800 MB - 1 GB**.
- En ambos casos, el archivo de distribución ZIP descargado se mantiene en tan solo **~60-70 MB** gracias a que el entorno pesado no viaja en el release y se regenera localmente.

---

## 🧪 Pruebas Automatizadas

Para validar la integridad de todos los módulos del sistema:
```bat
test.bat
```
O especificar un archivo de prueba en particular:
```bash
python -m pytest tests/test_fase30_onboarding_polish.py -v
```

---

## ⚙️ Configuración (`.env`)

Las variables clave configurables se almacenan en `.env`:

| Variable | Descripción | Valor por defecto |
| :--- | :--- | :--- |
| `AI_PROVIDER` | Proveedor activo (`ollama`, `gemini`, `openai`, `anthropic`, `mock`) | `ollama` |
| `OLLAMA_MODEL` | Modelo local en Ollama | `qwen2.5:3b` |
| `OLLAMA_BASE_URL` | URL del servicio Ollama | `http://localhost:11434` |
| `GEMINI_API_KEY` | Clave API de Google Gemini (opcional) | - |
| `OPENAI_API_KEY` | Clave API de OpenAI (opcional) | - |
| `ANTHROPIC_API_KEY`| Clave API de Anthropic Claude (opcional) | - |
| `THEME` | Tema visual de la interfaz (`dark` / `light`) | `dark` |
| `LANGUAGE` | Idioma de la interfaz (`es` / `en`) | `es` |
| `FIRST_RUN` | Bandera de primer inicio para el asistente | `false` |
| `WORKSPACE_PATH` | Carpeta de trabajo para herramientas y archivos | `./workspace` |
| `CONFIRM_DESTRUCTIVE`| Confirmación obligatoria antes de acciones críticas | `true` |
| `PLAN_MAX_STEPS` | Cantidad máxima de pasos en una cadena multi-step | `8` |
| `PLAN_WAIT_APP_SECONDS`| Tiempo de espera (s) para foco de aplicación | `5` |
| `PLAN_WAIT_PAGE_SECONDS`| Tiempo de espera (s) entre navegación web | `2` |
| `PLAN_ON_ERROR` | Estrategia ante fallo de paso (`stop` / `continue`) | `stop` |
| `MEDIA_SERVICE` | Servicio de música por defecto (`youtube_music` / `spotify` / `youtube`) | `youtube_music` |

---

## 📂 Estructura del Proyecto

```
ORION/
├── aura/                    # Paquete raíz de compatibilidad y módulos centrales
│   ├── ai/                  # Adaptadores de IA (Ollama, Gemini, OpenAI, Claude, etc.)
│   ├── core/                # Configuración, eventos, memoria, logs, Ollama helper, planner (cadenas multi-step)
│   ├── data/                # Almacén de conversaciones y persistencia
│   ├── tools/               # Herramientas del sistema (web, scripts, archivos)
│   └── ui/                  # Componentes visuales Flet (chat, sidebar, settings, wizard)
├── automation/              # Motor de automatizaciones y ejecución de cadenas de pasos (AutomationEngine)
├── core/                    # Módulos centrales (re-export y accesos directos: planner, entity_resolver)
├── data/                    # Base de datos local (conversaciones, memoria, backups)
│   ├── backups/             # Archivos ZIP de copias de seguridad
│   ├── conversations/       # Historial de sesiones en JSON
│   └── memory/              # Datos de memoria y perfil de usuario
├── scripts/                 # Scripts de utilidad (make_release.py, backup_manager.py, make_shortcut.py)
├── skills/                  # Skills del sistema (web, files, programs, app_writer, app_saver, media_play)
├── tests/                   # Suite de pruebas unitarias e integración (Fases 1 a 71)
├── ui/                      # Vistas y componentes UI
│   ├── pages/               # Páginas de Chat, Ajustes, Automatizaciones, Código
│   └── wizard/              # Asistente de configuración inicial (SetupWizard)
├── .env.example             # Plantilla de variables de entorno
├── Aura.bat                 # Script portable de ejecución
├── Aura.lnk                 # Acceso directo oficial con ícono de la waifu
├── backup.bat               # Script portable de respaldo en un clic
├── setup_env.bat            # Script de inicialización de entorno virtual
├── test.bat                 # Script portable de ejecución de pruebas
├── requirements.txt         # Dependencias Python
└── PROMPT_BASE.md           # Hoja de ruta arquitectónica y registro del proyecto
```

---

## Reportes y sugerencias

Este proyecto se encuentra en continuo desarrollo, por lo que pueden aparecer bugs o errores. Si encuentras alguno, puedes reportarlo utilizando cualquiera de los medios de contacto que aparecen a continuación.

Estos medios también están disponibles para enviar sugerencias, ideas o propuestas para futuras actualizaciones y mejoras de la aplicación.

Email: valenciopintos@gmail.com
Discord: b_vayoneta

## 📄 Licencia y Créditos

Proyecto desarrollado como parte de la iniciativa **AURA Orion**.  
Diseñado bajo principios de código limpio, modularidad, extensibilidad y preservación estricta de la privacidad del usuario.
# Manual de Usuario y Guía Operativa
**AURA (Orion) — Asistente Inteligente de Escritorio y Apoyo a la Decisión**  
*Guía completa para el usuario final | Diseñado para estudiantes, investigadores y profesionales*

---

## 1. Bienvenida e Introducción

### 1.1 Resumen Ejecutivo
Bienvenido a **AURA** (nombre de proyecto: **Orion**), tu asistente inteligente de escritorio diseñado para acompañarte en tus tareas cotidianas de estudio, investigación, programación y productividad diaria.

AURA no es una simple ventana de chat: es un **copiloto de apoyo a la decisión y ejecución operativa** que interactúa con tu computadora de manera natural, respetando en todo momento tu privacidad y autonomía.

---

### 1.2 ¿Qué problema resuelve AURA en tu día a día?

En la actualidad, trabajar o estudiar frente a la computadora suele implicar una constante sobrecarga mental:
- **Dispersión de tareas**: Saltar continuamente entre navegadores, procesadores de texto, carpetas y reproductores de música interrumpe tu concentración.
- **Pérdida de tiempo en rutinas repetitivas**: Abrir todas las aplicaciones necesarias para comenzar a trabajar, buscar documentos guardados en rutas complejas o redactar notas rápidas consume tiempo valioso.
- **Incertidumbre en la toma de decisiones**: Al investigar o programar, a menudo se requiere una segunda opinión técnica, explicaciones claras paso a paso o una revisión de borradores.
- **Riesgos de privacidad en la nube**: Muchos asistentes comerciales transmiten tus conversaciones y archivos privados a servidores externos. AURA nace con una filosofía **100% enfocada en tu privacidad local**: tú decides si opera totalmente dentro de tu computadora sin conexión a internet o si deseas conectar servicios externos de apoyo.

---

### 1.3 ¿Cómo te ayuda en tus decisiones diarias?

| Área de Apoyo | ¿En qué te asiste AURA? | Ejemplo Práctico |
| :--- | :--- | :--- |
| **Planificación Secuencial** | Descompone una orden compleja en pasos claros y los ejecuta en orden, informándote del progreso. | *"Abre el bloc de notas, escribe 'Ideas para el proyecto' y guarda en el escritorio como 'resumen.txt'"* |
| **Rutinas y Automatizaciones** | Prepara tu entorno de trabajo completo con un solo clic o una sola frase. | Activar la rutina *"Modo Programar"* o *"Inicio del Día"*. |
| **Asistencia Técnica y Estudio** | Responde preguntas sobre conceptos difíciles, depura errores en tus trabajos y te guía en la redacción. | *"¿Por qué falla este cálculo en mi hoja de cálculo y cómo lo corrijo?"* |
| **Control Seguro del Equipo** | Protege tus datos antes de ejecutar acciones delicadas mediante avisos de confirmación. | Preguntar antes de vaciar la papelera o reiniciar el equipo. |
| **Gestión Multimedia** | Localiza y reproduce música o videos para tu sesión de trabajo sin que pierdas el foco. | *"Pon música relajante en YouTube Music"* |

---

## 2. Guía de Inicio Rápido

### 2.1 Cómo acceder al sistema

1. **Abrir la aplicación**:
   - Haz doble clic en el acceso directo oficial con el ícono de Aura: **`Aura.lnk`** (ubicado en la carpeta de la aplicación o en tu Escritorio).
   - *Alternativa*: También puedes iniciar haciendo doble clic en el archivo **`Aura.bat`**.
2. **Asistente de Bienvenida Inicial (Setup Wizard)**:
   - La primera vez que abras AURA, aparecerá un asistente guiado de 5 pasos para dejar todo a tu gusto:
     - **Paso 1 (Idioma)**: Selecciona tu idioma preferido (español o inglés).
     - **Paso 2 (Tema visual)**: Elige entre modo oscuro o claro y tu paleta de colores favorita.
     - **Paso 3 (Inteligencia)**: Selecciona si deseas operar en modo **Local y Privado** (recomendado mediante el servicio Ollama en tu PC) o conectar una cuenta de servicio en línea.
     - **Paso 4 (Comprobación)**: El sistema verificará de inmediato si el motor de inteligencia está listo para responderte.
     - **Paso 5 (Seguridad)**: Configura si deseas que AURA siempre te pida confirmación antes de borrar archivos o apagar la máquina.
3. Una vez finalizado el asistente, se abrirá la **Ventana Principal**.

---

### 2.2 Anatomía de la Interfaz

La pantalla principal se divide en cuatro zonas intuitivas:

```
┌────────────────────────────────────────────────────────────────────────┐
│ [TOPBAR] Nombre de la vista actual  |  Estado de conexión  |  Versión  │
├──────────────┬─────────────────────────────────────────────────────────┤
│ [BARRA       │ [ÁREA CENTRAL DE TRABAJO]                               │
│  LATERAL]    │                                                         │
│              │ • Conversación interactiva con AURA                     │
│ • Chat       │ • Respuestas en texto claro y bloques visuales          │
│ • Habilidades│ • Lista interactiva de pasos en tiempo real             │
│ • Rutinas    │                                                         │
│ • Archivos   │                                                         │
│ • Código     │                                                         │
│ • Ajustes    ├─────────────────────────────────────────────────────────┤
│              │ [BARRA DE ENTRADA] [ 🎙️ Voz ] [ Escribe un mensaje... ] [ 🚀 ] │
└──────────────┴─────────────────────────────────────────────────────────┘
```

- **Barra Lateral Izquierda**:
  - 💬 **Chat**: Tu centro de mando principal para conversar, pedir acciones y seguir ejecuciones.
  - 🧩 **Habilidades (Skills)**: Muestra el catálogo de todo lo que AURA sabe hacer en tu computadora.
  - ⚡ **Automatizaciones**: Panel para activar y diseñar rutinas de un solo clic.
  - 📁 **Archivos**: Explorador inteligente para gestionar tus carpetas de trabajo y proyectos.
  - 💻 **Asistente de Programación**: Espacio dedicado a la consulta de código, revisión de errores y proyectos de desarrollo.
  - ⚙️ **Configuración**: Panel para personalizar audio, micrófono, aspecto visual, personalidad y seguridad.
- **Área Central**: Muestra el historial de mensajes, las respuestas formateadas y los paneles de ejecución paso a paso.
- **Barra Inferior de Entrada**: Contiene el botón del micrófono, el cuadro de texto y el botón de enviar.

---

### 2.3 Cómo interactuar con el sistema

#### A. Interacción por Texto (Chatbot)
Escribe tu consulta o pedido con tus propias palabras en el cuadro de texto inferior y presiona la tecla **Enter** (o haz clic en el botón de la flecha/avión).
- AURA responde progresivamente en pantalla, mostrando textos ordenados, tablas explicativas y bloques de texto destacados.
- Si una respuesta incluye código o instrucciones, dispones de un **botón de copia rápida** en la esquina del bloque.

#### B. Interacción por Voz (Micrófono Inteligente)
AURA cuenta con un sistema de detección automática de voz:
1. Haz clic en el botón del **micrófono (🎙️)** en la barra inferior.
2. Comienza a hablar con naturalidad (por ejemplo: *"Abre la calculadora"* o *"Pon música de fondo"*).
3. **No necesitas tocar nada para terminar**: el sistema detecta de forma inteligente cuando terminas de hablar gracias a tu silencio natural y enviará tu orden automáticamente.
4. Si cambias de idea mientras hablas o hay ruido accidental, puedes cancelar la grabación con el botón de detener.

#### C. Gestión y Carga de Archivos
- Puedes pedirle a AURA que localice o abra archivos de tu computadora diciendo su nombre: *"Busca el documento de historia"* o *"Abre el archivo presupuesto.xlsx"*.
- En la sección **Archivos** de la barra lateral, puedes añadir carpetas frecuentes para que AURA siempre sepa dónde buscar tus apuntes o proyectos de trabajo sin tener que escribir rutas largas.

---

### 2.4 Qué información ingresar y en qué formato (Buenas pautas de comunicación)

AURA entiende lenguaje coloquial, pero seguir estas tres reglas sencillas garantiza la máxima precisión:

1. **Usa comillas para nombres específicos**:
   - Cuando quieras que AURA escriba un texto exacto o guarde un archivo con un nombre particular, enciérralo entre comillas dobles (`"..."`) o simples (`'...'`).
   - *Ejemplo óptimo*: `Abre el bloc de notas y escribe "Lista de compras para mañana"`
   - *Ejemplo óptimo*: `Guarda este documento como "resumen_semanal.txt" en el escritorio`
2. **Encadena acciones con conjunciones comunes**:
   - Puedes solicitar varias tareas en una sola oración usando palabras de unión como **"y"**, **"luego"**, **"después"**, **"entonces"**.
   - *Ejemplo compuesto*: `Abre Firefox, entra a YouTube y pon "música clásica para estudiar"`
3. **Para preguntas técnicas o explicaciones**:
   - No necesitas resumir de más: puedes pegar fragmentos de texto, errores de pantalla o párrafos completos y consultar: *"¿Qué significa este error y cómo lo resuelvo?"*

---

## 3. Interpretación de Resultados y Salidas

### 3.1 Lista Interactiva de Pasos (Planes Multi-Acción)

Cuando le pides a AURA una tarea compuesta por varias acciones, el asistente no actúa a ciegas; primero arma una **lista ordenada de pasos** y la muestra en pantalla con indicadores dinámicos en vivo:

| Símbolo | Estado Funcional | Significado para el Usuario |
| :---: | :--- | :--- |
| ⚪ | **Pendiente** | La acción está registrada en la lista de espera, lista para ejecutarse cuando llegue su turno. |
| ⏳ | **En Progreso** | El sistema está trabajando activamente en esta acción (por ejemplo, esperando que se abra la ventana o que cargue el sitio web). |
| ✅ | **Completado con Éxito** | La acción finalizó satisfactoriamente y el sistema verificó el resultado. |
| ⚠️ | **Advertencia u Omitido** | La acción requirió una aclaración, se corrigió un error menor de escritura o la aplicación no admitía esa función específica y se continuó de forma segura. |
| ❌ | **Interrumpido o con Error** | La acción no pudo completarse (por ejemplo, el programa no está instalado en tu equipo o se canceló el proceso). El sistema se detiene para evitar inconsistencias. |

---

### 3.2 Códigos de Color y Mensajes de Estado del Sistema

En la barra de estado y en las burbujas de respuesta, AURA utiliza un lenguaje visual coherente:

- 🟢 **Verde (Éxito / Confirmación)**:
  - Indica que una orden se completó sin dificultades (ejemplo: *“Guardado en Escritorio con éxito (48 caracteres)”*).
- 🔵 **Azul o Cian (Orientación / Información)**:
  - Respuestas explicativas, resúmenes didácticos o cuando AURA te aclara qué entendió (ejemplo: *“Entendí: cerrar Bloc de Notas”*).
- 🟡 **Amarillo o Naranja (Atención Requerida)**:
  - Avisos donde el asistente necesita tu confirmación o te informa que una acción no es reversible.
- 🔴 **Rojo (Aviso de Problema / Bloqueo)**:
  - Alerta de que algo impidió completar la solicitud (ejemplo: falta de conexión al motor de inteligencia o un archivo no encontrado). Siempre se acompaña de una sugerencia clara de solución.

---

### 3.3 Niveles de Personalidad y Tono de Respuesta

En **Configuración > Personalidad**, puedes ajustar cómo se comunica AURA contigo. Esto cambia el estilo de las conversaciones sin alterar nunca la seguridad:

- **Nivel 0 — Profesional**: Respuestas formales, técnicas, breves y estrictamente objetivas. Ideal para entornos laborales o estudio riguroso.
- **Nivel 1 — Amigable**: Trato cálido, cercano, paciente y alentador.
- **Nivel 2 — Sarcástico**: Respuestas con ironía inteligente y humor ácido sutil.
- **Nivel 3 — Descarado Suave**: Tono coloquial, quejoso en broma y espontáneo.
- **Nivel 4 — Irreverente (Estilo Grok)**: Respuestas directas, picantes, sin rodeos y con humor rebelde.
- **Nivel 5 — Desinhibido / Sin Filtro**: Estilo cómico sin censura ni diplomacia (para quienes buscan un trato descontracturado y divertido).

> [!NOTE]
> Independientemente del nivel de personalidad que elijas, **las reglas de seguridad y respeto a tus datos son inviolables**. La personalidad solo cambia la forma de hablar, nunca las decisiones del sistema.

---

## 4. Buenas Prácticas y Consideraciones Éticas

### 4.1 Qué SÍ hacer con los resultados de AURA
- ✅ **Revisar borradores antes de enviarlos**: Si utilizas a AURA para redactar correos, textos de estudio o código, revisa siempre la versión final. Eres el responsable humano final de tus entregas.
- ✅ **Mantener activadas las confirmaciones de seguridad**: Conserva la opción *“Confirmar acciones destructivas”* activada en Configuración para evitar borrados accidentales.
- ✅ **Aprovechar el aprendizaje de errores de escritura**: Si sueles escribir rápido y cometes pequeñas erratas (por ejemplo, *"notepa d"* en vez de *"notepad"*), AURA aprenderá tu costumbre y no tendrás que preocuparte por escribir perfecto.
- ✅ **Crear respaldos periódicos**: Aprovecha la herramienta de respaldo rápido de la aplicación para resguardar tus conversaciones y notas de memoria.

---

### 4.2 Qué NO hacer con el sistema
- ❌ **No ingresar contraseñas bancarias ni claves de acceso personales en el chat**: Aunque AURA guarda todo en tu equipo, como buena práctica de seguridad digital nunca debes escribir credenciales de cuentas en ninguna ventana de conversación.
- ❌ **No delegar decisiones críticas de forma ciega**: Las respuestas generadas por inteligencia artificial son una guía de apoyo y orientación; no reemplazan el juicio crítico profesional en medicina, finanzas o leyes.
- ❌ **No forzar ejecuciones en documentos con cambios sin guardar**: Si tienes un documento abierto con información crítica, asegúrate de guardarlo antes de pedirle al asistente que cierre aplicaciones.

---

### 4.3 Privacidad de Datos y Manejo Seguro de tu Información

AURA fue construido bajo un **Marco de Responsabilidad y Privacidad Estricta**:

1. **Tus datos se quedan en tu casa**: En el modo local (con Ollama), tus conversaciones, grabaciones de voz, proyectos y preferencias no se suben a ningún servidor de internet. Todo reside en la carpeta `data/` dentro de la carpeta del programa en tu propio disco duro.
2. **Voz privada**: Cuando hablas por el micrófono, el reconocimiento de tu voz se ejecuta en el procesador o tarjeta gráfica de tu propia computadora.
3. **Cero almacenamiento de claves visibles**: Si configuras servicios opcionales en la nube, tus claves de conexión se mantienen ocultas (mostrando únicamente `sk-...1234`) y no quedan expuestas en registros de texto.
4. **Protección de la papelera**: Cuando le pides a AURA borrar un archivo, la aplicación utiliza por defecto la Papelera de Reciclaje de Windows, permitiéndote recuperar cualquier archivo en caso de arrepentimiento.

---

## 5. Preguntas Frecuentes (FAQ) y Solución de Problemas

### ❓ ¿Por qué AURA me dice que "Ollama no responde"?
- **Causa**: Si elegiste el modo local, el servicio Ollama no está en ejecución en segundo plano.
- **Solución**:
  1. Abre el menú Inicio de Windows y abre la aplicación **Ollama** (o abre una ventana de comandos y escribe `ollama serve`).
  2. Vuelve a AURA y escribe tu mensaje; la conexión se restablecerá de inmediato.

---

### ❓ ¿AURA funciona si no tengo conexión a Internet?
- **Respuesta**: **Sí, totalmente.** Si utilizas el motor local (Ollama) y el sintetizador de voz integrado, AURA puede redactar, conversar, abrir programas, buscar documentos locales y organizar tus tareas sin necesidad de tener Wi-Fi o datos móviles.

---

### ❓ El micrófono no me escucha o se corta muy rápido antes de que termine de hablar
- **Causa**: El volumen de entrada de tu micrófono es bajo o el tiempo de espera por silencio es demasiado corto.
- **Solución**:
  1. Ve a **Configuración > Audio y Voz**.
  2. En *Dispositivo de entrada*, asegúrate de tener seleccionado tu micrófono principal.
  3. Aumenta ligeramente el valor de *Tiempo de silencio para envío* (por ejemplo, a `2.0` o `2.5` segundos) para que te dé más tiempo para hacer pausas al hablar.

---

### ❓ ¿Cómo creo una copia de seguridad de mis conversaciones y notas?
- **Solución rápida en un clic**:
  - En la carpeta de AURA, haz doble clic en el archivo **`backup.bat`**.
  - El sistema creará automáticamente un archivo comprimido `.zip` con la fecha y hora dentro de la carpeta `data/backups/`.
  - Puedes guardar ese archivo en un pendrive o en tu servicio de respaldo habitual para no perder nunca tus datos.

---

### ❓ Le pedí abrir un programa y me respondió que no lo encontró
- **Causa**: El programa está instalado en una ruta no convencional o tiene un nombre diferente al que pronunciaste.
- **Solución**:
  - Puedes enseñarle la aplicación: ve a **Configuración > Programas**, añade el programa con el nombre que te guste (ejemplo: *"mi editor"*) e indícale dónde está su archivo de inicio. A partir de ese momento, bastará con decir *"abre mi editor"*.

---

### ❓ ¿Cómo restauro la aplicación si muevo la carpeta a otra computadora?
- **Solución**:
  1. Copia tu carpeta de AURA a la nueva computadora con Windows.
  2. Haz doble clic en **`setup_env.bat`** para que prepare el entorno en la nueva máquina automáticamente.
  3. Haz doble clic en **`Aura.lnk`** y continúa trabajando exactamente donde lo dejaste, con toda tu memoria y preferencias intactas.

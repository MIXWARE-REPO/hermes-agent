# Estrategia operativa — Voice Orchestrator

## Objetivo
Construir un flujo de voz productivo, determinista y de baja fricción que convierta la conversación en salida oral natural sin reanalizar toda la lógica en cada turno.

La estrategia se apoya en dos verticales:
1. Arquitectura disponible: OpenVoice autoalojado + máquina local GPU/CPU/RAM.
2. Eficiencia operativa: mínimo uso de tokens, procedimientos limpios, y ejecución estricta por script interno.

---

## Vertical 1 — Qué podemos hacer con la arquitectura actual

### 1. Base técnica ya utilizable
- OpenVoice autoalojado como motor principal.
- Caché local persistente para audio y recursos.
- FFmpeg / imageio-ffmpeg para conversión y compatibilidad Telegram.
- Python interno como fuente de verdad para el pipeline.

### 2. División de trabajo por capas
El sistema debe operar siempre con la misma secuencia:

1. Clasificar la entrada.
2. Detectar si es texto o audio.
3. Determinar el modo conversacional.
4. Sanitizar contenido técnico.
5. Construir speech_text.
6. Construir guion oral.
7. Aplicar prosodia.
8. Renderizar audio con OpenVoice.
9. Validar salida.
10. Entregar el resultado.

### 3. Separación estricta de responsabilidades
- El LLM no debe decidir todo cada vez.
- El script interno debe conocer el protocolo.
- La capa de voz solo debe materializar el guion final.
- La capa de conversación debe producir contenido útil, no ruido.

### 4. Identidad prosódica
- Voz 9 como referencia base.
- Tono: estratégico, estable, claro, con criterio.
- Naturalidad funcional, no teatral.
- Pausas vivas, respiración mínima, fillers controlados.

### 5. Sanitización obligatoria
Antes de cualquier TTS:
- transformar URLs en conceptos orales
- resumir endpoints
- abstraer JSON/logs/código
- eliminar ruido técnico no relevante

Ejemplo:
- display: `POST /api/auth/login devuelve 401`
- speech: `El login está fallando por autenticación`

---

## Vertical 2 — Cómo hacerlo lo más eficiente posible

### 1. Regla central: no pensar desde cero cada vez
El sistema debe comportarse como un procedimiento cerrado y estable.
Eso significa:
- reglas fijas,
- rutas predecibles,
- contratos estables,
- y decisiones repetibles.

El LLM se usa solo donde agrega valor real:
- interpretación,
- contraargumento,
- reencuadre,
- síntesis,
- y ajuste contextual.

### 2. Minimizar tokens
Para reducir tokens:
- mantener prompts cortos y estructurados,
- usar plantillas por modo,
- guardar estado acumulado fuera del prompt,
- recuperar solo contexto relevante,
- comprimir historial a tesis, riesgos y decisiones.

### 3. Procedimiento estricto interno
El pipeline debe ser un script interno que siempre ejecute el mismo orden:

- leer contexto
- decidir carril
- sanitizar texto
- generar speech plan
- aplicar prosodia
- renderizar
- validar
- entregar

No debe improvisar arquitectura en tiempo de ejecución.

### 4. Uso eficiente de hardware
#### GPU
Usar GPU solo para lo que realmente lo necesita:
- inferencia de TTS si aporta aceleración real,
- procesamiento pesado de audio,
- operaciones que benefician de paralelismo.

#### CPU
Reservar CPU para:
- clasificación,
- sanitización,
- orquestación,
- lógica procedural,
- validación,
- colas y control.

#### RAM
Mantener en memoria:
- caché caliente de recursos frecuentes,
- modelos cargados si conviene,
- estado conversacional reciente,
- plantillas de guion y prosodia.

### 5. Reducir latencia percibida
La latencia no se combate solo acelerando modelos.
También se reduce con:
- respuestas estructuradas,
- pausas naturales,
- fallback limpio,
- pipeline sin pasos redundantes,
- y generación anticipada de guion.

### 6. Protocolo determinista
El orquestador debe comportarse como máquina de estados:
- si la entrada es texto → texto
- si la entrada es audio → audio
- si el modo es análisis → no ejecutar
- si el modo es ejecución → pasar por validación y skill

### 7. Validación final
Antes de entregar audio:
- comprobar que el contenido no incluye ruido técnico no deseado
- comprobar que el canal correcto fue elegido
- comprobar que la prosodia corresponde al modo
- comprobar que el archivo existe y es reproducible

---

## Arquitectura recomendada del flujo

### Pipeline canónico
1. Input classifier
2. Context retriever
3. Mode detector
4. Semantic sanitizer
5. Speech planner
6. Prosody planner
7. OpenVoice renderer
8. Audio validator
9. Delivery adapter

### Qué hace cada capa
- Input classifier: identifica texto/audio/documento.
- Context retriever: trae solo contexto útil.
- Mode detector: define fast, strategic, reflective, executive, debug, etc.
- Semantic sanitizer: convierte ruido técnico en lenguaje oral.
- Speech planner: decide qué decir y cómo estructurarlo.
- Prosody planner: decide pausas, velocidad, fillers y respiración.
- OpenVoice renderer: materializa el audio.
- Audio validator: comprueba calidad y compatibilidad.
- Delivery adapter: entrega en Telegram u otro canal.

---

## Reglas de diseño

- No leer literales técnicos salvo necesidad real.
- No reanalizar la misma estructura en cada turno.
- No delegar la identidad de voz al TTS solamente.
- No mezclar conversación y ejecución.
- No improvisar si ya existe un contrato estable.
- No usar fillers ni respiraciones si no aportan continuidad real.

---

## Resultado esperado

Un Voice Orchestrator que:
- sea determinista,
- use pocos tokens,
- opere con procedimientos fijos,
- humanice la voz por diseño y no por azar,
- y entregue una experiencia oral coherente, estable y profesional.

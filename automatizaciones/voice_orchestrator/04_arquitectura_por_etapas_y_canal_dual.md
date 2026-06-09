# Arquitectura por etapas y canal dual — Voice Orchestrator

## Objetivo
Construir el sistema de voz como una secuencia de etapas estancas, validables y reversibles, para poder añadir capacidades de forma incremental sin romper el comportamiento ya aprobado.

Cada etapa se prueba sola, luego se prueba acumulada con las anteriores, y solo después se habilita para uso real.

---

## Principio general

La arquitectura no debe crecer como un bloque único.
Debe crecer como una cadena de módulos independientes con contratos claros.

Cada módulo debe poder:
- activarse
- validarse
- desactivarse
- revertirse
- y observarse

---

## Modelo de trabajo

### Etapa n
Cada etapa contiene:
- objetivo funcional
- entradas permitidas
- salidas esperadas
- criterio de aprobación
- criterio de fallo
- rollback

### Validación acumulativa
Cuando una etapa nueva se aprueba:
- se conserva la anterior
- se suma la nueva
- se prueba la combinación completa

Ejemplo:
- Etapa 1 OK
- Etapa 2 se agrega
- Se prueba 1 + 2
- Si falla, se revisa 2 o la interfaz 1↔2

---

## Etapas recomendadas

### Etapa 1 — Clasificación y canal
Objetivo:
- detectar texto vs audio
- decidir si se activa voz o no

Validación:
- texto → texto
- audio → puede activar voz

Rollback:
- desactivar la activación de voz para entradas no audio

---

### Etapa 2 — Recuperación de contexto
Objetivo:
- traer solo la memoria relevante
- evitar reintroducir ruido innecesario

Validación:
- contexto útil
- sin repetición excesiva
- sin pérdida de tesis activa

Rollback:
- reducir contexto al mínimo estable

---

### Etapa 3 — Detección de modo
Objetivo:
- seleccionar fast, strategic, reflective, executive, debug, etc.

Validación:
- modo coherente con intención y densidad temática

Rollback:
- usar modo por defecto seguro

---

### Etapa 4 — Sanitización semántica
Objetivo:
- convertir ruido técnico en lenguaje oral útil

Validación:
- URLs, endpoints, logs, JSON, código y rutas no se leen literal si no corresponde

Rollback:
- forzar resumen oral

---

### Etapa 5 — Planificador de respuesta
Objetivo:
- construir la respuesta en estructura
- definir display_text y speech_text

Validación:
- respuesta clara
- con tesis, soporte y contrapunto si aplica

Rollback:
- simplificar a estructura mínima

---

### Etapa 6 — Canal reactivo frontal
Objetivo:
- emitir micro-reacciones humanas breves mientras se procesa el fondo

Validación:
- reacción corta
- natural
- no repetitiva
- no vacía

Rollback:
- desactivar reacción si empieza a sonar artificial o redundante

---

### Etapa 7 — Canal analítico profundo
Objetivo:
- procesar la respuesta completa
- razonar con profundidad
- construir el contenido final

Validación:
- calidad intelectual
- continuidad
- contrapunto útil
- claridad

Rollback:
- volver a modo analítico básico

---

### Etapa 8 — Prosodia
Objetivo:
- aplicar ritmo, pausas, respiración, fillers y cadencia

Validación:
- voz natural
- estable
- sin teatralización
- sin silencio muerto

Rollback:
- usar prosodia estándar segura

---

### Etapa 9 — Render TTS
Objetivo:
- materializar el guion oral con OpenVoice autoalojado

Validación:
- archivo generado
- formato correcto
- reproducible
- compatible con el canal

Rollback:
- degradar a texto si el audio falla

---

### Etapa 10 — Entrega y auditoría
Objetivo:
- enviar el resultado final
- registrar qué se ejecutó

Validación:
- salida entregada
- trazabilidad mínima disponible

Rollback:
- reintentar entrega o entregar texto limpio

---

## Doble canal

La conversación debe correr con dos planos simultáneos:

### 1. Canal frontal reactivo
Función:
- mantener conexión viva
- mostrar escucha
- confirmar entendimiento
- sostener presencia mientras se procesa

Características:
- breve
- natural
- de baja carga cognitiva
- casi instantáneo

Ejemplos:
- "Entiendo."
- "Ajá."
- "Sí, claro."
- "Ufff, eso es bastante."
- "Comprendo, déjame analizarlo."

---

### 2. Canal analítico
Función:
- procesar en profundidad
- estructurar respuesta
- evaluar contexto
- construir salida final

Características:
- más lento
- más profundo
- más preciso
- con posibilidad de contrapunto

---

## Coordinación entre canales

El canal frontal no debe competir con el analítico.
Debe acompañarlo.

Reglas:
- la reacción breve no debe comprometer la respuesta final
- la reacción debe ser compatible con el análisis posterior
- si el análisis cambia de rumbo, la reacción no debe prometer una conclusión falsa

---

## Reglas de seguridad operativa

- No activar voz por defecto en texto.
- No leer ruido técnico literal si no aporta valor oral.
- No permitir que una etapa nueva rompa las anteriores.
- No mezclar ejecución con conversación.
- No improvisar cuando el contrato ya existe.

---

## Beneficios del diseño por etapas

- detección rápida de fallos
- rollback simple
- menor riesgo de regresión
- validación incremental
- mejor mantenimiento
- mejor claridad del pipeline
- menos tokens desperdiciados
- más estabilidad en voz y conversación

---

## Resultado esperado

Un sistema de voz que crece como producto serio:
- módulo por módulo
- etapa por etapa
- con validación acumulativa
- con canal dual
- y con control explícito sobre cuándo habla, cómo habla y por qué habla.

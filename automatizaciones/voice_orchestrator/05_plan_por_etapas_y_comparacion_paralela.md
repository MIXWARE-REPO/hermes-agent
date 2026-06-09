# Plan por etapas y comparación paralela — Voice Orchestrator

## Objetivo
Implementar la voz como una sucesión de etapas independientes, validadas y acumulativas, con la posibilidad de comparar cada avance contra la versión previa.

La idea no es reconstruir todo en cada iteración, sino sumar una capa nueva, verificarla y dejarla estable antes de continuar.

---

## Estructura de trabajo

### Etapa 1
- Gate de canal
- Clasificación de entrada
- Separación texto / audio
- Activación de voz solo cuando corresponde

### Etapa 2
- Recuperación contextual mínima
- Memoria relevante
- Tesis activa

### Etapa 3
- Detección de modo conversacional
- Ajuste de profundidad y tono

### Etapa 4
- Sanitización semántica
- Conversión de ruido técnico a oralidad útil

### Etapa 5
- Planificador de guion oral
- Estructura de respuesta
- display_text vs speech_text

### Etapa 6
- Canal reactivo frontal
- Micro-confirmaciones humanas
- Presencia viva mientras el análisis continúa

### Etapa 7
- Canal analítico profundo
- Contrapunto
- Síntesis

### Etapa 8
- Prosodia
- Pausas
- Respiración
- Cadencia

### Etapa 9
- Render TTS
- OpenVoice autoalojado

### Etapa 10
- Validación y entrega
- Auditoría mínima
- Fallback limpio

---

## Regla de comparación

Cada nueva etapa debe compararse contra el comportamiento anterior.

Comparar:
- texto visible
- texto hablado
- eventos de voz
- naturalidad
- limpieza técnica
- continuidad
- coste de tokens
- riesgo de regresión

---

## Estrategia de implementación

### Fase A — Aislar
Cada etapa se implementa y verifica sola.

### Fase B — Acumular
Se suma la nueva etapa a las anteriores aprobadas.

### Fase C — Comparar
Se ejecuta la misma entrada contra:
- versión base
- versión base + nueva etapa

### Fase D — Aprobar o rollback
Si la nueva capa mejora sin romper estabilidad, se conserva.
Si rompe algo, se revierte solo esa capa.

---

## Canal dual

La conversación se divide en dos planos simultáneos:

1. Canal frontal
- reacción breve
- confirma escucha
- mantiene presencia

2. Canal analítico
- procesa en profundidad
- razona
- produce la respuesta final

Ambos deben convivir sin contradecirse.

---

## Resultado esperado

Un sistema que:
- crece por módulos
- compara cambios de forma clara
- reduce riesgo
- facilita rollback
- y permite humanizar la voz sin perder control técnico.

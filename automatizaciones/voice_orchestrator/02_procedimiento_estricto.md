# Procedimiento estricto — Voice Orchestrator

## Propósito
Definir un procedimiento interno único para que el sistema no tenga que decidir desde cero cada vez.

La lógica debe ser siempre la misma: detectar, filtrar, planificar, sintetizar, renderizar, validar y entregar.

---

## Entrada permitida
- Texto
- Audio
- Documento
- Evento estructurado

## Regla de canal
- Si la entrada es texto, la salida por defecto es texto.
- Si la entrada es audio, la salida puede ser audio.
- Solo el modo audio activa el carril de voz.

---

## Secuencia operativa fija

### 1. Clasificación
Identificar:
- tipo de entrada
- intención
- modo conversacional
- necesidad de voz
- riesgo operativo

### 2. Recuperación de contexto
Traer solo:
- tesis activa
- memoria relevante
- modo actual
- preferencias estables
- restricciones de canal

### 3. Sanitización semántica
Transformar todo lo técnico que no deba leerse literalmente:
- URLs
- endpoints
- logs
- JSON
- rutas
- código
- hashes
- UUIDs

### 4. Speech planning
Construir el contenido oral con:
- una idea por bloque
- introducción
- desarrollo
- contrapunto
- síntesis parcial

### 5. Prosody planning
Asignar:
- tono
- ritmo
- pausas
- respiración
- fillers mínimos
- continuidad acústica

### 6. Rendering
Enviar el guion ya resuelto al motor TTS autoalojado.

### 7. Validation
Comprobar:
- que el archivo existe
- que el formato es correcto
- que no hay ruido técnico mal leído
- que la salida corresponde al canal

### 8. Delivery
Entregar al canal destino sin reinterpretar otra vez el contenido.

---

## Reglas invariables

### Regla 1 — Canal correcto
No producir voz si el input es texto, salvo petición explícita.

### Regla 2 — No lectura literal
No leer rutas, endpoints ni bloques técnicos completos si eso rompe la comprensión oral.

### Regla 3 — No re-pensar
El sistema no debe resolver arquitectura de voz en cada turno.
Debe aplicar el contrato ya definido.

### Regla 4 — Prosodia estable
La voz 9 es la referencia base.

### Regla 5 — Procedimiento auditable
Cada ejecución debe dejar trazabilidad mínima:
- entrada
- modo
- salida
- validación
- entrega

---

## Reglas de eficiencia

- Reducir prompts largos.
- Reducir reescrituras internas.
- Mantener plantillas por modo.
- Evitar duplicar lógica en varios componentes.
- Cachear lo que no cambia.
- Mantener el procesamiento local siempre que sea posible.

---

## Fallbacks

Si algo falla:
1. degradar a texto limpio
2. no bloquear la conversación
3. no leer ruido técnico
4. registrar el error
5. conservar continuidad

---

## Resultado esperado

Un procedimiento repetible, corto y estable que funcione como máquina interna:
- sin improvisación
- sin excesos de tokens
- sin lectura técnica innecesaria
- y con identidad oral consistente.

# Roadmap de implementación — Voice Orchestrator

## Fase 1 — Base estable
- Confirmar OpenVoice autoalojado.
- Mantener checkpoints y cachés locales.
- Validar conversión y entrega de audio.
- Definir voz 9 como referencia base.

## Fase 2 — Orquestación mínima
- Clasificar entrada: texto vs audio.
- Activar audio solo cuando la entrada sea audio.
- Mantener fallback limpio a texto.
- Evitar duplicación de salida.

## Fase 3 — Sanitización oral
- Reescribir URLs, endpoints y código a lenguaje oral.
- Separar display_text y speech_text.
- Prohibir lectura literal de ruido técnico.

## Fase 4 — Prosodia controlada
- Aplicar pausas vivas.
- Ajustar ritmo por modo.
- Usar fillers mínimos y contextuales.
- Mantener respiración sintética casi imperceptible.

## Fase 5 — Procedimiento estricto
- Ejecutar siempre la misma secuencia.
- Reducir tokens y decisiones repetidas.
- Mantener el flujo como script interno.
- Validar salida antes de entregar.

## Fase 6 — Optimización
- Cachear contexto estable.
- Reducir pasos redundantes.
- Mover lógica pesada al nivel local.
- Dejar al LLM solo el trabajo cognitivo útil.

## Métrica de éxito
- Texto sigue siendo texto.
- Audio solo cuando toca.
- La voz suena natural sin leer ruido técnico.
- El pipeline es repetible, auditable y barato en tokens.

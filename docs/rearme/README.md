# Rearme del modelo principal — Documento 2

Este directorio contiene la base ejecutable derivada del análisis del procedimiento real de rearme.

## Objetivo

Convertir la propuesta ejecutiva en un flujo implementable y verificable.

## Estado actual

Fase 1 implementada:
- diagnóstico del entorno
- estado de Codex
- detección de Playwright
- inspección de archivos de configuración
- salida JSON contractual

Fase 2 implementada:
- intento de refresh de credenciales Codex
- validación real con `codex exec "Responde solamente OK"`
- clasificación de fallo a `PRIMARY_RESTORED`, `FALLBACK_ACTIVE`, `CONFIG_REPAIR_REQUIRED` o `HUMAN_REQUIRED`
- opción de login interactivo legítimo si se habilita explícitamente

Fase 3 implementada:
- runner determinista de Playwright con contrato JSON
- acciones soportadas: `goto`, `click`, `type`, `wait_visible`, `assert_text`, `screenshot`
- captura de evidencias por paso
- salida JSON normalizada para integración futura

## Script de diagnóstico

Ejecutar:

```bash
python scripts/hermes_reconnect_doctor.py --json-output /tmp/hermes_reconnect_doctor.json
```

Salida esperada:
- `PHASE1_OK`: entorno listo para continuar
- `PHASE1_WARN`: faltan piezas no bloqueantes
- `PHASE1_BLOCKED`: faltan prerequisitos críticos

## Script de recuperación

Ejecutar:

```bash
python scripts/hermes_reconnect_recovery.py --json-output /tmp/hermes_reconnect_recovery.json
```

Opciones útiles:
- `--allow-interactive-login`: permite el flujo interactivo legítimo si la credencial ya no se puede refrescar
- `--restart-service`: reinicia el servicio del agente tras una validación exitosa

Salida esperada:
- `PRIMARY_RESTORED`: el modelo respondió OK y el camino no-browser funcionó
- `FALLBACK_ACTIVE`: el primario sigue caído o no responde correctamente
- `CONFIG_REPAIR_REQUIRED`: el problema parece de configuración/modelo
- `HUMAN_REQUIRED`: hace falta reautenticación legítima o intervención manual

## Standby operativo

Ejecutar antes de que ocurra la caída:

```bash
python scripts/hermes_reconnect_standby.py --restart-service
```

Opciones útiles:
- `--allow-browser-login`: deja habilitada la ruta legítima interactiva si el refresh local falla
- `--service-name hermes-agent`: servicio a reiniciar tras una recuperación exitosa

Salida esperada:
- `ready_for_failure=true`: el flujo quedó precomprobado y listo para responder a una caída
- si hace falta browser, se deja un handoff en `/tmp/hermes_reconnect_browser_handoff.json`

Trigger automático:
- cuando el agente detecta la caída y entra en la cadena de fallback, `run_agent.py` lanza una vez el standby operativo en segundo plano para dejar trazado el handoff

## Siguiente paso

La fase 3 queda lista para enlazar con la autorización legítima asistida por Playwright cuando el flujo interactivo sea necesario.

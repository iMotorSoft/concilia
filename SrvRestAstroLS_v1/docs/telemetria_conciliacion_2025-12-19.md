# Telemetría de conciliación — Contrato SSE (v1)

Fecha: 2025-12-19  
Rama: `procesamiento-multiple-extractos`

Este documento define un contrato de telemetría por SSE para informar progreso y etapas de conciliación al usuario.

---

## Objetivo

- Dividir la conciliación en **etapas visibles** y **medibles**.
- Exponer progreso (por etapa + global) y tiempos.
- Mantener compatibilidad con eventos existentes (`RUN_START`, `RESULTS_READY`).

---

## Envelope propuesto (mensaje SSE)

Todos los mensajes continúan con el formato actual `{ type, payload }`.
Se agregan campos estandarizados en `payload` para telemetría.

```json
{
  "type": "RECONCILE_STAGE",
  "payload": {
    "run_id": "run-uuid",
    "stage": "LOAD_EXTRACTO",
    "status": "start|progress|done|error",
    "message": "Cargando extracto…",
    "progress": { "current": 12000, "total": 45000, "pct": 26.7, "eta_ms": 120000 },
    "metrics": { "rows": 12000, "bytes": 10485760 },
    "timing_ms": 1840
  }
}
```

Campos clave:
- `run_id`: identifica una corrida (importante si el usuario relanza).
- `stage`: etapa declarada (ver lista abajo).
- `status`: estado del stage (`start`, `progress`, `done`, `error`).
- `message`: texto amigable para UI.
- `progress`: opcional; si no hay granularidad real, usar solo `pct` o emitir solo `start/done`.
- `metrics`: opcional; filas, bytes, contadores parciales.
- `timing_ms`: opcional; tiempo acumulado en la etapa.

---

## Tipos de eventos SSE

Compatibles con el flujo actual:
- `RUN_START` (se mantiene, puede incluir `run_id` y `stages`).
- `RESULTS_READY` (se mantiene, puede incluir `run_id`).
- `TOAST` (mensajes puntuales).

Nuevos eventos sugeridos:
- `RECONCILE_PLAN`
  - payload: `{ run_id, stages: [{ name, label, weight }] }`
  - Permite renderizar timeline antes de procesar.
- `RECONCILE_STAGE`
  - payload: `{ run_id, stage, status, message, progress, metrics, timing_ms }`
- `RECONCILE_ERROR`
  - payload: `{ run_id, stage, error: { type, message }, retryable: bool }`

---

## Etapas sugeridas (pasos)

Estas etapas permiten fraccionar el proceso y mostrar progreso visible.

1. `PREPARE_INPUTS`
   - Validar URIs, parámetros y permisos.
2. `LOAD_EXTRACTO`
   - Parseo / lectura del extracto (xlsx/csv/parquet).
3. `LOAD_CONTABLE`
   - Parseo / lectura del contable (PILAGA).
4. `NORMALIZE`
   - Normalización de columnas, fechas y montos.
5. `MATCH_1_1`
   - Conciliación exacta 1→1 por monto + ventana.
6. `N1_APPROVED`
   - Grupos N→1 aprobados (tolerancia estricta).
7. `N1_SUGGESTED`
   - Grupos N→1 sugeridos (tolerancia laxa).
8. `SUMMARY`
   - Resumen y métricas generales.
9. `DETAILS_CACHE` (opcional)
   - Preparar/cachear detalles si se decide persistir resultados.
10. `FINALIZE`
   - Emisión de `RESULTS_READY` y limpieza.

---

## Progreso global (opcional)

Si se necesita un porcentaje total, se proponen pesos iniciales:

```json
[
  {"stage":"PREPARE_INPUTS", "weight": 2},
  {"stage":"LOAD_EXTRACTO",  "weight": 18},
  {"stage":"LOAD_CONTABLE",  "weight": 18},
  {"stage":"NORMALIZE",      "weight": 8},
  {"stage":"MATCH_1_1",      "weight": 16},
  {"stage":"N1_APPROVED",    "weight": 10},
  {"stage":"N1_SUGGESTED",   "weight": 10},
  {"stage":"SUMMARY",        "weight": 10},
  {"stage":"DETAILS_CACHE",  "weight": 6},
  {"stage":"FINALIZE",       "weight": 2}
]
```

Regla:
- `overall_pct = sum(stage_weight * stage_pct) / total_weight`
- Si no hay granularidad, emitir solo `start` y `done` (0%/100%).

---

## Secuencia mínima recomendada

1) `RUN_START` (incluye `run_id`)  
2) `RECONCILE_PLAN` (lista de etapas)  
3) `RECONCILE_STAGE` (start/progress/done por etapa)  
4) `RESULTS_READY`  
5) `TOAST` (si hay warnings o errores no fatales)

---

## Notas de compatibilidad

- El UI actual puede ignorar los eventos nuevos sin romperse.
- Los eventos existentes (`RUN_START`, `RESULTS_READY`) siguen funcionando.
- Se puede comenzar emitiendo solo `RECONCILE_STAGE` con `start/done` por etapa y luego enriquecer con `progress`.

---

## Implementacion MVP (con DB)

Proyecto: `concilia`  
Tenant por defecto: `fce`

- `routes/v1/reconcile_start.py` emite `RUN_START` + `RECONCILE_STAGE` (start/done) + `RESULTS_READY`.
- Se persiste cada corrida en `concilia_runs` y cada etapa en `concilia_events`.
- `run_id` se incluye en `RUN_START` y `RESULTS_READY`.
- Configuracion en `globalVar.py`:
  - `TENANT_SLUG`, `TENANT_NAME`, `PROJECT_NAME`
  - `ENABLE_TELEMETRY`, `TELEMETRY_BASIC_ONLY`, `AUTO_BOOTSTRAP_TENANCY`

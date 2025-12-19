# Inventario de conciliación — 2025-12-19

Fecha: 2025-12-19  
Rama: `procesamiento-multiple-extractos`

Este inventario describe el flujo actual de conciliación, endpoints, eventos SSE y UI vigente.

---

## Infra SSE (backend)

Archivo: `routes/v1/agui_notify.py`

- Endpoint: `GET /api/ag-ui/notify/stream?threadId=...`
- Modelo: cola en memoria por `threadId` (topic) + buffer `_PENDING` si no hay suscriptor.
- Emite siempre `DEBUG CONNECTED` al conectar, luego flush de pendientes.
- No hay persistencia; si se cae el proceso se pierden eventos en cola.

### Eventos SSE emitidos hoy

- `DEBUG` `{ stage: "CONNECTED", threadId }`
- `TEXT_MESSAGE_REQUEST_UPLOAD` (desde `routes/v1/chat_concilia.py`)
- `TEXT_MESSAGE_CONTENT` (desde `routes/v1/chat_concilia.py`)
- `INGEST_PREVIEW` (desde `routes/v1/uploads_v2_concilia.py`, `routes/v1/uploads_ingest.py`, `routes/v1/uploads_concilia.py`)
- `INGEST_CANONICAL_READY` (desde `routes/v1/ingest_confirm.py`)
- `READY_TO_RECONCILE` (desde `routes/v1/ingest_confirm.py`)
- `RUN_START` (desde `routes/v1/reconcile_start.py`)
- `RESULTS_READY` (desde `routes/v1/reconcile_start.py`)
- `TOAST` (errores o info puntual desde varios endpoints)
- `RECONCILE_SNAPSHOT` (desde `routes/v1/reconcile_quick.py`)

---

## Backend: Ingesta y confirmación

### Upload (extracto/contable)

Archivo: `routes/v1/uploads_v2_concilia.py`

- Endpoint principal: `POST /api/uploads/v2/ingest?role=extracto|contable`
- Admite **multi-file real** (`FormData.append("file", ...)`).
- Guarda en `storage/incoming`, ejecuta `sniff_file()` por archivo.
- Para extracto con `uploads_count > 1`:
  - Genera XLSX consolidado `*_extracto_merged.xlsx` para mantener pipeline.
  - Calcula cobertura por meses/dias, gaps y solapamientos.
  - Emite `INGEST_PREVIEW` con `meta.uploads[]`.
- Para 1 archivo:
  - `INGEST_PREVIEW` con `detected`, `suggest`, `needs`, `validation`, `meta`.

Endpoints legacy aún presentes:
- `POST /api/uploads/ingest` (single-file, requiere role)
- `POST /api/uploads/bank-movements` (single-file legacy)

### Confirmación de preview

Archivo: `routes/v1/ingest_confirm.py`

- Endpoint: `POST /api/ingest/confirm`
- Requiere: `threadId` y `role` (`extracto` | `contable`).
- Guarda estado en memoria `_CONFIRMS[threadId]`.
- Dispara generación **asíncrona** de Parquet canónico (`storage/canonical`).
- Emite:
  - `TOAST` confirmación.
  - `INGEST_CANONICAL_READY { role, canonical_uri }`.
  - `READY_TO_RECONCILE` cuando ambos roles confirmaron.

---

## Backend: Conciliación y resultados

### Inicio de conciliación

Archivo: `routes/v1/reconcile_start.py`

- Endpoint: `POST /api/reconcile/start`
- Inputs: `uri_extracto`, `uri_contable`, `days_window` (default 5).
- Emite `RUN_START` al arrancar y `RESULTS_READY` con summary final.
- Algoritmo actual: match 1→1 por `monto_r` + ventana de fechas.
- Cache en memoria `_DF_CACHE` para evitar reparsear el mismo XLSX.

### Resumen

Archivo: `routes/v1/reconcile_summary.py`

- Endpoints:
  - `POST /api/reconcile/summary` (summary completo + descomposición)
  - `POST /api/reconcile/summary/head` (totales sin descomposición)
  - `POST /api/reconcile/summary/descomposicion`
- Usa `_compute_pipeline` (pares, N→1, sugeridos, sobrantes).
- Incluye `timings` por etapa.

### Detalle de resultados

Archivo: `routes/v1/reconcile_details.py`

Endpoints:
- `POST /api/reconcile/details`
- `POST /api/reconcile/details/no-banco`
- `POST /api/reconcile/details/pares`
- `POST /api/reconcile/details/no-contable`
- `POST /api/reconcile/details/n1/grupos`
- `POST /api/reconcile/details/n1/sugeridos`

Características:
- Todos recalculan pipeline sobre la marcha.
- Límites de filas en responses (500/1000 según endpoint).

### Quick reconcile

Archivo: `routes/v1/reconcile_quick.py`

- Endpoint: `POST /api/reconcile/quick` (multipart con archivos).
- Emite `RECONCILE_SNAPSHOT` con detalle completo si se pasa `threadId`.

---

## Pipeline y heurísticas (actual)

Archivo: `routes/v1/reconcile_details.py`

- 1→1: match por `monto_r` + `days_window`.
- N→1 aprobado (exacto): `N1_TOL_APPROVED = 1.0`.
- N→1 sugerido: `N1_TOL_SUGGESTED = 5.0`.
- `N1_MAX_COMBO_DEFAULT = 6`, `N1_CAND_LIMIT_DEFAULT = 20`.
- Fase 1→N banco→PILAGA está desactivada por performance.

---

## Frontend (UI actual)

### ReconciliarApp (principal)

Archivo: `clientA/src/components/agui/ReconciliarApp.svelte`

- Genera `threadId` y conecta SSE al cargar.
- Flujo: chat → upload multi-file → `INGEST_PREVIEW` → confirmación por rol → `startReconcile`.
- Usa `canonical_uri` si llega `INGEST_CANONICAL_READY`.
- Maneja `RUN_START` y `RESULTS_READY`.
- Renderiza:
  - `ReconciliarResumen` (summary head + descomposición).
  - `ReconciliarDetalle` (detalle con endpoints específicos).

### ConciliaApp (legacy)

Archivo: `clientA/src/components/agui/ConciliaApp.svelte`

- Flujo simple con una única preview.
- Maneja `INGEST_PREVIEW` y `RUN_START`.
- No maneja `READY_TO_RECONCILE` ni `RESULTS_READY`.
- Escucha `DIALOG_SNAPSHOT` pero hoy no hay emisor en backend.

---

## Estado de telemetría (hoy)

- Para conciliación: `RUN_START` + `RECONCILE_STAGE` (start/done por etapa) + `RESULTS_READY` con `run_id`.
- Persistencia: `concilia_runs` + `concilia_events` guardan cada corrida y etapa.
- Resumen y detalle: endpoints síncronos sin SSE; recalculan pipeline por request.

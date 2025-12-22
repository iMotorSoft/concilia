# RUNS / EVENTS CONTRACT (core_*)

Fecha: 2025-12-21

## API minima (backend helpers)

Fuente: `services/db_pg.py:19-96`

- `connect_db()` -> asyncpg conn (DB_URL + DB_SCHEMA)
- `get_workspace_by_slug(slug)` -> `workspace_id`
- `create_run(workspace_id, kind, params)` -> `run_id`
- `append_event(workspace_id, run_id, type, payload)`
- `close_run(workspace_id, run_id, status)`

## Tablas core

- `core_runs`: `run_id`, `workspace_id`, `kind`, `status`, `params`, `started_at`, `ended_at`
- `core_events`: `event_id`, `workspace_id`, `run_id`, `ts`, `type`, `payload`

Referencias:
- `services/db_pg.py:36-96` (insert/update queries)

## Contrato minimo para UI

### Crear run
- Input: `workspace_id`, `kind`, `params`
- Output: `run_id`

### Append event
- Input: `workspace_id`, `run_id`, `type`, `payload`
- Output: none (insert)

### Cerrar run
- Input: `workspace_id`, `run_id`, `status`
- Output: none (update)

### Reconstruccion (por run_id)

Consulta base (eventos ordenados):

```sql
SELECT ts, type, payload
FROM core_events
WHERE workspace_id = $1 AND run_id = $2
ORDER BY ts, event_id;
```

Consulta para ultimo estado por stage (STAGE events):

```sql
SELECT DISTINCT ON ((payload->>'stage'))
  payload->>'stage' AS stage,
  payload->>'status' AS status,
  payload->>'message' AS message,
  ts
FROM core_events
WHERE workspace_id = $1
  AND run_id = $2
  AND type = 'STAGE'
ORDER BY (payload->>'stage'), ts DESC, event_id DESC;
```

Consulta de run (status + metadatos):

```sql
SELECT run_id, workspace_id, kind, status, params, started_at, ended_at
FROM core_runs
WHERE workspace_id = $1 AND run_id = $2;
```

## Payload recomendado (STAGE)

- `payload.stage` (string)
- `payload.status` (start|progress|done|error)
- `payload.message` (string)
- `payload.progress` (optional)
- `payload.timing_ms` (optional)

Referencia actual en reconcile_start:
- `routes/v1/reconcile_start.py:512-521`

## Housekeeping (runs colgados -> canceled)

Propuesta (sin implementar):

- criterio: `status = 'running' AND started_at < now() - interval '2 hours'`
- accion: `update core_runs set status='canceled', ended_at=now()`
- opcional: append event `type='STAGE' payload={stage:'FINALIZE',status:'error'}`

SQL sugerido:

```sql
UPDATE core_runs
SET status = 'canceled', ended_at = now()
WHERE status = 'running'
  AND started_at < now() - interval '2 hours';
```

Ubicacion recomendada: job periodic (cron o worker).

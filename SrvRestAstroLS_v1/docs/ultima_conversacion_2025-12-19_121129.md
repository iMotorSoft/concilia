# Ultima conversacion

Fecha/hora: 2025-12-19 12:11:29

## Resumen

- Se reviso el directorio comun de DB en `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/db`.
- Se confirmo que `concilia` tiene migraciones reales: `concilia_tenants`, `concilia_projects`, `concilia_users`, `concilia_memberships`, `concilia_ingest_*`, `concilia_runs`, `concilia_events`, `concilia_artifacts`, `concilia_metrics` y la funcion `concilia_uuid_v7()`.
- `vertice360` y `solhubfx` tienen placeholders sin SQL ejecutable aun.
- Se leyeron los docs de telemetria e inventario de conciliacion:
  - `docs/inventario_conciliacion_2025-12-19.md`
  - `docs/telemetria_conciliacion_2025-12-19.md`
- Se definio el objetivo inmediato: **MVP de concilia** con telemetria basica y persistencia en DB.

## Telemetria (MVP)

- Emitir `RUN_START` + `RECONCILE_STAGE` (start/done) + `RESULTS_READY`.
- Etapas sugeridas: `PREPARE_INPUTS`, `LOAD_EXTRACTO`, `LOAD_CONTABLE`, `NORMALIZE`, `MATCH_1_1`, `SUMMARY`, `FINALIZE`.
- Persistir cada etapa en `concilia_events` y el estado global en `concilia_runs`.

## Multitenancy (simplificado para MVP)

- Proyecto: `concilia`.
- Cliente (tenant): `fce`.
- Usar el usuario root de DB (definido en `globalVar.py`).
- Guardar `tenant_id` y `project_id` en cada run/event para futuro.

## Pendientes

- Implementar en `routes/v1/reconcile_start.py`:
  - Crear `run_id` al iniciar.
  - Emitir etapas intermedias por SSE.
  - Guardar `concilia_runs` y `concilia_events` en Postgres.
  - Agregar `run_id` a `RUN_START` y `RESULTS_READY`.
- Confirmar si se auto-crea tenant/proyecto (`fce`/`concilia`) o se carga manualmente.

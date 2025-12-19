# MVP Telemetria + Multitenancy (Concilia)

Este documento describe la implementacion MVP de telemetria con persistencia en DB,
considerando defaults de multitenancy por proyecto.

## Defaults del proyecto

- Tenant (cliente): `fce`
- Project (producto): `concilia`
- Configuracion en `globalVar.py`:
  - `TENANT_SLUG`, `TENANT_NAME`, `PROJECT_NAME`
  - `ENABLE_TELEMETRY`, `TELEMETRY_BASIC_ONLY`, `AUTO_BOOTSTRAP_TENANCY`

## Flujo MVP

1) `POST /api/reconcile/start`
2) Se crea un `run_id` y se guarda en `concilia_runs`.
3) Se emiten etapas basicas por SSE (`RECONCILE_STAGE` start/done).
4) Se guarda cada etapa en `concilia_events`.
5) Se emite `RESULTS_READY` con `run_id` y `summary`.

## Etapas MVP

- `PREPARE_INPUTS`
- `LOAD_EXTRACTO`
- `LOAD_CONTABLE`
- `NORMALIZE`
- `MATCH_1_1`
- `SUMMARY`
- `FINALIZE`

## Persistencia

- `concilia_runs`: estado global de la corrida.
- `concilia_events`: estados por etapa.

## Nota

Este MVP usa el usuario root de DB, pero guarda `tenant_id` y `project_id` para
no romper el multi-tenant a futuro.

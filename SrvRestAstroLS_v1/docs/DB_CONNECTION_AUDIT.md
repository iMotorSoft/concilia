# DB Connection Audit

## Scope
- Repo path: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1`
- Search patterns: `postgresql`, `psycopg`, `psycopg2`, `asyncpg`, `create_engine`, `create_async_engine`, `asyncpg.create_pool`, `connect(`, `DB_URL`, `DATABASE_URL`, `DB_PG_WORKFLOW_AI`, `workflow_ai`, `workflow_ai_v1`.
- Result: only asyncpg connections, no SQLAlchemy engine/pool creation found in code.

## Findings (DSN/URL construction and connection initialization)
| Archivo | Línea (aprox) | Tipo | Variables env usadas | DB hardcodeada | Respeta `globalVar.DB_URL` |
| --- | --- | --- | --- | --- | --- |
| `globalVar.py` | 54-66 | DSN builder (SQLAlchemy-style URL string) | `CONCIAI_DB_URL` (override), `DB_PG_IP`, `DB_PG_PORT`, `DB_PG_USER`, `DB_PG_PASS`, `DB_PG_WORKFLOW_AI` | default `workflow_ai_v1` (fallback) | N/A (define la fuente de verdad) |
| `services/db_pg.py` | 11-23 | asyncpg | `DB_URL`, `DB_SCHEMA` (desde `globalVar`) | no | si |
| `services/db_concilia_legacy.py` | 17-29 | asyncpg | `DB_URL`, `DB_SCHEMA` (desde `globalVar`) | no | si |
| `scripts/analyze_db.py` | 5-19 | asyncpg | `DB_URL`, `DB_SCHEMA` (desde `globalVar`) | no | si |
| `backend/tools/db_smoke_test.py` | 9-66 | asyncpg | `DB_URL`, `DB_SCHEMA` (desde `globalVar`), **DB_PG_\*** cargadas desde `~/.bashrc` si no están en `os.environ` | no | si (pero el `DB_URL` queda influenciado por la carga desde `.bashrc`) |
| `backend/tools/core_run_smoke_test.py` | 6-45 | asyncpg (via `services/db_pg.connect_db`) | `DB_URL`, `DB_SCHEMA` (indirecto), **DB_PG_\*** cargadas desde `~/.bashrc` si no están en `os.environ` | no | si (indirecto) |

## Hardcode de DB "workflow_ai"
- No hay ocurrencias de `workflow_ai` hardcodeado en el repo.
- Solo aparece `workflow_ai_v1` como default en `globalVar.py` (`DB_PG_WORKFLOW_AI`).

## Variables de entorno similares / potencialmente confusas
- Usadas realmente por el código:
  - `CONCIAI_DB_URL` (override de `DB_URL`)
  - `CONCIAI_DB_SCHEMA`
  - `DB_PG_*` (fallback para construir `DB_URL`)
- **No se usa** `CONCILIA_DB_URL` ni `DATABASE_URL` en el código.
- Si el entorno exporta `CONCILIA_DB_URL`, queda **ignorado** y se usa el fallback (que depende de `DB_PG_WORKFLOW_AI`).

## Duplicados de `globalVar`
- No se detectaron archivos alternativos (solo `globalVar.py` en la raíz).

## Plan mínimo de corrección (sin implementar)
- `globalVar.py`: aceptar alias `CONCILIA_DB_URL` (y opcionalmente `DATABASE_URL`) además de `CONCIAI_DB_URL`, o emitir warning claro si `CONCILIA_DB_URL` está seteada pero no se usa. Esto evita que el servicio ignore el env correcto por typo de nombre.
- `backend/tools/db_smoke_test.py`: eliminar `_load_env_from_bashrc()` o migrarlo a lectura exclusiva de `DB_URL` (para evitar que un export antiguo de `DB_PG_WORKFLOW_AI=workflow_ai` se cuele en pruebas).
- `backend/tools/core_run_smoke_test.py`: mismo ajuste que arriba (no cargar `.bashrc`, usar solo `DB_URL`).
- No se requieren cambios en `services/db_pg.py`, `services/db_concilia_legacy.py` ni `scripts/analyze_db.py`: ya respetan `globalVar.DB_URL` + `DB_SCHEMA`.

## Root cause candidate #1/#2/#3 (ordenado por probabilidad)
1) `CONCIAI_DB_URL` está definido en el entorno con `.../workflow_ai` y está sobreescribiendo el default.  
2) `DB_PG_WORKFLOW_AI` está definido como `workflow_ai` (p. ej. export en entorno/servicio o `.bashrc`), y `CONCIAI_DB_URL` no está seteado.  
3) El entorno está seteando `CONCILIA_DB_URL` (no `CONCIAI_DB_URL`), por lo que se ignora y se cae al fallback basado en `DB_PG_WORKFLOW_AI` (posiblemente antiguo).

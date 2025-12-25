# DB Connection Audit

## Scope
- Repo path: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1`
- Search patterns: `postgresql`, `psycopg`, `psycopg2`, `asyncpg`, `create_engine`, `create_async_engine`, `asyncpg.create_pool`, `connect(`, `DB_URL`, `DATABASE_URL`, `DB_PG_WORKFLOW_AI`, `workflow_ai`, `workflow_ai_v1`.
- Result: only asyncpg connections, no SQLAlchemy engine/pool creation found in code.

## Findings (DSN/URL construction and connection initialization)
| Archivo | Línea (aprox) | Tipo | Variables env usadas | DB hardcodeada | Respeta `globalVar.DB_URL` |
| --- | --- | --- | --- | --- | --- |
| `globalVar.py` | 54-70 | DSN builder (SQLAlchemy-style URL string) | `DB_PG_IP`, `DB_PG_PORT`, `DB_PG_USER`, `DB_PG_PASS`, `DB_PG_WORKFLOW_AI`, `DB_SCHEMA` | default `workflow_ai_v1` (fallback) | N/A (define la fuente de verdad) |
| `services/db_config.py` | 1-120 | DB config + normalizacion + logging | `DB_URL`, `DB_SCHEMA` (desde `globalVar`) | no | si |
| `services/db_pg.py` | 1-40 | asyncpg (core) | `DB_URL`, `DB_SCHEMA` (via `services/db_config.py`) | no | si |
| `services/db_concilia_legacy.py` | 1-40 | asyncpg (legacy) | `DB_URL`, `DB_SCHEMA` (via `services/db_config.py`) | no | si |
| `scripts/analyze_db.py` | 1-30 | asyncpg | `DB_URL`, `DB_SCHEMA` (desde `globalVar`) | no | si |
| `backend/tools/db_smoke_test.py` | 1-60 | asyncpg | `DB_URL`, `DB_SCHEMA` (via `services/db_config.py`) | no | si |
| `backend/tools/core_run_smoke_test.py` | 6-45 | asyncpg (via `services/db_pg.connect_db`) | `DB_URL`, `DB_SCHEMA` (indirecto), **DB_PG_\*** cargadas desde `~/.bashrc` si no están en `os.environ` | no | si (indirecto) |

## Hardcode de DB "workflow_ai"
- No hay ocurrencias de `workflow_ai` hardcodeado en el repo.
- Solo aparece `workflow_ai_v1` como default en `globalVar.py` (`DB_PG_WORKFLOW_AI`).

## Variables de entorno similares / potencialmente confusas
- Usadas realmente por el código:
  - `DB_PG_*` (para construir `DB_URL`)
  - `DB_SCHEMA`
- **No se usa** `CONCIAI_DB_URL`, `CONCILIA_DB_URL` ni `DATABASE_URL` en el codigo.
- Si el entorno exporta `CONCILIA_DB_URL`, queda **ignorado** y se usa el fallback (que depende de `DB_PG_WORKFLOW_AI`).

## Duplicados de `globalVar`
- No se detectaron archivos alternativos (solo `globalVar.py` en la raíz).

## Notas recientes
- Se centralizo la config en `services/db_config.py` (normalizacion de host IPv4, logging seguro de host/puerto/db/schema).
- `connect_db` ahora acepta `connect_timeout` y `statement_timeout_ms` en `services/db_pg.py` y `services/db_concilia_legacy.py`.
- `backend/tools/db_smoke_test.py` valida conectividad core + legacy con timeouts explicitos.
- `backend/tools/core_run_smoke_test.py` sigue cargando variables desde `~/.bashrc`.

## Root cause candidate #1/#2/#3 (ordenado por probabilidad)
1) `DB_PG_WORKFLOW_AI` apunta a la DB incorrecta (export en entorno/servicio o `.bashrc`).  
2) `DB_PG_IP`/`DB_PG_PORT` apuntan al host equivocado o no accesible.  
3) `DB_SCHEMA` no coincide con el schema esperado (objetos faltantes).

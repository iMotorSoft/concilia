# PostgreSQL Driver Policy

## Driver

- **Only** `psycopg 3` (async) — `psycopg[pool]`, `psycopg[binary]`
- No `asyncpg`, no `psycopg2`, no ORM (SQLAlchemy, Tortoise, etc.) without ADR

## Connection Management

- Pool via `psycopg.AsyncConnectionPool` from `backend/core/config.py`
- Pool size: `min_size=2`, `max_size=10` (tunable via `CONCILIA_DB_POOL_*`)
- Connections acquired via `pool.connection()` context manager
- No persistent connections outside pool

## SQL Location

- All SQL lives in `backend/repositories/*.py`
- One repository per domain entity (uploads, canonical, runs, reconciliation)
- Repository methods return typed dataclasses / Pydantic models
- Raw SQL with `sql.SQL` composition — no string interpolation

## Transactions

- Explicit `async with pool.connection() as conn, conn.transaction():`
- Read-only transactions for queries (`conn.read_only = True`)
- No implicit commits; all writes in explicit transaction blocks

## Migrations

- SQL files in `backend/db/migrations/` (numbered, e.g., `001_initial.sql`)
- Applied via `backend/scripts/migrate.py` (psycopg direct execution)
- No auto-migration on startup; explicit `make migrate` required

## Forbidden

- ORM models replacing repository SQL
- Connection strings in code (only via `config.py`)
- `SELECT *` in production queries
- DDL in application code (only in migration files)
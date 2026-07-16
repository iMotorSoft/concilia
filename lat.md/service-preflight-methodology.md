# Service Preflight Methodology

This policy governs validation against real external services (PostgreSQL, future Milvus/LiteLLM).

## Principle

**No silent fallbacks.** Service-dependent work must explicitly verify availability and fail fast if unavailable.

## Preflight Check

```python
# scripts/preflight.py
async def preflight_postgres():
    pool = create_pool(dsn_from_config())
    async with pool.connection() as conn:
        await conn.execute("SELECT 1")
        # Verify schema
        await conn.execute("SELECT 1 FROM reconciliation_runs LIMIT 1")
    return {"status": "ok", "latency_ms": ...}
```

**Required before**:
- Integration tests marked `@pytest.mark.real_services`
- E2E tests requiring DB
- Migration scripts
- Benchmark runs

## Test Markers

```python
# pytest.ini
markers =
    real_services: requires PostgreSQL (and future Milvus/LiteLLM)
    unit: no external services
    smoke: fast startup verification
```

```bash
# Run only unit tests (default)
uv run pytest

# Run with real services
uv run pytest -m real_services

# Smoke test
uv run pytest -m smoke
```

## CI/CD

- Unit tests: always run
- Real services: run only when `POSTGRES_DSN` secret present
- No mocking PostgreSQL in `@real_services` tests

## Fallback Policy

| Scenario | Behavior |
|----------|----------|
| Wizard DB unavailable | Explicit in-memory fallback (logged, metrics emitted) |
| Reconciliation DB unavailable | **Hard fail** — no fallback |
| Upload canonical write fail | **Hard fail** — no partial state |
| Future Milvus unavailable | Vector search disabled, FTS only (explicit) |

**No silent degradation** — every fallback is a deliberate code path with observability.

## Observability

Every preflight/check emits structured log:

```json
{
  "event": "preflight.postgres",
  "status": "ok|fail",
  "latency_ms": 12,
  "dsn_host": "db.internal",
  "schema_version": "20260716_01"
}
```

## Forbidden

- `try/except` around DB connect without explicit fallback logic
- Mocking external services in integration tests
- Assuming service availability without preflight
- Silent retry loops without backoff + max attempts + logging
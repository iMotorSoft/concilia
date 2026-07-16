# Wizard Runtime Policy

This policy governs the reconciliation wizard execution model, memory fallback, SSE streaming and lifecycle.

## Execution Model

The wizard is a **multi-step flow** that guides scope selection before launching reconciliation.

### Steps

1. **Alcance** — detect max window, show extracto/contable date ranges, user confirms or adjusts
2. **Confirmación** — user confirms scope (`Continuar igual` / `Ajustar alcance`)
3. **Ejecución** — launches `POST /api/reconcile/start`, streams progress via SSE

### State Machine

```
INIT → SCOPE_DETECTED → SCOPE_CONFIRMED → RUNNING → COMPLETED
                    ↓
              SCOPE_ADJUSTED → SCOPE_CONFIRMED
```

## Memory Fallback

When `workflow_ai_v1` database unavailable:

- **Trigger**: `asyncpg.exceptions.InvalidCatalogNameError` on run creation
- **Store**: `services/wizard_runtime.InMemoryWizardStore`
- **Run ID prefix**: `mem-` (e.g., `mem-abc123`)
- **Persistence**: Process memory only (lost on restart)
- **Logging**: WARNING with run_id and trigger error

### Store Interface

```python
class WizardStore(ABC):
    async def create_run(self, payload: WizardStartPayload) -> RunRecord
    async def get_run(self, run_id: str) -> RunRecord | None
    async def append_event(self, run_id: str, event: WizardEvent) -> None
    async def get_events(self, run_id: str, after: int) -> list[WizardEvent]
    async def set_status(self, run_id: str, status: RunStatus) -> None
```

Both `PostgresWizardStore` and `InMemoryWizardStore` implement this interface.

## SSE Streaming

- Endpoint: `GET /api/reconcile_wizard/runs/{run_id}/events`
- Format: Server-Sent Events (`text/event-stream`)
- Event types: `STARTED`, `SCOPE_DETECTED`, `FORM_SNAPSHOT`, `CONFIRMATION_REQUIRED`, `LIST_SNAPSHOT`, `STEP_COMPLETED`, `COMPLETED`, `ERROR`
- Client: `EventSource` in `ReconciliarApp.svelte`
- Heartbeat: `:` comment every 15s to prevent proxy timeout

## Run Action

- Endpoint: `POST /api/reconcile_wizard/runs/{run_id}/action`
- Actions: `confirm_scope`, `adjust_scope`, `cancel`
- Validates current state before transition

## Concurrency

- One active wizard run per user session (enforced by frontend)
- Store supports multiple concurrent runs (different `run_id`)
- In-memory store uses `asyncio.Lock` per `run_id`

## Cleanup

- PostgreSQL runs: TTL 24h (cleanup job `backend/scripts/cleanup_wizard_runs.py`)
- Memory runs: evicted on `COMPLETED` + 5min or `ERROR` immediate
- No cleanup on process restart (memory runs lost — acceptable for dev)

## Forbidden

- Persisting wizard state in `core_runs`/`core_events` (decoupled 2026-04-21)
- `days_window` parameter in wizard (moved to reconciliation engine)
- Blocking calls in SSE generator
- Silent fallback without logging
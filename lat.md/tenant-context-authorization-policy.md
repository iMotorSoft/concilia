# Tenant Context & Authorization Policy

This policy governs multi-tenancy and request-scoped authorization in Concilia.

## Tenant Model

- **Single-tenant default** (current): One logical tenant per deployment
- **Multi-tenant ready**: Schema supports `tenant_id` on all domain tables
- **No shared-data tenants**: Each tenant's data fully isolated

## Request Context

```python
# middleware/tenant.py
async def tenant_middleware(request: Request, call_next):
    # 1. Extract from session
    tenant_id = request.session.get("tenant_id")
    # 2. Admin override header (dev only)
    if request.headers.get("X-Tenant-Override") and request.user.is_admin:
        tenant_id = request.headers["X-Tenant-Override"]
    # 3. Validate exists + active
    tenant = await tenant_repo.get(tenant_id)
    if not tenant or not tenant.active:
        raise HTTPException(403, "Invalid tenant")
    # 4. Bind to request.state
    request.state.tenant_id = tenant.id
    request.state.tenant = tenant
```

## Repository Pattern

```python
# repositories/base.py
class TenantRepository:
    def __init__(self, pool, tenant_id: str):
        self.pool = pool
        self.tenant_id = tenant_id

    async def _execute(self, query, params):
        # Automatically inject tenant_id
        return await self.pool.execute(
            query + " AND tenant_id = $1", *params, self.tenant_id
        )
```

**All queries** go through tenant-scoped repository — no raw SQL with manual `tenant_id`.

## Row-Level Security (Future)

PostgreSQL RLS policies as defense-in-depth:

```sql
ALTER TABLE reconciliation_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON reconciliation_runs
  USING (tenant_id = current_setting('app.current_tenant_id'));
```

Set via `SET LOCAL app.current_tenant_id = '...'` in middleware.

## Authorization Checks

| Resource | Check |
|----------|-------|
| Upload | `tenant_id` match |
| Wizard run | `tenant_id` match + `operator` role |
| Reconciliation | `tenant_id` match + `operator` role |
| Reports | `tenant_id` match + `viewer` role |
| Admin panel | `admin` role (global) |

## API Contract

- All responses include `X-Tenant-ID` header (for debugging)
- 403 if tenant mismatch
- 404 (not 403) for cross-tenant resource access (info hiding)

## Forbidden

- `tenant_id` as query param or body field
- Cross-tenant joins without `admin` role
- Session without `tenant_id` (except login)
- Repository methods without tenant scoping
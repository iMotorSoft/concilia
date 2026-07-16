# Global Configuration Facade Policy

This policy governs how configuration and secrets are accessed in Concilia.

## Architecture

```
Environment Variables → backend/core/config.py → globalVar.py (facade) → application code
                                                      ↓
                                            global.js (public only)
```

## Rules

### Backend

- **Only** `backend/core/config.py` reads environment variables directly.
- `globalVar.py` (root) is a **pure facade**: re-exports `config` values, no I/O, no side effects.
- Application code imports from `globalVar` or `config` — never `os.environ` directly.
- Migration target: all code uses `backend.core.config`; `globalVar.py` becomes thin re-export.

### Frontend

- `global.js` contains **only public, non-sensitive** config (titles, endpoints, feature flags).
- No secrets, DSNs, tokens, API keys in `global.js`.
- Build-time injection via Astro `import.meta.env.PUBLIC_*`.

### Environment Variables

Prefix: `CONCILIA_`

| Variable | Scope | Required | Description |
|----------|-------|----------|-------------|
| `CONCILIA_DB_PG_HOST` | backend | yes | PostgreSQL host |
| `CONCILIA_DB_PG_PORT` | backend | yes | PostgreSQL port (default 5432) |
| `CONCILIA_DB_PG_USER` | backend | yes | PostgreSQL user |
| `CONCILIA_DB_PG_PASSWORD` | backend | yes | PostgreSQL password |
| `CONCILIA_DB_PG_DATABASE` | backend | yes | Database name (`concilia` or `workflow_ai_v1`) |
| `CONCILIA_BACKEND_HOST` | dev | no | Override backend host (default 127.0.0.1) |
| `CONCILIA_BACKEND_PORT` | dev | no | Override backend port (default 7058) |
| `CONCILIA_ASTRO_HOST` | dev | no | Override frontend host |
| `CONCILIA_ASTRO_PORT` | dev | no | Override frontend port |
| `CONCILIA_E2E_ADMIN_EMAIL` | test | no | E2E auth email |
| `CONCILIA_E2E_ADMIN_PASSWORD` | test | no | E2E auth password |

### Secrets Management

- **Never** commit `.env*`, `.env.*.local`, or files with real credentials.
- `SrvRestAstroLS_v1/.env.backend-dev.local` allowed for local dev overrides (gitignored).
- Production secrets injected via deployment platform (not filesystem).

## Validation

- `backend/core/config.py` validates required vars at startup; fails fast with clear error.
- `lat check` verifies no `os.environ` access outside `config.py`.
- `git diff --check` blocks committed secrets.
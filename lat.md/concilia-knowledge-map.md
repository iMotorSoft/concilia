# Concilia Knowledge Map

Navigable index of canonical concepts, components and their relationships.

## Core Domains

```
concilia/
├── reconciliation/          # Motor de conciliación bancario-contable
│   ├── pipeline/           # 1a1, N->1, sugeridos, sobrantes
│   ├── sicom/              # Ingesta, agrupación, regla Nro Pago+OP
│   ├── scope/              # Bank scope, account scope, SICOM scope
│   └── output/             # Summary, details, cards, auditoría
├── wizard/                 # Asistente de alcance/cobertura
│   ├── runtime/            # Fallback memoria, SSE, actions
│   ├── steps/              # Scope detection, confirmation, execution
│   └── events/             # Event log, snapshots
├── upload/                 # Ingesta multi-formato
│   ├── extracto/           # Extracto bancario (patagonia, santander, etc)
│   ├── contable/           # PILAGA / contable cliente
│   ├── sicom/              # SICOM mensual multi-solapa
│   └── canonical/          # Parquet canónicos + metadata
├── auth/                   # Autenticación, sesiones, roles
└── config/                 # Configuración centralizada (core/config.py)
```

## Key Contracts (LAT)

| Contract | File | Anchors |
|----------|------|---------|
| Scope resolution | `reconciliation-scope-contract.md` | `@lat:reconciliation-scope-contract` |
| SICOM rules | `sicom-integration-policy.md` | `@lat:sicom-integration-policy` |
| Wizard fallback | `wizard-runtime-policy.md` | `@lat:wizard-runtime-policy` |
| Config facade | `global-configuration-facade-policy.md` | `@lat:global-configuration-facade-policy` |
| PostgreSQL | `postgres-driver-policy.md` | `@lat:postgres-driver-policy` |

## Data Flow

```
Upload (extracto, contable, sicom) 
    → Confirm → Canonical Parquet
    → Wizard (scope detection → confirmation)
    → Reconcile Start (bank_scope, account_scope, uri_sicom)
    → Pipeline (1a1, N->1 with SICOM enforcement)
    → Summary + Details (cards: 1a1, N1 aprobados, sugeridos, cierre SICOM)
    → Audit trail (runs, events, snapshots)
```

## Canonical Data Artifacts

| Artifact | Location | Schema |
|----------|----------|--------|
| Extracto canonical | `storage/canonical/extracto/{id}.parquet` | fecha, importe, descripcion, banco, cuenta, ... |
| Contable canonical | `storage/canonical/contable/{id}.parquet` | nro_comprobante, fecha, importe, op, ... |
| SICOM canonical | `storage/canonical/sicom/{id}.parquet` | fecha_pago, banco, nro_pago, op, imp_neto, ... |
| Reconciliation run | PostgreSQL `reconciliation_runs` | id, scope, uri_*, status, created_at |
| Wizard run | PostgreSQL `wizard_runs` / memory | id, step, scope, snapshot, events |

## External Integrations

| Service | Purpose | Policy |
|---------|---------|--------|
| PostgreSQL | Source of truth | `postgres-driver-policy.md` |
| Local FS / S3 | Canonical parquet storage | `pdf-excel-extraction-policy.md` |
| Playwright + Chromium | E2E gate | `browser-mcp-validation-policy.md` |

## Entry Points

| Interface | Path | Description |
|-----------|------|-------------|
| Backend API | `SrvRestAstroLS_v1/backend/ls_iMotorSoft_Srv01.py` | Litestar app factory |
| Frontend | `SrvRestAstroLS_v1/clientA/src/pages/reconciliar.astro` | Main reconciliation page |
| Dev backend | `SrvRestAstroLS_v1/backend-dev.sh` | Uvicorn on :7058 |
| Dev frontend | `SrvRestAstroLS_v1/astro-dev.sh` | Astro dev/preview on :3058 |

## Decision Records (ADR)

- `docs/adr/ADR-001-global-config-facade.md` (pending)
- `docs/adr/ADR-002-wizard-memory-fallback.md` (pending)
- `docs/adr/ADR-003-sicom-mandatory-nro-pago-op.md` (pending)
- `docs/adr/ADR-004-bank-scope-data-driven.md` (pending)
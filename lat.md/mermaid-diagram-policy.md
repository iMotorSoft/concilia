# Mermaid Diagram Policy

This policy governs architecture and flow diagrams in Concilia documentation.

## Tooling

- **Source**: Mermaid (`.mmd` or fenced in `.md`)
- **Render**: GitHub-native + `mmdc` CLI for local preview
- **Format**: `flowchart`, `sequenceDiagram`, `erDiagram`, `classDiagram`

## Conventions

### Flowcharts

```mermaid
flowchart LR
  subgraph Frontend[Astro + Svelte]
    UI[Reconciliar Page]
    Wizard[Wizard Island]
  end
  subgraph Backend[Litestar]
    API[API Routes]
    WizardRT[Wizard Runtime]
  end
  subgraph Data[PostgreSQL]
    PG[(reconciliation_runs)]
    PG2[(uploads)]
  end

  UI -->|HTTP| API
  Wizard -->|SSE| WizardRT
  WizardRT -.->|fallback| Mem[(Memory Store)]
  API --> PG
  API --> PG2
```

- Direction: `LR` (left-right) for architecture, `TD` for sequences
- Subgraphs for logical boundaries
- Dashed `-.->` for fallback/async paths
- Solid `-->` for sync HTTP/RPC

### Sequence Diagrams

```mermaid
sequenceDiagram
  participant U as Usuario
  participant F as Frontend
  participant B as Backend
  participant D as PostgreSQL

  U->>F: Click "Iniciar"
  F->>B: POST /reconcile_wizard/start
  alt DB available
    B->>D: INSERT run
  else DB unavailable
    B->>Mem: Create in-memory run
  end
  B-->>F: run_id + scope
  F->>B: GET /reconcile_wizard/runs/{id}/events (SSE)
```

### ER Diagrams

```mermaid
erDiagram
  UPLOADS ||--o{ CANONICAL_FILES : generates
  CANONICAL_FILES ||--o{ RECONCILIATION_RUNS : inputs
  RECONCILIATION_RUNS ||--o{ RECONCILIATION_GROUPS : produces
  RECONCILIATION_GROUPS }|--o{ PILAGA_ROWS : contains
  SICOM_LOTES ||--o{ RECONCILIATION_GROUPS : matches
```

## Location

- **Architecture**: `lat.md/lat.md` (top-level)
- **Feature flows**: In relevant LAT policy (e.g., `wizard-runtime-policy.md`)
- **Data model**: `lat.md/concilia-knowledge-map.md`
- **ADRs**: Embedded in `docs/adr/ADR-XXX.md`

## Validation

```bash
# Local preview
npx -p @mermaid-js/mermaid-cli mmdc -i diagram.mmd -o diagram.svg

# CI check (syntax only)
npx -p @mermaid-js/mermaid-cli mmdc -i lat.md/lat.md -o /dev/null
```

## Forbidden

- PlantUML, GraphViz, Draw.io, Lucidchart sources
- Diagrams without source (no `.mmd` or fenced block)
- Diagrams in docs that drift from code (review in PR)
- Color-dependent meaning (use shape/label)
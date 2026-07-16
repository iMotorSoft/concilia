# SICOM Integration Policy

This policy governs SICOM ingestion, grouping, matching rules and auditability in Concilia.

## Ingestion

- **Input**: Single monthly workbook (`.xlsx`), multi-sheet (one per business day)
- **Role**: `sicom` (distinct from `extracto` and `contable`)
- **Parser**: `services/ingest/sicom_excel.py`
- **Output**: Canonical parquet at `storage/canonical/sicom/{upload_id}.parquet`
- **State**: `files.sicom = {uri, rows, period_from, period_to, bancos_detectados, op_count, nro_pago_count}`

### Preview Contract

```json
{
  "rows": 507,
  "sheet_count": 17,
  "sheet_names": ["03-11", "04-11", "..."],
  "period_from": "2025-11-03",
  "period_to": "2025-11-28",
  "bancos_detectados": ["Banco Patagonia", "Banco Pat.Otros", "Banco Santander", "Banco Sant.Otros"],
  "op_count": 402,
  "nro_pago_count": 87,
  "relacional_op_nropago": {
    "33436": ["8902/2025", "8906/2025", "..."],
    "..."
  }
}
```

## Grouping

SICOM rows grouped by composite key:

```
(Fecha de Pago, Banco, Nro Pago)
```

Each group = 1 **lote SICOM** with:

- `nro_pago` (string)
- `fecha_pago` (date)
- `banco` (string)
- `imp_neto` (Decimal) — **not** `Importe`
- `ops` (list[str]) — unique `Order de P.` / `OP` in group

## Mandatory Matching Rule

When `uri_sicom` present in reconciliation:

> Aprobado `N PILAGA -> 1 extracto` **requires** a SICOM lote matching:
> - `lote.fecha_pago == extracto.fecha`
> - `lote.imp_neto == extracto.importe`
> - All PILAGA `OP` in group ⊆ `lote.ops`

If no such lote exists → group demoted to `sicom_auditoria` (visible, not approved, not consumed).

## OP ↔ Nro Pago Traceability

- `OP` = `Order de P.` from PILAGA (e.g., `1261/2026`)
- `Nro Pago` = SICOM lote key (e.g., `33436`)
- Relationship: **many-to-many** in source, **one-to-many** per lote
- UI shows: `Banco · lote <Nro Pago>` and `OP · lote <Nro Pago>`

## Auditability

Every SICOM-influenced group retains:

- `motivo_auditoria` if demoted (e.g., `sin lote SICOM para fecha + importe del banco; OP sin SICOM: 1261/2026`)
- `lote_nro_pago` if approved
- `ops_en_lote` array
- `ops_sin_match` array (for audit card)

## Scope Filtering

SICOM filtered by resolved `bank_scope` (see [[reconciliation-scope-contract]]).

Default: `patagonia` → `{banco_patagonia, banco_pat_otros}`

## Canonical Schema

Parquet columns:

| Column | Type | Notes |
|--------|------|-------|
| `fecha_pago` | date | |
| `banco` | string | Normalized (see below) |
| `nro_pago` | string | Preserved as-is |
| `op` | string | `Order de P.` normalized |
| `imp_neto` | decimal(18,2) | Matching amount |
| `importe` | decimal(18,2) | Original (may differ) |
| `upload_id` | string | FK to ingest |

### Banco Normalization

```python
BANCO_NORMALIZATION = {
    "BANCO PATAGONIA": "banco_patagonia",
    "BANCO PAT. OTROS": "banco_pat_otros",
    "BANCO SANTANDER": "banco_santander",
    "BANCO SANT. OTROS": "banco_sant_otros",
    # extensible
}
```

## Versioning

- Parser version in parquet metadata: `sicom_parser_version`
- Breaking parser change → new version, re-ingest required
- Migration script in `backend/scripts/migrate_sicom.py`
# Reconciliation Scope Contract

This contract defines the scope boundaries for reconciliation in Concilia.

## Scope Types

| Scope Code | Description | Resolution |
|------------|-------------|------------|
| `bank_scope` | Banco(s) del extracto | Derivado del extracto subido |
| `account_scope` | Cuenta(s) contables | Derivado del contable (PILAGA) |
| `sicom_scope` | Bancos en SICOM a considerar | Mapeo `bank_scope -> {sicom_bancos}` |

## Bank Scope Resolution

The extracto defines the **authoritative bank scope**.

```python
# In routes/v1/reconcile_start.py
BANK_SCOPE_MAP = {
    "patagonia": ["banco_patagonia", "banco_pat_otros"],
    "santander": ["banco_santander", "banco_sant_otros"],
    # extensible per client
}
```

- `bank_scope_code` comes from extracto detection (e.g., `patagonia`)
- Resolves to set of SICOM banco values for filtering
- **Never hardcode** banco values in matching logic

## SICOM Scope Contract

When `uri_sicom` provided:

1. Load SICOM parquet canonical
2. Filter rows: `sicom.banco IN (resolved_bank_scope)`
3. Group by: `Fecha de Pago + Banco + Nro Pago`
4. Each group = 1 lote SICOM with `nro_pago`, `fecha_pago`, `imp_neto`, `ops[]`

## Matching Rules (Mandatory)

### SICOM-Mandatory Groups (when SICOM loaded)

A group `N PILAGA -> 1 extracto` is **approved** iff:

- ∃ lote SICOM with `fecha_pago == extracto.fecha` AND `imp_neto == extracto.importe`
- All PILAGA rows in group have `OP` present in that lote's `ops[]`
- Group labeled `sicom_lote` with `nro_pago = lote.nro_pago`

### Fallback N->1 (no SICOM or no match)

- Sum exact match only
- Labeled `n1_fallback`
- **Not** counted as approved if `uri_sicom` exists
- Visible in `Sugeridos / Auditoría` card

### 1->1 Direct

- Exact `fecha + importe + (OP if available)`
- Labeled `directo_1a1`

## Output Contract

Reconciliation summary returns:

```json
{
  "directos_1a1": { "count": N, "importe": M, "rows": [...] },
  "agrupados_aprobados": { "count": N, "importe": M, "groups": [...] },
  "sugeridos_auditoria": { "count": N, "groups": [...] },
  "pilaga_sin_extracto": { "count": N, "importe": M },
  "extracto_sin_pilaga": { "count": N, "importe": M },
  "sicom": {
    "scope_aplicado": ["banco_patagonia", "banco_pat_otros"],
    "lotes_scope": N,
    "cobertura_extracto": { "matched": N, "total": M },
    "cobertura_pilaga": { "matched": N, "total": M },
    "conciliacion_efectiva": { "filas_pilaga": N, "ops_unicas": M, "importe": X, "lotes_extracto": Y }
  }
}
```

## Extensibility

New bank scopes added via:
1. Entry in `BANK_SCOPE_MAP`
2. Test case in `tests/reconciliation/test_scope_*.py`
3. No matching logic changes required
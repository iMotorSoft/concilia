# PDF/Excel Extraction Policy

This policy governs document parsing for uploads in Concilia.

## Supported Formats

| Format | Parser | Output |
|--------|--------|--------|
| `.xlsx` | `openpyxl` (read-only) | Canonical parquet |
| `.xls` | `xlrd` (legacy) | Canonical parquet |
| `.pdf` | `pdfplumber` + `PyMuPDF` fallback | Text + tables |

## Extraction Contract

### Excel (.xlsx/.xls)

```python
def extract_excel(path: Path) -> ExtractionResult:
    return ExtractionResult(
        rows: list[dict],           # Each row as dict[col_name] = value
        headers: list[str],         # Normalized header names
        sheet_names: list[str],     # All sheets processed
        metadata: {
            "row_count": int,
            "period_from": date|None,
            "period_to": date|None,
        }
    )
```

### PDF

```python
def extract_pdf(path: Path) -> ExtractionResult:
    return ExtractionResult(
        text: str,                    # Full text
        tables: list[list[dict]],     # Extracted tables (pdfplumber)
        pages: int,
        metadata: {}
    )
```

## Header Normalization

- Lowercase, snake_case, ASCII-only
- Alias map for known variants:
  - `Nº Pago` → `nro_pago`
  - `Fecha de Pago` → `fecha_pago`
  - `Imp.Neto` → `imp_neto`
  - `Order de P.` → `op`

## Canonical Parquet Schema

```python
# Extracto
fecha: date
importe: decimal(18,2)
descripcion: string
banco: string
cuenta: string
hash_row: string  # SHA256 for idempotency

# Contable (PILAGA)
nro_comprobante: string
fecha: date
importe: decimal(18,2)
op: string
hash_row: string

# SICOM
fecha_pago: date
banco: string
nro_pago: string
op: string
imp_neto: decimal(18,2)
hash_row: string
```

## Validation

- Row count > 0
- Required columns present (per document type)
- Date range plausible (not future, not > 5 years past)
- No duplicate `hash_row` within file

## Error Handling

- Corrupt file → `400` with parse error detail
- Empty file → `400` "no data rows"
- Unsupported format → `415`
- Parser crash → `500` + Sentry capture

## Forbidden

- `pandas.read_excel` in request path (memory, startup time)
- Writing extracted files to disk outside `storage/`
- Losing original column order (preserve in `headers`)
- Hardcoded header names in matching logic (use normalized keys)
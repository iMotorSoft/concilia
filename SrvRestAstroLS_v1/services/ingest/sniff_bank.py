# SrvRestAstroLS_v1/services/ingest/sniff_bank.py
from __future__ import annotations
import re
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Any, List, Tuple

# ===== Dependencias opcionales =====
try:
    import pandas as pd  # type: ignore
except Exception:
    pd = None

try:
    from openpyxl import load_workbook  # type: ignore
except Exception:
    load_workbook = None

# ===== Config / Mapeos =====
ACCOUNT_MAP = {
    "3-111-0100026005-5": {"bank": "ciudad", "display": "Banco Ciudad - CC $"},
    "100-393300535-000": {"bank": "patagonia", "display": "Banco Patagonia - CC $"},
    "163-0-015508/3":    {"bank": "santander", "display": "Banco Santander - CC $"},
}

BANK_HINTS = [
    ("BANCO CIUDAD", "ciudad"),
    ("BANCO SANTANDER", "santander"),
    ("SANTANDER", "santander"),
    ("BANCO PATAGONIA", "patagonia"),
    ("PATAGONIA", "patagonia"),
]

RE_PERIOD  = re.compile(r"(0?[1-9]|[12][0-9]|3[01])[/\.-](0?[1-9]|1[0-2])[/\.-]([12]\d{3})")
RE_ACCOUNT_ON_LINE = re.compile(r"(?:CC\s*\$|C\/C|\bCTA\.?\s*CTE\b|CUENTA\s*CORRIENTE)[^0-9A-Za-z]*([0-9][0-9\-\./ ]{6,}[0-9])")
RE_PILAGA_ACCOUNT = re.compile(r"\b(\d{3,6}/\d)\b")  # ej: 26005/5

TABLE_HEADER_HINTS = (
    "FECHA DOCUMENTO PRINCIPAL", "DOC. COBRO", "CONTENEDOR", "DETALLE",
    "BENEFICIARIO", "INGRESOS", "EGRESOS", "ACUMULADO",
)
EXCLUDE_TEXT_HINTS = ("SALDO INICIAL", "SALDO FINAL")

# ===== Entry point =====
def sniff_path(path: Path, filename_hint: Optional[str] = None) -> dict:
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xls"):
        return sniff_excel(p, filename_hint)
    if p.suffix.lower() == ".csv":
        return sniff_csv(p)
    return {"kind": "unknown", "detected": {}, "table": {"columns": [], "sample": []}, "suggest": {}}

# ===== Excel =====
def sniff_excel(path: Path, filename_hint: Optional[str]) -> dict:
    grid = read_excel_header_grid(path, max_rows=20, max_cols=12)
    cols_preview, rows_preview, min_date_tab, max_date_tab = read_table_preview(path)

    raw_header_lines = header_lines_from_grid(grid, limit=8)
    compact_header_lines = compact_header(raw_header_lines)
    header_excerpt = "\n".join(compact_header_lines)

    kind = decide_kind(header_excerpt, grid, cols_preview)

    # Cuenta
    account_core_dv = header_extract_account(grid)
    if not account_core_dv and kind == "gl":
        account_core_dv = pilaga_extract_account(grid)

    # Fechas (header o tabla)
    header_from, header_to = header_extract_period(grid)
    period_from = None
    period_to = None

    # === Prioridad para CONTABLE (PILAGA): columna "Fecha" ===
    if kind == "gl":
        fmin, fmax = fecha_column_range(path, header_keyword="Fecha")
        if fmin and fmax:
            period_from, period_to = fmin, fmax

    # Si no se encontraron fechas con el método prioritario, usar los otros métodos
    if not (period_from and period_to):
        period_from = header_from or min_date_tab
        period_to = header_to or max_date_tab

    # Banco + mapeo PILAGA (short→full)
    bank = None
    account_full: Optional[str] = None

    if account_core_dv and account_core_dv in ACCOUNT_MAP:
        bank = ACCOUNT_MAP[account_core_dv]["bank"]
        account_full = account_core_dv

    if kind == "gl" and not bank and account_core_dv and RE_PILAGA_ACCOUNT.fullmatch(account_core_dv):
        mapped_full = map_short_account_to_full(account_core_dv)
        if mapped_full:
            account_full = mapped_full
            bank = ACCOUNT_MAP[mapped_full]["bank"]

    if not bank and header_excerpt:
        txt = header_excerpt.upper()
        for key, label in BANK_HINTS:
            if key in txt:
                bank = label
                break

    if not bank and filename_hint and kind == "bank_movements":
        low = filename_hint.lower()
        if "ciudad" in low: bank = "ciudad"
        elif "patagonia" in low: bank = "patagonia"
        elif "santander" in low: bank = "santander"

    out = {
        "kind": kind if kind != "unknown" else ("gl" if account_core_dv and RE_PILAGA_ACCOUNT.fullmatch(str(account_core_dv)) else kind),
        "detected": {
            "bank": bank,
            "account_core_dv": account_core_dv,
            "account_full": account_full,
            "header_excerpt": header_excerpt if header_excerpt else None,
            "period_from": period_from,
            "period_to": period_to,
        },
        "table": {"columns": cols_preview, "sample": rows_preview},
        "suggest": {"period_from": period_from, "period_to": period_to},
        "needs": {
            "bank": bank is None,
            "account_id": False,
            "period_range": not (period_from and period_to),
        },
    }
    return out

# ===== Heurísticas de tipo =====
def header_has_bank_extract_fields(header_excerpt: str | None, grid: list[list[str]]) -> bool:
    if not header_excerpt:
        return False
    up = header_excerpt.upper()
    hit_keywords = [
        "EXTRACTO DE CUENTA",
        "TIPO Y NRO. DE CUENTA",
        "DENOMINACIÓN",
        "FECHA DESDE",
        "FECHA HASTA",
    ]
    if any(k in up for k in hit_keywords):
        return True
    labels = { (row[0] or "").strip().upper() for row in (grid or []) if row }
    if {"TIPO Y NRO. DE CUENTA", "DENOMINACIÓN"} & labels:
        return True
    return False

def header_looks_like_pilaga(header_excerpt: str | None, grid: list[list[str]]) -> bool:
    text = (header_excerpt or "").upper()
    if not text:
        return True
    if header_has_bank_extract_fields(header_excerpt, grid):
        return False
    for row in (grid or []):
        line = " ".join([c for c in row if c]).upper()
        if RE_PILAGA_ACCOUNT.search(line) and "CC $" not in line and "TIPO Y NRO" not in line:
            return True
    return False

def columns_look_like_bank(cols: list[str]) -> bool:
    up = [c.strip().upper() for c in (cols or [])]
    hints_any = any(h in upj for upj in up for h in ("FECHA", "DESCRIPCIÓN", "CONCEPTO", "DETALLE"))
    money_any = any(h in upj for upj in up for h in ("DEBE", "HABER", "DÉBITO", "CRÉDITO", "IMPORTE", "MONTO"))
    saldo_any = any("SALDO" in upj for upj in up)
    return (hints_any and (money_any or saldo_any))

def decide_kind(header_excerpt: str | None, grid: list[list[str]], cols: list[str]) -> str:
    if header_has_bank_extract_fields(header_excerpt, grid) or columns_look_like_bank(cols):
        return "bank_movements"
    if header_looks_like_pilaga(header_excerpt, grid):
        return "gl"
    return "unknown"

# ===== Header parsing & helpers =====
def read_excel_header_grid(path: Path, max_rows: int = 20, max_cols: int = 12) -> list[list[str]]:
    if not load_workbook:
        return []
    try:
        wb = load_workbook(filename=str(path), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        grid: list[list[str]] = []
        for r in ws.iter_rows(min_row=1, max_row=max_rows, min_col=1, max_col=max_cols, values_only=True):
            row = [(str(c).strip() if c not in (None, "") else "") for c in r]
            grid.append(row)
        wb.close()
        return grid
    except Exception:
        return []

def header_lines_from_grid(grid: list[list[str]], limit: int = 8) -> list[str]:
    lines: list[str] = []
    for r in grid[:limit]:
        line = " ".join([c for c in r if c])
        if not line:
            continue
        if looks_like_table_header(line):
            break
        lines.append(line)
        if len(lines) >= 3:
            break
    return lines

def compact_header(lines: list[str]) -> list[str]:
    out: list[str] = []
    for ln in lines:
        if looks_like_table_header(ln):
            continue
        if len(ln) > 120:
            continue
        out.append(ln)
        if len(out) >= 3:
            break
    return out or (lines[:1] if lines else [])

def looks_like_table_header(line: str) -> bool:
    up = line.upper()
    if any(k in up for k in TABLE_HEADER_HINTS):
        return True
    if len([w for w in up.split() if w]) >= 10:
        return True
    return False

def header_find_value(grid: list[list[str]], label: str) -> Optional[str]:
    lab = label.lower()
    for row in grid:
        if not row:
            continue
        if (row[0] or "").strip().lower() == lab:
            for cell in row[1:]:
                if cell:
                    return cell
            return ""
    return None

def header_extract_account(grid: list[list[str]]) -> Optional[str]:
    line = header_find_value(grid, "Tipo y Nro. de Cuenta")
    if line:
        m = RE_ACCOUNT_ON_LINE.search(f"Tipo y Nro. de Cuenta {line}")
        if m:
            return m.group(1).strip()
        return line.strip()
    text = "\n".join([" ".join([c for c in r if c]) for r in grid[:8]])
    m2 = RE_ACCOUNT_ON_LINE.search(text)
    return m2.group(1).strip() if m2 else None

def pilaga_extract_account(grid: list[list[str]]) -> Optional[str]:
    for row in (grid or []):
        line = " ".join([c for c in row if c])
        m = RE_PILAGA_ACCOUNT.search(line)
        if m:
            return m.group(1)
    return None

def header_extract_period(grid: list[list[str]]) -> tuple[Optional[str], Optional[str]]:
    from_val = header_find_value(grid, "Fecha desde")
    to_val   = header_find_value(grid, "Fecha hasta")
    return parse_dmy(from_val), parse_dmy(to_val)

# ===== Limpieza y parse de fechas =====
def clean_date_text(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = s.replace("\ufeff", "").replace("\xa0", " ").strip()
    s = re.sub(r"^[^\d]+", "", s)  # quita prefijos no numéricos, ej. '01/08/2025
    return s or None

def parse_dmy(s: Optional[str]) -> Optional[str]:
    s = clean_date_text(s)
    if not s:
        return None
    m = RE_PERIOD.search(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        try:
            d = date(int(yyyy), int(mm), int(dd))
            return d.isoformat()
        except Exception:
            pass
    try:
        if pd is not None:
            d = pd.to_datetime(s, dayfirst=True, errors="coerce")
            if pd.notna(d):
                if hasattr(d, "iloc"):
                    d = d.iloc[0]
                return d.date().isoformat()
    except Exception:
        pass
    return None

# ===== Detección prioritaria por columna "Fecha" (PILAGA) =====
def fecha_column_range(path: Path, header_keyword: str = "Fecha") -> tuple[Optional[str], Optional[str]]:
    """Busca una columna cuyo encabezado contenga 'Fecha' y devuelve min/max ISO.
       Ignora filas con 'Saldo inicial/final'. Limpia apóstrofos u otros prefijos."""
    if not load_workbook:
        return None, None
    try:
        wb = load_workbook(filename=str(path), read_only=True, data_only=True)
        ws = wb.worksheets[0]

        header_row_idx = -1
        fecha_col_idx = -1

        # 1) localizar encabezado 'Fecha' (limitar búsqueda a primeras 30 filas)
        for r in range(1, min(30, ws.max_row + 1)):
            found = False
            for c in range(1, ws.max_column + 1):
                v = ws.cell(row=r, column=c).value
                if v and header_keyword.lower() in str(v).lower():
                    header_row_idx = r
                    fecha_col_idx = c
                    found = True
                    break
            if found:
                break

        if header_row_idx == -1 or fecha_col_idx == -1:
            wb.close()
            return None, None

        dmin: Optional[date] = None
        dmax: Optional[date] = None

        # 2) recorrer columna desde la fila siguiente al encabezado
        empty_rows_in_a_row = 0
        for rr in range(header_row_idx + 1, ws.max_row + 1):
            # Ignorar filas “saldo inicial/final”
            row_text = " ".join([str(x) for x in (cell.value for cell in ws[rr]) if x]).upper()
            if any(h in row_text for h in EXCLUDE_TEXT_HINTS):
                continue

            cell_val = ws.cell(row=rr, column=fecha_col_idx).value
            dt = _as_date(cell_val)
            if dt:
                dmin = dt if (dmin is None or dt < dmin) else dmin
                dmax = dt if (dmax is None or dt > dmax) else dmax
                empty_rows_in_a_row = 0  # Reset counter on valid date
            elif not cell_val:
                empty_rows_in_a_row += 1

            # Si encontramos 20 filas vacías seguidas, asumimos fin de tabla
            if empty_rows_in_a_row >= 20:
                break

        wb.close()
        return (dmin.isoformat() if dmin else None, dmax.isoformat() if dmax else None)
    except Exception:
        return None, None



def _as_date(val: Any) -> Optional[date]:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, (int, float)):
        # Posible serial de Excel: evitar confundir importes (descartar floats no enteros y rangos irreales)
        if isinstance(val, float) and not float(val).is_integer():
            return None
        # Rango típico de serial date Excel (~40000 ≈ 2009-10-16)
        if 20000 <= int(val) <= 80000:
            # Excel base 1899-12-30
            base = datetime(1899, 12, 30)
            return (base + timedelta(days=int(val))).date()
        return None
    if val not in (None, ""):
        iso = parse_dmy(str(val))
        if iso:
            return datetime.fromisoformat(iso).date()
    return None

# ===== Table preview (xlsx/csv) =====
def read_table_preview(path: Path) -> tuple[list[str], list[list[Any]], Optional[str], Optional[str]]:
    if pd is None:
        return [], [], None, None
    try:
        df = pd.read_excel(str(path), engine="openpyxl", nrows=120)
        cols = [str(c) for c in df.columns.tolist()]
        sample = df.head(10).fillna("").astype(object).values.tolist()
        min_d, max_d = try_parse_dates_in_df(df)
        return cols, sample, min_d, max_d
    except Exception:
        return [], [], None, None

def try_parse_dates_in_df(df) -> tuple[Optional[str], Optional[str]]:
    if df is None or df.empty:
        return None, None
    date_col = None
    for c in df.columns:
        s = df[c]
        if str(s.dtype).startswith("datetime"):
            date_col = c; break
        if s.dtype == "object" and pd is not None:
            try:
                # Convertir toda la columna usando la lógica robusta de _as_date
                parsed = s.map(_as_date)
                if parsed.notna().sum() >= max(3, int(len(parsed) * 0.1)):
                    df[c] = pd.to_datetime(parsed, errors="coerce")
                    date_col = c
                    break
            except Exception:
                pass
    if not date_col:
        return None, None
    try:
        s = pd.to_datetime(df[date_col], errors="coerce").dropna()
        if s.empty:
            return None, None
        return s.min().date().isoformat(), s.max().date().isoformat()
    except Exception:
        return None, None

# ===== CSV =====
def sniff_csv(path: Path) -> dict:
    cols, rows, min_date, max_date = read_csv_preview(path)
    out = {
        "kind": "csv",
        "detected": {"bank": None, "account_core_dv": None, "period_from": min_date, "period_to": max_date},
        "table": {"columns": cols, "sample": rows},
        "suggest": {"period_from": min_date, "period_to": max_date},
        "needs": {"bank": True, "account_id": False, "period_range": not (min_date and max_date)},
    }
    return out

def read_csv_preview(path: Path) -> tuple[list[str], list[list[Any]], Optional[str], Optional[str]]:
    if pd is None:
        return [], [], None, None
    try:
        df = pd.read_csv(str(path), nrows=120, sep=None, engine="python")
        cols = [str(c) for c in df.columns.tolist()]
        sample = df.head(10).fillna("").astype(object).values.tolist()
        min_d, max_d = try_parse_dates_in_df(df)
        return cols, sample, min_d, max_d
    except Exception:
        return [], [], None, None

# ===== Mapeo short → full =====
def map_short_account_to_full(short_code: str) -> Optional[str]:
    short_digits = re.sub(r"\D+", "", short_code or "")  # '26005/5' → '260055'
    if not short_digits:
        return None
    candidates: list[str] = []
    for full in ACCOUNT_MAP.keys():
        full_digits = re.sub(r"\D+", "", full)           # '3-111-0100026005-5' → '311101000260055'
        if full_digits.endswith(short_digits) or short_digits in full_digits[-12:]:
            candidates.append(full)
    if len(candidates) == 1:
        return candidates[0]
    return None


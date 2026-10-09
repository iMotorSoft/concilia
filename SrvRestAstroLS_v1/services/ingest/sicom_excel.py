from __future__ import annotations

import math
import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd


_MONEY_ALLOWED = re.compile(r"[^\d,\.\-\(\)]")

_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "fecha_pago": ("fecha de pago", "fecha pago", "fecha"),
    "order_de_p": ("order de p", "order de p.", "op", "o/p"),
    "nro_pago": ("nro pago", "nro. pago", "n pago", "n de pago", "numero de pago", "nº pago"),
    "banco_raw": ("banco",),
    "importe": ("importe",),
    "imp_neto": ("imp neto", "imp. neto", "importe neto", "neto"),
    "organismo": ("organismo",),
    "convenio": ("convenio",),
    "medio_pago": ("medio pago", "medio de pago"),
}

_REQUIRED_CANONICAL = {"fecha_pago", "order_de_p", "nro_pago", "banco_raw"}
_OPTIONAL_CANONICAL = {"importe", "imp_neto", "organismo", "convenio", "medio_pago"}


def _normalize_label(value: Any) -> str:
    txt = str(value or "").strip().lower()
    if not txt:
        return ""
    txt = txt.replace("nº", "nro").replace("n°", "nro").replace("num.", "numero ").replace("num ", "numero ")
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = txt.replace("nro.", "nro ").replace("n.", "n ")
    txt = txt.replace("º", "o").replace("°", "o")
    txt = re.sub(r"[^a-z0-9]+", " ", txt)
    return " ".join(txt.split())


def _normalize_id(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if value.is_integer():
            return str(int(value))
    if isinstance(value, int):
        return str(value)
    txt = str(value).strip()
    if not txt:
        return ""
    if txt.endswith(".0"):
        try:
            return str(int(float(txt)))
        except Exception:
            return txt
    return txt


def _parse_money_value(raw: Any) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and math.isnan(raw):
            return 0.0
        return float(raw)

    txt = str(raw).strip()
    if not txt:
        return 0.0

    neg = False
    if "(" in txt and ")" in txt:
        neg = True

    txt = _MONEY_ALLOWED.sub("", txt)
    txt = txt.replace("(", "").replace(")", "")
    if not txt:
        return 0.0

    if txt.startswith("-"):
        neg = True
        txt = txt[1:]
    txt = txt.replace("-", "")

    last_dot = txt.rfind(".")
    last_comma = txt.rfind(",")
    if last_dot != -1 and last_comma != -1:
        if last_comma > last_dot:
            txt = txt.replace(".", "").replace(",", ".")
        else:
            txt = txt.replace(",", "")
    elif last_comma != -1:
        txt = txt.replace(".", "").replace(",", ".")
    else:
        txt = txt.replace(",", "")

    try:
        val = float(txt) if txt else 0.0
    except ValueError:
        val = 0.0
    return -abs(val) if neg else val


def _clean_money_series(series: pd.Series) -> pd.Series:
    return series.apply(_parse_money_value).fillna(0.0)


def _bank_scope(bank_raw: str) -> str:
    norm = _normalize_label(bank_raw)
    if not norm:
        return ""
    return norm.replace(" ", "_")


def _canonical_header(cell_value: Any) -> str | None:
    norm = _normalize_label(cell_value)
    if not norm:
        return None
    for canonical, aliases in _HEADER_ALIASES.items():
        if norm in aliases:
            return canonical
    for canonical, aliases in _HEADER_ALIASES.items():
        if any(alias in norm for alias in aliases):
            return canonical
    return None


def _detect_header_row(raw: pd.DataFrame, max_rows: int = 20) -> tuple[int | None, dict[str, int]]:
    best_idx: int | None = None
    best_map: dict[str, int] = {}
    best_score = -1

    for idx in range(min(len(raw), max_rows)):
        row = raw.iloc[idx].tolist()
        mapped: dict[str, int] = {}
        for col_idx, value in enumerate(row):
            canonical = _canonical_header(value)
            if canonical and canonical not in mapped:
                mapped[canonical] = col_idx
        required_hits = len(_REQUIRED_CANONICAL.intersection(mapped.keys()))
        score = required_hits * 10 + len(mapped)
        if required_hits >= 3 and score > best_score:
            best_idx = idx
            best_map = mapped
            best_score = score

    return best_idx, best_map


def _unique_columns(values: list[Any]) -> list[str]:
    columns: list[str] = []
    seen: dict[str, int] = {}
    for idx, value in enumerate(values):
        base = _canonical_header(value) or f"col_{idx}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        columns.append(base if count == 0 else f"{base}_{count + 1}")
    return columns


def _coerce_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, dayfirst=True, errors="coerce")


def _parse_sheet(raw: pd.DataFrame, *, sheet_name: str, source_file_name: str) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    header_idx, header_map = _detect_header_row(raw)
    if header_idx is None:
        return None, {
            "sheet_name": sheet_name,
            "rows": 0,
            "required_columns_ok": False,
            "missing_columns": sorted(_REQUIRED_CANONICAL),
        }

    df = raw.iloc[header_idx + 1 :].copy()
    df.columns = _unique_columns(raw.iloc[header_idx].tolist())
    df = df.dropna(axis=1, how="all")
    df = df.dropna(axis=0, how="all")

    available = {col.split("_", 1)[0] if col.startswith("col_") else col for col in df.columns}
    missing = sorted(col for col in _REQUIRED_CANONICAL if col not in available and col not in df.columns)
    if missing:
        return None, {
            "sheet_name": sheet_name,
            "rows": 0,
            "required_columns_ok": False,
            "missing_columns": missing,
        }

    canon = pd.DataFrame({
        "fecha_pago": _coerce_date(df["fecha_pago"]),
        "order_de_p": df["order_de_p"].apply(_normalize_id),
        "nro_pago": df["nro_pago"].apply(_normalize_id),
        "banco_raw": df["banco_raw"].fillna("").astype(str).str.strip(),
        "importe": _clean_money_series(df["importe"]) if "importe" in df.columns else pd.Series([0.0] * len(df)),
        "imp_neto": _clean_money_series(df["imp_neto"]) if "imp_neto" in df.columns else (
            _clean_money_series(df["importe"]) if "importe" in df.columns else pd.Series([0.0] * len(df))
        ),
        "organismo": df["organismo"].fillna("").astype(str).str.strip() if "organismo" in df.columns else "",
        "convenio": df["convenio"].fillna("").astype(str).str.strip() if "convenio" in df.columns else "",
        "medio_pago": df["medio_pago"].fillna("").astype(str).str.strip() if "medio_pago" in df.columns else "",
    })
    canon["sheet_name"] = sheet_name
    canon["source_file_name"] = source_file_name
    canon["bank_scope"] = canon["banco_raw"].apply(_bank_scope)
    canon["op_key"] = canon["order_de_p"]
    canon["lote_key"] = canon.apply(
        lambda row: "|".join([
            row["fecha_pago"].date().isoformat() if pd.notna(row["fecha_pago"]) else "",
            row["bank_scope"],
            row["nro_pago"],
        ]),
        axis=1,
    )
    canon["op_lote_key"] = canon.apply(
        lambda row: "|".join([
            row["fecha_pago"].date().isoformat() if pd.notna(row["fecha_pago"]) else "",
            row["order_de_p"],
            row["bank_scope"],
            row["nro_pago"],
        ]),
        axis=1,
    )

    canon = canon[
        (canon["fecha_pago"].notna()) |
        (canon["order_de_p"] != "") |
        (canon["nro_pago"] != "") |
        (canon["banco_raw"] != "")
    ].copy()

    return canon.reset_index(drop=True), {
        "sheet_name": sheet_name,
        "rows": int(len(canon)),
        "required_columns_ok": True,
        "missing_columns": [],
    }


def _parse_workbook(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    if path.suffix.lower() not in {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}:
        raise ValueError("SICOM espera un workbook Excel (.xlsx/.xls).")

    xls = pd.ExcelFile(str(path))
    frames: list[pd.DataFrame] = []
    sheet_summaries: list[dict[str, Any]] = []
    invalid_sheets: list[dict[str, Any]] = []

    for sheet_name in xls.sheet_names:
        raw = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        frame, summary = _parse_sheet(raw, sheet_name=sheet_name, source_file_name=path.name)
        if frame is None:
            invalid_sheets.append(summary)
            continue
        if len(frame) == 0:
            continue
        frames.append(frame)
        sheet_summaries.append(summary)

    if not frames:
        raise ValueError("No se detectaron solapas SICOM con columnas requeridas.")

    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values(["fecha_pago", "sheet_name", "order_de_p", "nro_pago"], kind="stable").reset_index(drop=True)

    return df, {
        "sheet_count": len(sheet_summaries),
        "sheet_names": [item["sheet_name"] for item in sheet_summaries],
        "sheet_summaries": sheet_summaries,
        "invalid_sheets": invalid_sheets,
    }


def load_sicom_workbook(path: Path) -> pd.DataFrame:
    df, _meta = _parse_workbook(path)
    return df


def inspect_sicom_workbook(path: Path) -> dict[str, Any]:
    df, meta = _parse_workbook(path)

    rel = df.loc[(df["order_de_p"] != "") & (df["nro_pago"] != ""), ["order_de_p", "nro_pago"]].drop_duplicates()
    op_multi = int((rel.groupby("order_de_p")["nro_pago"].nunique() > 1).sum()) if len(rel) else 0
    nro_multi = int((rel.groupby("nro_pago")["order_de_p"].nunique() > 1).sum()) if len(rel) else 0

    bank_summary = (
        df.groupby("banco_raw", dropna=False)
        .agg(rows=("banco_raw", "size"), imp_neto_total=("imp_neto", "sum"))
        .reset_index()
        .sort_values(["rows", "banco_raw"], ascending=[False, True], kind="stable")
    )

    return {
        "kind": "sicom",
        "validation": {
            "is_valid": True,
            "errors": [],
            "warnings": [] if not meta["invalid_sheets"] else [
                f"Se ignoraron {len(meta['invalid_sheets'])} solapa(s) sin columnas SICOM requeridas."
            ],
        },
        "preview": {
            "rows": int(len(df)),
            "sheet_count": int(meta["sheet_count"]),
            "sheet_names": list(meta["sheet_names"]),
            "period_from": df["fecha_pago"].min().date().isoformat() if len(df) and pd.notna(df["fecha_pago"].min()) else None,
            "period_to": df["fecha_pago"].max().date().isoformat() if len(df) and pd.notna(df["fecha_pago"].max()) else None,
            "required_columns_ok": True,
            "banks": [
                {
                    "bank_raw": row["banco_raw"],
                    "rows": int(row["rows"]),
                    "imp_neto_total": float(row["imp_neto_total"] or 0.0),
                }
                for _, row in bank_summary.iterrows()
            ],
            "bank_names_available": [str(v) for v in bank_summary["banco_raw"].tolist() if str(v).strip()],
            "bank_count": int(bank_summary["banco_raw"].astype(str).str.strip().replace("", pd.NA).dropna().nunique()),
            "op_count": int(df.loc[df["order_de_p"] != "", "order_de_p"].nunique()),
            "nro_pago_count": int(df.loc[df["nro_pago"] != "", "nro_pago"].nunique()),
            "relation_summary": {
                "op_multi_nro_pago_count": op_multi,
                "nro_pago_multi_op_count": nro_multi,
            },
            "invalid_sheets": meta["invalid_sheets"],
        },
    }

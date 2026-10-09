# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/routes/v1/reconcile_start.py

from __future__ import annotations

import asyncio
import logging
import math
import re
import time
import traceback
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional, Tuple
from uuid import uuid4

from litestar import post
from litestar.response import Response

import pandas as pd
from openpyxl import load_workbook

from .agui_notify import emit
from services.ingest.sniff_bank import sniff_file
from services.ingest.sicom_excel import load_sicom_workbook
from urllib.parse import urlparse

try:
    import polars as pl  # type: ignore
except Exception:  # pragma: no cover
    pl = None

logger = logging.getLogger(__name__)
_OP_KEY_RE = re.compile(r"(\d+/\d{4})", re.IGNORECASE)
_OP_MATCH_KEY_RE = re.compile(r"(\d+)(?:/\d{2,4})?", re.IGNORECASE)

_CASE_BANK_ALIASES = {
    "patagonia": "patagonia",
    "banco_patagonia": "patagonia",
    "patagonia_otros": "patagonia_otros",
    "banco_pat_otros": "patagonia_otros",
    "santander": "santander",
    "banco_santander": "santander",
    "santander_otros": "santander_otros",
    "banco_sant_otros": "santander_otros",
    "ciudad": "ciudad",
    "banco_ciudad": "ciudad",
}

_CASE_BANK_TO_SICOM = {
    "patagonia": {"banco_patagonia", "banco_pat_otros"},
    "patagonia_otros": {"banco_pat_otros"},
    "santander": {"banco_santander"},
    "santander_otros": {"banco_sant_otros"},
    "ciudad": {"banco_ciudad"},
}

# =========================
# Helpers (IO) + cache
# =========================

# Cache simple en memoria para evitar reparsear el mismo XLSX en la misma serie de request.
_DF_CACHE: dict[tuple, pd.DataFrame] = {}

def _preferred_engine() -> str:
    """Devuelve 'pyarrow' si está disponible (más rápido), si no openpyxl."""
    try:
        import pyarrow  # noqa: F401
        return "pyarrow"
    except Exception:
        return "openpyxl"


def _df_cache_key(kind: str, path: Path) -> tuple:
    st = path.stat()
    return (kind, str(path.resolve()), st.st_mtime_ns, st.st_size)


def _from_file_uri(uri: str) -> Path:
    """
    Convierte file://... en Path usable.
    Permite también rutas planas por compat.
    """
    if uri and uri.startswith("file://"):
        return Path(urlparse(uri).path)
    return Path(uri)


# =========================
# Loaders estandarizados
# =========================
_MONEY_ALLOWED = re.compile(r"[^\d,\.\-\(\)]")


def _parse_money_value(raw: str) -> float:
    """
    Normaliza importes con formatos mixtos:
      - 1.234,56  -> decimal coma
      - 1,234.56  -> decimal punto
      - 1234,56   -> decimal coma
      - 1234.56   -> decimal punto
    También respeta paréntesis como negativo y quita símbolos extra.
    """
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

    if neg:
        val = -abs(val)
    return val


def _clean_money(s: pd.Series) -> pd.Series:
    """Normaliza importes mezclando formatos AR/intl."""
    out = s.apply(_parse_money_value)
    return out.fillna(0.0)


def _load_pilaga(path: Path) -> pd.DataFrame:
    """
    Lee PILAGA (hojas típicas: “Resumen cuenta bancaria” o “Resumen cuenta tesorería”, si no la primera).
    Busca la fila de cabecera por la palabra “Fecha” y columnas Ingresos/Egresos/Acumulado.
    Devuelve DF estandarizado:
      ['fecha','monto','documento','ingreso_bruto','egreso_bruto','origen']
    """
    cache_key = _df_cache_key("pilaga", path)
    if cache_key in _DF_CACHE:
        return _DF_CACHE[cache_key].copy()

    if path.suffix.lower() in {".parquet", ".pq"}:
        if pl is not None:
            df = pl.read_parquet(str(path)).to_pandas()
        else:
            df = pd.read_parquet(str(path))
        if "fecha" in df.columns:
            df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        _DF_CACHE[cache_key] = df.copy()
        return df

    engine = _preferred_engine()
    try:
        xls = pd.ExcelFile(str(path), engine=engine)
    except Exception:
        xls = pd.ExcelFile(str(path), engine="openpyxl")

    # Elegir hoja contable conocida
    sheet = next(
        (
            n for n in xls.sheet_names
            if "resumen cuenta bancaria" in str(n).strip().lower()
            or "resumen cuenta tesorer" in str(n).strip().lower()
        ),
        xls.sheet_names[0],
    )

    # Leemos sin header para poder detectar la fila con "Fecha"
    raw = pd.read_excel(xls, sheet_name=sheet, header=None)

    header_idx = None
    header_row = None
    for idx in range(min(len(raw), 40)):  # primeras filas
        row_vals = raw.iloc[idx].tolist()
        norm = [str(c).strip().upper() for c in row_vals if not (pd.isna(c) or str(c).strip() == "")]
        if any("FECHA" in c for c in norm) and (any("INGRES" in c for c in norm) or any("EGRES" in c for c in norm) or any("ACUM" in c for c in norm)):
            header_idx = idx
            header_row = row_vals
            break

    if header_idx is None:
        # fallback: primera fila como header
        header_idx = 0
        header_row = raw.iloc[0].tolist()

    def _clean_col_name(val, idx) -> str:
        if pd.isna(val):
            return f"col_{idx}"
        s = str(val).strip()
        return s if s else f"col_{idx}"

    columns = [_clean_col_name(c, i) for i, c in enumerate(header_row)]
    df = raw.iloc[header_idx + 1 :].copy()
    df.columns = columns

    # Quitar columnas completamente vacías
    df = df.dropna(axis=1, how="all")

    # Localizar columnas clave
    def _find_col(substrs):
        subs = [s.lower() for s in substrs]
        for c in df.columns:
            low = str(c).lower()
            if any(s in low for s in subs):
                return c
        return None

    fecha_col = _find_col(["fecha"])
    doc_col   = _find_col(["doc", "detalle"]) or (df.columns[1] if len(df.columns) > 1 else df.columns[0])
    ing_col   = _find_col(["ingres"])
    egr_col   = _find_col(["egres"])
    acu_col   = _find_col(["acum"])

    ingreso = _clean_money(df[ing_col]) if ing_col else pd.Series([0.0] * len(df))
    egreso  = _clean_money(df[egr_col]) if egr_col else pd.Series([0.0] * len(df))

    fechas = pd.to_datetime(df[fecha_col], dayfirst=True, errors="coerce") if fecha_col else pd.to_datetime([], errors="coerce")
    monto = ingreso - egreso

    out = pd.DataFrame({
        "fecha": fechas,
        "monto": monto,
        "documento": df[doc_col].astype(str) if doc_col in df else "",
        "ingreso_bruto": ingreso,
        "egreso_bruto": egreso,
    })

    out = out.dropna(subset=["fecha"])
    out = out[out["monto"].notna()]
    out = out[out["monto"] != 0]
    out = out.loc[:, ["fecha", "monto", "documento", "ingreso_bruto", "egreso_bruto"]].copy()
    out["origen"] = "PILAGA"
    out = out.reset_index(drop=True)
    _DF_CACHE[cache_key] = out.copy()
    return out


def _load_sicom(path: Path) -> pd.DataFrame:
    """
    Lee un workbook mensual SICOM y consolida todas las solapas válidas en un único DF.
    Devuelve un dataset canónico orientado a trazabilidad operativa y lotes bancarios.
    """
    cache_key = _df_cache_key("sicom", path)
    if cache_key in _DF_CACHE:
        return _DF_CACHE[cache_key].copy()

    if path.suffix.lower() in {".parquet", ".pq"}:
        if pl is not None:
            df = pl.read_parquet(str(path)).to_pandas()
        else:
            df = pd.read_parquet(str(path))
        if "fecha_pago" in df.columns:
            df["fecha_pago"] = pd.to_datetime(df["fecha_pago"], errors="coerce")
        _DF_CACHE[cache_key] = df.copy()
        return df

    out = load_sicom_workbook(path)
    _DF_CACHE[cache_key] = out.copy()
    return out


def _normalize_case_bank(value: Any) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_")
    return _CASE_BANK_ALIASES.get(raw, raw)


def _normalize_account_scope(value: Any) -> str:
    txt = str(value or "").strip().upper()
    if not txt:
        return ""
    txt = re.sub(r"^(CC\s*\$|C/C|CTA\.?\s*CTE\.?|CUENTA\s*CORRIENTE)\s*", "", txt).strip()
    digits = "".join(ch for ch in txt if ch.isdigit())
    return digits or txt


def _extract_op_key(value: Any) -> str:
    txt = str(value or "").strip().upper()
    if not txt:
        return ""
    match = _OP_KEY_RE.search(txt)
    return match.group(1) if match else ""


def _extract_op_match_key(value: Any) -> str:
    txt = str(value or "").strip().upper()
    if not txt:
        return ""
    match = _OP_MATCH_KEY_RE.search(txt)
    return match.group(1) if match else ""


def _resolve_sicom_bank_scopes(case_bank: str) -> set[str]:
    normalized = _normalize_case_bank(case_bank)
    if normalized in _CASE_BANK_TO_SICOM:
        return set(_CASE_BANK_TO_SICOM[normalized])
    if normalized.startswith("banco_"):
        return {normalized}
    return set()


def _safe_pct(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 2)


def _resolve_case_scope(
    path_extracto: Path,
    *,
    bank_scope: str = "",
    account_scope: str = "",
) -> dict[str, Any]:
    requested_bank = _normalize_case_bank(bank_scope)
    requested_account_raw = str(account_scope or "").strip()

    detected_bank = ""
    detected_account_raw = ""
    sniff_source = "none"

    if path_extracto.suffix.lower() in {".xlsx", ".xls", ".xlsm", ".xltx", ".xltm"}:
        sniffed = sniff_file(path_extracto)
        detected = sniffed.get("detected") or {}
        detected_bank = _normalize_case_bank(detected.get("bank"))
        detected_account_raw = (
            str(detected.get("account_full") or "").strip()
            or str(detected.get("account_core_dv") or "").strip()
        )
        if detected_bank or detected_account_raw:
            sniff_source = "extracto"

    final_bank = requested_bank or detected_bank
    final_account_raw = requested_account_raw or detected_account_raw

    return {
        "bank_scope": final_bank,
        "account_scope_raw": final_account_raw,
        "account_scope": _normalize_account_scope(final_account_raw),
        "detected_bank_scope": detected_bank,
        "detected_account_scope_raw": detected_account_raw,
        "sicom_bank_scopes": sorted(_resolve_sicom_bank_scopes(final_bank)),
        "bank_scope_source": "explicit" if requested_bank else sniff_source,
        "account_scope_source": "explicit" if requested_account_raw else sniff_source,
    }


def _greedy_match_by_date_and_abs_amount(
    df_left: pd.DataFrame,
    *,
    left_date_col: str,
    left_amount_col: str,
    df_right: pd.DataFrame,
    right_date_col: str,
    right_amount_col: str,
) -> pd.DataFrame:
    left = df_left.reset_index(drop=True).copy()
    right = df_right.reset_index(drop=True).copy()
    if left.empty or right.empty:
        return pd.DataFrame()

    left["_match_left_id"] = range(len(left))
    right["_match_right_id"] = range(len(right))
    left["_match_date"] = pd.to_datetime(left[left_date_col], errors="coerce").dt.normalize()
    right["_match_date"] = pd.to_datetime(right[right_date_col], errors="coerce").dt.normalize()
    left["_amount_abs_r"] = pd.to_numeric(left[left_amount_col], errors="coerce").fillna(0.0).abs().round(2)
    right["_amount_abs_r"] = pd.to_numeric(right[right_amount_col], errors="coerce").fillna(0.0).abs().round(2)

    merged = left.merge(right, on=["_match_date", "_amount_abs_r"], suffixes=("_left", "_right"))
    merged = merged.sort_values(["_match_date", "_amount_abs_r", "_match_left_id", "_match_right_id"], kind="stable")

    used_left: set[int] = set()
    used_right: set[int] = set()
    selected_rows: list[dict[str, Any]] = []
    for record in merged.to_dict("records"):
        left_id = int(record["_match_left_id"])
        right_id = int(record["_match_right_id"])
        if left_id in used_left or right_id in used_right:
            continue
        used_left.add(left_id)
        used_right.add(right_id)
        selected_rows.append(record)

    return pd.DataFrame(selected_rows, columns=merged.columns) if selected_rows else merged.iloc[0:0].copy()


def _greedy_match_pilaga_ops_with_sicom(df_pilaga: pd.DataFrame, df_sicom: pd.DataFrame) -> pd.DataFrame:
    if df_pilaga.empty or df_sicom.empty:
        return pd.DataFrame()

    pilaga = df_pilaga.copy()
    pilaga["op_key"] = pilaga["documento"].apply(_extract_op_match_key)
    pilaga = pilaga[pilaga["op_key"] != ""].copy()
    if pilaga.empty:
        return pd.DataFrame()

    pilaga["_match_p_id"] = range(len(pilaga))
    pilaga["_amount_abs_r"] = pd.to_numeric(pilaga["monto"], errors="coerce").fillna(0.0).abs().round(2)
    pilaga["fecha"] = pd.to_datetime(pilaga["fecha"], errors="coerce")

    sicom = df_sicom.copy()
    sicom["op_key"] = sicom["order_de_p"].apply(_extract_op_match_key)
    sicom = sicom[sicom["op_key"] != ""].copy()
    if sicom.empty:
        return pd.DataFrame()

    sicom["_match_s_id"] = range(len(sicom))
    sicom["_amount_abs_r"] = pd.to_numeric(sicom["imp_neto"], errors="coerce").fillna(0.0).abs().round(2)
    sicom["fecha_pago"] = pd.to_datetime(sicom["fecha_pago"], errors="coerce")

    merged = pilaga.merge(
        sicom,
        left_on=["op_key", "_amount_abs_r"],
        right_on=["op_key", "_amount_abs_r"],
        suffixes=("_pilaga", "_sicom"),
    )
    if merged.empty:
        return merged

    merged["lag_days"] = (merged["fecha"] - merged["fecha_pago"]).abs().dt.days
    merged = merged.sort_values(
        ["_match_p_id", "lag_days", "_match_s_id"],
        ascending=[True, True, True],
        kind="stable",
    )

    used_p: set[int] = set()
    used_s: set[int] = set()
    selected_rows: list[dict[str, Any]] = []
    for record in merged.to_dict("records"):
        pilaga_id = int(record["_match_p_id"])
        sicom_id = int(record["_match_s_id"])
        if pilaga_id in used_p or sicom_id in used_s:
            continue
        used_p.add(pilaga_id)
        used_s.add(sicom_id)
        selected_rows.append(record)

    return pd.DataFrame(selected_rows, columns=merged.columns) if selected_rows else merged.iloc[0:0].copy()


def _lote_key_from_columns(fecha_value: Any, bank_scope: Any, nro_pago: Any) -> str:
    fecha = pd.to_datetime(fecha_value, errors="coerce")
    fecha_iso = fecha.date().isoformat() if pd.notna(fecha) else ""
    return "|".join([fecha_iso, str(bank_scope or "").strip(), str(nro_pago or "").strip()])


def _build_sicom_insights(
    df_sicom: pd.DataFrame,
    df_pilaga: pd.DataFrame,
    df_banco: pd.DataFrame,
    *,
    bank_scope: str = "",
    account_scope: str = "",
    path_extracto: Optional[Path] = None,
) -> dict[str, Any]:
    if df_sicom is None or df_sicom.empty:
        return {"used": False}

    case_scope = _resolve_case_scope(
        path_extracto or Path(""),
        bank_scope=bank_scope,
        account_scope=account_scope,
    ) if path_extracto is not None else {
        "bank_scope": _normalize_case_bank(bank_scope),
        "account_scope_raw": str(account_scope or "").strip(),
        "account_scope": _normalize_account_scope(account_scope),
        "detected_bank_scope": "",
        "detected_account_scope_raw": "",
        "sicom_bank_scopes": sorted(_resolve_sicom_bank_scopes(bank_scope)),
        "bank_scope_source": "explicit" if bank_scope else "none",
        "account_scope_source": "explicit" if account_scope else "none",
    }

    sicom_bank_scopes = set(case_scope.get("sicom_bank_scopes") or [])
    if sicom_bank_scopes:
        scoped = df_sicom[df_sicom["bank_scope"].isin(sicom_bank_scopes)].copy()
    else:
        scoped = df_sicom.copy()

    rel_total = df_sicom.loc[
        (df_sicom["order_de_p"].astype(str).str.strip() != "") &
        (df_sicom["nro_pago"].astype(str).str.strip() != ""),
        ["order_de_p", "nro_pago"],
    ].drop_duplicates()
    rel_scoped = scoped.loc[
        (scoped["order_de_p"].astype(str).str.strip() != "") &
        (scoped["nro_pago"].astype(str).str.strip() != ""),
        ["order_de_p", "nro_pago"],
    ].drop_duplicates()

    lotes = (
        scoped.loc[scoped["nro_pago"].astype(str).str.strip() != ""]
        .groupby(["fecha_pago", "bank_scope", "banco_raw", "nro_pago"], dropna=False)
        .agg(
            imp_neto=("imp_neto", "sum"),
            rows=("nro_pago", "size"),
            op_count=("order_de_p", lambda s: int(s.astype(str).str.strip().replace("", pd.NA).dropna().nunique())),
        )
        .reset_index()
    )
    lotes["lote_key"] = lotes.apply(
        lambda row: _lote_key_from_columns(row["fecha_pago"], row["bank_scope"], row["nro_pago"]),
        axis=1,
    )
    matched_lotes = _greedy_match_by_date_and_abs_amount(
        lotes,
        left_date_col="fecha_pago",
        left_amount_col="imp_neto",
        df_right=df_banco,
        right_date_col="fecha",
        right_amount_col="monto",
    )

    matched_ops = _greedy_match_pilaga_ops_with_sicom(df_pilaga, scoped)
    matched_lote_keys = set(matched_lotes["lote_key"].astype(str)) if ("lote_key" in matched_lotes.columns and not matched_lotes.empty) else set()
    final_ops = matched_ops[matched_ops["lote_key"].astype(str).isin(matched_lote_keys)].copy() if (not matched_ops.empty and matched_lote_keys) else matched_ops.iloc[0:0].copy()
    effective_lote_keys = set(final_ops["lote_key"].astype(str)) if ("lote_key" in final_ops.columns and not final_ops.empty) else set()
    effective_lotes = matched_lotes[matched_lotes["lote_key"].astype(str).isin(effective_lote_keys)].copy() if (not matched_lotes.empty and effective_lote_keys) else matched_lotes.iloc[0:0].copy()

    bank_distribution = []
    if not matched_ops.empty:
        by_bank = (
            matched_ops.groupby("banco_raw", dropna=False)
            .agg(
                count=("banco_raw", "size"),
                amount=("imp_neto", lambda s: float(pd.to_numeric(s, errors="coerce").fillna(0.0).abs().sum())),
            )
            .reset_index()
            .sort_values(["count", "banco_raw"], ascending=[False, True], kind="stable")
        )
        bank_distribution = [
            {
                "bank_raw": str(row["banco_raw"] or ""),
                "count": int(row["count"]),
                "amount": round(float(row["amount"] or 0.0), 2),
            }
            for _, row in by_bank.iterrows()
        ]

    lag_histogram = []
    if not matched_ops.empty:
        lag_counts = (
            matched_ops["lag_days"]
            .fillna(-1)
            .astype(int)
            .value_counts()
            .sort_index()
        )
        lag_histogram = [
            {"days": int(days), "count": int(count)}
            for days, count in lag_counts.items()
            if days >= 0
        ]

    banks_available = sorted({str(v).strip() for v in df_sicom["banco_raw"].astype(str).tolist() if str(v).strip()})
    banks_scoped = sorted({str(v).strip() for v in scoped["banco_raw"].astype(str).tolist() if str(v).strip()})
    matched_lotes_amount = float(pd.to_numeric(matched_lotes.get("imp_neto"), errors="coerce").fillna(0.0).abs().sum()) if not matched_lotes.empty else 0.0
    total_lotes_amount = float(pd.to_numeric(lotes.get("imp_neto"), errors="coerce").fillna(0.0).abs().sum()) if not lotes.empty else 0.0
    matched_ops_amount = float(pd.to_numeric(matched_ops.get("imp_neto"), errors="coerce").fillna(0.0).abs().sum()) if not matched_ops.empty else 0.0
    final_ops_amount = float(pd.to_numeric(final_ops.get("imp_neto"), errors="coerce").fillna(0.0).abs().sum()) if not final_ops.empty else 0.0
    effective_lotes_amount = float(pd.to_numeric(effective_lotes.get("imp_neto"), errors="coerce").fillna(0.0).abs().sum()) if not effective_lotes.empty else 0.0
    matched_ops_key_col = next(
        (col for col in ("op_key", "op_key_pilaga", "op_key_left") if col in matched_ops.columns),
        "",
    )
    final_ops_key_col = next(
        (col for col in ("op_key", "op_key_pilaga", "op_key_left") if col in final_ops.columns),
        "",
    )
    final_banks = []
    if not final_ops.empty:
        final_banks = sorted({str(v).strip() for v in final_ops["banco_raw"].astype(str).tolist() if str(v).strip()})

    return {
        "used": True,
        "scope": {
            "bank_scope": case_scope.get("bank_scope") or None,
            "bank_scope_source": case_scope.get("bank_scope_source"),
            "account_scope_raw": case_scope.get("account_scope_raw") or None,
            "account_scope": case_scope.get("account_scope") or None,
            "account_scope_source": case_scope.get("account_scope_source"),
            "sicom_bank_scopes": list(case_scope.get("sicom_bank_scopes") or []),
            "scope_applied": bool(sicom_bank_scopes),
        },
        "source": {
            "rows_total": int(len(df_sicom)),
            "rows_scoped": int(len(scoped)),
            "rows_excluded": int(len(df_sicom) - len(scoped)),
            "period_from": df_sicom["fecha_pago"].min().date().isoformat() if len(df_sicom) and pd.notna(df_sicom["fecha_pago"].min()) else None,
            "period_to": df_sicom["fecha_pago"].max().date().isoformat() if len(df_sicom) and pd.notna(df_sicom["fecha_pago"].max()) else None,
            "banks_available": banks_available,
            "banks_scoped": banks_scoped,
            "op_count_total": int(df_sicom.loc[df_sicom["order_de_p"].astype(str).str.strip() != "", "order_de_p"].nunique()),
            "op_count_scoped": int(scoped.loc[scoped["order_de_p"].astype(str).str.strip() != "", "order_de_p"].nunique()),
            "nro_pago_count_total": int(df_sicom.loc[df_sicom["nro_pago"].astype(str).str.strip() != "", "nro_pago"].nunique()),
            "nro_pago_count_scoped": int(scoped.loc[scoped["nro_pago"].astype(str).str.strip() != "", "nro_pago"].nunique()),
            "lote_count_scoped": int(len(lotes)),
        },
        "traceability": {
            "op_multi_lote_count_total": int((rel_total.groupby("order_de_p")["nro_pago"].nunique() > 1).sum()) if len(rel_total) else 0,
            "lote_multi_op_count_total": int((rel_total.groupby("nro_pago")["order_de_p"].nunique() > 1).sum()) if len(rel_total) else 0,
            "op_multi_lote_count_scoped": int((rel_scoped.groupby("order_de_p")["nro_pago"].nunique() > 1).sum()) if len(rel_scoped) else 0,
            "lote_multi_op_count_scoped": int((rel_scoped.groupby("nro_pago")["order_de_p"].nunique() > 1).sum()) if len(rel_scoped) else 0,
        },
        "extracto_coverage": {
            "matched_lotes": int(len(matched_lotes)),
            "total_lotes": int(len(lotes)),
            "matched_amount": round(matched_lotes_amount, 2),
            "total_amount": round(total_lotes_amount, 2),
            "coverage_count_pct": _safe_pct(len(matched_lotes), len(lotes)),
            "coverage_amount_pct": _safe_pct(matched_lotes_amount, total_lotes_amount),
        },
        "pilaga_coverage": {
            "matched_rows": int(len(matched_ops)),
            "matched_unique_ops": int(matched_ops[matched_ops_key_col].nunique()) if (not matched_ops.empty and matched_ops_key_col) else 0,
            "matched_amount": round(matched_ops_amount, 2),
            "lag_days_histogram": lag_histogram,
            "bank_distribution": bank_distribution,
        },
        "final_reconciliation": {
            "pilaga_rows_with_extracto": int(len(final_ops)),
            "pilaga_unique_ops_with_extracto": int(final_ops[final_ops_key_col].nunique()) if (not final_ops.empty and final_ops_key_col) else 0,
            "pilaga_amount_with_extracto": round(final_ops_amount, 2),
            "extracto_lotes_with_contable_support": int(len(effective_lotes)),
            "extracto_amount_with_contable_support": round(effective_lotes_amount, 2),
            "shared_lote_count": int(len(effective_lote_keys)),
            "banks_in_final_reconciliation": final_banks,
            "pilaga_rows_traced_only": int(max(len(matched_ops) - len(final_ops), 0)),
            "pilaga_amount_traced_only": round(max(matched_ops_amount - final_ops_amount, 0.0), 2),
            "extracto_lotes_only_sicom": int(max(len(matched_lotes) - len(effective_lotes), 0)),
            "extracto_amount_only_sicom": round(max(matched_lotes_amount - effective_lotes_amount, 0.0), 2),
        },
    }


def _get_extracto_saldos(path: Path) -> Tuple[Optional[float], Optional[float]]:
    """Lee saldos inicial/final del extracto sin alterar el loader principal."""
    try:
        wb = load_workbook(str(path), data_only=True, read_only=True)
    except Exception:
        return (None, None)
    try:
        sheet = next(
            (n for n in wb.sheetnames if str(n).strip().lower() == "principal"),
            wb.sheetnames[0],
        )
        ws = wb[sheet]
        saldo_inicial = None
        saldo_final = None
        for row in ws.iter_rows(values_only=True):
            if not row:
                continue
            first = row[0]
            if isinstance(first, str) and "SALDO INICIAL" in first.upper():
                saldo_inicial = _parse_money_value(row[1])
            marker = row[8] if len(row) > 8 else None
            if isinstance(marker, str) and "SALDO FINAL" in marker.upper():
                saldo_final = _parse_money_value(row[9] if len(row) > 9 else None)
                break
        return (saldo_inicial, saldo_final)
    finally:
        wb.close()


def _get_pilaga_saldos(path: Path) -> Tuple[Optional[float], Optional[float]]:
    """Lee saldos inicial/final de PILAGA desde la primera columna de resumen."""
    try:
        wb = load_workbook(str(path), data_only=True, read_only=True)
    except Exception:
        return (None, None)
    try:
        sheet = next(
            (n for n in wb.sheetnames if str(n).strip().lower() == "resumen cuenta bancaria"),
            wb.sheetnames[0],
        )
        ws = wb[sheet]
        saldo_inicial = None
        saldo_final = None
        for row in ws.iter_rows(values_only=True):
            if not row:
                continue
            first = row[0]
            if not isinstance(first, str):
                continue
            txt = first.strip()
            up = txt.upper()
            if up.startswith("SALDO INICIAL"):
                saldo_inicial = _parse_money_value(txt.split(":")[-1])
            elif up.startswith("SALDO FINAL"):
                saldo_final = _parse_money_value(txt.split(":")[-1])
                if saldo_inicial is not None:
                    break
        return (saldo_inicial, saldo_final)
    finally:
        wb.close()


def _find_header_row_with_fecha(df: pd.DataFrame, scan_rows: int = 50) -> Optional[int]:
    """
    Busca la fila de encabezado en la que, además de 'Fecha', aparecen otras
    columnas esperables del extracto (Comprobante, Concepto, Importe, etc.).
    Esto evita falsos positivos en filas informativas previas al detalle.
    """
    expected = {"FECHA", "COMPROBANTE", "CONCEPTO/COD.OP.", "CONCEPTO", "DETALLE",
                "DESCRIPCION", "DESCRIPCIÓN", "IMPORTE", "MONTO", "SALDO"}
    best_idx: Optional[int] = None
    best_score = -1

    for i in range(min(len(df), scan_rows)):
        vals = [str(x).strip().upper() for x in df.iloc[i].tolist()]
        if not any(vals):
            continue
        has_fecha = any(v == "FECHA" or v.startswith("FECHA") for v in vals)
        score = sum(1 for v in vals if v in expected)
        if has_fecha:
            score += 1  # favorecemos filas que tengan FECHA explícito

        if score > best_score and (has_fecha or score >= 2):
            best_idx = i
            best_score = score
            if best_score >= 4:  # heurística: suficiente evidencia
                break

    return best_idx


def _load_extracto(path: Path) -> pd.DataFrame:
    """
    Lee EXTRACTO bancario (hoja 'principal' o primera).
    Detecta encabezado (fila con 'Fecha'), normaliza monto.
    Devuelve DF con columnas estandarizadas: ['fecha','monto','documento','origen']
    """
    cache_key = _df_cache_key("extracto", path)
    if cache_key in _DF_CACHE:
        return _DF_CACHE[cache_key].copy()

    if path.suffix.lower() in {".parquet", ".pq"}:
        if pl is not None:
            out = pl.read_parquet(str(path)).to_pandas()
        else:
            out = pd.read_parquet(str(path))
        if "fecha" in out.columns:
            out["fecha"] = pd.to_datetime(out["fecha"], errors="coerce")
        if "monto" in out.columns:
            out["monto"] = pd.to_numeric(out["monto"], errors="coerce").fillna(0.0)
        if "documento" in out.columns:
            out["documento"] = out["documento"].astype(str)
        _DF_CACHE[cache_key] = out.copy()
        return out

    engine = _preferred_engine()
    try:
        xls = pd.ExcelFile(str(path), engine=engine)
    except Exception:
        xls = pd.ExcelFile(str(path), engine="openpyxl")

    sheet = next((n for n in xls.sheet_names if str(n).strip().lower() == "principal"), xls.sheet_names[0])
    raw = pd.read_excel(xls, sheet_name=sheet, header=None)

    hdr = _find_header_row_with_fecha(raw)
    if hdr is None:
        hdr = 0

    headers = [str(x or "").strip() for x in raw.iloc[hdr].tolist()]
    df = raw.iloc[hdr + 1:].copy()
    df.columns = headers
    df = df.dropna(how="all")

    # Candidatos típicos (según tu análisis)
    fecha_col = next((c for c in df.columns if str(c).strip().upper() == "FECHA"), df.columns[0])
    # Importe suele estar en 'Unnamed: 4' o 'IMPORTE' etc. Probamos:
    cand_importe = [c for c in df.columns if str(c).strip().upper() in ("IMPORTE", "IMPORTE EN $", "MONTO")]
    importe_col = cand_importe[0] if cand_importe else (df.columns[4] if len(df.columns) > 4 else df.columns[-1])

    # Documento/descripcion (opcional; si no está, igual seguimos)
    cand_doc = [c for c in df.columns if str(c).strip().upper() in ("COMPROBANTE", "DESCRIPCIÓN", "DETALLE", "DESCRIPCION")]
    doc_col = cand_doc[0] if cand_doc else (df.columns[2] if len(df.columns) > 2 else df.columns[0])

    def _col_as_series(col_name: Any) -> pd.Series:
        col = df[col_name]
        if isinstance(col, pd.DataFrame):
            return col.iloc[:, 0]
        return col

    fecha_data = _col_as_series(fecha_col)
    doc_data = _col_as_series(doc_col)
    importe_data = _col_as_series(importe_col)

    out = pd.DataFrame({
        "fecha": pd.to_datetime(fecha_data, dayfirst=True, errors="coerce"),
        "documento": doc_data.astype(str),
        "monto": _clean_money(importe_data),
    })
    out = out.dropna(subset=["fecha"])
    out = out[out["monto"] != 0]
    out["origen"] = "EXTRACTO"
    out = out.reset_index(drop=True)
    _DF_CACHE[cache_key] = out.copy()
    return out


# =========================
# Matching (± ventana días)
# =========================
def _match_one_to_one_by_amount_and_date_window(
    df_p: pd.DataFrame,
    df_b: pd.DataFrame,
    days_window: int
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Empareja uno-a-uno por monto idéntico (redondeado a 2) y |fecha_p - fecha_b| <= days_window.
    Retorna: pairs, sobrantes_pilaga, sobrantes_banco
    """
    orig_cols_p = df_p.columns
    orig_cols_b = df_b.columns
    p = df_p.reset_index(drop=True).copy()
    b = df_b.reset_index(drop=True).copy()
    p["_row_id_p"] = p.index
    b["_row_id_b"] = b.index
    p["monto_r"] = p["monto"].round(2)
    b["monto_r"] = b["monto"].round(2)

    # Join por monto
    merged = p.merge(b, on="monto_r", suffixes=("_p", "_b"))
    # Ventana de fechas
    merged["date_diff_days"] = (merged["fecha_p"] - merged["fecha_b"]).abs().dt.days
    merged = merged[merged["date_diff_days"] <= abs(int(days_window))]

    # Greedy: quedarnos con el match más cercano por monto/fecha
    merged = merged.sort_values(["monto_r", "date_diff_days", "_row_id_p", "_row_id_b"])

    used_p: set[int] = set()
    used_b: set[int] = set()
    selected_rows = []
    for record in merged.to_dict("records"):
        row_id_p = record["_row_id_p"]
        row_id_b = record["_row_id_b"]
        if row_id_p in used_p or row_id_b in used_b:
            continue
        used_p.add(row_id_p)
        used_b.add(row_id_b)
        selected_rows.append(record)

    if selected_rows:
        merged = pd.DataFrame(selected_rows, columns=merged.columns)
    else:
        merged = merged.iloc[0:0].copy()

    matched_p = set(merged["_row_id_p"])
    matched_b = set(merged["_row_id_b"])

    sobrantes_p = p[~p["_row_id_p"].isin(matched_p)][orig_cols_p].copy()
    sobrantes_b = b[~b["_row_id_b"].isin(matched_b)][orig_cols_b].copy()
    pairs = merged.drop(columns=["_row_id_p", "_row_id_b"], errors="ignore")

    return pairs.reset_index(drop=True), sobrantes_p.reset_index(drop=True), sobrantes_b.reset_index(drop=True)


# =========================
# API Route
# =========================
_RECONCILE_STAGES = [
    {"name": "PREPARE_INPUTS", "label": "Preparando entradas", "weight": 2},
    {"name": "LOAD_EXTRACTO", "label": "Cargando extracto", "weight": 18},
    {"name": "LOAD_CONTABLE", "label": "Cargando contable", "weight": 18},
    {"name": "LOAD_SICOM", "label": "Cargando SICOM", "weight": 10},
    {"name": "NORMALIZE", "label": "Normalizando", "weight": 8},
    {"name": "MATCH_1_1", "label": "Conciliando 1→1", "weight": 16},
    {"name": "SUMMARY", "label": "Resumen", "weight": 10},
    {"name": "FINALIZE", "label": "Finalizando", "weight": 2},
]


@post("/api/reconcile/start")
async def reconcile_start(request: Any) -> Response:
    """
    FORM multipart o x-www-form-urlencoded:
      - threadId (opcional): para SSE
      - uri_extracto: file://... (obligatorio)
      - uri_contable: file://... (obligatorio)
      - days_window: int (opcional, default 5)

    Emite por SSE:
      - {type:"RUN_START", ...}
      - {type:"RESULTS_READY", payload:{summary, counts}}
    """
    run_id = None
    stage_started: dict[str, float] = {}
    thread_id = None

    async def _emit_event(payload: dict[str, Any]) -> None:
        if thread_id:
            await emit(thread_id, payload)

    async def _emit_stage(
        stage: str,
        status: str,
        message: Optional[str] = None,
        timing_ms: Optional[int] = None,
        metrics: Optional[dict[str, Any]] = None,
    ) -> None:
        payload = {
            "type": "RECONCILE_STAGE",
            "payload": {
                "run_id": run_id,
                "stage": stage,
                "status": status,
                "message": message,
                "timing_ms": timing_ms,
                "metrics": metrics,
            },
        }
        await _emit_event(payload)

    try:
        form = await request.form()
        thread_id = form.get("threadId")
        # Campos históricos del frontend: extracto_original_uri / contable_original_uri
        # Nueva versión usa uri_extracto / uri_contable. Aceptamos ambos.
        uri_extracto = form.get("extracto_original_uri") or form.get("uri_extracto") or ""
        uri_contable = form.get("contable_original_uri") or form.get("uri_contable") or ""
        uri_sicom = form.get("sicom_original_uri") or form.get("uri_sicom") or ""
        bank_scope = str(form.get("bank_scope") or "").strip()
        account_scope = str(form.get("account_scope") or "").strip()
        days_window = int(form.get("days_window") or 5)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable son obligatorios."}, status_code=400)

        run_id = str(uuid4())
        from backend.http.audit import audit_temporary
        await audit_temporary(request, 'reconcile_compute_start', run_id)

        await _emit_event({
            "type": "RUN_START",
            "payload": {
                "run_id": run_id,
                "days_window": days_window,
                "stages": _RECONCILE_STAGES,
            },
        })

        path_extracto = _from_file_uri(uri_extracto)
        path_contable = _from_file_uri(uri_contable)
        path_sicom = _from_file_uri(uri_sicom) if uri_sicom else None

        # 1) Cargar
        await _emit_stage("PREPARE_INPUTS", "start", "Validando entradas…")
        stage_started["PREPARE_INPUTS"] = time.monotonic()
        await _emit_stage(
            "PREPARE_INPUTS",
            "done",
            "Entradas listas.",
            timing_ms=int((time.monotonic() - stage_started["PREPARE_INPUTS"]) * 1000),
        )

        await _emit_stage("LOAD_CONTABLE", "start", "Cargando contable…")
        stage_started["LOAD_CONTABLE"] = time.monotonic()
        df_pilaga = _load_pilaga(path_contable)
        await _emit_stage(
            "LOAD_CONTABLE",
            "done",
            "Contable cargado.",
            timing_ms=int((time.monotonic() - stage_started["LOAD_CONTABLE"]) * 1000),
            metrics={"rows": len(df_pilaga)},
        )

        df_sicom: pd.DataFrame | None = None
        if path_sicom is not None:
            await _emit_stage("LOAD_SICOM", "start", "Cargando SICOM…")
            stage_started["LOAD_SICOM"] = time.monotonic()
            df_sicom = _load_sicom(path_sicom)
            await _emit_stage(
                "LOAD_SICOM",
                "done",
                "SICOM cargado.",
                timing_ms=int((time.monotonic() - stage_started["LOAD_SICOM"]) * 1000),
                metrics={"rows": len(df_sicom)},
            )

        await _emit_stage("LOAD_EXTRACTO", "start", "Cargando extracto…")
        stage_started["LOAD_EXTRACTO"] = time.monotonic()
        df_banco = _load_extracto(path_extracto)
        await _emit_stage(
            "LOAD_EXTRACTO",
            "done",
            "Extracto cargado.",
            timing_ms=int((time.monotonic() - stage_started["LOAD_EXTRACTO"]) * 1000),
            metrics={"rows": len(df_banco)},
        )

        await _emit_stage("NORMALIZE", "start", "Normalizando datos…")
        stage_started["NORMALIZE"] = time.monotonic()
        await _emit_stage(
            "NORMALIZE",
            "done",
            "Normalizacion completa.",
            timing_ms=int((time.monotonic() - stage_started["NORMALIZE"]) * 1000),
        )

        # 2) Conciliar
        await _emit_stage("MATCH_1_1", "start", "Conciliando 1→1…")
        stage_started["MATCH_1_1"] = time.monotonic()
        pairs, sobrantes_p, sobrantes_b = _match_one_to_one_by_amount_and_date_window(df_pilaga, df_banco, days_window)
        await _emit_stage(
            "MATCH_1_1",
            "done",
            "Conciliacion 1→1 completa.",
            timing_ms=int((time.monotonic() - stage_started["MATCH_1_1"]) * 1000),
            metrics={"pairs": len(pairs)},
        )

        # 3) Resumen
        await _emit_stage("SUMMARY", "start", "Armando resumen…")
        stage_started["SUMMARY"] = time.monotonic()
        total_p = len(df_pilaga)
        total_b = len(df_banco)
        conc_pairs = len(pairs)
        no_en_banco = len(sobrantes_p)
        no_en_pilaga = len(sobrantes_b)

        summary = {
            "movimientos_pilaga": total_p,
            "movimientos_banco": total_b,
            "conciliados_pares": conc_pairs,
            "no_en_banco": no_en_banco,    # están en PILAGA pero no en el banco
            "no_en_pilaga": no_en_pilaga,  # están en banco pero no en PILAGA
            "days_window": days_window,
        }
        if df_sicom is not None:
            summary["sicom"] = _build_sicom_insights(
                df_sicom,
                df_pilaga,
                df_banco,
                bank_scope=bank_scope,
                account_scope=account_scope,
                path_extracto=path_extracto,
            )

        await _emit_stage(
            "SUMMARY",
            "done",
            "Resumen listo.",
            timing_ms=int((time.monotonic() - stage_started["SUMMARY"]) * 1000),
            metrics={"banco": total_b, "contable": total_p},
        )

        await _emit_stage("FINALIZE", "start", "Finalizando…")
        stage_started["FINALIZE"] = time.monotonic()
        await _emit_stage(
            "FINALIZE",
            "done",
            "Finalizacion completa.",
            timing_ms=int((time.monotonic() - stage_started["FINALIZE"]) * 1000),
        )

        await _emit_event({
            "type": "RESULTS_READY",
            "payload": {
                "run_id": run_id,
                "summary": summary,
            },
        })

        await audit_temporary(request, 'reconcile_compute_complete', run_id)
        return Response({"ok": True, "summary": summary, "persistence": "temporary"}, status_code=200)

    except TimeoutError as e:
        from backend.http.audit import audit_temporary
        await audit_temporary(request, 'reconcile_compute_error', run_id, 'FAILURE', 'timeout; no durable decision')
        tb = traceback.format_exc(limit=8)
        logger.exception("reconcile_start timeout")
        print("[reconcile_start] ERROR:", type(e).__name__, str(e), flush=True)
        print(tb, flush=True)
        if thread_id:
            await _emit_event({
                "type": "TOAST",
                "level": "error",
                "message": "Timeout durante la conciliación.",
            })
        return Response(
            {
                "ok": False,
                "message": "Timeout durante la conciliación",
                "error": f"{type(e).__name__}: {e}",
                "trace": tb,
                "where": "reconcile_start",
            },
            status_code=503,
        )
    except Exception as e:
        from backend.http.audit import audit_temporary
        await audit_temporary(request, 'reconcile_compute_error', run_id, 'FAILURE', 'computation failed; no durable decision')
        tb = traceback.format_exc(limit=12)
        logger.exception("reconcile_start error")
        print("[reconcile_start] ERROR:", type(e).__name__, str(e), flush=True)
        print(tb, flush=True)
        try:
            await _emit_stage(
                "FINALIZE",
                "error",
                f"{type(e).__name__}: {e}",
            )
        except Exception as stage_err:
            print(
                f"[reconcile_start] error stage failed: {type(stage_err).__name__}: {stage_err}",
                flush=True,
            )
        if thread_id:
            await _emit_event({
                "type": "TOAST",
                "level": "error",
                "message": f"Reconcile error: {type(e).__name__}: {e}",
            })
        return Response(
            {
                "ok": False,
                "message": "Error interno en conciliación",
                "error": f"{type(e).__name__}: {e}",
                "trace": tb,
                "where": "reconcile_start",
            },
            status_code=500,
        )

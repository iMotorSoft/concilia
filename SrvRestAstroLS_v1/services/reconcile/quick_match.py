# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/services/reconcile/quick_match.py

from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

try:
    import pandas as pd  # type: ignore
except Exception:
    pd = None

# Normalización común
@dataclass
class TxRow:
    date: Optional[pd.Timestamp]
    amount: float
    desc: str
    src: str         # "bank" | "gl"
    raw: Dict[str, Any]

def _to_ts(x) -> Optional[pd.Timestamp]:
    if pd is None: return None
    try:
        if pd.isna(x): return None
        return pd.to_datetime(x, dayfirst=True, errors="coerce")
    except Exception:
        return None

def _as_float(x) -> Optional[float]:
    if x is None: return None
    if isinstance(x, str):
        s = x.strip().replace(".", "").replace(",", ".")
        try:
            return float(s)
        except Exception:
            pass
    try:
        return float(x)
    except Exception:
        return None

def normalize_bank_df(df0: "pd.DataFrame") -> List[TxRow]:
    """Heurística para extractos bancarios (Ciudad / Patagonia / Santander).
       Busca columnas con 'Fecha' y una de ('Importe','Debe/Haber','Crédito/Débito','Monto','Importe Pesos').
    """
    out: List[TxRow] = []
    if df0 is None or df0.empty:
        return out

    df = df0.copy()
    # detectar fecha
    date_col = None
    for c in df.columns:
        up = str(c).strip().upper()
        if "FECHA" in up:
            date_col = c; break
    if date_col is None:
        # fallback: primera columna parseable
        for c in df.columns:
            ts = pd.to_datetime(df[c], dayfirst=True, errors="coerce")
            if ts.notna().sum() >= max(3, int(len(ts) * 0.1)):
                date_col = c; break

    # detectar importe (+/-) – preferimos una sola col de signo explícito
    amt_col = None
    candidates = []
    for c in df.columns:
        up = str(c).strip().upper()
        if any(k in up for k in ("IMPORTE", "MONTO", "IMPORTES", "CREDITO", "CRÉDITO", "DEBITO", "DÉBITO", "DEBE", "HABER")):
            candidates.append(c)
    if candidates:
        # heurística: si hay "Importe" o "Monto" lo priorizamos
        for pref in ("IMPORTE", "MONTO"):
            m = [c for c in candidates if pref in str(c).strip().upper()]
            if m:
                amt_col = m[0]; break
        if amt_col is None:
            amt_col = candidates[0]

    # si hay dos columnas Debe/Haber, restamos
    debe = haber = None
    if amt_col is None:
        for c in df.columns:
            up = str(c).strip().upper()
            if "DEBE" == up or "DÉBE" == up or "DÉBITO" in up:
                debe = c
            if "HABER" == up or "CRÉDITO" in up or "CREDITO" in up:
                haber = c

    # descripción
    desc_col = None
    for c in df.columns:
        up = str(c).strip().upper()
        if any(k in up for k in ("DETALLE", "DESCRIP", "CONCEPTO", "LEYENDA", "DESCRIPCIÓN", "BENEFICIARIO")):
            desc_col = c; break

    for _, row in df.iterrows():
        ts = _to_ts(row.get(date_col)) if date_col else None

        amount = None
        if amt_col is not None:
            amount = _as_float(row.get(amt_col))
        else:
            v_debe = _as_float(row.get(debe)) if debe else None
            v_haber = _as_float(row.get(haber)) if haber else None
            if v_debe is not None or v_haber is not None:
                amount = (v_haber or 0.0) - (v_debe or 0.0)

        if amount is None:
            continue

        desc = str(row.get(desc_col) or "").strip()
        out.append(TxRow(date=ts, amount=round(float(amount), 2), desc=desc, src="bank", raw=row.to_dict()))
    return out

def normalize_gl_df(df0: "pd.DataFrame") -> List[TxRow]:
    """Heurística para PILAGA:
       - Fecha en primera columna o columna con 'Fecha'
       - Ingresos / Egresos → amount = Ingresos - Egresos
       - Descripción: 'Detalle' o similar
    """
    out: List[TxRow] = []
    if df0 is None or df0.empty:
        return out

    df = df0.copy()
    # fecha
    date_col = None
    for c in df.columns:
        up = str(c).strip().upper()
        if "FECHA" in up:
            date_col = c; break
    if date_col is None:
        date_col = df.columns[0]  # como vimos que funciona bien

    # ingresos / egresos
    col_ing = col_egr = None
    for c in df.columns:
        up = str(c).strip().upper()
        if "INGRESOS" in up:
            col_ing = c
        elif "EGRESOS" in up:
            col_egr = c

    # desc
    desc_col = None
    for c in df.columns:
        up = str(c).strip().upper()
        if any(k in up for k in ("DETALLE", "CONCEPTO", "OBSERV", "DOC", "BENEFICIARIO")):
            desc_col = c; break

    # saltar encabezados (las primeras 2-3 lineas en contable)
    start_idx = 2
    s = df[date_col].astype(str).str.strip().str.lower()
    hit = s.eq("fecha")
    if hit.any():
        start_idx = int(hit[hit].index[0]) + 1

    for _, row in df.iloc[start_idx:].iterrows():
        ts = _to_ts(row.get(date_col))
        ing = _as_float(row.get(col_ing)) if col_ing else None
        egr = _as_float(row.get(col_egr)) if col_egr else None
        if ing is None and egr is None:
            # podría haber una sola columna “Importe”
            # intentamos cualquier numérico
            merged = None
            for c in df.columns:
                merged = _as_float(row.get(c))
                if merged is not None:
                    break
            if merged is None: 
                continue
            amount = merged
        else:
            amount = (ing or 0.0) - (egr or 0.0)

        desc = str(row.get(desc_col) or "").strip()
        out.append(TxRow(date=ts, amount=round(float(amount), 2), desc=desc, src="gl", raw=row.to_dict()))
    return out

def _load_excel(path: Path) -> "pd.DataFrame":
    xls = pd.ExcelFile(str(path), engine="openpyxl")
    # si existe hoja 'archivo contable' usarla, si no, la 1ra
    sheet = xls.sheet_names[0]
    for pref in ("archivo contable", "contable", "resumen"):
        for s in xls.sheet_names:
            if s.strip().lower() == pref:
                sheet = s; break
    return pd.read_excel(xls, sheet_name=sheet)

def _guess_kind_from_preview_cols(cols: List[str]) -> str:
    up = [c.upper() for c in cols]
    if any("FECHA" in c for c in up) and any(("INGRESOS" in c or "EGRESOS" in c) for c in up):
        return "gl"
    return "bank"

def reconcile(bank_df: "pd.DataFrame", gl_df: "pd.DataFrame", days_tolerance: int = 3) -> Dict[str, Any]:
    """Matching simple:
       - criterio 1: importe exacto y fecha dentro de ±days_tolerance
       - unmatched quedan listados
    """
    bank_rows = normalize_bank_df(bank_df)
    gl_rows   = normalize_gl_df(gl_df)

    matched: List[Dict[str, Any]] = []
    unmatched_bank = bank_rows.copy()
    unmatched_gl   = gl_rows.copy()

    # índice rápido por importe en GL
    gl_by_amount: Dict[float, List[TxRow]] = {}
    for r in gl_rows:
        gl_by_amount.setdefault(r.amount, []).append(r)

    def date_close(a: Optional[pd.Timestamp], b: Optional[pd.Timestamp]) -> bool:
        if a is None or b is None:
            return False
        delta = abs((a.date() - b.date()).days)
        return delta <= days_tolerance

    used_gl: set[int] = set()

    for b in bank_rows:
        candidates = gl_by_amount.get(b.amount, [])
        hit_idx = None
        for idx, g in enumerate(candidates):
            if id(g) in used_gl:
                continue
            if date_close(b.date, g.date):
                hit_idx = idx
                break
        if hit_idx is not None:
            g = candidates[hit_idx]
            used_gl.add(id(g))
            matched.append({
                "amount": b.amount,
                "bank_date": b.date.date().isoformat() if b.date is not None else None,
                "gl_date":   g.date.date().isoformat() if g.date is not None else None,
                "bank_desc": b.desc,
                "gl_desc":   g.desc,
            })

    # reconstruir unmatched
    matched_bank_ids = set(id(m) for m in [br for br in bank_rows for mm in matched if br.amount == mm["amount"] and (br.date is not None and mm["bank_date"] == br.date.date().isoformat())])
    unmatched_bank = [r for r in bank_rows if id(r) not in matched_bank_ids]

    matched_gl_ids = { id(r) for r in gl_rows if id(r) in used_gl }
    unmatched_gl = [r for r in gl_rows if id(r) not in matched_gl_ids]

    return {
        "summary": {
            "bank_count": len(bank_rows),
            "gl_count": len(gl_rows),
            "matched": len(matched),
            "unmatched_bank": len(unmatched_bank),
            "unmatched_gl": len(unmatched_gl),
            "days_tolerance": days_tolerance,
        },
        "matched": matched[:200],  # limitar para UI
        "unmatched_bank": [
            {
                "date": r.date.date().isoformat() if r.date is not None else None,
                "amount": r.amount,
                "desc": r.desc,
            } for r in unmatched_bank[:200]
        ],
        "unmatched_gl": [
            {
                "date": r.date.date().isoformat() if r.date is not None else None,
                "amount": r.amount,
                "desc": r.desc,
            } for r in unmatched_gl[:200]
        ],
    }

def reconcile_from_paths(bank_path: Path, gl_path: Path, days_tolerance: int = 3) -> Dict[str, Any]:
    if pd is None:
        return {"ok": False, "error": "pandas no disponible"}
    bank_df = _load_excel(bank_path)
    gl_df   = _load_excel(gl_path)
    return reconcile(bank_df, gl_df, days_tolerance=days_tolerance)


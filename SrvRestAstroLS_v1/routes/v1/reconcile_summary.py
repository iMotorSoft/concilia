# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/routes/v1/reconcile_summary.py
from __future__ import annotations

import traceback
import time
from typing import Any, Optional, Tuple
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from litestar import post
from litestar.response import Response

# Reusamos helpers y loaders del start (mantiene coherencia con lo ya probado)
from .reconcile_start import (
    _from_file_uri,              # convierte file://... en Path
    _load_pilaga,                # DF con ingreso/egreso originales + monto neto
    _load_extracto,              # DF: ['fecha','monto','documento','origen']  (importe limpio)
    _get_extracto_saldos,
    _get_pilaga_saldos,
)
# Pipeline completo (pares, agrupados, sugeridos, sobrantes)
from .reconcile_details import _compute_pipeline

EXCLUDE_MARKERS = ("SALDO INICIAL", "SALDO FINAL")

def _filter_movements_df(df: pd.DataFrame) -> pd.DataFrame:
    """Quita filas informativas (saldos) y asegura tipos."""
    if df is None or df.empty:
        return df
    d = df.copy()
    # Filtrar por texto en 'documento' si existe
    doc_col = "documento" if "documento" in d.columns else None
    if doc_col:
        up = d[doc_col].astype(str).str.upper()
        for mark in EXCLUDE_MARKERS:
            d = d[~up.str.contains(mark, na=False)]
    # Asegurar tipos
    d["monto"] = pd.to_numeric(d["monto"], errors="coerce")
    d = d.dropna(subset=["fecha", "monto"])
    d = d[d["monto"] != 0]
    return d.reset_index(drop=True)

def _sum_pos_neg(series: pd.Series) -> Tuple[float, float, float]:
    """Devuelve (negativos_abs_as_debe, positivos_as_haber, neto = haber - debe)."""
    s = pd.to_numeric(series, errors="coerce").fillna(0.0)
    haber = float(s[s > 0].sum())
    debe  = float((-s[s < 0]).sum())  # abs de negativos
    neto  = float(haber - debe)
    return (round(debe, 2), round(haber, 2), round(neto, 2))


def _sum_pilaga_totals(df: pd.DataFrame) -> Tuple[float, float, float]:
    """
    Devuelve (ingresos, egresos, neto) priorizando las columnas originales
    del archivo (ingreso/egreso). Si no existen, cae al comportamiento previo.
    """
    if df is None or df.empty:
        return (0.0, 0.0, 0.0)

    if "ingreso_bruto" in df.columns and "egreso_bruto" in df.columns:
        ingresos = pd.to_numeric(df["ingreso_bruto"], errors="coerce").fillna(0.0)
        egresos = pd.to_numeric(df["egreso_bruto"], errors="coerce").fillna(0.0)
        p_ing = float(ingresos.sum())
        p_egr = float(egresos.sum())
        return (round(p_ing, 2), round(p_egr, 2), round(p_ing - p_egr, 2))

    # Fallback: derivar de los signos del monto neto.
    s = pd.to_numeric(df["monto"], errors="coerce").fillna(0.0)
    p_ing = float(s[s > 0].sum())
    p_egr = float((-s[s < 0]).sum())
    return (round(p_ing, 2), round(p_egr, 2), round(p_ing - p_egr, 2))

def _build_summary(uri_extracto: str, uri_contable: str, days_window: int, *, include_descomposicion: bool = True) -> dict[str, Any]:
    """Genera el resumen completo; opcionalmente omite la descomposición."""
    t_start = time.perf_counter()
    path_extracto = _from_file_uri(uri_extracto)
    path_contable = _from_file_uri(uri_contable)

    # 1) Cargar con los mismos loaders del flujo actual
    t_load_start = time.perf_counter()
    df_pilaga  = _filter_movements_df(_load_pilaga(path_contable))
    df_banco   = _filter_movements_df(_load_extracto(path_extracto))
    t_after_load = time.perf_counter()

    # 2) Totales:
    p_ing, p_egr, p_neto = _sum_pilaga_totals(df_pilaga)
    #    - BANCO: debe/haber a partir de signos, neto = haber - debe
    b_debe, b_haber, b_neto = _sum_pos_neg(df_banco["monto"])

    b_saldo_inicial, b_saldo_final = _get_extracto_saldos(path_extracto)
    p_saldo_inicial, p_saldo_final = _get_pilaga_saldos(path_contable)

    # 3) Pipeline completo (pares 1→1, agrupados, sugeridos, sobrantes)
    pipeline = _compute_pipeline(df_pilaga, df_banco, days_window)
    pairs_df = pipeline["pairs_df"]
    approved = pipeline["approved"]
    suggested = pipeline["suggested"]
    sobrantes_p = pipeline["sobrantes_p"]  # PILAGA no reflejado en banco
    sobrantes_b = pipeline["sobrantes_b"]  # Banco no reflejado en PILAGA
    timings_pipe = pipeline.get("timings", {}) if isinstance(pipeline, dict) else {}

    total_p = int(len(df_pilaga))
    total_b = int(len(df_banco))

    conc_pairs = int(len(pairs_df))
    no_en_banco = int(len(sobrantes_p))
    no_en_pilaga = int(len(sobrantes_b))

    summary: dict[str, Any] = {
        "movimientos_pilaga": total_p,
        "movimientos_banco": total_b,
        "conciliados_pares": conc_pairs,
        "no_en_banco": no_en_banco,
        "no_en_pilaga": no_en_pilaga,
        "days_window": int(days_window),
        "banco":   {
            "debe": b_debe,
            "haber": b_haber,
            "neto": b_neto,
            "saldo_inicial": b_saldo_inicial,
            "saldo_final": b_saldo_final if b_saldo_final is not None else (b_saldo_inicial if b_saldo_inicial is not None else 0.0) + b_neto,
        },
        "pilaga":  {
            "ingresos": p_ing,
            "egresos": p_egr,
            "neto": p_neto,
            "saldo_inicial": p_saldo_inicial,
            "saldo_final": p_saldo_final if p_saldo_final is not None else (p_saldo_inicial if p_saldo_inicial is not None else 0.0) + p_neto,
        },
        "diferencia_neto": round(b_neto - p_neto, 2),
        "timings": {
            "load_total": round(t_after_load - t_load_start, 3),
            "pipeline_total": round(timings_pipe.get("total", 0.0), 3),
            "pairs": round(timings_pipe.get("pairs", 0.0), 3),
            "n1_approved": round(timings_pipe.get("n1_approved", 0.0), 3),
            "n1_suggested": round(timings_pipe.get("n1_suggested", 0.0), 3),
            "n1_suggested_bank_to_pilaga": round(timings_pipe.get("n1_suggested_bank_to_pilaga", 0.0), 3),
            "total_endpoint": round(time.perf_counter() - t_start, 3),
        },
    }

    if include_descomposicion:
        conciliados_amount = float(pd.to_numeric(pairs_df["monto_r"], errors="coerce").fillna(0).sum()) if not pairs_df.empty else 0.0
        agrupados_amount = float(sum((g.get("monto_total") or 0.0) for g in approved))
        sugeridos_amount = float(sum((g.get("monto_total") or 0.0) for g in suggested))
        no_en_banco_amount = float(pd.to_numeric(sobrantes_p["monto"], errors="coerce").fillna(0).sum()) if not sobrantes_p.empty else 0.0
        no_en_pilaga_amount = float(pd.to_numeric(sobrantes_b["monto"], errors="coerce").fillna(0).sum()) if not sobrantes_b.empty else 0.0

        summary["descomposicion"] = {
            "conciliados": {"count": conc_pairs, "amount": round(conciliados_amount, 2)},
            "agrupados": {"count": len(approved), "amount": round(agrupados_amount, 2)},
            "sugeridos": {"count": len(suggested), "amount": round(sugeridos_amount, 2)},
            "no_en_banco": {"count": no_en_banco, "amount": round(no_en_banco_amount, 2)},
            "no_en_pilaga": {"count": no_en_pilaga, "amount": round(no_en_pilaga_amount, 2)},
        }

    return summary


def _parse_form(request: Any) -> tuple[str, str, int]:
    form = request
    uri_extracto = form.get("uri_extracto") or form.get("extracto_original_uri") or ""
    uri_contable = form.get("uri_contable") or form.get("contable_original_uri") or ""
    days_window  = int(form.get("days_window") or 5)
    return uri_extracto, uri_contable, days_window


@post("/api/reconcile/summary")
async def reconcile_summary(request: Any) -> Response:
    """
    POST (multipart o x-www-form-urlencoded):
      - uri_extracto   : file://... (obligatorio)
      - uri_contable   : file://... (obligatorio)
      - days_window    : int (opcional, default 5)

    Respuesta completa (compatibilidad hacia atrás):
      {
        ok: true,
        summary: { ... todas las métricas + descomposición ... }
      }
    """
    try:
        form = await request.form()
        uri_extracto, uri_contable, days_window = _parse_form(form)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable son obligatorios."}, status_code=400)

        summary = _build_summary(uri_extracto, uri_contable, days_window, include_descomposicion=True)

        return Response({"ok": True, "summary": summary}, status_code=200)

    except Exception as e:
        tb = traceback.format_exc(limit=12)
        print("[reconcile_summary] ERROR:", type(e).__name__, str(e), flush=True)
        print(tb, flush=True)
        return Response(
            {"ok": False, "message": "Error interno en resumen", "error": f"{type(e).__name__}: {e}", "trace": tb},
            status_code=500
        )


@post("/api/reconcile/summary/head")
async def reconcile_summary_head(request: Any) -> Response:
    """Devuelve solo el head (totales/cantidades) sin la descomposición."""
    try:
        form = await request.form()
        uri_extracto, uri_contable, days_window = _parse_form(form)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable son obligatorios."}, status_code=400)

        summary = _build_summary(uri_extracto, uri_contable, days_window, include_descomposicion=False)
        return Response({"ok": True, "summary": summary}, status_code=200)
    except Exception as e:
        tb = traceback.format_exc(limit=12)
        print("[reconcile_summary_head] ERROR:", type(e).__name__, str(e), flush=True)
        print(tb, flush=True)
        return Response(
            {"ok": False, "message": "Error interno en resumen (head)", "error": f"{type(e).__name__}: {e}", "trace": tb},
            status_code=500
        )


@post("/api/reconcile/summary/descomposicion")
async def reconcile_summary_descomposicion(request: Any) -> Response:
    """Devuelve solo la descomposición de movimientos."""
    try:
        form = await request.form()
        uri_extracto, uri_contable, days_window = _parse_form(form)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable son obligatorios."}, status_code=400)

        summary = _build_summary(uri_extracto, uri_contable, days_window, include_descomposicion=True)
        descomposicion = summary.get("descomposicion", {})
        return Response({"ok": True, "descomposicion": descomposicion, "days_window": summary.get("days_window")}, status_code=200)
    except Exception as e:
        tb = traceback.format_exc(limit=12)
        print("[reconcile_summary_descomposicion] ERROR:", type(e).__name__, str(e), flush=True)
        print(tb, flush=True)
        return Response(
            {"ok": False, "message": "Error interno en resumen (descomposición)", "error": f"{type(e).__name__}: {e}", "trace": tb},
            status_code=500
        )

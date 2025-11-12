# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/routes/v1/reconcile_summary.py
from __future__ import annotations

import traceback
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
    _match_one_to_one_by_amount_and_date_window,
    _get_extracto_saldos,
    _get_pilaga_saldos,
)

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

@post("/api/reconcile/summary")
async def reconcile_summary(request: Any) -> Response:
    """
    POST (multipart o x-www-form-urlencoded):
      - uri_extracto   : file://... (obligatorio)
      - uri_contable   : file://... (obligatorio)
      - days_window    : int (opcional, default 5)

    Respuesta:
      {
        ok: true,
        summary: {
          movimientos_pilaga,
          movimientos_banco,
          conciliados_pares,
          no_en_banco,
          no_en_pilaga,
          days_window,
          banco:   { debe, haber, neto },
          pilaga:  { ingresos, egresos, neto },
          diferencia_neto: (banco.neto - pilaga.neto)
        }
      }
    """
    try:
        form = await request.form()
        uri_extracto = form.get("uri_extracto") or form.get("extracto_original_uri") or ""
        uri_contable = form.get("uri_contable") or form.get("contable_original_uri") or ""
        days_window  = int(form.get("days_window") or 5)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable son obligatorios."}, status_code=400)

        path_extracto = _from_file_uri(uri_extracto)
        path_contable = _from_file_uri(uri_contable)

        # 1) Cargar con los mismos loaders del flujo actual
        df_pilaga  = _filter_movements_df(_load_pilaga(path_contable))
        df_banco   = _filter_movements_df(_load_extracto(path_extracto))

        # 2) Totales:
        p_ing, p_egr, p_neto = _sum_pilaga_totals(df_pilaga)
        #    - BANCO: debe/haber a partir de signos, neto = haber - debe
        b_debe, b_haber, b_neto = _sum_pos_neg(df_banco["monto"])

        b_saldo_inicial, b_saldo_final = _get_extracto_saldos(path_extracto)
        p_saldo_inicial, p_saldo_final = _get_pilaga_saldos(path_contable)

        # 3) Métricas de conciliación (igual que /start)
        pairs, sobrantes_p, sobrantes_b = _match_one_to_one_by_amount_and_date_window(df_pilaga, df_banco, days_window)

        total_p = int(len(df_pilaga))
        total_b = int(len(df_banco))
        conc_pairs   = int(len(pairs))
        no_en_banco  = int(len(sobrantes_p))  # en PILAGA pero no en banco
        no_en_pilaga = int(len(sobrantes_b))  # en banco pero no en PILAGA

        summary = {
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
        }

        return Response({"ok": True, "summary": summary}, status_code=200)

    except Exception as e:
        tb = traceback.format_exc(limit=12)
        print("[reconcile_summary] ERROR:", type(e).__name__, str(e), flush=True)
        print(tb, flush=True)
        return Response(
            {"ok": False, "message": "Error interno en resumen", "error": f"{type(e).__name__}: {e}", "trace": tb},
            status_code=500
        )

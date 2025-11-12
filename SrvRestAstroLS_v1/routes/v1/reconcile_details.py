# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/routes/v1/reconcile_details.py
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
from litestar import post
from litestar.response import Response

# Importamos helpers desde reconcile_start (para no duplicar lógica)
from .reconcile_start import (
    _from_file_uri,
    _load_pilaga,
    _load_extracto,
    _match_one_to_one_by_amount_and_date_window,
)

def _rows_for_ui(df: pd.DataFrame, limit: int = 500) -> list[dict]:
    """Convierte a filas serializables para UI (fecha ISO, monto, documento)."""
    if df.empty:
        return []
    df2 = df[["fecha", "monto", "documento"]].copy()
    df2["fecha"] = pd.to_datetime(df2["fecha"], errors="coerce").dt.date.astype(str)
    df2["monto"] = pd.to_numeric(df2["monto"], errors="coerce").fillna(0).round(2)
    return df2.head(limit).to_dict(orient="records")

@post("/api/reconcile/details")
async def reconcile_details(request: Any) -> Response:
    """
    FORM:
      - uri_extracto  (obligatorio)
      - uri_contable  (obligatorio)
      - days_window   (opcional, default 5)
    Devuelve:
      {
        ok: True,
        no_en_banco_rows: [...],   # PILAGA sin banco
        no_en_pilaga_rows: [...],  # Banco sin PILAGA
        counts: { no_en_banco, no_en_pilaga }
      }
    """
    try:
        form = await request.form()
        uri_extracto = form.get("uri_extracto") or form.get("extracto_original_uri") or ""
        uri_contable = form.get("uri_contable") or form.get("contable_original_uri") or ""
        days_window = int(form.get("days_window") or 5)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable."}, status_code=400)

        # Cargar igual que en /api/reconcile/start
        path_extracto = _from_file_uri(uri_extracto)
        path_contable = _from_file_uri(uri_contable)

        df_pilaga = _load_pilaga(path_contable)
        df_banco  = _load_extracto(path_extracto)

        # Reaplicar matching con misma ventana
        pairs, sobrantes_p, sobrantes_b = _match_one_to_one_by_amount_and_date_window(
            df_pilaga, df_banco, days_window
        )

        out = {
            "ok": True,
            "no_en_banco_rows": _rows_for_ui(sobrantes_p, limit=500),
            "no_en_pilaga_rows": _rows_for_ui(sobrantes_b, limit=500),
            "counts": {
                "no_en_banco": int(len(sobrantes_p)),
                "no_en_pilaga": int(len(sobrantes_b)),
            }
        }
        return Response(out, status_code=200)

    except Exception as e:
        return Response({"ok": False, "message": f"Error en details: {type(e).__name__}: {e}"}, status_code=500)

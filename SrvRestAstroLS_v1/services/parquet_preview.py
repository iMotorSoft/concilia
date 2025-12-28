# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/services/parquet_preview.py

from __future__ import annotations

from datetime import date, datetime
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import pandas as pd

from routes.v1.reconcile_start import (
    _load_extracto,
    _load_pilaga,
    _match_one_to_one_by_amount_and_date_window,
)

logger = logging.getLogger(__name__)

MAX_WINDOW_DAYS = 36500


def _path_from_uri(uri: str) -> Optional[Path]:
    if not uri:
        return None
    if uri.startswith("file://"):
        return Path(urlparse(uri).path)
    return Path(uri)


def _to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return value.date()
    except Exception:
        return None


def _iso_date(value: Any) -> Optional[str]:
    d = _to_date(value)
    return d.isoformat() if d else None


def _mock_preview(dataset_ref: str, bank: str, account: str) -> Dict[str, Any]:
    return {
        "missing_months": ["2025-05"],
        "partial_months": [
            {"month": "2025-07", "missing_days": ["2025-07-19", "2025-07-20"]},
        ],
        "outliers": [{"date": "2025-05-31", "declared_file_month": "2025-06"}],
        "range": ["2025-05-31", "2025-07-31"],
        "files": [
            {"name": "06- Junio al 30.xlsx", "range": ["2025-05-31", "2025-06-30"], "days": 30},
            {"name": "07- Julio al 31.xlsx", "range": ["2025-07-01", "2025-07-31"], "days": 29},
        ],
        "dataset_ref": dataset_ref,
        "bank": bank,
        "account": account,
    }


def get_extract_preview(
    dataset_ref: str,
    bank: str,
    account: str,
    *,
    uri_extracto: str | None = None,
    uri_contable: str | None = None,
) -> Dict[str, Any]:
    """
    Devuelve preview para el wizard. Si hay URIs de extracto/contable, calcula
    la ventana máxima real (matching 1→1) y un rango de extracto.
    """
    if dataset_ref == "mock" and not (uri_extracto or uri_contable):
        return _mock_preview(dataset_ref, bank, account)

    preview: Dict[str, Any] = {
        "missing_months": [],
        "partial_months": [],
        "outliers": [],
        "range": [],
        "files": [],
        "dataset_ref": dataset_ref,
        "bank": bank,
        "account": account,
    }

    extracto_path = _path_from_uri(uri_extracto or "")
    contable_path = _path_from_uri(uri_contable or "")

    df_banco = None
    df_pilaga = None
    try:
        if extracto_path and extracto_path.exists():
            df_banco = _load_extracto(extracto_path)
            if "fecha" in df_banco.columns:
                fechas = pd.to_datetime(df_banco["fecha"], errors="coerce").dropna()
                if not fechas.empty:
                    preview["range"] = [
                        fechas.min().date().isoformat(),
                        fechas.max().date().isoformat(),
                    ]
                    preview["files"] = [
                        {
                            "name": extracto_path.name,
                            "range": preview["range"],
                            "days": int((fechas.max().date() - fechas.min().date()).days),
                        }
                    ]
        if contable_path and contable_path.exists():
            df_pilaga = _load_pilaga(contable_path)
    except Exception as exc:
        logger.exception("Preview: fallo al leer extracto/contable: %s", exc)
        return preview

    try:
        if df_banco is not None and df_pilaga is not None:
            pairs, _, _ = _match_one_to_one_by_amount_and_date_window(
                df_pilaga,
                df_banco,
                days_window=MAX_WINDOW_DAYS,
            )
            if not pairs.empty:
                row = pairs.loc[pairs["date_diff_days"].idxmax()]
                fecha_b = _to_date(row.get("fecha_b"))
                fecha_p = _to_date(row.get("fecha_p"))
                range_from = None
                range_to = None
                if fecha_b and fecha_p:
                    if fecha_b <= fecha_p:
                        range_from, range_to = fecha_b, fecha_p
                    else:
                        range_from, range_to = fecha_p, fecha_b
                preview["window_max"] = {
                    "days": int(row.get("date_diff_days") or 0),
                    "range": [
                        range_from.isoformat() if range_from else None,
                        range_to.isoformat() if range_to else None,
                    ],
                    "pair": {
                        "extracto": {
                            "fecha": _iso_date(fecha_b),
                            "documento": str(row.get("documento_b") or ""),
                            "monto": float(row.get("monto_r") or 0),
                        },
                        "contable": {
                            "fecha": _iso_date(fecha_p),
                            "documento": str(row.get("documento_p") or ""),
                            "monto": float(row.get("monto_r") or 0),
                        },
                    },
                    "matched_count": int(len(pairs)),
                }
    except Exception as exc:
        logger.exception("Preview: fallo al calcular ventana maxima: %s", exc)

    return preview

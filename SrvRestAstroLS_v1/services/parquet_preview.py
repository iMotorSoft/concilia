# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/services/parquet_preview.py

from __future__ import annotations

from typing import Any, Dict


def get_extract_preview(dataset_ref: str, bank: str, account: str) -> Dict[str, Any]:
    """
    Devuelve un preview mock para el wizard (sin leer Parquet real).
    """
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

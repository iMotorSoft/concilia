from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from routes.v1.reconcile_details import (
    _build_sicom_context,
    _compute_pipeline,
    _load_frames,
    _sicom_bank_context,
    _sicom_pilaga_context,
)
from routes.v1.reconcile_start import _build_sicom_insights, _extract_op_match_key
from routes.v1.reconcile_start import _load_sicom
from routes.v1.reconcile_summary import _filter_movements_df


DATA_DIR = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SpendIQ/Doc/FCE/Conciliacion/SICOM")
DAYS_WINDOW = 5

CASES = [
    {
        "name": "Prueba 1 - Noviembre Base",
        "extracto": "11- Noviembre al 30.xlsx",
        "pilaga": "salida(261).xlsx",
        "sicom": "Base.xlsx",
        "bank_scope": "patagonia",
        "account_scope": "100-393300535-000",
    },
    {
        "name": "Prueba 2 - Noviembre SICOM mensual",
        "extracto": "11- Noviembre al 30.xlsx",
        "pilaga": "salida(261).xlsx",
        "sicom": "SICON CRUDO noviembre 2025.xlsx",
        "bank_scope": "patagonia",
        "account_scope": "100-393300535-000",
    },
    {
        "name": "Prueba 3 - Marzo 2026",
        "extracto": "2026_03-EXTRACTO.xlsx",
        "pilaga": "2026_03-PILAGA.xlsx",
        "sicom": "2026_03_SICON MARZO CRUDO.xlsx",
        "bank_scope": "patagonia",
        "account_scope": "100-393300535-000",
    },
]


def uri(name: str) -> str:
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(path)
    return f"file://{path.as_posix()}"


def amount_sum(df: pd.DataFrame, column: str = "monto") -> float:
    if df is None or df.empty or column not in df.columns:
        return 0.0
    return round(float(pd.to_numeric(df[column], errors="coerce").fillna(0.0).sum()), 2)


def group_amount(groups: list[dict[str, Any]]) -> float:
    return round(float(sum(float(g.get("monto_total") or 0.0) for g in groups)), 2)


def pilaga_rows_in_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in groups:
        rows.extend(group.get("pilaga_rows") or [])
        if group.get("pilaga_row"):
            rows.append(group["pilaga_row"])
    return rows


def bank_rows_in_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in groups:
        if group.get("bank_row"):
            rows.append(group["bank_row"])
        rows.extend(group.get("bank_rows") or [])
    return rows


def op_stats(rows: list[dict[str, Any]], sicom_ctx: dict[str, Any]) -> dict[str, Any]:
    total = len(rows)
    with_op = 0
    with_sicom_op = 0
    with_sicom_exact = 0
    sample_missing: list[dict[str, Any]] = []

    for row in rows:
        documento = row.get("documento") or ""
        monto = row.get("monto")
        op_key = _extract_op_match_key(documento)
        if op_key:
            with_op += 1
        elif len(sample_missing) < 5:
            sample_missing.append({
                "fecha": row.get("fecha"),
                "monto": row.get("monto"),
                "documento": documento,
            })

        ctx = _sicom_pilaga_context(documento, monto, sicom_ctx)
        if ctx and int(ctx.get("op_match_count") or 0) > 0:
            with_sicom_op += 1
        if ctx and int(ctx.get("exact_match_count") or 0) > 0:
            with_sicom_exact += 1

    return {
        "total_rows": total,
        "with_op_in_documento": with_op,
        "with_sicom_op_match": with_sicom_op,
        "with_sicom_exact_amount_match": with_sicom_exact,
        "sample_without_op": sample_missing,
    }


def bank_sicom_lot_stats(rows: list[dict[str, Any]], sicom_ctx: dict[str, Any]) -> dict[str, int]:
    total = len(rows)
    with_lot = 0
    for row in rows:
        ctx = _sicom_bank_context(row.get("fecha"), row.get("monto"), sicom_ctx)
        if ctx and int(ctx.get("match_count") or 0) > 0:
            with_lot += 1
    return {"total_rows": total, "with_sicom_lot_match": with_lot}


def run_case(case: dict[str, str]) -> dict[str, Any]:
    uri_extracto = uri(case["extracto"])
    uri_contable = uri(case["pilaga"])
    uri_sicom = uri(case["sicom"])

    df_pilaga, df_banco, df_sicom, scope_info = _load_frames(
        uri_extracto,
        uri_contable,
        uri_sicom,
        case["bank_scope"],
        case["account_scope"],
    )
    df_pilaga = _filter_movements_df(df_pilaga)
    df_banco = _filter_movements_df(df_banco)
    df_sicom_full = _load_sicom(DATA_DIR / case["sicom"])

    pipeline = _compute_pipeline(df_pilaga, df_banco, DAYS_WINDOW)
    pairs = pipeline["pairs_df"]
    approved = pipeline["approved"]
    suggested = pipeline["suggested"]
    sobrantes_p = pipeline["sobrantes_p"]
    sobrantes_b = pipeline["sobrantes_b"]
    sicom_ctx = _build_sicom_context(df_sicom)
    sicom = _build_sicom_insights(
        df_sicom_full,
        df_pilaga,
        df_banco,
        bank_scope=case["bank_scope"],
        account_scope=case["account_scope"],
        path_extracto=DATA_DIR / case["extracto"],
    )

    pair_rows = [
        {
            "fecha": row.get("fecha_p"),
            "monto": row.get("monto_p"),
            "documento": row.get("documento_p"),
        }
        for _, row in pairs.iterrows()
    ]
    approved_pilaga_rows = pilaga_rows_in_groups(approved)
    suggested_pilaga_rows = pilaga_rows_in_groups(suggested)
    sobrantes_p_rows = [
        {"fecha": row.get("fecha"), "monto": row.get("monto"), "documento": row.get("documento")}
        for _, row in sobrantes_p.iterrows()
    ]

    return {
        "name": case["name"],
        "inputs": {
            "extracto": case["extracto"],
            "pilaga": case["pilaga"],
            "sicom": case["sicom"],
            "days_window": DAYS_WINDOW,
        },
        "totals": {
            "pilaga_rows": int(len(df_pilaga)),
            "extracto_rows": int(len(df_banco)),
            "pilaga_amount": amount_sum(df_pilaga),
            "extracto_amount": amount_sum(df_banco),
        },
        "conciliation_partition": {
            "direct_1_to_1": {
                "pairs": int(len(pairs)),
                "pilaga_rows": int(len(pairs)),
                "extracto_rows": int(len(pairs)),
                "amount": round(float(pd.to_numeric(pairs.get("monto_r"), errors="coerce").fillna(0.0).sum()), 2) if not pairs.empty else 0.0,
            },
            "grouped_n_pilaga_to_1_extracto_approved": {
                "groups": int(len(approved)),
                "pilaga_rows": len(approved_pilaga_rows),
                "extracto_rows": len(bank_rows_in_groups(approved)),
                "amount": group_amount(approved),
            },
            "suggested_for_review": {
                "groups": int(len(suggested)),
                "pilaga_rows": len(suggested_pilaga_rows),
                "extracto_rows": len(bank_rows_in_groups(suggested)),
                "amount": group_amount(suggested),
            },
            "not_conciliated_after_pipeline": {
                "pilaga_rows_no_extracto": int(len(sobrantes_p)),
                "pilaga_amount_no_extracto": amount_sum(sobrantes_p),
                "extracto_rows_no_pilaga": int(len(sobrantes_b)),
                "extracto_amount_no_pilaga": amount_sum(sobrantes_b),
            },
        },
        "op_traceability": {
            "direct_1_to_1": op_stats(pair_rows, sicom_ctx),
            "grouped_approved": op_stats(approved_pilaga_rows, sicom_ctx),
            "suggested": op_stats(suggested_pilaga_rows, sicom_ctx),
            "not_conciliated_pilaga": op_stats(sobrantes_p_rows, sicom_ctx),
        },
        "sicom_lot_traceability": {
            "grouped_approved_extracto_rows": bank_sicom_lot_stats(bank_rows_in_groups(approved), sicom_ctx),
            "suggested_extracto_rows": bank_sicom_lot_stats(bank_rows_in_groups(suggested), sicom_ctx),
            "not_conciliated_extracto_rows": bank_sicom_lot_stats(
                [{"fecha": row.get("fecha"), "monto": row.get("monto"), "documento": row.get("documento")} for _, row in sobrantes_b.iterrows()],
                sicom_ctx,
            ),
        },
        "sicom_final_bridge": sicom.get("final_reconciliation", {}),
        "sicom_scope": sicom.get("scope", {}),
        "sicom_source": sicom.get("source", {}),
        "scope_info": scope_info,
    }


def main() -> int:
    results = [run_case(case) for case in CASES]
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

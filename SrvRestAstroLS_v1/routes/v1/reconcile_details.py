# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/routes/v1/reconcile_details.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Tuple
from urllib.parse import urlparse

import pandas as pd
import time
from litestar import post
from litestar.response import Response

# Importamos helpers desde reconcile_start (para no duplicar lógica)
from .reconcile_start import (
    _from_file_uri,
    _load_pilaga,
    _load_extracto,
    _load_sicom,
    _resolve_case_scope,
    _extract_op_key,
    _extract_op_match_key,
    _match_one_to_one_by_amount_and_date_window,
)
from .reconcile_start import _match_one_to_one_by_amount_and_date_window as _match_1a1  # alias legible

def _rows_for_ui(df: pd.DataFrame, limit: int = 500) -> list[dict]:
    """Convierte a filas serializables para UI (fecha ISO, monto, documento)."""
    if df.empty:
        return []
    df2 = df[["fecha", "monto", "documento"]].copy()
    df2["fecha"] = pd.to_datetime(df2["fecha"], errors="coerce").dt.date.astype(str)
    df2["monto"] = pd.to_numeric(df2["monto"], errors="coerce").fillna(0).round(2)
    return df2.head(limit).to_dict(orient="records")

def _parse_common_form(form: Any) -> Tuple[str, str, str, str, str, int]:
    uri_extracto = form.get("uri_extracto") or form.get("extracto_original_uri") or ""
    uri_contable = form.get("uri_contable") or form.get("contable_original_uri") or ""
    uri_sicom = form.get("uri_sicom") or form.get("sicom_original_uri") or ""
    bank_scope = str(form.get("bank_scope") or "").strip()
    account_scope = str(form.get("account_scope") or "").strip()
    days_window = int(form.get("days_window") or 5)
    return uri_extracto, uri_contable, uri_sicom, bank_scope, account_scope, days_window


def _load_frames(
    uri_extracto: str,
    uri_contable: str,
    uri_sicom: str = "",
    bank_scope: str = "",
    account_scope: str = "",
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None, dict[str, Any]]:
    path_extracto = _from_file_uri(uri_extracto)
    path_contable = _from_file_uri(uri_contable)
    df_pilaga = _load_pilaga(path_contable)
    df_banco = _load_extracto(path_extracto)
    df_sicom = None
    scope_info: dict[str, Any] = {}
    if uri_sicom:
        scope_info = _resolve_case_scope(path_extracto, bank_scope=bank_scope, account_scope=account_scope)
        df_sicom = _load_sicom(_from_file_uri(uri_sicom))
        sicom_bank_scopes = set(scope_info.get("sicom_bank_scopes") or [])
        if sicom_bank_scopes:
            df_sicom = df_sicom[df_sicom["bank_scope"].isin(sicom_bank_scopes)].copy()
    return df_pilaga, df_banco, df_sicom, scope_info


def _row_amount_abs(value: Any) -> float:
    return round(abs(float(pd.to_numeric(value, errors="coerce") or 0.0)), 2)


def _row_date_iso(value: Any) -> str:
    dt = pd.to_datetime(value, errors="coerce")
    return dt.date().isoformat() if pd.notna(dt) else ""


def _build_sicom_context(df_sicom: pd.DataFrame | None) -> dict[str, Any]:
    if df_sicom is None or df_sicom.empty:
        return {"used": False}

    work = df_sicom.copy()
    work["fecha_pago"] = pd.to_datetime(work["fecha_pago"], errors="coerce")
    work["imp_neto"] = pd.to_numeric(work["imp_neto"], errors="coerce").fillna(0.0)
    work["order_de_p"] = work["order_de_p"].astype(str).str.strip()
    work["op_match_key"] = work["order_de_p"].apply(_extract_op_match_key)
    work["nro_pago"] = work["nro_pago"].astype(str).str.strip()
    work["banco_raw"] = work["banco_raw"].astype(str).str.strip()

    lotes = (
        work.loc[work["nro_pago"] != ""]
        .groupby(["fecha_pago", "banco_raw", "nro_pago"], dropna=False)
        .agg(
            imp_neto=("imp_neto", "sum"),
            op_keys=("order_de_p", lambda s: sorted({v for v in s if v})),
            op_match_keys=("op_match_key", lambda s: sorted({v for v in s if v})),
        )
        .reset_index()
        .sort_values(["fecha_pago", "banco_raw", "nro_pago"], kind="stable")
    )

    lot_lookup: dict[tuple[str, float], list[dict[str, Any]]] = {}
    for _, row in lotes.iterrows():
        key = (_row_date_iso(row["fecha_pago"]), _row_amount_abs(row["imp_neto"]))
        lot_lookup.setdefault(key, []).append({
            "fecha_pago": _row_date_iso(row["fecha_pago"]),
            "banco_raw": str(row["banco_raw"] or ""),
            "nro_pago": str(row["nro_pago"] or ""),
            "imp_neto": round(float(row["imp_neto"] or 0.0), 2),
            "op_keys": list(row["op_keys"] or []),
            "op_match_keys": list(row["op_match_keys"] or []),
            "op_count": len(row["op_keys"] or []),
        })

    op_lookup_by_key: dict[str, list[dict[str, Any]]] = {}
    op_lookup_exact: dict[tuple[str, float], list[dict[str, Any]]] = {}
    for _, row in work.iterrows():
        op_match_key = str(row["op_match_key"] or "").strip()
        if not op_match_key:
            continue
        entry = {
            "op_key": str(row["order_de_p"] or "").strip(),
            "op_match_key": op_match_key,
            "fecha_pago": _row_date_iso(row["fecha_pago"]),
            "banco_raw": str(row["banco_raw"] or ""),
            "nro_pago": str(row["nro_pago"] or ""),
            "imp_neto": round(float(row["imp_neto"] or 0.0), 2),
        }
        op_lookup_by_key.setdefault(op_match_key, []).append(entry)
        op_lookup_exact.setdefault((op_match_key, _row_amount_abs(row["imp_neto"])), []).append(entry)

    return {
        "used": True,
        "lot_lookup": lot_lookup,
        "op_lookup_by_key": op_lookup_by_key,
        "op_lookup_exact": op_lookup_exact,
    }


def _sicom_bank_context(fecha: Any, monto: Any, sicom_ctx: dict[str, Any], limit: int = 5) -> dict[str, Any] | None:
    if not sicom_ctx.get("used"):
        return None
    matches = sicom_ctx.get("lot_lookup", {}).get((_row_date_iso(fecha), _row_amount_abs(monto)), [])
    if not matches:
        return None
    return {
        "match_count": len(matches),
        "lot_matches": matches[:limit],
    }


def _sicom_pilaga_context(documento: Any, monto: Any, sicom_ctx: dict[str, Any], limit: int = 5) -> dict[str, Any] | None:
    if not sicom_ctx.get("used"):
        return None
    op_key = _extract_op_key(documento)
    op_match_key = _extract_op_match_key(documento)
    if not op_match_key:
        return None
    exact_matches = sicom_ctx.get("op_lookup_exact", {}).get((op_match_key, _row_amount_abs(monto)), [])
    op_matches = sicom_ctx.get("op_lookup_by_key", {}).get(op_match_key, [])
    return {
        "op_key": op_key or op_match_key,
        "op_match_key": op_match_key,
        "exact_match_count": len(exact_matches),
        "op_match_count": len(op_matches),
        "exact_matches": exact_matches[:limit],
        "op_matches": op_matches[:limit],
    }


def _entry_matches_lot(entry: dict[str, Any], lot: dict[str, Any]) -> bool:
    return (
        str(entry.get("nro_pago") or "").strip() == str(lot.get("nro_pago") or "").strip()
        and str(entry.get("banco_raw") or "").strip() == str(lot.get("banco_raw") or "").strip()
        and str(entry.get("fecha_pago") or "").strip() == str(lot.get("fecha_pago") or "").strip()
    )


def _restrict_pilaga_sicom_context_to_lot(row: dict[str, Any], lot: dict[str, Any] | None) -> dict[str, Any]:
    if not lot:
        return row
    sicom = row.get("sicom")
    if not isinstance(sicom, dict):
        return row

    exact_matches = [m for m in (sicom.get("exact_matches") or []) if _entry_matches_lot(m, lot)]
    op_matches = [m for m in (sicom.get("op_matches") or []) if _entry_matches_lot(m, lot)]
    row["sicom"] = {
        **sicom,
        "exact_match_count": len(exact_matches),
        "op_match_count": len(op_matches),
        "exact_matches": exact_matches,
        "op_matches": op_matches,
    }
    return row


def _group_has_sicom_support(group: dict[str, Any], sicom_ctx: dict[str, Any] | None) -> bool:
    if not sicom_ctx or not sicom_ctx.get("used"):
        return True
    basis = group.get("sicom_basis") or {}
    if basis.get("mandatory"):
        return True

    bank_row = group.get("bank_row") or {}
    if bank_row and _sicom_bank_context(bank_row.get("fecha"), bank_row.get("monto"), sicom_ctx):
        return True

    pilaga_rows = group.get("pilaga_rows") or []
    if not pilaga_rows:
        pilaga_row = group.get("pilaga_row")
        pilaga_rows = [pilaga_row] if pilaga_row else []
    if not pilaga_rows:
        return False

    for row in pilaga_rows:
        ctx = _sicom_pilaga_context(row.get("documento"), row.get("monto"), sicom_ctx)
        if not ctx or int(ctx.get("op_match_count") or 0) <= 0:
            return False
    return True


def _remove_group_usage(groups: list[dict[str, Any]], used_p: set[int], used_b: set[int]) -> tuple[set[int], set[int]]:
    for group in groups:
        if group.get("_row_id_b") is not None:
            used_b.discard(int(group["_row_id_b"]))
        if group.get("_row_id_p") is not None:
            used_p.discard(int(group["_row_id_p"]))
        for pid in group.get("_row_ids_p", []):
            used_p.discard(int(pid))
        for bid in group.get("_row_ids_b", []):
            used_b.discard(int(bid))
    return used_p, used_b


def _audit_sicom_rejected_group(group: dict[str, Any], sicom_ctx: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(group or {})
    missing_ops: list[str] = []
    mismatched_ops: list[str] = []
    for row in out.get("pilaga_rows") or []:
        ctx = _sicom_pilaga_context(row.get("documento"), row.get("monto"), sicom_ctx or {})
        op = _extract_op_key(row.get("documento")) or _extract_op_match_key(row.get("documento")) or str(row.get("documento") or "")
        if not ctx or int(ctx.get("op_match_count") or 0) <= 0:
            missing_ops.append(op)
        elif int(ctx.get("exact_match_count") or 0) <= 0:
            mismatched_ops.append(op)

    reasons: list[str] = []
    if not _sicom_bank_context((out.get("bank_row") or {}).get("fecha"), (out.get("bank_row") or {}).get("monto"), sicom_ctx or {}):
        reasons.append("sin lote SICOM para fecha + importe del banco")
    if missing_ops:
        reasons.append("OP sin SICOM: " + ", ".join(sorted(set(missing_ops))))
    if mismatched_ops:
        reasons.append("OP sin match exacto de importe: " + ", ".join(sorted(set(mismatched_ops))))
    if not reasons:
        reasons.append("sin respaldo SICOM suficiente")

    out["estado"] = "sicom_auditoria"
    out["audit_status"] = "rechazado_sicom"
    out["audit_reason"] = "; ".join(reasons)
    out["audit_visible"] = True
    out["consumes_rows"] = False
    return out


def _rows_for_ui_with_sicom(df: pd.DataFrame, sicom_ctx: dict[str, Any], kind: str, limit: int = 500) -> list[dict]:
    if df.empty:
        return []
    rows: list[dict] = []
    for _, row in df.head(limit).iterrows():
        out = {
            "fecha": _row_date_iso(row.get("fecha")),
            "monto": round(float(pd.to_numeric(row.get("monto"), errors="coerce") or 0.0), 2),
            "documento": str(row.get("documento") or ""),
        }
        if kind == "pilaga":
            out["sicom"] = _sicom_pilaga_context(out["documento"], out["monto"], sicom_ctx)
        else:
            out["sicom"] = _sicom_bank_context(out["fecha"], out["monto"], sicom_ctx)
        rows.append(out)
    return rows


def _enrich_simple_row_dict(row: dict[str, Any], sicom_ctx: dict[str, Any], kind: str) -> dict[str, Any]:
    out = dict(row or {})
    if kind == "pilaga":
        out["sicom"] = _sicom_pilaga_context(out.get("documento"), out.get("monto"), sicom_ctx)
    else:
        out["sicom"] = _sicom_bank_context(out.get("fecha"), out.get("monto"), sicom_ctx)
    return out


# Defaults para N→1 (aprobados y sugeridos comparten heurística base)
N1_MAX_COMBO_DEFAULT = 6
N1_TOL_APPROVED = 1.0   # dif aceptada para considerarlo "agrupado" (≤ $1)
N1_TOL_SUGGESTED = 5.0  # dif amplia para sugeridos; todo lo que supere la tol aprobada queda aquí
N1_CAND_LIMIT_DEFAULT = 20


def _to_row_id(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Agrega un id incremental estable para evitar reusar filas."""
    d = df.copy()
    d[f"_row_id_{prefix}"] = range(len(d))
    return d


def _prepare_row(row: pd.Series) -> dict:
    """Serializa una fila banco/PILAGA a dict simple."""
    return {
        "fecha": pd.to_datetime(row.get("fecha"), errors="coerce").date().isoformat() if pd.notna(row.get("fecha")) else "",
        "monto": float(pd.to_numeric(row.get("monto"), errors="coerce") or 0.0),
        "documento": str(row.get("documento") or ""),
    }

def _serialize_pair(row: pd.Series, sicom_ctx: dict[str, Any] | None = None) -> dict:
    """Convierte un merge 1→1 a dict simple para UI."""
    monto = row.get("monto_r")
    if pd.isna(monto):
        monto = row.get("monto_p") if pd.notna(row.get("monto_p")) else row.get("monto_b")
    try:
        monto_val = float(monto)
    except Exception:
        monto_val = 0.0
    out = {
        "fecha_banco": pd.to_datetime(row.get("fecha_b"), errors="coerce").date().isoformat() if pd.notna(row.get("fecha_b")) else "",
        "fecha_pilaga": pd.to_datetime(row.get("fecha_p"), errors="coerce").date().isoformat() if pd.notna(row.get("fecha_p")) else "",
        "monto": monto_val,
        "documento_banco": str(row.get("documento_b") or ""),
        "documento_pilaga": str(row.get("documento_p") or ""),
        "date_diff_days": int(row.get("date_diff_days") or 0),
    }
    if sicom_ctx and sicom_ctx.get("used"):
        out["sicom_bank"] = _sicom_bank_context(row.get("fecha_b"), row.get("monto_b"), sicom_ctx)
        out["sicom_pilaga"] = _sicom_pilaga_context(row.get("documento_p"), row.get("monto_p"), sicom_ctx)
    return out


def _find_combo(
    candidates: list[dict],
    target: float,
    max_combo: int,
    tol_amount: float,
    min_combo: int = 2,
) -> list[dict]:
    """
    Busca una combinación (2..max_combo) cuya suma se acerque al target dentro de la tolerancia.
    Estrategia DFS controlada, candidatos ya limitados/sorteados por magnitud.
    """
    n = len(candidates)
    best: list[dict] = []
    target_abs = abs(target)

    def dfs(start: int, current: list[dict], current_sum: float):
        nonlocal best
        # Si ya encontramos combinación dentro de tolerancia y cumple el tamaño mínimo, devolver
        if len(current) >= min_combo and abs(current_sum - target) <= tol_amount:
            best = list(current)
            return True  # encontrada combinación exacta dentro de tol
        if len(current) >= max_combo:
            return False
        for i in range(start, n):
            c = candidates[i]
            next_sum = current_sum + c["monto"]
            # poda simple: si nos pasamos mucho, seguir igual porque hay montos negativos/positivos del mismo signo (ya filtrado por signo)
            current.append(c)
            found = dfs(i + 1, current, next_sum)
            current.pop()
            if found:
                return True
        return False

    dfs(0, [], 0.0)
    return best


def _compute_pairs(df_p: pd.DataFrame, df_b: pd.DataFrame, days_window: int):
    """Replica el matcher 1→1 pero conservando ids para pipeline."""
    p = df_p.copy()
    b = df_b.copy()
    if "_row_id_p" not in p.columns:
        p["_row_id_p"] = range(len(p))
    if "_row_id_b" not in b.columns:
        b["_row_id_b"] = range(len(b))
    p["monto_r"] = p["monto"].round(2)
    b["monto_r"] = b["monto"].round(2)

    merged = p.merge(b, on="monto_r", suffixes=("_p", "_b"))
    merged["date_diff_days"] = (merged["fecha_p"] - merged["fecha_b"]).abs().dt.days
    merged = merged[merged["date_diff_days"] <= abs(int(days_window))]
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

    pairs_df = pd.DataFrame(selected_rows, columns=merged.columns) if selected_rows else merged.iloc[0:0].copy()
    return pairs_df, used_p, used_b


def _build_sicom_mandated_groups(
    df_p: pd.DataFrame,
    df_b: pd.DataFrame,
    used_p: set[int],
    used_b: set[int],
    sicom_ctx: dict[str, Any] | None,
) -> tuple[list[dict], set[int], set[int]]:
    """
    Cuando un movimiento bancario matchea un lote SICOM por fecha + importe,
    el Nro Pago manda: las componentes contables salen de las OP de ese lote.
    La fecha PILAGA no filtra estos componentes; SICOM es la fuente de verdad
    para explicar el agregado bancario.
    """
    if not sicom_ctx or not sicom_ctx.get("used"):
        return [], used_p, used_b

    p = df_p.copy()
    b = df_b.copy()
    if p.empty or b.empty:
        return [], used_p, used_b

    p["fecha"] = pd.to_datetime(p["fecha"], errors="coerce")
    b["fecha"] = pd.to_datetime(b["fecha"], errors="coerce")
    p["monto"] = pd.to_numeric(p["monto"], errors="coerce").fillna(0.0)
    b["monto"] = pd.to_numeric(b["monto"], errors="coerce").fillna(0.0)
    p["_op_match_key"] = p["documento"].apply(_extract_op_match_key)

    groups: list[dict] = []
    bank_rows = b.sort_values(by="monto", key=lambda s: s.abs(), ascending=False)
    for _, bank_row in bank_rows.iterrows():
        row_id_b = int(bank_row["_row_id_b"])
        if row_id_b in used_b:
            continue

        bank_context = _sicom_bank_context(bank_row.get("fecha"), bank_row.get("monto"), sicom_ctx, limit=20)
        lot_matches = list((bank_context or {}).get("lot_matches") or [])
        if not lot_matches:
            continue

        lot = lot_matches[0]
        op_match_keys = {str(v).strip() for v in lot.get("op_match_keys") or [] if str(v).strip()}
        if not op_match_keys:
            continue

        target = float(bank_row["monto"])
        target_sign = 1 if target >= 0 else -1
        combo_by_id: dict[int, dict[str, Any]] = {}
        op_lookup = sicom_ctx.get("op_lookup_by_key", {}) or {}

        for op_match_key in sorted(op_match_keys):
            op_sicom_rows = [
                row
                for row in list(op_lookup.get(op_match_key) or [])
                if _entry_matches_lot(row, lot)
            ]
            if not op_sicom_rows:
                continue
            op_sicom_amount = round(sum(abs(float(r.get("imp_neto") or 0.0)) for r in op_sicom_rows), 2)
            op_pilaga = p[
                (p["_op_match_key"].eq(op_match_key)) &
                (~p["_row_id_p"].isin(used_p)) &
                (p["monto"].apply(lambda x: (x >= 0) == (target_sign >= 0)))
            ].copy()
            if op_pilaga.empty:
                continue

            op_pilaga = op_pilaga.sort_values(["fecha", "_row_id_p"], kind="stable")
            exact_selected: dict[int, dict[str, Any]] = {}
            exact_used: set[int] = set()
            for srow in sorted(op_sicom_rows, key=lambda r: (str(r.get("nro_pago") or ""), abs(float(r.get("imp_neto") or 0.0)))):
                amount_abs = _row_amount_abs(srow.get("imp_neto"))
                matches = op_pilaga[
                    (~op_pilaga["_row_id_p"].isin(exact_used)) &
                    (op_pilaga["monto"].abs().round(2).eq(amount_abs))
                ]
                if matches.empty:
                    continue
                prow = matches.iloc[0]
                pid = int(prow["_row_id_p"])
                exact_used.add(pid)
                exact_selected[pid] = {
                    "_row_id_p": pid,
                    "fecha": prow["fecha"],
                    "monto": float(prow["monto"]),
                    "documento": prow.get("documento", ""),
                }

            exact_amount = round(sum(abs(item["monto"]) for item in exact_selected.values()), 2)
            all_amount = round(float(op_pilaga["monto"].abs().sum()), 2)
            if exact_selected and abs(exact_amount - op_sicom_amount) <= N1_TOL_APPROVED:
                selected_items = list(exact_selected.values())
            elif abs(all_amount - op_sicom_amount) <= N1_TOL_APPROVED:
                selected_items = [
                    {
                        "_row_id_p": int(prow["_row_id_p"]),
                        "fecha": prow["fecha"],
                        "monto": float(prow["monto"]),
                        "documento": prow.get("documento", ""),
                    }
                    for _, prow in op_pilaga.iterrows()
                ]
            elif exact_selected:
                selected_items = list(exact_selected.values())
            else:
                selected_items = [
                    {
                        "_row_id_p": int(prow["_row_id_p"]),
                        "fecha": prow["fecha"],
                        "monto": float(prow["monto"]),
                        "documento": prow.get("documento", ""),
                    }
                    for _, prow in op_pilaga.iterrows()
                ]

            for item in selected_items:
                combo_by_id[int(item["_row_id_p"])] = item

        combo = list(combo_by_id.values())
        combo.sort(key=lambda item: (str(_extract_op_match_key(item.get("documento"))), pd.to_datetime(item.get("fecha"), errors="coerce"), int(item["_row_id_p"])))

        used_b.add(row_id_b)
        for item in combo:
            used_p.add(int(item["_row_id_p"]))

        pilaga_rows = [_prepare_row(pd.Series(item)) for item in combo]
        grupo_sum = round(sum(float(item["monto"]) for item in combo), 2)
        diff = round(grupo_sum - target, 2)
        groups.append({
            "bank_row": _prepare_row(bank_row),
            "pilaga_rows": pilaga_rows,
            "monto_total": grupo_sum,
            "estado": "sicom_lote",
            "diff": diff,
            "direction": "sicom_lote_to_bank",
            "_row_id_b": row_id_b,
            "_row_ids_p": [int(item["_row_id_p"]) for item in combo],
            "sicom_basis": {
                "mandatory": True,
                "match_count": len(lot_matches),
                "selected_lot": lot,
                "nro_pago": lot.get("nro_pago"),
                "banco_raw": lot.get("banco_raw"),
                "fecha_pago": lot.get("fecha_pago"),
                "op_keys": lot.get("op_keys") or [],
                "op_match_keys": sorted(op_match_keys),
                "lote_amount": round(float(lot.get("imp_neto") or 0.0), 2),
                "pilaga_amount": grupo_sum,
                "diff_vs_bank": diff,
            },
        })

    return groups, used_p, used_b


def _build_groups_pipeline(
    df_p: pd.DataFrame,
    df_b: pd.DataFrame,
    used_p: set[int],
    used_b: set[int],
    days_window: int,
    tol_amount: float,
    estado: str,
    min_combo: int = 2,
):
    """Genera grupos N→1 usando sobrantes actuales. Marca usados banco/PILAGA."""
    groups: list[dict] = []
    total_amount = 0.0

    # Filtrar sobrantes según usados
    sobrantes_p = df_p[~df_p["_row_id_p"].isin(used_p)].copy()
    sobrantes_b = df_b[~df_b["_row_id_b"].isin(used_b)].copy()

    sobrantes_p["fecha"] = pd.to_datetime(sobrantes_p["fecha"], errors="coerce")
    sobrantes_b["fecha"] = pd.to_datetime(sobrantes_b["fecha"], errors="coerce")
    sobrantes_p["monto"] = pd.to_numeric(sobrantes_p["monto"], errors="coerce")
    sobrantes_b["monto"] = pd.to_numeric(sobrantes_b["monto"], errors="coerce")

    sobrantes_b = sobrantes_b.sort_values(by="monto", key=lambda s: s.abs(), ascending=False)

    for _, bank_row in sobrantes_b.iterrows():
        target = float(bank_row["monto"])
        sign = 1 if target >= 0 else -1
        fecha_b = bank_row["fecha"]
        row_id_b = int(bank_row["_row_id_b"])

        # Candidatos PILAGA
        cands_df = sobrantes_p[
            (sobrantes_p["monto"].apply(lambda x: (x >= 0) == (sign >= 0))) &
            (~sobrantes_p["_row_id_p"].isin(used_p))
        ].copy()

        if fecha_b is not None and pd.notna(fecha_b):
            cands_df = cands_df[
                cands_df["fecha"].notna() &
                ((cands_df["fecha"] - fecha_b).abs() <= pd.to_timedelta(days_window, unit="D"))
            ]

        cands_df = cands_df[abs(cands_df["monto"]) <= abs(target) + tol_amount]
        cands_df = cands_df.sort_values(by="monto", key=lambda s: s.abs(), ascending=False).head(N1_CAND_LIMIT_DEFAULT)

        candidates = []
        for _, row in cands_df.iterrows():
            candidates.append({
                "_row_id_p": int(row["_row_id_p"]),
                "fecha": row["fecha"],
                "monto": float(row["monto"]),
                "documento": row.get("documento", ""),
            })

        if not candidates:
            continue

        combo = _find_combo(candidates, target, max_combo=N1_MAX_COMBO_DEFAULT, tol_amount=tol_amount, min_combo=min_combo)
        if not combo:
            continue

        # registrar uso
        used_b.add(row_id_b)
        for c in combo:
            used_p.add(c["_row_id_p"])

        pilaga_rows = [_prepare_row(pd.Series(c)) for c in combo]
        grupo_sum = sum(c["monto"] for c in combo)
        groups.append({
            "bank_row": _prepare_row(bank_row),
            "pilaga_rows": pilaga_rows,
            "monto_total": round(grupo_sum, 2),
            "estado": estado,
            "diff": round(grupo_sum - target, 2),
            "direction": "p_to_bank",  # target = banco, componentes = PILAGA
            "_row_id_b": row_id_b,
            "_row_ids_p": [c["_row_id_p"] for c in combo],
        })
        total_amount += grupo_sum

    return groups, round(total_amount, 2), used_p, used_b


def _build_groups_pipeline_bank_to_pilaga(
    df_p: pd.DataFrame,
    df_b: pd.DataFrame,
    used_p: set[int],
    used_b: set[int],
    days_window: int,
    tol_amount: float,
    estado: str,
    min_combo: int = 2,
):
    """
    Variante simétrica 1→N: combina movimientos de BANCO (mismo signo) para acercarse
    a un movimiento de PILAGA dentro de tolerancia.
    """
    groups: list[dict] = []
    total_amount = 0.0

    # Filtrar sobrantes según usados actuales
    sobrantes_p = df_p[~df_p["_row_id_p"].isin(used_p)].copy()
    sobrantes_b = df_b[~df_b["_row_id_b"].isin(used_b)].copy()

    sobrantes_p["fecha"] = pd.to_datetime(sobrantes_p["fecha"], errors="coerce")
    sobrantes_b["fecha"] = pd.to_datetime(sobrantes_b["fecha"], errors="coerce")
    sobrantes_p["monto"] = pd.to_numeric(sobrantes_p["monto"], errors="coerce")
    sobrantes_b["monto"] = pd.to_numeric(sobrantes_b["monto"], errors="coerce")

    # Recorremos PILAGA como objetivo; candidatos: banco
    for _, pilaga_row in sobrantes_p.iterrows():
        target = float(pilaga_row["monto"])
        sign = 1 if target >= 0 else -1
        fecha_p = pilaga_row["fecha"]
        row_id_p = int(pilaga_row["_row_id_p"])

        cands_df = sobrantes_b[
            (sobrantes_b["monto"].apply(lambda x: (x >= 0) == (sign >= 0))) &
            (~sobrantes_b["_row_id_b"].isin(used_b))
        ].copy()

        if fecha_p is not None and pd.notna(fecha_p):
            cands_df = cands_df[
                cands_df["fecha"].notna() &
                ((cands_df["fecha"] - fecha_p).abs() <= pd.to_timedelta(days_window, unit="D"))
            ]

        cands_df = cands_df[abs(cands_df["monto"]) <= abs(target) + tol_amount]
        cands_df = cands_df.sort_values(by="monto", key=lambda s: s.abs(), ascending=False).head(N1_CAND_LIMIT_DEFAULT)

        candidates = []
        for _, row in cands_df.iterrows():
            candidates.append({
                "_row_id_b": int(row["_row_id_b"]),
                "fecha": row["fecha"],
                "monto": float(row["monto"]),
                "documento": row.get("documento", ""),
            })

        if not candidates:
            continue

        combo = _find_combo(candidates, target, max_combo=N1_MAX_COMBO_DEFAULT, tol_amount=tol_amount, min_combo=min_combo)
        if not combo:
            continue

        # registrar uso
        used_p.add(row_id_p)
        for c in combo:
            used_b.add(c["_row_id_b"])

        bank_rows = [_prepare_row(pd.Series(c)) for c in combo]
        grupo_sum = sum(c["monto"] for c in combo)
        groups.append({
            "pilaga_row": _prepare_row(pilaga_row),
            "bank_rows": bank_rows,
            "monto_total": round(grupo_sum, 2),
            "estado": estado,
            "diff": round(grupo_sum - target, 2),
            "direction": "bank_to_pilaga",  # target = PILAGA, componentes = banco
            "_row_id_p": row_id_p,
            "_row_ids_b": [c["_row_id_b"] for c in combo],
        })
        total_amount += grupo_sum

    return groups, round(total_amount, 2), used_p, used_b


def _compute_pipeline(
    df_pilaga: pd.DataFrame,
    df_banco: pd.DataFrame,
    days_window: int,
    sicom_ctx: dict[str, Any] | None = None,
):
    """Particiona en pares 1→1, agrupados (≤$1), sugeridos (>$1 hasta tol sugerida) y sobrantes."""
    t_start_total = time.perf_counter()
    timings: dict[str, float] = {}

    # preparar copias con ids
    p = df_pilaga.reset_index(drop=True).copy()
    b = df_banco.reset_index(drop=True).copy()
    p["_row_id_p"] = range(len(p))
    b["_row_id_b"] = range(len(b))

    sicom_groups, used_p, used_b = _build_sicom_mandated_groups(p, b, set(), set(), sicom_ctx)
    timings["sicom_mandated"] = time.perf_counter() - t_start_total
    t_after_sicom = time.perf_counter()

    # 1→1
    pairs_df, pair_used_p, pair_used_b = _compute_pairs(
        p[~p["_row_id_p"].isin(used_p)].copy(),
        b[~b["_row_id_b"].isin(used_b)].copy(),
        days_window,
    )
    used_p.update(int(v) for v in pair_used_p)
    used_b.update(int(v) for v in pair_used_b)
    timings["pairs"] = time.perf_counter() - t_after_sicom
    t_after_pairs = time.perf_counter()

    # Aprobados (tol estricta). min_combo=2 mantiene comportamiento previo (N→1 real).
    audit_groups: list[dict[str, Any]] = []

    approved, _, used_p, used_b = _build_groups_pipeline(
        p, b, used_p, used_b, days_window, N1_TOL_APPROVED, "approved", min_combo=2
    )
    if sicom_ctx and sicom_ctx.get("used"):
        approved_supported = [g for g in approved if _group_has_sicom_support(g, sicom_ctx)]
        approved_dropped = [g for g in approved if g not in approved_supported]
        if approved_dropped:
            audit_groups.extend(_audit_sicom_rejected_group(g, sicom_ctx) for g in approved_dropped)
            used_p, used_b = _remove_group_usage(approved_dropped, used_p, used_b)
        approved = approved_supported
    approved = sicom_groups + approved
    timings["n1_approved"] = time.perf_counter() - t_after_pairs
    t_after_approved = time.perf_counter()

    # Sugeridos (tol laxa), excluyendo diff <= tol estricta.
    # Permitimos min_combo=1 para incluir casos 1→1 aproximados (|diff|<=tol_suggested).
    suggested, _, used_p, used_b = _build_groups_pipeline(
        p, b, used_p, used_b, days_window, N1_TOL_SUGGESTED, "suggested", min_combo=1
    )
    suggested = [g for g in suggested if abs(float(g.get("diff", 0.0))) > N1_TOL_APPROVED]
    if sicom_ctx and sicom_ctx.get("used"):
        suggested_supported = [g for g in suggested if _group_has_sicom_support(g, sicom_ctx)]
        suggested_dropped = [g for g in suggested if g not in suggested_supported]
        if suggested_dropped:
            audit_groups.extend(_audit_sicom_rejected_group(g, sicom_ctx) for g in suggested_dropped)
            used_p, used_b = _remove_group_usage(suggested_dropped, used_p, used_b)
        suggested = suggested_supported
    timings["n1_suggested"] = time.perf_counter() - t_after_approved
    t_after_suggested = time.perf_counter()

    # Nota: fase 1→N banco->PILAGA desactivada por performance y porque el caso real es N PILAGA → 1 banco.
    timings["n1_suggested_bank_to_pilaga"] = 0.0

    # Recalcular conjuntos usados a partir de los resultados finales (para evitar marcar combinaciones filtradas)
    used_p_final: set[int] = set(pairs_df.get("_row_id_p", [])) if "_row_id_p" in pairs_df.columns else set()
    used_b_final: set[int] = set(pairs_df.get("_row_id_b", [])) if "_row_id_b" in pairs_df.columns else set()
    for g in approved + suggested:
        if "bank_row" in g and g.get("_row_id_b") is not None:
            used_b_final.add(int(g.get("_row_id_b")))
        if "pilaga_row" in g and g.get("_row_id_p") is not None:
            used_p_final.add(int(g.get("_row_id_p")))
        for pid in g.get("_row_ids_p", []):
            used_p_final.add(int(pid))
        for bid in g.get("_row_ids_b", []):
            used_b_final.add(int(bid))

    # Sobrantes finales
    sobrantes_p = p[~p["_row_id_p"].isin(used_p_final)].drop(columns=["_row_id_p"], errors="ignore").copy()
    sobrantes_b = b[~b["_row_id_b"].isin(used_b_final)].drop(columns=["_row_id_b"], errors="ignore").copy()
    timings["total"] = time.perf_counter() - t_start_total

    return {
        "pairs_df": pairs_df,
        "approved": approved,
        "suggested": suggested,
        "audit_groups": audit_groups,
        "sobrantes_p": sobrantes_p,
        "sobrantes_b": sobrantes_b,
        "timings": timings,
    }


def _build_n1_groups(
    df_pilaga: pd.DataFrame,
    df_banco: pd.DataFrame,
    days_window: int,
    estado: str = "approved",
    tol_amount: float | None = None,
) -> tuple[list[dict], float]:
    """
    Genera grupos N→1 exactos (suma dentro de tolerancia) sin reutilizar PILAGA.
    Usa heurística acotada (cand_limit, max_combo, tol_amount).
    """
    # Primero aplicamos 1→1 para obtener sobrantes consistentes
    pairs, sobrantes_p_base, sobrantes_b_base = _match_one_to_one_by_amount_and_date_window(
        _to_row_id(df_pilaga, "p"),
        _to_row_id(df_banco, "b"),
        days_window,
    )

    max_combo = N1_MAX_COMBO_DEFAULT
    tol_amount = N1_TOL_APPROVED if tol_amount is None else float(tol_amount)
    cand_limit = N1_CAND_LIMIT_DEFAULT

    sobrantes_p = sobrantes_p_base.copy()
    sobrantes_b = sobrantes_b_base.copy()
    # Normalizar tipos
    sobrantes_p["fecha"] = pd.to_datetime(sobrantes_p["fecha"], errors="coerce")
    sobrantes_b["fecha"] = pd.to_datetime(sobrantes_b["fecha"], errors="coerce")
    sobrantes_p["monto"] = pd.to_numeric(sobrantes_p["monto"], errors="coerce")
    sobrantes_b["monto"] = pd.to_numeric(sobrantes_b["monto"], errors="coerce")

    used_p = set()
    groups: list[dict] = []
    total_amount = 0.0

    # Ordenar bancarios por monto absoluto descendente para priorizar grandes
    sobrantes_b = sobrantes_b.sort_values(by="monto", key=lambda s: s.abs(), ascending=False)

    for _, bank_row in sobrantes_b.iterrows():
        target = float(bank_row["monto"])
        sign = 1 if target >= 0 else -1
        fecha_b = bank_row["fecha"]

        # Filtrar candidatos PILAGA compatibles
        cands_df = sobrantes_p[
            (sobrantes_p["monto"].apply(lambda x: (x >= 0) == (sign >= 0))) &
            (sobrantes_p["_row_id_p"].apply(lambda rid: rid not in used_p))
        ].copy()

        if fecha_b is not None and pd.notna(fecha_b):
            cands_df = cands_df[
                cands_df["fecha"].notna() &
                ((cands_df["fecha"] - fecha_b).abs() <= pd.to_timedelta(days_window, unit="D"))
            ]

        cands_df = cands_df[abs(cands_df["monto"]) <= abs(target) + tol_amount]

        # Ordenar por magnitud para priorizar combinaciones razonables
        cands_df = cands_df.sort_values(by="monto", key=lambda s: s.abs(), ascending=False).head(cand_limit)

        candidates = []
        for _, row in cands_df.iterrows():
            candidates.append({
                "_row_id_p": int(row["_row_id_p"]),
                "fecha": row["fecha"],
                "monto": float(row["monto"]),
                "documento": row.get("documento", ""),
            })

        if not candidates:
            continue

        combo = _find_combo(candidates, target, max_combo=max_combo, tol_amount=tol_amount)
        if not combo:
            continue

        # Marcar usados y registrar grupo
        for c in combo:
            used_p.add(c["_row_id_p"])

        pilaga_rows = [_prepare_row(pd.Series(c)) for c in combo]
        grupo_sum = sum(c["monto"] for c in combo)
        groups.append({
            "bank_row": _prepare_row(bank_row),
            "pilaga_rows": pilaga_rows,
            "monto_total": round(grupo_sum, 2),
            "estado": estado,
            "diff": round(grupo_sum - target, 2),
        })
        total_amount += grupo_sum

    return groups, round(total_amount, 2)


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
        uri_extracto, uri_contable, uri_sicom, bank_scope, account_scope, days_window = _parse_common_form(form)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable."}, status_code=400)

        df_pilaga, df_banco, df_sicom, scope_info = _load_frames(
            uri_extracto,
            uri_contable,
            uri_sicom,
            bank_scope,
            account_scope,
        )
        sicom_ctx = _build_sicom_context(df_sicom)
        pipeline = _compute_pipeline(df_pilaga, df_banco, days_window, sicom_ctx)

        pairs_df = pipeline["pairs_df"]
        sobrantes_p = pipeline["sobrantes_p"]
        sobrantes_b = pipeline["sobrantes_b"]

        out = {
            "ok": True,
            "no_en_banco_rows": _rows_for_ui_with_sicom(sobrantes_p, sicom_ctx, "pilaga", limit=500),
            "no_en_pilaga_rows": _rows_for_ui_with_sicom(sobrantes_b, sicom_ctx, "banco", limit=500),
            "counts": {
                "no_en_banco": int(len(sobrantes_p)),
                "no_en_pilaga": int(len(sobrantes_b)),
            },
            "meta": {
                "days_window": days_window,
                "sicom_used": bool(sicom_ctx.get("used")),
                "scope": scope_info,
            },
        }
        return Response(out, status_code=200)

    except Exception as e:
        return Response({"ok": False, "message": f"Error en details: {type(e).__name__}: {e}"}, status_code=500)


@post("/api/reconcile/details/no-banco")
async def reconcile_details_no_banco(request: Any) -> Response:
    """
    FORM:
      - uri_extracto  (obligatorio)
      - uri_contable  (obligatorio)
      - days_window   (opcional, default 5)
    Devuelve:
      {
        ok: True,
        total: <int>,
        rows: [...]
      }
    """
    try:
        form = await request.form()
        uri_extracto, uri_contable, uri_sicom, bank_scope, account_scope, days_window = _parse_common_form(form)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable."}, status_code=400)

        df_pilaga, df_banco, df_sicom, scope_info = _load_frames(
            uri_extracto,
            uri_contable,
            uri_sicom,
            bank_scope,
            account_scope,
        )
        sicom_ctx = _build_sicom_context(df_sicom)

        pipeline = _compute_pipeline(df_pilaga, df_banco, days_window, sicom_ctx)
        sobrantes_p = pipeline["sobrantes_p"]

        rows = _rows_for_ui_with_sicom(sobrantes_p, sicom_ctx, "pilaga", limit=1000)
        total_amount = float(pd.to_numeric(sobrantes_p["monto"], errors="coerce").fillna(0).sum()) if not sobrantes_p.empty else 0.0
        total_amount = round(total_amount, 2)
        out = {
            "ok": True,
            "total": int(len(sobrantes_p)),
            "total_amount": total_amount,
            "rows": rows,
            "meta": {
                "days_window": days_window,
                "sicom_used": bool(sicom_ctx.get("used")),
                "scope": scope_info,
            },
        }
        return Response(out, status_code=200)

    except Exception as e:
        return Response({"ok": False, "message": f"Error en detalle no-banco: {type(e).__name__}: {e}"}, status_code=500)


@post("/api/reconcile/details/pares")
async def reconcile_details_pares(request: Any) -> Response:
    """
    Conciliados exactos 1→1 (mismo monto redondeado, dentro de ventana).

    FORM:
      - uri_extracto  (obligatorio)
      - uri_contable  (obligatorio)
      - days_window   (opcional, default 5)
    Respuesta:
      {
        ok: True,
        total: <int>,
        total_amount: <float>,
        rows: [
          {fecha_banco, fecha_pilaga, monto, documento_banco, documento_pilaga, date_diff_days},
          ...
        ],
        meta: { days_window }
      }
    """
    try:
        form = await request.form()
        uri_extracto, uri_contable, uri_sicom, bank_scope, account_scope, days_window = _parse_common_form(form)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable."}, status_code=400)

        df_pilaga, df_banco, df_sicom, scope_info = _load_frames(
            uri_extracto,
            uri_contable,
            uri_sicom,
            bank_scope,
            account_scope,
        )
        sicom_ctx = _build_sicom_context(df_sicom)
        pipeline = _compute_pipeline(df_pilaga, df_banco, days_window, sicom_ctx)
        pairs_df = pipeline["pairs_df"]

        rows = [_serialize_pair(row, sicom_ctx) for _, row in pairs_df.iterrows()]
        total_amount = sum(r.get("monto") or 0 for r in rows)

        out = {
            "ok": True,
            "total": len(rows),
            "total_amount": round(total_amount, 2),
            "rows": rows,
            "meta": {
                "days_window": days_window,
                "sicom_used": bool(sicom_ctx.get("used")),
                "scope": scope_info,
            },
        }
        return Response(out, status_code=200)

    except Exception as e:
        return Response({"ok": False, "message": f"Error en detalle pares: {type(e).__name__}: {e}"}, status_code=500)


@post("/api/reconcile/details/no-contable")
async def reconcile_details_no_contable(request: Any) -> Response:
    """
    FORM:
      - uri_extracto  (obligatorio)
      - uri_contable  (obligatorio)
      - days_window   (opcional, default 5)
    Devuelve:
      {
        ok: True,
        total: <int>,
        total_amount: <float>,
        rows: [...]
      }
    """
    try:
        form = await request.form()
        uri_extracto, uri_contable, uri_sicom, bank_scope, account_scope, days_window = _parse_common_form(form)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable."}, status_code=400)

        df_pilaga, df_banco, df_sicom, scope_info = _load_frames(
            uri_extracto,
            uri_contable,
            uri_sicom,
            bank_scope,
            account_scope,
        )
        sicom_ctx = _build_sicom_context(df_sicom)

        pipeline = _compute_pipeline(df_pilaga, df_banco, days_window, sicom_ctx)
        sobrantes_b = pipeline["sobrantes_b"]

        rows = _rows_for_ui_with_sicom(sobrantes_b, sicom_ctx, "banco", limit=1000)
        total_amount = float(pd.to_numeric(sobrantes_b["monto"], errors="coerce").fillna(0).sum()) if not sobrantes_b.empty else 0.0
        total_amount = round(total_amount, 2)
        out = {
            "ok": True,
            "total": int(len(sobrantes_b)),
            "total_amount": total_amount,
            "rows": rows,
            "meta": {
                "days_window": days_window,
                "sicom_used": bool(sicom_ctx.get("used")),
                "scope": scope_info,
            },
        }
        return Response(out, status_code=200)

    except Exception as e:
        return Response({"ok": False, "message": f"Error en detalle no-contable: {type(e).__name__}: {e}"}, status_code=500)


@post("/api/reconcile/details/n1/grupos")
async def reconcile_details_n1_grupos(request: Any) -> Response:
    """
    Endpoint para grupos N→1 aprobados (combinaciones exactas sin validación manual).

    FORM:
      - uri_extracto  (obligatorio)
      - uri_contable  (obligatorio)
      - days_window   (opcional, default 5)
    Respuesta:
      {
        ok: True,
        total: <int>,
        total_amount: <float>,
        rows: [
          {
            bank_row: { fecha, monto, documento },
            pilaga_rows: [{ fecha, monto, documento }, ...],
            monto_total: <float>,
            estado: "approved",
          },
          ...
        ],
        meta: { days_window }
      }
    """
    try:
        form = await request.form()
        uri_extracto, uri_contable, uri_sicom, bank_scope, account_scope, days_window = _parse_common_form(form)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable."}, status_code=400)

        df_pilaga, df_banco, df_sicom, scope_info = _load_frames(
            uri_extracto,
            uri_contable,
            uri_sicom,
            bank_scope,
            account_scope,
        )
        sicom_ctx = _build_sicom_context(df_sicom)

        pipeline = _compute_pipeline(df_pilaga, df_banco, days_window, sicom_ctx)
        rows = pipeline["approved"]
        enriched_rows = []
        for row in rows:
            selected_lot = ((row.get("sicom_basis") or {}).get("selected_lot") or None)
            pilaga_rows = []
            for item in row.get("pilaga_rows") or []:
                enriched = _enrich_simple_row_dict(item, sicom_ctx, "pilaga")
                if selected_lot:
                    enriched = _restrict_pilaga_sicom_context_to_lot(enriched, selected_lot)
                pilaga_rows.append(enriched)
            enriched_rows.append({
                **row,
                "bank_row": _enrich_simple_row_dict(row.get("bank_row") or {}, sicom_ctx, "banco") if row.get("bank_row") else row.get("bank_row"),
                "pilaga_rows": pilaga_rows,
            })
        rows = enriched_rows
        total_amount = sum((r.get("monto_total") or 0) for r in rows)
        out = {
            "ok": True,
            "total": len(rows),
            "total_amount": round(total_amount, 2),
            "rows": rows,
            "meta": {
                "days_window": days_window,
                "max_combo": N1_MAX_COMBO_DEFAULT,
                "tol_amount": N1_TOL_APPROVED,
                "cand_limit": N1_CAND_LIMIT_DEFAULT,
                "sicom_used": bool(sicom_ctx.get("used")),
                "scope": scope_info,
            },
        }
        return Response(out, status_code=200)

    except Exception as e:
        return Response({"ok": False, "message": f"Error en detalle n1/grupos: {type(e).__name__}: {e}"}, status_code=500)


@post("/api/reconcile/details/n1/sugeridos")
async def reconcile_details_n1_sugeridos(request: Any) -> Response:
    """
    Endpoint para grupos N→1 sugeridos (misma heurística que aprobados, marcados como 'suggested').

    FORM:
      - uri_extracto  (obligatorio)
      - uri_contable  (obligatorio)
      - days_window   (opcional, default 5)
    Respuesta:
      {
        ok: True,
        total: <int>,
        total_amount: <float>,
        rows: [
          {
            bank_row: { fecha, monto, documento },
            pilaga_rows: [{ fecha, monto, documento }, ...],
            monto_total: <float>,
            estado: "suggested",
          },
          ...
        ],
        meta: { days_window }
      }
    """
    try:
        form = await request.form()
        uri_extracto, uri_contable, uri_sicom, bank_scope, account_scope, days_window = _parse_common_form(form)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable."}, status_code=400)

        df_pilaga, df_banco, df_sicom, scope_info = _load_frames(
            uri_extracto,
            uri_contable,
            uri_sicom,
            bank_scope,
            account_scope,
        )
        sicom_ctx = _build_sicom_context(df_sicom)

        pipeline = _compute_pipeline(df_pilaga, df_banco, days_window, sicom_ctx)
        rows = list(pipeline["suggested"] or []) + list(pipeline.get("audit_groups") or [])
        rows = [
            {
                **row,
                "bank_row": _enrich_simple_row_dict(row.get("bank_row") or {}, sicom_ctx, "banco") if row.get("bank_row") else row.get("bank_row"),
                "pilaga_row": _enrich_simple_row_dict(row.get("pilaga_row") or {}, sicom_ctx, "pilaga") if row.get("pilaga_row") else row.get("pilaga_row"),
                "pilaga_rows": [_enrich_simple_row_dict(item, sicom_ctx, "pilaga") for item in (row.get("pilaga_rows") or [])],
                "bank_rows": [_enrich_simple_row_dict(item, sicom_ctx, "banco") for item in (row.get("bank_rows") or [])],
            }
            for row in rows
        ]
        total_amount = sum((r.get("monto_total") or 0) for r in rows)
        out = {
            "ok": True,
            "total": len(rows),
            "total_amount": round(total_amount, 2),
            "rows": rows,
            "meta": {
                "days_window": days_window,
                "max_combo": N1_MAX_COMBO_DEFAULT,
                "tol_amount": N1_TOL_SUGGESTED,
                "cand_limit": N1_CAND_LIMIT_DEFAULT,
                "sicom_used": bool(sicom_ctx.get("used")),
                "audit_groups": len(pipeline.get("audit_groups") or []),
                "scope": scope_info,
            },
        }
        return Response(out, status_code=200)

    except Exception as e:
        return Response({"ok": False, "message": f"Error en detalle n1/sugeridos: {type(e).__name__}: {e}"}, status_code=500)

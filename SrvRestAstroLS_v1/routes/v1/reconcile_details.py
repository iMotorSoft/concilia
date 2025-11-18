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

def _parse_common_form(form: Any) -> Tuple[str, str, int]:
    uri_extracto = form.get("uri_extracto") or form.get("extracto_original_uri") or ""
    uri_contable = form.get("uri_contable") or form.get("contable_original_uri") or ""
    days_window = int(form.get("days_window") or 5)
    return uri_extracto, uri_contable, days_window


def _load_frames(uri_extracto: str, uri_contable: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    path_extracto = _from_file_uri(uri_extracto)
    path_contable = _from_file_uri(uri_contable)
    df_pilaga = _load_pilaga(path_contable)
    df_banco = _load_extracto(path_extracto)
    return df_pilaga, df_banco


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

def _serialize_pair(row: pd.Series) -> dict:
    """Convierte un merge 1→1 a dict simple para UI."""
    monto = row.get("monto_r")
    if pd.isna(monto):
        monto = row.get("monto_p") if pd.notna(row.get("monto_p")) else row.get("monto_b")
    try:
        monto_val = float(monto)
    except Exception:
        monto_val = 0.0
    return {
        "fecha_banco": pd.to_datetime(row.get("fecha_b"), errors="coerce").date().isoformat() if pd.notna(row.get("fecha_b")) else "",
        "fecha_pilaga": pd.to_datetime(row.get("fecha_p"), errors="coerce").date().isoformat() if pd.notna(row.get("fecha_p")) else "",
        "monto": monto_val,
        "documento_banco": str(row.get("documento_b") or ""),
        "documento_pilaga": str(row.get("documento_p") or ""),
        "date_diff_days": int(row.get("date_diff_days") or 0),
    }


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
    p["_row_id_p"] = range(len(p))
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


def _compute_pipeline(df_pilaga: pd.DataFrame, df_banco: pd.DataFrame, days_window: int):
    """Particiona en pares 1→1, agrupados (≤$1), sugeridos (>$1 hasta tol sugerida) y sobrantes."""
    t_start_total = time.perf_counter()
    timings: dict[str, float] = {}

    # preparar copias con ids
    p = df_pilaga.reset_index(drop=True).copy()
    b = df_banco.reset_index(drop=True).copy()
    p["_row_id_p"] = range(len(p))
    b["_row_id_b"] = range(len(b))

    # 1→1
    pairs_df, used_p, used_b = _compute_pairs(p, b, days_window)
    timings["pairs"] = time.perf_counter() - t_start_total
    t_after_pairs = time.perf_counter()

    # Aprobados (tol estricta). min_combo=2 mantiene comportamiento previo (N→1 real).
    approved, _, used_p, used_b = _build_groups_pipeline(
        p, b, used_p, used_b, days_window, N1_TOL_APPROVED, "approved", min_combo=2
    )
    timings["n1_approved"] = time.perf_counter() - t_after_pairs
    t_after_approved = time.perf_counter()

    # Sugeridos (tol laxa), excluyendo diff <= tol estricta.
    # Permitimos min_combo=1 para incluir casos 1→1 aproximados (|diff|<=tol_suggested).
    suggested, _, used_p, used_b = _build_groups_pipeline(
        p, b, used_p, used_b, days_window, N1_TOL_SUGGESTED, "suggested", min_combo=1
    )
    suggested = [g for g in suggested if abs(float(g.get("diff", 0.0))) > N1_TOL_APPROVED]
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
        uri_extracto, uri_contable, days_window = _parse_common_form(form)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable."}, status_code=400)

        df_pilaga, df_banco = _load_frames(uri_extracto, uri_contable)
        pipeline = _compute_pipeline(df_pilaga, df_banco, days_window)

        pairs_df = pipeline["pairs_df"]
        sobrantes_p = pipeline["sobrantes_p"]
        sobrantes_b = pipeline["sobrantes_b"]

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
        uri_extracto, uri_contable, days_window = _parse_common_form(form)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable."}, status_code=400)

        df_pilaga, df_banco = _load_frames(uri_extracto, uri_contable)

        pipeline = _compute_pipeline(df_pilaga, df_banco, days_window)
        sobrantes_p = pipeline["sobrantes_p"]

        rows = _rows_for_ui(sobrantes_p, limit=1000)
        total_amount = float(pd.to_numeric(sobrantes_p["monto"], errors="coerce").fillna(0).sum()) if not sobrantes_p.empty else 0.0
        total_amount = round(total_amount, 2)
        out = {
            "ok": True,
            "total": int(len(sobrantes_p)),
            "total_amount": total_amount,
            "rows": rows,
            "meta": {
                "days_window": days_window,
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
        uri_extracto, uri_contable, days_window = _parse_common_form(form)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable."}, status_code=400)

        df_pilaga, df_banco = _load_frames(uri_extracto, uri_contable)
        pipeline = _compute_pipeline(df_pilaga, df_banco, days_window)
        pairs_df = pipeline["pairs_df"]

        rows = [_serialize_pair(row) for _, row in pairs_df.iterrows()]
        total_amount = sum(r.get("monto") or 0 for r in rows)

        out = {
            "ok": True,
            "total": len(rows),
            "total_amount": round(total_amount, 2),
            "rows": rows,
            "meta": {
                "days_window": days_window,
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
        uri_extracto, uri_contable, days_window = _parse_common_form(form)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable."}, status_code=400)

        df_pilaga, df_banco = _load_frames(uri_extracto, uri_contable)

        pipeline = _compute_pipeline(df_pilaga, df_banco, days_window)
        sobrantes_b = pipeline["sobrantes_b"]

        rows = _rows_for_ui(sobrantes_b, limit=1000)
        total_amount = float(pd.to_numeric(sobrantes_b["monto"], errors="coerce").fillna(0).sum()) if not sobrantes_b.empty else 0.0
        total_amount = round(total_amount, 2)
        out = {
            "ok": True,
            "total": int(len(sobrantes_b)),
            "total_amount": total_amount,
            "rows": rows,
            "meta": {
                "days_window": days_window,
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
        uri_extracto, uri_contable, days_window = _parse_common_form(form)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable."}, status_code=400)

        df_pilaga, df_banco = _load_frames(uri_extracto, uri_contable)

        pipeline = _compute_pipeline(df_pilaga, df_banco, days_window)
        rows = pipeline["approved"]
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
        uri_extracto, uri_contable, days_window = _parse_common_form(form)

        if not uri_extracto or not uri_contable:
            return Response({"ok": False, "message": "Faltan URIs: uri_extracto y uri_contable."}, status_code=400)

        df_pilaga, df_banco = _load_frames(uri_extracto, uri_contable)

        pipeline = _compute_pipeline(df_pilaga, df_banco, days_window)
        rows = pipeline["suggested"]
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
            },
        }
        return Response(out, status_code=200)

    except Exception as e:
        return Response({"ok": False, "message": f"Error en detalle n1/sugeridos: {type(e).__name__}: {e}"}, status_code=500)

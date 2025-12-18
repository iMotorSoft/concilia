# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/routes/v1/ingest_confirm.py
from __future__ import annotations
from typing import Any, Dict, Optional
from datetime import date

from litestar import post
from litestar.response import Response

from .agui_notify import emit
import globalVar as Var

from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
import asyncio
import re

# Estado en memoria por threadId
# _CONFIRMS[threadId] = {"extracto": {...} | None, "contable": {...} | None}
_CONFIRMS: Dict[str, Dict[str, Optional[dict]]] = {}

_SAFE_NAME_RX = re.compile(r"[^A-Za-z0-9._-]+")

def _safe_filename(name: str) -> str:
    base = Path(name or "canonical.parquet").name
    base = _SAFE_NAME_RX.sub("_", base).strip("._") or "canonical.parquet"
    return base

def _from_file_uri(uri: str) -> Path:
    if uri and uri.startswith("file://"):
        return Path(urlparse(uri).path)
    return Path(uri)

def _build_canonical_parquet(role: str, original_uri: str, *, bank: str | None, period_from: str | None, period_to: str | None) -> str:
    """
    Genera un parquet canónico (estandarizado) a partir del archivo original (xlsx/csv o ya parquet).
    Retorna canonical_uri (file://...).
    """
    if not original_uri:
        raise ValueError("original_uri vacío")

    # Si ya es parquet, lo aceptamos como canónico.
    if str(original_uri).lower().endswith((".parquet", ".pq")):
        return original_uri

    from routes.v1.reconcile_start import _load_extracto, _load_pilaga  # import local para evitar ciclos globales

    src_path = _from_file_uri(original_uri)
    if role == "extracto":
        df = _load_extracto(src_path)
        prefix = "extracto"
    else:
        df = _load_pilaga(src_path)
        prefix = "contable"

    tag_pf = (period_from or "").replace("-", "")[:8] or "na"
    tag_pt = (period_to or "").replace("-", "")[:8] or "na"
    tag_bank = (bank or "bank").lower()
    fname = _safe_filename(f"{uuid4()}_{prefix}_{tag_bank}_{tag_pf}_{tag_pt}.parquet")

    canonical_uri = Var.resolve_storage_uri("canonical", filename=fname)
    if not canonical_uri.startswith("file://"):
        raise RuntimeError("Storage provider no soportado (solo local).")
    out_path = Path(urlparse(canonical_uri).path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import polars as pl  # type: ignore
        pl.from_pandas(df).write_parquet(out_path)
    except Exception:
        # fallback: pandas (requiere engine instalado)
        df.to_parquet(out_path)

    return canonical_uri

async def _canonicalize_async(thread_id: str, role: str, original_uri: str, bank: str | None, period_from: str | None, period_to: str | None) -> None:
    try:
        canonical_uri = await asyncio.to_thread(
            _build_canonical_parquet,
            role,
            original_uri,
            bank=bank,
            period_from=period_from,
            period_to=period_to,
        )

        state = _CONFIRMS.setdefault(thread_id, {"extracto": None, "contable": None})
        if state.get(role) is None:
            state[role] = {}
        state[role]["canonical_uri"] = canonical_uri

        await emit(thread_id, {
            "type": "INGEST_CANONICAL_READY",
            "payload": {"role": role, "canonical_uri": canonical_uri},
        })
    except Exception as e:
        await emit(thread_id, {
            "type": "TOAST", "level": "warning",
            "message": f"No se pudo generar canónico ({role}): {type(e).__name__}: {e}",
        })

def _iso_date_min(a: Optional[str], b: Optional[str]) -> Optional[str]:
    if not a:
        return b
    if not b:
        return a
    return a if a <= b else b

def _iso_date_max(a: Optional[str], b: Optional[str]) -> Optional[str]:
    if not a:
        return b
    if not b:
        return a
    return a if a >= b else b

@post("/api/ingest/confirm")
async def ingest_confirm(request: Any) -> Response:
    """
    Confirma un preview. Espera multipart/form-data:
      - threadId (obligatorio)
      - role: extracto | contable (obligatorio)
      - source_file_id, original_uri, bank, period_from, period_to (opcionales)
    Side-effects:
      - Guarda estado por threadId/role.
      - Emite READY_TO_RECONCILE por SSE cuando los 2 están confirmados.
    """
    form = await request.form()
    threadId = (form.get("threadId") or "").strip()
    role = (form.get("role") or "").strip().lower()

    if not threadId:
        return Response({"ok": False, "message": "Falta threadId"}, status_code=400)
    if role not in {"extracto", "contable"}:
        return Response({"ok": False, "message": "role inválido (use extracto|contable)"}, status_code=400)

    source_file_id = (form.get("source_file_id") or "").strip()
    original_uri   = (form.get("original_uri") or "").strip()
    bank           = (form.get("bank") or "").strip() or None
    period_from    = (form.get("period_from") or "").strip() or None
    period_to      = (form.get("period_to") or "").strip() or None

    state = _CONFIRMS.setdefault(threadId, {"extracto": None, "contable": None})
    state[role] = {
        "source_file_id": source_file_id,
        "original_uri": original_uri,
        "bank": bank,
        "period_from": period_from,
        "period_to": period_to,
        "confirmed": True,
    }

    # Generar canónico en background (Parquet) para acelerar reconcile
    asyncio.create_task(_canonicalize_async(threadId, role, original_uri, bank, period_from, period_to))

    # Feedback inmediato
    await emit(threadId, {
        "type": "TOAST", "level": "success",
        "message": f"{role.capitalize()} confirmado."
    })

    # Si ambos están confirmados, emitir READY_TO_RECONCILE
    e = state.get("extracto")
    c = state.get("contable")
    if e and c and e.get("confirmed") and c.get("confirmed"):
        # Banco “consenso” (si coincide)
        bank_consensus = e.get("bank") if e.get("bank") == c.get("bank") else None
        # Rango total (mínimo de los from, máximo de los to)
        from_union = _iso_date_min(e.get("period_from"), c.get("period_from"))
        to_union   = _iso_date_max(e.get("period_to"), c.get("period_to"))

        await emit(threadId, {
            "type": "READY_TO_RECONCILE",
            "payload": {
                "roles": ["extracto", "contable"],
                "bank": bank_consensus,
                "period": {"from": from_union, "to": to_union},
                "files": {
                    "extracto": {"uri": e.get("original_uri")},
                    "contable": {"uri": c.get("original_uri")},
                }
            }
        })

    return Response({"ok": True, "message": "Confirmado"}, status_code=200)

# Exponer estado para otros endpoints (reconcile_start)
def get_confirms(thread_id: str) -> Dict[str, Optional[dict]]:
    return _CONFIRMS.get(thread_id, {"extracto": None, "contable": None})

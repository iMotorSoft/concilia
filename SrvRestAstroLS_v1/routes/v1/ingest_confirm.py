# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/routes/v1/ingest_confirm.py
from __future__ import annotations
from typing import Any, Dict, Optional
from datetime import date
import json
import logging

from litestar import post
from litestar.response import Response

from .agui_notify import emit
import globalVar as Var

from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
import asyncio
import re

logger = logging.getLogger(__name__)

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

def _form_values(form: Any, key: str) -> list[str]:
    values: list[str] = []
    getter = getattr(form, "getall", None)
    if callable(getter):
        try:
            values = [v for v in getter(key) if str(v).strip()]
        except Exception:
            values = []
    if not values:
        raw = form.get(key)
        if raw is None:
            return []
        if isinstance(raw, (list, tuple)):
            values = list(raw)
        else:
            raw_str = str(raw).strip()
            if raw_str.startswith("[") and raw_str.endswith("]"):
                try:
                    parsed = json.loads(raw_str)
                    if isinstance(parsed, list):
                        values = parsed
                except Exception:
                    values = []
            if not values and raw_str:
                if "," in raw_str:
                    values = [v.strip() for v in raw_str.split(",") if v.strip()]
                else:
                    values = [raw_str]
    return [str(v).strip() for v in values if str(v).strip()]

def _value_for_index(values: list[str], idx: int) -> Optional[str]:
    if not values:
        return None
    if idx < len(values):
        return values[idx]
    return values[-1]

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

def _build_extracto_manifest(uris: list[str]) -> str:
    fname = _safe_filename(f"{uuid4()}_extracto_manifest.json")
    manifest_uri = Var.resolve_storage_uri("canonical", filename=fname)
    if not manifest_uri.startswith("file://"):
        raise RuntimeError("Storage provider no soportado (solo local).")
    out_path = Path(urlparse(manifest_uri).path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"role": "extracto", "count": len(uris), "uris": uris}
    out_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    logger.debug("manifest created count=%s path=%s", len(uris), out_path.as_posix())
    return manifest_uri

async def _maybe_emit_ready(thread_id: str) -> None:
    state = _CONFIRMS.get(thread_id)
    if not state or state.get("_ready_sent"):
        return

    extracto = state.get("extracto") or {}
    contable = state.get("contable") or {}
    if not (extracto.get("confirmed") and contable.get("confirmed")):
        return

    items = extracto.get("items") or []
    if not items:
        return

    extracto_count = len(items)
    canonical_uris = [item.get("canonical_uri") for item in items]

    if extracto_count >= 2:
        if not all(canonical_uris):
            return
        manifest_uri = extracto.get("manifest_uri")
        if not manifest_uri:
            manifest_uri = _build_extracto_manifest([uri for uri in canonical_uris if uri])
            extracto["manifest_uri"] = manifest_uri
        extracto_uri = manifest_uri
    else:
        extracto_uri = items[0].get("canonical_uri") or items[0].get("original_uri")
        if not extracto_uri:
            return

    contable_uri = contable.get("canonical_uri") or contable.get("original_uri")

    bank_consensus = None
    extracto_banks = [item.get("bank") for item in items if item.get("bank")]
    if extracto_banks and all(b == extracto_banks[0] for b in extracto_banks):
        if extracto_banks[0] == contable.get("bank"):
            bank_consensus = extracto_banks[0]

    from_union = None
    to_union = None
    for item in items:
        from_union = _iso_date_min(from_union, item.get("period_from"))
        to_union = _iso_date_max(to_union, item.get("period_to"))
    from_union = _iso_date_min(from_union, contable.get("period_from"))
    to_union = _iso_date_max(to_union, contable.get("period_to"))

    await emit(thread_id, {
        "type": "READY_TO_RECONCILE",
        "payload": {
            "roles": ["extracto", "contable"],
            "bank": bank_consensus,
            "period": {"from": from_union, "to": to_union},
            "files": {
                "extracto": {"uri": extracto_uri},
                "contable": {"uri": contable_uri},
            },
        },
    })
    state["_ready_sent"] = True

async def _canonicalize_async(
    thread_id: str,
    role: str,
    original_uri: str,
    bank: str | None,
    period_from: str | None,
    period_to: str | None,
    item_id: str | None = None,
) -> None:
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
        if role == "extracto" and item_id:
            items = state[role].get("items") or []
            for item in items:
                if item.get("item_id") == item_id:
                    item["canonical_uri"] = canonical_uri
                    break
        else:
            state[role]["canonical_uri"] = canonical_uri

        await emit(thread_id, {
            "type": "INGEST_CANONICAL_READY",
            "payload": {"role": role, "canonical_uri": canonical_uri},
        })
        await _maybe_emit_ready(thread_id)
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
    if role == "extracto":
        original_uris = _form_values(form, "original_uri")
        source_ids = _form_values(form, "source_file_id")
        banks = _form_values(form, "bank")
        period_froms = _form_values(form, "period_from")
        period_tos = _form_values(form, "period_to")
        if not original_uris:
            return Response({"ok": False, "message": "Falta original_uri"}, status_code=400)

        extracto_state = state.get("extracto") or {}
        existing_items = extracto_state.get("items") or []
        new_items = []
        for idx, uri in enumerate(original_uris):
            new_items.append({
                "item_id": str(uuid4()),
                "source_file_id": _value_for_index(source_ids, idx) or "",
                "original_uri": uri,
                "bank": _value_for_index(banks, idx),
                "period_from": _value_for_index(period_froms, idx),
                "period_to": _value_for_index(period_tos, idx),
                "confirmed": True,
            })

        if len(original_uris) > 1:
            items = new_items
        else:
            items = existing_items + new_items

        state["extracto"] = {
            "items": items,
            "confirmed": True,
        }
        state["_ready_sent"] = False

        for item in items:
            if not item.get("canonical_uri"):
                asyncio.create_task(
                    _canonicalize_async(
                        threadId,
                        role,
                        item.get("original_uri") or "",
                        item.get("bank"),
                        item.get("period_from"),
                        item.get("period_to"),
                        item_id=item.get("item_id"),
                    )
                )
    else:
        state[role] = {
            "source_file_id": source_file_id,
            "original_uri": original_uri,
            "bank": bank,
            "period_from": period_from,
            "period_to": period_to,
            "confirmed": True,
        }
        state["_ready_sent"] = False
        # Generar canónico en background (Parquet) para acelerar reconcile
        asyncio.create_task(_canonicalize_async(threadId, role, original_uri, bank, period_from, period_to))

    # Feedback inmediato
    if role == "extracto":
        extracto_count = len(state.get("extracto", {}).get("items") or [])
        await emit(threadId, {
            "type": "TOAST", "level": "success",
            "message": f"Extractos confirmados: {extracto_count}",
        })
    else:
        await emit(threadId, {
            "type": "TOAST", "level": "success",
            "message": f"{role.capitalize()} confirmado."
        })

    await _maybe_emit_ready(threadId)

    return Response({"ok": True, "message": "Confirmado"}, status_code=200)

# Exponer estado para otros endpoints (reconcile_start)
def get_confirms(thread_id: str) -> Dict[str, Optional[dict]]:
    return _CONFIRMS.get(thread_id, {"extracto": None, "contable": None})

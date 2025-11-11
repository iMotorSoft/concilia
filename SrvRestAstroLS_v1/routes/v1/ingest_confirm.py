# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/routes/v1/ingest_confirm.py
from __future__ import annotations
from typing import Any, Dict, Optional
from datetime import date

from litestar import post
from litestar.response import Response

from .agui_notify import emit

# Estado en memoria por threadId
# _CONFIRMS[threadId] = {"extracto": {...} | None, "contable": {...} | None}
_CONFIRMS: Dict[str, Dict[str, Optional[dict]]] = {}

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


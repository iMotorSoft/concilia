# SrvRestAstroLS_v1/routes/v1/ingest_confirm.py
from __future__ import annotations
import asyncio
from typing import Any, Dict, Optional

from litestar import post
from litestar.response import Response

from .agui_notify import emit

# Estado en memoria por threadId
# Estructura: { "<threadId>": {"extracto": bool, "contable": bool} }
CONFIRMED: Dict[str, Dict[str, bool]] = {}


def _get_state(tid: str) -> Dict[str, bool]:
    st = CONFIRMED.get(tid)
    if not st:
        st = {"extracto": False, "contable": False}
        CONFIRMED[tid] = st
    return st


def _get_form_or_json(data: Any, key: str) -> Optional[str]:
    # Permite usar tanto FormData como JSON
    if hasattr(data, "get"):
        val = data.get(key)  # starlette/litestar form
        if val is not None:
            return str(val)
    try:
        # litestar parsea automáticamente JSON → dict
        return str(data[key]) if isinstance(data, dict) and key in data else None
    except Exception:
        return None


@post("/api/ingest/confirm")
async def ingest_confirm(request: Any) -> Response:
    """
    Confirma un archivo ya subido, por rol.
    Acepta FormData o JSON con:
      - threadId (str)   [requerido]
      - role ("extracto" | "contable") [requerido]
      - source_file_id, original_uri   [opcionales, por trazabilidad]
    Efectos:
      - Marca CONFIRMED[threadId][role] = True
      - Emite SSE: CONFIRM_OK {role}
      - Si ambos confirmados -> BOTH_CONFIRMED {ready:true}
    """
    data = {}
    try:
        ct = (request.headers.get("content-type") or "").lower()
        if "multipart/form-data" in ct:
            data = await request.form()
        elif "application/json" in ct:
            data = await request.json()
        else:
            data = await request.form()

        thread_id = _get_form_or_json(data, "threadId")
        role = (_get_form_or_json(data, "role") or "").strip().lower()

        if not thread_id:
            return Response({"ok": False, "message": "Falta threadId"}, status_code=400)
        if role not in ("extracto", "contable"):
            return Response({"ok": False, "message": "role inválido (extracto|contable)"}, status_code=400)

        # marcar estado
        st = _get_state(thread_id)
        st[role] = True

        # emitir confirmación de ese rol
        asyncio.create_task(emit(thread_id, {"type": "CONFIRM_OK", "payload": {"role": role}}))

        # si ambos confirmados → avisar
        if st["extracto"] and st["contable"]:
            asyncio.create_task(emit(thread_id, {"type": "BOTH_CONFIRMED", "payload": {"ready": True}}))

        return Response({"ok": True, "message": "Confirmado"}, status_code=200)

    except Exception as e:
        asyncio.create_task(emit(_get_form_or_json(data or {}, "threadId"), {
            "type": "TOAST", "level": "error", "message": f"Confirm error: {type(e).__name__}: {e}"
        }))
        return Response({"ok": False, "message": "Error interno"}, status_code=500)

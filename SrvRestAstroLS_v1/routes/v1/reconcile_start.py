# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/routes/v1/reconcile_start.py
from __future__ import annotations
from typing import Any

from litestar import post
from litestar.response import Response

from .agui_notify import emit
from .ingest_confirm import get_confirms

@post("/api/reconcile/start")
async def reconcile_start(request: Any) -> Response:
    """
    Inicia la conciliación (mock por ahora).
    Espera multipart/form-data:
      - threadId (obligatorio)
    Side-effects:
      - Emite RUN_START y RESULT_READY (mock) por SSE.
    """
    form = await request.form()
    threadId = (form.get("threadId") or "").strip()
    if not threadId:
        return Response({"ok": False, "message": "Falta threadId"}, status_code=400)

    state = get_confirms(threadId)
    if not (state.get("extracto") and state.get("contable")):
        return Response({"ok": False, "message": "Falta confirmar extracto y contable"}, status_code=400)

    # Señal de inicio
    await emit(threadId, {"type": "RUN_START"})

    # TODO: aquí irá la conciliación real.
    # Enviamos un resultado mock para verificar la UI end-to-end.
    summary = {
        "matches": 0,
        "bank_only": 0,
        "gl_only": 0,
        "note": "Mock inicial: la conciliación real se agregará en el próximo paso."
    }
    await emit(threadId, {"type": "RESULT_READY", "payload": summary})

    return Response({"ok": True, "message": "Conciliación iniciada"}, status_code=200)


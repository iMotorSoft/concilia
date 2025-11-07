# SrvRestAstroLS_v1/routes/v1/chat_concilia.py
from __future__ import annotations

from typing import Any, Dict
from litestar import post
from litestar.response import Response
from .agui_notify import emit

@post("/api/chat/turn")
async def chat_turn(data: Dict[str, Any]) -> Response:
    """
    MVP: siempre pedimos el upload.
    Emite TEXT_MESSAGE_REQUEST_UPLOAD al threadId recibido y devuelve 200.
    """
    thread_id = (data or {}).get("threadId")
    correlation_id = (data or {}).get("correlationId")
    # (opcional) texto, por si querés loguear
    # text = (data or {}).get("text", "") or ""

    await emit(thread_id, {
        "type": "TEXT_MESSAGE_REQUEST_UPLOAD",
        "correlationId": correlation_id,
        "payload": {
            "title": "Subí el archivo para analizar",
            "hint": "Elegí el extracto bancario (XLSX/CSV) del período",
            "form": {
                "modalId": "uploadBankMovements",
                "fields": [
                    {"name":"account_id","label":"Cuenta","type":"select","options":[],"required":True},
                    {"name":"period","label":"Período (YYYY-MM)","type":"text","required":True,"pattern":"^\\d{4}-\\d{2}$"},
                    {"name":"source","label":"Fuente","type":"select","options":["bank"],"required":True},
                    {"name":"profile_id","label":"Perfil de banco","type":"select","options":["ciudad","santander","patagonia"],"required":True},
                    {"name":"file","label":"Archivo","type":"file","accept":".xlsx,.csv","required":True}
                ],
                "submit":{"label":"Subir y analizar","endpoint":"/api/uploads/bank-movements","method":"POST"}
            }
        }
    })

    # responder 200 explícito (evitamos 201 por default)
    return Response({"type": "OK"}, status_code=200)


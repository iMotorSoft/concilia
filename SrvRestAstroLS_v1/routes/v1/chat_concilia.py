from __future__ import annotations
from typing import Any, Dict
from litestar import post
from litestar.response import Response
import re

from .agui_notify import emit

def upload_form(endpoint: str, accept: str) -> dict:
    return {
        "title": "Subí el archivo para analizar",
        "hint": "Acepta .xlsx, .xls, .csv",
        "fields": [
            {"name": "file", "label": "Archivo", "type": "file", "accept": accept, "required": True},
        ],
        "submit": {"endpoint": endpoint, "method": "POST", "label": "Subir y analizar"},
    }

@post("/api/chat/turn")
async def chat_turn(data: Dict[str, Any]) -> Response:
    text = (data.get("text") or "").strip().lower()
    thread_id = data.get("threadId")

    async def push(event: dict) -> None:
        if thread_id:
            await emit(thread_id, event)

    # Intent: subir extracto
    if re.search(r"\bextracto\b", text):
        await push({
            "type": "TEXT_MESSAGE_REQUEST_UPLOAD",
            "payload": { "form": upload_form("/api/uploads/v2/ingest?role=extracto", ".xlsx,.xls,.csv") },
        })
        return Response({"ok": True}, status_code=200)

    # Intent: subir contable / pilaga
    if re.search(r"\b(contable|pilaga)\b", text):
        await push({
            "type": "TEXT_MESSAGE_REQUEST_UPLOAD",
            "payload": { "form": upload_form("/api/uploads/v2/ingest?role=contable", ".xlsx,.xls") },
        })
        return Response({"ok": True}, status_code=200)

    # Fallback
    await push({
        "type": "TEXT_MESSAGE_CONTENT",
        "delta": "Decime 'subir extracto' o 'subir contable' para abrir el modal.",
    })
    return Response({"ok": True}, status_code=200)

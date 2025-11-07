# SrvRestAstroLS_v1/routes/v1/agui_notify.py
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional
from litestar import get
from litestar.response import Stream

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
    "Content-Type": "text/event-stream; charset=utf-8",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Last-Event-ID",
    "Vary": "Origin",
}

_SUBS: Dict[str, asyncio.Queue] = {}
_PENDING: Dict[str, List[Dict[str, Any]]] = {}  # buffer por threadId/topic

def _topic(thread_id: Optional[str]) -> str:
    return thread_id or "global"

def _sse(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

async def emit(thread_id: Optional[str], payload: Dict[str, Any]) -> None:
    """Encola un evento para el topic; si no hay suscriptor aún, lo bufferiza."""
    t = _topic(thread_id)
    q = _SUBS.get(t)
    if q:
        await q.put(payload)
    else:
        _PENDING.setdefault(t, []).append(payload)

@get("/api/ag-ui/notify/stream", media_type="text/event-stream", status_code=200)
async def notify_stream(threadId: Optional[str] = None) -> Stream:
    t = _topic(threadId)
    q: asyncio.Queue = asyncio.Queue()
    _SUBS[t] = q

    async def gen():
        try:
            # saludo / debug
            yield _sse({"type": "DEBUG", "stage": "CONNECTED", "threadId": t})
            # flush de pendientes si los había
            for p in _PENDING.pop(t, []):
                yield _sse(p)
            # loop normal
            while True:
                payload = await q.get()
                yield _sse(payload)
        finally:
            try:
                if _SUBS.get(t) is q:
                    del _SUBS[t]
            except Exception:
                pass

    return Stream(gen(), headers=SSE_HEADERS)


# SrvRestAstroLS_v1/routes/v1/agui_notify.py
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import anyio
from litestar import get
from litestar.response import Stream

from services.json_safe import json_default, to_jsonable

logger = logging.getLogger(__name__)

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
    safe_payload = to_jsonable(payload)
    return f"data: {json.dumps(safe_payload, default=json_default, ensure_ascii=False)}\n\n"

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
            try:
                yield _sse({"type": "DEBUG", "stage": "CONNECTED", "threadId": t})
            except Exception:
                logger.exception("Failed to serialize AG-UI debug payload", extra={"thread_id": t})
            # flush de pendientes si los había
            for p in _PENDING.pop(t, []):
                try:
                    yield _sse(p)
                except Exception:
                    logger.exception("Failed to serialize AG-UI pending payload", extra={"thread_id": t})
            # loop normal
            while True:
                payload = await q.get()
                try:
                    yield _sse(payload)
                except Exception:
                    logger.exception("Failed to serialize AG-UI payload", extra={"thread_id": t})
        except (asyncio.CancelledError, anyio.get_cancelled_exc_class()):
            return
        finally:
            try:
                if _SUBS.get(t) is q:
                    del _SUBS[t]
            except Exception:
                pass

    return Stream(gen(), headers=SSE_HEADERS)

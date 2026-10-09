# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/routes/v1/run_action.py

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from litestar import get, post, Request
from backend.http.audit import audit_temporary
from litestar.response import Response, Stream

from routes.v1.agui_notify import SSE_HEADERS
from services.json_safe import json_default, to_jsonable
from services.wizard_engine import apply_action, build_state_event, build_step_events, normalize_window_days
from services.wizard_runtime import (
    append_memory_events,
    get_memory_state,
    list_memory_events,
    has_memory_run,
)


def _sse(payload: Dict[str, Any]) -> str:
    safe_payload = to_jsonable(payload)
    return f"data: {json.dumps(safe_payload, default=json_default, ensure_ascii=False)}\n\n"


async def _stream_memory_events(run_id: str):
    sent_ids = set()
    last_heartbeat = asyncio.get_event_loop().time()
    while True:
        rows = list_memory_events(run_id)
        if rows:
            for row in rows:
                evt_id = str(row.event_id)
                if evt_id in sent_ids:
                    continue
                yield _sse({"type": row.type, "payload": row.payload})
                sent_ids.add(evt_id)
            last_heartbeat = asyncio.get_event_loop().time()
        else:
            now = asyncio.get_event_loop().time()
            if now - last_heartbeat >= 12:
                yield _sse({"type": "HEARTBEAT", "payload": {"run_id": run_id}})
                last_heartbeat = now
        await asyncio.sleep(0.5)


@get("/api/reconcile_wizard/runs/{run_id:str}/events", media_type="text/event-stream")
async def run_events(run_id: str) -> Stream | Response:
    if not has_memory_run(run_id):
        return Response({"ok": False, "message": "run_id invalido"}, status_code=404)

    async def gen():
        async for chunk in _stream_memory_events(run_id):
            yield chunk

    return Stream(gen(), headers=SSE_HEADERS)


@post("/api/reconcile_wizard/runs/{run_id:str}/action")
async def run_action(request: Request, run_id: str, data: Dict[str, Any]) -> Response:
    action_type = (data.get("action_type") or "").strip()
    payload = data.get("payload") or {}
    allowed = {
        "FORM_UPDATE",
        "LIST_SELECT",
        "CLICK",
        "CONFIRM",
        "SELECT_WINDOW",
        "SELECT_WINDOW_DAYS",
        "SELECT_SCOPE",
        "CONFIRM_START",
    }
    if action_type not in allowed:
        return Response({"ok": False, "message": "action_type invalido"}, status_code=400)

    if not has_memory_run(run_id):
        return Response({"ok": False, "message": "run_id invalido"}, status_code=404)

    state = get_memory_state(run_id)
    if not state:
        return Response({"ok": False, "message": "wizard_state no encontrado"}, status_code=404)

    preview = (state.get("context") or {}).get("preview") or {}
    if action_type == "SELECT_WINDOW_DAYS":
        selection = state.setdefault("selection", {})
        selection["window_days"] = normalize_window_days(
            payload.get("window_days"),
            selection.get("window_days"),
        )
        events = [build_state_event(state)]
    elif action_type == "SELECT_WINDOW":
        selection = state.setdefault("selection", {})
        selection["window_range"] = {
            "from": payload.get("from"),
            "to": payload.get("to"),
        }
        events = [build_state_event(state)]
        events.extend(build_step_events(state, preview))
    elif action_type == "SELECT_SCOPE":
        mode = (payload.get("mode") or "").upper()
        if mode == "ALL":
            mode = "ALL_RANGE"
        elif mode == "RANGE":
            mode = "WINDOW"
        events = []
        if mode == "ALL_RANGE":
            state, ev1 = apply_action(state, "FORM_UPDATE", {"scope_mode": "ALL"}, preview)
            state, ev2 = apply_action(state, "CLICK", {"id": "next"}, preview)
            events = ev1 + ev2
        elif mode == "MONTHS":
            state, ev1 = apply_action(state, "FORM_UPDATE", {"scope_mode": "MANUAL"}, preview)
            state, ev2 = apply_action(state, "CLICK", {"id": "next"}, preview)
            events = ev1 + ev2
            months = payload.get("months") or []
            if months:
                state, ev3 = apply_action(state, "LIST_SELECT", {"months": months}, preview)
                events += ev3
                state, ev4 = apply_action(state, "CLICK", {"id": "next"}, preview)
                events += ev4
        elif mode == "WINDOW":
            selection = state.setdefault("selection", {})
            selection["scope_mode"] = "WINDOW"
            selection["window_range"] = {
                "from": payload.get("from"),
                "to": payload.get("to"),
            }
            state["step"] = "WINDOW"
            events = [build_state_event(state)]
            events.extend(build_step_events(state, preview))
            window_range = selection.get("window_range") or {}
            if window_range.get("from") and window_range.get("to"):
                state["step"] = "SUMMARY"
                events = [build_state_event(state)]
                events.extend(build_step_events(state, preview))
        else:
            return Response({"ok": False, "message": "mode invalido"}, status_code=400)
    elif action_type == "CONFIRM_START":
        selection = state.setdefault("selection", {})
        confirmations = selection.setdefault("confirmations", {"all": False, "partial": False})
        pending = selection.get("pending_confirmation")
        if pending:
            confirmations[pending] = True
            selection["pending_confirmation"] = None
        state["step"] = "SUMMARY"
        events = [build_state_event(state)]
        events.extend(build_step_events(state, preview))
        events.append({
            "type": "TEXT_MESSAGE_ADD",
            "payload": {"role": "assistant", "text": "Plan listo. Iniciando conciliación."},
        })
        events.append({"type": "RUN_READY_TO_EXECUTE", "payload": {"ready": True}})
    else:
        state, events = apply_action(state, action_type, payload, preview)

    await audit_temporary(request, 'wizard_action_' + action_type.lower(), run_id)
    append_memory_events(run_id, events)

    return Response({"ok": True, "events": len(events), "persistence": "temporary"}, status_code=200)

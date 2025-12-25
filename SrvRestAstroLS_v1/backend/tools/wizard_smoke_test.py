# -*- coding: utf-8 -*-
# backend/tools/wizard_smoke_test.py
#
# Usage:
#   python backend/tools/wizard_smoke_test.py
#
# Env overrides:
#   WIZARD_BASE_URL=http://localhost:7058
#   WIZARD_WORKSPACE_ID=<uuid>

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, List, Tuple

import requests

import globalVar as Var
from services.db_pg import connect_db, get_workspace_by_slug


async def _resolve_workspace_id() -> str:
    workspace_id = os.environ.get("WIZARD_WORKSPACE_ID")
    if workspace_id:
        return workspace_id
    conn = await connect_db(connect_timeout=5.0, statement_timeout_ms=30000)
    try:
        return await get_workspace_by_slug(conn, Var.WORKSPACE_SLUG)
    finally:
        await conn.close()


def _post_json(url: str, payload: Dict[str, Any], timeout: int | Tuple[int, int] = 15) -> Dict[str, Any]:
    res = requests.post(url, json=payload, timeout=timeout)
    if not res.ok:
        raise RuntimeError(f"POST {url} failed: status={res.status_code} body={res.text[:300]}")
    # Validate that we got JSON and not something else (like SSE stream)
    if "application/json" not in res.headers.get("Content-Type", "").lower():
        raise RuntimeError(f"Respuesta no es JSON: {res.headers.get('Content-Type')}")
    return res.json()


def _read_first_sse_event(url: str, timeout: Tuple[int, int] = (5, 20)) -> Dict[str, Any]:
    with requests.get(url, stream=True, timeout=timeout) as res:
        if not res.ok:
            raise RuntimeError(f"SSE {url} failed: status={res.status_code} body={res.text[:300]}")
        for raw in res.iter_lines(decode_unicode=True):
            if not raw:
                continue
            if raw.startswith("data: "):
                data = raw[len("data: ") :]
                try:
                    return json.loads(data)
                except Exception:
                    return {"raw": data}
    raise RuntimeError("No SSE event received")


async def _fetch_events(run_id: str) -> List[Tuple[str, Dict[str, Any]]]:
    conn = await connect_db(connect_timeout=5.0, statement_timeout_ms=30000)
    try:
        rows = await conn.fetch(
            "SELECT type, payload FROM core_events WHERE run_id = $1 ORDER BY ts ASC, event_id ASC",
            run_id,
        )
    finally:
        await conn.close()
    
    def _ensure_dict(v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v or {}

    return [(row["type"], _ensure_dict(row["payload"])) for row in rows]


def _ordered_subset(haystack: List[str], needles: List[str]) -> bool:
    it = iter(haystack)
    return all(any(val == n for val in it) for n in needles)


async def main() -> None:
    default_base = f"http://127.0.0.1:{Var.PUERTO}"
    base_url = os.environ.get("WIZARD_BASE_URL", default_base)
    workspace_id = await _resolve_workspace_id()

    try:
        start_resp = await asyncio.to_thread(
            _post_json,
            f"{base_url}/api/reconcile_wizard/start",
            {
                "workspace_id": workspace_id,
                "bank": "fce",
                "account": "001",
                "dataset_ref": "mock",
            },
            20,
        )
    except Exception as exc:
        raise RuntimeError(f"Wizard start failed: {exc}") from exc
    if start_resp.get("status") not in ["ok", "started"]:
        raise RuntimeError(f"status inesperado: {start_resp}")
    run_id = start_resp.get("run_id")
    if not run_id:
        raise RuntimeError("run_id no recibido")
    if not isinstance(run_id, str):
        raise RuntimeError("run_id no es string")
    thread_id = start_resp.get("thread_id")
    if not thread_id:
        raise RuntimeError("thread_id no recibido")
    if not isinstance(thread_id, str):
        raise RuntimeError("thread_id no es string")
    sse_url = start_resp.get("sse_url")
    if not sse_url or run_id not in sse_url:
        raise RuntimeError("sse_url no contiene run_id")

    # The background task might take a few seconds to emit the first event
    sse_event = None
    deadline_sse = time.time() + 25
    while time.time() < deadline_sse:
        try:
            # SSE might take a moment to start streaming
            sse_event = await asyncio.to_thread(
                _read_first_sse_event,
                f"{base_url}/api/reconcile_wizard/runs/{run_id}/events",
            )
            if sse_event:
                break
        except Exception:
            await asyncio.sleep(1)

    if not sse_event:
        raise RuntimeError("SSE sin eventos tras 25s")

    actions = [
        {"action_type": "SELECT_SCOPE", "payload": {"mode": "MONTHS"}},
        {"action_type": "SELECT_SCOPE", "payload": {"mode": "MONTHS", "months": ["2025-06", "2025-07"]}},
        {"action_type": "CONFIRM_START", "payload": {}},
    ]

    for action in actions:
        await asyncio.to_thread(
            _post_json,
            f"{base_url}/api/reconcile_wizard/runs/{run_id}/action",
            action,
        )

    deadline = time.time() + 10
    events: List[Tuple[str, Dict[str, Any]]] = []
    types: List[str] = []
    while time.time() < deadline:
        events = await _fetch_events(run_id)
        types = [event_type for event_type, _payload in events]
        if "RUN_READY_TO_EXECUTE" in types and "LIST_SNAPSHOT" in types:
            break
        await asyncio.sleep(0.5)

    step_ids = [
        payload.get("step_id")
        for event_type, payload in events
        if event_type == "STEP_SET"
    ]
    if not _ordered_subset(step_ids, ["SCOPE", "MONTHS", "SUMMARY"]):
        raise RuntimeError("STEP_SET fuera de orden o incompletos")
    if "LIST_SNAPSHOT" not in types:
        raise RuntimeError("LIST_SNAPSHOT no emitido")
    if "FORM_SNAPSHOT" not in types:
        raise RuntimeError("FORM_SNAPSHOT no emitido")
    if "RUN_READY_TO_EXECUTE" not in types:
        raise RuntimeError("RUN_READY_TO_EXECUTE no emitido")

    print("Wizard smoke test OK")


if __name__ == "__main__":
    asyncio.run(main())

# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/routes/v1/reconcile_wizard_start.py

from __future__ import annotations

import logging
from typing import Any, Dict

from litestar import post
from litestar.response import Response

from globalVar import WORKSPACE_SLUG
from services.db_pg import (
    append_event as core_append_event,
    connect_db as core_connect_db,
    create_run as core_create_run,
    get_workspace_by_slug,
)
from services.parquet_preview import get_extract_preview
from services.wizard_engine import init_state, initial_events
from services.json_safe import to_jsonable

logger = logging.getLogger(__name__)


@post("/api/reconcile_wizard/start")
async def reconcile_wizard_start(data: Dict[str, Any]) -> Response:
    workspace_id = data.get("workspace_id")
    bank = data.get("bank") or ""
    account = data.get("account") or ""
    dataset_ref = data.get("dataset_ref") or ""

    conn = await core_connect_db()
    try:
        try:
            if not workspace_id:
                try:
                    workspace_id = await get_workspace_by_slug(conn, WORKSPACE_SLUG)
                except Exception:
                    return Response({"ok": False, "message": "workspace_id requerido"}, status_code=400)
            workspace_exists = await conn.fetchval(
                "SELECT 1 FROM core_workspaces WHERE workspace_id = $1",
                workspace_id,
            )
            if not workspace_exists:
                return Response({"ok": False, "message": "workspace_id invalido"}, status_code=400)

            run_id = await core_create_run(
                conn,
                workspace_id=workspace_id,
                kind="reconcile_wizard",
                params={
                    "bank": bank,
                    "account": account,
                    "dataset_ref": dataset_ref,
                },
            )

            preview = get_extract_preview(dataset_ref, bank, account)
            state = init_state(
                {"bank": bank, "account": account, "dataset_ref": dataset_ref},
                preview,
            )
            events = initial_events(run_id, state, preview)
            for event in events:
                payload = to_jsonable(event.get("payload") or {})
                await core_append_event(
                    conn,
                    workspace_id=workspace_id,
                    run_id=run_id,
                    type=event["type"],
                    payload=payload,
                )
        except Exception:
            logger.exception("reconcile_wizard_start failed")
            raise
    finally:
        await conn.close()

    run_id_str = str(run_id)
    thread_id = f"wizard-{run_id_str}"
    return Response(
        {
            "status": "ok",
            "run_id": run_id_str,
            "thread_id": thread_id,
            "sse_url": f"/api/reconcile_wizard/runs/{run_id_str}/events",
        },
        status_code=200,
    )

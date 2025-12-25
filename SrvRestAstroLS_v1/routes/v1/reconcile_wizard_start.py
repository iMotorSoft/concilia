# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/routes/v1/reconcile_wizard_start.py

from __future__ import annotations

import asyncio
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


async def _initialize_wizard_background(
    workspace_id: Any,
    run_id: Any,
    bank: str,
    account: str,
    dataset_ref: str,
):
    """
    Background task to initialize the wizard state and append initial events.
    """
    logger.info(f"Starting background initialization for run_id={run_id}")
    conn = await core_connect_db(connect_timeout=10.0, statement_timeout_ms=15000)
    try:
        # Simulate heavy work or actually do it
        preview = get_extract_preview(dataset_ref, bank, account)
        state = init_state(
            {"bank": bank, "account": account, "dataset_ref": dataset_ref},
            preview,
        )
        events = initial_events(str(run_id), state, preview)
        
        for event in events:
            payload = to_jsonable(event.get("payload") or {})
            await core_append_event(
                conn,
                workspace_id=workspace_id,
                run_id=run_id,
                type=event["type"],
                payload=payload,
            )
        logger.info(f"Background initialization finished for run_id={run_id}")
    except Exception:
        logger.exception(f"Background initialization failed for run_id={run_id}")
        # Option: append a FAILURE event so the UI knows.
        try:
            await core_append_event(
                conn,
                workspace_id=workspace_id,
                run_id=run_id,
                type="RUN_FAILED",
                payload={"error": "Initialization failed"},
            )
        except Exception:
            logger.exception("Failed to append RUN_FAILED event")
    finally:
        await conn.close()


@post("/api/reconcile_wizard/start")
async def reconcile_wizard_start(data: Dict[str, Any]) -> Response:
    workspace_id = data.get("workspace_id")
    bank = data.get("bank") or ""
    account = data.get("account") or ""
    dataset_ref = data.get("dataset_ref") or ""

    logger.info(f"reconcile_wizard_start: bank={bank}, account={account}, dataset_ref={dataset_ref}")

    conn = await core_connect_db(connect_timeout=10.0, statement_timeout_ms=15000)
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
    except Exception:
        logger.exception("Failed to create run for reconcile_wizard")
        return Response({"ok": False, "message": "Error al crear el run"}, status_code=500)
    finally:
        await conn.close()

    run_id_str = str(run_id)
    thread_id = f"wizard-{run_id_str}"

    # Fire and forget the heavy initialization
    asyncio.create_task(
        _initialize_wizard_background(workspace_id, run_id, bank, account, dataset_ref)
    )

    return Response(
        {
            "status": "started",
            "run_id": run_id_str,
            "thread_id": thread_id,
            "sse_url": f"/api/reconcile_wizard/runs/{run_id_str}/events",
        },
        status_code=200,
    )

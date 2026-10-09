# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/routes/v1/reconcile_wizard_start.py

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4
from typing import Any, Dict

from litestar import post, Request
from backend.http.audit import audit_temporary
from litestar.response import Response

from services.parquet_preview import get_extract_preview
from services.wizard_engine import init_state, initial_events
from services.wizard_runtime import append_memory_events, create_memory_run

logger = logging.getLogger(__name__)


async def _initialize_wizard_background(
    run_id: Any,
    bank: str,
    account: str,
    dataset_ref: str,
    uri_extracto: str | None,
    uri_contable: str | None,
    security,
    actor,
    correlation,
):
    """
    Background task to initialize the wizard state and append initial events.
    """
    logger.info(f"Starting background initialization for run_id={run_id}")
    try:
        preview = get_extract_preview(
            dataset_ref,
            bank,
            account,
            uri_extracto=uri_extracto,
            uri_contable=uri_contable,
        )
        state = init_state(
            {"bank": bank, "account": account, "dataset_ref": dataset_ref},
            preview,
        )
        events = initial_events(str(run_id), state, preview)
        await security.audit_operation(actor, 'wizard_initialized_temporary', str(run_id), 'SUCCESS',
                                       correlation, 'in_memory_only; not a durable financial decision')
        append_memory_events(str(run_id), events)
        logger.info(f"Background initialization finished for run_id={run_id}")
    except Exception:
        await security.audit_operation(actor, 'wizard_initialize_error', str(run_id), 'FAILURE',
                                       correlation, 'initialization failed; no durable financial decision')
        logger.exception(f"Background initialization failed for run_id={run_id}")
        try:
            append_memory_events(
                str(run_id),
                [{"type": "RUN_FAILED", "payload": {"error": "Initialization failed"}}],
            )
        except Exception:
            logger.exception("Failed to append RUN_FAILED event")


@post("/api/reconcile_wizard/start")
async def reconcile_wizard_start(request: Request, data: Dict[str, Any]) -> Response:
    workspace_id = data.get("workspace_id")
    bank = data.get("bank") or ""
    account = data.get("account") or ""
    dataset_ref = data.get("dataset_ref") or ""
    uri_extracto = data.get("uri_extracto")
    uri_contable = data.get("uri_contable")

    logger.info(f"reconcile_wizard_start: bank={bank}, account={account}, dataset_ref={dataset_ref}")

    run_id = str(uuid4())
    await audit_temporary(request, 'wizard_start_temporary', run_id)
    run_id = create_memory_run(
        {
            "kind": "reconcile_wizard",
            "actor_id": str(request.state.principal.id),
            "workspace_id": workspace_id,
            "bank": bank,
            "account": account,
            "dataset_ref": dataset_ref,
            "uri_extracto": uri_extracto,
            "uri_contable": uri_contable,
        },
        run_id=run_id,
    )

    run_id_str = str(run_id)
    thread_id = f"wizard-{run_id_str}"

    # Fire and forget the heavy initialization
    asyncio.create_task(
        _initialize_wizard_background(
            run_id,
            bank,
            account,
            dataset_ref,
            uri_extracto,
            uri_contable,
            request.app.state.security,
            request.state.principal.id,
            request.state.correlation_id,
        )
    )

    return Response(
        {
            "status": "started",
            "persistence": "temporary",
            "run_id": run_id_str,
            "thread_id": thread_id,
            "sse_url": f"/api/reconcile_wizard/runs/{run_id_str}/events",
        },
        status_code=200,
    )

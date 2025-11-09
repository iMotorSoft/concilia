# SrvRestAstroLS_v1/routes/v1/ingest_confirm.py
from __future__ import annotations
from typing import Dict, Any
from litestar import post
from litestar.params import Body
from uuid import uuid4
from .agui_notify import emit

@post("/api/ingest/confirm")
async def ingest_confirm(
    threadId: str = Body(),
    correlationId: str | None = Body(default=None),
    source_file_id: str = Body(),
    original_uri: str = Body(),
    account_id: str | None = Body(default=None),
    bank: str | None = Body(default=None),
    period_from: str | None = Body(default=None),  # YYYY-MM-DD
    period_to: str | None = Body(default=None),    # YYYY-MM-DD
) -> Dict[str, Any]:
    # En este paso arrancamos la corrida (RUN_START). El procesamiento real llega en el próximo paso.
    run_id = str(uuid4())
    await emit(threadId, {
        "type": "RUN_START",
        "payload": {
            "run_id": run_id,
            "status": "starting",
            "source_file_id": source_file_id,
            "original_uri": original_uri,
            "account_id": account_id,
            "bank": bank,
            "period_from": period_from,
            "period_to": period_to
        }
    })
    return {"ok": True, "message": "Confirmado. Iniciando análisis…", "run_id": run_id}


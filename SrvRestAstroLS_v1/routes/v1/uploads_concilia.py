# SrvRestAstroLS_v1/routes/v1/uploads_concilia.py
from __future__ import annotations

from typing import Any
from litestar import post
from litestar.params import Body
from uuid import uuid4
from urllib.parse import urlparse
from pathlib import Path
import shutil

import globalVar as G
from .agui_notify import emit

@post("/api/uploads/bank-movements")
async def upload_bank_movements(
    account_id: str = Body(media_type="multipart/form-data"),
    period: str = Body(media_type="multipart/form-data"),
    profile_id: str = Body(media_type="multipart/form-data"),
    file: Any = Body(media_type="multipart/form-data"),
    threadId: str | None = Body(media_type="multipart/form-data"),
    correlationId: str | None = Body(media_type="multipart/form-data"),
) -> dict:
    # 1) Guardar original en storage/incoming
    filename = file.filename
    tmp_path = Path(f"/tmp/{uuid4()}_{filename}")
    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    original_uri = G.resolve_storage_uri("incoming", filename=filename)
    if original_uri.startswith("file://"):
        dst = Path(urlparse(original_uri).path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(tmp_path, dst)
    else:
        raise NotImplementedError("Sólo provider local habilitado por ahora")

    # 2) IDs para tracking
    source_file_id = str(uuid4())
    run_id = str(uuid4())

    # 3) Emitir inicio de run por SSE
    await emit(threadId, {
        "type": "RUN_START",
        "payload": {
            "run_id": run_id,
            "status": "starting",
            "account_id": account_id,
            "period": period,
            "profile_id": profile_id
        }
    })

    # 4) Respuesta HTTP
    return {
        "ok": True,
        "message": "Archivo recibido. Iniciando análisis…",
        "source_file_id": source_file_id,
        "run_id": run_id,
        "original_uri": original_uri
    }


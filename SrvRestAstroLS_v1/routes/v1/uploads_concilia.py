# SrvRestAstroLS_v1/routes/v1/uploads_concilia.py
from __future__ import annotations
import asyncio
import shutil
import traceback
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from typing import Any

from litestar import post
from litestar.response import Response

import globalVar as Var
from .agui_notify import emit
from services.ingest.sniff_bank import sniff_file

@post("/api/uploads/bank-movements")  # ⬅️ Quitamos media_type=MULTI_PART
async def upload_bank_movements(request: Any) -> Response:
    """
    Recibe multipart/form-data:
      - file: archivo a subir (xlsx/csv)
      - threadId, correlationId, account_id, period, profile_id (opcionales)
    """
    try:
        # 0) Parsear multipart directo (Starlette-like)
        form = await request.form()
        file = form.get("file")
        threadId = form.get("threadId")
        correlationId = form.get("correlationId")
        account_id = form.get("account_id")
        period = form.get("period")
        profile_id = form.get("profile_id")

        if file is None:
            return Response(
                {"ok": False, "message": "Falta campo 'file' en multipart."},
                status_code=400,
                media_type="application/json",
            )

        # 1) Guardar a /tmp en streaming
        filename = getattr(file, "filename", None) or f"upload_{uuid4()}.bin"
        tmp_path = Path(f"/tmp/{uuid4()}_{filename}")
        bytes_written = 0
        with open(tmp_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                bytes_written += len(chunk)

        # 2) Mover a storage/incoming
        original_uri = Var.resolve_storage_uri("incoming", filename=filename)
        if not original_uri.startswith("file://"):
            return Response(
                {"ok": False, "message": "Storage provider no soportado."},
                status_code=500,
                media_type="application/json",
            )

        dst = Path(urlparse(original_uri).path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(tmp_path, dst)

        # 3) Sniff
        intel = sniff_file(dst, filename_hint=filename)
        source_file_id = str(uuid4())

        # 4) Emitir vista previa por SSE (no bloquear)
        if threadId:
            payload = {
                "type": "INGEST_PREVIEW",
                "payload": {
                    "source_file_id": source_file_id,
                    "original_uri": original_uri,
                    "detected": {
                        "bank": intel.get("detected", {}).get("bank"),
                        "account_core_dv": intel.get("detected", {}).get("account_core_dv"),
                        "account_full": intel.get("detected", {}).get("account_full"),
                        "header_excerpt": intel.get("detected", {}).get("header_excerpt"),
                        "period_from": intel.get("detected", {}).get("period_from"),
                        "period_to": intel.get("detected", {}).get("period_to"),
                    },
                    "table": intel.get("table", {}),
                    "suggest": intel.get("suggest", {}),
                    "needs": intel.get("needs", {}),
                    "kind": intel.get("kind"),
                    "meta": {
                        "bytes_written": bytes_written,
                        "filename": filename,
                        "account_id": account_id,
                        "period": period,
                        "profile_id": profile_id,
                        "correlationId": correlationId,
                    },
                },
            }
            asyncio.create_task(emit(threadId, payload))

        # 5) Responder inmediato (JSON)
        return Response(
            {
                "ok": True,
                "message": "Archivo recibido. Mostrando vista previa…",
                "source_file_id": source_file_id,
                "original_uri": original_uri,
                "kind": intel.get("kind"),
                "bytes_written": bytes_written,
                "filename": filename,
            },
            status_code=200,
            media_type="application/json",  # ⬅️ Aseguramos JSON
        )

    except Exception as e:
        tb = traceback.format_exc(limit=12)
        print("[upload_bank_movements] ERROR:", type(e).__name__, str(e), flush=True)
        print(tb, flush=True)
        # feedback no bloqueante al SSE, si hay thread
        try:
            form = await request.form()
            threadId = form.get("threadId")
            if threadId:
                asyncio.create_task(emit(threadId, {
                    "type": "TOAST",
                    "level": "error",
                    "message": f"Upload error: {type(e).__name__}: {e}"
                }))
        except Exception:
            pass

        return Response(
            {"ok": False, "message": "Error interno en upload", "error": f"{type(e).__name__}: {e}", "trace": tb},
            status_code=500,
            media_type="application/json",
        )

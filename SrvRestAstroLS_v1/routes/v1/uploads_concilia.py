# SrvRestAstroLS_v1/routes/v1/uploads_concilia.py
from __future__ import annotations
import asyncio
import traceback
from pathlib import Path
from uuid import uuid4
from typing import Any

from litestar import post
from litestar.response import Response

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

        # Same controlled, non-overwriting storage and persistent IDs as v2.
        from .uploads_v2_concilia import _save_upload_to_incoming
        filename = Path(str(getattr(file, "filename", ""))).name
        if Path(filename).suffix.lower() not in {".xlsx", ".xls", ".xlsm", ".xltx", ".xltm", ".csv"}:
            return Response({"ok": False, "message": "Formato de archivo no permitido"}, status_code=400)
        _, dst, bytes_written, filename = await _save_upload_to_incoming(file, prefix="extracto")
        source_file_id = await request.app.state.files.register(
            dst, "extracto", request.state.principal.id, uuid4())
        original_uri = source_file_id
        intel = sniff_file(dst, filename_hint=filename)

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
                    "message": "Error interno en upload"
                }))
        except Exception:
            pass

        return Response(
            {"ok": False, "message": "Error interno en upload"},
            status_code=500,
            media_type="application/json",
        )

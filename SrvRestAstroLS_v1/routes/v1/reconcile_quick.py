# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/routes/v1/reconcile_quick.py

from __future__ import annotations
import asyncio
import shutil
import traceback
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from typing import Any, Optional, Dict

from litestar import post
from litestar.response import Response

import globalVar as Var
from .agui_notify import emit
from services.reconcile.quick_match import reconcile_from_paths

def _save_form_file(file, prefix: str = "upload") -> tuple[str, Path]:
    filename = getattr(file, "filename", None) or f"{prefix}_{uuid4()}.bin"
    tmp_path = Path(f"/tmp/{uuid4()}_{filename}")
    bytes_written = 0
    with open(tmp_path, "wb") as out:
        while True:
            chunk = asyncio.get_event_loop().run_until_complete(file.read(1024 * 1024))
            if not chunk:
                break
            out.write(chunk)
            bytes_written += len(chunk)
    # mover a storage/incoming
    original_uri = Var.resolve_storage_uri("incoming", filename=filename)
    dst = Path(urlparse(original_uri).path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(tmp_path, dst)
    return original_uri, dst

@post("/api/reconcile/quick")
async def reconcile_quick(request: Any) -> Response:
    """
    Recibe multipart/form-data:
      - bank_file: Excel/csv de extracto bancario
      - gl_file:   Excel contable (PILAGA)
      - threadId (opcional) → emite RECONCILE_SNAPSHOT por SSE
      - days_tolerance (opcional, default 3)
    """
    try:
        form = await request.form()
        bank_file = form.get("bank_file")
        gl_file   = form.get("gl_file")
        threadId  = form.get("threadId")
        days_tol  = form.get("days_tolerance") or "3"

        if not bank_file or not gl_file:
            return Response({"ok": False, "message": "Faltan archivos (bank_file / gl_file)."},
                            status_code=400, media_type="application/json")

        try:
            days_tolerance = int(str(days_tol))
        except Exception:
            days_tolerance = 3

        bank_uri, bank_path = _save_form_file(bank_file, prefix="bank")
        gl_uri, gl_path     = _save_form_file(gl_file, prefix="gl")

        result = reconcile_from_paths(bank_path, gl_path, days_tolerance=days_tolerance)

        # opcional: evento SSE
        if threadId:
            asyncio.create_task(emit(threadId, {
                "type": "RECONCILE_SNAPSHOT",
                "payload": {
                    "bank_uri": bank_uri,
                    "gl_uri": gl_uri,
                    "summary": result.get("summary", {}),
                    "matched": result.get("matched", []),
                    "unmatched_bank": result.get("unmatched_bank", []),
                    "unmatched_gl": result.get("unmatched_gl", []),
                }
            }))

        return Response({
            "ok": True,
            "message": "Conciliación generada",
            "bank_uri": bank_uri,
            "gl_uri": gl_uri,
            "result": result
        }, status_code=200, media_type="application/json")

    except Exception as e:
        tb = traceback.format_exc(limit=12)
        print("[reconcile_quick] ERROR:", type(e).__name__, str(e), flush=True)
        print(tb, flush=True)
        try:
            form = await request.form()
            threadId = form.get("threadId")
            if threadId:
                asyncio.create_task(emit(threadId, {
                    "type": "TOAST", "level": "error",
                    "message": f"Reconcile error: {type(e).__name__}: {e}"
                }))
        except Exception:
            pass

        return Response({"ok": False, "message": "Error interno en reconcile", "error": f"{type(e).__name__}: {e}", "trace": tb},
                        status_code=500, media_type="application/json")


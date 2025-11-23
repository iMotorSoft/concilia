# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/routes/v1/uploads_v2_concilia.py
from __future__ import annotations
import asyncio
import shutil
import traceback
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from typing import Any, Optional

from litestar import post
from litestar.response import Response
from litestar.enums import MediaType  # 👈 usamos MediaType.JSON

import globalVar as Var
from .agui_notify import emit
from services.ingest.sniff_bank import sniff_file

def _merge_validation_for_role(intel: dict, role: str) -> dict | None:
    """Combina la validación base con un error de tipo si role != kind detectado."""
    base = intel.get("validation") or None
    kind = (intel.get("kind") or "").lower()
    mismatch_error: str | None = None
    if role == "extracto" and kind and kind != "bank_movements":
        mismatch_error = f"Se detectó tipo '{kind}' y no parece extracto bancario."
    if role == "contable" and kind and kind != "gl":
        mismatch_error = f"Se detectó tipo '{kind}' y no parece contable/PILAGA."

    if not mismatch_error:
        return base

    errors = list(base.get("errors") or []) if base else []
    warnings = list(base.get("warnings") or []) if base else []
    errors.append(mismatch_error)
    return {"is_valid": False, "errors": errors, "warnings": warnings}


async def _handle_upload(request: Any, role_required: Optional[str] = None, path_label: str = "v2") -> Response:
    try:
        role = (role_required or (request.query_params.get("role") or "")).strip().lower()
        if role not in {"extracto", "contable"}:
            return Response(
                content={"ok": False, "message": "role inválido (use extracto|contable)"},
                media_type=MediaType.JSON,
                status_code=400,
            )

        form = await request.form()
        file = form.get("file")
        threadId = form.get("threadId")
        correlationId = form.get("correlationId")

        if file is None:
            return Response(
                content={"ok": False, "message": "Falta campo 'file' en multipart."},
                media_type=MediaType.JSON,
                status_code=400,
            )

        # 1) Guardar a /tmp (stream)
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
                content={"ok": False, "message": "Storage provider no soportado."},
                media_type=MediaType.JSON,
                status_code=500,
            )

        dst = Path(urlparse(original_uri).path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(tmp_path, dst)

        # 3) Sniff de contenido
        intel = sniff_file(dst, filename_hint=filename)
        source_file_id = str(uuid4())
        validation = _merge_validation_for_role(intel, role)
        needs = dict(intel.get("needs", {}))
        if validation is not None and validation.get("is_valid") is False and role == "extracto":
            needs["valid_extracto"] = True
        if validation is not None and validation.get("is_valid") is False and role == "contable":
            needs["valid_contable"] = True

        # 4) Emitir preview al topic por SSE
        if threadId:
            payload = {
                "type": "INGEST_PREVIEW",
                "payload": {
                    "role": role,
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
                    "needs": needs,
                    "kind": intel.get("kind"),
                    "validation": validation or intel.get("validation"),
                    "meta": {
                        "bytes_written": bytes_written,
                        "filename": filename,
                        "correlationId": correlationId,
                        "path": path_label,
                    },
                },
            }
            asyncio.create_task(emit(threadId, payload))

        # 5) Responder ya (JSON explícito)
        return Response(
            content={
                "ok": True,
                "message": "Archivo recibido. Mostrando vista previa…",
                "source_file_id": source_file_id,
                "original_uri": original_uri,
                "kind": intel.get("kind"),
                "bytes_written": bytes_written,
                "filename": filename,
                "role": role,
                "path": path_label,
            },
            media_type=MediaType.JSON,
            status_code=200,
        )

    except Exception as e:
        tb = traceback.format_exc(limit=12)
        print(f"[upload_ingest_{path_label}] ERROR:", type(e).__name__, str(e), flush=True)
        print(tb, flush=True)
        try:
            form = await request.form()
            threadId = form.get("threadId")
            if threadId:
                asyncio.create_task(emit(threadId, {
                    "type": "TOAST", "level": "error",
                    "message": f"Upload error: {type(e).__name__}: {e} ({path_label})"
                }))
        except Exception:
            pass
        return Response(
            content={"ok": False, "message": f"Error interno en upload ({path_label})", "error": f"{type(e).__name__}: {e}", "trace": tb},
            media_type=MediaType.JSON,
            status_code=500,
        )


# Ruta nueva (v2) — respondemos JSON
@post("/api/uploads/v2/ingest", media_type=MediaType.JSON)
async def upload_ingest_v2(request: Any) -> Response:
    return await _handle_upload(request, role_required=None, path_label="v2")


# Alias compatible (vieja) — también JSON
@post("/api/uploads/v2/ingest", media_type=MediaType.JSON)
async def upload_ingest_alias(request: Any) -> Response:
    role = (request.query_params.get("role") or "extracto").strip().lower()
    return await _handle_upload(request, role_required=role, path_label="alias")

# SrvRestAstroLS_v1/routes/v1/uploads_ingest.py
from __future__ import annotations
import asyncio, shutil, traceback
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from typing import Any, Optional

from litestar import post
from litestar.response import Response

import globalVar as Var
from .agui_notify import emit
from services.ingest.sniff_bank import sniff_file

def _bad(status: int, msg: str) -> Response:
    return Response({"ok": False, "message": msg}, status_code=status, media_type="application/json")

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

@post("/api/uploads/ingest")
async def uploads_ingest(request: Any) -> Response:
    try:
        # 0) Chequear content-type
        ctype = (request.headers.get("content-type") or "").lower()
        if "multipart/form-data" not in ctype:
            return _bad(415, f"Content-Type inválido: {ctype} (se espera multipart/form-data)")

        # 1) Intentar parsear form
        try:
            form = await request.form()
        except AssertionError as e:
            # típico cuando falta python-multipart
            return _bad(500, f"Falta 'python-multipart' para parsear forms: {e}")
        except Exception as e:
            return _bad(400, f"No se pudo leer multipart/form-data: {type(e).__name__}: {e}")

        file = form.get("file")
        threadId = (form.get("threadId") or "").strip() or None
        correlationId = (form.get("correlationId") or "").strip() or None

        # role por query o form
        q_role = (request.query_params.get("role") or "").strip().lower()  # type: ignore
        f_role = (form.get("role") or "").strip().lower()
        role = q_role or f_role
        if role not in ("extracto", "contable"):
            return _bad(400, "role inválido (usar extracto | contable)")

        if file is None:
            return _bad(400, "Falta campo 'file' en multipart.")

        # 2) Guardar a /tmp (streaming)
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

        # 3) Mover a storage/incoming
        original_uri = Var.resolve_storage_uri("incoming", filename=filename)
        if not original_uri.startswith("file://"):
            return _bad(500, "Storage provider no soportado (solo 'local' por ahora).")

        dst = Path(urlparse(original_uri).path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(tmp_path, dst)

        # 4) Sniff
        intel = sniff_file(dst, filename_hint=filename)
        source_file_id = str(uuid4())
        validation = _merge_validation_for_role(intel, role)
        needs = dict(intel.get("needs", {}))
        if validation is not None and validation.get("is_valid") is False and role == "extracto":
            needs["valid_extracto"] = True
        if validation is not None and validation.get("is_valid") is False and role == "contable":
            needs["valid_contable"] = True

        # 5) Emitir PREVIEW por SSE
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
                    },
                },
            }
            asyncio.create_task(emit(threadId, payload))

        # 6) Responder JSON
        return Response(
            {
                "ok": True,
                "message": "Archivo recibido. Mostrando vista previa…",
                "role": role,
                "source_file_id": source_file_id,
                "original_uri": original_uri,
                "kind": intel.get("kind"),
                "bytes_written": bytes_written,
                "filename": filename,
            },
            status_code=200,
            media_type="application/json",
        )

    except Exception as e:
        # Log explícito + feedback por SSE si hay threadId
        tb = traceback.format_exc(limit=20)
        print("[uploads_ingest] ERROR:", type(e).__name__, str(e))
        print(tb)
        try:
            # ojo: volver a leer el form puede fallar; intentar obtener threadId con query
            threadId = (request.query_params.get("threadId") or "").strip() or None  # type: ignore
            if threadId:
                asyncio.create_task(emit(threadId, {
                    "type": "TOAST", "level": "error",
                    "message": f"Upload error: {type(e).__name__}: {e}"
                }))
        except Exception:
            pass
        return Response(
            {"ok": False, "message": f"Error interno en upload: {type(e).__name__}", "error": str(e)},
            status_code=500,
            media_type="application/json",
        )

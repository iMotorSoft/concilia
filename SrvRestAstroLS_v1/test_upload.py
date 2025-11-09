# test_upload_starlette.py
from __future__ import annotations
import os, re, traceback
from pathlib import Path
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

UPLOAD_DIR = Path("./_uploads").resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
SAFE_NAME_RX = re.compile(r"[^A-Za-z0-9._-]+")

def sanitize_filename(name: str) -> str:
    return (SAFE_NAME_RX.sub("_", os.path.basename(name or "upload.bin")).strip("._") or "upload.bin")

async def health(request):
    return JSONResponse({"ok": True, "upload_dir": str(UPLOAD_DIR)})

async def upload(request):
    try:
        form = await request.form()
        file = form.get("file")
        if file is None:
            return JSONResponse({"ok": False, "error": "Falta campo 'file' en multipart."}, status_code=400)

        original_name = file.filename or "upload.bin"
        content_type  = file.content_type
        safe_name     = sanitize_filename(original_name)
        dest          = UPLOAD_DIR / safe_name

        # streaming por chunks
        bytes_written = 0
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                bytes_written += len(chunk)

        return JSONResponse({
            "ok": True,
            "filename": original_name,
            "saved_as": str(dest),
            "bytes_written": bytes_written,
            "content_type": content_type,
        })
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        tb  = traceback.format_exc(limit=8)
        print("UPLOAD ERROR:", err, "\n", tb, flush=True)
        return JSONResponse({"ok": False, "error": err, "trace": tb}, status_code=500)

app = Starlette(routes=[
    Route("/health", health),
    Route("/upload", upload, methods=["POST"]),
])


# SrvRestAstroLS_v1/ls_iMotorSoft_Srv01.py
# gunicorn ls_iMotorSoft_Srv01:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:7058

from __future__ import annotations

import sys
from pathlib import Path
from litestar import Litestar
from litestar.config.cors import CORSConfig
from litestar import get
import uvicorn
import globalVar as Var

# sys.path a la raíz del proyecto
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Rutas productivas
from routes.v1.agui_notify import notify_stream           # GET  /api/ag-ui/notify/stream
from routes.v1.chat_concilia import chat_turn             # POST /api/chat/turn
from routes.v1.uploads_concilia import upload_bank_movements  # POST /api/uploads/bank-movements
from routes.v1.ingest_confirm import ingest_confirm          # POST /api/ingest/confirm


route_handlers = [
    notify_stream,
    chat_turn,
    upload_bank_movements,
    ingest_confirm,
]

# --- CORS ---
if Var.DEBUG:
    # DEV: abrir CORS totalmente para evitar preflight 400
    cors_config = CORSConfig(
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Content-Type"],
        allow_credentials=False,
        max_age=86400,
    )
else:
    # PROD: lista blanca explícita
    cors_config = CORSConfig(
        allow_origins=[
            "https://tu-dominio-front.com",
        ],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Content-Type",
            "Authorization",
            "Cache-Control",
            "Last-Event-ID",
            "X-Requested-With",
        ],
        expose_headers=["Content-Type"],
        allow_credentials=False,
        max_age=86400,
    )

app = Litestar(route_handlers=route_handlers, cors_config=cors_config)

if __name__ == "__main__":
    try:
        import globalVar as G
        G.ensure_local_dirs()
        G.boot_log()
    except Exception:
        pass

    uvicorn.run(
        "ls_iMotorSoft_Srv01:app",
        host=Var.HOST,
        port=Var.PUERTO,
        reload=Var.DEBUG,
    )

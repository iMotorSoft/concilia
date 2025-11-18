# -*- coding: utf-8 -*-
# SrvRestAstroLS_v1/ls_iMotorSoft_Srv01.py
# gunicorn ls_iMotorSoft_Srv01:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:7058
from __future__ import annotations

import sys
from pathlib import Path
from litestar import Litestar, get
from litestar.config.cors import CORSConfig
import uvicorn
import globalVar as Var

# sys.path a la raíz del proyecto
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Rutas productivas
from routes.v1.agui_notify import notify_stream
from routes.v1.chat_concilia import chat_turn
from routes.v1.ingest_confirm import ingest_confirm

# v1 (existente)
from routes.v1.uploads_concilia import upload_bank_movements
# v2 (NUEVA) — la que usa ReconciliarApp.svelte
from routes.v1.uploads_v2_concilia import upload_ingest_v2
from routes.v1.reconcile_start import reconcile_start          # <-- NUEVO
from routes.v1.reconcile_details import (
    reconcile_details,
    reconcile_details_no_banco,
    reconcile_details_pares,
    reconcile_details_no_contable,
    reconcile_details_n1_grupos,
    reconcile_details_n1_sugeridos,  # <--- NUEVO
)  # <--- NUEVO
from routes.v1.reconcile_summary import (
    reconcile_summary,              # resumen completo (compatibilidad)
    reconcile_summary_head,         # solo head (totales)
    reconcile_summary_descomposicion,  # solo descomposición
)  # NUEVO



route_handlers = [
    notify_stream,
    chat_turn,
    ingest_confirm,
    upload_bank_movements,  # dejamos la v1 por compat
    upload_ingest_v2,       # montamos v2
    reconcile_start,        # montamos reconcile_start
    reconcile_details,      # montamos reconcile_details
    reconcile_details_no_banco,  # endpoint específico por card
    reconcile_details_pares,  # endpoint para concilios 1→1
    reconcile_details_no_contable,  # endpoint específico por card (Banco no reflejado en PILAGA)
    reconcile_details_n1_grupos,  # endpoint específico por card (Agrupados aprobados)
    reconcile_details_n1_sugeridos,  # endpoint específico por card (Sugeridos N→1)
    reconcile_summary,      # montamos reconcile_summary
    reconcile_summary_head,  # montamos head
    reconcile_summary_descomposicion,  # montamos descomposición
]


# --- CORS ---
if Var.DEBUG:
    cors_config = CORSConfig(
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Content-Type"],
        allow_credentials=False,
        max_age=86400,
    )
else:
    cors_config = CORSConfig(
        allow_origins=["https://tu-dominio-front.com"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "Authorization", "Cache-Control", "Last-Event-ID", "X-Requested-With"],
        expose_headers=["Content-Type"],
        allow_credentials=False,
        max_age=86400,
    )

app = Litestar(route_handlers=route_handlers, cors_config=cors_config)

if __name__ == "__main__":
    try:
        Var.ensure_local_dirs()
    except Exception:
        pass
    uvicorn.run(
        "ls_iMotorSoft_Srv01:app",
        host=Var.HOST,
        port=Var.PUERTO,
        reload=Var.DEBUG,
    )

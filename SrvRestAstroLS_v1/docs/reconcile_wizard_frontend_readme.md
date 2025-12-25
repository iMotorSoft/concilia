# Wizard UX Quick Check
- Start backend + frontend, upload and confirm extracto/contable, then click "Abrir asistente de conciliacion": the modal opens immediately and the network shows POST `/api/reconcile_wizard/start` with a non-empty `account`.
- Verify SSE connects to `/api/reconcile_wizard/runs/{run_id}/events` and the modal moves from "Inicializando..." to Step 1.
- Confirm the scope in the wizard and ensure `/api/reconcile/start` is not called until the final confirmation.
- Smoke test: `python backend/tools/wizard_smoke_test.py` (override base URL with `WIZARD_BASE_URL=http://host:port`).

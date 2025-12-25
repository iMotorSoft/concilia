# backend/tools/agui_sse_smoke_test.py
#
# Usage:
#   python backend/tools/agui_sse_smoke_test.py
#
# Purpose:
#   Ensure SSE payload serialization handles UUID and datetime types safely.

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone

from routes.v1.agui_notify import _sse


def _parse_sse_line(sse_payload: str) -> dict:
    line = sse_payload.splitlines()[0]
    if not line.startswith("data: "):
        raise RuntimeError("SSE payload missing data: prefix")
    raw = line[len("data: ") :]
    return json.loads(raw)


def main() -> None:
    run_id = uuid.uuid4()
    payload = {
        "type": "RUN_START",
        "payload": {
            "run_id": run_id,
            "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            "report_date": date(2025, 1, 2),
            "nested": [
                {"ids": {uuid.uuid4(), uuid.uuid4()}},
                ("tuple", uuid.uuid4()),
            ],
        },
    }

    sse_payload = _sse(payload)
    parsed = _parse_sse_line(sse_payload)

    parsed_payload = parsed.get("payload", {})
    if parsed_payload.get("run_id") != str(run_id):
        raise RuntimeError("run_id was not serialized to string")
    if parsed_payload.get("created_at") != "2025-01-02T03:04:05+00:00":
        raise RuntimeError("created_at was not serialized to ISO string")
    if parsed_payload.get("report_date") != "2025-01-02":
        raise RuntimeError("report_date was not serialized to ISO string")

    print("agui_notify SSE smoke test OK")


if __name__ == "__main__":
    main()

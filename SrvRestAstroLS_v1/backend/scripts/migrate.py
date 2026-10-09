"""Explicit V2 migrations; no application-startup migration or legacy credentials."""
from __future__ import annotations

import asyncio
import json

from backend.core.config import credentials
from backend.repositories.dev_foundation import migrate, verify_runtime
from backend.scripts.provision_dev import SECRET_PATH


async def run() -> dict:
    applied = await migrate(credentials(SECRET_PATH, "concilia_owner"))
    verified = await verify_runtime(credentials(SECRET_PATH, "concilia_app"))
    return {"applied": applied, **verified}


if __name__ == "__main__":
    try:
        print(json.dumps(asyncio.run(run())))
    except Exception as exc:
        print(json.dumps({"migration": "FAIL", "error_type": type(exc).__name__, "details": "withheld"}))
        raise SystemExit(1) from None

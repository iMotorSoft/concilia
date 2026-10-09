"""Run explicitly: python -m backend.scripts.provision_dev [--apply]."""
from __future__ import annotations

import argparse
import asyncio
import json
import secrets
from pathlib import Path

from psycopg import AsyncConnection
from backend.core.config import administrative_database, credentials
from backend.repositories.dev_foundation import inspect_server, provision

SECRET_PATH = Path(__file__).resolve().parents[3] / "storage" / "v2-dev" / "technical-credentials.json"


async def run(apply: bool) -> dict:
    admin = administrative_database()
    async with await AsyncConnection.connect(**admin.kwargs()) as conn:
        async with conn.transaction():
            await conn.execute("SET TRANSACTION READ ONLY")
            state = await inspect_server(conn)
    if not apply:
        return {"mode": "READ_ONLY", **state}
    if not SECRET_PATH.exists():
        if state["database_exists"] or state["roles"]:
            raise ValueError("Existing resources without local credentials; refusing overwrite")
        if SECRET_PATH.parent.is_symlink():
            raise ValueError("Secret directory must not be a symlink")
        SECRET_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Exclusive creation, never replace credentials on retry.
        import os
        fd = os.open(SECRET_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({role: secrets.token_urlsafe(48) for role in ("concilia_owner", "concilia_app")}, stream)
            stream.flush()
            os.fsync(stream.fileno())
    owner = credentials(SECRET_PATH, "concilia_owner")
    app = credentials(SECRET_PATH, "concilia_app")
    result = await provision(admin, owner, app)
    return {"provisioning": result, "database": "concilia_fce", "secrets": "local mode 0600; values withheld"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Explicitly authorize DEV creation")
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(run(args.apply))))
    except Exception as exc:
        # Driver exception strings can contain connection details or SQL literals.
        print(json.dumps({"provisioning": "FAIL", "error_type": type(exc).__name__, "details": "withheld"}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

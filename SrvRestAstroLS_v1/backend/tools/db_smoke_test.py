import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg


def _load_env_from_bashrc() -> None:
    path = Path.home() / ".bashrc"
    if not path.exists():
        return
    wanted = {
        "DB_PG_IP",
        "DB_PG_PORT",
        "DB_PG_USER",
        "DB_PG_PASS",
        "DB_PG_WORKFLOW_AI",
    }
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line.startswith("export "):
            continue
        keyval = line[len("export ") :].strip()
        if "=" not in keyval:
            continue
        key, value = keyval.split("=", 1)
        key = key.strip()
        if key not in wanted or key in os.environ:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


_load_env_from_bashrc()

from globalVar import DB_SCHEMA, DB_URL


def _normalize_db_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.split("postgresql+psycopg://", 1)[1]
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + url.split("postgresql+asyncpg://", 1)[1]
    return url


def _mask_url(url: str) -> str:
    parts = urlsplit(url)
    hostname = parts.hostname or ""
    if parts.port:
        hostname = f"{hostname}:{parts.port}"
    if parts.username:
        password = "****" if parts.password else ""
        userinfo = f"{parts.username}:{password}" if password else parts.username
        hostname = f"{userinfo}@{hostname}"
    return urlunsplit((parts.scheme, hostname, parts.path, parts.query, parts.fragment))


async def main() -> None:
    url = _normalize_db_url(DB_URL)
    print(f"Connecting to {_mask_url(url)} (schema={DB_SCHEMA})")
    conn = await asyncpg.connect(
        url,
        server_settings={"search_path": DB_SCHEMA},
    )
    try:
        now = await conn.fetchval("SELECT now()")
        workspace_count = await conn.fetchval("SELECT count(*) FROM core_workspaces")
        print(f"now: {now}")
        print(f"core_workspaces: {workspace_count}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

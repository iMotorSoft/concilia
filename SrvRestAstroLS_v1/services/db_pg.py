# SrvRestAstroLS_v1/services/db_pg.py
from __future__ import annotations

import asyncio
import asyncpg
import json
from typing import Any, Optional

from services.db_config import DB_SCHEMA, DB_URL, log_db_config_once, normalize_db_url
from services.json_safe import json_default, to_jsonable


async def connect_db(
    connect_timeout: float = 10.0,
    statement_timeout_ms: int | None = None,
    application_name: str = "concilia",
    connect_retries: int = 1,
    connect_retry_backoff: float = 0.5,
) -> asyncpg.Connection:
    log_db_config_once()
    settings = {
        "search_path": DB_SCHEMA,
        "application_name": application_name,
    }
    if statement_timeout_ms is not None:
        settings["statement_timeout"] = str(statement_timeout_ms)
    attempts = max(1, int(connect_retries))
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await asyncpg.connect(
                normalize_db_url(DB_URL),
                server_settings=settings,
                timeout=connect_timeout,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_err = exc
            if attempt >= attempts:
                break
            await asyncio.sleep(connect_retry_backoff * attempt)
    assert last_err is not None
    raise last_err


async def get_workspace_by_slug(conn: asyncpg.Connection, slug: str) -> str:
    workspace_id = await conn.fetchval(
        "SELECT workspace_id FROM core_workspaces WHERE slug = $1",
        slug,
    )
    if not workspace_id:
        raise ValueError(f"Workspace no existe: {slug}")
    return str(workspace_id)


async def create_run(
    conn: asyncpg.Connection,
    *,
    workspace_id: str,
    kind: str,
    status: str = "running",
    params: Optional[dict[str, Any]] = None,
) -> str:
    params_json = json.dumps(to_jsonable(params or {}), default=json_default)
    run_id = await conn.fetchval(
        """
        INSERT INTO core_runs (workspace_id, kind, status, params, started_at)
        VALUES ($1, $2, $3, $4::jsonb, now())
        RETURNING run_id
        """,
        workspace_id,
        kind,
        status,
        params_json,
    )
    return str(run_id)


async def append_event(
    conn: asyncpg.Connection,
    *,
    workspace_id: str,
    run_id: str,
    type: str,
    payload: Optional[dict[str, Any]] = None,
) -> None:
    payload_json = json.dumps(to_jsonable(payload or {}), default=json_default)
    await conn.execute(
        """
        INSERT INTO core_events (workspace_id, run_id, type, payload)
        VALUES ($1, $2, $3, $4::jsonb)
        """,
        workspace_id,
        run_id,
        type,
        payload_json,
    )


async def close_run(
    conn: asyncpg.Connection,
    *,
    workspace_id: str,
    run_id: str,
    status: str,
) -> None:
    await conn.execute(
        """
        UPDATE core_runs
        SET status = $1,
            ended_at = now()
        WHERE workspace_id = $2 AND run_id = $3
        """,
        status,
        workspace_id,
        run_id,
    )

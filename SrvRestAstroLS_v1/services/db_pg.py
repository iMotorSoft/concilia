# SrvRestAstroLS_v1/services/db_pg.py
from __future__ import annotations

import asyncpg
import json
from typing import Any, Optional

from globalVar import DB_SCHEMA, DB_URL


def _normalize_db_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.split("postgresql+psycopg://", 1)[1]
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + url.split("postgresql+asyncpg://", 1)[1]
    return url


async def connect_db() -> asyncpg.Connection:
    return await asyncpg.connect(
        _normalize_db_url(DB_URL),
        server_settings={"search_path": DB_SCHEMA},
    )


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
    params_json = json.dumps(params or {})
    return await conn.fetchval(
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


async def append_event(
    conn: asyncpg.Connection,
    *,
    workspace_id: str,
    run_id: str,
    type: str,
    payload: Optional[dict[str, Any]] = None,
) -> None:
    payload_json = json.dumps(payload or {})
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

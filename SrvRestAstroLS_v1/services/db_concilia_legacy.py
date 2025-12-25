# SrvRestAstroLS_v1/services/db_concilia_legacy.py
from __future__ import annotations

import asyncio
import asyncpg
from typing import Any, Optional, Tuple

from globalVar import (
    AUTO_BOOTSTRAP_TENANCY,
    PROJECT_NAME,
    TENANT_NAME,
    TENANT_SLUG,
)
from services.db_config import DB_SCHEMA, DB_URL, log_db_config_once, normalize_db_url


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


async def ensure_tenant_project(conn: asyncpg.Connection) -> Tuple[str, str]:
    tenant_id = await conn.fetchval(
        "SELECT id FROM concilia_tenants WHERE slug = $1",
        TENANT_SLUG,
    )
    if not tenant_id:
        if not AUTO_BOOTSTRAP_TENANCY:
            raise RuntimeError("Tenant no existe y AUTO_BOOTSTRAP_TENANCY=false")
        tenant_id = await conn.fetchval(
            """
            INSERT INTO concilia_tenants (slug, name)
            VALUES ($1, $2)
            RETURNING id
            """,
            TENANT_SLUG,
            TENANT_NAME,
        )

    project_id = await conn.fetchval(
        "SELECT id FROM concilia_projects WHERE tenant_id = $1 AND name = $2",
        tenant_id,
        PROJECT_NAME,
    )
    if not project_id:
        if not AUTO_BOOTSTRAP_TENANCY:
            raise RuntimeError("Project no existe y AUTO_BOOTSTRAP_TENANCY=false")
        project_id = await conn.fetchval(
            """
            INSERT INTO concilia_projects (tenant_id, name)
            VALUES ($1, $2)
            RETURNING id
            """,
            tenant_id,
            PROJECT_NAME,
        )

    return str(tenant_id), str(project_id)


async def insert_run(
    conn: asyncpg.Connection,
    *,
    tenant_id: str,
    project_id: str,
    status: str,
    current_stage: Optional[str],
    days_window: int,
    extracto_uri: str,
    contable_uri: str,
    payload: Optional[dict[str, Any]] = None,
) -> str:
    return await conn.fetchval(
        """
        INSERT INTO concilia_runs (
            tenant_id, project_id, status, current_stage, days_window,
            extracto_uri, contable_uri, payload, started_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
        RETURNING id
        """,
        tenant_id,
        project_id,
        status,
        current_stage,
        days_window,
        extracto_uri,
        contable_uri,
        payload or {},
    )


async def update_run(
    conn: asyncpg.Connection,
    *,
    run_id: str,
    status: Optional[str] = None,
    current_stage: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    finished: bool = False,
) -> None:
    fields = []
    values = []
    idx = 1

    if status is not None:
        fields.append(f"status = ${idx}")
        values.append(status)
        idx += 1
    if current_stage is not None:
        fields.append(f"current_stage = ${idx}")
        values.append(current_stage)
        idx += 1
    if error_code is not None:
        fields.append(f"error_code = ${idx}")
        values.append(error_code)
        idx += 1
    if error_message is not None:
        fields.append(f"error_message = ${idx}")
        values.append(error_message)
        idx += 1
    if finished:
        fields.append("finished_at = now()")

    if not fields:
        return

    values.append(run_id)
    set_clause = ", ".join(fields)
    await conn.execute(
        f"UPDATE concilia_runs SET {set_clause} WHERE id = ${idx}",
        *values,
    )


async def insert_event(
    conn: asyncpg.Connection,
    *,
    run_id: str,
    tenant_id: str,
    project_id: str,
    stage: str,
    status: str,
    message: Optional[str] = None,
    progress_current: Optional[int] = None,
    progress_total: Optional[int] = None,
    progress_pct: Optional[float] = None,
    timing_ms: Optional[int] = None,
    metrics: Optional[dict[str, Any]] = None,
    meta: Optional[dict[str, Any]] = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO concilia_events (
            run_id, tenant_id, project_id, stage, status, message,
            progress_current, progress_total, progress_pct, timing_ms,
            metrics, meta
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        """,
        run_id,
        tenant_id,
        project_id,
        stage,
        status,
        message,
        progress_current,
        progress_total,
        progress_pct,
        timing_ms,
        metrics,
        meta or {},
    )

import asyncio
import os
from pathlib import Path


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

from services.db_pg import (
    append_event,
    close_run,
    connect_db,
    create_run,
    get_workspace_by_slug,
)


async def main() -> None:
    conn = await connect_db()
    try:
        workspace_id = await get_workspace_by_slug(conn, "fce-concilia")
        run_id = await create_run(
            conn,
            workspace_id=workspace_id,
            kind="concilia_reconcile",
            params={"smoke": True},
        )

        await append_event(
            conn,
            workspace_id=workspace_id,
            run_id=run_id,
            type="STAGE",
            payload={"stage": "LOAD_EXTRACTO", "status": "start"},
        )
        await append_event(
            conn,
            workspace_id=workspace_id,
            run_id=run_id,
            type="STAGE",
            payload={"stage": "LOAD_EXTRACTO", "status": "done"},
        )

        rows = await conn.fetch(
            """
            SELECT payload->>'stage' AS stage,
                   payload->>'status' AS status,
                   ts,
                   event_id
            FROM core_events
            WHERE workspace_id = $1
              AND run_id = $2
              AND type = 'STAGE'
            ORDER BY ts, event_id
            """,
            workspace_id,
            run_id,
        )

        last_status = {}
        for row in rows:
            stage = row["stage"]
            status = row["status"]
            last_status[stage] = status

        print(f"workspace_id: {workspace_id}")
        print(f"run_id: {run_id}")
        print(f"last_stage_status: {last_status}")

        await close_run(
            conn,
            workspace_id=workspace_id,
            run_id=run_id,
            status="done",
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

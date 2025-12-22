# Usage:
#   python backend/tools/db_runtime_check.py
#
# Validates:
#   - current_database() == globalVar.DB_PG_WORKFLOW_AI
#   - public.core_workspaces/public.core_runs/public.core_events exist

from __future__ import annotations

import sys

import psycopg

import globalVar


def _connection_dsn() -> str:
    return (
        f"host={globalVar.DB_PG_IP} "
        f"port={globalVar.DB_PG_PORT} "
        f"dbname={globalVar.DB_PG_WORKFLOW_AI} "
        f"user={globalVar.DB_PG_USER} "
        f"password={globalVar.DB_PG_PASS}"
    )


def main() -> int:
    print(f"DB_URL: {globalVar.DB_URL}")
    print(f"DB_SCHEMA: {globalVar.DB_SCHEMA}")

    with psycopg.connect(_connection_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("select current_database(), current_schema();")
            current_db, current_schema = cur.fetchone()

            if current_db != globalVar.DB_PG_WORKFLOW_AI:
                print(
                    "DB mismatch: expected "
                    f"{globalVar.DB_PG_WORKFLOW_AI} got {current_db}",
                    file=sys.stderr,
                )
                return 2

            cur.execute(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'public'
                  and table_name in ('core_workspaces', 'core_runs', 'core_events')
                """
            )
            present = {row[0] for row in cur.fetchall()}

    required = {"core_workspaces", "core_runs", "core_events"}
    missing = sorted(required - present)
    if missing:
        print(f"Missing core tables in public schema: {', '.join(missing)}", file=sys.stderr)
        return 3

    print("DB OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

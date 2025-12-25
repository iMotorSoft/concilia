# -*- coding: utf-8 -*-
# backend/tools/db_smoke_test.py
#
# Usage:
#   python backend/tools/db_smoke_test.py

from __future__ import annotations

import asyncio

from services.db_concilia_legacy import connect_db as legacy_connect_db
from services.db_pg import connect_db as core_connect_db


async def _smoke(connect_fn, label: str) -> None:
    conn = await connect_fn(connect_timeout=5.0, statement_timeout_ms=30000)
    try:
        val = await conn.fetchval("SELECT 1")
        if val != 1:
            raise RuntimeError(f"{label}: SELECT 1 returned {val}")
    finally:
        await conn.close()


async def main() -> None:
    await _smoke(core_connect_db, "core")
    await _smoke(legacy_connect_db, "legacy")
    print("DB smoke test OK")


if __name__ == "__main__":
    asyncio.run(main())

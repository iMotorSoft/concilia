"""Explicit DEV-only administration SQL; never used by HTTP runtime."""
from __future__ import annotations

import hashlib
from pathlib import Path

from psycopg import AsyncConnection, sql

from backend.core.config import DevDatabase

MIGRATIONS = Path(__file__).parents[1] / "db" / "migrations"


async def inspect_server(conn: AsyncConnection) -> dict:
    version = (await (await conn.execute("SHOW server_version_num")).fetchone())[0]
    if int(version) // 10000 != 18:
        raise ValueError("Expected PostgreSQL 18 DEV; refusing provisioning")
    exists = (await (await conn.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = %s)",
        ("concilia_fce",))).fetchone())[0]
    roles = await (await conn.execute(
        "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
        "FROM pg_roles WHERE rolname IN ('concilia_owner', 'concilia_app') ORDER BY rolname"
    )).fetchall()
    return {"server_version_num": int(version), "database_exists": exists, "roles": roles}


async def provision(admin: DevDatabase, owner: DevDatabase, app: DevDatabase) -> str:
    async with await AsyncConnection.connect(**admin.kwargs(), autocommit=True) as conn:
        await conn.execute("SELECT pg_advisory_lock(7058, 2000)")
        try:
            state = await inspect_server(conn)
            if state["database_exists"] or state["roles"]:
                if not state["database_exists"] or len(state["roles"]) != 2:
                    raise ValueError("Partial/existing provisioning detected; inspect manually, no overwrite")
                if any(any(row[1:]) for row in state["roles"]):
                    raise ValueError("Existing technical role has excessive privileges")
                db_owner = (await (await conn.execute(
                    "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s",
                    ("concilia_fce",))).fetchone())[0]
                if db_owner != "concilia_owner":
                    raise ValueError("Existing database has unexpected owner; no overwrite")
                for config in (owner, app):
                    async with await AsyncConnection.connect(**config.kwargs()) as check:
                        await check.execute("SELECT 1")
                return "EXISTING_VERIFIED_NO_CHANGES"
            async with conn.transaction():
                template = sql.SQL((MIGRATIONS / "000_dev_provision.sql").read_text())
                await conn.execute(template.format(
                    owner=sql.Identifier(owner.user), app=sql.Identifier(app.user),
                    owner_password=sql.Literal(owner.password), app_password=sql.Literal(app.password)))
            # psycopg extended multi-statement CREATE DATABASE would run in a transaction.
            for statement in (MIGRATIONS / "000_dev_database.sql").read_text().split(';'):
                if statement.strip():
                    await conn.execute(statement)
            return "CREATED"
        finally:
            await conn.execute("SELECT pg_advisory_unlock(7058, 2000)")


async def migrate(owner: DevDatabase) -> list[str]:
    applied = []
    async with await AsyncConnection.connect(**owner.kwargs()) as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(7058, 2001)")
            version = (await (await conn.execute("SHOW server_version_num")).fetchone())[0]
            if int(version) // 10000 != 18:
                raise ValueError("Expected PostgreSQL 18")
            identity = (await (await conn.execute("SELECT current_user, current_database()")).fetchone())
            if identity != ("concilia_owner", "concilia_fce"):
                raise ValueError("Migration connection must be concilia_owner on concilia_fce")
            await conn.execute((MIGRATIONS / "000_migration_ledger.sql").read_text())
            for path in sorted(MIGRATIONS.glob("*.sql")):
                if path.name.startswith("000_"):
                    continue
                content = path.read_bytes()
                digest = hashlib.sha256(content).hexdigest()
                prior = await (await conn.execute(
                    "SELECT sha256 FROM public.concilia_schema_migrations WHERE version = %s",
                    (path.name,))).fetchone()
                if prior:
                    if prior[0] != digest:
                        raise ValueError("Applied migration checksum mismatch; refusing changes")
                    continue
                await conn.execute(content.decode())
                await conn.execute(
                    "INSERT INTO public.concilia_schema_migrations(version, sha256) VALUES (%s, %s)",
                    (path.name, digest))
                applied.append(path.name)
    return applied


async def verify_runtime(app: DevDatabase) -> dict:
    async with await AsyncConnection.connect(**app.kwargs()) as conn:
        async with conn.transaction():
            await conn.execute("SET TRANSACTION READ ONLY")
            role = await (await conn.execute(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user")).fetchone()
            if not role or any(role):
                raise ValueError("Runtime role has excessive privileges")
            checks = await (await conn.execute(
                "SELECT current_user, current_database(), "
                "has_schema_privilege(current_user, 'public', 'CREATE'), "
                "has_database_privilege(current_user, current_database(), 'CREATE'), "
                "has_table_privilege(current_user, 'public.seg_audit_events', 'UPDATE'), "
                "has_table_privilege(current_user, 'public.seg_audit_events', 'DELETE'), "
                "has_table_privilege(current_user, 'public.seg_audit_events', 'INSERT')"
            )).fetchone()
            if checks[:2] != ("concilia_app", "concilia_fce") or any(checks[2:6]) or not checks[6]:
                raise ValueError("Runtime grants are invalid")
            tables = await (await conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            )).fetchall()
            return {"runtime_privileges": "PASS", "tables": [row[0] for row in tables]}

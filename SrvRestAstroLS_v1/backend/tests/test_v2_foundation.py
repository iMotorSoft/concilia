from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from pathlib import Path

import pytest
from argon2 import PasswordHasher, Type
from psycopg import AsyncConnection, errors

from backend.core.config import DevDatabase, credentials
from backend.repositories.dev_foundation import migrate, verify_runtime
from backend.scripts.provision_dev import SECRET_PATH


@pytest.mark.parametrize("host,port,db", [("remote", 5432, "concilia_fce"),
    ("127.0.0.1", 5433, "concilia_fce"), ("127.0.0.1", 5432, "other")])
def test_reject_out_of_scope(host, port, db):
    with pytest.raises(ValueError):
        DevDatabase("concilia_app", "not-a-real-password", db, host, port).kwargs()


def test_password_not_in_repr():
    assert "private-value" not in repr(DevDatabase("concilia_app", "private-value"))


def test_secret_permissions(tmp_path):
    path = tmp_path / "secrets.json"
    path.write_text(json.dumps({"concilia_owner": "x" * 48, "concilia_app": "y" * 48}))
    path.chmod(0o644)
    with pytest.raises(ValueError):
        credentials(path, "concilia_app")
    path.chmod(0o600)
    assert credentials(path, "concilia_app").user == "concilia_app"
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        credentials(link, "concilia_app")


def test_argon2id():
    hasher = PasswordHasher(type=Type.ID)
    password = "synthetic-test-only-long-passphrase"
    encoded = hasher.hash(password)
    assert encoded.startswith("$argon2id$")
    assert hasher.verify(encoded, password)


def test_real_seg_schema_and_grants():
    if not SECRET_PATH.exists():
        pytest.skip("Explicit DEV provisioning required; not a PASS for the phase")

    async def check():
        app = credentials(SECRET_PATH, "concilia_app")
        assert (await verify_runtime(app))["runtime_privileges"] == "PASS"
        assert await migrate(credentials(SECRET_PATH, "concilia_owner")) == []
        async with await AsyncConnection.connect(**app.kwargs()) as conn:
            # All synthetic mutations deliberately rolled back, including audit events.
            async with conn.transaction(force_rollback=True):
                user_id = uuid.uuid4()
                encoded = PasswordHasher(type=Type.ID).hash("synthetic-test-only-long-passphrase")
                await conn.execute("INSERT INTO public.seg_users(id,email,password_hash,role) VALUES (%s,%s,%s,%s)",
                    (user_id, f"{user_id}@example.invalid", encoded, "OPERADOR"))
                token = hashlib.sha256(uuid.uuid4().bytes).digest()
                await conn.execute("INSERT INTO public.seg_sessions(token_hash,user_id,csrf_hash,absolute_expires_at) "
                    "VALUES (%s,%s,%s,CURRENT_TIMESTAMP + interval '24 hours')", (token, user_id, token))
                await conn.execute("UPDATE public.seg_users SET role='CONSULTA' WHERE id=%s", (user_id,))
                row = await (await conn.execute("SELECT revoked_at FROM public.seg_sessions WHERE token_hash=%s", (token,))).fetchone()
                assert row[0] is not None
                await conn.execute("INSERT INTO public.seg_audit_events(id,user_id,action,entity_type,result,correlation_id) "
                    "VALUES (%s,%s,'synthetic_validation','user','SUCCESS',%s)", (uuid.uuid4(), user_id, uuid.uuid4()))
                with pytest.raises(errors.InsufficientPrivilege):
                    async with conn.transaction():
                        await conn.execute("UPDATE public.seg_audit_events SET action='tampered'")
                with pytest.raises(errors.InsufficientPrivilege):
                    async with conn.transaction():
                        await conn.execute("DELETE FROM public.seg_audit_events")
                with pytest.raises(errors.InsufficientPrivilege):
                    async with conn.transaction():
                        await conn.execute("CREATE TABLE public.unauthorized_probe(id int)")
                with pytest.raises(errors.CheckViolation):
                    async with conn.transaction():
                        await conn.execute("UPDATE public.seg_users SET role='UNKNOWN' WHERE id=%s", (user_id,))
                with pytest.raises(errors.CheckViolation):
                    async with conn.transaction():
                        await conn.execute("INSERT INTO public.seg_sessions(token_hash,user_id,csrf_hash,absolute_expires_at) "
                            "VALUES (%s,%s,%s,CURRENT_TIMESTAMP + interval '25 hours')", (b'a'*32, user_id, token))
    asyncio.run(check())

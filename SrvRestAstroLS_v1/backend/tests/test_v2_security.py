from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import secrets
from uuid import uuid4

import pytest
from psycopg import AsyncConnection, errors

from backend.core.config import credentials
from backend.core.security import Principal, password_hash, token_hash, valid_csrf, verify_password
from backend.repositories.security import SecurityRepository
from backend.scripts.provision_dev import SECRET_PATH


def test_password_and_permissions():
    with pytest.raises(ValueError):
        password_hash("short")
    value = password_hash("synthetic-only-long-passphrase")
    assert verify_password(value, "synthetic-only-long-passphrase")
    assert not verify_password(value, "incorrect")
    assert not verify_password("invalid-hash", "incorrect")
    assert Principal(uuid4(), "test@example.invalid", "CONSULTA", b'').allows("view")
    assert not Principal(uuid4(), "test@example.invalid", "CONSULTA", b'').allows("upload")
    assert not Principal(uuid4(), "test@example.invalid", "UNKNOWN", b'').allows("view")


def test_csrf():
    assert valid_csrf(token_hash("token"), "token", "token")
    assert not valid_csrf(token_hash("token"), "token", "different")
    assert not valid_csrf(token_hash("token"), "different", "different")
    assert not valid_csrf(token_hash("token"), "", "")


def test_real_persistent_security_operations():
    if not SECRET_PATH.exists():
        pytest.skip("Requires explicit DEV provisioning")

    async def check():
        async with await AsyncConnection.connect(**credentials(SECRET_PATH, "concilia_app").kwargs()) as conn:
            async with conn.transaction(force_rollback=True):
                # Real PostgreSQL, scoped to a rollback transaction; no mocked persistence.
                class TransactionPool:
                    @asynccontextmanager
                    async def connection(self):
                        yield conn
                repository = SecurityRepository(TransactionPool())
                user_id = uuid4()
                email = f"{user_id}@example.invalid"
                password = secrets.token_urlsafe(48)
                client = str(uuid4())
                await conn.execute("INSERT INTO public.seg_users(id,email,password_hash,role) VALUES (%s,%s,%s,'OPERADOR')",
                    (user_id, email, password_hash(password)))
                assert await repository.login(email, "invalid", client, uuid4()) is None
                issued = await repository.login(email, password, client, uuid4())
                token, csrf, user = issued
                assert user.id == user_id
                assert valid_csrf(user.csrf_hash, csrf, csrf)
                assert (await repository.authenticate(token)).id == user_id
                await repository.logout(token, uuid4())
                assert await repository.authenticate(token) is None
                token, _, _ = await repository.login(email, password, client, uuid4())
                await conn.execute("UPDATE public.seg_sessions SET last_seen_at=CURRENT_TIMESTAMP - interval '9 hours' WHERE token_hash=%s", (token_hash(token),))
                assert await repository.authenticate(token) is None
                token, _, _ = await repository.login(email, password, client, uuid4())
                await conn.execute("UPDATE public.seg_sessions SET created_at=CURRENT_TIMESTAMP - interval '25 hours', "
                    "absolute_expires_at=CURRENT_TIMESTAMP - interval '1 hour' WHERE token_hash=%s", (token_hash(token),))
                assert await repository.authenticate(token) is None
                token, _, _ = await repository.login(email, password, client, uuid4())
                await conn.execute("UPDATE public.seg_users SET active=false WHERE id=%s", (user_id,))
                assert await repository.authenticate(token) is None
                assert await repository.login(email, password, client, uuid4()) is None
                # Shared persistent limiter: a second repository observes the same bucket.
                for _ in range(5):
                    await repository.login(email, "invalid", client, uuid4())
                attempts = (await (await conn.execute("SELECT attempts FROM public.seg_rate_limits WHERE key_hash=%s", (token_hash("email:" + email),))).fetchone())[0]
                assert attempts > 10
                await conn.execute("UPDATE public.seg_users SET active=true WHERE id=%s", (user_id,))
                assert await SecurityRepository(TransactionPool()).login(email, password, client, uuid4()) is None
                audits = (await (await conn.execute("SELECT count(*) FROM public.seg_audit_events WHERE user_id=%s", (user_id,))).fetchone())[0]
                assert audits >= 6
                # Even valid login fails atomically if audit INSERT cannot persist.
                other = uuid4()
                other_email = f"{other}@example.invalid"
                await conn.execute("INSERT INTO public.seg_users(id,email,password_hash,role) VALUES (%s,%s,%s,'CONSULTA')",
                    (other, other_email, password_hash(password)))
                with pytest.raises(errors.NotNullViolation):
                    async with conn.transaction():
                        await repository.login(other_email, password, str(uuid4()), None)
                sessions = (await (await conn.execute("SELECT count(*) FROM public.seg_sessions WHERE user_id=%s", (other,))).fetchone())[0]
                assert sessions == 0
    asyncio.run(check())

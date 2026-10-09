"""Persistent SEG-01 operations. Financial audit integration remains separate."""
from __future__ import annotations

import asyncio
import secrets
from uuid import UUID, uuid4

from psycopg_pool import AsyncConnectionPool

from backend.core.security import Principal, password_hash, token_hash, verify_password

# Timing equalization for unknown users; not an account or default password.
_DUMMY_HASH = password_hash(secrets.token_urlsafe(48))


class SecurityRepository:
    def __init__(self, pool: AsyncConnectionPool):
        self.pool = pool

    async def _audit(self, conn, user_id, action, result, correlation_id, entity_type="session", entity_id=None):
        await conn.execute(
            "INSERT INTO public.seg_audit_events(id,user_id,action,entity_type,entity_id,result,correlation_id,reason) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (uuid4(), user_id, action, entity_type, entity_id, result, correlation_id,
             action + ' rejected by security policy' if result == 'DENIED' else None))

    async def audit_operation(self, actor, action, entity_id, result, correlation_id, reason, entity_type='temporary_runtime'):
        """Append an event; never represents an in-memory decision as durable."""
        async with self.pool.connection() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO public.seg_audit_events(id,user_id,action,entity_type,entity_id,result,correlation_id,reason) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (uuid4(), actor, action, entity_type, entity_id, result, correlation_id, reason))

    async def provision_e2e(self):
        """Explicit local DEV utility, random credentials, no existing account changes."""
        accounts = []
        async with self.pool.connection() as conn, conn.transaction():
            for role in ('ADMINISTRADOR', 'OPERADOR', 'CONSULTA'):
                user_id, password = uuid4(), secrets.token_urlsafe(48)
                email = f'seg01-e2e-{user_id}@example.invalid'
                encoded = await asyncio.to_thread(password_hash, password)
                await conn.execute(
                    'INSERT INTO public.seg_users(id,email,password_hash,role) VALUES (%s,%s,%s,%s)',
                    (user_id, email, encoded, role))
                await self._audit(conn, user_id, 'dev_e2e_provision', 'SUCCESS', uuid4(), 'user', str(user_id))
                accounts.append(dict(id=str(user_id), email=email, password=password, role=role))
        return accounts

    async def deactivate_e2e(self, accounts):
        """Retain audit provenance but irreversibly retire only generated test accounts."""
        async with self.pool.connection() as conn, conn.transaction():
            for account in accounts:
                user_id = UUID(account['id'])
                row = await (await conn.execute(
                    "UPDATE public.seg_users SET active=false,password_hash=%s,updated_at=CURRENT_TIMESTAMP "
                    "WHERE id=%s AND email=%s AND email LIKE 'seg01-e2e-%%@example.invalid' RETURNING id",
                    (password_hash(secrets.token_urlsafe(48)), user_id, account['email']))).fetchone()
                if not row:
                    raise ValueError('Not a generated E2E account')
                await self._audit(conn, user_id, 'dev_e2e_deactivate', 'SUCCESS', uuid4(), 'user', str(user_id))
                live = await (await conn.execute(
                    'SELECT count(*) FROM public.seg_sessions WHERE user_id=%s AND revoked_at IS NULL',
                    (user_id,))).fetchone()
                if live[0]:
                    raise ValueError('E2E session revocation failed')

    async def login(self, email: str, password: str, client_key: str, correlation_id: UUID):
        email = email.strip().lower()
        if len(email) > 320 or len(password) > 1024:
            return None
        async with self.pool.connection() as conn, conn.transaction():
            # Persistent, atomic buckets shared by workers. Independent IP/email limits.
            limited = False
            keys = sorted([token_hash("email:" + email), token_hash("client:" + client_key)])
            for key in keys:
                row = await (await conn.execute(
                    "INSERT INTO public.seg_rate_limits(key_hash,window_started_at,attempts) "
                    "VALUES (%s,CURRENT_TIMESTAMP,1) ON CONFLICT(key_hash) DO UPDATE SET "
                    "attempts=CASE WHEN seg_rate_limits.window_started_at <= CURRENT_TIMESTAMP - interval '15 minutes' "
                    "THEN 1 ELSE seg_rate_limits.attempts + 1 END, "
                    "window_started_at=CASE WHEN seg_rate_limits.window_started_at <= CURRENT_TIMESTAMP - interval '15 minutes' "
                    "THEN CURRENT_TIMESTAMP ELSE seg_rate_limits.window_started_at END RETURNING attempts",
                    (key,))).fetchone()
                limited = limited or row[0] > 10
            if limited:
                await self._audit(conn, None, "login_rate_limited", "DENIED", correlation_id)
                return None
            user = await (await conn.execute(
                "SELECT id,email,role,password_hash,active FROM public.seg_users WHERE email=%s FOR UPDATE",
                (email,))).fetchone()
            valid = await asyncio.to_thread(verify_password, user[3] if user else _DUMMY_HASH, password)
            if not user or not valid or not user[4]:
                await self._audit(conn, user[0] if user else None, "login", "DENIED", correlation_id)
                return None
            token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(48)
            await conn.execute(
                "INSERT INTO public.seg_sessions(token_hash,user_id,csrf_hash,absolute_expires_at) "
                "VALUES (%s,%s,%s,CURRENT_TIMESTAMP + interval '24 hours')",
                (token_hash(token), user[0], token_hash(csrf)))
            await self._audit(conn, user[0], "login", "SUCCESS", correlation_id)
            return token, csrf, Principal(user[0], user[1], user[2], token_hash(csrf))

    async def authenticate(self, token: str) -> Principal | None:
        if not token or len(token) > 256:
            return None
        async with self.pool.connection() as conn, conn.transaction():
            # Lock user before session, consistent with revocation trigger / privilege change.
            user = await (await conn.execute(
                "SELECT u.id,u.email,u.role,u.active FROM public.seg_users u "
                "JOIN public.seg_sessions s ON s.user_id=u.id WHERE s.token_hash=%s FOR SHARE OF u",
                (token_hash(token),))).fetchone()
            if not user or not user[3]:
                return None
            row = await (await conn.execute(
                "UPDATE public.seg_sessions SET last_seen_at=CURRENT_TIMESTAMP "
                "WHERE token_hash=%s AND revoked_at IS NULL "
                "AND last_seen_at > CURRENT_TIMESTAMP - interval '8 hours' "
                "AND absolute_expires_at > CURRENT_TIMESTAMP RETURNING csrf_hash",
                (token_hash(token),))).fetchone()
            return Principal(user[0], user[1], user[2], row[0]) if row else None

    async def logout(self, token: str, correlation_id: UUID) -> None:
        async with self.pool.connection() as conn, conn.transaction():
            row = await (await conn.execute(
                "UPDATE public.seg_sessions SET revoked_at=CURRENT_TIMESTAMP "
                "WHERE token_hash=%s AND revoked_at IS NULL RETURNING user_id",
                (token_hash(token),))).fetchone()
            if row:
                await self._audit(conn, row[0], "logout", "SUCCESS", correlation_id)

    async def list_users(self) -> list[dict]:
        async with self.pool.connection() as conn:
            rows = await (await conn.execute(
                "SELECT id,email,role,active FROM public.seg_users ORDER BY email")).fetchall()
            return [dict(id=str(row[0]), email=row[1], role=row[2], active=row[3]) for row in rows]

    async def create_user(self, actor: UUID, email: str, password: str, role: str, correlation_id: UUID) -> UUID:
        from backend.core.security import ROLES
        from psycopg.errors import UniqueViolation
        if (not isinstance(email, str) or not email.strip() or len(email) > 320 or email.count("@") != 1
                or not isinstance(password, str) or not isinstance(role, str) or role not in ROLES):
            raise ValueError("Invalid user")
        encoded = await asyncio.to_thread(password_hash, password)
        user_id = uuid4()
        try:
            async with self.pool.connection() as conn, conn.transaction():
                await conn.execute(
                    "INSERT INTO public.seg_users(id,email,password_hash,role) VALUES (%s,%s,%s,%s)",
                    (user_id, email.strip().lower(), encoded, role))
                await self._audit(conn, actor, "user_create", "SUCCESS", correlation_id, "user", str(user_id))
        except UniqueViolation:
            raise ValueError("User exists") from None
        return user_id

    async def update_user(self, actor: UUID, user_id: UUID, role: str, active: bool, correlation_id: UUID):
        from backend.core.security import ROLES
        if not isinstance(role, str) or role not in ROLES or type(active) is not bool:
            raise ValueError("Invalid update")
        async with self.pool.connection() as conn, conn.transaction():
            # Serialize administrator changes to avoid concurrent removal of the last admin.
            await conn.execute("SELECT pg_advisory_xact_lock(7058, 2002)")
            row = await (await conn.execute(
                "SELECT role,active FROM public.seg_users WHERE id=%s FOR UPDATE", (user_id,))).fetchone()
            if not row:
                raise ValueError("Unknown user")
            if row == ('ADMINISTRADOR', True) and (role != 'ADMINISTRADOR' or not active):
                count = (await (await conn.execute(
                    "SELECT count(*) FROM public.seg_users WHERE role='ADMINISTRADOR' AND active")).fetchone())[0]
                if count <= 1:
                    raise ValueError("Cannot remove last active administrator")
            await conn.execute(
                "UPDATE public.seg_users SET role=%s,active=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                (role, active, user_id))
            await self._audit(conn, actor, "user_update", "SUCCESS", correlation_id, "user", str(user_id))

    async def revoke_user(self, actor: UUID, user_id: UUID, correlation_id: UUID):
        async with self.pool.connection() as conn, conn.transaction():
            await conn.execute("SELECT id FROM public.seg_users WHERE id=%s FOR UPDATE", (user_id,))
            await conn.execute(
                "UPDATE public.seg_sessions SET revoked_at=CURRENT_TIMESTAMP WHERE user_id=%s AND revoked_at IS NULL",
                (user_id,))
            await self._audit(conn, actor, "user_sessions_revoke", "SUCCESS", correlation_id, "user", str(user_id))

    async def change_password(self, user_id: UUID, current: str, new: str, correlation_id: UUID) -> bool:
        encoded = await asyncio.to_thread(password_hash, new)
        async with self.pool.connection() as conn, conn.transaction():
            row = await (await conn.execute(
                "SELECT password_hash FROM public.seg_users WHERE id=%s AND active FOR UPDATE", (user_id,))).fetchone()
            if not row or not await asyncio.to_thread(verify_password, row[0], current):
                await self._audit(conn, user_id, "password_change", "DENIED", correlation_id, "user", str(user_id))
                return False
            await conn.execute(
                "UPDATE public.seg_users SET password_hash=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s", (encoded, user_id))
            await self._audit(conn, user_id, "password_change", "SUCCESS", correlation_id, "user", str(user_id))
            return True

    async def issue_password_reset(self, actor: UUID, user_id: UUID, current_password: str, correlation_id: UUID) -> str | None:
        """Admin-assisted DEV recovery; deliver the one-use token out of band."""
        async with self.pool.connection() as conn, conn.transaction():
            # Lock both users in stable order, including self-recovery.
            rows = await (await conn.execute(
                "SELECT id,password_hash,active,role FROM public.seg_users WHERE id=ANY(%s) ORDER BY id FOR UPDATE",
                ([actor, user_id],))).fetchall()
            users = {row[0]: row for row in rows}
            administrator = users.get(actor)
            target = users.get(user_id)
            if (not administrator or not administrator[2] or administrator[3] != 'ADMINISTRADOR'
                    or not target or not target[2]
                    or not await asyncio.to_thread(verify_password, administrator[1], current_password)):
                await self._audit(conn, actor, "password_reset_issue", "DENIED", correlation_id, "user", str(user_id))
                return None
            token = secrets.token_urlsafe(48)
            await conn.execute("UPDATE public.seg_password_resets SET used_at=CURRENT_TIMESTAMP WHERE user_id=%s AND used_at IS NULL", (user_id,))
            await conn.execute(
                "INSERT INTO public.seg_password_resets(token_hash,user_id,expires_at) VALUES (%s,%s,CURRENT_TIMESTAMP + interval '15 minutes')",
                (token_hash(token), user_id))
            await conn.execute("UPDATE public.seg_sessions SET revoked_at=CURRENT_TIMESTAMP WHERE user_id=%s AND revoked_at IS NULL", (user_id,))
            await self._audit(conn, actor, "password_reset_issue", "SUCCESS", correlation_id, "user", str(user_id))
            return token

    async def reset_password(self, token: str, password: str, client_key: str, correlation_id: UUID) -> bool:
        if not isinstance(token, str) or not token or len(token) > 256:
            return False
        async with self.pool.connection() as conn, conn.transaction():
            rate = await (await conn.execute(
                "INSERT INTO public.seg_rate_limits(key_hash,window_started_at,attempts) VALUES (%s,CURRENT_TIMESTAMP,1) "
                "ON CONFLICT(key_hash) DO UPDATE SET attempts=CASE WHEN seg_rate_limits.window_started_at <= CURRENT_TIMESTAMP - interval '15 minutes' "
                "THEN 1 ELSE seg_rate_limits.attempts+1 END, window_started_at=CASE WHEN seg_rate_limits.window_started_at <= CURRENT_TIMESTAMP - interval '15 minutes' "
                "THEN CURRENT_TIMESTAMP ELSE seg_rate_limits.window_started_at END RETURNING attempts",
                (token_hash('reset-client:' + client_key),))).fetchone()
            if rate[0] > 10:
                await self._audit(conn, None, "password_reset", "DENIED", correlation_id)
                return False
            user = await (await conn.execute(
                "SELECT u.id,u.active FROM public.seg_users u JOIN public.seg_password_resets r ON r.user_id=u.id "
                "WHERE r.token_hash=%s FOR UPDATE OF u", (token_hash(token),))).fetchone()
            reset = await (await conn.execute(
                "UPDATE public.seg_password_resets SET used_at=CURRENT_TIMESTAMP "
                "WHERE token_hash=%s AND used_at IS NULL AND expires_at>CURRENT_TIMESTAMP RETURNING user_id",
                (token_hash(token),))).fetchone() if user and user[1] else None
            if not reset:
                await self._audit(conn, None, "password_reset", "DENIED", correlation_id)
                return False
            encoded = await asyncio.to_thread(password_hash, password)
            await conn.execute("UPDATE public.seg_users SET password_hash=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s", (encoded, user[0]))
            await self._audit(conn, user[0], "password_reset", "SUCCESS", correlation_id, "user", str(user[0]))
            return True

    async def create_first_admin(self, email: str, encoded: str) -> None:
        async with self.pool.connection() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(7058, 2002)")
            exists = (await (await conn.execute(
                "SELECT EXISTS(SELECT 1 FROM public.seg_users WHERE role='ADMINISTRADOR')")).fetchone())[0]
            if exists:
                raise ValueError("Administrator already exists; no bootstrap overwrite")
            user_id = uuid4()
            await conn.execute(
                "INSERT INTO public.seg_users(id,email,password_hash,role) VALUES (%s,%s,%s,'ADMINISTRADOR')",
                (user_id, email.strip().lower(), encoded))
            await self._audit(conn, user_id, "first_admin_provision", "SUCCESS", uuid4(), "user", str(user_id))

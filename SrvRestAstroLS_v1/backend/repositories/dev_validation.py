"""Read-only evidence and narrowly scoped cleanup for generated DEV E2E accounts."""
from uuid import UUID, uuid4
from backend.core.security import token_hash
from backend.repositories.files import controlled_path, file_digest


async def login_budget_delay(pool):
    """Respect the live limiter; never reset a shared DEV client bucket."""
    async with pool.connection() as conn:
        row = await (await conn.execute(
            "SELECT CASE WHEN attempts > 6 THEN GREATEST(0,extract(epoch FROM "
            "window_started_at + interval '15 minutes' - CURRENT_TIMESTAMP)) ELSE 0 END "
            "FROM seg_rate_limits WHERE key_hash=%s", (token_hash('client:127.0.0.1'),))).fetchone()
        return float(row[0]) + 1 if row and row[0] > 0 else 0


async def snapshot(pool, accounts):
    ids = [UUID(a['id']) for a in accounts]
    async with pool.connection() as conn:
        users = await (await conn.execute('SELECT id,role,active FROM seg_users WHERE id=ANY(%s) ORDER BY id', (ids,))).fetchall()
        files = await (await conn.execute('SELECT id,relative_path,sha256,parent_id FROM seg_files WHERE uploaded_by=ANY(%s) ORDER BY id', (ids,))).fetchall()
        events = await (await conn.execute('SELECT id,action,result,reason,correlation_id,occurred_at FROM seg_audit_events WHERE user_id=ANY(%s) ORDER BY id', (ids,))).fetchall()
        sessions = await (await conn.execute('SELECT token_hash,revoked_at FROM seg_sessions WHERE user_id=ANY(%s) ORDER BY token_hash', (ids,))).fetchall()
        return dict(users=users, files=files, events=events, sessions=sessions)


async def cleanup_files(owner_pool, accounts):
    ids = [UUID(a['id']) for a in accounts]
    async with owner_pool.connection() as conn, conn.transaction():
        rows = await (await conn.execute(
            "UPDATE seg_files SET status='REVOKED' WHERE uploaded_by=ANY(%s) "
            "AND uploaded_by IN (SELECT id FROM seg_users WHERE NOT active AND email LIKE 'seg01-e2e-%%@example.invalid') "
            "RETURNING id,relative_path,sha256,uploaded_by", (ids,))).fetchall()
        for file_id, relative, digest, actor in rows:
            # Do not unlink anything whose integrity/ownership cannot be demonstrated.
            path = controlled_path(relative)
            if file_digest(path) != digest:
                raise ValueError('Test file changed; refusing unlink')
            await conn.execute(
                "INSERT INTO seg_audit_events(id,user_id,action,entity_type,entity_id,result,correlation_id,reason) "
                "VALUES (%s,%s,'dev_e2e_file_cleanup','file',%s,'SUCCESS',%s,'synthetic test artifact retired')",
                (uuid4(), actor, str(file_id), uuid4()))
        # Transaction commits revocation before removal of test-only artifacts.
    for _, relative, _, _ in rows:
        controlled_path(relative).unlink()
    return len(rows)

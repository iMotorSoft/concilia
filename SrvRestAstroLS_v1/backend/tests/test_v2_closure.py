"""Focused audit fail-closed and temporary DEV lifecycle regressions."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from psycopg import AsyncConnection
from backend.core.config import credentials
from backend.repositories.security import SecurityRepository
from backend.scripts.provision_dev import SECRET_PATH


def test_real_temporary_account_lifecycle_and_audit():
    if not SECRET_PATH.exists():
        pytest.skip('Requires provisioned DEV database')
    async def check():
        async with await AsyncConnection.connect(**credentials(SECRET_PATH, 'concilia_app').kwargs()) as conn:
            async with conn.transaction(force_rollback=True):
                class Pool:
                    @asynccontextmanager
                    async def connection(self):
                        yield conn
                repository = SecurityRepository(Pool())
                accounts = await repository.provision_e2e()
                assert len(accounts) == 3
                issued = await repository.login(accounts[0]['email'], accounts[0]['password'], str(uuid4()), uuid4())
                assert issued
                await repository.audit_operation(issued[2].id, 'test_temporary', str(uuid4()), 'SUCCESS', uuid4(), 'in_memory_only')
                await repository.deactivate_e2e(accounts)
                assert await repository.authenticate(issued[0]) is None
                row = await (await conn.execute(
                    "SELECT count(*),bool_and(reason='in_memory_only'),bool_and(occurred_at IS NOT NULL AND correlation_id IS NOT NULL) "
                    "FROM seg_audit_events WHERE user_id=%s AND action='test_temporary'", (issued[2].id,))).fetchone()
                assert row == (1, True, True)
                count = await (await conn.execute(
                    "SELECT count(*) FROM seg_users WHERE id=ANY(%s) AND active", ([__import__('uuid').UUID(a['id']) for a in accounts],))).fetchone()
                assert count[0] == 0
    asyncio.run(check())


def test_wizard_action_audit_failure_does_not_publish_or_change_state():
    from routes.v1.run_action import run_action
    from services.wizard_runtime import create_memory_run, append_memory_events, get_memory_state, list_memory_events
    run = create_memory_run({'actor_id': str(uuid4())})
    append_memory_events(run, [{'type': 'WIZARD_STATE_SET', 'payload': {'selection': {'window_days': 5}, 'context': {}}}])
    before_state, before_events = get_memory_state(run), list_memory_events(run)
    class UnavailableAudit:
        async def audit_operation(self, *args):
            raise RuntimeError('audit unavailable')
    request = SimpleNamespace(state=SimpleNamespace(principal=SimpleNamespace(id=uuid4())),
                              app=SimpleNamespace(state=SimpleNamespace(security=UnavailableAudit())))
    with pytest.raises(RuntimeError, match='audit unavailable'):
        asyncio.run(run_action.fn(request, run, {'action_type': 'SELECT_WINDOW_DAYS', 'payload': {'window_days': 20}}))
    assert get_memory_state(run) == before_state
    assert list_memory_events(run) == before_events

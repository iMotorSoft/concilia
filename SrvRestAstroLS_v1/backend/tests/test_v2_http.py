"""Real TCP / real PostgreSQL checks, isolated with transaction rollback.

These do not claim browser, resource-ID transition or reconciliation gates.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import secrets
import socket
from uuid import uuid4

import httpx
import pytest
from psycopg import AsyncConnection
import uvicorn

from backend.core.config import credentials, http_security
from backend.core.security import password_hash
from backend.http.security import CAPABILITIES, validate_legacy_file
from backend.repositories.security import SecurityRepository
from backend.scripts.provision_dev import SECRET_PATH
from litestar.exceptions import HTTPException


def test_legacy_path_boundary():
    for value in ['file:///etc/passwd', '/etc/passwd', 'https://example.invalid/data.xlsx',
                  'file://remote/storage/data.xlsx', '../storage/canonical/data.parquet']:
        with pytest.raises(HTTPException):
            validate_legacy_file(value)


def test_http_config_dev_only(monkeypatch):
    monkeypatch.setenv('CONCILIA_AUTH_ORIGINS', 'https://production.example.invalid')
    with pytest.raises(ValueError):
        http_security()


def test_real_http_security(caplog, tmp_path, monkeypatch):
    if not SECRET_PATH.exists():
        pytest.skip('Requires explicitly provisioned DEV SEG-01 database')

    async def check():
        import ls_iMotorSoft_Srv01 as entrypoint
        seen_secrets = []
        # Every business handler must have an explicit capability.
        assert all(handler.fn.__name__ in CAPABILITIES for handler in entrypoint.route_handlers)
        server_socket = socket.socket()
        server_socket.bind(('127.0.0.1', 0))
        port = server_socket.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(entrypoint.app, host='127.0.0.1', port=port,
                                              log_level='error', access_log=False))
        task = asyncio.create_task(server.serve(sockets=[server_socket]))
        try:
            for _ in range(200):
                if server.started:
                    break
                if task.done():
                    await task
                    raise AssertionError('HTTP startup failed')
                await asyncio.sleep(.025)
            assert server.started
            async with await AsyncConnection.connect(**credentials(SECRET_PATH, 'concilia_app').kwargs()) as conn:
                async with conn.transaction(force_rollback=True):
                    # Isolate the TCP test's loopback bucket from previous DEV logins.
                    # This setup is rolled back; the runtime limiter is not disabled.
                    from backend.core.security import token_hash
                    await conn.execute('UPDATE public.seg_rate_limits SET attempts=0,window_started_at=CURRENT_TIMESTAMP WHERE key_hash=%s',
                                       (token_hash('client:127.0.0.1'),))
                    class TransactionPool:
                        @asynccontextmanager
                        async def connection(self):
                            yield conn
                    # Real repository and SQL; isolation avoids persistent test users/secrets.
                    entrypoint.app.state.security = SecurityRepository(TransactionPool())
                    from backend.repositories.files import FileRepository
                    monkeypatch.setattr('backend.repositories.files.STORAGE_ROOT', tmp_path)
                    entrypoint.app.state.files = FileRepository(TransactionPool(), tmp_path)
                    accounts = {}
                    for role in ('CONSULTA', 'OPERADOR', 'ADMINISTRADOR'):
                        user_id, password = uuid4(), secrets.token_urlsafe(48)
                        email = f'{user_id}@example.invalid'
                        await conn.execute(
                            'INSERT INTO public.seg_users(id,email,password_hash,role) VALUES (%s,%s,%s,%s)',
                            (user_id, email, password_hash(password), role))
                        accounts[role] = (user_id, email, password)
                        seen_secrets.append(password)
                    base_url = f'http://127.0.0.1:{port}'
                    async with httpx.AsyncClient(base_url=base_url) as client:
                        # Every registered business route rejects anonymous HTTP requests,
                        # including both SSE handlers, before executing the business logic.
                        for handler in entrypoint.route_handlers:
                            path = next(iter(handler.paths)).replace('{run_id:str}', str(uuid4()))
                            method = 'GET' if 'GET' in handler.http_methods else 'POST'
                            assert (await client.request(method, path)).status_code == 401, path
                        assert (await client.get('/schema')).status_code == 404
                        assert (await client.post('/api/auth/login', json={'email': accounts['CONSULTA'][1],
                            'password': 'incorrect'})).status_code == 401
                        for role, (user_id, email, password) in accounts.items():
                            client.cookies.clear()
                            result = await client.post('/api/auth/login', json={'email': email, 'password': password},
                                headers={'Origin': 'http://127.0.0.1:3058'})
                            assert result.status_code == 200
                            assert result.json()['role'] == role
                            cookie_headers = result.headers.get_list('set-cookie')
                            assert any('HttpOnly' in value and 'SameSite=lax' in value for value in cookie_headers)
                            csrf = client.cookies.get('concilia_csrf')
                            seen_secrets.extend([csrf, client.cookies.get('concilia_session')])
                            headers = {'X-CSRF-Token': csrf, 'Origin': 'http://127.0.0.1:3058'}
                            assert (await client.get('/api/auth/me')).status_code == 200
                            assert (await client.post('/api/auth/logout')).status_code == 403
                            assert (await client.post('/api/auth/logout', headers={**headers, 'X-CSRF-Token': 'invalid'})).status_code == 403
                            assert (await client.post('/api/auth/logout', headers={**headers, 'Origin': 'https://evil.invalid'})).status_code == 403
                            assert (await client.post('/api/uploads/v2/ingest', headers=headers)).status_code == (403 if role == 'CONSULTA' else 400)
                            assert (await client.get('/api/auth/users')).status_code == (200 if role == 'ADMINISTRADOR' else 403)
                            for ref in (str(uuid4()), 'file:///etc/passwd', '../incoming/test.csv'):
                                assert (await client.post('/api/ingest/confirm', data={
                                    'threadId': str(uuid4()), 'role': 'extracto', 'original_uri': ref},
                                    headers=headers)).status_code == 403
                            if role != 'CONSULTA':
                                uploaded = await client.post('/api/uploads/v2/ingest?role=extracto',
                                    files={'file': ('synthetic.csv', b'fecha,importe\n2026-01-01,1\n', 'text/csv')}, headers=headers)
                                assert uploaded.status_code == 200, uploaded.text
                                reference = uploaded.json()['original_uri']
                                assert reference == uploaded.json()['source_file_id']
                                assert str(__import__('uuid').UUID(reference)) == reference
                                uri = await entrypoint.app.state.files.resolve(reference,
                                    await entrypoint.app.state.security.authenticate(client.cookies.get('concilia_session')))
                                # Even a known, existing managed path is forbidden over HTTP.
                                assert (await client.post('/api/ingest/confirm', data={
                                    'threadId': str(uuid4()), 'role': 'extracto', 'original_uri': uri},
                                    headers=headers)).status_code == 403
                                assert (await client.post('/api/uploads/v2/ingest?role=extracto',
                                    files={'file': ('manifest.json', b'{"uris":["/etc/passwd"]}', 'application/json')},
                                    headers=headers)).status_code == 400
                            # POST reads allowed even for CONSULTA; empty payload reaches handler validation.
                            assert (await client.post('/api/reconcile/summary/head', data={}, headers=headers)).status_code == 400
                            assert (await client.post('/api/reconcile/summary/head', data={
                                'uri_extracto': 'file:///etc/passwd', 'uri_contable': '/etc/passwd'}, headers=headers)).status_code == 403
                            assert (await client.post('/api/auth/logout', json={}, headers=headers)).status_code == 200
                            assert (await client.get('/api/auth/me')).status_code == 401
                        # User deactivation and revocation are enforced on the next real request.
                        user_id, email, password = accounts['OPERADOR']
                        assert (await client.post('/api/auth/login', json={'email': email, 'password': password})).status_code == 200
                        await conn.execute('UPDATE public.seg_users SET active=false WHERE id=%s', (user_id,))
                        assert (await client.get('/api/auth/me')).status_code == 401
                        await conn.execute('UPDATE public.seg_users SET active=true WHERE id=%s', (user_id,))
                        assert (await client.post('/api/auth/login', json={'email': email, 'password': password})).status_code == 200
                        await entrypoint.app.state.security.revoke_user(accounts['ADMINISTRADOR'][0], user_id, uuid4())
                        # Reconstructing the repository does not resurrect a revoked session.
                        entrypoint.app.state.security = SecurityRepository(TransactionPool())
                        assert (await client.get('/api/auth/me')).status_code == 401
                        audits = (await (await conn.execute('SELECT count(*) FROM public.seg_audit_events WHERE user_id=%s', (user_id,))).fetchone())[0]
                        assert audits >= 4
                        # An already-open authenticated stream must stop after revocation.
                        from routes.v1.agui_notify import emit
                        assert (await client.post('/api/auth/login', json={'email': email, 'password': password})).status_code == 200
                        topic = str(uuid4())
                        async with client.stream('GET', f'/api/ag-ui/notify/stream?threadId={topic}') as stream:
                            assert stream.status_code == 200
                            iterator = stream.aiter_lines()
                            assert 'CONNECTED' in await anext(iterator)
                            await entrypoint.app.state.security.revoke_user(accounts['ADMINISTRADOR'][0], user_id, uuid4())
                            await emit(str(user_id) + ':' + topic, {'type': 'SHOULD_NOT_BE_SENT'})
                            async def remainder():
                                return [line async for line in iterator]
                            lines = await asyncio.wait_for(remainder(), timeout=5)
                            assert not any('SHOULD_NOT_BE_SENT' in line for line in lines)
                        # Administration and password change go through actual HTTP, not repository calls.
                        admin_id, admin_email, admin_password = accounts['ADMINISTRADOR']
                        assert (await client.post('/api/auth/login', json={'email': admin_email, 'password': admin_password})).status_code == 200
                        headers = {'X-CSRF-Token': client.cookies.get('concilia_csrf')}
                        created_password = secrets.token_urlsafe(48)
                        seen_secrets.append(created_password)
                        created = await client.post('/api/auth/users', headers=headers, json={
                            'email': f'{uuid4()}@example.invalid', 'password': created_password, 'role': 'CONSULTA'})
                        assert created.status_code == 201
                        created_id = created.json()['id']
                        created_email = (await client.get('/api/auth/users')).json()
                        created_email = next(row['email'] for row in created_email if row['id'] == created_id)
                        async with httpx.AsyncClient(base_url=base_url) as recovering:
                            assert (await recovering.post('/api/auth/login', json={'email': created_email, 'password': created_password})).status_code == 200
                            assert (await client.post(f'/api/auth/users/{created_id}/password-reset', headers=headers,
                                json={'current_password': 'incorrect'})).status_code == 403
                            issued = await client.post(f'/api/auth/users/{created_id}/password-reset', headers=headers,
                                json={'current_password': admin_password})
                            assert issued.status_code == 200
                            reset_token = issued.json()['reset_token']
                            seen_secrets.append(reset_token)
                            assert (await recovering.get('/api/auth/me')).status_code == 401
                            reset_body = {'reset_token': reset_token, 'new_password': created_password}
                            assert (await recovering.post('/api/auth/password-reset', json=reset_body)).status_code == 200
                            assert (await recovering.post('/api/auth/password-reset', json=reset_body)).status_code == 400
                            second = await client.post(f'/api/auth/users/{created_id}/password-reset', headers=headers,
                                json={'current_password': admin_password})
                            assert second.status_code == 200
                            expired = second.json()['reset_token']
                            seen_secrets.append(expired)
                            from backend.core.security import token_hash
                            await conn.execute("UPDATE public.seg_password_resets SET created_at=CURRENT_TIMESTAMP - interval '2 hours', expires_at=CURRENT_TIMESTAMP - interval '1 hour' WHERE token_hash=%s", (token_hash(expired),))
                            assert (await recovering.post('/api/auth/password-reset', json={'reset_token': expired, 'new_password': created_password})).status_code == 400
                        assert (await client.post(f'/api/auth/users/{created_id}/update', headers=headers,
                            json={'role': 'OPERADOR', 'active': False})).status_code == 200
                        assert (await client.post(f'/api/auth/users/{created_id}/revoke', headers=headers, json={})).status_code == 200
                        assert (await client.post(f'/api/auth/users/{admin_id}/update', headers=headers,
                            json={'role': 'CONSULTA', 'active': True})).status_code == 400
                        assert (await client.post('/api/auth/password', headers=headers,
                            json={'current_password': 'incorrect', 'new_password': created_password})).status_code == 403
                        assert (await client.post('/api/auth/password', headers=headers,
                            json={'current_password': admin_password, 'new_password': created_password})).status_code == 200
                        assert (await client.get('/api/auth/me')).status_code == 401
                        assert all(secret not in caplog.text for secret in seen_secrets)
        finally:
            server.should_exit = True
            await task
            server_socket.close()
    asyncio.run(check())

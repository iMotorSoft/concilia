"""Real DEV Chromium/HTTP/restart regression. No secrets printed or repository credentials.
Run from SrvRestAstroLS_v1: uv run --with playwright python -m backend.scripts.verify_seg01_closure
Owns only processes it starts; PostgreSQL is never restarted or migrated.
"""
from __future__ import annotations
import asyncio
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
from uuid import uuid4

from backend.core.config import credentials, http_security, runtime_pool
from backend.repositories.security import SecurityRepository
from backend.repositories.dev_validation import snapshot, cleanup_files, login_budget_delay
from backend.repositories.files import file_digest

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent
API = 'http://127.0.0.1:7058'
UI = 'http://127.0.0.1:3058'


def fixture(role):
    from openpyxl import Workbook
    from datetime import datetime
    wb = Workbook()
    ws = wb.active
    if role == 'extracto':
        ws.append(['FECHA', 'DESCRIPCION', 'IMPORTE'])
        ws.append([datetime(2026, 1, 2), 'SYNTHETIC SEG01', -100])
    else:
        ws.title = 'Resumen cuenta bancaria'
        ws.append(['Fecha', 'Documento', 'Ingresos', 'Egresos'])
        ws.append([datetime(2026, 1, 2), 'SYNTHETIC SEG01', 0, 100])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


async def run():
    from playwright.async_api import async_playwright, expect
    from psycopg_pool import AsyncConnectionPool
    for port in (7058, 3058):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', port))
    historical = json.loads((REPO / 'data/reports/seg01_historical_before.json').read_text())
    def intact():
        assert all(file_digest(REPO / name) == digest for name, digest in historical.items())
    intact()
    result = dict(authenticated_e2e='FAIL', anonymous_chromium='FAIL', restart='FAIL')
    processes = []
    accounts = []
    phase = 'preflight'
    pool = runtime_pool(http_security().secret_path)
    async with pool, tempfile_context() as temporary:
        repository = SecurityRepository(pool)
        async def stop():
            for process, log in reversed(processes):
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        await asyncio.to_thread(process.wait, timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        await asyncio.to_thread(process.wait)
                log.close()
            processes.clear()
        async def start():
            for port in (7058, 3058):
                with socket.socket() as probe:
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    probe.bind(('127.0.0.1', port))
            for name, command, cwd in [
                ('backend', [sys.executable, '-m', 'uvicorn', 'ls_iMotorSoft_Srv01:app', '--host', '127.0.0.1', '--port', '7058', '--no-access-log', '--no-proxy-headers'], ROOT),
                ('frontend', ['pnpm', 'dev', '--host', '127.0.0.1', '--port', '3058'], ROOT / 'clientA')]:
                log = open(temporary / (name + '.log'), 'w')
                os.chmod(log.name, 0o600)
                processes.append((subprocess.Popen(command, cwd=cwd, stdout=log, stderr=log, start_new_session=True), log))
            import httpx
            async with httpx.AsyncClient() as client:
                for url, status in [(API + '/api/auth/me', 401), (UI + '/reconciliar', 200)]:
                    for _ in range(240):
                        assert all(process.poll() is None for process, _ in processes), 'server process exited'
                        try:
                            if (await client.get(url)).status_code == status:
                                break
                        except httpx.TransportError:
                            pass
                        await asyncio.sleep(.1)
                    else:
                        raise AssertionError('server readiness')
        try:
            delay = await login_budget_delay(pool)
            if delay:
                await asyncio.sleep(delay)
            accounts = await repository.provision_e2e()
            # Local outside-repository credential artifact, mode 0600, removed in finally.
            path = temporary / 'accounts.json'
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump(accounts, stream)
            result['temporary_users_created'] = len(accounts)
            await start()
            async with async_playwright() as pw:
                browser = await pw.chromium.launch()
                try:
                    context = await browser.new_context()
                    page = await context.new_page()
                    await page.goto(UI + '/reconciliar')
                    await expect(page.get_by_role('heading', name='Ingresar a Concilia FCE')).to_be_visible()
                    await expect(page.get_by_role('button', name='Subir extracto')).to_have_count(0)
                    assert (await context.request.post(API + '/api/reconcile/start')).status == 401
                    result['anonymous_chromium'] = 'PASS'
                    phase = 'login'
                    admin = accounts[0]
                    await page.get_by_label('Correo', exact=True).fill(admin['email'])
                    await page.get_by_label('Contraseña', exact=True).fill(admin['password'])
                    await page.get_by_role('button', name='Ingresar', exact=True).click()
                    await expect(page.get_by_role('button', name='Cerrar sesión')).to_be_visible()
                    await expect(page.get_by_role('button', name='Subir extracto')).to_be_enabled()
                    csrf = next(c['value'] for c in await context.cookies(API) if c['name'] == 'concilia_csrf')
                    headers = {'X-CSRF-Token': csrf, 'Origin': UI}
                    async def post(endpoint, form=None, data=None):
                        return await context.request.post(API + endpoint, form=form, data=data, headers=headers)
                    phase = 'financial_upload'
                    refs = {}
                    thread = str(uuid4())
                    await page.evaluate("url => { window.__segEvents = []; window.__segSource = new EventSource(url, {withCredentials:true}); window.__segSource.onmessage = e => window.__segEvents.push(JSON.parse(e.data)); }", API + '/api/ag-ui/notify/stream?threadId=' + thread)
                    await page.wait_for_function("window.__segEvents.some(e => e.stage === 'CONNECTED')")
                    for role in ('extracto', 'contable'):
                        uploaded = await context.request.post(API + '/api/uploads/v2/ingest?role=' + role, headers=headers,
                            multipart={'threadId': thread, 'file': {'name': 'seg01-synthetic-' + role + '.xlsx', 'mimeType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'buffer': fixture(role)}})
                        assert uploaded.status == 200, 'upload status'
                        payload = await uploaded.json()
                        refs[role] = payload['source_file_id']
                        assert str(__import__('uuid').UUID(refs[role])) == refs[role]
                        await page.wait_for_function("role => window.__segEvents.some(e => e.type === 'INGEST_PREVIEW' && e.payload.role === role)", arg=role)
                        preview = await page.evaluate("role => window.__segEvents.find(e => e.type === 'INGEST_PREVIEW' && e.payload.role === role).payload", role)
                        assert preview['table'].get('sample'), 'movement preview missing'
                        phase = 'financial_confirm'
                        confirmed = await post('/api/ingest/confirm', form={'threadId': thread, 'role': role, 'original_uri': refs[role]})
                        assert confirmed.status == 200, 'confirm status'
                    phase = 'financial_derived'
                    for _ in range(100):
                        evidence = await snapshot(pool, accounts)
                        if len(evidence['files']) >= 4:
                            break
                        await asyncio.sleep(.1)
                    assert len(evidence['files']) == 4, 'derived files missing'
                    form = {'uri_extracto': refs['extracto'], 'uri_contable': refs['contable'], 'threadId': thread}
                    phase = 'financial_compute'
                    response = await post('/api/reconcile/start', form=form)
                    assert response.status == 200, 'reconciliation status'
                    assert (await response.json())['summary']['conciliados_pares'] == 1
                    for endpoint in ('/api/reconcile/summary/head', '/api/reconcile/details/pares'):
                        assert (await post(endpoint, form=form)).status == 200, endpoint
                    phase = 'wizard'
                    response = await post('/api/reconcile_wizard/start', data={**form, 'bank': 'synthetic'})
                    assert response.status == 200
                    wizard = (await response.json())['run_id']
                    for _ in range(100):
                        response = await post('/api/reconcile_wizard/runs/' + wizard + '/action', data={'action_type': 'SELECT_WINDOW_DAYS', 'payload': {'window_days': 5}})
                        if response.status == 200:
                            break
                        await asyncio.sleep(.1)
                    assert response.status == 200
                    phase = 'negative_roles'
                    revoked = None
                    for account in accounts[1:]:
                        other = await browser.new_context()
                        login = await other.request.post(API + '/api/auth/login', data={'email': account['email'], 'password': account['password']})
                        assert login.status == 200
                        other_csrf = next(c['value'] for c in await other.cookies(API) if c['name'] == 'concilia_csrf')
                        other_headers = {'X-CSRF-Token': other_csrf, 'Origin': UI}
                        assert (await other.request.get(API + '/api/auth/users')).status == 403
                        assert (await other.request.post(API + '/api/reconcile_wizard/runs/' + wizard + '/action', headers=other_headers, data={'action_type': 'CONFIRM_START'})).status == 403
                        assert (await other.request.post(API + '/api/ingest/confirm', headers=other_headers, form={'threadId': str(uuid4()), 'role': 'extracto', 'original_uri': refs['extracto']})).status == 403
                        if account['role'] == 'CONSULTA':
                            assert (await other.request.post(API + '/api/reconcile/start', headers=other_headers, form=form)).status == 403
                        if revoked is None:
                            revoked = await other.storage_state()
                        assert (await other.request.post(API + '/api/auth/logout', headers=other_headers, data={})).status == 200
                        await other.close()
                    phase = 'audit'
                    before = await snapshot(pool, accounts)
                    actions = {r[1] for r in before['events']}
                    assert {'file_upload', 'file_derived', 'ingest_confirm_temporary', 'reconcile_compute_start', 'reconcile_compute_complete', 'wizard_start_temporary', 'wizard_action_select_window_days', 'http_rejection'} <= actions
                    assert all(r[4] and r[5].tzinfo for r in before['events'])
                    result['audit_actions'] = sorted(actions)
                    result['authenticated_e2e'] = 'PASS'
                    phase = 'restart'
                    await page.evaluate('window.__segSource.close()')
                    await stop()
                    await start()
                    assert (await context.request.get(API + '/api/auth/me')).status == 200
                    retired = await browser.new_context(storage_state=revoked)
                    assert (await retired.request.get(API + '/api/auth/me')).status == 401
                    await retired.close()
                    after = await snapshot(pool, accounts)
                    assert before['users'] == after['users']
                    assert before['files'] == after['files']
                    assert set(before['events']) <= set(after['events'])
                    assert before['sessions'] == after['sessions']
                    canonical = {str(row[3]): str(row[0]) for row in after['files'] if row[3]}
                    derived_form = {'uri_extracto': canonical[refs['extracto']], 'uri_contable': canonical[refs['contable']]}
                    assert (await post('/api/reconcile/summary/head', form=derived_form)).status == 200
                    anonymous = await browser.new_context()
                    assert (await anonymous.request.post(API + '/api/reconcile/start')).status == 401
                    await anonymous.close()
                    result['restart'] = 'PASS'
                    phase = 'logout'
                    saved = await context.storage_state()
                    await page.get_by_role('button', name='Cerrar sesión').click()
                    await expect(page.get_by_role('heading', name='Ingresar a Concilia FCE')).to_be_visible()
                    replay = await browser.new_context(storage_state=saved)
                    assert (await replay.request.get(API + '/api/auth/me')).status == 401
                    await replay.close()
                    result['logout_revocation'] = 'PASS'
                finally:
                    await browser.close()
        except Exception as exc:
            result['failure_phase'] = phase
            result['error_type'] = type(exc).__name__
            if type(exc) is AssertionError and str(exc) in {'upload status', 'movement preview missing', 'confirm status', 'derived files missing', 'reconciliation status', 'server readiness'}:
                result['assertion'] = str(exc)
            # Never print Playwright traces with passwords/cookies.
        finally:
            await stop()
            if accounts:
                await repository.deactivate_e2e(accounts)
                state = await snapshot(pool, accounts)
                assert all(not row[2] for row in state['users'])
                assert all(row[1] is not None for row in state['sessions'])
                result['temporary_users_deactivated'] = len(accounts)
                async with AsyncConnectionPool(kwargs=credentials(http_security().secret_path, 'concilia_owner').kwargs(), open=False) as owner:
                    result['synthetic_files_removed'] = await cleanup_files(owner, accounts)
            intact()
            result['historical_files_intact'] = len(historical)
    return result


from contextlib import asynccontextmanager
@asynccontextmanager
async def tempfile_context():
    with tempfile.TemporaryDirectory(prefix='concilia-seg01-') as directory:
        os.chmod(directory, 0o700)
        yield Path(directory)


if __name__ == '__main__':
    try:
        result = asyncio.run(run())
        print(json.dumps(result))
        raise SystemExit(0 if all(result.get(k) == 'PASS' for k in ('authenticated_e2e', 'anonymous_chromium', 'restart', 'logout_revocation')) else 1)
    except Exception as exc:
        print(json.dumps({'closure': 'FAIL', 'error_type': type(exc).__name__, 'details': 'withheld'}))
        raise SystemExit(1) from None

"""Chromium smoke against real DEV servers; starts/stops only its own processes.

Run from SrvRestAstroLS_v1 with uv run --with playwright python -m
backend.scripts.verify_http_browser. Never substitutes for financial E2E.
"""
from __future__ import annotations

from contextlib import ExitStack
import json
import os
import signal
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from backend.core.config import e2e_credentials

ROOT = Path(__file__).resolve().parents[2]
BACKEND = 'http://127.0.0.1:7058'
FRONTEND = 'http://127.0.0.1:3058'


def wait_for(url: str, expected: int):
    for _ in range(160):
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        except (urllib.error.URLError, TimeoutError):
            status = None
        if status == expected:
            return
        time.sleep(.1)
    raise RuntimeError('DEV server preflight failed')


def run():
    from playwright.sync_api import sync_playwright, expect
    credentials = e2e_credentials()
    for port in (7058, 3058):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))  # Refuse to touch existing services.
    processes = []
    logs = []
    try:
        with ExitStack() as stack:
            for command, cwd in [
                ([sys.executable, '-m', 'uvicorn', 'ls_iMotorSoft_Srv01:app', '--host', '127.0.0.1',
                  '--port', '7058', '--no-proxy-headers', '--no-access-log'], ROOT),
                (['pnpm', 'preview', '--host', '127.0.0.1', '--port', '3058'], ROOT / 'clientA'),
            ]:
                log = stack.enter_context(tempfile.NamedTemporaryFile(mode='w+', prefix='concilia-seg01-', suffix='.log', delete=False))
                logs.append(log.name)
                processes.append(subprocess.Popen(command, cwd=cwd, stdout=log, stderr=log, start_new_session=True))
            wait_for(BACKEND + '/api/auth/me', 401)
            wait_for(FRONTEND + '/reconciliar', 200)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    page = browser.new_page()
                    page.goto(FRONTEND + '/reconciliar')
                    expect(page.get_by_role('heading', name='Ingresar a Concilia FCE')).to_be_visible()
                    expect(page.get_by_role('button', name='Subir extracto')).to_have_count(0)
                    assert page.request.get(BACKEND + '/api/ag-ui/notify/stream').status == 401
                    assert page.request.post(BACKEND + '/api/reconcile/start').status == 401
                    authenticated = 'SKIP: E2E credentials not supplied'
                    if credentials:
                        email, password = credentials
                        page.get_by_label('Correo', exact=True).fill(email)
                        page.get_by_label('Contraseña', exact=True).fill(password)
                        page.get_by_role('button', name='Ingresar', exact=True).click()
                        expect(page.get_by_role('button', name='Cerrar sesión')).to_be_visible()
                        expect(page.get_by_role('button', name='Subir extracto')).to_be_enabled()
                        page.reload()
                        expect(page.get_by_role('button', name='Cerrar sesión')).to_be_visible()
                        page.get_by_role('button', name='Cerrar sesión').click()
                        expect(page.get_by_role('heading', name='Ingresar a Concilia FCE')).to_be_visible()
                        assert page.request.get(BACKEND + '/api/auth/me').status == 401
                        authenticated = 'PASS: login, persistent cookie, reload, logout'
                    return {'anonymous_chromium': 'PASS', 'authenticated_chromium': authenticated,
                            'financial_operations': 'NOT_TESTED', 'logs': logs}
                finally:
                    browser.close()
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)


if __name__ == '__main__':
    try:
        print(json.dumps(run()))
    except Exception as exc:
        # Do not print browser traces containing filled passwords or response cookies.
        print(json.dumps({'browser': 'FAIL', 'error_type': type(exc).__name__, 'details': 'withheld'}))
        raise SystemExit(1) from None

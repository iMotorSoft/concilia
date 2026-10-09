"""Revalidate persistent sessions before sending each SSE chunk."""
from __future__ import annotations

from litestar.connection import ASGIConnection
from uuid import uuid4

from backend.http.security import SESSION_COOKIE


class _SessionEnded(BaseException):
    pass


class SessionStreamMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        streaming = False
        connection = ASGIConnection(scope, receive, send)

        async def checked_send(message):
            nonlocal streaming
            if message['type'] == 'http.response.start':
                if message['status'] >= 400:
                    principal = getattr(connection.state, 'principal', None)
                    await scope['app'].state.security.audit_operation(
                        principal.id if principal else None, 'http_error', scope['path'],
                        'FAILURE' if message['status'] >= 500 else 'DENIED',
                        getattr(connection.state, 'correlation_id', None) or uuid4(),
                        'HTTP status ' + str(message['status']), 'http')
                headers = dict(message.get('headers', []))
                streaming = message['status'] == 200 and b'text/event-stream' in headers.get(b'content-type', b'')
            elif streaming and message['type'] == 'http.response.body':
                user = await scope['app'].state.security.authenticate(connection.cookies.get(SESSION_COOKIE, ''))
                if user is None:
                    await send({'type': 'http.response.body', 'body': b'', 'more_body': False})
                    raise _SessionEnded()
            await send(message)

        try:
            await self.app(scope, receive, checked_send)
        except* _SessionEnded:
            # Headers are already sent: terminate, never stream another protected event.
            pass

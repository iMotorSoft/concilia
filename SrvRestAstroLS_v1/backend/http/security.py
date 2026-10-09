"""Central HTTP boundary for SEG-01. Unknown operations are denied, never inferred."""
from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from litestar import Request, get, post
from litestar.connection import ASGIConnection
from litestar.exceptions import HTTPException
from litestar.response import Response

from backend.core.config import http_security, runtime_pool
from backend.core.security import valid_csrf
from backend.repositories.security import SecurityRepository
from backend.repositories.files import FileDenied, FileRepository

SESSION_COOKIE = "concilia_session"
CSRF_COOKIE = "concilia_csrf"

# POST summaries/details are reads, not operator-only writes.
CAPABILITIES = {
    "upload_bank_movements": "upload", "upload_ingest_v2": "upload",
    "ingest_confirm": "upload", "reconcile_start": "reconcile",
    "reconcile_wizard_start": "reconcile", "run_action": "manual",
    "notify_stream": "view", "run_events": "view", "chat_turn": "reconcile",
    "reconcile_details": "view", "reconcile_details_no_banco": "view",
    "reconcile_details_pares": "view", "reconcile_details_no_contable": "view",
    "reconcile_details_n1_grupos": "view", "reconcile_details_n1_sugeridos": "view",
    "reconcile_summary": "view", "reconcile_summary_head": "view",
    "reconcile_summary_descomposicion": "view",
    "auth_me": "view", "auth_logout": "view", "auth_change_password": "view",
    "auth_users": "users", "auth_create_user": "users", "auth_update_user": "users",
    "auth_revoke_user": "users", "auth_issue_reset": "users",
}


@asynccontextmanager
async def security_lifespan(app):
    config = http_security()
    pool = runtime_pool(config.secret_path)
    await pool.open(wait=True)
    app.state.security = SecurityRepository(pool)
    app.state.files = FileRepository(pool)
    app.state.http_security = config
    try:
        yield
    finally:
        await pool.close()


def repository(connection) -> SecurityRepository:
    return connection.app.state.security


def require_origin(connection) -> None:
    # Exact allowlist, no trust in forwarded headers or wildcard origins.
    origin = connection.headers.get("origin")
    if origin is not None and origin not in connection.app.state.http_security.origins:
        raise HTTPException(status_code=403, detail="Origin denied")


async def security_guard(connection: ASGIConnection, route_handler) -> None:
    name = route_handler.fn.__name__
    if name in {"auth_login", "auth_reset_password"}:
        require_origin(connection)
        return
    user = await repository(connection).authenticate(connection.cookies.get(SESSION_COOKIE, ""))
    connection.state.correlation_id = uuid4()
    async def denied(status, reason):
        await repository(connection).audit_operation(
            user.id if user else None, 'http_rejection', name, 'DENIED',
            connection.state.correlation_id, reason)
        raise HTTPException(status_code=status, detail=reason)
    if user is None:
        await denied(401, "Authentication required")
    capability = CAPABILITIES.get(name)
    if capability is None or not user.allows(capability):
        await denied(403, "Permission denied")
    connection.state.principal = user
    if connection.scope.get("method") not in {"GET", "HEAD", "OPTIONS"}:
        require_origin(connection)
        if not valid_csrf(user.csrf_hash, connection.cookies.get(CSRF_COOKIE, ""),
                          connection.headers.get("x-csrf-token", "")):
            await denied(403, "CSRF denied")
    if name in {'run_action', 'run_events'}:
        from services.wizard_runtime import memory_run_owner
        owner = memory_run_owner(connection.path_params.get('run_id', ''))
        if owner is not None and owner != str(user.id):
            await denied(403, 'Wizard reference denied')
    if name in CAPABILITIES and not name.startswith('auth_') and connection.scope.get('method') == 'POST':
        request = Request(connection.scope, receive=connection.receive, send=connection.send)
        if "application/json" in request.headers.get("content-type", ""):
            values = await request.json()
            pairs = values.items() if isinstance(values, dict) else []
        else:
            values = await request.form()
            pairs = values.multi_items()
        # Preserve legacy field names, but their public values are now permanent UUIDs.
        # The HTTP parser cache is replaced so handlers never receive client paths.
        resolved = []
        connection.state.file_refs = {}
        try:
            for key, value in pairs:
                if key == 'threadId' and value:
                    # Private event channels: knowing another user's thread UUID grants no access.
                    value = str(user.id) + ':' + str(value)
                if key in {"original_uri", "uri_extracto", "uri_contable", "uri_sicom",
                           "extracto_original_uri", "contable_original_uri", "sicom_original_uri"} and value:
                    reference = value
                    value = await connection.app.state.files.resolve(reference, user)
                    connection.state.file_refs[value] = reference
                resolved.append((key, value))
        except FileDenied:
            await denied(403, "File reference denied")
        if isinstance(values, dict):
            request._connection_state.json = dict(resolved)
        else:
            form_data = {}
            for key, value in resolved:
                form_data.setdefault(key, []).append(value)
            request._connection_state.form = form_data


def validate_legacy_file(value: str) -> None:
    """Transitional boundary, not a replacement for a PostgreSQL resource-ID catalog."""
    from pathlib import Path
    from urllib.parse import urlparse
    if not isinstance(value, str):
        raise HTTPException(status_code=403, detail="File reference denied")
    uri = urlparse(value)
    path = Path(uri.path if uri.scheme == "file" else value)
    root = Path(__file__).resolve().parents[3] / "storage"
    roots = [root / "incoming", root / "canonical"]
    # Exact absolute server paths only: no traversal, remote URIs, aliases or symlinks.
    if (uri.scheme not in {"", "file"} or uri.netloc or uri.query or uri.fragment
            or not path.is_absolute() or ".." in path.parts
            or not path.is_file() or path.resolve() != path
            or not any(path.is_relative_to(allowed) for allowed in roots)
            or path.suffix.lower() not in {".xlsx", ".xls", ".xlsm", ".xltx", ".xltm", ".csv", ".parquet", ".json"}):
        raise HTTPException(status_code=403, detail="File reference denied")


def user_json(user) -> dict:
    return {"id": str(user.id), "email": user.email, "role": user.role}


def cookies(response, request, token: str, csrf: str, clear: bool = False):
    secure = request.app.state.http_security.secure_cookies
    for name, value, http_only in [(SESSION_COOKIE, token, True), (CSRF_COOKIE, csrf, False)]:
        response.set_cookie(key=name, value=value, path="/", httponly=http_only,
                            secure=secure, samesite="lax", max_age=0 if clear else 86400)
    return response


@post("/api/auth/login", status_code=200)
async def auth_login(request: Request, data: dict[str, str]) -> Response:
    email, password = data.get("email", ""), data.get("password", "")
    if not isinstance(email, str) or not isinstance(password, str):
        raise HTTPException(status_code=400, detail="Invalid login")
    # IP comes from the ASGI server, not a browser-provided key / forwarded header.
    client_key = request.client.host if request.client else "unknown"
    issued = await repository(request).login(email, password, client_key, uuid4())
    if not issued:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token, csrf, user = issued
    return cookies(Response(user_json(user), headers={"Cache-Control": "no-store"}), request, token, csrf)


@get("/api/auth/me")
async def auth_me(request: Request) -> Response:
    return Response(user_json(request.state.principal), headers={"Cache-Control": "no-store"})


@post("/api/auth/logout", status_code=200)
async def auth_logout(request: Request) -> Response:
    await repository(request).logout(request.cookies[SESSION_COOKIE], uuid4())
    return cookies(Response({"ok": True}, headers={"Cache-Control": "no-store"}), request, "", "", clear=True)


@post("/api/auth/password", status_code=200)
async def auth_change_password(request: Request, data: dict[str, str]) -> Response:
    try:
        changed = await repository(request).change_password(request.state.principal.id,
            data.get("current_password", ""), data.get("new_password", ""), uuid4())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid password policy") from None
    if not changed:
        raise HTTPException(status_code=403, detail="Current password rejected")
    return cookies(Response({"ok": True}), request, "", "", clear=True)


@get("/api/auth/users")
async def auth_users(request: Request) -> Response:
    return Response(await repository(request).list_users(), headers={"Cache-Control": "no-store"})


@post("/api/auth/users", status_code=201)
async def auth_create_user(request: Request, data: dict) -> Response:
    try:
        user_id = await repository(request).create_user(request.state.principal.id, data.get("email", ""),
            data.get("password", ""), data.get("role", ""), uuid4())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid or existing user") from None
    return Response({"id": str(user_id)}, status_code=201)


@post("/api/auth/users/{user_id:uuid}/update", status_code=200)
async def auth_update_user(request: Request, user_id: UUID, data: dict) -> dict:
    try:
        await repository(request).update_user(request.state.principal.id, user_id,
            data.get("role"), data.get("active"), uuid4())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user update") from None
    return {"ok": True}


@post("/api/auth/users/{user_id:uuid}/revoke", status_code=200)
async def auth_revoke_user(request: Request, user_id: UUID) -> dict:
    await repository(request).revoke_user(request.state.principal.id, user_id, uuid4())
    return {"ok": True}


@post("/api/auth/users/{user_id:uuid}/password-reset", status_code=200)
async def auth_issue_reset(request: Request, user_id: UUID, data: dict[str, str]) -> Response:
    token = await repository(request).issue_password_reset(request.state.principal.id, user_id,
        data.get("current_password", ""), uuid4())
    if token is None:
        raise HTTPException(status_code=403, detail="Recovery issuance rejected")
    return Response({"reset_token": token, "expires_in_seconds": 900}, headers={"Cache-Control": "no-store"})


@post("/api/auth/password-reset", status_code=200)
async def auth_reset_password(request: Request, data: dict[str, str]) -> Response:
    try:
        changed = await repository(request).reset_password(data.get("reset_token", ""),
            data.get("new_password", ""), request.client.host if request.client else "unknown", uuid4())
    except ValueError:
        raise HTTPException(status_code=400, detail="Recovery rejected") from None
    if not changed:
        raise HTTPException(status_code=400, detail="Recovery rejected")
    return cookies(Response({"ok": True}, headers={"Cache-Control": "no-store"}), request, "", "", clear=True)


AUTH_HANDLERS = [auth_login, auth_me, auth_logout, auth_change_password, auth_users,
                 auth_create_user, auth_update_user, auth_revoke_user, auth_issue_reset, auth_reset_password]

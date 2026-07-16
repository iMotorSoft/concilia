# Authentication & Security Policy

This policy governs authentication, authorization and security in Concilia.

## Authentication

### Method

- **Session-based** with `httpOnly` `Secure` `SameSite=Lax` cookies
- **No JWT in localStorage** (XSS vector)
- **CSRF** via `SameSite` + double-submit cookie for mutating endpoints

### Login Flow

```
POST /api/auth/login {email, password}
→ 200 + Set-Cookie: session=...; HttpOnly; Secure; SameSite=Lax
→ GET /api/auth/me → 200 {user, roles}
```

### Password Policy

- Argon2id (via `passlib`)
- Min 12 chars, no complexity rules (length > complexity)
- Breach check via `haveibeenpwned` API (k-anonymity)

### Session

- TTL: 24h sliding, 7d absolute
- Rotated on privilege change
- Invalidated on password change, logout, admin revoke

## Authorization

### Roles

| Role | Scope | Capabilities |
|------|-------|--------------|
| `admin` | Global | All + user management |
| `operator` | Tenant | Upload, reconcile, wizard, view |
| `viewer` | Tenant | Read-only reports |

### Tenant Isolation

- Every request scoped to `request.state.tenant_id`
- Middleware enforces `tenant_id` on all repository queries
- No cross-tenant queries without explicit `admin` override

## Security Headers

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=()
```

## Secrets Management

- **Never** in code, `.env` committed, logs, or browser
- Backend: `CONCILIA_*` env vars → `core/config.py`
- Frontend: Only `global.js` public config (no secrets)
- Rotation: Quarterly + on compromise suspicion

## Audit Logging

| Event | Logged |
|-------|--------|
| Login success/failure | ✅ |
| Password change | ✅ |
| Role change | ✅ |
| Reconciliation run | ✅ |
| Wizard action | ✅ |
| File upload | ✅ |

## Forbidden

- `localStorage`/`sessionStorage` for auth tokens
- Password in URL, logs, or error messages
- Admin endpoints without `admin` role check
- SQL string interpolation
- `eval`/`Function` constructor in frontend
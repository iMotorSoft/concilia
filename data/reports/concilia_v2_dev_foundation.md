# Concilia FCE V2 — entrega parcial DEV

Se ejecutó preparación, aprovisionamiento y persistencia inicial SEG-01. No se cerró la fase 0 ni se avanzó a fases dependientes. Esta entrega no protege todavía el runtime HTTP existente.

## Identidad y alcance

Rama: `procesamiento-multiple-extractos`. HEAD inicial/final: `701fc910f49e80981b532e100c35413736d22eb8`.

Sin commit, push, cambios de rama, despliegue ni reinicio de PostgreSQL/backend. Se preservaron los cambios preexistentes; no se modificaron sus rutas/componentes. No se conectó a bases ajenas: únicamente `postgres` para aprovisionamiento autorizado y `concilia_fce` para V2.

## Implementado

La base `concilia_fce` se creó tras comprobar otra vez que no existía. PostgreSQL DEV respondió versión `18.4 (Debian 18.4-1.pgdg13+1)`, `server_version_num=180004`, en `127.0.0.1:5432`.

Roles técnicos `concilia_owner` y `concilia_app`, ambos sin SUPERUSER, CREATEDB, CREATEROLE, REPLICATION ni BYPASSRLS. El owner aplica migraciones; el app conecta con privilegios de tablas específicos. PUBLIC no tiene acceso a la base/esquema. El app no crea tablas ni actualiza/borra auditoría.

Tablas creadas en `public`:

- `concilia_schema_migrations` (ledger exclusivo de migraciones).
- `seg_users` (roles fijos y hashes Argon2id).
- `seg_sessions` (hash SHA-256 de token opaco y CSRF, límite absoluto 24h).
- `seg_password_resets` (solo estructura; flujo pendiente).
- `seg_audit_events` (append-only para runtime).
- `seg_rate_limits` (buckets persistentes).

Aplicada `001_seg01.sql` con checksum. Los scripts `000_dev_provision.sql` / `000_dev_database.sql` son aprovisionamiento explícito; `000_migration_ledger.sql` inicializa el ledger. No hay migración automática al arrancar.

Primitivas implementadas, **sin integrar al HTTP**: Argon2id, validación de passwords de 12–1024 caracteres, sesiones revocables, inactividad 8h, absoluta 24h, logout, capacidades deny-by-default, validación CSRF, rate limiting persistente por correo y cliente, auditoría transaccional de login/logout. Un trigger revoca sesiones al cambiar password/rol o desactivar usuario.

Procedimiento interactivo para el primer administrador sin defaults ni contraseñas por argumento. Implementado, pero no ejecutado: no hay usuarios persistentes ni credenciales E2E provisionadas.

Secretos técnicos generados aleatoriamente en `storage/v2-dev/technical-credentials.json`, ignorado por Git, modo 0600. No contiene datos financieros. Se confirmó que sus valores no aparecen en los 16 archivos de código/configuración/ADR examinados. No se imprimieron passwords/tokens. Esto no constituye una auditoría completa de logs del runtime legacy.

## Validado mediante ejecución

El primer aprovisionamiento informó `CREATED`. Una segunda ejecución informó `EXISTING_VERIFIED_NO_CHANGES`. La segunda migración devolvió `applied: []`. Una conexión real mediante el pool V2 confirmó `('concilia_app', 'concilia_fce')`.

Comandos ejecutados desde `SrvRestAstroLS_v1/`:

```bash
uv sync
uv run python -m backend.scripts.provision_dev
uv run python -m backend.scripts.provision_dev --apply
uv run python -m backend.scripts.migrate
uv run python -m backend.scripts.provision_dev --apply
uv run python -m backend.scripts.migrate
uv run pytest backend/tests/test_v2_foundation.py -q
uv run pytest backend/tests tests/test_sniff_bank.py tests/reconcile -q
```

Resultados: primera suite **7 passed**; suite final **15 passed**, 11 warnings preexistentes de inferencia de fechas del parser. No se omitieron tests de las suites ejecutadas.

Las pruebas V2 cubren configuración fuera de alcance, permisos del archivo de secretos, ausencia de password en repr, Argon2id, capacidades, comprobación CSRF, login válido/inválido a nivel repository, logout, sesiones expiradas, usuario desactivado, revocación por rol, rate limiter compartido entre instancias y rollback de sesión si falla auditoría. Prueban rechazo real PostgreSQL de DDL runtime, actualización/borrado de auditoría, rol inválido y sesión absoluta mayor a 24h.

Los fixtures sintéticos de los tests se ejecutaron contra PostgreSQL real dentro de transacciones rollback. Al finalizar se verificó `0` filas persistentes en las cinco tablas SEG-01. No son pruebas HTTP ni sustituyen el gate browser.

Frontend: `pnpm check` **FAIL**, no existe ese script en el package.json actual. `pnpm build` **PASS**, 4 páginas, warning CSS `@property`. No se agregó un script ficticio ni se declaró typecheck aprobado.

`git diff --check`: **PASS**. `lat check`: **FAIL**, 102 errores estructurales en documentos LAT existentes (secciones sin párrafo inicial o demasiado largo). No se modificó LAT ni se mezcló esa deuda con el alcance V2.

## Integridad de archivos históricos

Se calcularon manifests SHA-256 antes y después del aprovisionamiento/pruebas, incorporando nombre y digest de cada archivo. Los manifests y conteos quedaron idénticos:

| Directorio | Archivos | Manifest SHA-256 |
| --- | ---: | --- |
| `storage/incoming/` | 368 XLSX | `4ab04ea64ab5ec606f4a0bb98a4e3072544fb1facdb478c6892ff99dd05379dd` |
| `storage/canonical/` | 219 Parquet + 1 JSON | `7d66f0efb1fdfcbfb8ecc15b599f82a467e1ec3b0cc0076359be3c354b7b41be` |

No se importaron ni modificaron estos archivos. El hashing para integridad no valida casos financieros.

## Archivos de esta entrega

Se modificaron exclusivamente estos archivos versionados adicionales al estado inicial:

- `SrvRestAstroLS_v1/pyproject.toml`.
- `SrvRestAstroLS_v1/uv.lock`.

Se crearon:

- `SrvRestAstroLS_v1/backend/core/config.py`.
- `SrvRestAstroLS_v1/backend/core/security.py`.
- `SrvRestAstroLS_v1/backend/db/migrations/000_dev_provision.sql`.
- `SrvRestAstroLS_v1/backend/db/migrations/000_dev_database.sql`.
- `SrvRestAstroLS_v1/backend/db/migrations/000_migration_ledger.sql`.
- `SrvRestAstroLS_v1/backend/db/migrations/001_seg01.sql`.
- `SrvRestAstroLS_v1/backend/repositories/dev_foundation.py`.
- `SrvRestAstroLS_v1/backend/repositories/security.py`.
- `SrvRestAstroLS_v1/backend/scripts/provision_dev.py`.
- `SrvRestAstroLS_v1/backend/scripts/migrate.py`.
- `SrvRestAstroLS_v1/backend/scripts/create_first_admin.py`.
- `SrvRestAstroLS_v1/backend/tests/test_v2_foundation.py`.
- `SrvRestAstroLS_v1/backend/tests/test_v2_security.py`.
- `docs/adr/ADR-005-concilia-v2-dev-foundation.md`.
- `data/reports/concilia_v2_dev_foundation.md`.

Además se creó el archivo local de secretos ignorado indicado arriba. Los outputs habituales del build no son cambios de fuentes de esta entrega.

## Gates y limitaciones críticas

Los estados FAIL expresan que no se satisface el gate completo, no que todas las pruebas ejecutadas hayan fallado.

```text
CONCILIA_V2_SEG01_DEV=FAIL
CONCILIA_V2_FOUNDATION_DEV=FAIL
CONCILIA_V2_RECONCILIATION_DEV=FAIL
```

SEG-01 está **IMPLEMENTADO PARCIALMENTE / VALIDADO SOLO EN PRIMITIVAS Y PERSISTENCIA**. Las fases anual y conciliación están **PENDIENTES, NO EJECUTADAS, BLOQUEADAS POR EL GATE ANTERIOR**.

**Endpoints protegidos por esta entrega: ninguno.** El entrypoint existente no monta estos repositories. El runtime legacy sigue sin autenticación efectiva y sigue aceptando URIs del navegador. No se declara que el acceso anónimo o indebido a archivos haya sido corregido.

Para completar SEG-01 quedan login/logout/me HTTP, cookies HttpOnly/SameSite/Secure en HTTPS, protección CSRF efectiva de rutas, CORS de credenciales restringido, middleware central por operación, autorización de SSE y recursos, resolución autorizada por IDs internos, gestión de usuarios/password reset, login frontend y Playwright Chromium. El valor `client_key` del rate limiter debe derivarse de IP confiable del servidor, nunca de datos enviados libremente por el navegador.

No se verificaron reinicio HTTP conservando sesiones, concurrencia multiworker, flujo administrativo interactivo, secretos de logs legacy, restablecimiento de passwords ni reproducción en un segundo clúster limpio. Las pruebas CSRF/capacidades son de primitivas, no pruebas de cookies ni de acceso a endpoints.

No hay modelo anual, catálogo de nuevos uploads, decisiones financieras persistentes, diferencias/complementaciones/reversiones ni integración de auditoría financiera. No se validaron los casos reales de junio–agosto ni Payway/DECIDIR con V2.

## Próximo paso y riesgos

Continuar la fase 0 integrando los controles HTTP y frontend, con pruebas anónimo/roles/CSRF/archivos/SSE y reinicio. No iniciar fases 1–2 hasta SEG-01 PASS. No desplegar este estado parcial como aplicación segura.

La documentación describe paths/stack que no coinciden con este checkout; se registra la desviación en ADR-005 sin trasladar ni sobrescribir archivos. Persisten la deuda LAT y la ausencia de typecheck frontend.

El aprovisionamiento no repara automáticamente estados parciales: si CREATE DATABASE falla después de crear roles, se detiene para inspección segura. Los secretos locales incluyen owner/app juntos para herramientas DEV; todavía falta separar configuración y secretos por proceso al activar runtime. No se considera producción lista.

# ADR-005 — Fundación aislada de Concilia FCE V2 en DEV

Esta decisión establece el aprovisionamiento y las primitivas SEG-01 de V2 sin activar una integración HTTP de seguridad incompleta.

## Estado

Aceptada para la preparación DEV autorizada por el usuario. La fase SEG-01 permanece incompleta y no está habilitada en el runtime existente.

## Contexto comprobado

El worktree usa `procesamiento-multiple-extractos`. El entrypoint real es `SrvRestAstroLS_v1/ls_iMotorSoft_Srv01.py:app`; el entrypoint bajo `backend/` y los launchers descritos por LAT no existen en este checkout.

El frontend instalado es Astro 5 / Svelte 5, no Astro 7. No hay script `pnpm check`. El backend legacy usa `asyncpg`, configuración con lecturas de entorno y rutas que reciben URIs del navegador. Varias rutas y componentes tienen cambios preexistentes del usuario.

El preflight de solo lectura confirmó PostgreSQL 18.4 en loopback:5432, ausencia de `concilia_fce` y ausencia de ambos roles técnicos antes del aprovisionamiento.

## Decisión

V2 reside inicialmente bajo `SrvRestAstroLS_v1/backend/`, aislado del runtime legacy. No se crea `app.py`, no se mueve el entrypoint ni se modifica el matcher en esta entrega.

- Base `concilia_fce`, esquema `public`, propietario `concilia_owner`, runtime `concilia_app`.
- Ambos roles son LOGIN sin SUPERUSER, CREATEDB, CREATEROLE, REPLICATION ni BYPASSRLS.
- La conexión administrativa existente se utiliza solo para inspección/aprovisionamiento autorizado de esos recursos. No se conecta a bases ajenas.
- Psycopg 3 async para V2; `asyncpg` permanece exclusivamente por compatibilidad legacy.
- Configuración V2 centralizada en `backend/core/config.py`, sin importar `globalVar`.
- Secretos técnicos aleatorios en archivo local ignorado, propietario actual, modo 0600; no se imprimen ni se sobrescriben.
- DDL versionado en `backend/db/migrations/`; aplicación explícita con rol owner, bloqueo advisory y checksum. No hay automigración al arrancar.
- Grants específicos; runtime no puede crear tablas ni actualizar/borrar auditoría.
- No se importa ningún archivo financiero ni se crea automáticamente un administrador.

Las instrucciones V2 del usuario prevalecen sobre los defaults LAT anteriores: inactividad 8 horas, absoluta 24 horas, roles CONSULTA/OPERADOR/ADMINISTRADOR y despliegue single-tenant sin IAM/workspaces. Argon2id se implementa con `argon2-cffi`, no `passlib`. La comprobación externa de contraseñas comprometidas no está implementada.

## Integración pendiente

Las primitivas de password, sesión, CSRF, permisos, rate limiting y auditoría tienen pruebas propias contra PostgreSQL. **No equivalen a autenticación HTTP efectiva**: no hay nuevas cookies, rutas auth, middleware, frontend login ni autorización de recursos conectados al entrypoint.

Antes de integrar hay que cubrir todas las operaciones registradas, incluyendo POST de consulta y SSE, y sustituir URIs arbitrarias por identificadores internos autorizados. La auditoría financiera debe compartir transacción con la decisión; el repository de sesiones no resuelve ese contrato.

No se activa parcialmente la protección HTTP ni se avanza a la fase anual mientras SEG-01 no obtenga PASS. Esto no elimina los problemas de seguridad existentes del runtime legacy.

## Reproducción DEV

Los comandos se ejecutan desde `SrvRestAstroLS_v1/`, con las credenciales administrativas autorizadas ya inyectadas en el entorno; no se incluyen valores en esta documentación.

```bash
uv sync
uv run python -m backend.scripts.provision_dev          # solo lectura
uv run python -m backend.scripts.provision_dev --apply  # creación explícita DEV
uv run python -m backend.scripts.migrate
uv run pytest backend/tests -q
```

El primer administrador requiere una acción local explícita con entrada interactiva, nunca password por argumento, default o fixture:

```bash
uv run python -m backend.scripts.create_first_admin
```

Este último procedimiento está implementado pero no fue ejecutado en esta entrega. Rechaza aprovisionar si ya existe un administrador. No constituye todavía una UI de administración ni un flujo de restablecimiento.

## Recuperación y límites

El aprovisionamiento detecta recursos existentes y verifica propietario, roles y credenciales sin alterarlos. Un estado parcial o incompatible produce FAIL: no borra ni repara recursos automáticamente. CREATE DATABASE no puede compartir la transacción de creación de roles; si falla, se requiere inspección explícita del estado parcial.

La idempotencia de migraciones usa un ledger y checksum, no DDL destructivo ni `DROP`. No se ha reproducido aún todo el aprovisionamiento en un segundo clúster limpio: solo se validaron la creación inicial real y las repeticiones en este DEV.

La separación owner/app evita privilegios de esquema en runtime, pero la entrega aún no proporciona separación de secretos por proceso ni integración de configuración con el runtime legacy. El archivo local contiene ambos secretos técnicos y solo sirve a herramientas DEV.

La evidencia y gates se registran en `data/reports/concilia_v2_dev_foundation.md`. No se considera producción lista.

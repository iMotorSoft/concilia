# SEG-01 DEV — cierre parcial de referencias a archivos

## Gates

- `CONCILIA_V2_SEG01_HTTP_DEV=FAIL`
- `CONCILIA_V2_SEG01_DEV=FAIL`

No se ejecutaron fases 1–2, commits, push ni acciones sobre producción/Team360.
No se reinició ni reconfiguró PostgreSQL. Se aplicó exclusivamente una migración aditiva
al catálogo de la base DEV aislada `concilia_fce`.

## Repositorio e implementación de esta ejecución

Rama inicial/final: `procesamiento-multiple-extractos`. Worktree inicialmente sucio con
cambios de seguridad, frontend, SICOM y matcher preexistentes, preservados con ediciones puntuales.
El entrypoint efectivo sigue siendo `SrvRestAstroLS_v1/ls_iMotorSoft_Srv01.py:app`.
No se creó `backend/app.py` ni se reconstruyeron login, sesiones, roles o CSRF.

Archivos intervenidos en esta ejecución (no es la lista completa del worktree sucio):

- `SrvRestAstroLS_v1/backend/db/migrations/002_seg01_files.sql` (nuevo).
- `SrvRestAstroLS_v1/backend/repositories/files.py` (nuevo).
- `SrvRestAstroLS_v1/backend/http/security.py` (preexistente no versionado).
- `SrvRestAstroLS_v1/backend/tests/test_v2_files.py` (nuevo).
- `SrvRestAstroLS_v1/backend/tests/test_v2_http.py` (preexistente no versionado).
- `SrvRestAstroLS_v1/routes/v1/uploads_concilia.py`.
- `SrvRestAstroLS_v1/routes/v1/uploads_v2_concilia.py`.
- `SrvRestAstroLS_v1/routes/v1/ingest_confirm.py`.
- `SrvRestAstroLS_v1/docs/status_actual.md`.
- `data/reports/seg01_historical_before.json` (nuevo inventario de hashes).
- Este informe (nuevo).

## Catálogo y autorización

`public.seg_files`: UUID permanente, fuente (`extracto`, `contable`, `sicom`), ubicación relativa
controlada, usuario de carga, fecha, SHA-256, estado y parent_id opcional de derivación.
No es un catálogo provisional ni incorpora ejercicio/cuenta/período, pendientes de otras fases.
El despliegue sigue siendo single-tenant; no se implementó IAM/workspaces.

Runtime tiene SELECT/INSERT en catálogo, sin permiso de DDL ni actualización/borrado de auditoría.
Propietario y ADMINISTRADOR pueden resolver archivos disponibles; otro usuario no puede.
CONSULTA mantiene permisos de lectura, no de carga/confirmación. No hay endpoint de registro por path.
Solo backend registra archivos recién creados. La tabla queda vacía después de los tests rollback:
**0 archivos históricos importados**, 0 cargas sintéticas comprometidas por estos tests.

Los nombres `original_uri`, `uri_extracto`, etc. se preservan para compatibilidad UI, pero sus
valores públicos ahora son UUIDs. Backend reemplaza el cache JSON/form de Litestar por URIs
internas después de autorizar y comprobar hash. Los parsers legacy no reciben paths del navegador.
Las referencias de canónicos y manifest de extractos emitidas por SSE también son IDs.
Confirmación ignora el source_file_id suministrado y utiliza la identidad resuelta.
Un thread de confirmación ya existente no puede ser mutado por otro actor.

Cargas JSON/parquet están prohibidas: un cliente no puede introducir un manifest con paths internos.
Cargas originales usan nombre UUID y creación exclusiva, no el nombre original como destino.
Se rechazan paths absolutos, file://, URLs, traversal, IDs inexistentes/ajenos, symlinks en cualquier
componente, archivos inexistentes y hash modificado. No existe fallback de IDs a paths históricos.
El helper legacy de validación permanece únicamente para su prueba previa; ya no autoriza HTTP.

## Inventario HTTP

Productores de referencias:

- `POST /api/uploads/bank-movements`
- `POST /api/uploads/v2/ingest`
- Canónicos/manifest derivados durante confirmación (backend/SSE).

Consumidores protegidos por resolución central (12 rutas):

- `POST /api/ingest/confirm`
- `POST /api/reconcile/start`
- `POST /api/reconcile_wizard/start` (JSON).
- `POST /api/reconcile/details`
- `POST /api/reconcile/details/no-banco`
- `POST /api/reconcile/details/pares`
- `POST /api/reconcile/details/no-contable`
- `POST /api/reconcile/details/n1/grupos`
- `POST /api/reconcile/details/n1/sugeridos`
- `POST /api/reconcile/summary`
- `POST /api/reconcile/summary/head`
- `POST /api/reconcile/summary/descomposicion`

Las 18 rutas de negocio montadas mantienen prueba HTTP de rechazo anónimo. Los módulos legacy
no montados no se han habilitado ni se consideran parte de un gate autenticado financiero.

## Auditoría

Tabla existente `public.seg_audit_events`, sin nuevos secretos ni contenido financiero en eventos.
Acciones nuevas `file_upload` y `file_derived`: actor, recurso UUID, resultado, fecha automática,
correlación UUID generada por servidor. INSERT de catálogo y auditoría comparten transacción;
una excepción en auditoría revierte el INSERT de catálogo y la carga no responde éxito.
Una escritura física puede quedar huérfana si falla catálogo/auditoría: no se expone una referencia
autorizada; no hay limpieza destructiva automática.

Prueba real PostgreSQL comprueba evento, correlación y rollback ante fallo de auditoría.
Las pruebas son aisladas con rollback: **no equivalen a evidencia de auditoría financiera
comprometida y verificada tras reinicio**. No se implementó todavía auditoría transaccional
para confirmación, inicio de conciliación, acciones wizard y errores del circuito financiero.
Operaciones administrativas conservan la auditoría previa del repository de seguridad.

## Validación ejecutada

- `uv run python -m backend.scripts.migrate`: aplicada `002_seg01_files.sql`, privilegios runtime PASS.
- `uv run pytest backend/tests tests -q`: **20 PASS**, 11 warnings preexistentes de inferencia de fechas.
- `uv run pytest backend/tests/test_v2_files.py -q` después de ampliar prueba de canónico: **2 PASS**.
- Pruebas nuevas: autorización propietario/admin, rechazo ajeno/path/UUID inexistente,
  symlink/traversal, hash alterado, reconstrucción de repository, auditoría atómica,
  carga HTTP sintética con UUID permanente y rechazo de manifest cliente.
- Canonicalización real de XLSX contable sintético a parquet y evento SSE con UUID, no path.
- `pnpm build`: **PASS** (Astro 5 del checkout).
- `pnpm check`: **FAIL / comando inexistente**; no se instaló ni simuló un typecheck.
- `uv run --with playwright python -m backend.scripts.verify_http_browser`:
  Chromium anónimo **PASS**, Chromium autenticado **SKIP**, operaciones financieras **NOT_TESTED**.
  Logs de procesos propios: `/tmp/concilia-seg01-5hqrpg5x.log`, `/tmp/concilia-seg01-3vj27h5v.log`.
  El script arrancó y detuvo exclusivamente sus procesos, sin tocar servicios compartidos.
- SHA-256: **588 archivos** inventariados, **0 modificados o faltantes** respecto de
  `seg01_historical_before.json`. El conteo observado no es 587; no se corrigió borrando archivos.
- `git diff --check`: **PASS** en revisión final; diff revisado sin reconstruir cambios previos.
- Repetición de migraciones: `applied: []`, privilegios runtime PASS (idempotencia).
- Revisión de secretos de las adiciones: sin credenciales funcionales ni secretos hardcodeados.
- Las adiciones no incluyen passwords, tokens, DSNs ni claves; no se imprime contenido del
  archivo de credenciales técnicas. Fixtures exclusivamente sintéticos.

## Bloqueos y riesgos residuales

1. No hay `CONCILIA_E2E_ADMIN_EMAIL`/`CONCILIA_E2E_ADMIN_PASSWORD` en el entorno. No se creó
   una credencial persistente perdida ni se usó SQL como bypass del aprovisionamiento seguro.
   Sigue disponible `backend.scripts.create_first_admin` para aprovisionamiento interactivo DEV.
2. Sin E2E financiero autenticado: preview/confirmación/reconcile/resultados/logout conjunto
   y negativas completas por roles no tienen evidencia Chromium.
3. Confirmaciones, wizard y eventos conservan estado en memoria. Falta contrato transaccional
   duradero del resto de las operaciones financieras; no se oculta con auditoría best-effort.
4. Reinicio real **NOT_TESTED**. Reconstruir repository bajo rollback no equivale a reiniciar
   procesos con sesiones/archivos/auditoría comprometidos. No había servidores activos al iniciar;
   los launchers canónicos descritos por AGENTS no existen en este checkout.
5. No se ha cerrado autorización por recurso de topics SSE/runs wizard. La revalidación de
   sesión SSE previa no demuestra aislamiento de recursos entre usuarios.
6. La compatibilidad de parsers de archivos se preserva por resolución backend, pero no se
   considera validada toda la UI financiera o el procesamiento múltiple autenticado.
7. La comprobación de paths/hash presupone almacenamiento controlado por el proceso DEV;
   no aporta aislamiento frente a un atacante local con permiso de escritura concurrente.

## Próximo paso

Completar la auditoría transaccional financiera sobre decisiones persistentes sin reconstruir
seguridad existente; aprovisionar/suministrar credenciales dedicadas DEV por mecanismo seguro;
ejecutar circuito Chromium sintético completo y negativas por roles; verificar después de
reinicio exclusivo de procesos propios los cinco invariantes solicitados. Solo entonces
revisar gates SEG-01. **No avanzar a fases 1–2.**

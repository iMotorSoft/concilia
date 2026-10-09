# Concilia FCE V2 — SEG-01 HTTP DEV, entrega parcial

Rama: `procesamiento-multiple-extractos`. Se conservaron los cambios locales anteriores y el informe `concilia_v2_dev_foundation.md`. Sin commits, push, producción, migraciones ni gestión de PostgreSQL. No se ejecutaron fases 1–2.

```text
CONCILIA_V2_SEG01_HTTP_DEV=FAIL
CONCILIA_V2_SEG01_DEV=FAIL
```

Los FAIL indican que el gate integral aún no está satisfecho. **La protección HTTP central está activada en este checkout DEV, pero la aplicación no está terminada ni aprobada como segura.** El runtime no vuelve al acceso anónimo si falla PostgreSQL.

## Archivos de esta intervención

Modificados, preservando sus cambios anteriores cuando existían:

- `SrvRestAstroLS_v1/ls_iMotorSoft_Srv01.py` — entrypoint real; no se creó `backend/app.py` ni se movió el entrypoint.
- `SrvRestAstroLS_v1/backend/core/config.py` — configuración HTTP DEV y lectura centralizada de credenciales E2E.
- `SrvRestAstroLS_v1/backend/repositories/security.py` — usuarios, revocación, cambio y recuperación de contraseña, auditoría de entidades.
- `SrvRestAstroLS_v1/routes/v1/agui_notify.py` — elimina CORS wildcard del stream.
- `SrvRestAstroLS_v1/clientA/src/components/global.js` — API DEV usa el mismo hostname del navegador para las cookies.
- `SrvRestAstroLS_v1/clientA/src/components/agui/ReconciliarApp.svelte` — transporte autenticado, SSE con credenciales, cierre de streams al desmontar y restricciones visuales CONSULTA.
- `SrvRestAstroLS_v1/clientA/src/components/agui/ReconciliarResumen.svelte` — transporte autenticado.
- `SrvRestAstroLS_v1/clientA/src/components/agui/cards/{AprobadosN1Card,Conciliados11Card,NoBancoCard,NoContableCard,SugeridosN1Card}.svelte` — transporte autenticado.
- `SrvRestAstroLS_v1/clientA/src/pages/reconciliar.astro` — monta la interfaz autenticada.
- `SrvRestAstroLS_v1/docs/status_actual.md` — estado compacto y enlace a esta evidencia.

Nuevos:

- `SrvRestAstroLS_v1/backend/http/security.py`.
- `SrvRestAstroLS_v1/backend/http/session_stream.py`.
- `SrvRestAstroLS_v1/backend/tests/test_v2_http.py`.
- `SrvRestAstroLS_v1/backend/scripts/verify_http_browser.py`.
- `SrvRestAstroLS_v1/clientA/src/components/auth/transport.js`.
- `SrvRestAstroLS_v1/clientA/src/components/auth/AuthenticatedConcilia.svelte`.
- Este informe.

No se modificaron en esta intervención el matcher, parsers, estado financiero ni las migraciones SEG-01 anteriores. El diff contra HEAD incluye trabajo preexistente: no atribuirlo completo a esta entrega.

## Endpoints implementados

| Método | Endpoint | Control |
| --- | --- | --- |
| POST | `/api/auth/login` | Público, origin allowlist, rate limiting PostgreSQL, Argon2id |
| GET | `/api/auth/me` | Sesión válida |
| POST | `/api/auth/logout` | Sesión + CSRF, revocación PostgreSQL |
| POST | `/api/auth/password` | Sesión + CSRF + contraseña actual, revoca sesiones |
| GET | `/api/auth/users` | ADMINISTRADOR |
| POST | `/api/auth/users` | ADMINISTRADOR + CSRF |
| POST | `/api/auth/users/{user_id}/update` | ADMINISTRADOR + CSRF; conserva al último administrador activo |
| POST | `/api/auth/users/{user_id}/revoke` | ADMINISTRADOR + CSRF |
| POST | `/api/auth/users/{user_id}/password-reset` | ADMINISTRADOR + CSRF + reautenticación |
| POST | `/api/auth/password-reset` | Público estrictamente para recuperación; código opaco, expiración y rate limiting |

Recuperación asistida DEV: el administrador reautenticado obtiene un código de un solo uso, con hash persistido y TTL de 15 minutos. Se invalidan códigos anteriores y sesiones del destinatario. El código se entrega por un canal privado verificado, **nunca por URL**. Consumo, actualización de password, revocación y auditoría son transaccionales. No hay envío de email automatizado ni recuperación por enumeración de correos.

Las cookies son host-only, `SameSite=Lax`, sesión `HttpOnly`, TTL 24h. En HTTP loopback DEV no llevan `Secure`; en configuración HTTPS llevan `Secure`. La configuración rechaza orígenes externos a loopback. No es configuración de producción. CORS usa allowlist exacta y credenciales, no wildcard. Todos los POST autenticados, incluso consultas POST, requieren CSRF vinculado a la sesión.

El arranque directo del entrypoint ahora escucha en `127.0.0.1` y deshabilita proxy headers. Si se lanza mediante CLI, usar también `--no-proxy-headers`: el rate limiter no debe confiar en `X-Forwarded-For` del cliente. No se implementó infraestructura de proxy confiable.

## Endpoints protegidos

Los **18 handlers de negocio registrados** se probaron anónimamente por TCP: todos respondieron 401 antes de ejecutar lógica de negocio.

- Uploads: `/api/uploads/bank-movements`, `/api/uploads/v2/ingest`.
- Confirmación: `/api/ingest/confirm`.
- Ejecución: `/api/reconcile/start`.
- Details: `/api/reconcile/details`, `/no-banco`, `/pares`, `/no-contable`, `/n1/grupos`, `/n1/sugeridos` bajo ese prefijo.
- Summary: `/api/reconcile/summary`, `/head`, `/descomposicion` bajo ese prefijo.
- Wizard: `/api/reconcile_wizard/start`, `/api/reconcile_wizard/runs/{run_id}/action`, `/events`.
- SSE de ingest: `/api/ag-ui/notify/stream`.
- Chat: `/api/chat/turn`.

Cada handler necesita una capacidad explícita; los desconocidos se deniegan. OpenAPI público fue deshabilitado; `/schema` respondió 404. El preflight CORS no entrega datos de negocio. Solo login y consumo del código de recuperación son públicos.

SSE revalida la sesión persistente antes de cada chunk: una prueba abre el stream, recibe CONNECTED, revoca la sesión y verifica que un evento posterior no se entrega y el stream termina. La terminación ocurre al siguiente chunk, no mediante polling mientras el stream permanece inactivo.

No hay endpoints de exportación/descarga registrados en este entrypoint: **no se implementó ni validó un nuevo servicio de descarga/exportación autorizado**. Incorporarlos requiere capacidad explícita y resolución de recursos; el guard no concede permisos automáticamente.

## Matriz comprobada por HTTP real

| Caso | Resultado |
| --- | --- |
| Anónimo en los 18 handlers, incluyendo SSE | 401 |
| Login incorrecto | 401 |
| Login correcto, los tres roles; me | 200 |
| CONSULTA intenta upload | 403 |
| OPERADOR intenta administración de usuarios | 403 |
| ADMINISTRADOR lista usuarios | 200 |
| ADMINISTRADOR crea usuario | 201 |
| ADMINISTRADOR actualiza/revoca usuario | 200 |
| Remover último administrador activo | 400 |
| POST summary/head con payload vacío, los tres roles | 400 del handler; no 403 por rol |
| CSRF ausente/incorrecto, origin externo | 403 |
| Paths externos en summary/head | 403 |
| Logout y siguiente me | 200 / 401 |
| Desactivación o revocación y siguiente me | 401 |
| Cambio con contraseña actual incorrecta/correcta | 403 / 200; sesión anterior inválida |
| Recuperación sin reautenticación correcta | 403 |
| Recuperación válida / replay / vencida | 200 / 400 / 400 |
| SSE ya abierto después de revocación | Termina sin entregar el siguiente evento |

**Límite de esta matriz:** uploads de OPERADOR/ADMINISTRADOR alcanzan validación de formulario (400 sin archivo); summary/head alcanza validación de campos (400). Esto demuestra autorización efectiva, **no procesamiento exitoso de archivos ni resultados financieros**. Reversión no tiene endpoint implementado/verificado. La reconstrucción del repository no resucita sesiones revocadas, pero no reemplaza la prueba de reinicio real del proceso.

## Referencias de archivos: inspección y límite pendiente

Antes de modificar la integración se identificó el contrato actual:

- `ReconciliarApp.svelte` toma `canonical_uri || original_uri` de los previews.
- Confirmación envía `original_uri` en multipart, con múltiples valores para extractos.
- Start, summary y las cinco cards details envían `uri_extracto`, `uri_contable`, `uri_sicom` en multipart.
- Wizard envía URIs en JSON; SSE puede actualizar `canonical_uri`.

Se conservaron esos nombres para no sustituir a ciegas todo el circuito. El guard verifica las referencias recibidas: archivo regular existente, path absoluto exacto sin traversal/symlinks, esquema local, dentro de `storage/incoming` o `storage/canonical` y extensión admitida. Se verificó rechazo de `/etc/passwd`, hosts remotos y traversal.

**No está cumplido el punto de IDs internos autorizados.** Todavía se aceptan referencias legacy a archivos existentes dentro del storage permitido; no existe catálogo PostgreSQL nuevo de recursos/IDs, autorización por recurso ni migración de respuestas/SSE a IDs. El control transitorio de roots no debe presentarse como sustituto de ese contrato. Tampoco se comprobó la compatibilidad financiera de manifests multi-extracto ni toda referencia anidada del wizard.

## Pruebas y evidencia reproducible

Desde `SrvRestAstroLS_v1/`:

```bash
uv run pytest backend/tests tests/test_sniff_bank.py tests/reconcile -q
cd clientA && pnpm build
cd ..
uv run --with playwright python -m playwright install chromium
uv run --with playwright python -m backend.scripts.verify_http_browser
```

Resultados finales:

- Backend: **18 passed**, 11 warnings preexistentes de inferencia de fechas.
- Nuevas pruebas HTTP: **3 passed**. Uvicorn monta el entrypoint real sobre un socket TCP loopback; startup abre el pool real. Para aislar datos de prueba se inyecta el repository real sobre una conexión PostgreSQL en transacción rollback. No se mockea SQL, pero no es un worker independiente con cuentas persistentes.
- Build frontend: **PASS**, 4 páginas; warning CSS `@property` preexistente.
- Playwright Chromium con backend y frontend preview reales en 7058/3058: **anónimo PASS**. El login se muestra, no se monta el botón de upload y API/SSE anónimos devuelven 401.
- Playwright autenticado: **SKIP**, faltan `CONCILIA_E2E_ADMIN_EMAIL` y `CONCILIA_E2E_ADMIN_PASSWORD`. Sin credenciales inventadas/defaults. Operación financiera: **NOT_TESTED**.
- `pnpm check`: **FAIL preexistente**, no existe el script. No se añadió uno ficticio ni se declaró typecheck PASS.
- `lat check`: **102 errores**, igual al conteo anterior. Sin cambios en `lat.md/` ni nuevas referencias `@lat`.
- `git diff --check`: **PASS**.
- Secretos técnicos: comparación de los valores locales contra 59 archivos de código/diff/log examinados: **PASS**, sin imprimir valores. La prueba HTTP comprueba que passwords, cookies y códigos de recuperación generados no aparecen en sus logs capturados. No equivale a una auditoría completa de logs legacy de operaciones financieras.

Los procesos del smoke browser son propios, solo loopback, y se detienen por sus process groups; no se gestionó PostgreSQL ni se mataron procesos ajenos. Al cierre no quedaron servidores de esta prueba en 7058/3058.

Se detectaron y corrigieron durante desarrollo dos fallos nuevos: Chromium no estaba instalado para la versión de Playwright usada; y el middleware SSE interpretaba inicialmente una respuesta 401 con content-type SSE como stream autorizado, truncando el body. Se instaló Chromium y se restringió la revalidación a streams 200. La regresión TCP de todos los endpoints y del stream revocado pasa tras la corrección.

## Integridad histórica

No se escribió en `storage/incoming` ni `storage/canonical`; las pruebas HTTP usan formularios sin archivo y rollback de datos SEG. Los conteos al cierre son los del informe anterior: **368 archivos incoming y 220 canonical**.

Inventario SHA-256 al cierre, formato explícito `relative_path + TAB + sha256(file) + LF`, orden lexicográfico:

- incoming: `b68e8ebdc45c6188b381b1131a7a47c93016b02203dc4ebbdee70f4ac8eed066`.
- canonical: `fd0de18da34d38abc7e2f3b8191603a093c270ae52fb99bfd31fa31623c64d94`.

No se capturó un manifest con este mismo formato antes de esta intervención; por tanto **no se declara igualdad criptográfica antes/después** ni se comparan estos digests con los de un algoritmo anterior no especificado. El informe de fundación y los archivos históricos se conservaron, pero esta limitación de evidencia permanece.

## Primer administrador DEV

El procedimiento existente se conserva, sin defaults, sin bypass y con password interactivo fuera de argumentos/logs:

```bash
cd SrvRestAstroLS_v1
uv run python -m backend.scripts.create_first_admin
```

No se ejecutó ni se crearon usuarios persistentes de prueba. Los fixtures HTTP fueron rollback. El operador debe elegir el administrador y proporcionar credenciales E2E desde el entorno para continuar el gate autenticado. El archivo técnico DEV aún contiene secretos owner/app juntos; no se resolvió separación de secretos por proceso para producción.

## Circuito integral y próximo paso

Comprobado por API: login real → sesión SQL → autorización/CSRF → administración/cambio/recuperación → auditoría SQL → logout. Comprobado por Chromium: frontend real → login requerido → API/SSE anónimos denegados.

**No comprobado como un único circuito:** login browser → sesión persistente tras reinicio de backend → upload/confirmación → conciliación → informes/descarga → auditoría de operación → logout. La auditoría financiera legacy no se integró transaccionalmente con el actor SEG. La UI antigua `/concilia` tampoco se migró a la nueva envoltura autenticada, aunque sus endpoints backend sí están protegidos.

Para cerrar ambos gates:

1. Implementar catálogo PostgreSQL/IDs internos y transición segura completa, incluyendo manifests y SSE, sin paths del navegador como autoridad.
2. Completar la UI legacy o definir explícitamente su transición; proporcionar administrador DEV y credenciales E2E.
3. Probar con Chromium autenticado los tres roles, uploads/confirmación/conciliación reales, sesión después de reinicio, recuperación y revocación.
4. Completar auditoría de operaciones y resolución autorizada de exports/descargas que corresponda.
5. Capturar manifests históricos antes/después de la siguiente validación financiera y verificar todos los logs del circuito.

No declarar SEG-01 PASS ni avanzar a persistencia anual o conciliaciones manuales mientras esos puntos permanezcan abiertos.

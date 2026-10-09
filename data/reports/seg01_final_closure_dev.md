# SEG-01 — cierre DEV

Fecha: 2026-10-09. Rama: `procesamiento-multiple-extractos`.
HEAD inicial/final: `701fc910f49e80981b532e100c35413736d22eb8` (sin commits/push).
Los cambios previos del worktree fueron preservados.

## Gates

```
CONCILIA_V2_SEG01_HTTP_DEV=PASS
CONCILIA_V2_SEG01_DEV=PASS
```

Alcance exclusivo DEV, despliegue único actual. No certifica producción, aislamiento multi-tenant ni persistencia anual/manual de fases 1–2.

## Aprovisionamiento y limpieza

Preflight real: PostgreSQL 18.4, `concilia_fce`, inicialmente 0 administradores activos y 0 entradas `seg_files`.
Se agregó una utilidad local explícita de aprovisionamiento de cuentas aleatorias
`ADMINISTRADOR`, `OPERADOR`, `CONSULTA`, con identidad sintética `example.invalid`.
No utiliza cuentas reales, bootstrap existente ni bypass HTTP.
Credenciales aleatorias en directorio temporal fuera del repositorio, modo 0700;
archivo exclusivo 0600. Sin passwords/cookies/traces en evidencia. Directorio eliminado al cerrar.

Última ejecución: 3 cuentas creadas y desactivadas, 4 XLSX/parquets sintéticos retirados.
Verificación final acumulada de las ejecuciones: 18 cuentas de prueba, 0 activas,
0 sesiones sin revocar, 0 archivos de prueba AVAILABLE. Los hashes de contraseña
se reemplazan al desactivar y el trigger PostgreSQL revoca sesiones.
Se retienen las identidades inactivas, referencias REVOKED y auditoría para preservar trazabilidad.
La limpieza usa el rol técnico owner exclusivamente para retirar referencias de estos usuarios;
no amplía privilegios del runtime y comprueba propietario e integridad antes de unlink.

## Auditoría

Tablas utilizadas: `seg_users`, `seg_sessions`, `seg_password_resets`,
`seg_rate_limits`, `seg_files`, `seg_audit_events`. Sin DDL/migraciones nuevas.

- Carga/derivados: catálogo y auditoría existentes en la misma transacción; no se reconstruyó `FileRepository`.
- Administración, sesión, contraseña, revocación y aprovisionamiento: modificación y evento en una transacción PostgreSQL.
- Confirmación de ingesta: `ingest_confirm_temporary`, antes de aplicar estado temporal.
- Conciliación: `reconcile_compute_start/complete/error`, cálculo temporal, no decisión financiera durable.
- Wizard: inicio, inicialización, acciones y fallo de inicialización, con recurso run UUID y etiqueta temporal.
- Derivación fallida y errores/rechazos HTTP: actor cuando está autenticado, recurso, resultado, motivo, UTC y correlation UUID.
- Un error de auditoría no permite reconocer una operación segura como completada; prueba de wizard verifica que no modifica estado ni publica eventos si falla el registro.

El wizard y las confirmaciones siguen en memoria. La auditoría es persistente;
no transforma el estado transitorio en una conciliación financiera persistente.
No hay nuevas escrituras de decisiones anuales ni fallback financiero durable.
Se cerró además acceso cruzado a acciones/eventos de wizard por propietario y
se separaron canales AG-UI por actor autenticado.

## Evidencia reproducible

Desde `SrvRestAstroLS_v1`:

```
uv run pytest backend/tests tests -q
uv run --with playwright python -m backend.scripts.verify_seg01_closure
pnpm -C clientA build
```

Ejecutar tests que escriben en DEV **secuencialmente**, no simultáneamente.
El script comprueba puertos libres, levanta backend real `ls_iMotorSoft_Srv01:app`
y frontend `pnpm dev`, reinicia únicamente sus grupos de procesos y los detiene al finalizar.
No había launchers `backend-dev.sh`/`astro-dev.sh` en este checkout.
No se inició, detuvo, reinició, migró ni reconfiguró PostgreSQL.
Puertos 7058/3058 libres al cierre, como al inicio.

| Validación | Resultado |
| --- | --- |
| Backend + HTTP TCP/PostgreSQL + matcher/parser | 22 PASS, 0 SKIP |
| Chromium anónimo | PASS |
| Login HTTP desde UI, sesión y frontend | PASS |
| XLSX sintéticos y UUIDs permanentes | PASS |
| Preview real de filas por SSE en Chromium | PASS |
| Confirmación + derivados registrados | PASS |
| Conciliación sintética, 1 par esperado | PASS |
| Resumen y detalles reales | PASS |
| Auditoría consultada en PostgreSQL | PASS |
| CONSULTA, OPERADOR y anónimo negativos | PASS |
| Logout + replay de sesión revocada | PASS |
| Reinicio backend/frontend con sesión activa | PASS |
| Sesión revocada sigue rechazada tras reinicio | PASS |
| Usuarios/roles, catálogo y auditoría tras reinicio | PASS |
| Referencias de derivados utilizables tras reinicio | PASS |
| Build frontend | PASS |
| `pnpm check` | NO DISPONIBLE: script ya ausente en package.json inicial |
| `git diff --check` | PASS |
| Secret scan detect-secrets 1.5.0, incluye untracked | PASS tras revisión de 5 falsos positivos |
| SHA-256 históricos | 588/588 intactos |

La prueba autenticada combina login/DOM/SSE con requests reales desde el contexto
Playwright autenticado; no es una prueba exhaustiva de todos los botones de la UI.
No sustituye los endpoints por mocks ni exige sobrevivencia del wizard al reinicio.
Las pruebas unitarias fail-closed son complementarias, no fundamento del gate E2E.

Artefactos: `seg01_closure_runtime.json`, `seg01_closure_pytest.txt`,
`seg01_closure_build.txt`, `seg01_secret_scan.json` en este directorio.
Scan: `detect-secrets scan --all-files`, backend/rutas/frontend src, sin node_modules/pycache/dist.
Los 5 candidatos son: valor de capability en `http/security.py`, texto de informe
`create_first_admin.py`, texto de informe `provision_dev.py`, passphrase sintética
sin usuario en `test_v2_foundation.py`, password incorrecto de prueba negativa en `test_v2_http.py`.
Ninguno contiene una credencial utilizable; no se ocultaron candidatos en la evidencia del scanner.

Durante preparación hubo dos fallos del harness (expectativa del formato de preview
HTTP y saludo SSE), corregidos leyendo el contrato real. Todas sus cuentas fueron retiradas.
Se reprodujeron interferencias de tests por rate-limit compartido y por administrador
temporal simultáneo: fixture transaccional aísla el bucket con rollback, E2E respeta
el limiter real esperando su ventana cuando corresponde y la regresión final fue secuencial.
La terminación SSE por revocación maneja también ExceptionGroup de AnyIO.

## Archivos de esta intervención

Bajo `SrvRestAstroLS_v1/`:

- `backend/http/audit.py` (nuevo)
- `backend/http/security.py`
- `backend/http/session_stream.py`
- `backend/repositories/security.py`
- `backend/repositories/dev_validation.py` (nuevo)
- `backend/scripts/verify_seg01_closure.py` (nuevo)
- `backend/tests/test_v2_closure.py` (nuevo)
- `backend/tests/test_v2_http.py`
- `routes/v1/agui_notify.py`
- `routes/v1/ingest_confirm.py`
- `routes/v1/reconcile_start.py`
- `routes/v1/reconcile_wizard_start.py`
- `routes/v1/run_action.py`
- `services/wizard_runtime.py`
- `docs/status_actual.md`

Más este informe y los cuatro artefactos de validación. No se modificó `lat.md/`
ni referencias `@lat`; `lat check` no aplica a esta intervención.

## Riesgos y próximo paso

Sin nueva regresión crítica detectada en el alcance probado. Permanecen warnings
preexistentes de inferencia de fechas y CSS `@property`, y ausencia previa de script
de typecheck. PostgreSQL conserva auditoría append-only y registros sintéticos
retirados deliberadamente; no son datos financieros históricos.

La persistencia anual y las decisiones manuales durables quedan fuera de SEG-01.
Próximo paso: revisión del cierre y planificación de fases 1–2; no se implementaron aquí.

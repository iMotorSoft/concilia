# Status Actual - Concilia Runtime

Fecha: 2026-07-16
Proyecto: `SrvRestAstroLS_v1`
Tema activo: `SICOM` en uploads + estabilidad del wizard de conciliación

## SEG-01 HTTP DEV — cerrado en DEV (2026-10-09)

El entrypoint real `SrvRestAstroLS_v1/ls_iMotorSoft_Srv01.py:app` integra sesiones PostgreSQL,
guard central deny-by-default, CSRF, roles y autenticación frontend en `/reconciliar`.
Todas las rutas de negocio montadas rechazan HTTP anónimo; SSE revalida la sesión por evento.
Login/logout/me, usuarios, cambio y recuperación asistida de contraseña tienen pruebas HTTP reales.

`CONCILIA_V2_SEG01_HTTP_DEV=PASS` y `CONCILIA_V2_SEG01_DEV=PASS` para el despliegue DEV actual.
`seg_files` conserva UUIDs permanentes, autorización e integridad SHA-256; carga/derivación
y su auditoría comparten transacción. Los 588 históricos permanecen intactos y no se registraron.

Auditoría integrada en confirmación temporal, cálculo, wizard, administración y rechazos/errores.
Confirmaciones y wizard siguen **en memoria**, sin decisiones financieras durables ni modelo anual.
Chromium autenticado/anónimo y reinicio real backend/frontend PASS; 22 tests PASS; build PASS.
Usuarios sintéticos aprovisionados localmente, desactivados y sesiones revocadas; artefactos retirados.
No existe script `pnpm check` en este checkout (limitación previa). No se implementaron fases 1–2.

Evidencia vigente y alcance: `data/reports/seg01_final_closure_dev.md`.
Evidencia anterior: `data/reports/concilia_v2_seg01_http_dev.md` y
`data/reports/seg01_closure_files_dev.md`.

## Estado funcional confirmado

Quedo confirmado lo siguiente:

- la conciliación base sigue siendo `extracto bancario vs contable (PILAGA)`;
- `SICOM` entra como fuente auxiliar opcional;
- el banco no es fijo del producto; lo define cada cliente;
- `Patagonia` se uso solo como caso de ejemplo y validación;
- `SICOM` del mes viene como `1 workbook mensual` con días en solapas internas;
- la relación `Order de P. / OP <-> Nro Pago` es crítica para trazabilidad, pero no es `1 a 1`;
- `OP` sirve como eje operativo/manual;
- `Nro Pago` sirve como clave de lote bancario;
- el cruce por banco debe resolverse por caso/cliente, no hardcodeado en producto.

## Implementado y validado

### Fase 1 SICOM (cerrada 2026-04-23)

- upload/preview/confirmación `SICOM` con `role=sicom`;
- parser consolida workbook mensual multi-solapa;
- preview expone: rows, sheet_count, period_from/to, bancos detectados, op_count, nro_pago_count, resumen `OP <-> Nro Pago`;
- parquet canónico `SICOM` + persistencia `files.sicom` en estado de ingest;
- UI card propia preview/confirmación `SICOM`;
- parser corregido para encabezados `Nº Pago`.

### Validación objetivo final (2026-04-29)

3 casos reales validados end-to-end:

| Caso | Extracto | PILAGA | SICOM | Filas PILAGA c/banco | Egresos PILAGA trazados | Lotes banco c/soporte |
|------|----------|--------|-------|---------------------|------------------------|----------------------|
| Nov + Base.xlsx | 11-Nov... | salida(261) | Base.xlsx | 18 | $40.570.180 | 7 |
| Nov + SICON CRUDO | 11-Nov... | salida(261) | SICON CRUDO... | 213 | $851.051.646 | 47 |
| Mar 2026 | 2026_03... | 2026_03... | 2026_03_SICON... | 255 | $1.401.569.967 | 67 |

### Regla mandatoria SICOM Nro Pago + OP (2026-05-05)

Cuando hay `SICOM` cargado, un agrupamiento aprobado `N PILAGA -> 1 extracto` **no puede depender solo de suma exacta**:

- debe existir lote SICOM que matchee movimiento bancario por `Fecha de Pago + Imp.Neto`;
- el `Nro Pago` de ese lote manda;
- componentes PILAGA deben corresponder a las `OP` de ese mismo `Nro Pago`;
- si OP aparece con `0 match(es)` SICOM, no puede formar agrupado aprobado;
- si misma OP aparece en >1 `Nro Pago`, UI muestra solo lote del grupo seleccionado.

Implementación:
- `routes/v1/reconcile_details.py`: crea grupos SICOM mandatorios antes de fallback N->1;
- restringe OP y contexto visible al `Nro Pago` del grupo;
- reclasifica N->1 sin soporte SICOM como auditoría cuando existe `uri_sicom`;
- no los cuenta como aprobados ni los consume como conciliados.

### Decisión Pat.Otros como Patagonia (2026-04-30)

- `Banco Pat.Otros` considerado parte del universo `Patagonia` para análisis SICOM;
- mejora trazabilidad `PILAGA -> SICOM`;
- no cambia cierre efectivo contra extracto (esos lotes no matchean directo por `fecha + importe`);
- implementado: `routes/v1/reconcile_start.py` resuelve `patagonia -> {banco_patagonia, banco_pat_otros}`;
- validado e2e: UI muestra `Banco Pat.Otros, Banco Patagonia` como bancos en scope.

### Wizard runtime fallback (2026-04-20)

- `services/wizard_runtime.py`: store en memoria para runs, events, snapshots;
- `reconcile_wizard/start` cae a memoria si falla crear run en DB (`workflow_ai_v1` no existe);
- SSE y `run_action` sirven desde memoria para runs fallback;
- objetivo: no bloquear pruebas funcionales por DB del core.

## Servicios al cerrar (2026-05-06)

- backend: `uv run python ls_iMotorSoft_Srv01.py` en `:7058`;
- frontend estable: `uv run pnpm preview --port 3058 --host 127.0.0.1` en `:3058`;
- URL manual: `http://127.0.0.1:3058/reconciliar`.

## Validación técnica

- `pnpm -C clientA build` OK;
- Playwright mínimo contra `:3058`: botón `Subir extracto` visible, click abre `dialog[open]`, sin errores consola;
- e2e real con 3 casos: `SUMMARY {"ok": true, "total": 3, "passed": 3}`.

## Archivos de referencia canónica

- `lat.md/lat.md` - arquitectura viva;
- `lat.md/status_actual.md` - arquitectura estado actual;
- `docs/adr/` - decisiones arquitectónicas;
- `data/reports/` - evidencia generada.

## Próximo paso sugerido

Consolidar salida final unificada: `1 a 1` real + `N PILAGA -> 1 extracto` explicado por `SICOM` + sugeridos para revisión + PILAGA sin extracto + extracto sin PILAGA + OP/lote visibles en cada grupo.
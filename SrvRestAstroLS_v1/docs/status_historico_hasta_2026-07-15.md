# Status Actual - Concilia (Histórico completo hasta 2026-07-15)

Este archivo congela la historia técnica acumulada del runtime Concilia. No se modifica hacia adelante.

---

## Actualización 2026-05-06 frontend wizard + e2e real OK

Se cerró una pasada de estabilidad de frontend y validación end-to-end con datos reales.

**Cambios de UI/producto:**

- se agregó margen inferior al botón `Abrir asistente de conciliación`;
- el wizard dejó de mostrar eventos técnicos visibles como `FORM_SNAPSHOT`, `CONFIRMATION_REQUIRED` y `LIST_SNAPSHOT`;
- la confirmación del alcance ahora se muestra como advertencia operativa:
  - `Continuar igual`;
  - `Ajustar alcance`;
- la ventana máxima detectada se muestra con tarjetas separadas para `Extracto` y `Contable`;
- los importes del wizard se formatean como moneda ARS;
- si el documento viene vacío, ya no se muestra `doc ,`;
- los meses `ok` se muestran como `Completo`;
- si hay un solo mes seleccionable, queda preseleccionado;
- el resumen del wizard cambió `Archivos: 1` por `Extracto: 1 archivo`.

**Limpieza de frontend heredado:**

- se eliminaron referencias a `judaismoenvivo.com`, cursos, certificados, `ViewCourse`, `Course`, `Universo Interior`, `Aryeh Kaplan` y tracking heredado;
- `Layout.astro` quedó con metadata de `Concilia FCE`;
- `astro.config.mjs` usa `https://fce.concilia.imotorsoft.com`;
- `global.js` quedó con título/descripción de Concilia y sin comentarios del proyecto anterior.

**Corrección de hidratación/ejecución:**

- se removieron `$effect` que abrían/cerraban dialogs y rompían hidratación en dev;
- los dialogs pasaron a control declarativo con `open={...}`;
- los botones rápidos `Subir extracto`, `Subir contable` y `Subir SICOM` abren el formulario localmente y conectan SSE al usarse;
- se corrigieron marcas Svelte ambiguas:
  - `textarea` autocerrado;
  - `span` autocerrados;
  - `client:load` dentro de componente `.svelte`;
- para pruebas manuales queda recomendado servir el build estable con `astro preview`, no `astro dev`, porque `astro dev` mostró un problema de hidratación del renderer Svelte/Vite aunque el build de producción hidrata OK.

**Servicios al cerrar:**

- backend: `uv run python ls_iMotorSoft_Srv01.py` en `:7058`;
- frontend estable: `uv run pnpm preview --port 3058 --host 127.0.0.1` en `:3058`;
- URL manual: `http://127.0.0.1:3058/reconciliar`.

**Validación técnica:**

- `pnpm -C clientA build` OK;
- verificación Playwright mínima contra `:3058`:
  - botón `Subir extracto` visible;
  - click abre `dialog[open]`;
  - sin errores de consola.

**Validación e2e real:**

- script: `scripts/e2e_sicom_real_playwright.py`;
- se agregó soporte `E2E_BASE_URL` para poder correr contra `astro preview`;
- se actualizó el script para aceptar `Continuar igual` además de `Confirmar selección`;
- comando final corrido contra `http://127.0.0.1:3058/reconciliar`:
  - `uv run --with playwright python scripts/e2e_sicom_real_playwright.py`;
- resultado:
  - `SUMMARY {"ok": true, "total": 3, "passed": 3}`.

**Casos reales validados:**

1. Noviembre + `Base.xlsx`
   - extracto: `11- Noviembre al 30.xlsx`;
   - PILAGA: `salida(261).xlsx`;
   - SICOM: `Base.xlsx`;
   - filas PILAGA con banco: `18`;
   - egresos PILAGA trazados: `$40.570.180,00`;
   - lotes banco con soporte contable: `7`;
   - endpoints principales respondieron `200`.

2. Noviembre + `SICON CRUDO noviembre 2025.xlsx`
   - extracto: `11- Noviembre al 30.xlsx`;
   - PILAGA: `salida(261).xlsx`;
   - SICOM: `SICON CRUDO noviembre 2025.xlsx`;
   - filas PILAGA con banco: `213`;
   - egresos PILAGA trazados: `$851.051.646,30`;
   - lotes banco con soporte contable: `47`;
   - endpoints principales respondieron `200`.

3. Marzo 2026
   - extracto: `2026_03-EXTRACTO.xlsx`;
   - PILAGA: `2026_03-PILAGA.xlsx`;
   - SICOM: `2026_03_SICON MARZO CRUDO.xlsx`;
   - filas PILAGA con banco: `255`;
   - egresos PILAGA trazados: `$1.401.569.967,23`;
   - lotes banco con soporte contable: `67`;
   - endpoints principales respondieron `200`.

**Archivos tocados en este bloque:**

- `clientA/src/components/agui/ReconciliarApp.svelte`;
- `clientA/src/pages/reconciliar.astro`;
- `clientA/src/layouts/Layout.astro`;
- `clientA/src/components/global.js`;
- `clientA/astro.config.mjs`;
- `scripts/e2e_sicom_real_playwright.py`.

---

## Actualización 2026-05-05 regla mandatoria SICOM Nro Pago + OP

Se cerró una regla funcional crítica descubierta validando noviembre 2025 con `Base.xlsx` como SICOM.

**Decisión:**

- cuando hay `SICOM` cargado, una agrupación aprobada `N PILAGA -> 1 extracto` no puede depender solo de que la suma de importes sea exacta;
- debe existir un lote SICOM que matchee el movimiento bancario por `Fecha de Pago + Imp.Neto`;
- el `Nro Pago` de ese lote manda;
- las componentes PILAGA deben corresponder a las `OP / Order de P.` de ese mismo `Nro Pago`;
- si una OP aparece con `0 match(es)` SICOM, no puede formar parte de un agrupado SICOM aprobado;
- si una misma OP aparece en más de un `Nro Pago`, la interfaz del grupo debe mostrar solo el lote del grupo seleccionado.

**Caso falso corregido:**

- banco: `2025-11-26 -$3.100.000,00`;
- PILAGA: `9445/2025`, `9956/2025`, `9620/2025`, `9938/2025`;
- esas OP existen en PILAGA pero no existen en `Base.xlsx`;
- no hay lote SICOM para esa fecha/importe;
- antes entraban por fallback N->1 de suma exacta;
- ahora no aparecen como agrupado aprobado.

**Caso válido confirmado:**

- `Nro Pago 33436`;
- banco/SICOM: `-$21.110.000,00`;
- OP correctas: `8902/2025`, `8906/2025`, `8907/2025`, `8908/2025`;
- PILAGA: `-$22.110.000,00`;
- diferencia visible: `-$1.000.000,00`;
- la diferencia queda expuesta, pero la asignación por `Nro Pago + OP` es correcta.

**Validación UI con Playwright:**

- extracto: `11- Noviembre al 30.xlsx`;
- PILAGA: `salida(261).xlsx`;
- SICOM: `Base.xlsx`;
- tarjeta `Agrupaciones contables -> banco`:
  - `7 grupos`;
  - todos los grupos son `sicom_lote`;
  - cero componentes con `0 match(es)`;
  - cero componentes con lote distinto al `Nro Pago` del grupo;
  - el grupo falso de `$3.100.000,00` no aparece.
- tarjeta `Agrupaciones sugeridas / auditoría`:
  - `8 sugeridos`;
  - todos quedan visibles como casos auditables;
  - el caso `$3.100.000,00` aparece con `9445/2025`, `9956/2025`, `9620/2025`, `9938/2025`;
  - motivo visible: `sin lote SICOM para fecha + importe del banco; OP sin SICOM: ...`;
  - los grupos auditables no consumen filas como conciliadas.

**Implementación relacionada:**

- `routes/v1/reconcile_details.py`
  - crea grupos SICOM mandatorios antes del fallback N->1;
  - restringe OP y contexto visible al `Nro Pago` del grupo;
  - reclasifica N->1 libres sin soporte SICOM como auditoría cuando existe `uri_sicom`;
  - no los cuenta como aprobados ni los consume como conciliados.
- `clientA/src/components/agui/cards/AprobadosN1Card.svelte`
  - muestra `Banco Patagonia · lote <Nro Pago>`;
  - muestra `OP · lote <Nro Pago>`.
- `clientA/src/components/agui/cards/SugeridosN1Card.svelte`
  - muestra casos `sicom_auditoria`;
  - conserva los `0 match(es)` para revisión.

**Documento nuevo:**

- `docs/regla_sicom_nro_pago_op_2026-05-05.md`

---

## Actualización 2026-04-30 decisión Pat.Otros como Patagonia

Se validó con los 3 casos reales ya usados en e2e qué pasaría si `Banco Pat.Otros` se considera parte del universo `Patagonia`.

**Casos revisados:**

1. Noviembre + `Base.xlsx`
   - scope SICOM pasa de `19` a `24` filas y de `7` a `9` lotes;
   - `SICOM -> extracto` queda igual: `7` lotes por `$48.570.180,00`;
   - `PILAGA -> SICOM` sube de `18` a `22` filas y de `$40.570.180,00` a `$42.140.180,00`;
   - cierre final queda igual: `18` filas por `$40.570.180,00`.

2. Noviembre + `SICON CRUDO noviembre 2025.xlsx`
   - scope SICOM pasa de `404` a `484` filas y de `79` a `105` lotes;
   - `SICOM -> extracto` queda igual: `77` lotes por `$1.874.529.108,48`;
   - `PILAGA -> SICOM` sube de `220` a `282` filas y de `$903.162.938,30` a `$968.860.037,30`;
   - cierre final queda igual: `213` filas por `$851.051.646,30`.

3. Marzo 2026
   - scope SICOM pasa de `327` a `371` filas y de `87` a `112` lotes;
   - `SICOM -> extracto` queda igual: `77` lotes por `$1.913.465.547,23`;
   - `PILAGA -> SICOM` sube de `280` a `309` filas y de `$1.679.865.594,08` a `$1.730.652.984,17`;
   - cierre final queda igual: `255` filas por `$1.401.569.967,23`.

**Decisión funcional:**

- `Banco Pat.Otros` debe considerarse parte del universo `Patagonia` para el análisis SICOM;
- esto mejora la trazabilidad operativa `PILAGA -> SICOM`;
- no cambia el cierre efectivo contra extracto con los datos actuales, porque esos lotes no matchean directo por `fecha + importe`;
- la implementación pendiente es ajustar el mapeo de scope para que `patagonia` incluya `banco_patagonia` y `banco_pat_otros`.

**Documento actualizado:**

- `docs/analisis_pat_otros_patagonia_2026-04-30.md`

**Implementación cerrada:**

- se ajustó `routes/v1/reconcile_start.py` para resolver `patagonia -> {banco_patagonia, banco_pat_otros}`;
- se endureció `scripts/e2e_sicom_real_playwright.py` para validar números visibles en la UI, no solo render/endpoints;
- Playwright e2e con los 3 casos reales terminó OK:
  - `SUMMARY {"ok": true, "total": 3, "passed": 3}`;
  - la página mostró `Banco Pat.Otros, Banco Patagonia` como bancos en scope;
  - los números visibles coincidieron con el análisis para filas/lotes SICOM, `SICOM -> extracto`, `PILAGA -> SICOM` y cierre efectivo.

---

## Actualización 2026-04-29 e2e SICOM real

Se cerró una validación end-to-end con Playwright levantando backend y frontend locales.

**Servicios usados:**

- backend: `uv run python ls_iMotorSoft_Srv01.py` en `:7058`;
- frontend: `uv run pnpm dev --port 3058 --host 127.0.0.1` en `:3058`;
- ruta UI: `/reconciliar`.

**Se agregó script reproducible:**

- `scripts/e2e_sicom_real_playwright.py`

**Flujo validado por cada prueba:**

- upload por UI de extracto, PILAGA y `SICOM`;
- confirmación/canonicalización de los 3 insumos;
- apertura del wizard;
- avance del wizard hasta confirmación final;
- `POST /api/reconcile/start`;
- render del sumario;
- render de `Cierre efectivo via SICOM`.

**Resultado general:**

- `SUMMARY {"ok": true, "total": 3, "passed": 3}`;
- endpoints principales observados en `200`:
  - `/api/uploads/v2/ingest`;
  - `/api/ingest/confirm`;
  - `/api/reconcile_wizard/start`;
  - `/api/reconcile_wizard/runs/{run_id}/events`;
  - `/api/reconcile_wizard/runs/{run_id}/action`;
  - `/api/reconcile/start`;
  - `/api/reconcile/summary/head`;
  - `/api/reconcile/summary/descomposicion`.

**Pruebas reales validadas:**

1. Noviembre + `Base.xlsx`
   - extracto: `11- Noviembre al 30.xlsx`
   - PILAGA: `salida(261).xlsx`
   - SICOM: `Base.xlsx`
   - resultado UI:
     - filas PILAGA con banco: `18`
     - OP únicas: `18`
     - importe contable conciliado: `$40.570.180,00`
     - lotes banco con soporte contable: `7`
     - banco final observado: `Banco Patagonia`

2. Noviembre + `SICON CRUDO noviembre 2025.xlsx`
   - extracto: `11- Noviembre al 30.xlsx`
   - PILAGA: `salida(261).xlsx`
   - SICOM: `SICON CRUDO noviembre 2025.xlsx`
   - resultado UI:
     - filas PILAGA con banco: `213`
     - OP únicas: `203`
     - importe contable conciliado: `$851.051.646,30`
     - lotes banco con soporte contable: `47`
     - banco final observado: `Banco Patagonia`

3. Marzo 2026
   - extracto: `2026_03-EXTRACTO.xlsx`
   - PILAGA: `2026_03-PILAGA.xlsx`
   - SICOM: `2026_03_SICON MARZO CRUDO.xlsx`
   - resultado UI:
     - filas PILAGA con banco: `255`
     - OP únicas: `253`
     - importe contable conciliado: `$1.401.569.967,23`
     - lotes banco con soporte contable: `67`
     - banco final observado: `Banco Patagonia`

**Estado al cerrar:**

- backend apagado;
- frontend apagado;
- validación e2e real de las 3 combinaciones: cerrada OK.

---

## Actualización 2026-04-29 validación objetivo final Concilia

Se hizo una validación adicional enfocada en el objetivo contable real:

- conciliar `PILAGA` contra extracto bancario;
- usar `SICOM` como apoyo para agrupados/lotes;
- verificar directos `1 a 1`, agrupados, sugeridos, no conciliados y trazabilidad de `OP`.

**Se agregó script reproducible:**

- `scripts/validate_concilia_final_objective.py`

**Resultado observado:**

- el flujo e2e funciona, pero la validación de objetivo final muestra que hoy hay dos lecturas separadas:
  - pipeline base `PILAGA <-> extracto`:
    - directos `1 a 1`;
    - agrupados aprobados `N PILAGA -> 1 extracto`;
    - sugeridos;
    - sobrantes;
  - cierre efectivo via `SICOM`:
    - `PILAGA -> SICOM -> extracto`;
    - OP únicas;
    - lotes de extracto con soporte contable.

**Números del pipeline base:**

1. Noviembre + `Base.xlsx`
   - directos `1 a 1`: `70`
   - agrupados aprobados: `10` grupos, `34` filas PILAGA, `10` movimientos extracto
   - sugeridos: `0`
   - PILAGA sin extracto después del pipeline: `884`
   - extracto sin PILAGA después del pipeline: `158`
   - OP en agrupados aprobados: `34 / 34`
   - agrupados aprobados con match OP en SICOM: `0 / 34`
   - movimientos extracto agrupados con lote SICOM: `4 / 10`
   - cierre SICOM efectivo: `18` filas PILAGA, `18` OP únicas, `7` lotes extracto

2. Noviembre + `SICON CRUDO noviembre 2025.xlsx`
   - directos `1 a 1`: `70`
   - agrupados aprobados: `10` grupos, `34` filas PILAGA, `10` movimientos extracto
   - sugeridos: `0`
   - PILAGA sin extracto después del pipeline: `884`
   - extracto sin PILAGA después del pipeline: `158`
   - OP en agrupados aprobados: `34 / 34`
   - agrupados aprobados con match OP en SICOM: `3 / 34`
   - agrupados aprobados con match exacto OP+importe en SICOM: `2 / 34`
   - movimientos extracto agrupados con lote SICOM: `6 / 10`
   - cierre SICOM efectivo: `213` filas PILAGA, `203` OP únicas, `47` lotes extracto

3. Marzo 2026
   - directos `1 a 1`: `90`
   - agrupados aprobados: `17` grupos, `45` filas PILAGA, `17` movimientos extracto
   - sugeridos: `0`
   - PILAGA sin extracto después del pipeline: `617`
   - extracto sin PILAGA después del pipeline: `199`
   - OP en agrupados aprobados: `45 / 45`
   - agrupados aprobados con match OP en SICOM: `14 / 45`
   - agrupados aprobados con match exacto OP+importe en SICOM: `12 / 45`
   - movimientos extracto agrupados con lote SICOM: `6 / 17`
   - cierre SICOM efectivo: `255` filas PILAGA, `253` OP únicas, `67` lotes extracto

**Conclusión técnica:**

- las `OP` quedan indicadas en los agrupados aprobados del pipeline base;
- la card de cierre via `SICOM` muestra una cobertura contable mayor que la partición base;
- todavía falta consolidar ambos mundos en una salida final única:
  - `1 a 1` real;
  - `N PILAGA -> 1 extracto` explicado por `SICOM`;
  - sugeridos para revisión;
  - PILAGA sin extracto;
  - extracto sin PILAGA;
  - OP/lote visibles en cada grupo.

Por lo tanto, no conviene dar por cerrado el objetivo final de producto hasta implementar/validar esa partición final unificada.

---

## Actualización 2026-04-29 corrección etiqueta importe SICOM

Se revisó el valor observado en marzo:

- UI mostraba: `$1.401.569.967,23` como `Importe contable conciliado`;
- el diagnóstico confirmó que ese valor sale de las `255` OP de PILAGA trazadas via `SICOM` y con lote en extracto;
- no es saldo neto contable;
- es suma bruta de egresos PILAGA trazados (`egreso_bruto`) y coincide con `SICOM.imp_neto` por `OP + importe`.

**Datos de control marzo:**

- PILAGA neto del mes: `-438.280.513,55`;
- PILAGA egresos brutos totales: `$3.525.371.507,10`;
- OP trazadas con extracto via SICOM: `$1.401.569.967,23`;
- extracto neto del mes: `-180.159.405,78`.

**Cambio aplicado:**

- `clientA/src/components/agui/ReconciliarResumen.svelte`
- `clientA/src/components/agui/cards/CierreEfectivoSicomCard.svelte`

**Etiqueta nueva:**

- `Egresos PILAGA trazados`;
- descripción: `Importe bruto, no saldo neto`.

**Validación:**

- `pnpm -C clientA build` OK.

---

## Actualización 2026-04-29 validación Base noviembre humana

Se validó el caso `Base.xlsx` como recorte humano del SICOM crudo mensual.

**Resultado confirmado:**

- `Base.xlsx`: `25` filas;
- `SICON CRUDO noviembre 2025.xlsx`, día `03/11/2025`: `25` filas;
- fecha única: `2025-11-03`;
- misma distribución por banco:
  - `Banco Patagonia`: `19` filas, `7` lotes, `$48.570.180,00` por `Imp.Neto`;
  - `Banco Pat.Otros`: `5` filas, `2` lotes, `$2.570.000,00` por `Imp.Neto`;
  - `Banco Santander`: `1` fila, `1` lote, `$700.000,00` por `Imp.Neto`.

**Contra extracto Patagonia:**

- solo `Banco Patagonia`: `7 / 7` lotes, `$48.570.180,00`;
- `Banco Patagonia + Pat.Otros`: `7 / 9` lotes, mismo importe conciliado;
- todos los bancos: `7 / 10` lotes, mismo importe conciliado.

**Regla reforzada:**

- el extracto define el scope bancario real;
- para extracto Patagonia, el cierre efectivo se hace con `Banco Patagonia`;
- `Banco Pat.Otros` no se suma automáticamente al cierre bancario;
- `SICOM` se agrupa por `Fecha de Pago + Banco + Nro Pago`;
- el importe correcto contra extracto es `Imp.Neto`, no `Importe`;
- el match auditado es por `fecha + importe`;
- bancos `Otros` quedan como trazabilidad auxiliar salvo evidencia explícita en extracto.

**Documento actualizado:**

- `docs/analisis_sicom_noviembre_bank_scope_2026-04-19.md`

---

## Uso de este archivo

Este archivo queda como referencia canónica de continuidad.

**Reglas:**

- actualizarlo al cerrar cada bloque relevante;
- leerlo antes de retomar;
- dejar aquí solo estado operativo real del proyecto.

---

## Actualización 2026-04-21

Se cerró el cambio del wizard para sacar la llamada real a Postgres.

**Estado nuevo confirmado:**

- `reconcile_wizard/start` ya no intenta `core_connect_db`;
- el wizard ya no usa `core_runs/core_events`;
- `start`, `events` y `run_action` quedaron en memoria como camino único;
- `reconcile_start` también quedó desacoplado de `core_*` y ya no intenta Postgres;
- `days_window` se sacó del wizard;
- la tolerancia en días queda solo en el motor de conciliación y en la UI de resultados;
- se endureció `services/wizard_runtime.py` con copias profundas para evitar aliasing de estado/eventos;
- validado por HTTP:
  - `POST /api/reconcile_wizard/start` responde `200`;
  - `GET /api/reconcile_wizard/runs/{run_id}/events` entrega eventos;
  - `POST /api/reconcile_wizard/runs/{run_id}/action` responde `200`;
- validado en proceso:
  - `POST /api/reconcile/start` responde `200` con summary;
- validado además con Playwright usando archivos reales:
  - extracto
  - contable
  - `SICOM`
  - apertura del wizard hasta `Paso 1/3`.

**Conclusión operativa:**

- la dependencia del wizard y del inicio real de conciliación a Postgres queda removida por decisión de código, no solo mitigada por fallback.
- el wizard queda enfocado en alcance/cobertura; la tolerancia en días deja de configurarse antes de iniciar.

---

## Actualización 2026-04-21 bis

Se cerró la integración real de `SICOM` en el flujo de resultados.

**Estado nuevo confirmado:**

- `reconcile/start` ya acepta `uri_sicom`, `bank_scope` y `account_scope`;
- `reconcile/summary`, `summary/head` y `summary/descomposicion` ya aceptan y procesan `uri_sicom`;
- el frontend ya envía `SICOM` confirmado al iniciar conciliación y al pedir sumario;
- el resumen ya muestra un bloque `SICOM` con:
  - scope aplicado;
  - filas incluidas/excluidas por banco;
  - cobertura `SICOM -> extracto` por lote;
  - cobertura `PILAGA -> SICOM` por `OP + importe`;
- el filtrado de `SICOM` ya respeta el relevamiento:
  - para extracto `Patagonia` se toma solo `Banco Patagonia`;
  - `Banco Pat.Otros` y otros bancos quedan fuera del scope del caso.

**Validación cerrada con archivos reales:**

- extracto: `11- Noviembre al 30.xlsx`
- contable: `salida(261).xlsx`
- sicom: `Base.xlsx`

**Resultado confirmado por endpoint:**

- `POST /api/reconcile/summary/head` responde `200` y devuelve `summary.sicom`;
- `POST /api/reconcile/start` responde `200` y devuelve `summary.sicom`;
- con `Base.xlsx` y scope `patagonia`:
  - `rows_scoped`: `19 / 25`
  - `lote_count_scoped`: `7`
  - `extracto_coverage.matched_lotes`: `7 / 7`
  - `pilaga_coverage.matched_rows`: `18`

---

## Actualización 2026-04-21 cards

Se cerró el ajuste de los cards para que no queden ciegos a `SICOM`.

**Estado confirmado:**

- `reconcile_details` ya acepta `uri_sicom`, `bank_scope` y `account_scope`;
- los endpoints de cards ahora enriquecen filas con trazabilidad `SICOM`:
  - banco -> lote `nro_pago`;
  - PILAGA -> `OP` y matches en `SICOM`;
- el frontend ya envía `SICOM` también a:
  - `no-banco`
  - `no-contable`
  - `pares`
  - `n1/grupos`
  - `n1/sugeridos`
- los cards renderizan etiquetas `SICOM` cuando hay match o contexto operativo.

**Validación cerrada:**

- `python3 -m py_compile routes/v1/reconcile_details.py`
- `pnpm -C clientA build`
- `POST /api/reconcile/details/no-banco` responde `200` con `rows[].sicom`
- `POST /api/reconcile/details/pares` responde `200` con `rows[].sicom_bank / rows[].sicom_pilaga`

---

## Actualización 2026-04-23 marzo Patagonia

Se cerró la validación contable real de marzo 2026 para el caso `Patagonia`.

**Estado confirmado:**

- el objetivo correcto queda fijado como `contable <-> extracto`, usando `SICOM` solo como puente auxiliar de trazabilidad y explicación de lotes;
- el extracto de marzo detecta `Banco Patagonia` con cuenta `100-393300535-000` y define el scope efectivo del caso;
- `2026_03_SICON MARZO CRUDO.xlsx` vino mezclado con otros bancos, pero eso no altera el cierre bancario porque el extracto sigue mandando el scope;
- se corrigió la normalización de `OP` entre `PILAGA` y `SICOM` para compatibilizar formatos `1261/2026` vs `1261`;
- el fix quedó aplicado en:
  - `routes/v1/reconcile_start.py`
  - `routes/v1/reconcile_details.py`

**Resultado operativo validado:**

- `SICOM Patagonia -> extracto`:
  - `77 / 87` lotes conciliados;
  - `$1.913.465.547,23` conciliados por lote;
- `PILAGA -> SICOM Patagonia`:
  - `280` filas;
  - `277` `OP` únicas;
  - `$1.679.865.594,08` trazados;
- resultado final `PILAGA -> SICOM -> extracto`:
  - `255` filas `PILAGA`;
  - `253` `OP` únicas;
  - `$1.401.569.967,23` conciliados efectivamente contra extracto.

**Hipótesis validada:**

- sumar `Banco Pat.Otros` mejora trazabilidad `PILAGA -> SICOM`;
- no mejora la conciliación final contra extracto;
- por lo tanto, `Pat.Otros` puede servir como explicación operativa, pero no cambia el cierre bancario final del caso marzo.

**Documento de base nuevo:**

- `docs/analisis_conciliacion_marzo_2026_patagonia.md`

---

## Actualización 2026-04-23 frontend + e2e

Se cerró el ajuste de producto para que frontend y backend reflejen la lógica contable validada, no solo la lógica técnica del matcher.

**Estado confirmado:**

- el resumen ahora separa explícitamente:
  - `SICOM -> extracto`;
  - `PILAGA -> SICOM`;
  - cierre efectivo `PILAGA -> SICOM -> extracto`;
- se agregó una card nueva de trabajo diario:
  - `Cierre efectivo via SICOM`;
- las cards de detalle ahora muestran `OP` de forma explícita en:
  - `coincidencias directas 1->1`;
  - `agrupaciones contables -> banco`;
  - `agrupaciones sugeridas para revisión`;
- las agrupaciones ya no quedan explicadas solo por documento libre; el usuario puede ver las `OP` involucradas.

**Backend ajustado:**

- `routes/v1/reconcile_start.py` ahora expone `summary.sicom.final_reconciliation` con:
  - filas `PILAGA` con contraparte bancaria;
  - `OP` únicas con contraparte bancaria;
  - importe efectivamente conciliado;
  - lotes de extracto con soporte contable;
  - diferencia entre:
    - trazado solo por `SICOM`;
    - cierre bancario efectivo.

**Frontend ajustado:**

- `clientA/src/components/agui/ReconciliarResumen.svelte`
- `clientA/src/components/agui/ReconciliarDetalle.svelte`
- `clientA/src/components/agui/cards/CierreEfectivoSicomCard.svelte`
- `clientA/src/components/agui/cards/Conciliados11Card.svelte`
- `clientA/src/components/agui/cards/AprobadosN1Card.svelte`
- `clientA/src/components/agui/cards/SugeridosN1Card.svelte`

**Validación técnica cerrada:**

- `uv run python -m py_compile routes/v1/reconcile_start.py routes/v1/reconcile_summary.py routes/v1/reconcile_details.py`
- `pnpm -C clientA build`

**Validación end-to-end cerrada:**

- backend levantado en `:7058`;
- frontend levantado en `:3058`;
- Playwright ejecutado contra `/reconciliar`;
- flujo validado con archivos reales:
  - `2026_03-EXTRACTO.xlsx`
  - `2026_03-PILAGA.xlsx`
  - `2026_03_SICON MARZO CRUDO.xlsx`
- flujo cubierto:
  - upload y confirmación de extracto;
  - upload y confirmación de contable;
  - upload y confirmación de `SICOM`;
  - apertura del wizard;
  - avance completo del wizard;
  - inicio real de conciliación;
  - render de `Cierre efectivo via SICOM`;
  - carga de `Agrupaciones contables -> banco`;
  - carga de `Coincidencias directas 1->1`.

**Resultado observado en UI y backend:**

- `255` filas `PILAGA` con contraparte bancaria;
- `253` `OP` únicas;
- `$1.401.569.967,23` conciliados efectivamente;
- `n1/grupos` y `pares` respondieron `200` durante la prueba.

**Estado al cerrar:**

- backend: alineado con la lógica contable validada;
- frontend: alineado con trabajo diario de auditoría/operación;
- e2e: validado con archivos reales de marzo;
- servicios locales: apagados al terminar.

---

## Estado funcional confirmado

Quedó confirmado lo siguiente:

- la conciliación base sigue siendo `extracto bancario vs contable (PILAGA)`;
- `SICOM` entra como fuente auxiliar opcional;
- el banco no es fijo del producto; lo define cada cliente;
- `Patagonia` se usó solo como caso de ejemplo y validación;
- `SICOM` del mes viene como `1 workbook mensual` con días en solapas internas;
- la relación `Order de P. / OP <-> Nro Pago` es crítica para trazabilidad, pero no es `1 a 1`;
- `OP` sirve como eje operativo/manual;
- `Nro Pago` sirve como clave de lote bancario;
- el cruce por banco debe resolverse por caso/cliente, no hardcodeado en producto.

---

## Implementado hoy

Se terminó la `Fase 1` de `SICOM`:

- se agregó `role=sicom` en chat, upload backend, confirmación y UI;
- el upload de `SICOM` exige un solo archivo mensual por vez;
- se parsean las solapas válidas del workbook mensual y se consolida preview;
- el preview expone:
  - `rows`
  - `sheet_count`
  - `sheet_names`
  - `period_from / period_to`
  - bancos detectados
  - `op_count`
  - `nro_pago_count`
  - resumen relacional `OP <-> Nro Pago`
- se genera parquet canónico de `SICOM`;
- se persiste `files.sicom` en el estado de ingest;
- la UI ya muestra card propia de preview y confirmación de `SICOM`;
- se corrigió el parser para reconocer encabezados tipo `Nº Pago`.

---

## Validación hecha hoy

Se validó lo siguiente:

- `python3 -m py_compile` sobre los archivos Python modificados;
- `pnpm -C clientA build`;
- frontend levantado con `uv run pnpm dev --port 3058`;
- backend levantado con `uv run python ls_iMotorSoft_Srv01.py`;
- smoke de `SICOM` por HTTP;
- prueba Playwright del upload `SICOM` mínimo;
- prueba Playwright con archivos reales:
  - extracto: `11- Noviembre al 30.xlsx`
  - contable: `salida(261).xlsx`
  - sicom: `SICON CRUDO noviembre 2025.xlsx`
- con esos archivos reales quedaron validados:
  - upload
  - preview
  - confirmación
  - canónicos de `extracto`, `contable` y `SICOM`

---

## Datos reales validados de SICOM

Sobre `SICON CRUDO noviembre 2025.xlsx` quedó validado:

- `rows`: `507`
- `sheet_count`: `17`
- `period_from`: `2025-11-03`
- `period_to`: `2025-11-28`
- `bank_count`: `4`
- distribución detectada:
  - `Banco Patagonia`: `404`
  - `Banco Pat.Otros`: `80`
  - `Banco Santander`: `18`
  - `Banco Sant.Otros`: `5`

---

## Bloqueo detectado hoy

El siguiente bloqueo apareció al abrir el wizard de conciliación:

- `POST /api/reconcile_wizard/start` devolvía `500`;
- el motivo real no fue `SICOM`;
- el backend actual del wizard depende de Postgres via `core_*`;
- la DB configurada por defecto hoy es `workflow_ai_v1`;
- en este entorno el servidor de Postgres pudo estar levantado, pero la base `workflow_ai_v1` no existe;
- error reproducido: `asyncpg.exceptions.InvalidCatalogNameError: database "workflow_ai_v1" does not exist`.

---

## Hallazgo de historial del repo

Revisando el historial local del repo:

- antes, la conciliación original no dependía de este flujo `core_*` para todo;
- el baseline `run_ok_status_2025-12-22` ya usaba Postgres en `reconcile_start`;
- el wizard es posterior a ese baseline y quedó montado directamente sobre `core_runs/core_events`;
- por lo tanto, el problema del wizard no lo introdujo `SICOM`;
- `SICOM` expuso un problema de infraestructura/configuración ya presente en ese flujo.

---

## Cambio en progreso para destrabar el wizard

Quedó implementado en código un fallback en memoria para el wizard:

- nuevo helper: `services/wizard_runtime.py`;
- `routes/v1/reconcile_wizard_start.py` ahora cae a memoria si falla crear el run en DB;
- `routes/v1/run_action.py` ya puede leer/escribir estado y eventos del wizard en memoria;
- el stream SSE del wizard también puede salir desde memoria para esos runs.

**Objetivo de este cambio:**

- que el wizard funcione aunque `workflow_ai_v1` no exista;
- no bloquear las pruebas funcionales de conciliación por la DB del core.

---

## Estado exacto al cerrar hoy

**Estado real:**

- `SICOM` upload/preview/confirmación: terminado y validado;
- parser `SICOM`: corregido y validado con archivo real;
- wizard: diagnóstico terminado;
- fallback en memoria del wizard: implementado en código;
- verificación final del wizard con Playwright: pendiente de rerun completo.

**Importante:**

- la última corrida Playwright del wizard fue interrumpida antes de concluir;
- por eso no hay que asumir todavía `wizard OK` hasta rerun end-to-end.

---

## Archivos tocados hoy

- `services/ingest/sicom_excel.py`
- `routes/v1/uploads_v2_concilia.py`
- `routes/v1/ingest_confirm.py`
- `routes/v1/chat_concilia.py`
- `routes/v1/reconcile_start.py`
- `clientA/src/components/agui/ReconciliarApp.svelte`
- `routes/v1/reconcile_wizard_start.py`
- `routes/v1/run_action.py`
- `services/wizard_runtime.py`

---

## Próximo paso sugerido

Mañana retomar en este orden:

1. levantar frontend y backend con `uv`;
2. rerun de Playwright del wizard con los 3 archivos reales;
3. confirmar que `reconcile_wizard/start`, SSE y `run_action` funcionan via fallback en memoria;
4. si eso pasa, recién después seguir con `Fase 2`:
   - `uri_sicom` en conciliación;
   - `bank_scope/account_scope`;
   - filtrado de `SICOM` por banco objetivo;
   - trazabilidad `OP <-> Nro Pago` en summary/details.

---

## Documentos de base

- `docs/analisis_integracion_sicom_uploads_2026-04-17.md`
- `docs/analisis_sicom_noviembre_bank_scope_2026-04-19.md`
- `docs/especificacion_tecnica_sicom_bank_scope_2026-04-19.md`
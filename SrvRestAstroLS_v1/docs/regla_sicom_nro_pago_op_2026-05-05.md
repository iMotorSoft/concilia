# Regla SICOM mandatoria: Nro Pago + OP

Fecha: 2026-05-05
Proyecto: `SrvRestAstroLS_v1`

## Resumen

Cuando el usuario carga un archivo SICOM, la conciliacion de agrupados no puede quedar gobernada solo por suma de importes.

La realidad operativa validada es:

- `Nro Pago` identifica el lote bancario SICOM;
- `Order de P.` / `OP` identifica los componentes operativos del lote;
- el movimiento de extracto se explica por un lote SICOM cuando coincide por `Fecha de Pago + Imp.Neto`;
- una agrupacion `N PILAGA -> 1 extracto` solo es valida como agrupado aprobado si sus OP pertenecen al `Nro Pago` SICOM del movimiento bancario.

Regla corta:

> Si hay SICOM, manda `Nro Pago + OP`. Una suma exacta sin respaldo SICOM no alcanza.

## Alcance de la regla

Aplica cuando la corrida tiene:

- extracto bancario;
- contable PILAGA;
- SICOM mensual o recorte SICOM, por ejemplo `Base.xlsx`.

No aplica a corridas sin SICOM: en esos casos el fallback N->1 por suma puede seguir usandose como heuristica propia del pipeline base.

## Orden correcto de decision

1. Resolver `bank_scope` y `account_scope` del caso.
2. Filtrar SICOM al universo del caso.
   - Para `patagonia`, el universo SICOM incluye `Banco Patagonia` y `Banco Pat.Otros`.
3. Agrupar SICOM por:
   - `Fecha de Pago`;
   - `Banco`;
   - `Nro Pago`;
   - suma de `Imp.Neto`.
4. Buscar movimiento del extracto por:
   - misma fecha;
   - mismo importe absoluto.
5. Si existe lote SICOM exacto para el movimiento bancario:
   - el `Nro Pago` es mandatorio;
   - los componentes PILAGA deben salir de las OP de ese `Nro Pago`;
   - las fechas PILAGA pueden ser distintas;
   - no se deben tomar OP ajenas aunque sumen exacto.
6. Si no existe lote SICOM exacto:
   - no se debe fabricar un agrupado SICOM aprobado;
   - el movimiento puede quedar en no conciliado o, si corresponde, en otro circuito de sugeridos/pipeline sin SICOM.

## Regla de componentes PILAGA

Para cada OP del `Nro Pago` SICOM:

1. Buscar PILAGA por `OP`.
2. Preferir coincidencia exacta `OP + importe`.
3. Si la OP esta dividida entre `Banco Patagonia` y `Banco Pat.Otros`, no mezclar lotes en la fila visible del grupo:
   - dentro del grupo `33436`, la OP debe etiquetarse como `lote 33436`;
   - si la misma OP tambien aparece en `33437`, eso sirve para trazabilidad, pero no debe contaminar el grupo `33436`.
4. Si PILAGA trae un importe distinto al importe SICOM de ese lote, se muestra la diferencia; no se oculta.

## Caso validado: Base.xlsx, noviembre 2025

Archivos:

- extracto: `11- Noviembre al 30.xlsx`
- PILAGA: `salida(261).xlsx`
- SICOM: `Base.xlsx`

Scope:

- `patagonia`;
- cuenta `100-393300535-000`;
- SICOM en scope: `Banco Patagonia` + `Banco Pat.Otros`;
- `Base.xlsx`: `25` filas totales, `24` filas en scope Patagonia/Pat.Otros.

Grupos aprobados correctos en la interfaz:

| Fecha banco | Monto banco | Nro Pago | OP del lote | Diferencia |
|---|---:|---:|---|---:|
| `2025-11-03` | `-$21.110.000,00` | `33436` | `8902/2025`, `8906/2025`, `8907/2025`, `8908/2025` | `-$1.000.000,00` |
| `2025-11-03` | `-$11.774.180,00` | `33438` | `8909/2025`, `8912/2025`, `8914/2025`, `8915/2025` | `$0,00` |
| `2025-11-03` | `-$7.250.000,00` | `33439` | `8913/2025`, `8916/2025`, `8918/2025` | `$0,00` |
| `2025-11-03` | `-$4.300.000,00` | `33440` | `8910/2025`, `8922/2025` | `$0,00` |
| `2025-11-03` | `-$3.700.000,00` | `33442` | `8923/2025`, `8924/2025`, `8925/2025` | `$0,00` |
| `2025-11-03` | `-$400.000,00` | `33434` | `8876/2025` | `$0,00` |
| `2025-11-03` | `-$36.000,00` | `33435` | `8896/2025`, `8901/2025` | `$0,00` |

Control de UI validado con Playwright:

- `7 grupos`;
- todos los grupos son `sicom_lote`;
- todas las OP visibles tienen `OP + lote`;
- cero componentes con `0 match(es)`;
- cero componentes apuntando a un `Nro Pago` distinto al del grupo;
- el grupo falso del `2025-11-26 -$3.100.000,00` no aparece.

## Caso falso detectado y corregido

La interfaz habia mostrado:

- banco: `2025-11-26 -$3.100.000,00`;
- componentes PILAGA:
  - `9445/2025`;
  - `9956/2025`;
  - `9620/2025`;
  - `9938/2025`;
- suma PILAGA: `-$3.100.000,00`;
- cada componente: `0 match(es)`.

Validacion manual:

- esas 4 OP existen en PILAGA;
- esas 4 OP no existen en `Base.xlsx`;
- no hay lote SICOM en `Base.xlsx` por `2025-11-26` y `$3.100.000,00`;
- por lo tanto el grupo era solo un falso positivo del fallback N->1 por suma exacta.

Decision:

- con SICOM cargado, ese tipo de grupo no puede aparecer como agrupado aprobado;
- si una OP tiene `0 match(es)` SICOM, no puede formar parte de un grupo SICOM aprobado.
- por objetivo de auditoria, el grupo no debe ocultarse: debe aparecer en `Agrupaciones sugeridas / auditoria` con el motivo de rechazo.

## Diferencia esperada en Nro Pago 33436

El grupo `33436` es correcto aunque tenga diferencia:

- banco/SICOM lote `33436`: `-$21.110.000,00`;
- PILAGA seleccionado por OP del lote: `-$22.110.000,00`;
- diferencia visible: `-$1.000.000,00`.

La diferencia no invalida la asignacion del `Nro Pago`; indica una discrepancia PILAGA/SICOM que debe quedar visible.

Punto importante:

- `8908/2025` debe mostrarse como `8908/2025 · lote 33436`;
- aunque la misma OP pueda aparecer en otro lote SICOM, el grupo visible no debe decir que pertenece a otro `Nro Pago`.

## Implementacion vigente

Backend:

- `routes/v1/reconcile_details.py`
  - crea grupos SICOM mandatorios antes del fallback N->1;
  - usa solo filas SICOM del `Nro Pago` seleccionado;
  - filtra el contexto visible de cada componente PILAGA al lote del grupo;
  - descarta agrupados N->1 libres sin soporte SICOM cuando `uri_sicom` esta presente.

Frontend:

- `clientA/src/components/agui/cards/AprobadosN1Card.svelte`
  - muestra `Banco Patagonia · lote <Nro Pago>` en la fila bancaria;
  - muestra `OP · lote <Nro Pago>` en cada componente PILAGA;
  - distingue singular/plural de `lote/lotes`.
- `clientA/src/components/agui/cards/SugeridosN1Card.svelte`
  - funciona tambien como vista de auditoria;
  - muestra grupos rechazados por SICOM como `Auditoria SICOM`;
  - conserva componentes con `0 match(es)` visibles;
  - muestra `audit_reason`, por ejemplo `sin lote SICOM para fecha + importe del banco; OP sin SICOM: ...`.

## Regresiones que no deben volver

No aceptar como agrupado aprobado:

- OP con `0 match(es)` SICOM;
- grupo bancario sin lote SICOM si hay `uri_sicom`;
- componentes PILAGA cuyo lote visible sea distinto del `Nro Pago` del grupo;
- combinaciones por suma exacta que no existen en `Base.xlsx` o en el SICOM de la corrida;
- mezcla de datos entre meses o entre corridas.

Pero esos casos deben quedar visibles para auditoria:

- en `Agrupaciones sugeridas / auditoria`;
- con estado `sicom_auditoria`;
- sin consumir filas como conciliadas;
- con las mismas OP, importes, fechas y motivo de rechazo.

## Validaciones ejecutadas

Noviembre + `Base.xlsx`:

- endpoint `POST /api/reconcile/details/n1/grupos`;
- endpoint `POST /api/reconcile/details/n1/sugeridos`;
- Playwright contra UI `/reconciliar`;
- resultado OK:
  - `7 grupos`;
  - sin `0 match(es)`;
  - sin OP falsas;
  - sin mezcla de `Nro Pago`.
- resultado auditoria OK:
  - `8 sugeridos`;
  - visibles como `Auditoria SICOM`;
  - incluye el caso `2025-11-26 -$3.100.000,00`;
  - componentes `9445/2025`, `9956/2025`, `9620/2025`, `9938/2025`;
  - motivo `sin lote SICOM para fecha + importe del banco; OP sin SICOM: ...`.

Marzo 2026:

- corrida independiente con:
  - `2026_03-EXTRACTO.xlsx`;
  - `2026_03-PILAGA.xlsx`;
  - `2026_03_SICON MARZO CRUDO.xlsx`;
- Playwright OK;
- los archivos de marzo no deben mezclarse con noviembre/Base.

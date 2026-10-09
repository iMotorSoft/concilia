# Analisis profundo de `Banco Pat.Otros` en casos Patagonia

Fecha: 2026-04-30
Proyecto: `SrvRestAstroLS_v1`

## Objetivo

Revisar en profundidad que significa `Banco Pat.Otros` en `SICOM` y como debe usarse en la conciliacion de cuentas Patagonia.

La hipotesis revisada fue:

- `Pat.Otros` podria representar pagos originados desde Banco Patagonia hacia cuentas de otros bancos;
- por lo tanto podria ser un monto operativo acumulado de "otros";
- pero hay que definir si ese monto debe sumarse al cierre contra el extracto Patagonia o si solo sirve como trazabilidad auxiliar.

## Fuentes revisadas

Noviembre 2025:

- extracto: `11- Noviembre al 30.xlsx`
- PILAGA: `salida(261).xlsx`
- SICOM: `SICON CRUDO noviembre 2025.xlsx`
- recorte humano: `Base.xlsx`

Marzo 2026:

- extracto: `2026_03-EXTRACTO.xlsx`
- PILAGA: `2026_03-PILAGA.xlsx`
- SICOM: `2026_03_SICON MARZO CRUDO.xlsx`

Tambien se contrasto contra:

- [status_actual.md](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/docs/status_actual.md)
- [analisis_sicom_noviembre_bank_scope_2026-04-19.md](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/docs/analisis_sicom_noviembre_bank_scope_2026-04-19.md)
- [analisis_conciliacion_marzo_2026_patagonia.md](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/docs/analisis_conciliacion_marzo_2026_patagonia.md)

## Resultado numerico

### Noviembre 2025 mensual

Distribucion SICOM:

| Banco SICOM | Filas | Lotes | Imp.Neto |
|---|---:|---:|---:|
| `Banco Patagonia` | `404` | `79` | `$1.926.640.400,48` |
| `Banco Pat.Otros` | `80` | `26` | `$93.928.093,00` |
| `Banco Santander` | `18` | `13` | `$16.486.187,00` |
| `Banco Sant.Otros` | `5` | `3` | `$4.445.047,00` |

Comparacion de escenarios:

| Escenario | SICOM -> extracto | Importe contra extracto | PILAGA -> SICOM | Importe trazado | Cierre final |
|---|---:|---:|---:|---:|---:|
| Solo `Banco Patagonia` | `77 / 79` lotes | `$1.874.529.108,48` | `220` filas | `$903.162.938,30` | `213` filas / `$851.051.646,30` |
| `Patagonia + Pat.Otros` | `77 / 105` lotes | `$1.874.529.108,48` | `282` filas | `$968.860.037,30` | `213` filas / `$851.051.646,30` |
| Solo `Pat.Otros` | `0 / 26` lotes | `$0,00` | `62` filas | `$65.697.099,00` | `0` filas / `$0,00` |

Lectura:

- sumar `Pat.Otros` agrega `$65.697.099,00` de trazabilidad `PILAGA -> SICOM`;
- no agrega ningun lote conciliado contra el extracto;
- el cierre final no cambia.

### Base 03/11/2025

El recorte humano confirma el mismo patron en un caso chico:

| Escenario | SICOM -> extracto | Importe contra extracto | PILAGA -> SICOM | Importe trazado | Cierre final |
|---|---:|---:|---:|---:|---:|
| Solo `Banco Patagonia` | `7 / 7` lotes | `$48.570.180,00` | `18` filas | `$40.570.180,00` | `18` filas / `$40.570.180,00` |
| `Patagonia + Pat.Otros` | `7 / 9` lotes | `$48.570.180,00` | `22` filas | `$42.140.180,00` | `18` filas / `$40.570.180,00` |
| Solo `Pat.Otros` | `0 / 2` lotes | `$0,00` | `4` filas | `$1.570.000,00` | `0` filas / `$0,00` |

Lectura:

- `Pat.Otros` mejora la explicacion de OP;
- no cambia el monto bancario cerrado;
- tampoco aparece como lote separado en extracto.

### Marzo 2026 mensual

Distribucion SICOM:

| Banco SICOM | Filas | Lotes | Imp.Neto |
|---|---:|---:|---:|
| `Banco Patagonia` | `327` | `87` | `$2.332.397.292,46` |
| `Banco Pat.Otros` | `44` | `25` | `$81.489.660,09` |
| `Banco Santander` | `4` | `3` | `$3.360.000,00` |
| `Banco Sant.Otros` | `1` | `1` | `$400.000,00` |

Comparacion de escenarios:

| Escenario | SICOM -> extracto | Importe contra extracto | PILAGA -> SICOM | Importe trazado | Cierre final |
|---|---:|---:|---:|---:|---:|
| Solo `Banco Patagonia` | `77 / 87` lotes | `$1.913.465.547,23` | `280` filas | `$1.679.865.594,08` | `255` filas / `$1.401.569.967,23` |
| `Patagonia + Pat.Otros` | `77 / 112` lotes | `$1.913.465.547,23` | `309` filas | `$1.730.652.984,17` | `255` filas / `$1.401.569.967,23` |
| Solo `Pat.Otros` | `0 / 25` lotes | `$0,00` | `29` filas | `$50.787.390,09` | `0` filas / `$0,00` |

Lectura:

- sumar `Pat.Otros` agrega `$50.787.390,09` de trazabilidad `PILAGA -> SICOM`;
- no agrega cierre bancario;
- el resultado final validado contra extracto queda igual.

## Prueba de la hipotesis "Pat.Otros acumulado"

Se probo si `Pat.Otros` aparece en el extracto como:

1. lote propio por `fecha + importe`;
2. total diario de `Pat.Otros`;
3. total diario `Banco Patagonia + Pat.Otros`;
4. combinacion simple de un lote `Banco Patagonia` mas un lote `Pat.Otros` del mismo dia.

Resultado:

| Caso | Hits directos `Pat.Otros` | Hits combinados |
|---|---:|---:|
| Noviembre 2025 mensual | `0` | `0` |
| Base 03/11/2025 | `0` | `0` |
| Marzo 2026 mensual | `0` | `0` |

Conclusion:

- con la evidencia disponible, `Pat.Otros` no debe sumarse al cierre contra extracto Patagonia;
- no hay prueba de que el extracto Patagonia registre esos importes como un unico debito acumulado de "otros";
- si existe un circuito bancario real "Patagonia -> otros bancos", falta un campo o reporte que lo identifique explicitamente.

## Que significa operacionalmente `Pat.Otros`

La evidencia si muestra una relacion operativa fuerte:

| Caso | Importe `Pat.Otros` total | Importe `Pat.Otros` en OP compartidas con `Banco Patagonia` | Proporcion |
|---|---:|---:|---:|
| Noviembre 2025 mensual | `$93.928.093,00` | `$89.684.993,00` | `95,48%` |
| Base 03/11/2025 | `$2.570.000,00` | `$2.370.000,00` | `92,22%` |
| Marzo 2026 mensual | `$81.489.660,09` | `$78.689.660,09` | `96,56%` |

Esto sostiene esta lectura:

- `Pat.Otros` parece ser una clasificacion operativa de SICOM asociada a OP que tambien tienen pagos `Banco Patagonia`;
- probablemente separa destino o canal de acreditacion, no la cuenta bancaria fuente del extracto;
- sirve para explicar la composicion completa de una OP;
- no identifica por si solo un movimiento bancario conciliable en el extracto Patagonia usado como fuente del caso.

## Regla contable recomendada

Decision revisada luego de validar los 3 casos reales:

- `Banco Pat.Otros` debe considerarse parte del universo `Patagonia` para el analisis SICOM;
- eso permite explicar mas OP y mas importe operativo en `PILAGA -> SICOM`;
- el cierre efectivo contra extracto no se infla: solo cuentan los lotes que matchean por `fecha + importe`.

Separar dos conceptos:

1. `Universo Patagonia SICOM`: incluye `Banco Patagonia` y `Banco Pat.Otros`.
2. `Cierre bancario efectivo`: dentro de ese universo, solo suma lotes que aparecen en el extracto por `fecha + importe`.

Regla concreta:

- `Banco Patagonia` entra en el scope `patagonia`;
- `Banco Pat.Otros` tambien entra en el scope `patagonia`;
- `Banco Pat.Otros` entra en `PILAGA -> SICOM` y mejora trazabilidad;
- si un lote `Pat.Otros` no matchea contra extracto, queda trazado pero no cerrado;
- el resultado final `PILAGA -> SICOM -> extracto` solo debe tomar lotes que efectivamente matchearon contra extracto.

## Actualizacion 2026-05-05: `Nro Pago` manda dentro del universo Patagonia

Luego de validar la tarjeta `Agrupaciones contables -> banco` con noviembre 2025 y `Base.xlsx`, se agrega una restriccion operacional:

- incluir `Banco Pat.Otros` en el universo Patagonia mejora trazabilidad;
- pero un grupo visible de extracto siempre debe estar atado a un `Nro Pago` concreto;
- las OP visibles de ese grupo deben pertenecer a ese mismo `Nro Pago`;
- si una OP aparece en `Banco Patagonia` y tambien en `Banco Pat.Otros`, no se deben mezclar ambos lotes en la misma fila del grupo bancario.

Ejemplo:

- `8908/2025` aparece relacionada con mas de un lote SICOM;
- dentro del grupo bancario `33436`, la interfaz debe mostrar `8908/2025 · lote 33436`;
- no debe mostrar ni seleccionar informacion de otro `Nro Pago` como si fuera parte del grupo `33436`.

Regla de rechazo:

- una combinacion PILAGA que suma exacto contra banco, pero cuyas OP no existen en SICOM para el lote, no es un agrupado aprobado SICOM;
- el caso `2025-11-26 -$3.100.000,00` con OP `9445/2025`, `9956/2025`, `9620/2025`, `9938/2025` fue descartado por ese motivo.

Regla de visibilidad:

- descartado no significa oculto;
- el caso debe quedar visible como auditoria, con OP, importes, fechas y motivo de rechazo;
- no debe consumir filas como conciliadas ni mezclarse con los grupos aprobados.

Referencia:

- [regla_sicom_nro_pago_op_2026-05-05.md](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/docs/regla_sicom_nro_pago_op_2026-05-05.md)

## Que falta contemplar

### 1. Scope Patagonia compuesto

Implementado en `routes/v1/reconcile_start.py`:

- cuando el caso es `patagonia`, el filtro SICOM incluye `banco_patagonia` y `banco_pat_otros`;
- `patagonia_otros` puede seguir existiendo como etiqueta interna, pero no debe quedar fuera del analisis Patagonia.

### 2. Mostrar la diferencia entre trazado y cerrado

Al incluir `Pat.Otros`, el resumen debe dejar clara la diferencia:

- `PILAGA -> SICOM`: sube al sumar `Pat.Otros`;
- `SICOM -> extracto`: no sube si los lotes `Pat.Otros` no aparecen por `fecha + importe`;
- `final_reconciliation`: queda atado solo a lotes efectivamente cerrados contra extracto.

### 3. Tests de no regresion

Agregar tests/golden para:

- noviembre mensual;
- Base 03/11/2025;
- marzo 2026.

La expectativa debe ser:

- al sumar `Pat.Otros`, sube `PILAGA -> SICOM`;
- no sube `SICOM -> extracto`;
- no cambia `final_reconciliation`.

### 4. Drilldown de OP compartidas

Mostrar OP donde una misma `Order de P.` tiene:

- lineas `Banco Patagonia`;
- lineas `Banco Pat.Otros`;
- importe Patagonia;
- importe Pat.Otros;
- lotes involucrados.

Esto es lo que permite explicar al usuario por que la OP tiene mas trazabilidad que cierre bancario.

### 5. Evidencia externa del significado de `Pat.Otros`

Con los XLSX actuales solo se infiere el significado por comportamiento.

Para cerrar semantica bancaria hace falta alguna de estas evidencias:

- manual/codigo de SICOM;
- campo de destino CBU/banco receptor;
- reporte de interbanking/acreditaciones;
- extracto de cuenta puente si existiera;
- descripcion bancaria especifica para transferencias a otros bancos.

Sin esa evidencia, `Pat.Otros` no debe convertirse en cierre bancario automatico.

## Conclusion final actualizada

`Banco Pat.Otros` debe tratarse como parte del universo Patagonia para el analisis SICOM.

La evidencia de noviembre, Base y marzo es consistente:

- `Pat.Otros` aparece fuertemente relacionado con OP de Patagonia;
- mejora la explicacion de pagos desde PILAGA hacia SICOM;
- no aparece como lote conciliable contra el extracto;
- no hay hits de acumulacion simple `Patagonia + Pat.Otros` contra lineas bancarias;
- por eso debe incluirse en el scope Patagonia, pero manteniendo separado lo trazado de lo efectivamente cerrado contra extracto.

# Analisis de conciliacion noviembre 2025 con foco en banco/cuenta

Fecha: 2026-04-19
Proyecto: `SrvRestAstroLS_v1`
Fuentes analizadas localmente:

- `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SpendIQ/Doc/FCE/Conciliacion/SICOM/11- Noviembre al 30.xlsx`
- `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SpendIQ/Doc/FCE/Conciliacion/SICOM/salida(261).xlsx`
- `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SpendIQ/Doc/FCE/Conciliacion/SICOM/SICON CRUDO noviembre 2025.xlsx`

## 1. Objetivo

Rehacer el analisis mensual incorporando una condicion que en la primera version no estaba modelada de forma explicita:

- el `extracto bancario` pertenece a una cuenta especifica;
- `PILAGA` opera desde una tesoreria/cuenta de trabajo especifica;
- `SICOM` puede contener pagos de mas de un banco dentro del mismo archivo mensual;
- por lo tanto, antes de usar `SICOM` en conciliacion, hay que resolver el `bank/account scope`.

## 2. Hallazgo principal

La consideracion de banco/cuenta es correcta y cambia el diseño tecnico:

1. El `extracto` analizado corresponde a una cuenta `Patagonia`.
2. `SICOM` mensual mezcla varios bancos.
3. Solo los lotes `Banco Patagonia` de `SICOM` hacen match exacto contra el extracto.
4. Los lotes de otros bancos (`Banco Pat.Otros`, `Banco Santander`, `Banco Sant.Otros`) no pegan contra este extracto.
5. `PILAGA` si muestra trazabilidad visible con `SICOM`, pero no por `Nro Pago`; la muestra mas fuerte aparece por `Order de P.` y monto.

Conclusion:

- `SICOM` no puede entrar al pipeline como dataset "plano" mensual sin filtro;
- primero debe quedar acotado al `scope` de banco/cuenta que representa la conciliacion corriente.

## 3. Extracto bancario

### 3.1 Identificacion de cuenta

En el encabezado del archivo se lee:

- `Tipo y Nro. de Cuenta: CC $ 100-393300535-000`
- `Denominacion: FAC.CS.ECONOMICAS -UBA-`

Esa cuenta coincide con la familia de cuenta `Patagonia` ya observada en muestras anteriores (`393300/5` en otros extractos/PILAGA de referencia).

### 3.2 Inconsistencia de metadatos del archivo

El archivo se llama `11- Noviembre al 30.xlsx`, pero el encabezado visible dice:

- `Fecha desde: 01/11/2025`
- `Fecha hasta: 10/11/2025`

Sin embargo, los movimientos reales llegan hasta `28/11/2025`.

Esto implica que:

- no conviene confiar ciegamente en el rango de fechas del encabezado;
- el parser debe calcular el rango real a partir de las filas leidas.

### 3.3 Perfil del extracto

- movimientos leidos: `238`
- movimiento relevante dominante: `DEBITO P/ACREDITAC.DE SUE`
- cantidad de esas lineas: `136`
- total de esas lineas: `$2.164.448.330,27`

Ese patron confirma que el extracto refleja lotes bancarios de sueldos/acreditaciones y no el detalle analitico de cada OP.

## 4. PILAGA / contable

### 4.1 Perfil general

- registros leidos: `988`
- rango de fechas: `03/11/2025` a `28/11/2025`
- egresos con `Medio = Transferencia`: `946`
- total de esos egresos: `$2.159.006.711,06`

### 4.2 Banco/cuenta en PILAGA

El archivo `salida(261).xlsx` no expone de forma limpia un numero de cuenta en el encabezado, a diferencia del extracto.

Si aparecen muchas lineas con referencia visible a `BANCO PATAGONIA S.A.` dentro del detalle exportado, pero eso no resuelve por si solo el problema de identificacion de cuenta fuente.

Conclusion tecnica:

- para `PILAGA`, el `account_scope` no deberia depender solo del contenido visible del XLSX;
- conviene persistirlo como metadato explicito de ingest.

## 5. SICOM mensual

### 5.1 Estructura

- hojas detectadas: `17`
- nombres de hoja: `Hoja2` a `Hoja18`
- registros totales: `507`
- rango de fechas: `03/11/2025` a `28/11/2025`

El workbook se comporta efectivamente como:

- `1 archivo mensual -> N hojas internas -> 1 dataset consolidado`

### 5.2 Distribucion por banco

Registros:

- `Banco Patagonia`: `404`
- `Banco Pat.Otros`: `80`
- `Banco Santander`: `18`
- `Banco Sant.Otros`: `5`

Totales netos:

- `Banco Patagonia`: `$1.926.640.400,48`
- `Banco Pat.Otros`: `$93.928.093,00`
- `Banco Santander`: `$16.486.187,00`
- `Banco Sant.Otros`: `$4.445.047,00`

Conclusion:

- `SICOM` es realmente multibanco en un mismo mes;
- por eso no alcanza con saber que el archivo es "de noviembre";
- hace falta saber para que banco/cuenta se quiere conciliar.

## 6. Cruce bank-aware entre SICOM y extracto

### 6.1 Regla probada

Se agruparon los registros de `SICOM` por:

- `Fecha de Pago`
- `Banco`
- `Nro Pago`

y se comparo su `Imp.Neto` contra las lineas del extracto con descripcion:

- `DEBITO P/ACREDITAC.DE SUE`

### 6.2 Resultado para Banco Patagonia

Tomando solo `Banco Patagonia`:

- lotes `SICOM Patagonia`: `79`
- lotes con match exacto en extracto: `77`
- cobertura por lotes: `97,47%`
- cobertura por importe sobre `SICOM Patagonia`: `97,30%`
- cobertura por importe sobre el total de debitos relevantes del extracto: `86,61%`
- total exacto conciliado por esa via: `$1.874.529.108,48`

Lotes Patagonia sin match exacto:

1. `04/11/2025` - `Nro Pago 33455` - `$51.611.292,00`
2. `18/11/2025` - `Nro Pago 33514` - `$500.000,00`

### 6.3 Resultado para otros bancos

En la misma ventana temporal:

- `Banco Pat.Otros`: `26` lotes, `0` hits exactos en extracto
- `Banco Santander`: `13` lotes, `0` hits exactos en extracto
- `Banco Sant.Otros`: `3` lotes, `0` hits exactos en extracto

Conclusion funcional fuerte:

- este extracto no debe compararse contra todo `SICOM`;
- debe compararse contra la porcion `Banco Patagonia`.

## 7. Cruce entre PILAGA y extracto

El match directo `misma fecha + mismo importe` entre:

- egresos `Transferencia` de `PILAGA`
- y debitos `DEBITO P/ACREDITAC.DE SUE` del extracto

da un resultado pobre:

- matches exactos: `13`
- total exacto: `$5.951.400,00`

Esto confirma que:

- la conciliacion `PILAGA -> extracto` no se resuelve bien como `1 a 1` lineal;
- sigue haciendo falta una capa intermedia de interpretacion por lotes.

## 8. Hallazgo nuevo: cruce visible entre PILAGA y SICOM

Este punto cambia parte de la lectura anterior.

### 8.1 Que si aparece

Si se toma `Doc. Principal` de `PILAGA` y se normaliza el valor `OP: xxxx/2025`, aparecen coincidencias claras con `Order de P.` de `SICOM`.

Resultado:

- coincidencias de `Doc. Principal OP` presentes en `Order de P.` de `SICOM`: `287`

Si ademas se exige coincidencia exacta por:

- `Order de P.`
- `importe/egreso`

aparecen:

- `282` filas `PILAGA` con match exacto `OP + importe`
- total representado: `$968.860.037,30`

Distribucion por banco del lado SICOM:

- `Banco Patagonia`: `220`
- `Banco Pat.Otros`: `62`

No aparecieron matches equivalentes por `Doc. Cobro / Id Pago` contra `Nro Pago`:

- coincidencias `Doc. Cobro / Id Pago` numerico vs `Nro Pago`: `0`

### 8.2 Desfase temporal

En esos matches `PILAGA <-> SICOM` el desfase dominante entre:

- `Fecha PILAGA`
- `Fecha de Pago SICOM`

no es `0` dias.

Distribucion observada del lag:

- `6` dias: `83`
- `4` dias: `57`
- `5` dias: `54`
- `7` dias: `34`
- `2` dias: `32`
- `3` dias: `12`
- `1` dia: `8`
- `8` dias: `2`

Ejemplo fuerte:

- `PILAGA 10/11/2025 - OP 8902/2025 - egreso 9.450.000`
- `SICOM 03/11/2025 - Order de P. 8902/2025 - Banco Patagonia - Nro Pago 33436 - Imp.Neto 9.450.000`

Tambien para la misma `OP 8902/2025` aparece:

- `PILAGA 10/11/2025 - egreso 450.000`
- `SICOM 03/11/2025 - Banco Pat.Otros - Nro Pago 33437 - Imp.Neto 450.000`

Conclusion:

- `PILAGA` si conserva una referencia operativa util hacia `SICOM`;
- esa referencia visible es `Order de P.` via `Doc. Principal`;
- `Doc. Cobro / Id Pago` no parece ser el mismo identificador que `Nro Pago`;
- y el cruce debe tolerar desfases de fecha de varios dias.

## 8.3 Validacion puntual con `Base.xlsx` del 03/11/2025

Se valido especificamente el archivo:

- `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SpendIQ/Doc/FCE/Conciliacion/SICOM/Base.xlsx`

Tambien se comparo `Base.xlsx` contra el subconjunto del archivo mensual:

- `SICON CRUDO noviembre 2025.xlsx`
- filtrado por `Fecha de Pago = 03/11/2025`

Resultado de la comparacion:

- filas en `Base.xlsx`: `25`
- filas en `SICOM mensual` para `03/11/2025`: `25`
- mismo conteo por banco:
  - `Banco Patagonia`: `19`
  - `Banco Pat.Otros`: `5`
  - `Banco Santander`: `1`
- mismos totales por banco usando `Imp.Neto`:
  - `Banco Patagonia`: `$48.570.180,00`
  - `Banco Pat.Otros`: `$2.570.000,00`
  - `Banco Santander`: `$700.000,00`
- misma estructura relacional `OP <-> Nro Pago`

Al normalizar nombres de columna y formato numerico, el resultado fue:

- `Base.xlsx` y el subconjunto mensual del `03/11/2025` son exactamente el mismo dataset

Esto confirma que:

- el caso puntual del dia 3 no contradice el analisis mensual;
- `Base.xlsx` es una vista diaria consistente con el `SICOM` mensual;
- y la historia operativa es la misma en ambos niveles.

Aplicando la regla de scope bancario:

- solo `Banco Patagonia`:
  - `7` lotes `SICOM`;
  - `7` lotes con match exacto en extracto;
  - importe conciliado: `$48.570.180,00`;
- `Banco Patagonia + Banco Pat.Otros`:
  - `9` lotes `SICOM`;
  - `7` lotes con match exacto en extracto;
  - importe conciliado: `$48.570.180,00`;
- todos los bancos:
  - `10` lotes `SICOM`;
  - `7` lotes con match exacto en extracto;
  - importe conciliado: `$48.570.180,00`.

Los `7` lotes `Banco Patagonia` conciliados son:

| Nro Pago | Imp.Neto |
|---:|---:|
| `33434` | `$400.000,00` |
| `33435` | `$36.000,00` |
| `33436` | `$21.110.000,00` |
| `33438` | `$11.774.180,00` |
| `33439` | `$7.250.000,00` |
| `33440` | `$4.300.000,00` |
| `33442` | `$3.700.000,00` |

Los lotes adicionales de `Banco Pat.Otros` no agregan cierre contra el extracto Patagonia:

| Nro Pago | Banco | Imp.Neto |
|---:|---|---:|
| `33437` | `Banco Pat.Otros` | `$1.450.000,00` |
| `33441` | `Banco Pat.Otros` | `$1.120.000,00` |

Tambien se confirmo que el campo correcto para conciliacion bancaria es `Imp.Neto`, no `Importe`.

Para `Banco Patagonia` del `03/11/2025`:

- total por `Importe`: `$48.591.000,00`;
- total por `Imp.Neto`: `$48.570.180,00`;
- diferencia: `$20.820,00`.

La diferencia corresponde a la OP `8909/2025`, `Nro Pago 33438`:

| OP | Banco | Nro Pago | Importe | Imp.Neto | Diferencia |
|---|---|---:|---:|---:|---:|
| `8909/2025` | `Banco Patagonia` | `33438` | `$150.000,00` | `$129.180,00` | `$20.820,00` |

Conclusion puntual:

- la revision humana de un dia confirma la logica mensual;
- el cierre de extracto Patagonia debe usar solo `Banco Patagonia`;
- los bancos `Otros` quedan como trazabilidad auxiliar, no como cierre bancario;
- `SICOM -> extracto` debe matchear por `Fecha de Pago + Nro Pago/Banco agrupado + Imp.Neto`, validado contra extracto por `fecha + importe`.

Resultados leidos:

- filas: `25`
- `Order de P.` unicas: `20`
- `Nro Pago` unicos: `10`

Distribucion de cardinalidad:

- `16` OP se asocian a un unico `Nro Pago`
- `4` OP se asocian a mas de un `Nro Pago`
- `2` `Nro Pago` se asocian a una unica OP
- `8` `Nro Pago` agrupan mas de una OP

Ejemplos de `OP -> multiples Nro Pago`:

- `8902/2025 -> 33436, 33437, 33443`
- `8908/2025 -> 33436, 33437`
- `8912/2025 -> 33438, 33441`
- `8915/2025 -> 33438, 33441`

Ejemplos de `Nro Pago -> multiples OP`:

- `33436 -> 8902/2025, 8906/2025, 8907/2025, 8908/2025`
- `33438 -> 8909/2025, 8912/2025, 8914/2025, 8915/2025`
- `33439 -> 8913/2025, 8916/2025, 8918/2025`
- `33442 -> 8923/2025, 8924/2025, 8925/2025`

Conclusion puntual:

- si hay relacion entre `Order de P.` y `Nro Pago`;
- pero esa relacion no es univoca;
- `Order de P.` funciona como clave operativa de rastreo;
- `Nro Pago` funciona como clave de lote bancario.

Esto encaja bien con el dato funcional adicional:

- las personas que hacen validacion manual usan `OP`.

Implicancia:

- en el producto, `OP / Order de P.` debe ser un campo de primera clase para busqueda, trazabilidad y explicacion;
- no conviene intentar reemplazar esa experiencia manual por una interfaz centrada solo en `Nro Pago`;
- el modelo deberia permitir navegar en ambos sentidos:
  - `OP -> uno o varios Nro Pago`
  - `Nro Pago -> una o varias OP`

## 8.4 Actualizacion 2026-05-05: regla final `Nro Pago + OP`

La validacion de interfaz con `Base.xlsx` agrego una regla mas fuerte que la version inicial de este analisis.

Regla final:

- si un movimiento bancario matchea un lote SICOM por `Fecha de Pago + Imp.Neto`, el `Nro Pago` de ese lote es mandatorio;
- las OP del agrupado deben ser exactamente las OP de ese `Nro Pago`;
- si la misma OP aparece tambien en otro `Nro Pago`, eso no autoriza a mezclar lotes en la misma fila de la interfaz;
- una suma exacta de PILAGA contra banco no es suficiente cuando esas OP no existen en SICOM.

Caso falso detectado:

| Fecha banco | Monto banco | OP PILAGA | Motivo de rechazo |
|---|---:|---|---|
| `2025-11-26` | `-$3.100.000,00` | `9445/2025`, `9956/2025`, `9620/2025`, `9938/2025` | las OP existen en PILAGA pero no existen en `Base.xlsx`; no hay lote SICOM por fecha/importe |

Ese grupo sumaba exacto, pero era incorrecto para una corrida con SICOM. Debe quedar fuera de `Agrupaciones contables -> banco` aprobadas.

Como el objetivo del producto es auditoria, no debe ocultarse:

- queda visible en `Agrupaciones sugeridas / auditoria`;
- se muestra con estado `Auditoria SICOM`;
- conserva las OP, importes y fechas;
- muestra el motivo `sin lote SICOM para fecha + importe del banco; OP sin SICOM: ...`;
- no consume esas filas como conciliadas.

Grupos aprobados correctos para `Base.xlsx`:

| Nro Pago | OP del lote | Estado |
|---:|---|---|
| `33436` | `8902/2025`, `8906/2025`, `8907/2025`, `8908/2025` | valido con diferencia visible `-$1.000.000,00` |
| `33438` | `8909/2025`, `8912/2025`, `8914/2025`, `8915/2025` | valido |
| `33439` | `8913/2025`, `8916/2025`, `8918/2025` | valido |
| `33440` | `8910/2025`, `8922/2025` | valido |
| `33442` | `8923/2025`, `8924/2025`, `8925/2025` | valido |
| `33434` | `8876/2025` | valido |
| `33435` | `8896/2025`, `8901/2025` | valido |

Validacion de interfaz:

- todos los componentes muestran `OP · lote <Nro Pago>`;
- no hay componentes `0 match(es)`;
- no hay OP con lote distinto al del grupo;
- la diferencia no invalida el grupo, pero debe quedar visible.

Detalle completo:

- [regla_sicom_nro_pago_op_2026-05-05.md](/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/docs/regla_sicom_nro_pago_op_2026-05-05.md)

## 9. Implicancias para el modelo

### 9.1 Scope explicito

La especificacion futura deberia incorporar explicitamente:

- `bank_scope`
- y preferentemente `account_scope`

para `extracto` y `contable`.

### 9.2 Ingest de SICOM

Al confirmar un `SICOM` mensual, conviene persistir:

- `available_banks`
- `bank_count`
- `period_from`
- `period_to`
- `sheet_count`
- `sheet_names`

y luego derivar una version canonicamente filtrable por banco.

### 9.3 Regla de conciliacion recomendada

La logica correcta queda por capas:

1. `Extracto` define el `account_scope` efectivo.
2. `SICOM` se filtra al banco compatible con ese scope.
3. `SICOM -> extracto` se explica por lote:
   - `Fecha de Pago`
   - `Banco`
   - `Nro Pago`
   - `Imp.Neto`
4. `PILAGA -> SICOM` se explica mejor por:
   - `Nro Pago` del lote cuando hay match contra extracto;
   - `Order de P. / OP` dentro de ese mismo `Nro Pago`;
   - `importe`, prefiriendo match exacto `OP + importe`;
   - y una tolerancia de desfase temporal, porque la fecha PILAGA puede diferir de la fecha SICOM/extracto.
5. `PILAGA -> extracto` directo queda reservado para matches realmente univocos.

## 10. Conclusion ejecutiva

La conclusion tecnica mas importante es esta:

- el problema no es solo agregar `uri_sicom`;
- tambien hay que modelar el `bank/account scope`.

Sin esa capa:

- `SICOM` mezcla bancos y puede inducir falsos matches;
- `extracto` se cruza contra universo incorrecto;
- y la explicacion de lotes queda contaminada por pagos que pertenecen a otro circuito bancario.

Con esa capa:

- el extracto `Patagonia 393300/5` se explica muy bien con `SICOM Banco Patagonia`;
- `PILAGA` aporta trazabilidad real por `Order de P.`;
- y el pipeline puede pasar de una conciliacion ingenua por monto/fecha a una conciliacion asistida por lotes y banco objetivo.

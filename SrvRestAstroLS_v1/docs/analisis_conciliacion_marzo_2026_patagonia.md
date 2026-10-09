# Analisis conciliacion marzo 2026 Patagonia

Fecha: 2026-04-23
Proyecto: `SrvRestAstroLS_v1`

## Fuentes validadas

- `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SpendIQ/Doc/FCE/Conciliacion/SICOM/2026_03-EXTRACTO.xlsx`
- `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SpendIQ/Doc/FCE/Conciliacion/SICOM/2026_03-PILAGA.xlsx`
- `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SpendIQ/Doc/FCE/Conciliacion/SICOM/2026_03_SICON MARZO CRUDO.xlsx`

## Objetivo contable

Quedo fijado el siguiente criterio:

- la conciliacion principal sigue siendo `PILAGA <-> extracto bancario`;
- `SICOM` no reemplaza ninguna de esas dos fuentes;
- `SICOM` se usa como capa auxiliar para explicar lotes bancarios y trazabilidad operativa;
- el objetivo es reconocer:
  - operaciones contables que tienen contraparte en el extracto;
  - movimientos del extracto que tienen sustento en el contable;
- cuando el extracto agrupa pagos, `SICOM` permite reconstruir el puente `OP -> Nro Pago -> lote bancario`.

## Hallazgos sobre las fuentes

### Extracto

- el caso queda identificado como `Banco Patagonia`;
- la cuenta detectada es `100-393300535-000`;
- ese dato define el `scope` efectivo del caso.

### PILAGA

- el archivo trae operaciones con referencia `OP: NNNN/2026`;
- esa referencia es la clave operativa correcta para navegar y auditar desde contabilidad.

### SICOM

- el archivo mensual vino mezclado:
  - `Banco Patagonia`
  - `Banco Pat.Otros`
  - `Banco Santander`
  - `Banco Sant.Otros`
- esto no cambia el alcance del caso bancario, porque el extracto sigue definiendo el scope principal;
- aun asi, se evaluo la hipotesis operativa de que `Banco Pat.Otros` represente pagos originados desde Patagonia hacia otros bancos.

## Validacion operativa cerrada

### 1. `SICOM -> extracto` con scope `Patagonia`

Resultado validado:

- filas `SICOM` totales: `376`
- filas `Banco Patagonia`: `327`
- filas fuera de scope: `49`
- lotes `Patagonia`: `87`
- lotes con match exacto en extracto: `77`
- importe conciliado por lote: `$1.913.465.547,23`
- importe total `SICOM Patagonia` por `Imp.Neto`: `$2.332.397.292,46`
- importe bruto informado en `Importe`: `$2.336.422.191,37`
- cobertura por cantidad de lotes: `88,51%`
- cobertura por importe: `82,04%`

Conclusion:

- para el match `SICOM -> extracto` se considera conciliacion valida unicamente cuando coincide `fecha + importe`;
- la comparacion por importe aislado puede generar falsos positivos por montos repetidos o coincidentes;
- el cierre bancario efectivo se sostiene sobre lotes `Banco Patagonia`;
- los otros bancos no agregan cobertura directa contra el extracto.

### 2. `PILAGA -> SICOM`

Se detecto una incompatibilidad de formato entre fuentes:

- `PILAGA` venia como `OP: 1261/2026`;
- `SICOM` venia como `1261`.

Se corrigio la normalizacion para comparar ambas fuentes por una clave operativa compatible.

Resultado validado para `Banco Patagonia`:

- filas `PILAGA` con match exacto por `OP + importe`: `280`
- `OP` unicas con match: `277`
- importe trazado: `$1.679.865.594,08`

## Hipotesis `Patagonia + Pat.Otros`

Se evaluo si `Banco Pat.Otros` debia sumarse al alcance operativo del caso.

### Impacto en `SICOM -> extracto`

- `Banco Pat.Otros` aporta `25` lotes;
- lotes adicionales conciliados contra extracto: `0`;
- importe adicional conciliado contra extracto: `$0,00`.

Conclusion:

- `Pat.Otros` no mejora la conciliacion bancaria final contra el extracto.

### Impacto en `PILAGA -> SICOM`

Si se suma `Banco Pat.Otros`:

- filas con match suben de `280` a `309`;
- `OP` unicas suben de `277` a `281`;
- importe trazado sube de `$1.679.865.594,08` a `$1.730.652.984,17`;
- mejora de trazabilidad: `$50.787.390,09`.

Conclusion:

- `Pat.Otros` si agrega trazabilidad operativa desde `PILAGA`;
- pero no agrega conciliacion bancaria efectiva contra el extracto.

## Resultado final util para auditoria

Para el circuito completo `PILAGA -> SICOM -> extracto` el resultado final validado queda asi:

- filas `PILAGA` efectivamente conciliadas contra extracto: `255`
- `OP` unicas efectivamente conciliadas contra extracto: `253`
- importe final conciliado: `$1.401.569.967,23`
- banco final observado en ese cierre: solo `Banco Patagonia`

Importante:

- este resultado final no cambia aunque se sume `Banco Pat.Otros` al analisis;
- `Pat.Otros` mejora explicacion operativa, pero no cambia el cierre bancario final.

## Conclusion contable

La formulacion correcta del caso queda cerrada de esta manera:

- la conciliacion principal es `contable <-> extracto`;
- `SICOM` se usa como evidencia auxiliar para reconstruir el puente operativo;
- `OP` es la clave de lectura operativa/manual;
- `Nro Pago` es la clave de lote bancario;
- cuando el extracto agrupa pagos, la suma y desagregacion debe apoyarse en `SICOM`;
- el resultado de auditoria debe distinguir siempre entre:
  - trazabilidad operativa explicada;
  - conciliacion bancaria efectivamente cerrada.

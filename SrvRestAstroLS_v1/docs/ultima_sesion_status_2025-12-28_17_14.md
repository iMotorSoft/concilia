# Estado de avance - Wizard UX

Fecha/hora: 2025-12-28 17:14

## Contexto
- Se detecto que la UX mostraba una ventana maxima incorrecta (61 dias) respecto del matching real (42 dias).

## Cambios realizados
- El preview del wizard calcula window_max real usando matching 1->1 sin limite practico y devuelve el par de mayor diferencia.
- El wizard start recibe uri_extracto/uri_contable y los pasa al preview.
- La UI muestra la ventana maxima real con detalle de par extracto/contable.
- Cuando hay confirmacion requerida, el boton de confirmar resalta mas y el boton Continuar queda deshabilitado.

## Resultado verificado
- Ventana maxima detectada: 2025-08-06 -> 2025-09-17 (42 dias).
- Extracto: 2025-08-06, doc 4101987, monto -100000.0.
- Contable: 2025-09-17, doc OP: 7339/2025, monto -100000.0.

## Nota para reconstruir
- Archivos:
  - Extracto: /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SpendIQ/Doc/FCE/Conciliacion/EXTRACTO SANTANDER AGOST-SEPT.xlsx
  - Contable: /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SpendIQ/Doc/FCE/Conciliacion/PILAGA SANTANDER AGOST -SEPT.xlsx
- Comando:
```bash
.venv/bin/python - <<'PY'
from services.parquet_preview import get_extract_preview
extracto = "file:///media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SpendIQ/Doc/FCE/Conciliacion/EXTRACTO SANTANDER AGOST-SEPT.xlsx"
contable = "file:///media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SpendIQ/Doc/FCE/Conciliacion/PILAGA SANTANDER AGOST -SEPT.xlsx"
preview = get_extract_preview("", "fce", "001", uri_extracto=extracto, uri_contable=contable)
print(preview.get("window_max"))
PY
```
- Esperado: days=42 y par extracto/contable con monto -100000.0.

## Pendientes
- Validar visualmente el contraste del boton de confirmacion en UI.
- Confirmar flujo completo del wizard con confirmaciones en distintos escenarios.

## Notas
- No se corrieron tests automatizados.

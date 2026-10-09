# Publicación ordenada en GitHub

Rama: `procesamiento-multiple-extractos`. Remoto: `origin` (`iMotorSoft/concilia`).

## Orden de entrega

1. Base DEV de seguridad: configuración, PostgreSQL/psycopg, migraciones versionadas, repositorio de sesiones, herramientas locales, tests y ADR-005.
2. Integración backend: límite HTTP, catálogo de archivos, auditoría, SICOM, conciliación y wizard temporal, tests y herramientas de validación.
3. Frontend: autenticación, transporte con CSRF, SSE autenticado, previews SICOM y tarjetas de conciliación.
4. Documentación funcional y evidencia histórica de validación.

No se cambió de rama ni se ejecutaron migraciones, aprovisionamiento o gestión de PostgreSQL. Las migraciones se publican como código, no se aplican.

## Validación previa a publicar

- `git fetch origin`: rama local alineada con el remoto antes de los commits.
- Desde `SrvRestAstroLS_v1/backend`: `uv run pytest tests ../tests -q -k 'not real_seg_schema_and_grants'`: **21 PASS, 1 DESELECTED**. Se excluyó el test que invoca `migrate`; publicar no autoriza migraciones. Los tests HTTP/PostgreSQL restantes se ejecutaron secuencialmente.
- Desde `SrvRestAstroLS_v1/clientA`: `pnpm build`: **PASS** (4 páginas).
- `pnpm check`: **NO DISPONIBLE**; no existe el script en `package.json`.
- `git diff --check`: **PASS**.
- `detect-secrets 1.5.0`: revisión de candidatos de publicación, incluidos archivos nuevos. Los cinco candidatos del código son capabilities, mensajes sin secretos y valores sintéticos de tests. Los candidatos en JSON de evidencia son hashes SHA-256/SHA-1, no credenciales.
- Comparación de credenciales técnicas locales contra candidatos de publicación: **sin coincidencias**, sin imprimir sus valores.

Los resultados Chromium/reinicio documentados en `seg01_final_closure_dev.md` corresponden al cierre anterior; no se repitió ese gate para esta publicación.

## Artefactos locales preservados

Las cuatro capturas `SrvRestAstroLS_v1/scripts/e2e_sicom*failure*.png` son artefactos generados de fallos. No se publican, no se borran; una captura revisada contiene cuenta y detalle financiero real.

## Límites y próximo paso

Entrega exclusivamente DEV. Confirmaciones y wizard permanecen en memoria. No certifica producción ni persistencia financiera durable. Persisten warnings de inferencia de fechas y CSS `@property` y falta de typecheck frontend.

Las herramientas antiguas de smoke/SICOM no sustituyen el gate autenticado de SEG-01; el smoke HTTP sin sesión no es válido con el guard actual. Próximo paso: revisar los commits en GitHub y planificar persistencia durable fuera de esta publicación.

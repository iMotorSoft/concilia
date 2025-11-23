# Guía rápida de ramas y puntos de retorno

## Rama principal
- En este proyecto la rama válida es `main`.
- El repo raíz es `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia` y el código está en `SrvRestAstroLS_v1`, pero todo está bajo la misma rama `main`.

## Crear una rama de prueba
```bash
git switch main && git pull          # partir del último estado válido
git switch -c pruebas-nombre         # rama para experimentar
```

## Trabajar y decidir
- Haz tus cambios y pruebas en la rama `pruebas-nombre`.
- Si los cambios sirven:
```bash
git switch main
git merge pruebas-nombre             # une los cambios a main
git branch -d pruebas-nombre         # elimina la rama local
```
- Si no sirven:
```bash
git switch main
git branch -D pruebas-nombre         # borra la rama de prueba
```

## Punto de retorno rápido (tag opcional)
- Antes de probar algo en `main`, puedes marcar un snapshot:
```bash
git tag -a pre-prueba-AAAAmmdd -m "antes de prueba X"
```
- Para volver a ese punto (esto descarta cambios sin commitear):
```bash
git reset --hard pre-prueba-AAAAmmdd
```

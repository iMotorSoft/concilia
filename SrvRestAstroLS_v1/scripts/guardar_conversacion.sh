#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ts="$(date +"%Y-%m-%d_%H%M%S")"
human="$(date +"%Y-%m-%d %H:%M:%S")"
out="${root_dir}/docs/ultima_conversacion_${ts}.md"

cat > "${out}" <<EOF2
# Ultima conversacion

Fecha/hora: ${human}

## Resumen
- 

## Decisiones
- 

## Cambios realizados
- 

## Pendientes
- 

## Proximos pasos
- 
EOF2

echo "Generado: ${out}"

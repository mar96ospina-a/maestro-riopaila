# maestro-riopaila

Maestro de Suertes de Riopaila y Castilla Agrícola: PWA estática (GitHub Pages)
que consulta todo el mundo en campo. La fuente de verdad es **`maestro.csv`**
(delimitado por `;`, con la columna `COORDENADAS` que enlaza a Rio Map).

## Relación con Rio Map

Rio Map (repo `agrocontrol-campo`) mantiene una copia del maestro que **debe ser
espejo de este CSV**. Cada push a `main` que toque `maestro.csv` dispara el
workflow **Avisar a Rio Map** (`.github/workflows/avisar-riomap.yml`), que
notifica a Rio Map para que regenere su maestro y abra el PR de sincronización.

- Requiere el secreto **`RIOMAP_DISPATCH_TOKEN`** (Settings → Secrets → Actions):
  un PAT fine-grained con permisos *Contents* y *Pull requests* sobre
  `agrocontrol-campo`.
- Sin el secreto el workflow no falla: Rio Map se sincroniza igual en su corrida
  diaria (06:00 Colombia, lunes a viernes).

El sitio se sigue publicando desde `main` con GitHub Pages; este workflow no lo
toca.

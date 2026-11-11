# Maestro de Suertes — Riopaila / Castilla

PWA estática **offline-first** que consultan los ingenieros y supervisores en campo.
Muestra el maestro de suertes (caña) y el histórico de cortes ZQM101, y enlaza cada
suerte a su ubicación en **Rio Map** por coordenadas.

- **Producción:** https://juancarloszuluagaranzon-afk.github.io/maestro-riopaila/
- **Repo:** https://github.com/juancarloszuluagaranzon-afk/maestro-riopaila (rama `main`)
- **Despliegue:** GitHub Pages sirve `main` directamente. **Push a `main` = publicar.**
  No hay paso de build. El único workflow, `avisar-riomap.yml`, avisa a Rio Map cuando cambia
  `maestro.csv` (Rio Map mantiene un espejo del maestro).

## Arquitectura

Sin build, sin dependencias, sin `package.json`. Todo es HTML/CSS/JS plano servido tal cual,
**incluidos Tailwind y las fuentes**, que viven en `vendor/` (ver la regla 1 abajo).

| Archivo | Rol |
|---|---|
| `index.html` | Portada. Selección de empresa, registro del SW, prompt de instalación PWA. |
| `maestro.html` | **La aplicación completa** (~3.300 líneas: HTML + CSS + JS inline). |
| `service-worker.js` | Caché offline: caché primero para todo el origen (ver regla 2). |
| `manifest.json` | Manifiesto PWA. |
| `maestro.csv` | Datos del maestro de suertes. |
| `zqm.csv` | Datos del histórico de cortes (ZQM101). |
| `icon-192/512.png`, `logo-riopaila.png`, `logo-castilla.png` | Assets. |
| `vendor/` | Tailwind y las fuentes, servidos desde el propio origen. |

Los CSV se actualizan subiéndolos al repo. No hay backend ni base de datos.

### Importar el maestro oficial

Planeación y Control manda un `.xlsx` (p. ej. `maestro 30092026.xlsx`): un reporte con
títulos arriba, ~96 columnas de trabajo interno y los encabezados reales más abajo.

```bash
python tools/importar_maestro.py "C:/ruta/maestro DDMMAAAA.xlsx"
python tools/recalcular_coordenadas.py            # obligatorio: el importador deja COORDENADAS vacía
python tools/recalcular_coordenadas.py --verificar # debe decir "fuera de su propia suerte: 0"
```

El importador toma las 19 columnas de la app en su orden, aplica los formatos del CSV
(fechas `d/MM/yyyy`, toneladas y TCH enteros, área y edad con 2 decimales), **filtra las
filas `EMPRESA = BENG`** y **conserva `TCH ANTERIOR` / `TCHM ANTERIOR`** del CSV anterior,
porque el oficial no las trae. Si el reporte cambia de estructura, el script aborta en vez
de escribir columnas corridas: valida que cada índice de `MAPA` tenga el encabezado
esperado.

**Antes de publicar, compara contra lo que está publicado.** El oficial va por detrás de
los ajustes que pide el usuario y los revierte en silencio. En la importación del
30-sep-2026 revertía 158 suertes de técnico agrícola (cambios pedidos dos días antes) y
3 cortes de Riopaila registrados el 22-23 de septiembre. Revisa al menos:

```bash
git diff --stat maestro.csv     # y el detalle por columna antes de confirmar
```

técnico agrícola, responsable de zona, fecha y número de corte, y suertes que desaparecen.

**Al subir un `maestro.csv` nuevo, actualiza también `CONFIG.dataUpdated` y
`CONFIG.dataUpdatedShort`** en `maestro.html`: es la fecha de los datos que se muestra
en el encabezado, junto a la versión. No la confundas con la versión de la app — una
cambia cuando el ingenio manda datos, la otra cuando cambia el código.

Las exportaciones traen a veces fechas como **número de serie de Excel** (`46260` en vez
de `26/08/2026`), mezcladas con fechas normales en la misma columna. No hay que
convertirlas: `parseDate` y `formatDateDisplay` ya las interpretan.

**Quita las filas con `EMPRESA = BENG`.** Son cultivos de frutales, no caña, y no
pertenecen a este maestro. La exportación del ingenio las incluye, así que hay que
filtrarlas en cada actualización:

```bash
python -c "
import io
ls=io.open('maestro.csv',encoding='utf-8-sig',newline='').read().split('\r\n')
i=ls[0].split(';').index('EMPRESA')
out=[ls[0]]+[l for l in ls[1:] if l.strip() and l.split(';')[i].strip()!='BENG']
io.open('maestro.csv','w',encoding='utf-8',newline='').write('﻿'+'\r\n'.join(out)+'\r\n')
print(len(out)-1,'filas')"
```

Las únicas empresas válidas son `RIOP`, `CAST` y `CAUC`. Si aparece otra, no la verá
nadie: la portada solo abre `?empresa=RIOP` y `?empresa=CAST,CAUC`.

**Vuelve a agregar `TCH ANTERIOR` y `TCHM ANTERIOR`.** No vienen en la exportación del
ingenio; salen de un Excel aparte (Ubic Técnica, TCH, TCHM del último corte de cada suerte,
p. ej. `~/Documents/tch anterior.xlsx`). El script las inserta después de `TCH PPTO`, o
las actualiza si ya existen, y es idempotente:

```bash
python tools/tch_anterior.py "C:/Users/Agr349/Documents/tch anterior.xlsx"
```

El Excel repite suertes con valores de dos cosechas distintas (sep-2026: 18 casos). El
script se queda con el que coincide con el **último corte en `zqm.csv`**; si ninguno
coincide, con la fila de más abajo. Ojo con las suertes recién cortadas: en sep-2026, al
menos 62 de las cortadas desde julio mostraban el TCH de la cosecha de 2025, es decir la
anterior a la recién hecha, porque el dato de la cosecha nueva todavía no estaba cerrado.

**`TCH RANDOM FOREST`: llénala después de cada corrida mensual del Estimador TCH.** Es el
TCH estimado que muestra el visor "Modelo predictivo de TCH · Random Forest" (ya ajustado
con el factor de campaña). Sale de `~/tch-dashboard/data/estimados.json`, que escribe
`tch-motor/scripts/mensual.py` el día 2 de cada mes. Va después de `TCHM ANTERIOR`, con 1
decimal; el script es idempotente:

```bash
python tools/tch_random_forest.py                     # o la ruta de otro estimados.json
```

- Solo llena la suerte si el estimado es de la caña que el maestro tiene creciendo: misma
  soca que `NUMERO DE CORTE` y ningún corte posterior a la fecha de la corrida.
- Quedan vacías las suertes sin estimado: menos de 4 meses, sin polígono en el mapa,
  renovación u otros usos.
- El importador la conserva, salvo en las suertes que traen un corte nuevo.
- El total es el TCH ponderado por área de las suertes con dato.
- El motor lee este mismo `maestro.csv` publicado para sacar la edad y la soca. Por eso,
  importa el maestro oficial **antes** de la corrida mensual cuando se pueda.

**Recalcula `COORDENADAS` después de cada importación. Nunca uses la del ingenio.**
La exportación trae esa columna pegada como bloque sobre una lista con suertes nuevas
intercaladas, así que queda **corrida**: cada suerte nueva empuja todas las coordenadas
de abajo una fila. El 8-sep-2026 se publicó así y 1.018 suertes (67%) llevaban a otra
suerte en Rio Map — todo Riopaila iba 25 filas desplazado (3501-110 abría 3501-350).
Los valores parecían correctos porque eran coordenadas reales… de otra suerte.

```bash
python tools/recalcular_coordenadas.py              # regenera desde la geometría de Rio Map
python tools/recalcular_coordenadas.py --verificar  # debe decir "fuera de su propia suerte: 0"
```

Lee `~/agrocontrol-campo/public/data/tablones_{riopaila,castilla}.geojson` (cambia la ruta
con `--geo`). Cada punto queda garantizado dentro de su propio polígono: promedio de los
tablones; si ese promedio cae en un camino entre tablones, el tablón más grande; si no, un
punto interior. Las suertes sin geometría quedan vacías ("Sin coordenada") — preferible a
un enlace que lleve a otra suerte. La exportación usa `0` para "sin coordenada"; la app lo
trata igual que vacío.

### Dos vistas en una sola UI

`maestro.html` define `VIEWS = { maestro, zqm }`. Cada vista tiene su propio objeto de
estado (`makeViewState()`: filas, filtros, orden, página). `STATE` es un **alias** a la
vista activa; `switchView(key)` cambia el alias y reconstruye la UI desde el estado
guardado de la vista destino. Cada vista declara su CSV, columnas fijas (`stickyCols`),
filtros, procesador de filas y renderizador del modal.

Solo `maestro` tiene `totalsConfig` (fila de totales declarativa: `sum`, `weightedAvg`,
`ratio`). ZQM no muestra totales.

### Alcance por empresa

`index.html` abre la app con `?empresa=RIOP` (Riopaila) o `?empresa=CAST,CAUC` (Castilla,
que incluye las suertes CAUC). La vista Maestro queda restringida a esos códigos de la
columna `EMPRESA`. **Sin el parámetro, Maestro no muestra filas** y pide elegir empresa.
ZQM no tiene columna `EMPRESA` y nunca se filtra por empresa.

### Enlace a Rio Map

La columna `COORDENADAS` (`"lat,lon"`) se convierte en un enlace 📍 en la tabla y en un
botón en el modal de detalle:

```
https://riomap.vercel.app/mapa?p={planta}&lat={lat}&lon={lon}&n=Suerte {suerte}
```

`p` = `riopaila` si `EMPRESA` es `RIOP`, si no `castilla`. Coordenadas mal formadas o
vacías muestran "Sin coordenada" en vez de un enlace roto. La columna la genera
`tools/recalcular_coordenadas.py` (ver arriba), no la exportación del ingenio.

### Lectura de CSV

`parseCsvText` es deliberadamente tolerante porque los archivos vienen de exportaciones
de SAP/Excel/Sheets con formatos inconsistentes: autodetecta separador (`;`, tabulador,
coma), maneja ANSI y UTF-8, normaliza encabezados (`normalizeHeader`) y neutraliza
sentinelas de error (`#N/D`, `#REF!`, `#DIV/0!`, …) vía `ERROR_VALUES`.

Los `match:` de los filtros toleran variantes de codificación a propósito
(p. ej. `AÑO` / `ANO` / `AÃO`, `Ubic Técnica` / `Ubic Tecnica`). **No los "simplifiques".**

## Reglas del proyecto

### 1. Nada de recursos externos

**Ningún `<script src="http...">`, `<link href="http...">`, CDN, webfont ni API externa.**
Todo lo que la app necesita para pintar tiene que estar en el repo y en `CRITICAL_URLS`.

Esto no es purismo: hasta v2.3.x, Tailwind y las fuentes venían de CDN. El service worker
no las veía siquiera (ignora todo lo que no sea del propio origen), así que sin señal la
app se quedaba sin CSS. Y sin Tailwind la clase `.hidden` deja de existir, o sea que el
spinner, el mensaje de error, el banner de offline, el drawer y los modales aparecen
**todos a la vez, encimados**. No se veía "sin estilos": se veía rota.

Peor aún, el CSS de Google Fonts se sirve con `Cache-Control: max-age=86400`. Caducaba
cada 24 h, y por eso fallaba justo *la primera apertura del día* sin señal.

### 2. Caché primero, siempre

La app abre desde caché; la red solo refresca en segundo plano (`staleWhileRevalidate`).
Nunca al revés.

En campo la conexión rara vez está limpiamente ausente: es una barra que no enruta. Ahí
`fetch()` **no rechaza rápido**, se queda esperando el timeout del sistema. Una estrategia
"red primero" deja la pantalla en blanco decenas de segundos aunque la respuesta esté en
caché — que era exactamente el síntoma en v2.3.x. Además `navigator.onLine` devuelve
`true` en ese estado, así que no te fíes de él para decidir nada importante.

Por el mismo motivo `install` es **todo o nada**: si algún recurso crítico falla, la
instalación se aborta y se sigue sirviendo la versión anterior. Antes cacheaba lo que
podía, y como `activate` borra la caché previa, una instalación a medias con señal
intermitente dejaba al usuario sin app.

### 3. La versión vive en CINCO lugares — súbelos juntos

Un release desincronizado deja a los usuarios con caché vieja y sin forma de actualizar:

| Archivo | Símbolo |
|---|---|
| `service-worker.js` | `CACHE_VERSION` |
| `index.html` | `APP_VERSION` |
| `index.html` | texto visible `v2.5.2 • 2026 Edition` al pie |
| `maestro.html` | `CONFIG.version` |
| `maestro.html` | `<span id="appVersion">` en el encabezado |

Versión actual: **v2.5.2**. Comprobación rápida — deben salir 5 coincidencias iguales:

```bash
grep -oh "v2\.[0-9]*\.[0-9]*" index.html maestro.html service-worker.js | sort | uniq -c
```

### 4. Temporadas: solo el acento, nunca el significado

Hay un tema de Halloween que se enciende **solo por fecha, del 24 de octubre al 2 de
noviembre**, cualquier año (`aplicarTemporada()`, en el `<head>` de `index.html` y
`maestro.html` para que la clase `temporada-halloween` exista antes del primer pintado y no
haya parpadeo). No hay interruptor ni nada que recordar apagar.

Lo que cambia: el acento teal pasa a ámbar (título, encabezados de la tabla, enlace a Rio
Map), los tres blobs de la portada pasan a calabaza y violeta, y aparece una calabaza
dibujada en SVG junto al título.

Lo que **no** cambia, y es la regla: los colores que significan algo. Verde de éxito, ámbar
de aviso, rojo de error, teal de la empresa activa y de la navegación. Si el acento de
temporada se comiera esos, la app diría cosas que no son.

Los tonos están escogidos por contraste sobre cada fondo, porque esto se lee a pleno sol:
`#fbbf24` en oscuro (10,7:1) y `#b45309` en claro (4,6:1 sobre el encabezado y 5,0:1 sobre
blanco). Si algún día se agrega otra temporada, el mismo molde sirve: una clase en `<html>`,
solo tokens de acento, y los colores de estado quietos.

### 5. Un solo archivo, sin framework

`maestro.html` es intencionalmente monolítico para que funcione offline sin build. Mantén
el estilo existente: funciones planas, `STATE` compartido, sin dependencias nuevas.

## Desarrollo local

El SW y el `fetch` de los CSV **no funcionan con `file://`**. Sirve la carpeta por HTTP:

```bash
python -m http.server 3600 --directory "C:/Users/Agr349/maestro-riopaila"
```

Luego abre http://localhost:3600 .

No hay tests ni linter. La verificación es manual: cargar ambas vistas, filtrar, ordenar,
abrir un detalle, exportar CSV y probar en modo avión.

### Probar el service worker en la subruta real

En local la app corre en la raíz (`/`), pero en producción vive bajo `/maestro-riopaila/`.
Un SW que asuma la raíz **parece funcionar en local y falla publicado** (así se coló el bug
corregido en v2.3.3). **Prueba siempre así antes de publicar un cambio en el SW.**
Para reproducir la ruta real, sirve desde el directorio *padre*:

```bash
python -m http.server 3601 --directory "C:/Users/Agr349"
```

y abre http://localhost:3601/maestro-riopaila/ . Comprobación de que el precache entró:

```js
caches.open('riopaila-maestro-v2.4.0').then(c => c.keys()).then(k => console.log(k.length, k.map(r => r.url)))
```

Deben aparecer **16** entradas, todas bajo `/maestro-riopaila/`. Y cero peticiones a otro
origen:

```js
performance.getEntriesByType('resource').filter(e => !e.name.startsWith(location.origin))
```

Luego **apaga el servidor** y navega a una página que no hayas abierto. Debe cargar completa
y con estilos. Medido así en v2.4.0: 277 ms hasta `load`, HTML y CSV a 4 y 3 ms desde caché.

## Fuentes e íconos

`vendor/fonts.css` está escrito a mano y apunta a los `.woff2` locales. Manrope es variable
(un solo archivo cubre 300–800). Material Symbols va **subseteada a los íconos que usa la
app** — 24 KB en vez de ~200 KB.

Si agregas un ícono nuevo, hay que regenerar ese subset o **saldrá como texto** (se ve la
palabra `arrow_upward` en vez de la flecha). Hoy son 43. El grep de abajo solo encuentra
los escritos literalmente en el HTML; **no ve los que asigna el JS**, y así se perdieron 15
en v2.4.0: las flechas de orden (`ind.textContent = … 'arrow_upward' : 'arrow_downward'`),
los 13 de las tarjetas del detalle de ZQM (`kpiCard('water_drop', …)`) y el ícono de tema.
Revisa también esos puntos. La lista literal sale de:

```bash
grep -oh 'material-symbols-outlined[^>]*>[[:space:]]*[a-z0-9_]*' index.html maestro.html | grep -o '[a-z0-9_]*$' | sort -u
```

Con esa lista, pide el `.woff2` a Google conservando los ejes variables (de ellos depende el
`font-variation-settings: 'FILL' 1` de la app) y guárdalo como `vendor/material-symbols.woff2`:

```
https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&icon_names=<lista,separada,por,comas>
```

Ese CSS devuelve la URL del binario; hay que descargarla con un User-Agent moderno o Google
responde con TTF en vez de WOFF2.

Comprobación en el navegador — un ícono dibujado mide ~24 px; si sale como texto mide mucho más:

```js
[...document.querySelectorAll('.material-symbols-outlined')].filter(e => e.getBoundingClientRect().width > 40).map(e => e.textContent)
```

(o crea un `<span class="material-symbols-outlined">` por cada nombre y mide su ancho). Al
cambiar la fuente, **sube la versión**: el `.woff2` está en la caché del service worker.

## Contexto de negocio

- **Suerte**: unidad mínima de manejo del cultivo de caña (lote).
- **Corte**: cada cosecha de una suerte; `EDAD HOY MESES` se calcula desde la fecha del
  último corte.
- **TCH**: toneladas de caña por hectárea. En la fila de totales, el TCH se calcula como
  Σtoneladas / Σárea, **no** como promedio de los TCH por fila.
- **Empresas**: `RIOP` (Riopaila Agrícola), `CAST` / `CAUC` (Castilla Agrícola).

### Registrar un corte

Llega como una lista "Validación Sec-Ste RIOCAS" con la suerte y la fecha fin. Por cada
suerte hay que tocar **tres** columnas:

| Columna | Qué se hace |
|---|---|
| `FECHA DE ULTIMO CORTE` | la fecha fin reportada |
| `NUMERO DE CORTE` | +1 |
| `FECHA DEL PROXIMO CORTE` | último corte **+ el ciclo que indique quien manda la lista** |

**El ciclo no es fijo: pregúntalo si no viene.** El lote del 8-sep-2026 se pidió a 12,5 meses
(12 meses de calendario + 15 días = 380 días) y el del 14-sep-2026 a 12 meses (365 días).

`EDAD HOY MESES` no se toca: la app la recalcula.

Antes de aplicar, dos comprobaciones obligatorias:

1. **Que la suerte exista.** Han llegado códigos que no están (segmentos nuevos, suertes
   de otra finca, series enteras ausentes como la 2139).
2. **Que no esté ya registrada.** Las listas se solapan: el lote del 14-sep repetía 11
   suertes del 8-sep, con fechas que diferían 0–2 días. Si el último corte actual está a
   pocos días de la fecha nueva, es **la misma cosecha**: sumarle +1 otra vez deja el
   número de corte inflado. Un corte legítimo llega 9–16 meses después del anterior.
   Con esas se decidió dejarlas como estaban; ante la duda, pregunta.

El formato de fecha del CSV es **día sin cero y mes con cero**: `3/09/2026`, `21/09/2027`.

"""Recalcula la columna COORDENADAS de maestro.csv desde la geometría de tablones.

Por qué existe: la exportación del ingenio trae COORDENADAS pegada como bloque
sobre una lista con suertes nuevas intercaladas, así que queda corrida (el
8-sep-2026, 1.018 suertes apuntaban a otra suerte; todo Riopaila iba 25 filas
desplazado). Esa columna NO es confiable: se regenera siempre desde la geometría
de Rio Map (agrocontrol-campo/public/data/tablones_*.geojson).

Punto elegido por suerte, garantizado dentro de su propio polígono:
  1. promedio del lat/lon de sus tablones, si cae dentro de la suerte;
  2. si cae en un camino/canal entre tablones: el lat/lon del tablón más grande
     (ha_oficial) que esté dentro de su polígono;
  3. si no: un punto interior del polígono más grande (barrido horizontal).
Suertes sin geometría quedan con COORDENADAS vacía: mejor "Sin coordenada" que
un enlace que lleva a otra suerte.

Uso (desde la raíz del repo):
  python tools/recalcular_coordenadas.py            # reescribe COORDENADAS
  python tools/recalcular_coordenadas.py --verificar  # solo audita; sale con 1 si hay errores
Solo toca la columna COORDENADAS; conserva BOM, separador ';' y fin de línea CRLF.
"""
import argparse, io, json, sys
from collections import defaultdict
from pathlib import Path

GEO_DEFECTO = [
    Path.home() / 'agrocontrol-campo/public/data/tablones_riopaila.geojson',
    Path.home() / 'agrocontrol-campo/public/data/tablones_castilla.geojson',
]


def dentro_anillo(x, y, anillo):
    ins, j = False, len(anillo) - 1
    for i in range(len(anillo)):
        xi, yi = anillo[i][0], anillo[i][1]
        xj, yj = anillo[j][0], anillo[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-15) + xi:
            ins = not ins
        j = i
    return ins


def dentro_poligono(x, y, pol):  # pol = [exterior, huecos...]
    return dentro_anillo(x, y, pol[0]) and not any(dentro_anillo(x, y, h) for h in pol[1:])


def area(anillo):
    return abs(sum(anillo[i][0] * anillo[i - 1][1] - anillo[i - 1][0] * anillo[i][1]
                   for i in range(len(anillo)))) / 2


def punto_interior(pol):
    """Punto medio del tramo más ancho de un barrido horizontal a media altura."""
    ys = [c[1] for c in pol[0]]
    for frac in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
        y = min(ys) + (max(ys) - min(ys)) * frac
        xs = []
        for anillo in pol:
            for i in range(len(anillo)):
                (x1, y1), (x2, y2) = anillo[i - 1][:2], anillo[i][:2]
                if (y1 > y) != (y2 > y):
                    xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        tramos = [(xs[k], xs[k + 1]) for k in range(0, len(xs) - 1, 2)]
        if tramos:
            a, b = max(tramos, key=lambda t: t[1] - t[0])
            if dentro_poligono((a + b) / 2, y, pol):
                return (a + b) / 2, y
    return None


def cargar_geometria(rutas):
    tablones = defaultdict(list)  # suerte -> [(ha, lat, lon, [poligonos])]
    for ruta in rutas:
        for ft in json.load(io.open(ruta, encoding='utf-8'))['features']:
            p, g = ft['properties'], ft['geometry']
            pols = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
            tablones[str(p['sec_ste']).strip()].append(
                (float(p.get('ha_oficial') or 0), p.get('lat'), p.get('lon'), pols))
    return tablones


def punto_de_suerte(tabs):
    # Los candidatos se prueban ya redondeados a 6 decimales, que es como se
    # guardan: un punto a centímetros del borde puede quedar fuera al redondear.
    pols = [pl for t in tabs for pl in t[3]]
    en_suerte = lambda lat, lon: any(dentro_poligono(round(lon, 6), round(lat, 6), pl) for pl in pols)
    con_punto = [t for t in tabs if t[1] is not None and t[2] is not None]
    if con_punto:
        lat = sum(t[1] for t in con_punto) / len(con_punto)
        lon = sum(t[2] for t in con_punto) / len(con_punto)
        if en_suerte(lat, lon):
            return lat, lon, 'promedio'
    for t in sorted(con_punto, key=lambda t: -t[0]):
        if any(dentro_poligono(round(t[2], 6), round(t[1], 6), pl) for pl in t[3]):
            return t[1], t[2], 'tablon mayor'
    for pl in sorted(pols, key=lambda pl: -area(pl[0])):
        p = punto_interior(pl)
        if p and dentro_poligono(round(p[0], 6), round(p[1], 6), pl):
            return p[1], p[0], 'interior'
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--maestro', default='maestro.csv')
    ap.add_argument('--geo', nargs='+', default=[str(p) for p in GEO_DEFECTO])
    ap.add_argument('--verificar', action='store_true', help='solo auditar, no escribir')
    a = ap.parse_args()

    tablones = cargar_geometria(a.geo)
    raw = io.open(a.maestro, encoding='utf-8-sig', newline='').read()
    lineas = raw.split('\r\n')
    h = lineas[0].split(';')
    iS, iC = h.index('SUERTE'), h.index('COORDENADAS')

    metodos, errores, vacias, cambios = defaultdict(int), [], [], 0
    sin_geometria = []
    for n, l in enumerate(lineas[1:], start=1):
        if not l.strip():
            continue
        c = l.split(';')
        s = c[iS].strip()
        tabs = tablones.get(s)
        if a.verificar:
            try:  # la exportación pone '0' donde no hay coordenada; la app lo trata como vacía
                lat, lon = map(float, c[iC].strip().split(','))
            except ValueError:
                vacias.append(s); continue
            if not tabs:
                # La suerte no está en la cartografía (re-suerteo, o shapefile viejo) y
                # conserva una coordenada de una versión anterior. No es un error: no hay
                # polígono contra el cual comprobarla. Se cuenta aparte para que un error
                # de verdad no se pierda entre estas.
                sin_geometria.append(s)
            elif not any(dentro_poligono(lon, lat, pl) for t in tabs for pl in t[3]):
                errores.append(s)
            continue
        r = punto_de_suerte(tabs) if tabs else None
        actual = c[iC].strip()
        if r:
            nuevo = f'{r[0]:.6f},{r[1]:.6f}'
            metodos[r[2]] += 1
        elif ',' in actual:
            # Sin cartografía pero con coordenada previa: se CONSERVA, no se borra.
            # La cartografía de septiembre de 2026 dejó fuera 79 suertes activas de
            # Castilla y Cauca; vaciarlas les quitaba el enlace a Rio Map sin que
            # nada hubiera cambiado en campo.
            nuevo = actual
            sin_geometria.append(s)
        else:
            nuevo = ''
            vacias.append(s)
        if c[iC] != nuevo:
            c[iC] = nuevo
            lineas[n] = ';'.join(c)
            cambios += 1

    total = sum(1 for l in lineas[1:] if l.strip())
    if a.verificar:
        print(f'{total} suertes | fuera de su propia suerte: {len(errores)} | '
              f'sin coordenada: {len(vacias)} | con coordenada conservada, sin cartografía: {len(sin_geometria)}')
        if sin_geometria:
            print('  sin cartografía:', ', '.join(sin_geometria[:20]) + (' ...' if len(sin_geometria) > 20 else ''))
        if errores:
            print('  MAL:', ', '.join(errores[:30]) + (' ...' if len(errores) > 30 else ''))
        sys.exit(1 if errores else 0)

    io.open(a.maestro, 'w', encoding='utf-8', newline='').write('﻿' + '\r\n'.join(lineas))
    print(f'{total} suertes | COORDENADAS cambiadas: {cambios} | '
          + ' | '.join(f'{k}: {v}' for k, v in metodos.items())
          + f' | conservadas sin cartografía: {len(sin_geometria)}'
          + f' | sin coordenada: {len(vacias)}')
    if sin_geometria:
        print('  conservadas (no están en la cartografía):', ', '.join(sin_geometria))
    if vacias:
        print('  sin coordenada:', ', '.join(vacias))


if __name__ == '__main__':
    main()

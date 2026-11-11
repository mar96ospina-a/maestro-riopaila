"""Agrega o actualiza la columna "TCH RANDOM FOREST" de maestro.csv.

Fuente: estimados.json del Estimador TCH (el visor "Modelo predictivo de TCH · Random
Forest"), que escribe cada mes tch-motor/scripts/mensual.py. Es el mismo TCH que muestra
el visor: el del modelo ajustado con el factor de la campaña.

Solo se llena si el estimado es de la caña que el maestro tiene creciendo:
  - la soca del estimado es el NUMERO DE CORTE del maestro, y
  - el maestro no registra un corte posterior a la fecha de la corrida.
Si no, el estimado era de caña ya cosechada y la celda queda vacía. También quedan
vacías las suertes sin estimado: menos de 4 meses, sin polígono en el mapa, renovación
u otros usos.

La columna va justo después de "TCHM ANTERIOR" (o de "TCH PPTO" si no existe); si ya
existe se actualiza en su lugar. TCH con 1 decimal. Conserva BOM, separador ';' y CRLF.
Hay que volver a correrlo después de cada corrida mensual del estimador.

Uso (desde la raíz del repo):
  python tools/tch_random_forest.py                          # ~/tch-dashboard/data/estimados.json
  python tools/tch_random_forest.py ruta/estimados.json
"""
import argparse, datetime, io, json, os

COL, DESPUES_DE = 'TCH RANDOM FOREST', ('TCHM ANTERIOR', 'TCH PPTO')
ESTIMADOS = os.path.join(os.path.expanduser('~'), 'tch-dashboard', 'data', 'estimados.json')


def fecha(s):
    try:
        d, m, a = (int(x) for x in s.strip().split('/'))
        return datetime.date(a, m, d)
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('estimados', nargs='?', default=ESTIMADOS)
    ap.add_argument('--maestro', default='maestro.csv')
    a = ap.parse_args()

    est = {e['sec_ste']: e for e in json.load(io.open(a.estimados, encoding='utf-8'))}
    corridas = {e['fecha_corrida'] for e in est.values()}
    corrida = datetime.date.fromisoformat(max(corridas))

    lineas = io.open(a.maestro, encoding='utf-8-sig', newline='').read().split('\r\n')
    h = lineas[0].split(';')
    insertar = None
    if COL not in h:
        insertar = next(h.index(c) for c in DESPUES_DE if c in h) + 1
        h.insert(insertar, COL)
        lineas[0] = ';'.join(h)
    iS, iC, iU, iV = h.index('SUERTE'), h.index('NUMERO DE CORTE'), h.index('FECHA DE ULTIMO CORTE'), h.index(COL)

    con = otra_soca = cortada = 0
    vistas = set()
    for n, l in enumerate(lineas[1:], start=1):
        if not l.strip():
            continue
        c = l.split(';')
        if insertar is not None:
            c.insert(insertar, '')
        s = c[iS].strip()
        e, valor = est.get(s), ''
        if e is not None:
            vistas.add(s)
            ult = fecha(c[iU])
            if e.get('soca') is not None and c[iC].strip() and int(c[iC]) != int(e['soca']):
                otra_soca += 1
            elif ult is not None and ult > corrida:
                cortada += 1
            elif e.get('tch_estimado') is not None:
                valor = f"{e['tch_estimado']:.1f}"
                con += 1
        c[iV] = valor
        lineas[n] = ';'.join(c)

    io.open(a.maestro, 'w', encoding='utf-8', newline='').write('﻿' + '\r\n'.join(lineas))
    print(f'{"columna insertada" if insertar is not None else "columna actualizada"}: {COL} | corrida {corrida} | '
          f'con dato: {con} | vacías por soca distinta: {otra_soca} | por corte después de la corrida: {cortada} | '
          f'estimados que no están en el maestro: {len(set(est) - vistas)}')


if __name__ == '__main__':
    main()

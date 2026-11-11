"""Agrega o actualiza las columnas "TCH ANTERIOR" y "TCHM ANTERIOR" de maestro.csv.

Fuente: un Excel con tres columnas — Ubic Técnica, TCH, TCHM — del último corte
de cada suerte (p. ej. "tch anterior.xlsx", hoja "ultimo"). La exportación del
ingenio NO trae estas columnas: hay que volver a correr esto en cada importación.

Duplicados: el Excel trae a veces la misma suerte dos veces con valores de dos
cosechas distintas (sep-2026: 18 casos). Se resuelve con el histórico zqm.csv:
gana el valor que coincide con el ÚLTIMO corte registrado de esa suerte. Si
ninguno coincide, gana la fila de más abajo del Excel (en los 18 casos
verificados el último corte siempre era la de más abajo).

Las columnas se insertan justo después de "TCH PPTO" para comparar a la vista;
si ya existen se actualizan en su lugar. TCH con 1 decimal, TCHM con 2.
Suertes sin dato quedan vacías. Conserva BOM, separador ';' y CRLF.

Uso (desde la raíz del repo):
  python tools/tch_anterior.py "C:/Users/Agr349/Documents/tch anterior.xlsx"
"""
import argparse, io, sys, unicodedata
from collections import defaultdict

COL_TCH, COL_TCHM, DESPUES_DE = 'TCH ANTERIOR', 'TCHM ANTERIOR', 'TCH PPTO'


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode()
    return ' '.join(s.upper().split())


def num(v):
    if v is None or str(v).strip() == '':
        return None
    try:
        return float(str(v).strip().replace(',', '.'))
    except ValueError:
        return None


def leer_excel(ruta):
    import openpyxl
    ws = openpyxl.load_workbook(ruta, data_only=True, read_only=True).worksheets[0]
    filas = list(ws.iter_rows(values_only=True))
    h = [norm(x) for x in filas[0]]
    iU = next(i for i, x in enumerate(h) if x.startswith('UBIC') or x == 'SUERTE')
    iT, iTM = h.index('TCH'), h.index('TCHM')
    datos = defaultdict(list)  # suerte -> [(fila, tch, tchm)]
    for n, r in enumerate(filas[1:], start=2):
        if r[iU] is None:
            continue
        t, tm = num(r[iT]), num(r[iTM])
        if t is None or tm is None or t <= 0 or tm <= 0:
            continue
        datos[str(r[iU]).strip()].append((n, t, tm))
    return datos


def ultimo_corte_zqm(ruta):
    try:
        raw = io.open(ruta, encoding='utf-8-sig', newline='').read().replace('\r\n', '\n')
    except FileNotFoundError:
        return {}
    ls = [l for l in raw.split('\n') if l.strip()]
    h = [norm(x) for x in ls[0].split(';')]
    iA = next(i for i, x in enumerate(h) if x in ('ANO', 'AO') or x.startswith('A') and len(x) <= 3)
    iU = next(i for i, x in enumerate(h) if x.startswith('UBIC'))
    iM, iC, iT, iTM = h.index('MES'), h.index('CORTE'), h.index('TCH'), h.index('TCHM')
    ult = {}
    for l in ls[1:]:
        c = l.split(';')
        try:
            clave = (int(c[iA]), int(c[iM]), int(float(c[iC].replace(',', '.'))))
        except (ValueError, IndexError):
            continue
        s = c[iU].strip()
        if s not in ult or clave > ult[s][0]:
            ult[s] = (clave, num(c[iT]), num(c[iTM]))
    return ult


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('xlsx')
    ap.add_argument('--maestro', default='maestro.csv')
    ap.add_argument('--zqm', default='zqm.csv')
    a = ap.parse_args()

    datos, ult = leer_excel(a.xlsx), ultimo_corte_zqm(a.zqm)
    elegido, resueltos = {}, []
    for s, v in datos.items():
        if len(v) == 1:
            elegido[s] = v[0]; continue
        z = ult.get(s)
        match = [x for x in v if z and z[1] is not None and abs(x[1] - z[1]) < 0.05
                 and (z[2] is None or abs(x[2] - z[2]) < 0.05)]
        elegido[s] = match[-1] if match else max(v)  # max = fila más abajo
        resueltos.append((s, 'zqm' if match else 'fila más abajo', elegido[s][0], [x[0] for x in v]))

    raw = io.open(a.maestro, encoding='utf-8-sig', newline='').read()
    lineas = raw.split('\r\n')
    h = lineas[0].split(';')
    if COL_TCH not in h:
        k = h.index(DESPUES_DE) + 1
        h[k:k] = [COL_TCH, COL_TCHM]
        insertar = k
    else:
        insertar = None
    lineas[0] = ';'.join(h)
    iS, iT, iTM = h.index('SUERTE'), h.index(COL_TCH), h.index(COL_TCHM)

    con = sin = 0
    for n, l in enumerate(lineas[1:], start=1):
        if not l.strip():
            continue
        c = l.split(';')
        if insertar is not None:
            c[insertar:insertar] = ['', '']
        e = elegido.get(c[iS].strip())
        c[iT], c[iTM] = (f'{e[1]:.1f}', f'{e[2]:.2f}') if e else ('', '')
        con, sin = (con + 1, sin) if e else (con, sin + 1)
        lineas[n] = ';'.join(c)

    io.open(a.maestro, 'w', encoding='utf-8', newline='').write('\ufeff' + '\r\n'.join(lineas))
    print(f'{"columnas insertadas" if insertar is not None else "columnas actualizadas"} después de {DESPUES_DE} | '
          f'con dato: {con} | sin dato: {sin} | suertes del Excel que no están en el maestro: '
          f'{len(set(elegido) - {l.split(";")[iS].strip() for l in lineas[1:] if l.strip()})}')
    for s, como, fila, filas in resueltos:
        print(f'  duplicada {s}: filas {filas} -> fila {fila} ({como})')


if __name__ == '__main__':
    main()

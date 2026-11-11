"""Convierte el maestro oficial de Planeación y Control (.xlsx) a maestro.csv.

El archivo oficial es un reporte con formato: títulos en las primeras filas,
~96 columnas de trabajo interno y los encabezados reales más abajo. De ahí se
toman solo las 19 columnas que usa la app, en su orden, con los formatos del
CSV (fechas d/MM/yyyy, toneladas y TCH enteros, área y edad con 2 decimales).

Lo que el oficial NO trae y este script conserva del maestro.csv actual:
  - TCH ANTERIOR y TCHM ANTERIOR (vienen de otro Excel; ver tools/tch_anterior.py)
  - TCH RANDOM FOREST (del Estimador TCH; ver tools/tch_random_forest.py), solo si la
    suerte sigue en el mismo NUMERO DE CORTE: si el oficial trae un corte nuevo, ese
    estimado era de la caña cosechada y la celda queda vacía.
  - COORDENADAS: se dejan vacías a propósito. Después de importar hay que correr
    tools/recalcular_coordenadas.py, que las regenera desde la geometría.

Filtra las filas con EMPRESA = BENG (frutales, no caña): el oficial las incluye
y la app no puede mostrarlas.

Uso (desde la raíz del repo):
  python tools/importar_maestro.py "C:/ruta/maestro 30092026.xlsx"
  python tools/importar_maestro.py <xlsx> --salida /tmp/nuevo.csv   # sin sobrescribir
"""
import argparse, datetime, io, re

# columna del CSV -> índice en el oficial (None = no viene en el oficial)
MAPA = [
    ('SUERTE', 0), ('ZONA', 5), ('FINCA', 8), ('AREA NETA HA', 25),
    ('EDAD HOY MESES', 20), ('Zona Agroecologica', 14), ('VARIEDAD', 23),
    ('USO DE LA SUERTE', 16), ('FECHA DE SIEMBRA', 18), ('FECHA DE ULTIMO CORTE', 19),
    ('NUMERO DE CORTE', 21), ('TONELADAS PPTO', 30), ('TCH PPTO', 32),
    ('TCH ANTERIOR', None), ('TCHM ANTERIOR', None), ('TCH RANDOM FOREST', None), ('TONELADAS ESTIMADAS', 37),
    ('RESPONSABLE ZONA', 6), ('TECNICO AGRICOLA RESPONSABLE', 7),
    ('FECHA DEL PROXIMO CORTE', 11), ('EMPRESA', 4), ('COORDENADAS', None),
]
MAPA_IDX = dict(MAPA)
ENTEROS = {'TONELADAS PPTO', 'TCH PPTO', 'TONELADAS ESTIMADAS', 'NUMERO DE CORTE', 'ZONA'}
DOS_DECIMALES = {'AREA NETA HA', 'EDAD HOY MESES'}
CODIGO = re.compile(r'\d{4}-\d{3}')


def celda(col, v):
    if v is None:
        return ''
    if isinstance(v, datetime.datetime):
        return f'{v.day}/{v.month:02d}/{v.year}'
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if col in ENTEROS:
            return str(int(round(v)))
        if col in DOS_DECIMALES:
            return f'{v:.2f}'
        return f'{v:g}'
    s = str(v)
    if ';' in s or '\n' in s or '\r' in s:
        raise SystemExit(f'valor con separador o salto de línea en {col}: {s!r}')
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('xlsx')
    ap.add_argument('--maestro', default='maestro.csv',
                    help='CSV del que se heredan TCH ANTERIOR, TCHM ANTERIOR y TCH RANDOM FOREST')
    ap.add_argument('--salida', default=None, help='por defecto sobrescribe --maestro')
    ap.add_argument('--hoja', default=None,
                    help='hoja a leer; por defecto busca la que tenga SUERTE en la columna A '
                         '(el libro completo de Planeación trae 22 hojas)')
    a = ap.parse_args()

    import openpyxl
    wb = openpyxl.load_workbook(a.xlsx, data_only=True)

    def encabezados(ws):
        """Fila de encabezados de la hoja, o None si no la tiene."""
        for i, r in enumerate(ws.iter_rows(min_row=1, max_row=12, values_only=True)):
            if r and str(r[0] or '').strip().upper() == 'SUERTE':
                return i
        return None

    if a.hoja:
        if a.hoja not in wb.sheetnames:
            raise SystemExit(f'el libro no tiene la hoja {a.hoja!r}. Hojas: {wb.sheetnames}')
        ws = wb[a.hoja]
    else:
        candidatas = [h for h in wb.sheetnames if encabezados(wb[h]) is not None]
        if not candidatas:
            raise SystemExit(f'ninguna hoja tiene SUERTE en la columna A. Hojas: {wb.sheetnames}')
        if len(candidatas) > 1:
            raise SystemExit(f'varias hojas podrían servir ({candidatas}); elige una con --hoja')
        ws = wb[candidatas[0]]
        if len(wb.sheetnames) > 1:
            print(f'hoja: {ws.title}')
    filas = list(ws.iter_rows(values_only=True))
    hdr = encabezados(ws)
    if hdr is None:
        raise SystemExit('no se encontró la fila de encabezados (celda A = SUERTE)')
    # los encabezados del oficial deben estar donde los espera MAPA
    reales = {j: str(filas[hdr][j] or '').replace('\n', ' ').strip().upper() for _, j in MAPA if j is not None}
    for col, j in MAPA:
        if j is not None and col.upper() not in reales[j] and reales[j] not in col.upper():
            raise SystemExit(f'la columna {j} del oficial es {reales[j]!r}, se esperaba {col!r}. '
                             'Cambió el formato del reporte: revisa MAPA.')
    datos = [r for r in filas[hdr + 1:] if r[0] and CODIGO.fullmatch(str(r[0]).strip())]

    # TCH ANTERIOR / TCHM ANTERIOR / TCH RANDOM FOREST (con su NUMERO DE CORTE) del CSV actual
    previo = {}
    try:
        ls = [l for l in io.open(a.maestro, encoding='utf-8-sig', newline='').read().split('\r\n') if l.strip()]
        h = ls[0].split(';')
        iS, iT, iTM, iC = h.index('SUERTE'), h.index('TCH ANTERIOR'), h.index('TCHM ANTERIOR'), h.index('NUMERO DE CORTE')
        iRF = h.index('TCH RANDOM FOREST') if 'TCH RANDOM FOREST' in h else None
        for l in ls[1:]:
            c = l.split(';')
            previo[c[iS].strip()] = (c[iT], c[iTM], c[iRF] if iRF is not None else '', c[iC].strip())
    except (FileNotFoundError, ValueError):
        print('aviso: no se pudo leer TCH ANTERIOR del CSV actual; quedarán vacías')

    salida, beng, sin_tch, rf_vaciado = [';'.join(c for c, _ in MAPA)], 0, 0, 0
    for r in datos:
        if str(r[4] or '').strip() == 'BENG':
            beng += 1
            continue
        s = str(r[0]).strip()
        p = previo.get(s, ('', '', '', ''))
        fila = []
        for col, j in MAPA:
            if col == 'TCH ANTERIOR':
                fila.append(p[0])
            elif col == 'TCHM ANTERIOR':
                fila.append(p[1])
            elif col == 'TCH RANDOM FOREST':
                mismo_corte = p[3] == celda('NUMERO DE CORTE', r[MAPA_IDX['NUMERO DE CORTE']])
                fila.append(p[2] if mismo_corte else '')
                rf_vaciado += bool(p[2]) and not mismo_corte
            elif col == 'COORDENADAS':
                fila.append('')
            else:
                fila.append(celda(col, r[j]))
        if not fila[MAPA.index(('TCH ANTERIOR', None))]:
            sin_tch += 1
        salida.append(';'.join(fila))

    destino = a.salida or a.maestro
    io.open(destino, 'w', encoding='utf-8', newline='').write('\ufeff' + '\r\n'.join(salida) + '\r\n')
    print(f'{destino}: {len(salida)-1} suertes | BENG filtradas: {beng} | sin TCH anterior: {sin_tch} | '
          f'TCH RANDOM FOREST vaciado por corte nuevo: {rf_vaciado}')
    print('FALTA: python tools/recalcular_coordenadas.py   (COORDENADAS quedó vacía)')


if __name__ == '__main__':
    main()

"""Regenera maestro.csv desde el maestro oficial de Planeacion y Control.

FUENTE UNICA DE VERDAD: el maestro oficial del area
  X:\\PLANEACION Y CONTROL\\Soportes Informacion Financiera\\1-Maestro de Suerte\\
  Anio 2026\\Maestro Suertes 2026.xlsx   (hoja MAESTRO)

Este script deja el maestro.csv del sitio de campo 100% conectado con ese
oficial: toma las 18 columnas que vienen del oficial y las escribe tal cual,
y VALIDA los encabezados del oficial antes de escribir: si Planeacion cambia
el formato del reporte, el script se detiene en vez de publicar datos corridos.

Lo que el oficial NO trae, se HEREDA del maestro.csv actual (por codigo de suerte):
  - TCH ANTERIOR, TCHM ANTERIOR  (vienen de otro Excel)
  - TCH RANDOM FOREST            (del Estimador TCH), solo si la suerte sigue en
                                 el mismo NUMERO DE CORTE; si el oficial trae un
                                 corte nuevo ese estimado era de la cania ya
                                 cosechada y la celda queda vacia.
  - COORDENADAS                  la ubicacion fisica no cambia entre versiones.
                                 (Rio Map/agrocontrol-campo recalcula coordenadas
                                 desde la geometria; mientras ese repo no este
                                 disponible, aqui se CONSERVAN las que ya hay.)

Filtra las filas con EMPRESA = BENG (frutales, no cania; el sitio no las muestra).

Uso (desde la raiz del repo):
  python tools/importar_maestro.py "X:/.../Maestro Suertes 2026.xlsx"
  python tools/importar_maestro.py <xlsx> --salida /tmp/nuevo.csv   # sin sobrescribir
  python tools/importar_maestro.py <xlsx> --hoja MAESTRO            # forzar hoja

Historia: el libro oficial trae 23 hojas; la buena es MAESTRO (1521 filas,
encabezado en la fila 5). Hojas como "Detalle1" o "Suertes iniciadas" tambien
tienen SUERTE en la columna A pero son auxiliares, por eso se prefiere MAESTRO.
"""
import argparse, datetime, io, re

# columna del CSV -> indice (0-based) en la hoja MAESTRO del oficial.
# None = no viene del oficial (se hereda del CSV actual, ver arriba).
MAPA = [
    ('SUERTE', 0), ('ZONA', 5), ('FINCA', 8), ('AREA NETA HA', 25),
    ('EDAD HOY MESES', 20), ('Zona Agroecologica', 14), ('VARIEDAD', 23),
    ('USO DE LA SUERTE', 16), ('FECHA DE SIEMBRA', 18), ('FECHA DE ULTIMO CORTE', 19),
    ('NUMERO DE CORTE', 21), ('TONELADAS PPTO', 30), ('TCH PPTO', 32),
    ('TCH ANTERIOR', None), ('TCHM ANTERIOR', None), ('TCH RANDOM FOREST', None),
    ('TONELADAS ESTIMADAS', 37), ('RESPONSABLE ZONA', 6),
    ('TECNICO AGRICOLA RESPONSABLE', 7), ('FECHA DEL PROXIMO CORTE', 11),
    ('EMPRESA', 4), ('COORDENADAS', None),
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
        raise SystemExit(f'valor con separador o salto de linea en {col}: {s!r}')
    return s


def fila_encabezados(ws):
    """Indice (0-based) de la fila cuyo A dice SUERTE, o None."""
    for i, r in enumerate(ws.iter_rows(min_row=1, max_row=12, values_only=True)):
        if r and str(r[0] or '').strip().upper() == 'SUERTE':
            return i
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('xlsx', help='ruta del maestro oficial .xlsx')
    ap.add_argument('--maestro', default='maestro.csv',
                    help='CSV del que se heredan TCH anterior, Random Forest y coordenadas')
    ap.add_argument('--salida', default=None, help='por defecto sobrescribe --maestro')
    ap.add_argument('--hoja', default=None, help='hoja a leer; por defecto prefiere MAESTRO')
    a = ap.parse_args()

    import openpyxl
    wb = openpyxl.load_workbook(a.xlsx, data_only=True, read_only=True)

    if a.hoja:
        if a.hoja not in wb.sheetnames:
            raise SystemExit(f'el libro no tiene la hoja {a.hoja!r}. Hojas: {wb.sheetnames}')
        ws = wb[a.hoja]
    elif 'MAESTRO' in wb.sheetnames and fila_encabezados(wb['MAESTRO']) is not None:
        ws = wb['MAESTRO']
    else:
        cand = [h for h in wb.sheetnames if fila_encabezados(wb[h]) is not None]
        if not cand:
            raise SystemExit(f'ninguna hoja tiene SUERTE en la columna A. Hojas: {wb.sheetnames}')
        if len(cand) > 1:
            raise SystemExit(f'varias hojas podrian servir ({cand}); elige una con --hoja')
        ws = wb[cand[0]]
    print(f'hoja: {ws.title}  (de {len(wb.sheetnames)} hojas)')

    filas = list(ws.iter_rows(values_only=True))
    hdr = fila_encabezados(ws)
    if hdr is None:
        raise SystemExit('no se encontro la fila de encabezados (celda A = SUERTE)')

    reales = {j: str(filas[hdr][j] or '').replace('\n', ' ').strip().upper()
              for _, j in MAPA if j is not None}
    for col, j in MAPA:
        if j is not None and col.upper() not in reales[j] and reales[j] not in col.upper():
            raise SystemExit(f'la columna {j} del oficial es {reales[j]!r}, se esperaba {col!r}. '
                             'Cambio el formato del reporte: revisa MAPA.')
    print('validacion de encabezados: OK')
    datos = [r for r in filas[hdr + 1:] if r[0] and CODIGO.fullmatch(str(r[0]).strip())]

    # herencia del CSV actual: TCH ANTERIOR, TCHM ANTERIOR, TCH RANDOM FOREST (+corte), COORDENADAS
    previo = {}
    try:
        ls = [l for l in io.open(a.maestro, encoding='utf-8-sig', newline='').read().split('\r\n') if l.strip()]
        h = ls[0].split(';')
        iS, iT, iTM, iC = h.index('SUERTE'), h.index('TCH ANTERIOR'), h.index('TCHM ANTERIOR'), h.index('NUMERO DE CORTE')
        iRF = h.index('TCH RANDOM FOREST') if 'TCH RANDOM FOREST' in h else None
        iCO = h.index('COORDENADAS') if 'COORDENADAS' in h else None
        for l in ls[1:]:
            c = l.split(';')
            previo[c[iS].strip()] = (c[iT], c[iTM],
                                     c[iRF] if iRF is not None else '',
                                     c[iC].strip(),
                                     c[iCO] if iCO is not None else '')
    except (FileNotFoundError, ValueError):
        print('aviso: no se pudo leer el CSV actual; TCH anterior/RF/coordenadas quedaran vacias')

    salida = [';'.join(c for c, _ in MAPA)]
    beng = rf_vaciado = coords = 0
    for r in datos:
        if str(r[4] or '').strip() == 'BENG':
            beng += 1
            continue
        s = str(r[0]).strip()
        p = previo.get(s, ('', '', '', '', ''))
        fila = []
        for col, j in MAPA:
            if col == 'TCH ANTERIOR':
                fila.append(p[0])
            elif col == 'TCHM ANTERIOR':
                fila.append(p[1])
            elif col == 'TCH RANDOM FOREST':
                mismo = p[3] == celda('NUMERO DE CORTE', r[MAPA_IDX['NUMERO DE CORTE']])
                fila.append(p[2] if mismo else '')
                rf_vaciado += bool(p[2]) and not mismo
            elif col == 'COORDENADAS':
                fila.append(p[4])
                coords += bool(p[4].strip())
            else:
                fila.append(celda(col, r[j]))
        salida.append(';'.join(fila))

    destino = a.salida or a.maestro
    io.open(destino, 'w', encoding='utf-8', newline='').write('\ufeff' + '\r\n'.join(salida) + '\r\n')
    print(f'{destino}: {len(salida)-1} suertes | BENG filtradas: {beng} | '
          f'RF vaciado por corte nuevo: {rf_vaciado} | coordenadas heredadas: {coords}')
    print('Nota: las COORDENADAS se heredan. Cuando Rio Map (agrocontrol-campo) este '
          'disponible, correr tools/recalcular_coordenadas.py para refrescarlas desde la geometria.')


if __name__ == '__main__':
    main()

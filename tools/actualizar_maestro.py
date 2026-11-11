"""Boton "Actualizar maestro" — motor de un clic.

Lo que hace, en silencio y en orden:
  1. Lee el maestro oficial de Planeacion y Control (X:, hoja MAESTRO).
  2. Regenera maestro.csv (misma logica/validacion que tools/importar_maestro.py;
     hereda TCH anterior / Random Forest / coordenadas por suerte).
  3. Pone la fecha de datos de hoy en maestro.html (CONFIG.dataUpdated).
  4. Si algo cambio: git add + commit + push -> GitHub Pages republica solo y a
     los celulares les llega el dato nuevo. Si NO cambio nada, no hace commit.
  5. Muestra UN mensaje final (ventana de Windows): "Listo", "Sin cambios" o el error.

No abre consola: se lanza con pythonw desde el acceso directo del escritorio.
Pensado para doble clic de la usuaria; no requiere IA ni permisos especiales.
"""
import sys, os, io, re, datetime, subprocess, ctypes

# --- rutas ---
AQUI = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(AQUI)                       # raiz del repo (padre de tools/)
CSV = os.path.join(REPO, 'maestro.csv')
HTML = os.path.join(REPO, 'maestro.html')
OFICIAL = r"X:\PLANEACION Y CONTROL\Soportes Información Financiera\1-Maestro de Suerte\Año 2026\Maestro Suertes 2026.xlsx"

MESES = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto',
         'septiembre','octubre','noviembre','diciembre']
MES_CORTO = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic']

# --- mapeo oficial -> CSV (igual que importar_maestro.py) ---
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
DOS_DEC = {'AREA NETA HA', 'EDAD HOY MESES'}
CODIGO = re.compile(r'\d{4}-\d{3}')


def aviso(titulo, texto, icono=0x40):  # 0x40 info, 0x10 error, 0x30 warning
    ctypes.windll.user32.MessageBoxW(0, texto, titulo, icono)


def celda(col, v):
    if v is None:
        return ''
    if isinstance(v, datetime.datetime):
        return f'{v.day}/{v.month:02d}/{v.year}'
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if col in ENTEROS:
            return str(int(round(v)))
        if col in DOS_DEC:
            return f'{v:.2f}'
        return f'{v:g}'
    s = str(v)
    if ';' in s or '\n' in s or '\r' in s:
        raise ValueError(f'valor con separador/salto en {col}: {s!r}')
    return s


def fila_hdr(ws):
    for i, r in enumerate(ws.iter_rows(min_row=1, max_row=12, values_only=True)):
        if r and str(r[0] or '').strip().upper() == 'SUERTE':
            return i
    return None


def regenerar():
    """Reescribe maestro.csv desde el oficial. Devuelve (suertes, coords) o lanza."""
    import openpyxl
    if not os.path.exists(OFICIAL):
        raise FileNotFoundError('No encuentro el maestro oficial en X:.\n' + OFICIAL +
                                '\n\n¿Estás conectada a la red de la empresa?')
    wb = openpyxl.load_workbook(OFICIAL, data_only=True, read_only=True)
    ws = wb['MAESTRO'] if 'MAESTRO' in wb.sheetnames and fila_hdr(wb['MAESTRO']) is not None else None
    if ws is None:
        raise ValueError('El libro oficial no tiene la hoja MAESTRO en el formato esperado.')
    filas = list(ws.iter_rows(values_only=True))
    hdr = fila_hdr(ws)
    reales = {j: str(filas[hdr][j] or '').replace('\n', ' ').strip().upper() for _, j in MAPA if j is not None}
    for col, j in MAPA:
        if j is not None and col.upper() not in reales[j] and reales[j] not in col.upper():
            raise ValueError(f'Cambió el formato del maestro oficial (columna {j} = {reales[j]!r}, '
                             f'se esperaba {col!r}). No publico para no dañar los datos; avísale a quien te ayuda.')
    datos = [r for r in filas[hdr + 1:] if r[0] and CODIGO.fullmatch(str(r[0]).strip())]

    previo = {}
    try:
        ls = [l for l in io.open(CSV, encoding='utf-8-sig', newline='').read().split('\r\n') if l.strip()]
        h = ls[0].split(';')
        iS, iT, iTM, iC = h.index('SUERTE'), h.index('TCH ANTERIOR'), h.index('TCHM ANTERIOR'), h.index('NUMERO DE CORTE')
        iRF = h.index('TCH RANDOM FOREST') if 'TCH RANDOM FOREST' in h else None
        iCO = h.index('COORDENADAS') if 'COORDENADAS' in h else None
        for l in ls[1:]:
            c = l.split(';')
            previo[c[iS].strip()] = (c[iT], c[iTM], c[iRF] if iRF is not None else '',
                                     c[iC].strip(), c[iCO] if iCO is not None else '')
    except (FileNotFoundError, ValueError):
        pass

    salida = [';'.join(c for c, _ in MAPA)]
    coords = 0
    for r in datos:
        if str(r[4] or '').strip() == 'BENG':
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
            elif col == 'COORDENADAS':
                fila.append(p[4]); coords += bool(p[4].strip())
            else:
                fila.append(celda(col, r[j]))
        salida.append(';'.join(fila))
    io.open(CSV, 'w', encoding='utf-8', newline='').write('\ufeff' + '\r\n'.join(salida) + '\r\n')
    return len(salida) - 1, coords


def poner_fecha_hoy():
    hoy = datetime.date.today()
    larga = f'{hoy.day} de {MESES[hoy.month-1]} de {hoy.year}'
    corta = f'{hoy.day} {MES_CORTO[hoy.month-1]} {hoy.year}'
    t = io.open(HTML, encoding='utf-8', newline='').read()  # newline='' preserva CRLF/LF
    t = re.sub(r"dataUpdated:\s*'[^']*'", f"dataUpdated: '{larga}'", t, count=1)
    t = re.sub(r"dataUpdatedShort:\s*'[^']*'", f"dataUpdatedShort: '{corta}'", t, count=1)
    io.open(HTML, 'w', encoding='utf-8', newline='').write(t)


def git(*args):
    r = subprocess.run(['git', *args], cwd=REPO, capture_output=True, text=True,
                       creationflags=0x08000000)  # CREATE_NO_WINDOW
    return r


def main():
    check = '--check' in sys.argv  # modo prueba: no publica, no muestra ventanas, imprime
    try:
        n, coords = regenerar()
        poner_fecha_hoy()
    except Exception as e:
        if check:
            print('ERROR:', e); return
        aviso('Actualizar maestro — error', str(e), 0x10)
        return
    if check:
        st = git('status', '--porcelain', 'maestro.csv', 'maestro.html')
        print(f'regenerado OK: {n} suertes, {coords} con ubicacion')
        print('cambios pendientes:', repr(st.stdout.strip()) or 'NINGUNO')
        return

    st = git('status', '--porcelain', 'maestro.csv', 'maestro.html')
    if not st.stdout.strip():
        aviso('Actualizar maestro', 'El maestro ya estaba al día.\nNo había cambios para publicar.')
        return

    hoy = datetime.date.today().isoformat()
    git('add', 'maestro.csv', 'maestro.html')
    cm = git('-c', 'user.name=Maria del Mar Ospina', '-c', 'user.email=mar96ospina@gmail.com',
             'commit', '-m', f'datos: maestro al {hoy} (boton Actualizar)')
    if cm.returncode != 0:
        aviso('Actualizar maestro — error', 'No pude registrar los cambios:\n\n' + (cm.stderr or cm.stdout), 0x10)
        return
    ps = git('push', 'origin', 'main')
    if ps.returncode != 0:
        aviso('Actualizar maestro — error',
              'Regeneré el maestro pero NO pude publicarlo (¿sin internet?).\n\n' + (ps.stderr or ps.stdout), 0x10)
        return
    aviso('Actualizar maestro ✅',
          f'Maestro actualizado y publicado.\n\n{n} suertes · {coords} con ubicación.\n'
          f'El campo lo verá en pocos minutos (puede que les salga aviso de actualizar).')


if __name__ == '__main__':
    main()

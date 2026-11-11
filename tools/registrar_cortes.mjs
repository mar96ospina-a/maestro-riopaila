/**
 * Registra en maestro.csv los cortes que la app de cosecha (Turnos & Jornales)
 * ya cerró. Es el paso que mantiene el maestro al día entre importaciones del
 * libro oficial de Planeación.
 *
 * Por cada suerte toca TRES columnas, con las reglas de la app
 * (lib/maestro/sincronizar.ts):
 *  - FECHA DE ULTIMO CORTE = la fecha fin que guardó la app.
 *  - NUMERO DE CORTE +1, SALVO si el maestro ya trae el número posterior; ahí
 *    se corrige solo la fecha, o la suerte quedaría con un corte de más.
 *  - FECHA DEL PROXIMO CORTE = último + 12,5 meses (un año anclado a fin de mes
 *    si desborda, + 15 días). OJO: el ciclo NO es fijo por norma — este es el
 *    que usa la app. Si quien manda la lista pide otro, cámbialo a mano.
 *
 * Además VACÍA TCH RANDOM FOREST donde sube el número de corte: ese estimado
 * era de la caña que se acaba de cosechar, no de la soca nueva (misma regla
 * que tools/importar_maestro.py).
 *
 * EDAD HOY MESES NO SE TOCA: maestro.html la recalcula al cargar el CSV y pisa
 * lo que traiga el archivo. (Para un Excel sí hay que calcularla —ahí no la
 * recalcula nadie—: ver tools/exportar_excel.py.)
 *
 * Dos guardas, por lo que ya ha pasado:
 *  - aborta si el maestro no trae ni el mismo número del corte cerrado ni ese +1;
 *  - aborta si el corte anterior del maestro está a menos de 150 días del nuevo:
 *    un corte legítimo llega 9-16 meses después, así que eso es la MISMA cosecha
 *    llegando dos veces y subirle el número la dejaría inflada.
 *
 * Entrada: un JSON { "3106-071": [7, "2026-10-05"], ... } con el número del
 * corte que la app cerró y su fecha fin. Sale de `cosecha_cortes` (estado T).
 *
 * Uso (desde la raíz del repo):
 *   node tools/registrar_cortes.mjs cierres.json            # simulacro
 *   node tools/registrar_cortes.mjs cierres.json --aplicar
 *
 * Después: actualizar CONFIG.dataUpdated en maestro.html y volver a correr la
 * sincronización del lado de la app (scripts/sincronizar_maestro.mjs).
 */
import { readFileSync, writeFileSync } from "node:fs";

const RUTA = "maestro.csv";
const ARCH = process.argv.slice(2).find((a) => !a.startsWith("--"));
if (!ARCH) {
  console.error("Uso: node tools/registrar_cortes.mjs <cierres.json> [--aplicar]");
  process.exit(1);
}
const CIERRES = JSON.parse(readFileSync(ARCH, "utf8"));

/** "2026-10-25" → "25/10/2026": día sin cero, mes con cero (formato del CSV). */
const aCsv = (iso) => `${+iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;

/** Un año después (anclado a fin de mes si desborda) + 15 días = 12,5 meses. */
function proximoCorte(iso) {
  const [a, m, d] = iso.split("-").map(Number);
  const ultimoDelMes = new Date(Date.UTC(a + 1, m, 0)).getUTCDate();
  const base = Date.UTC(a + 1, m - 1, Math.min(d, ultimoDelMes));
  return new Date(base + 15 * 86_400_000).toISOString().slice(0, 10);
}

const crudo = readFileSync(RUTA, "utf8");
const bom = crudo.startsWith("﻿") ? "﻿" : "";
const L = crudo.replace(/^﻿/, "").replace(/\r\n/g, "\n").split("\n");
const H = L[0].split(";");
const col = (n) => {
  const k = H.indexOf(n);
  if (k < 0) throw new Error(`el maestro no tiene la columna ${n}`);
  return k;
};
const [iS, iUlt, iNum, iRF, iProx] = [
  "SUERTE", "FECHA DE ULTIMO CORTE", "NUMERO DE CORTE", "TCH RANDOM FOREST", "FECHA DEL PROXIMO CORTE",
].map(col);

const vistas = new Set();
const cortes = [];
for (let k = 1; k < L.length; k++) {
  if (!L[k].trim()) continue;
  const c = L[k].split(";");
  const s = c[iS].trim();
  const cierre = CIERRES[s];
  if (!cierre) continue;
  if (vistas.has(s)) throw new Error(`${s} aparece dos veces en el maestro`);
  vistas.add(s);

  const [nCerrado, finISO] = cierre;
  const nMaestro = Number(c[iNum]);
  if (!Number.isFinite(nMaestro)) throw new Error(`${s}: número de corte ilegible "${c[iNum]}"`);
  const adelantado = nMaestro === nCerrado + 1;
  if (!adelantado && nMaestro !== nCerrado) {
    throw new Error(`${s}: la app cerró el corte ${nCerrado} y el maestro trae ${nMaestro}; ni igual ni +1`);
  }
  const previo = c[iUlt].match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!adelantado && previo) {
    const dias = (Date.parse(`${finISO}T00:00:00Z`) - Date.UTC(+previo[3], +previo[2] - 1, +previo[1])) / 86_400_000;
    if (dias < 150) {
      throw new Error(`${s}: el maestro trae ${c[iUlt]} y el cierre es ${finISO}, solo ${Math.round(dias)} días después; parece la misma cosecha`);
    }
  }

  const antes = { num: c[iNum], ult: c[iUlt], prox: c[iProx], rf: c[iRF] };
  if (!adelantado) {
    c[iNum] = String(nCerrado + 1);
    c[iRF] = "";
  }
  c[iUlt] = aCsv(finISO);
  c[iProx] = aCsv(proximoCorte(finISO));
  cortes.push({ s, antes, num: c[iNum], ult: c[iUlt], prox: c[iProx], rf: c[iRF], adelantado });
  L[k] = c.join(";");
}

const faltan = Object.keys(CIERRES).filter((s) => !vistas.has(s));
if (faltan.length) throw new Error(`no están en el maestro: ${faltan.join(", ")}`);

console.log("SUERTE      n°        últ. corte            próximo corte          TCH RF");
for (const x of cortes.sort((a, b) => a.s.localeCompare(b.s))) {
  console.log(
    `${x.s}  ${String(x.antes.num).padStart(2)}→${String(x.num).padEnd(3)} ` +
    `${x.antes.ult.padStart(11)}→${x.ult.padEnd(11)} ${x.antes.prox.padStart(11)}→${x.prox.padEnd(11)} ` +
    `${(x.antes.rf || "—").padStart(6)}→${(x.rf || "—").padEnd(6)}${x.adelantado ? "  (ya iba adelantado: no sube el n°)" : ""}`,
  );
}
const subidos = cortes.filter((x) => !x.adelantado);
console.log(`\n${cortes.length} cortes · número subido en ${subidos.length} · TCH RF vaciado en ${subidos.filter((x) => x.antes.rf).length}`);

if (!process.argv.includes("--aplicar")) {
  console.log("\nSimulacro. Añade --aplicar para escribir.");
} else {
  writeFileSync(RUTA, bom + L.join("\r\n"), "utf8");
  console.log("\n✓ maestro.csv escrito. Falta CONFIG.dataUpdated en maestro.html.");
}

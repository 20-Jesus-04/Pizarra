/* eslint-disable @typescript-eslint/no-explicit-any */
// Datos generados por el motor Python (pronosticos/build.py) e inyectados en la página.
function readData(): any {
  const el = document.getElementById("pz-data");
  const txt = el?.textContent?.trim() ?? "";
  const vacio = () => ({ partidos: [], ligas: {}, config: { kelly: 0.25, dias: 21 }, pkeys: [], generado: new Date().toISOString() });
  if (!txt || txt.startsWith("__")) return vacio();
  try {
    return JSON.parse(txt);
  } catch {
    return vacio();   // datos rotos: la página carga vacía en vez de quedar en blanco
  }
}
export const DATA: any = readData();
export const LG: Record<string, any> = DATA.ligas;
export const TZ = "America/Lima";
export const NOW = Date.now();
export const MATCH_MS = 2.25 * 3600e3;

// Solo partidos de hoy en adelante: los terminados desaparecen solos.
export const MATCHES: any[] = DATA.partidos.filter((p: any) => new Date(p.fecha).getTime() + MATCH_MS > NOW);
export const BY_ID: Record<string, any> = Object.fromEntries(DATA.partidos.map((p: any) => [p.id, p]));
export const isLive = (p: any) => { const t = new Date(p.fecha).getTime(); return t <= NOW && NOW < t + MATCH_MS; };
export const isPlayed = (p: any) => new Date(p.fecha).getTime() + MATCH_MS <= NOW;
export const DATA_AGE_H = (NOW - new Date(DATA.generado).getTime()) / 3600e3;

export const pct = (p: number | null | undefined, d = 0) => (p == null ? "–" : (p * 100).toFixed(d) + "%");
export const odd = (o: number | null | undefined) => (o == null ? "–" : Number(o).toFixed(2));
export const fair = (p: number) => (p ? (1 / p).toFixed(2) : "–");
export const fTime = (d: string) => new Date(d).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: TZ });
export const dayKey = (d: string | Date) => new Date(d).toLocaleDateString("en-CA", { timeZone: TZ });
export const TODAY = dayKey(new Date());
export const TOMORROW = dayKey(new Date(NOW + 864e5));
export const dayLabel = (k: string) => (k === TODAY ? "Hoy" : k === TOMORROW ? "Mañana" : new Date(k + "T12:00:00").toLocaleDateString("es-PE", { weekday: "long", day: "numeric", month: "long" }));
export const dayShort = (k: string) => (k === TODAY ? "Hoy" : k === TOMORROW ? "Mañana" : new Date(k + "T12:00:00").toLocaleDateString("es-PE", { weekday: "short", day: "numeric" }));
export const longDate = (d: string) => new Date(d).toLocaleDateString("es-PE", { day: "numeric", month: "long", timeZone: TZ });

const COMP_ES: Record<string, string> = {
  "UEFA Nations League": "Nations League", "International Friendly": "Amistoso", "Concacaf Nations League": "Nations League Concacaf",
  "Africa Cup of Nations Qualifying": "Eliminatorias Copa África", "FIFA World Cup": "Mundial", "Copa América": "Copa América",
  "UEFA European Championship": "Eurocopa", "UEFA European Championship Qualifying": "Eliminatorias Eurocopa",
  "FIFA World Cup Qualifying - CONMEBOL": "Eliminatorias Sudamericanas", "FIFA World Cup Qualifying - UEFA": "Eliminatorias UEFA",
  "FIFA World Cup Qualifying - Concacaf": "Eliminatorias Concacaf", "FIFA World Cup Qualifying - CAF": "Eliminatorias CAF",
  "FIFA World Cup Qualifying - AFC": "Eliminatorias AFC", "AFC Asian Cup Qualifiers": "Eliminatorias Copa Asia",
  "Africa Cup of Nations": "Copa África", "Concacaf Gold Cup": "Copa Oro",
};
/** "Fija" = está en la lista publicada (3 días, 1 por partido, 5 por día), no solo candidata. */
const FIJA_KEYS = new Set((DATA.fijas?.lista || []).map((f: any) => `${f.id}|${f.clave}`));
export const esFija = (p: any, o: any) => (p ? FIJA_KEYS.has(`${p.id}|${o.clave}`) : !!o.fija);
export const compName = (p: any) => (p.liga === "INT" ? COMP_ES[p.competicion] || p.competicion : LG[p.liga]?.name);

export function initials(n: string) {
  const w = n.replace(/[^A-Za-zÀ-ÿ ]/g, "").split(" ").filter((x) => x.length > 1 && !/^(de|del|la|fc|cf|ac|as|sc|afc|united|city)$/i.test(x));
  return (w.slice(0, 2).map((x) => x[0]).join("") || n.slice(0, 2)).toUpperCase();
}
export function hue(n: string) { let h = 0; for (const c of n) h = (h * 31 + c.charCodeAt(0)) % 360; return h; }

export const unpack = (j: any) => ({
  nombre: j.n, pos: j.p, min: j.m, tit: j.t / 100,
  prob: Object.fromEntries(DATA.pkeys.map((k: string, i: number) => [k, j.q[i] / 1000])) as Record<string, number>,
  temp: { pj: j.s[0], min: j.s[1], goles: j.s[2], asist: j.s[3], tiros: j.s[4], arco: j.s[5], faltas: j.s[6], ta: j.s[7], tr: j.s[8] },
  ult: j.u as string,
});
export type Player = ReturnType<typeof unpack>;

// ---------- lectura en palabras
export function verdict(p: any): { lead: string; rest: string } {
  const m = p.mercados, x = m["1x2"], tot = m.xg_home + m.xg_away, btts = m.ambos_marcan.si;
  let lead: string;
  if (x["1"] >= 0.6) lead = `${p.local} es claro favorito`;
  else if (x["2"] >= 0.6) lead = `${p.visita} es claro favorito aunque juegue de visita`;
  else if (x["1"] >= 0.45) lead = `${p.local} parte con ventaja`;
  else if (x["2"] >= 0.45) lead = `${p.visita} parte con ventaja`;
  else lead = x.X >= 0.29 ? "Partido muy parejo, el empate tiene opciones reales" : "Partido parejo, sin un favorito claro";
  const g = tot >= 3.1 ? `se esperan muchos goles (${tot.toFixed(1)})` : tot <= 2.2 ? `se espera un partido cerrado (${tot.toFixed(1)} goles)` : `se esperan unos ${tot.toFixed(1)} goles`;
  const b = btts >= 0.58 ? " y lo normal es que marquen los dos" : btts <= 0.4 ? " y es probable que alguno se quede sin marcar" : "";
  return { lead, rest: `${g}${b}.` };
}

export function favLabel(p: any) {
  const x = p.mercados["1x2"];
  if (x["1"] >= 0.5) return { t: `Favorito ${p.local}`, kind: "fav" as const };
  if (x["2"] >= 0.5) return { t: `Favorito ${p.visita}`, kind: "fav" as const };
  return { t: "Parejo", kind: "even" as const };
}

export function prettyAlt(p: any, l: string) {
  const map: Record<string, string> = {
    "Doble oportunidad 1X (local o empate)": `${p.local} o empate`, "Doble oportunidad X2 (visita o empate)": `${p.visita} o empate`,
    "Doble oportunidad 12 (no hay empate)": "Cualquiera gana (sin empate)", "Empate no apuesta: local": `${p.local} (si empata, te devuelven)`,
    "Empate no apuesta: visita": `${p.visita} (si empata, te devuelven)`, "Gana el local": `Gana ${p.local}`, "Gana la visita": `Gana ${p.visita}`,
    "Hándicap asiático local -1": `${p.local} gana por 2 o más (si gana por 1, se devuelve)`, "Hándicap asiático visita -1": `${p.visita} gana por 2 o más (si gana por 1, se devuelve)`,
    "Local gana por 2 o más": `${p.local} gana por 2 o más`, "Visita gana por 2 o más": `${p.visita} gana por 2 o más`,
    "Local no marca": `${p.local} no marca`, "Visita no marca": `${p.visita} no marca`, "Empate": "Empate",
  };
  return map[l] || l.replace(/^Local /, p.local + " ").replace(/^Visita /, p.visita + " ");
}
function valorLabel(p: any, v: any) {
  if (v.mercado === "1X2") return v.seleccion === "Local" ? `Gana ${p.local}` : v.seleccion === "Visita" ? `Gana ${p.visita}` : "Empate";
  if (v.mercado === "Goles totales") return `${v.seleccion} goles`;
  if (v.mercado === "Hándicap asiático") { const [side, ln] = v.seleccion.split(" "); return `${side === "local" ? p.local : p.visita} ${ln} (hándicap)`; }
  return `${v.mercado}: ${v.seleccion}`;
}
export type Pick = { sel: string; prob: number; fair: number; casa?: number; ev?: number; valor?: boolean; p: any };
export function picksFor(p: any): Pick[] {
  const out: Pick[] = [];
  for (const v of p.valor.filter((v: any) => v.valor)) out.push({ sel: valorLabel(p, v), prob: v.prob, fair: v.cuota_justa, casa: v.cuota, ev: v.ev, valor: true, p });
  for (const a of p.alternativas) out.push({ sel: prettyAlt(p, a.seleccion), prob: a.prob, fair: a.cuota_justa, p });
  const score = (c: Pick) => (c.valor ? 2 + (c.ev || 0) : c.prob * Math.pow(1 / c.prob, 0.6) * (c.prob < 0.9 ? 1 : 0.7));
  return out.sort((a, b) => score(b) - score(a));
}
/** Todas las oportunidades de los partidos que aún no empiezan, con su partido. */
export const OPS: { p: any; o: any }[] = MATCHES.filter((p) => !isLive(p)).flatMap((p) => (p.oportunidades || []).map((o: any) => ({ p, o })));
export const opToPick = (p: any, o: any): Pick => ({ sel: prettyAlt(p, o.seleccion), prob: o.prob_real, fair: o.cuota_justa, casa: o.cuota_casa || undefined,
  ev: o.ev ?? undefined, valor: !!(o.ev && o.ev > 0.03 && !o.valor_sospechoso), p });

/** Las mejores oportunidades de los próximos días: primero las fijas, luego por puntaje; una por partido y variando de liga. */
export function topPicks(n = 6): Pick[] {
  const soonMs = 3.2 * 864e5;
  let pool = OPS.filter(({ p }) => new Date(p.fecha).getTime() - NOW < soonMs);
  if (pool.length < n) pool = OPS;
  if (!pool.length) return legacyTopPicks(n);
  const best = new Map<string, { p: any; o: any }>();
  for (const x of pool) { const cur = best.get(x.p.id); if (!cur || x.o.puntaje > cur.o.puntaje) best.set(x.p.id, x); }
  const list = [...best.values()].sort((a, b) => (esFija(b.p, b.o) ? 1 : 0) - (esFija(a.p, a.o) ? 1 : 0) || b.o.puntaje - a.o.puntaje || b.p.confianza - a.p.confianza);
  const seen = new Set<string>(), res: Pick[] = [];
  for (const { p, o } of list) {
    const key = p.liga + p.competicion;
    if (seen.has(key) && res.length < n - 1 && list.length > n * 2) continue;
    seen.add(key); res.push(opToPick(p, o));
    if (res.length === n) break;
  }
  return res;
}

function legacyTopPicks(n: number): Pick[] {
  const upcoming = MATCHES.filter((p) => !isLive(p));
  const soon = upcoming.filter((p) => new Date(p.fecha).getTime() - NOW < 3.2 * 864e5);
  const pool = (soon.length >= n ? soon : upcoming).flatMap((p) => { const k = picksFor(p)[0]; return k ? [k] : []; });
  pool.sort((a, b) => (b.valor ? 1 : 0) - (a.valor ? 1 : 0) || b.prob * Math.pow(b.fair, 0.6) - a.prob * Math.pow(a.fair, 0.6) || b.p.confianza - a.p.confianza);
  return pool.slice(0, n);
}

export function keyFacts(p: any): string[] {
  const f: string[] = [], pl = p.perfil_local, pv = p.perfil_visita, h = p.h2h;
  const ls = pl.temporada_local || {}, vs = pv.temporada_visita || {};
  if (pl.racha) f.push(`**${p.local}**: ${pl.racha}.`);
  if (pv.racha) f.push(`**${p.visita}**: ${pv.racha}.`);
  if (ls.pj >= 3) f.push(`**${p.local}** de local esta temporada: ganó ${ls.g}, empató ${ls.e} y perdió ${ls.p}, con ${ls.gf} goles a favor por partido.`);
  if (vs.pj >= 3) f.push(`**${p.visita}** de visita: ganó ${vs.g}, empató ${vs.e} y perdió ${vs.p}; recibe ${vs.gc} goles por partido.`);
  if (h.partidos.length) f.push(`Últimos ${h.partidos.length} cruces: ${p.local} ganó ${h.gana_local}, ${h.empates} empates, ${p.visita} ganó ${h.gana_visita} (${h.goles_prom} goles de media).`);
  const all = [...(p.jugadores?.local || []).map((j: any) => ({ ...unpack(j), eq: p.local })), ...(p.jugadores?.visita || []).map((j: any) => ({ ...unpack(j), eq: p.visita }))];
  const top = all.sort((a, b) => b.prob.marca - a.prob.marca)[0];
  if (top) f.push(`Con más opciones de marcar: **${top.nombre}** (${top.eq}), ${pct(top.prob.marca)}.`);
  if (p.fijas?.length) f.push(`Está entre las **fijas** del día: pasó los cuatro filtros de acierto comprobado.`);
  const r = p.arbitro, t = p.mercados?.tarjetas;
  if (r?.partidos && t) f.push(`Árbitro: **${r.nombre}**, ${r.factor > 1.03 ? "saca más tarjetas que la media" : r.factor < 0.97 ? "saca menos tarjetas que la media" : "en la media de tarjetas"} (×${r.factor.toFixed(2)}). Se esperan ${t.esperadas_total.toFixed(1)} amarillas.`);
  if (p.mercado && p.desacuerdo_modelo_mercado > 0.08) f.push(`El modelo y las casas no coinciden del todo: revisa lesiones o rotaciones antes de apostar.`);
  return f;
}

export const MK_NAMES: Record<string, string> = {
  "1x2": "Resultado final", doble_oportunidad: "Doble oportunidad", empate_no_apuesta: "Empate no apuesta", goles_totales: "Goles del partido",
  goles_local: "Goles del local", goles_visita: "Goles de la visita", ambos_marcan: "Ambos marcan", ambos_marcan_y_resultado: "Ambos marcan + resultado",
  "resultado_y_goles_2.5": "Resultado + goles (2.5)", valla_invicta: "Valla invicta", gana_sin_recibir: "Gana sin recibir gol", goles_exactos: "Número exacto de goles",
  par_impar: "Goles par o impar", margen_victoria: "Margen de victoria", handicap_asiatico_local: "Hándicap asiático", marcador_exacto: "Marcador exacto",
  primer_tiempo_1x2: "1er tiempo: resultado", primer_tiempo_goles: "1er tiempo: goles", segundo_tiempo_goles: "2do tiempo: goles",
  ambos_marcan_1T: "Ambos marcan en el 1er tiempo", mitad_con_mas_goles: "Mitad con más goles", descanso_final: "Descanso / final",
  corners: "Córners", tarjetas: "Tarjetas", tiros: "Tiros", tiros_al_arco: "Tiros al arco", faltas: "Faltas", fueras_de_juego: "Fueras de juego", amarillas: "Tarjetas amarillas",
};
export const GROUPS: [string, string, string[]][] = [
  ["Lo principal", "Quién gana, goles y ambos marcan", ["1x2", "doble_oportunidad", "empate_no_apuesta", "goles_totales", "ambos_marcan"]],
  ["Goles por equipo", "Cuántos marca cada uno", ["goles_local", "goles_visita", "valla_invicta", "gana_sin_recibir"]],
  ["Combinadas y exactos", "Marcador exacto, margen y combinadas", ["ambos_marcan_y_resultado", "resultado_y_goles_2.5", "marcador_exacto", "goles_exactos", "margen_victoria", "par_impar"]],
  ["Por tiempos", "Primer y segundo tiempo", ["primer_tiempo_1x2", "primer_tiempo_goles", "segundo_tiempo_goles", "ambos_marcan_1T", "mitad_con_mas_goles", "descanso_final"]],
  ["Hándicap asiático", "Ventaja o desventaja de goles", ["handicap_asiatico_local"]],
  ["Córners, tarjetas y tiros", "Estadísticas del partido", ["corners", "tarjetas", "amarillas", "tiros", "tiros_al_arco", "faltas", "fueras_de_juego"]],
];
const SEL: Record<string, string> = { "1": "Local", X: "Empate", "2": "Visita", "1X": "Local o empate", X2: "Visita o empate", "12": "Cualquiera gana", si: "Sí", no: "No",
  over: "Más de", under: "Menos de", local: "Local", visita: "Visita", par: "Par", impar: "Impar", igual: "Igual", "1T": "1er tiempo", "2T": "2do tiempo" };
const selName = (k: string) => SEL[k] ?? k.replace(/_/g, " ").replace("local por", "Local por").replace("visita por", "Visita por");
const TEAMSTAT = ["tiros", "tiros_al_arco", "faltas", "fueras_de_juego", "amarillas"];

export type MRow = { label: string; p?: number; value?: string; extra?: string };
export function marketRows(p: any, key: string, val: any): MRow[] {
  const rows: MRow[] = [];
  const nm = (s: string) => s.replace(/^Local/, p.local).replace(/^Visita/, p.visita);
  if (key === "handicap_asiatico_local") {
    for (const [ln, v] of Object.entries<any>(val)) rows.push({ label: `${p.local} ${ln}`, p: v.gana, extra: v.devuelve > 0.001 ? `devuelve ${pct(v.devuelve)}` : undefined });
  } else if (TEAMSTAT.includes(key)) {
    rows.push({ label: `Esperados: ${p.local} ${val.esperado_local.toFixed(1)} · ${p.visita} ${val.esperado_visita.toFixed(1)}`, value: val.esperado_total.toFixed(1) });
    for (const [ln, v] of Object.entries<any>(val.total)) rows.push({ label: `Total: más de ${ln}`, p: v.over });
    for (const [ln, v] of Object.entries<any>(val.local)) rows.push({ label: `${p.local}: más de ${ln}`, p: v });
    for (const [ln, v] of Object.entries<any>(val.visita)) rows.push({ label: `${p.visita}: más de ${ln}`, p: v });
  } else if (key === "corners" || key === "tarjetas") {
    rows.push({ label: "Esperados en total", value: (key === "corners" ? val.esperados_total : val.esperadas_total).toFixed(1) });
    for (const [ln, v] of Object.entries<any>(val.total)) rows.push({ label: `Más de ${ln}`, p: v.over });
    if (val.mas_corners) for (const [k, v] of Object.entries<any>(val.mas_corners)) rows.push({ label: `Más córners: ${nm(selName(k))}`, p: v });
  } else {
    for (const [k, v] of Object.entries<any>(val)) {
      if (typeof v === "number") rows.push({ label: nm(selName(k)), p: v });
      else for (const [k2, v2] of Object.entries<any>(v)) rows.push({ label: `${selName(k2)} ${k}`, p: v2 });
    }
  }
  return rows;
}
export function allSelections(p: any) {
  const out: { l: string; p: number }[] = [];
  for (const [, , keys] of GROUPS) for (const k of keys) {
    const v = p.mercados[k]; if (!v || typeof v !== "object") continue;
    for (const r of marketRows(p, k, v)) if (r.p != null) out.push({ l: `${MK_NAMES[k]}: ${r.label}`, p: r.p });
  }
  for (const list of [p.jugadores?.local, p.jugadores?.visita]) for (const j of (list || []).map(unpack)) {
    out.push({ l: `${j.nombre}: marca`, p: j.prob.marca }, { l: `${j.nombre}: 1+ tiro al arco`, p: j.prob["arco_1+"] }, { l: `${j.nombre}: 2+ tiros`, p: j.prob["tiros_2+"] }, { l: `${j.nombre}: tarjeta`, p: j.prob.tarjeta });
  }
  return out;
}

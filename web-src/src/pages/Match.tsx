/* eslint-disable @typescript-eslint/no-explicit-any */
import { useMemo, useState } from "react";
import { ArrowLeft, Calculator, Gavel, Info, ShieldCheck, ShieldAlert } from "lucide-react";
import { BY_ID, DATA, LG, GROUPS, MK_NAMES, allSelections, compName, dayKey, dayLabel, fTime, fair, isLive, isPlayed, keyFacts, marketRows, odd, pct, picksFor, unpack, verdict } from "@/lib/data";
import { Accordion, Badge, FormDots, Meter, Pitch, Reveal, Ring, SectionHead, Tabs, Ticket } from "@/components/ui-pz";
import { JugadorCard, OportunidadCard } from "@/components/oport";

const bold = (s: string) => s.split(/\*\*(.+?)\*\*/g).map((t, i) => (i % 2 ? <b key={i} className="text-chalk">{t}</b> : t));

export default function Match({ id, backTo }: { id: string; backTo: string }) {
  const p = BY_ID[id];
  const [tab, setTab] = useState("resumen");
  if (!p || isPlayed(p)) {
    return (
      <div className="mx-auto max-w-[1180px] px-5 py-16 md:px-8">
        <a href="#partidos" className="inline-flex items-center gap-2 font-semibold text-chalk-2"><ArrowLeft className="h-4 w-4" /> Partidos</a>
        <h1 id="titulo" tabIndex={-1} className="mt-6 text-[36px] font-black">{p ? `${p.local} vs ${p.visita} ya se jugó` : "Este partido ya no está en la lista"}</h1>
        <p className="mt-3 text-chalk-2">Solo mostramos partidos de hoy en adelante.</p>
      </div>
    );
  }
  const x = p.mercados["1x2"], mx = Math.max(x["1"], x.X, x["2"]);
  const v = verdict(p);
  const picks = picksFor(p).slice(0, 3);
  const ops = p.oportunidades || [], jugOps = p.oportunidades_jugador || [];
  const cells: [string, number, string][] = [["1", x["1"], `Gana ${p.local}`], ["X", x.X, "Empate"], ["2", x["2"], `Gana ${p.visita}`]];

  return (
    <div className="mx-auto w-full max-w-[1240px] px-4 sm:px-6 lg:px-8">
      <nav aria-label="Ruta" className="mt-5 flex flex-wrap items-center gap-1.5 text-[13px] text-chalk-3">
        <a href={backTo} className="inline-flex items-center gap-1.5 font-semibold text-chalk-2 hover:text-chalk"><ArrowLeft className="h-4 w-4" />Partidos</a>
        <span aria-hidden="true">/</span><a href={`#partidos.${p.liga}`} className="hover:text-chalk">{LG[p.liga]?.name}</a>
        <span aria-hidden="true">/</span><span className="truncate text-chalk-2">{p.local} vs {p.visita}</span>
      </nav>

      {/* MARCADOR */}
      <section
        className={`enter-scale relative mt-4 overflow-hidden rounded-[24px] sm:rounded-[28px] border border-white/10 bg-gradient-to-b from-night-800 to-night-850 px-4 py-7 sm:px-6 md:px-10 md:py-10 ${p.fijas?.length ? "glow-border" : ""}`}>
        <Pitch />
        <div className="pointer-events-none absolute left-1/2 top-0 h-60 w-[70%] -translate-x-1/2 rounded-full bg-cobalt/20 blur-[90px]" />
        <div className="relative">
          <div className="text-center text-[13px] font-semibold text-chalk-2">
            {isLive(p) && <span className="mr-2 inline-flex items-center gap-1.5 font-bold text-flare"><span className="live-dot h-2 w-2 rounded-full bg-flare" />EN VIVO ·</span>}
            {compName(p)} · <span className="capitalize">{dayLabel(dayKey(p.fecha))}</span> {fTime(p.fecha)}{p.estadio ? ` · ${p.estadio}` : ""}{p.neutral ? " · cancha neutral" : ""}
          </div>
          <div className="mt-7 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 md:gap-8">
            {[p.local, null, p.visita].map((t, i) => t === null ? (
              <div key={i} className="text-center">
                <div className="num text-[11px] uppercase tracking-[0.1em] text-chalk-3">goles esperados</div>
                <div className="mt-1 whitespace-nowrap font-display text-[clamp(22px,5vw,48px)] font-black" style={{ fontStretch: "118%" }}>
                  {p.mercados.xg_home.toFixed(1)}<span className="mx-2 text-chalk-3">–</span>{p.mercados.xg_away.toFixed(1)}
                </div>
              </div>
            ) : (
              <div key={i} style={{ animationDelay: "0.15s", ["--dx" as any]: i === 0 ? "-30px" : "30px" }}
                className="enter-x flex min-w-0 flex-col items-center gap-2 text-center sm:gap-3">
                <Badge name={t} size={56} />
                {i === 0 ? <h1 id="titulo" tabIndex={-1} className="w-full text-[clamp(15px,3.4vw,34px)] font-black leading-tight [hyphens:auto]">{t}</h1>
                  : <h2 className="w-full text-[clamp(15px,3.4vw,34px)] font-black leading-tight [hyphens:auto]">{t}</h2>}
                <FormDots s={i === 0 ? p.perfil_local.forma : p.perfil_visita.forma} />
              </div>
            ))}
          </div>
          <div className="mt-8 grid grid-cols-3 gap-2 sm:gap-2.5 md:gap-4">
            {cells.map(([k, v, l], i) => (
              <div key={k} style={{ animationDelay: `${0.3 + i * 0.08}s` }}
                className={`enter relative overflow-hidden rounded-2xl px-2 py-3.5 text-center sm:px-3 sm:py-4 ${v === mx ? "bg-gold/10 ring-2 ring-gold" : "bg-white/[0.04] ring-1 ring-white/10"}`}>
                <div className={`grow-y absolute inset-x-0 bottom-0 ${v === mx ? "bg-gold/20" : "bg-cobalt/15"}`} style={{ height: `${v * 100}%`, animationDelay: "0.4s" }} />
                <div className={`num relative text-[clamp(22px,3.6vw,34px)] font-semibold ${v === mx ? "text-gold" : ""}`}>{pct(v)}</div>
                <div className="relative mt-1 line-clamp-2 text-[11.5px] font-semibold leading-tight text-chalk-2 sm:text-[12px]">{l}</div>
              </div>
            ))}
          </div>
          <p className="mx-auto mt-7 max-w-[62ch] text-center text-[clamp(15.5px,2vw,20px)] leading-relaxed text-chalk-2">
            <b className="text-chalk">{v.lead}</b>; {v.rest}
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            {p.fijas?.length > 0 && <a href="#fijas" className="pop-in tag bg-gold px-2.5 py-1 text-night-900"><ShieldCheck className="h-3.5 w-3.5" />{p.fijas.length === 1 ? "1 fija" : `${p.fijas.length} fijas`}</a>}
            {p.auditoria && <span className={`tag px-2.5 py-1 ${p.auditoria.estado === "ok" ? "bg-turf-soft text-turf" : p.auditoria.estado === "revisar" ? "bg-gold-soft text-gold" : "bg-flare/15 text-flare"}`}>{p.auditoria.estado === "ok" ? <ShieldCheck className="h-3.5 w-3.5" /> : <ShieldAlert className="h-3.5 w-3.5" />}{p.auditoria.estado === "ok" ? "Auditoría ok" : p.auditoria.estado === "revisar" ? "Con avisos" : "Bloqueado"}</span>}
            <span className="tag bg-white/[0.06] px-2.5 py-1 text-chalk-2"><Gavel className="h-3.5 w-3.5" />{p.arbitro?.nombre || "Árbitro por confirmar"}</span>
            {p.mercado && <span className="tag bg-cobalt-soft px-2.5 py-1 text-cobalt">Con cuotas</span>}
            {ops.length > 0 && <span className="tag bg-turf-soft px-2.5 py-1 text-turf">{ops.length === 1 ? "1 oportunidad" : `${ops.length} oportunidades`}</span>}
          </div>
        </div>
      </section>

      <div className="mt-12 grid gap-8 xl:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0">
      {/* OPORTUNIDADES */}
      <section>
        {ops.length > 0 ? (
          <>
            <SectionHead eyebrow="Modelo · historial · recientes · jugadores · cuota" title={ops.length === 1 ? "La oportunidad de este partido" : `${ops.length} oportunidades en este partido`}
              sub="Picks que las cinco señales respaldan, ordenados por puntaje. La primera es la destacada del partido." />
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {ops.map((o: any, i: number) => <div key={o.clave} className="row-in" style={{ animationDelay: `${i * 0.06}s` }}><OportunidadCard o={o} /></div>)}
            </div>
          </>
        ) : (
          <>
            <SectionHead title="Opciones más probables" sub="Ningún pick de este partido pasó los filtros de oportunidad: aquí van las opciones más probables según el modelo." />
            <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
              {picks.map((k, i) => <div key={i} className="row-in" style={{ animationDelay: `${i * 0.06}s` }}><Ticket k={k} compact /></div>)}
            </div>
          </>
        )}
        {jugOps.length > 0 && (
          <div className="mt-8">
            <h3 className="mb-3 text-[18px] font-extrabold">Oportunidades de jugadores</h3>
            <div className="grid gap-4 sm:grid-cols-2">{jugOps.map((o: any, i: number) => <JugadorCard key={i} o={o} />)}</div>
          </div>
        )}
      </section>

      {/* DETALLE */}
      <section className="mt-14 pb-20">
        <div className="sticky top-[60px] z-20 -mx-4 bg-night-900/85 px-4 backdrop-blur-xl sm:top-[68px] sm:-mx-6 sm:px-6 lg:mx-0 lg:px-0">
        <Tabs id="det" value={tab} onChange={setTab} tabs={[["resumen", "Resumen"], ["jugadores", "Jugadores"], ["mercados", "Todos los mercados"], ["modelos", "Modelos y árbitro"], ["stats", "Estadísticas"], ["cuotas", "Cuotas y calculadora"]]} />
        </div>
        <div id="det-panel" role="tabpanel" aria-labelledby={`det-${tab}`} className="pt-7">
          <div key={tab} className="page-in">
              {tab === "resumen" && <Resumen p={p} />}
              {tab === "jugadores" && <Jugadores p={p} />}
              {tab === "mercados" && <Mercados p={p} />}
              {tab === "modelos" && <Modelos p={p} />}
              {tab === "stats" && <Stats p={p} />}
              {tab === "cuotas" && <Cuotas p={p} />}
          </div>
        </div>
      </section>
      </div>
      <Aside p={p} />
      </div>
    </div>
  );
}

const FIJA_LABEL: Record<string, string> = Object.fromEntries((DATA.fijas?.lista || []).map((f: any) => [f.id + f.clave, f.seleccion]));

/** Resumen fijo al costado (escritorio): el ensamble, goles, árbitro, fijas y auditoría de un vistazo. */
function Aside({ p }: { p: any }) {
  const m = p.mercados, x = m["1x2"];
  const rows: [string, number, string][] = [[p.local, x["1"], "bg-cobalt"], ["Empate", x.X, "bg-white/30"], [p.visita, x["2"], "bg-turf"]];
  return (
    <aside className="hidden xl:block">
      <div className="sticky top-[88px] flex flex-col gap-4">
        <div className="spot card p-5">
          <div className="eyebrow">Ensamble de 6 modelos</div>
          <div className="mt-4 flex flex-col gap-3">
            {rows.map(([l, v, c]) => (
              <div key={l}>
                <div className="mb-1 flex justify-between gap-3 text-[13.5px]"><span className="truncate">{l}</span><b className="num">{pct(v)}</b></div>
                <Meter p={v} color={c} />
              </div>
            ))}
          </div>
          <div className="mt-5 grid grid-cols-3 gap-2 border-t border-white/[0.07] pt-4 text-center">
            {[["xG", `${m.xg_home.toFixed(1)}–${m.xg_away.toFixed(1)}`], ["+2.5", pct(m.goles_totales["2.5"].over)], ["Ambos", pct(m.ambos_marcan.si)]].map(([l, v]) => (
              <div key={l}><div className="num text-[16px] font-semibold">{v}</div><div className="text-[11px] text-chalk-3">{l}</div></div>
            ))}
          </div>
        </div>
        {p.fijas?.length > 0 && (
          <a href="#fijas" className="glow-border card block p-5">
            <div className="flex items-center gap-2 text-[13px] font-bold text-gold"><ShieldCheck className="h-4 w-4" />Fija{p.fijas.length > 1 ? "s" : ""} de este partido</div>
            <ul className="mt-2 grid gap-1 text-[15px] font-bold">{p.fijas.map((k: string) => <li key={k}>{FIJA_LABEL[p.id + k] || k}</li>)}</ul>
          </a>
        )}
        <div className="card p-5 text-[13.5px] text-chalk-2">
          <div className="flex items-center gap-2 font-bold text-chalk"><Gavel className="h-4 w-4 text-gold" />{p.arbitro?.nombre || "Árbitro por confirmar"}</div>
          {p.arbitro?.partidos ? <p className="mt-1.5">Factor de tarjetas <b className="num text-chalk">×{p.arbitro.factor.toFixed(2)}</b> en {p.arbitro.partidos} partidos.</p>
            : <p className="mt-1.5 text-chalk-3">Las tarjetas usan solo a los equipos hasta que haya designación.</p>}
          {m.tarjetas && <p className="mt-1">Amarillas esperadas: <b className="num text-chalk">{m.tarjetas.esperadas_total.toFixed(1)}</b></p>}
          {m.corners && <p className="mt-1">Córners esperados: <b className="num text-chalk">{m.corners.esperados_total.toFixed(1)}</b></p>}
        </div>
        <div className="card p-5">
          <div className="flex items-center justify-between text-[13px]"><span className="font-bold">Confianza en los datos</span><span className="num">{pct(p.confianza)}</span></div>
          <Meter p={p.confianza} color={p.confianza >= 0.7 ? "bg-turf" : p.confianza >= 0.4 ? "bg-gold" : "bg-flare"} className="mt-2" />
          {p.auditoria?.notas?.length > 0 && <p className="mt-3 text-[12.5px] leading-relaxed text-chalk-3">{p.auditoria.notas[0]}</p>}
        </div>
      </div>
    </aside>
  );
}

function Resumen({ p }: { p: any }) {
  const m = p.mercados, f = keyFacts(p);
  const quick: [string, number][] = [["Más de 1.5 goles", m.goles_totales["1.5"].over], ["Más de 2.5 goles", m.goles_totales["2.5"].over], ["Ambos marcan", m.ambos_marcan.si],
    [`${p.local} o empate`, m.doble_oportunidad["1X"]], [`${p.visita} o empate`, m.doble_oportunidad.X2], ["Gol en el 1er tiempo", m.primer_tiempo_goles["0.5"].over]];
  if (m.corners) quick.push(["Más de 8.5 córners", m.corners.total["8.5"].over]);
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div className="card p-6">
        <h3 className="text-[20px] font-extrabold">Lo que tienes que saber</h3>
        <ul className="mt-5 flex flex-col gap-4">
          {f.map((t, i) => (
            <li key={i} style={{ animationDelay: `${i * 0.05}s` }} className="row-in grid grid-cols-[30px_1fr] gap-3 text-[15px] leading-relaxed text-chalk-2">
              <span className="grid h-[30px] w-[30px] place-items-center rounded-lg bg-cobalt-soft text-[13px] font-extrabold text-cobalt">{i + 1}</span><span>{bold(t)}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="card p-6">
        <h3 className="text-[20px] font-extrabold">Probabilidades rápidas</h3>
        <p className="mt-1 text-[13.5px] text-chalk-3">Los mercados más buscados. A la derecha, la cuota justa.</p>
        <div className="mt-5 flex flex-col gap-4">
          {quick.map(([l, v], i) => (
            <div key={i}>
              <div className="mb-1.5 flex items-baseline justify-between gap-3 text-[14.5px]"><span>{l}</span><span className="num"><b>{pct(v)}</b> <span className="ml-2 text-chalk-3">{fair(v)}</span></span></div>
              <Meter p={v} color={v >= 0.7 ? "bg-turf" : v >= 0.5 ? "bg-cobalt" : "bg-chalk-3"} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const AUD: Record<string, [string, string]> = { ok: ["Revisado: sin problemas", "bg-turf-soft text-turf"], revisar: ["Revisado: con avisos", "bg-gold-soft text-gold"], bloqueado: ["Bloqueado por el auditor", "bg-flare/15 text-flare"] };

function Modelos({ p }: { p: any }) {
  const N = DATA.metodologia?.nombres || {};
  const L = p.modelos?.lista || [];
  const x = p.mercados["1x2"], a = p.auditoria, r = p.arbitro, t = p.mercados.tarjetas;
  return (
    <div className="grid gap-5 lg:grid-cols-[1.25fr_.75fr]">
      <div className="card p-6">
        <h3 className="text-[20px] font-extrabold">Los 6 modelos</h3>
        <p className="mt-1 text-[13.5px] text-chalk-3">Cada uno da su 1X2; el ensamble los combina con los pesos calibrados contra partidos ya jugados.</p>
        <div className="-mx-2 mt-4 overflow-x-auto">
          <table className="pz">
            <thead><tr><th>Modelo</th><th className="n">{p.local}</th><th className="n">Empate</th><th className="n">{p.visita}</th><th className="n">+2.5</th><th className="n">Peso</th></tr></thead>
            <tbody>
              {L.map((m: any) => (
                <tr key={m.clave}><td>{N[m.clave] || m.clave}</td><td className="n">{pct(m["1"])}</td><td className="n">{pct(m.X)}</td><td className="n">{pct(m["2"])}</td>
                  <td className="n">{m.o25 != null ? pct(m.o25) : "–"}</td><td className="n text-chalk-3">{pct(m.peso)}</td></tr>
              ))}
              <tr className="bg-gold-soft font-bold"><td className="text-gold">Ensamble</td><td className="n">{pct(x["1"])}</td><td className="n">{pct(x.X)}</td><td className="n">{pct(x["2"])}</td><td className="n">{pct(p.mercados.goles_totales["2.5"].over)}</td><td className="n">100%</td></tr>
            </tbody>
          </table>
        </div>
        {p.modelos?.elo && <p className="mt-3 text-[13px] text-chalk-3">Elo: {p.local} {p.modelos.elo[0]} · {p.visita} {p.modelos.elo[1]}. <a href="#metodo" className="font-semibold text-gold hover:underline">Qué mide cada modelo</a></p>}
      </div>
      <div className="flex flex-col gap-5">
        <div className="card p-6">
          <h3 className="text-[20px] font-extrabold">Árbitro y tarjetas</h3>
          {r ? (
            <div className="mt-3 text-[14.5px] leading-relaxed text-chalk-2">
              <div className="text-[18px] font-bold text-chalk">{r.nombre}</div>
              {r.partidos ? <p className="mt-1">{r.partidos} partidos en los datos · {r.tarjetas_prom} amarillas por partido (se esperaban {r.esperadas_prom}).
                Factor <b className={`num ${r.factor > 1.03 ? "text-flare" : r.factor < 0.97 ? "text-turf" : "text-chalk"}`}>×{r.factor.toFixed(2)}</b>{r.factor > 1.03 ? ": saca más tarjetas que la media." : r.factor < 0.97 ? ": saca menos tarjetas que la media." : ": en la media."}</p>
                : <p className="mt-1">Sin partidos suyos en los datos: se usa la media de la liga.</p>}
              {r.tarjetas_con_arbitro != null && <p className="mt-2">Amarillas esperadas: <b className="num text-chalk">{r.tarjetas_con_arbitro.toFixed(1)}</b> <span className="text-chalk-3">(sin el árbitro serían {r.tarjetas_sin_arbitro.toFixed(1)})</span></p>}
            </div>
          ) : <p className="mt-2 text-[14.5px] text-chalk-2">Árbitro aún sin confirmar. Las tarjetas esperadas ({t ? t.esperadas_total.toFixed(1) : "–"}) usan solo a los equipos; se ajustan solas cuando se publique la designación.</p>}
        </div>
        {a && (
          <div className="card p-6">
            <h3 className="text-[20px] font-extrabold">Auditoría automática</h3>
            <span className={`tag mt-3 inline-block ${AUD[a.estado]?.[1]}`}>{AUD[a.estado]?.[0]}</span>
            {a.notas?.length > 0 && <ul className="mt-3 flex list-disc flex-col gap-1.5 pl-5 text-[14px] text-chalk-2">{a.notas.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul>}
          </div>
        )}
      </div>
    </div>
  );
}

function Jugadores({ p }: { p: any }) {
  const [full, setFull] = useState(false);
  const tbl = (list: any[], team: string) => {
    const L = (list || []).map(unpack);
    if (!L.length) return <div className="card p-6"><h3 className="text-[19px] font-extrabold">{team}</h3><p className="mt-2 text-chalk-3">Sin datos recientes de jugadores.</p></div>;
    const top = [...L].sort((a, b) => b.prob.marca - a.prob.marca).slice(0, 3);
    return (
      <div className="card p-6">
        <div className="flex items-center gap-3"><Badge name={team} size={34} /><h3 className="text-[20px] font-extrabold">{team}</h3></div>
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          {top.map((j, i) => (
            <div key={j.nombre} style={{ animationDelay: `${i * 0.08}s` }} className="row-in flex items-center gap-3 rounded-xl bg-white/[0.04] p-3 ring-1 ring-white/10">
              <Ring p={j.prob.marca} size={54} stroke={5} color="#FFC23D" />
              <div className="min-w-0"><div className="truncate font-bold">{j.nombre}</div><div className="text-[12.5px] text-chalk-3">probabilidad de marcar · {j.min}'</div></div>
            </div>
          ))}
        </div>
        <div className="-mx-2 mt-5 overflow-x-auto">
          <table className="pz">
            <thead><tr><th>Jugador</th><th className="n">Min</th><th className="n">Marca</th><th className="n">Tiro al arco</th><th className="n">2+ tiros</th><th className="n">Tarjeta</th>
              {full && <><th className="n">Asiste</th><th className="n">Gol o asist.</th><th className="n">1+ tiros</th><th className="n">2+ al arco</th><th className="n">1+ faltas</th><th className="n">Goles temp.</th><th className="n">Tiros temp.</th><th className="n">TA temp.</th></>}</tr></thead>
            <tbody>
              {L.map((j) => { const q = j.prob, t = j.temp; return (
                <tr key={j.nombre} className="transition-colors hover:bg-white/[0.03]">
                  <td title={j.ult}><b>{j.nombre}</b> <span className="text-[12.5px] text-chalk-3">{j.pos}{j.tit < 0.6 ? " · suplente" : ""}</span></td>
                  <td className="n">{j.min}'</td>
                  <td className={`n ${q.marca >= 0.35 ? "font-bold text-gold" : ""}`}>{pct(q.marca)}</td>
                  <td className={`n ${q["arco_1+"] >= 0.6 ? "font-bold text-turf" : ""}`}>{pct(q["arco_1+"])}</td>
                  <td className="n">{pct(q["tiros_2+"])}</td><td className="n">{pct(q.tarjeta)}</td>
                  {full && <><td className="n">{pct(q.asiste)}</td><td className="n">{pct(q.gol_o_asist)}</td><td className="n">{pct(q["tiros_1+"])}</td><td className="n">{pct(q["arco_2+"])}</td><td className="n">{pct(q["faltas_1+"])}</td><td className="n">{t.goles}</td><td className="n">{t.tiros}</td><td className="n">{t.ta}</td></>}
                </tr>); })}
            </tbody>
          </table>
        </div>
      </div>
    );
  };
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex max-w-[64ch] items-start gap-2 text-[14px] text-chalk-3"><Info className="mt-0.5 h-4 w-4 shrink-0" />Probabilidad de cada jugador en este partido, según sus minutos recientes y el rival. Confirma la alineación una hora antes.</p>
        <button onClick={() => setFull(!full)} aria-pressed={full} className="chip">{full ? "Ver menos columnas" : "Ver todas las columnas"}</button>
      </div>
      {tbl(p.jugadores?.local, p.local)}
      {tbl(p.jugadores?.visita, p.visita)}
    </div>
  );
}

function Mercados({ p }: { p: any }) {
  const m = p.mercados;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[14px] text-chalk-3">Probabilidad y cuota justa de cada opción. Abre solo lo que te interese.</p>
      {GROUPS.map(([g, sub, keys], i) => {
        const ks = keys.filter((k) => m[k] && typeof m[k] === "object");
        if (!ks.length) return null;
        return (
          <Accordion key={g} title={g} sub={sub} defaultOpen={i === 0}>
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {ks.map((k) => (
                <div key={k}>
                  <div className="mb-2 flex justify-between text-[11.5px] font-bold uppercase tracking-[0.08em] text-chalk-3"><span>{MK_NAMES[k]}</span><span>Prob. · Justa</span></div>
                  {marketRows(p, k, m[k]).map((r, j) => (
                    <div key={j} className="border-t border-white/[0.06] py-2">
                      <div className="flex items-baseline justify-between gap-3 text-[14px]">
                        <span>{r.label}{r.extra && <span className="ml-1 text-[12px] text-chalk-3">({r.extra})</span>}</span>
                        {r.p != null ? <span className="num shrink-0"><b>{pct(r.p, 1)}</b><span className="ml-2 text-chalk-3">{fair(r.p)}</span></span> : <span className="num">{r.value}</span>}
                      </div>
                      {r.p != null && <Meter p={r.p} className="mt-1.5 h-1" color="bg-cobalt/80" />}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </Accordion>
        );
      })}
    </div>
  );
}

function Stats({ p }: { p: any }) {
  const L = p.perfil_local.temporada || {}, V = p.perfil_visita.temporada || {};
  const items: [string, string, boolean?, string?][] = ([["Puntos por partido", "ppp"], ["Goles a favor", "gf"], ["Goles en contra", "gc", true], ["xG a favor", "xgf"], ["Tiros", "tiros"], ["Tiros al arco", "tiros_arco"], ["Córners", "corners"],
    ["Partidos con +2.5 goles", "over25_pct", false, "%"], ["Ambos marcan", "btts_pct", false, "%"], ["Valla invicta", "valla_invicta_pct", false, "%"]] as any).filter(([, k]: any) => L[k] != null && V[k] != null);
  const last = (pr: any, name: string) => (
    <div className="card p-6">
      <div className="flex items-center gap-3"><Badge name={name} size={32} /><h3 className="text-[19px] font-extrabold">{name}</h3></div>
      <p className="mt-1 text-[13.5px] text-chalk-3">{pr.racha || "Últimos partidos"}</p>
      <div className="mt-4 flex flex-col gap-2">
        {pr.ultimos.map((m: any, i: number) => (
          <div key={i} style={{ animationDelay: `${i * 0.04}s` }} className="row-in grid grid-cols-[46px_16px_minmax(0,1fr)_auto_20px] items-center gap-2 text-[13.5px] sm:grid-cols-[52px_18px_minmax(0,1fr)_auto_20px] sm:text-[14px]">
            <span className="num text-chalk-3">{m.fecha.slice(0, 5)}</span><span className="text-chalk-3">{m.cond}</span><span className="truncate">{m.rival}</span><span className="num font-semibold">{m.marcador}</span>
            <FormDots s={m.res} />
          </div>
        ))}
      </div>
    </div>
  );
  const h = p.h2h;
  return (
    <div className="flex flex-col gap-5">
      <div className="card p-6">
        <h3 className="text-[20px] font-extrabold">Cara a cara esta temporada</h3>
        <div className="mt-4 grid grid-cols-2 text-[14px] font-bold"><span className="text-cobalt">{p.local}</span><span className="text-right text-turf">{p.visita}</span></div>
        <div className="mt-3 flex flex-col gap-4">
          {items.length ? items.map(([lab, k, inv, u]) => {
            const a = +L[k], b = +V[k], mx = Math.max(a, b, 0.01);
            return (
              <div key={k} className="grid grid-cols-[56px_1fr_56px] items-center gap-3">
                <span className="num font-semibold">{a}{u || ""}</span>
                <div>
                  <div className="mb-1.5 text-center text-[12.5px] text-chalk-2">{lab}{inv ? " (menos es mejor)" : ""}</div>
                  <div className="grid grid-cols-2 gap-1">
                    <div className="flex h-2 justify-end overflow-hidden rounded-full bg-white/[0.06]"><i className="grow-x block h-full rounded-full bg-cobalt" style={{ width: `${(a / mx) * 100}%`, transformOrigin: "right" }} /></div>
                    <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]"><i className="grow-x block h-full rounded-full bg-turf" style={{ width: `${(b / mx) * 100}%` }} /></div>
                  </div>
                </div>
                <span className="num text-right font-semibold">{b}{u || ""}</span>
              </div>
            );
          }) : <p className="text-chalk-3">Sin datos suficientes.</p>}
        </div>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">{last(p.perfil_local, p.local)}{last(p.perfil_visita, p.visita)}</div>
      <div className="card p-6">
        <h3 className="text-[20px] font-extrabold">Historial entre ambos</h3>
        {h.partidos.length ? (
          <div className="mt-4 flex flex-col gap-2">
            {h.partidos.map((m: any, i: number) => (
              <div key={i} className="grid grid-cols-[76px_1fr_auto_1fr] items-center gap-3 rounded-xl bg-white/[0.03] px-3 py-2.5 text-[14px]">
                <span className="num text-chalk-3">{m.fecha}</span><span className="truncate text-right">{m.local}</span><span className="num rounded-md bg-white/10 px-2 py-0.5 font-bold">{m.marcador}</span><span className="truncate">{m.visita}</span>
              </div>
            ))}
          </div>
        ) : <p className="mt-2 text-chalk-3">No se enfrentaron en los datos disponibles.</p>}
      </div>
    </div>
  );
}

function Cuotas({ p }: { p: any }) {
  const opts = useMemo(() => allSelections(p), [p]);
  const [i, setI] = useState(0);
  const [o, setO] = useState("");
  const prob = opts[i]?.p ?? 0, od = parseFloat(o.replace(",", "."));
  const ev = od > 1 ? prob * od - 1 : null;
  const kelly = od > 1 ? Math.max(0, (prob * (od - 1) - (1 - prob)) / (od - 1)) * DATA.config.kelly : 0;
  const c = p.cuotas;
  return (
    <div className="grid gap-5 lg:grid-cols-[1.1fr_.9fr]">
      <div className="card relative overflow-hidden p-6">
        <div className="pointer-events-none absolute -right-20 -top-20 h-56 w-56 rounded-full bg-gold/10 blur-3xl" />
        <div className="relative flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-gold-soft text-gold"><Calculator className="h-5 w-5" /></span><h3 className="text-[20px] font-extrabold">¿Me conviene?</h3></div>
        <p className="relative mt-2 text-[14px] text-chalk-3">Elige la apuesta y escribe la cuota que te da tu casa.</p>
        <div className="relative mt-5 grid gap-3 sm:grid-cols-[1fr_130px]">
          <select value={i} onChange={(e) => setI(+e.target.value)} aria-label="Apuesta" className="min-w-0 rounded-xl border border-white/10 bg-night-850 px-3 py-3 text-[14.5px] text-chalk focus:border-cobalt focus:outline-none">
            {opts.map((r, k) => <option key={k} value={k}>{r.l} ({pct(r.p, 1)})</option>)}
          </select>
          <input value={o} onChange={(e) => setO(e.target.value)} inputMode="decimal" placeholder="Cuota, ej. 1.85" aria-label="Cuota de tu casa"
            className="rounded-xl border border-white/10 bg-night-850 px-3 py-3 text-[15px] text-chalk placeholder:text-chalk-3 focus:border-cobalt focus:outline-none" />
        </div>
          <div key={ev == null ? "none" : ev > 0 ? "yes" : "no"}
            aria-live="polite" className={`page-in relative mt-5 rounded-2xl p-5 ${ev == null ? "bg-white/[0.04]" : ev > 0 ? "bg-turf-soft ring-1 ring-turf/40" : "bg-flare/10 ring-1 ring-flare/30"}`}>
            {ev == null ? (
              <p className="text-[15px] text-chalk-2">Cuota justa: <b className="num text-chalk">{fair(prob)}</b>. Si tu casa paga más, la apuesta tiene valor.</p>
            ) : ev > 0 ? (
              <div className="flex items-center gap-5">
                <Ring p={Math.min(1, ev * 4)} size={70} color="#2FE0A0" label={<span className="num text-[14px] font-bold text-turf">+{(ev * 100).toFixed(0)}%</span>} />
                <p className="text-[15px] leading-relaxed text-chalk-2"><b className="text-turf">Tiene valor.</b> A la larga ganarías en promedio <b className="num text-chalk">{(ev * 100).toFixed(1)}%</b> de lo apostado. Apuesta como máximo <b className="num text-chalk">{pct(kelly, 1)}</b> de tu banca.</p>
              </div>
            ) : (
              <p className="text-[15px] leading-relaxed text-chalk-2"><b className="text-flare">Sin valor.</b> Esta cuota paga menos de lo que debería (la justa es <b className="num text-chalk">{fair(prob)}</b>). A la larga perderías <b className="num text-chalk">{(ev * -100).toFixed(1)}%</b>.</p>
            )}
          </div>
      </div>
      <div className="card p-6">
        <h3 className="text-[20px] font-extrabold">Cuotas publicadas</h3>
        {c ? (
          <>
            <p className="mt-1 text-[13.5px] text-chalk-3">De {c.provider || "una casa de referencia"}. En dorado, las que pagan más que la cuota justa.</p>
            <div className="mt-4 flex flex-col gap-2">
              {p.valor.map((r: any, k: number) => (
                <div key={k} className={`grid grid-cols-[1fr_auto_auto] items-center gap-4 rounded-xl px-3 py-2.5 text-[14px] ${r.valor ? "bg-gold-soft ring-1 ring-gold/40" : "bg-white/[0.03]"}`}>
                  <span>{r.mercado}: <b>{r.seleccion}</b></span>
                  <span className="num text-chalk-3">{odd(r.cuota)}</span>
                  <span className={`num font-semibold ${r.ev > 0 ? "text-turf" : "text-flare"}`}>{r.ev > 0 ? "+" : ""}{(r.ev * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
            <p className="mt-4 text-[13px] text-chalk-3">Movimiento: {odd(c.H_open)} / {odd(c.D_open)} / {odd(c.A_open)} → {odd(c.H)} / {odd(c.D)} / {odd(c.A)}</p>
          </>
        ) : <p className="mt-2 text-chalk-3">Todavía no hay cuotas publicadas. Usa la calculadora con la cuota de tu casa.</p>}
      </div>
      <Reveal className="lg:col-span-2"><p className="text-[13px] text-chalk-3">Ninguna apuesta es segura. El stake sugerido es un tope, calculado con ¼ de Kelly.</p></Reveal>
    </div>
  );
}

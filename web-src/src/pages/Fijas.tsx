/* eslint-disable @typescript-eslint/no-explicit-any */
import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { BellRing, FlaskConical } from "lucide-react";
import { BY_ID, DATA, MATCHES, NOW, OPS, dayKey, dayLabel, dayShort, isLive, pct } from "@/lib/data";
import { Page, PageHeader, Reveal } from "@/components/ui-pz";
import { JugadorCard, OportunidadCard, SENALES } from "@/components/oport";

const CUOTAS: [number, string][] = [[0, "Todas"], [1.5, "≥ 1.50"], [1.8, "≥ 1.80"]];

export default function Fijas({ tab: initial = "fijas" }: { tab?: string }) {
  const [tab, setTab] = useState(initial);
  const F = DATA.fijas || { lista: [], criterios: {} };
  const c = F.criterios || {};
  const R = DATA.resultados || {};
  const fijas = (F.lista || []).filter((f: any) => new Date(f.fecha).getTime() > NOW);
  const jugadores = MATCHES.filter((p) => !isLive(p)).flatMap((p) => (p.oportunidades_jugador || []).map((o: any) => ({ p, o })));
  const pesos = c.pesos || {};
  return (
    <Page>
      <PageHeader eyebrow="Picks con respaldo" title={<span className="text-shine">Fijas y oportunidades</span>}
        sub={<>Cada pick se cruza con <b className="text-chalk">cinco señales</b>: el modelo, el historial de ese tipo de pick, los últimos partidos de ambos equipos, los jugadores y la cuota.
          Una <b className="text-chalk">oportunidad</b> es un pick que esas señales respaldan; una <b className="text-gold">fija</b> es una oportunidad donde todo confirma. A cualquier cuota.</>}
        stats={[{ v: fijas.length, l: "fijas en los próximos 3 días", tone: "gold" }, { v: OPS.length, l: "oportunidades de partido" },
          { v: jugadores.length, l: "oportunidades de jugador", tone: "cobalt" },
          { v: R.oportunidades?.acierto != null ? pct(R.oportunidades.acierto) : "–", l: R.oportunidades?.n ? `acierto real (esperado ${pct(R.oportunidades.esperado)})` : "acierto real: aún sin liquidar", tone: "turf" }]} />

      <div role="tablist" className="mb-6 inline-flex max-w-full rounded-full border border-white/10 bg-white/[0.03] p-1">
        {[["fijas", `Fijas (${fijas.length})`], ["oportunidades", `Oportunidades (${OPS.length + jugadores.length})`]].map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={`relative rounded-full px-4 py-2 text-[14px] font-bold transition-colors sm:px-5 ${tab === k ? "text-night-900" : "text-chalk-2 hover:text-chalk"}`}>
            {tab === k && <motion.span layoutId="fx-tab" className="absolute inset-0 rounded-full bg-gold" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
            <span className="relative">{l}</span>
          </button>
        ))}
      </div>

      {F.modo === "calibracion" && (
        <div className="card mb-6 flex items-start gap-4 p-5">
          <FlaskConical className="h-6 w-6 shrink-0 text-gold" />
          <p className="text-[14.5px] leading-relaxed text-chalk-2"><b className="text-chalk">En calibración.</b> Todavía no hay {c.volumen_30d} picks reales liquidados en 30 días, así que el historial de cada tipo de pick sale del backtest (partidos pasados pronosticados solo con datos anteriores).</p>
        </div>
      )}

      {tab === "fijas" && (
        <div className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-3 rounded-2xl border border-white/[0.07] bg-white/[0.03] px-4 py-3 sm:px-5">
          <BellRing className="h-5 w-5 shrink-0 text-gold" aria-hidden="true" />
          <p className="min-w-[12rem] flex-1 text-[14.5px] text-chalk-2"><b className="text-chalk">Recibe un aviso 30 min antes de cada fija.</b> Gratis, sin registrarte.</p>
          <a href="#avisos" className="chip !border-gold/40 !text-gold hover:!bg-gold-soft">Activar avisos</a>
        </div>
      )}

      {tab === "fijas" ? <FijasList fijas={fijas} /> : <OportunidadesList jugadores={jugadores} />}

      <Reveal><div className="card mt-12 p-5 sm:p-7">
        <h2 className="text-[20px] font-extrabold">Cómo se eligen</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {SENALES.map(([k, l]) => (
            <div key={k} className="spot rounded-xl bg-white/[0.03] p-4 ring-1 ring-white/[0.06]">
              <div className="flex items-baseline justify-between"><b className="text-chalk">{l}</b><span className="num text-[12.5px] text-gold">{pct(pesos[k] ?? 0)}</span></div>
              <p className="mt-1.5 text-[13px] leading-relaxed text-chalk-2">{({
                historial: "Funciona como veto y no suma puntos: si en ese tipo de pick, competición y rango de probabilidad el modelo exagera de forma comprobada, el pick se descarta.",
                reciente: "En los últimos 8 partidos de cada equipo, ¿cuántas veces se cumplió? Tiene que ser al menos lo que dice el modelo.",
                jugadores: "Goleadores en forma para picks de goles, tarjeteros para tarjetas. Si los jugadores contradicen el pick, se descarta.",
                cuota: "Si la casa publica cuota, ¿paga más que la justa? Un valor mayor a +20% se marca para revisar.",
                probabilidad: "A igualdad de lo demás, un pick más probable es más sólido.",
              } as Record<string, string>)[k]}</p>
            </div>
          ))}
        </div>
        <ul className="mt-5 grid gap-2 text-[14px] leading-relaxed text-chalk-2">
          <li><b className="text-chalk">Oportunidad:</b> puntaje de {c.min_puntaje ?? 74} o más, cuota justa entre {c.min_cuota?.toFixed(2)} y {c.max_cuota?.toFixed(2)}. Hasta 3 por partido, sin repetir grupo de mercado.</li>
          <li><b className="text-gold">Fija:</b> puntaje de {c.fija_puntaje} o más, sin veto del historial y con los últimos partidos por encima de lo que dice el modelo. Máximo 1 por partido y {c.max_dia} por día.</li>
          <li><b className="text-chalk">"Apuesta si paga ≥":</b> la cuota justa más un {Math.round(((c.margen || 1.05) - 1) * 100)}% de margen. Si tu casa paga menos, no conviene aunque el pick sea bueno.</li>
        </ul>
      </div></Reveal>
    </Page>
  );
}

function DayHead({ d, n }: { d: string; n: number }) {
  return (
    <div className="mb-3 flex items-center gap-3">
      <h3 className="font-display text-[15px] font-extrabold uppercase tracking-[0.06em] text-chalk-3" style={{ fontStretch: "112%" }}>{dayLabel(d)}</h3>
      <span className="h-px flex-1 bg-white/[0.07]" /><span className="num text-[12.5px] text-chalk-3">{n}</span>
    </div>
  );
}

function FijasList({ fijas }: { fijas: any[] }) {
  const days = [...new Set(fijas.map((f) => dayKey(f.fecha)))] as string[];
  if (!fijas.length) return <div className="card p-10 text-center text-chalk-3">Hoy ningún pick pasa todos los filtros. Revisa las oportunidades: tienen respaldo, aunque no todas las señales al máximo.</div>;
  return (
    <>
      {days.map((d) => (
        <section key={d} className="mt-8 first:mt-0">
          <DayHead d={d} n={fijas.filter((f) => dayKey(f.fecha) === d).length} />
          <div className="fit-grid">
            {fijas.filter((f) => dayKey(f.fecha) === d).map((f, i) => <div key={i} className="row-in" style={{ animationDelay: `${i * 0.05}s` }}><OportunidadCard o={f} p={BY_ID[f.id]} /></div>)}
          </div>
        </section>
      ))}
    </>
  );
}

function OportunidadesList({ jugadores }: { jugadores: { p: any; o: any }[] }) {
  const days = useMemo(() => [...new Set(OPS.map(({ p }) => dayKey(p.fecha)))].slice(0, 10) as string[], []);
  const [day, setDay] = useState<string | null>(null);
  const [minC, setMinC] = useState(0);
  const [orden, setOrden] = useState<"puntaje" | "cuota" | "hora">("puntaje");
  const [tipo, setTipo] = useState<"partido" | "jugador">("partido");
  const dsel = day && days.includes(day) ? day : days[0];
  const list = (tipo === "partido" ? OPS : jugadores)
    .filter(({ p, o }) => dayKey(p.fecha) === dsel && o.cuota_justa >= minC)
    .sort((a, b) => orden === "puntaje" ? b.o.puntaje - a.o.puntaje : orden === "cuota" ? b.o.cuota_justa - a.o.cuota_justa : a.p.fecha.localeCompare(b.p.fecha));
  const chip = (on: boolean) => `chip ${on ? "!border-transparent !bg-chalk !text-night-900" : ""}`;
  return (
    <>
      <div className="scrollbar-none -mx-4 flex snap-x gap-2 overflow-x-auto px-4 pb-1 sm:-mx-6 sm:px-6 lg:mx-0 lg:px-0" role="group" aria-label="Día">
        {days.map((d) => (
          <button key={d} onClick={() => setDay(d)} aria-pressed={d === dsel} className={`relative shrink-0 snap-start rounded-xl px-4 py-2 text-left transition ${d === dsel ? "text-night-900" : "text-chalk-2 hover:bg-white/5"}`}>
            {d === dsel && <motion.span layoutId="op-day" className="absolute inset-0 rounded-xl bg-gold" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
            <span className="relative block text-[14px] font-bold capitalize">{dayShort(d)}</span>
            <span className="relative block text-[11.5px] opacity-70">{OPS.filter(({ p }) => dayKey(p.fecha) === d).length} oport.</span>
          </button>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex gap-1.5" role="group" aria-label="Tipo">
          <button className={chip(tipo === "partido")} aria-pressed={tipo === "partido"} onClick={() => setTipo("partido")}>Partido</button>
          <button className={chip(tipo === "jugador")} aria-pressed={tipo === "jugador"} onClick={() => setTipo("jugador")}>Jugador</button>
        </div>
        <div className="flex gap-1.5" role="group" aria-label="Cuota justa mínima">
          {CUOTAS.map(([v, l]) => <button key={v} className={chip(minC === v)} aria-pressed={minC === v} onClick={() => setMinC(v)}>{l}</button>)}
        </div>
        <label className="flex items-center gap-2 text-[13px] text-chalk-3 sm:ml-auto">Ordenar
          <select value={orden} onChange={(e) => setOrden(e.target.value as any)} className="rounded-lg border border-white/10 bg-night-850 px-2 py-1.5 text-[13.5px] text-chalk focus:border-cobalt focus:outline-none">
            <option value="puntaje">por puntaje</option><option value="cuota">por cuota</option><option value="hora">por hora</option>
          </select>
        </label>
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {list.length ? list.map(({ p, o }, i) => (
          <div key={p.id + (o.clave || o.seleccion)} className="row-in" style={{ animationDelay: `${Math.min(i, 12) * 0.04}s` }}>
            {tipo === "partido" ? <OportunidadCard o={o} p={p} /> : <a href={`#p.${p.id}`} className="block h-full"><JugadorCard o={o} side={o.equipo === p.local ? "L" : "V"} /></a>}
          </div>
        )) : <div className="card p-10 text-center text-chalk-3 md:col-span-2 xl:col-span-3">No hay oportunidades con estos filtros.</div>}
      </div>
    </>
  );
}

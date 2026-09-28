/* eslint-disable @typescript-eslint/no-explicit-any */
import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ChevronRight, Search } from "lucide-react";
import { DATA, DATA_AGE_H, LG, MATCHES, compName, dayKey, dayLabel, dayShort, fTime, favLabel, isLive, longDate, pct, picksFor } from "@/lib/data";
import { Badge } from "@/components/ui-pz";

export default function Matches({ lg }: { lg: string | null }) {
  const list = useMemo(() => MATCHES.filter((p) => !lg || p.liga === lg), [lg]);
  const days = useMemo(() => [...new Set(list.map((p) => dayKey(p.fecha)))], [list]);
  const [day, setDay] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const dsel = day && days.includes(day) ? day : days[0];
  const items = list.filter((p) => (q ? (p.local + " " + p.visita).toLowerCase().includes(q.toLowerCase()) : dayKey(p.fecha) === dsel));
  const counts = Object.fromEntries(Object.keys(LG).map((c) => [c, MATCHES.filter((p) => p.liga === c).length]));

  return (
    <div className="mx-auto max-w-[1180px] px-5 md:px-8">
      <div className="flex flex-col gap-5 pb-4 pt-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="eyebrow">Solo de hoy en adelante</div>
            <h1 id="titulo" tabIndex={-1} className="mt-2 text-[clamp(36px,5vw,56px)] font-black leading-none">Partidos</h1>
          </div>
          <label className="relative w-full max-w-[300px]">
            <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-chalk-3" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar un equipo" aria-label="Buscar un equipo"
              className="w-full rounded-full border border-white/10 bg-white/[0.04] py-2.5 pl-10 pr-4 text-[14.5px] text-chalk placeholder:text-chalk-3 focus:border-cobalt focus:outline-none" />
          </label>
        </div>
        <div className="scrollbar-none -mx-5 flex gap-2 overflow-x-auto px-5" role="group" aria-label="Liga">
          <a className="chip" href="#partidos" aria-current={!lg}>Todas <span className="num text-[12px] opacity-60">{MATCHES.length}</span></a>
          {Object.entries(LG).map(([c, l]: any) => (
            <a key={c} className="chip" href={`#partidos.${c}`} aria-current={lg === c}>{l.name} <span className="num text-[12px] opacity-60">{counts[c]}</span></a>
          ))}
        </div>
        {!q && (
          <div className="scrollbar-none -mx-5 flex gap-2 overflow-x-auto px-5" role="group" aria-label="Día">
            {days.slice(0, 14).map((d) => (
              <button key={d} onClick={() => setDay(d)} aria-pressed={d === dsel}
                className={`relative shrink-0 rounded-xl px-4 py-2 text-left transition ${d === dsel ? "text-night-900" : "text-chalk-2 hover:bg-white/5"}`}>
                {d === dsel && <motion.span layoutId="day-pill" className="absolute inset-0 rounded-xl bg-gold" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
                <span className="relative block text-[14px] font-bold capitalize">{dayShort(d)}</span>
                <span className="relative block text-[11.5px] opacity-70">{list.filter((p) => dayKey(p.fecha) === d).length} partidos</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {DATA_AGE_H > 30 && (
        <div className="card mb-4 px-5 py-3.5 text-[14px] text-chalk-2">Los datos son del {longDate(DATA.generado)}. Ya ocultamos los partidos jugados; las cuotas se renuevan en la próxima actualización diaria.</div>
      )}

      <div className="mb-3 mt-6 font-display text-[15px] font-extrabold uppercase tracking-[0.06em] text-chalk-3" style={{ fontStretch: "112%" }}>
        {q ? `Resultados para "${q}"` : dayLabel(dsel || "")}
      </div>

      <div key={(q || dsel) + (lg || "")} className="flex flex-col gap-2.5 pb-10">
        {items.length ? items.map((p, i) => <Row key={p.id} p={p} delay={Math.min(i, 12) * 0.035} />) : <div className="card p-10 text-center text-chalk-3">No hay partidos para esta selección.</div>}
      </div>
      <p className="pb-16 text-[13.5px] text-chalk-3">El porcentaje junto a cada equipo es su probabilidad de ganar. <a href="#guia" className="font-semibold text-gold hover:underline">¿Cómo se calcula?</a></p>
    </div>
  );
}

function Row({ p, delay = 0 }: { p: any; delay?: number }) {
  const x = p.mercados["1x2"], k = picksFor(p)[0], fav = favLabel(p);
  const live = isLive(p);
  const team = (name: string, prob: number, isFav: boolean) => (
    <div className="flex min-w-0 items-center gap-3">
      <Badge name={name} size={30} />
      <span className={`truncate font-semibold ${isFav ? "text-chalk" : "text-chalk-2"}`}>{name}</span>
      <span className={`num ml-auto text-[13.5px] ${isFav ? "font-bold text-gold" : "text-chalk-3"}`}>{pct(prob)}</span>
    </div>
  );
  return (
    <motion.a whileHover={{ scale: 1.01 }} style={{ animationDelay: `${delay}s` }}
      href={`#p.${p.id}`} className="row-in card groupgrid grid-cols-[56px_minmax(0,1fr)_16px] items-center gap-4 px-4 py-3.5 transition-colors hover:border-gold/40 md:grid-cols-[72px_minmax(0,1fr)_minmax(0,300px)_16px]">
      <div>
        {live ? <span className="inline-flex items-center gap-1.5 text-[12px] font-bold text-flare"><span className="live-dot h-2 w-2 rounded-full bg-flare" />EN VIVO</span>
          : <div className="num text-[15px] font-semibold">{fTime(p.fecha)}</div>}
        <div className="truncate text-[11px] font-semibold text-chalk-3">{compName(p)}</div>
      </div>
      <div className="flex min-w-0 flex-col gap-1.5">
        {team(p.local, x["1"], x["1"] >= x["2"] && x["1"] >= 0.45)}
        {team(p.visita, x["2"], x["2"] > x["1"] && x["2"] >= 0.45)}
      </div>
      <div className="col-start-2 flex flex-col items-start gap-1.5 md:col-start-auto">
        <span className={`tag ${k?.valor ? "bg-gold-soft text-gold" : fav.kind === "fav" ? "bg-cobalt-soft text-cobalt" : "bg-white/5 text-chalk-3"}`}>{k?.valor ? "Con valor" : fav.t}</span>
        {k && <span className="text-[13px] leading-snug text-chalk-2">{k.sel} · <b className="num text-chalk">{pct(k.prob)}</b></span>}
      </div>
      <ChevronRight className="row-span-1 h-4 w-4 text-chalk-3 transition-transform group-hover:translate-x-1 md:col-start-4 md:row-start-1 col-start-3 row-start-1" />
    </motion.a>
  );
}

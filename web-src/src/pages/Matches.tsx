/* eslint-disable @typescript-eslint/no-explicit-any */
import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ChevronRight, Search, ShieldCheck, Sparkles, X } from "lucide-react";
import { DATA, DATA_AGE_H, LG, MATCHES, compName, dayKey, dayLabel, dayShort, fTime, favLabel, isLive, longDate, pct, picksFor, prettyAlt } from "@/lib/data";
import { Badge, Page, PageHeader } from "@/components/ui-pz";

const FIJAS = new Set((DATA.fijas?.lista || []).map((f: any) => f.id));

export default function Matches({ lg }: { lg: string | null }) {
  const list = useMemo(() => MATCHES.filter((p) => !lg || p.liga === lg), [lg]);
  const days = useMemo(() => [...new Set(list.map((p) => dayKey(p.fecha)))], [list]);
  const [day, setDay] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const dsel = day && days.includes(day) ? day : days[0];
  const items = list.filter((p) => (q ? (p.local + " " + p.visita).toLowerCase().includes(q.toLowerCase()) : dayKey(p.fecha) === dsel));
  const counts = Object.fromEntries(Object.keys(LG).map((c) => [c, MATCHES.filter((p) => p.liga === c).length]));
  const nValor = list.filter((p) => p.valor?.some((v: any) => v.valor)).length;
  const nFijas = list.filter((p) => FIJAS.has(p.id)).length;

  const search = (
    <label className="relative block w-full">
      <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-chalk-3" />
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar un equipo" aria-label="Buscar un equipo"
        className="w-full rounded-full border border-white/10 bg-white/[0.04] py-2.5 pl-10 pr-9 text-[14.5px] text-chalk placeholder:text-chalk-3 transition focus:border-cobalt focus:bg-white/[0.06] focus:outline-none" />
      {q && <button onClick={() => setQ("")} aria-label="Borrar búsqueda" className="absolute right-2.5 top-1/2 grid h-6 w-6 -translate-y-1/2 place-items-center rounded-full text-chalk-3 hover:bg-white/10 hover:text-chalk"><X className="h-3.5 w-3.5" /></button>}
    </label>
  );

  return (
    <Page>
      <PageHeader eyebrow="Solo de hoy en adelante" title={lg ? LG[lg].name : "Partidos"}
        sub="Probabilidad de cada equipo, el pick más interesante y si hay valor frente a las cuotas. Los partidos terminados desaparecen solos."
        stats={[{ v: list.length, l: "partidos en los próximos días" }, { v: days.length, l: "días con partidos" },
          { v: nValor, l: "con valor frente a la casa", tone: "turf" }, { v: nFijas, l: "con una fija", tone: "gold" }]} />

      <div className="grid gap-6 lg:grid-cols-[250px_minmax(0,1fr)] lg:gap-8">
        {/* filtros: panel lateral en escritorio */}
        <aside className="hidden lg:block">
          <div className="sticky top-[88px] flex flex-col gap-4">
            {search}
            <nav aria-label="Liga" className="card flex flex-col p-2">
              {[["", "Todas", MATCHES.length], ...Object.entries(LG).map(([c, l]: any) => [c, l.name, counts[c]])].map(([c, name, n]: any) => {
                const on = (lg || "") === c;
                return (
                  <a key={c || "all"} href={c ? `#partidos.${c}` : "#partidos"} aria-current={on ? "true" : undefined}
                    className={`relative flex items-center justify-between rounded-xl px-3.5 py-2.5 text-[14.5px] font-semibold transition-colors ${on ? "text-night-900" : "text-chalk-2 hover:bg-white/5 hover:text-chalk"}`}>
                    {on && <motion.span layoutId="lg-pill" className="absolute inset-0 rounded-xl bg-chalk" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
                    <span className="relative">{name}</span><span className={`num relative text-[12.5px] ${on ? "text-night-900/60" : "text-chalk-3"}`}>{n}</span>
                  </a>
                );
              })}
            </nav>
            <div className="card p-4 text-[13px] leading-relaxed text-chalk-3">
              <div className="mb-2 font-bold text-chalk-2">Cómo leer la fila</div>
              <div className="flex items-center gap-2"><i className="h-1.5 w-5 rounded-full bg-cobalt" />gana el local</div>
              <div className="flex items-center gap-2"><i className="h-1.5 w-5 rounded-full bg-white/25" />empate</div>
              <div className="flex items-center gap-2"><i className="h-1.5 w-5 rounded-full bg-turf" />gana la visita</div>
              <a href="#fijas" className="mt-3 inline-flex items-center gap-1.5 font-bold text-gold hover:underline"><ShieldCheck className="h-4 w-4" />Ver las fijas</a>
            </div>
          </div>
        </aside>

        <div className="min-w-0">
          {/* filtros: barra fija en móvil y tablet */}
          <div className="sticky top-[60px] z-30 -mx-4 flex flex-col gap-3 border-b border-white/[0.06] bg-night-900/85 px-4 pb-3 pt-3 backdrop-blur-xl sm:-mx-6 sm:top-[68px] sm:px-6 lg:hidden">
            {search}
            <div className="scrollbar-none -mx-4 flex snap-x gap-2 overflow-x-auto px-4 sm:-mx-6 sm:px-6" role="group" aria-label="Liga">
              <a className="chip snap-start" href="#partidos" aria-current={!lg}>Todas <span className="num text-[12px] opacity-60">{MATCHES.length}</span></a>
              {Object.entries(LG).map(([c, l]: any) => (
                <a key={c} className="chip snap-start" href={`#partidos.${c}`} aria-current={lg === c}>{l.name} <span className="num text-[12px] opacity-60">{counts[c]}</span></a>
              ))}
            </div>
          </div>

          {!q && (
            <div className="scrollbar-none -mx-4 mt-4 flex snap-x gap-2 overflow-x-auto px-4 pb-1 sm:-mx-6 sm:px-6 lg:mx-0 lg:mt-0 lg:px-0" role="group" aria-label="Día">
              {days.slice(0, 14).map((d) => (
                <button key={d} onClick={() => setDay(d)} aria-pressed={d === dsel}
                  className={`relative shrink-0 snap-start rounded-xl px-4 py-2 text-left transition ${d === dsel ? "text-night-900" : "text-chalk-2 hover:bg-white/5"}`}>
                  {d === dsel && <motion.span layoutId="day-pill" className="absolute inset-0 rounded-xl bg-gold shadow-[0_8px_24px_-10px_rgba(255,194,61,.9)]" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
                  <span className="relative block text-[14px] font-bold capitalize">{dayShort(d)}</span>
                  <span className="relative block text-[11.5px] opacity-70">{list.filter((p) => dayKey(p.fecha) === d).length} partidos</span>
                </button>
              ))}
            </div>
          )}

          {DATA_AGE_H > 30 && (
            <div className="card mt-4 px-5 py-3.5 text-[14px] text-chalk-2">Los datos son del {longDate(DATA.generado)}. Ya ocultamos los partidos jugados; las cuotas se renuevan en la próxima actualización diaria.</div>
          )}

          <div className="mb-3 mt-6 flex items-center gap-3">
            <h2 className="font-display text-[15px] font-extrabold uppercase tracking-[0.06em] text-chalk-3" style={{ fontStretch: "112%" }}>
              {q ? `Resultados para "${q}"` : dayLabel(dsel || "")}
            </h2>
            <span className="h-px flex-1 bg-white/[0.07]" />
            <span className="num text-[12.5px] text-chalk-3">{items.length}</span>
          </div>

          <div key={(q || dsel) + (lg || "")} className="cq flex flex-col gap-2.5 pb-8">
            {items.length ? items.map((p, i) => <Row key={p.id} p={p} delay={Math.min(i, 12) * 0.035} />) : <div className="card p-10 text-center text-chalk-3">No hay partidos para esta selección.</div>}
          </div>
          <p className="text-[13.5px] text-chalk-3">El porcentaje junto a cada equipo es su probabilidad de ganar. <a href="#metodo" className="font-semibold text-gold hover:underline">¿Cómo se calcula?</a></p>
        </div>
      </div>
    </Page>
  );
}

function Row({ p, delay = 0 }: { p: any; delay?: number }) {
  const x = p.mercados["1x2"], k = picksFor(p)[0], fav = favLabel(p), d = p.destacada, nOp = (p.oportunidades || []).length;
  const live = isLive(p), fija = FIJAS.has(p.id);
  const team = (name: string, prob: number, isFav: boolean) => (
    <div className="flex min-w-0 items-center gap-3">
      <Badge name={name} size={30} />
      <span className={`truncate text-[15px] font-semibold ${isFav ? "text-chalk" : "text-chalk-2"}`}>{name}</span>
      <span className={`num ml-auto shrink-0 text-[13.5px] ${isFav ? "font-bold text-gold" : "text-chalk-3"}`}>{pct(prob)}</span>
    </div>
  );
  const bar = [["1", "bg-cobalt", p.local], ["X", "bg-white/25", "Empate"], ["2", "bg-turf", p.visita]] as const;
  return (
    <a href={`#p.${p.id}`} style={{ animationDelay: `${delay}s` }}
      className={`row-in spot lift card group mrow px-4 py-4 hover:border-gold/40 sm:px-5 ${fija ? "border-gold/30" : ""}`}>
      <div className="self-start pt-1">
        {live ? <span className="inline-flex items-center gap-1 whitespace-nowrap text-[11.5px] font-bold text-flare"><span className="live-dot h-2 w-2 rounded-full bg-flare" />VIVO</span>
          : <div className="num text-[16px] font-semibold leading-none text-chalk">{fTime(p.fecha)}</div>}
        <div className="mt-1.5 line-clamp-2 text-[11px] font-semibold leading-tight text-chalk-3">{compName(p)}</div>
      </div>
      <div className="flex min-w-0 flex-col gap-2">
        {team(p.local, x["1"], x["1"] >= x["2"] && x["1"] >= 0.45)}
        {team(p.visita, x["2"], x["2"] > x["1"] && x["2"] >= 0.45)}
        <div className="mt-0.5 flex h-1 gap-0.5 overflow-hidden rounded-full" aria-hidden="true">
          {bar.map(([key, color, label]) => (
            <span key={key} className={`grow-x h-full rounded-full ${color}`} style={{ width: `${x[key] * 100}%` }} title={`${label} ${pct(x[key])}`} />
          ))}
        </div>
      </div>
      <div className="mrow-pick min-w-0">
        <div className="flex flex-wrap gap-1.5">
          {fija && <span className="tag bg-gold text-night-900"><ShieldCheck className="h-3 w-3" />Fija</span>}
          {nOp > 0 ? <span className="tag bg-turf-soft text-turf"><Sparkles className="h-3 w-3" />{nOp === 1 ? "1 oportunidad" : `${nOp} oportunidades`}</span>
            : <span className={`tag ${k?.valor ? "bg-gold-soft text-gold" : fav.kind === "fav" ? "bg-cobalt-soft text-cobalt" : "bg-white/5 text-chalk-3"}`}>{k?.valor ? <><Sparkles className="h-3 w-3" />Con valor</> : fav.t}</span>}
        </div>
        {d ? <span className="min-w-0 text-[13.5px] leading-snug text-chalk-2">{prettyAlt(p, d.seleccion)} · <b className="num text-chalk">{d.cuota_justa.toFixed(2)}</b> <span className="text-chalk-3">· {d.puntaje} pts</span></span>
          : k && <span className="min-w-0 text-[13.5px] leading-snug text-chalk-2">{k.sel} · <b className="num text-chalk">{pct(k.prob)}</b></span>}
      </div>
      <ChevronRight className="mrow-chev h-4 w-4 text-chalk-3 transition-transform group-hover:translate-x-1 group-hover:text-gold" />
    </a>
  );
}

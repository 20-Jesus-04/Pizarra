/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from "react";
import { ChevronDown, ShieldCheck, Sparkles, User } from "lucide-react";
import { compName, dayKey, dayShort, fTime, pct, prettyAlt } from "@/lib/data";
import { Badge, Ring } from "@/components/ui-pz";

export const SENALES: [string, string][] = [["historial", "Historial"], ["reciente", "Recientes"], ["jugadores", "Jugadores"], ["cuota", "Cuota"], ["probabilidad", "Probabilidad"]];
const CORTO: Record<string, string> = { historial: "Historial", reciente: "Recientes", jugadores: "Jugadores", cuota: "Cuota", probabilidad: "Prob." };

const tone = (v: number) => (v >= 0.7 ? "bg-turf" : v >= 0.45 ? "bg-gold" : "bg-flare");
const ringColor = (s: number) => (s >= 75 ? "#2FE0A0" : s >= 65 ? "#FFC23D" : "#6C7BFF");

/** Tarjeta de una oportunidad: pick, puntaje, señales, cuotas y motivos. Con `p` muestra además el partido. */
export function OportunidadCard({ o, p, compact = false }: { o: any; p?: any; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const sel = p ? prettyAlt(p, o.seleccion) : o.seleccion;
  const Wrap: any = p ? "a" : "div";
  return (
    <div className={`spot lift card relative flex h-full flex-col overflow-hidden ${o.fija ? "glow-border" : ""}`}>
      <Wrap {...(p ? { href: `#p.${p.id}` } : {})} className="flex flex-1 flex-col gap-3 p-4 sm:p-5">
        {p && (
          <div className="flex items-center justify-between gap-2 text-[12px] font-semibold text-chalk-3">
            <span className="truncate">{dayShort(dayKey(p.fecha))} · {fTime(p.fecha)} · {compName(p)}</span>
          </div>
        )}
        {p && (
          <div className="flex min-w-0 items-center gap-2 text-[14px] font-semibold">
            <Badge name={p.local} size={22} /><span className="min-w-0 truncate">{p.local}</span><span className="text-chalk-3">vs</span>
            <span className="min-w-0 truncate">{p.visita}</span><Badge name={p.visita} size={22} />
          </div>
        )}
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap gap-1.5">
              {o.fija && <span className="tag bg-gold text-night-900"><ShieldCheck className="h-3 w-3" />Fija</span>}
              {o.ev != null && o.ev > 0.03 && !o.valor_sospechoso && <span className="tag bg-turf-soft text-turf"><Sparkles className="h-3 w-3" />Valor {`+${(o.ev * 100).toFixed(0)}%`}</span>}
              {o.valor_sospechoso && <span className="tag bg-flare/15 text-flare">Revisar cuota</span>}
            </div>
            <div className={`mt-2 font-display font-extrabold leading-[1.15] ${compact ? "text-[17px]" : "text-[19px] sm:text-[20px]"}`} style={{ fontStretch: "110%" }}>{sel}</div>
          </div>
          <Ring p={o.puntaje / 100} size={compact ? 50 : 58} stroke={5} color={ringColor(o.puntaje)}
            label={<span className="text-center leading-none"><span className="num block text-[15px] font-semibold">{o.puntaje}</span><span className="block text-[8.5px] font-bold uppercase tracking-wider text-chalk-3">pts</span></span>} />
        </div>
        <div className="grid grid-cols-3 gap-1 rounded-xl bg-white/[0.03] px-2 py-3 text-center ring-1 ring-white/[0.06]">
          <div><div className="num text-[16px] font-semibold">{pct(o.prob_real)}</div><div className="text-[10.5px] leading-tight text-chalk-3">probabilidad</div></div>
          <div><div className="num text-[16px] font-semibold">{o.cuota_justa.toFixed(2)}</div><div className="text-[10.5px] leading-tight text-chalk-3">cuota justa</div></div>
          <div title="Apuesta solo si tu casa paga esta cuota o más"><div className="num text-[16px] font-semibold text-gold">{o.cuota_minima.toFixed(2)}</div><div className="text-[10.5px] leading-tight text-chalk-3">cuota mínima</div></div>
        </div>
        {!compact && (
          <div className="grid grid-cols-5 gap-1.5" aria-label="Señales">
            {SENALES.map(([k, l]) => {
              const v = o.senales?.[k] ?? 0.5;
              return (
                <div key={k} title={`${l}: ${Math.round(v * 100)}/100`}>
                  <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.07]"><div className={`grow-x h-full rounded-full ${tone(v)}`} style={{ width: `${Math.max(8, v * 100)}%` }} /></div>
                  <div className="mt-1 truncate text-center text-[10px] text-chalk-3">{CORTO[k] || l}</div>
                </div>
              );
            })}
          </div>
        )}
      </Wrap>
      {!compact && o.razones?.length > 0 && (
        <div className="border-t border-white/[0.06]">
          <button onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center justify-between px-4 py-2.5 text-[12.5px] font-semibold text-chalk-2 hover:text-chalk sm:px-5">
            Por qué lo elegimos <ChevronDown className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} />
          </button>
          {open && (
            <ul className="page-in flex flex-col gap-1.5 px-4 pb-4 text-[12.5px] leading-relaxed text-chalk-2 sm:px-5">
              {o.razones.map((r: string, i: number) => <li key={i} className="flex gap-2"><span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-gold" />{r}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/** Oportunidad de jugador (tiros al arco, gol): solo aparecen donde la validación de jugadores lo respalda. */
export function JugadorCard({ o }: { o: any }) {
  return (
    <div className="spot lift card flex h-full flex-col gap-2.5 p-4">
      <div className="flex items-center gap-2 text-[12px] font-semibold text-chalk-3"><User className="h-3.5 w-3.5 text-cobalt" />{o.equipo}</div>
      <div className="flex items-start justify-between gap-3">
        <div className="text-[16px] font-extrabold leading-snug">{o.seleccion}</div>
        <span className="num shrink-0 rounded-lg bg-white/[0.05] px-2 py-1 text-[13px] font-semibold">{o.puntaje}<span className="text-[10px] text-chalk-3"> pts</span></span>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-chalk-3">
        <span><b className="num text-chalk">{pct(o.prob_real)}</b> prob.</span><span>justa <b className="num text-chalk">{o.cuota_justa.toFixed(2)}</b></span><span>mínima <b className="num text-gold">{o.cuota_minima.toFixed(2)}</b></span>
      </div>
      <ul className="mt-auto flex flex-col gap-1 border-t border-white/[0.06] pt-2.5 text-[12px] leading-snug text-chalk-3">
        {o.razones.map((r: string, i: number) => <li key={i}>{r}</li>)}
      </ul>
    </div>
  );
}

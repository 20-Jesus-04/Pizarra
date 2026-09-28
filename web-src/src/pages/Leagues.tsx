/* eslint-disable @typescript-eslint/no-explicit-any */
import { motion } from "framer-motion";
import { Trophy } from "lucide-react";
import { LG, pct } from "@/lib/data";
import { Badge, Counter, Meter, Reveal, Ring, ease, item, stagger } from "@/components/ui-pz";

export default function Leagues({ code }: { code: string }) {
  const L = LG[code] || LG.E0;
  const b = L.backtest || {};
  const ratings = (L.ratings || []).slice(0, code === "INT" ? 16 : 10);
  const max = Math.max(...ratings.map((r: any) => r.attack / r.defense), 1);
  return (
    <div className="mx-auto max-w-[1180px] px-5 pb-20 md:px-8">
      <div className="flex flex-col gap-5 pt-10">
        <div><div className="eyebrow">{L.country}</div><h1 id="titulo" tabIndex={-1} className="mt-2 text-[clamp(36px,5vw,56px)] font-black leading-none">{L.name}</h1></div>
        <div className="scrollbar-none -mx-5 flex gap-2 overflow-x-auto px-5">
          {Object.entries(LG).map(([k, l]: any) => <a key={k} className="chip" href={`#liga.${k}`} aria-current={k === code}>{l.name}</a>)}
        </div>
      </div>

      <motion.div key={code} variants={stagger} initial="hidden" animate="show" className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <motion.div variants={item} className="card flex items-center gap-4 p-5">
          <Ring p={b.acierto_modelo || 0} size={72} color="#FFC23D" />
          <p className="text-[14px] text-chalk-2">acierta el ganador en <b className="text-chalk">{b.n}</b> partidos de prueba</p>
        </motion.div>
        <motion.div variants={item} className="card flex items-center gap-4 p-5">
          {b.acierto_mercado != null ? <><Ring p={b.acierto_mercado} size={72} color="#6C7BFF" /><p className="text-[14px] text-chalk-2">acierto de las casas de apuestas en los mismos partidos</p></>
            : <p className="text-[14px] text-chalk-3">Sin cuotas históricas para comparar con las casas en esta competición.</p>}
        </motion.div>
        <motion.div variants={item} className="card p-5"><div className="font-display text-[40px] font-black leading-none" style={{ fontStretch: "118%" }}><Counter to={L.goles_prom} decimals={2} /></div><p className="mt-2 text-[14px] text-chalk-2">goles por partido esta temporada</p></motion.div>
        <motion.div variants={item} className="card p-5"><div className="font-display text-[40px] font-black leading-none" style={{ fontStretch: "118%" }}>×<Counter to={L.ventaja_local} decimals={2} /></div><p className="mt-2 text-[14px] text-chalk-2">goles de más por jugar de local</p></motion.div>
      </motion.div>

      <div className="mt-6 grid gap-5 lg:grid-cols-3">
        {L.tabla?.length > 0 && (
          <Reveal className="lg:row-span-2"><div className="card h-full p-6">
            <h3 className="text-[20px] font-extrabold">Tabla</h3>
            <div className="mt-4 flex flex-col">
              {L.tabla.map((t: any, i: number) => (
                <motion.div key={t.equipo} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.02, ease }}
                  className="grid grid-cols-[26px_1fr_34px_40px] items-center gap-2 border-b border-white/[0.06] py-2 text-[14px]">
                  <span className={`num text-[12.5px] ${i < 4 ? "text-gold" : "text-chalk-3"}`}>{t.pos}</span><span className="truncate">{t.equipo}</span>
                  <span className="num text-right text-chalk-3">{t.dg > 0 ? "+" : ""}{t.dg}</span><span className="num text-right font-bold">{t.pts}</span>
                </motion.div>
              ))}
            </div>
          </div></Reveal>
        )}
        <Reveal className={L.tabla?.length ? "lg:col-span-2" : "lg:col-span-3"}><div className="card p-6">
          <h3 className="text-[20px] font-extrabold">Los más fuertes según el modelo</h3>
          <p className="mt-1 text-[13.5px] text-chalk-3">Combina ataque y defensa. Mide el nivel real, no los puntos.</p>
          <div className="mt-5 flex flex-col gap-3">
            {ratings.map((r: any, i: number) => (
              <div key={r.team} className="grid grid-cols-[22px_28px_1fr_minmax(80px,40%)_44px] items-center gap-3 text-[14px]">
                <span className="num text-chalk-3">{i + 1}</span><Badge name={r.team} size={26} /><span className="truncate font-semibold">{r.team}</span>
                <Meter p={r.attack / r.defense / max} color={i < 3 ? "bg-gold" : "bg-cobalt"} /><span className="num text-right">{(r.attack / r.defense).toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div></Reveal>
        {L.goleadores?.length > 0 && (
          <Reveal className={L.tabla?.length ? "lg:col-span-2" : "lg:col-span-3"}><div className="card p-6">
            <div className="flex items-center gap-2"><Trophy className="h-5 w-5 text-gold" /><h3 className="text-[20px] font-extrabold">Goleadores</h3></div>
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              {L.goleadores.map((g: any, i: number) => (
                <div key={g.nombre} className="flex items-center gap-3 rounded-xl bg-white/[0.03] px-3 py-2.5">
                  <span className={`num w-5 text-[13px] ${i === 0 ? "text-gold" : "text-chalk-3"}`}>{i + 1}</span>
                  <div className="min-w-0 flex-1"><div className="truncate font-bold">{g.nombre}</div><div className="truncate text-[12.5px] text-chalk-3">{g.equipo}</div></div>
                  <div className="text-right"><div className="num text-[18px] font-semibold">{g.goles}</div><div className="text-[11px] text-chalk-3">{g.asist} asist.</div></div>
                </div>
              ))}
            </div>
          </div></Reveal>
        )}
      </div>
      <p className="mt-8 text-[13.5px] text-chalk-3">Aciertos medidos semana a semana, entrenando solo con partidos anteriores ({pct(b.acierto_modelo)} en {b.n} partidos). <a href="#guia" className="font-semibold text-gold hover:underline">Cómo se calculan</a></p>
    </div>
  );
}

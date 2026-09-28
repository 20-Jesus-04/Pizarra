/* eslint-disable @typescript-eslint/no-explicit-any */
import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { ArrowRight, BarChart3, Coins, Search, ShieldCheck, Sparkles, Users } from "lucide-react";
import { DATA, LG, MATCHES, longDate, topPicks, pct, compName } from "@/lib/data";
import { Counter, Pitch, Reveal, SectionHead, Ticket, ease, item, stagger } from "@/components/ui-pz";

export default function Home() {
  const picks = topPicks(7);
  const hero = picks[0], rest = picks.slice(1);
  const hist = Object.values(LG).reduce((s: number, l: any) => s + l.partidos_historicos, 0);
  const intAcc = LG.INT?.backtest?.acierto_modelo;
  const counts = Object.fromEntries(Object.keys(LG).map((c) => [c, MATCHES.filter((p) => p.liga === c).length]));
  const reduce = useReducedMotion();
  const { scrollY } = useScroll();
  const yPitch = useTransform(scrollY, [0, 600], [0, 120]);
  const words = ["Apuesta", "con", "datos,"];

  return (
    <>
      {/* HERO */}
      <section className="relative overflow-hidden border-b border-white/5">
        <motion.div style={reduce ? {} : { y: yPitch }} className="absolute inset-0"><Pitch /></motion.div>
        <div className="pointer-events-none absolute -left-40 -top-40 h-[520px] w-[520px] rounded-full bg-cobalt/20 blur-[120px]" />
        <div className="pointer-events-none absolute -bottom-52 right-0 h-[480px] w-[480px] rounded-full bg-gold/10 blur-[120px]" />
        <div className="relative mx-auto grid max-w-[1180px] items-center gap-12 px-5 pb-20 pt-14 md:px-8 lg:grid-cols-[1.12fr_.88fr] lg:pb-24 lg:pt-20">
          <div>
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease }}
              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[12.5px] font-semibold text-chalk-2">
              <span className="live-dot h-2 w-2 rounded-full bg-turf" /> Actualizado el {longDate(DATA.generado)} · {MATCHES.length} partidos por analizar
            </motion.div>
            <h1 id="titulo" tabIndex={-1} className="mt-6 text-[clamp(44px,7.4vw,86px)] font-black leading-[0.95]">
              {words.map((w, i) => (
                <motion.span key={w} className="mr-[0.22em] inline-block" initial={reduce ? false : { opacity: 0, y: 40, rotateX: -60 }} animate={{ opacity: 1, y: 0, rotateX: 0 }}
                  transition={{ duration: 0.8, delay: 0.1 + i * 0.09, ease }}>{w}</motion.span>
              ))}
              <br />
              <motion.span className="inline-block bg-gradient-to-r from-gold via-[#FFE08A] to-gold bg-clip-text text-transparent" initial={reduce ? false : { opacity: 0, y: 40 }}
                animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.9, delay: 0.42, ease }}>no con corazonadas.</motion.span>
            </h1>
            <motion.p initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.7, duration: 0.8 }}
              className="mt-6 max-w-[54ch] text-[clamp(16px,1.7vw,19px)] leading-relaxed text-chalk-2">
              Pizarra calcula la probabilidad real de cada resultado en las 5 grandes ligas de Europa, la Liga 1 y las selecciones, y te avisa cuando la cuota de tu casa paga más de lo que debería.
            </motion.p>
            <motion.div initial={reduce ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.85, duration: 0.6, ease }} className="mt-9 flex flex-wrap gap-3">
              <motion.a whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.98 }} href="#partidos"
                className="group inline-flex items-center gap-2 rounded-full bg-gold px-6 py-3.5 font-bold text-night-900 shadow-[0_10px_40px_-12px_rgba(255,194,61,.8)]">
                Ver los próximos partidos <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
              </motion.a>
              <motion.a whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.98 }} href="#guia" className="inline-flex items-center gap-2 rounded-full border border-white/20 px-6 py-3.5 font-bold text-chalk hover:bg-white/5">
                Cómo usarla en 2 minutos
              </motion.a>
            </motion.div>
            <div className="mt-11 grid max-w-[520px] grid-cols-3 gap-6 border-t border-white/10 pt-6">
              {[
                [<Counter key="a" to={Math.round(hist / 1000)} suffix=" mil" />, "partidos históricos"],
                [<Counter key="b" to={25} prefix="+" />, "mercados por partido"],
                [intAcc ? <Counter key="c" to={Math.round(intAcc * 100)} suffix="%" /> : "–", "acierto en selecciones"],
              ].map(([v, l], i) => (
                <div key={i}><div className="font-display text-[clamp(24px,3vw,32px)] font-extrabold" style={{ fontStretch: "118%" }}>{v}</div><div className="text-[13px] text-chalk-3">{l}</div></div>
              ))}
            </div>
          </div>
          {hero && (
            <motion.div initial={reduce ? false : { opacity: 0, y: 40, rotate: -3 }} animate={{ opacity: 1, y: 0, rotate: 0 }} transition={{ duration: 1, delay: 0.5, ease }} className="relative">
              <div className="mb-3 flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.14em] text-gold"><Sparkles className="h-4 w-4" /> La oportunidad destacada</div>
              <div className="absolute -inset-6 -z-0 rounded-[32px] bg-gold/10 blur-2xl" />
              <div className="relative"><Ticket k={hero} featured /></div>
              <p className="mt-4 text-[13px] text-chalk-3">Toca el ticket para ver el análisis completo del partido.</p>
            </motion.div>
          )}
        </div>
      </section>

      {/* TICKER */}
      {picks.length > 3 && (
        <div className="relative overflow-hidden border-b border-white/5 bg-night-850 py-3" aria-label="Oportunidades del momento">
          <div className="marquee flex w-max gap-10 whitespace-nowrap">
            {[...picks, ...picks].map((k, i) => (
              <a key={i} href={`#p.${k.p.id}`} className="flex items-center gap-3 text-[14px] text-chalk-2 hover:text-chalk" aria-hidden={i >= picks.length}>
                <span className="text-gold">●</span><span className="font-semibold text-chalk">{k.p.local} – {k.p.visita}</span><span>{k.sel}</span><span className="num text-gold">{pct(k.prob)}</span>
                <span className="text-chalk-3">· {compName(k.p)}</span>
              </a>
            ))}
          </div>
          <div className="pointer-events-none absolute inset-y-0 left-0 w-20 bg-gradient-to-r from-night-850" /><div className="pointer-events-none absolute inset-y-0 right-0 w-20 bg-gradient-to-l from-night-850" />
        </div>
      )}

      {/* OPORTUNIDADES */}
      <section className="mx-auto max-w-[1180px] px-5 py-20 md:px-8">
        <Reveal><SectionHead title="Las mejores oportunidades" sub="Una por partido, de los próximos días. Toca cualquiera para ver por qué la elegimos."
          action={<a href="#partidos" className="inline-flex items-center gap-1.5 font-bold text-gold hover:underline">Todos los partidos <ArrowRight className="h-4 w-4" /></a>} /></Reveal>
        <motion.div variants={stagger} initial="hidden" whileInView="show" viewport={{ once: true, margin: "-60px" }} className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {rest.map((k, i) => <motion.div key={i} variants={item}><Ticket k={k} /></motion.div>)}
        </motion.div>
      </section>

      {/* CÓMO FUNCIONA */}
      <section className="border-y border-white/5 bg-night-850/60">
        <div className="mx-auto max-w-[1180px] px-5 py-20 md:px-8">
          <Reveal><SectionHead title="Tres pasos. Cero estadística." sub="Está hecho para decidir rápido, no para estudiar." /></Reveal>
          <div className="grid gap-5 md:grid-cols-3">
            {[
              [Search, "Elige un partido", "En una frase ves quién es favorito, cuántos goles se esperan y qué opciones son más probables."],
              [Coins, "Mira la cuota justa", "Es lo mínimo que debería pagar una apuesta según su probabilidad real. Un 80% vale 1.25."],
              [ShieldCheck, "Compara con tu casa", "Si tu casa paga más que la cuota justa, hay valor. Si paga menos, mejor déjala pasar."],
            ].map(([Icon, t, d]: any, i) => (
              <Reveal key={i} delay={i * 0.1}>
                <div className="card group relative h-full overflow-hidden p-7">
                  <span className="absolute -right-3 -top-6 font-display text-[120px] font-black leading-none text-white/[0.04]" style={{ fontStretch: "125%" }}>{i + 1}</span>
                  <motion.div whileHover={{ rotate: -8, scale: 1.08 }} className="grid h-12 w-12 place-items-center rounded-xl bg-cobalt-soft text-cobalt"><Icon className="h-6 w-6" /></motion.div>
                  <h3 className="mt-5 text-[21px] font-extrabold">{t}</h3>
                  <p className="mt-2 text-[15px] leading-relaxed text-chalk-2">{d}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* LIGAS */}
      <section className="mx-auto max-w-[1180px] px-5 py-20 md:px-8">
        <Reveal><SectionHead title="Elige tu liga" /></Reveal>
        <motion.div variants={stagger} initial="hidden" whileInView="show" viewport={{ once: true }} className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7">
          {Object.entries(LG).map(([c, l]: any) => (
            <motion.a key={c} variants={item} whileHover={{ y: -4 }} href={`#partidos.${c}`} className="card group flex flex-col gap-1 p-4 hover:border-gold/40">
              <span className="text-[12px] text-chalk-3">{l.country}</span>
              <span className="font-display text-[18px] font-extrabold" style={{ fontStretch: "112%" }}>{l.name}</span>
              <span className="mt-2 text-[13px] text-chalk-2"><span className="num text-gold">{counts[c]}</span> partidos</span>
            </motion.a>
          ))}
        </motion.div>
      </section>

      {/* CONFIANZA */}
      <section className="mx-auto max-w-[1180px] px-5 pb-16 md:px-8">
        <Reveal><SectionHead title="Por qué confiar" sub="Cada número se probó contra partidos que el modelo no había visto."
          action={<a href="#ligas" className="inline-flex items-center gap-1.5 font-bold text-gold hover:underline">Resultados por liga <ArrowRight className="h-4 w-4" /></a>} /></Reveal>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            [BarChart3, <Counter key="1" to={Math.round(hist / 1000)} suffix="k" />, "partidos reales para medir la fuerza de cada equipo"],
            [Users, <Counter key="2" to={Math.round((DATA.n_actuaciones || 79000) / 1000)} suffix="k" />, "actuaciones de jugadores con tiros, tarjetas y minutos"],
            [ShieldCheck, <Counter key="3" to={Object.keys(LG).length} />, "competiciones, incluidas la Liga 1 y las selecciones"],
            [Sparkles, "Diaria", "actualización de partidos, cuotas y estadísticas"],
          ].map(([Icon, v, l]: any, i) => (
            <Reveal key={i} delay={i * 0.08}><div className="card h-full p-6"><Icon className="h-5 w-5 text-gold" /><div className="mt-4 font-display text-[38px] font-black leading-none" style={{ fontStretch: "118%" }}>{v}</div><p className="mt-2 text-[14px] text-chalk-2">{l}</p></div></Reveal>
          ))}
        </div>
        <p className="mt-12 border-t border-white/10 pt-6 text-[13px] text-chalk-3">Pizarra muestra probabilidades, no certezas: una opción del 80% falla 1 de cada 5 veces. Apuesta solo lo que puedas perder. Solo mayores de 18 años.</p>
      </section>
    </>
  );
}

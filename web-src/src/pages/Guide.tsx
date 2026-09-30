import { useState } from "react";
import { motion } from "framer-motion";
import { DATA } from "@/lib/data";
import { Accordion, Page, PageHeader, Reveal, Ring } from "@/components/ui-pz";

const LESSONS = [
  { k: "Probabilidad", t: "Qué tan seguido pasa", d: "Un 70% significa que, si el partido se jugara 10 veces, eso pasaría unas 7. Nunca es una garantía.", ex: <>"Más de 1.5 goles: <b>78%</b>" falla más o menos 1 de cada 5 veces.</>, p: 0.78 },
  { k: "Cuota justa", t: "Lo que debería pagar", d: "Es 1 dividido entre la probabilidad: el precio sin trampa de la apuesta.", ex: <>Probabilidad <b>50%</b> → cuota justa <b>2.00</b>. Probabilidad <b>80%</b> → <b>1.25</b>.</>, p: 0.5 },
  { k: "Valor", t: "Cuando la casa paga de más", d: "Si tu casa paga más que la cuota justa, a la larga ganas. Si paga menos, a la larga pierdes aunque aciertes a veces.", ex: <>Justa <b>1.80</b>, tu casa <b>2.00</b> → valor <b className="text-turf">+11%</b>.</>, p: 0.56 },
  { k: "Cuánto apostar", t: "Protege tu banca", d: "La calculadora sugiere un máximo según la ventaja. Nunca apuestes más, aunque lo veas clarísimo.", ex: <>Ventaja pequeña → entre <b>0.5% y 2%</b> de tu banca.</>, p: 0.02 },
];

export default function Guide() {
  const [i, setI] = useState(0);
  const L = LESSONS[i];
  return (
    <Page>
      <PageHeader eyebrow="Guía rápida" crumbs={[["Método", "#metodo"], ["Guía", "#guia"]]} title="Aprende a usar Pizarra en 2 minutos" sub="Cuatro ideas. Tócalas en orden." />

      <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
        <div className="scrollbar-none -mx-4 flex gap-2 overflow-x-auto px-4 sm:-mx-6 sm:px-6 lg:mx-0 lg:flex-col lg:overflow-visible lg:px-0" role="group" aria-label="Lecciones">
          {LESSONS.map((l, k) => (
            <button key={l.k} aria-pressed={k === i} onClick={() => setI(k)}
              className={`relative flex shrink-0 items-center gap-3 rounded-2xl px-4 py-3 text-left transition lg:gap-4 lg:px-5 lg:py-4 ${k === i ? "text-night-900" : "text-chalk-2 hover:bg-white/5"}`}>
              {k === i && <motion.span layoutId="lesson" className="absolute inset-0 rounded-2xl bg-gold" transition={{ type: "spring", stiffness: 420, damping: 36 }} />}
              <span className={`relative grid h-9 w-9 place-items-center rounded-full font-display text-[16px] font-black ${k === i ? "bg-night-900 text-gold" : "bg-white/10"}`}>{k + 1}</span>
              <span className="relative text-[16px] font-bold">{l.k}</span>
            </button>
          ))}
        </div>
        <div className="spot card relative min-h-[300px] overflow-hidden p-5 sm:p-8">
          <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-cobalt/15 blur-3xl" />
          <div key={i} className="page-in relative grid gap-8 md:grid-cols-[1fr_auto] md:items-center">
              <div>
                <span className="tag bg-cobalt-soft text-cobalt">{i + 1} · {L.k}</span>
                <h2 className="mt-4 text-[clamp(26px,3.4vw,38px)] font-black">{L.t}</h2>
                <p className="mt-3 max-w-[52ch] text-[16.5px] leading-relaxed text-chalk-2">{L.d}</p>
                <div className="mt-6 rounded-xl bg-white/[0.05] p-4 text-[15px] text-chalk-2 ring-1 ring-white/10">{L.ex}</div>
                {i < LESSONS.length - 1 ? <button onClick={() => setI(i + 1)} className="mt-6 font-bold text-gold hover:underline">Siguiente: {LESSONS[i + 1].k} →</button>
                  : <a href="#partidos" className="mt-6 inline-block rounded-full bg-gold px-5 py-3 font-bold text-night-900">Listo, ver partidos →</a>}
              </div>
              <Ring key={i} p={L.p} size={140} stroke={11} color={i === 2 ? "#2FE0A0" : "#FFC23D"} label={<span className="num text-[30px] font-semibold">{Math.round(L.p * 100)}%</span>} />
          </div>
        </div>
      </div>

      <section className="mt-16 grid gap-3">
        <Reveal><h2 className="mb-3 text-[clamp(26px,3.4vw,36px)] font-black">Preguntas frecuentes</h2></Reveal>
        <Accordion title="¿De dónde salen los números?" defaultOpen>
          <p className="max-w-[70ch] leading-relaxed text-chalk-2">Para cada liga, Pizarra mide qué tan bueno es cada equipo atacando y defendiendo con miles de partidos reales, dando más peso a los recientes y teniendo en cuenta si juega de local. Con eso calcula la probabilidad de cada marcador posible, y de ahí salen todos los mercados. Cuando hay cuotas publicadas, las combina con el modelo porque las casas conocen noticias que los datos no tienen. En las pruebas, esa mezcla fue más precisa que cualquiera de los dos por separado.</p>
        </Accordion>
        <Accordion title="¿Y los jugadores?">
          <p className="max-w-[70ch] leading-relaxed text-chalk-2">Usa los minutos, tiros, goles, faltas y tarjetas de cada partido reciente de cada jugador, ajustados al rival. Así un delantero rinde más ante una defensa débil.</p>
        </Accordion>
        <Accordion title="¿Qué no sabe Pizarra?">
          <ul className="list-disc space-y-1.5 pl-5 text-chalk-2"><li>Lesiones, sanciones y rotaciones de último minuto: revisa la alineación.</li><li>El árbitro: por eso las tarjetas son lo más difícil de anticipar.</li><li>La motivación: un equipo ya clasificado puede salir con suplentes.</li></ul>
        </Accordion>
        <Accordion title="¿Cada cuánto se actualiza?">
          <p className="max-w-[70ch] leading-relaxed text-chalk-2">Cada día entran los partidos nuevos con sus cuotas, y los que ya se jugaron desaparecen solos. Solo verás partidos de hoy en adelante.</p>
        </Accordion>
        <Accordion title="Juego responsable">
          <p className="max-w-[70ch] leading-relaxed text-chalk-2">Apostar debe ser entretenimiento. Define un presupuesto que puedas perder, no persigas pérdidas y detente si deja de ser divertido. Solo para mayores de 18 años.</p>
        </Accordion>
        <p className="mt-6 text-[13px] text-chalk-3">Fuentes: football-data.co.uk, ESPN y la base de resultados internacionales de martj42. Datos del {new Date(DATA.generado).toLocaleString("es-PE", { timeZone: "America/Lima", dateStyle: "long", timeStyle: "short" })}.</p>
      </section>
    </Page>
  );
}

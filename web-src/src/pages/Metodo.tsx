/* eslint-disable @typescript-eslint/no-explicit-any */
import { Database, Cpu, ShieldCheck, Scale } from "lucide-react";
import { DATA, longDate, pct } from "@/lib/data";
import { Page, PageHeader, Reveal } from "@/components/ui-pz";

const MODELS: [string, string, string, string][] = [
  ["poisson", "Probabilidad de cada marcador suponiendo que los goles de cada equipo siguen una distribución de Poisson independiente.", "Base para resultado, goles y ambos marcan.", "Solo, no capta la relación entre marcadores bajos."],
  ["dixon_coles", "Como Poisson, más una corrección para 0-0, 1-0, 0-1 y 1-1, ventaja de local por equipo, más peso a lo reciente y xG aproximado con tiros.", "Mejor calibrado en empates y marcadores cortos.", "Sigue dependiendo de goles esperados."],
  ["elo", "Fuerza relativa de cada equipo a partir de toda su historia de resultados, convertida a 1X2 con un logit ordenado.", "Separa quién es más fuerte más allá de los promedios de gol.", "No sabe de lesiones ni de motivación."],
  ["bayes", "Tasa de gol que parte del promedio de la liga y se actualiza con los goles recientes (Gamma-Poisson).", "Estable con poca historia: una racha corta no lo engaña.", "Es una actualización estadística, no intuición."],
  ["mercado", "Probabilidad implícita de las cuotas, quitando el margen de la casa.", "La señal previa más informada: resume la opinión de todo el mercado.", "Es externa: no es un pronóstico propio."],
  ["xgboost", "Árboles de decisión con forma, descanso, xG reciente, tiros al arco y diferencia de Elo; entrenado con todas las ligas.", "Diversidad real: no siempre coincide con los demás y corrige puntos ciegos.", "Acompaña; no reemplaza a los otros."],
];

export default function Metodo() {
  const M = DATA.metodologia || {};
  const N = M.nombres || {};
  const pw = M.pesos || {};
  const w1 = pw["1x2"] || {};
  return (
    <Page>
      <PageHeader eyebrow="Metodología y tecnología" title="Cómo se calcula"
        sub="Seis modelos estadísticos independientes miden aspectos distintos de cada partido. Ninguno decide solo: se combinan con pesos que se recalibran cada semana contra partidos ya jugados. Los mismos datos, la misma versión y los mismos parámetros dan siempre el mismo resultado."
        stats={[{ v: "6", l: "modelos independientes", tone: "gold" }, { v: (M.picks_simulados || 0).toLocaleString("es-PE"), l: "picks simulados para calibrar" },
          { v: M.fecha ? longDate(M.fecha) : "–", l: "última recalibración" }, { v: "Diaria", l: "actualización automática", tone: "turf" }]} />

      <ol className="relative grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <span aria-hidden="true" className="pointer-events-none absolute left-6 right-6 top-[46px] hidden h-px bg-gradient-to-r from-cobalt via-gold to-turf opacity-40 lg:block" />
        {[[Database, "Datos", "Resultados, estadísticas y cuotas de football-data.co.uk; partidos, cuotas, fichas y árbitros de ESPN; selecciones desde 2014."],
          [Cpu, "Estimación", "6 modelos → ensamble con pesos calibrados → matriz de marcadores → más de 25 mercados + jugadores."],
          [ShieldCheck, "Revisión", "Un auditor automático revisa cada pronóstico (coherencia, rangos, cuotas, desacuerdos) antes de publicarlo."],
          [Scale, "Resultado", "Una lectura explicada con probabilidades, no una garantía. Todo queda registrado antes del partido."]].map(([Icon, t, d]: any) => (
          <li key={t} className="reveal spot lift card relative p-5"><span className="grid h-11 w-11 place-items-center rounded-xl bg-gold-soft ring-1 ring-gold/30"><Icon className="h-5 w-5 text-gold" /></span><h3 className="mt-3 text-[17px] font-extrabold">{t}</h3><p className="mt-1.5 text-[13.5px] leading-relaxed text-chalk-2">{d}</p></li>
        ))}
      </ol>

      <h2 className="mt-14 text-[clamp(22px,3.4vw,30px)] font-black">Los seis modelos</h2>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {MODELS.map(([k, mide, aporta, limite]) => (
          <Reveal key={k}><div className="spot lift card h-full p-5 sm:p-6">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <h3 className="text-[19px] font-extrabold">{N[k] || k}</h3>
              <span className="num text-[12.5px] text-chalk-3">peso {pct(w1.con_mercado?.[k] ?? 0, 0)} con cuotas · {k === "mercado" ? "–" : pct(w1.sin_mercado?.[k] ?? 0, 0)} sin</span>
            </div>
            <div className="mt-3 flex h-1.5 gap-1" aria-hidden="true">
              <span className="grow-x h-full rounded-full bg-cobalt" style={{ width: `${(w1.con_mercado?.[k] ?? 0) * 50}%` }} />
              <span className="grow-x h-full rounded-full bg-turf" style={{ width: `${(w1.sin_mercado?.[k] ?? 0) * 50}%` }} />
            </div>
            <dl className="mt-3 grid gap-2 text-[14px] leading-relaxed">
              <div><dt className="inline font-bold text-chalk">Mide: </dt><dd className="inline text-chalk-2">{mide}</dd></div>
              <div><dt className="inline font-bold text-turf">Aporta: </dt><dd className="inline text-chalk-2">{aporta}</dd></div>
              <div><dt className="inline font-bold text-chalk-3">Límite: </dt><dd className="inline text-chalk-2">{limite}</dd></div>
            </dl>
          </div></Reveal>
        ))}
      </div>
      <p className="mt-3 text-[13px] text-chalk-3">Peso con cuotas / sin cuotas, recalibrado el {M.fecha ? longDate(M.fecha) : "–"}. Con cuotas de cierre el mercado es muy difícil de superar, y los pesos lo reflejan sin maquillarlo.</p>

      <Reveal><div className="card mt-10 p-5 sm:p-7">
        <h2 className="text-[22px] font-black">Cómo se combinan</h2>
        <ol className="mt-5 grid gap-4 border-l border-white/10 pl-5 text-[14.5px] leading-relaxed text-chalk-2 sm:pl-6">
          <li className="relative"><span className="absolute -left-[31px] top-0.5 grid h-5 w-5 place-items-center rounded-full bg-night-800 text-[11px] font-black text-gold ring-2 ring-gold/40 sm:-left-[35px]">1</span><b className="text-chalk">Backtest semanal.</b> Para los últimos 2-3 años, cada semana se reentrenan los seis modelos solo con el pasado y se pronostica la semana siguiente.</li>
          <li className="relative"><span className="absolute -left-[31px] top-0.5 grid h-5 w-5 place-items-center rounded-full bg-night-800 text-[11px] font-black text-gold ring-2 ring-gold/40 sm:-left-[35px]">2</span><b className="text-chalk">Pesos.</b> Se buscan los pesos que minimizan el log-loss de esos pronósticos; se validan con la mitad del período que no se usó para elegirlos.</li>
          <li className="relative"><span className="absolute -left-[31px] top-0.5 grid h-5 w-5 place-items-center rounded-full bg-night-800 text-[11px] font-black text-gold ring-2 ring-gold/40 sm:-left-[35px]">3</span><b className="text-chalk">Marcadores.</b> El 1X2 y el over 2.5 del ensamble se convierten en goles esperados para cada equipo, y de ahí sale la matriz de marcadores con todos los mercados.</li>
          <li className="relative"><span className="absolute -left-[31px] top-0.5 grid h-5 w-5 place-items-center rounded-full bg-night-800 text-[11px] font-black text-gold ring-2 ring-gold/40 sm:-left-[35px]">4</span><b className="text-chalk">Calibración.</b> Cada probabilidad se contrasta con lo que de verdad ocurrió en su rango (curva declarada → real).</li>
          <li className="relative"><span className="absolute -left-[31px] top-0.5 grid h-5 w-5 place-items-center rounded-full bg-night-800 text-[11px] font-black text-gold ring-2 ring-gold/40 sm:-left-[35px]">5</span><b className="text-chalk">Tarjetas y árbitro.</b> Las tarjetas esperadas salen de los equipos y se multiplican por el factor del árbitro cuando está confirmado (football-data para Inglaterra, ESPN para el resto).</li>
          <li className="relative"><span className="absolute -left-[31px] top-0.5 grid h-5 w-5 place-items-center rounded-full bg-night-800 text-[11px] font-black text-gold ring-2 ring-gold/40 sm:-left-[35px]">6</span><b className="text-chalk">Auditoría.</b> Reglas fijas marcan cada pronóstico como correcto, a revisar o bloqueado; los bloqueados no entran a fijas ni se marcan "con valor".</li>
        </ol>
      </div></Reveal>

      <div className="mt-5 grid gap-5 md:grid-cols-2">
        <Reveal><div className="spot lift card h-full p-5 sm:p-6">
          <h2 className="text-[20px] font-black">Métricas</h2>
          <p className="mt-2 text-[14.5px] leading-relaxed text-chalk-2"><b className="text-chalk">Brier:</b> qué tan cerca estuvieron las probabilidades del resultado real. <b className="text-chalk">Calibración:</b> si lo que decimos al 70% ocurre cerca del 70% de las veces. Ambas se calculan solo con partidos liquidados, nunca con futuros.</p>
          <a href="#resultados" className="mt-4 inline-block font-bold text-gold hover:underline">Ver resultados →</a>
        </div></Reveal>
        <Reveal><div className="spot lift card h-full p-5 sm:p-6">
          <h2 className="text-[20px] font-black">Tecnología</h2>
          <p className="mt-2 text-[14.5px] leading-relaxed text-chalk-2">Motor en Python (numpy, pandas, scipy, xgboost). Se ejecuta solo en GitHub Actions todos los días (y viernes y sábado otra vez), descarga los datos, recalibra si toca, registra las predicciones y publica esta web estática en GitHub Pages. La interfaz es React.</p>
        </div></Reveal>
      </div>

      <Reveal><div className="card mt-5 p-5 sm:p-6">
        <h2 className="text-[20px] font-black">Límites</h2>
        <p className="mt-2 text-[14.5px] leading-relaxed text-chalk-2">Las probabilidades resumen la información disponible; no eliminan la incertidumbre de un partido. El modelo no conoce lesiones, sanciones ni rotaciones de último momento. La cobertura de datos varía por liga (la Liga 1 y las selecciones tienen menos estadísticas). Ningún pronóstico garantiza resultados. +18, apuesta con responsabilidad. <a href="#guia" className="font-semibold text-gold hover:underline">Guía para usar la web</a> · <a href="#ligas" className="font-semibold text-gold hover:underline">Ligas</a></p>
      </div></Reveal>
    </Page>
  );
}

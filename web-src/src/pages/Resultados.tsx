/* eslint-disable @typescript-eslint/no-explicit-any */
import { Check, X } from "lucide-react";
import { DATA, longDate, pct } from "@/lib/data";
import { Meter, Page, PageHeader, Reveal } from "@/components/ui-pz";

function Stat({ v, label, sub }: { v: string; label: string; sub?: string }) {
  return (
    <div className="spot lift card p-5">
      <div className="font-display text-[clamp(26px,4vw,34px)] font-black leading-none" style={{ fontStretch: "118%" }}>{v}</div>
      <p className="mt-2 text-[14px] text-chalk-2">{label}</p>
      {sub && <p className="mt-1 text-[12.5px] text-chalk-3">{sub}</p>}
    </div>
  );
}

function CalTable({ rows, title, sub }: { rows: any[]; title: string; sub: string }) {
  return (
    <div className="card p-5 sm:p-6">
      <h3 className="text-[19px] font-extrabold">{title}</h3>
      <p className="mt-1 text-[13.5px] text-chalk-3">{sub}</p>
      <div className="mt-4 flex flex-col gap-3">
        {rows.map((r: any) => (
          <div key={r.rango} className="grid grid-cols-[58px_1fr_auto] items-center gap-2 text-[13.5px] sm:grid-cols-[70px_1fr_120px] sm:gap-3 sm:text-[14px]">
            <span className="num text-chalk-3">{r.rango}</span>
            <div className="relative h-2 rounded-full bg-white/[0.07]">
              <Meter p={r.real} color={Math.abs(r.real - r.declarada) <= 0.03 ? "bg-turf" : "bg-gold"} className="absolute inset-0" />
              <span className="absolute top-[-3px] h-[14px] w-[2px] bg-chalk" style={{ left: `${r.declarada * 100}%` }} title="declarada" />
            </div>
            <span className="num text-right"><b>{pct(r.real, 1)}</b> <span className="text-[12px] text-chalk-3">n={r.n.toLocaleString("es-PE")}</span></span>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[12.5px] text-chalk-3">La barra es el acierto real; la marca blanca, lo que se declaró. Verde = diferencia de 3 puntos o menos.</p>
    </div>
  );
}

export default function Resultados() {
  const R = DATA.resultados || {};
  const M = DATA.metodologia || {};
  const ev = M.evaluacion?.con_mercado, evs = M.evaluacion?.sin_mercado;
  const hasReal = (R.liquidados || 0) > 0;
  return (
    <Page>
      <PageHeader eyebrow="Historial completo, sin borrar fallos" title="Resultados"
        sub={<>Cada pronóstico se guarda <b className="text-chalk">antes</b> de que empiece el partido y se liquida cuando termina. Nada se oculta ni se borra;
          el archivo queda en el historial público de GitHub. Las métricas usan solo partidos ya jugados.</>} />

      <div className="flex items-center gap-3"><h2 className="text-[clamp(20px,3vw,26px)] font-black">En vivo desde {R.desde ? longDate(R.desde) : "hoy"}</h2><span className="h-px flex-1 bg-white/[0.08]" /></div>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <Stat v={String(R.registrados || 0)} label="predicciones registradas" sub={`${R.pendientes || 0} por jugarse`} />
        <Stat v={String(R.liquidados || 0)} label="partidos liquidados" />
        <Stat v={R.oportunidades?.acierto != null ? pct(R.oportunidades.acierto) : "–"} label="acierto de las oportunidades" sub={R.oportunidades?.n ? `${R.oportunidades.aciertos} de ${R.oportunidades.n} · esperado ${pct(R.oportunidades.esperado)}` : "aún sin oportunidades liquidadas"} />
        <Stat v={R.fijas?.acierto != null ? pct(R.fijas.acierto) : "–"} label="acierto de las fijas" sub={R.fijas?.n ? `${R.fijas.aciertos} de ${R.fijas.n}${R.fijas.esperado ? ` · esperado ${pct(R.fijas.esperado)}` : ""}` : "aún sin fijas liquidadas"} />
      </div>
      {hasReal ? (
        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <div className="card p-5 sm:p-6">
            <h3 className="text-[19px] font-extrabold">Precisión 1X2</h3>
            <p className="mt-1 text-[13.5px] text-chalk-3">Brier: 0 es perfecto, más bajo es mejor.</p>
            <div className="mt-4 grid grid-cols-2 gap-4 text-[14px]">
              <div><div className="num text-[26px] font-semibold">{R.brier?.toFixed(3)}</div>Brier de CuchiFijas</div>
              <div><div className="num text-[26px] font-semibold text-chalk-2">{R.brier_mercado != null ? R.brier_mercado.toFixed(3) : "–"}</div>Brier de las casas {R.n_con_mercado ? `(${R.n_con_mercado} partidos)` : ""}</div>
              <div><div className="num text-[26px] font-semibold">{pct(R.acierto_favorito)}</div>acierta al favorito</div>
              <div><div className="num text-[26px] font-semibold">{R.logloss?.toFixed(3)}</div>log-loss</div>
            </div>
          </div>
          {R.calibracion?.length > 0 && <CalTable rows={R.calibracion} title="Calibración real" sub="Todos los picks candidatos registrados, agrupados por probabilidad declarada." />}
        </div>
      ) : (
        <div className="card mt-5 p-6 text-[14.5px] text-chalk-2">El registro empezó hace poco: las métricas reales aparecen cuando se liquiden los primeros partidos. Mientras tanto, abajo está el backtest.</div>
      )}

      {R.ultimos?.length > 0 && (
        <Reveal><div className="card mt-5 p-5 sm:p-6">
          <h3 className="text-[19px] font-extrabold">Últimos picks liquidados</h3>
          <ul className="mt-4 grid grid-cols-1 gap-2 md:hidden">
            {R.ultimos.map((x: any, i: number) => (
              <li key={i} className={`flex min-w-0 items-center gap-3 rounded-xl px-3 py-2.5 ring-1 ${x.acierto ? "bg-turf-soft/40 ring-turf/20" : "bg-flare/5 ring-flare/20"}`}>
                <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full ${x.acierto ? "bg-turf text-night-900" : "bg-flare text-white"}`}>{x.acierto ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />}</span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[14px] font-semibold">{x.tipo === "fija" && <span className="tag mr-1.5 bg-gold-soft text-gold">Fija</span>}{x.seleccion}</div>
                  <div className="truncate text-[12.5px] text-chalk-3">{x.local} {x.marcador} {x.visita}</div>
                </div>
                <span className="num text-[13px] text-chalk-2">{pct(x.prob)}</span>
              </li>
            ))}
          </ul>
          <div className="-mx-2 mt-4 hidden overflow-x-auto md:block">
            <table className="pz">
              <thead><tr><th>Partido</th><th>Pick</th><th className="n">Prob.</th><th className="n">Marcador</th><th className="n">Resultado</th></tr></thead>
              <tbody>
                {R.ultimos.map((x: any, i: number) => (
                  <tr key={i}>
                    <td><span className="text-[12px] text-chalk-3">{new Date(x.fecha).toLocaleDateString("es-PE", { day: "numeric", month: "short" })}</span> {x.local} – {x.visita}</td>
                    <td>{x.tipo === "fija" && <span className="tag mr-1.5 bg-gold-soft text-gold">Fija</span>}{x.seleccion}</td>
                    <td className="n">{pct(x.prob)}</td><td className="n">{x.marcador}</td>
                    <td className="n">{x.acierto ? <Check className="ml-auto h-4 w-4 text-turf" aria-label="acierto" /> : <X className="ml-auto h-4 w-4 text-flare" aria-label="fallo" />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div></Reveal>
      )}

      <div className="mt-14 flex items-center gap-3"><h2 className="text-[clamp(20px,3vw,26px)] font-black">Backtest: {ev?.periodo ? `${longDate(ev.periodo[0])} a ${longDate(ev.periodo[1])}` : "partidos pasados"}</h2><span className="hidden h-px flex-1 bg-white/[0.08] sm:block" /></div>
      <p className="mt-2 max-w-[72ch] text-[14.5px] text-chalk-3">Cada semana se reentrenan los modelos solo con partidos anteriores y se pronostica la siguiente. Los pesos del ensamble se evalúan con partidos que no vieron (validación cruzada temporal).</p>
      <div className="mt-4 grid gap-5 lg:grid-cols-2">
        {ev && (
          <div className="reveal card p-5 sm:p-6">
            <h3 className="text-[19px] font-extrabold">Con cuotas de las casas</h3>
            <p className="mt-1 text-[13.5px] text-chalk-3">{ev.ensamble.n.toLocaleString("es-PE")} partidos de ligas europeas. Log-loss: más bajo es mejor.</p>
            <ModelRows ev={ev} />
          </div>
        )}
        {evs && (
          <div className="reveal card p-5 sm:p-6">
            <h3 className="text-[19px] font-extrabold">Sin cuotas (Liga 1, selecciones, partidos sin cuotas)</h3>
            <p className="mt-1 text-[13.5px] text-chalk-3">{evs.ensamble.n.toLocaleString("es-PE")} partidos. Aquí el ensamble de 5 modelos es el que manda.</p>
            <ModelRows ev={evs} />
          </div>
        )}
        {M.calibracion?.length > 0 && <CalTable rows={M.calibracion} title="Calibración en el backtest" sub={`${(M.picks_simulados || 0).toLocaleString("es-PE")} picks simulados fuera de muestra.`} />}
        {M.arbitros?.sin_arbitro && (
          <div className="reveal card p-5 sm:p-6">
            <h3 className="text-[19px] font-extrabold">¿Sirve el árbitro para las tarjetas?</h3>
            <p className="mt-1 text-[13.5px] text-chalk-3">Premier League, {M.arbitros.n} partidos pronosticados semana a semana.</p>
            <div className="mt-4 grid grid-cols-2 gap-4 text-[14px]">
              <div><div className="num text-[24px] font-semibold">{M.arbitros.sin_arbitro.error_medio}</div>error medio sin árbitro</div>
              <div><div className="num text-[24px] font-semibold text-turf">{M.arbitros.con_arbitro.error_medio}</div>error medio con árbitro</div>
            </div>
            <p className="mt-4 text-[13.5px] leading-relaxed text-chalk-2">
              {M.arbitros.mejora ? "El factor del árbitro mejora la predicción, aunque poco: en la Premier los árbitros se parecen bastante entre sí." : "En este período el factor del árbitro no mejoró la predicción."} El efecto se encoge hacia la media ({M.arbitros.k} partidos ficticios), así que un árbitro con pocos partidos casi no mueve el número.
            </p>
          </div>
        )}
      </div>
    </Page>
  );
}

function ModelRows({ ev }: { ev: any }) {
  const N = DATA.metodologia?.nombres || {};
  const rows = [["Ensamble", ev.ensamble, true], ...Object.entries(ev.modelos).map(([k, v]) => [N[k] || k, v, false])] as [string, any, boolean][];
  if (ev.metodo_anterior) rows.push(["Método anterior (75% casas + 25% Dixon-Coles)", ev.metodo_anterior, false]);
  const best = Math.min(...rows.map((r) => r[1].logloss));
  return (
    <div className="-mx-2 mt-4 overflow-x-auto">
      <table className="pz">
        <thead><tr><th>Modelo</th><th className="n">Log-loss</th><th className="n">Brier</th><th className="n">Acierto</th></tr></thead>
        <tbody>
          {rows.map(([n, v, ens]) => (
            <tr key={n} className={ens ? "bg-gold-soft" : ""}>
              <td className={ens ? "font-bold text-gold" : ""}>{n}</td>
              <td className={`n ${v.logloss === best ? "font-bold text-turf" : ""}`}>{v.logloss.toFixed(4)}</td>
              <td className="n">{v.brier.toFixed(4)}</td><td className="n">{pct(v.acierto, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

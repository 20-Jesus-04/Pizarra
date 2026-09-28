/* eslint-disable @typescript-eslint/no-explicit-any */
import { ShieldCheck, PauseCircle, FlaskConical } from "lucide-react";
import { DATA, BY_ID, NOW, compName, dayKey, dayLabel, fTime, fair, pct } from "@/lib/data";
import { Badge, Reveal } from "@/components/ui-pz";

const NIVEL: Record<string, string> = { l1: "este mercado y línea", l2: "este mercado (todas las líneas)", l3: "esta categoría" };

export default function Fijas() {
  const F = DATA.fijas || { lista: [], criterios: {} };
  const c = F.criterios || {};
  const lista = (F.lista || []).filter((f: any) => new Date(f.fecha).getTime() > NOW);
  const days = [...new Set(lista.map((f: any) => dayKey(f.fecha)))] as string[];
  const R = DATA.resultados || {};
  return (
    <div className="mx-auto max-w-[1180px] px-5 pb-20 md:px-8">
      <div className="pt-10">
        <div className="eyebrow">El filtro más estricto</div>
        <h1 id="titulo" tabIndex={-1} className="mt-2 text-[clamp(36px,5vw,56px)] font-black leading-none">Fijas</h1>
        <p className="mt-4 max-w-[68ch] text-[16px] leading-relaxed text-chalk-2">
          No son los picks con el número más alto: son los tipos de apuesta que <b className="text-chalk">ya demostraron acertar</b> con resultados liquidados.
          Máximo {c.max_dia} por día y {c.max_partido} por partido. Si fallan, quedan en <a href="#resultados" className="font-semibold text-gold hover:underline">Resultados</a>.
        </p>
      </div>

      {F.pausa && (
        <div className="card mt-6 flex items-start gap-4 border-flare/40 p-5">
          <PauseCircle className="h-6 w-6 shrink-0 text-flare" />
          <p className="text-[15px] text-chalk-2"><b className="text-chalk">Fijas en pausa automática.</b> El acierto real de los últimos 30 días bajó de {pct(c.pausa_bajo)}. Se reanudan solas cuando vuelva a superarlo.</p>
        </div>
      )}
      {F.modo === "calibracion" && (
        <div className="card mt-6 flex items-start gap-4 p-5">
          <FlaskConical className="h-6 w-6 shrink-0 text-gold" />
          <p className="text-[14.5px] leading-relaxed text-chalk-2">
            <b className="text-chalk">En período de calibración.</b> Todavía no hay {c.volumen_30d} picks reales liquidados en 30 días
            ({R.liquidados_30d || 0} por ahora), así que la evidencia viene del backtest: partidos pasados pronosticados solo con datos anteriores a cada uno.
            Cuando haya suficiente historial real, el filtro pasa a usarlo automáticamente.
          </p>
        </div>
      )}

      {!F.pausa && (lista.length ? days.map((d) => (
        <section key={d} className="mt-8">
          <div className="mb-3 font-display text-[15px] font-extrabold uppercase tracking-[0.06em] text-chalk-3" style={{ fontStretch: "112%" }}>{dayLabel(d)}</div>
          <div className="grid gap-4 md:grid-cols-2">
            {lista.filter((f: any) => dayKey(f.fecha) === d).map((f: any, i: number) => {
              const p = BY_ID[f.id];
              return (
                <a key={i} href={`#p.${f.id}`} className="row-in card group flex flex-col gap-4 p-5 transition-colors hover:border-gold/40" style={{ animationDelay: `${i * 0.05}s` }}>
                  <div className="flex items-center justify-between gap-3 text-[12.5px] font-semibold text-chalk-3">
                    <span>{fTime(f.fecha)} · {p ? compName(p) : f.liga}</span>
                    <span className="tag bg-gold-soft text-gold"><ShieldCheck className="mr-1 inline h-3.5 w-3.5" />Fija</span>
                  </div>
                  <div className="flex items-center gap-2 text-[15px] font-semibold"><Badge name={f.local} size={26} />{f.local}<span className="text-chalk-3">vs</span>{f.visita}<Badge name={f.visita} size={26} /></div>
                  <div className="text-[20px] font-extrabold leading-snug">{f.seleccion}</div>
                  <div className="grid grid-cols-3 gap-3 border-t border-white/[0.06] pt-4 text-[12.5px] text-chalk-3">
                    <div><div className="num text-[18px] font-semibold text-chalk">{pct(f.prob_calibrada)}</div>prob. calibrada</div>
                    <div><div className="num text-[18px] font-semibold text-turf">{pct(f.lcb)}</div>acierto mínimo creíble</div>
                    <div><div className="num text-[18px] font-semibold text-chalk">{fair(f.prob_calibrada)}</div>cuota justa</div>
                  </div>
                  <p className="text-[12.5px] leading-snug text-chalk-3">
                    {f.aciertos} de {f.n} acertados en {NIVEL[f.nivel]} ({f.fuente === "real" ? "resultados reales" : "backtest"}){f.forma != null ? ` · ${f.forma} de los últimos 10` : ""}.
                  </p>
                </a>
              );
            })}
          </div>
        </section>
      )) : <div className="card mt-8 p-10 text-center text-chalk-3">Hoy ningún pick pasa los cuatro filtros. Es normal: el filtro prefiere no publicar antes que publicar algo dudoso.</div>)}

      <Reveal><div className="card mt-10 p-6">
        <h2 className="text-[20px] font-extrabold">Los cuatro filtros</h2>
        <ol className="mt-4 grid gap-4 text-[14.5px] leading-relaxed text-chalk-2 md:grid-cols-2">
          <li><b className="text-chalk">1. Volumen real.</b> Solo cuenta evidencia con al menos {c.volumen_30d} picks liquidados en 30 días; mientras tanto se usa el backtest y se avisa.</li>
          <li><b className="text-chalk">2. Subtipo (Beta-Binomial).</b> El límite inferior creíble al 95% del acierto de ese mercado y línea debe superar {pct(c.min_lcb)} con al menos {c.min_n} casos. Sin muestra suficiente se amplía al mercado completo y luego a la categoría, sin mezclar selecciones opuestas.</li>
          <li><b className="text-chalk">3. Forma reciente.</b> Al menos {c.forma} liquidados de ese nivel acertados.</li>
          <li><b className="text-chalk">4. Correlación.</b> Máximo 1 por grupo (resultado, goles, córners, tarjetas) y partido, {c.max_partido} por partido y {c.max_dia} por día. Pausa automática si el acierto real en 30 días cae bajo {pct(c.pausa_bajo)}.</li>
        </ol>
        <p className="mt-4 text-[13px] text-chalk-3">Antes de filtrar, cada probabilidad pasa por la curva de calibración (lo que el modelo declara → lo que de verdad ocurrió). Se descartan picks por encima de {pct(c.max_declarada)}: pagarían tan poco que no tienen sentido. Ninguna fija es segura.</p>
      </div></Reveal>
    </div>
  );
}

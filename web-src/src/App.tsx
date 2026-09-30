import { useEffect, useState } from "react";
import { flushSync } from "react-dom";
import { MotionConfig, motion, useScroll, useSpring } from "framer-motion";
import { BarChart3, BookOpen, History, Home as HomeIcon, ShieldCheck, Trophy } from "lucide-react";
import Home from "@/pages/Home";
import Matches from "@/pages/Matches";
import Match from "@/pages/Match";
import Leagues from "@/pages/Leagues";
import Guide from "@/pages/Guide";
import Fijas from "@/pages/Fijas";
import Resultados from "@/pages/Resultados";
import Metodo from "@/pages/Metodo";
import { BY_ID, DATA, LG, MATCHES, NOW } from "@/lib/data";

const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Ruta en el hash. Si el navegador soporta View Transitions, el cambio de página se anima (mejora progresiva). */
function useHash() {
  const read = () => location.hash.slice(1) || "inicio";
  const [h, setH] = useState(read);
  useEffect(() => {
    const f = () => {
      const next = read();
      const update = () => { setH(next); window.scrollTo({ top: 0 }); };
      type VT = { finished: Promise<void>; ready: Promise<void>; updateCallbackDone: Promise<void> };
      const doc = document as Document & { startViewTransition?: (cb: () => void) => VT };
      if (!doc.startViewTransition || reduceMotion() || document.visibilityState !== "visible") { update(); return; }
      const t = doc.startViewTransition(() => flushSync(update));
      // si la transición se cancela (navegación muy rápida), la página igual se actualiza: solo se evita el error en consola
      const ignore = () => {};
      t.ready.catch(ignore); t.updateCallbackDone.catch(ignore);
      t.finished.catch(ignore).finally(() => document.getElementById("titulo")?.focus({ preventScroll: true }));
    };
    addEventListener("hashchange", f);
    return () => removeEventListener("hashchange", f);
  }, []);
  return h;
}

/** Un único listener mueve el foco de luz de la card bajo el cursor (.spot). */
function useSpotlight() {
  useEffect(() => {
    if (!matchMedia("(hover: hover)").matches) return;
    let raf = 0;
    const on = (e: PointerEvent) => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const el = (e.target as Element | null)?.closest?.(".spot") as HTMLElement | null;
        if (!el) return;
        const r = el.getBoundingClientRect();
        el.style.setProperty("--mx", `${e.clientX - r.left}px`);
        el.style.setProperty("--my", `${e.clientY - r.top}px`);
      });
    };
    addEventListener("pointermove", on, { passive: true });
    return () => { removeEventListener("pointermove", on); cancelAnimationFrame(raf); };
  }, []);
}

const NAV = [
  ["inicio", "Inicio", HomeIcon],
  ["partidos", "Partidos", Trophy],
  ["fijas", "Fijas", ShieldCheck],
  ["resultados", "Resultados", History],
  ["ligas", "Ligas", BarChart3],
  ["metodo", "Método", BookOpen],
] as const;
const MOBILE = NAV.filter(([k]) => k !== "ligas");

function Logo() {
  return (
    <a href="#inicio" className="flex shrink-0 items-center gap-2.5 font-display text-[19px] font-black tracking-wide sm:text-[20px]" style={{ fontStretch: "125%" }} aria-label="Pizarra, inicio">
      <motion.svg whileHover={{ rotate: 90 }} transition={{ type: "spring", stiffness: 300 }} width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
        <rect width="30" height="30" rx="9" fill="#1A2445" /><circle cx="15" cy="15" r="6" fill="none" stroke="#FFC23D" strokeWidth="2.2" /><path d="M15 4v22" stroke="#EEF2FF" strokeWidth="1.6" opacity=".5" /><circle cx="15" cy="15" r="1.8" fill="#FFC23D" />
      </motion.svg>
      PIZARRA
    </a>
  );
}

export default function App() {
  const hash = useHash();
  useSpotlight();
  const [view, ...rest] = hash.split(".");
  const arg = rest.join(".") || null;
  const [lastLg, setLastLg] = useState<string | null>(null);
  useEffect(() => { if (view === "partidos") setLastLg(arg); }, [view, arg]);
  const section = view === "p" ? "partidos" : view === "liga" ? "ligas" : ["partidos", "ligas", "fijas", "resultados", "metodo"].includes(view) ? view : view === "oportunidades" ? "fijas" : view === "guia" ? "metodo" : "inicio";

  let page, title;
  if (view === "partidos") { page = <Matches lg={arg && LG[arg] ? arg : null} />; title = "Partidos"; }
  else if (view === "p") { page = <Match id={arg || ""} backTo={`#partidos${lastLg ? "." + lastLg : ""}`} />; const m = BY_ID[arg || ""]; title = m ? `${m.local} vs ${m.visita}` : "Partido"; }
  else if (view === "ligas" || view === "liga") { const c = arg && LG[arg] ? arg : "E0"; page = <Leagues code={c} />; title = LG[c]?.name; }
  else if (view === "guia") { page = <Guide />; title = "Cómo usar Pizarra"; }
  else if (view === "fijas") { page = <Fijas key="f" />; title = "Fijas"; }
  else if (view === "oportunidades") { page = <Fijas key="o" tab="oportunidades" />; title = "Oportunidades"; }
  else if (view === "resultados") { page = <Resultados />; title = "Resultados"; }
  else if (view === "metodo") { page = <Metodo />; title = "Metodología"; }
  else { page = <Home />; title = "Pronósticos con datos"; }

  useEffect(() => {
    document.title = `${title} — Pizarra`;
    const t = setTimeout(() => document.getElementById("titulo")?.focus({ preventScroll: true }), 350);
    return () => clearTimeout(t);
  }, [hash, title]);

  const { scrollYProgress } = useScroll();
  const progress = useSpring(scrollYProgress, { stiffness: 200, damping: 30 });
  const vt = typeof document !== "undefined" && "startViewTransition" in document;
  const nFijas = (DATA.fijas?.lista || []).filter((f: { fecha: string }) => new Date(f.fecha).getTime() > NOW).length;

  return (
    <MotionConfig reducedMotion="user">
      <div className="grain relative min-h-screen overflow-x-clip bg-night-900">
        <div className="aurora" aria-hidden="true"><i /><i /><i /></div>
        <a href="#titulo" onClick={(e) => { e.preventDefault(); document.getElementById("titulo")?.focus(); }}
          className="fixed left-3 top-3 z-[60] -translate-y-20 rounded-lg bg-gold px-4 py-2 font-bold text-night-900 focus:translate-y-0">Saltar al contenido</a>
        <motion.div style={{ scaleX: progress }} className="fixed inset-x-0 top-0 z-[55] h-[3px] origin-left bg-gradient-to-r from-cobalt via-gold to-turf" />

        <header className="hdr sticky z-50 border-b border-white/[0.06] bg-night-900/70 backdrop-blur-xl" style={{ top: "env(safe-area-inset-top, 0px)" }}>
          <div className="mx-auto flex h-[60px] max-w-[1240px] items-center gap-4 px-4 sm:h-[68px] sm:px-6 lg:px-8">
            <Logo />
            <nav className="ml-auto hidden items-center gap-0.5 lg:flex" aria-label="Principal">
              {NAV.map(([k, t]) => (
                <a key={k} href={`#${k}`} aria-current={section === k ? "page" : undefined} className={`relative rounded-full px-3.5 py-2 text-[14.5px] font-semibold transition-colors ${section === k ? "text-night-900" : "text-chalk-2 hover:text-chalk"}`}>
                  {section === k && <motion.span layoutId="nav-pill" className="absolute inset-0 rounded-full bg-chalk" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
                  <span className="relative">{t}</span>
                  {k === "fijas" && nFijas > 0 && <span className="relative ml-1.5 rounded-full bg-gold px-1.5 py-px text-[10.5px] font-extrabold text-night-900">{nFijas}</span>}
                </a>
              ))}
            </nav>
            <a href="#partidos" className="shine ml-auto inline-flex items-center gap-2 rounded-full bg-gold px-4 py-2 text-[13.5px] font-bold text-night-900 shadow-[0_8px_30px_-10px_rgba(255,194,61,.8)] sm:text-[14px] lg:ml-0">
              <span className="live-dot h-1.5 w-1.5 rounded-full bg-night-900" />{MATCHES.length} partidos
            </a>
          </div>
        </header>

        <main key={hash} className={`relative z-[1] pb-28 lg:pb-0 ${vt ? "" : "page-in"}`}>
          {page}
        </main>

        <footer className="relative z-[1] border-t border-white/[0.06] bg-night-950/60 pb-28 backdrop-blur lg:pb-0">
          <div className="mx-auto grid max-w-[1240px] grid-cols-2 gap-8 px-4 py-10 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr] lg:px-8">
            <div className="col-span-2 md:col-span-1">
              <Logo />
              <p className="mt-3 max-w-[42ch] text-[14px] leading-relaxed text-chalk-3">Seis modelos estadísticos, un auditor automático y un historial que no se borra. Probabilidades, no certezas.</p>
              <p className="mt-3 text-[12.5px] text-chalk-3">Datos del {new Date(DATA.generado).toLocaleString("es-PE", { timeZone: "America/Lima", dateStyle: "long", timeStyle: "short" })}</p>
            </div>
            {[["Pronósticos", [["Partidos", "#partidos"], ["Fijas", "#fijas"], ["Ligas", "#ligas"]]], ["Transparencia", [["Resultados", "#resultados"], ["Metodología", "#metodo"], ["Guía rápida", "#guia"]]]].map(([h, links]) => (
              <div key={h as string}>
                <div className="eyebrow">{h as string}</div>
                <ul className="mt-3 grid gap-2 text-[14.5px]">
                  {(links as string[][]).map(([t, href]) => <li key={href}><a href={href} className="text-chalk-2 transition-colors hover:text-gold">{t}</a></li>)}
                </ul>
              </div>
            ))}
          </div>
          <div className="border-t border-white/[0.06]">
            <p className="mx-auto max-w-[1240px] px-4 py-5 text-[12.5px] text-chalk-3 sm:px-6 lg:px-8">Apuesta con responsabilidad · Solo mayores de 18 años · Fuentes: football-data.co.uk, ESPN, martj42/international_results.</p>
          </div>
        </footer>

        <nav className="bnav fixed inset-x-0 bottom-0 z-50 grid grid-cols-5 border-t border-white/10 bg-night-850/85 px-1 pt-1.5 backdrop-blur-xl lg:hidden"
          style={{ paddingBottom: "calc(6px + env(safe-area-inset-bottom, 0px))" }} aria-label="Principal (móvil)">
          {MOBILE.map(([k, t, Icon]) => (
            <a key={k} href={`#${k}`} aria-current={section === k ? "page" : undefined} className={`relative flex flex-col items-center gap-0.5 rounded-xl py-1.5 text-[11px] font-semibold transition-colors ${section === k ? "text-gold" : "text-chalk-3"}`}>
              {section === k && <motion.span layoutId="bnav" className="absolute inset-x-1 inset-y-0 rounded-xl bg-gold-soft" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
              <span className="relative">
                <Icon className="h-[22px] w-[22px]" />
                {k === "fijas" && nFijas > 0 && <span className="absolute -right-2.5 -top-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-gold px-1 text-[9.5px] font-extrabold text-night-900">{nFijas}</span>}
              </span>
              <span className="relative">{t}</span>
            </a>
          ))}
        </nav>
      </div>
    </MotionConfig>
  );
}

import { useEffect, useState } from "react";
import { MotionConfig, motion, useScroll, useSpring } from "framer-motion";
import { BarChart3, CircleHelp, Home as HomeIcon, Trophy } from "lucide-react";
import Home from "@/pages/Home";
import Matches from "@/pages/Matches";
import Match from "@/pages/Match";
import Leagues from "@/pages/Leagues";
import Guide from "@/pages/Guide";
import { BY_ID, LG } from "@/lib/data";

function useHash() {
  const [h, setH] = useState(() => location.hash.slice(1) || "inicio");
  useEffect(() => { const f = () => setH(location.hash.slice(1) || "inicio"); addEventListener("hashchange", f); return () => removeEventListener("hashchange", f); }, []);
  return h;
}

const NAV = [
  ["inicio", "Inicio", HomeIcon],
  ["partidos", "Partidos", Trophy],
  ["ligas", "Ligas", BarChart3],
  ["guia", "Cómo usarla", CircleHelp],
] as const;

export default function App() {
  const hash = useHash();
  const [view, ...rest] = hash.split(".");
  const arg = rest.join(".") || null;
  const [lastLg, setLastLg] = useState<string | null>(null);
  useEffect(() => { if (view === "partidos") setLastLg(arg); }, [view, arg]);
  const section = view === "p" ? "partidos" : view === "liga" ? "ligas" : ["partidos", "ligas", "guia"].includes(view) ? view : "inicio";

  let page, title;
  if (view === "partidos") { page = <Matches lg={arg && LG[arg] ? arg : null} />; title = "Partidos"; }
  else if (view === "p") { page = <Match id={arg || ""} backTo={`#partidos${lastLg ? "." + lastLg : ""}`} />; const m = BY_ID[arg || ""]; title = m ? `${m.local} vs ${m.visita}` : "Partido"; }
  else if (view === "ligas" || view === "liga") { const c = arg && LG[arg] ? arg : "E0"; page = <Leagues code={c} />; title = LG[c]?.name; }
  else if (view === "guia") { page = <Guide />; title = "Cómo usar Pizarra"; }
  else { page = <Home />; title = "Pronósticos con datos"; }

  useEffect(() => {
    document.title = `${title} — Pizarra`;
    window.scrollTo({ top: 0 });
    const t = setTimeout(() => document.getElementById("titulo")?.focus({ preventScroll: true }), 350);
    return () => clearTimeout(t);
  }, [hash, title]);

  const { scrollYProgress } = useScroll();
  const progress = useSpring(scrollYProgress, { stiffness: 200, damping: 30 });

  return (
    <MotionConfig reducedMotion="user">
      <div className="grain min-h-screen bg-night-900">
        <a href="#titulo" onClick={(e) => { e.preventDefault(); document.getElementById("titulo")?.focus(); }}
          className="fixed left-3 top-3 z-[60] -translate-y-20 rounded-lg bg-gold px-4 py-2 font-bold text-night-900 focus:translate-y-0">Saltar al contenido</a>
        <motion.div style={{ scaleX: progress }} className="fixed inset-x-0 top-0 z-[55] h-[3px] origin-left bg-gradient-to-r from-cobalt via-gold to-turf" />

        <header className="sticky z-50 border-b border-white/[0.06] bg-night-900/75 backdrop-blur-xl" style={{ top: "env(safe-area-inset-top, 0px)" }}>
          <div className="mx-auto flex h-[68px] max-w-[1180px] items-center gap-6 px-5 md:px-8">
            <a href="#inicio" className="flex items-center gap-2.5 font-display text-[20px] font-black tracking-wide" style={{ fontStretch: "125%" }} aria-label="Pizarra, inicio">
              <motion.svg whileHover={{ rotate: 90 }} transition={{ type: "spring", stiffness: 300 }} width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
                <rect width="30" height="30" rx="9" fill="#1A2445" /><circle cx="15" cy="15" r="6" fill="none" stroke="#FFC23D" strokeWidth="2.2" /><path d="M15 4v22" stroke="#EEF2FF" strokeWidth="1.6" opacity=".5" /><circle cx="15" cy="15" r="1.8" fill="#FFC23D" />
              </motion.svg>
              PIZARRA
            </a>
            <nav className="ml-auto hidden gap-1 md:flex" aria-label="Principal">
              {NAV.map(([k, t]) => (
                <a key={k} href={`#${k}`} aria-current={section === k ? "page" : undefined} className={`relative rounded-full px-4 py-2 text-[14.5px] font-semibold transition-colors ${section === k ? "text-night-900" : "text-chalk-2 hover:text-chalk"}`}>
                  {section === k && <motion.span layoutId="nav-pill" className="absolute inset-0 rounded-full bg-chalk" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
                  <span className="relative">{t}</span>
                </a>
              ))}
            </nav>
            <a href="#partidos" className="ml-auto rounded-full bg-gold px-4 py-2 text-[14px] font-bold text-night-900 md:ml-0">Ver partidos</a>
          </div>
        </header>

        <main key={hash} className="page-in pb-24 md:pb-0">
          {page}
        </main>

        <footer className="hidden border-t border-white/[0.06] md:block">
          <div className="mx-auto flex max-w-[1180px] items-center justify-between gap-6 px-8 py-8 text-[13px] text-chalk-3">
            <span className="font-display font-black tracking-wide text-chalk-2" style={{ fontStretch: "125%" }}>PIZARRA</span>
            <span>Probabilidades, no certezas. Apuesta con responsabilidad · +18</span>
          </div>
        </footer>

        <nav className="fixed inset-x-0 bottom-0 z-50 grid grid-cols-4 border-t border-white/10 bg-night-850/90 px-2 pt-1.5 backdrop-blur-xl md:hidden"
          style={{ paddingBottom: "calc(6px + env(safe-area-inset-bottom, 0px))" }} aria-label="Principal (móvil)">
          {NAV.map(([k, t, Icon]) => (
            <a key={k} href={`#${k}`} aria-current={section === k ? "page" : undefined} className={`relative flex flex-col items-center gap-0.5 rounded-xl py-1.5 text-[11px] font-semibold ${section === k ? "text-gold" : "text-chalk-3"}`}>
              {section === k && <motion.span layoutId="bnav" className="absolute inset-0 rounded-xl bg-gold-soft" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
              <Icon className="relative h-[22px] w-[22px]" /><span className="relative">{k === "guia" ? "Guía" : t}</span>
            </a>
          ))}
        </nav>
      </div>
    </MotionConfig>
  );
}

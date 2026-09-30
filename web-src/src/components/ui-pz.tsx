/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { motion, useInView, useMotionValue, useSpring, useTransform, animate, AnimatePresence, useReducedMotion } from "framer-motion";
import { hue, initials, pct, fTime, dayShort, dayKey, compName, isLive, type Pick } from "@/lib/data";

export const ease = [0.22, 1, 0.36, 1] as const;

/** Aparece al entrar en pantalla con CSS nativo (scroll-driven). Sin soporte, el contenido simplemente está. */
export function Reveal({ children, className = "" }: { children: ReactNode; delay?: number; y?: number; className?: string }) {
  return <div className={`reveal ${className}`}>{children}</div>;
}

export const stagger = { hidden: {}, show: { transition: { staggerChildren: 0.06 } } };
export const item = { hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0, transition: { duration: 0.5, ease } } };

/** Número que cuenta desde 0 al entrar en pantalla. */
export function Counter({ to, decimals = 0, suffix = "", prefix = "" }: { to: number; decimals?: number; suffix?: string; prefix?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const reduce = useReducedMotion();
  const [v, setV] = useState(to);
  useEffect(() => {
    if (!inView || reduce) return;
    const c = animate(0, to, { duration: 1.4, ease, onUpdate: setV });
    const t = setTimeout(() => setV(to), 1700);   // si el navegador pausa la animación, igual termina en el valor real
    return () => { c.stop(); clearTimeout(t); };
  }, [inView, to, reduce]);
  return <span ref={ref} className="num">{prefix}{v.toLocaleString("es-PE", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}{suffix}</span>;
}

/** Anillo de probabilidad: el valor final está en el estilo; la animación CSS solo parte de vacío. */
export function Ring({ p, size = 64, stroke = 6, color = "#6C7BFF", label }: { p: number; size?: number; stroke?: number; color?: string; label?: ReactNode }) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r;
  return (
    <div className="relative grid shrink-0 place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(238,242,255,.09)" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" className="ring-fill"
          strokeDasharray={c} style={{ strokeDashoffset: c * (1 - Math.max(0, Math.min(1, p))), ["--c" as any]: c, filter: `drop-shadow(0 0 6px ${color}66)` }} />
      </svg>
      <div className="absolute inset-0 grid place-items-center">{label ?? <span className="num text-[15px] font-semibold">{pct(p)}</span>}</div>
    </div>
  );
}

export function Meter({ p, color = "bg-cobalt", className = "" }: { p: number; color?: string; className?: string }) {
  return (
    <div className={`h-1.5 overflow-hidden rounded-full bg-white/[0.07] ${className}`}>
      <div className={`grow-x h-full rounded-full ${color}`} style={{ width: `${Math.min(100, Math.max(0, p * 100))}%` }} />
    </div>
  );
}

export function Badge({ name, size = 40 }: { name: string; size?: number }) {
  const h = hue(name);
  return (
    <span className="grid shrink-0 place-items-center rounded-full font-display font-extrabold text-white"
      style={{ width: size, height: size, fontSize: size * 0.34, fontStretch: "112%",
        background: `radial-gradient(120% 120% at 30% 20%, hsl(${h} 70% 58%), hsl(${(h + 40) % 360} 60% 28%))`,
        boxShadow: `0 0 0 2px rgba(255,255,255,.08), 0 8px 24px -10px hsl(${h} 70% 50% / .7)` }} aria-hidden="true">
      {initials(name)}
    </span>
  );
}

export function FormDots({ s }: { s?: string }) {
  if (!s) return null;
  const c: Record<string, string> = { G: "bg-turf text-night-900", E: "bg-chalk-3 text-night-900", P: "bg-flare text-white" };
  const t: Record<string, string> = { G: "Ganó", E: "Empató", P: "Perdió" };
  return (
    <span className="inline-flex gap-1">
      {[...s].slice(-5).map((x, i) => (
        <i key={i} title={t[x]} style={{ animationDelay: `${0.3 + i * 0.06}s` }}
          className={`pop-in grid h-[18px] w-[18px] place-items-center rounded-[5px] text-[9.5px] font-black not-italic ${c[x] || ""}`}>{x}</i>
      ))}
    </span>
  );
}

/** Pizarra táctica animada: las líneas se dibujan y la pelota recorre la jugada. */
export function Pitch({ className = "" }: { className?: string }) {
  const reduce = useReducedMotion();
  const draw = (d: number) => (reduce ? {} : { initial: { pathLength: 0, opacity: 0 }, animate: { pathLength: 1, opacity: 1 }, transition: { duration: 1.8, delay: d, ease } });
  return (
    <svg className={`pointer-events-none absolute inset-0 h-full w-full ${className}`} viewBox="0 0 1200 600" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <g fill="none" stroke="rgba(238,242,255,.09)" strokeWidth="2">
        <motion.rect x="40" y="40" width="1120" height="520" rx="6" {...draw(0)} />
        <motion.path d="M600 40v520" {...draw(0.2)} />
        <motion.circle cx="600" cy="300" r="90" {...draw(0.3)} />
        <motion.path d="M40 170h150v260H40M1160 170h-150v260h150M40 235h55v130H40M1160 235h-55v130h55" {...draw(0.4)} />
        <motion.path d="M190 240a70 70 0 0 1 0 120M1010 240a70 70 0 0 0 0 120" {...draw(0.5)} />
      </g>
      <motion.path d="M300 440C420 330 520 370 600 300S790 140 905 205" fill="none" stroke="rgba(255,194,61,.35)" strokeWidth="3" strokeDasharray="2 12" strokeLinecap="round"
        {...(reduce ? {} : { initial: { pathLength: 0 }, animate: { pathLength: 1 }, transition: { duration: 2.2, delay: 1, ease } })} />
      <g fill="none" stroke="rgba(238,242,255,.18)" strokeWidth="3"><circle cx="300" cy="440" r="13" /><path d="M895 195l20 20M915 195l-20 20" /></g>
      {!reduce && (
        <motion.circle r="7" fill="#FFC23D" initial={{ offsetDistance: "0%", opacity: 0 }} animate={{ offsetDistance: "100%", opacity: [0, 1, 1, 0] }}
          transition={{ duration: 3.2, delay: 1.2, repeat: Infinity, repeatDelay: 2.5, ease: "easeInOut" }}
          style={{ offsetPath: "path('M300 440C420 330 520 370 600 300S790 140 905 205')", filter: "drop-shadow(0 0 10px rgba(255,194,61,.9))" } as any} />
      )}
    </svg>
  );
}

/** Ticket de apuesta con inclinación 3D al pasar el cursor. */
export function Ticket({ k, compact = false, featured = false }: { k: Pick; compact?: boolean; featured?: boolean }) {
  const p = k.p;
  const reduce = useReducedMotion();
  const mx = useMotionValue(0), my = useMotionValue(0);
  const rx = useSpring(useTransform(my, [-0.5, 0.5], [7, -7]), { stiffness: 200, damping: 18 });
  const ry = useSpring(useTransform(mx, [-0.5, 0.5], [-9, 9]), { stiffness: 200, damping: 18 });
  const onMove = (e: React.MouseEvent) => { if (reduce) return; const r = e.currentTarget.getBoundingClientRect(); mx.set((e.clientX - r.left) / r.width - 0.5); my.set((e.clientY - r.top) / r.height - 0.5); };
  const reset = () => { mx.set(0); my.set(0); };
  const Tag: any = compact ? motion.div : motion.a;
  return (
    <div style={{ perspective: 900 }} className="h-full">
      <Tag href={compact ? undefined : `#p.${p.id}`} onMouseMove={onMove} onMouseLeave={reset} style={{ rotateX: rx, rotateY: ry, transformStyle: "preserve-3d" }}
        whileHover={{ y: -4 }} className={`shine group relative flex h-full flex-col rounded-2xl text-night-900 no-underline ${featured ? "bg-gradient-to-br from-[#FFF7E3] to-[#FFE4A3]" : "bg-[#F4F6FF]"}`}
        aria-label={compact ? undefined : `${k.sel} en ${p.local} contra ${p.visita}, probabilidad ${pct(k.prob)}`}>
        <div className="flex flex-1 flex-col gap-1.5 px-5 pb-4 pt-4" style={{ transform: "translateZ(30px)" }}>
          <div className="flex items-center justify-between gap-2 text-[12px] font-semibold text-night-600/70">
            <span className="truncate">{compact ? (k.valor ? "Recomendada por valor" : "Alta probabilidad") : compName(p)}</span>
            {!compact && <span className="shrink-0">{isLive(p) ? "En juego" : `${dayShort(dayKey(p.fecha))} · ${fTime(p.fecha)}`}</span>}
          </div>
          {!compact && <div className="text-[15px] font-bold">{p.local} <span className="font-medium text-night-600/60">vs</span> {p.visita}</div>}
          <div className={`font-display font-extrabold leading-[1.1] ${featured ? "text-[27px]" : "text-[21px]"}`} style={{ fontStretch: "112%" }}>{k.sel}</div>
          {k.valor && <span className="tag mt-1 self-start bg-night-900 text-gold">Con valor · +{((k.ev || 0) * 100).toFixed(0)}%</span>}
        </div>
        <div className="relative mx-4 border-t-2 border-dashed border-night-900/15" aria-hidden="true">
          <span className="absolute -left-[27px] -top-[11px] h-5 w-5 rounded-full bg-night-900" />
          <span className="absolute -right-[27px] -top-[11px] h-5 w-5 rounded-full bg-night-900" />
        </div>
        <div className="grid grid-cols-[auto_1fr_auto] items-center gap-4 px-5 pb-4 pt-3.5" style={{ transform: "translateZ(20px)" }}>
          <div>
            <div className="num text-[26px] font-semibold leading-none">{pct(k.prob)}</div>
            <div className="mt-1 text-[10.5px] font-bold tracking-[0.08em] text-night-600/60">PROBABILIDAD</div>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-night-900/10">
            <div className="grow-x h-full rounded-full bg-cobalt-deep" style={{ width: `${k.prob * 100}%` }} />
          </div>
          <div className="text-right text-[11.5px] font-semibold text-night-600/60">
            {k.casa ? "Casa" : "Cuota justa"}
            <div className="num text-[18px] font-semibold text-night-900">{Number(k.casa || k.fair).toFixed(2)}</div>
          </div>
        </div>
      </Tag>
    </div>
  );
}

/** Pestañas con subrayado animado y navegación con flechas. */
export function Tabs({ tabs, value, onChange, id = "tabs" }: { tabs: [string, string][]; value: string; onChange: (v: string) => void; id?: string }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: React.KeyboardEvent, i: number) => {
    let j: number | null = null;
    if (e.key === "ArrowRight") j = (i + 1) % tabs.length; if (e.key === "ArrowLeft") j = (i - 1 + tabs.length) % tabs.length;
    if (e.key === "Home") j = 0; if (e.key === "End") j = tabs.length - 1;
    if (j != null) { e.preventDefault(); onChange(tabs[j][0]); refs.current[j]?.focus(); }
  };
  return (
    <div role="tablist" className="scrollbar-none flex gap-1 overflow-x-auto border-b border-white/10">
      {tabs.map(([k, t], i) => (
        <button key={k} ref={(el) => { refs.current[i] = el; }} role="tab" id={`${id}-${k}`} aria-selected={k === value} aria-controls={`${id}-panel`} tabIndex={k === value ? 0 : -1}
          onClick={() => onChange(k)} onKeyDown={(e) => onKey(e, i)}
          className={`relative shrink-0 px-4 py-3 text-[15px] font-bold transition-colors ${k === value ? "text-chalk" : "text-chalk-3 hover:text-chalk-2"}`}>
          {t}
          {k === value && <motion.span layoutId={`${id}-u`} className="absolute inset-x-2 -bottom-px h-[3px] rounded-full bg-gold" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
        </button>
      ))}
    </div>
  );
}

export function Accordion({ title, sub, children, defaultOpen = false }: { title: string; sub?: string; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="card overflow-hidden">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center gap-4 px-5 py-4 text-left">
        <div className="flex-1"><div className="text-[16px] font-bold">{title}</div>{sub && <div className="text-[13px] text-chalk-3">{sub}</div>}</div>
        <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full bg-white/5 text-[20px] text-chalk-2 transition-transform duration-300 ${open ? "rotate-45" : ""}`} aria-hidden="true">+</span>
      </button>
      <div className="acc" data-open={open}>
        <div><div className="px-5 pb-5" hidden={!open}>{children}</div></div>
      </div>
    </div>
  );
}

export function SectionHead({ title, sub, action, eyebrow }: { title: string; sub?: string; action?: ReactNode; eyebrow?: string }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow mb-2 flex items-center gap-2"><span className="h-px w-6 bg-gold" />{eyebrow}</div>}
        <h2 className="text-[clamp(24px,3.6vw,38px)] font-extrabold leading-[1.05]">{title}</h2>
        {sub && <p className="mt-2 max-w-[60ch] text-[15px] text-chalk-2 md:text-[16px]">{sub}</p>}
      </div>
      {action}
    </div>
  );
}

/** Encabezado común de cada página: migas, título, bajada, acciones y cifras clave. */
export function PageHeader({ eyebrow, title, sub, actions, stats, crumbs }: {
  eyebrow?: string; title: ReactNode; sub?: ReactNode; actions?: ReactNode; crumbs?: [string, string][];
  stats?: { v: ReactNode; l: string; tone?: "gold" | "turf" | "cobalt" | "flare" }[];
}) {
  const tone = { gold: "text-gold", turf: "text-turf", cobalt: "text-cobalt", flare: "text-flare" };
  return (
    <header className="relative pb-8 pt-8 md:pb-10 md:pt-12">
      <div className="pointer-events-none absolute -top-10 left-1/3 h-48 w-[60%] -translate-x-1/2 rounded-full bg-cobalt/10 blur-[90px]" />
      {crumbs && (
        <nav aria-label="Ruta" className="relative mb-4 flex flex-wrap items-center gap-1.5 text-[13px] text-chalk-3">
          {crumbs.map(([t, h], i) => <span key={h} className="flex items-center gap-1.5">{i > 0 && <span aria-hidden="true">/</span>}<a href={h} className="hover:text-chalk">{t}</a></span>)}
        </nav>
      )}
      <div className="relative flex flex-wrap items-end justify-between gap-x-8 gap-y-5">
        <div className="min-w-0 max-w-[760px]">
          {eyebrow && <div className="eyebrow flex items-center gap-2"><span className="h-px w-6 bg-gold" />{eyebrow}</div>}
          <h1 id="titulo" tabIndex={-1} className="mt-3 text-[clamp(34px,6vw,64px)] font-black leading-[0.98]">{title}</h1>
          {sub && <div className="mt-4 max-w-[68ch] text-[15.5px] leading-relaxed text-chalk-2 md:text-[17px]">{sub}</div>}
        </div>
        {actions && <div className="flex w-full flex-wrap gap-2 sm:w-auto">{actions}</div>}
      </div>
      {stats && stats.length > 0 && (
        <div className="relative mt-8 grid grid-cols-2 gap-3 md:grid-cols-4">
          {stats.map((st, i) => (
            <div key={i} className="spot lift rounded-2xl border border-white/[0.07] bg-white/[0.03] px-4 py-3.5 backdrop-blur">
              <div className={`font-display text-[clamp(22px,3.2vw,30px)] font-black leading-none ${st.tone ? tone[st.tone] : ""}`} style={{ fontStretch: "118%" }}>{st.v}</div>
              <div className="mt-1.5 text-[12.5px] leading-snug text-chalk-3">{st.l}</div>
            </div>
          ))}
        </div>
      )}
    </header>
  );
}

/** Contenedor de página con ancho y márgenes consistentes. */
export function Page({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`mx-auto w-full max-w-[1240px] px-4 pb-24 sm:px-6 lg:px-8 ${className}`}>{children}</div>;
}

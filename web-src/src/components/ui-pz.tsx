/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { motion, useInView, useMotionValue, useSpring, useTransform, animate, AnimatePresence, useReducedMotion } from "framer-motion";
import { hue, initials, pct, fTime, dayShort, dayKey, compName, isLive, type Pick } from "@/lib/data";

export const ease = [0.22, 1, 0.36, 1] as const;

/** Aparece al entrar en pantalla (arranca visible si el usuario prefiere menos movimiento). */
export function Reveal({ children, delay = 0, y = 18, className = "" }: { children: ReactNode; delay?: number; y?: number; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <motion.div className={className} initial={reduce ? false : { opacity: 0, y }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }} transition={{ duration: 0.6, delay, ease }}>
      {children}
    </motion.div>
  );
}

export const stagger = { hidden: {}, show: { transition: { staggerChildren: 0.06 } } };
export const item = { hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0, transition: { duration: 0.5, ease } } };

/** Número que cuenta desde 0 al entrar en pantalla. */
export function Counter({ to, decimals = 0, suffix = "", prefix = "" }: { to: number; decimals?: number; suffix?: string; prefix?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const reduce = useReducedMotion();
  const [v, setV] = useState(reduce ? to : 0);
  useEffect(() => {
    if (!inView || reduce) return;
    const c = animate(0, to, { duration: 1.4, ease, onUpdate: setV });
    return () => c.stop();
  }, [inView, to, reduce]);
  return <span ref={ref} className="num">{prefix}{v.toLocaleString("es-PE", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}{suffix}</span>;
}

/** Anillo de probabilidad animado. */
export function Ring({ p, size = 64, stroke = 6, color = "#6C7BFF", label }: { p: number; size?: number; stroke?: number; color?: string; label?: ReactNode }) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r;
  return (
    <div className="relative grid shrink-0 place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(238,242,255,.09)" strokeWidth={stroke} />
        <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} initial={{ strokeDashoffset: c }} whileInView={{ strokeDashoffset: c * (1 - p) }} viewport={{ once: true }}
          transition={{ duration: 1.2, ease }} />
      </svg>
      <div className="absolute inset-0 grid place-items-center">{label ?? <span className="num text-[15px] font-semibold">{pct(p)}</span>}</div>
    </div>
  );
}

export function Meter({ p, color = "bg-cobalt", className = "" }: { p: number; color?: string; className?: string }) {
  return (
    <div className={`h-1.5 overflow-hidden rounded-full bg-white/[0.07] ${className}`}>
      <motion.div className={`h-full rounded-full ${color}`} initial={{ width: 0 }} whileInView={{ width: `${Math.min(100, p * 100)}%` }}
        viewport={{ once: true }} transition={{ duration: 0.9, ease }} />
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
        <motion.i key={i} title={t[x]} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.3 + i * 0.06, type: "spring", stiffness: 400, damping: 18 }}
          className={`grid h-[18px] w-[18px] place-items-center rounded-[5px] text-[9.5px] font-black not-italic ${c[x] || ""}`}>{x}</motion.i>
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
            <motion.div className="h-full rounded-full bg-cobalt-deep" initial={{ width: 0 }} whileInView={{ width: `${k.prob * 100}%` }} viewport={{ once: true }} transition={{ duration: 1, ease, delay: 0.2 }} />
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
        <motion.span animate={{ rotate: open ? 45 : 0 }} className="grid h-8 w-8 place-items-center rounded-full bg-white/5 text-[20px] text-chalk-2" aria-hidden="true">+</motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.35, ease }}>
            <div className="px-5 pb-5">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function SectionHead({ title, sub, action }: { title: string; sub?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
      <div><h2 className="text-[clamp(26px,3.6vw,38px)] font-extrabold leading-none">{title}</h2>{sub && <p className="mt-2 max-w-[58ch] text-chalk-2">{sub}</p>}</div>
      {action}
    </div>
  );
}

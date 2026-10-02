import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { BellOff, BellRing, Check, Clock, ExternalLink, Lock, RefreshCw, Share, Smartphone, SquarePlus } from "lucide-react";
import { Page, PageHeader } from "@/components/ui-pz";
import { ApiError, activar, avisosListos, current, desactivar, esLimite, isIOS, isStandalone, permission, probarLocal, register, registrar, supported } from "@/lib/push";

const WEB = "https://20-jesus-04.github.io/Pizarra/#avisos";

type Sync = "pendiente" | "ok" | "error" | "limite";
type Estado =
  | { k: "cargando" } | { k: "pronto" } | { k: "ios" } | { k: "no-soportado" } | { k: "no-disponible" }
  | { k: "denegado" } | { k: "inactivo" } | { k: "fallo"; limite: boolean; lleno?: boolean } | { k: "activo"; sync: Sync };
type Msg = { tone: "ok" | "err"; t: string } | null;

const btn = "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full px-5 py-3 text-[15px] font-bold transition disabled:cursor-not-allowed disabled:opacity-60";
const primary = `${btn} shine bg-gold text-night-900 shadow-[0_8px_30px_-12px_rgba(255,194,61,.8)]`;
const ghost = `${btn} border border-white/15 text-chalk hover:border-white/30 hover:bg-white/[0.04]`;

const ext = (href: string, children: ReactNode) => (
  <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold text-gold underline-offset-2 hover:underline">
    {children}<ExternalLink className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
  </a>
);

export default function Avisos() {
  const [s, setS] = useState<Estado>({ k: "cargando" });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<Msg>(null);
  const seq = useRef(0);
  const busyRef = useRef(false);
  const synced = useRef("");   // endpoint ya confirmado por el Worker en esta visita (evita re-sincronizar en cada vuelta)

  /** Mira en qué punto está este celular. Solo vale el resultado de la última revisión. */
  const check = useCallback(async () => {
    const n = ++seq.current;
    const set = (e: Estado) => { if (n === seq.current) setS(e); };
    if (!avisosListos()) return set({ k: "pronto" });
    if (isIOS() && !isStandalone()) return set({ k: "ios" });
    if (!supported()) return set({ k: "no-soportado" });
    if (!(await register())) return set({ k: "no-disponible" });
    if (permission() === "denied") return set({ k: "denegado" });
    const sub = await current();
    if (!sub) return set({ k: "inactivo" });
    if (synced.current === sub.endpoint) return set({ k: "activo", sync: "ok" });
    // ya estaba suscrito: re-sincroniza en silencio con el Worker (idempotente)
    set({ k: "activo", sync: "pendiente" });
    try {
      await registrar(sub);
      synced.current = sub.endpoint;
      set({ k: "activo", sync: "ok" });
    } catch (e) {
      set({ k: "activo", sync: esLimite(e) ? "limite" : "error" });
    }
  }, []);

  useEffect(() => {
    check();
    // al volver de los ajustes del celular, se revisa de nuevo
    const f = () => { if (document.visibilityState === "visible" && !busyRef.current) check(); };
    document.addEventListener("visibilitychange", f);
    return () => document.removeEventListener("visibilitychange", f);
  }, [check]);

  const run = (p: Promise<void>) => {
    seq.current++; busyRef.current = true; setBusy(true); setMsg(null);
    p.finally(() => { busyRef.current = false; setBusy(false); });
  };

  // activar() pide el permiso en su primera línea: debe llamarse directo desde el toque (iOS lo exige)
  const onActivar = () => run(activar().then(
    (sub) => { synced.current = sub.endpoint; setS({ k: "activo", sync: "ok" }); setMsg({ tone: "ok", t: "Listo. Te avisaremos antes de cada partido con fija." }); },
    (e: unknown) => {
      if (e instanceof ApiError) return setS({ k: "fallo", limite: esLimite(e), lleno: e.status === 503 && e.code === "lleno" });
      const m = e instanceof Error ? e.message : "";
      if (m === "denied") setS({ k: "denegado" });
      else if (m === "default") setMsg({ tone: "err", t: "No se dio el permiso. Toca otra vez «Activar avisos» y elige Permitir." });
      else setMsg({ tone: "err", t: "Este navegador no pudo activar los avisos. Inténtalo de nuevo en un momento." });
    }));

  const onSync = () => run((async () => {
    const sub = await current();
    if (!sub) { setS({ k: "inactivo" }); return; }
    try {
      await registrar(sub);
      synced.current = sub.endpoint;
      setS({ k: "activo", sync: "ok" });
      setMsg({ tone: "ok", t: "Listo, tu celular quedó registrado." });
    } catch (e) {
      setS({ k: "activo", sync: esLimite(e) ? "limite" : "error" });
    }
  })());

  const onProbar = () => run(probarLocal().then(
    () => setMsg({ tone: "ok", t: "Aviso de prueba enviado. Revisa tus notificaciones." }),
    () => setMsg({ tone: "err", t: "No se pudo mostrar la prueba. Revisa que las notificaciones estén permitidas." })));

  const onDesactivar = () => run(desactivar().then(
    (borrado) => {
      synced.current = "";
      setS({ k: "inactivo" });
      setMsg({ tone: "ok", t: borrado ? "Avisos desactivados. Borramos la dirección de este celular." : "Avisos desactivados en este celular. La dirección ya no sirve y se borrará sola." });
    },
    () => setMsg({ tone: "err", t: "No se pudo desactivar. Inténtalo de nuevo." })));

  return (
    <Page>
      <PageHeader eyebrow="Avisos de fijas" title="Avisos"
        sub={<><b className="text-chalk">Gratis, sin registrarte.</b> Te avisamos ~30 min antes de cada partido con fija. Desactívalos cuando quieras.</>} />

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-6">
        <section className="card p-5 sm:p-7" aria-labelledby="av-estado">
          <Panel s={s} busy={busy} onActivar={onActivar} onSync={onSync} onProbar={onProbar} onDesactivar={onDesactivar}
            onRevisar={() => { setMsg(null); check(); }} />
          <p role="status" aria-live="polite" className={`text-[14px] leading-relaxed ${msg ? "mt-4" : ""} ${msg?.tone === "err" ? "text-flare" : "text-turf"}`}>{msg?.t}</p>
        </section>

        <aside className="card p-5 sm:p-7" aria-labelledby="av-como">
          <h2 id="av-como" className="flex items-center gap-2.5 text-[20px] font-extrabold"><Clock className="h-5 w-5 shrink-0 text-gold" aria-hidden="true" />Cómo funciona</h2>
          <ol className="mt-4 grid gap-3.5 text-[14.5px] leading-relaxed text-chalk-2">
            <Paso n={1}>Toca <b className="text-chalk">Activar avisos</b> y elige <b className="text-chalk">Permitir</b>.</Paso>
            <Paso n={2}>Te llega una notificación ~30 min antes de cada partido con fija.</Paso>
            <Paso n={3}>Tócala y vas directo al partido.</Paso>
          </ol>
          <p className="mt-5 flex gap-2.5 rounded-xl bg-white/[0.04] p-3.5 text-[13px] leading-relaxed text-chalk-3 ring-1 ring-white/[0.07]">
            <Lock className="mt-0.5 h-4 w-4 shrink-0 text-cobalt" aria-hidden="true" />
            <span><b className="text-chalk-2">Privacidad:</b> guardamos solo la dirección técnica que tu navegador crea para recibir avisos, dos llaves para cifrarlos y la fecha, en un servidor de Cloudflare. Sin nombre, correo, IP ni ubicación. El aviso lo entrega el servicio de tu navegador (Google, Apple, Mozilla o Microsoft). Se borra al desactivar, o cuando ese servicio la da de baja.</span>
          </p>
        </aside>
      </div>
    </Page>
  );
}

function Paso({ n, children }: { n: number; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-gold-soft font-display text-[13.5px] font-black text-gold" aria-hidden="true">{n}</span>
      <span className="min-w-0 pt-0.5">{children}</span>
    </li>
  );
}

function Head({ icon, tone = "text-gold", title, children }: { icon: ReactNode; tone?: string; title: string; children?: ReactNode }) {
  return (
    <>
      <h2 id="av-estado" className="flex items-center gap-2.5 text-[22px] font-extrabold leading-tight"><span className={`shrink-0 ${tone}`} aria-hidden="true">{icon}</span>{title}</h2>
      {children && <div className="mt-2.5 max-w-[60ch] text-[15px] leading-relaxed text-chalk-2">{children}</div>}
    </>
  );
}

function Panel({ s, busy, onActivar, onSync, onProbar, onDesactivar, onRevisar }: {
  s: Estado; busy: boolean; onActivar: () => void; onSync: () => void; onProbar: () => void; onDesactivar: () => void; onRevisar: () => void;
}) {
  const ico = "h-6 w-6";
  switch (s.k) {
    case "cargando":
      return <Head icon={<BellRing className={ico} />} title="Revisando este celular…" />;

    case "pronto":
      return (
        <Head icon={<Clock className={ico} />} title="Los avisos se activan muy pronto">
          Estamos terminando de prepararlos. Vuelve pronto a esta página para activarlos con un toque.
        </Head>
      );

    case "ios":
      return (
        <>
          <Head icon={<Smartphone className={ico} />} title="Primero instala la app">
            En iPhone los avisos solo funcionan con CuchiFijas instalada y abierta desde su ícono (iOS 16.4 o superior).
          </Head>
          <ol className="mt-5 grid gap-3.5 text-[14.5px] leading-relaxed text-chalk-2">
            <Paso n={1}>Abre esta página en <b className="text-chalk">Safari</b>.</Paso>
            <Paso n={2}>Toca <b className="inline-flex items-center gap-1 text-chalk">Compartir <Share className="h-4 w-4" aria-hidden="true" /></b>.</Paso>
            <Paso n={3}>Elige <b className="inline-flex items-center gap-1 text-chalk">Agregar a pantalla de inicio <SquarePlus className="h-4 w-4" aria-hidden="true" /></b>.</Paso>
            <Paso n={4}>Abre CuchiFijas desde el ícono y entra a <b className="text-chalk">Avisos</b> (al final de la página).</Paso>
          </ol>
        </>
      );

    case "no-soportado":
      return (
        <Head icon={<BellOff className={ico} />} tone="text-flare" title="Este navegador no permite avisos">
          {isIOS()
            ? "Actualiza tu iPhone a iOS 16.4 o superior y vuelve a abrir la app desde su ícono."
            : "Usa Chrome, Edge o Firefox en Android o en la PC. En iPhone, instala la app desde Safari (iOS 16.4 o superior)."}
        </Head>
      );

    case "no-disponible":
      return (
        <Head icon={<BellOff className={ico} />} tone="text-flare" title="Aquí no se pueden activar">
          Esta vista (vista previa o archivo abierto en la PC) no permite avisos. Abre la {ext(WEB, "web de CuchiFijas")} o la app instalada.
        </Head>
      );

    case "denegado":
      return (
        <>
          <Head icon={<BellOff className={ico} />} tone="text-flare" title="Notificaciones bloqueadas">
            Este navegador las tiene bloqueadas para CuchiFijas. Reactívalas así y vuelve:
          </Head>
          <ul className="mt-4 grid gap-2.5 text-[14.5px] leading-relaxed text-chalk-2">
            <li><b className="text-chalk">Android:</b> toca el candado (o ⋮ → Configuración del sitio) → Notificaciones → Permitir. Si usas la app: mantén presionado su ícono → Información de la app → Notificaciones.</li>
            <li><b className="text-chalk">iPhone:</b> Ajustes → Notificaciones → CuchiFijas → Permitir notificaciones.</li>
            <li><b className="text-chalk">PC:</b> clic en el candado junto a la dirección → Notificaciones → Permitir.</li>
          </ul>
          <button type="button" onClick={onRevisar} className={`${ghost} mt-5`}>Ya lo cambié</button>
        </>
      );

    case "inactivo":
      return (
        <>
          <Head icon={<BellRing className={ico} />} title="Activa los avisos en este celular">
            Te pediremos permiso para mostrar notificaciones. Nada más.
          </Head>
          <button type="button" onClick={onActivar} disabled={busy} className={`${primary} mt-5 w-full sm:w-auto`}>
            <BellRing className="h-5 w-5" aria-hidden="true" />{busy ? "Activando…" : "Activar avisos"}
          </button>
        </>
      );

    case "fallo":
      return (
        <>
          <Head icon={<BellOff className={ico} />} tone="text-flare" title="No pudimos registrar tu celular">
            {s.limite ? "Hubo demasiados intentos seguidos. Espera unos minutos y vuelve a intentar."
              : s.lleno ? "Por ahora llegamos al máximo de celulares registrados. Vuelve a intentarlo más adelante."
              : "Intenta de nuevo. Si sigue fallando, revisa tu conexión."}
          </Head>
          <button type="button" onClick={onActivar} disabled={busy} className={`${primary} mt-5 w-full sm:w-auto`}>
            <RefreshCw className="h-5 w-5" aria-hidden="true" />{busy ? "Reintentando…" : "Reintentar"}
          </button>
        </>
      );

    case "activo":
      return (
        <>
          <Head icon={<Check className={ico} />} tone="text-turf" title="Avisos activados en este celular">
            Te avisaremos ~30 min antes de cada partido con fija.
          </Head>
          {(s.sync === "error" || s.sync === "limite") && (
            <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl bg-flare/10 px-4 py-3 text-[14px] leading-relaxed text-chalk-2 ring-1 ring-flare/25">
              <span className="min-w-[12rem] flex-1">{s.sync === "limite" ? "Demasiados intentos seguidos. Reintenta en unos minutos." : "No pudimos confirmar tu registro con el servidor."}</span>
              <button type="button" onClick={onSync} disabled={busy} className="inline-flex shrink-0 items-center gap-1.5 font-bold text-gold hover:underline disabled:opacity-60">
                <RefreshCw className="h-4 w-4" aria-hidden="true" />Reintentar
              </button>
            </div>
          )}
          <div className="mt-5 flex flex-wrap gap-2">
            <button type="button" onClick={onProbar} disabled={busy} className={`${ghost} grow sm:grow-0`}>Probar en este celular</button>
            <button type="button" onClick={onDesactivar} disabled={busy} className={`${btn} grow text-flare hover:bg-flare/10 sm:grow-0`}>Desactivar</button>
          </div>
        </>
      );
  }
}

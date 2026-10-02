/* Avisos push (Web Push con VAPID), públicos: cualquier visitante se suscribe con un toque.
   La suscripción se registra en el Worker de avisos (AVISOS_URL). No se guarda nada en el navegador
   y no se piden datos personales: solo viaja la dirección técnica que crea el navegador. */

/** Base del Worker de avisos, sin "/" final. Vacía = avisos aún no publicados (la página dice "muy pronto").
 *  ¡Debe coincidir con AVISOS_URL de web/sw.js! */
export const AVISOS_URL = "https://cuchifijas-avisos.cuchifijas.workers.dev";

/** Clave pública VAPID (applicationServerKey). ¡Debe coincidir con web/sw.js! */
export const VAPID_PUBLIC_KEY = "BOOctT0QJA1ufLFa8p-6HdbM6wY05AC8dV6qFdS66UCnED4JbvmfV81WJk8fy9KMePKg9iSg3i-DlpC6InAcYms";

export const avisosListos = () => AVISOS_URL.trim() !== "";

/** base64url → bytes (lo que pide pushManager.subscribe). */
export function b64urlToBytes(s: string): Uint8Array<ArrayBuffer> {
  const b64 = (s + "=".repeat((4 - (s.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

const KEY = b64urlToBytes(VAPID_PUBLIC_KEY);

function sameKey(buf: ArrayBuffer | null | undefined) {
  if (!buf) return true;   // el navegador no la expone: se asume la nuestra
  const a = new Uint8Array(buf);
  return a.length === KEY.length && a.every((b, i) => b === KEY[i]);
}

/** El navegador soporta todo lo necesario. */
export const supported = () =>
  typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

/** iPhone/iPad (los iPad nuevos se presentan como Mac con pantalla táctil). */
export const isIOS = () =>
  /iPad|iPhone|iPod/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);

/** Abierta como app instalada (desde el ícono de la pantalla de inicio). */
export const isStandalone = () =>
  matchMedia("(display-mode: standalone)").matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;

export const permission = (): NotificationPermission | "unsupported" =>
  "Notification" in window ? Notification.permission : "unsupported";

/** Solo en http(s): en file:// o en el artefacto de claude.ai no hay service worker posible. */
const canRegister = () => /^https?:$/.test(location.protocol) && "serviceWorker" in navigator;

/** Registra sw.js (junto a la página). Devuelve null si aquí no se puede, sin lanzar error. */
export async function register(): Promise<ServiceWorkerRegistration | null> {
  if (!canRegister()) return null;
  try {
    // URL resuelta contra la página (sw.js va junto a index.html en docs/); Parcel no debe empaquetarlo
    const url = new URL("sw.js", location.href).href;
    return await navigator.serviceWorker.register(url, { scope: "./" });
  } catch {
    return null;
  }
}

/** Registro con un service worker activo (pushManager.subscribe lo exige). */
async function activeRegistration(): Promise<ServiceWorkerRegistration> {
  const reg = await register();
  if (!reg) throw new Error("no-sw");
  if (reg.active) return reg;
  const ready = navigator.serviceWorker.ready;
  const timeout = new Promise<never>((_, rej) => setTimeout(() => rej(new Error("sw-lento")), 10000));
  return Promise.race([ready, timeout]);
}

/** Suscripción actual de este navegador, o null. */
export async function current(): Promise<PushSubscription | null> {
  if (!canRegister() || !("PushManager" in window)) return null;
  try {
    const reg = await navigator.serviceWorker.getRegistration("./");
    return (await reg?.pushManager.getSubscription()) ?? null;
  } catch {
    return null;
  }
}

/* ---------------------------------------------------------------- Worker de avisos */

/** Error de la API: status 0 = sin conexión o tiempo agotado. */
export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string) {
    super(code);
    this.status = status;
    this.code = code;
  }
}

export const esLimite = (e: unknown) => e instanceof ApiError && (e.status === 429 || e.code === "demasiados_intentos");

async function post(path: string, body: unknown): Promise<void> {
  if (!avisosListos()) throw new ApiError(0, "sin_servidor");
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 10_000);
  let r: Response;
  try {
    r = await fetch(`${AVISOS_URL.trim().replace(/\/+$/, "")}${path}`, {
      method: "POST", mode: "cors", credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ctrl.signal,
    });
  } catch {
    throw new ApiError(0, "red");
  } finally {
    clearTimeout(timer);
  }
  if (!r.ok) {
    let code = "";
    try { const j = await r.json(); if (j && typeof j.error === "string") code = j.error; } catch { /* sin cuerpo JSON */ }
    throw new ApiError(r.status, code || `http_${r.status}`);
  }
}

/** Registra (o re-sincroniza) la suscripción en el Worker. Idempotente. */
export const registrar = (sub: PushSubscription) => post("/v1/suscribir", sub.toJSON());

/* ---------------------------------------------------------------- acciones */

/** Pide permiso y suscribe este navegador (solo local). Llamar directo desde un toque del usuario (iOS lo exige).
 *  Lanza Error("denied") o Error("default") si no se concede el permiso. */
export async function subscribe(): Promise<PushSubscription> {
  const perm = await Notification.requestPermission();
  if (perm !== "granted") throw new Error(perm);
  const reg = await activeRegistration();
  const old = await reg.pushManager.getSubscription();
  if (old) {
    if (sameKey(old.options?.applicationServerKey)) return old;
    await old.unsubscribe();   // suscripción hecha con otra clave: no serviría
  }
  return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: KEY });
}

/** Suscribe y registra en el Worker. Si el registro falla, la suscripción local queda para reintentar. */
export async function activar(): Promise<PushSubscription> {
  const sub = await subscribe();
  await registrar(sub);
  return sub;
}

/** Desactiva en este navegador y pide al Worker que borre la dirección.
 *  Si el Worker no responde, igual queda desactivado aquí. Devuelve si el Worker confirmó el borrado. */
export async function desactivar(): Promise<boolean> {
  const sub = await current();
  if (!sub) return true;
  const endpoint = sub.endpoint;
  await sub.unsubscribe();
  try {
    await post("/v1/desuscribir", { endpoint });
    return true;
  } catch {
    return false;
  }
}

/** Notificación de prueba en este celular, sin servidor. */
export async function probarLocal(): Promise<void> {
  const reg = await activeRegistration();
  await reg.showNotification("CuchiFijas · prueba", {
    body: "Así te llegará el aviso ~30 min antes de cada partido con fija.",
    icon: "icon-192.png",
    badge: "badge-96.png",
    tag: "prueba",
    lang: "es",
    data: { url: "./#fijas" },
  });
}

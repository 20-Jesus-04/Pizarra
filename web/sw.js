/* CuchiFijas: service worker solo para los avisos push (Web Push con VAPID).
   Sin handler de fetch y sin caché a propósito: los datos cambian a diario y no hay que servir versiones viejas.
   build.py::write_web lo copia a docs/sw.js. */

/* ¡Deben coincidir con AVISOS_URL y VAPID_PUBLIC_KEY de web-src/src/lib/push.ts! Vacía = avisos aún no publicados. */
const AVISOS_URL = "https://cuchifijas-avisos.cuchifijas.workers.dev";
const VAPID_PUBLIC_KEY = "BOOctT0QJA1ufLFa8p-6HdbM6wY05AC8dV6qFdS66UCnED4JbvmfV81WJk8fy9KMePKg9iSg3i-DlpC6InAcYms";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

/* Payload esperado: {"title": str, "body": str, "url": "./#p.<id>", "tag": "fija-<id>"}.
   Si no llega JSON, el texto se usa como cuerpo. */
self.addEventListener("push", (event) => {
  let d = {};
  if (event.data) {
    try { d = event.data.json(); } catch (_) { d = { body: event.data.text() }; }
  }
  if (!d || typeof d !== "object") d = { body: String(d ?? "") };
  const str = (v) => (typeof v === "string" ? v : "");
  const options = {
    body: str(d.body),
    icon: "icon-192.png",
    badge: "badge-96.png",   // silueta blanca sobre transparente: Android la usa en la barra de estado
    lang: "es",
    data: { url: str(d.url) || "./" },
  };
  if (str(d.tag)) options.tag = d.tag;
  event.waitUntil(self.registration.showNotification(str(d.title) || "CuchiFijas", options));
});

/* Solo se abren direcciones del mismo origen y dentro del scope de la app; cualquier otra cosa abre el inicio. */
function safeUrl(raw) {
  const scope = self.registration.scope;
  try {
    const u = new URL(typeof raw === "string" ? raw : "./", scope);
    if (u.origin === self.location.origin && u.href.startsWith(scope)) return u.href;
  } catch (_) { /* URL inválida: se usa el scope */ }
  return scope;
}

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = safeUrl(event.notification.data && event.notification.data.url);
  const scope = self.registration.scope;
  event.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const mine = wins.filter((c) => c.url.startsWith(scope));
    const win = mine.find((c) => c.focused) || mine.find((c) => c.visibilityState === "visible") || mine[0];
    if (win) {
      try {
        const focused = await win.focus();
        if (focused.url !== url) await focused.navigate(url);
        return;
      } catch (_) { /* no se pudo enfocar o navegar (ventana no controlada): se abre una nueva */ }
    }
    if (self.clients.openWindow) await self.clients.openWindow(url);
  })());
});

/* ---- el navegador renovó (o invalidó) la suscripción: se avisa al Worker para no perder al usuario ---- */

function b64urlToBytes(s) {
  const b64 = (s + "=".repeat((4 - (s.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function post(path, body) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 10000);
  try {
    const r = await fetch(AVISOS_URL.replace(/\/+$/, "") + path, {
      method: "POST", mode: "cors", credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ctrl.signal,
    });
    return r.ok;
  } finally {
    clearTimeout(timer);
  }
}

self.addEventListener("pushsubscriptionchange", (event) => {
  if (!AVISOS_URL) return;
  event.waitUntil((async () => {
    const old = event.oldSubscription || null;
    let sub = event.newSubscription || null;
    try {
      if (!sub) {
        sub = await self.registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64urlToBytes(VAPID_PUBLIC_KEY) });
      }
    } catch (_) { sub = null; /* sin permiso o sin servicio push: solo se da de baja la vieja */ }
    await Promise.allSettled([
      sub ? post("/v1/suscribir", sub.toJSON()) : null,
      old && (!sub || old.endpoint !== sub.endpoint) ? post("/v1/desuscribir", { endpoint: old.endpoint }) : null,
    ]);
  })());
});

/**
 * CuchiFijas · avisos públicos (Cloudflare Worker + D1).
 *
 * Públicas (con CORS solo para ALLOWED_ORIGINS y rate limiting por IP, /64 en IPv6):
 *   POST /v1/suscribir     subscription.toJSON()      201 {"ok":true}
 *   POST /v1/desuscribir   {"endpoint": "..."}        200 {"ok":true} siempre (no es un oráculo)
 *   GET  /v1/salud                                    200 {"ok":true}
 * Admin (Authorization: Bearer <AVISOS_TOKEN>, sin CORS):
 *   GET  /v1/suscripciones?cursor=   {"suscripciones":[{endpoint, keys:{p256dh, auth}}], "cursor": null | "..."}
 *   POST /v1/eliminar      {"endpoints":[...]}        {"ok":true,"eliminadas":n}
 *   POST /v1/marcar        {"clave":"<id>@<inicio>"}  {"ok":true,"nuevo":true|false}  (aviso enviado como máximo una vez)
 *
 * No guarda IP, user agent ni nada personal. La IP solo sirve de clave efímera del rate limiter.
 * Los errores son genéricos y nunca repiten lo que llegó.
 */

const MAX_CUERPO = 4096;            // bytes, rutas públicas y /v1/marcar
const MAX_CUERPO_ADMIN = 1 << 20;   // bytes, /v1/eliminar
const MAX_ENDPOINT = 1024;          // caracteres
const MAX_ELIMINAR = 1000;          // endpoints por llamada a /v1/eliminar
const PAGINA = 1000;                // suscripciones por página
const LOTE_SQL = 90;                // D1 admite hasta 100 parámetros por consulta
const TOPE_POR_DEFECTO = 20000;
const RETENCION_MARCAS_MS = 3 * 24 * 3600 * 1000;

// Servicios push reales: host exacto y forma del path (tokens de al menos 16 caracteres).
const TOKEN = "[A-Za-z0-9_.~%=-]{16,}";
const SERVICIOS_PUSH = [
  // Chrome, Opera, Brave, Samsung Internet (FCM): /fcm/send/<token> o /wp/<token>
  { host: /^fcm\.googleapis\.com$/, ruta: new RegExp(`^/(?:fcm/send|wp)/[A-Za-z0-9_.~%=:-]{16,}$`), query: null },
  // Firefox (autopush): /wpush/v1/<token> o /wpush/v2/<token>
  { host: /^updates\.push\.services\.mozilla\.com$/, ruta: new RegExp(`^/wpush/v[12]/${TOKEN}$`), query: null },
  // Safari (Apple): /<token>
  { host: /^web\.push\.apple\.com$/, ruta: new RegExp(`^/${TOKEN}$`), query: null },
  // Edge (WNS): /w/?token=<token>
  { host: /^wns2-[a-z0-9-]+\.notify\.windows\.com$/, ruta: /^\/w\/$/, query: /^\?token=[A-Za-z0-9_.~%+\/=-]{16,}$/ },
];

const RE_CLAVE_AVISO = /^[A-Za-z0-9_.:-]{1,64}@\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$/;

const RUTAS_PUBLICAS = { "/v1/suscribir": "POST", "/v1/desuscribir": "POST", "/v1/salud": "GET" };
const RUTAS_ADMIN = { "/v1/suscripciones": "GET", "/v1/eliminar": "POST", "/v1/marcar": "POST" };

const CABECERAS_BASE = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
  "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
  "Referrer-Policy": "no-referrer",
};

// Alta con tope atómico. Si falta la fila del contador, la comparación da NULL: se trata como lleno.
// Una renovación solo escribe (y toca `actualizado`) si cambiaron las llaves.
const SQL_UPSERT = `
INSERT INTO suscripciones (id, endpoint, p256dh, auth, creado, actualizado)
SELECT ?1, ?2, ?3, ?4, ?5, ?5
WHERE EXISTS (SELECT 1 FROM suscripciones WHERE id = ?1)
   OR (SELECT valor FROM contadores WHERE nombre = 'suscripciones') < ?6
ON CONFLICT (id) DO UPDATE SET
  p256dh = excluded.p256dh, auth = excluded.auth, actualizado = excluded.actualizado
WHERE suscripciones.p256dh <> excluded.p256dh OR suscripciones.auth <> excluded.auth
RETURNING id`;

class Falla extends Error {
  constructor(estado, codigo) {
    super(codigo);
    this.estado = estado;
    this.codigo = codigo;
  }
}

function responder(estado, cuerpo, extra = {}) {
  const cabeceras = new Headers(CABECERAS_BASE);
  for (const [k, v] of Object.entries(extra)) cabeceras.set(k, v);
  if (cuerpo === null) cabeceras.delete("Content-Type");
  return new Response(cuerpo === null ? null : JSON.stringify(cuerpo), { status: estado, headers: cabeceras });
}

const fallo = (estado, codigo, extra) => responder(estado, { ok: false, error: codigo }, extra);

export default {
  async fetch(request, env) {
    try {
      return await atender(request, env);
    } catch (e) {
      console.error("error interno:", e && e.name); // sin datos de la petición
      return fallo(500, "error_interno");
    }
  },
};

async function atender(request, env) {
  const ruta = new URL(request.url).pathname;
  const metodo = request.method;

  // ---- admin: sin CORS
  if (Object.hasOwn(RUTAS_ADMIN, ruta)) {
    if (metodo !== RUTAS_ADMIN[ruta]) return fallo(405, "metodo_no_permitido", { Allow: RUTAS_ADMIN[ruta] });
    if (!(await autorizado(request, env))) return fallo(401, "no_autorizado", { "WWW-Authenticate": "Bearer" });
    try {
      if (ruta === "/v1/suscripciones") return await listar(request, env);
      if (ruta === "/v1/eliminar") return await eliminar(request, env);
      return await marcar(request, env);
    } catch (e) {
      if (e instanceof Falla) return fallo(e.estado, e.codigo);
      throw e;
    }
  }

  if (!Object.hasOwn(RUTAS_PUBLICAS, ruta)) return fallo(404, "no_encontrado");

  // ---- públicas
  const permitido = RUTAS_PUBLICAS[ruta];
  const origen = request.headers.get("Origin");
  const origenOk = origen !== null && origenesPermitidos(env).has(origen);
  const cors = origenOk ? { "Access-Control-Allow-Origin": origen, Vary: "Origin" } : { Vary: "Origin" };

  if (metodo === "OPTIONS") {
    if (!origenOk || request.headers.get("Access-Control-Request-Method") !== permitido) {
      return fallo(403, "origen_no_permitido", { Vary: "Origin" });
    }
    return responder(204, null, {
      ...cors,
      "Access-Control-Allow-Methods": `${permitido}, OPTIONS`,
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
      Vary: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers",
    });
  }
  if (metodo !== permitido) return fallo(405, "metodo_no_permitido", { ...cors, Allow: `${permitido}, OPTIONS` });

  const limite = await revisarLimite(request, env);
  if (limite === "excedido") return fallo(429, "demasiados_intentos", { ...cors, "Retry-After": "60" });
  if (limite === "error" && ruta === "/v1/suscribir") {
    // Sin limitador no se aceptan altas (falla cerrado); salud y desuscribir siguen.
    return fallo(503, "no_disponible", { ...cors, "Retry-After": "60" });
  }

  if (ruta === "/v1/salud") return responder(200, { ok: true }, cors);

  if (ruta === "/v1/desuscribir") {
    // Siempre 200: no revela si el endpoint existía ni si el cuerpo era válido.
    if (origenOk) {
      try {
        await desuscribir(request, env);
      } catch (e) {
        if (!(e instanceof Falla)) throw e;
      }
    }
    return responder(200, { ok: true }, cors);
  }

  // /v1/suscribir
  try {
    if (!origenOk) throw new Falla(403, "origen_no_permitido");
    await suscribir(request, env);
    return responder(201, { ok: true }, cors);
  } catch (e) {
    if (e instanceof Falla) return fallo(e.estado, e.codigo, cors);
    throw e;
  }
}

// ------------------------------------------------------------------ rutas
async function suscribir(request, env) {
  const s = await validarSuscripcion(await leerJson(request, MAX_CUERPO));
  if (!s) throw new Falla(400, "datos_invalidos");
  const id = await sha256Hex(s.endpoint);
  const ahora = new Date().toISOString();
  const { results } = await env.DB.prepare(SQL_UPSERT).bind(id, s.endpoint, s.p256dh, s.auth, ahora, tope(env)).all();
  if (results.length) return; // nueva o con llaves nuevas
  // Nada escrito: o ya estaba con las mismas llaves (ok), o era nueva y no hay cupo.
  const ya = await env.DB.prepare("SELECT 1 AS x FROM suscripciones WHERE id = ?1").bind(id).first();
  if (!ya) throw new Falla(503, "lleno");
}

async function desuscribir(request, env) {
  const d = await leerJson(request, MAX_CUERPO);
  const endpoint = normalizarEndpoint(d && typeof d === "object" ? d.endpoint : null, false);
  if (!endpoint) return;
  await env.DB.prepare("DELETE FROM suscripciones WHERE id = ?1").bind(await sha256Hex(endpoint)).run();
}

async function listar(request, env) {
  const cursor = new URL(request.url).searchParams.get("cursor");
  let desde = 0;
  if (cursor !== null && cursor !== "") {
    if (!/^\d{1,15}$/.test(cursor)) throw new Falla(400, "datos_invalidos");
    desde = Number(cursor);
  }
  const { results } = await env.DB.prepare(
    "SELECT rowid AS fila, endpoint, p256dh, auth FROM suscripciones WHERE rowid > ?1 ORDER BY rowid LIMIT ?2",
  ).bind(desde, PAGINA + 1).all();
  const hayMas = results.length > PAGINA;
  const pagina = hayMas ? results.slice(0, PAGINA) : results;
  return responder(200, {
    suscripciones: pagina.map((f) => ({ endpoint: f.endpoint, keys: { p256dh: f.p256dh, auth: f.auth } })),
    cursor: hayMas ? String(pagina[pagina.length - 1].fila) : null,
  });
}

async function eliminar(request, env) {
  const d = await leerJson(request, MAX_CUERPO_ADMIN);
  const lista = d && typeof d === "object" && Array.isArray(d.endpoints) ? d.endpoints : null;
  if (!lista || lista.length > MAX_ELIMINAR) throw new Falla(400, "datos_invalidos");
  const ids = new Set();
  for (const e of lista) {
    const endpoint = normalizarEndpoint(e, false); // sin allowlist: se puede borrar todo lo guardado
    if (endpoint) ids.add(await sha256Hex(endpoint));
  }
  const todos = [...ids];
  let eliminadas = 0;
  for (let i = 0; i < todos.length; i += LOTE_SQL) {
    const lote = todos.slice(i, i + LOTE_SQL);
    const marcas = lote.map((_, j) => `?${j + 1}`).join(",");
    // RETURNING y no meta.changes: D1 suma ahí también las filas que tocan los triggers del contador.
    const { results } = await env.DB.prepare(`DELETE FROM suscripciones WHERE id IN (${marcas}) RETURNING id`)
      .bind(...lote).all();
    eliminadas += results.length;
  }
  return responder(200, { ok: true, eliminadas });
}

/** Registra que el aviso <id_partido>@<inicio> se va a enviar. nuevo=false: ya lo envió otra corrida. */
async function marcar(request, env) {
  const d = await leerJson(request, MAX_CUERPO);
  const clave = d && typeof d === "object" ? d.clave : null;
  if (typeof clave !== "string" || !RE_CLAVE_AVISO.test(clave)) throw new Falla(400, "datos_invalidos");
  const ahora = Date.now();
  const [, alta] = await env.DB.batch([
    env.DB.prepare("DELETE FROM enviados WHERE creado < ?1").bind(ahora - RETENCION_MARCAS_MS),
    env.DB.prepare("INSERT INTO enviados (clave, creado) VALUES (?1, ?2) ON CONFLICT (clave) DO NOTHING RETURNING clave")
      .bind(clave, ahora),
  ]);
  return responder(200, { ok: true, nuevo: alta.results.length === 1 });
}

// ------------------------------------------------------------- validación
async function leerJson(request, maximo) {
  const tipo = (request.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
  if (tipo !== "application/json") throw new Falla(400, "datos_invalidos");
  const declarado = Number(request.headers.get("Content-Length"));
  if (Number.isFinite(declarado) && declarado > maximo) throw new Falla(413, "muy_grande");
  if (!request.body) throw new Falla(400, "datos_invalidos");

  // Se lee con límite: Content-Length puede faltar (chunked) o mentir.
  const lector = request.body.getReader();
  const trozos = [];
  let total = 0;
  for (;;) {
    const { done, value } = await lector.read();
    if (done) break;
    total += value.byteLength;
    if (total > maximo) {
      await lector.cancel().catch(() => {});
      throw new Falla(413, "muy_grande");
    }
    trozos.push(value);
  }
  const bytes = new Uint8Array(total);
  let i = 0;
  for (const t of trozos) {
    bytes.set(t, i);
    i += t.byteLength;
  }
  try {
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    throw new Falla(400, "datos_invalidos");
  }
}

function servicioPush(u) {
  return SERVICIOS_PUSH.some((s) => s.host.test(u.hostname) && s.ruta.test(u.pathname)
    && (s.query ? s.query.test(u.search) : u.search === ""));
}

/** Endpoint https en forma canónica (con `estricto`, además de un servicio push real); si no, null. */
function normalizarEndpoint(valor, estricto = true) {
  if (typeof valor !== "string" || valor.length === 0 || valor.length > MAX_ENDPOINT) return null;
  let u;
  try {
    u = new URL(valor);
  } catch {
    return null;
  }
  if (u.protocol !== "https:" || u.username || u.password || u.port !== "") return null;
  u.hash = "";
  if (estricto && !servicioPush(u)) return null;
  return u.href.length <= MAX_ENDPOINT ? u.href : null;
}

/** base64url (sin relleno) que decodifica a exactamente `largo` bytes. */
function base64url(valor, largo) {
  if (typeof valor !== "string") return null;
  const texto = valor.replace(/=+$/, "");
  if (texto.length !== Math.ceil((largo * 4) / 3) || !/^[A-Za-z0-9_-]+$/.test(texto)) return null;
  let binario;
  try {
    binario = atob(texto.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (texto.length % 4)) % 4));
  } catch {
    return null;
  }
  if (binario.length !== largo) return null;
  return { texto, bytes: Uint8Array.from(binario, (c) => c.charCodeAt(0)) };
}

async function validarSuscripcion(d) {
  if (!d || typeof d !== "object" || Array.isArray(d)) return null;
  const endpoint = normalizarEndpoint(d.endpoint);
  const k = d.keys;
  if (!endpoint || !k || typeof k !== "object" || Array.isArray(k)) return null;
  const p256dh = base64url(k.p256dh, 65);
  const auth = base64url(k.auth, 16);
  if (!p256dh || !auth || p256dh.bytes[0] !== 0x04) return null;
  try { // que sea un punto válido de P-256, no solo 65 bytes que empiezan en 0x04
    await crypto.subtle.importKey("raw", p256dh.bytes, { name: "ECDH", namedCurve: "P-256" }, false, []);
  } catch {
    return null;
  }
  return { endpoint, p256dh: p256dh.texto, auth: auth.texto };
}

// --------------------------------------------------------------- utilidades
function origenesPermitidos(env) {
  return new Set(String(env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean));
}

function tope(env) {
  const n = Number.parseInt(env.MAX_SUSCRIPCIONES, 10);
  return Number.isFinite(n) && n > 0 ? n : TOPE_POR_DEFECTO;
}

/** Clave del limitador: la IPv4 tal cual; en IPv6, el prefijo /64 (un cliente suele tener el /64 entero). */
function claveLimite(ip) {
  if (!ip) return "sin-ip";
  if (!ip.includes(":")) return ip;
  let s = ip.trim().toLowerCase().split("%")[0];
  const v4 = /^(.*:)(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(s);
  if (v4) {
    const [a, b, c, d] = v4.slice(2).map(Number);
    s = `${v4[1]}${((a << 8) | b).toString(16)}:${((c << 8) | d).toString(16)}`;
  }
  const partes = s.split("::");
  if (partes.length > 2) return `v6:${s}`;
  const cabeza = partes[0] ? partes[0].split(":") : [];
  const cola = partes.length === 2 && partes[1] ? partes[1].split(":") : [];
  const relleno = partes.length === 2 ? 8 - cabeza.length - cola.length : 0;
  if (relleno < 0) return `v6:${s}`;
  const grupos = [...cabeza, ...Array(relleno).fill("0"), ...cola];
  if (grupos.length !== 8 || grupos.some((g) => !/^[0-9a-f]{1,4}$/.test(g))) return `v6:${s}`;
  const n = grupos.map((g) => parseInt(g, 16));
  if (n.slice(0, 5).every((x) => x === 0) && n[5] === 0xffff) { // IPv4 mapeada (::ffff:a.b.c.d)
    return `${n[6] >> 8}.${n[6] & 255}.${n[7] >> 8}.${n[7] & 255}`;
  }
  return `v6:${grupos.slice(0, 4).map((g) => g.padStart(4, "0")).join(":")}::/64`;
}

/** "ok", "excedido" o "error" (sin binding o el limitador falló). */
async function revisarLimite(request, env) {
  try {
    if (!env.LIMITE || typeof env.LIMITE.limit !== "function") throw new TypeError("sin binding LIMITE");
    const { success } = await env.LIMITE.limit({ key: claveLimite(request.headers.get("CF-Connecting-IP")) });
    return success ? "ok" : "excedido";
  } catch (e) {
    console.error("ratelimit:", e && e.name);
    return "error";
  }
}

async function sha256(texto) {
  return crypto.subtle.digest("SHA-256", new TextEncoder().encode(texto));
}

async function sha256Hex(texto) {
  return [...new Uint8Array(await sha256(texto))].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Bearer token comparado en tiempo constante (se comparan los SHA-256, que siempre miden 32 bytes). */
async function autorizado(request, env) {
  const esperado = typeof env.AVISOS_TOKEN === "string" ? env.AVISOS_TOKEN : "";
  const m = /^Bearer[ ]+(\S+)[ ]*$/.exec(request.headers.get("Authorization") || "");
  const dado = m ? m[1] : "";
  const [a, b] = await Promise.all([sha256(dado), sha256(esperado)]);
  const iguales = crypto.subtle.timingSafeEqual(a, b);
  return iguales && esperado.length >= 32 && dado.length > 0; // sin token configurado, nadie entra
}

"""Avisos push de CuchiFijas: unos 30 min antes de cada partido con fija.

Lee docs/data.json (fijas.lista), elige los partidos con fija que empiezan dentro
de los próximos VENTANA_MIN minutos y manda un Web Push (VAPID) a cada suscripción.
Las suscripciones salen de dos fuentes, que se unen sin repetir:
  - el Worker público de avisos (worker/): AVISOS_URL + AVISOS_TOKEN, paginando;
  - el secret PUSH_SUBSCRIPTIONS (opcional; los celulares del dueño).

Con el Worker, cada aviso se envía como máximo una vez: primero se bajan las
suscripciones (si falla, no se hace nada y se reintenta en la próxima corrida),
luego se marca el aviso en D1 (/v1/marcar; si ya estaba marcado, se salta) y
recién entonces se envía. Sin Worker, lo ya avisado queda en un archivo local
(--estado), solo para desarrollo.

Las suscripciones que el servicio push da por caducadas (404/410) se borran del
Worker; las que da por inválidas (400, o un host que no existe en DNS) también,
pero solo si en la corrida llegó al menos la mitad de los envíos. Un 403 nunca
borra nada (suele ser una VAPID mal configurada).

    python -m pronosticos.notificar                       # envía lo que toque ahora
    python -m pronosticos.notificar --dry-run             # muestra sin enviar ni marcar
    python -m pronosticos.notificar --dry-run --ahora 2026-10-01T13:25Z
    python -m pronosticos.notificar --prueba              # aviso de prueba a PUSH_SUBSCRIPTIONS

Entorno: VAPID_PRIVATE_KEY (clave P-256 cruda de 32 bytes en base64url);
AVISOS_URL y AVISOS_TOKEN (Worker); PUSH_SUBSCRIPTIONS (arreglo JSON de
PushSubscription.toJSON(); también una sola, o varias pegadas una tras otra
separadas por coma o salto de línea); PRUEBA=true (igual que --prueba).
Solo usa la biblioteca estándar y pywebpush (con sus dependencias), que se
importa al enviar para que --dry-run funcione sin ella.

Nunca imprime un endpoint completo (es una URL-capacidad: quien la tiene puede
mandar avisos a ese celular), las llaves ni el token.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import sys
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import quote, unquote, urlsplit

VENTANA_MIN = 40        # avisa si el partido empieza dentro de 0..VENTANA_MIN minutos (el cron corre cada 10)
RETENCION_DIAS = 3      # archivo local: olvida los avisos enviados hace más de esto
TTL_MIN = 60            # segundos: TTL mínimo de un aviso de partido
TTL_PRUEBA = 600        # segundos: el aviso de prueba no sirve de nada horas después
TIMEOUT = 20            # segundos por envío push
HILOS = 16              # envíos push en paralelo (una requests.Session por hilo)
MAX_CUERPO = 1200       # caracteres: el payload cifrado no puede pasar de 4 KB
TIMEOUT_WORKER = 15     # segundos por petición al Worker
MAX_PAGINAS = 100       # páginas de 1000 suscripciones (el Worker tiene un tope de 20 000)
MAX_RESPUESTA = 4 << 20  # bytes por respuesta del Worker
LOTE_ELIMINAR = 500     # endpoints por llamada a /v1/eliminar (el Worker acepta hasta 1000)
MAX_AVISOS_LOG = 20     # warnings por envío; el resto se resume
TASA_MIN_BORRADO = 0.5  # las inválidas (400/DNS) solo se borran si llegó al menos esta fracción de envíos

LIMA = timezone(timedelta(hours=-5))  # Perú: UTC−5, sin horario de verano
VAPID_SUB = "https://20-jesus-04.github.io"
VAPID_PUBLICA = "BOOctT0QJA1ufLFa8p-6HdbM6wY05AC8dV6qFdS66UCnED4JbvmfV81WJk8fy9KMePKg9iSg3i-DlpC6InAcYms"
DATOS = "docs/data.json"
ESTADO = ".avisos/enviados.json"
HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}

# La misma allowlist que el Worker (worker/src/index.js): host exacto y forma del path.
_TOKEN = r"[A-Za-z0-9_.~%=-]{16,}"
SERVICIOS_PUSH = [
    # Chrome, Opera, Brave, Samsung Internet (FCM)
    (re.compile(r"fcm\.googleapis\.com"), re.compile(r"/(?:fcm/send|wp)/[A-Za-z0-9_.~%=:-]{16,}"), None),
    # Firefox (autopush)
    (re.compile(r"updates\.push\.services\.mozilla\.com"), re.compile(r"/wpush/v[12]/" + _TOKEN), None),
    # Safari (Apple)
    (re.compile(r"web\.push\.apple\.com"), re.compile(r"/" + _TOKEN), None),
    # Edge (WNS)
    (re.compile(r"wns2-[a-z0-9-]+\.notify\.windows\.com"), re.compile(r"/w/"),
     re.compile(r"token=[A-Za-z0-9_.~%+/=-]{16,}")),
]

# Igual que prettyAlt() de web-src/src/lib/data.ts, para que el aviso diga lo mismo que la web.
_PICKS_WEB = {
    "Doble oportunidad 1X (local o empate)": "{l} o empate",
    "Doble oportunidad X2 (visita o empate)": "{v} o empate",
    "Doble oportunidad 12 (no hay empate)": "Cualquiera gana (sin empate)",
    "Empate no apuesta: local": "{l} (si empata, te devuelven)",
    "Empate no apuesta: visita": "{v} (si empata, te devuelven)",
    "Gana el local": "Gana {l}",
    "Gana la visita": "Gana {v}",
    "Hándicap asiático local -1": "{l} gana por 2 o más",
    "Hándicap asiático visita -1": "{v} gana por 2 o más",
    "Local gana por 2 o más": "{l} gana por 2 o más",
    "Visita gana por 2 o más": "{v} gana por 2 o más",
    "Local no marca": "{l} no marca",
    "Visita no marca": "{v} no marca",
    "Empate": "Empate",
}


class ConfigFaltante(Exception):
    """No están los secrets: todavía no se configuró nada."""


class ConfigInvalida(Exception):
    """Los secrets están, pero mal formados."""


# ----------------------------------------------------------------- utilidades
def parse_fecha(texto) -> datetime | None:
    """'2026-10-01T14:00Z' (o cualquier ISO) -> datetime en UTC. Sin zona = UTC."""
    if not texto:
        return None
    s = str(texto).strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _anotar(nivel: str, msg: str) -> None:
    """Comando de GitHub Actions (::notice::, ::warning::, ::error::) en una sola línea."""
    msg = str(msg).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::{nivel}::{msg}", flush=True)


def _log(texto) -> str:
    """Texto que viene de los datos, listo para el log: una línea y sin '::' (no puede abrir un comando)."""
    return str(texto).replace("\r", " ").replace("\n", " ").replace("::", ": :")


def ocultar(endpoint) -> str:
    """Solo el host y los últimos 6 caracteres del endpoint."""
    ep = str(endpoint or "")
    try:
        host = urlsplit(ep).hostname or "?"
    except ValueError:
        host = "?"
    return f"{host} …{ep[-6:]}"


def _trozos_secretos(endpoint: str) -> set[str]:
    """Partes del endpoint que no deben aparecer en los logs, también como las reescribe requests
    (requote_uri pasa %2b/%2f/%3d a mayúsculas) y decodificadas."""
    variantes = {endpoint, unquote(endpoint)}
    try:
        from requests.utils import requote_uri
        variantes.add(requote_uri(endpoint))
    except Exception:  # sin requests (dry-run) o URL rara: basta con las otras variantes
        pass
    trozos: set[str] = set()
    for v in variantes:
        trozos.add(v)
        try:
            p = urlsplit(v)
        except ValueError:
            continue
        trozos |= {p.path, p.query, p.path + "?" + p.query}
        trozos |= set(p.path.split("/")) | set(p.query.split("&"))
        trozos |= {q.split("=", 1)[1] for q in p.query.split("&") if "=" in q}
    return trozos


def _sanear(texto, secretos) -> str:
    """Una línea, sin endpoints, llaves ni token (sin distinguir mayúsculas), y corta."""
    s = " ".join(str(texto).split())
    for sec in sorted((x for x in secretos if x and len(x) >= 8), key=len, reverse=True):
        s = re.sub(re.escape(sec), "…", s, flags=re.I)
    return s[:300]


def _tipo_error(e: BaseException) -> str:
    """Solo los nombres de la excepción y de su causa: sus textos pueden traer la URL del endpoint."""
    nombres = [type(e).__name__]
    causa = e.__cause__ or e.__context__
    if causa is None and e.args and isinstance(e.args[0], BaseException):
        causa = e.args[0]
    if causa is not None:
        nombres.append(type(causa).__name__)
        razon = getattr(causa, "reason", None)
        if isinstance(razon, BaseException):
            nombres.append(type(razon).__name__)
    return " ← ".join(dict.fromkeys(nombres))


def _es_dns(e: BaseException, profundidad: int = 0) -> bool:
    """¿El host del endpoint no existe en DNS? (urllib3 NameResolutionError o socket.gaierror)."""
    if e is None or profundidad > 6:
        return False
    if type(e).__name__ in ("NameResolutionError", "gaierror"):
        return True
    siguientes = [e.__cause__, e.__context__, getattr(e, "reason", None)]
    siguientes += [a for a in getattr(e, "args", ()) if isinstance(a, BaseException)]
    return any(isinstance(x, BaseException) and _es_dns(x, profundidad + 1) for x in siguientes)


def _salida(n: int) -> None:
    """enviados=<n> en $GITHUB_OUTPUT (cuántos partidos se avisaron en esta corrida)."""
    ruta = os.environ.get("GITHUB_OUTPUT")
    if ruta:
        with open(ruta, "a", encoding="utf-8") as fh:
            fh.write(f"enviados={n}\n")


def servicio_push(endpoint) -> bool:
    """¿Es un endpoint https de un servicio push real, con la forma que usan los navegadores?"""
    if not isinstance(endpoint, str) or len(endpoint) > 1024:
        return False
    try:
        p = urlsplit(endpoint)
        if p.scheme != "https" or p.username or p.password or p.port is not None or p.fragment:
            return False
    except ValueError:
        return False
    host = p.hostname or ""
    for re_host, re_ruta, re_query in SERVICIOS_PUSH:
        if re_host.fullmatch(host) and re_ruta.fullmatch(p.path):
            return bool(re_query.fullmatch(p.query)) if re_query else p.query == ""
    return False


def _sub_valida(s) -> dict | None:
    """{"endpoint", "keys": {"p256dh", "auth"}} si el endpoint pasa la allowlist y están las llaves."""
    if not isinstance(s, dict):
        return None
    ep, keys = s.get("endpoint"), s.get("keys")
    if not (servicio_push(ep) and isinstance(keys, dict)
            and isinstance(keys.get("p256dh"), str) and keys["p256dh"]
            and isinstance(keys.get("auth"), str) and keys["auth"]):
        return None
    return {"endpoint": ep, "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]}}


# ------------------------------------------------------------------- secrets
def leer_suscripciones(crudo: str, origen: str = "PUSH_SUBSCRIPTIONS") -> list[dict]:
    """Un arreglo JSON, un objeto suelto, o varios objetos pegados uno tras otro (separados por
    coma o salto de línea): la web entrega el código de un celular a la vez."""
    datos, dec, i = [], json.JSONDecoder(), 0
    while True:
        while i < len(crudo) and crudo[i] in " \t\r\n,":
            i += 1
        if i >= len(crudo):
            break
        try:
            valor, i = dec.raw_decode(crudo, i)
        except json.JSONDecodeError as e:  # sin el texto: podría traer endpoints
            raise ConfigInvalida(f"{origen} no es JSON válido (línea {e.lineno}, columna {e.colno}).") from None
        if isinstance(valor, list):
            datos.extend(valor)
        elif isinstance(valor, dict):
            datos.append(valor)
        else:
            raise ConfigInvalida(f"{origen} debe ser un arreglo JSON de suscripciones (o una sola).")
    subs, vistos = [], set()
    for n, s in enumerate(datos, 1):
        v = _sub_valida(s)
        if v is None:
            _anotar("warning", f"La suscripción #{n} de {origen} está incompleta o no es de un servicio push "
                               "conocido (endpoint https, keys.p256dh y keys.auth): se ignora.")
            continue
        if v["endpoint"] not in vistos:
            vistos.add(v["endpoint"])
            subs.append(v)
    return subs


def _leer_clave(env) -> str:
    clave = (env.get("VAPID_PRIVATE_KEY") or "").strip()
    if not clave:
        return ""
    try:
        bruto = base64.urlsafe_b64decode(clave + "=" * (-len(clave) % 4))
    except (ValueError, binascii.Error):
        bruto = b""
    if len(bruto) != 32:
        raise ConfigInvalida("VAPID_PRIVATE_KEY no es una clave P-256 cruda de 32 bytes en base64url (43 caracteres).")
    return clave


def _leer_worker(env) -> tuple[str, str] | None:
    """(url_base, token) del Worker, o None si no está configurado o está mal."""
    url = (env.get("AVISOS_URL") or "").strip().rstrip("/")
    token = (env.get("AVISOS_TOKEN") or "").strip()
    if not url and not token:
        return None
    if not url or not token:
        falta = "la variable AVISOS_URL" if not url else "el secret AVISOS_TOKEN"
        _anotar("warning", f"Falta {falta}: no se usan las suscripciones del Worker.")
        return None
    try:
        p = urlsplit(url)
        host = p.hostname or ""
        local = p.scheme == "http" and host in HOSTS_LOCALES
        ok = (p.scheme == "https" or local) and bool(host) and not p.query and not p.fragment and not p.username
    except ValueError:
        ok, local, host = False, False, ""
    if not ok:  # el token solo viaja cifrado (http solo para pruebas en esta máquina)
        _anotar("error", "AVISOS_URL debe ser una URL https:// sin query: no se usan las suscripciones del Worker.")
        return None
    if not local and not host.endswith(".workers.dev"):
        _anotar("warning", f"AVISOS_URL apunta a {_log(host)}, que no es *.workers.dev: revisa que sea el Worker de avisos "
                           "(el token se le envía en cada corrida).")
    return url, token


def leer_config(env=None) -> tuple[str, list[dict], tuple[str, str] | None]:
    """(clave VAPID, suscripciones de PUSH_SUBSCRIPTIONS, (url, token) del Worker o None).

    Hace falta VAPID_PRIVATE_KEY y al menos una fuente: PUSH_SUBSCRIPTIONS o AVISOS_URL + AVISOS_TOKEN.
    """
    env = os.environ if env is None else env
    clave = _leer_clave(env)
    worker = _leer_worker(env)
    crudo = (env.get("PUSH_SUBSCRIPTIONS") or "").strip()
    faltan = []
    if not clave:
        faltan.append("el secret VAPID_PRIVATE_KEY")
    if not crudo and not worker:
        faltan.append("una fuente de suscripciones (la variable AVISOS_URL + el secret AVISOS_TOKEN, "
                      "o el secret PUSH_SUBSCRIPTIONS)")
    if faltan:
        raise ConfigFaltante(" y ".join(faltan))

    subs: list[dict] = []
    if crudo:
        try:
            subs = leer_suscripciones(crudo)
        except ConfigInvalida as e:
            if not worker:
                raise
            _anotar("error", f"{e} Sigo solo con las del Worker.")
        if not subs and not worker:
            raise ConfigInvalida("PUSH_SUBSCRIPTIONS no tiene ninguna suscripción válida.")
    return clave, subs, worker


def preparar_vapid(clave: str):
    """Objeto Vapid listo para firmar. Avisa si no corresponde a la clave pública de la web."""
    from cryptography.hazmat.primitives import serialization  # viene con pywebpush
    from pywebpush import Vapid

    vapid = Vapid.from_string(clave)
    publica = vapid.public_key.public_bytes(serialization.Encoding.X962,
                                            serialization.PublicFormat.UncompressedPoint)
    if base64.urlsafe_b64encode(publica).rstrip(b"=").decode() != VAPID_PUBLICA:
        _anotar("warning", "VAPID_PRIVATE_KEY no corresponde a la clave pública de la web: "
                           "los servicios push van a rechazar los avisos (401/403).")
    return vapid


# -------------------------------------------------------------------- Worker
class _SinRedirecciones(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # un 3xx queda como error: el token no viaja a otro host
        return None


_ABRIDOR = urllib.request.build_opener(_SinRedirecciones)


def _pedir_worker(worker: tuple[str, str], metodo: str, ruta: str, cuerpo=None):
    url, token = worker
    datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
    cab = {"Authorization": f"Bearer {token}", "Accept": "application/json",
           "User-Agent": "cuchifijas-avisos/1 (GitHub Actions)"}
    if datos is not None:
        cab["Content-Type"] = "application/json"
    req = urllib.request.Request(url + ruta, data=datos, method=metodo, headers=cab)
    with _ABRIDOR.open(req, timeout=TIMEOUT_WORKER) as r:
        bruto = r.read(MAX_RESPUESTA + 1)
    if len(bruto) > MAX_RESPUESTA:
        raise ValueError("respuesta demasiado grande")
    return json.loads(bruto.decode("utf-8"))


def _error_worker(e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        pista = ": ¿AVISOS_TOKEN es el mismo secret del Worker?" if e.code == 401 else ""
        return f"HTTP {e.code}{pista}"
    if isinstance(e, urllib.error.URLError):
        return f"sin conexión: {type(e.reason).__name__}"
    return type(e).__name__  # timeout, JSON inválido…


def bajar_del_worker(worker: tuple[str, str]) -> tuple[list[dict], bool]:
    """(suscripciones del Worker, True si se bajaron completas). Si falla, avisa y devuelve False."""
    subs, cursor = [], ""
    for _ in range(MAX_PAGINAS):
        try:
            j = _pedir_worker(worker, "GET", "/v1/suscripciones?cursor=" + quote(cursor, safe=""))
        except Exception as e:
            _anotar("warning", f"No se pudieron leer las suscripciones del Worker ({_error_worker(e)}).")
            return subs, False
        lista = j.get("suscripciones") if isinstance(j, dict) else None
        cursor = j.get("cursor") if isinstance(j, dict) else None
        if not isinstance(lista, list) or (cursor is not None and not isinstance(cursor, str)):
            _anotar("warning", "Respuesta inesperada del Worker al listar suscripciones.")
            return subs, False
        subs.extend(lista)
        if not cursor:
            return subs, True
    _anotar("warning", f"El Worker devolvió más de {MAX_PAGINAS} páginas de suscripciones.")
    return subs, False


def marcar_en_worker(worker: tuple[str, str], clave: str) -> bool | None:
    """True: aviso nuevo (se envía). False: otra corrida ya lo marcó. None: no se pudo marcar."""
    try:
        j = _pedir_worker(worker, "POST", "/v1/marcar", {"clave": clave})
    except Exception as e:
        _anotar("warning", f"No se pudo marcar el aviso {clave} en el Worker ({_error_worker(e)}): "
                           "no se envía; se reintenta en la próxima corrida.")
        return None
    if not isinstance(j, dict) or not isinstance(j.get("nuevo"), bool):
        _anotar("warning", f"Respuesta inesperada del Worker al marcar {clave}: no se envía.")
        return None
    return j["nuevo"]


def eliminar_del_worker(worker: tuple[str, str], endpoints: list[str]) -> int | None:
    """Borra del Worker los endpoints dados. Devuelve cuántos borró, o None si falló."""
    total = 0
    for i in range(0, len(endpoints), LOTE_ELIMINAR):
        try:
            j = _pedir_worker(worker, "POST", "/v1/eliminar", {"endpoints": endpoints[i:i + LOTE_ELIMINAR]})
            total += int(j.get("eliminadas") or 0)
        except Exception as e:
            _anotar("warning", f"No se pudieron borrar suscripciones del Worker ({_error_worker(e)}).")
            return None
    return total


def juntar(subs_secret: list[dict], subs_worker: list[dict]) -> tuple[list[dict], set[str], set[str]]:
    """Une ambas fuentes sin repetir endpoints. Devuelve (subs, endpoints_del_worker, endpoints_del_secret)."""
    subs, vistos, del_worker, invalidas = [], set(), set(), 0
    for s in subs_worker:
        v = _sub_valida(s)
        if v is None:
            invalidas += 1
            continue
        del_worker.add(v["endpoint"])
        if v["endpoint"] not in vistos:
            vistos.add(v["endpoint"])
            subs.append(v)
    if invalidas:
        _anotar("warning", f"El Worker devolvió {invalidas} suscripción(es) fuera de la allowlist: se ignoran.")
    del_secret = {s["endpoint"] for s in subs_secret}
    for s in subs_secret:
        if s["endpoint"] not in vistos:
            vistos.add(s["endpoint"])
            subs.append(s)
    return subs, del_worker, del_secret


# ------------------------------------------------------------------ partidos
def clave_aviso(pid: str, inicio: datetime) -> str:
    """Un aviso por partido y hora de inicio (si lo reprograman, se vuelve a avisar)."""
    return f"{pid}@{inicio:%Y-%m-%dT%H:%MZ}"


def agrupar_fijas(datos: dict) -> dict[str, list[dict]]:
    """{id_partido: [fijas]} en el orden de docs/data.json."""
    lista = ((datos or {}).get("fijas") or {}).get("lista") or []
    grupos: dict[str, list[dict]] = {}
    for f in lista:
        if isinstance(f, dict) and f.get("id") not in (None, ""):
            grupos.setdefault(str(f["id"]), []).append(f)
    return grupos


def avisos_pendientes(grupos: dict, ahora: datetime, enviados: dict,
                      ventana_min: int = VENTANA_MIN) -> tuple[list[dict], int]:
    """Partidos con fija que empiezan en 0..ventana_min minutos y no se avisaron. Devuelve (pendientes, ya_avisados)."""
    pendientes, ya = [], 0
    for pid, fijas in grupos.items():
        inicio = min((t for t in (parse_fecha(f.get("fecha")) for f in fijas) if t), default=None)
        if inicio is None:
            continue
        faltan = (inicio - ahora).total_seconds()
        if not 0 <= faltan <= ventana_min * 60:
            continue
        clave = clave_aviso(pid, inicio)
        if clave in enviados:
            ya += 1
            continue
        pendientes.append({"id": pid, "clave": clave, "inicio": inicio, "faltan": faltan, "fijas": fijas})
    pendientes.sort(key=lambda a: a["inicio"])
    return pendientes, ya


def _seleccion_web(f: dict) -> str:
    """El pick con el mismo texto que la tarjeta de la web (prettyAlt)."""
    texto = str(f.get("seleccion") or "Fija").strip()
    local, visita = str(f.get("local") or "Local"), str(f.get("visita") or "Visita")
    if texto in _PICKS_WEB:
        return _PICKS_WEB[texto].format(l=local, v=visita)
    texto = re.sub(r"^Local ", lambda _: local + " ", texto)
    return re.sub(r"^Visita ", lambda _: visita + " ", texto)


def _prob_web(f: dict) -> str | None:
    """La probabilidad que muestra la web: prob_real (si falta, prob_calibrada y luego prob), como
    (p * 100).toFixed(0) de JavaScript."""
    for campo in ("prob_real", "prob_calibrada", "prob"):
        v = f.get(campo)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return f"{Decimal(float(v) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)}%"
    return None


def _linea_fija(f: dict) -> str:
    partes = [_seleccion_web(f)]
    pct = _prob_web(f)
    if pct:
        partes.append(pct)
    try:
        partes.append(f"apuesta si paga ≥ {float(f['cuota_minima']):.2f}")
    except (KeyError, TypeError, ValueError):
        pass
    return " · ".join(partes)


def mensaje(aviso: dict) -> dict:
    """Payload que espera el service worker: title, body, url y tag."""
    f0 = aviso["fijas"][0]
    partido = f"{f0.get('local') or 'Local'} vs {f0.get('visita') or 'Visita'}"
    minutos = round(aviso["faltan"] / 60)
    titulo = f"⏰ En {minutos} min: {partido}" if minutos >= 1 else f"⏰ Ya empieza: {partido}"

    fijas, vistas = [], set()
    for f in sorted(aviso["fijas"], key=lambda x: -(x.get("puntaje") or 0)):
        k = f.get("clave") or f.get("seleccion")
        if k not in vistas:
            vistas.add(k)
            fijas.append(f)
    if len(fijas) == 1:
        cuerpo = f"Fija: {_linea_fija(fijas[0])}"
    else:
        cuerpo = f"{len(fijas)} fijas:\n" + "\n".join(f"• {_linea_fija(f)}" for f in fijas)
    if len(cuerpo) > MAX_CUERPO:
        cuerpo = cuerpo[:MAX_CUERPO - 1] + "…"
    cuerpo += f"\nEmpieza {aviso['inicio'].astimezone(LIMA):%H:%M} (Lima)"
    return {"title": titulo, "body": cuerpo, "url": f"./#p.{aviso['id']}", "tag": f"fija-{aviso['id']}"}


def mensaje_prueba() -> dict:
    return {"title": "Notificaciones activadas ✅",
            "body": "Te avisaremos unos 30 min antes de cada partido con fija.",
            "url": "./", "tag": "cuchifijas-prueba"}


def _mostrar(payload: dict, ttl: int) -> None:
    print(f"  {_log(payload['title'])}")
    for linea in str(payload["body"]).split("\n"):
        print(f"    {_log(linea)}")
    print(f"    [url {_log(payload['url'])} · tag {_log(payload['tag'])} · TTL {ttl} s · urgency high]", flush=True)


# --------------------------------------------------------------------- estado
def cargar_estado(ruta: str, ahora: datetime) -> dict[str, str]:
    """Archivo local (solo sin Worker): {clave_aviso: enviado_en}, sin lo de hace más de RETENCION_DIAS días."""
    try:
        with open(ruta, encoding="utf-8") as fh:
            est = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        _anotar("warning", f"No se pudo leer {ruta}: empiezo sin avisos previos.")
        return {}
    enviados = est.get("enviados") if isinstance(est, dict) else None
    if not isinstance(enviados, dict):
        return {}
    limite = ahora - timedelta(days=RETENCION_DIAS)
    vivos = {}
    for k, v in enviados.items():
        t = parse_fecha(v)
        if t is not None and t >= limite:
            vivos[str(k)] = _iso(t)
    return vivos


def guardar_estado(ruta: str, enviados: dict) -> None:
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "enviados": dict(sorted(enviados.items()))}, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    os.replace(tmp, ruta)


# ---------------------------------------------------------------------- envío
class Envio:
    """Manda payloads a un conjunto de suscripciones y, al cerrar, limpia las caducadas o inválidas."""

    def __init__(self, subs, vapid, clave="", worker=None, del_worker=(), del_secret=()):
        self.subs = list(subs)
        self.vapid, self.clave, self.worker = vapid, clave, worker
        self.del_worker, self.del_secret = set(del_worker), set(del_secret)
        self.caducadas: dict[str, int] = {}   # 404/410: no se reintentan y se borran siempre
        self.invalidas: dict[str, str] = {}   # 400 o DNS: se borran si la tasa de éxito ≥ TASA_MIN_BORRADO
        self.intentos = self.exitos = 0
        self._hilo = threading.local()
        self._sesiones: list = []
        self._candado = threading.Lock()
        self._pool: ThreadPoolExecutor | None = None

    def _sesion(self):
        """Una requests.Session por hilo (reutiliza conexiones TLS; Session no es segura entre hilos)."""
        s = getattr(self._hilo, "sesion", None)
        if s is None:
            import requests
            s = self._hilo.sesion = requests.Session()
            with self._candado:
                self._sesiones.append(s)
        return s

    def _uno(self, sub, datos: bytes, ttl: int):
        from pywebpush import WebPushException, webpush

        secretos = _trozos_secretos(sub["endpoint"]) | {self.clave, sub["keys"]["p256dh"], sub["keys"]["auth"]}
        if self.worker:
            secretos.add(self.worker[1])
        try:
            # claims nuevos en cada envío: webpush() les pone 'aud' según el host del endpoint
            resp = webpush(sub, data=datos, vapid_private_key=self.vapid, vapid_claims={"sub": VAPID_SUB},
                           ttl=ttl, headers={"Urgency": "high"}, timeout=TIMEOUT, requests_session=self._sesion())
        except WebPushException as e:
            codigo = e.status_code
            if codigo in (404, 410):
                return "caducada", codigo
            cuerpo = getattr(e.response, "text", "") if e.response is not None else ""
            detalle = f"HTTP {codigo} {_sanear(cuerpo, secretos)}".rstrip()
            if codigo in (401, 403):
                detalle += " ¿VAPID_PRIVATE_KEY corresponde a la clave pública de la web?"
            return ("invalida" if codigo == 400 else "error"), detalle
        except Exception as e:  # red, timeout, llaves malformadas… El texto puede traer la URL: solo los tipos.
            return ("invalida" if _es_dns(e) else "error"), _tipo_error(e)
        return "ok", resp.status_code

    def enviar(self, payload: dict, ttl: int) -> int:
        """Manda el payload a todas las suscripciones vivas. Devuelve cuántas lo recibieron."""
        import pywebpush  # noqa: F401  (falla aquí, antes de abrir hilos, si no está instalado)

        subs = [s for s in self.subs if s["endpoint"] not in self.caducadas]
        if not subs:
            return 0
        datos = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=HILOS)
        resultados = list(self._pool.map(lambda s: self._uno(s, datos, ttl), subs))
        ok = errores = 0
        for sub, (estado, info) in zip(subs, resultados):
            ep, quien = sub["endpoint"], ocultar(sub["endpoint"])
            if estado == "ok":
                ok += 1
                self.invalidas.pop(ep, None)
                if len(subs) <= MAX_AVISOS_LOG:
                    print(f"    enviado a {quien} (HTTP {info})", flush=True)
            elif estado == "caducada":
                self.caducadas[ep] = info
            else:
                if estado == "invalida":
                    self.invalidas[ep] = info
                errores += 1
                if errores <= MAX_AVISOS_LOG:
                    _anotar("warning", f"No se pudo avisar a {quien}: {info}")
        if errores > MAX_AVISOS_LOG:
            _anotar("warning", f"… y {errores - MAX_AVISOS_LOG} error(es) más de envío.")
        self.intentos += len(subs)
        self.exitos += ok
        nuevas = sum(1 for s in subs if s["endpoint"] in self.caducadas)
        print(f"    entregados: {ok} de {len(subs)}" + (f" · caducadas: {nuevas}" if nuevas else "")
              + (f" · errores: {errores}" if errores else ""), flush=True)
        return ok

    def cerrar(self) -> None:
        """Cierra hilos y sesiones; borra del Worker lo caducado (y lo inválido si la corrida fue sana)."""
        if self._pool is not None:
            self._pool.shutdown(wait=True)
        for s in self._sesiones:
            s.close()
        borrar = {ep: f"caducó (HTTP {codigo})" for ep, codigo in self.caducadas.items()}
        if self.invalidas:
            tasa = self.exitos / self.intentos if self.intentos else 0.0
            if tasa >= TASA_MIN_BORRADO:
                borrar.update({ep: f"es inválida ({_log(motivo)})" for ep, motivo in self.invalidas.items()})
            else:
                _anotar("warning", f"No se borran {len(self.invalidas)} suscripción(es) con HTTP 400 o host sin DNS: "
                                   f"en esta corrida solo llegó el {tasa:.0%} de los envíos (mínimo "
                                   f"{TASA_MIN_BORRADO:.0%}); puede ser una falla general y no de esas suscripciones.")
        for ep, motivo in borrar.items():
            if ep in self.del_secret:
                _anotar("warning", f"La suscripción {ocultar(ep)} {motivo}: quítala del secret PUSH_SUBSCRIPTIONS.")
        del_worker = [ep for ep in borrar if ep in self.del_worker]
        if del_worker and self.worker:
            n = eliminar_del_worker(self.worker, del_worker)
            if n is not None:
                print(f"Suscripciones caducadas o inválidas borradas del Worker: {n} de {len(del_worker)}", flush=True)


def _config(prueba: bool):
    """(clave, subs_secret, worker, vapid), o el código de salida si no se puede enviar."""
    try:
        clave, subs, worker = leer_config()
    except ConfigFaltante as e:
        _anotar("notice", f"Falta {e} (Settings → Secrets and variables → Actions): no se envía nada.")
        return 0
    except ConfigInvalida as e:
        _anotar("error", str(e))
        return 1 if prueba else 0  # el cron no falla cada 10 min; la prueba manual sí
    try:
        vapid = preparar_vapid(clave)
    except ImportError:
        _anotar("error", "Falta pywebpush: pip install --require-hashes -r pronosticos/requirements-avisos.txt")
        return 1
    except Exception as e:
        _anotar("error", f"VAPID_PRIVATE_KEY no se pudo cargar ({type(e).__name__}).")
        return 1 if prueba else 0
    return clave, subs, worker, vapid


def _suscripciones(subs_secret, worker):
    """Baja las del Worker y las une a las del secret. Devuelve (subs, del_worker, del_secret, worker_ok)."""
    subs_worker, worker_ok = bajar_del_worker(worker) if worker else ([], True)
    subs, del_worker, del_secret = juntar(subs_secret, subs_worker)
    origen = []
    if worker:
        origen.append(f"Worker {len(del_worker)}" + ("" if worker_ok else " (incompleto)"))
    if subs_secret:
        origen.append(f"PUSH_SUBSCRIPTIONS {len(subs_secret)}")
    print(f"Suscripciones: {len(subs)} ({' · '.join(origen) or 'ninguna fuente'})", flush=True)
    return subs, del_worker, del_secret, worker_ok


def _correr(a, prueba: bool, ahora: datetime) -> int:
    print(f"Hora: {ahora:%Y-%m-%d %H:%M} UTC ({ahora.astimezone(LIMA):%H:%M} Lima)"
          + (" · simulación, no se envía nada" if a.dry_run else ""), flush=True)

    if prueba:
        # Solo a PUSH_SUBSCRIPTIONS (los celulares del dueño): una prueba no se manda a los suscriptores públicos.
        payload = mensaje_prueba()
        if a.dry_run:
            print("Aviso de prueba:")
            _mostrar(payload, TTL_PRUEBA)
            _salida(0)
            return 0
        cfg = _config(prueba=True)
        if isinstance(cfg, int):
            _salida(0)
            return cfg
        clave, subs, worker, vapid = cfg
        _salida(0)
        if not subs:
            _anotar("error", "El aviso de prueba solo va a los celulares de PUSH_SUBSCRIPTIONS (no a los suscriptores "
                             "públicos del Worker), y ese secret no tiene ninguno.")
            return 1
        print(f"Aviso de prueba a {len(subs)} suscripción(es) de PUSH_SUBSCRIPTIONS:")
        _mostrar(payload, TTL_PRUEBA)
        envio = Envio(subs, vapid, clave, worker, del_secret={s["endpoint"] for s in subs})
        try:
            ok = envio.enviar(payload, TTL_PRUEBA)
        finally:
            envio.cerrar()
        if not ok:
            _anotar("error", "El aviso de prueba no llegó a ninguna suscripción.")
            return 1
        return 0

    cfg = None
    if not a.dry_run:
        cfg = _config(prueba=False)
        if isinstance(cfg, int):
            _salida(0)
            return cfg

    try:
        with open(a.datos, encoding="utf-8") as fh:
            datos = json.load(fh)
    except (OSError, ValueError) as e:
        _anotar("error", f"No se pudo leer {a.datos}: {type(e).__name__}")
        _salida(0)
        return 1

    if a.dry_run:
        env = os.environ
        worker = _leer_worker(env)
        try:
            subs_secret = leer_suscripciones((env.get("PUSH_SUBSCRIPTIONS") or "").strip())
        except ConfigInvalida as e:
            _anotar("warning", str(e))
            subs_secret = []
    else:
        clave, subs_secret, worker, vapid = cfg

    # Con Worker, lo ya avisado está en D1 (/v1/marcar); sin Worker, en el archivo local (desarrollo).
    enviados = {} if worker else cargar_estado(a.estado, ahora)
    grupos = agrupar_fijas(datos)
    pendientes, ya = avisos_pendientes(grupos, ahora, enviados)
    print(f"Fijas: {sum(len(v) for v in grupos.values())} en {len(grupos)} partido(s) · "
          f"por avisar en los próximos {VENTANA_MIN} min: {len(pendientes)}"
          + ("" if worker else f" · ya avisados: {ya}")
          + (" · estado: D1 del Worker" if worker else " · estado: archivo local"), flush=True)

    if a.dry_run:
        if worker or subs_secret:
            _suscripciones(subs_secret, worker)
        for av in pendientes:
            print(f"Partido {_log(av['id'])} ({_log(av['clave'])}):")
            _mostrar(mensaje(av), max(TTL_MIN, int(av["faltan"])))
        _salida(0)
        return 0

    nuevos = 0
    envio = None
    try:
        if pendientes:
            subs, del_worker, del_secret, worker_ok = _suscripciones(subs_secret, worker)
            if not worker_ok:
                # B3: sin la lista completa no se marca nada (si no, el aviso se perdería para quienes faltan).
                _anotar("warning", "No se envía ni se marca nada en esta corrida: se reintenta en la próxima.")
                pendientes = []
            elif not subs:
                print("No hay suscripciones: nada que enviar (se reintenta en la próxima corrida).")
                pendientes = []
            else:
                envio = Envio(subs, vapid, clave, worker, del_worker, del_secret)
        for av in pendientes:
            payload = mensaje(av)
            ttl = max(TTL_MIN, int(av["faltan"]))
            print(f"Partido {_log(av['id'])} ({_log(av['clave'])}):")
            if worker:
                nuevo = marcar_en_worker(worker, av["clave"])
                if nuevo is None:
                    continue
                if not nuevo:
                    print("  ya avisado en otra corrida (D1): se salta")
                    continue
                _mostrar(payload, ttl)
                nuevos += 1  # marcado: no se vuelve a enviar aunque falle (como máximo una vez)
                if not envio.enviar(payload, ttl):
                    _anotar("warning", f"El aviso de {payload['title']} no llegó a nadie (ya estaba marcado: no se reintenta).")
            else:
                _mostrar(payload, ttl)
                if envio.enviar(payload, ttl):
                    enviados[av["clave"]] = _iso(ahora)
                    nuevos += 1
                else:
                    _anotar("warning", f"El aviso de {payload['title']} no llegó a nadie: se reintenta en la próxima corrida.")
    finally:
        if nuevos and not worker:
            guardar_estado(a.estado, enviados)
        if envio:
            envio.cerrar()
        _salida(nuevos)
    print(f"Partidos avisados en esta corrida: {nuevos}")
    return 0


def main(argv=None) -> int:
    try:  # en la consola de Windows, para que los emojis y tildes no revienten print()
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(prog="python -m pronosticos.notificar",
                                 description="Avisos push ~30 min antes de cada partido con fija.")
    ap.add_argument("--dry-run", action="store_true", help="muestra los avisos sin enviarlos, marcarlos ni guardar estado")
    ap.add_argument("--ahora", metavar="ISO", help="simula la hora actual (sin zona = UTC), p. ej. 2026-10-01T13:25Z")
    ap.add_argument("--prueba", action="store_true", help="envía ya un aviso de prueba a los celulares de "
                                                          "PUSH_SUBSCRIPTIONS (también con PRUEBA=true)")
    ap.add_argument("--datos", default=DATOS, help=f"JSON de la web (por defecto {DATOS})")
    ap.add_argument("--estado", default=ESTADO, help=f"avisos ya enviados sin Worker, solo desarrollo (por defecto {ESTADO})")
    a = ap.parse_args(argv)

    prueba = a.prueba or os.environ.get("PRUEBA", "").strip().lower() in ("true", "1", "si", "sí", "yes")
    if a.ahora:
        ahora = parse_fecha(a.ahora)
        if ahora is None:
            ap.error(f"--ahora no es una fecha ISO válida: {a.ahora}")
    else:
        ahora = datetime.now(timezone.utc)
    return _correr(a, prueba, ahora)


if __name__ == "__main__":
    sys.exit(main())

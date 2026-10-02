"""Descarga de datos: football-data.co.uk (historia + cuotas) y ESPN (Liga 1 Perú,
próximos partidos y cuotas actuales). Guarda todo en data/ como caché JSON.

Los tres archivos de caché tienen el mismo formato que usa el resto del motor:
  data/raw.json         {"fd": {"2526/E0": csv_text, ...}, "espn": {"2025": [eventos Perú]}}
  data/proximos.json    {"leagues": {"eng.1": [eventos no jugados con cuotas]}}
  data/espn_top5.json   {"eng.1": [[fecha, local, visita, gl, gv], ...]}  (para mapear nombres)
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import requests

from .config import (LEAGUES, FD_BASE, ESPN_BASE, N_SEASONS_EUROPE, N_YEARS_PERU, INT_COMPETITIONS, INT_RESULTS_URL,
                     WOMEN_HISTORY, N_YEARS_WOMEN, ESPN_ANUALES)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
    "Referer": "https://www.espn.com/",
    "Origin": "https://www.espn.com",
}
# Hosts alternativos de la API de ESPN (si uno bloquea, se prueba el siguiente).
ESPN_HOSTS = [ESPN_BASE.replace("site.api.espn.com", "site.web.api.espn.com"), ESPN_BASE]  # site.api bloquea a GitHub (403)
_FAILS = {}          # host -> fallos seguidos (para no perder 15 minutos reintentando un host caído)
_LOGGED = set()


def season_codes(now: datetime, n: int) -> list[str]:
    start = now.year if now.month >= 7 else now.year - 1
    return [f"{(y) % 100:02d}{(y + 1) % 100:02d}" for y in range(start - n + 1, start + 1)]


def _host(url: str) -> str:
    return url.split("/")[2]


def _get(url: str, tries: int = 2, **kw):
    host = _host(url)
    if _FAILS.get(host, 0) >= 6:   # host caído: no insistir
        return None
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=20, **kw)
            if r.status_code == 200:
                _FAILS[host] = 0
                return r
            if host not in _LOGGED:
                _LOGGED.add(host)
                print(f"::warning::{host} respondió {r.status_code} para {r.url[:120]}: {r.text[:200]!r}")
            if r.status_code in (400, 404):
                return None
        except requests.RequestException as e:
            if host not in _LOGGED:
                _LOGGED.add(host)
                print(f"::warning::No se pudo conectar con {host}: {type(e).__name__}: {str(e)[:200]}")
        time.sleep(1.5 * (i + 1))
    _FAILS[host] = _FAILS.get(host, 0) + 1
    return None


def _espn(path: str, **params):
    """Llama a la API de ESPN probando los hosts alternativos."""
    for base in ESPN_HOSTS:
        r = _get(f"{base}/{path}", params=params)
        if r is not None:
            try:
                return r.json()
            except ValueError:
                continue
    return None


def _espn_year(slug: str, year: int) -> list[dict]:
    j = _espn(f"{slug}/scoreboard", dates=str(year), limit=1000)
    return (j or {}).get("events") or []


def _slim_event(e: dict) -> dict:
    c = e["competitions"][0]
    return {
        "id": e["id"], "date": e["date"], "status": e["status"]["type"]["name"],
        "season": (e.get("season") or {}).get("slug"), "neutral": bool(c.get("neutralSite")),
        "t": [{"ha": x["homeAway"], "id": x["team"]["id"], "name": x["team"]["displayName"],
               "score": x.get("score"),
               "st": {s["name"]: s.get("displayValue") for s in (x.get("statistics") or [])}}
              for x in c["competitors"]],
    }


def _pick_odds(o: dict | None):
    if not o:
        return None
    g = lambda *ks: _dig(o, ks)
    return {
        "h": g("moneyline", "home", "close", "odds"), "d": g("moneyline", "draw", "close", "odds"),
        "a": g("moneyline", "away", "close", "odds"),
        "hO": g("moneyline", "home", "open", "odds"), "dO": g("moneyline", "draw", "open", "odds"),
        "aO": g("moneyline", "away", "open", "odds"),
        "ou": o.get("overUnder"), "ov": g("total", "over", "close", "odds"), "un": g("total", "under", "close", "odds"),
        "sh": g("pointSpread", "home", "close", "line"), "shO": g("pointSpread", "home", "close", "odds"),
        "saO": g("pointSpread", "away", "close", "odds"), "prov": g("provider", "name"),
    }


def _dig(d, ks):
    for k in ks:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def fetch_all(verbose: bool = True) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    now = datetime.now(timezone.utc)
    log = print if verbose else (lambda *a, **k: None)

    # 1) football-data: historia + cuotas de cierre
    raw = {"fd": {}, "espn": {}, "fetched": now.isoformat()}
    for code in season_codes(now, N_SEASONS_EUROPE):
        for lg in LEAGUES.values():
            if not lg["fd"]:
                continue
            r = _get(f"{FD_BASE}/mmz4281/{code}/{lg['fd']}.csv")
            if r is not None and len(r.content) > 200:
                raw["fd"][f"{code}/{lg['fd']}"] = r.content.decode("latin-1")
                log(f"  football-data {code}/{lg['fd']}: ok")
    r = _get(f"{FD_BASE}/fixtures.csv")
    if r is not None and len(r.content) > 200:
        raw["fd"]["fixtures"] = r.content.decode("utf-8-sig", errors="replace")

    # 2) ESPN Perú (resultados + estadísticas)
    for y in range(now.year - N_YEARS_PERU + 1, now.year + 1):
        ev = _espn_year("per.1", y)
        raw["espn"][str(y)] = [_slim_event(e) for e in ev]
        log(f"  ESPN Liga 1 {y}: {len(ev)} partidos")

    # 2a) otras ligas anuales solo de ESPN (Argentina)
    raw["espn_x"] = {}
    for code, (slug, n_years) in ESPN_ANUALES.items():
        for y in range(now.year - n_years + 1, now.year + 1):
            raw["espn_x"].setdefault(code, {})[str(y)] = [_slim_event(e) for e in _espn_year(slug, y)]
        log(f"  ESPN {slug}: {sum(len(v) for v in raw['espn_x'][code].values())} partidos")

    # 2b) Champions femenina + ligas domésticas de sus equipos (historia para los ratings)
    raw["espn_w"] = {}
    for slug in WOMEN_HISTORY:
        for y in range(now.year - N_YEARS_WOMEN + 1, now.year + 1):
            raw["espn_w"].setdefault(slug, {})[str(y)] = [_slim_event(e) for e in _espn_year(slug, y)]
        log(f"  ESPN {slug}: {sum(len(v) for v in raw['espn_w'][slug].values())} partidos")

    # 3) ESPN próximos partidos (todas las ligas) + resultados recientes para mapear nombres
    prox = {"fetched": now.isoformat(), "leagues": {}, "resultados": {}}
    top5 = {}
    years = [now.year - 1, now.year] + ([now.year + 1] if now.month >= 11 else [])
    for lg in LEAGUES.values():
        slug = lg["espn"]
        if not slug:
            continue
        events = []
        for y in years:
            events += _espn_year(slug, y)
        seen, up, done = set(), [], []
        for e in events:
            if e["id"] in seen:
                continue
            seen.add(e["id"])
            c = e["competitions"][0]
            state = e["status"]["type"]["state"]
            if state == "post":
                h = next(x for x in c["competitors"] if x["homeAway"] == "home")
                a = next(x for x in c["competitors"] if x["homeAway"] == "away")
                done.append([e["date"], h["team"]["displayName"], a["team"]["displayName"], h.get("score"), a.get("score"), e["id"]])
                if e["status"]["type"].get("completed") and e["date"] >= f"{now.year - 1}":
                    prox["resultados"][e["id"]] = {"hg": _int(h.get("score")), "ag": _int(a.get("score"))}
            else:
                up.append({
                    "id": e["id"], "date": e["date"], "state": state, "season": (e.get("season") or {}).get("slug"),
                    "venue": (c.get("venue") or {}).get("fullName"),
                    "t": [{"ha": x["homeAway"], "id": x["team"]["id"], "name": x["team"]["displayName"],
                           "abbr": x["team"].get("abbreviation"), "form": x.get("form"),
                           "rec": ((x.get("records") or [{}])[0]).get("summary")} for x in c["competitors"]],
                    "odds": _pick_odds((c.get("odds") or [None])[0]),
                })
        prox["leagues"][slug] = up
        if lg["fd"]:
            top5[slug] = done
        log(f"  ESPN {slug}: {len(up)} próximos, {len(done)} jugados")

    # 4) Selecciones: base histórica + ESPN (resultados recientes y próximos con cuotas)
    r = _get(INT_RESULTS_URL)
    if r is not None:
        with open(os.path.join(DATA_DIR, "int_results.csv"), "wb") as f:
            f.write(r.content)
        log("  resultados internacionales: ok")
    intl = {"fetched": now.isoformat(), "done": [], "up": []}
    finals = {"STATUS_FULL_TIME", "STATUS_FINAL_PEN", "STATUS_FINAL_AET", "STATUS_FINAL"}
    for slug in INT_COMPETITIONS:
        for y in (now.year - 1, now.year):
            j = _espn(f"{slug}/scoreboard", dates=str(y), limit=1000)
            if not j:
                continue
            comp = ((j.get("leagues") or [{}])[0]).get("name")
            for e in j.get("events") or []:
                c = e["competitions"][0]
                h = next(x for x in c["competitors"] if x["homeAway"] == "home")
                a = next(x for x in c["competitors"] if x["homeAway"] == "away")
                st = e["status"]["type"]
                base = {"id": e["id"], "slug": slug, "comp": comp, "date": e["date"], "neutral": bool(c.get("neutralSite")),
                        "venue": (c.get("venue") or {}).get("fullName"), "home": h["team"]["displayName"], "away": a["team"]["displayName"]}
                if st["state"] == "post":
                    if st["name"] in finals:
                        intl["done"].append({**base, "hs": h.get("score"), "as": a.get("score"), "status": st["name"]})
                else:
                    intl["up"].append({**base, "state": st["state"], "hform": h.get("form"), "aform": a.get("form"),
                                       "odds": _pick_odds((c.get("odds") or [None])[0])})
    log(f"  ESPN selecciones: {len(intl['up'])} próximos, {len(intl['done'])} jugados")

    # Si una fuente falló, se conserva lo que ya había en la caché en vez de dejar la web vacía.
    old = lambda n: _load_old(n)
    o_raw = old("raw.json") or {}
    if not raw["fd"]:
        print("::warning::football-data no respondió: se usan los datos anteriores de Europa.")
        raw["fd"] = o_raw.get("fd", {})
    if not any(raw["espn"].values()):
        print("::warning::ESPN (Liga 1) no respondió: se usan los datos anteriores.")
        raw["espn"] = o_raw.get("espn", {})
    for code, years in list(raw["espn_x"].items()):
        if not any(years.values()) and (o_raw.get("espn_x") or {}).get(code):
            print(f"::warning::ESPN {code} no respondió: se usan los datos anteriores.")
            raw["espn_x"][code] = o_raw["espn_x"][code]
    for slug, years in list(raw["espn_w"].items()):
        if not any(years.values()) and (o_raw.get("espn_w") or {}).get(slug):
            print(f"::warning::ESPN {slug} no respondió: se usan los datos anteriores.")
            raw["espn_w"][slug] = o_raw["espn_w"][slug]
    o_prox = (old("proximos.json") or {}).get("leagues", {})
    o_top5 = old("espn_top5.json") or {}
    for slug in list(prox["leagues"]):
        if not prox["leagues"][slug] and o_prox.get(slug):
            print(f"::warning::ESPN {slug}: sin datos nuevos, se conservan los anteriores.")
            prox["leagues"][slug] = o_prox[slug]
        if slug in top5 and not top5[slug] and o_top5.get(slug):
            top5[slug] = o_top5[slug]
    if not intl["up"] and not intl["done"]:
        o_int = old("internacional.json")
        if o_int:
            print("::warning::ESPN selecciones: sin datos nuevos, se conservan los anteriores.")
            intl = o_int
    prox["resultados"] = {**(old("proximos.json") or {}).get("resultados", {}), **prox["resultados"]}
    for e in intl.get("done", []):
        prox["resultados"].setdefault(e["id"], {"hg": _int(e.get("hs")), "ag": _int(e.get("as"))})
    prox["arbitros"] = fetch_referees(prox, intl, now, (old("proximos.json") or {}).get("arbitros", {}))
    log(f"  árbitros confirmados en ESPN: {len(prox['arbitros'])}")
    for name, obj in (("raw.json", raw), ("proximos.json", prox), ("espn_top5.json", top5), ("internacional.json", intl)):
        with open(os.path.join(DATA_DIR, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
    if _FAILS:
        print("Hosts con fallos:", {h: n for h, n in _FAILS.items() if n})


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _referee(j: dict):
    return next((o.get("displayName") for o in ((j.get("gameInfo") or {}).get("officials") or [])
                 if (o.get("position") or {}).get("name") == "Referee"), None)


def fetch_referees(prox: dict, intl: dict, now: datetime, old: dict, days: int = 4, workers: int = 8) -> dict:
    """ESPN publica el árbitro poco antes del partido: se consulta la ficha de los partidos de los próximos días."""
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    lim = (now + timedelta(days=days)).strftime("%Y-%m-%dT%H:%MZ")
    todo = [(slug, e["id"]) for slug, evs in prox["leagues"].items() for e in evs if e["date"] <= lim]
    todo += [(e["slug"], e["id"]) for e in intl.get("up", []) if e["date"] <= lim]
    upcoming = {i for _, i in todo}
    out = {k: v for k, v in old.items() if k in upcoming}

    def one(t):
        j = _espn(f"{t[0]}/summary", event=t[1])
        return t[1], _referee(j) if j else None

    with ThreadPoolExecutor(workers) as ex:
        for eid, ref in ex.map(one, todo):
            if ref:
                out[eid] = ref
    return out


def _load_old(name):
    try:
        with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None




# ---------------------------------------------------------------- estadísticas de jugadores (ESPN summary)
PLAYER_TARGETS = [  # (slug, código, días hacia atrás)
    ("eng.1", "E0", 270), ("esp.1", "SP1", 270), ("ita.1", "I1", 270), ("ger.1", "D1", 270), ("fra.1", "F1", 270),
    ("per.1", "PER", 450), ("uefa.wchampions", "UWCL", 450),
] + [(slug, code, 450) for code, (slug, _) in ESPN_ANUALES.items()] + [(s, "INT", 480) for s in INT_COMPETITIONS]


def _clock(v):
    import re
    m = re.match(r"^(\d+)", str(v or ""))
    return min(90, int(m.group(1))) if m else None


def summarize_event(j: dict, slug: str, lg: str, eid: str, date: str) -> dict:
    sub_in, sub_out = {}, {}
    for e in j.get("keyEvents") or []:
        if (e.get("type") or {}).get("type") == "substitution" and len(e.get("participants") or []) >= 2:
            m = _clock((e.get("clock") or {}).get("displayValue"))
            sub_in[e["participants"][0]["athlete"]["id"]] = m
            sub_out[e["participants"][1]["athlete"]["id"]] = m
    teams = [{"id": t["team"]["id"], "name": t["team"]["displayName"], "ha": t.get("homeAway"),
              "st": {x["name"]: x.get("displayValue") for x in (t.get("statistics") or [])}}
             for t in ((j.get("boxscore") or {}).get("teams") or [])]
    players = []
    for ro in j.get("rosters") or []:
        side = 0 if ro.get("homeAway") == "home" else 1
        for p in ro.get("roster") or []:
            st = {x["name"]: x.get("value") or 0 for x in (p.get("stats") or [])}
            if not st.get("appearances") and not p.get("starter"):
                continue
            aid = p["athlete"]["id"]
            if p.get("starter"):
                mins = sub_out.get(aid) if sub_out.get(aid) is not None else (75 if p.get("subbedOut") else 90)
            else:
                mins = max(1, 90 - sub_in[aid]) if sub_in.get(aid) is not None else (20 if p.get("subbedIn") else 0)
            if not mins:
                continue
            players.append([side, aid, p["athlete"]["displayName"], (p.get("position") or {}).get("abbreviation") or "",
                            1 if p.get("starter") else 0, mins] +
                           [st.get(k, 0) for k in ("totalGoals", "goalAssists", "totalShots", "shotsOnTarget", "foulsCommitted",
                                                   "foulsSuffered", "yellowCards", "redCards", "offsides", "saves")])
    ref = _referee(j)
    comp = ((j.get("header") or {}).get("league") or {}).get("name") or slug
    ht = None
    comps = (((j.get("header") or {}).get("competitions") or [{}])[0]).get("competitors") or []
    ls = {c.get("homeAway"): c.get("linescores") or [] for c in comps}
    if ls.get("home") and ls.get("away"):
        ht = [_int(ls["home"][0].get("displayValue")), _int(ls["away"][0].get("displayValue"))]
    score = {c.get("homeAway"): _int(c.get("score")) for c in comps}
    return {"id": eid, "slug": slug, "lg": lg, "comp": comp, "date": date, "ref": ref, "ht": ht,
            "score": [score.get("home"), score.get("away")], "teams": teams, "players": players}


def fetch_players(verbose: bool = True, workers: int = 8) -> None:
    """Descarga incremental: solo pide los partidos que aún no están en data/jugadores.json."""
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    log = print if verbose else (lambda *a, **k: None)
    path = os.path.join(DATA_DIR, "jugadores.json")
    cache = {"matches": []}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cache = json.load(f)
    have = {m["id"] for m in cache["matches"]}
    now = datetime.now(timezone.utc)
    todo = []
    for slug, lg, days in PLAYER_TARGETS:
        since = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%MZ")
        for y in sorted({now.year - 1, now.year}):
            for e in _espn_year(slug, y):
                if e["status"]["type"]["state"] == "post" and e["date"] >= since and e["id"] not in have:
                    have.add(e["id"])
                    todo.append((slug, lg, e["id"], e["date"]))
    log(f"  jugadores: {len(todo)} partidos nuevos por descargar")

    def one(t):
        slug, lg, eid, date = t
        j = _espn(f"{slug}/summary", event=eid)
        return summarize_event(j, slug, lg, eid, date) if j else None

    with ThreadPoolExecutor(workers) as ex:
        for res in ex.map(one, todo):
            if res:
                cache["matches"].append(res)
    # conservar solo la ventana útil
    oldest = (now - timedelta(days=max(d for *_, d in PLAYER_TARGETS))).strftime("%Y-%m-%d")
    cache["matches"] = [m for m in cache["matches"] if m["date"] >= oldest]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


if __name__ == "__main__":
    fetch_all()
    fetch_players()

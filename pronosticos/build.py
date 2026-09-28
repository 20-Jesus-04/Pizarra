"""Pipeline completo: (descarga) -> 6 modelos -> ensamble -> mercados -> auditoría -> fijas -> historial -> web.

Uso:
    python -m pronosticos.build            # descarga datos frescos y genera docs/index.html
    python -m pronosticos.build --offline  # usa la caché de data/ sin descargar
    python -m pronosticos.build --recalibrar   # fuerza el backtest semanal del ensamble
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .config import LEAGUES, DAYS_AHEAD, MIN_EDGE, MIN_PROB, KELLY_FRACTION
from .data import load_all, load_results, ES_NAMES
from .markets import all_markets
from .stats import team_profile, head_to_head, standings, rate_model
from .players import load_player_data, squad_projection, compact, PKEYS, team_stat_markets, team_rate_predictor
from .picks import PICK_LABELS, get as _get
from . import arbitros, auditor, ensamble, fijas, historial

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ev_row(market, selection, p, odds, fair_source=""):
    if not odds or not p:
        return None
    ev = p * odds - 1
    b = odds - 1
    kelly = max(0.0, (p * b - (1 - p)) / b) * KELLY_FRACTION if b > 0 else 0
    return {"mercado": market, "seleccion": selection, "prob": round(p, 4), "cuota": odds,
            "cuota_justa": round(1 / p, 2), "ev": round(ev, 4), "kelly": round(kelly, 4),
            "valor": bool(ev > MIN_EDGE and p >= MIN_PROB)}


def ah_ev(mk, line_home, odds_h, odds_a):
    """EV de hándicap asiático local/visita usando la tabla gana/devuelve/pierde."""
    out = []
    key = f"{line_home:+g}"
    t = mk["handicap_asiatico_local"].get(key)
    if t is None:
        return out
    for sel, odds, (w, p, l) in (("local", odds_h, (t["gana"], t["devuelve"], t["pierde"])),
                                 ("visita", odds_a, (t["pierde"], t["devuelve"], t["gana"]))):
        if not odds:
            continue
        ev = w * (odds - 1) - l
        pw = w / max(w + l, 1e-9)
        b = odds - 1
        kelly = max(0.0, (pw * b - (1 - pw)) / b) * KELLY_FRACTION * (w + l)
        lbl = f"{sel} {line_home:+g}" if sel == "local" else f"{sel} {-line_home:+g}"
        out.append({"mercado": "Hándicap asiático", "seleccion": lbl, "prob": round(w, 4), "prob_devolucion": round(p, 4),
                    "cuota": odds, "cuota_justa": round((w + l) / w + 0, 2) if w > 0 else None,
                    "ev": round(ev, 4), "kelly": round(kelly, 4), "valor": bool(ev > MIN_EDGE and w >= MIN_PROB)})
    return out


def best_alternatives(mk, curva=None, lo=0.62, hi=0.93, n=5):
    cands = []
    for fam, path, label in PICK_LABELS:
        p = _get(mk, path)
        if p is None or not (lo <= p <= hi):
            continue
        # puntuación: probabilidad, pero premiando selecciones con cuota justa más alta (más informativas)
        score = p * (1 / p) ** 0.35
        cands.append({"familia": fam, "clave": "|".join(path), "seleccion": label, "prob": round(p, 4),
                      "prob_calibrada": round(ensamble.calibrate_prob(p, curva), 4), "cuota_justa": round(1 / p, 2),
                      "_s": score, "nivel": "alta" if p >= 0.78 else "media"})
    cands.sort(key=lambda x: -x["_s"])
    out, fams = [], set()
    for c in cands:
        if c["familia"] in fams:
            continue
        fams.add(c["familia"])
        c.pop("_s")
        out.append(c)
        if len(out) == n:
            break
    return out


def _normalize(rows):
    """Reescala ataque/defensa para que el equipo medio de la temporada actual valga 1.00."""
    if not rows:
        return rows
    ga = float(np.exp(np.mean([np.log(r["attack"]) for r in rows])))
    gd = float(np.exp(np.mean([np.log(r["defense"]) for r in rows])))
    for r in rows:
        r["attack"] = round(r["attack"] / ga, 3)
        r["defense"] = round(r["defense"] / gd, 3)
    return rows


def top_scorers(P, code, now, n=10):
    """Goleadores de la temporada en curso (desde ESPN)."""
    ts = pd.Timestamp(now).tz_localize(None)
    if code == "PER":
        start = pd.Timestamp(ts.year, 1, 1)
    elif code == "INT":
        start = ts - pd.Timedelta(days=365)
    else:
        start = pd.Timestamp(ts.year if ts.month >= 7 else ts.year - 1, 7, 1)
    d = P[(P.lg == code) & (P.date >= start)]
    if d.empty:
        return []
    g = d.groupby("pid").agg(nombre=("name", "last"), equipo=("team", "last"), goles=("g", "sum"), asist=("a", "sum"),
                              tiros=("sh", "sum"), arco=("sot", "sum"), pj=("mid", "nunique"), min=("mins", "sum"))
    g = g[g.goles > 0].sort_values(["goles", "asist", "min"], ascending=[False, False, True]).head(n)
    return [{k: (int(v) if isinstance(v, (np.integer, int, float)) and k not in ("nombre", "equipo") else v)
             for k, v in r.items()} for r in g.to_dict("records")]


def season_of(df):
    s = str(df.season.iloc[-1])
    return s[:4] if df["div"].iloc[0] in ("PER", "INT") else s


def lima_day(iso: str) -> str:
    """Fecha (AAAA-MM-DD) en hora de Lima, para topes diarios."""
    return (pd.Timestamp(iso).tz_convert("America/Lima") if pd.Timestamp(iso).tzinfo else pd.Timestamp(iso)).strftime("%Y-%m-%d")


def referee_tables(leagues, rates_y, T):
    """Tabla de árbitros por liga: football-data si trae el árbitro (Inglaterra), si no las fichas de ESPN."""
    out = {}
    for code, df in leagues.items():
        rows = arbitros.fd_rows(df, rates_y.get(code)) if code != "INT" else None
        if rows is None or len(rows) < 100:
            yp = team_rate_predictor(T, code, "yc") if T is not None else None
            rows = arbitros.espn_rows(T, code, yp)
        out[code] = arbitros.factors(rows) if len(rows) else {}
    return out


def run(offline=False, backtest=True, out_dir=None, recalibrar=False):
    if not offline:
        from .fetch import fetch_all, fetch_players
        print("Descargando datos…")
        fetch_all()
        print("Descargando estadísticas de jugadores…")
        fetch_players()
    leagues, upcoming, fetched = load_all()
    P, T = load_player_data()
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=DAYS_AHEAD)

    # 1) calibración semanal del ensamble (backtest de los 6 modelos, pesos, curva, subtipos, árbitros)
    cache = ensamble.load_cache()
    if recalibrar or not ensamble.cache_is_fresh(cache, now) and (backtest or cache is None):
        print("Calibrando el ensamble (backtest walk-forward de los 6 modelos)…")
        cache = ensamble.calibrar(leagues, now, P=P if backtest else None)
        ensamble.save_cache(cache)
    else:
        print(f"Usando la calibración del {cache['fecha'][:10]}")

    # 2) modelos ajustados con todos los datos de hoy
    print("Ajustando los 6 modelos…")
    motor = ensamble.Motor(leagues, cache)
    out = {"n_actuaciones": int(len(P)) if P is not None else 0, "pkeys": PKEYS, "generado": now.isoformat(),
           "datos_actualizados": fetched, "ligas": {}, "partidos": [],
           "config": {"min_ventaja": MIN_EDGE, "min_prob": MIN_PROB, "kelly": KELLY_FRACTION, "dias": DAYS_AHEAD}}
    rates_c, rates_y = {}, {}
    for code, df in leagues.items():
        m = motor.m[code]["dc"]
        rates_c[code] = rate_model(df, "hc", "ac")
        rates_y[code] = rate_model(df, "hy", "ay")
        cur = season_of(df)
        ratings = sorted(m.ratings_table(), key=lambda r: -(r["attack"] / r["defense"]))
        if code == "INT":
            recent = df[df.date >= df.date.max() - pd.Timedelta(days=730)]
            cur_teams = set(recent.home) | set(recent.away)
        else:
            cur_teams = set(df[df.season.astype(str).str.startswith(cur)].home)
        info = {
            **LEAGUES[code], "code": code, "temporada": cur, "partidos_historicos": int(len(df)),
            "desde": df.date.min().strftime("%Y-%m-%d"), "hasta": df.date.max().strftime("%Y-%m-%d"),
            "ventaja_local": round(float(np.exp(m.home)), 3), "rho": round(float(m.rho), 3),
            "goles_prom": round(float((df.hg + df.ag)[df.season.astype(str).str.startswith(cur)].mean()), 2),
            "tabla": [] if code == "INT" else standings(df, cur),
            "ratings": _normalize([r for r in ratings if r["team"] in cur_teams])[:80 if code == "INT" else None],
        }
        if P is not None:
            info["goleadores"] = top_scorers(P, code, now)
        if cache.get("ligas", {}).get(code):
            info["backtest"] = cache["ligas"][code]
        if cache.get("validacion_jugadores", {}).get(code):
            info["validacion_jugadores"] = cache["validacion_jugadores"][code]
        out["ligas"][code] = info
    ref_tabs = referee_tables(leagues, rates_y, T)
    curva = cache.get("curva")

    # 3) cada próximo partido
    for u in upcoming:
        dt = pd.Timestamp(u["date"]).to_pydatetime()
        if dt > horizon or dt < now - timedelta(hours=3):
            continue
        code = u["league"]
        df = leagues[code]
        cur = season_of(df)
        neutral = bool(u.get("neutral"))
        o = u.get("odds")
        pred = motor.predict(code, u["home"], u["away"], neutral, u["date"], o)
        comb = motor.combine(pred)
        lam, mu = motor.rates_for(pred, comb)
        dc = pred["dc"]
        market = None
        if "mercado" in pred["modelos"]:
            mk_ = pred["modelos"]["mercado"]
            market = {"1": round(mk_["1"], 4), "X": round(mk_["X"], 4), "2": round(mk_["2"], 4),
                      "over": round(mk_["o25"], 4) if "o25" in mk_ else None,
                      "margen_casa": round(float(sum(1 / np.array([o["H"], o["D"], o["A"]])) - 1), 4)}
        # árbitro: multiplica las tarjetas esperadas
        arb = arbitros.lookup(ref_tabs.get(code, {}), u.get("arbitro")) if u.get("arbitro") else None
        fac = arb["factor"] if arb else 1.0
        corners = rates_c[code](u["home"], u["away"]) if rates_c[code] else None
        cards = rates_y[code](u["home"], u["away"]) if rates_y[code] else None
        if cards is None and T is not None:  # Liga 1 y selecciones: tarjetas desde ESPN
            yp = team_rate_predictor(T, code, "yc")
            if yp:
                cards = (yp(u["home_espn"], u["away_espn"], True, neutral), yp(u["away_espn"], u["home_espn"], False, neutral))
        if corners is None and T is not None:
            cp = team_rate_predictor(T, code, "cor")
            if cp:
                corners = (cp(u["home_espn"], u["away_espn"], True, neutral), cp(u["away_espn"], u["home_espn"], False, neutral))
        cards_base = cards
        if cards:
            cards = (cards[0] * fac, cards[1] * fac)
        if arb:
            arb = {**arb, "tarjetas_sin_arbitro": round(sum(cards_base), 2) if cards_base else None,
                   "tarjetas_con_arbitro": round(sum(cards), 2) if cards else None}
        mk = all_markets(lam, mu, dc.rho, dc.ht_frac, corners, cards)
        jugadores = {"local": [], "visita": []}
        if T is not None:
            mk.update(team_stat_markets(T, code, u["home_espn"], u["away_espn"], neutral, yc_factor=fac))
        if P is not None:
            shp = team_rate_predictor(T, code, "sh")
            sh_h = shp(u["home_espn"], u["away_espn"], True, neutral) if shp else None
            sh_a = shp(u["away_espn"], u["home_espn"], False, neutral) if shp else None
            ts = pd.Timestamp(now).tz_localize(None)
            jugadores = {"local": compact(squad_projection(P, code, u["home_espn"], u["away_espn"], ts, lam, sh_h)),
                         "visita": compact(squad_projection(P, code, u["away_espn"], u["home_espn"], ts, mu, sh_a))}

        n_h = int(((df.home == u["home"]) | (df.away == u["home"])).sum())
        n_a = int(((df.home == u["away"]) | (df.away == u["away"])).sum())
        audit = auditor.revisar(mk, comb, pred, lam, mu, n_h, n_a, o, arb)
        value = []
        if o:
            for sel, key in (("1", "H"), ("X", "D"), ("2", "A")):
                r = ev_row("1X2", {"1": "Local", "X": "Empate", "2": "Visita"}[sel], mk["1x2"][sel], o.get(key))
                if r: value.append(r)
            ln = o.get("ou_line")
            if ln is not None and str(float(ln)) in mk["goles_totales"]:
                t = mk["goles_totales"][str(float(ln))]
                for sel, key in (("over", "over"), ("under", "under")):
                    r = ev_row("Goles totales", f"{'Más' if sel == 'over' else 'Menos'} de {ln}", t[sel], o.get(key))
                    if r: value.append(r)
            if o.get("ah_line") is not None:
                value += ah_ev(mk, float(o["ah_line"]), o.get("ah_home"), o.get("ah_away"))
            if audit["estado"] == "bloqueado":
                for r in value:
                    r["valor"] = False

        own = comb["propio"]
        disagreement = None
        if market:
            disagreement = round(float(sum(abs(own[k] - market[k]) for k in ("1", "X", "2")) / 2), 4)
        conf = min(1.0, min(n_h, n_a) / 60) * (1 - min(disagreement or 0, 0.3))
        mods = pred["modelos"]
        out["partidos"].append({
            "id": u["id"], "liga": code, "fecha": u["date"], "estadio": u.get("venue"),
            "competicion": u.get("competicion") or LEAGUES[code]["name"], "neutral": neutral,
            "local": u["home_display"], "visita": u["away_display"], "local_key": u["home"], "visita_key": u["away"],
            "cuotas": o, "mercado": market,
            "modelo_puro": {"1x2": {k: round(v, 4) for k, v in own.items()}, "xg_home": round(pred["rates"]["dixon_coles"][0], 3),
                            "xg_away": round(pred["rates"]["dixon_coles"][1], 3)},
            "modelos": {"lista": [{"clave": k, "1": round(mods[k]["1"], 4), "X": round(mods[k]["X"], 4), "2": round(mods[k]["2"], 4),
                                   "o25": round(mods[k]["o25"], 4) if "o25" in mods[k] else None,
                                   "peso": comb["pesos"].get(k, 0.0), "peso_o25": comb["pesos_o25"].get(k)}
                                  for k in ensamble.MODELOS if k in mods],
                        "elo": [round(pred["elo"][0]), round(pred["elo"][1])]},
            "arbitro": arb,
            "auditoria": audit,
            "mercados": mk, "valor": sorted(value, key=lambda r: -r["ev"]),
            "alternativas": best_alternatives(mk, curva),
            "confianza": round(conf, 2), "desacuerdo_modelo_mercado": disagreement,
            "perfil_local": team_profile(df, u["home"], cur), "perfil_visita": team_profile(df, u["away"], cur),
            "h2h": head_to_head(df, u["home"], u["away"]),
            "jugadores": jugadores,
            "forma_espn": u.get("espn_form"), "record_espn": u.get("espn_record"),
        })
    out["partidos"].sort(key=lambda p: p["fecha"])
    # nombres en español para selecciones
    tr = lambda n: ES_NAMES.get(n, n)
    if "INT" in out["ligas"]:
        for r in out["ligas"]["INT"]["ratings"]:
            r["team"] = tr(r["team"])
    for p in out["partidos"]:
        if p["liga"] != "INT":
            continue
        for k in ("perfil_local", "perfil_visita"):
            for m in p[k]["ultimos"]:
                m["rival"] = tr(m["rival"])
        for m in p["h2h"]["partidos"]:
            m["local"], m["visita"] = tr(m["local"]), tr(m["visita"])

    # 4) historial: liquidar lo jugado, elegir fijas, registrar lo nuevo (antes del inicio)
    hist = historial.load()
    n_liq = historial.liquidar(hist, load_results(), now)
    res = historial.metricas(hist, now, lima_day)
    estado = {"liquidados_30d": res.get("liquidados_30d", 0), "fijas_30d_n": (res.get("fijas_30d") or {}).get("n", 0),
              "fijas_30d_acierto": (res.get("fijas_30d") or {}).get("acierto")}
    out["fijas"] = fijas.seleccionar(out["partidos"], cache, historial.subtipos_reales(hist), estado, now, lima_day)
    fset = {}
    for f in out["fijas"]["lista"]:
        fset.setdefault(f["id"], []).append(f["clave"])
    for p in out["partidos"]:
        p["fijas"] = fset.get(p["id"], [])
    n_reg = historial.registrar(hist, out["partidos"], out["fijas"]["lista"], now)
    historial.save(hist)
    out["resultados"] = historial.metricas(hist, now, lima_day)
    print(f"Historial: {n_reg} predicciones registradas, {n_liq} liquidadas, {len(out['fijas']['lista'])} fijas")

    # 5) transparencia: cómo está calibrado el motor
    out["metodologia"] = {k: cache.get(k) for k in ("fecha", "pesos", "evaluacion", "calibracion", "arbitros", "picks_simulados",
                                                    "acierto_simulado_70", "nombres")}
    out["metodologia"]["arbitros_conocidos"] = {c: len(t) for c, t in ref_tabs.items()}
    write_web(out, out_dir)
    return out


def write_web(out, out_dir=None):
    """Inyecta los datos en la web (React ya compilada en web/app.html) y escribe:
    docs/index.html (página completa, para GitHub Pages o abrir en el PC) y docs/artifact.html (fragmento)."""
    import re
    out_dir = out_dir or os.path.join(ROOT, "docs")
    os.makedirs(out_dir, exist_ok=True)
    payload = json.dumps(out, ensure_ascii=False, default=_json_default)
    with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
        f.write(payload)
    with open(os.path.join(ROOT, "web", "app.html"), encoding="utf-8") as f:
        app = f.read()
    safe = payload.replace("</", "<\\/")
    app = app.replace("__PIZARRA_DATA__", safe.replace("\\", "\\\\") if False else safe, 1)
    # limpiar envoltorio del bundle
    for pat in (r"<!DOCTYPE html>", r"<!doctype html>", r"<html[^>]*>", r"</html>", r"<head>", r"</head>", r"<body>", r"</body>",
                r"<meta[^>]*>", r"<title>[^<]*</title>"):
        app = re.sub(pat, "", app, flags=re.I)
    head = ('<title>Pizarra de Pronósticos</title>\n'
            '<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@100..125,500..900'
            '&family=Public+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">\n')
    with open(os.path.join(out_dir, "artifact.html"), "w", encoding="utf-8") as f:
        f.write(head + app)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write('<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                + head + "</head>\n<body>\n" + app + "\n</body>\n</html>\n")
    print(f"Listo: {len(out['partidos'])} partidos -> {out_dir}/index.html")


def _json_default(o):
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    return str(o)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="no descargar, usar data/ existente")
    ap.add_argument("--sin-backtest", action="store_true", help="no recalibrar aunque la calibración tenga más de 6 días")
    ap.add_argument("--recalibrar", action="store_true", help="forzar el backtest y la calibración del ensamble")
    ap.add_argument("--solo-web", action="store_true", help="regenerar solo la página desde docs/data.json")
    a = ap.parse_args()
    if a.solo_web:
        with open(os.path.join(ROOT, "docs", "data.json"), encoding="utf-8") as f:
            write_web(json.load(f))
    else:
        run(offline=a.offline, backtest=not a.sin_backtest, recalibrar=a.recalibrar)

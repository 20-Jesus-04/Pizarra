"""Pipeline completo: (descarga) -> modelo -> mercados -> alternativas -> backtest -> web.

Uso:
    python -m pronosticos.build            # descarga datos frescos y genera docs/index.html
    python -m pronosticos.build --offline  # usa la caché de data/ sin descargar
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .config import LEAGUES, INT_XI, DAYS_AHEAD, MARKET_WEIGHT, MIN_EDGE, MIN_PROB, KELLY_FRACTION
from .data import load_all, ES_NAMES
from .model import DixonColes, score_matrix
from .markets import all_markets
from .stats import team_profile, head_to_head, standings, rate_model
from .backtest import walk_forward, evaluate, devig
from .players import load_player_data, squad_projection, compact, PKEYS, team_stat_markets, team_rate_predictor, validate_players

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ------------------------------------------------------------------ mercado -> goles esperados implícitos
def implied_rates(pH, pA, p_over, line, rho, lam0, mu0):
    """Busca (lambda, mu) cuya matriz reproduce las probabilidades del mercado."""
    def loss(x):
        lam, mu = np.exp(x)
        M = score_matrix(lam, mu, rho)
        i, j = np.indices(M.shape)
        e = (M[i > j].sum() - pH) ** 2 + (M[i < j].sum() - pA) ** 2
        if p_over is not None:
            e += (M[(i + j) > line].sum() - p_over) ** 2
        return e
    r = minimize(loss, np.log([lam0, mu0]), method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-9})
    return tuple(np.exp(r.x))


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


PICK_LABELS = [
    # (familia, ruta, etiqueta)
    ("dc", ("doble_oportunidad", "1X"), "Doble oportunidad 1X (local o empate)"),
    ("dc", ("doble_oportunidad", "X2"), "Doble oportunidad X2 (visita o empate)"),
    ("dc", ("doble_oportunidad", "12"), "Doble oportunidad 12 (no hay empate)"),
    ("res", ("1x2", "1"), "Gana el local"),
    ("res", ("1x2", "2"), "Gana la visita"),
    ("dnb", ("empate_no_apuesta", "1"), "Empate no apuesta: local"),
    ("dnb", ("empate_no_apuesta", "2"), "Empate no apuesta: visita"),
    ("ou", ("goles_totales", "1.5", "over"), "Más de 1.5 goles"),
    ("ou", ("goles_totales", "2.5", "over"), "Más de 2.5 goles"),
    ("ou", ("goles_totales", "2.5", "under"), "Menos de 2.5 goles"),
    ("ou", ("goles_totales", "3.5", "under"), "Menos de 3.5 goles"),
    ("ou", ("goles_totales", "4.5", "under"), "Menos de 4.5 goles"),
    ("btts", ("ambos_marcan", "si"), "Ambos marcan: Sí"),
    ("btts", ("ambos_marcan", "no"), "Ambos marcan: No"),
    ("tl", ("goles_local", "0.5", "over"), "Local marca al menos 1 gol"),
    ("tl", ("goles_local", "1.5", "over"), "Local marca 2 o más"),
    ("tv", ("goles_visita", "0.5", "over"), "Visita marca al menos 1 gol"),
    ("tv", ("goles_visita", "1.5", "under"), "Visita marca 1 o menos"),
    ("tl2", ("goles_local", "1.5", "under"), "Local marca 1 o menos"),
    ("ht", ("primer_tiempo_goles", "0.5", "over"), "Hay gol en el 1er tiempo"),
    ("ht", ("primer_tiempo_goles", "1.5", "under"), "Menos de 1.5 goles en el 1er tiempo"),
    ("ah", ("handicap_asiatico_local", "-1", "gana"), "Hándicap asiático local -1"),
    ("ah", ("handicap_asiatico_local", "+1", "pierde"), "Hándicap asiático visita -1"),
    ("co", ("corners", "total", "8.5", "over"), "Más de 8.5 córners"),
    ("co", ("corners", "total", "11.5", "under"), "Menos de 11.5 córners"),
    ("ca", ("tarjetas", "total", "2.5", "over"), "Más de 2.5 tarjetas"),
]


def _get(d, path):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def best_alternatives(mk, lo=0.62, hi=0.93, n=5):
    cands = []
    for fam, path, label in PICK_LABELS:
        p = _get(mk, path)
        if p is None or not (lo <= p <= hi):
            continue
        # puntuación: probabilidad, pero premiando selecciones con cuota justa más alta (más informativas)
        score = p * (1 / p) ** 0.35
        cands.append({"familia": fam, "seleccion": label, "prob": round(p, 4), "cuota_justa": round(1 / p, 2),
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


def run(offline=False, backtest=True, out_dir=None):
    if not offline:
        from .fetch import fetch_all
        print("Descargando datos…")
        fetch_all()
    if not offline:
        from .fetch import fetch_players
        print("Descargando estadísticas de jugadores…")
        fetch_players()
    leagues, upcoming, fetched = load_all()
    P, T = load_player_data()
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=DAYS_AHEAD)
    out = {"n_actuaciones": int(len(P)) if P is not None else 0, "pkeys": PKEYS, "generado": now.isoformat(), "datos_actualizados": fetched, "ligas": {}, "partidos": [], "config": {
        "peso_mercado": MARKET_WEIGHT, "min_ventaja": MIN_EDGE, "min_prob": MIN_PROB, "kelly": KELLY_FRACTION, "dias": DAYS_AHEAD}}

    models, rates_c, rates_y = {}, {}, {}
    for code, df in leagues.items():
        print(f"Ajustando modelo {code} ({len(df)} partidos)…")
        mkw = dict(xi=INT_XI, home_shrink=30.0, promoted_prior=False) if code == "INT" else {}
        m = DixonColes(**mkw).fit(df)
        models[code] = m
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
        if P is not None and backtest:
            print(f"  validando proyecciones de jugadores {code}…")
            info["validacion_jugadores"] = validate_players(P, code)
        if backtest:
            seasons = [str(now.year - 1), str(now.year)] if code in ("PER", "INT") else sorted(set(df.season))[-2:]
            bt = walk_forward(df, seasons, **mkw)
            info["backtest"] = evaluate(bt)
            info["backtest"]["temporadas"] = seasons
        out["ligas"][code] = info

    for u in upcoming:
        dt = pd.Timestamp(u["date"]).to_pydatetime()
        if dt > horizon or dt < now - timedelta(hours=3):
            continue
        code = u["league"]
        df, m = leagues[code], models[code]
        cur = season_of(df)
        lam_m, mu_m = m.rates(u["home"], u["away"], neutral=bool(u.get("neutral")))
        model_mk = all_markets(lam_m, mu_m, m.rho, m.ht_frac)
        lam, mu = lam_m, mu_m
        o = u.get("odds")
        market = None
        if o and o.get("H") and o.get("D") and o.get("A"):
            pm = devig(np.array([o["H"], o["D"], o["A"]]))
            p_over = None
            if o.get("over") and o.get("under") and o.get("ou_line"):
                p_over = float(devig(np.array([o["over"], o["under"]]))[0])
            lam_k, mu_k = implied_rates(pm[0], pm[2], p_over, o.get("ou_line") or 2.5, m.rho, lam_m, mu_m)
            w = MARKET_WEIGHT
            lam = float(np.exp((1 - w) * np.log(lam_m) + w * np.log(lam_k)))
            mu = float(np.exp((1 - w) * np.log(mu_m) + w * np.log(mu_k)))
            margin = float(sum(1 / np.array([o["H"], o["D"], o["A"]])) - 1)
            market = {"1": round(float(pm[0]), 4), "X": round(float(pm[1]), 4), "2": round(float(pm[2]), 4),
                      "over": round(p_over, 4) if p_over else None, "margen_casa": round(margin, 4),
                      "xg_home": round(lam_k, 3), "xg_away": round(mu_k, 3)}
        corners = rates_c[code](u["home"], u["away"]) if rates_c[code] else None
        cards = rates_y[code](u["home"], u["away"]) if rates_y[code] else None
        if cards is None and T is not None:  # Liga 1 y selecciones: tarjetas desde ESPN
            yp = team_rate_predictor(T, code, "yc")
            if yp:
                cards = (yp(u["home_espn"], u["away_espn"], True, u.get("neutral")), yp(u["away_espn"], u["home_espn"], False, u.get("neutral")))
        if corners is None and T is not None:
            cp = team_rate_predictor(T, code, "cor")
            if cp:
                corners = (cp(u["home_espn"], u["away_espn"], True, u.get("neutral")), cp(u["away_espn"], u["home_espn"], False, u.get("neutral")))
        mk = all_markets(lam, mu, m.rho, m.ht_frac, corners, cards)
        jugadores = {"local": [], "visita": []}
        if T is not None:
            mk.update(team_stat_markets(T, code, u["home_espn"], u["away_espn"], bool(u.get("neutral"))))
        if P is not None:
            shp = team_rate_predictor(T, code, "sh")
            sh_h = shp(u["home_espn"], u["away_espn"], True, u.get("neutral")) if shp else None
            sh_a = shp(u["away_espn"], u["home_espn"], False, u.get("neutral")) if shp else None
            ts = pd.Timestamp(now).tz_localize(None)
            jugadores = {"local": compact(squad_projection(P, code, u["home_espn"], u["away_espn"], ts, lam, sh_h)),
                         "visita": compact(squad_projection(P, code, u["away_espn"], u["home_espn"], ts, mu, sh_a))}

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

        # confianza: cantidad de datos de ambos equipos y acuerdo modelo-mercado
        n_h = int(((df.home == u["home"]) | (df.away == u["home"])).sum())
        n_a = int(((df.home == u["away"]) | (df.away == u["away"])).sum())
        disagreement = None
        if market:
            disagreement = round(float(np.abs(np.array([model_mk["1x2"][k] for k in "1X2"]) -
                                              np.array([market[k] for k in "1X2"])).sum() / 2), 4)
        conf = min(1.0, min(n_h, n_a) / 60) * (1 - min(disagreement or 0, 0.3))
        out["partidos"].append({
            "id": u["id"], "liga": code, "fecha": u["date"], "estadio": u.get("venue"),
            "competicion": u.get("competicion") or LEAGUES[code]["name"], "neutral": bool(u.get("neutral")),
            "local": u["home_display"], "visita": u["away_display"], "local_key": u["home"], "visita_key": u["away"],
            "cuotas": o, "mercado": market, "modelo_puro": {"1x2": model_mk["1x2"], "xg_home": round(lam_m, 3), "xg_away": round(mu_m, 3),
                                                            "over25": model_mk["goles_totales"]["2.5"]["over"],
                                                            "btts": model_mk["ambos_marcan"]["si"]},
            "mercados": mk, "valor": sorted(value, key=lambda r: -r["ev"]),
            "alternativas": best_alternatives(mk),
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
    ap.add_argument("--sin-backtest", action="store_true")
    ap.add_argument("--solo-web", action="store_true", help="regenerar solo la página desde docs/data.json")
    a = ap.parse_args()
    if a.solo_web:
        with open(os.path.join(ROOT, "docs", "data.json"), encoding="utf-8") as f:
            write_web(json.load(f))
    else:
        run(offline=a.offline, backtest=not a.sin_backtest)

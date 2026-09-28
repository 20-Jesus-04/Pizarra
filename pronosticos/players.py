"""Estadísticas y mercados de jugadores (goles, asistencias, tiros, tiros al arco, faltas, tarjetas)
y estadísticas de equipo por partido (tiros, tiros al arco, faltas, fueras de juego, tarjetas) desde ESPN.

Formato de entrada (data/jugadores.json -> {"matches": [...]}), un registro por partido:
  {id, slug, lg, comp, date, ref, teams:[{id,name,ha,st:{...}}],
   players:[[lado(0 local/1 visita), athlete_id, nombre, pos, titular, minutos, goles, asist, tiros, al_arco,
             faltas_com, faltas_rec, amarillas, rojas, offsides, atajadas], ...]}
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
from scipy.stats import nbinom, poisson

from .fetch import DATA_DIR

PCOLS = ["side", "pid", "name", "pos", "starter", "mins", "g", "a", "sh", "sot", "fc", "fs", "yc", "rc", "off", "sv"]
STATS = ["g", "a", "sh", "sot", "fc", "fs", "yc", "off"]
DECAY = 0.004          # vida media ~6 meses para rendimiento de jugadores
SHRINK = 3.0           # partidos de 90' "ficticios" con el promedio de su posición
NB_SIZE = {"sh": 4.0, "sot": 6.0, "fc": 6.0, "fs": 6.0}   # sobredispersión (binomial negativa)
POS_ES = {"G": "POR", "D": "DEF", "M": "MED", "F": "DEL"}


def load_player_data():
    path = os.path.join(DATA_DIR, "jugadores.json")
    if not os.path.exists(path):
        return None, None
    with open(path, encoding="utf-8") as f:
        matches = json.load(f)["matches"]
    prow, trow = [], []
    for m in matches:
        dt = pd.to_datetime(m["date"]).tz_localize(None)
        teams = sorted(m["teams"], key=lambda t: 0 if t["ha"] == "home" else 1)
        if len(teams) != 2:
            continue
        names = [t["name"] for t in teams]
        for side, t in enumerate(teams):
            st = t["st"]
            num = lambda k: pd.to_numeric(st.get(k), errors="coerce")
            trow.append({"mid": m["id"], "lg": m["lg"], "date": dt, "team": t["name"], "opp": names[1 - side], "home": side == 0,
                         "sh": num("totalShots"), "sot": num("shotsOnTarget"), "fc": num("foulsCommitted"), "yc": num("yellowCards"),
                         "rc": num("redCards"), "off": num("offsides"), "cor": num("wonCorners"), "poss": num("possessionPct"),
                         "sv": num("saves"), "tk": num("totalTackles"), "pas": num("totalPasses"), "ref": m.get("ref")})
        for p in m["players"]:
            r = dict(zip(PCOLS, p))
            r.update({"mid": m["id"], "lg": m["lg"], "date": dt, "team": names[r["side"]], "opp": names[1 - r["side"]],
                      "comp": m.get("comp")})
            prow.append(r)
    P = pd.DataFrame(prow)
    T = pd.DataFrame(trow)
    if P.empty:
        return None, None
    P["pos"] = P["pos"].map(pos_group)
    # suplentes: usar la posición más habitual del jugador cuando fue titular
    known = P[P.pos.notna()].groupby("pid").pos.agg(lambda x: x.value_counts().index[0])
    P["pos"] = P["pos"].fillna(P.pid.map(known)).fillna("M")
    return P.sort_values("date"), T.sort_values("date")


def pos_group(code: str):
    c = (code or "").upper()
    if c in ("", "SUB"):
        return None
    if c == "G":
        return "G"
    if c.startswith(("CD", "LB", "RB", "SW", "D", "LWB", "RWB")):
        return "D"
    if c.startswith(("CF", "F", "LF", "RF", "RCF", "LCF", "ST")):
        return "F"
    if c.startswith(("AM", "LM", "RM", "CM", "DM", "M", "RCM", "LCM", "LW", "RW")):
        return "M"
    return "M"


# ------------------------------------------------------------------ tasas de equipo (tiros, faltas, ...)
def team_rate_predictor(T: pd.DataFrame, lg: str, col: str, ref_date=None):
    d = T[(T.lg == lg)].dropna(subset=[col])
    if ref_date is not None:
        d = d[d.date < ref_date]
    if len(d) < 40:
        return None
    ref = d.date.max() + pd.Timedelta(days=1) if ref_date is None else pd.Timestamp(ref_date)
    w = np.exp(-0.003 * (ref - d.date).dt.days.values)
    mu_h = np.average(d[col][d.home], weights=w[d.home.values])
    mu_a = np.average(d[col][~d.home], weights=w[~d.home.values])
    base = (mu_h + mu_a) / 2
    k = 5.0
    att, dfn = {}, {}
    for t, g in d.groupby("team"):
        ww = w[d.team.values == t]
        adj = g[col].values / np.where(g.home.values, mu_h, mu_a)
        att[t] = ((ww * adj).sum() + k) / (ww.sum() + k)
    for t, g in d.groupby("opp"):
        ww = w[d.opp.values == t]
        adj = g[col].values / np.where(g.home.values, mu_h, mu_a)
        dfn[t] = ((ww * adj).sum() + k) / (ww.sum() + k)

    def predict(team, opp, is_home=True, neutral=False):
        mu = base if neutral else (mu_h if is_home else mu_a)
        return float(mu * att.get(team, 1.0) * dfn.get(opp, 1.0))
    return predict


def team_stat_markets(T, lg, home, away, neutral=False):
    """Mercados de equipo: tiros, tiros al arco, faltas, fueras de juego, tarjetas (según ESPN)."""
    out = {}
    specs = [("sh", "tiros", (19.5, 22.5, 24.5, 26.5, 28.5)), ("sot", "tiros_al_arco", (6.5, 7.5, 8.5, 9.5, 10.5)),
             ("fc", "faltas", (19.5, 21.5, 23.5, 25.5)), ("off", "fueras_de_juego", (2.5, 3.5, 4.5)),
             ("yc", "amarillas", (2.5, 3.5, 4.5, 5.5))]
    for col, name, lines in specs:
        pr = team_rate_predictor(T, lg, col)
        if pr is None:
            continue
        eh, ea = pr(home, away, True, neutral), pr(away, home, False, neutral)
        tot = eh + ea
        size = NB_SIZE.get(col, 8.0) * 3
        dist = lambda m: nbinom(size, size / (size + m))
        # líneas centradas en el valor esperado
        c = round(tot) + 0.5
        lines = sorted(set([c - 2, c - 1, c, c + 1, c + 2]))
        out[name] = {"esperado_local": round(eh, 2), "esperado_visita": round(ea, 2), "esperado_total": round(tot, 2),
                     "total": {f"{ln:g}": {"over": round(float(1 - dist(tot).cdf(int(ln))), 4),
                                           "under": round(float(dist(tot).cdf(int(ln))), 4)} for ln in lines if ln > 0},
                     "local": {f"{ln:g}": round(float(1 - dist(eh).cdf(int(ln))), 4) for ln in [round(eh) - 0.5, round(eh) + 0.5, round(eh) + 1.5] if ln > 0},
                     "visita": {f"{ln:g}": round(float(1 - dist(ea).cdf(int(ln))), 4) for ln in [round(ea) - 0.5, round(ea) + 0.5, round(ea) + 1.5] if ln > 0}}
    return out


# ------------------------------------------------------------------ jugadores
def _pos_priors(P: pd.DataFrame, lg: str):
    d = P[P.lg == lg]
    if len(d) < 200:
        d = P
    pri = {}
    for pos, g in d.groupby("pos"):
        m = g.mins.sum() / 90
        pri[pos] = {s: g[s].sum() / m for s in STATS}
    return pri


def _nb_over(mean, line, size):
    if mean <= 0:
        return 0.0
    return float(1 - nbinom(size, size / (size + mean)).cdf(int(line)))


_IDX = {}


def _index(P):
    """Índices para acelerar: por equipo, por jugador y promedios por posición (se calculan una vez)."""
    key = id(P)
    if key not in _IDX:
        _IDX.clear()
        _IDX[key] = {"team": {t: g for t, g in P.groupby("team")}, "pid": {k: g for k, g in P.groupby("pid")},
                     "pri": {lg: _pos_priors(P, lg) for lg in P.lg.unique()}}
    return _IDX[key]


def squad_projection(P, lg, team, opp, as_of, team_lambda=None, team_shots=None, max_players=16):
    """Proyección de cada jugador para el próximo partido.
    team_lambda: goles esperados del equipo (del modelo). team_shots: tiros esperados del equipo."""
    ix = _index(P)
    d = ix["team"].get(team)
    if d is None:
        return []
    d = d[d.date < as_of]
    if d.empty:
        return []
    # últimos partidos del equipo (en cualquier competición de este grupo de datos)
    last_mids = d.drop_duplicates("mid").sort_values("date").mid.tolist()[-6:]
    recent = d[d.mid.isin(last_mids)]
    n_recent = len(last_mids)
    pri = ix["pri"].get(lg) or _pos_priors(P, lg)
    rows = []
    wts = np.linspace(0.6, 1.0, n_recent)  # más peso al último partido
    wmap = dict(zip(last_mids, wts))
    for pid, g in recent.groupby("pid"):
        pos = g.pos.iloc[-1]
        # minutos esperados: promedio ponderado de los últimos partidos (0 si no jugó)
        mins_by = {m: 0.0 for m in last_mids}
        st_by = {m: 0.0 for m in last_mids}
        for r in g.itertuples():
            mins_by[r.mid] = r.mins
            st_by[r.mid] = r.starter
        exp_min = sum(mins_by[m] * wmap[m] for m in last_mids) / sum(wts)
        start_share = sum(st_by[m] * wmap[m] for m in last_mids) / sum(wts)
        if exp_min < 12:
            continue
        # historia completa del jugador con decaimiento (incluye otras temporadas/competiciones del mismo equipo)
        h = ix["pid"][pid]
        h = h[h.date < as_of]
        w = np.exp(-DECAY * (pd.Timestamp(as_of) - h.date).dt.days.values)
        m90 = (w * h.mins.values).sum() / 90
        rates = {}
        for s in STATS:
            prior = pri.get(pos, pri.get("M"))[s]
            rates[s] = ((w * h[s].values).sum() + SHRINK * prior) / (m90 + SHRINK)
        season = h[h.date >= pd.Timestamp(as_of) - pd.Timedelta(days=330)]
        rows.append({"pid": pid, "nombre": g.name.iloc[-1], "pos": POS_ES.get(pos, pos), "_pos": pos,
                     "min_esperados": round(exp_min), "titular_prob": round(start_share, 2),
                     "rates": rates, "exp": {s: rates[s] * exp_min / 90 for s in STATS},
                     "temporada": {"pj": int(len(season)), "min": int(season.mins.sum()), "goles": int(season.g.sum()),
                                   "asist": int(season.a.sum()), "tiros": int(season.sh.sum()), "al_arco": int(season.sot.sum()),
                                   "faltas": int(season.fc.sum()), "amarillas": int(season.yc.sum()), "rojas": int(season.rc.sum())},
                     "ultimos": [{"fecha": r.date.strftime("%d/%m"), "rival": r.opp, "min": int(r.mins), "g": int(r.g), "a": int(r.a),
                                  "tiros": int(r.sh), "arco": int(r.sot), "tarj": int(r.yc)} for r in h.tail(5).iloc[::-1].itertuples()]})
    if not rows:
        return []
    # coherencia con el equipo: los tiros y goles de los jugadores suman lo esperado para el equipo
    exp_mins_total = sum(r["min_esperados"] for r in rows)
    scale_min = min(1.0, 990 / exp_mins_total) if exp_mins_total > 0 else 1.0  # 11 jugadores x 90'
    for r in rows:
        for s in STATS:
            r["exp"][s] *= scale_min
    if team_shots:
        tot = sum(r["exp"]["sh"] for r in rows)
        if tot > 0:
            f = team_shots / tot
            for r in rows:
                r["exp"]["sh"] *= f
                r["exp"]["sot"] *= f
    if team_lambda:
        tot = sum(r["exp"]["g"] for r in rows)
        if tot > 0:
            f = team_lambda * 0.97 / tot  # ~3% de goles son en contra
            for r in rows:
                r["exp"]["g"] *= f
                r["exp"]["a"] *= f * 0.95
    out = []
    for r in rows:
        e = r["exp"]
        pg, pa = 1 - np.exp(-e["g"]), 1 - np.exp(-e["a"])
        out.append({
            "nombre": r["nombre"], "pos": r["pos"], "min_esperados": r["min_esperados"], "titular_prob": r["titular_prob"],
            "esperado": {k: round(float(v), 3) for k, v in e.items()},
            "por90": {k: round(float(v), 3) for k, v in r["rates"].items()},
            "prob": {
                "marca": round(float(pg), 4), "marca_2+": round(float(1 - poisson.cdf(1, e["g"])), 4),
                "asiste": round(float(pa), 4), "gol_o_asist": round(float(1 - np.exp(-(e["g"] + e["a"]))), 4),
                "tiros_1+": round(_nb_over(e["sh"], 0, NB_SIZE["sh"]), 4), "tiros_2+": round(_nb_over(e["sh"], 1, NB_SIZE["sh"]), 4),
                "tiros_3+": round(_nb_over(e["sh"], 2, NB_SIZE["sh"]), 4),
                "arco_1+": round(_nb_over(e["sot"], 0, NB_SIZE["sot"]), 4), "arco_2+": round(_nb_over(e["sot"], 1, NB_SIZE["sot"]), 4),
                "faltas_1+": round(_nb_over(e["fc"], 0, NB_SIZE["fc"]), 4), "faltas_2+": round(_nb_over(e["fc"], 1, NB_SIZE["fc"]), 4),
                "recibe_falta_1+": round(_nb_over(e["fs"], 0, NB_SIZE["fs"]), 4),
                "tarjeta": round(float(1 - np.exp(-e["yc"])), 4),
                "offside_1+": round(float(1 - np.exp(-e["off"])), 4),
            },
            "temporada": r["temporada"], "ultimos": r["ultimos"],
        })
    out.sort(key=lambda x: (-x["min_esperados"] * (x["esperado"]["sh"] + 0.2), x["nombre"]))
    return out[:max_players]


def validate_players(P, lg, days=45, max_matches=120):
    """Validación: para los partidos de los últimos `days` días predice con datos anteriores y compara."""
    d = P[P.lg == lg]
    if d.empty:
        return None
    cut = d.date.max() - pd.Timedelta(days=days)
    test = d[d.date >= cut]
    mids = test.drop_duplicates("mid").sort_values("date").mid.tolist()[-max_matches:]
    test = test[test.mid.isin(mids)]
    recs = []
    for mid, g in test.groupby("mid"):
        as_of = g.date.iloc[0]
        for team in g.team.unique():
            opp = g[g.team == team].opp.iloc[0]
            prev = d[(d.team == team) & (d.date < as_of)].drop_duplicates("mid").tail(6).mid
            # goles recientes del equipo como aproximación a lo que el modelo esperaría (sin mirar el resultado)
            tg = d[(d.team == team) & d.mid.isin(prev)].groupby("mid").g.sum().mean() if len(prev) else None
            proj = {p["nombre"]: p for p in squad_projection(P, lg, team, opp, as_of, team_lambda=tg if tg and tg > 0 else None,
                                                              max_players=30)}
            for r in g[(g.team == team)].itertuples():
                p = proj.get(r.name)
                if not p:
                    continue
                recs.append({"pg": p["prob"]["marca"], "yg": int(r.g > 0), "ps": p["prob"]["tiros_1+"], "ys": int(r.sh > 0),
                             "pa": p["prob"]["arco_1+"], "ya": int(r.sot > 0), "pc": p["prob"]["tarjeta"], "yc": int(r.yc > 0)})
    if len(recs) < 50:
        return None
    R = pd.DataFrame(recs)
    res = {"n": len(R)}
    for k, lab in (("g", "marca"), ("s", "tiros_1+"), ("a", "arco_1+"), ("c", "tarjeta")):
        p, y = R["p" + k].values, R["y" + k].values
        base = np.full_like(p, y.mean())
        bins = []
        for lo, hi in ((0, .1), (.1, .2), (.2, .35), (.35, .5), (.5, .7), (.7, 1.01)):
            m = (p >= lo) & (p < hi)
            if m.sum() >= 15:
                bins.append({"rango": f"{int(lo*100)}-{int(min(hi,1)*100)}%", "prob_media": round(float(p[m].mean()), 3),
                             "real": round(float(y[m].mean()), 3), "n": int(m.sum())})
        res[lab] = {"brier": round(float(np.mean((p - y) ** 2)), 4), "brier_base": round(float(np.mean((base - y) ** 2)), 4),
                    "calibracion": bins}
    return res


PKEYS = ["marca", "marca_2+", "asiste", "gol_o_asist", "tiros_1+", "tiros_2+", "tiros_3+", "arco_1+", "arco_2+",
         "faltas_1+", "faltas_2+", "recibe_falta_1+", "tarjeta", "offside_1+"]


def compact(players: list) -> list:
    """Formato compacto para la web (probabilidades en milésimas)."""
    out = []
    for j in players:
        t = j["temporada"]
        out.append({"n": j["nombre"], "p": j["pos"], "m": j["min_esperados"], "t": int(round(j["titular_prob"] * 100)),
                    "q": [int(round(j["prob"][k] * 1000)) for k in PKEYS],
                    "s": [t["pj"], t["min"], t["goles"], t["asist"], t["tiros"], t["al_arco"], t["faltas"], t["amarillas"], t["rojas"]],
                    "u": " | ".join(f"{u['fecha']} vs {u['rival']}: {u['min']}' {u['g']}G {u['a']}A {u['tiros']}T/{u['arco']}AA"
                                    + (" TA" if u["tarj"] else "") for u in j["ultimos"][:4])})
    return out

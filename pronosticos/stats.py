"""Estadísticas reales: forma reciente, rendimiento local/visita, H2H, tabla y tasas de córners/tarjetas."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import XI


def _team_rows(df: pd.DataFrame, team: str) -> pd.DataFrame:
    h = df[df.home == team].assign(venue="L", opp=lambda d: d.away, gf=lambda d: d.hg, ga=lambda d: d.ag,
                                    xgf=lambda d: d.hxg, xga=lambda d: d.axg, sf=lambda d: d["hs"], sa=lambda d: d["as"],
                                    stf=lambda d: d.hst, sta=lambda d: d.ast, cf=lambda d: d.hc, ca=lambda d: d.ac,
                                    yc=lambda d: d.hy, rc=lambda d: d.hr)
    a = df[df.away == team].assign(venue="V", opp=lambda d: d.home, gf=lambda d: d.ag, ga=lambda d: d.hg,
                                    xgf=lambda d: d.axg, xga=lambda d: d.hxg, sf=lambda d: d["as"], sa=lambda d: d["hs"],
                                    stf=lambda d: d.ast, sta=lambda d: d.hst, cf=lambda d: d.ac, ca=lambda d: d.hc,
                                    yc=lambda d: d.ay, rc=lambda d: d.ar)
    r = pd.concat([h, a]).sort_values("date")
    r["res"] = np.where(r.gf > r.ga, "G", np.where(r.gf == r.ga, "E", "P"))
    r["pts"] = r.res.map({"G": 3, "E": 1, "P": 0})
    return r


def _summ(r: pd.DataFrame) -> dict:
    if r.empty:
        return {}
    m = lambda c: None if r[c].isna().all() else round(float(r[c].mean()), 2)
    return {
        "pj": int(len(r)), "g": int((r.res == "G").sum()), "e": int((r.res == "E").sum()), "p": int((r.res == "P").sum()),
        "ppp": round(float(r.pts.mean()), 2), "gf": m("gf"), "gc": m("ga"), "xgf": m("xgf"), "xgc": m("xga"),
        "tiros": m("sf"), "tiros_arco": m("stf"), "tiros_arco_contra": m("sta"), "corners": m("cf"), "corners_contra": m("ca"),
        "amarillas": m("yc"),
        "over25_pct": round(float(((r.gf + r.ga) > 2.5).mean()) * 100),
        "btts_pct": round(float(((r.gf > 0) & (r.ga > 0)).mean()) * 100),
        "valla_invicta_pct": round(float((r.ga == 0).mean()) * 100),
        "sin_marcar_pct": round(float((r.gf == 0).mean()) * 100),
    }


def team_profile(df: pd.DataFrame, team: str, cur_season: str) -> dict:
    r = _team_rows(df, team)
    season = r[r.season.astype(str).str.startswith(cur_season)]
    last = r.tail(8)
    return {
        "ultimos": [{"fecha": d.date.strftime("%d/%m/%y"), "cond": d.venue, "rival": d.opp,
                     "marcador": f"{int(d.gf)}-{int(d.ga)}", "res": d.res} for d in last.iloc[::-1].itertuples()],
        "forma": "".join(last.tail(5).res.tolist()),
        "ultimos5": _summ(r.tail(5)),
        "temporada": _summ(season),
        "temporada_local": _summ(season[season.venue == "L"]),
        "temporada_visita": _summ(season[season.venue == "V"]),
        "ultimos10_local": _summ(r[r.venue == "L"].tail(10)),
        "ultimos10_visita": _summ(r[r.venue == "V"].tail(10)),
        "racha": _streak(r),
    }


def _streak(r: pd.DataFrame) -> str:
    if r.empty:
        return ""
    res = r.res.tolist()[::-1]
    unbeaten = next((k for k, x in enumerate(res) if x == "P"), len(res))
    winless = next((k for k, x in enumerate(res) if x == "G"), len(res))
    if res[0] == "G":
        wins = next((k for k, x in enumerate(res) if x != "G"), len(res))
        return f"{wins} victoria(s) seguidas" if wins > 1 else f"{unbeaten} sin perder"
    if unbeaten >= 3:
        return f"{unbeaten} partidos sin perder"
    if winless >= 3:
        return f"{winless} partidos sin ganar"
    return ""


def head_to_head(df: pd.DataFrame, home: str, away: str, n: int = 6) -> dict:
    m = df[((df.home == home) & (df.away == away)) | ((df.home == away) & (df.away == home))].sort_values("date").tail(n)
    rows = [{"fecha": d.date.strftime("%d/%m/%y"), "local": d.home, "visita": d.away, "marcador": f"{int(d.hg)}-{int(d.ag)}"}
            for d in m.iloc[::-1].itertuples()]
    wh = int((((m.home == home) & (m.hg > m.ag)) | ((m.away == home) & (m.ag > m.hg))).sum())
    wa = int((((m.home == away) & (m.hg > m.ag)) | ((m.away == away) & (m.ag > m.hg))).sum())
    return {"partidos": rows, "gana_local": wh, "empates": int((m.hg == m.ag).sum()), "gana_visita": wa,
            "goles_prom": round(float((m.hg + m.ag).mean()), 2) if len(m) else None}


def standings(df: pd.DataFrame, cur_season: str) -> list[dict]:
    s = df[df.season.astype(str).str.startswith(cur_season)]
    tab = {}
    for d in s.itertuples():
        for t, gf, ga in ((d.home, d.hg, d.ag), (d.away, d.ag, d.hg)):
            x = tab.setdefault(t, {"equipo": t, "pj": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0, "pts": 0})
            x["pj"] += 1; x["gf"] += int(gf); x["gc"] += int(ga)
            if gf > ga: x["g"] += 1; x["pts"] += 3
            elif gf == ga: x["e"] += 1; x["pts"] += 1
            else: x["p"] += 1
    rows = sorted(tab.values(), key=lambda x: (-x["pts"], -(x["gf"] - x["gc"]), -x["gf"]))
    for k, x in enumerate(rows, 1):
        x["pos"] = k; x["dg"] = x["gf"] - x["gc"]
    return rows


def rate_model(df: pd.DataFrame, col_h: str, col_a: str, ref_date=None):
    """Tasas esperadas (córners/tarjetas) con decaimiento temporal: modelo multiplicativo simple."""
    d = df.dropna(subset=[col_h, col_a])
    if len(d) < 50:
        return None
    ref = pd.Timestamp(ref_date) if ref_date is not None else d.date.max() + pd.Timedelta(days=1)
    d = d[d.date < ref]
    w = np.exp(-XI * 1.5 * (ref - d.date).dt.days.values)
    lh = np.average(d[col_h], weights=w)
    la = np.average(d[col_a], weights=w)
    teams = set(d.home) | set(d.away)
    k = 6.0  # partidos "ficticios" de encogimiento hacia la media
    rates = {}
    for t in teams:
        mh = (d.home == t).values; ma = (d.away == t).values
        wf = np.r_[w[mh], w[ma]]
        fo = np.r_[d[col_h].values[mh] / lh, d[col_a].values[ma] / la]
        ag = np.r_[d[col_a].values[mh] / la, d[col_h].values[ma] / lh]
        rates[t] = ((wf * fo).sum() + k) / (wf.sum() + k), ((wf * ag).sum() + k) / (wf.sum() + k)
    def predict(h, a):
        fh, ah = rates.get(h, (1, 1)); fa, aa = rates.get(a, (1, 1))
        return lh * fh * aa, la * fa * ah
    return predict

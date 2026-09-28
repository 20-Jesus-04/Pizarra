"""Árbitros: cuántas tarjetas saca cada uno comparado con lo que se esperaba por los equipos que dirigió.

factor = (K * media + tarjetas_reales) / (K * media + tarjetas_esperadas)

Con pocos partidos el factor queda cerca de 1 (K partidos "ficticios" en la media de la liga); con muchos, refleja
al árbitro. Las tarjetas esperadas salen del modelo de equipos, así que un árbitro no queda como "tarjetero" solo
por haber dirigido partidos de equipos que se amonestan mucho.
"""
from __future__ import annotations

import unicodedata

import numpy as np
import pandas as pd

REF_K = 40.0          # partidos ficticios en la media (elegido en el backtest de la Premier: K menor sobreajusta)
REF_XI = 0.002        # vida media ~1 año


def ref_key(name) -> str | None:
    """'Michael Oliver' y 'M Oliver' -> 'm oliver' (inicial + último apellido, sin tildes)."""
    if not isinstance(name, str) or not name.strip():
        return None
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().replace(".", " ").replace("-", " ")
    w = [x for x in s.split() if x]
    if not w:
        return None
    return w[0] if len(w) == 1 else f"{w[0][0]} {w[-1]}"


def factors(rows: pd.DataFrame, ref_date=None, k: float = REF_K, xi: float = REF_XI) -> dict:
    """rows: date, referee, actual, expected (tarjetas totales del partido). Devuelve {clave: info del árbitro}."""
    d = rows.dropna(subset=["referee", "actual", "expected"])
    if ref_date is not None:
        d = d[d.date < pd.Timestamp(ref_date)]
    if d.empty:
        return {}
    ref = pd.Timestamp(ref_date) if ref_date is not None else d.date.max() + pd.Timedelta(days=1)
    d = d.assign(key=d.referee.map(ref_key), w=np.exp(-xi * (ref - d.date).dt.days.values))
    d = d.dropna(subset=["key"])
    mean_exp = float(d.expected.mean())
    prior = k * mean_exp
    out = {}
    for kk, g in d.groupby("key"):
        A, E = float((g.w * g.actual).sum()), float((g.w * g.expected).sum())
        out[kk] = {"nombre": g.referee.iloc[-1], "partidos": int(len(g)), "factor": round((prior + A) / (prior + E), 3),
                   "tarjetas_prom": round(float(g.actual.mean()), 2), "esperadas_prom": round(float(g.expected.mean()), 2)}
    return out


def fd_rows(df: pd.DataFrame, ry) -> pd.DataFrame:
    """Partidos de football-data con árbitro (solo Inglaterra lo trae): amarillas reales vs esperadas por el modelo."""
    if ry is None or "referee" not in df or df.referee.isna().all():
        return pd.DataFrame(columns=["date", "referee", "actual", "expected"])
    d = df.dropna(subset=["referee", "hy", "ay"])
    exp = [sum(ry(h, a)) for h, a in zip(d.home, d.away)]
    return pd.DataFrame({"date": d.date.values, "referee": d.referee.values, "actual": (d.hy + d.ay).values, "expected": exp})


def espn_rows(T: pd.DataFrame, lg: str, yp) -> pd.DataFrame:
    """Fichas de ESPN (todas las ligas): amarillas por equipo y árbitro del partido."""
    if T is None or yp is None:
        return pd.DataFrame(columns=["date", "referee", "actual", "expected"])
    d = T[(T.lg == lg) & T.ref.notna() & T.yc.notna()]
    out = []
    for mid, g in d.groupby("mid"):
        if len(g) != 2:
            continue
        h = g[g.home].iloc[0] if g.home.any() else g.iloc[0]
        a = g[~g.home].iloc[0] if (~g.home).any() else g.iloc[1]
        exp = yp(h.team, a.team, True, False) + yp(a.team, h.team, False, False)
        out.append({"date": h.date, "referee": h.ref, "actual": float(h.yc + a.yc), "expected": exp})
    return pd.DataFrame(out, columns=["date", "referee", "actual", "expected"])


def lookup(table: dict, name) -> dict | None:
    k = ref_key(name)
    if not k:
        return None
    info = table.get(k)
    if info:
        return {**info, "nombre": name}
    return {"nombre": name, "partidos": 0, "factor": 1.0, "tarjetas_prom": None, "esperadas_prom": None}


def validate(pairs: pd.DataFrame, lines=(3.5, 4.5)) -> dict:
    """pairs: actual, expected (sin árbitro), expected_ref (con árbitro), n_ref (partidos previos del árbitro).
    Compara log-verosimilitud Poisson y Brier en líneas de tarjetas con y sin el factor del árbitro."""
    from scipy.stats import poisson
    p = pairs.dropna(subset=["actual", "expected", "expected_ref"])
    if len(p) < 50:
        return {"n": int(len(p))}
    y = p.actual.values.astype(int)
    res = {"n": int(len(p)), "con_historial": int((p.n_ref >= 5).sum())}
    for tag, col in (("sin_arbitro", "expected"), ("con_arbitro", "expected_ref")):
        m = p[col].values
        res[tag] = {"logverosimilitud": round(float(poisson.logpmf(y, m).mean()), 4),
                    "error_medio": round(float(np.abs(y - m).mean()), 3),
                    "brier": {f"{ln}": round(float(((1 - poisson.cdf(int(ln), m)) - (y > ln)) .__pow__(2).mean()), 4) for ln in lines}}
    res["mejora"] = bool(res["con_arbitro"]["logverosimilitud"] > res["sin_arbitro"]["logverosimilitud"])
    return res

"""Backtest walk-forward: cada semana se reentrena solo con datos anteriores y se predice la siguiente.
Compara modelo vs mercado (cuotas de cierre) y simula apuestas de valor con stake plano."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ANUALES
from .model import DixonColes, score_matrix


def devig(odds: np.ndarray) -> np.ndarray:
    inv = 1 / odds
    return inv / inv.sum(axis=-1, keepdims=True)


def walk_forward(df: pd.DataFrame, seasons: list[str], **model_kw) -> pd.DataFrame:
    test = df[df.season.astype(str).str[:4].isin([s[:4] for s in seasons]) if df["div"].iloc[0] in (*ANUALES, "INT")
              else df.season.isin(seasons)].copy()
    test["wk"] = test.date.dt.to_period("W-MON")
    rows = []
    for wk, g in test.groupby("wk"):
        ref = g.date.min()
        if (df.date < ref).sum() < 300:
            continue
        m = DixonColes(**model_kw).fit(df, ref_date=ref)
        for r in g.itertuples():
            lam, mu = m.rates(r.home, r.away)
            M = score_matrix(lam, mu, m.rho)
            i, j = np.indices(M.shape)
            rows.append({"date": r.date, "home": r.home, "away": r.away, "hg": r.hg, "ag": r.ag,
                         "pH": M[i > j].sum(), "pD": M[i == j].sum(), "pA": M[i < j].sum(),
                         "pO25": M[(i + j) > 2.5].sum(),
                         "oH": r.oH, "oD": r.oD, "oA": r.oA, "oO25": r.oO25, "oU25": r.oU25,
                         "mH": r.mH, "mD": r.mD, "mA": r.mA, "mO25": r.mO25, "mU25": r.mU25})
    return pd.DataFrame(rows)


def evaluate(bt: pd.DataFrame, weights=(0, 0.25, 0.5, 0.75, 1.0), edge=0.03, min_prob=0.25) -> dict:
    y = np.select([bt.hg > bt.ag, bt.hg == bt.ag], [0, 1], 2)
    P = bt[["pH", "pD", "pA"]].values
    has = bt[["oH", "oD", "oA"]].notna().all(axis=1).values
    out = {"n": int(len(bt))}
    ll = lambda Q, yy: float(-np.mean(np.log(np.clip(Q[np.arange(len(yy)), yy], 1e-9, 1))))
    br = lambda Q, yy: float(np.mean(((Q - np.eye(3)[yy]) ** 2).sum(1)))
    out["logloss_modelo"] = round(ll(P, y), 4)
    out["brier_modelo"] = round(br(P, y), 4)
    out["acierto_modelo"] = round(float((P.argmax(1) == y).mean()), 4)
    # base "ingenua": frecuencias de local/empate/visita
    base = np.tile(np.bincount(y, minlength=3) / len(y), (len(y), 1))
    out["logloss_base"] = round(ll(base, y), 4)
    if has.sum() > 50:
        Pm = devig(bt.loc[has, ["oH", "oD", "oA"]].values)
        yy = y[has]
        out["n_con_cuotas"] = int(has.sum())
        out["logloss_mercado"] = round(ll(Pm, yy), 4)
        out["acierto_mercado"] = round(float((Pm.argmax(1) == yy).mean()), 4)
        blends = {}
        for w in weights:
            Q = w * Pm + (1 - w) * P[has]
            blends[w] = round(ll(Q, yy), 4)
        out["logloss_mezcla"] = blends
        # simulación de apuestas 1X2 y O/U 2.5 con mejor cuota disponible (Max) y con cuota promedio
        sims = {}
        for w in weights:
            Q = w * Pm + (1 - w) * P[has]
            for kind, cols in (("promedio", ["oH", "oD", "oA"]), ("mejor", ["mH", "mD", "mA"])):
                O = bt.loc[has, cols].values
                ev = Q * O - 1
                pick = (ev > edge) & (Q >= min_prob) & ~np.isnan(O)
                win = np.eye(3)[yy].astype(bool)
                profit = np.where(win, O - 1, -1.0)
                n = int(pick.sum())
                sims[f"1x2_w{w}_{kind}"] = {"apuestas": n, "acierto": round(float(win[pick].mean()), 3) if n else None,
                                           "roi": round(float(profit[pick].sum() / n), 4) if n else None}
            # over/under 2.5
            po = w * devig(bt.loc[has, ["oO25", "oU25"]].values)[:, 0] + (1 - w) * bt.loc[has, "pO25"].values
            Qo = np.c_[po, 1 - po]
            yo = ((bt.loc[has, "hg"] + bt.loc[has, "ag"]).values > 2.5)
            wo = np.c_[yo, ~yo]
            for kind, cols in (("promedio", ["oO25", "oU25"]), ("mejor", ["mO25", "mU25"])):
                O = bt.loc[has, cols].values
                ev = Qo * O - 1
                pick = (ev > edge) & (Qo >= min_prob) & ~np.isnan(O)
                profit = np.where(wo, O - 1, -1.0)
                n = int(pick.sum())
                sims[f"ou25_w{w}_{kind}"] = {"apuestas": n, "acierto": round(float(wo[pick].mean()), 3) if n else None,
                                            "roi": round(float(profit[pick].sum() / n), 4) if n else None}
        out["simulacion"] = sims
    # calibración: en bins de probabilidad, frecuencia real
    flat_p = P.ravel(); flat_y = np.eye(3)[y].ravel()
    bins = np.linspace(0, 1, 11)
    cal = []
    for a, b in zip(bins[:-1], bins[1:]):
        m = (flat_p >= a) & (flat_p < b)
        if m.sum() >= 20:
            cal.append({"rango": f"{int(a*100)}-{int(b*100)}%", "prob_media": round(float(flat_p[m].mean()), 3),
                        "frecuencia_real": round(float(flat_y[m].mean()), 3), "n": int(m.sum())})
    out["calibracion"] = cal
    return out

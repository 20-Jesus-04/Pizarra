"""Modelo Dixon-Coles con decaimiento temporal, ventaja local por equipo y mezcla goles/xG.

goles_local  ~ Poisson(lambda),  log(lambda) = ataque[local] + defensa[visita] + local_liga + local_extra[local]
goles_visita ~ Poisson(mu),      log(mu)     = ataque[visita] + defensa[local]
con la corrección Dixon-Coles (rho) para los marcadores bajos (0-0, 1-0, 0-1, 1-1).
Cada partido pesa exp(-XI * días_de_antigüedad): lo reciente importa más.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .config import XI, XG_WEIGHT, HOME_SHRINK

RIDGE = 1.0            # regularización de ataque/defensa hacia su "prior"
PROMOTED_PRIOR = 0.18  # equipos nuevos en la liga: arrancan algo peores que la media


class DixonColes:
    def __init__(self, xi=XI, xg_weight=XG_WEIGHT, home_shrink=HOME_SHRINK, promoted_prior=True):
        self.xi, self.xg_weight, self.home_shrink = xi, xg_weight, home_shrink
        self.promoted_prior = promoted_prior

    # ------------------------------------------------------------------ ajuste
    def fit(self, df: pd.DataFrame, ref_date=None):
        df = df.dropna(subset=["hg", "ag"])
        ref_date = pd.Timestamp(ref_date) if ref_date is not None else df.date.max() + pd.Timedelta(days=1)
        df = df[df.date < ref_date]
        days = (ref_date - df.date).dt.days.values
        w = np.exp(-self.xi * days)
        if "mw" in df:  # peso por tipo de partido (amistoso < oficial)
            w = w * df["mw"].fillna(1.0).values
        keep = w > 0.02
        df, w = df[keep], w[keep]
        # sede neutral: sin ventaja de local
        hf = (1.0 - df["neutral"].fillna(False).astype(float).values) if "neutral" in df else np.ones(len(df))

        teams = sorted(set(df.home) | set(df.away))
        self.teams = teams
        ix = {t: i for i, t in enumerate(teams)}
        h = df.home.map(ix).values
        a = df.away.map(ix).values
        gh_i = df.hg.values.astype(int)
        ga_i = df.ag.values.astype(int)
        # objetivo "suavizado": mezcla goles con xG cuando existe
        gh = df.hg.values.astype(float)
        ga = df.ag.values.astype(float)
        xh, xa = ("hxg_m", "axg_m") if "hxg_m" in df else ("hxg", "axg")
        if xh in df and self.xg_weight > 0:
            hx, ax = df[xh].values.astype(float), df[xa].values.astype(float)
            m = ~np.isnan(hx) & ~np.isnan(ax)
            gh = np.where(m, (1 - self.xg_weight) * gh + self.xg_weight * np.nan_to_num(hx), gh)
            ga = np.where(m, (1 - self.xg_weight) * ga + self.xg_weight * np.nan_to_num(ax), ga)

        # prior: equipos que no jugaron la temporada anterior en esta liga (ascendidos)
        seasons = list(dict.fromkeys(df.season))
        cur = seasons[-1]
        prev_teams = set(df[df.season != cur].home) | set(df[df.season != cur].away)
        cur_teams = set(df[df.season == cur].home) | set(df[df.season == cur].away)
        n = len(teams)
        prior_att = np.zeros(n)
        prior_def = np.zeros(n)
        if len(seasons) > 1 and self.promoted_prior:
            for t in cur_teams - prev_teams:
                prior_att[ix[t]] = -PROMOTED_PRIOR
                prior_def[ix[t]] = PROMOTED_PRIOR

        W = w.sum()
        lo = (gh_i <= 1) & (ga_i <= 1)
        c00 = (gh_i == 0) & (ga_i == 0)
        c01 = (gh_i == 0) & (ga_i == 1)
        c10 = (gh_i == 1) & (ga_i == 0)
        c11 = (gh_i == 1) & (ga_i == 1)

        def unpack(p):
            return p[:n], p[n:2 * n], p[2 * n], p[2 * n + 1:3 * n + 1], p[3 * n + 1]

        def f(p):
            att, de, home, hx, rho = unpack(p)
            ll_l = att[h] + de[a] + hf * (home + hx[h])
            ll_m = att[a] + de[h]
            lam, mu = np.exp(ll_l), np.exp(ll_m)
            tau = np.ones_like(lam)
            tau[c00] = 1 - lam[c00] * mu[c00] * rho
            tau[c01] = 1 + lam[c01] * rho
            tau[c10] = 1 + mu[c10] * rho
            tau[c11] = 1 - rho
            if np.any(tau <= 0):
                return 1e10, np.zeros_like(p)
            ll = w * (gh * ll_l - lam + ga * ll_m - mu + np.log(tau))
            # gradientes respecto a log(lambda) y log(mu)
            dl = gh - lam
            dm = ga - mu
            dtl = np.zeros_like(lam); dtm = np.zeros_like(lam); drho = np.zeros_like(lam)
            dtl[c00] = -lam[c00] * mu[c00] * rho / tau[c00]
            dtm[c00] = dtl[c00]
            drho[c00] = -lam[c00] * mu[c00] / tau[c00]
            dtl[c01] = lam[c01] * rho / tau[c01]
            drho[c01] = lam[c01] / tau[c01]
            dtm[c10] = mu[c10] * rho / tau[c10]
            drho[c10] = mu[c10] / tau[c10]
            drho[c11] = -1 / tau[c11]
            gl = w * (dl + dtl)
            gm = w * (dm + dtm)
            g_att = np.bincount(h, gl, n) + np.bincount(a, gm, n)
            g_def = np.bincount(a, gl, n) + np.bincount(h, gm, n)
            g_home = (gl * hf).sum()
            g_hx = np.bincount(h, gl * hf, n)
            g_rho = (w * drho).sum()
            # penalizaciones (en unidades de "partidos")
            pen = RIDGE * (((att - prior_att) ** 2).sum() + ((de - prior_def) ** 2).sum()) + self.home_shrink * (hx ** 2).sum()
            pen += 50.0 * (att.sum() ** 2)  # identificabilidad
            g_att = g_att - 2 * RIDGE * (att - prior_att) - 100.0 * att.sum()
            g_def = g_def - 2 * RIDGE * (de - prior_def)
            g_hx = g_hx - 2 * self.home_shrink * hx
            obj = -(ll.sum() - pen)
            grad = -np.concatenate([g_att, g_def, [g_home], g_hx, [g_rho]])
            return obj, grad

        mean_g = np.log(max(np.average(gh + ga, weights=w) / 2, 0.3))
        p0 = np.concatenate([prior_att, prior_def + mean_g, [0.25], np.zeros(n), [-0.05]])
        bounds = [(-3, 3)] * (2 * n) + [(-1, 1.5)] + [(-1, 1)] * n + [(-0.3, 0.3)]
        res = minimize(f, p0, jac=True, method="L-BFGS-B", bounds=bounds, options={"maxiter": 500})
        att, de, home, hx, rho = unpack(res.x)
        self.att = dict(zip(teams, att))
        self.de = dict(zip(teams, de))
        self.home = home
        self.hx = dict(zip(teams, hx))
        self.rho = rho
        self.n_matches = len(df)
        self.ref_date = ref_date
        # fracción de goles en el primer tiempo (para mercados de 1T)
        if "hthg" in df and df.hthg.notna().any():
            m = df.hthg.notna()
            self.ht_frac = float(((df.hthg + df.htag)[m] * w[m.values]).sum() / ((df.hg + df.ag)[m] * w[m.values]).sum())
        else:
            self.ht_frac = 0.44
        return self

    # ------------------------------------------------------------------ predicción
    def rates(self, home: str, away: str, neutral: bool = False):
        ah = self.att.get(home, -PROMOTED_PRIOR); dh = self.de.get(home, np.mean(list(self.de.values())) + PROMOTED_PRIOR)
        aa = self.att.get(away, -PROMOTED_PRIOR); da = self.de.get(away, np.mean(list(self.de.values())) + PROMOTED_PRIOR)
        lam = np.exp(ah + da + (0.0 if neutral else self.home + self.hx.get(home, 0.0)))
        mu = np.exp(aa + dh)
        return float(lam), float(mu)

    def ratings_table(self):
        base_def = np.mean(list(self.de.values()))
        rows = []
        for t in self.teams:
            rows.append({"team": t, "attack": round(float(np.exp(self.att[t])), 3),
                         "defense": round(float(np.exp(self.de[t] - base_def)), 3),
                         "home_adv": round(float(np.exp(self.home + self.hx[t])), 3)})
        return rows


def score_matrix(lam: float, mu: float, rho: float, max_goals: int = 10) -> np.ndarray:
    from scipy.stats import poisson
    k = np.arange(max_goals + 1)
    m = np.outer(poisson.pmf(k, lam), poisson.pmf(k, mu))
    m[0, 0] *= 1 - lam * mu * rho
    m[0, 1] *= 1 + lam * rho
    m[1, 0] *= 1 + mu * rho
    m[1, 1] *= 1 - rho
    return m / m.sum()

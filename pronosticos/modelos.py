"""Los modelos del ensamble, además de Dixon-Coles (que vive en model.py).

- PoissonModel: Poisson independiente clásico (ataque/defensa + ventaja local global), sin corrección de marcadores bajos.
- BayesModel:   tasas de gol Gamma-Poisson: parte del promedio de la liga y se actualiza con los goles recientes.
- Elo:          fuerza relativa según resultados; se convierte a 1X2 con un logit ordenado.
- XGBoost:      patrones no lineales entre variables del partido (forma, descanso, xG reciente, Elo...).
- Mercado:      probabilidad implícita de las cuotas sin el margen de la casa (ver backtest.devig).

Todas las variables se calculan con partidos ANTERIORES a cada partido: nada del futuro se filtra al pasado.
"""
from __future__ import annotations

import math
from collections import deque

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .config import XI, MAX_GOALS

PROMOTED = 0.18       # ascendidos / equipos sin historia: algo peores que la media (en log)
_K = np.arange(MAX_GOALS + 1)
_LOGFACT = np.array([math.lgamma(k + 1) for k in _K])


# ------------------------------------------------------------------ utilidades
def _weights(df, ref, xi):
    days = (ref - df.date).dt.days.values
    w = np.exp(-xi * days)
    if "mw" in df:
        w = w * df["mw"].fillna(1.0).values
    return w


def _neutral(df):
    return df["neutral"].fillna(False).astype(bool).values if "neutral" in df else np.zeros(len(df), bool)


def fast_matrix(lam: float, mu: float, rho: float = 0.0) -> np.ndarray:
    """Matriz de marcadores (igual que model.score_matrix, pero sin scipy: se llama miles de veces)."""
    ph = np.exp(_K * np.log(max(lam, 1e-9)) - lam - _LOGFACT)
    pa = np.exp(_K * np.log(max(mu, 1e-9)) - mu - _LOGFACT)
    m = np.outer(ph, pa)
    if rho:
        m[0, 0] *= 1 - lam * mu * rho
        m[0, 1] *= 1 + lam * rho
        m[1, 0] *= 1 + mu * rho
        m[1, 1] *= 1 - rho
    return m / m.sum()


_I, _J = np.indices((MAX_GOALS + 1, MAX_GOALS + 1))


def probs_from_rates(lam, mu, rho=0.0):
    """(pH, pD, pA, pOver2.5) de una pareja de goles esperados."""
    M = fast_matrix(lam, mu, rho)
    return M[_I > _J].sum(), M[_I == _J].sum(), M[_I < _J].sum(), M[(_I + _J) > 2.5].sum()


def implied_rates_fast(pH, pA, p_over, rho, lam0, mu0, line=2.5):
    """Busca (lambda, mu) cuya matriz reproduce 1X2 (y over si se da). Versión rápida de build.implied_rates."""
    def loss(x):
        M = fast_matrix(math.exp(x[0]), math.exp(x[1]), rho)
        e = (M[_I > _J].sum() - pH) ** 2 + (M[_I < _J].sum() - pA) ** 2
        if p_over is not None:
            e += (M[(_I + _J) > line].sum() - p_over) ** 2
        return e
    r = minimize(loss, np.log([max(lam0, 0.05), max(mu0, 0.05)]), method="Nelder-Mead",
                 options={"xatol": 1e-4, "fatol": 1e-10, "maxiter": 400})
    return float(math.exp(r.x[0])), float(math.exp(r.x[1]))


# ------------------------------------------------------------------ Poisson independiente
class PoissonModel:
    """log(lambda) = c + ataque[local] + defensa[visita] + local;  log(mu) = c + ataque[visita] + defensa[local].
    Solo goles reales (sin xG), ventaja local única para toda la liga y sin corrección Dixon-Coles."""
    RIDGE = 1.0

    def __init__(self, xi=XI, promoted_prior=True):
        self.xi, self.promoted_prior = xi, promoted_prior

    def fit(self, df: pd.DataFrame, ref_date=None):
        df = df.dropna(subset=["hg", "ag"])
        ref = pd.Timestamp(ref_date) if ref_date is not None else df.date.max() + pd.Timedelta(days=1)
        df = df[df.date < ref]
        w = _weights(df, ref, self.xi)
        keep = w > 0.02
        df, w = df[keep], w[keep]
        hf = 1.0 - _neutral(df).astype(float)
        teams = sorted(set(df.home) | set(df.away))
        ix = {t: i for i, t in enumerate(teams)}
        n = len(teams)
        h, a = df.home.map(ix).values, df.away.map(ix).values
        gh, ga = df.hg.values.astype(float), df.ag.values.astype(float)
        R = self.RIDGE

        def f(p):
            att, de, home, c = p[:n], p[n:2 * n], p[2 * n], p[2 * n + 1]
            ll_l = c + att[h] + de[a] + hf * home
            ll_m = c + att[a] + de[h]
            lam, mu = np.exp(ll_l), np.exp(ll_m)
            ll = (w * (gh * ll_l - lam + ga * ll_m - mu)).sum()
            gl, gm = w * (gh - lam), w * (ga - mu)
            g_att = np.bincount(h, gl, n) + np.bincount(a, gm, n) - 2 * R * att - 100.0 * att.sum()
            g_def = np.bincount(a, gl, n) + np.bincount(h, gm, n) - 2 * R * de - 100.0 * de.sum()
            pen = R * ((att ** 2).sum() + (de ** 2).sum()) + 50.0 * (att.sum() ** 2 + de.sum() ** 2)
            grad = np.concatenate([g_att, g_def, [(gl * hf).sum()], [(gl + gm).sum()]])
            return -(ll - pen), -grad

        c0 = np.log(max(np.average(gh + ga, weights=w) / 2, 0.3))
        p0 = np.concatenate([np.zeros(2 * n), [0.2, c0]])
        res = minimize(f, p0, jac=True, method="L-BFGS-B", bounds=[(-3, 3)] * (2 * n) + [(-1, 1.5), (-3, 3)],
                       options={"maxiter": 500})
        p = res.x
        self.teams = teams
        self.att, self.de = dict(zip(teams, p[:n])), dict(zip(teams, p[n:2 * n]))
        self.home, self.c = float(p[2 * n]), float(p[2 * n + 1])
        return self

    def rates(self, home, away, neutral=False):
        u = PROMOTED if self.promoted_prior else 0.0
        lam = math.exp(self.c + self.att.get(home, -u) + self.de.get(away, u) + (0.0 if neutral else self.home))
        mu = math.exp(self.c + self.att.get(away, -u) + self.de.get(home, u))
        return lam, mu


# ------------------------------------------------------------------ Bayesiano Gamma-Poisson
class BayesModel:
    """Cada equipo tiene un multiplicador de ataque y otro de defensa con prior Gamma centrado en la media
    de la liga (o algo peor si es ascendido). Los goles recientes lo actualizan; con pocos partidos casi no se mueve.
    Posterior: (alpha * m0 + goles) / (alpha + goles_esperados)."""

    def __init__(self, xi=XI * 2.0, alpha=6.0, promoted_prior=True):
        self.xi, self.alpha, self.promoted_prior = xi, alpha, promoted_prior

    def fit(self, df: pd.DataFrame, ref_date=None):
        df = df.dropna(subset=["hg", "ag"])
        ref = pd.Timestamp(ref_date) if ref_date is not None else df.date.max() + pd.Timedelta(days=1)
        df = df[df.date < ref]
        w = _weights(df, ref, self.xi)
        keep = w > 0.01
        df, w = df[keep], w[keep]
        neu = _neutral(df)
        teams = sorted(set(df.home) | set(df.away))
        ix = {t: i for i, t in enumerate(teams)}
        n = len(teams)
        h, a = df.home.map(ix).values, df.away.map(ix).values
        gh, ga = df.hg.values.astype(float), df.ag.values.astype(float)
        bh, ba = np.average(gh, weights=w), np.average(ga, weights=w)
        bn = (bh + ba) / 2
        base_l, base_m = np.where(neu, bn, bh), np.where(neu, bn, ba)
        m_att, m_def = np.ones(n), np.ones(n)
        if self.promoted_prior and "season" in df:
            seasons = list(dict.fromkeys(df.season))
            if len(seasons) > 1:
                cur = df.season == seasons[-1]
                prev = set(df[~cur].home) | set(df[~cur].away)
                for t in (set(df[cur].home) | set(df[cur].away)) - prev:
                    m_att[ix[t]], m_def[ix[t]] = math.exp(-PROMOTED), math.exp(PROMOTED)
        g_for = np.bincount(h, w * gh, n) + np.bincount(a, w * ga, n)
        g_ag = np.bincount(h, w * ga, n) + np.bincount(a, w * gh, n)
        att, de = m_att.copy(), m_def.copy()
        al = self.alpha
        for _ in range(12):
            e_for = np.bincount(h, w * base_l * de[a], n) + np.bincount(a, w * base_m * de[h], n)
            att = (al * m_att + g_for) / (al + e_for)
            e_ag = np.bincount(h, w * base_m * att[a], n) + np.bincount(a, w * base_l * att[h], n)
            de = (al * m_def + g_ag) / (al + e_ag)
        self.teams = teams
        self.att, self.de = dict(zip(teams, att)), dict(zip(teams, de))
        self.bh, self.ba, self.bn = float(bh), float(ba), float(bn)
        return self

    def rates(self, home, away, neutral=False):
        u = math.exp(PROMOTED) if self.promoted_prior else 1.0
        ah, dh = self.att.get(home, 1 / u), self.de.get(home, u)
        aa, da = self.att.get(away, 1 / u), self.de.get(away, u)
        bl, bm = (self.bn, self.bn) if neutral else (self.bh, self.ba)
        return bl * ah * da, bm * aa * dh


# ------------------------------------------------------------------ Elo
ELO_BASE = 1500.0


def elo_run(df: pd.DataFrame, k=20.0, hadv=65.0, national=False, regress=0.2):
    """Recorre los partidos en orden y devuelve el Elo de cada equipo ANTES de cada partido.
    Clubes: al empezar temporada se acerca un 20% a la media; los recién llegados empiezan 80 puntos abajo.
    Selecciones: K mayor en partidos oficiales que en amistosos."""
    d = df.dropna(subset=["hg", "ag"])
    R: dict[str, float] = {}
    pre = np.zeros((len(d), 2))
    neu = _neutral(d)
    mw = d["mw"].fillna(1.0).values if "mw" in d else np.ones(len(d))
    seasons = d.season.astype(str).values if "season" in d else np.array([""] * len(d))
    first = seasons[0] if len(seasons) else ""
    cur = first
    for i, (h, a, hg, ag) in enumerate(zip(d.home.values, d.away.values, d.hg.values, d.ag.values)):
        if not national and seasons[i] != cur:
            cur = seasons[i]
            R = {t: ELO_BASE + (1 - regress) * (r - ELO_BASE) for t, r in R.items()}
        new = ELO_BASE if (national or seasons[i] == first) else ELO_BASE - 80
        rh, ra = R.get(h, new), R.get(a, new)
        pre[i] = rh, ra
        dr = rh - ra + (0.0 if neu[i] else hadv)
        we = 1.0 / (10 ** (-dr / 400) + 1)
        wres = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
        gd = abs(int(hg) - int(ag))
        g = 1.0 if gd <= 1 else 1.5 if gd == 2 else (11 + gd) / 8
        kk = (40.0 if mw[i] >= 1 else 20.0) if national else k
        delta = kk * g * (wres - we)
        R[h], R[a] = rh + delta, ra - delta
    return pd.DataFrame(pre, index=d.index, columns=["elo_h", "elo_a"]), R


def _sig(x):
    return 1.0 / (1.0 + np.exp(-x))


class EloModel:
    """Convierte la diferencia de Elo en 1X2 con un logit ordenado de 3 parámetros (escala, empate, ventaja local),
    ajustados por máxima verosimilitud con partidos ya jugados."""

    def fit(self, elo_pre: pd.DataFrame, df: pd.DataFrame, ref_date=None, burn_in=200):
        d = df.loc[elo_pre.index]
        m = np.ones(len(d), bool)
        if ref_date is not None:
            m &= (d.date < pd.Timestamp(ref_date)).values
        m[:burn_in] = False
        if m.sum() < 150:
            m = (d.date < pd.Timestamp(ref_date)).values if ref_date is not None else np.ones(len(d), bool)
        diff = ((elo_pre.elo_h - elo_pre.elo_a).values / 100)[m]
        hf = 1.0 - _neutral(d)[m].astype(float)
        y = np.select([d.hg.values[m] > d.ag.values[m], d.hg.values[m] == d.ag.values[m]], [0, 1], 2)

        def nll(p):
            s, c, ha = p
            x = s * (diff + ha * hf)
            ph, pa = _sig(x - c), _sig(-x - c)
            P = np.c_[ph, 1 - ph - pa, pa]
            return -np.log(np.clip(P[np.arange(len(y)), y], 1e-9, 1)).mean()
        r = minimize(nll, [0.6, 0.6, 0.6], method="L-BFGS-B", bounds=[(0.05, 3), (0.02, 3), (-1, 3)])
        self.s, self.c, self.ha = map(float, r.x)
        return self

    def probs(self, elo_h, elo_a, neutral=False):
        x = self.s * ((elo_h - elo_a) / 100 + (0.0 if neutral else self.ha))
        ph, pa = float(_sig(x - self.c)), float(_sig(-x - self.c))
        return ph, 1 - ph - pa, pa


# ------------------------------------------------------------------ variables para XGBoost
FEATURES = ["elo_diff", "elo_h", "elo_a", "neutral", "is_int", "mw",
            "h_pts5", "a_pts5", "h_gd5", "a_gd5", "h_venue_pts", "a_venue_pts",
            "h_gf", "h_ga", "a_gf", "a_ga", "h_xgf", "h_xga", "a_xgf", "a_xga", "h_sot", "a_sot",
            "h_rest", "a_rest", "h_n", "a_n", "lg_goals", "lg_home"]
EW = 0.15   # peso del último partido en las medias exponenciales


class _Team:
    __slots__ = ("pts", "gd", "home_pts", "away_pts", "gf", "ga", "xgf", "xga", "sot", "last", "n")

    def __init__(self, gf0, ga0):
        self.pts, self.gd = deque(maxlen=5), deque(maxlen=5)
        self.home_pts, self.away_pts = deque(maxlen=5), deque(maxlen=5)
        self.gf = self.xgf = gf0
        self.ga = self.xga = ga0
        self.sot = np.nan
        self.last = None
        self.n = 0


def _team_feats(t: _Team, date, venue_home: bool):
    rest = min(30.0, (date - t.last).days) if t.last is not None else 30.0
    venue = t.home_pts if venue_home else t.away_pts
    return [np.mean(t.pts) if t.pts else np.nan, np.mean(t.gd) if t.gd else np.nan,
            np.mean(venue) if venue else np.nan, t.gf, t.ga, t.xgf, t.xga, t.sot, rest, min(t.n, 60)]


class FeatureState:
    """Estado secuencial de una liga: permite calcular variables de partidos históricos y de los próximos."""

    def __init__(self, national: bool):
        self.national = national
        self.teams: dict[str, _Team] = {}
        self.lg_goals, self.lg_home = 2.6, 1.45

    def team(self, name):
        if name not in self.teams:
            self.teams[name] = _Team(self.lg_goals / 2, self.lg_goals / 2)
        return self.teams[name]

    def row(self, home, away, date, neutral, mw, elo_h, elo_a):
        th, ta = self.team(home), self.team(away)
        fh, fa = _team_feats(th, date, True), _team_feats(ta, date, False)
        return {"elo_diff": elo_h - elo_a, "elo_h": elo_h - ELO_BASE, "elo_a": elo_a - ELO_BASE,
                "neutral": float(neutral), "is_int": float(self.national), "mw": mw,
                "h_pts5": fh[0], "a_pts5": fa[0], "h_gd5": fh[1], "a_gd5": fa[1], "h_venue_pts": fh[2], "a_venue_pts": fa[2],
                "h_gf": fh[3], "h_ga": fh[4], "a_gf": fa[3], "a_ga": fa[4], "h_xgf": fh[5], "h_xga": fh[6],
                "a_xgf": fa[5], "a_xga": fa[6], "h_sot": fh[7], "a_sot": fa[7], "h_rest": fh[8], "a_rest": fa[8],
                "h_n": fh[9], "a_n": fa[9], "lg_goals": self.lg_goals, "lg_home": self.lg_home}

    def update(self, home, away, date, hg, ag, hx, ax, hsot, asot):
        th, ta = self.team(home), self.team(away)
        for t, gf, ga, xf, xa, sot, is_home in ((th, hg, ag, hx, ax, hsot, True), (ta, ag, hg, ax, hx, asot, False)):
            pts = 3 if gf > ga else 1 if gf == ga else 0
            t.pts.append(pts); t.gd.append(gf - ga)
            (t.home_pts if is_home else t.away_pts).append(pts)
            t.gf += EW * (gf - t.gf); t.ga += EW * (ga - t.ga)
            xf = gf if xf is None or np.isnan(xf) else xf
            xa = ga if xa is None or np.isnan(xa) else xa
            t.xgf += EW * (xf - t.xgf); t.xga += EW * (xa - t.xga)
            if sot is not None and not np.isnan(sot):
                t.sot = sot if np.isnan(t.sot) else t.sot + EW * (sot - t.sot)
            t.last, t.n = date, t.n + 1
        self.lg_goals += 0.01 * (hg + ag - self.lg_goals)
        self.lg_home += 0.01 * (hg - self.lg_home)


def build_features(df: pd.DataFrame, elo_pre: pd.DataFrame, national: bool):
    """Variables de cada partido histórico (con datos previos) + estado final para los próximos."""
    d = df.loc[elo_pre.index]
    st = FeatureState(national)
    neu = _neutral(d)
    mw = d["mw"].fillna(1.0).values if "mw" in d else np.ones(len(d))
    col = lambda c: d[c].values.astype(float) if c in d else np.full(len(d), np.nan)
    hx, ax = (col("hxg_m"), col("axg_m")) if "hxg_m" in d else (col("hxg"), col("axg"))
    hs, as_ = col("hst"), col("ast")
    rows = []
    for i, r in enumerate(d.itertuples()):
        rows.append(st.row(r.home, r.away, r.date, neu[i], mw[i], elo_pre.elo_h.values[i], elo_pre.elo_a.values[i]))
        st.update(r.home, r.away, r.date, int(r.hg), int(r.ag), hx[i], ax[i], hs[i], as_[i])
    X = pd.DataFrame(rows, index=d.index, columns=FEATURES)
    return X, st


XGB_ROUNDS = 260
XGB_PARAMS = dict(max_depth=3, eta=0.035, subsample=0.8, colsample_bytree=0.8, min_child_weight=12,
                  reg_lambda=3.0, tree_method="hist", nthread=4, verbosity=0, seed=7)


class XGBModel:
    """kind='1x2' (3 clases) u 'o25' (binario). API nativa de xgboost (no necesita scikit-learn)."""

    def __init__(self, kind: str):
        self.kind = kind

    def fit(self, X: pd.DataFrame, y: np.ndarray):
        import xgboost as xgb
        p = dict(XGB_PARAMS, **({"objective": "multi:softprob", "num_class": 3} if self.kind == "1x2"
                                else {"objective": "binary:logistic"}))
        self.booster = xgb.train(p, xgb.DMatrix(X[FEATURES].values.astype(float), label=y), num_boost_round=XGB_ROUNDS)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """1x2: matriz (n, 3) con pH, pD, pA.  o25: vector con p(más de 2.5)."""
        import xgboost as xgb
        return self.booster.predict(xgb.DMatrix(X[FEATURES].values.astype(float)))


def train_xgb(X: pd.DataFrame, y: np.ndarray, kind: str) -> XGBModel:
    return XGBModel(kind).fit(X, y)


def trainable(X: pd.DataFrame) -> np.ndarray:
    """Se entrena solo con partidos donde ambos equipos ya tienen algo de historia."""
    return ((X.h_n >= 3) & (X.a_n >= 3)).values

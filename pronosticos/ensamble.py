"""Ensamble de seis modelos independientes con pesos recalibrados contra partidos ya jugados.

calibrar():  backtest walk-forward de los 6 modelos (cada semana se reentrena solo con el pasado), ajuste de pesos,
             evaluación fuera de muestra, curva de calibración, estadísticas por subtipo de pick y validación del
             factor árbitro. Se guarda en data/modelo.json y se recalcula una vez por semana (o con --recalibrar).
Motor:       los modelos ajustados con todos los datos, para pronosticar los próximos partidos.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .arbitros import REF_K, factors, fd_rows, validate as validate_refs
from .backtest import devig, evaluate
from .config import INT_XI
from .fetch import DATA_DIR
from .markets import all_markets
from .model import DixonColes
from .modelos import (BayesModel, EloModel, PoissonModel, build_features, elo_run, implied_rates_fast, probs_from_rates,
                      train_xgb, trainable, _neutral)
from .picks import BANDS, PICK_LABELS, get, levels, settle
from .stats import rate_model

MODELOS = ["poisson", "dixon_coles", "elo", "bayes", "mercado", "xgboost"]
NOMBRES = {"poisson": "Poisson", "dixon_coles": "Dixon-Coles", "elo": "Elo", "bayes": "Bayesiano",
           "mercado": "Consenso del mercado", "xgboost": "XGBoost"}
O25 = ["poisson", "dixon_coles", "bayes", "mercado", "xgboost"]   # modelos que estiman goles totales
CACHE = os.path.join(DATA_DIR, "modelo.json")
MAX_AGE_DAYS = 6
PICK_MIN = 0.385         # probabilidad mínima para guardar un pick simulado (cuota justa hasta 2.60)


def kwargs(code):
    nat = code == "INT"
    return {"nat": nat,
            "dc": dict(xi=INT_XI, home_shrink=30.0, promoted_prior=False) if nat else {},
            "po": dict(xi=INT_XI, promoted_prior=False) if nat else {},
            "ba": dict(xi=INT_XI * 2, promoted_prior=False) if nat else {}}


def _labels(df):
    y = np.select([df.hg > df.ag, df.hg == df.ag], [0, 1], 2)
    yo = ((df.hg + df.ag) > 2.5).astype(int).values
    return y, yo


def _test_start(code, df, now):
    if code == "INT":
        return pd.Timestamp(now) - pd.Timedelta(days=int(365 * 2.5))
    if code == "PER":
        return pd.Timestamp(now.year - 2, 1, 1)
    seasons = sorted(set(df.season))
    s = seasons[-3] if len(seasons) >= 3 else seasons[0]
    return df[df.season == s].date.min()


# ------------------------------------------------------------------ backtest por liga
def league_backtest(code: str, df: pd.DataFrame, start) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    k = kwargs(code)
    df = df.dropna(subset=["hg", "ag"])
    ep, _ = elo_run(df, national=k["nat"])
    X, _ = build_features(df, ep, k["nat"])
    neu = pd.Series(_neutral(df), index=df.index)
    has_ref = code != "INT" and "referee" in df and df.referee.notna().sum() > 300
    test = df[df.date >= start]
    rows, refpairs = [], []
    em, em_month = None, None
    for _, g in test.groupby(test.date.dt.to_period("W-MON")):
        ref = g.date.min()
        if (df.date < ref).sum() < 300:
            continue
        dc = DixonColes(**k["dc"]).fit(df, ref_date=ref)
        po = PoissonModel(**k["po"]).fit(df, ref_date=ref)
        ba = BayesModel(**k["ba"]).fit(df, ref_date=ref)
        if em_month != (ref.year, ref.month):
            em, em_month = EloModel().fit(ep, df, ref_date=ref), (ref.year, ref.month)
        rc = rate_model(df, "hc", "ac", ref_date=ref)
        ry = rate_model(df, "hy", "ay", ref_date=ref)
        rtab = factors(fd_rows(df[df.date < ref], ry), ref) if has_ref and ry else {}
        for r in g.itertuples():
            n = bool(neu[r.Index])
            row = {"lg": code, "ix": r.Index, "date": r.date, "home": r.home, "away": r.away, "neutral": n,
                   "hg": int(r.hg), "ag": int(r.ag), "hthg": getattr(r, "hthg", np.nan), "htag": getattr(r, "htag", np.nan),
                   "rho": dc.rho, "ht_frac": dc.ht_frac}
            for name, mdl, rho in (("poisson", po, 0.0), ("dixon_coles", dc, dc.rho), ("bayes", ba, 0.0)):
                lam, mu = mdl.rates(r.home, r.away, n)
                row.update(zip([f"{name}_H", f"{name}_D", f"{name}_A", f"{name}_O"], probs_from_rates(lam, mu, rho)))
                if name == "dixon_coles":
                    row["dc_lam"], row["dc_mu"] = lam, mu
            row.update(zip(["elo_H", "elo_D", "elo_A"], em.probs(ep.elo_h[r.Index], ep.elo_a[r.Index], n)))
            for c in ("oH", "oD", "oA", "oO25", "oU25", "mH", "mD", "mA", "mO25", "mU25"):
                row[c] = getattr(r, c, np.nan)
            if not any(pd.isna(row[c]) for c in ("oH", "oD", "oA")):
                row.update(zip(["mercado_H", "mercado_D", "mercado_A"], devig(np.array([r.oH, r.oD, r.oA]))))
            if not any(pd.isna(row[c]) for c in ("oO25", "oU25")):
                row["mercado_O"] = float(devig(np.array([r.oO25, r.oU25]))[0])
            if rc is not None and not pd.isna(getattr(r, "hc", np.nan)):
                row["c_h"], row["c_a"] = rc(r.home, r.away)
                row["corners"] = r.hc + r.ac
            if ry is not None and not pd.isna(getattr(r, "hy", np.nan)):
                yh, ya = ry(r.home, r.away)
                row["y_h"], row["y_a"], row["cards"] = yh, ya, r.hy + r.ay
                row["y_fac"] = 1.0
                if has_ref and isinstance(r.referee, str):
                    from .arbitros import ref_key
                    info = rtab.get(ref_key(r.referee))
                    if info:
                        row["y_fac"] = info["factor"]
                    refpairs.append({"actual": r.hy + r.ay, "expected": yh + ya, "expected_ref": (yh + ya) * row["y_fac"],
                                     "n_ref": info["partidos"] if info else 0})
            rows.append(row)
    y, yo = _labels(df)
    X = X.assign(date=df.date.values, lg=code, y=y, yo=yo)
    return pd.DataFrame(rows), X, pd.DataFrame(refpairs)


def xgb_walk_forward(bt: pd.DataFrame, feats: pd.DataFrame, every_months=1) -> pd.DataFrame:
    """XGBoost entrenado con TODAS las ligas juntas, reentrenado cada mes solo con partidos anteriores."""
    bt = bt.copy()
    for c in ("xgboost_H", "xgboost_D", "xgboost_A", "xgboost_O"):
        bt[c] = np.nan
    F = feats.set_index(["lg", "ix"])
    months = sorted(bt.date.dt.to_period("M").unique())
    for mi in range(0, len(months), every_months):
        chunk = months[mi:mi + every_months]
        start = chunk[0].start_time
        tr = feats[(feats.date < start) & trainable(feats) & (feats.date >= start - pd.Timedelta(days=365 * 7))]
        if len(tr) < 800:
            continue
        m1, m2 = train_xgb(tr, tr.y.values, "1x2"), train_xgb(tr, tr.yo.values, "o25")
        sel = bt.date.dt.to_period("M").isin(chunk)
        Xt = F.loc[list(zip(bt.loc[sel, "lg"], bt.loc[sel, "ix"]))]
        P, O = m1.predict(Xt), m2.predict(Xt)
        bt.loc[sel, ["xgboost_H", "xgboost_D", "xgboost_A"]] = P
        bt.loc[sel, "xgboost_O"] = O
    return bt


# ------------------------------------------------------------------ pesos del ensamble
def _stack(bt, models, kind):
    cols = ["H", "D", "A"] if kind == "1x2" else ["O"]
    P = np.stack([bt[[f"{m}_{c}" for c in cols]].values for m in models], axis=1)   # (n, k, c)
    if kind == "o25":
        P = np.concatenate([P, 1 - P], axis=2)
    return P


def fit_weights(P: np.ndarray, y: np.ndarray, l2=0.001) -> np.ndarray:
    k = P.shape[1]

    def loss(th):
        w = np.exp(th - th.max()); w /= w.sum()
        Q = np.einsum("nkc,k->nc", P, w)
        return -np.log(np.clip(Q[np.arange(len(y)), y], 1e-9, 1)).mean() + l2 * ((w - 1 / k) ** 2).sum()
    r = minimize(loss, np.zeros(k), method="L-BFGS-B")
    w = np.exp(r.x - r.x.max())
    return w / w.sum()


def _metrics(Q, y):
    Q = np.clip(Q, 1e-9, 1)
    n, c = Q.shape
    return {"n": int(n), "logloss": round(float(-np.log(Q[np.arange(n), y]).mean()), 4),
            "brier": round(float(((Q - np.eye(c)[y]) ** 2).sum(1).mean()), 4),
            "acierto": round(float((Q.argmax(1) == y).mean()), 4)}


def ensemble_weights(bt: pd.DataFrame) -> tuple[dict, dict, pd.DataFrame]:
    """Pesos 1X2 y over 2.5, con y sin mercado. Validación cruzada temporal: la mitad antigua ajusta los pesos que
    se evalúan en la mitad reciente y viceversa (así ningún partido se evalúa con pesos que lo vieron)."""
    y = np.select([bt.hg > bt.ag, bt.hg == bt.ag], [0, 1], 2)
    yo = 1 - ((bt.hg + bt.ag) > 2.5).astype(int).values      # índice 0 = over en el stack
    mid = bt.date.quantile(0.5)
    half = (bt.date >= mid).values
    bt = bt.copy()
    pesos, ev = {"1x2": {}, "o25": {}}, {}
    for kind, target, base in (("1x2", y, MODELOS), ("o25", yo, O25)):
        for tag, models in (("con_mercado", base), ("sin_mercado", [m for m in base if m != "mercado"])):
            cols = [f"{m}_{c}" for m in models for c in (["H", "D", "A"] if kind == "1x2" else ["O"])]
            ok = bt[cols].notna().all(axis=1).values
            if ok.sum() < 300:
                continue
            P, yy = _stack(bt[ok], models, kind), target[ok]
            pesos[kind][tag] = dict(zip(models, np.round(fit_weights(P, yy), 4).tolist()))
            # cross-fitting
            Q = np.zeros((ok.sum(), P.shape[2]))
            for train_mask in (~half[ok], half[ok]):
                if train_mask.sum() < 150 or (~train_mask).sum() < 150:
                    Q[~train_mask] = np.einsum("nkc,k->nc", P[~train_mask], np.array(list(pesos[kind][tag].values())))
                    continue
                w = fit_weights(P[train_mask], yy[train_mask])
                Q[~train_mask] = np.einsum("nkc,k->nc", P[~train_mask], w)
            name = f"ens_{kind}_{tag}"
            cols_out = [f"{name}_{c}" for c in (["H", "D", "A"] if kind == "1x2" else ["O", "U"])]
            for j, c in enumerate(cols_out):
                bt.loc[ok, c] = Q[:, j]
            if kind == "1x2":
                ev[tag] = {"ensamble": _metrics(Q, yy), "modelos": {m: _metrics(P[:, i], yy) for i, m in enumerate(models)},
                           "periodo": [bt.date[ok].min().strftime("%Y-%m-%d"), bt.date[ok].max().strftime("%Y-%m-%d")]}
                if tag == "con_mercado":
                    i_dc, i_mk = models.index("dixon_coles"), models.index("mercado")
                    ev[tag]["metodo_anterior"] = _metrics(0.75 * P[:, i_mk] + 0.25 * P[:, i_dc], yy)
            else:
                ev[f"o25_{tag}"] = {"ensamble": _metrics(Q, yy), "modelos": {m: _metrics(P[:, i], yy) for i, m in enumerate(models)}}
    # predicción final de cada fila: con mercado si lo hay
    for c_new, a, b in (("ens_H", "ens_1x2_con_mercado_H", "ens_1x2_sin_mercado_H"), ("ens_D", "ens_1x2_con_mercado_D", "ens_1x2_sin_mercado_D"),
                        ("ens_A", "ens_1x2_con_mercado_A", "ens_1x2_sin_mercado_A"), ("ens_O", "ens_o25_con_mercado_O", "ens_o25_sin_mercado_O")):
        bt[c_new] = bt[a].fillna(bt[b]) if a in bt else bt.get(b)
    return pesos, ev, bt


# ------------------------------------------------------------------ calibración y picks simulados
def isotonic(x, y, w):
    """Regresión isotónica (pool adjacent violators): la probabilidad real nunca baja cuando sube la declarada."""
    blocks = [[xi, yi, wi] for xi, yi, wi in zip(x, y, w)]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][1] > blocks[i + 1][1]:
            a, b = blocks[i], blocks[i + 1]
            wt = a[2] + b[2]
            blocks[i] = [(a[0] * a[2] + b[0] * b[2]) / wt, (a[1] * a[2] + b[1] * b[2]) / wt, wt]
            del blocks[i + 1]
            i = max(i - 1, 0)
        else:
            i += 1
    return [[round(b[0], 4), round(b[1], 4)] for b in blocks]


def simulate_picks(bt: pd.DataFrame) -> pd.DataFrame:
    """Para cada partido del backtest: matriz del ensamble -> todos los tipos de pick -> ¿se ganó?"""
    out = []
    for r in bt.itertuples():
        if pd.isna(r.ens_H) or pd.isna(r.ens_O):
            continue
        lam, mu = implied_rates_fast(r.ens_H, r.ens_A, r.ens_O, r.rho, r.dc_lam, r.dc_mu)
        corners = (r.c_h, r.c_a) if not pd.isna(getattr(r, "c_h", np.nan)) else None
        cards = (r.y_h * r.y_fac, r.y_a * r.y_fac) if not pd.isna(getattr(r, "y_h", np.nan)) else None
        mk = all_markets(lam, mu, r.rho, r.ht_frac, corners, cards)
        res = {"hg": r.hg, "ag": r.ag, "hthg": r.hthg, "htag": r.htag,
               "corners": getattr(r, "corners", None), "cards": getattr(r, "cards", None)}
        for _, path, _ in PICK_LABELS:
            p = get(mk, path)
            if p is None or p < PICK_MIN:
                continue
            ok = settle(path, res)
            if ok is None:
                continue
            l1, l2, l3 = levels(path)
            out.append((r.date, r.lg, l1, l2, l3, float(p), bool(ok)))
    return pd.DataFrame(out, columns=["date", "lg", "l1", "l2", "l3", "p", "ok"])


def calibration(picks: pd.DataFrame) -> tuple[list, list]:
    bins = np.r_[np.arange(0.40, 0.95, 0.05), 0.97, 1.0]
    tab, xs, ys, ws = [], [], [], []
    for a, b in zip(bins[:-1], bins[1:]):
        m = (picks.p >= a) & (picks.p < b)
        if m.sum() < 30:
            continue
        pm, fr, n = float(picks.p[m].mean()), float(picks.ok[m].mean()), int(m.sum())
        tab.append({"rango": f"{a * 100:.0f}-{b * 100:.0f}%", "declarada": round(pm, 3), "real": round(fr, 3), "n": n})
        xs.append(pm); ys.append(fr); ws.append(n)
    return tab, isotonic(xs, ys, ws)


def subtype_stats(picks: pd.DataFrame) -> dict:
    """Por nivel de cuota (segura/media/alta) y por subtipo: casos, aciertos, probabilidad media declarada, últimos 10."""
    out = {}
    for band, lo, hi in BANDS:
        p = picks[(picks.p >= lo) & (picks.p < hi)].sort_values("date")
        out[band] = {}
        for lvl in ("l1", "l2", "l3"):
            d = {}
            for k, g in p.groupby(lvl):
                d[k] = {"n": int(len(g)), "aciertos": int(g.ok.sum()), "ultimos10": [int(x) for x in g.ok.values[-10:]],
                        "prob_media": round(float(g.p.mean()), 3)}
            out[band][lvl] = d
    return out


def band_summary(picks: pd.DataFrame) -> dict:
    """Acierto real vs declarado de cada nivel en el backtest (lo que el usuario puede esperar)."""
    out = {}
    for band, lo, hi in BANDS:
        g = picks[(picks.p >= lo) & (picks.p < hi)]
        if len(g):
            out[band] = {"n": int(len(g)), "declarada": round(float(g.p.mean()), 3), "real": round(float(g.ok.mean()), 3),
                         "cuota_justa_media": round(float((1 / g.p).mean()), 2)}
    return out


# ------------------------------------------------------------------ calibración completa (semanal)
def calibrar(leagues: dict, now=None, verbose=True, P=None) -> dict:
    log = print if verbose else (lambda *a, **k: None)
    now = now or datetime.now(timezone.utc)
    t0 = time.time()
    bts, feats, refs = [], [], []
    for code, df in leagues.items():
        t = time.time()
        bt, X, rp = league_backtest(code, df, _test_start(code, df, now.replace(tzinfo=None)))
        log(f"  backtest {code}: {len(bt)} partidos ({time.time() - t:.0f}s)")
        bts.append(bt); feats.append(X.assign(ix=X.index)); refs.append(rp)
    bt = pd.concat(bts, ignore_index=True)
    feats = pd.concat(feats, ignore_index=True)
    t = time.time()
    bt = xgb_walk_forward(bt, feats)
    log(f"  XGBoost walk-forward ({time.time() - t:.0f}s)")
    pesos, ev, bt = ensemble_weights(bt)
    t = time.time()
    picks = simulate_picks(bt)
    log(f"  picks simulados: {len(picks)} ({time.time() - t:.0f}s)")
    tabla_cal, curva = calibration(picks)
    # métricas por liga (formato del backtest anterior, ahora con el ensamble como "modelo")
    ligas = {}
    for code, g in bt.groupby("lg"):
        g = g.dropna(subset=["ens_H"]).rename(columns={"ens_H": "pH", "ens_D": "pD", "ens_A": "pA"})
        g = g.assign(pO25=g.ens_O)
        if len(g) >= 50:
            ligas[code] = evaluate(g[["date", "home", "away", "hg", "ag", "pH", "pD", "pA", "pO25", "oH", "oD", "oA",
                                      "oO25", "oU25", "mH", "mD", "mA", "mO25", "mU25"]])
            ligas[code]["desde"] = g.date.min().strftime("%Y-%m-%d")
    refp = pd.concat(refs, ignore_index=True) if refs else pd.DataFrame()
    arb = validate_refs(refp) if not refp.empty else {"n": 0}
    arb["k"] = REF_K
    out = {"version": 3, "fecha": now.isoformat(), "segundos": round(time.time() - t0),
           "pesos": pesos, "evaluacion": ev, "calibracion": tabla_cal, "curva": curva,
           "subtipos": subtype_stats(picks), "niveles": band_summary(picks), "picks_simulados": int(len(picks)),
           "acierto_simulado_70": round(float(picks.ok[picks.p >= 0.7].mean()), 4) if len(picks) else None,
           "ligas": ligas, "arbitros": arb, "nombres": NOMBRES}
    if P is not None:
        from .players import validate_players
        out["validacion_jugadores"] = {}
        for code in leagues:
            try:
                out["validacion_jugadores"][code] = validate_players(P, code)
            except Exception as e:  # la validación de jugadores nunca debe romper la calibración
                log(f"  validación jugadores {code}: {e}")
    log(f"Calibración lista en {time.time() - t0:.0f}s")
    return out


def load_cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_cache(c):
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, default=float)


def cache_is_fresh(c, now) -> bool:
    if not c or c.get("version") != 3:
        return False
    age = (now - datetime.fromisoformat(c["fecha"])).total_seconds() / 86400
    return age < MAX_AGE_DAYS


def calibrate_prob(p: float, curva: list) -> float:
    """Probabilidad declarada -> probabilidad real observada (curva isotónica del backtest)."""
    if not curva or len(curva) < 2:
        return p
    xs, ys = zip(*curva)
    if p <= xs[0]:
        return float(min(p, ys[0] + (p - xs[0])))
    return float(np.interp(p, xs, ys))


# ------------------------------------------------------------------ motor de producción
class Motor:
    """Los 6 modelos ajustados con todos los datos disponibles hoy."""

    def __init__(self, leagues: dict, cache: dict, verbose=True):
        log = print if verbose else (lambda *a, **k: None)
        self.cache = cache
        self.m, feats = {}, []
        for code, df in leagues.items():
            k = kwargs(code)
            df = df.dropna(subset=["hg", "ag"])
            ep, R = elo_run(df, national=k["nat"])
            X, st = build_features(df, ep, k["nat"])
            y, yo = _labels(df)
            feats.append(X.assign(date=df.date.values, y=y, yo=yo))
            self.m[code] = {"dc": DixonColes(**k["dc"]).fit(df), "po": PoissonModel(**k["po"]).fit(df),
                            "ba": BayesModel(**k["ba"]).fit(df), "elo": EloModel().fit(ep, df), "R": R, "st": st,
                            "nat": k["nat"], "last_season": df.season.iloc[-1]}
        F = pd.concat(feats, ignore_index=True)
        now = F.date.max()
        tr = F[trainable(F) & (F.date >= now - pd.Timedelta(days=365 * 7))]
        self.xgb1, self.xgb2 = train_xgb(tr, tr.y.values, "1x2"), train_xgb(tr, tr.yo.values, "o25")
        log(f"  XGBoost entrenado con {len(tr)} partidos")

    def predict(self, code, home, away, neutral=False, date=None, odds=None) -> dict:
        m = self.m[code]
        out = {}
        rates = {}
        for name, mdl, rho in (("poisson", m["po"], 0.0), ("dixon_coles", m["dc"], m["dc"].rho), ("bayes", m["ba"], 0.0)):
            lam, mu = mdl.rates(home, away, neutral)
            rates[name] = (lam, mu)
            out[name] = dict(zip(["1", "X", "2", "o25"], map(float, probs_from_rates(lam, mu, rho))))
        new = 1500.0 if m["nat"] else 1420.0
        eh, ea = m["R"].get(home, new), m["R"].get(away, new)
        out["elo"] = dict(zip(["1", "X", "2"], m["elo"].probs(eh, ea, neutral)))
        date = pd.Timestamp(date).tz_localize(None) if date is not None else pd.Timestamp.now()
        row = pd.DataFrame([m["st"].row(home, away, date, neutral, 1.0, eh, ea)])
        P, O = self.xgb1.predict(row)[0], self.xgb2.predict(row)[0]
        out["xgboost"] = {"1": float(P[0]), "X": float(P[1]), "2": float(P[2]), "o25": float(O)}
        if odds and odds.get("H") and odds.get("D") and odds.get("A"):
            pm = devig(np.array([odds["H"], odds["D"], odds["A"]]))
            out["mercado"] = {"1": float(pm[0]), "X": float(pm[1]), "2": float(pm[2])}
            if odds.get("over") and odds.get("under") and odds.get("ou_line") == 2.5:
                out["mercado"]["o25"] = float(devig(np.array([odds["over"], odds["under"]]))[0])
        return {"modelos": out, "dc": m["dc"], "rates": rates, "elo": (eh, ea)}

    def combine(self, pred: dict) -> dict:
        """Mezcla lineal con los pesos calibrados. Devuelve 1X2, over 2.5 y los pesos usados."""
        mods = pred["modelos"]
        pw = self.cache["pesos"]
        tag = "con_mercado" if "mercado" in mods else "sin_mercado"
        w1 = {k: v for k, v in pw["1x2"][tag].items() if k in mods}
        s = sum(w1.values())
        p = {c: sum(w * mods[k][c] for k, w in w1.items()) / s for c in ("1", "X", "2")}
        tag_o = "con_mercado" if "o25" in mods.get("mercado", {}) else "sin_mercado"
        wo = {k: v for k, v in pw["o25"][tag_o].items() if k in mods and "o25" in mods[k]}
        so = sum(wo.values())
        p["o25"] = sum(w * mods[k]["o25"] for k, w in wo.items()) / so
        # sin mercado (para medir el desacuerdo con las casas)
        ws = {k: v for k, v in pw["1x2"]["sin_mercado"].items() if k in mods}
        ss = sum(ws.values())
        own = {c: sum(w * mods[k][c] for k, w in ws.items()) / ss for c in ("1", "X", "2")}
        return {"p": p, "pesos": {k: round(v / s, 4) for k, v in w1.items()}, "pesos_o25": {k: round(v / so, 4) for k, v in wo.items()},
                "propio": own}

    def rates_for(self, pred: dict, comb: dict) -> tuple[float, float]:
        dc = pred["dc"]
        lam0, mu0 = pred["rates"]["dixon_coles"]
        p = comb["p"]
        return implied_rates_fast(p["1"], p["2"], p["o25"], dc.rho, lam0, mu0)

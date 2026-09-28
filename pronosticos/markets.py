"""Probabilidades de todos los mercados a partir de la matriz de marcadores."""
from __future__ import annotations

import numpy as np
from scipy.stats import poisson

from .model import score_matrix


def _r(x):
    return round(float(x), 4)


def asian_handicap(M: np.ndarray, line: float):
    """Devuelve (p_gana, p_devuelve, p_pierde) para el LOCAL con hándicap `line` (p.ej. -1.5, -0.25)."""
    n = M.shape[0]
    diff = np.subtract.outer(np.arange(n), np.arange(n))  # goles local - visita

    def settle(l):
        adj = diff + l
        return M[adj > 0].sum(), M[adj == 0].sum(), M[adj < 0].sum()

    if abs(line * 4) % 2 == 1:  # línea de cuarto: mitad en cada línea vecina
        a, b = settle(line - 0.25), settle(line + 0.25)
        # para cuartos, el resultado "medio" se expresa en win/push/lose equivalentes
        return tuple((x + y) / 2 for x, y in zip(a, b))
    return settle(line)


def all_markets(lam: float, mu: float, rho: float, ht_frac: float = 0.44,
                corners: tuple | None = None, cards: tuple | None = None) -> dict:
    M = score_matrix(lam, mu, rho)
    n = M.shape[0]
    i, j = np.indices(M.shape)
    tot = i + j
    pH, pD, pA = M[i > j].sum(), M[i == j].sum(), M[i < j].sum()
    out = {"xg_home": _r(lam), "xg_away": _r(mu)}

    out["1x2"] = {"1": _r(pH), "X": _r(pD), "2": _r(pA)}
    out["doble_oportunidad"] = {"1X": _r(pH + pD), "12": _r(pH + pA), "X2": _r(pD + pA)}
    out["empate_no_apuesta"] = {"1": _r(pH / (pH + pA)), "2": _r(pA / (pH + pA))}

    out["goles_totales"] = {f"{ln}": {"over": _r(M[tot > ln].sum()), "under": _r(M[tot < ln].sum())}
                            for ln in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5)}
    out["goles_local"] = {f"{ln}": {"over": _r(M[i > ln].sum()), "under": _r(M[i < ln].sum())} for ln in (0.5, 1.5, 2.5, 3.5)}
    out["goles_visita"] = {f"{ln}": {"over": _r(M[j > ln].sum()), "under": _r(M[j < ln].sum())} for ln in (0.5, 1.5, 2.5, 3.5)}
    btts = M[(i > 0) & (j > 0)].sum()
    out["ambos_marcan"] = {"si": _r(btts), "no": _r(1 - btts)}
    out["ambos_marcan_y_resultado"] = {
        "1_y_si": _r(M[(i > j) & (j > 0)].sum()), "X_y_si": _r(M[(i == j) & (i > 0)].sum()), "2_y_si": _r(M[(i < j) & (i > 0)].sum()),
        "1_y_no": _r(M[(i > j) & (j == 0)].sum()), "X_y_no": _r(M[0, 0]), "2_y_no": _r(M[(i < j) & (i == 0)].sum()),
    }
    out["resultado_y_goles_2.5"] = {f"{r}_{ou}": _r(M[cond & (tot > 2.5 if ou == 'over' else tot < 2.5)].sum())
                                    for r, cond in (("1", i > j), ("X", i == j), ("2", i < j)) for ou in ("over", "under")}
    out["valla_invicta"] = {"local": _r(M[:, 0].sum()), "visita": _r(M[0, :].sum())}
    out["gana_sin_recibir"] = {"local": _r(M[1:, 0].sum()), "visita": _r(M[0, 1:].sum())}
    out["goles_exactos"] = {str(k) if k < 6 else "6+": _r(M[tot == k].sum() if k < 6 else M[tot >= 6].sum()) for k in range(7)}
    out["par_impar"] = {"par": _r(M[tot % 2 == 0].sum()), "impar": _r(M[tot % 2 == 1].sum())}
    margin = {}
    for k in (1, 2, 3):
        margin[f"local_por_{k}"] = _r(M[(i - j) == k].sum())
        margin[f"visita_por_{k}"] = _r(M[(j - i) == k].sum())
    margin["local_por_4+"] = _r(M[(i - j) >= 4].sum())
    margin["visita_por_4+"] = _r(M[(j - i) >= 4].sum())
    out["margen_victoria"] = margin
    ah = {}
    for ln in (-2.5, -2, -1.5, -1.25, -1, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5):
        w, p, l = asian_handicap(M, ln)
        ah[f"{ln:+g}"] = {"gana": _r(w), "devuelve": _r(p), "pierde": _r(l)}
    out["handicap_asiatico_local"] = ah
    cs = sorted(((M[a, b], f"{a}-{b}") for a in range(7) for b in range(7)), reverse=True)
    out["marcador_exacto"] = {k: _r(v) for v, k in cs[:12]}

    # ---- primer tiempo / segundo tiempo (Poisson independiente por mitades)
    l1, m1 = lam * ht_frac, mu * ht_frac
    l2, m2 = lam - l1, mu - m1
    k = np.arange(n)
    H1 = np.outer(poisson.pmf(k, l1), poisson.pmf(k, m1))
    H2 = np.outer(poisson.pmf(k, l2), poisson.pmf(k, m2))
    out["primer_tiempo_1x2"] = {"1": _r(H1[i > j].sum()), "X": _r(H1[i == j].sum()), "2": _r(H1[i < j].sum())}
    out["primer_tiempo_goles"] = {f"{ln}": {"over": _r(H1[tot > ln].sum()), "under": _r(H1[tot < ln].sum())} for ln in (0.5, 1.5, 2.5)}
    out["segundo_tiempo_goles"] = {f"{ln}": {"over": _r(H2[tot > ln].sum()), "under": _r(H2[tot < ln].sum())} for ln in (0.5, 1.5, 2.5)}
    out["ambos_marcan_1T"] = {"si": _r(H1[(i > 0) & (j > 0)].sum()), "no": _r(1 - H1[(i > 0) & (j > 0)].sum())}
    # mitad con más goles
    t1 = np.bincount(tot.ravel(), H1.ravel(), 2 * n - 1)
    t2 = np.bincount(tot.ravel(), H2.ravel(), 2 * n - 1)
    T = np.outer(t1, t2)
    a_, b_ = np.indices(T.shape)
    out["mitad_con_mas_goles"] = {"1T": _r(T[a_ > b_].sum()), "igual": _r(T[a_ == b_].sum()), "2T": _r(T[a_ < b_].sum())}
    # descanso / final (HT/FT)
    htft = {}
    sign = lambda x: np.sign(x)
    # distribución conjunta de (dif_1T, dif_FT): dif_FT = dif_1T + dif_2T
    d1 = {}
    for a in range(n):
        for b in range(n):
            d1[a - b] = d1.get(a - b, 0) + H1[a, b]
    d2 = {}
    for a in range(n):
        for b in range(n):
            d2[a - b] = d2.get(a - b, 0) + H2[a, b]
    lab = {1: "1", 0: "X", -1: "2"}
    for x, px in d1.items():
        for y, py in d2.items():
            key = f"{lab[int(sign(x))]}/{lab[int(sign(x + y))]}"
            htft[key] = htft.get(key, 0) + px * py
    out["descanso_final"] = {k: _r(v) for k, v in sorted(htft.items(), key=lambda z: -z[1])}

    # ---- córners y tarjetas (Poisson sobre las tasas esperadas)
    if corners:
        ch, ca = corners
        ct = ch + ca
        out["corners"] = {"esperados_local": _r(ch), "esperados_visita": _r(ca), "esperados_total": _r(ct),
                          "total": {f"{ln}": {"over": _r(1 - poisson.cdf(int(ln), ct)), "under": _r(poisson.cdf(int(ln), ct))}
                                    for ln in (7.5, 8.5, 9.5, 10.5, 11.5, 12.5)},
                          "mas_corners": _more(ch, ca)}
    if cards:
        yh, ya = cards
        yt = yh + ya
        out["tarjetas"] = {"esperadas_local": _r(yh), "esperadas_visita": _r(ya), "esperadas_total": _r(yt),
                           "total": {f"{ln}": {"over": _r(1 - poisson.cdf(int(ln), yt)), "under": _r(poisson.cdf(int(ln), yt))}
                                     for ln in (2.5, 3.5, 4.5, 5.5, 6.5)}}
    return out


def _more(a, b):
    k = np.arange(40)
    P = np.outer(poisson.pmf(k, a), poisson.pmf(k, b))
    i, j = np.indices(P.shape)
    return {"local": _r(P[i > j].sum()), "igual": _r(P[i == j].sum()), "visita": _r(P[i < j].sum())}

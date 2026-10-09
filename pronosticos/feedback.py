"""Feedback de resultados: lo ya liquidado corrige los pronósticos siguientes. Se recalcula en cada corrida.

1. Córners y tarjetas por grupo de competición (S1). Nivel r = (Σreal + a·ē) / (Σesperado + a·ē), con a = 10 partidos y
   ē la media esperada. Dispersión: binomial negativa con tamaño phi por máxima verosimilitud en una grilla (None = Poisson),
   con los partidos reales del grupo si hay 50 o más, si no la del backtest. p = NB_cdf(línea; esp·r, phi).
2. Goles y resultado según la fuente. Con cuota de mercado la curva global ya está calibrada: p_real = pc. Sin mercado:
   Platt logit p' = a + b·logit pc, ajustado con los picks reales sin mercado, pérdida dividida por el efecto de diseño
   (varios picks del mismo partido no son independientes) y ridge 5 hacia el Platt del backtest sin mercado.
3. Veto del historial. Celda = grupo × fuente × familia|lado × banda de 10 puntos. Prior Beta del backtest de la misma celda
   (fuerza hasta 200 picks) + conteos reales divididos por el efecto de diseño (solo si el grupo ya tiene 150 partidos
   liquidados). La celda se bloquea si P(real/declarado < 0.95) > 0.8. El historial ya no suma puntaje: solo veta.
4. Córners en selecciones: fuera de las fijas y del pick principal hasta tener 100 partidos con dato y Spearman >= 0.15
   entre córners esperados y reales.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
from scipy.optimize import minimize
from scipy.stats import beta, nbinom, poisson, spearmanr

from .ensamble import calibrate_prob
from .markets import count_cdf
from .picks import FAMILY, GRUPOS, LEGACY, grupo, settle

EPS = 1e-4
A_CC = 10                     # partidos de prior para el nivel de córners/tarjetas
PHI_GRID = (None, 200, 100, 50, 30, 20, 15, 10, 7, 5)
MIN_PHI_N = 50                # partidos con dato para estimar la dispersión con resultados reales
PLATT_LAMBDA = 5.0
MIN_PLATT_PARTIDOS = 10           # con pocos partidos el ridge ya lo deja cerca del centro
VETO_K, VETO_RATIO, VETO_P = 200, 0.95, 0.80
VETO_MIN_PARTIDOS = 150       # partidos liquidados del grupo para usar sus datos reales en el veto
VETO_MIN_BT = 30              # picks del backtest para usar la celda como prior
GATE_N, GATE_RHO = 100, 0.15
CONTEOS = {"corners": ("corners_esp", "corners"), "tarjetas": ("tarjetas_esp", "cards")}
SIN_PLATT = {"co", "ca"}       # córners/tarjetas: su corrección es S1
FUERA_AJUSTE_PLATT = {"co", "ca", "ah"}   # el hándicap viejo guardaba la probabilidad sin condicionar


def logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sig(x):
    return 1 / (1 + np.exp(-np.asarray(x, float)))


def fuente_de(con_mercado: bool) -> str:
    return "mercado" if con_mercado else "modelo"


def banda10(p: float) -> str:
    return str(int(min(9, max(4, math.floor(p * 10 + 1e-9)))) * 10)


def familia(path) -> str:
    return FAMILY.get("|".join(path), path[0])


def celda(grp: str, fuente: str, path, p: float) -> str:
    return f"{grp}|{fuente}|{familia(path)}|{path[-1]}|{banda10(p)}"


def deff(ok, p, ids) -> float:
    """Efecto de diseño por partido: varianza de la suma de errores por partido / suma de varianzas individuales."""
    e = np.asarray(ok, float) - np.asarray(p, float)
    _, inv = np.unique(np.asarray(ids), return_inverse=True)
    E = np.bincount(inv, weights=e)
    return max(1.0, float((E ** 2).sum() / max((e ** 2).sum(), 1e-9)))


# ------------------------------------------------------------------ 1. córners y tarjetas
def phi_ml(y, mu, grid=PHI_GRID):
    y = np.asarray(y).astype(int)
    mu = np.asarray(mu, float)

    def ll(phi):
        if phi is None:
            return float(poisson.logpmf(y, mu).sum())
        return float(nbinom.logpmf(y, phi, phi / (phi + mu)).sum())
    return max(grid, key=ll)


def ajustar_conteo(esp, y, r0: float = 1.0, phi0=None, a: float = A_CC) -> dict:
    esp, y = np.asarray(esp, float), np.asarray(y, float)
    if len(y) == 0:
        return {"r": float(r0), "phi": phi0, "n": 0}
    aa = a * esp.mean()
    r = (y.sum() + aa * r0) / (esp.sum() + aa)
    phi = phi_ml(y, esp * r) if len(y) >= MIN_PHI_N else phi0
    return {"r": round(float(r), 4), "phi": phi, "n": int(len(y))}


def prob_conteo(esp_base: float, ajuste: dict | None, path) -> float:
    """Probabilidad de un pick de córners/tarjetas desde el valor esperado sin ajustar."""
    r, phi = (ajuste or {}).get("r", 1.0), (ajuste or {}).get("phi")
    cdf = count_cdf(int(float(path[2])), esp_base * r, phi)
    return cdf if path[-1] == "under" else 1 - cdf


def _valido(v) -> bool:
    """Número finito y no negativo (los conteos y esperados no pueden ser otra cosa)."""
    return (isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool)
            and math.isfinite(float(v)) and float(v) >= 0)


def params_conteo(registros: list, cache: dict | None) -> dict:
    """{grupo: {"corners": {r, phi, n}, "tarjetas": {...}}} con los partidos liquidados (y el prior del backtest)."""
    bt = (cache or {}).get("cc_backtest") or {}
    pares = defaultdict(lambda: ([], []))
    for rec in registros:
        res = rec.get("resultado") or {}
        for stat, (k_esp, k_real) in CONTEOS.items():
            e, y = rec.get(k_esp), res.get(k_real)
            if _valido(e) and _valido(y) and e > 0:
                pares[(grupo(rec["liga"]), stat)][0].append(float(e))
                pares[(grupo(rec["liga"]), stat)][1].append(float(y))
    grupos = set(GRUPOS.values()) | {"clubes"} | set(bt)
    out = {}
    for g in sorted(grupos):
        for stat in CONTEOS:
            b = (bt.get(g) or {}).get(stat) or {}
            e, y = pares.get((g, stat), ([], []))
            out.setdefault(g, {})[stat] = ajustar_conteo(e, y, b.get("r", 1.0), b.get("phi"))
    return out


def cc_markets(cc_grupo: dict | None) -> dict | None:
    """Formato que espera markets.all_markets: {"corners": (r, phi), "tarjetas": (r, phi)}."""
    if not cc_grupo:
        return None
    return {s: (v["r"], v["phi"]) for s, v in cc_grupo.items()}


# ------------------------------------------------------------------ 2. Platt sin mercado
def ajustar_platt(pc, y, ids, lam: float = PLATT_LAMBDA, centro=(0.0, 1.0)) -> tuple:
    pc, y = np.asarray(pc, float), np.asarray(y, float)
    if len(np.unique(ids)) < MIN_PLATT_PARTIDOS:
        return float(centro[0]), float(centro[1])
    d = deff(y, pc, ids)
    x0 = logit(pc)
    c0, c1 = centro

    def nll(w):
        p = np.clip(sig(w[0] + w[1] * x0), 1e-12, 1 - 1e-12)
        return -(y * np.log(p) + (1 - y) * np.log(1 - p)).sum() / d + lam * ((w[0] - c0) ** 2 + (w[1] - c1) ** 2)
    r = minimize(nll, [c0, c1], method="Nelder-Mead")
    return float(r.x[0]), float(r.x[1])


def aplicar_platt(pc: float, platt: dict | None) -> float:
    if not platt:
        return float(pc)
    return float(sig(platt["a"] + platt["b"] * logit(pc)))


def prob_real(path, pc: float, fuente: str, platt: dict | None) -> float:
    """Probabilidad publicada: la curva global; además Platt en goles/resultado sin cuota de mercado."""
    if familia(path) in SIN_PLATT or fuente == "mercado":
        return float(pc)
    return aplicar_platt(pc, platt)


# ------------------------------------------------------------------ filas de picks reales
def picks_reales(registros: list, curva, cc: dict | None = None) -> list[dict]:
    """Picks liquidados con su probabilidad recalculada como hoy (córners/tarjetas con el ajuste vigente)."""
    rows = []
    for rec in registros:
        res = rec.get("resultado") or {}
        g = grupo(rec["liga"])
        fuente = fuente_de(bool(rec.get("mercado")))
        for k, pr in rec.get("picks") or []:
            if k in LEGACY:                   # hándicap viejo sin condicionar: no se mezcla con las celdas nuevas
                continue
            path = tuple(k.split("|"))
            ok = settle(path, res)
            if ok is None:
                continue
            p = pr
            if path[0] in CONTEOS and cc is not None:
                e = rec.get(CONTEOS[path[0]][0])
                if _valido(e) and e > 0:
                    p = prob_conteo(float(e), (cc.get(g) or {}).get(path[0]), path)
            rows.append({"id": rec["id"], "fecha": rec["fecha"], "grupo": g, "fuente": fuente, "path": path, "fam": familia(path),
                         "p": float(p), "pc": calibrate_prob(float(p), curva), "ok": int(ok)})
    return rows


def params_platt(rows: list, cache: dict | None) -> dict:
    centro = tuple(((cache or {}).get("platt_backtest") or {}).get("ab") or (0.0, 1.0))
    sel = [r for r in rows if r["fuente"] == "modelo" and r["fam"] not in FUERA_AJUSTE_PLATT]
    ids = [r["id"] for r in sel]
    a, b = ajustar_platt([r["pc"] for r in sel], [r["ok"] for r in sel], ids, centro=centro)
    return {"a": round(a, 4), "b": round(b, 4), "picks": len(sel), "partidos": len(set(ids)),
            "centro": [round(float(centro[0]), 4), round(float(centro[1]), 4)]}


# ------------------------------------------------------------------ 3. veto por celda
def posterior_celda(real: dict | None, bt, p_now: float | None = None) -> dict:
    """real: {n, h, sd, deff} (o None si no se usan datos reales); bt: [n, aciertos, suma_declarada] del backtest."""
    n_bt, h_bt, sd_bt = bt or (0, 0, 0.0)
    n, h, sd, de = (real["n"], real["h"], real["sd"], real["deff"]) if real else (0, 0, 0.0, 1.0)
    pbar = max(sd / n if n else (sd_bt / n_bt if n_bt else (p_now or 0.5)), 1e-6)
    if n_bt >= VETO_MIN_BT and sd_bt > 0:
        rho0, k = h_bt / sd_bt, min(VETO_K, n_bt)
    else:
        rho0, k = 1.0, VETO_MIN_BT
    m0 = min(0.99, max(0.01, rho0 * pbar))
    a = k * m0 + h / de
    b = k * (1 - m0) + (n - h) / de
    p_bad = float(beta.cdf(VETO_RATIO * pbar, a, b))
    return {"bloqueada": p_bad > VETO_P, "p_exagera": round(p_bad, 3), "ratio_post": round(a / (a + b) / pbar, 3),
            "n": int(n), "aciertos": int(h), "n_bt": int(n_bt), "aciertos_bt": int(h_bt),
            "declarada": round(pbar, 3), "fuente": "real" if n else "backtest"}


def tabla_real(rows: list, platt: dict | None) -> dict:
    """Conteos reales por celda, con la probabilidad declarada como la publicaría hoy el motor."""
    acc = defaultdict(lambda: {"ok": [], "p": [], "id": []})
    for r in rows:
        decl = prob_real(r["path"], r["pc"], r["fuente"], platt)
        c = acc[celda(r["grupo"], r["fuente"], r["path"], decl)]
        c["ok"].append(r["ok"]); c["p"].append(decl); c["id"].append(r["id"])
    return {k: {"n": len(v["ok"]), "h": int(sum(v["ok"])), "sd": float(sum(v["p"])), "deff": deff(v["ok"], v["p"], v["id"])}
            for k, v in acc.items()}


def info_celda(fb: dict, key: str, p_now: float) -> dict:
    if key in fb["celdas"]:
        return fb["celdas"][key]
    return posterior_celda(None, fb["bt_celdas"].get(key), p_now)


# ------------------------------------------------------------------ 4. córners en selecciones
def puerta_corners(registros: list, g: str = "selecciones") -> dict:
    e, y = [], []
    for rec in registros:
        if grupo(rec["liga"]) != g:
            continue
        ce, cr = rec.get("corners_esp"), (rec.get("resultado") or {}).get("corners")
        if _valido(ce) and _valido(cr):
            e.append(ce); y.append(cr)
    rho = float(spearmanr(e, y).correlation) if len(e) >= 10 else None
    return {"n": len(e), "spearman": round(rho, 3) if rho is not None and not math.isnan(rho) else None,
            "abierta": len(e) >= GATE_N and rho is not None and rho >= GATE_RHO, "min_n": GATE_N, "min_spearman": GATE_RHO}


# ------------------------------------------------------------------ todo junto (una vez por corrida)
def liquidados(hist: dict) -> list:
    return [r for r in hist["partidos"].values() if (r.get("resultado") or {}).get("hg") is not None]


def calcular(hist: dict, cache: dict) -> dict:
    regs = liquidados(hist)
    curva = cache.get("curva")
    cc = params_conteo(regs, cache)
    rows = picks_reales(regs, curva, cc)
    platt = params_platt(rows, cache)
    partidos = defaultdict(set)
    for r in rows:
        partidos[r["grupo"]].add(r["id"])
    usar = {g: len(ids) >= VETO_MIN_PARTIDOS for g, ids in partidos.items()}
    real = tabla_real(rows, platt)
    bt = cache.get("celdas") or {}
    celdas = {}
    for key in set(real) | set(bt):
        g = key.split("|")[0]
        celdas[key] = posterior_celda(real.get(key) if usar.get(g) else None, bt.get(key))
    return {"cc": cc, "platt": platt, "celdas": celdas, "bt_celdas": bt, "usar_real": usar,
            "partidos_grupo": {g: len(v) for g, v in partidos.items()}, "puerta_corners": puerta_corners(regs)}


def corners_bloqueados(fb: dict | None, grp: str) -> bool:
    """Córners fuera de fijas y pick principal (solo selecciones, hasta que la puerta se abra)."""
    return bool(fb) and grp == "selecciones" and not fb["puerta_corners"]["abierta"]


def resumen(fb: dict) -> dict:
    """Lo que se publica en la web (metodología): parámetros vigentes y celdas bloqueadas por grupo."""
    bloq = defaultdict(int)
    for k, v in fb["celdas"].items():
        if v["bloqueada"]:
            bloq[k.split("|")[0]] += 1
    return {"conteos": fb["cc"], "platt_sin_mercado": fb["platt"], "partidos_grupo": fb["partidos_grupo"],
            "veto": {"celdas_bloqueadas": dict(bloq), "usa_datos_reales": fb["usar_real"], "k": VETO_K, "ratio": VETO_RATIO,
                     "p": VETO_P, "min_partidos": VETO_MIN_PARTIDOS},
            "puerta_corners_selecciones": fb["puerta_corners"]}


# ------------------------------------------------------------------ lado backtest (lo usa ensamble.calibrar)
def cc_backtest(bt) -> dict:
    """Dispersión de córners y tarjetas por grupo en el backtest (prior de phi en S1 y simulación de picks).
    El nivel del prior queda en 1: el ratio real/esperado del backtest cambia entre periodos (tarjetas de clubes: 0.946 en
    la 1ra mitad, 0.978 en la 2da) y centrarlo ahí empeoró el log-loss fuera de muestra (+1.5e-3). Se guarda como
    "r_backtest" solo para mostrarlo."""
    out = {}
    g = bt.lg.map(grupo)
    specs = {"corners": (("c_h", "c_a"), "corners", None), "tarjetas": (("y_h", "y_a"), "cards", "y_fac")}
    for stat, ((ch, ca), real, fac) in specs.items():
        if ch not in bt or real not in bt:
            continue
        ok = bt[ch].notna() & bt[real].notna()
        esp = (bt[ch] + bt[ca]) * (bt[fac].fillna(1.0) if fac and fac in bt else 1.0)
        for grp, idx in bt[ok].groupby(g[ok]).groups.items():
            e, y = esp.loc[idx].values.astype(float), bt.loc[idx, real].values.astype(float)
            if len(y) < MIN_PHI_N or e.sum() <= 0:
                continue
            out.setdefault(grp, {})[stat] = {"r": 1.0, "r_backtest": round(float(y.sum() / e.sum()), 4), "phi": phi_ml(y, e),
                                             "n": int(len(y))}
    return out


def platt_backtest(picks, curva) -> dict:
    sel = picks[(picks.src == "modelo") & ~picks.fam.isin(FUERA_AJUSTE_PLATT)]
    if sel.empty:
        return {"ab": [0.0, 1.0], "n": 0}
    pc = np.array([calibrate_prob(p, curva) for p in sel.p])
    a, b = ajustar_platt(pc, sel.ok.astype(float).values, sel.mid.values, centro=(0.0, 1.0))
    return {"ab": [round(a, 4), round(b, 4)], "n": int(len(sel)), "partidos": int(sel.mid.nunique())}


def celdas_backtest(picks, curva, platt_bt: dict) -> dict:
    """{celda: [n, aciertos, suma declarada]} con la probabilidad como la publicaría el motor."""
    platt = {"a": platt_bt["ab"][0], "b": platt_bt["ab"][1]}
    acc = defaultdict(lambda: [0, 0, 0.0])
    for r in picks.itertuples():
        path = tuple(r.l1.split("|"))
        decl = prob_real(path, calibrate_prob(r.p, curva), r.src, platt)
        c = acc[celda(grupo(r.lg), r.src, path, decl)]
        c[0] += 1; c[1] += int(r.ok); c[2] += decl
    return {k: [v[0], v[1], round(v[2], 3)] for k, v in acc.items()}

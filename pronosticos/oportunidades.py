"""Oportunidades y fijas: los picks que vale la pena mirar en cada partido, cruzando todas las señales.

Cada pick candidato se juzga con cinco señales; ninguna decide sola:
 1. Modelo:     probabilidad del ensamble, calibrada con el backtest (lo que declara -> lo que de verdad ocurre) y con
                los resultados reales (feedback.py): sin cuota de mercado, Platt ajustado con los picks reales sin mercado;
                córners y tarjetas, con el nivel y la dispersión reales del grupo de competición.
 2. Historial:  solo VETA. Celda = grupo × fuente (con/sin mercado) × familia|lado × banda de 10 puntos; se bloquea si
                P(real/declarado < 0.95) > 0.8 (prior del backtest de la celda + datos reales). Ya no suma puntaje: el
                ratio del historial como bonificación empeoraba la calibración en goles/resultado.
 3. Reciente:   en los últimos 8 partidos de cada equipo, ¿cuántas veces se habría cumplido este mismo pick?
 4. Jugadores:  goleadores en forma para picks de goles, tarjeteros para tarjetas, ausencia de ellos para los "menos".
 5. Cuota:      si la casa publica cuota para ese mercado, ¿paga más que la cuota justa? (un valor > 20% se toma con
                cautela: suele indicar una cuota errónea o algo que el modelo no sabe).

Oportunidad: la celda del historial no está vetada, los últimos partidos de ambos equipos lo respaldan (se cumplió al
             menos tan seguido como dice el modelo), los jugadores no lo contradicen y la cuota justa está entre 1.30 y
             2.60. Puntaje 0-100 >= 74; hasta 3 por partido, 1 por grupo de mercado.
Fija:        oportunidad donde todo confirma: puntaje >= 82, lo reciente supera la probabilidad por 8 puntos o más, los
             jugadores no lo contradicen y la cuota no es sospechosa. En selecciones no son fijas "Menos de 4.5 goles"
             ni los córners (estos hasta que el historial demuestre que el modelo los ordena bien). Cualquier cuota;
             máximo 1 por partido y 5 por día.
Jugadores:   picks de jugador solo si la validación de jugadores de esa liga demuestra que en ese rango no exagera.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from scipy.stats import beta

from . import feedback
from .ensamble import calibrate_prob
from .picks import LABEL, NOMBRE_GRUPO, PICK_LABELS, get, levels, odds_for, settle

GRUPO = {"res": "resultado", "dc": "resultado", "dnb": "resultado", "ah": "resultado",
         "ou": "goles", "tl": "goles", "tv": "goles", "tl2": "goles", "ht": "goles", "btts": "goles",
         "co": "corners", "ca": "tarjetas"}
MIN_N = 30               # casos mínimos de la validación de jugadores
MIN_CUOTA = 1.30         # por debajo no se considera oportunidad
MAX_CUOTA = 2.60
MARGEN = 1.05            # cuota mínima recomendada = cuota justa + 5%
RECIENTES = 8
MAX_OPORT = 3
# Umbrales reescalados al quitar el peso del historial (antes 65 y 75): con las señales restantes el puntaje sube y 65/75
# daban 745 oportunidades y 329 candidatas a fija en 311 partidos (antes 462 y 157). 74/82 conservan la selectividad.
MIN_PUNTAJE = 74
FIJA_PUNTAJE = 82
FIJAS_DIA = 5
DIAS_FIJAS = 3
VOLUMEN_30D = 100
VALOR_SOSPECHOSO = 0.20
# El historial ya no suma: su 0.30 se repartió en proporción entre las demás señales (siguen sumando 1).
_BASE = {"reciente": 0.25, "jugadores": 0.15, "cuota": 0.15, "probabilidad": 0.15}
PESOS = {"historial": 0.0, **{k: round(v / sum(_BASE.values()), 4) for k, v in _BASE.items()}}
NO_FIJA = {"selecciones": {"goles_totales|4.5|under"}}   # subtipos que no pueden ser fija en ese grupo


def lcb(hits: int, n: int, q: float = 0.10) -> float:
    return float(beta.ppf(q, 1 + hits, 1 + n - hits))


# ------------------------------------------------------------------ señal 3: partidos recientes
def _persp(df: pd.DataFrame, team: str, as_local: bool, n: int) -> list[dict]:
    """Últimos n partidos del equipo vistos como si jugara de local (o de visita) en el partido a pronosticar."""
    d = df[(df.home == team) | (df.away == team)].tail(n)
    out = []
    num = lambda v: None if pd.isna(v) else float(v)
    for r in d.itertuples():
        home = r.home == team
        gf, ga = (r.hg, r.ag) if home else (r.ag, r.hg)
        h1f, h1a = (getattr(r, "hthg", np.nan), getattr(r, "htag", np.nan)) if home else (getattr(r, "htag", np.nan), getattr(r, "hthg", np.nan))
        corners = num(getattr(r, "hc", np.nan) + getattr(r, "ac", np.nan))
        cards = num(getattr(r, "hy", np.nan) + getattr(r, "ay", np.nan))
        row = {"hg": gf, "ag": ga, "hthg": num(h1f), "htag": num(h1a), "corners": corners, "cards": cards}
        if not as_local:
            row = {"hg": ga, "ag": gf, "hthg": row["htag"], "htag": row["hthg"], "corners": corners, "cards": cards}
        out.append(row)
    return out


def reciente(path, rows_h: list, rows_a: list):
    """Frecuencia con la que el pick se habría cumplido en los últimos partidos de ambos equipos."""
    res = [settle(path, r) for r in rows_h + rows_a]
    res = [x for x in res if x is not None]
    if len(res) < 6:
        return None
    rh = [x for x in (settle(path, r) for r in rows_h) if x is not None]
    ra = [x for x in (settle(path, r) for r in rows_a) if x is not None]
    return {"frecuencia": round(sum(res) / len(res), 3), "n": len(res),
            "local": f"{sum(rh)}/{len(rh)}" if rh else None, "visita": f"{sum(ra)}/{len(ra)}" if ra else None}


# ------------------------------------------------------------------ señal 4: jugadores
def _hot(players: list, min_p=0.30):
    """Goleadores probables que además marcaron en sus últimos partidos."""
    out = []
    for j in players or []:
        pg = j["prob"]["marca"]
        goles = sum(u["g"] > 0 for u in j.get("ultimos", [])[:4])
        if pg >= min_p and goles >= 1 and j.get("titular_prob", 0) >= 0.6:
            out.append((pg, goles, j["nombre"]))
    return sorted(out, reverse=True)


def jugadores(path, pl_h: list, pl_a: list):
    """+1 si los jugadores respaldan el pick, -1 si lo contradicen, 0 si no aplica. Con el motivo."""
    m, sel = path[0], path[-1]
    if not pl_h and not pl_a:
        return 0, None
    hot_h, hot_a = _hot(pl_h), _hot(pl_a)
    fmt = lambda h: f"{h[2]} ({h[0] * 100:.0f}% de marcar, marcó en {h[1]} de sus últimos 4)"
    goles_si = (m == "goles_totales" and sel == "over") or (m == "ambos_marcan" and sel == "si") or (m == "primer_tiempo_goles" and sel == "over")
    goles_no = (m == "goles_totales" and sel == "under") or (m == "ambos_marcan" and sel == "no") or (m == "primer_tiempo_goles" and sel == "under")
    team = None
    if m in ("goles_local",) or (m in ("1x2", "empate_no_apuesta") and sel == "1") or (m == "handicap_asiatico_local" and sel.startswith("gana")) or (m == "doble_oportunidad" and sel == "1X"):
        team = "h"
    if m in ("goles_visita",) or (m in ("1x2", "empate_no_apuesta") and sel == "2") or (m == "handicap_asiatico_local" and sel.startswith("pierde")) or (m == "doble_oportunidad" and sel == "X2"):
        team = "a"
    if m in ("goles_local", "goles_visita") and sel == "under":
        hot = hot_h if m == "goles_local" else hot_a
        return (-1, f"{fmt(hot[0])} llega en forma") if hot else (1, "sin goleadores en racha")
    if team:
        hot = hot_h if team == "h" else hot_a
        return (1, fmt(hot[0])) if hot else (0, None)
    if goles_si:
        hot = sorted(hot_h + hot_a, reverse=True)
        return (1, fmt(hot[0])) if len(hot) >= 1 else (0, None)
    if goles_no:
        hot = sorted(hot_h + hot_a, reverse=True)
        return (-1, f"{fmt(hot[0])} llega en forma") if len(hot) >= 2 else (1, "sin goleadores en racha") if not hot else (0, None)
    if m == "tarjetas":
        tarj = sorted((j["prob"]["tarjeta"], j["nombre"]) for j in (pl_h or []) + (pl_a or []) if j.get("titular_prob", 0) >= 0.6)
        muchos = [t for t in tarj if t[0] >= 0.22]
        if sel == "over":
            return (1, f"{len(muchos)} titulares con tendencia a ver tarjeta") if len(muchos) >= 3 else (-1, "pocos jugadores tarjeteros") if not muchos else (0, None)
        return (1, "pocos jugadores tarjeteros") if len(muchos) <= 1 else (-1, f"{len(muchos)} titulares con tendencia a ver tarjeta") if len(muchos) >= 4 else (0, None)
    return 0, None


# ------------------------------------------------------------------ evaluación de un pick
def _clip(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def evaluar(path, pr, ctx: dict, odds=None) -> dict | None:
    fb, grp, fuente = ctx.get("fb"), ctx.get("grupo") or "clubes", ctx.get("fuente") or "modelo"
    pc = calibrate_prob(pr, ctx["curva"])
    p_real = _clip(feedback.prob_real(path, pc, fuente, (fb or {}).get("platt")), 0.02, 0.97)
    if not (1 / MAX_CUOTA <= p_real <= 1 / MIN_CUOTA):
        return None
    key = "|".join(path)
    cel = feedback.info_celda(fb, feedback.celda(grp, fuente, path, p_real), p_real) if fb else None
    if cel and cel["bloqueada"]:
        return None                                   # en esta celda el modelo exagera (veto del historial)
    rec = reciente(path, ctx["rows_h"], ctx["rows_a"])
    if not rec or rec["frecuencia"] < p_real:
        return None                                   # sin partidos recientes que lo respalden
    jug, jug_txt = jugadores(path, ctx["pl_h"], ctx["pl_a"])
    if jug < 0 and not (rec and rec["frecuencia"] >= p_real):
        return None
    ev = p_real * odds - 1 if odds else None
    if odds and odds < 1 / p_real:
        return None                                   # la casa paga menos que la cuota justa
    sospechoso = ev is not None and ev > VALOR_SOSPECHOSO
    s = {"historial": round(1 - cel["p_exagera"], 2) if cel else 0.5,      # informativo (peso 0): qué tan segura es la celda
         "reciente": _clip((rec["frecuencia"] - p_real + 0.15) / 0.25),
         "jugadores": {1: 1.0, 0: 0.5, -1: 0.0}[jug],
         "cuota": (0.3 if sospechoso else _clip(ev / 0.10)) if ev is not None else 0.5,
         "probabilidad": _clip((p_real - 1 / MAX_CUOTA) / (0.77 - 1 / MAX_CUOTA))}
    puntaje = round(100 * sum(PESOS[k] * v for k, v in s.items()))
    razones = []
    if cel:
        ambito = NOMBRE_GRUPO.get(grp, grp)
        tipo = "con cuota de mercado" if fuente == "mercado" else "sin cuota de mercado"
        juicio = ("hasta ahora el modelo no ha exagerado en este tipo de pick" if cel["ratio_post"] >= 1 else
                  f"sin evidencia firme de que el modelo exagere (probabilidad {cel['p_exagera'] * 100:.0f}%)")
        if cel["fuente"] == "real":
            razones.append(f"Historial real en {ambito} ({tipo}): {cel['aciertos']} de {cel['n']} acertados cuando se declaraba "
                           f"{cel['declarada'] * 100:.0f}%; {juicio}")
        elif cel["n_bt"]:
            razones.append(f"Backtest en {ambito} ({tipo}): {cel['aciertos_bt']} de {cel['n_bt']} acertados "
                           f"({cel['aciertos_bt'] / cel['n_bt'] * 100:.0f}%); {juicio}")
    razones.append(f"Últimos partidos: se cumplió {rec['frecuencia'] * 100:.0f}% de las veces (local {rec['local']}, visita {rec['visita']})")
    if jug_txt:
        razones.append(("A favor: " if jug > 0 else "En contra: ") + jug_txt)
    if ev is not None:
        razones.append(f"Casa paga {odds:.2f}: " + ("valor sospechosamente alto, revisa noticias" if sospechoso else f"valor {ev * 100:+.0f}%"))
    no_fija = key in NO_FIJA.get(grp, set()) or (path[0] == "corners" and feedback.corners_bloqueados(fb, grp))
    fija = (puntaje >= FIJA_PUNTAJE and rec["frecuencia"] >= p_real + 0.08 and jug >= 0 and not sospechoso and not no_fija)
    hist = ({"n": cel["n"], "aciertos": cel["aciertos"], "real": round(cel["aciertos"] / cel["n"], 4), "prob_media": cel["declarada"],
             "fuente": "real", "grupo": grp} if cel and cel["n"] else
            {"n": cel["n_bt"], "aciertos": cel["aciertos_bt"], "real": round(cel["aciertos_bt"] / cel["n_bt"], 4) if cel["n_bt"] else None,
             "prob_media": cel["declarada"], "fuente": "backtest", "grupo": grp} if cel else None)
    return {"clave": key, "seleccion": LABEL[key], "prob": round(pr, 4), "prob_calibrada": round(pc, 4), "prob_real": round(p_real, 4),
            "cuota_justa": round(1 / p_real, 2), "cuota_minima": round(MARGEN / p_real, 2), "cuota_casa": odds,
            "ev": round(ev, 4) if ev is not None else None, "valor_sospechoso": sospechoso, "puntaje": puntaje,
            "senales": {k: round(v, 2) for k, v in s.items()}, "razones": razones, "fija": fija,
            "historial": hist, "veto": {"p_exagera": cel["p_exagera"], "ratio_post": cel["ratio_post"]} if cel else None,
            "fuente": fuente, "reciente": rec, "grupo": GRUPO.get(levels(path)[2].split("|")[0], path[0])}


def analizar(p: dict, ctx: dict) -> list:
    """Oportunidades de un partido (0-3), ordenadas por puntaje."""
    if (p.get("auditoria") or {}).get("estado") == "bloqueado":
        return []
    om = odds_for(p.get("cuotas"))
    cands = []
    for _, path, _ in PICK_LABELS:
        pr = get(p["mercados"], path)
        if pr is None:
            continue
        o = evaluar(path, pr, ctx, om.get("|".join(path)))
        if o and o["puntaje"] >= MIN_PUNTAJE:
            cands.append(o)
    cands.sort(key=lambda o: -o["puntaje"])
    out, grupos = [], set()
    for o in cands:
        if o["grupo"] in grupos:
            continue
        grupos.add(o["grupo"])
        out.append(o)
        if len(out) == MAX_OPORT:
            break
    return out


# ------------------------------------------------------------------ jugadores: solo donde la validación lo respalda
PLAYER_PICKS = [("marca", "marca", "marca un gol"), ("arco_1+", "arco_1+", "1 o más tiros al arco")]


def _val_bin(val: dict, stat: str, p: float):
    for b in (val or {}).get(stat, {}).get("calibracion", []):
        lo, hi = [int(x) / 100 for x in b["rango"].rstrip("%").split("-")]
        if lo <= p < (hi if hi < 1 else 1.01):
            return b
    return None


def oportunidades_jugador(players_h: list, players_a: list, local: str, visita: str, val: dict) -> list:
    out = []
    for team, players in ((local, players_h), (visita, players_a)):
        for j in players or []:
            if j.get("titular_prob", 0) < 0.75 or j.get("min_esperados", 0) < 60:
                continue
            for key, vkey, label in PLAYER_PICKS:
                pr = j["prob"][key]
                if not (1 / MAX_CUOTA <= pr <= 1 / MIN_CUOTA):
                    continue
                b = _val_bin(val, vkey, pr)
                if not b or b["n"] < MIN_N:
                    continue
                ratio_lcb = lcb(round(b["real"] * b["n"]), b["n"]) / b["prob_media"]
                if ratio_lcb < 0.92:
                    continue
                ult = j.get("ultimos", [])[:5]
                hits = sum((u["g"] > 0) if key == "marca" else (u["arco"] > 0) for u in ult)
                if len(ult) < 4 or hits / len(ult) < pr:
                    continue
                s = {"historial": _clip((ratio_lcb - 0.92) / 0.12), "reciente": _clip(hits / max(len(ult), 1) - pr + 0.5) if ult else 0.5,
                     "probabilidad": _clip((pr - 1 / MAX_CUOTA) / (0.77 - 1 / MAX_CUOTA))}
                puntaje = round(100 * (0.45 * s["historial"] + 0.35 * s["reciente"] + 0.20 * s["probabilidad"]))
                if puntaje < MIN_PUNTAJE:
                    continue
                p_real = _clip(pr * min(ratio_lcb * 1.05, b["real"] / b["prob_media"]), 0.02, 0.97)
                out.append({"jugador": j["nombre"], "equipo": team, "seleccion": f"{j['nombre']} {label}", "prob": round(pr, 4),
                            "prob_real": round(p_real, 4), "cuota_justa": round(1 / p_real, 2), "cuota_minima": round(MARGEN / p_real, 2),
                            "puntaje": puntaje, "razones": [
                                f"Validación de jugadores en esta liga: {b['real'] * 100:.0f}% real cuando se declaraba {b['prob_media'] * 100:.0f}% ({b['n']} casos)",
                                f"Últimos {len(ult)} partidos: lo cumplió {hits}", f"Titular {j['titular_prob'] * 100:.0f}% · {j['min_esperados']}' esperados"]})
    return sorted(out, key=lambda o: -o["puntaje"])[:2]


# ------------------------------------------------------------------ fijas del período
def fijas(partidos: list, estado: dict, now: datetime, lima_day) -> dict:
    """Las fijas son las oportunidades que pasaron todo. Máximo 1 por partido y 5 por día (siempre se publican)."""
    info = {"modo": estado.get("modo"), "liquidados_30d": estado.get("liquidados_30d", 0),
            "criterios": {"min_n": MIN_N, "min_cuota": MIN_CUOTA, "max_cuota": MAX_CUOTA, "fija_puntaje": FIJA_PUNTAJE,
                          "min_puntaje": MIN_PUNTAJE, "margen": MARGEN, "max_dia": FIJAS_DIA, "volumen_30d": VOLUMEN_30D,
                          "pesos": PESOS, "veto": {"k": feedback.VETO_K, "ratio": feedback.VETO_RATIO, "p": feedback.VETO_P},
                          "no_fija": {g: sorted(v) for g, v in NO_FIJA.items()}},
            "lista": []}
    limit = now + timedelta(days=DIAS_FIJAS)
    cands = []
    for p in partidos:
        t = datetime.fromisoformat(p["fecha"].replace("Z", "+00:00"))
        if t <= now or t > limit or (p.get("auditoria") or {}).get("estado") != "ok":
            continue
        for o in p.get("oportunidades") or []:
            if o["fija"]:
                cands.append({**o, "id": p["id"], "fecha": p["fecha"], "liga": p["liga"], "local": p["local"], "visita": p["visita"]})
                break                                  # máximo 1 por partido: la de mayor puntaje
    per_day = defaultdict(int)
    for c in sorted(cands, key=lambda c: -c["puntaje"]):
        d = lima_day(c["fecha"])
        if per_day[d] >= FIJAS_DIA:
            continue
        per_day[d] += 1
        info["lista"].append(c)
    info["lista"].sort(key=lambda c: c["fecha"])
    return info


def contexto(df: pd.DataFrame, home: str, away: str, pl_h, pl_a, cache: dict, grupo: str, fuente: str, fb: dict | None) -> dict:
    """fuente: "mercado" si el partido tiene cuotas 1X2 de la casa (el ensamble usa el mercado), "modelo" si no.
    fb: feedback.calcular() de esta corrida."""
    return {"curva": cache.get("curva"), "grupo": grupo, "fuente": fuente, "fb": fb,
            "rows_h": _persp(df, home, True, RECIENTES), "rows_a": _persp(df, away, False, RECIENTES),
            "pl_h": pl_h, "pl_a": pl_a}

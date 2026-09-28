"""Fijas: el filtro más estricto. No busca números altos declarados sino tipos de pick con acierto real comprobado.

Cuatro filtros en orden:
 1. Volumen: el historial real necesita >=100 picks liquidados en 30 días. Mientras no los haya, el sistema está
    "en calibración" y usa como evidencia el backtest (picks simulados fuera de muestra), avisándolo.
 2. Subtipo Beta-Binomial: el límite inferior de credibilidad al 95% del acierto de ese mercado/selección/línea debe
    ser >= 65% con al menos 30 casos. Si no hay 30, se amplía a "mismo mercado, todas las líneas" y luego a
    "categoría completa", nunca mezclando selecciones opuestas. La probabilidad del pick pasa antes por la curva de
    calibración (declarada -> real).
 3. Forma reciente: de los últimos 10 liquidados de ese nivel, al menos 6 acertados.
 4. Correlación: máximo 1 por grupo de mercados y partido (resultado, goles, córners, tarjetas), 2 por partido y 3 por día.
Pausa automática: si el acierto real de las fijas en 30 días cae bajo 70% (con al menos 20 liquidadas), no se publican.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from scipy.stats import beta

from .ensamble import calibrate_prob
from .picks import LABEL, PICK_LABELS, get, levels

MIN_DECLARADA = 0.70
MAX_DECLARADA = 0.92     # por encima la cuota justa es ~1.08 o menos: no aporta nada apostable
GRUPO = {"res": "resultado", "dc": "resultado", "dnb": "resultado", "ah": "resultado",
         "ou": "goles", "tl": "goles", "tv": "goles", "tl2": "goles", "ht": "goles", "btts": "goles",
         "co": "corners", "ca": "tarjetas"}
MIN_CALIBRADA = 0.72
MIN_LCB = 0.65
MIN_N = 30
FORMA = (6, 10)
MAX_PARTIDO, MAX_DIA = 2, 3
VOLUMEN_30D = 100
PAUSA = (0.70, 20)
DIAS = 3


def lcb(hits: int, n: int) -> float:
    return float(beta.ppf(0.05, 1 + hits, 1 + n - hits))


def _evidence(path, real: dict, sim: dict, modo: str):
    for i, k in enumerate(levels(path)):
        lvl = f"l{i + 1}"
        for fuente, stats in (("real", real), ("backtest", sim)) if modo == "real" else (("backtest", sim),):
            s = (stats.get(lvl) or {}).get(k)
            if s and s["n"] >= MIN_N:
                return lvl, k, s, fuente
    return None


def seleccionar(partidos: list, cache: dict, real: dict, estado_real: dict, now: datetime, lima_day) -> dict:
    """partidos: salida de build (con mercados y auditoría). real: estadísticas por subtipo del historial real.
    estado_real: {'liquidados_30d', 'fijas_30d_n', 'fijas_30d_acierto'}."""
    modo = "real" if estado_real.get("liquidados_30d", 0) >= VOLUMEN_30D else "calibracion"
    pausa = (estado_real.get("fijas_30d_n", 0) >= PAUSA[1] and (estado_real.get("fijas_30d_acierto") or 1) < PAUSA[0])
    info = {"modo": modo, "pausa": pausa, "criterios": {
        "min_calibrada": MIN_CALIBRADA, "max_declarada": MAX_DECLARADA, "min_lcb": MIN_LCB, "min_n": MIN_N, "forma": f"{FORMA[0]} de {FORMA[1]}",
        "max_partido": MAX_PARTIDO, "max_dia": MAX_DIA, "volumen_30d": VOLUMEN_30D, "pausa_bajo": PAUSA[0]},
        **estado_real, "lista": []}
    if pausa:
        return info
    curva, sim = cache.get("curva"), cache.get("subtipos") or {}
    limit = now + timedelta(days=DIAS)
    cands = []
    for p in partidos:
        t = datetime.fromisoformat(p["fecha"].replace("Z", "+00:00"))
        if t <= now or t > limit or p.get("auditoria", {}).get("estado") != "ok":
            continue
        for _, path, _ in PICK_LABELS:
            pr = get(p["mercados"], path)
            if pr is None or not (MIN_DECLARADA <= pr <= MAX_DECLARADA):
                continue
            pc = calibrate_prob(pr, curva)
            if pc < MIN_CALIBRADA:
                continue
            ev = _evidence(path, real, sim, modo)
            if not ev:
                continue
            lvl, k, s, fuente = ev
            lo = lcb(s["aciertos"], s["n"])
            if lo < MIN_LCB:
                continue
            u = s.get("ultimos10") or []
            if len(u) >= FORMA[1] and sum(u[-FORMA[1]:]) < FORMA[0]:
                continue
            cands.append({"id": p["id"], "fecha": p["fecha"], "liga": p["liga"], "local": p["local"], "visita": p["visita"],
                          "clave": "|".join(path), "seleccion": LABEL["|".join(path)], "prob": round(pr, 4),
                          "prob_calibrada": round(pc, 4), "lcb": round(lo, 4), "nivel": lvl, "evidencia": k,
                          "n": s["n"], "aciertos": s["aciertos"], "forma": sum(u[-10:]) if u else None,
                          "fuente": fuente, "_s": pc * lo, "_fam": GRUPO.get(levels(path)[2].split("|")[0], path[0])})
    cands.sort(key=lambda c: -c["_s"])
    per_match, per_fam, per_day = defaultdict(int), set(), defaultdict(int)
    for c in cands:
        day = lima_day(c["fecha"])
        if per_match[c["id"]] >= MAX_PARTIDO or (c["id"], c["_fam"]) in per_fam or per_day[day] >= MAX_DIA:
            continue
        per_match[c["id"]] += 1; per_fam.add((c["id"], c["_fam"])); per_day[day] += 1
        c.pop("_s"); c.pop("_fam")
        info["lista"].append(c)
    info["lista"].sort(key=lambda c: c["fecha"])
    return info

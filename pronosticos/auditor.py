"""Revisión automática de cada pronóstico antes de publicarlo (reglas fijas, sin intervención manual).

Estados:  ok        -> se publica normal
          revisar   -> se publica con avisos; no entra a fijas
          bloqueado -> hay una incoherencia: no entra a fijas ni se marca "con valor"
"""
from __future__ import annotations

import math


def revisar(mk: dict, comb: dict, pred: dict, lam: float, mu: float, n_home: int, n_away: int,
            odds: dict | None, arbitro: dict | None) -> dict:
    notas, bloquea, avisa = [], False, False
    x = mk["1x2"]
    s = x["1"] + x["X"] + x["2"]
    if abs(s - 1) > 0.01 or min(x.values()) < 0:
        notas.append("Las probabilidades 1X2 no suman 100%."); bloquea = True
    if not (0.1 <= lam <= 5) or not (0.1 <= mu <= 5) or any(map(math.isnan, (lam, mu))):
        notas.append("Goles esperados fuera de rango."); bloquea = True
    # ¿la matriz final reproduce lo que pidió el ensamble?
    gap = max(abs(x["1"] - comb["p"]["1"]), abs(x["2"] - comb["p"]["2"]))
    if gap > 0.03:
        notas.append("La matriz de marcadores no reproduce bien el ensamble."); avisa = True
    # cuotas coherentes
    if odds and odds.get("H") and odds.get("D") and odds.get("A"):
        inv = 1 / odds["H"] + 1 / odds["D"] + 1 / odds["A"]
        if min(odds["H"], odds["D"], odds["A"]) <= 1.01 or not (1.0 <= inv <= 1.2):
            notas.append("Las cuotas publicadas parecen erróneas (margen fuera de lo normal)."); bloquea = True
    # desacuerdo fuerte entre nuestros modelos y el mercado
    mods = pred["modelos"]
    if "mercado" in mods:
        own = comb["propio"]
        tv = sum(abs(own[k] - mods["mercado"][k]) for k in ("1", "X", "2")) / 2
        if tv > 0.15:
            notas.append(f"Nuestros modelos y las casas difieren {tv * 100:.0f} puntos: puede haber lesiones o rotaciones."); avisa = True
    # dispersión entre modelos
    ph = [m["1"] for k, m in mods.items() if k != "mercado"]
    if ph and max(ph) - min(ph) > 0.25:
        notas.append("Los modelos no se ponen de acuerdo sobre el favorito."); avisa = True
    if min(n_home, n_away) < 8:
        notas.append("Pocos partidos de historia de uno de los equipos."); avisa = True
    if not odds:
        notas.append("Sin cuotas publicadas todavía: el pronóstico usa solo nuestros modelos.")
    if "tarjetas" in mk and not (arbitro and arbitro.get("partidos")):
        notas.append("Árbitro sin confirmar o sin historial: las tarjetas usan solo a los equipos.")
    estado = "bloqueado" if bloquea else "revisar" if avisa else "ok"
    return {"estado": estado, "notas": notas}

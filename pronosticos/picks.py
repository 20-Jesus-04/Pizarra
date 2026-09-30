"""Tipos de pick, cómo se liquidan con el resultado real y sus niveles de agrupación (subtipo, mercado, categoría).

La misma liquidación se usa en el backtest (picks simulados) y en el historial real, para que las cifras sean comparables.
"""
from __future__ import annotations

import math

PICK_LABELS = [
    # (familia, ruta dentro de los mercados, etiqueta)
    ("dc", ("doble_oportunidad", "1X"), "Doble oportunidad 1X (local o empate)"),
    ("dc", ("doble_oportunidad", "X2"), "Doble oportunidad X2 (visita o empate)"),
    ("dc", ("doble_oportunidad", "12"), "Doble oportunidad 12 (no hay empate)"),
    ("res", ("1x2", "1"), "Gana el local"),
    ("res", ("1x2", "2"), "Gana la visita"),
    ("res", ("1x2", "X"), "Empate"),
    ("dnb", ("empate_no_apuesta", "1"), "Empate no apuesta: local"),
    ("dnb", ("empate_no_apuesta", "2"), "Empate no apuesta: visita"),
    ("ou", ("goles_totales", "1.5", "over"), "Más de 1.5 goles"),
    ("ou", ("goles_totales", "2.5", "over"), "Más de 2.5 goles"),
    ("ou", ("goles_totales", "2.5", "under"), "Menos de 2.5 goles"),
    ("ou", ("goles_totales", "3.5", "under"), "Menos de 3.5 goles"),
    ("ou", ("goles_totales", "4.5", "under"), "Menos de 4.5 goles"),
    ("ou", ("goles_totales", "3.5", "over"), "Más de 3.5 goles"),
    ("ou", ("goles_totales", "1.5", "under"), "Menos de 1.5 goles"),
    ("btts", ("ambos_marcan", "si"), "Ambos marcan: Sí"),
    ("btts", ("ambos_marcan", "no"), "Ambos marcan: No"),
    ("tl", ("goles_local", "0.5", "over"), "Local marca al menos 1 gol"),
    ("tl", ("goles_local", "1.5", "over"), "Local marca 2 o más"),
    ("tv", ("goles_visita", "0.5", "over"), "Visita marca al menos 1 gol"),
    ("tv", ("goles_visita", "1.5", "under"), "Visita marca 1 o menos"),
    ("tl2", ("goles_local", "1.5", "under"), "Local marca 1 o menos"),
    ("tv", ("goles_visita", "1.5", "over"), "Visita marca 2 o más"),
    ("tv", ("goles_visita", "0.5", "under"), "Visita no marca"),
    ("tl2", ("goles_local", "0.5", "under"), "Local no marca"),
    ("ht", ("primer_tiempo_goles", "0.5", "over"), "Hay gol en el 1er tiempo"),
    ("ht", ("primer_tiempo_goles", "1.5", "under"), "Menos de 1.5 goles en el 1er tiempo"),
    ("ht", ("primer_tiempo_goles", "1.5", "over"), "Más de 1.5 goles en el 1er tiempo"),
    ("ah", ("handicap_asiatico_local", "-1", "gana"), "Hándicap asiático local -1"),
    ("ah", ("handicap_asiatico_local", "+1", "pierde"), "Hándicap asiático visita -1"),
    ("ah", ("handicap_asiatico_local", "-1.5", "gana"), "Local gana por 2 o más"),
    ("ah", ("handicap_asiatico_local", "+1.5", "pierde"), "Visita gana por 2 o más"),
    ("co", ("corners", "total", "8.5", "over"), "Más de 8.5 córners"),
    ("co", ("corners", "total", "9.5", "over"), "Más de 9.5 córners"),
    ("co", ("corners", "total", "11.5", "under"), "Menos de 11.5 córners"),
    ("co", ("corners", "total", "10.5", "over"), "Más de 10.5 córners"),
    ("co", ("corners", "total", "9.5", "under"), "Menos de 9.5 córners"),
    ("ca", ("tarjetas", "total", "2.5", "over"), "Más de 2.5 tarjetas"),
    ("ca", ("tarjetas", "total", "3.5", "over"), "Más de 3.5 tarjetas"),
    ("ca", ("tarjetas", "total", "5.5", "under"), "Menos de 5.5 tarjetas"),
    ("ca", ("tarjetas", "total", "4.5", "over"), "Más de 4.5 tarjetas"),
    ("ca", ("tarjetas", "total", "3.5", "under"), "Menos de 3.5 tarjetas"),
]
LABEL = {"|".join(p): l for _, p, l in PICK_LABELS}
FAMILY = {"|".join(p): f for f, p, _ in PICK_LABELS}


# Rangos de probabilidad en los que se mide el historial de cada tipo de pick (cortes estadísticos, no niveles).
BANDS = [("p40", 0.385, 0.50), ("p50", 0.50, 0.60), ("p60", 0.60, 0.70), ("p70", 0.70, 0.80), ("p80", 0.80, 0.93)]


def band_of(p: float) -> str | None:
    for name, lo, hi in BANDS:
        if lo <= p < hi:
            return name
    return None


def get(d, path):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def key(path) -> str:
    return "|".join(path)


def levels(path) -> tuple[str, str, str]:
    """(subtipo, mercado con todas sus líneas, categoría) sin mezclar selecciones opuestas."""
    k = key(path)
    side = path[-1]
    return k, f"{path[0]}|{side}", f"{FAMILY.get(k, path[0])}|{side}"


def settle(path, r: dict):
    """True/False si el pick se ganó/perdió; None si se anula (empate en DNB, hándicap devuelto) o falta el dato.
    r: hg, ag y opcionalmente hthg, htag, corners (total), cards (total de amarillas)."""
    r = {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in r.items()}
    hg, ag = r.get("hg"), r.get("ag")
    if hg is None or ag is None:
        return None
    hg, ag = int(hg), int(ag)
    m, sel = path[0], path[-1]
    over = lambda v, ln: (v > float(ln)) if sel == "over" else (v < float(ln))
    if m == "1x2":
        return {"1": hg > ag, "X": hg == ag, "2": hg < ag}[sel]
    if m == "doble_oportunidad":
        return {"1X": hg >= ag, "X2": hg <= ag, "12": hg != ag}[sel]
    if m == "empate_no_apuesta":
        return None if hg == ag else (hg > ag) == (sel == "1")
    if m == "goles_totales":
        return over(hg + ag, path[1])
    if m == "goles_local":
        return over(hg, path[1])
    if m == "goles_visita":
        return over(ag, path[1])
    if m == "ambos_marcan":
        return (hg > 0 and ag > 0) == (sel == "si")
    if m == "primer_tiempo_goles":
        h1, a1 = r.get("hthg"), r.get("htag")
        return None if h1 is None or a1 is None else over(int(h1) + int(a1), path[1])
    if m == "handicap_asiatico_local":
        diff = hg - ag + float(path[1])          # desde el punto de vista del local
        if diff == 0:
            return None
        return diff > 0 if sel == "gana" else diff < 0
    if m in ("corners", "tarjetas"):
        v = r.get("corners" if m == "corners" else "cards")
        return None if v is None else over(float(v), path[2])
    return None


def odds_for(o: dict | None) -> dict:
    """Cuota publicada (decimal) de cada pick que la casa ofrece, con la misma clave que PICK_LABELS."""
    if not o:
        return {}
    out = {"1x2|1": o.get("H"), "1x2|X": o.get("D"), "1x2|2": o.get("A")}
    ln = o.get("ou_line")
    if ln is not None:
        out[f"goles_totales|{float(ln)}|over"] = o.get("over")
        out[f"goles_totales|{float(ln)}|under"] = o.get("under")
    ah = o.get("ah_line")
    if ah is not None:
        out[f"handicap_asiatico_local|{float(ah):+g}|gana"] = o.get("ah_home")
        out[f"handicap_asiatico_local|{float(ah):+g}|pierde"] = o.get("ah_away")
    return {k: v for k, v in out.items() if v}

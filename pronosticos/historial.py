"""Historial de predicciones: se registra ANTES de cada partido y se liquida cuando hay resultado.

- Solo se agregan registros: una predicción nunca se borra ni se oculta, falle o acierte.
- Mientras el partido no empieza, el registro se actualiza con la última versión (la que se publicó antes del inicio);
  desde el pitazo inicial queda congelado y solo se le agrega el resultado.
- El archivo vive en data/historial.json y cada cambio queda en el historial de commits de GitHub.
"""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np

from .fetch import DATA_DIR
from .picks import BANDS, LABEL, PICK_LABELS, band_of, get, grupo, levels, settle


PATH = os.path.join(DATA_DIR, "historial.json")
GUARDAR_DESDE = 0.385       # se guardan todos los picks candidatos con prob >= 38.5% (para calibración real)


def load() -> dict:
    try:
        with open(PATH, encoding="utf-8") as f:
            h = json.load(f)
        if isinstance(h, dict) and "partidos" in h:
            return h
    except (OSError, ValueError):
        pass
    return {"version": 1, "creado": datetime.now(timezone.utc).isoformat(), "partidos": {}}


def limpio(x):
    """Copia apta para JSON estricto: NaN/infinito -> None, tipos de numpy -> nativos (json no llama a `default`
    para los float de numpy porque heredan de float, así que hay que limpiarlos antes)."""
    if isinstance(x, dict):
        return {k: limpio(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [limpio(v) for v in x]
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return float(x) if math.isfinite(x) else None
    return x


def save(h: dict) -> None:
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(limpio(h), f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def registrar(h: dict, partidos: list, fijas: list, now: datetime) -> int:
    """Agrega o actualiza (solo si aún no empezó) cada partido publicado."""
    fset = defaultdict(list)
    for f in fijas:
        fset[f["id"]].append(f["clave"])
    n = 0
    for p in partidos:
        if _t(p["fecha"]) <= now:
            continue
        old = h["partidos"].get(p["id"])
        if old and _t(old["fecha"]) <= now:
            continue          # congelado
        mk = p["mercados"]
        picks = []
        for _, path, _ in PICK_LABELS:
            pr = get(mk, path)
            if pr is not None and pr >= GUARDAR_DESDE:
                picks.append(["|".join(path), round(pr, 4)])
        alt = p.get("alternativas") or []
        rec = {
            "id": p["id"], "liga": p["liga"], "comp": p.get("competicion"), "fecha": p["fecha"],
            "local": p["local"], "visita": p["visita"],
            "primer_registro": old["primer_registro"] if old else now.isoformat(), "registro": now.isoformat(),
            "p": {"1": mk["1x2"]["1"], "X": mk["1x2"]["X"], "2": mk["1x2"]["2"],
                  "o25": mk["goles_totales"]["2.5"]["over"], "btts": mk["ambos_marcan"]["si"]},
            "mercado": {k: p["mercado"][k] for k in ("1", "X", "2")} if p.get("mercado") else None,
            "propio": p.get("modelo_puro", {}).get("1x2"),
            "xg": [mk["xg_home"], mk["xg_away"]],
            # valores esperados SIN el ajuste por resultados reales: son la base con la que se recalcula ese ajuste
            "corners_esp": (mk.get("corners") or {}).get("esperados_base", (mk.get("corners") or {}).get("esperados_total")),
            "tarjetas_esp": (mk.get("tarjetas") or {}).get("esperadas_base", (mk.get("tarjetas") or {}).get("esperadas_total")),
            "neutral": bool(p.get("neutral")),
            "arbitro": (p.get("arbitro") or {}).get("nombre"),
            "principal": alt[0]["clave"] if alt and alt[0].get("clave") else None,
            "fijas": fset.get(p["id"], []),
            "destacada": (p.get("destacada") or {}).get("clave"),
            "oportunidades": [o["clave"] for o in p.get("oportunidades") or []],
            "auditoria": (p.get("auditoria") or {}).get("estado"),
            "picks": picks, "resultado": old.get("resultado") if old else None,
        }
        h["partidos"][p["id"]] = rec
        n += 1
    return n


MANUAL_ESPERA = timedelta(hours=24)      # un resultado manual solo se acepta 24 h después del inicio del partido


def liquidar(h: dict, resultados: dict, now: datetime) -> int:
    """resultados: {id: {hg, ag, hthg?, htag?, corners?, cards?, final?, fuente?, _anular?}}. Liquida partidos terminados.
    Solo toca el resultado, nunca el pronóstico. Si un dato ya guardado resulta faltante (0 córners de una ficha sin
    estadísticas, córners/tarjetas con prórroga) se anula dejando constancia en "anulados"; si el partido fue a prórroga
    o penales y se había guardado otro marcador, se corrige al de los 90 minutos dejando el anterior en "corregido"."""
    n = 0
    for pid, rec in h["partidos"].items():
        r = resultados.get(pid)
        if not r or r.get("hg") is None or _t(rec["fecha"]) > now:
            continue
        if r.get("manual") and now - _t(rec["fecha"]) < MANUAL_ESPERA:
            print(f"::warning::resultado manual {pid} descartado: el partido empezó hace menos de 24 horas")
            continue
        new = dict(rec.get("resultado") or {})
        changed = False
        nulos = set(r.get("_anular") or [])
        for k in nulos:
            # se anula solo un 0 guardado (dato faltante) o cualquier valor si hubo prórroga o penales
            if new.get(k) is not None and (new[k] == 0 or r.get("final")):
                new.setdefault("anulados", {})[k] = new[k]
                new[k] = None
                changed = True
        distinto = new.get("hg") is not None and (new["hg"], new["ag"]) != (r["hg"], r["ag"])
        if distinto and (r.get("final") or (new.get("manual") and not r.get("manual"))):
            # prórroga/penales liquidados con otro marcador, o resultado manual que ESPN contradice: gana ESPN
            new.setdefault("corregido", {"hg": new["hg"], "ag": new["ag"],
                                         **({"fuente": new["fuente"]} if new.get("manual") else {})})
            new["hg"], new["ag"] = r["hg"], r["ag"]
            if new.pop("manual", None):
                new.pop("fuente", None)
            changed = True
        for k, v in r.items():          # los córners/tarjetas de la ficha pueden llegar un día después
            if k.startswith("_") or k in nulos:
                continue
            if v is not None and new.get(k) is None:
                new[k] = v
                changed = True
        if changed:
            new.setdefault("liquidado", now.isoformat())
            rec["resultado"] = new
            n += 1
    return n


def _outcomes(rec):
    r = rec.get("resultado")
    if not r:
        return []
    out = []
    for k, pr in rec["picks"]:
        ok = settle(tuple(k.split("|")), r)
        if ok is not None:
            out.append((k, pr, ok))
    return out


def subtipos_reales(h: dict, solo_grupo: str | None = None) -> dict:
    """Mismas estadísticas por nivel y subtipo que el backtest, pero con resultados reales (opcional: de un solo grupo)."""
    rows = []
    for rec in h["partidos"].values():
        if solo_grupo and grupo(rec["liga"]) != solo_grupo:
            continue
        for k, pr, ok in _outcomes(rec):
            b = band_of(pr)
            if b:
                rows.append((rec["fecha"], b, tuple(k.split("|")), pr, ok))
    rows.sort()
    out = {b: {"l1": {}, "l2": {}, "l3": {}} for b, _, _ in BANDS}
    for _, b, path, pr, ok in rows:
        for lvl, kk in zip(("l1", "l2", "l3"), levels(path)):
            s = out[b][lvl].setdefault(kk, {"n": 0, "aciertos": 0, "ultimos10": [], "_sp": 0.0})
            s["n"] += 1; s["aciertos"] += int(ok); s["_sp"] += pr
            s["ultimos10"] = (s["ultimos10"] + [int(ok)])[-10:]
            s["prob_media"] = round(s["_sp"] / s["n"], 3)
    return out


def metricas(h: dict, now: datetime, lima_day) -> dict:
    """Resumen para la web: Brier y calibración con partidos ya liquidados, acierto por banda, fijas y últimos picks."""
    recs = sorted((r for r in h["partidos"].values() if r.get("resultado")), key=lambda r: r["fecha"])
    pend = sum(1 for r in h["partidos"].values() if not r.get("resultado") and _t(r["fecha"]) > now - timedelta(days=3))
    out = {"registrados": len(h["partidos"]), "liquidados": len(recs), "pendientes": pend, "desde": h.get("creado")}
    if not recs:
        return out
    ys, P, Pm, ym = [], [], [], []
    for r in recs:
        res = r["resultado"]
        y = 0 if res["hg"] > res["ag"] else 1 if res["hg"] == res["ag"] else 2
        ys.append(y); P.append([r["p"]["1"], r["p"]["X"], r["p"]["2"]])
        if r.get("mercado"):
            Pm.append([r["mercado"]["1"], r["mercado"]["X"], r["mercado"]["2"]]); ym.append(y)
    P, ys = np.array(P), np.array(ys)
    E = np.eye(3)
    out["brier"] = round(float(((P - E[ys]) ** 2).sum(1).mean()), 4)
    out["logloss"] = round(float(-np.log(np.clip(P[np.arange(len(ys)), ys], 1e-9, 1)).mean()), 4)
    out["acierto_favorito"] = round(float((P.argmax(1) == ys).mean()), 4)
    if len(ym) >= 10:
        Pm, ym = np.array(Pm), np.array(ym)
        out["brier_mercado"] = round(float(((Pm - E[ym]) ** 2).sum(1).mean()), 4)
        out["n_con_mercado"] = int(len(ym))
    # calibración de todos los picks candidatos
    allp = [(pr, ok) for r in recs for _, pr, ok in _outcomes(r)]
    bands = [(0.385, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    out["calibracion"] = []
    for a, b in bands:
        sel = [ok for pr, ok in allp if a <= pr < b]
        if sel:
            dec = [pr for pr, ok in allp if a <= pr < b]
            out["calibracion"].append({"rango": f"{a * 100:.0f}-{min(b, 1) * 100:.0f}%", "declarada": round(float(np.mean(dec)), 3),
                                       "real": round(float(np.mean(sel)), 3), "n": len(sel)})
    # picks publicados: el principal de cada partido y las fijas
    pub, fij, dest = [], [], []
    cut30 = now - timedelta(days=30)
    for r in recs:
        oc = {k: (pr, ok) for k, pr, ok in _outcomes(r)}
        base = {"id": r["id"], "fecha": r["fecha"], "liga": r["liga"], "local": r["local"], "visita": r["visita"],
                "marcador": f"{r['resultado']['hg']}-{r['resultado']['ag']}",
                **({"manual": True} if r["resultado"].get("manual") else {}),
                **({"anulado": sorted(r["resultado"]["anulados"])} if r["resultado"].get("anulados") else {})}
        if r.get("principal") in oc:
            pr, ok = oc[r["principal"]]
            pub.append({**base, "seleccion": LABEL.get(r["principal"], r["principal"]), "prob": pr, "acierto": ok, "tipo": "principal"})
        for k in r.get("fijas") or []:
            if k in oc:
                pr, ok = oc[k]
                fij.append({**base, "seleccion": LABEL.get(k, k), "prob": pr, "acierto": ok, "tipo": "fija"})
        if r.get("destacada") in oc:
            pr, ok = oc[r["destacada"]]
            dest.append({**base, "seleccion": LABEL.get(r["destacada"], r["destacada"]), "prob": pr, "acierto": ok, "tipo": "destacada"})
        for k in r.get("oportunidades") or []:
            if k in oc and k != r.get("destacada"):
                pr, ok = oc[k]
                dest.append({**base, "seleccion": LABEL.get(k, k), "prob": pr, "acierto": ok, "tipo": "oportunidad"})
    stat = lambda L: {"n": len(L), "aciertos": sum(x["acierto"] for x in L),
                      "acierto": round(sum(x["acierto"] for x in L) / len(L), 4) if L else None}
    out["principal"] = stat(pub)
    out["principal_30d"] = stat([x for x in pub if _t(x["fecha"]) >= cut30])
    out["fijas"] = stat(fij)
    out["fijas_30d"] = stat([x for x in fij if _t(x["fecha"]) >= cut30])
    esperado = lambda L: round(float(np.mean([x["prob"] for x in L])), 3) if L else None
    out["fijas"]["esperado"] = esperado(fij)
    out["fijas_30d"]["esperado"] = esperado([x for x in fij if _t(x["fecha"]) >= cut30])
    out["oportunidades"] = {**stat(dest), "esperado": esperado(dest)}
    out["liquidados_30d"] = sum(1 for r in recs if _t(r["fecha"]) >= cut30 for _ in _outcomes(r))
    out["ultimos"] = sorted(pub + fij + dest, key=lambda x: x["fecha"], reverse=True)[:300]

    # evolución diaria del acierto del pick principal
    by_day = defaultdict(lambda: [0, 0])
    for x in pub:
        d = lima_day(x["fecha"]); by_day[d][0] += 1; by_day[d][1] += int(x["acierto"])
    out["por_dia"] = [{"dia": d, "n": v[0], "aciertos": v[1]} for d, v in sorted(by_day.items())][-60:]
    return out

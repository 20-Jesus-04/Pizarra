"""Carga los archivos de caché y los convierte en tablas limpias por liga."""
from __future__ import annotations

import io
import json
import os
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from .config import LEAGUES, INT_SINCE, FRIENDLY_WEIGHT
from .fetch import DATA_DIR

COLS = {
    "HomeTeam": "home", "AwayTeam": "away", "FTHG": "hg", "FTAG": "ag", "HTHG": "hthg", "HTAG": "htag",
    "HxG": "hxg", "AxG": "axg", "HS": "hs", "AS": "as", "HST": "hst", "AST": "ast", "HC": "hc", "AC": "ac",
    "HY": "hy", "AY": "ay", "HR": "hr", "AR": "ar", "HF": "hf", "AF": "af", "Referee": "referee",
}
# Cuotas: preferimos cierre promedio del mercado (AvgC*), si no existe promedio de apertura (Avg*).
ODDS = {
    "oH": ["AvgCH", "AvgH", "PSCH", "B365CH", "B365H"], "oD": ["AvgCD", "AvgD", "PSCD", "B365CD", "B365D"],
    "oA": ["AvgCA", "AvgA", "PSCA", "B365CA", "B365A"],
    "oO25": ["AvgC>2.5", "Avg>2.5", "B365C>2.5", "B365>2.5"], "oU25": ["AvgC<2.5", "Avg<2.5", "B365C<2.5", "B365<2.5"],
    "mH": ["MaxCH", "MaxH"], "mD": ["MaxCD", "MaxD"], "mA": ["MaxCA", "MaxA"],
    "mO25": ["MaxC>2.5", "Max>2.5"], "mU25": ["MaxC<2.5", "Max<2.5"],
    "ahLine": ["AHCh", "AHh"], "oAHH": ["AvgCAHH", "AvgAHH"], "oAHA": ["AvgCAHA", "AvgAHA"],
}


def _load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def _first(df, cands):
    out = pd.Series(np.nan, index=df.index)
    for c in cands:
        if c in df:
            out = out.fillna(pd.to_numeric(df[c], errors="coerce"))
    return out


def load_europe(raw) -> dict[str, pd.DataFrame]:
    per = defaultdict(list)
    for key, txt in raw["fd"].items():
        if key == "fixtures":
            continue
        season, div = key.split("/")
        df = pd.read_csv(io.StringIO(txt), on_bad_lines="skip")
        df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"])
        out = pd.DataFrame({v: df[k] if k in df else np.nan for k, v in COLS.items()})
        for k, c in ODDS.items():
            out[k] = _first(df, c)
        out["date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
        out["season"] = season
        out["div"] = div
        per[div].append(out)
    res = {}
    for div, parts in per.items():
        d = pd.concat(parts, ignore_index=True).dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        for c in ["hg", "ag", "hthg", "htag", "hs", "as", "hst", "ast", "hc", "ac", "hy", "ay", "hr", "ar", "hxg", "axg"]:
            d[c] = pd.to_numeric(d[c], errors="coerce")
        d["home"] = d["home"].str.strip()
        d["away"] = d["away"].str.strip()
        res[div] = d
    return res


def load_peru(raw) -> pd.DataFrame:
    rows, seen = [], set()
    for year, evs in raw["espn"].items():
        for e in evs:
            if e["status"] not in ("STATUS_FULL_TIME", "STATUS_FINAL_PEN", "STATUS_FINAL_AET") or e["id"] in seen:
                continue
            seen.add(e["id"])
            h = next(t for t in e["t"] if t["ha"] == "home")
            a = next(t for t in e["t"] if t["ha"] == "away")
            f = lambda t, k: pd.to_numeric(t["st"].get(k), errors="coerce")
            rows.append({
                "date": pd.to_datetime(e["date"]).tz_localize(None).normalize(), "home": h["name"], "away": a["name"],
                "hg": int(h["score"]), "ag": int(a["score"]), "hs": f(h, "totalShots"), "as": f(a, "totalShots"),
                "hst": f(h, "shotsOnTarget"), "ast": f(a, "shotsOnTarget"), "hc": f(h, "wonCorners"), "ac": f(a, "wonCorners"),
                "hposs": f(h, "possessionPct"), "aposs": f(a, "possessionPct"),
                "season": f"{year}-{e.get('season') or ''}", "div": "PER",
            })
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    for c in ["hthg", "htag", "hxg", "axg", "hy", "ay", "hr", "ar", "hf", "af", "referee"] + list(ODDS):
        d[c] = np.nan
    return d


# ---------------------------------------------------------------- mapeo de nombres ESPN -> football-data
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    for w in [" fc", "fc ", " cf", "ac ", "as ", " afc", "sc ", "ssc ", "1. ", "vfb ", "vfl ", "tsg ", "rc ", "ogc ", "stade "]:
        s = s.replace(w, " ")
    return " ".join(s.replace("-", " ").replace(".", " ").split())


def build_name_map(fd: pd.DataFrame, espn_results: list) -> dict[str, str]:
    """Empareja nombres ESPN con football-data usando partidos idénticos (fecha ±1 día y marcador)."""
    votes = defaultdict(Counter)
    idx = defaultdict(list)
    for r in fd[["date", "home", "away", "hg", "ag"]].itertuples(index=False):
        idx[(int(r.hg), int(r.ag))].append(r)
    for date, h, a, hs, as_, *_ in espn_results:
        try:
            dt = pd.to_datetime(date).tz_localize(None).normalize()
            key = (int(hs), int(as_))
        except (ValueError, TypeError):
            continue
        for r in idx.get(key, []):
            if abs((r.date - dt).days) <= 1:
                votes[h][r.home] += 1
                votes[a][r.away] += 1
    mapping = {}
    for espn_name, c in votes.items():
        best, n = c.most_common(1)[0]
        # exigir consistencia: el ganador debe dominar las coincidencias
        if n >= 3 and n >= 0.5 * sum(c.values()):
            mapping[espn_name] = best
    # respaldo por similitud de texto
    teams = sorted(set(fd.home) | set(fd.away))
    for date, h, a, *_ in espn_results:
        for nm in (h, a):
            if nm not in mapping:
                mapping[nm] = max(teams, key=lambda t: SequenceMatcher(None, _norm(nm), _norm(t)).ratio())
    return mapping


def fuzzy_team(name: str, teams: list[str]) -> str:
    return max(teams, key=lambda t: SequenceMatcher(None, _norm(name), _norm(t)).ratio())


def american_to_decimal(x):
    if x in (None, "", "EVEN", "EV"):
        return 2.0 if x in ("EVEN", "EV") else None
    try:
        v = float(str(x).replace("+", ""))
    except ValueError:
        return None
    if v == 0:
        return None
    return round(1 + v / 100, 3) if v > 0 else round(1 + 100 / abs(v), 3)


def add_xg_proxy(d: pd.DataFrame) -> pd.DataFrame:
    """xG aproximado a partir de tiros y tiros al arco (regresión por liga) para temporadas sin xG.
    Se guarda en columnas aparte (hxg_m/axg_m) que usa solo el modelo; las estadísticas muestran xG real."""
    d = d.copy()
    m = d[["hs", "hst", "as", "ast"]].notna().all(axis=1)
    d["hxg_m"], d["axg_m"] = d["hxg"], d["axg"]
    if m.sum() < 100:
        return d
    X = np.r_[d.loc[m, ["hst", "hs"]].values, d.loc[m, ["ast", "as"]].values].astype(float)
    X[:, 1] -= X[:, 0]
    y = np.r_[d.loc[m, "hg"].values, d.loc[m, "ag"].values].astype(float)
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    d["hxg_m"] = d["hxg_m"].fillna(d.hst * b[0] + (d.hs - d.hst) * b[1])
    d["axg_m"] = d["axg_m"].fillna(d.ast * b[0] + (d["as"] - d.ast) * b[1])
    return d


# ---------------------------------------------------------------- selecciones
ESPN_TO_INT = {
    "Bosnia-Herzegovina": "Bosnia and Herzegovina", "Brunei Darussalam": "Brunei", "Chinese Taipei": "Taiwan",
    "Congo DR": "DR Congo", "Czechia": "Czech Republic", "Kyrgyz Republic": "Kyrgyzstan",
    "Sao Tome and Principe": "São Tomé and Príncipe", "St. Kitts and Nevis": "Saint Kitts and Nevis",
    "St. Lucia": "Saint Lucia", "St. Martin": "Saint Martin", "St. Vincent and the Grenadines": "Saint Vincent and the Grenadines",
    "Türkiye": "Turkey", "US Virgin Islands": "United States Virgin Islands", "USA": "United States",
    "Korea Republic": "South Korea", "Côte d'Ivoire": "Ivory Coast", "Cape Verde Islands": "Cape Verde",
}
ES_NAMES = {  # nombres en español para la web
    "Peru": "Perú", "Spain": "España", "Germany": "Alemania", "France": "Francia", "England": "Inglaterra", "Italy": "Italia",
    "Netherlands": "Países Bajos", "Belgium": "Bélgica", "Brazil": "Brasil", "Mexico": "México", "United States": "Estados Unidos",
    "Switzerland": "Suiza", "Sweden": "Suecia", "Norway": "Noruega", "Denmark": "Dinamarca", "Poland": "Polonia", "Turkey": "Turquía",
    "Croatia": "Croacia", "Scotland": "Escocia", "Wales": "Gales", "Republic of Ireland": "Irlanda", "Northern Ireland": "Irlanda del Norte",
    "Czech Republic": "Chequia", "Hungary": "Hungría", "Austria": "Austria", "Greece": "Grecia", "Romania": "Rumania", "Serbia": "Serbia",
    "Ukraine": "Ucrania", "Slovakia": "Eslovaquia", "Slovenia": "Eslovenia", "Finland": "Finlandia", "Iceland": "Islandia",
    "Bosnia and Herzegovina": "Bosnia", "North Macedonia": "Macedonia del Norte", "Albania": "Albania", "Georgia": "Georgia",
    "Lithuania": "Lituania", "Latvia": "Letonia", "Estonia": "Estonia", "Azerbaijan": "Azerbaiyán", "Kazakhstan": "Kazajistán",
    "Belarus": "Bielorrusia", "Moldova": "Moldavia", "Montenegro": "Montenegro", "Cyprus": "Chipre", "Luxembourg": "Luxemburgo",
    "Armenia": "Armenia", "Bulgaria": "Bulgaria", "Israel": "Israel", "Faroe Islands": "Islas Feroe", "Malta": "Malta",
    "Kosovo": "Kosovo", "Andorra": "Andorra", "San Marino": "San Marino", "Liechtenstein": "Liechtenstein", "Gibraltar": "Gibraltar",
    "Colombia": "Colombia", "Argentina": "Argentina", "Uruguay": "Uruguay", "Chile": "Chile", "Ecuador": "Ecuador", "Paraguay": "Paraguay",
    "Bolivia": "Bolivia", "Venezuela": "Venezuela", "Canada": "Canadá", "Japan": "Japón", "South Korea": "Corea del Sur",
    "Morocco": "Marruecos", "Egypt": "Egipto", "Ivory Coast": "Costa de Marfil", "South Africa": "Sudáfrica", "Cameroon": "Camerún",
    "Algeria": "Argelia", "Tunisia": "Túnez", "Saudi Arabia": "Arabia Saudita", "Australia": "Australia", "New Zealand": "Nueva Zelanda",
    "Portugal": "Portugal", "Costa Rica": "Costa Rica", "Panama": "Panamá", "Jamaica": "Jamaica", "Honduras": "Honduras",
    "El Salvador": "El Salvador", "Guatemala": "Guatemala", "Haiti": "Haití", "DR Congo": "RD Congo", "Guinea": "Guinea",
}


def load_international(results_csv: str, espn: dict) -> pd.DataFrame:
    r = pd.read_csv(results_csv)
    r["date"] = pd.to_datetime(r["date"], errors="coerce")
    r = r[(r.date >= INT_SINCE) & r.home_score.notna()]
    d = pd.DataFrame({
        "date": r.date, "home": r.home_team, "away": r.away_team, "hg": r.home_score.astype(int), "ag": r.away_score.astype(int),
        "neutral": r.neutral.astype(str).str.upper().eq("TRUE"), "tournament": r.tournament,
    })
    # partidos recientes que el dataset aún no tiene: se completan con ESPN
    last = d.date.max()
    extra = []
    for e in espn.get("done", []):
        dt = pd.to_datetime(e["date"]).tz_localize(None).normalize()
        if dt <= last:
            continue
        try:
            hg, ag = int(e["hs"]), int(e["as"])
        except (TypeError, ValueError):
            continue
        extra.append({"date": dt, "home": ESPN_TO_INT.get(e["home"], e["home"]), "away": ESPN_TO_INT.get(e["away"], e["away"]),
                      "hg": hg, "ag": ag, "neutral": bool(e.get("neutral")), "tournament": e.get("comp") or ""})
    if extra:
        d = pd.concat([d, pd.DataFrame(extra)], ignore_index=True)
    d = d.drop_duplicates(subset=["date", "home", "away"]).sort_values("date").reset_index(drop=True)
    d["mw"] = np.where(d.tournament.str.contains("Friendly|Amistoso", case=False, na=False), FRIENDLY_WEIGHT, 1.0)
    d["season"] = d.date.dt.year.astype(str)
    d["div"] = "INT"
    for c in ["hthg", "htag", "hxg", "axg", "hs", "as", "hst", "ast", "hc", "ac", "hy", "ay", "hr", "ar", "hf", "af", "referee"] + list(ODDS):
        d[c] = np.nan
    return d


def int_upcoming(espn: dict, teams: set) -> list[dict]:
    out, seen = [], set()
    for e in espn.get("up", []):
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        hn, an = ESPN_TO_INT.get(e["home"], e["home"]), ESPN_TO_INT.get(e["away"], e["away"])
        if hn not in teams:
            hn = fuzzy_team(hn, sorted(teams))
        if an not in teams:
            an = fuzzy_team(an, sorted(teams))
        out.append({"id": e["id"], "date": e["date"], "venue": e.get("venue"), "neutral": bool(e.get("neutral")),
                    "competicion": e.get("comp"), "t": [
                        {"ha": "home", "name": e["home"], "key": hn, "form": e.get("hform")},
                        {"ha": "away", "name": e["away"], "key": an, "form": e.get("aform")}], "odds": e.get("odds")})
    return out


def _odds_dec(o):
    if not o or not o.get("h"):
        return None
    return {
        "H": american_to_decimal(o.get("h")), "D": american_to_decimal(o.get("d")), "A": american_to_decimal(o.get("a")),
        "H_open": american_to_decimal(o.get("hO")), "D_open": american_to_decimal(o.get("dO")),
        "A_open": american_to_decimal(o.get("aO")),
        "ou_line": o.get("ou"), "over": american_to_decimal(o.get("ov")), "under": american_to_decimal(o.get("un")),
        "ah_line": float(o["sh"]) if o.get("sh") not in (None, "") else None,
        "ah_home": american_to_decimal(o.get("shO")), "ah_away": american_to_decimal(o.get("saO")),
        "provider": o.get("prov"),
    }


def load_all():
    raw = _load("raw.json")
    prox = _load("proximos.json")
    top5 = _load("espn_top5.json")
    leagues = load_europe(raw)
    leagues["PER"] = load_peru(raw)
    leagues = {k: add_xg_proxy(v) for k, v in leagues.items() if v is not None and not v.empty}

    upcoming = []
    for code, lg in LEAGUES.items():
        if code == "INT":
            continue
        hist = leagues.get(code)
        if hist is None or hist.empty:
            continue
        cur_season = hist.season.iloc[-1]
        current_teams = sorted(set(hist[hist.season == cur_season].home) | set(hist[hist.season == cur_season].away))
        all_teams = sorted(set(hist.home) | set(hist.away))
        nmap = build_name_map(hist, top5.get(lg["espn"], [])) if lg["fd"] else {}
        for e in prox["leagues"].get(lg["espn"], []):
            h = next(t for t in e["t"] if t["ha"] == "home")
            a = next(t for t in e["t"] if t["ha"] == "away")
            if lg["fd"]:
                hn = nmap.get(h["name"]) or fuzzy_team(h["name"], current_teams)
                an = nmap.get(a["name"]) or fuzzy_team(a["name"], current_teams)
            else:
                hn = h["name"] if h["name"] in all_teams else fuzzy_team(h["name"], all_teams)
                an = a["name"] if a["name"] in all_teams else fuzzy_team(a["name"], all_teams)
            o = e.get("odds") or {}
            odds = _odds_dec(o)
            upcoming.append({
                "id": e["id"], "league": code, "date": e["date"], "venue": e.get("venue"), "neutral": False,
                "home": hn, "away": an, "home_display": h["name"], "away_display": a["name"],
                "home_espn": h["name"], "away_espn": a["name"],
                "espn_form": {"home": h.get("form"), "away": a.get("form")},
                "espn_record": {"home": h.get("rec"), "away": a.get("rec")},
                "odds": odds, "arbitro": prox.get("arbitros", {}).get(e["id"]),
            })
    # árbitros publicados por football-data (Inglaterra, días antes del partido)
    fx = fixture_referees(raw["fd"].get("fixtures"))
    for u in upcoming:
        code_fd = LEAGUES[u["league"]]["fd"]
        if u.get("arbitro") or not code_fd:
            continue
        d = pd.Timestamp(u["date"]).tz_localize(None).normalize()
        for dd in (d, d - pd.Timedelta(days=1), d + pd.Timedelta(days=1)):
            ref = fx.get((code_fd, dd, u["home"], u["away"]))
            if ref:
                u["arbitro"] = ref
                break
    # selecciones
    ip = os.path.join(DATA_DIR, "int_results.csv")
    ie = os.path.join(DATA_DIR, "internacional.json")
    if os.path.exists(ip) and os.path.exists(ie):
        espn_int = _load("internacional.json")
        idf = load_international(ip, espn_int)
        leagues["INT"] = idf
        teams = set(idf.home) | set(idf.away)
        for e in int_upcoming(espn_int, teams):
            h, a = e["t"]
            upcoming.append({
                "id": e["id"], "league": "INT", "competicion": e["competicion"], "date": e["date"], "venue": e["venue"],
                "neutral": e["neutral"], "home": h["key"], "away": a["key"],
                "home_display": ES_NAMES.get(h["key"], h["name"]), "away_display": ES_NAMES.get(a["key"], a["name"]),
                "home_espn": h["name"], "away_espn": a["name"],
                "espn_form": {"home": h.get("form"), "away": a.get("form")}, "espn_record": {}, "odds": _odds_dec(e["odds"]),
                "arbitro": prox.get("arbitros", {}).get(e["id"]),
            })
    return leagues, upcoming, prox.get("fetched")


def fixture_referees(txt) -> dict:
    """{(div, fecha, local, visita): árbitro} desde fixtures.csv de football-data."""
    if not txt:
        return {}
    try:
        f = pd.read_csv(io.StringIO(txt), on_bad_lines="skip")
    except (ValueError, pd.errors.ParserError):
        return {}
    f.columns = [c.lstrip("﻿") for c in f.columns]
    if not {"Div", "Date", "HomeTeam", "AwayTeam", "Referee"} <= set(f.columns):
        return {}
    f = f.dropna(subset=["Referee"])
    f["d"] = pd.to_datetime(f.Date, dayfirst=True, errors="coerce")
    return {(r.Div, r.d, r.HomeTeam.strip(), r.AwayTeam.strip()): r.Referee.strip() for r in f.itertuples() if not pd.isna(r.d)}


def load_results() -> dict:
    """Resultados reales por id de ESPN: marcador, descanso, córners y amarillas (para liquidar el historial)."""
    out = {}
    try:
        prox = _load("proximos.json")
    except OSError:
        prox = {}
    for eid, r in (prox.get("resultados") or {}).items():
        if r.get("hg") is not None:
            out[eid] = {"hg": r["hg"], "ag": r["ag"]}
    try:
        raw = _load("raw.json")
        for evs in raw.get("espn", {}).values():
            for e in evs:
                if e["status"] not in ("STATUS_FULL_TIME", "STATUS_FINAL_PEN", "STATUS_FINAL_AET"):
                    continue
                h = next(t for t in e["t"] if t["ha"] == "home"); a = next(t for t in e["t"] if t["ha"] == "away")
                num = lambda t, k: pd.to_numeric(t["st"].get(k), errors="coerce")
                c = num(h, "wonCorners") + num(a, "wonCorners")
                out.setdefault(e["id"], {}).update({"hg": int(h["score"]), "ag": int(a["score"]),
                                                    **({"corners": float(c)} if not pd.isna(c) else {})})
    except (OSError, KeyError, ValueError, StopIteration):
        pass
    try:
        matches = _load("jugadores.json")["matches"]
    except (OSError, KeyError):
        matches = []
    for m in matches:
        r = out.setdefault(m["id"], {})
        if m.get("score") and m["score"][0] is not None:
            r.setdefault("hg", m["score"][0]); r.setdefault("ag", m["score"][1])
        if m.get("ht") and None not in m["ht"]:
            r["hthg"], r["htag"] = m["ht"]
        st = [t.get("st") or {} for t in m.get("teams") or []]
        if len(st) == 2:
            num = lambda d, k: pd.to_numeric(d.get(k), errors="coerce")
            c, y = num(st[0], "wonCorners") + num(st[1], "wonCorners"), num(st[0], "yellowCards") + num(st[1], "yellowCards")
            if not pd.isna(c):
                r["corners"] = float(c)
            if not pd.isna(y):
                r["cards"] = float(y)
    return {k: v for k, v in out.items() if v.get("hg") is not None}

"""Carga los archivos de caché y los convierte en tablas limpias por liga."""
from __future__ import annotations

import io
import json
import math
import os
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from .config import LEAGUES, INT_SINCE, FRIENDLY_WEIGHT, WOMEN_HISTORY, ESPN_ANUALES
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


def load_espn(by_year: dict, div: str, tag: str = "", seen=None) -> list[dict]:
    """Partidos terminados de un scoreboard de ESPN (por año) en el formato de las demás ligas."""
    rows, seen = [], seen if seen is not None else set()
    for year, evs in by_year.items():
        for e in evs:
            if e["status"] not in ("STATUS_FULL_TIME", "STATUS_FINAL_PEN", "STATUS_FINAL_AET") or e["id"] in seen:
                continue
            seen.add(e["id"])
            h = next((t for t in e.get("t") or [] if t.get("ha") == "home"), None)
            a = next((t for t in e.get("t") or [] if t.get("ha") == "away"), None)
            if h is None or a is None:
                continue
            f = lambda t, k: pd.to_numeric((t.get("st") or {}).get(k), errors="coerce")
            try:
                hg, ag = int(h["score"]), int(a["score"])
            except (TypeError, ValueError):
                continue
            rows.append(_sin_cobertura({
                "date": pd.to_datetime(e["date"]).tz_localize(None).normalize(), "home": h["name"], "away": a["name"],
                "hg": hg, "ag": ag, "hs": f(h, "totalShots"), "as": f(a, "totalShots"),
                "hst": f(h, "shotsOnTarget"), "ast": f(a, "shotsOnTarget"), "hc": f(h, "wonCorners"), "ac": f(a, "wonCorners"),
                "hy": f(h, "yellowCards"), "ay": f(a, "yellowCards"),
                "hposs": f(h, "possessionPct"), "aposs": f(a, "possessionPct"), "neutral": bool(e.get("neutral")),
                "season": f"{year}-{e.get('season') or ''}", "div": div, "tournament": tag,
            }))
    return rows


STAT_COLS = ("hs", "as", "hst", "ast", "hc", "ac", "hy", "ay", "hposs", "aposs")
MAX_CORNERS, MAX_TARJETAS = 40, 20      # totales por partido fuera de este rango son datos corruptos


def _sin_cobertura(row: dict) -> dict:
    """ESPN pone 0 en todas las estadísticas cuando no cubrió el partido: eso es dato faltante, no un cero.
    0 córners en total tampoco ocurre en la práctica (también se toma como faltante)."""
    tiros = row.get("hs", np.nan) + row.get("as", np.nan)
    if tiros == 0:
        for c in STAT_COLS:
            row[c] = np.nan
    c = row.get("hc", np.nan) + row.get("ac", np.nan)
    if c == 0 or not (0 <= c <= MAX_CORNERS):
        row["hc"] = row["ac"] = np.nan
    y = row.get("hy", np.nan) + row.get("ay", np.nan)
    if not (0 <= y <= MAX_TARJETAS):
        row["hy"] = row["ay"] = np.nan
    return row


def load_women(raw) -> pd.DataFrame:
    """Champions femenina + ligas domésticas de sus equipos: un solo grupo de ratings (la Champions las conecta)."""
    rows, seen = [], set()
    for slug in WOMEN_HISTORY:
        rows += load_espn((raw.get("espn_w") or {}).get(slug, {}), "UWCL", slug, seen)
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    d["mw"] = 1.0
    for c in ["hthg", "htag", "hxg", "axg", "hr", "ar", "hf", "af", "referee"] + list(ODDS):
        d[c] = np.nan
    return d


def load_espn_anual(raw, code: str) -> pd.DataFrame:
    """Liga de calendario anual solo de ESPN (Argentina, MLS, Brasil): mismo formato que las demás."""
    rows = load_espn((raw.get("espn_x") or {}).get(code, {}), code)
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    d["mw"] = 1.0
    for c in ["hthg", "htag", "hxg", "axg", "hr", "ar", "hf", "af", "referee"] + list(ODDS):
        d[c] = np.nan
    return d


def load_peru(raw) -> pd.DataFrame:
    rows, seen = [], set()
    for year, evs in raw["espn"].items():
        for e in evs:
            if e["status"] not in ("STATUS_FULL_TIME", "STATUS_FINAL_PEN", "STATUS_FINAL_AET") or e["id"] in seen:
                continue
            seen.add(e["id"])
            try:
                h = next((t for t in e.get("t") or [] if t.get("ha") == "home"), None)
                a = next((t for t in e.get("t") or [] if t.get("ha") == "away"), None)
                if h is None or a is None:
                    continue
                f = lambda t, k: pd.to_numeric((t.get("st") or {}).get(k), errors="coerce")
                rows.append(_sin_cobertura({
                    "date": pd.to_datetime(e["date"]).tz_localize(None).normalize(), "home": h["name"], "away": a["name"],
                    "hg": int(h["score"]), "ag": int(a["score"]), "hs": f(h, "totalShots"), "as": f(a, "totalShots"),
                    "hst": f(h, "shotsOnTarget"), "ast": f(a, "shotsOnTarget"), "hc": f(h, "wonCorners"), "ac": f(a, "wonCorners"),
                    "hposs": f(h, "possessionPct"), "aposs": f(a, "possessionPct"),
                    "season": f"{year}-{e.get('season') or ''}", "div": "PER",
                }))
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
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
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or v == 0:
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
                      "hg": hg, "ag": ag, "neutral": int_neutral(e), "tournament": e.get("comp") or ""})
    if extra:
        d = pd.concat([d, pd.DataFrame(extra)], ignore_index=True)
    d = d.drop_duplicates(subset=["date", "home", "away"]).sort_values("date").reset_index(drop=True)
    d["mw"] = np.where(d.tournament.str.contains("Friendly|Amistoso", case=False, na=False), FRIENDLY_WEIGHT, 1.0)
    d["season"] = d.date.dt.year.astype(str)
    d["div"] = "INT"
    for c in ["hthg", "htag", "hxg", "axg", "hs", "as", "hst", "ast", "hc", "ac", "hy", "ay", "hr", "ar", "hf", "af", "referee"] + list(ODDS):
        d[c] = np.nan
    return d


VENUE_COUNTRY = {"usa": "united states", "china pr": "china", "korea republic": "south korea", "cote d'ivoire": "ivory coast",
                 "turkiye": "turkey", "czechia": "czech republic", "ir iran": "iran", "uae": "united arab emirates",
                 "kyrgyz republic": "kyrgyzstan", "congo dr": "dr congo", "us virgin islands": "united states virgin islands"}


def _pais(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().replace(".", "").replace("saint ", "st ")
    s = " ".join(s.split())
    s = VENUE_COUNTRY.get(s, s)
    return s[:-8] if s.endswith(" islands") else s


def _mismo_pais(team: str, country: str) -> bool:
    c = _pais(country)
    for t in {team, ESPN_TO_INT.get(team, team)}:
        t = _pais(t)
        if t == c or t.startswith(c + " ") or c.startswith(t + " ") or t.endswith(" " + c):   # "dr congo" / "congo"
            return True
    return False


def int_neutral(e: dict) -> bool:
    """Selecciones: ESPN casi nunca marca neutralSite. Se usa el país de la sede: si no es el del local, es neutral
    (si es el del visitante, también: el local nominal no tiene ventaja). Sin país de la sede, lo que diga ESPN."""
    if e.get("neutral"):
        return True
    country = e.get("venue_country")
    if not isinstance(country, str) or not _pais(country) or not isinstance(e.get("home"), str):
        return bool(e.get("neutral"))
    return not _mismo_pais(e["home"], country)


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
        out.append({"id": e["id"], "date": e["date"], "venue": e.get("venue"), "neutral": int_neutral(e),
                    "competicion": e.get("comp"), "t": [
                        {"ha": "home", "name": e["home"], "key": hn, "form": e.get("hform")},
                        {"ha": "away", "name": e["away"], "key": an, "form": e.get("aform")}], "odds": e.get("odds")})
    return out


def _linea(x):
    """Línea de goles o de hándicap de ESPN como número; None si no es número (ESPN a veces manda "OFF" o vacío)."""
    try:
        v = float(str(x).replace("+", ""))
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def _odds_dec(o):
    if not o or not o.get("h"):
        return None
    ou = _linea(o.get("ou"))
    return {
        "H": american_to_decimal(o.get("h")), "D": american_to_decimal(o.get("d")), "A": american_to_decimal(o.get("a")),
        "H_open": american_to_decimal(o.get("hO")), "D_open": american_to_decimal(o.get("dO")),
        "A_open": american_to_decimal(o.get("aO")),
        "ou_line": ou, "over": american_to_decimal(o.get("ov")) if ou is not None else None,
        "under": american_to_decimal(o.get("un")) if ou is not None else None,
        "ah_line": _linea(o.get("sh")),
        "ah_home": american_to_decimal(o.get("shO")), "ah_away": american_to_decimal(o.get("saO")),
        "provider": o.get("prov"),
    }


def load_all():
    raw = _load("raw.json")
    prox = _load("proximos.json")
    top5 = _load("espn_top5.json")
    leagues = load_europe(raw)
    leagues["PER"] = load_peru(raw)
    leagues["UWCL"] = load_women(raw)
    for code in ESPN_ANUALES:
        leagues[code] = load_espn_anual(raw, code)
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
            h = next((t for t in e.get("t") or [] if t.get("ha") == "home"), None)
            a = next((t for t in e.get("t") or [] if t.get("ha") == "away"), None)
            if h is None or a is None:
                continue
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


FINAL_EXTRA = ("STATUS_FINAL_PEN", "STATUS_FINAL_AET")   # se liquidan con el marcador de los 90 minutos
MANUALES = "resultados_manuales.json"


def _num(d: dict, k: str):
    """Número finito de una estadística de ESPN, o None."""
    v = pd.to_numeric((d or {}).get(k), errors="coerce")
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _suma(a: dict, b: dict, k: str):
    x, y = _num(a, k), _num(b, k)
    return None if x is None or y is None else x + y


def _entero(v, lo: int = 0, hi: int = 20):
    """Entero en [lo, hi] (acepta 2 o 2.0, no True/'2'/2.5); None si no."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v != int(v):
        return None
    return int(v) if lo <= v <= hi else None


def _manual_valido(eid: str, r) -> dict | None:
    """Entrada de resultados_manuales.json: hg y ag enteros 0-20, fuente https://. La regla de las 24 horas desde el
    inicio del partido la aplica historial.liquidar (es quien conoce la fecha). Si no cumple: aviso y se descarta."""
    motivo = None
    if not isinstance(r, dict):
        motivo = "no es un objeto"
    elif _entero(r.get("hg")) is None or _entero(r.get("ag")) is None:
        motivo = "hg/ag deben ser enteros entre 0 y 20"
    elif not (isinstance(r.get("fuente"), str) and r["fuente"].startswith("https://")):
        motivo = "la fuente debe empezar con https://"
    if motivo:
        print(f"::warning::resultado manual {eid} descartado: {motivo}")
        return None
    out = {"hg": _entero(r["hg"]), "ag": _entero(r["ag"]), "fuente": r["fuente"], "manual": True}
    for k, hi in (("hthg", 20), ("htag", 20), ("corners", MAX_CORNERS), ("cards", MAX_TARJETAS)):
        if _entero(r.get(k), 0, hi) is not None:
            out[k] = _entero(r[k], 0, hi)
    return out


def load_results() -> dict:
    """Resultados reales por id de ESPN para liquidar el historial: marcador de los 90 minutos, descanso, córners y amarillas.

    - Partidos con prórroga o penales: marcador de los 90 minutos (suma de los dos primeros periodos de la ficha, solo si
      no supera el final de cada equipo); si no hay, el partido NO se liquida. Sus córners y tarjetas incluyen la
      prórroga: se anulan.
    - ESPN pone 0 en todas las estadísticas cuando no cubrió el partido: 0 córners es dato faltante, y 0 tarjetas solo
      cuenta si la ficha tiene estadísticas (tiros, faltas o córners). Totales fuera de rango (córners 0-40, tarjetas
      0-20) o no finitos se descartan. "_anular" lista campos que deben quedar vacíos, salvo que otra fuente traiga un
      valor mayor que 0.
    - data/resultados_manuales.json ({id: {hg, ag, fuente}}) completa partidos que ESPN borró; se marcan "manual"."""
    out, estado, finales = {}, {}, {}
    anular = defaultdict(set)
    try:
        prox = _load("proximos.json")
    except (OSError, ValueError):
        prox = {}
    for eid, r in (prox.get("resultados") or {}).items():
        try:
            hg, ag = _entero(r.get("hg"), 0, 99), _entero(r.get("ag"), 0, 99)
            if hg is not None and ag is not None:
                out[eid] = {"hg": hg, "ag": ag}
            if r.get("st"):
                estado[eid] = r["st"]
        except (AttributeError, TypeError):
            continue
    try:
        raw = _load("raw.json")
    except (OSError, ValueError):
        raw = {}
    for evs in (raw.get("espn") or {}).values():
        for e in evs:
            try:
                if e["status"] not in ("STATUS_FULL_TIME", "STATUS_FINAL_PEN", "STATUS_FINAL_AET"):
                    continue
                h = next((t for t in e.get("t") or [] if t.get("ha") == "home"), None)
                a = next((t for t in e.get("t") or [] if t.get("ha") == "away"), None)
                if h is None or a is None:
                    continue
                hg, ag = int(h["score"]), int(a["score"])
                estado.setdefault(e["id"], e["status"])
                out.setdefault(e["id"], {}).update({"hg": hg, "ag": ag})
                c = _suma(h.get("st"), a.get("st"), "wonCorners")
                if c is not None and 0 < c <= MAX_CORNERS:
                    out[e["id"]]["corners"] = c
                elif c == 0:
                    anular[e["id"]].add("corners")
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
    try:
        matches = _load("jugadores.json")["matches"]
    except (OSError, KeyError, ValueError):
        matches = []
    ls90 = {}
    for m in matches:
        try:
            r = out.setdefault(m["id"], {})
            if m.get("st"):
                estado.setdefault(m["id"], m["st"])
            sc = m.get("score") or [None, None]
            if _entero(sc[0], 0, 99) is not None and _entero(sc[1], 0, 99) is not None:
                r.setdefault("hg", int(sc[0])); r.setdefault("ag", int(sc[1]))
                finales[m["id"]] = (int(sc[0]), int(sc[1]))
            ht = m.get("ht")
            if ht and _entero(ht[0], 0, 99) is not None and _entero(ht[1], 0, 99) is not None:
                r["hthg"], r["htag"] = int(ht[0]), int(ht[1])
            ls = m.get("ls")
            if ls and len(ls) == 2 and min(len(ls[0]), len(ls[1])) >= 2 and None not in ls[0][:2] + ls[1][:2]:
                ls90[m["id"]] = (int(ls[0][0]) + int(ls[0][1]), int(ls[1][0]) + int(ls[1][1]))
            st = [t.get("st") or {} for t in m.get("teams") or []]
            if len(st) == 2:
                c = _suma(st[0], st[1], "wonCorners")
                y = _suma(st[0], st[1], "yellowCards")
                cobertura = any((_suma(st[0], st[1], k) or 0) > 0 for k in ("totalShots", "foulsCommitted", "wonCorners"))
                if c is not None and 0 < c <= MAX_CORNERS:
                    r["corners"] = c
                elif c == 0:
                    anular[m["id"]].add("corners")
                if y is not None and (0 < y <= MAX_TARJETAS or (y == 0 and cobertura)):
                    r["cards"] = y
                elif y == 0:
                    anular[m["id"]].add("cards")
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            continue
    for eid, st in estado.items():
        if st not in FINAL_EXTRA or eid not in out:
            continue
        fin = finales.get(eid) or (out[eid].get("hg"), out[eid].get("ag"))
        l90 = ls90.get(eid)
        if l90 is None or None in fin or l90[0] > fin[0] or l90[1] > fin[1]:
            out.pop(eid)                      # sin un marcador de los 90 minutos confiable no se liquida
            continue
        out[eid].update({"hg": l90[0], "ag": l90[1], "final": st})
        for k in ("corners", "cards"):
            out[eid].pop(k, None)
            anular[eid].add(k)
    try:
        manual = _load(MANUALES)
    except (OSError, ValueError):
        manual = {}
    for eid, r in (manual.items() if isinstance(manual, dict) else []):
        if eid.startswith("_") or out.get(eid, {}).get("hg") is not None:
            continue
        ok = _manual_valido(eid, r)
        if ok:
            out[eid] = ok
    for eid, ks in anular.items():
        if eid not in out:
            continue
        # no se anula lo que otra fuente sí trae (valor > 0); con prórroga o penales se anula siempre
        ks = {k for k in ks if out[eid].get("final") or not (out[eid].get(k) or 0) > 0}
        if ks:
            out[eid]["_anular"] = sorted(ks)
    return {k: v for k, v in out.items() if v.get("hg") is not None}

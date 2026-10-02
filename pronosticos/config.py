"""Configuración general del motor de pronósticos."""

# Ligas soportadas. fd = código football-data.co.uk (None si no existe), espn = slug ESPN.
LEAGUES = {
    "E0":  {"name": "Premier League", "country": "Inglaterra", "fd": "E0",  "espn": "eng.1"},
    "SP1": {"name": "LaLiga",         "country": "España",     "fd": "SP1", "espn": "esp.1"},
    "I1":  {"name": "Serie A",        "country": "Italia",     "fd": "I1",  "espn": "ita.1"},
    "D1":  {"name": "Bundesliga",     "country": "Alemania",   "fd": "D1",  "espn": "ger.1"},
    "F1":  {"name": "Ligue 1",        "country": "Francia",    "fd": "F1",  "espn": "fra.1"},
    "PER": {"name": "Liga 1",         "country": "Perú",       "fd": None,  "espn": "per.1"},
    "ARG": {"name": "Liga Profesional", "country": "Argentina", "fd": None,  "espn": "arg.1"},
    "MLS": {"name": "MLS",            "country": "Estados Unidos", "fd": None, "espn": "usa.1"},
    "UWCL": {"name": "Champions Femenina", "country": "Europa", "fd": None, "espn": "uefa.wchampions"},
    "INT": {"name": "Selecciones",    "country": "Internacional", "fd": None, "espn": None},
}

# Competiciones de selecciones (ESPN). Se incluyen solo si tienen partidos en el período.
INT_COMPETITIONS = [
    "uefa.nations", "fifa.friendly", "concacaf.nations.league", "caf.nations_qual", "fifa.world",
    "fifa.worldq.uefa", "fifa.worldq.conmebol", "fifa.worldq.concacaf", "fifa.worldq.caf", "fifa.worldq.afc",
    "conmebol.america", "uefa.euro", "uefa.euroq", "afc.cupq", "afc.asian.cup", "caf.nations", "concacaf.gold",
]
INT_RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
INT_SINCE = "2014-01-01"      # historia usada para selecciones
INT_XI = 0.00045             # las selecciones juegan poco: se olvida lento (vida media ~4 años, mejor en backtest)
FRIENDLY_WEIGHT = 0.6         # un amistoso pesa menos que un partido oficial

# Temporadas de historia (football-data usa '2526' = 2025/26). Se calculan automáticamente
# a partir de la fecha actual; aquí solo cuántas hacia atrás.
N_SEASONS_EUROPE = 4          # temporada actual + 3 anteriores
N_YEARS_PERU = 3              # año actual + 2 anteriores

# Ligas de calendario anual que salen solo de ESPN (resultados + estadísticas por año): código -> (slug, años)
ESPN_ANUALES = {"ARG": ("arg.1", 3), "MLS": ("usa.1", 3)}
ANUALES = ("PER", *ESPN_ANUALES)   # temporada = año calendario

# Champions femenina: sus equipos juegan pocos partidos europeos, así que los ratings también aprenden de sus ligas
# domésticas (solo como historia: en la web se muestran los partidos de la Champions). ESPN no tiene Alemania ni Italia.
WOMEN_HISTORY = ["uefa.wchampions", "eng.w.1", "esp.w.1", "fra.w.1"]
N_YEARS_WOMEN = 3

# Modelo
XI = 0.0019                   # decaimiento temporal por día (vida media ~ 1 año)
XG_WEIGHT = 0.35              # peso del xG frente a los goles reales cuando hay xG
HOME_SHRINK = 8.0             # penalización para la ventaja local por equipo (más = más parecida a la media)
MAX_GOALS = 10

# El peso de cada modelo (incluido el mercado) ya no es fijo: lo calcula ensamble.calibrar() cada semana
# con el backtest y queda en data/modelo.json. Árbitros: arbitros.py. Filtros de fijas: fijas.py.

# Criterios de "valor"
MIN_EDGE = 0.03               # ventaja mínima (prob_modelo * cuota - 1)
MIN_PROB = 0.25               # no recomendar apuestas con prob < 25%
KELLY_FRACTION = 0.25         # cuarto de Kelly

DAYS_AHEAD = 21               # partidos a mostrar

FD_BASE = "https://www.football-data.co.uk"
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

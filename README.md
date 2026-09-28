# Pizarra de Pronósticos

Motor de pronósticos de fútbol (Premier, LaLiga, Serie A, Bundesliga, Ligue 1, Liga 1 Perú y selecciones: Nations League, eliminatorias, Copa América, Eurocopa, Mundial, Copa África, amistosos) que:

1. Descarga resultados, estadísticas y cuotas históricas (football-data.co.uk), resultados de selecciones desde 2014 (martj42/international_results) y la Liga 1, los próximos partidos y las cuotas actuales (ESPN).
2. Ajusta un modelo **Dixon-Coles** por liga (ataque/defensa por equipo, ventaja local por equipo, más peso a lo reciente, xG aproximado con tiros).
3. Mezcla el modelo con el mercado (75% / 25%, calibrado con backtest) y calcula más de 25 mercados por partido.
4. Proyecta a cada jugador (minutos, goles, asistencias, tiros, tiros al arco, faltas, tarjetas, fueras de juego) con sus estadísticas partido a partido de ESPN, y calcula mercados de equipo (tiros, tiros al arco, faltas, fueras de juego, córners, tarjetas).
5. Compara con las cuotas reales: valor esperado, cuota justa y stake (¼ Kelly).
6. Genera `docs/index.html`, una web estática con todo lo anterior + forma, estadísticas, H2H, tablas y el backtest.

## Uso en tu PC

```bash
pip install -r requirements.txt
python -m pronosticos.build          # descarga datos frescos y genera docs/index.html
python -m pronosticos.build --offline   # regenera usando la caché de data/
```
Abre `docs/index.html` en el navegador. La primera vez tarda más (descarga ~3.000 fichas de partido de ESPN); después solo baja los partidos nuevos. El cálculo completo tarda unos 8 minutos.

## Actualización automática (gratis con GitHub)

1. Crea un repositorio en GitHub y sube esta carpeta.
2. En *Settings → Pages*: Source = *Deploy from a branch*, rama `main`, carpeta `/docs`.
3. En *Settings → Actions → General*: activa *Read and write permissions*.
4. Listo: el workflow `.github/workflows/actualizar.yml` se ejecuta cada día (y viernes/sábado otra vez) y publica la web en `https://TU-USUARIO.github.io/TU-REPO/`. También puedes lanzarlo a mano desde la pestaña *Actions*.

Si alguna fuente bloquea los servidores de GitHub, ejecútalo en tu PC con el Programador de tareas de Windows (`python -m pronosticos.build`) y sube `docs/`.

## Ajustes (`pronosticos/config.py`)

| Parámetro | Qué controla |
|---|---|
| `MARKET_WEIGHT` | Peso del mercado en la probabilidad final (0.75) |
| `MIN_EDGE`, `MIN_PROB` | Cuándo marcar una apuesta "con valor" |
| `KELLY_FRACTION` | Fracción de Kelly para el stake |
| `XI` | Rapidez con la que "olvida" partidos viejos |
| `DAYS_AHEAD` | Cuántos días de partidos mostrar |
| `LEAGUES` | Ligas incluidas |
| `INT_COMPETITIONS` | Competiciones de selecciones que se siguen |
| `FRIENDLY_WEIGHT`, `INT_XI` | Peso de los amistosos y memoria del modelo de selecciones |

## Archivos

- `pronosticos/fetch.py` descarga · `data.py` limpia y une fuentes · `model.py` Dixon-Coles
- `players.py` jugadores y estadísticas de equipo · `markets.py` todos los mercados · `stats.py` forma/H2H/tabla/córners · `backtest.py` validación
- `build.py` pipeline completo · `web/template.html` la página

## Límites

No hay fijas. El modelo no conoce lesiones, sanciones ni rotaciones. En el backtest, apostar solo con el modelo contra la cuota promedio perdió dinero; úsalo como herramienta de análisis y compara siempre cuotas entre casas. Apuesta con responsabilidad.

## La web (React)

La interfaz está hecha con React + Tailwind + Framer Motion en `web-src/`. Ya viene compilada en `web/app.html`,
así que el motor Python y la actualización diaria **no necesitan Node**: solo inyectan los datos nuevos.

Si cambias el diseño:
```bash
cd web-src
pnpm install
bash bundle.sh                # genera bundle.html
cp bundle.html ../web/app.html
cd .. && python -m pronosticos.build --solo-web
```

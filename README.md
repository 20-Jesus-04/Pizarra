# Pizarra de Pronósticos

Motor de pronósticos de fútbol (Premier, LaLiga, Serie A, Bundesliga, Ligue 1, Liga 1 Perú y selecciones: Nations League, eliminatorias, Copa América, Eurocopa, Mundial, Copa África, amistosos) que corre solo cada día:

1. **Datos**: resultados, estadísticas, cuotas y árbitros (football-data.co.uk), selecciones desde 2014 (martj42/international_results), Liga 1, próximos partidos, cuotas actuales, fichas de jugadores y árbitros designados (ESPN).
2. **Seis modelos independientes**: Poisson, Dixon-Coles, Elo, Bayesiano (Gamma-Poisson), consenso del mercado (cuotas sin margen) y XGBoost (forma, descanso, xG reciente, Elo…).
3. **Ensamble**: los pesos de cada modelo se recalibran cada semana con un backtest walk-forward (cada semana se reentrena solo con el pasado) y se validan con partidos que no se usaron para elegirlos. Con cuotas, el mercado se lleva casi todo el peso (es muy difícil de superar); sin cuotas (Liga 1, selecciones, partidos lejanos) el ensamble mejora a Dixon-Coles solo.
4. **Mercados**: el 1X2 y el over 2.5 del ensamble se convierten en una matriz de marcadores → más de 25 mercados + jugadores + estadísticas de equipo.
5. **Árbitros**: las tarjetas esperadas se multiplican por el factor del árbitro (tarjetas reales / esperadas por los equipos, encogido hacia la media).
6. **Auditor automático**: reglas que marcan cada pronóstico como ok / revisar / bloqueado.
7. **Oportunidades y fijas**: cada pick se cruza con 5 señales (modelo, historial de ese tipo de pick, últimos 8 partidos de ambos equipos, jugadores y cuota) y recibe un puntaje 0-100. Oportunidad: las señales lo respaldan (hasta 3 por partido, cuota justa 1.30-2.60). Fija: todo confirma, a cualquier cuota. También oportunidades de jugador donde la validación de jugadores lo respalda.
8. **Historial**: cada predicción se registra antes del partido en `data/historial.json`, se liquida después y nunca se borra. La web muestra Brier, calibración y acierto reales.
9. `docs/index.html`: web estática con todo lo anterior (Partidos, Fijas, Resultados, Ligas, Método).

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

## Ajustes

| Dónde | Qué controla |
|---|---|
| `config.py` `MIN_EDGE`, `MIN_PROB`, `KELLY_FRACTION` | Cuándo marcar una apuesta "con valor" y el stake |
| `config.py` `XI`, `INT_XI`, `FRIENDLY_WEIGHT` | Memoria de los modelos y peso de amistosos |
| `config.py` `DAYS_AHEAD`, `LEAGUES`, `INT_COMPETITIONS` | Qué partidos y ligas se muestran |
| `ensamble.py` `MAX_AGE_DAYS` | Cada cuántos días se recalibra el ensamble (6) |
| `arbitros.py` `REF_K`, `REF_XI` | Cuánto se encoge el factor del árbitro y su memoria |
| `oportunidades.py` | Pesos de las 5 señales, puntaje mínimo (65) y de fija (75), rango de cuotas, topes |

`python -m pronosticos.build --recalibrar` fuerza el backtest del ensamble (≈2-3 min).

## Archivos

- `fetch.py` descarga · `data.py` limpia y une fuentes · `model.py` Dixon-Coles · `modelos.py` Poisson, Bayes, Elo, XGBoost
- `ensamble.py` backtest, pesos, calibración y motor · `arbitros.py` · `auditor.py` · `oportunidades.py` · `historial.py` · `picks.py`
- `players.py` jugadores · `markets.py` mercados · `stats.py` forma/H2H/tabla · `backtest.py` métricas
- `build.py` pipeline completo · `web-src/` la interfaz (compilada en `web/app.html`)

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

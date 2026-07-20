# Cooling Economy

**Do hydration breaks change the game?** A data project that tracked every match of the 2026 FIFA World Cup to test whether the tournament's mandatory cooling breaks changed how the football played out, and what those breaks were worth in broadcast ad money. The tournament ended July 19, 2026; the dataset is complete and frozen, and the dashboard now stands as the project's final report.

### [Open the dashboard →](https://rograph.github.io/cooling-economy/)

Part of **Cooling Break**, a sports analytics lab by [Rodolfo López](https://rodolfo.app).

![Cooling Economy - do hydration breaks change the game?](./cooling_economy_card.png)

---

## The question

At the 2026 World Cup, every match stopped twice for a three-minute cooling break, near the 22nd and 67th minute, so players could drink and cool down. Broadcasters and coaches treated these pauses as a reset. This project asked a plain question and answered it with data: did the breaks change the football? And since every break is also two extra minutes of commercial airtime, a second track modeled what that airtime was worth.

## What the data says, final

Across all 104 matches, play after a break looks like play before it. Goals in the ten minutes after the breaks (53) trail the ten minutes before (59), but the gap sits inside the range you get by chance, it shrank as the sample grew, and the same pattern holds in hot games and cooler ones. The 2026 numbers track the no-break 2018 and 2022 World Cups closely. Final verdict: no measurable effect on match outcomes. The broadcast track closes at an estimated **$351.6M** (base scenario, range $184M to $598M) of US ad inventory created by the breaks across the tournament, built from sourced spot prices and reported Nielsen audiences where available.

Every figure on the dashboard is labeled as measured, estimated, or assumed, and each stored record carries a sources log. One pending correction: the final's official Nielsen audience, added when published.

## What is on the dashboard

- **Home** - the final verdict and the key numbers at a glance.
- **Analysis** - per-match and pooled views: a stadium heat map, before/after break tables, possession and momentum shifts, goal timing, chance quality (xG), substitutions, player welfare, and a heat-versus-goals scatter. Filter by round or by heat.
- **Verdict** - the closing call, with the confidence band that never left the no-effect line.
- **Broadcast** - the ad-revenue model: spot prices by stage, reported audiences, revenue flows, and a build-your-own estimate.
- **Bracket** - the full knockout path to Spain's title.
- **About** - data sources, method, honest limits, glossary, and the full update log.

English and Spanish, light and dark, Celsius and Fahrenheit.

## How it worked

```
ESPN public API  ──┐
                   ├──▶  update.py  ──▶  SQLite store  ──▶  build_dashboard.py  ──▶  index.html
Open-Meteo (WBGT) ─┘         ▲                                                          │
                             │                                                          ▼
                    GitHub Actions (twice-daily cron) ────────────────────▶   GitHub Pages
```

During the tournament an automated job ran twice a day: it pulled newly finished matches and their events from ESPN's public football API, estimated the real-feel heat (WBGT) at each stadium from Open-Meteo temperature and humidity, appended everything to a growing SQLite store, recomputed every panel, and republished the static site. Nothing was entered by hand. With the tournament over, the schedule is retired (`workflow_dispatch` remains for one-off corrections) and the store is frozen at 104 matches.

## Method, briefly

Three comparisons ran side by side: before versus after each break within the same match, which cancels out team quality; hot games versus cooler ones, to separate a break effect from a heat effect; and 2026 with breaks against 2018 and 2022 without them. A team-strength (Elo) control checks the momentum-reset story. Effect sizes come with confidence intervals, and thin or uncertain numbers are labeled as such rather than overstated. This is observational, not a controlled experiment: heat and breaks travel together, and the dashboard says so.

## Tech

- **Python standard library only** for the updater and the site builder, so it ran in CI with no dependencies and no API keys.
- **SQLite** for the persistent per-match store (`cooling_economy.db`, in this repo).
- **Vanilla HTML, CSS and JavaScript** with Chart.js for a single self-contained page.
- **GitHub Actions** for the scheduled pipeline, **GitHub Pages** for hosting.

## Data sources

- Match events, possession, attendance and officials: ESPN public football API and match centre.
- Weather for the WBGT estimate: Open-Meteo hourly and archive APIs.
- Audiences: Nielsen figures as reported by Sports Media Watch, Variety, Front Office Sports and Hollywood Reporter; tiered estimates elsewhere, labeled in the data.
- Spot pricing: trade-press ranges (Front Office Sports, Hollywood Reporter, HITC).
- No-break baselines: 2018 and 2022 World Cups.

---

Built by **Rodolfo López** · Part of the **Cooling Break** sports analytics lab · [rodolfo.app](https://rodolfo.app) · [LinkedIn](https://www.linkedin.com/in/rdflopez/)

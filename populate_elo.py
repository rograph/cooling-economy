#!/usr/bin/env python3
"""
Cooling Economy — team-strength control (Elo).
Populates matches.home_elo / matches.away_elo from World Football Elo Ratings
(eloratings.net), retrieved 2026-07-09.

Methodology note: we use each team's Elo as of ~1 month before retrieval
(eloratings.net's "1 month ago" column), not the CURRENT (2026-07-09) Elo.
The World Cup started 2026-06-11, so "1 month ago" (~2026-06-09) is a close
proxy for PRE-TOURNAMENT strength. Using current, live Elo instead would be
circular: teams that have overperformed in the tournament already have
inflated Elo, which would launder in-tournament results back into a
"pre-existing strength" control. This proxy isn't perfect (a few points of
early-June friendly results may be included) but avoids that circularity.
Confidence: medium. Source: https://www.eloratings.net/World.tsv (retrieved
2026-07-09). Swap in official pre-tournament FIFA rankings if a cleaner
snapshot is sourced later.
"""
import sqlite3, os, datetime

DB = os.environ.get("CE_DB", "cooling_economy.db")
NOW = datetime.datetime.utcnow().isoformat(timespec="seconds")

# team name (as stored in matches.home_team/away_team) -> elo ~1 month before
# 2026-07-09 (eloratings.net "1 month ago" column), i.e. an approx.
# pre-tournament rating. Source: eloratings.net/World.tsv, retrieved 2026-07-09.
ELO_PRETOURNAMENT = {
    "Spain": 2189, "Argentina": 2172, "France": 2143, "England": 2213,
    "Colombia": 2069, "Portugal": 2060, "Brazil": 2195, "Norway": 1972,
    "Netherlands": 2153, "Belgium": 2157, "Switzerland": 1949, "Morocco": 1923,
    "Mexico": 1985, "Germany": 2222, "Japan": 1925, "Croatia": 2015,
    "Ecuador": 1938, "Türkiye": 1910, "Uruguay": 2104, "Austria": 2070,
    "Senegal": 1879, "Paraguay": 1956, "Australia": 1875, "Egypt": 1872,
    "Algeria": 1807, "United States": 1890, "Scotland": 2104, "Sweden": 2013,
    "Canada": 1841, "Côte d'Ivoire": 1863, "Korea Republic": 1845,
    "Congo DR": 1782, "IR Iran": 1853, "Czechia": 2032, "Panama": 1773,
    "Jordan": 1701, "Cabo Verde": 1625, "Ghana": 1877, "Tunisia": 1757,
    "Iraq": 1740, "South Africa": 1847, "New Zealand": 1642, "Haiti": 1674,
    "Qatar": 1771, "Bosnia & Herz.": 1806, "Uzbekistan": 1766,
    "Saudi Arabia": 1736, "Curaçao": 1618,
}

def main():
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT match_id, home_team, away_team FROM matches").fetchall()
    updated, missing = 0, set()
    for mid, home, away in rows:
        he, ae = ELO_PRETOURNAMENT.get(home), ELO_PRETOURNAMENT.get(away)
        if he is None: missing.add(home)
        if ae is None: missing.add(away)
        if he is None or ae is None:
            continue
        con.execute("UPDATE matches SET home_elo=?, away_elo=? WHERE match_id=?", (he, ae, mid))
        con.execute("""INSERT INTO sources_log
            (match_id,table_ref,field,value,claim_type,confidence,source_name,source_url,retrieved_date,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (mid, "matches", "home_elo/away_elo", f"{he}/{ae}", "estimate", "medium",
             "eloratings.net", "https://www.eloratings.net/World.tsv", "2026-07-09",
             "Elo ~1 month before retrieval, used as a pre-tournament strength proxy (avoids circularity of using in-tournament-inflated current Elo)."))
        updated += 1
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    print(f"Populated Elo for {updated}/{n} matches.")
    if missing:
        print("Missing Elo for teams:", sorted(missing))
    con.close()

if __name__ == "__main__":
    main()

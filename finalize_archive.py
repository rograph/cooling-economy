#!/usr/bin/env python3
"""Tournament-complete finalization pass (2026-07-20).

Backfills descriptive metadata that the automated update.py path never
collected (attendance + referee) for every knockout match, using the same
sourced values as the earlier local backfill (ESPN official match-centre
Game Information panels, gameIds 760490-760517), plus press-sourced
officials for the 3rd-place match and final.

Facts only — nothing here touches the Track A break-window math.
Third-place attendance is left NULL (no published figure found as of
2026-07-20) rather than guessed.
"""
import sqlite3, os, datetime

DB = os.environ.get("CE_DB", "cooling_economy.db")
NOW = datetime.datetime.utcnow().isoformat(timespec="seconds")

# match_id: (attendance, referee, espn_gameid)  — R32 through QF
DATA = {
    "WC2026-R32-COD-NOR":        (69665, "Jesus Valenzuela", 760490),
    "WC2026-R32-MEX-ECU":        (80824, "Slavko Vincic", 760491),
    "WC2026-R32-FRA-SWE":        (80663, "Danny Makkelie", 760492),
    "WC2026-20260701-BEL-SEN":   (66925, "Hector Martinez", 760493),
    "WC2026-20260702-UNS-BOH":   (68827, "Raphael Claus", 760494),
    "WC2026-20260701-ENG-COD":   (68239, "Adham Mohammad", 760495),
    "WC2026-20260702-POR-CRO":   (43036, "Espen Eskas", 760496),
    "WC2026-20260702-SPA-AUS":   (70492, "Glenn Nyberg", 760497),
    "WC2026-20260703-SWI-ALG":   (52497, "Yael Falcon Perez", 760498),
    "WC2026-20260703-AUS-EGY":   (70244, "Gustavo Tejera", 760499),
    "WC2026-20260703-ARG-CAV":   (64478, "Drew Fischer", 760500),
    "WC2026-20260704-COL-GHA":   (69045, "Clement Turpin", 760501),
    "WC2026-20260704-CAN-MOR":   (68777, "Michael Oliver", 760502),
    "WC2026-20260704-PAR-FRA":   (68324, "Ilgiz Tantashev", 760503),
    "WC2026-20260705-BRA-NOR":   (80663, "Ismail Elfath", 760504),
    "WC2026-20260706-MEX-ENG":   (80824, "Alireza Faghani", 760505),
    "WC2026-20260706-POR-SPA":   (70649, "Anthony Taylor", 760506),
    "WC2026-20260707-UNS-BEL":   (66925, "Adham Mohammad", 760507),
    "WC2026-20260707-SWI-COL":   (52497, "Ivan Arcides Barton Cisneros", 760508),
    "WC2026-20260707-ARG-EGY":   (68239, "Francois Letexier", 760509),
    "WC2026-20260709-FRA-MOR":   (63811, "Facundo Tello", 760510),
    "WC2026-20260710-SPA-BEL":   (70492, "Michael Oliver", 760511),
    "WC2026-20260711-NOR-ENG":   (64478, "Clement Turpin", 760512),
    "WC2026-20260712-ARG-SWI":   (69045, "Joao Pinheiro", 760513),
    # Semifinals — ESPN match-centre gameIds 760514/760515 (sourced 2026-07-17)
    "WC2026-20260714-FRA-SPA":   (70176, "Ivan Arcides Barton Cisneros", 760514),
    "WC2026-20260715-ENG-ARG":   (68239, "Ismail Elfath", 760515),
}

# 3rd place + final: referee sourced from press (GiveMeSport / FOX Sports
# officials announcements). Final attendance = reported sellout at MetLife's
# FIFA capacity (~80,663, Legion Report); 3P attendance not yet published.
SPECIAL = {
    "WC2026-20260718-FRA-ENG": (None, "Jesus Valenzuela",
        "GiveMeSport officials announcement (VEN crew; VAR Leodan Gonzalez)",
        "https://www.givemesport.com/referee-world-cup-2026-third-place-game-england-france/",
        "Attendance left NULL — no published figure found as of 2026-07-20."),
    "WC2026-20260719-SPA-ARG": (80663, "Slavko Vincic",
        "FOX Sports officials announcement; Legion Report attendance (sellout at FIFA capacity)",
        "https://www.foxsports.com/stories/soccer/world-cup-final-referee-spain-argentina",
        "Attendance is the reported sellout figure (MetLife FIFA capacity), pending FIFA's official match report number."),
}

def main():
    con = sqlite3.connect(DB)
    updated, missing = 0, []
    for mid, (att, ref, gid) in DATA.items():
        if not con.execute("SELECT 1 FROM matches WHERE match_id=?", (mid,)).fetchone():
            missing.append(mid); continue
        con.execute("UPDATE matches SET attendance=?, referee=? WHERE match_id=?", (att, ref, mid))
        con.execute("""INSERT INTO sources_log
            (match_id,table_ref,field,value,claim_type,confidence,source_name,source_url,retrieved_date,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (mid, "matches", "attendance/referee", f"{att}/{ref}", "fact", "high",
             "ESPN official match-centre (Game Information panel)",
             f"https://www.espn.com/soccer/match/_/gameId/{gid}", "2026-07-20",
             "Tournament-complete backfill: descriptive metadata the automated update.py path never collected."))
        updated += 1
    for mid, (att, ref, src, url, note) in SPECIAL.items():
        if not con.execute("SELECT 1 FROM matches WHERE match_id=?", (mid,)).fetchone():
            missing.append(mid); continue
        if att is not None:
            con.execute("UPDATE matches SET attendance=?, referee=? WHERE match_id=?", (att, ref, mid))
        else:
            con.execute("UPDATE matches SET referee=? WHERE match_id=?", (ref, mid))
        con.execute("""INSERT INTO sources_log
            (match_id,table_ref,field,value,claim_type,confidence,source_name,source_url,retrieved_date,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (mid, "matches", "attendance/referee", f"{att}/{ref}", "fact", "medium-high",
             src, url, "2026-07-20", note))
        updated += 1
    con.commit()
    print(f"Updated {updated}/{len(DATA)+len(SPECIAL)} matches.", "Missing:", missing or "none")
    print("Remaining NULL attendance:",
          con.execute("SELECT match_id FROM matches WHERE attendance IS NULL").fetchall())
    print("Remaining NULL referee:",
          con.execute("SELECT COUNT(*) FROM matches WHERE referee IS NULL").fetchone()[0])
    print("integrity:", con.execute("PRAGMA integrity_check").fetchone())
    con.close()

if __name__ == "__main__":
    main()

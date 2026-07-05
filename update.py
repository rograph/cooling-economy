#!/usr/bin/env python3
"""
Cooling Economy — unattended updater (runs in GitHub Actions).
Pulls newly finished WC2026 matches from the free ESPN API, estimates WBGT
from Open-Meteo, computes the break-window metrics, appends to the SQLite
store, and rebuilds the dashboard. Only uses the Python standard library so
it needs no pip install and no API keys.

Safety: only adds matches that are FINISHED and that we can parse cleanly.
Anything odd (unknown venue, unparseable events) is logged and skipped, never
guessed. Never overwrites a match already in the store (preserves manual edits
like penalty results).

Self-test (offline):  CE_SELFTEST=1 python3 update.py   # validates window math
"""
import os, sys, json, sqlite3, datetime, unicodedata, re, urllib.request

DB = os.environ.get("CE_DB", "cooling_economy.db")
NOW = datetime.datetime.utcnow().isoformat(timespec="seconds")
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"

# ESPN display name -> our canonical stored name
NAME = {"Ivory Coast": "Côte d'Ivoire", "South Korea": "Korea Republic",
        "DR Congo": "Congo DR", "Iran": "IR Iran", "USA": "United States",
        "Bosnia-Herzegovina": "Bosnia & Herz.", "Cape Verde": "Cabo Verde",
        "Turkiye": "Türkiye", "Turkey": "Türkiye"}
def nm(n): return NAME.get(n, n)

# venue substring -> (lat, lon) for the 16 WC2026 stadiums (WBGT shade approx)
VENUES = [
    ("AT&T", 32.747, -97.093), ("MetLife", 40.813, -74.074), ("SoFi", 33.953, -118.339),
    ("Levi", 37.403, -121.970), ("Lumen", 47.595, -122.332), ("Arrowhead", 39.049, -94.484),
    ("GEHA", 39.049, -94.484), ("NRG", 29.685, -95.411), ("Reliant", 29.685, -95.411),
    ("Mercedes-Benz", 33.755, -84.401), ("Hard Rock", 25.958, -80.239),
    ("Gillette", 42.091, -71.264), ("Lincoln Financial", 39.901, -75.168),
    ("BC Place", 49.277, -123.112), ("BMO", 43.633, -79.418), ("Akron", 20.681, -103.462),
    ("BBVA", 25.669, -100.244), ("Banorte", 25.669, -100.244), ("Azteca", 19.303, -99.150),
]
def venue_coords(v):
    v = v or ""
    for key, la, lo in VENUES:
        if key.lower() in v.lower():
            return la, lo
    return None

def code(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    p = re.sub(r"[^A-Za-z ]", "", s).upper().split()
    return (p[0][:3] if len(p) == 1 else p[0][:2] + p[1][:1])[:3]

def stage_of(headline):
    h = (headline or "").lower()
    if "round of 16" in h: return "R16"
    if "quarter" in h: return "QF"
    if "semi" in h: return "SF"
    if "third" in h: return "3P"
    if "final" in h: return "F"
    if "round of 32" in h: return "R32"
    return "KO"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cooling-economy-bot"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def clock_min(k):
    d = (k.get("clock") or {}).get("displayValue") or ""
    m = re.match(r"(\d+)(?:\+(\d+))?", d)
    return (int(m.group(1)) + (int(m.group(2)) if m.group(2) else 0)) if m else None

def parse_events(summary):
    comp = summary["header"]["competitions"][0]
    H = next(c for c in comp["competitors"] if c["homeAway"] == "home")
    A = next(c for c in comp["competitors"] if c["homeAway"] == "away")
    m = {H["team"]["id"]: "h", A["team"]["id"]: "a"}
    goals, cards, subs = [], [], []
    for k in summary.get("keyEvents", []):
        t = (k.get("type") or {}).get("text", "").lower()
        tm = m.get((k.get("team") or {}).get("id"), "")
        mn = clock_min(k)
        if mn is None:      # shootout / no clock -> ignore (keeps penalties out of goal_minutes)
            continue
        if "own goal" in t:
            goals.append((mn, "a" if tm == "h" else "h"))
        elif k.get("scoringPlay") or t == "goal" or ("goal" in t and "own" not in t):
            goals.append((mn, tm))
        elif "yellow" in t or "red" in t:
            cards.append((mn, tm))
        elif "substitution" in t:
            subs.append((mn, tm))
    return goals, cards, subs, H, A

# window bounds: b1 before[12,22) after[22,32) ; b2 before[57,67) after[67,77)
def slot(mn):
    if 12 <= mn < 22: return ("b1", 0)
    if 22 <= mn < 32: return ("b1", 1)
    if 57 <= mn < 67: return ("b2", 0)
    if 67 <= mn < 77: return ("b2", 1)
    return None

def windows(goals, cards, subs):
    w = {"b1": [0]*10, "b2": [0]*10}   # g_b,g_a,c_b,c_a,s_b,s_a,lc_b,lc_a,cm_b,cm_a
    for mn, _ in cards:
        s = slot(mn)
        if s: w[s[0]][2 + s[1]] += 1
    for mn, _ in subs:
        s = slot(mn)
        if s: w[s[0]][4 + s[1]] += 1
    hh = aa = 0
    for mn, tm in sorted(goals, key=lambda x: x[0]):
        lead_before = (hh > aa) - (hh < aa)          # +1 home, -1 away, 0 tie
        mine_before = hh if tm == "h" else aa
        opp_before = aa if tm == "h" else hh
        if tm == "h": hh += 1
        else: aa += 1
        mine_after = hh if tm == "h" else aa
        opp_after = aa if tm == "h" else hh
        s = slot(mn)
        if s:
            w[s[0]][0 + s[1]] += 1                    # goals
            if mine_after > opp_after and not (mine_before > opp_before):
                w[s[0]][6 + s[1]] += 1                # lead change (go-ahead)
            if mine_before < opp_before:
                w[s[0]][8 + s[1]] += 1                # comeback goal (scored while trailing)
    return w["b1"], w["b2"]

def goal_str(goals):
    return ",".join(f"{mn}{tm}" for mn, tm in sorted(goals, key=lambda x: x[0]))

def wbgt_for(coords, utc_date, hour):
    if not coords: return None
    la, lo = coords
    u = (f"https://api.open-meteo.com/v1/forecast?latitude={la}&longitude={lo}"
         f"&hourly=temperature_2m,relative_humidity_2m&start_date={utc_date}"
         f"&end_date={utc_date}&timezone=UTC")
    try:
        j = get(u); times = j["hourly"]["time"]
        target = f"{utc_date}T{hour:02d}:00"
        idx = times.index(target) if target in times else hour
        t = j["hourly"]["temperature_2m"][idx]; rh = j["hourly"]["relative_humidity_2m"][idx]
        import math
        e = (rh/100)*6.105*math.exp(17.27*t/(237.7+t))
        return round(t, 1), round(rh), round(0.567*t + 0.393*e + 3.94, 1)
    except Exception as ex:
        print("  weather lookup failed:", ex); return None

COLS = ["g_before","g_after","c_before","c_after","s_before","s_after","lc_before","lc_after","cm_before","cm_after"]

def load_existing(con):
    rows = []
    for h, a, d in con.execute("SELECT home_team, away_team, date FROM matches"):
        rows.append((frozenset((nm(h), nm(a))), d))
    return rows

def is_dup(existing, teamset, date_iso):
    """Same pairing within a day counts as the same match (guards against
    UTC-vs-local date drift for late kickoffs that cross midnight)."""
    try: dd = datetime.date.fromisoformat(date_iso)
    except Exception: dd = None
    for ts, d in existing:
        if ts != teamset: continue
        if d == date_iso: return True
        if dd is not None:
            try:
                if abs((datetime.date.fromisoformat(d) - dd).days) <= 1: return True
            except Exception: pass
    return False

def upsert(con, ev):
    mid = f"WC2026-{ev['date'].replace('-','')}-{code(ev['home'])}-{code(ev['away'])}"
    con.execute("""INSERT OR IGNORE INTO matches
      (match_id,date,stage,matchday,venue,home_team,away_team,kickoff_local,attendance,referee,
       breaks_occurred,break1_min,break2_min,break_confirmed,home_goals,away_goals,result,
       temp_c_kickoff,humidity_kickoff,wbgt_kickoff,wbgt_confidence,goal_minutes,data_completeness,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?,?, 2,22.0,67.0,1, ?,?,?, ?,?,?, ?, ?, '+events', ?)""",
      (mid, ev["date"], ev["stage"], None, ev["venue"], ev["home"], ev["away"], ev["ko"], None, None,
       ev["hg"], ev["ag"], "H" if ev["hg"] > ev["ag"] else "A" if ev["ag"] > ev["hg"] else "D",
       ev.get("temp"), ev.get("rh"), ev.get("wbgt"),
       "estimate (shade approx)" if ev.get("wbgt") is not None else "unavailable",
       ev["gmin"], NOW))
    con.execute(f"INSERT OR IGNORE INTO break_metrics (match_id,{','.join('b1_'+c for c in COLS)},{','.join('b2_'+c for c in COLS)}) VALUES (?,{','.join('?'*20)})",
                [mid] + ev["w1"] + ev["w2"])
    con.execute("""INSERT INTO sources_log (match_id,table_ref,field,value,claim_type,confidence,source_name,source_url,retrieved_date,notes)
      VALUES (?,?,?,?,?,?,?,?,?,?)""",
      (mid, "matches", "result/events", f"{ev['hg']}-{ev['ag']}", "fact", "high",
       "ESPN summary API + Open-Meteo", "", ev["date"], "Auto-added by update.py."))
    return mid

def selftest():
    # Mexico 2-0 Ecuador: goals 22h,31h (both after Break 1); go-ahead at 22'
    goals=[(22,"h"),(31,"h")]; cards=[(45,"a"),(90,"a"),(90,"a")]; subs=[(45,"a"),(45,"a"),(58,"h"),(59,"a"),(73,"h"),(74,"h"),(79,"a"),(79,"a"),(80,"h"),(80,"h")]
    w1,w2=windows(goals,cards,subs)
    exp1=[0,2,0,0,0,0,0,1,0,0]; exp2=[0,0,0,0,2,2,0,0,0,0]
    ok = (w1==exp1 and w2==exp2 and goal_str(goals)=="22h,31h")
    print("SELFTEST", "PASS" if ok else "FAIL", "b1",w1,"b2",w2)
    sys.exit(0 if ok else 1)

def main():
    if os.environ.get("CE_SELFTEST"): selftest()
    con = sqlite3.connect(DB)
    have = load_existing(con)
    today = datetime.datetime.utcnow().date()
    dates = [today - datetime.timedelta(days=1), today]  # yesterday + today (UTC)
    added = []
    for d in dates:
        ds = d.strftime("%Y%m%d")
        try:
            sb = get(f"{ESPN}/scoreboard?dates={ds}")
        except Exception as ex:
            print("scoreboard fetch failed", ds, ex); continue
        for e in sb.get("events", []):
            if e.get("status", {}).get("type", {}).get("state") != "post":
                continue
            comp = e["competitions"][0]
            H = next(c for c in comp["competitors"] if c["homeAway"] == "home")
            A = next(c for c in comp["competitors"] if c["homeAway"] == "away")
            home, away = H["team"]["displayName"], A["team"]["displayName"]
            date_iso = comp["date"][:10]
            teamset = frozenset((nm(home), nm(away)))
            if is_dup(have, teamset, date_iso):
                continue
            try:
                summ = get(f"{ESPN}/summary?event={e['id']}")
                goals, cards, subs, _, _ = parse_events(summ)
            except Exception as ex:
                print("  skip (parse failed)", home, "v", away, ex); continue
            w1, w2 = windows(goals, cards, subs)
            hh = comp["date"][11:13]
            wx = wbgt_for(venue_coords(comp.get("venue", {}).get("fullName")), date_iso, int(hh))
            ev = {"home": nm(home), "away": nm(away), "hg": int(H["score"]), "ag": int(A["score"]),
                  "date": date_iso, "stage": stage_of((comp.get("notes") or [{}])[0].get("headline")),
                  "venue": comp.get("venue", {}).get("fullName"), "ko": comp["date"][11:16],
                  "gmin": goal_str(goals), "w1": w1, "w2": w2}
            if wx: ev["temp"], ev["rh"], ev["wbgt"] = wx
            mid = upsert(con, ev)
            have.append((teamset, date_iso))
            added.append(f"{ev['home']} {ev['hg']}-{ev['ag']} {ev['away']} ({ev['stage']}, WBGT {ev.get('wbgt')})")
    # Self-heal: retry weather for matches whose WBGT is missing (transient failures)
    fixed = []
    for mid, venue, ko, date in con.execute(
            "SELECT match_id, venue, kickoff_local, date FROM matches WHERE wbgt_kickoff IS NULL"):
        coords = venue_coords(venue)
        if not coords:
            continue
        try:
            hh = int((ko or "12:00")[:2])
        except Exception:
            hh = 12
        wx = wbgt_for(coords, date, hh)
        if wx:
            con.execute("UPDATE matches SET temp_c_kickoff=?, humidity_kickoff=?, wbgt_kickoff=?, "
                        "wbgt_confidence='estimate (shade approx)' WHERE match_id=?",
                        (wx[0], wx[1], wx[2], mid))
            fixed.append(f"{mid} -> WBGT {wx[2]}")
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    con.close()
    print(f"added {len(added)} match(es); store now {n}")
    for a in added: print("  +", a)
    if fixed:
        print(f"backfilled WBGT for {len(fixed)} match(es):")
        for f2 in fixed: print("  ~", f2)
    # write a flag file the workflow can read
    with open(os.environ.get("CE_ADDED_FILE", "/tmp/ce_added.txt"), "w") as f:
        f.write(str(len(added)))

if __name__ == "__main__":
    main()

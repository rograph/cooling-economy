#!/usr/bin/env python3
"""
Cooling Economy — Track B: hydration-break ad-revenue model (US / Fox, v2).
TRANSPARENT calculation chain. Every input is an ASSUMPTION or a CITED figure;
swap any value and totals update. Stores low/base/high rows in `broadcast`.
Idempotent: safe to re-run every pipeline cycle (rebuilds all USA rows from
the current `matches` table), same pattern as update.py's Track A step.

Calc chain (per break):
  revenue_per_break = spots_per_break × spot_price[tier][stage_band]
  revenue_per_match  = 2 breaks × revenue_per_break

v1 (2026-06-27/28) priced every match at flat group-stage rates. v2
(2026-07-09) adds a knockout stage premium and swaps three matches from
tiered estimates to REPORTED Nielsen figures, because the group-stage tier
was badly understating actual knockout audiences (e.g. US-Belgium R16 drew
30M vs the 14M "us" tier default).

Cited anchors:
  - Early rounds (group/R32): $200k floor, ~$300k group avg, $750k US
    matches (HITC; Hollywood Reporter; webiano.digital).
  - Knockout rounds (R16+): $300k floor, $1M+ for marquee ties, USMNT deep
    run priced past $2M/spot (Front Office Sports "USMNT World Cup Run
    Could Push Fox Ad Rates Past $2 Million"; Awful Announcing).
  - Final: no 2026 rate has been reported yet — treated as an ASSUMPTION,
    scaled up from the SF band, not a cited figure. Flag when it fires.
  - Reported audiences (Nielsen, via Hollywood Reporter / Sports Media
    Watch): USA 4-1 loss to Belgium (R16, 2026-07-07) 30.0M avg / 36.9M
    peak; Mexico-England (R16, 2026-07-06) 21.74M avg / 25.72M peak;
    USA-Paraguay (group, 2026-06-12) 15.99M (Front Office Sports).
  - Incremental: football has no natural in-play ad stop → ~90% of
    break-ad revenue is INCREMENTAL vs a no-break counterfactual
    (unchanged assumption from v1).

USMNT was eliminated in the R16 loss to Belgium (2026-07-07), so the "us"
pricing tier will not recur for the rest of the tournament — it stays in
the model only because it correctly prices the matches USA already played.
"""
import sqlite3, os, datetime

DB = os.environ.get("CE_DB", "/tmp/cooling_economy.db")
NOW = datetime.datetime.utcnow().isoformat(timespec="seconds")

# ---- ASSUMPTIONS (swap freely) ----
SPOTS = {"low": 3, "base": 4, "high": 5}          # 30s spots per 3-min break
SPOT_LEN = 30
USABLE_BREAK_S = 120                              # ad window inside 180s break
INCREMENTAL = 0.90

MARQUEE = {"Brazil", "Argentina", "Mexico", "England", "Spain", "France", "Germany",
           "Portugal", "Netherlands", "Belgium"}

EARLY = {"group", "R32"}           # priced from the group-stage citations
LATE = {"R16", "QF", "SF"}         # priced from the knockout citations
FINAL = {"F", "3P"}                # 3rd-place treated like a knockout marquee tie

# 30s spot price by tier & scenario (USD). Early band is directly cited.
# Late band is directly cited (range, not per-stage granularity — same price
# used for R16/QF/SF alike since no source breaks it out further). Final
# band is an ASSUMPTION (no 2026 final rate reported yet).
PRICE = {
    "early": {
        "us":      {"low": 400_000, "base": 600_000, "high": 750_000},
        "marquee": {"low": 300_000, "base": 400_000, "high": 550_000},
        "other":   {"low": 200_000, "base": 300_000, "high": 400_000},
    },
    "late": {
        "us":      {"low": 750_000, "base": 1_200_000, "high": 2_000_000},
        "marquee": {"low": 500_000, "base": 750_000, "high": 1_000_000},
        "other":   {"low": 300_000, "base": 450_000, "high": 600_000},
    },
    "final": {  # ASSUMPTION — scaled from "late", not independently sourced
        "us":      {"low": 900_000, "base": 1_500_000, "high": 2_500_000},
        "marquee": {"low": 700_000, "base": 1_000_000, "high": 1_500_000},
        "other":   {"low": 700_000, "base": 1_000_000, "high": 1_500_000},
    },
}

# Tiered audience ESTIMATE (low confidence), used only when we don't have a
# reported Nielsen figure for that specific match. Bumped for knockout
# rounds — the v1 flat tiers were calibrated on group-stage audiences only
# and badly understated actual knockout viewership.
AUD_TIER = {
    "early": {"us": 14_000_000, "marquee": 7_000_000, "other": 4_500_000},
    "late":  {"us": 25_000_000, "marquee": 12_000_000, "other": 8_000_000},
    "final": {"us": 30_000_000, "marquee": 18_000_000, "other": 18_000_000},
}

# REPORTED Nielsen figures for specific matches — overrides the tier
# estimate when present. {match_id: (audience, source_note)}
REPORTED_AUDIENCE = {
    "WC2026-MD1-UNS-PAR": (15_990_000, "Nielsen via Front Office Sports (2026-06-12)"),
    "WC2026-20260706-MEX-ENG": (21_740_000, "Nielsen via Sports Media Watch (2026-07-06, avg; peak 25.72M)"),
    "WC2026-20260707-UNS-BEL": (33_100_000, "Nielsen via Sports Media Watch (final figure; Hollywood Reporter fast-national was 30.0M avg)"),
    "WC2026-20260702-UNS-BOH": (26_400_000, "Nielsen via Sports Media Watch (R32, Fox)"),
    "WC2026-20260711-NOR-ENG": (21_800_000, "Nielsen via Sports Media Watch (QF, Fox)"),
    "WC2026-20260714-FRA-SPA": (11_500_000, "Nielsen via Variety (SF, Fox avg; Yahoo/TAD figure 13.1M)"),
    "WC2026-20260715-ENG-ARG": (15_100_000, "Nielsen via Variety (SF, Fox avg; Yahoo/TAD 16.9M; record Eng-lang SF)"),
}

# Audience ESTIMATE overrides where the flat tier is clearly wrong but no
# Nielsen figure exists yet — still estimates, still labeled as such.
AUD_OVERRIDE = {
    "WC2026-20260718-FRA-ENG": (6_000_000,
        "estimate: 2022 3rd-place drew 2.9M on Fox; scaled ~2x for 2026 uplift (low conf)"),
    "WC2026-20260719-SPA-ARG": (18_000_000,
        "conservative estimate pending Nielsen (2022 final 16.78M Eng-lang; SMW pre-match forecast 35.2M incl. pre-show)"),
}

def tier(home, away):
    if "United States" in (home, away):
        return "us"
    if home in MARQUEE or away in MARQUEE:
        return "marquee"
    return "other"

def stage_band(stage):
    if stage in FINAL:
        return "final"
    if stage in LATE:
        return "late"
    return "early"   # group, R32, or unrecognized -> treat as early (conservative)

def main():
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM broadcast WHERE market='USA'")  # idempotent rebuild
    rows = con.execute("SELECT match_id, home_team, away_team, stage FROM matches ORDER BY rowid").fetchall()
    tot = {"low": 0, "base": 0, "high": 0}
    by_stage = {}
    n_reported = 0
    for mid, home, away, stage in rows:
        tg = tier(home, away)
        band = stage_band(stage)
        price = PRICE[band][tg]
        if mid in REPORTED_AUDIENCE:
            aud, aud_src = REPORTED_AUDIENCE[mid]
            n_reported += 1
        elif mid in AUD_OVERRIDE:
            aud, aud_src = AUD_OVERRIDE[mid]
        else:
            aud, aud_src = AUD_TIER[band][tg], f"tiered estimate ({band}/{tg}, low conf)"
        conf = "medium (sourced pricing)" if band != "final" else "low (assumption, unsourced)"
        if mid in REPORTED_AUDIENCE:
            conf = "medium-high (reported audience)" if band != "final" else "low-medium"
        for sc in ("low", "base", "high"):
            rpb = SPOTS[sc] * price[sc]
            rpm = 2 * rpb
            tot[sc] += rpm
            by_stage.setdefault(stage, {"low": 0, "base": 0, "high": 0})
            by_stage[stage][sc] += rpm
            con.execute("""INSERT OR REPLACE INTO broadcast
               (bc_id,match_id,market,broadcaster,scenario,break_duration_s,est_spots,
                spot_length_s,audience,audience_source,cpm,rate_basis,
                est_revenue_per_break,est_revenue_match,confidence,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (f"{mid}|USA|{sc}", mid, "USA", "Fox", sc, USABLE_BREAK_S, SPOTS[sc],
                SPOT_LEN, aud, aud_src, None, f"spot_price:{band}/{tg}",
                rpb, rpm, conf, NOW))
    con.commit()
    n = len(rows)
    print(f"US/Fox model written for {n} completed matches (low/base/high each); "
          f"{n_reported} use reported Nielsen audience instead of a tier estimate.")
    print("Tournament-to-date hydration-break ad revenue, US/Fox:")
    for sc in ("low", "base", "high"):
        print(f"  {sc:4}: ${tot[sc]/1e6:6.1f}M   (incremental ~${tot[sc]*INCREMENTAL/1e6:.1f}M)")
    print("By stage (base scenario):")
    for st, vals in sorted(by_stage.items()):
        print(f"  {st:6}: ${vals['base']/1e6:6.1f}M")
    # Remaining fixtures = the 104-match template minus what is in the store
    # (zero once the tournament completed on 2026-07-19). Any genuinely
    # remaining fixture is priced at its stage band, marquee tier (ASSUMPTION).
    TEMPLATE = {"group": 72, "R32": 16, "R16": 8, "QF": 4, "SF": 2, "3P": 1, "F": 1}
    played = {st: 0 for st in TEMPLATE}
    for (st,) in con.execute("SELECT stage FROM matches"):
        if st in played:
            played[st] += 1
    remaining_est = {"low": 0, "base": 0, "high": 0}
    n_left = 0
    for st, count in TEMPLATE.items():
        left = max(0, count - played[st])
        n_left += left
        band = stage_band(st)
        for sc in ("low", "base", "high"):
            remaining_est[sc] += left * 2 * SPOTS[sc] * PRICE[band]["marquee"][sc]
    if n_left:
        print(f"Remaining fixtures ({n_left}), assumed marquee tier:")
        for sc in ("low", "base", "high"):
            print(f"  {sc:4}: +${remaining_est[sc]/1e6:6.1f}M")
        print("Projected full 104-match tournament total:")
        for sc in ("low", "base", "high"):
            print(f"  {sc:4}: ${(tot[sc]+remaining_est[sc])/1e6:6.0f}M")
    else:
        print("All 104 fixtures played — totals above are the FINAL tournament figures, not a projection.")
    con.close()

if __name__ == "__main__":
    main()

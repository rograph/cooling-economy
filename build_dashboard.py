#!/usr/bin/env python3
"""
Cooling Economy dashboard builder (tabbed, bilingual EN/ES, light/dark).
Tabs: Home / Analysis / Verdict / Glossary / Survey. Re-run after each match.
Charts via Chart.js CDN; font via Google Fonts.
"""
import sqlite3, os, json, datetime
import track_b_model as tb

DB  = os.environ.get("CE_DB",  "/tmp/cooling_economy.db")
OUT = os.environ.get("CE_OUT", "/tmp/index.html")

con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
rows = con.execute("""
 SELECT m.match_id,m.date,m.stage,m.home_team,m.away_team,m.home_goals,m.away_goals,
        m.venue,m.wbgt_kickoff,m.poss_home,m.poss_away,m.shots_home,m.shots_away,
        m.sot_home,m.sot_away,m.yellow_home,m.yellow_away,m.goal_minutes,m.pen_home,m.pen_away,
        bm.b1_g_before,bm.b1_g_after,bm.b1_c_before,bm.b1_c_after,bm.b1_s_before,bm.b1_s_after,
        bm.b1_lc_before,bm.b1_lc_after,bm.b1_cm_before,bm.b1_cm_after,
        bm.b2_g_before,bm.b2_g_after,bm.b2_c_before,bm.b2_c_after,bm.b2_s_before,bm.b2_s_after,
        bm.b2_lc_before,bm.b2_lc_after,bm.b2_cm_before,bm.b2_cm_after
 FROM matches m JOIN break_metrics bm ON m.match_id=bm.match_id ORDER BY m.rowid""").fetchall()

def brk(r,p):
    return {"g":[r[f"{p}_g_before"],r[f"{p}_g_after"]],"c":[r[f"{p}_c_before"],r[f"{p}_c_after"]],
            "s":[r[f"{p}_s_before"],r[f"{p}_s_after"]],"lc":[r[f"{p}_lc_before"],r[f"{p}_lc_after"]],
            "cm":[r[f"{p}_cm_before"],r[f"{p}_cm_after"]]}

mom={r[0]:[r[1],r[2],r[3],r[4]] for r in con.execute("SELECT match_id,pre1,post1,pre2,post2 FROM momentum_windows")} \
     if con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='momentum_windows'").fetchone() else {}

games=[]
for r in rows:
    g={"id":r["match_id"],"date":r["date"],"home":r["home_team"],"away":r["away_team"],
       "hg":r["home_goals"],"ag":r["away_goals"],"wbgt":r["wbgt_kickoff"],"stage":r["stage"],
       "venue":r["venue"],
       "possH":r["poss_home"],"possA":r["poss_away"],"shots":[r["shots_home"],r["shots_away"]],
       "sot":[r["sot_home"],r["sot_away"]],"cards":[r["yellow_home"],r["yellow_away"]],
       "gmin":r["goal_minutes"] or "","b1":brk(r,"b1"),"b2":brk(r,"b2"),
       "mom":mom.get(r["match_id"]),
       "pen":[r["pen_home"],r["pen_away"]] if r["pen_home"] is not None else None}
    games.append(g)
brows = con.execute("""
 SELECT b.match_id,b.scenario,b.est_revenue_match,b.audience,b.audience_source,b.confidence,
        m.stage,m.home_team,m.away_team,m.date
 FROM broadcast b JOIN matches m ON b.match_id=m.match_id
 WHERE b.market='USA' ORDER BY m.rowid""").fetchall()
bc_by_match = {}
for r in brows:
    e = bc_by_match.setdefault(r["match_id"], {
        "id": r["match_id"], "stage": r["stage"], "home": r["home_team"], "away": r["away_team"],
        "date": r["date"], "tier": tb.tier(r["home_team"], r["away_team"]),
        "rev": {}, "audience": r["audience"], "audSrc": r["audience_source"], "conf": r["confidence"]})
    e["rev"][r["scenario"]] = r["est_revenue_match"]
bgames = list(bc_by_match.values())
bTot = {"low": 0, "base": 0, "high": 0}
byStage, byTier = {}, {}
for g in bgames:
    byStage.setdefault(g["stage"], {"low": 0, "base": 0, "high": 0, "n": 0})
    byTier.setdefault(g["tier"], {"low": 0, "base": 0, "high": 0, "n": 0})
    byStage[g["stage"]]["n"] += 1
    byTier[g["tier"]]["n"] += 1
    for sc in ("low", "base", "high"):
        v = g["rev"].get(sc, 0) or 0
        bTot[sc] += v
        byStage[g["stage"]][sc] += v
        byTier[g["tier"]][sc] += v
bRemaining = {"low": 0, "base": 0, "high": 0}
# Remaining fixtures = 104-match template minus what is already in the store
# (0 across the board once the tournament completed on 2026-07-19).
_TEMPLATE = {"group": 72, "R32": 16, "R16": 8, "QF": 4, "SF": 2, "3P": 1, "F": 1}
for st, cnt in _TEMPLATE.items():
    left = max(0, cnt - byStage.get(st, {}).get("n", 0))
    if not left:
        continue
    band = tb.stage_band(st)
    for sc in ("low", "base", "high"):
        bRemaining[sc] += left * 2 * tb.SPOTS[sc] * tb.PRICE[band]["marquee"][sc]

# Sankey: tier -> stage band -> total, one flow-set per scenario, so the
# calc-chain visual matches whichever scenario the user has toggled to.
bSankey = {}
for sc in ("low", "base", "high"):
    flows = {}
    for g in bgames:
        key = (g["tier"], tb.stage_band(g["stage"]))
        flows[key] = flows.get(key, 0) + (g["rev"].get(sc, 0) or 0)
    bSankey[sc] = [{"tier": t, "band": b, "v": v} for (t, b), v in flows.items() if v]

# Cumulative revenue to date, one point per match date (matches on the same
# date are summed before the running total advances).
bByDate = {}
for g in bgames:
    e = bByDate.setdefault(g["date"], {"low": 0, "base": 0, "high": 0})
    for sc in ("low", "base", "high"):
        e[sc] += g["rev"].get(sc, 0) or 0
run = {"low": 0, "base": 0, "high": 0}
bCumulative = []
for d in sorted(bByDate.keys()):
    for sc in ("low", "base", "high"):
        run[sc] += bByDate[d][sc]
    bCumulative.append({"date": d, "low": run["low"], "base": run["base"], "high": run["high"]})

BROADCAST = {"games": bgames, "total": bTot, "byStage": byStage, "byTier": byTier,
             "remaining": bRemaining, "incremental": tb.INCREMENTAL,
             "sankey": bSankey, "cumulative": bCumulative}
con.close()

BASE={"2018":{"buckets":[3,5,5,6,6,1,8,7,3,9,10,7,6,5,10,5,1,9,16],"w":[10,8,13,14],"tot":122},
      "2022":{"buckets":[3,4,2,2,4,6,8,5,6,13,7,4,9,10,8,3,9,6,11],"w":[4,11,14,17],"tot":120}}
XGWIN={"goals":[44,30],"xg":[35.89,24.42],"shots":[342,219],"n":64}
MOMAGG={"n":54,"swing":15.7,"flip":26,"ontop":[19,5],"gainer":[9,15],"postgoals":24}
# Substitution timing (FBref). buckets = subs per 5-min slice. b1/b2 = subs in the
# Break-1 (22-25') and Break-2 (67-70') windows. 2022 = no-break baseline (same 5-sub rule).
SUBAGG={"y2026":{"buckets":[0,0,2,1,0,1,1,4,2,78,10,72,70,66,105,86,107,55,35],"b1":0,"b2":43,"tot":695,"n":76},
        "y2022":{"buckets":[0,0,1,0,1,0,1,2,2,42,2,38,42,59,63,64,43,43,27],"b1":0,"b2":35,"tot":430,"n":48}}
# Welfare (ESPN commentary: treatment stoppages + injury subs, broadcast-counted).
WELFARE={"n":76,"total":191,"perMatch":2.5,"latePct":36,
         "hot":{"n":26,"ev":1.9,"late":0.77},"cool":{"n":50,"ev":2.8,"late":0.98},
         "buckets":[5,1,10,6,9,3,5,14,9,13,7,17,15,8,8,9,18,14,20]}
N=len(games)
DATA={"updated":datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),"n":N,
      "games":games,"base":BASE,"xgwin":XGWIN,"momagg":MOMAGG,"subagg":SUBAGG,"welfare":WELFARE,"broadcast":BROADCAST}

HTML=r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cooling Economy · Do World Cup hydration breaks change the game?</title>
<meta name="description" content="A data-science look at every 2026 FIFA World Cup match: do the mandatory hydration breaks actually change goals, momentum, substitutions and player welfare? Interactive, bilingual, updated per match.">
<meta name="author" content="Rodolfo López">
<meta name="theme-color" content="#0a1330">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Cooling Economy">
<meta property="og:title" content="Cooling Economy: do World Cup hydration breaks change the game?">
<meta property="og:description" content="Every 2026 World Cup match, tested: do the mandatory water breaks change goals, momentum and player welfare? Interactive dashboard, updated per match.">
<meta property="og:image" content="__OGIMAGE__">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:url" content="__BASEURL__">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Cooling Economy: do World Cup hydration breaks change the game?">
<meta name="twitter:description" content="Every 2026 World Cup match, tested: do the mandatory water breaks change the game? Interactive, bilingual, updated per match.">
<meta name="twitter:image" content="__OGIMAGE__">
<link rel="icon" href="__FAVICON__">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"WebSite","name":"Cooling Economy","author":{"@type":"Person","name":"Rodolfo López"},"description":"A data-science analysis of whether 2026 FIFA World Cup hydration breaks change match dynamics.","url":"__BASEURL__"}</script>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800;900&family=Saira+Condensed:wght@600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root{--navy:#0a1f44;--gold:#f6c945;--green:#23d18b;--red:#ff4d6d;--violet:#9b6cff;
--c1:#f6c945;--c2:#2fe0d8;--c3:#ff2e74;--grad:linear-gradient(100deg,#f6c945,#ff2e74 52%,#2fe0d8);
--bg:#f4f6fb;--card:#ffffff;--ink:#0c1430;--muted:#5b6b8c;--line:#e7ecf4;--soft:#f5f8ff;--glow:none;}
body.dark{--bg:#070c1a;--card:#111a33;--ink:#eef3ff;--muted:#95a6cc;--line:#26324f;--soft:#0c1530;--glow:0 0 0 1px rgba(255,255,255,.03),0 12px 40px rgba(0,0,0,.45);}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Archivo','Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--ink);-webkit-font-smoothing:antialiased;transition:background .2s,color .2s;position:relative}
body.dark::before{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;background:radial-gradient(60% 40% at 15% 0%,rgba(246,201,69,.10),transparent 60%),radial-gradient(55% 45% at 100% 10%,rgba(255,46,116,.10),transparent 60%),radial-gradient(60% 50% at 50% 110%,rgba(47,224,216,.08),transparent 60%)}
.wrap,.topbar{position:relative;z-index:1}
h1,h2,h3,.disp{font-weight:900;letter-spacing:-.02em;line-height:1.05}
.disp-f{font-family:'Saira Condensed','Archivo',sans-serif}
.muted{color:var(--muted)}
.topbar{background:var(--navy);color:#fff;position:sticky;top:0;z-index:30}
.tbinner{max-width:1080px;margin:0 auto;padding:0 18px;display:flex;align-items:center;gap:14px;height:60px}
.logo{display:flex;align-items:center;gap:10px;font-family:'Saira Condensed','Archivo',sans-serif;font-weight:800;font-size:19px;letter-spacing:.02em;white-space:nowrap;text-transform:uppercase}
.logo .chip{background:var(--gold);color:var(--navy);border-radius:6px;padding:3px 8px;font-size:11px;font-weight:900;letter-spacing:.04em}
.nav{display:flex;gap:2px;margin-left:auto;flex-wrap:wrap}
.nav button{background:transparent;border:none;color:#b8c6e2;font-family:inherit;font-weight:700;font-size:13.5px;padding:8px 12px;border-radius:8px;cursor:pointer}
.nav button:hover{color:#fff}.nav button.on{background:rgba(255,255,255,.12);color:#fff}
.tg{display:flex;gap:6px;margin-left:10px}
.tg button{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);color:#fff;font-family:inherit;font-weight:800;font-size:12px;width:34px;height:32px;border-radius:8px;cursor:pointer}
.tg button.lang{width:auto;padding:0 10px}
.menu{display:flex;flex:1;align-items:center}
.navtoggle{display:none;margin-left:auto;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);color:#fff;font-size:20px;width:42px;height:38px;border-radius:9px;cursor:pointer;align-items:center;justify-content:center}
@media(max-width:760px){
 .tbinner{gap:8px;padding:0 14px;height:56px}
 .logo{font-size:16px}
 .navtoggle{display:inline-flex}
 .menu{position:absolute;top:100%;left:0;right:0;flex:none;flex-direction:column;align-items:stretch;background:var(--navy);border-top:1px solid rgba(255,255,255,.12);box-shadow:0 14px 34px rgba(0,0,0,.45);padding:6px 0 12px;display:none;z-index:40}
 body.dark .menu{background:#0d1530}
 .menu.open{display:flex}
 .nav{flex-direction:column;flex-wrap:nowrap;margin:0;width:100%;gap:0}
 .nav button{width:100%;text-align:left;padding:14px 20px;font-size:16px;border-radius:0}
 .nav button.on{background:rgba(255,255,255,.14)}
 .tg{margin:10px 20px 2px;gap:8px}
 .tg button{height:40px;min-width:48px;width:auto;font-size:14px;flex:1;max-width:80px}
}
.wrap{max-width:1080px;margin:0 auto;padding:24px 18px 60px}
.tab{display:none}.tab.on{display:block;animation:f .25s ease}
.prose{color:var(--ink);font-size:15px;line-height:1.62;max-width:760px}
.prose h4{font-size:15px;font-weight:800;color:var(--navy);margin:18px 0 5px}
body.dark .prose h4{color:var(--gold)}
.prose p{margin:0 0 10px}.prose b{font-weight:800}
@keyframes f{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px;box-shadow:0 4px 18px rgba(16,26,48,.05);margin-bottom:18px}
.eyebrow{font-size:12px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--gold)}
.h-title{font-family:'Saira Condensed','Archivo',sans-serif;font-size:39px;font-weight:800;letter-spacing:0;line-height:1.02;margin:8px 0 6px;color:var(--ink);text-transform:uppercase}
.lead{font-size:16px;line-height:1.6;color:var(--muted);max-width:680px}
.kgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}
@media(max-width:760px){.kgrid{grid-template-columns:repeat(2,1fr)}}
.kpi{position:relative;overflow:hidden;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:17px 16px 15px;box-shadow:0 2px 10px rgba(16,26,48,.06)}
.kpi::before{content:"";position:absolute;left:0;top:0;width:100%;height:4px;background:var(--grad)}
body.dark .kpi{box-shadow:var(--glow)}
.kpi .v{font-family:'Saira Condensed','Archivo',sans-serif;font-size:33px;font-weight:800;color:var(--ink);line-height:1}
.kpi .l{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-top:6px;font-weight:700}
.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}@media(max-width:820px){.two{grid-template-columns:1fr}}
.sect-h{font-size:18px;font-weight:800;margin-bottom:3px;color:var(--ink)}
.sect-s{font-size:12.5px;color:var(--muted);margin-bottom:14px}
.controls{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end;margin-bottom:18px}
.ctl label{display:block;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:5px}
select{font-family:inherit;background:var(--card);border:1.5px solid var(--line);border-radius:10px;padding:10px 12px;font-size:14px;font-weight:600;color:var(--ink);min-width:230px}
.seg{display:inline-flex;background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:3px}
.seg button{font-family:inherit;background:transparent;border:none;color:var(--muted);font-weight:800;font-size:13px;padding:7px 13px;border-radius:8px;cursor:pointer}
.seg button.on{background:var(--card);color:var(--ink);box-shadow:0 1px 4px rgba(0,0,0,.12)}
.breaks{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:640px){.breaks{grid-template-columns:1fr}}
.bcard{border:1px solid var(--line);border-radius:13px;padding:15px;background:var(--soft)}
.bhead{font-weight:900;color:var(--ink);font-size:15px}.bsub{font-size:11px;color:var(--muted);margin-bottom:9px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:right;padding:6px 4px;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left;font-weight:600;color:var(--ink)}
th{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.delta{font-weight:900}.delta.dn{color:var(--red)}.delta.up{color:var(--green)}.delta.fl{color:var(--muted)}
.pill{display:inline-block;font-weight:800;font-size:10.5px;padding:2px 9px;border-radius:20px;margin-left:6px}
.pill.s{background:#e2f4ea;color:var(--green)}.pill.ns{background:var(--soft);color:var(--muted)}.pill.mid{background:#fbedd2;color:#9a6b12}
.chartbox{position:relative;height:320px;margin-top:12px}.chartbox.sm{height:270px}
.pitchWrap{margin-top:10px}.pitchWrap svg{width:100%;height:auto;display:block;max-height:340px}
.pitchprompt{background:linear-gradient(180deg,#1f9d57,#16834a);border-radius:13px;padding:44px 26px;text-align:center;color:#fff;font-weight:700;font-size:15.5px;line-height:1.55}
.note{font-size:12px;color:var(--muted);line-height:1.6;margin-top:11px;padding-top:11px;border-top:1px dashed var(--line)}
.readbox{background:var(--soft);border:1px solid var(--line);border-left:4px solid var(--gold);border-radius:10px;padding:14px 18px;font-size:14px;line-height:1.65;color:var(--ink)}
.banner{background:var(--soft);border:1px solid var(--line);border-radius:12px;padding:12px 15px;font-size:12.5px;color:var(--muted);line-height:1.55}
.how{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:6px}@media(max-width:760px){.how{grid-template-columns:1fr}}
.howc{border:1px solid var(--line);border-radius:13px;padding:15px;background:var(--card)}
.howc .n{width:30px;height:30px;border-radius:8px;background:var(--navy);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:900;margin-bottom:9px}
.howc h4{font-size:15px;color:var(--ink);margin-bottom:4px}.howc p{font-size:12.5px;color:var(--muted);line-height:1.5}
.verdict{background:var(--navy);color:#fff;border-radius:14px;padding:18px 20px;margin:18px 0;border-left:6px solid var(--gold)}
.verdict .vlabel{font-size:11px;font-weight:800;letter-spacing:.13em;text-transform:uppercase;color:var(--gold)}
.verdict .vbig{font-family:'Saira Condensed','Archivo',sans-serif;font-size:25px;font-weight:800;margin:5px 0 7px;line-height:1.05}.verdict p{font-size:13.5px;line-height:1.6;color:#d7e0f2}
.vtext{font-size:13.5px;line-height:1.7;color:var(--ink)}
.vtest{display:flex;align-items:center;gap:14px;padding:13px 2px;border-bottom:1px solid var(--line)}
.vtest:last-child{border-bottom:none}.vtest .vname{font-weight:700;color:var(--ink);font-size:14px;flex:1}
.vtest .vnum{font-size:12.5px;color:var(--muted);font-weight:500;margin-top:2px}
.vstat{font-weight:800;font-size:11px;padding:3px 11px;border-radius:20px;white-space:nowrap}
.vstat.ok{background:#e2f4ea;color:var(--green)}.vstat.no{background:var(--soft);color:var(--muted);border:1px solid var(--line)}.vstat.mid{background:#fbedd2;color:#9a6b12}
.hero-svg{width:100%;height:auto;display:block;margin:14px 0 4px}
.detailbtn{font-family:inherit;background:transparent;border:1.5px solid var(--line);color:var(--ink);font-weight:700;font-size:13.5px;padding:11px 16px;border-radius:10px;cursor:pointer;width:100%;text-align:left}
.detailbtn:hover{border-color:var(--gold)}
.gloss{border-bottom:1px solid var(--line);padding:14px 2px}.gloss:last-child{border-bottom:none}
.gloss .gt{font-weight:800;color:var(--ink);font-size:15px}.gloss .gd{font-size:13px;color:var(--muted);line-height:1.6;margin-top:4px}
.q{margin-bottom:15px}.q .qt{font-weight:800;font-size:14px;color:var(--ink);margin-bottom:7px}
.opts{display:flex;gap:8px;flex-wrap:wrap}
.opts button{font-family:inherit;background:var(--soft);border:1.5px solid var(--line);border-radius:22px;padding:7px 14px;font-size:13px;cursor:pointer;color:var(--ink);font-weight:600}
.opts button.sel{background:var(--green);color:#fff;border-color:var(--green)}
textarea{width:100%;border:1.5px solid var(--line);border-radius:10px;padding:10px;font-family:inherit;font-size:13px;resize:vertical;background:var(--card);color:var(--ink)}
.btn{font-family:inherit;background:var(--navy);color:#fff;border:none;border-radius:10px;padding:11px 18px;font-weight:800;font-size:14px;cursor:pointer}
.btn.gold{background:var(--gold);color:var(--navy)}
.tally{font-size:12px;color:var(--muted);font-weight:600}
.foot{font-size:11px;color:var(--muted);line-height:1.6;margin-top:8px}
.subbar{background:var(--navy);color:#9fb6da;font-size:11px;font-weight:600;padding:5px 20px;text-align:center;border-top:1px solid rgba(255,255,255,.08)}
.bracket{display:flex;gap:14px;overflow-x:auto;padding-bottom:8px}
.bround{min-width:172px;flex:1}
.bround h4{font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:10px;text-align:center;font-weight:800}
.bmatch{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:9px 11px;margin-bottom:10px}
.bmatch .r{display:flex;justify-content:space-between;gap:8px;font-size:13px;padding:2px 0}
.bmatch .r.w{font-weight:800;color:var(--ink)}.bmatch .r.l{color:var(--muted)}
.bempty{border:1px dashed var(--line);border-radius:10px;padding:12px 8px;font-size:12px;color:var(--muted);text-align:center;margin-bottom:10px}
.up{border-left:3px solid var(--gold);padding:4px 0 4px 14px;margin-bottom:16px}
.up .ud{font-size:11.5px;font-weight:800;color:var(--gold);letter-spacing:.04em}
.up .ut{font-size:14px;font-weight:800;color:var(--ink);margin:2px 0 2px}.up .up2{font-size:13px;color:var(--muted);line-height:1.55}
/* FC vibe */
body.dark .card{box-shadow:var(--glow);border-color:#223052}
body.dark .topbar{background:linear-gradient(100deg,#0a1330,#10183a)}
.gradtext{background:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent}
.reveal{opacity:0;transform:translateY(22px);transition:opacity .55s ease,transform .55s ease}
.reveal.in{opacity:1;transform:none}
@media(prefers-reduced-motion:reduce){.reveal{opacity:1;transform:none;transition:none}}
.hero{position:relative;overflow:hidden;border:1px solid var(--line);border-radius:20px;padding:30px 24px;background:var(--card)}
body.dark .hero{box-shadow:var(--glow);border-color:#26345c;background:linear-gradient(160deg,#101a38,#0c1430)}
.hero::after{content:"";position:absolute;right:-60px;top:-60px;width:240px;height:240px;border-radius:50%;background:var(--grad);filter:blur(60px);opacity:.20;pointer-events:none}
.hero-q{font-family:'Saira Condensed','Archivo',sans-serif;font-weight:800;text-transform:uppercase;letter-spacing:-.01em;line-height:.98;font-size:clamp(34px,8vw,62px)}
.heatlegend{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.heatlegend .hl{display:flex;align-items:center;gap:7px;font-size:13px;font-weight:700;color:var(--ink);background:var(--soft);border:1px solid var(--line);border-radius:20px;padding:6px 12px}
.heatlegend .dot{width:11px;height:11px;border-radius:50%}
.scopebanner{display:block;font-size:13px;font-weight:600;line-height:1.5;color:var(--ink);background:var(--soft);border:1px solid var(--line);border-left:4px solid var(--c2);border-radius:0 10px 10px 0;padding:10px 13px;margin-bottom:11px}
.badge{display:inline-flex;align-items:center;gap:4px;font-weight:800;font-size:10px;padding:2px 8px;border-radius:20px;text-transform:uppercase;letter-spacing:.04em;white-space:nowrap;vertical-align:middle}
.badge .dot{width:6px;height:6px;border-radius:50%;background:currentColor;flex:none}
.badge.fact{background:#e2f4ea;color:var(--green)}
.badge.estimate{background:#fbedd2;color:#9a6b12}
.badge.assumption{background:#fde2e2;color:var(--red)}
.matchgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(126px,1fr));gap:8px;margin-top:10px}
.mcard{border:1px solid var(--line);border-radius:10px;padding:7px;background:var(--soft);cursor:pointer;transition:transform .12s,box-shadow .12s}
.mcard:hover{transform:translateY(-2px);box-shadow:0 6px 16px rgba(16,26,48,.14)}
.mcard .mt{font-size:10px;font-weight:800;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:4px}
.mcard svg{width:100%;height:auto;display:block;border-radius:6px}
.venuegrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:10px;margin-top:10px}
.vtile{border-radius:12px;padding:13px;color:#fff;position:relative}
.vtile .vn{font-size:12px;font-weight:800;line-height:1.25;margin-bottom:8px;min-height:30px}
.vtile .vw{font-family:'Saira Condensed','Archivo',sans-serif;font-size:23px;font-weight:800}
.vtile .vc{font-size:10.5px;opacity:.9;font-weight:700;text-transform:uppercase;letter-spacing:.04em;margin-top:2px}
.simgrid{display:grid;grid-template-columns:1.1fr 1fr;gap:20px;margin-top:14px;align-items:center}@media(max-width:640px){.simgrid{grid-template-columns:1fr}}
.simrow{margin-bottom:16px}
.simrow label{display:flex;justify-content:space-between;font-size:12.5px;font-weight:700;color:var(--ink);margin-bottom:6px}
.simrow label span:last-child{color:var(--gold);font-weight:800}
.simrow input[type=range]{width:100%;accent-color:var(--gold)}
.simout{background:var(--navy);color:#fff;border-radius:14px;padding:22px 20px;text-align:center}
.simout .v{font-family:'Saira Condensed','Archivo',sans-serif;font-size:36px;font-weight:800;color:var(--gold)}
.simout .l{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#b8c6e2;margin-top:4px}
.simout .n{font-size:11.5px;color:#c3cfe6;margin-top:10px;line-height:1.5}
.sankeywrap svg{width:100%;height:auto;display:block}
.heroball{filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))}
@keyframes heropulse{0%{opacity:.6;transform:scale(1)}70%{opacity:0;transform:scale(2.1)}100%{opacity:0;transform:scale(2.1)}}
.pulsering{animation:heropulse 2.6s ease-out infinite;transform-origin:center;transform-box:fill-box}
</style></head><body>
<div class="topbar"><div class="tbinner">
  <div class="logo"><span class="chip">FIFA 26</span>⚽ Cooling Economy</div>
  <button id="navToggle" class="navtoggle" aria-label="Menu" aria-expanded="false">☰</button>
  <div class="menu" id="menu">
   <div class="nav" id="nav">
    <button data-t="home" class="on" data-i18n="nav_home"></button>
    <button data-t="analysis" data-i18n="nav_analysis"></button>
    <button data-t="verdict" data-i18n="nav_verdict"></button>
    <button data-t="broadcast" data-i18n="nav_broadcast"></button>
    <button data-t="bracket" data-i18n="nav_bracket"></button>
    <button data-t="glossary" data-i18n="nav_glossary"></button>
    <button data-t="survey" data-i18n="nav_survey"></button>
    <button data-t="updates" data-i18n="nav_updates"></button>
    <button data-t="about" data-i18n="nav_about"></button>
   </div>
   <div class="tg"><button id="unitBtn" title="units">°F</button><button id="themeBtn" title="theme">☾</button><button id="langBtn" class="lang">ES</button></div>
  </div>
</div>
<div class="subbar"><span id="subUpdated"></span></div>
</div>
<div class="wrap">

 <div class="tab on" id="tab-home">
  <div class="hero">
   <div class="eyebrow" data-i18n="home_eyebrow"></div>
   <div class="hero-q gradtext" data-i18n="home_title"></div>
   <p class="lead" data-i18n="home_lead"></p>
   <div id="heroArt"></div>
  </div>
  <div class="card">
   <div class="verdict" id="homeVerdict"></div>
   <div class="kgrid" id="homeKpis"></div>
   <div class="readbox" id="homeFinding"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="home_howtitle"></div>
   <div class="how">
    <div class="howc"><div class="n">1</div><h4 data-i18n="how1_h"></h4><p data-i18n="how1_p"></p></div>
    <div class="howc"><div class="n">2</div><h4 data-i18n="how2_h"></h4><p data-i18n="how2_p"></p></div>
   </div>
   <div class="banner" style="margin-top:16px" data-i18n="home_banner"></div>
   <div class="foot" data-i18n="home_foot"></div>
   <div class="foot" style="margin-top:6px">Built by Rodolfo López · <a href="__LINKEDIN__" target="_blank" rel="noopener" style="color:var(--gold);font-weight:800;text-decoration:none">LinkedIn ↗</a></div>
  </div>
 </div>

 <div class="tab" id="tab-analysis">
  <div class="card">
   <div class="controls">
    <div class="ctl"><label data-i18n="lbl_match"></label><select id="selMatch"></select></div>
    <div class="ctl"><label data-i18n="lbl_stage"></label><select id="selStage"></select></div>
    <div class="ctl"><label data-i18n="lbl_heat"></label><div class="seg" id="segHeat"><button data-h="all" class="on" data-i18n="h_all"></button><button data-h="hot" data-i18n="h_hot"></button><button data-h="cool" data-i18n="h_cool"></button></div></div>
   </div>
   <div class="readbox" id="readbox"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="an_heat_h"></div><div class="sect-s" data-i18n="an_heat_s"></div>
   <div id="heatPitch"></div>
   <div class="heatlegend" id="heatLegend"></div>
   <div class="note" id="heatNote"></div>
  </div>
  <div class="card">
   <div class="sect-h"><span data-i18n="an_breaks_h"></span> <span id="scopeLbl" class="pill ns"></span></div>
   <div class="sect-s" data-i18n="an_breaks_s"></div>
   <div class="breaks" id="breaks"></div>
   <div class="note" id="breaksRecon"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="an_poss_h"></div><div class="sect-s" data-i18n="an_poss_s"></div>
   <div class="pitchWrap" id="pitchWrap"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="an_dist_h"></div><div class="sect-s" data-i18n="an_dist_s"></div>
   <div id="goalStrip" style="display:none"></div>
   <div class="chartbox"><canvas id="cDist"></canvas></div><div class="note" id="distNote"></div>
  </div>
  <button id="moreBtn" class="detailbtn" style="margin-bottom:18px"></button>
  <div id="moreWrap" style="display:none">
  <div class="card">
   <div class="sect-h" data-i18n="an_hist_h"></div><div class="sect-s" data-i18n="an_hist_s"></div>
   <div class="chartbox"><canvas id="cHist"></canvas></div><div class="note" id="histVerdict"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="an_xg_h"></div><div class="sect-s" data-i18n="an_xg_s"></div>
   <div class="chartbox sm"><canvas id="cXg"></canvas></div><div class="note" id="xgNote"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="an_mom_h"></div><div class="sect-s" data-i18n="an_mom_s"></div>
   <div class="kgrid" id="momKpis" style="grid-template-columns:repeat(3,1fr)"></div>
   <div id="momTug" style="display:none"></div>
   <div class="chartbox sm" id="momChartBox"><canvas id="cMom"></canvas></div><div class="note" id="momNote"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="an_subs_h"></div><div class="sect-s" data-i18n="an_subs_s"></div>
   <div class="chartbox"><canvas id="cSub"></canvas></div><div class="note" id="subNote"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="an_wel_h"></div><div class="sect-s" data-i18n="an_wel_s"></div>
   <div class="kgrid" id="welKpis" style="grid-template-columns:repeat(3,1fr)"></div>
   <div class="chartbox sm"><canvas id="cWel"></canvas></div><div class="note" id="welNote"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="an_heat2_h"></div><div class="sect-s" data-i18n="an_heat2_s"></div>
   <div class="chartbox"><canvas id="cHeatScatter"></canvas></div>
   <div class="heatlegend" id="heatScatterLegend"></div>
   <div class="note" id="heatScatterNote"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="an_grid_h"></div><div class="sect-s" data-i18n="an_grid_s"></div>
   <div class="matchgrid" id="matchGrid"></div>
   <div class="note" data-i18n="an_grid_note"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="an_venue_h"></div><div class="sect-s" data-i18n="an_venue_s"></div>
   <div class="venuegrid" id="venueGrid"></div>
   <div class="note" id="venueNote"></div>
  </div>
  </div>
 </div>

 <div class="tab" id="tab-verdict">
  <div class="card">
   <div class="eyebrow" id="vEyebrow"></div>
   <div class="h-title" id="vAnswer"></div>
   <div id="vMeter"></div>
   <p class="lead" id="vLead"></p>
   <button class="btn" id="shareBtn" style="margin-top:8px"></button>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="v_tests_h"></div><div class="sect-s" data-i18n="v_tests_s"></div>
   <div id="vTests"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="v_track_h"></div><div class="sect-s" data-i18n="v_track_s"></div>
   <div class="chartbox"><canvas id="cTrack"></canvas></div>
   <div class="note" id="trackNote"></div>
  </div>
  <div class="card two">
   <div><div class="sect-h" data-i18n="v_trend_h"></div><p class="vtext" id="vTrend"></p></div>
   <div><div class="sect-h" data-i18n="v_next_h"></div><p class="vtext" id="vNext"></p></div>
  </div>
 </div>

 <div class="tab" id="tab-broadcast">
  <div class="card">
   <div class="sect-h" data-i18n="bc_title"></div><div class="sect-s" data-i18n="bc_sub"></div>
   <div class="seg" id="segScenario">
    <button data-sc="low" data-i18n="sc_low"></button>
    <button data-sc="base" class="on" data-i18n="sc_base"></button>
    <button data-sc="high" data-i18n="sc_high"></button>
   </div>
   <div class="kgrid" id="bcKpis" style="margin-top:14px"></div>
   <div class="banner" id="bcBanner" style="margin-top:12px"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="bc_stage_h"></div><div class="sect-s" data-i18n="bc_stage_s"></div>
   <div class="chartbox sm"><canvas id="cBcStage"></canvas></div>
   <div class="note" id="bcStageNote"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="bc_tier_h"></div><div class="sect-s" data-i18n="bc_tier_s"></div>
   <div id="bcTierTable"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="bc_scatter_h"></div><div class="sect-s" data-i18n="bc_scatter_s"></div>
   <div class="chartbox"><canvas id="cBcScatter"></canvas></div>
   <div class="heatlegend" id="bcScatterLegend"></div>
   <div class="note" id="bcScatterNote"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="bc_proj_h"></div><div class="sect-s" data-i18n="bc_proj_s"></div>
   <div class="kgrid" id="bcProjKpis" style="grid-template-columns:repeat(3,1fr)"></div>
   <div class="note" data-i18n="bc_caveat"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="bc_sankey_h"></div><div class="sect-s" data-i18n="bc_sankey_s"></div>
   <div class="sankeywrap" id="bcSankey"></div>
   <div class="note" id="bcSankeyNote"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="bc_cum_h"></div><div class="sect-s" data-i18n="bc_cum_s"></div>
   <div class="chartbox sm"><canvas id="cBcCum"></canvas></div>
   <div class="note" data-i18n="bc_cum_note"></div>
  </div>
  <div class="card">
   <div class="sect-h" data-i18n="bc_sim_h"></div><div class="sect-s" data-i18n="bc_sim_s"></div>
   <div class="simgrid">
    <div>
     <div class="simrow"><label><span data-i18n="sim_spots"></span><span id="simSpotsV"></span></label><input type="range" id="simSpots" min="1" max="8" value="4" step="1"></div>
     <div class="simrow"><label><span data-i18n="sim_cpm"></span><span id="simCpmV"></span></label><input type="range" id="simCpm" min="100000" max="2500000" value="750000" step="25000"></div>
     <div class="simrow"><label><span data-i18n="sim_aud"></span><span id="simAudV"></span></label><input type="range" id="simAud" min="1000000" max="35000000" value="12000000" step="500000"></div>
    </div>
    <div class="simout">
     <div class="v" id="simOut"></div>
     <div class="l" data-i18n="sim_outl"></div>
     <div class="n" data-i18n="sim_note"></div>
    </div>
   </div>
  </div>
 </div>

 <div class="tab" id="tab-bracket">
  <div class="card">
   <div class="sect-h" data-i18n="br_title"></div><div class="sect-s" data-i18n="br_sub"></div>
   <div class="bracket" id="bracketWrap"></div>
  </div>
 </div>

 <div class="tab" id="tab-updates">
  <div class="card">
   <div class="sect-h" data-i18n="up_title"></div><div class="sect-s" data-i18n="up_sub"></div>
   <div id="updatesList"></div>
  </div>
 </div>

 <div class="tab" id="tab-glossary">
  <div class="card">
   <div class="sect-h" data-i18n="gl_title"></div><div class="sect-s" data-i18n="gl_sub"></div>
   <div id="glossList"></div>
  </div>
 </div>

 <div class="tab" id="tab-about">
  <div class="card">
   <div class="sect-h" data-i18n="about_title"></div><div class="sect-s" data-i18n="about_sub"></div>
   <div class="prose" id="aboutBody" data-i18n="about_body"></div>
   <div class="foot" style="margin-top:14px">Built by Rodolfo López · <a href="__LINKEDIN__" target="_blank" rel="noopener" style="color:var(--gold);font-weight:800;text-decoration:none">LinkedIn ↗</a> · <a href="https://rodolfo.app" target="_blank" rel="noopener" style="color:var(--gold);font-weight:800;text-decoration:none">rodolfo.app ↗</a></div>
  </div>
 </div>

 <div class="tab" id="tab-survey">
  <div class="card">
   <div class="sect-h" data-i18n="sv_title"></div><div class="sect-s" data-i18n="sv_sub"></div>
   <div id="survey"></div>
   <div style="display:flex;gap:10px;align-items:center;margin-top:8px;flex-wrap:wrap">
    <button class="btn" id="submitSurvey" data-i18n="sv_submit"></button>
    <span class="tally" id="tally"></span>
   </div>
   <div class="chartbox sm" id="surveyChartBox" style="display:none;margin-top:14px"><canvas id="cSurvey"></canvas></div>
   <div id="perception"></div>
   <div class="note" data-i18n="sv_note"></div>
  </div>
 </div>

</div>
<script>
const D=__DATA__; const G=D.games;
const $=id=>document.getElementById(id);
const RED='#c0392b',GREEN='#15924a',GREY='#94a3b8',GOLD='#e7b53c',NAVY='#0a1f44',VIOLET='#6c4bd1';
let state={tab:'home',sel:'all',heat:'all',stage:'all',lang:'en',theme:'light',unit:'c',more:false,scenario:'base'};
function toF(c){return c*9/5+32;}
function tU(c,dec){dec=(dec==null?0:dec);c=Number(c);return state.unit==='f'?(toF(c).toFixed(dec)+'°F'):(c.toFixed(dec)+'°C');}
let made={analysis:false};
let distChart,histChart,xgChart,momChart,subChart,welChart,heatScatter,surveyChart,trackChart,bcStageChart,bcScatter,bcCumChart;
const U=D.updated;

// ---------- i18n ----------
const TR={
 en:{
  nav_home:'Home',nav_analysis:'Analysis',nav_verdict:'Verdict',nav_glossary:'Glossary',nav_survey:'Survey',
  home_eyebrow:'FIFA World Cup 2026 · Hydration breaks · Final report',
  home_title:'Do the hydration breaks<br>change the game?',
  home_lead:'Every 2026 World Cup match paused for a <b>mandatory three-minute hydration break</b> near the 22nd and 67th minute. This project tracked what happened to the football in the ten minutes on either side of those pauses across all 104 matches — Spain lifted the trophy on July 19 — and checked it against two World Cups that had no such breaks.',
  home_howtitle:'How to use this dashboard',
  how1_h:'Analysis',how1_p:'What moves around each break: goals, cards, chances, plus momentum and possession. Benchmarked against no-break World Cups. Filter by match, stage or temperature.',
  how2_h:'Survey',how2_p:'Tell us what you felt watching. Did the game shift after the breaks? Your answers chart live below the questions.',
  home_banner:'<b>Tournament complete.</b> This is the final dataset: all <span class="nn"></span> matches, group stage through the final (Spain 1\u20130 Argentina, after extra time, July 19). Findings describe patterns, not proven cause: with breaks in every 2026 match there is no internal control group, so the yardstick throughout is the 2018 and 2022 World Cups, which had no mandatory breaks.',
  home_foot:'Sources: FBref (events), SofaScore (xG and momentum), Open-Meteo (WBGT estimate). Final build __UPDATED__ \u2014 the tournament ended July 19, 2026 and this dataset is now frozen.',
  an_heat_h:'How hot is it out there?',
  an_heat_s:'The "real-feel" heat on the pitch, called WBGT: air temperature, humidity, and sun rolled into one number. Around 28°C and up is tough on players.',
  heatLeg:()=>['Cooler','Warm','Hot '+tU(28,0)+'+'],
  heatNote:(avgT,thrT,hotN,coolN,n)=>`Across these ${n} games the pitch feels like about <b>${avgT}</b> on average. We count a game as <b>hot</b> when the real-feel heat is <b>${thrT} or more</b> (${hotN} games), and <b>cooler</b> below that (${coolN} games). That is the split the Hot / Cooler filter above uses. Real-feel heat (its proper name is WBGT) matters more than plain air temperature, because humidity and direct sun make the same temperature far harder on the body.`,
  lbl_match:'Match',opt_all:'All matches (totals)',lbl_stage:'Round',st_all:'All stages',st_ko:'Knockouts (all)',
  stageLabels:{group:'Group stage',R32:'Round of 32',R16:'Round of 16',QF:'Quarterfinals',SF:'Semifinals','3P':'Third place',F:'Final'},
  lbl_heat:'Heat',h_all:'All',h_hot:'Hot 🔥',h_cool:'Cooler',
  an_breaks_h:'What changes around each break',an_breaks_s:'Only the 10 minutes right before each break versus the 10 minutes right after. Goals, cards or subs at any other time in the match are not counted here, so these numbers will not add up to the final score. For every goal, see the goal-timing chart lower down.',
  recon1:(tot,inw,mins)=>`This match had <b>${tot}</b> goal${tot===1?'':'s'}${mins.length?' (at '+mins.map(m=>m+"'").join(', ')+')':''}. This table only looks at the 10 minutes on each side of the 22' and 67' breaks, so just <b>${inw}</b> land${inw===1?'s':''} inside a window here. The rest were scored at other times. The goal-timing chart below shows all of them.`,
  reconAll:(tot,inw,n)=>`Heads up: this table counts only the 10 minutes on each side of each break. Across these ${n} matches, <b>${inw}</b> of <b>${tot}</b> goals fell inside a break window; the other ${tot-inw} happened elsewhere in the match, which is why these totals look small. The goal-timing chart below has every goal.`,
  an_poss_h:'Who had the ball more',an_poss_s:'World Cup games are on neutral ground, so there is no real home team. Pick one match above and this shows how the two teams split the ball over the full game.',
  possPrompt:'⚽ Pick a single match above to see who kept the ball.<br><span style="font-weight:400;opacity:.85">World Cup games are on neutral ground, so there is no home side to average across all matches.</span>',
  possNoData:(h,a)=>`⚽ No possession data for ${h} v ${a} yet.<br><span style="font-weight:400;opacity:.85">We have the result and events for this match, but the ball-possession split has not come through. Try another match.</span>`,
  wideNote:(n)=>`<div class="scopebanner">📊 Whole-tournament view. This measure is not available match by match, so it uses the full sample and does not change when you pick a single game.</div>`,
  an_dist_h:'When the goals get scored',an_dist_s:'Every goal, grouped into 5-minute slices. The dashed lines are the breaks. If breaks slow the game down, you would see fewer goals right after them.',
  an_hist_h:'2026 vs the last two World Cups (no breaks)',an_hist_s:'When goals were scored. Red is 2026; grey is the average of the two no-break World Cups. If red dips at the breaks and grey does not, the breaks are doing something.',
  histLeg1:'No-break years (2018 & 2022)',histLeg2:'2026 (with breaks)',
  an_xg_h:'Fewer goals after a break: unlucky, or a quieter game?',an_xg_s:'Goals can dip for two reasons: teams miss good chances (bad luck), or they simply make fewer good chances (a quieter game). To tell them apart we look at chance quality, called expected goals or xG, which scores how likely each shot was to go in. Each bar is the 10 minutes after a break as a share of the 10 minutes before. 100% means no change; lower means less after the break.',
  an_mom_h:'Does the team on top change after a break?',an_mom_s:'Momentum means which team is pushing forward. When it flips after a break, does that team go on to score?',
  an_subs_h:'Do coaches use the breaks to make subs?',an_subs_s:'When substitutions happen, by 5-minute slice. The dashed lines are the breaks. If coaches used them as a free sub window, you would see a bump right at them.',
  subLeg26:'2026 (with breaks)',subLeg22:'2022 (no breaks)',
  subNote:(s)=>`No. The early break at 22' sees almost no subs (${s.b1} in the whole tournament), and the second only has subs because it lands in the normal 60-to-75 minute window. The gold 2022 line, which had no breaks, sits almost on top of 2026: same flat spot at 22', same half-time and late spikes. So the breaks changed nothing about when coaches sub. 2026: ${s.n} games; 2022: 48.`,
  an_wel_h:'Do the breaks protect players in the heat?',an_wel_s:'Injury stoppages and injury subs per game, counted from live commentary. Are hot games harder on the players?',
  an_heat2_h:'Does the heat itself change the game?',
  an_heat2_s:'Set the breaks aside for a moment. Each dot is a match: its real-feel heat against the total goals scored. If heat slowed matches down, the hotter ones would sit lower.',
  heatScatterLeg:()=>['Cooler games','Hot games ('+tU(28,0)+'+)'],
  heatScatterNote:(r,hotAvg,coolAvg,n)=>{const a=Math.abs(r),d=a<0.1?'essentially no link':a<0.3?'a weak link':a<0.5?'a moderate link':'a clear link';return `Each dot is one of the ${n} matches with a heat reading. The dotted line is the trend, and it points to <b>${d}</b> between heat and scoring (r = ${r.toFixed(2)}). Hotter matches average <b>${hotAvg}</b> goals versus <b>${coolAvg}</b> in cooler ones. So on the full-tournament evidence, heat ${a<0.1?'barely moves the score':(r<0?'nudges scoring down as it climbs':'nudges scoring up as it climbs')}.`;},
  welLeg:()=>['Hot games (real-feel '+tU(28,0)+'+)','Cooler games'],welAxis:['Whole game','Last 20 min'],
  welK:['Stoppages per game','Share in the last 20 min','Hot vs cool, per game'],
  welNote:(w)=>`Counted from live commentary (treatment stoppages and injury subs), the same way published World Cup injury studies do it. Treatments climb late as legs tire. The surprise: <b>hot games are not harder on players</b>, they have fewer stoppages, not more (${w.hot.ev} vs ${w.cool.ev} per game). That fits the breaks doing their job in heat, though slower, calmer hot games could explain it too. Versus 2022 (no breaks), the late-game share of injuries is about the same (34% then vs ${w.latePct}% now), so the breaks did not change when injuries strike. Broadcast-counted, not official medical data; we compare shares, not raw counts, since how fully each match is narrated differs by year.`,
  v_tests_h:'Three ways to check it',v_tests_s:'Each one asks the same question a different way: is the game really quieter right after a break? Green means it looks real, amber means maybe, grey means it could just be chance.',
  v_trend_h:'How the picture has moved',v_next_h:'What would change the answer',
  v_track_h:'Is the gap real, or just noise?',v_track_s:'The share of break-window goals that came after the break, tracked as matches piled up. If breaks did nothing it sits at 50%. The band is the 95% confidence range.',
  trackNote:(cur,n)=>`It closed the tournament at <b>${cur}%</b> across all ${n} matches, with the confidence band still crossing the 50% no-effect line \u2014 the gap stayed within chance from the group stage to the final. A real effect would have pulled the whole band off 50%; it never did.`,
  perceptionLow:'<div class="scopebanner">📊 Once a few more people vote, this box compares what fans felt with what the data shows.</div>',
  perception:(morePct,noticed,pre,post)=>{const dir=post<pre?'a slight dip':(post>pre?'a slight rise':'no change');const mm=morePct>=55&&post<=pre;return `<div class="scopebanner">Of the ${noticed} fans who felt a change, <b>${morePct}%</b> said the game got <b>more intense</b> after a break. The data leans the other way: goals in the 10 minutes after a break are <b>${post}</b> versus <b>${pre}</b> before, ${dir}. ${mm?'So the breaks feel more eventful than they actually are.':'Gut and numbers are roughly in line here.'}</div>`;},
  gl_title:'Plain-language glossary',gl_sub:'Every term on this dashboard, spelled out. No stats degree required.',
  sv_title:'Did the breaks change how the game felt?',sv_sub:'Vote once and watch how everyone answered, live. Results are shared across all visitors and update as people vote.',
  sv_submit:'Submit response',sv_export:'Export CSV',
  sv_note:'Answers are pooled anonymously across everyone who visits, and the chart updates live. Counts only, no names or comments are stored. One vote per browser.',
  nav_broadcast:'Broadcast',
  bc_title:'What the breaks are worth in ad money',
  bc_sub:'Every hydration break is also about two extra minutes of commercial airtime. This models what that airtime is worth on US television (Fox), from published spot-price ranges, with a transparent low / base / high calculation \u2014 not invented numbers.',
  sc_low:'Low',sc_base:'Base',sc_high:'High',
  bcKTotal:'\ud83d\udcb0 Total revenue',bcKIncr:'\ud83d\udcc8 Incremental',bcKPerMatch:'\u26bd Per match',bcKMatches:'\ud83c\udfdf\ufe0f Matches priced',
  bcBanner:(n)=>`<b>US/Fox only \u2014 by evidence, not oversight.</b> ${n} matches priced. Telemundo's Spanish-language audience is enormous (Mexico-England R16 drew 23.2M total audience, a Spanish-language World Cup record, per NBCUniversal) but no per-spot price is publicly disclosed, only opaque season packages \u2014 modeling it would mean guessing a number, so it stays out of the total rather than being invented. The UK splits oddly: the BBC carries zero advertising by design, and whether ITV even sells break-timed spots the way Fox does is unconfirmed. Brazil (Globo) has no public rate card found. Spot prices shown here are trade-press ranges for the US only (HITC, Hollywood Reporter, Front Office Sports), not Fox's audited actuals.`,
  bc_stage_h:'Value rises with the stage',bc_stage_s:'Knockout matches carry higher spot prices than the group stage, from cited trade-press ranges, not a flat extrapolation.',
  bcStageNote:'Group-stage spots run about $200k\u2013$400k for a 30-second slot. Knockout spots ($300k\u2013$2M, per Front Office Sports and Awful Announcing on the USMNT\'s run) push the per-match total up sharply once the bracket tightens.',
  bc_tier_h:'Which matches capture the value',bc_tier_s:'Matches are tagged USA (either team is the United States), marquee (a historically major team plays), or other. The tier drives both the spot price and the audience estimate.',
  bcTierCol1:'Tier',bcTierCol2:'Matches',bcTierCol3:'Revenue (this scenario)',bcTierCol4:'Avg / match',
  bandLabels:{early:'Group / R32',late:'R16-QF-SF',final:'Final / 3rd place'},
  sankeyTotal:'Total revenue',
  bc_sankey_h:'Where the money flows',bc_sankey_s:'The same calculation chain as the KPIs above, laid out as a flow: match tier, into tournament stage, into the total for this scenario.',
  bcSankeyNote:(b)=>`Read left to right: tier of match \u2192 stage band \u2192 total. ${b} Final-band pricing is an unsourced assumption scaled up from the knockout rate, not an independently cited figure \u2014 treat the right-hand edge of the flow as softer than the rest.`,
  bc_cum_h:'Revenue, day by day',bc_cum_s:'Running total across the whole tournament, all three scenarios \u2014 from opening day to the July 19 final.',
  bc_cum_note:'Steps track match dates, not a smooth trend \u2014 days with more matches (or a knockout tie) jump more than a normal group-stage day.',
  bc_sim_h:'Build your own estimate',bc_sim_s:'Drag the sliders to see how spot count, price per spot, and audience size move the per-match revenue estimate \u2014 the exact calc chain the model above uses.',
  sim_spots:'30-second spots per break',sim_cpm:'Price per spot',sim_aud:'Audience (viewers)',
  sim_outl:'Estimated revenue per match (2 breaks)',
  sim_note:'This mirrors track_b_model.py\u2019s formula: revenue = spots \u00d7 price \u00d7 2 breaks. Audience only affects a real campaign\u2019s CPM math, not this simplified per-spot version \u2014 shown for intuition, not as a fourth pricing model.',
  an_grid_h:'Every match, at a glance',an_grid_s:'One tile per match: color shows kickoff heat, dashed lines mark the ~22\' and ~67\' breaks, dots mark goals. Click a tile to load that match above.',
  an_grid_note:'Sorted by date. Heat color uses the same cool/warm/hot cutoffs as the heat panel above.',
  an_venue_h:'Venue comparison',an_venue_s:'Average kickoff WBGT by stadium across the matches played there.',
  venueMatches:'matches',
  venueNote:'Not a geographic map \u2014 stadium coordinates aren\u2019t in the data yet, so this is a sorted tile comparison, not a real map. Two pairs of names likely refer to the same physical stadium under an older name (Reliant Stadium / NRG Stadium in Houston; BC Place / BC Place Stadium in Vancouver) \u2014 shown separately here rather than silently merged, since that would assume a fact not yet confirmed.',
  badge_fact:'Fact',badge_estimate:'Estimate',badge_assumption:'Assumption',
  br_breaksfx:'post-break goals',
  tierLabels:{us:'\ud83c\uddfa\ud83c\uddf8 USA matches',marquee:'\u2b50 Marquee',other:'Other'},
  bc_scatter_h:'Revenue scales with audience',bc_scatter_s:'One dot per match: reported or estimated audience against modeled ad revenue. Seven matches use real Nielsen figures (both semifinals included); the rest use a tiered estimate, labeled as such in the underlying data.',
  bcScatterX:'audience (millions)',bcScatterY:'ad revenue per match ($M)',
  bcTierLegend:['Other','Marquee','USA'],
  bcScatterNote:'The USA-Belgium Round of 16 match (33.1M on Fox, Sports Media Watch \u2014 the tournament\u2019s record English-language audience) and England-Norway\u2019s 21.8M quarterfinal sit well above the tiered estimate used for other matches \u2014 a reminder that the marquee/other tiers are a stand-in for real per-match ratings, not a measurement. The final\u2019s own Nielsen number had not been published when the dataset was frozen; its dot is a conservative estimate flagged in the data.',
  bc_proj_h:'Full tournament \u2014 final modeled total (104 matches)',bc_proj_s:'All 104 matches have been played, so this is the final modeled total for the tournament, not a projection. It equals the revenue-to-date figures above.',
  bc_caveat:'<b>Read this like Track A: estimate, not measurement.</b> Spot prices are trade-press ranges; three matches use reported Nielsen audiences, everything else is a tiered estimate. About 90% of this revenue is treated as incremental (breaks create airtime a sport with no natural stoppages would not otherwise have) \u2014 that 90% is an assumption, not a sourced figure. Models US English-language broadcast (Fox) only; other markets are not yet included in the total.',
  nav_bracket:'Bracket',nav_updates:'Updates',nav_about:'About',
  about_title:'About this project',about_sub:'What it measures, where the data comes from, and what it cannot tell you.',
  about_body:`<h4>The question</h4><p>At the 2026 World Cup, play stops twice in most matches for a short cooling break, once in the first half and once in the second, so players can drink and cool down in the heat. This project asks a simple thing: do those pauses change the football? It tracked goals, chance quality, possession, momentum, cards and substitutions in the minutes around each break across all 104 matches, keeping a running verdict as the tournament unfolded. The tournament ended on July 19, 2026 and the dataset is now complete and frozen \u2014 what you see is the final report.</p>
<h4>The rule being tested</h4><p>The study treats each match as having two breaks of roughly three minutes, near the 22nd and 67th minute. For every match it compares the <b>10 minutes before</b> each break with the <b>10 minutes after</b>. Break timing shifts a little by match and by how hot it is, so read the windows as close approximations, not stopwatch-exact moments.</p>
<h4>Where the data comes from</h4><p>Match events (goals, cards, substitutions, possession and their timings) come from ESPN's public football API. Real-feel heat, whose proper name is WBGT, is estimated from Open-Meteo hourly temperature and humidity at each stadium's location and kickoff hour, using a standard shade formula. Historical no-break baselines come from the 2018 and 2022 World Cups, neither of which used routine cooling breaks. Every figure on the dashboard is either measured from these feeds or clearly labeled as an estimate.</p>
<h4>How the comparison works</h4><p>Three comparisons run side by side. Before versus after each break within the same match, which cancels out how good the teams are. Hot games versus cooler ones, to separate a break effect from a plain heat effect. And 2026 with breaks versus 2018 and 2022 without them. The Verdict tab also tracks the before-versus-after gap with a 95% confidence band, so you can watch it settle as the sample grows.</p>
<h4>What it cannot tell you</h4><p>This is observational, not a controlled experiment. Heat and breaks travel together, so no single match can fully separate them. Early in the tournament the samples are small and any gap should be read lightly. WBGT here is a location estimate, not a sensor on the pitch. And event data can miss the odd detail. Where a number is thin or uncertain, the dashboard says so rather than overstating it.</p>
<h4>How the rule got here</h4><p>Cooling breaks are not new. FIFA introduced them at the <b>2014 Brazil World Cup</b>: discretionary, called by the referee after the 30th minute of each half if the pitch-side WBGT passed 32\u00b0C, made up with extra stoppage time. The first one in World Cup history came in the 32nd minute of Netherlands-Mexico, a 2014 round of 16 match. <b>Qatar 2022</b> kept the same discretionary, 32\u00b0C-triggered rule \u2014 but air-conditioned stadiums likely kept pitch conditions under that threshold most nights, so in practice the breaks were rarely if ever called. <b>2026</b> is a different design: two three-minute breaks in every match, near the 22nd and 67th minute, regardless of temperature \u2014 mandatory and weather-independent, not a heat-safety trigger anymore. That is also why 2026 has no built-in no-break control group, and why this project leans on 2018 (no break rule at all) and 2022 (a rule that existed but was seldom used) as its reference points \u2014 useful baselines, but not identically "break-free" in the same way.</p>
<h4>How it stays current</h4><p>An automated job checks for newly finished matches, pulls their events and weather, appends them to a growing store, recomputes every panel and republishes the site. The date at the top of the page shows when it last refreshed. Nothing is entered by hand, so the verdict you see is the one the current data supports.</p>`,
  br_title:'Knockout bracket',br_sub:'The road to Spain\u2019s title \u2014 every knockout result, Round of 32 through the July 19 final.',
  up_title:'Update log',up_sub:'What has changed in this study and dashboard, newest first.',
  share:'Copy the verdict',shareDone:'Copied. Paste it anywhere.',
  subUpdated:(d,n)=>`Updated ${d} · ${n} matches`,brComing:'Coming up',pens:'decided on penalties',
  rounds:{R32:'Round of 32',R16:'Round of 16',QF:'Quarter-finals',SF:'Semi-finals',F:'Final'},
  shareText:(ans,pre,post,n)=>`Cooling Economy · FIFA World Cup 2026\nDo hydration breaks change the game? ${ans}\nGoals in the 10 min before vs after the breaks: ${pre} vs ${post}, across ${n} matches.`,
  updates:[
   ['2026-07-20','Tournament complete \u2014 final report','Spain beat Argentina 1\u20130 after extra time in the July 19 final (the only goal came at 106\u2032, nowhere near a break window). All 104 matches are in and the dataset is frozen: knockout attendance and referees backfilled, semifinal audiences switched to reported Nielsen figures, and the twice-daily auto-update retired. This dashboard now stands as the project\u2019s final report.'],
   ['2026-07-07','About page + exact rounds','Added an About page laying out the data sources, method and honest limits in plain language. Round labels now come straight from the official round tag, so a late kickoff that rolls past midnight no longer lands in the wrong round.'],
   ['2026-07-06','Filter by round','The round filter now lets you pick any stage on its own, Round of 32, Round of 16, quarterfinals, semis, final, and the match picker groups games by round. Every knockout match is tagged with its correct round.'],
   ['2026-07-06','Perception vs reality + a noise check','Two additions: the Verdict tab now tracks the before-vs-after gap with a 95% confidence band as matches pile up, so you can watch it hug the no-effect line. And the survey now compares what fans felt against what the data shows.'],
   ['2026-07-05','Heat vs goals','New scatter in the deeper analysis: real-feel heat against total goals, one dot per match, to see if heat alone changes scoring. Also patched a missing heat reading so every match with a known venue now has one.'],
   ['2026-07-01','More knockout games','Added Mexico 2-0 Ecuador, another hot one, so all three June 30 Round-of-32 games are in. 79 matches now, and the fan survey has a cleaner live results chart.'],
   ['2026-06-30','Today\'s matches added','Added the June 30 Round-of-32 games (Côte d\'Ivoire 1-2 Norway, France 3-0 Sweden), both played in real-feel heat above 29°C. Now 78 matches in the store.'],
   ['2026-06-30','New visuals + clearer wording','Added a momentum tug-of-war and a goals-on-the-pitch timeline for single matches, a °C/°F switch, and a plain-English rewrite of the chance-quality (xG) panel. The break tables now show how they reconcile with the final score.'],
   ['2026-06-30','No-break baselines','Added 2022 (no breaks) to the substitution and welfare panels. Sub timing is identical year to year, and the late-injury share barely moves.'],
   ['2026-06-30','Player welfare','New panel on injuries and treatments by heat, counted from live commentary. Hot games are not harder on players, if anything they have fewer stoppages.'],
   ['2026-06-30','Substitution timing','New panel asking if coaches use the breaks to make subs. They do not: the early break at 22′ sees almost no subs, and the late one only matches normal subbing.'],
   ['2026-06-30','Knockouts and penalties','Added the opening Round of 32 matches, a knockout bracket, and the penalty-shootout winners. The post-break dip softened further as the sample grew.'],
   ['2026-06-29','Plain-language pass','Swapped statistics shorthand for plain verdicts (Looks real, Could be something, Likely just chance) and added a glossary.'],
   ['2026-06-28','Momentum added','Brought in minute-level momentum to test whether a shift in control after a break leads to goals. It does not.'],
   ['2026-06-27','Baselines and xG','Benchmarked 2026 against the no-break 2018 and 2022 World Cups and confirmed chance quality (xG) drops with goals.'],
   ['2026-06-27','Launch','First build: goal, card and sub windows around each break across the group stage, with a heat filter.'],
  ],
  // dynamic
  kMatches:'🏟️ Matches',kGoals:'⚽ Goals',kGpm:'🎯 Goals / match',kWbgt:'🔥 Typical heat',
  meterLeft:'Could be chance',meterRight:'Looks real',moreShow:'Show the deeper analysis  ▾',moreHide:'Hide the deeper analysis  ▴',
  metrics:['⚽ Goals','🟨 Cards','🔁 Subs','🔀 Lead changes','↩️ Comeback goals'],
  before:'Before',after:'After',beforeAfter:'10 min before → after',
  hvLabel:'The final verdict',
  hvBig:'A faint cooling after the whistle, nothing the numbers will vouch for yet.',
  hvBody:(pre,post)=>`Play eases a touch right after each break: ${pre} goals in the ten minutes before versus ${post} after, with chance quality leaning the same way. But that is the kind of gap you would get by chance next to the no-break World Cups, and it has faded as more matches arrived. Straight answer: no, not in any way we can stand behind today. A hint worth watching, not a proven effect.`,
  hvFinding:(n)=>`<b>Why "not proven" rather than "case closed."</b> At 66 group matches the post-break dip looked sharper, and the hot-weather split briefly reached the usual bar. Over the knockout rounds it flattened back toward the no-break pattern \u2014 exactly how a small-sample fluke behaves \u2014 and at the final whistle of match ${n} it still sat inside the noise band. The knockouts decided it: the effect faded as the sample grew.`,
  scope1:'1 match',
  distNoteSingle:"Single match: just this game's goals.",
  distNoteAll:'Goals normally pick up later in each half. So if the breaks did nothing, the dashed lines should not line up with a dip.',
  histBase:(post,tot,pct)=>`<b>No-break baseline:</b> ${post} of ${tot} break-window goals fall <i>after</i> the mark (${pct}%). Scoring climbs there, the normal rhythm. `,
  histFew:(n)=>`This selection has too few break-window goals (${n}) to compare.`,
  histSel:(post,n,pct,below,verdict)=>`<b>This selection:</b> ${post} of ${n} land after (${pct}%). `+(below?`2026 dips below the no-break years here. <b>${verdict}.</b>`:`No real dip below the no-break years here.`),
  xgNote:(n)=>`After a break, goals, chance quality (xG) and shots all fall to about two-thirds of the level just before it. Here is the tell: <b>chance quality drops just as much as the goals do</b>. If it were only bad luck in front of goal, the good chances would still be there and only the goals would fall. Instead teams genuinely create less right after the whistle. From ${n} group games.`,
  momK:['How much momentum moves','How often the top team changes','Goals right after the breaks'],
  momNote:(M)=>`The team on top really does change a lot: in about 1 in 4 breaks (<b>${M.flip}%</b>), the other team takes over. But taking control does not mean you score. The goals after a break go to whoever is on top <b>at that moment</b> (${M.ontop[0]} of ${M.postgoals}), not to the team that just grabbed momentum (${M.gainer[0]}). With only ${M.postgoals} post-break goals in it, read this part lightly. From 54 group games \u2014 momentum was hand-transcribed per match and tracking ended with the group stage, so this note rests on that 54-match sample while the rest of the dashboard covers all ${D.n}.`,
  eloNote:'<span class="badge estimate"><span class="dot"></span>Estimate</span> Team strength held roughly fixed (added 2026-07-09). The earlier reading that "the leading team scores more after a break" is confounded: leading teams are usually just the stronger team already (Elo ~1 month pre-tournament). Looking only at post-break goals where the lead and the Elo favorite disagree \u2014 a team leading despite being the weaker side, or trailing despite being the stronger one \u2014 the pattern does not hold: those goals split roughly evenly, if anything tilting toward the trailing side (n=10, too small to lean on). Read as: the momentum-reset story looks more like a quality story than a break-timing story, but the de-confounded sample is thin.',
  tugB1:'Around the 22\' break (before → after)',tugB2:'Around the 67\' break (before → after)',
  tugKey:'○ before the break     ⚽ after the break',
  tugNote:(g)=>{const m=g.mom,side=v=>v>3?g.home:(v<-3?g.away:'neither side'),fl=(a,b)=>((a>3&&b<-3)||(a<-3&&b>3)),flipped=fl(m[0],m[1])||fl(m[2],m[3]);
   return `The ball shows who was pushing forward. After the 22' break, <b>${side(m[1])}</b> had the momentum; after the 67' break, <b>${side(m[3])}</b>. ${flipped?'The momentum flipped sides across a break in this game.':'The same side kept pushing across both breaks.'} Further right (gold) means ${g.home} on top; further left (blue) means ${g.away}.`;},
  momLabels:['Team on top AFTER break','Team that GAINED momentum'],momTitle:(t)=>`post-break goals scored (of ${t})`,
  readSingle:(g,m)=>`<b>${flag(g.home)} ${g.home} ${g.hg}–${g.ag} ${g.away} ${flag(g.away)}</b> · ${g.date} · ${tU(g.wbgt,1)} heat.${m} One match is anecdote, so switch to All matches for the pattern.`,
  readAll:(pre,post)=>`<b>Does the break change the game, or is this just normal?</b> Goals go ${pre}→${post} around the breaks here. Goals naturally pick up later in a half, so the comparison further down is the real test. The effect is clearest in <b>hot games</b>, so try the Hot filter.`,
  momTxt:(m,t)=>` Momentum (+ means ${t} pushing forward). B1 ${fmt(m[0])}→${fmt(m[1])}, B2 ${fmt(m[2])}→${fmt(m[3])}.`,
  distX:'match minute',distY:'goals',histX:'match minute',histY:'% of goals',xgX:'after ÷ before',
  vEyebrow:(n)=>`Final verdict · tournament complete · all ${n} matches`,
  vYes:'Probably yes: a measurable cooling after the whistle.',vNo:'No. The effect never rose above the noise.',
  vLead:(pre,post,n)=>`Across all ${n} matches, goals in the ten minutes after a break (${post}) trail the ten before (${pre}). The lean is there on the page, but none of the three checks below ever got strong enough to trust, so the honest closing read is a mild tendency, not a settled effect.`,
  vt1:'Within 2026 matches',vt2:()=>'Hot matches only (real-feel '+tU(28,0)+'+)',vt3:'Versus no-break 2018 & 2022',
  vt1n:(a,b)=>`${a} goals before vs ${b} after the breaks`,vt2n:(a,b,n)=>`${a} before vs ${b} after, ${n} matches`,vt3n:(pct)=>`${pct}% of break-window goals land after, vs 55% with no breaks`,
  cReal:'Looks real',cMaybe:'Could be something',cChance:'Likely just chance',vstatNa:'Not enough games yet',
  vTrend:'The arc of the tournament is the story. At 66 group matches the dip looked sharper and the hot-weather split briefly cleared the significance bar; every round added after that pulled the gap back toward the no-break pattern, and at the full 104 matches the confidence band still crosses the no-effect line. An effect that shrinks as the sample grows is behaving like noise. Heat on its own never moved the scoreboard either: the hottest matches averaged slightly more goals than the coolest, not fewer, though that link is far too weak to lean on.',
  vNext:'The sample will not grow \u2014 the tournament is over and the dataset is frozen. The closing read: a mild lean that never reached significance, so 2026 gives no evidence that hydration breaks change match outcomes. The cleaner test would be a future tournament where breaks are heat-triggered rather than universal: that would create the within-tournament control group 2026, by design, could not have.',
  gloss:[
   ['Looks real / Could be something / Likely just chance','Our plain verdicts on whether a gap can be trusted. "Looks real" means a gap that size would rarely happen by luck. "Could be something" means there is a hint, but it might still be chance. "Likely just chance" means gaps that size turn up at random all the time. They replace the technical confidence score, so you do not need the maths.'],
   ['Real-feel heat','How hot it actually feels on the pitch, not just the number on a thermometer. It combines air temperature, humidity, and direct sun into one figure, because a humid, sunny 30°C is far harder on players than a dry, breezy 30°C. Its technical name is WBGT (wet-bulb globe temperature), and it is what FIFA watches to decide heat measures. Around 28°C and up counts as hot here. The Heat filter uses it to split hot games from cooler ones.'],
   ['Neutral ground (no home team)','Almost every World Cup match is at a neutral stadium, so there is no real home advantage. The fixture still names one team first, but that does not make them the home side. The only exceptions are the hosts (USA, Canada, Mexico) playing in their own country.'],
   ['Injury stoppage','When play pauses for a player to be treated, or a sub is made because of an injury. We count these from live match commentary, the same method published World Cup injury studies use. It is a broadcast count, not official medical data.'],
   ['xG (expected goals)','A 0 to 1 score for how likely each shot was to be a goal, based on its position and type. Adding them up shows how many goals a team "should" have scored, separating chance quality from finishing luck.'],
   ['Hydration break','A mandatory three-minute pause near the 22nd and 67th minute of every 2026 match, so players can drink and cool down.'],
   ['Before / after window','The ten minutes just before a break versus the ten just after. We compare the two to see what the break changes.'],
   ['Momentum','SofaScore\'s minute-by-minute read of which team is pressing and threatening. Positive means the home side is on top. It is a stand-in for possession and territory, not the exact possession percentage.'],
   ['Momentum swing','How much that momentum number moves from before a break to after. A bigger swing means the balance of play shifted more.'],
   ['Lead change','A goal that flips who is ahead, an equaliser or a go-ahead goal.'],
   ['Comeback goal','A goal scored by the team that was losing at that moment.'],
   ['Group stage vs Knockout','Group stage is the opening round-robin. Knockout is the single-elimination phase that follows, usually tighter and lower-scoring. The Stage toggle switches between them.'],
   ['No-break baseline','The 2018 and 2022 World Cups, which had no mandatory breaks. They show the normal pattern, so we can tell whether 2026 is different.'],
  ],
  sq:[
   {id:'watched',q:'Have you watched 2026 World Cup matches?',o:['Yes, several','A few','No']},
   {id:'b1feel',q:"After Break 1 (around the 22nd minute), did the game feel different?",o:['More intense','Less intense','No change','Did not notice']},
   {id:'b2feel',q:"After Break 2 (around the 67th minute), did the game feel different?",o:['More intense','Less intense','No change','Did not notice']},
   {id:'whobenefits',q:'Who do the breaks help most?',o:['The leading team','The trailing team','Neither']},
   {id:'purpose',q:'What are the breaks mainly for?',o:['Player welfare','TV ad money','Both','Not sure']},
   {id:'fair',q:'Do mandatory breaks feel fair to the contest?',o:['Yes','No','Not sure']}
  ],
  svComment:'Anything else you noticed?',svPlaceholder:'Optional',svAfter1:'After Break 1',svAfter2:'After Break 2',
  svTally:(n)=>`${n} response${n===1?'':'s'} so far`,svNone:'No responses yet.',svThanks:'Thanks! Your vote is in ✓',svErr:'Could not send, try again',
  svFeel:['More intense','Less intense','No change','Did not notice'],
 },
 es:{
  nav_home:'Inicio',nav_analysis:'Análisis',nav_verdict:'Veredicto',nav_glossary:'Glosario',nav_survey:'Encuesta',
  home_eyebrow:'Copa del Mundo 2026 · Pausas de hidratación · Informe final',
  home_title:'¿Las pausas de hidratación<br>cambian el partido?',
  home_lead:'Cada partido del Mundial 2026 se detuvo por una <b>pausa obligatoria de hidratación de tres minutos</b> cerca del minuto 22 y del 67. Este proyecto siguió qué le pasó al juego en los diez minutos a cada lado de esas pausas en los 104 partidos \u2014 España levantó la copa el 19 de julio \u2014 y lo comparó con dos Mundiales que no tuvieron esas pausas.',
  home_howtitle:'Cómo usar este tablero',
  how1_h:'Análisis',how1_p:'Qué se mueve alrededor de cada pausa: goles, tarjetas, ocasiones, más momentum y posesión. Comparado con Mundiales sin pausas. Filtra por partido, fase o temperatura.',
  how2_h:'Encuesta',how2_p:'Cuéntanos qué sentiste viendo los partidos. ¿Cambió el juego después de las pausas? Tus respuestas se grafican en vivo debajo de las preguntas.',
  home_banner:'<b>Torneo completado.</b> Este es el conjunto de datos final: los <span class="nn"></span> partidos, desde la fase de grupos hasta la final (España 1\u20130 Argentina, en tiempo extra, 19 de julio). Los hallazgos describen patrones, no causa comprobada: como todos los partidos de 2026 tuvieron pausas, no hay grupo de control interno; el punto de comparación son los Mundiales 2018 y 2022, sin pausas obligatorias.',
  home_foot:'Fuentes: FBref (eventos), SofaScore (xG y momentum), Open-Meteo (estimación de WBGT). Versión final __UPDATED__ \u2014 el torneo terminó el 19 de julio de 2026 y estos datos quedan congelados.',
  an_heat_h:'¿Cuánto calor hace ahí afuera?',
  an_heat_s:'La sensación térmica real en la cancha, llamada WBGT: temperatura del aire, humedad y sol en un solo número. De 28°C para arriba es duro para los jugadores.',
  heatLeg:()=>['Fresco','Templado','Calor '+tU(28,0)+'+'],
  heatNote:(avgT,thrT,hotN,coolN,n)=>`En estos ${n} partidos la cancha se siente en promedio como <b>${avgT}</b>. Contamos un partido como <b>caluroso</b> cuando la sensación térmica es de <b>${thrT} o más</b> (${hotN} partidos), y <b>fresco</b> por debajo (${coolN} partidos). Ese es el corte que usa el filtro Calor / Fresco de arriba. La sensación térmica real (su nombre técnico es WBGT) importa más que la temperatura del aire sola, porque la humedad y el sol directo hacen que la misma temperatura pese mucho más en el cuerpo.`,
  lbl_match:'Partido',opt_all:'Todos los partidos (totales)',lbl_stage:'Ronda',st_all:'Todas las fases',st_ko:'Eliminatorias (todas)',
  stageLabels:{group:'Fase de grupos',R32:'Dieciseisavos',R16:'Octavos',QF:'Cuartos',SF:'Semifinales','3P':'Tercer puesto',F:'Final'},
  lbl_heat:'Calor',h_all:'Todos',h_hot:'Calor 🔥',h_cool:'Fresco',
  an_breaks_h:'Qué cambia alrededor de cada pausa',an_breaks_s:'Solo los 10 minutos justo antes de cada pausa frente a los 10 minutos justo después. Los goles, tarjetas o cambios en cualquier otro momento del partido no se cuentan aquí, así que estos números no van a cuadrar con el marcador final. Para ver todos los goles, mira el gráfico de tiempos de gol más abajo.',
  recon1:(tot,inw,mins)=>`Este partido tuvo <b>${tot}</b> gol${tot===1?'':'es'}${mins.length?' (al '+mins.map(m=>m+"'").join(', ')+')':''}. Esta tabla solo mira los 10 minutos a cada lado de las pausas del 22' y el 67', así que solo <b>${inw}</b> ${inw===1?'cae':'caen'} dentro de una ventana aquí. El resto se marcaron en otros momentos. El gráfico de tiempos de gol de abajo los muestra todos.`,
  reconAll:(tot,inw,n)=>`Ojo: esta tabla cuenta solo los 10 minutos a cada lado de cada pausa. En estos ${n} partidos, <b>${inw}</b> de <b>${tot}</b> goles cayeron dentro de una ventana de pausa; los otros ${tot-inw} pasaron en otro momento del partido, por eso estos totales se ven bajos. El gráfico de tiempos de gol de abajo los tiene todos.`,
  an_poss_h:'Quién tuvo más la pelota',an_poss_s:'Los partidos del Mundial son en cancha neutral, así que no hay un local de verdad. Elige un partido arriba y verás cómo se repartieron la pelota los dos equipos en todo el juego.',
  possPrompt:'⚽ Elige un partido arriba para ver quién tuvo más la pelota.<br><span style="font-weight:400;opacity:.85">Los partidos del Mundial son en cancha neutral, así que no hay un local para promediar entre todos.</span>',
  possNoData:(h,a)=>`⚽ Aún no hay datos de posesión para ${h} v ${a}.<br><span style="font-weight:400;opacity:.85">Tenemos el resultado y los eventos de este partido, pero el reparto de posesión no llegó. Prueba con otro partido.</span>`,
  wideNote:(n)=>`<div class="scopebanner">📊 Vista de todo el torneo. Esta medida no está disponible partido por partido, así que usa la muestra completa y no cambia cuando eliges un solo juego.</div>`,
  an_dist_h:'Cuándo se marcan los goles',an_dist_s:'Cada gol, agrupado en bloques de 5 minutos. Las líneas punteadas son las pausas. Si las pausas frenan el juego, verías menos goles justo después.',
  an_hist_h:'2026 vs los dos Mundiales anteriores (sin pausas)',an_hist_s:'Cuándo se marcaron los goles. Rojo es 2026; gris es el promedio de los dos Mundiales sin pausas. Si el rojo cae en las pausas y el gris no, las pausas están haciendo algo.',
  histLeg1:'Años sin pausas (2018 y 2022)',histLeg2:'2026 (con pausas)',
  an_xg_h:'¿Menos goles tras la pausa: mala suerte o partido más tranquilo?',an_xg_s:'Los goles pueden bajar por dos razones: los equipos fallan buenas ocasiones (mala suerte), o simplemente generan menos ocasiones buenas (partido más tranquilo). Para distinguirlo miramos la calidad de las ocasiones, llamada goles esperados o xG, que puntúa qué tan probable era cada remate. Cada barra son los 10 minutos después de una pausa como porcentaje de los 10 minutos antes. 100% es sin cambio; menos es menos tras la pausa.',
  an_mom_h:'¿Cambia el equipo que domina tras una pausa?',an_mom_s:'El momentum es qué equipo está atacando más. Cuando cambia tras una pausa, ¿ese equipo termina marcando?',
  an_subs_h:'¿Los técnicos usan las pausas para hacer cambios?',an_subs_s:'Cuándo se hacen los cambios, por bloque de 5 minutos. Las líneas punteadas son las pausas. Si los técnicos las usaran para cambiar, verías un pico justo ahí.',
  subLeg26:'2026 (con pausas)',subLeg22:'2022 (sin pausas)',
  subNote:(s)=>`No. La pausa temprana del 22' casi no tiene cambios (${s.b1} en todo el torneo), y la segunda solo tiene cambios porque cae en la ventana normal del minuto 60 al 75. La línea dorada de 2022, sin pausas, queda casi encima de 2026: mismo vacío en el 22', mismos picos del entretiempo y del final. Las pausas no cambiaron cuándo se hacen los cambios. 2026: ${s.n} partidos; 2022: 48.`,
  an_wel_h:'¿Las pausas protegen a los jugadores en el calor?',an_wel_s:'Pausas por lesión y cambios por lesión por partido, contados desde el relato en vivo. ¿Los partidos con calor son más duros para los jugadores?',
  an_heat2_h:'¿El calor en sí cambia el partido?',
  an_heat2_s:'Dejemos las pausas de lado un momento. Cada punto es un partido: su sensación térmica frente al total de goles. Si el calor frenara los partidos, los más calurosos estarían más abajo.',
  heatScatterLeg:()=>['Partidos frescos','Partidos con calor ('+tU(28,0)+'+)'],
  heatScatterNote:(r,hotAvg,coolAvg,n)=>{const a=Math.abs(r),d=a<0.1?'prácticamente ninguna relación':a<0.3?'una relación débil':a<0.5?'una relación moderada':'una relación clara';return `Cada punto es uno de los ${n} partidos con dato de calor. La línea punteada es la tendencia y apunta a <b>${d}</b> entre el calor y los goles (r = ${r.toFixed(2)}). Los partidos calurosos promedian <b>${hotAvg}</b> goles frente a <b>${coolAvg}</b> en los más frescos. Así que por ahora, el calor ${a<0.1?'casi no mueve el marcador':(r<0?'baja levemente el marcador cuando sube':'sube levemente el marcador cuando sube')}.`;},
  welLeg:()=>['Partidos con calor (sensación '+tU(28,0)+'+)','Partidos más frescos'],welAxis:['Todo el partido','Últimos 20 min'],
  welK:['Pausas por lesión por partido','Parte en los últimos 20 min','Calor vs fresco, por partido'],
  welNote:(w)=>`Contado desde el relato en vivo (pausas de atención y cambios por lesión), como lo hacen los estudios publicados de lesiones del Mundial. Las atenciones suben al final, cuando las piernas se cansan. La sorpresa: <b>los partidos con calor no son más duros</b>, tienen menos pausas, no más (${w.hot.ev} vs ${w.cool.ev} por partido). Eso encaja con que las pausas hacen su trabajo en el calor, aunque partidos más lentos y tranquilos también podrían explicarlo. Frente a 2022 (sin pausas), la parte de lesiones al final es casi igual (34% entonces vs ${w.latePct}% ahora), así que las pausas no cambiaron cuándo ocurren las lesiones. Contado por relato, no datos médicos oficiales; comparamos partes, no conteos, porque el detalle del relato cambia según el año.`,
  v_tests_h:'Tres formas de comprobarlo',v_tests_s:'Cada una hace la misma pregunta de otra forma: ¿de verdad el juego baja justo después de un pausa? Verde significa que parece real, ámbar que quizás, gris que podría ser casualidad.',
  v_trend_h:'Cómo ha cambiado el panorama',v_next_h:'Qué cambiaría la respuesta',
  v_track_h:'¿La diferencia es real o solo ruido?',v_track_s:'La proporción de goles de la ventana de pausa que cayeron después de la pausa, seguida a medida que se suman partidos. Si las pausas no hicieran nada, se queda en 50%. La banda es el rango de confianza del 95%.',
  trackNote:(cur,n)=>`Cerró el torneo en <b>${cur}%</b> con los ${n} partidos, y la banda de confianza sigue cruzando la línea de 50% (sin efecto): la diferencia se mantuvo dentro del azar desde la fase de grupos hasta la final. Un efecto real habría jalado toda la banda fuera del 50%; nunca pasó.`,
  perceptionLow:'<div class="scopebanner">📊 Cuando voten unas cuantas personas más, esta caja compara lo que sintieron los fans con lo que dicen los datos.</div>',
  perception:(morePct,noticed,pre,post)=>{const dir=post<pre?'una leve caída':(post>pre?'una leve subida':'sin cambio');const mm=morePct>=55&&post<=pre;return `<div class="scopebanner">De los ${noticed} fans que sintieron un cambio, <b>${morePct}%</b> dijeron que el juego se puso <b>más intenso</b> tras una pausa. Los datos van al revés: los goles en los 10 minutos después de una pausa son <b>${post}</b> frente a <b>${pre}</b> antes, ${dir}. ${mm?'Así que las pausas se sienten más movidas de lo que en realidad son.':'La percepción y los números van más o menos parejos aquí.'}</div>`;},
  gl_title:'Glosario en palabras sencillas',gl_sub:'Cada término del tablero, explicado. No hace falta saber de estadística.',
  sv_title:'¿Las pausas cambiaron cómo se sintió el partido?',sv_sub:'Vota una vez y mira cómo respondió todo el mundo, en vivo. Los resultados se comparten entre todos y se actualizan a medida que la gente vota.',
  sv_submit:'Enviar respuesta',sv_export:'Exportar CSV',
  sv_note:'Las respuestas se juntan de forma anónima entre todos los que visitan, y el gráfico se actualiza en vivo. Solo conteos, no se guardan nombres ni comentarios. Un voto por navegador.',
  nav_broadcast:'Publicidad',
  bc_title:'Cu\u00e1nto valen las pausas en plata de publicidad',
  bc_sub:'Cada pausa de hidrataci\u00f3n es tambi\u00e9n cerca de dos minutos extra de tiempo comercial. Esto modela cu\u00e1nto vale ese tiempo en la televisi\u00f3n de EE. UU. (Fox), con rangos de precio publicados y un c\u00e1lculo transparente de bajo / base / alto \u2014 no cifras inventadas.',
  sc_low:'Bajo',sc_base:'Base',sc_high:'Alto',
  bcKTotal:'\ud83d\udcb0 Ingresos totales',bcKIncr:'\ud83d\udcc8 Incremental',bcKPerMatch:'\u26bd Por partido',bcKMatches:'\ud83c\udfdf\ufe0f Partidos valorados',
  bcBanner:(n)=>`<b>Solo US/Fox, por ahora \u2014 por falta de datos, no por descuido.</b> ${n} partidos valorados. La audiencia de Telemundo en espa\u00f1ol es enorme (M\u00e9xico-Inglaterra en octavos junt\u00f3 23.2M de audiencia total, r\u00e9cord en espa\u00f1ol para un Mundial, seg\u00fan NBCUniversal), pero no hay un precio por tanda publicado, solo paquetes de temporada opacos \u2014 modelarlo ser\u00eda inventar un n\u00famero, as\u00ed que se queda fuera del total en vez de adivinarlo. El Reino Unido se divide raro: la BBC no tiene publicidad por dise\u00f1o, y no est\u00e1 confirmado si ITV vende tandas cronometradas a las pausas como hace Fox. Brasil (Globo) no tiene tarifario p\u00fablico encontrado. Los precios que se muestran aqu\u00ed son rangos de prensa especializada solo para EE. UU. (HITC, Hollywood Reporter, Front Office Sports), no cifras auditadas de Fox.`,
  bc_stage_h:'El valor sube con la fase',bc_stage_s:'Los partidos de eliminatoria tienen precios de tanda m\u00e1s altos que la fase de grupos, seg\u00fan rangos citados de prensa especializada, no una extrapolaci\u00f3n plana.',
  bcStageNote:'Las tandas de la fase de grupos rondan $200k\u2013$400k por 30 segundos. Las de eliminatoria ($300k\u2013$2M, seg\u00fan Front Office Sports y Awful Announcing sobre la carrera del equipo de EE. UU.) suben fuerte el total por partido a medida que se cierra el cuadro.',
  bc_tier_h:'Qu\u00e9 partidos capturan el valor',bc_tier_s:'Los partidos se etiquetan como EE. UU. (juega ese equipo), marquee (juega un equipo hist\u00f3ricamente grande) u otro. El nivel define tanto el precio de tanda como el estimado de audiencia.',
  bcTierCol1:'Nivel',bcTierCol2:'Partidos',bcTierCol3:'Ingresos (este escenario)',bcTierCol4:'Prom. / partido',
  bandLabels:{early:'Grupos / R32',late:'Octavos-Cuartos-Semis',final:'Final / 3er lugar'},
  sankeyTotal:'Ingresos totales',
  bc_sankey_h:'Hacia d\u00f3nde va el dinero',bc_sankey_s:'La misma cadena de c\u00e1lculo que los KPI de arriba, en forma de flujo: nivel del partido, hacia la fase del torneo, hacia el total de este escenario.',
  bcSankeyNote:(b)=>`Se lee de izquierda a derecha: nivel del partido \u2192 banda de fase \u2192 total. ${b} El precio de la banda Final es un supuesto sin fuente, escalado desde la tarifa de eliminatoria, no una cifra citada de forma independiente \u2014 trata el extremo derecho del flujo como menos s\u00f3lido que el resto.`,
  bc_cum_h:'Ingresos, d\u00eda a d\u00eda',bc_cum_s:'Total acumulado del torneo completo, en los tres escenarios \u2014 desde el d\u00eda inaugural hasta la final del 19 de julio.',
  bc_cum_note:'Los escalones siguen las fechas de partido, no una tendencia suave \u2014 los d\u00edas con m\u00e1s partidos (o una eliminatoria) suben m\u00e1s que un d\u00eda normal de grupos.',
  bc_sim_h:'Arma tu propio estimado',bc_sim_s:'Mueve los controles para ver c\u00f3mo el n\u00famero de tandas, el precio por tanda y el tama\u00f1o de audiencia cambian el estimado de ingresos por partido \u2014 la misma cadena de c\u00e1lculo del modelo de arriba.',
  sim_spots:'Tandas de 30 segundos por pausa',sim_cpm:'Precio por tanda',sim_aud:'Audiencia (espectadores)',
  sim_outl:'Ingresos estimados por partido (2 pausas)',
  sim_note:'Esto refleja la f\u00f3rmula de track_b_model.py: ingresos = tandas \u00d7 precio \u00d7 2 pausas. La audiencia solo afecta las matem\u00e1ticas de CPM de una campa\u00f1a real, no esta versi\u00f3n simplificada por tanda \u2014 se muestra para intuici\u00f3n, no como un cuarto modelo de precios.',
  an_grid_h:'Cada partido, de un vistazo',an_grid_s:'Una casilla por partido: el color muestra el calor al inicio, las l\u00edneas punteadas marcan las pausas de ~22\' y ~67\', los puntos marcan goles. Haz clic en una casilla para cargar ese partido arriba.',
  an_grid_note:'Ordenado por fecha. El color de calor usa los mismos cortes fresco/c\u00e1lido/caluroso que el panel de calor de arriba.',
  an_venue_h:'Comparaci\u00f3n de sedes',an_venue_s:'WBGT promedio al inicio por estadio, en los partidos jugados ah\u00ed.',
  venueMatches:'partidos',
  venueNote:'No es un mapa geogr\u00e1fico \u2014 las coordenadas de los estadios a\u00fan no est\u00e1n en los datos, as\u00ed que esto es una comparaci\u00f3n de casillas ordenadas, no un mapa real. Dos pares de nombres probablemente sean el mismo estadio f\u00edsico con un nombre anterior (Reliant Stadium / NRG Stadium en Houston; BC Place / BC Place Stadium en Vancouver) \u2014 se muestran por separado en vez de fusionarlos en silencio, ya que eso asumir\u00eda un hecho a\u00fan no confirmado.',
  badge_fact:'Hecho',badge_estimate:'Estimado',badge_assumption:'Supuesto',
  br_breaksfx:'goles tras pausa',
  tierLabels:{us:'\ud83c\uddfa\ud83c\uddf8 Partidos de EE. UU.',marquee:'\u2b50 Marquee',other:'Otros'},
  bc_scatter_h:'Los ingresos suben con la audiencia',bc_scatter_s:'Un punto por partido: audiencia reportada o estimada frente a los ingresos publicitarios modelados. Siete partidos usan cifras reales de Nielsen (incluidas ambas semifinales); el resto usa un estimado por nivel, marcado como tal en los datos.',
  bcScatterX:'audiencia (millones)',bcScatterY:'ingresos por partido ($M)',
  bcTierLegend:['Otros','Marquee','EE. UU.'],
  bcScatterNote:'El partido de octavos EE. UU.-B\u00e9lgica (33.1M en Fox, Sports Media Watch \u2014 r\u00e9cord del torneo en ingl\u00e9s) y el cuartos Inglaterra-Noruega (21.8M) quedan muy por encima del estimado por nivel usado para el resto \u2014 un recordatorio de que los niveles marquee/otro son un sustituto de un rating real por partido, no una medici\u00f3n. La cifra Nielsen de la final a\u00fan no se hab\u00eda publicado al congelar los datos; su punto es un estimado conservador, marcado en los datos.',
  bc_proj_h:'Torneo completo \u2014 total final del modelo (104 partidos)',bc_proj_s:'Los 104 partidos ya se jugaron, as\u00ed que esto es el total final modelado del torneo, no una proyecci\u00f3n. Coincide con las cifras de ingresos acumulados de arriba.',
  bc_caveat:'<b>Ley\u00e9ndolo como el Track A: estimaci\u00f3n, no medici\u00f3n.</b> Los precios de tanda son rangos de prensa especializada; tres partidos usan audiencias reales de Nielsen, el resto usa un estimado por nivel. Cerca del 90% de estos ingresos se trata como incremental (las pausas crean tiempo al aire que un deporte sin detenciones naturales no tendr\u00eda de otra forma) \u2014 ese 90% es un supuesto, no una cifra con fuente. Modela solo la transmisi\u00f3n en ingl\u00e9s de EE. UU. (Fox); otros mercados a\u00fan no est\u00e1n en el total.',
  nav_bracket:'Llaves',nav_updates:'Novedades',nav_about:'Acerca de',
  about_title:'Sobre este proyecto',about_sub:'Qué mide, de dónde salen los datos y qué no puede decirte.',
  about_body:`<h4>La pregunta</h4><p>En el Mundial 2026, en la mayoría de los partidos el juego se detiene dos veces para una pausa de hidratación corta, una en cada tiempo, para que los jugadores tomen agua y se refresquen con el calor. Este proyecto plantea algo sencillo: ¿esas pausas cambian el fútbol? Siguió los goles, la calidad de las ocasiones, la posesión, el momentum, las tarjetas y los cambios en los minutos alrededor de cada pausa en los 104 partidos, con un veredicto que se actualizaba mientras avanzaba el torneo. El torneo terminó el 19 de julio de 2026 y los datos quedan completos y congelados — lo que ves es el informe final.</p>
<h4>La regla que se pone a prueba</h4><p>El estudio asume que cada partido tiene dos pausas de unos tres minutos, cerca del minuto 22 y del 67. Para cada partido compara los <b>10 minutos antes</b> de cada pausa con los <b>10 minutos después</b>. El momento exacto varía un poco según el partido y el calor, así que lee las ventanas como aproximaciones cercanas, no como instantes de cronómetro.</p>
<h4>De dónde salen los datos</h4><p>Los eventos del partido (goles, tarjetas, cambios, posesión y sus tiempos) vienen de la API pública de fútbol de ESPN. El calor de sensación real, cuyo nombre técnico es WBGT, se estima con la temperatura y humedad por hora de Open-Meteo en la ubicación de cada estadio y la hora del saque, usando una fórmula estándar de sombra. Las referencias sin pausas vienen de los Mundiales 2018 y 2022, que no usaron pausas de hidratación de rutina. Cada cifra del tablero está medida de estas fuentes o marcada con claridad como estimación.</p>
<h4>Cómo funciona la comparación</h4><p>Corren tres comparaciones en paralelo. Antes contra después de cada pausa dentro del mismo partido, lo que cancela cuán buenos son los equipos. Partidos calurosos contra partidos más frescos, para separar un efecto de la pausa de un simple efecto del calor. Y 2026 con pausas contra 2018 y 2022 sin ellas. La pestaña Veredicto también sigue la diferencia antes-después con una banda de confianza del 95%, para que veas cómo se asienta a medida que crece la muestra.</p>
<h4>Qué no puede decirte</h4><p>Esto es observacional, no un experimento controlado. El calor y las pausas van juntos, así que ningún partido por sí solo los separa del todo. Al inicio del torneo las muestras son pequeñas y cualquier diferencia debe leerse con cautela. El WBGT aquí es una estimación por ubicación, no un sensor en la cancha. Y los datos de eventos pueden omitir algún detalle. Cuando un número es débil o incierto, el tablero lo dice en vez de exagerarlo.</p>
<h4>C\u00f3mo se lleg\u00f3 a esta regla</h4><p>Las pausas de hidrataci\u00f3n no son nuevas. la FIFA las introdujo en el <b>Mundial de Brasil 2014</b>: a discreci\u00f3n del \u00e1rbitro, despu\u00e9s del minuto 30 de cada tiempo si el WBGT en la cancha pasaba de 32\u00b0C, compensadas con tiempo a\u00f1adido extra. La primera de la historia del Mundial fue en el minuto 32 de Pa\u00edses Bajos-M\u00e9xico, un octavos de 2014. <b>Catar 2022</b> mantuvo la misma regla discrecional con umbral de 32\u00b0C \u2014 pero los estadios con aire acondicionado probablemente mantuvieron las condiciones de cancha bajo ese umbral casi todas las noches, as\u00ed que en la pr\u00e1ctica casi no se usaron. <b>2026</b> es un dise\u00f1o distinto: dos pausas de tres minutos en cada partido, cerca del minuto 22 y el 67, sin importar la temperatura \u2014 obligatorias e independientes del clima, ya no un disparador de seguridad t\u00e9rmica. Por eso 2026 no tiene un grupo de control sin pausas propio, y por eso este proyecto usa 2018 (sin regla de pausas) y 2022 (con regla, pero casi sin usar) como referencia \u2014 puntos de comparaci\u00f3n \u00fatiles, aunque no "sin pausas" exactamente de la misma forma.</p>
<h4>C\u00f3mo se mantiene al d\u00eda</h4><p>Un proceso autom\u00e1tico busca partidos reci\u00e9n terminados, trae sus eventos y el clima, los suma a un registro que crece, recalcula cada panel y vuelve a publicar el sitio. La fecha en la parte superior indica cuándo se actualizó por última vez. Nada se ingresa a mano, así que el veredicto que ves es el que sostienen los datos actuales.</p>`,
  br_title:'Llave de eliminatorias',br_sub:'El camino al título de España — todos los resultados de eliminatoria, de dieciseisavos a la final del 19 de julio.',
  up_title:'Registro de cambios',up_sub:'Qué ha cambiado en este estudio y tablero, lo más nuevo primero.',
  share:'Copiar el veredicto',shareDone:'Copiado. Pégalo donde quieras.',
  subUpdated:(d,n)=>`Actualizado ${d} · ${n} partidos`,brComing:'Por jugarse',pens:'definido por penales',
  rounds:{R32:'Dieciseisavos',R16:'Octavos',QF:'Cuartos',SF:'Semifinales',F:'Final'},
  shareText:(ans,pre,post,n)=>`Cooling Economy · Copa del Mundo 2026\n¿Las pausas de hidratación cambian el partido? ${ans}\nGoles en los 10 min antes vs después de las pausas: ${pre} vs ${post}, en ${n} partidos.`,
  updates:[
   ['2026-07-20','Torneo completado \u2014 informe final','España venció 1\u20130 a Argentina en tiempo extra en la final del 19 de julio (el único gol llegó al 106\u2032, lejos de cualquier ventana de pausa). Los 104 partidos están cargados y los datos quedan congelados: se completaron asistencias y árbitros de las eliminatorias, las audiencias de semifinales pasaron a cifras Nielsen reportadas y la actualización automática se retiró. Este tablero queda como el informe final del proyecto.'],
   ['2026-07-07','Página Acerca de + rondas exactas','Se agregó una página Acerca de que explica en lenguaje simple las fuentes de datos, el método y los límites honestos. Las rondas ahora vienen directo de la etiqueta oficial, así que un partido que arranca tarde y cruza la medianoche ya no cae en la ronda equivocada.'],
   ['2026-07-06','Filtrar por ronda','El filtro de ronda ahora permite elegir cada fase por separado: dieciseisavos, octavos, cuartos, semis y final, y el selector de partidos los agrupa por ronda. Cada partido de eliminatoria queda etiquetado con su ronda correcta.'],
   ['2026-07-06','Percepción vs realidad + prueba de ruido','Dos añadidos: la pestaña Veredicto ahora sigue la diferencia antes-vs-después con una banda de confianza del 95% a medida que se suman partidos, para verla pegarse a la línea de sin efecto. Y la encuesta ahora compara lo que sintieron los fans con lo que dicen los datos.'],
   ['2026-07-05','Calor vs goles','Nuevo gráfico de dispersión en el análisis profundo: sensación térmica frente al total de goles, un punto por partido, para ver si el calor por sí solo cambia el marcador. También se corrigió un dato de calor faltante, así que todo partido con estadio conocido ya lo tiene.'],
   ['2026-07-01','Más octavos','Se agregó México 2-0 Ecuador, otro con calor, así que ya están los tres partidos de octavos del 30 de junio. Ya son 79 partidos, y la encuesta tiene un gráfico de resultados en vivo más claro.'],
   ['2026-06-30','Partidos de hoy','Se agregaron los octavos del 30 de junio (Côte d\'Ivoire 1-2 Noruega, Francia 3-0 Suecia), ambos con sensación térmica sobre 29°C. Ya son 78 partidos en la base.'],
   ['2026-06-30','Nuevos gráficos y textos más claros','Se agregó un tira y afloja de momentum y una línea de goles sobre la cancha por partido, un botón °C/°F, y una reescritura en lenguaje simple del panel de calidad de ocasiones (xG). Las tablas de pausas ahora muestran cómo cuadran con el marcador.'],
   ['2026-06-30','Bases sin pausas','Se agregó 2022 (sin pausas) a los paneles de cambios y bienestar. El momento de los cambios es idéntico año a año, y la parte de lesiones al final casi no cambia.'],
   ['2026-06-30','Bienestar del jugador','Nuevo panel de lesiones y atenciones según el calor, contado desde el relato en vivo. Los partidos con calor no son más duros, incluso tienen menos pausas.'],
   ['2026-06-30','Momento de los cambios','Nuevo panel: ¿los técnicos usan las pausas para hacer cambios? No: la pausa temprana del 22′ casi no tiene cambios, y la tardía solo coincide con el subbing normal.'],
   ['2026-06-30','Eliminatorias y penales','Se agregaron los primeros dieciseisavos, una llave y los ganadores por penales. La caída tras la pausa se suavizó aún más al crecer la muestra.'],
   ['2026-06-29','Lenguaje sencillo','Se cambió la jerga estadística por veredictos en palabras (Parece real, Podría ser algo, Probablemente casualidad) y se añadió un glosario.'],
   ['2026-06-28','Momentum','Se incorporó el momentum minuto a minuto para probar si un cambio de control tras la pausa lleva a goles. No lo hace.'],
   ['2026-06-27','Bases y xG','Se comparó 2026 con los Mundiales sin pausas de 2018 y 2022 y se confirmó que la calidad de ocasiones (xG) baja junto con los goles.'],
   ['2026-06-27','Lanzamiento','Primera versión: ventanas de goles, tarjetas y cambios alrededor de cada pausa en la fase de grupos, con filtro de calor.'],
  ],
  kMatches:'🏟️ Partidos',kGoals:'⚽ Goles',kGpm:'🎯 Goles / partido',kWbgt:'🔥 Calor típico',
  meterLeft:'Podría ser azar',meterRight:'Parece real',moreShow:'Ver el análisis a fondo  ▾',moreHide:'Ocultar el análisis a fondo  ▴',
  metrics:['⚽ Goles','🟨 Tarjetas','🔁 Cambios','🔀 Cambios de ventaja','↩️ Goles de remontada'],
  before:'Antes',after:'Después',beforeAfter:'10 min antes → después',
  hvLabel:'El veredicto final',
  hvBig:'Un leve enfriamiento tras el pitazo, pero nada que los números respalden todavía.',
  hvBody:(pre,post)=>`El juego baja un poquito justo después de cada pausa: ${pre} goles en los diez minutos antes contra ${post} después, y la calidad de ocasiones va en la misma dirección. Pero es del tipo de diferencia que sale por casualidad al lado de los Mundiales sin pausas, y se ha ido desvaneciendo a medida que llegan más partidos. Respuesta directa: no, al menos no de una forma que hoy podamos sostener. Una pista para seguir mirando, no un efecto comprobado.`,
  hvFinding:(n)=>`<b>Por qué "no comprobado" y no "caso cerrado".</b> Con 66 partidos de grupos la caída tras la pausa se veía más marcada, y la versión con calor llegó a rozar el umbral usual. En las eliminatorias se aplanó de vuelta hacia el patrón sin pausas \u2014 justo como se comporta un golpe de suerte con muestra pequeña \u2014 y al pitazo final del partido ${n} seguía dentro de la banda de ruido. Las eliminatorias lo decidieron: el efecto se desvaneció al crecer la muestra.`,
  scope1:'1 partido',
  distNoteSingle:'Un solo partido: solo los goles de este juego.',
  distNoteAll:'Normalmente los goles aumentan al final de cada tiempo. Así que si las pausas no hicieran nada, las líneas punteadas no deberían coincidir con una caída.',
  histBase:(post,tot,pct)=>`<b>Base sin pausas:</b> ${post} de ${tot} goles de la ventana de la pausa caen <i>después</i> de la marca (${pct}%). Ahí el marcador sube, el ritmo normal. `,
  histFew:(n)=>`Esta selección tiene muy pocos goles en la ventana de la pausa (${n}) para comparar.`,
  histSel:(post,n,pct,below,verdict)=>`<b>Esta selección:</b> ${post} de ${n} caen después (${pct}%). `+(below?`2026 cae por debajo de los años sin pausas acá. <b>${verdict}.</b>`:`Acá no cae de verdad por debajo de los años sin pausas.`),
  xgNote:(n)=>`Después de una pausa, los goles, la calidad de las ocasiones (xG) y los remates bajan a unos dos tercios de lo que eran justo antes. La clave: <b>la calidad de las ocasiones baja tanto como los goles</b>. Si fuera solo mala suerte de cara al arco, las buenas ocasiones seguirían ahí y solo bajarían los goles. En cambio, los equipos de verdad crean menos justo tras el pitazo. De ${n} partidos de grupos.`,
  momK:['Cuánto se mueve el momentum','Cuántas veces cambia el dominante','Goles justo tras las pausas'],
  momNote:(M)=>`El equipo que domina s\u00ed cambia bastante: en 1 de cada 4 pausas (<b>${M.flip}%</b>), el otro toma el control. Pero tomar el control no significa marcar. Los goles tras la pausa son de quien domina <b>en ese momento</b> (${M.ontop[0]} de ${M.postgoals}), no del que acaba de agarrar el momentum (${M.gainer[0]}). Con solo ${M.postgoals} goles tras la pausa, t\u00f3malo con pinzas. De 54 partidos de grupos \u2014 el momentum se transcribi\u00f3 a mano partido por partido y el seguimiento termin\u00f3 con la fase de grupos, as\u00ed que esta nota descansa en esa muestra de 54 mientras el resto del tablero cubre los ${D.n}.`,
  eloNote:'<span class="badge estimate"><span class="dot"></span>Estimado</span> Con la fuerza de los equipos m\u00e1s controlada (agregado 2026-07-09). La lectura anterior de que "el equipo que va ganando marca m\u00e1s tras una pausa" est\u00e1 confundida: el que va ganando suele ser sencillamente el equipo m\u00e1s fuerte (Elo de ~1 mes antes del torneo). Mirando solo los goles tras la pausa donde el que va ganando y el favorito por Elo NO coinciden \u2014ganando pese a ser el m\u00e1s d\u00e9bil, o perdiendo pese a ser el m\u00e1s fuerte\u2014, el patr\u00f3n no se sostiene: esos goles se reparten parejo, si acaso un poco a favor del que iba perdiendo (n=10, muy poco para apoyarse). Lectura: la historia del "reinicio de momentum" se parece m\u00e1s a una historia de calidad de plantilla que de tiempos de pausa, pero la muestra sin ese sesgo es chica.',
  tugB1:'Alrededor de la pausa del 22\' (antes → después)',tugB2:'Alrededor de la pausa del 67\' (antes → después)',
  tugKey:'○ antes de la pausa     ⚽ después de la pausa',
  tugNote:(g)=>{const m=g.mom,side=v=>v>3?g.home:(v<-3?g.away:'ninguno'),fl=(a,b)=>((a>3&&b<-3)||(a<-3&&b>3)),flipped=fl(m[0],m[1])||fl(m[2],m[3]);
   return `La pelota muestra quién empujaba más. Tras la pausa del 22', <b>${side(m[1])}</b> tenía el control; tras la del 67', <b>${side(m[3])}</b>. ${flipped?'El momentum cambió de lado tras una pausa en este partido.':'El mismo lado siguió empujando en las dos pausas.'} Más a la derecha (dorado) es ${g.home} dominando; más a la izquierda (azul) es ${g.away}.`;},
  momLabels:['Equipo arriba DESPUÉS de la pausa','Equipo que GANÓ momentum'],momTitle:(t)=>`goles tras la pausa (de ${t})`,
  readSingle:(g,m)=>`<b>${flag(g.home)} ${g.home} ${g.hg}–${g.ag} ${g.away} ${flag(g.away)}</b> · ${g.date} · ${tU(g.wbgt,1)} de calor.${m} Un partido es anécdota, así que cambia a Todos los partidos para ver el patrón.`,
  readAll:(pre,post)=>`<b>¿La pausa cambia el partido, o esto es normal?</b> Los goles van ${pre}→${post} alrededor de las pausas acá. Los goles aumentan naturalmente al final del tiempo, así que la comparación de más abajo es la prueba real. El efecto se ve más claro en los <b>partidos con calor</b>, prueba el filtro de Calor.`,
  momTxt:(m,t)=>` Momentum (+ significa ${t} empujando). P1 ${fmt(m[0])}→${fmt(m[1])}, P2 ${fmt(m[2])}→${fmt(m[3])}.`,
  distX:'minuto del partido',distY:'goles',histX:'minuto del partido',histY:'% de goles',xgX:'después ÷ antes',
  vEyebrow:(n)=>`Veredicto final · torneo completado · los ${n} partidos`,
  vYes:'Probablemente sí: un enfriamiento medible tras el pitazo.',vNo:'No. El efecto nunca superó el ruido.',
  vLead:(pre,post,n)=>`En los ${n} partidos, los goles en los diez minutos después de una pausa (${post}) quedan por debajo de los diez minutos antes (${pre}). La inclinación está ahí en el papel, pero ninguna de las tres comprobaciones de abajo llegó a ser lo bastante fuerte para confiar, así que la lectura honesta de cierre es una tendencia leve, no un efecto firme.`,
  vt1:'Dentro de los partidos 2026',vt2:()=>'Solo partidos con calor (sensación '+tU(28,0)+'+)',vt3:'Frente a 2018 y 2022 sin pausas',
  vt1n:(a,b)=>`${a} goles antes contra ${b} después de las pausas`,vt2n:(a,b,n)=>`${a} antes contra ${b} después, ${n} partidos`,vt3n:(pct)=>`${pct}% de los goles de la ventana caen después, contra 55% sin pausas`,
  cReal:'Parece real',cMaybe:'Podría ser algo',cChance:'Probablemente casualidad',vstatNa:'Aún no hay suficientes partidos',
  vTrend:'El arco del torneo es la historia. Con 66 partidos de grupos la caída se veía más marcada y la versión con calor llegó a rozar el umbral; cada ronda que se sumó después la empujó de vuelta hacia el patrón sin pausas, y con los 104 partidos completos la banda de confianza sigue cruzando la línea de sin efecto. Un efecto que se encoge cuando crece la muestra se comporta como ruido. El calor por sí solo tampoco movió el marcador: los partidos más calurosos promediaron algo más de goles que los más frescos, no menos, aunque esa relación es demasiado débil para apoyarse en ella.',
  vNext:'La muestra ya no va a crecer: el torneo terminó y los datos quedan congelados. La lectura de cierre: una inclinación leve que nunca alcanzó significancia, así que 2026 no aporta evidencia de que las pausas de hidratación cambien los resultados. La prueba más limpia sería un torneo futuro con pausas activadas por calor en vez de universales: eso crearía el grupo de control interno que 2026, por diseño, no pudo tener.',
  gloss:[
   ['Parece real / Podría ser algo / Probablemente casualidad','Nuestros veredictos en palabras sobre si una diferencia es confiable. "Parece real" significa que una diferencia así casi nunca pasaría por azar. "Podría ser algo" significa que hay una pista, pero todavía podría ser suerte. "Probablemente casualidad" significa que diferencias de ese tamaño salen al azar todo el tiempo. Reemplazan al puntaje técnico para que no necesites las matemáticas.'],
   ['Sensación térmica real','Qué tan caluroso se siente de verdad en la cancha, no solo el número del termómetro. Junta temperatura del aire, humedad y sol directo en una sola cifra, porque 30°C con humedad y sol pesan mucho más que 30°C secos y con brisa. Su nombre técnico es WBGT (temperatura de globo de bulbo húmedo), y es lo que la FIFA vigila para decidir medidas por calor. De 28°C para arriba cuenta como caluroso aquí. El filtro de Calor lo usa para separar partidos calurosos de los más frescos.'],
   ['Cancha neutral (sin local)','Casi todos los partidos del Mundial se juegan en estadios neutrales, así que no hay ventaja de local de verdad. El fixture igual nombra a un equipo primero, pero eso no lo hace local. Las únicas excepciones son los anfitriones (EE. UU., Canadá, México) cuando juegan en su país.'],
   ['Pausa por lesión','Cuando el juego se detiene para atender a un jugador, o se hace un cambio por lesión. Las contamos desde el relato en vivo, el mismo método de los estudios publicados de lesiones del Mundial. Es un conteo por relato, no datos médicos oficiales.'],
   ['xG (goles esperados)','Un puntaje de 0 a 1 de qué tan probable era que cada remate fuera gol, según su posición y tipo. Al sumarlos se ve cuántos goles "debería" haber metido un equipo, separando la calidad de la ocasión de la suerte al definir.'],
   ['Pausa de hidratación','Una pausa obligatoria de tres minutos cerca del minuto 22 y del 67 de cada partido de 2026, para que los jugadores tomen agua y se refresquen.'],
   ['Ventana antes / después','Los diez minutos justo antes de un pausa contra los diez justo después. Comparamos ambos para ver qué cambia la pausa.'],
   ['Momentum','La lectura minuto a minuto de SofaScore sobre qué equipo presiona y genera peligro. Positivo significa que el equipo local va arriba. Es un sustituto de posesión y territorio, no el porcentaje exacto de posesión.'],
   ['Cambio de momentum','Cuánto se mueve ese número de momentum de antes de la pausa a después. Un cambio mayor significa que el control del juego se movió más.'],
   ['Cambio de ventaja','Un gol que voltea quién va ganando: un empate o un gol que pone adelante.'],
   ['Gol de remontada','Un gol del equipo que en ese momento iba perdiendo.'],
   ['Grupos vs Eliminatorias','La fase de grupos es la ronda inicial todos contra todos. Las eliminatorias son la fase de eliminación directa que sigue, normalmente más cerrada y con menos goles. El botón de Fase cambia entre ellas.'],
   ['Base sin pausas','Los Mundiales 2018 y 2022, que no tuvieron pausas obligatorias. Muestran el patrón normal, así que sirven para saber si 2026 es distinto.'],
  ],
  sq:[
   {id:'watched',q:'¿Has visto partidos del Mundial 2026?',o:['Sí, varios','Algunos','No']},
   {id:'b1feel',q:'Después de la Pausa 1 (cerca del minuto 22), ¿se sintió distinto el partido?',o:['Más intenso','Menos intenso','Sin cambio','No me fijé']},
   {id:'b2feel',q:'Después de la Pausa 2 (cerca del minuto 67), ¿se sintió distinto el partido?',o:['Más intenso','Menos intenso','Sin cambio','No me fijé']},
   {id:'whobenefits',q:'¿A quién ayudan más las pausas?',o:['Al equipo que va ganando','Al que va perdiendo','A ninguno']},
   {id:'purpose',q:'¿Para qué son las pausas principalmente?',o:['Bienestar del jugador','Plata de la publicidad','Ambos','No estoy seguro']},
   {id:'fair',q:'¿Te parece justo para la competencia que sean obligatorias?',o:['Sí','No','No estoy seguro']}
  ],
  svComment:'¿Algo más que notaste?',svPlaceholder:'Opcional',svAfter1:'Tras la Pausa 1',svAfter2:'Tras la Pausa 2',
  svTally:(n)=>`${n} respuesta${n===1?'':'s'} hasta ahora`,svNone:'Aún no hay respuestas.',svThanks:'¡Gracias! Tu voto quedó ✓',svErr:'No se pudo enviar, reintenta',
  svFeel:['Más intenso','Menos intenso','Sin cambio','No me fijé'],
 }
};
const L=()=>TR[state.lang];
function fmt(x){return (x>0?'+':'')+x;}
function fmtM(usd){return '$'+((usd||0)/1e6).toFixed(1)+'M';}
function badgeHTML(level){const T=L();return `<span class="badge ${level}"><span class="dot"></span>${T['badge_'+level]}</span>`;}

// ---------- helpers ----------
const nm=t=>{const m=t.match(/(\d+)(?:\+(\d+))?/);return m?(+m[1])+(m[2]?+m[2]:0):null;};
const parseGoals=s=>s?s.split(',').map(nm).filter(x=>x!=null):[];
const parseGoalsT=s=>s?s.split(',').map(t=>{const m=t.match(/(\d+)(?:\+(\d+))?\s*([ha])/i);return m?{m:(+m[1])+(m[2]?+m[2]:0),team:m[3].toLowerCase()}:null;}).filter(x=>x):[];
function selGames(){
 if(state.sel!=='all')return G.filter(g=>g.id===state.sel);
 let gs=G;
 if(state.stage==='group')gs=gs.filter(g=>g.stage==='group');
 else if(state.stage==='ko')gs=gs.filter(g=>g.stage!=='group');
 else if(state.stage!=='all')gs=gs.filter(g=>g.stage===state.stage);
 if(state.heat==='hot')gs=gs.filter(g=>g.wbgt>=28);
 else if(state.heat==='cool')gs=gs.filter(g=>g.wbgt<28);
 return gs;}
function binom(k,n){if(n===0)return NaN;const lc=n=>{let s=0;for(let i=2;i<=n;i++)s+=Math.log(i);return s;};
 const pmf=i=>Math.exp(lc(n)-lc(i)-lc(n-i)+n*Math.log(.5));const p0=pmf(k);let s=0;for(let i=0;i<=n;i++)if(pmf(i)<=p0+1e-12)s+=pmf(i);return s;}
function aggBreak(gs,w){const o={g:[0,0],c:[0,0],s:[0,0],lc:[0,0],cm:[0,0]};gs.forEach(g=>{const b=g[w];for(const k in o){o[k][0]+=b[k][0];o[k][1]+=b[k][1];}});return o;}
const erf=x=>{const t=1/(1+.3275911*Math.abs(x));const y=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-.284496736)*t+.254829592)*t*Math.exp(-x*x);return x>=0?y:-y;};
function baselineP(post,n){if(n<6)return NaN;const bPre=D.base['2018'].w[0]+D.base['2018'].w[2]+D.base['2022'].w[0]+D.base['2022'].w[2];const bPost=D.base['2018'].w[1]+D.base['2018'].w[3]+D.base['2022'].w[1]+D.base['2022'].w[3];const p1=bPost/(bPre+bPost),p2=post/n,pp=(bPost+post)/(bPre+bPost+n),se=Math.sqrt(pp*(1-pp)*(1/(bPre+bPost)+1/n));return 2*(1-0.5*(1+erf(Math.abs((p2-p1)/se)/Math.SQRT2)));}
const baseTot=()=>{const b=D.base;return{pre:b['2018'].w[0]+b['2018'].w[2]+b['2022'].w[0]+b['2022'].w[2],post:b['2018'].w[1]+b['2018'].w[3]+b['2022'].w[1]+b['2022'].w[3]};};
function conf(p){const T=L();if(isNaN(p))return{t:T.vstatNa,lvl:'lo'};if(p<0.05)return{t:T.cReal,lvl:'hi'};if(p<0.15)return{t:T.cMaybe,lvl:'mid'};return{t:T.cChance,lvl:'lo'};}
const pillC={hi:'s',mid:'mid',lo:'ns'},vstatC={hi:'ok',mid:'mid',lo:'no'};
const FLAG={"Mexico":"🇲🇽","South Africa":"🇿🇦","Korea Republic":"🇰🇷","Czechia":"🇨🇿","Canada":"🇨🇦","Bosnia & Herz.":"🇧🇦","United States":"🇺🇸","Paraguay":"🇵🇾","Qatar":"🇶🇦","Switzerland":"🇨🇭","Brazil":"🇧🇷","Morocco":"🇲🇦","Haiti":"🇭🇹","Scotland":"🏴󠁧󠁢󠁳󠁣󠁴󠁿","Australia":"🇦🇺","Türkiye":"🇹🇷","Germany":"🇩🇪","Curaçao":"🇨🇼","Netherlands":"🇳🇱","Japan":"🇯🇵","Côte d'Ivoire":"🇨🇮","Ecuador":"🇪🇨","Sweden":"🇸🇪","Tunisia":"🇹🇳","Belgium":"🇧🇪","Egypt":"🇪🇬","Spain":"🇪🇸","Cabo Verde":"🇨🇻","IR Iran":"🇮🇷","New Zealand":"🇳🇿","Saudi Arabia":"🇸🇦","Uruguay":"🇺🇾","France":"🇫🇷","Senegal":"🇸🇳","Iraq":"🇮🇶","Norway":"🇳🇴","Argentina":"🇦🇷","Algeria":"🇩🇿","Austria":"🇦🇹","Jordan":"🇯🇴","Portugal":"🇵🇹","Congo DR":"🇨🇩","England":"🏴󠁧󠁢󠁥󠁮󠁧󠁿","Croatia":"🇭🇷","Ghana":"🇬🇭","Panama":"🇵🇦","Uzbekistan":"🇺🇿","Colombia":"🇨🇴"};
const flag=n=>FLAG[n]||'⚽';
const obs=('IntersectionObserver'in window)?new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');obs.unobserve(e.target);}}),{threshold:.08,rootMargin:'0px 0px -6% 0px'}):null;
function armReveal(){document.querySelectorAll('.card,.hero').forEach(el=>{if(el.classList.contains('reveal'))return;el.classList.add('reveal');if(obs)obs.observe(el);else el.classList.add('in');});}
function countUp(el){const t=(el.textContent||'').trim();const m=t.match(/^([^\d-]*)(-?[\d]+(?:\.[\d]+)?)(.*)$/);if(!m)return;const pre=m[1],end=parseFloat(m[2]),suf=m[3],dec=(m[2].split('.')[1]||'').length;const dur=850,t0=performance.now();
 (function step(now){let p=Math.min(1,(now-t0)/dur);p=1-Math.pow(1-p,3);el.textContent=pre+(end*p).toFixed(dec)+suf;if(p<1)requestAnimationFrame(step);})(performance.now());}
function countScope(id){const s=$(id);if(s)s.querySelectorAll('.v').forEach(countUp);}
function renderBracket(){const T=L();const order=['R32','R16','QF','SF','F'];const byR={};order.forEach(r=>byR[r]=[]);
 G.forEach(g=>{if(byR[g.stage])byR[g.stage].push(g);});
 $('bracketWrap').innerHTML=order.map(r=>{const ms=byR[r];
  const cards=ms.length?ms.map(g=>{let hw=g.hg>g.ag,aw=g.ag>g.hg;let hs=''+g.hg,as=''+g.ag;
    if(g.pen){hw=g.pen[0]>g.pen[1];aw=g.pen[1]>g.pen[0];const ps=v=>` <span style="color:var(--muted);font-weight:600">(${v})</span>`;hs=g.hg+ps(g.pen[0]);as=g.ag+ps(g.pen[1]);}
    const pbg=(g.b1&&g.b1.g?g.b1.g[1]:0)+(g.b2&&g.b2.g?g.b2.g[1]:0);
    return `<div class="bmatch"><div class="r ${hw?'w':(aw?'l':'')}"><span>${flag(g.home)} ${g.home}</span><span>${hs}</span></div><div class="r ${aw?'w':(hw?'l':'')}"><span>${flag(g.away)} ${g.away}</span><span>${as}</span></div>${g.pen?`<div style="font-size:10px;color:var(--muted);text-align:right;margin-top:3px;letter-spacing:.04em">${T.pens}</div>`:''}<div style="font-size:10px;color:var(--muted);text-align:right;margin-top:3px;letter-spacing:.04em" title="${T.br_breaksfx}">⚡ ${pbg} ${T.br_breaksfx}</div></div>`;}).join('')
   :`<div class="bempty">${T.brComing}</div>`;
  return `<div class="bround"><h4>${T.rounds[r]}</h4>${cards}</div>`;}).join('');}
function renderBroadcast(){
 const T=L(); const B=D.broadcast; const sc=state.scenario;
 const tot=B.total[sc]||0, inc=tot*B.incremental, nM=B.games.length, perMatch=nM?tot/nM:0;
 const kpis=[[fmtM(tot),T.bcKTotal],[fmtM(inc),T.bcKIncr],[fmtM(perMatch),T.bcKPerMatch],[nM,T.bcKMatches]];
 $('bcKpis').innerHTML=kpis.map(([v,l])=>`<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
 countScope('bcKpis');
 $('bcBanner').innerHTML=T.bcBanner(nM);
 Chart.defaults.color=chartColor();
 const stOrder=STORDER.filter(s=>B.byStage[s]);
 const stLabels=stOrder.map(s=>T.stageLabels[s]||s), stData=stOrder.map(s=>+(B.byStage[s][sc]/1e6).toFixed(1));
 if(!bcStageChart){
  bcStageChart=new Chart($('cBcStage'),{type:'bar',data:{labels:stLabels,datasets:[{data:stData,backgroundColor:PB(),borderRadius:5}]},
   options:{indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{beginAtZero:true,ticks:{callback:v=>'$'+v+'M'}}}}});
 }else{bcStageChart.data.labels=stLabels;bcStageChart.data.datasets[0].data=stData;bcStageChart.data.datasets[0].backgroundColor=PB();bcStageChart.update();}
 $('bcStageNote').innerHTML=T.bcStageNote;
 const tierOrder=['us','marquee','other'];
 const trows=tierOrder.filter(t=>B.byTier[t]).map(t=>{const o=B.byTier[t];
   return `<tr><td>${T.tierLabels[t]}</td><td>${o.n}</td><td>${fmtM(o[sc])}</td><td>${fmtM(o[sc]/o.n)}</td></tr>`;}).join('');
 $('bcTierTable').innerHTML=`<table><thead><tr><th>${T.bcTierCol1}</th><th>${T.bcTierCol2}</th><th>${T.bcTierCol3}</th><th>${T.bcTierCol4}</th></tr></thead><tbody>${trows}</tbody></table>`;
 const col={us:'#ff4d6d',marquee:'#f6c945',other:'#5ea0ff'};
 const pts=B.games.map(g=>({x:+((g.audience||0)/1e6).toFixed(2),y:+((g.rev[sc]||0)/1e6).toFixed(2),tier:g.tier}));
 if(!bcScatter){
  bcScatter=new Chart($('cBcScatter'),{data:{datasets:[{type:'scatter',data:pts,pointBackgroundColor:pts.map(p=>col[p.tier]),pointBorderColor:pts.map(p=>col[p.tier]),pointBorderWidth:1,pointRadius:5,pointHoverRadius:7}]},
   options:{plugins:{legend:{display:false}},scales:{x:{type:'linear',title:{display:true,text:T.bcScatterX},grid:{display:false}},y:{beginAtZero:true,title:{display:true,text:T.bcScatterY}}}}});
 }else{bcScatter.data.datasets[0].data=pts;bcScatter.data.datasets[0].pointBackgroundColor=pts.map(p=>col[p.tier]);bcScatter.data.datasets[0].pointBorderColor=pts.map(p=>col[p.tier]);bcScatter.update();}
 $('bcScatterLegend').innerHTML=T.bcTierLegend.map((l,i)=>`<span class="hl"><span class="dot" style="background:${[col.other,col.marquee,col.us][i]}"></span>${l}</span>`).join('');
 $('bcScatterNote').innerHTML=T.bcScatterNote;
 const R=B.remaining;
 const proj={low:B.total.low+R.low,base:B.total.base+R.base,high:B.total.high+R.high};
 $('bcProjKpis').innerHTML=['low','base','high'].map(k=>`<div class="kpi"><div class="v">${fmtM(proj[k])}</div><div class="l">${T['sc_'+k]}</div></div>`).join('');
 countScope('bcProjKpis');
 $('bcSankey').innerHTML=sankeySVG(B.sankey[sc]||[]);
 $('bcSankeyNote').innerHTML=T.bcSankeyNote(badgeHTML('assumption'));
 const CUM=B.cumulative||[];
 const cumLabels=CUM.map(c=>c.date), cumLow=CUM.map(c=>+(c.low/1e6).toFixed(1)),
       cumBase=CUM.map(c=>+(c.base/1e6).toFixed(1)), cumHigh=CUM.map(c=>+(c.high/1e6).toFixed(1));
 if(!bcCumChart){
  bcCumChart=new Chart($('cBcCum'),{type:'line',data:{labels:cumLabels,datasets:[
    {label:T.sc_low,data:cumLow,borderColor:GREY,backgroundColor:'transparent',tension:.25,pointRadius:1.5,borderWidth:2},
    {label:T.sc_base,data:cumBase,borderColor:PB(),backgroundColor:'rgba(10,31,68,.10)',fill:true,tension:.25,pointRadius:1.5,borderWidth:3},
    {label:T.sc_high,data:cumHigh,borderColor:GOLD,backgroundColor:'transparent',tension:.25,pointRadius:1.5,borderWidth:2,borderDash:[5,3]}]},
   options:{plugins:{legend:{position:'bottom'}},scales:{y:{beginAtZero:true,ticks:{callback:v=>'$'+v+'M'}}}}});
 }else{
  bcCumChart.data.labels=cumLabels;
  bcCumChart.data.datasets[0].data=cumLow;bcCumChart.data.datasets[1].data=cumBase;bcCumChart.data.datasets[2].data=cumHigh;
  bcCumChart.update();
 }
 simRecompute();
}
function simRecompute(){
 const spotsEl=$('simSpots'),cpmEl=$('simCpm'),audEl=$('simAud');if(!spotsEl)return;
 const T=L();
 const spots=+spotsEl.value,cpm=+cpmEl.value,aud=+audEl.value;
 const perMatch=spots*cpm*2;
 $('simOut').textContent=fmtM(perMatch);
 $('simSpotsV').textContent=spots;
 $('simCpmV').textContent='$'+Math.round(cpm/1000)+'k';
 $('simAudV').textContent=(aud/1e6).toFixed(1)+'M';
}
function miniMatchSVG(g){const w=118,h=32,pad=4,fw=w-2*pad;
 const X=mn=>pad+(Math.max(0,Math.min(95,mn))/95)*fw;
 const heat=g.wbgt==null?'#94a3b8':(g.wbgt>=28?'#ff4d6d':(g.wbgt>=22?'#f6c945':'#2fb7d8'));
 const goals=parseGoalsT(g.gmin||'');
 const dots=goals.map(o=>`<circle cx="${X(o.m)}" cy="${o.team==='h'?11:21}" r="2.4" fill="#fff" stroke="rgba(0,0,0,.25)" stroke-width=".5"/>`).join('');
 return `<svg viewBox="0 0 ${w} ${h}" role="img"><rect width="${w}" height="${h}" rx="6" fill="${heat}" opacity=".8"/>
  <line x1="${X(22)}" y1="0" x2="${X(22)}" y2="${h}" stroke="#fff" stroke-width="1.3" stroke-dasharray="2 2" opacity=".85"/>
  <line x1="${X(67)}" y1="0" x2="${X(67)}" y2="${h}" stroke="#fff" stroke-width="1.3" stroke-dasharray="2 2" opacity=".85"/>
  ${dots}</svg>`;}
function renderMatchGrid(){
 const sorted=G.slice().sort((a,b)=>a.date<b.date?-1:(a.date>b.date?1:0));
 $('matchGrid').innerHTML=sorted.map(g=>`<div class="mcard" data-id="${g.id}" data-stage="${g.stage}" title="${g.home} ${g.hg}-${g.ag} ${g.away} · ${g.date}"><div class="mt">${flag(g.home)}${g.hg}-${g.ag}${flag(g.away)}</div>${miniMatchSVG(g)}</div>`).join('');
 $('matchGrid').querySelectorAll('.mcard').forEach(el=>{el.onclick=()=>{
  const id=el.dataset.id,st=el.dataset.stage;
  state.stage=st;fillStageSelect();fillMatchSelect(st);state.sel=id;$('selMatch').value=id;$('selStage').value=st;
  renderAnalysis();$('readbox').scrollIntoView({behavior:'smooth',block:'start'});
 };});
}
function renderVenueGrid(){
 const T=L();const by={};
 G.forEach(g=>{if(!g.venue)return;const e=by[g.venue]=by[g.venue]||{n:0,sum:0,cnt:0};e.n++;if(g.wbgt!=null){e.sum+=g.wbgt;e.cnt++;}});
 const arr=Object.entries(by).map(([venue,o])=>({venue,n:o.n,avg:o.cnt?o.sum/o.cnt:null})).sort((a,b)=>(b.avg==null?-1:b.avg)-(a.avg==null?-1:a.avg));
 $('venueGrid').innerHTML=arr.map(v=>{
  const heat=v.avg==null?'#94a3b8':(v.avg>=28?'#ff4d6d':(v.avg>=22?'#e7b53c':'#2fb7d8'));
  return `<div class="vtile" style="background:${heat}"><div class="vn">${v.venue}</div><div class="vw">${v.avg!=null?tU(v.avg,1):'—'}</div><div class="vc">${v.n} ${T.venueMatches}</div></div>`;
 }).join('');
 $('venueNote').innerHTML=badgeHTML('estimate')+' '+T.venueNote;
}
function renderUpdates(){$('updatesList').innerHTML=L().updates.map(u=>`<div class="up"><div class="ud">${u[0]}</div><div class="ut">${u[1]}</div><div class="up2">${u[2]}</div></div>`).join('');}

// ---------- static text + tabs ----------
function applyStatic(){
 document.querySelectorAll('[data-i18n]').forEach(el=>{el.innerHTML=L()[el.dataset.i18n];});
 document.querySelectorAll('.nn').forEach(e=>e.textContent=D.n);
 $('langBtn').textContent = state.lang==='en'?'ES':'EN';
 $('themeBtn').textContent = state.theme==='dark'?'☀':'☾';
 $('unitBtn').textContent = state.unit==='c'?'°F':'°C';
 $('moreBtn').textContent = state.more?L().moreHide:L().moreShow;
 $('moreWrap').style.display = state.more?'':'none';
 $('shareBtn').textContent = L().share;
 $('subUpdated').textContent = L().subUpdated(U,D.n);
 document.documentElement.lang=state.lang;
}
function showTab(t){state.tab=t;
 document.querySelectorAll('.tab').forEach(p=>p.classList.remove('on'));$('tab-'+t).classList.add('on');
 document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('on',b.dataset.t===t));
 if(t==='analysis')renderAnalysis(); if(t==='verdict')renderVerdict();
 if(t==='broadcast')renderBroadcast();
 if(t==='bracket')renderBracket(); if(t==='updates')renderUpdates();
 setTimeout(()=>{armReveal();document.querySelectorAll('#tab-'+t+' .reveal').forEach(e=>e.classList.add('in'));},50);
 window.scrollTo({top:0,behavior:'smooth'});}

// ---------- graphics ----------
function heroSVG(){const x=m=>30+(m/90)*640,w=(a,b)=>x(b)-x(a),es=state.lang==='es';
 const b1=es?'Pausa 1':'Break 1',b2=es?'Pausa 2':'Break 2',cap=es?'Comparamos los 10 minutos a cada lado de cada pausa':'We compare the 10 minutes on each side of every break';
 const mk=m=>`<rect x="${x(m)-2.5}" y="52" width="5" height="48" rx="2.5" fill="var(--gold)"/><text x="${x(m)}" y="55" text-anchor="middle" font-size="17">⚽</text>`;
 return `<svg class="hero-svg" viewBox="0 0 700 122" role="img">
  <rect x="${x(12)}" y="62" width="${w(12,22)}" height="26" rx="5" fill="rgba(100,116,139,.16)"/>
  <rect x="${x(22)}" y="62" width="${w(22,32)}" height="26" rx="5" fill="rgba(192,57,43,.15)"/>
  <rect x="${x(57)}" y="62" width="${w(57,67)}" height="26" rx="5" fill="rgba(100,116,139,.16)"/>
  <rect x="${x(67)}" y="62" width="${w(67,77)}" height="26" rx="5" fill="rgba(192,57,43,.15)"/>
  <rect x="30" y="70" width="640" height="10" rx="5" fill="var(--line)"/>
  <line x1="${x(45)}" y1="60" x2="${x(45)}" y2="90" stroke="var(--muted)" stroke-width="1" stroke-dasharray="3 3"/>
  ${mk(22)}${mk(67)}
  <text x="${x(22)}" y="38" text-anchor="middle" font-size="13" font-weight="800" fill="var(--ink)" font-family="Archivo">${b1}</text>
  <text x="${x(67)}" y="38" text-anchor="middle" font-size="13" font-weight="800" fill="var(--ink)" font-family="Archivo">${b2}</text>
  <text x="${x(22)}" y="114" text-anchor="middle" font-size="11" fill="var(--muted)" font-family="Archivo">~22'</text>
  <text x="${x(67)}" y="114" text-anchor="middle" font-size="11" fill="var(--muted)" font-family="Archivo">~67'</text>
  <text x="30" y="114" font-size="11" fill="var(--muted)" font-family="Archivo">0'</text>
  <text x="670" y="114" text-anchor="end" font-size="11" fill="var(--muted)" font-family="Archivo">90'</text>
  <text x="${x(45)}" y="114" text-anchor="middle" font-size="11" fill="var(--muted)" font-family="Archivo">HT</text>
  <circle class="pulsering" cx="${x(22)}" cy="76" r="9" fill="none" stroke="var(--red)" stroke-width="2"/>
  <circle class="pulsering" cx="${x(67)}" cy="76" r="9" fill="none" stroke="var(--red)" stroke-width="2" style="animation-delay:1.3s"/>
  <circle class="heroball" cx="30" cy="76" r="6" fill="var(--navy)" stroke="var(--gold)" stroke-width="1.5">
   <animate attributeName="cx" values="30;670;30" dur="9s" repeatCount="indefinite"/>
   <animate attributeName="cy" values="76;68;76;84;76" dur="1.15s" repeatCount="indefinite"/>
  </circle>
 </svg><div style="text-align:center;font-size:12.5px;color:var(--muted);margin-top:2px">${cap}</div>`;}
function pitchSVG(hp,hName,aName){const W=720,H=300,P=12,fw=W-2*P,div=P+(hp/100)*fw,cx=W/2,cy=H/2;
 const line=(a)=>`stroke="#ffffff" stroke-width="2" opacity="${a}" fill="none"`;
 return `<svg viewBox="0 0 ${W} ${H}" role="img">
  <defs><linearGradient id="pg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1f9d57"/><stop offset="1" stop-color="#16834a"/></linearGradient></defs>
  <rect x="${P}" y="${P}" width="${fw}" height="${H-2*P}" rx="12" fill="url(#pg)"/>
  ${[0,2,4,6,8,10].map(i=>`<rect x="${P+i*(fw/12)}" y="${P}" width="${fw/12}" height="${H-2*P}" fill="#ffffff" opacity="0.045"/>`).join('')}
  <rect x="${P}" y="${P}" width="${div-P}" height="${H-2*P}" rx="12" fill="#e7b53c" opacity="0.20"/>
  <rect x="${div}" y="${P}" width="${W-P-div}" height="${H-2*P}" fill="#0a1f44" opacity="0.20"/>
  <rect x="${P}" y="${P}" width="${fw}" height="${H-2*P}" rx="12" ${line(.85)}/>
  <line x1="${cx}" y1="${P}" x2="${cx}" y2="${H-P}" ${line(.8)}/>
  <circle cx="${cx}" cy="${cy}" r="46" ${line(.8)}/><circle cx="${cx}" cy="${cy}" r="3" fill="#fff" opacity=".8"/>
  <rect x="${P}" y="${cy-72}" width="78" height="144" ${line(.8)}/><rect x="${W-P-78}" y="${cy-72}" width="78" height="144" ${line(.8)}/>
  <rect x="${P}" y="${cy-34}" width="32" height="68" ${line(.8)}/><rect x="${W-P-32}" y="${cy-34}" width="32" height="68" ${line(.8)}/>
  <line x1="${div}" y1="${P}" x2="${div}" y2="${H-P}" stroke="#fff" stroke-width="3" stroke-dasharray="7 5"/>
  <rect x="${P+16}" y="${P+16}" width="104" height="48" rx="10" fill="#e7b53c"/>
  <text x="${P+16+52}" y="${P+16+34}" text-anchor="middle" font-size="27" font-weight="800" fill="#0a1f44" font-family="Saira Condensed">${Math.round(hp)}%</text>
  <rect x="${W-P-16-104}" y="${P+16}" width="104" height="48" rx="10" fill="#15336b"/>
  <text x="${W-P-16-52}" y="${P+16+34}" text-anchor="middle" font-size="27" font-weight="800" fill="#fff" font-family="Saira Condensed">${100-Math.round(hp)}%</text>
  <text x="${P+18}" y="${H-P-16}" font-size="14" fill="#fff" opacity=".95" font-weight="600" font-family="Archivo">${hName}</text>
  <text x="${W-P-18}" y="${H-P-16}" text-anchor="end" font-size="14" fill="#fff" opacity=".95" font-weight="600" font-family="Archivo">${aName}</text>
 </svg>`;}
function heatPitchSVG(avg,hotN,coolN){const W=720,H=300,P=12,fw=W-2*P,cx=W/2,cy=(P+(H-P-46))/2+ (P)/2;
 const top=P,bot=H-P-46,ph=bot-top;
 const xT=t=>P+((Math.max(15,Math.min(35,t))-15)/20)*fw;
 const line=a=>`stroke="#ffffff" stroke-width="2" opacity="${a}" fill="none"`;
 const mk=xT(avg),hot=xT(28),ccy=(top+bot)/2;
 const ticks=[15,20,25,30,35].map(t=>`<line x1="${xT(t)}" y1="${bot}" x2="${xT(t)}" y2="${bot+7}" stroke="var(--muted)" stroke-width="1.5"/><text x="${xT(t)}" y="${bot+26}" text-anchor="middle" font-size="13" fill="var(--muted)" font-family="Archivo">${tU(t,0)}</text>`).join('');
 return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="How hot the pitch feels">
  <defs><linearGradient id="heatg" x1="0" y1="0" x2="1" y2="0">
   <stop offset="0" stop-color="#2fb7d8"/><stop offset=".42" stop-color="#3fd18b"/><stop offset=".6" stop-color="#f6c945"/><stop offset=".78" stop-color="#ff8a3d"/><stop offset="1" stop-color="#ff2e5e"/></linearGradient></defs>
  <rect x="${P}" y="${top}" width="${fw}" height="${ph}" rx="12" fill="url(#heatg)"/>
  <rect x="${P}" y="${top}" width="${fw}" height="${ph}" rx="12" ${line(.8)}/>
  <line x1="${cx}" y1="${top}" x2="${cx}" y2="${bot}" ${line(.6)}/>
  <circle cx="${cx}" cy="${ccy}" r="42" ${line(.6)}/><circle cx="${cx}" cy="${ccy}" r="3" fill="#fff" opacity=".7"/>
  <rect x="${P}" y="${ccy-64}" width="70" height="128" ${line(.6)}/><rect x="${W-P-70}" y="${ccy-64}" width="70" height="128" ${line(.6)}/>
  <line x1="${hot}" y1="${top}" x2="${hot}" y2="${bot}" stroke="#fff" stroke-width="3" stroke-dasharray="7 5"/>
  <text x="${hot+8}" y="${top+22}" font-size="14" font-weight="800" fill="#fff" font-family="Saira Condensed">HOT ZONE →</text>
  <line x1="${mk}" y1="${top-2}" x2="${mk}" y2="${bot+2}" stroke="#0a1330" stroke-width="3"/>
  <rect x="${Math.max(P,Math.min(W-P-126,mk-63))}" y="${top-1}" width="126" height="34" rx="8" fill="#0a1330"/>
  <text x="${Math.max(P+63,Math.min(W-P-63,mk))}" y="${top+22}" text-anchor="middle" font-size="16" font-weight="800" fill="#fff" font-family="Saira Condensed">AVG ${tU(avg,1)}</text>
  ${ticks}
 </svg>`;}
function tugSVG(g){const W=720,pad=16,cx=W/2,span=cx-108,H=205,GOLD='#f6c945',GOLDT='#c98a00',NAVY='#3b6fd4',T=L();const m=g.mom;
 const cl=v=>Math.max(-50,Math.min(50,v)),X=v=>cx+(cl(v)/50)*span;
 function row(y,pre,post,lab){const xb=X(pre),xa=X(post);const col=post>0.5?GOLD:(post<-0.5?NAVY:'#94a3b8');
  return `<text x="${cx}" y="${y-22}" text-anchor="middle" font-size="12.5" font-weight="800" fill="var(--muted)" font-family="Archivo">${lab}</text>
   <line x1="${pad+74}" y1="${y}" x2="${W-pad-74}" y2="${y}" stroke="var(--line)" stroke-width="6" stroke-linecap="round"/>
   <line x1="${cx}" y1="${y-15}" x2="${cx}" y2="${y+15}" stroke="var(--muted)" stroke-width="2" stroke-dasharray="3 3"/>
   <line x1="${xb}" y1="${y}" x2="${xa}" y2="${y}" stroke="${col}" stroke-width="6" stroke-linecap="round" opacity=".5"/>
   <circle cx="${xb}" cy="${y}" r="7" fill="var(--card)" stroke="var(--muted)" stroke-width="2.5"/>
   <circle cx="${xa}" cy="${y}" r="16" fill="${col}"/><text x="${xa}" y="${y+5}" text-anchor="middle" font-size="15">⚽</text>`;}
 return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Momentum tug of war">
  <text x="${pad}" y="24" font-size="15" font-weight="800" fill="${NAVY}" font-family="Saira Condensed">◀ ${g.away.toUpperCase()}</text>
  <text x="${W-pad}" y="24" text-anchor="end" font-size="15" font-weight="800" fill="${GOLDT}" font-family="Saira Condensed">${g.home.toUpperCase()} ▶</text>
  ${row(88,m[0],m[1],T.tugB1)}
  ${row(160,m[2],m[3],T.tugB2)}
  <text x="${cx}" y="${H-4}" text-anchor="middle" font-size="12" fill="var(--muted)" font-family="Archivo">${T.tugKey}</text>
 </svg>`;}
function goalStripSVG(g){const W=720,pad=16,H=150,top=26,bot=104,fw=W-2*pad,cy=(top+bot)/2,GOLD='#f6c945',NAVY='#3b6fd4',T=L();
 const X=mn=>pad+(Math.max(0,Math.min(95,mn))/95)*fw;const goals=parseGoalsT(g.gmin);
 const brk=(mn,lab)=>`<line x1="${X(mn)}" y1="${top}" x2="${X(mn)}" y2="${bot}" stroke="#fff" stroke-width="2.5" stroke-dasharray="6 4" opacity=".9"/><text x="${X(mn)}" y="${top-8}" text-anchor="middle" font-size="12" font-weight="800" fill="var(--muted)" font-family="Archivo">${lab}</text>`;
 const ticks=[0,15,30,45,60,75,90].map(t=>`<text x="${X(t)}" y="${bot+20}" text-anchor="middle" font-size="12" fill="var(--muted)" font-family="Archivo">${t}'</text>`).join('');
 const balls=goals.map(o=>{const home=o.team==='h',x=X(o.m),y=home?top+20:bot-20,col=home?GOLD:NAVY;
   return `<circle cx="${x}" cy="${y}" r="13" fill="${col}" stroke="var(--card)" stroke-width="2"/><text x="${x}" y="${y+4}" text-anchor="middle" font-size="11" font-weight="800" fill="${home?'#5a4600':'#fff'}" font-family="Archivo">${o.m}</text>`;}).join('');
 return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="When the goals were scored">
  <defs><linearGradient id="gsp" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1f9d57"/><stop offset="1" stop-color="#16834a"/></linearGradient></defs>
  <rect x="${pad}" y="${top}" width="${fw}" height="${bot-top}" rx="10" fill="url(#gsp)"/>
  <line x1="${pad}" y1="${cy}" x2="${W-pad}" y2="${cy}" stroke="#fff" stroke-width="1.5" opacity=".35"/>
  ${brk(22,"22'")}${brk(67,"67'")}
  <text x="${pad+6}" y="${top+16}" font-size="11" fill="#fff" opacity=".85" font-family="Archivo">${g.home}</text>
  <text x="${pad+6}" y="${bot-8}" font-size="11" fill="#fff" opacity=".85" font-family="Archivo">${g.away}</text>
  ${balls}${ticks}
 </svg>`;}
function sankeySVG(rows){const T=L();
 const tiers=['us','marquee','other'].filter(t=>rows.some(r=>r.tier===t));
 const bands=['early','late','final'].filter(b=>rows.some(r=>r.band===b));
 if(!tiers.length||!bands.length)return `<div class="pitchprompt" style="padding:20px">${T.opt_all}</div>`;
 const tierTot={},bandTot={};
 tiers.forEach(t=>tierTot[t]=rows.filter(r=>r.tier===t).reduce((s,r)=>s+r.v,0));
 bands.forEach(b=>bandTot[b]=rows.filter(r=>r.band===b).reduce((s,r)=>s+r.v,0));
 const grand=rows.reduce((s,r)=>s+r.v,0)||1;
 const W=720,colX=[36,342,648],nodeW=26,unitH=180,gap=26,top=30;
 // stack() sizes each node from its share of unitH, but the real column
 // height (returned) already includes every gap + minimum-height floor, so
 // the caller can size the SVG to whatever the tallest column needs instead
 // of guessing a fixed height and clipping content that doesn't fit.
 function stack(items,totalMap){let y=top;const pos={};items.forEach(k=>{const h=Math.max(14,(totalMap[k]/grand)*unitH);pos[k]={y0:y,y1:y+h,h};y+=h+gap;});return {pos,bottom:y-gap};}
 const s1=stack(tiers,tierTot),s2=stack(bands,bandTot);
 const p1=s1.pos,p2=s2.pos;
 const totBottom=s1.bottom;
 const p3={total:{y0:top,y1:Math.max(top+14,totBottom),h:Math.max(14,totBottom-top)}};
 const H=Math.max(s1.bottom,s2.bottom,p3.total.y1)+26;
 const tierCol={us:'#ff4d6d',marquee:'#f6c945',other:'#5ea0ff'};
 const bandCol={early:'#94a3b8',late:'#2fe0d8',final:'#f6c945'};
 let paths='';const y1cur={},y2curIn={};
 tiers.forEach(t=>y1cur[t]=p1[t].y0);bands.forEach(b=>y2curIn[b]=p2[b].y0);
 tiers.forEach(t=>{bands.forEach(b=>{
  const r=rows.find(rr=>rr.tier===t&&rr.band===b);if(!r||!r.v)return;
  const h=Math.max(2,(r.v/grand)*unitH);
  const ys=y1cur[t],ye=ys+h;y1cur[t]=ye;
  const y2s=y2curIn[b],y2e=y2s+h;y2curIn[b]=y2e;
  const x0=colX[0]+nodeW,x1=colX[1],xm=(x0+x1)/2;
  paths+=`<path d="M${x0},${ys} C${xm},${ys} ${xm},${y2s} ${x1},${y2s} L${x1},${y2e} C${xm},${y2e} ${xm},${ye} ${x0},${ye} Z" fill="${tierCol[t]}" opacity=".5"/>`;
 });});
 let y3cur=p3.total.y0;
 bands.forEach(b=>{
  const h=Math.max(2,(bandTot[b]/grand)*unitH);
  const ys=p2[b].y0,ye=p2[b].y1;
  const y3s=y3cur,y3e=y3s+h;y3cur=y3e;
  const x0=colX[1]+nodeW,x1=colX[2],xm=(x0+x1)/2;
  paths+=`<path d="M${x0},${ys} C${xm},${ys} ${xm},${y3s} ${x1},${y3s} L${x1},${y3e} C${xm},${y3e} ${xm},${ye} ${x0},${ye} Z" fill="${bandCol[b]}" opacity=".45"/>`;
 });
 function nodeRect(x,pos,label,fill,val){return `<rect x="${x}" y="${pos.y0}" width="${nodeW}" height="${pos.h}" rx="4" fill="${fill}"/><text x="${x+nodeW/2}" y="${pos.y0-14}" text-anchor="middle" font-size="11" font-weight="800" fill="var(--ink)" font-family="Archivo">${label}</text><text x="${x+nodeW/2}" y="${pos.y0-3}" text-anchor="middle" font-size="10" fill="var(--muted)" font-family="Archivo">${val}</text>`;}
 let nodes='';
 tiers.forEach(t=>nodes+=nodeRect(colX[0],p1[t],T.tierLabels[t].replace(/^\S+\s/,''),tierCol[t],fmtM(tierTot[t])));
 bands.forEach(b=>nodes+=nodeRect(colX[1],p2[b],T.bandLabels[b],bandCol[b],fmtM(bandTot[b])));
 nodes+=nodeRect(colX[2],p3.total,T.sankeyTotal,'var(--navy)',fmtM(grand));
 return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Revenue flow">${paths}${nodes}</svg>`;
}
function meterSVG(p){const pos=isNaN(p)?0:Math.max(0,Math.min(1,1-p/0.3));const cx=40+pos*620;const T=L();
 const col=p<0.05?'#15924a':(p<0.15?'#e7b53c':'#94a3b8');
 return `<svg class="hero-svg" viewBox="0 0 700 64" role="img"><defs><linearGradient id="mg" x1="0" x2="1"><stop offset="0" stop-color="#94a3b8"/><stop offset=".55" stop-color="#e7b53c"/><stop offset="1" stop-color="#15924a"/></linearGradient></defs>
  <rect x="40" y="26" width="620" height="10" rx="5" fill="url(#mg)" opacity=".5"/>
  <circle cx="${cx}" cy="31" r="11" fill="${col}" stroke="var(--card)" stroke-width="3"/>
  <text x="40" y="56" font-size="12" fill="var(--muted)" font-family="Archivo">${T.meterLeft}</text>
  <text x="660" y="56" text-anchor="end" font-size="12" fill="var(--muted)" font-family="Archivo">${T.meterRight}</text></svg>`;}

// ---------- HOME ----------
function renderHome(){
 const T=L();$('heroArt').innerHTML=heroSVG();const goals=G.reduce((s,g)=>s+g.hg+g.ag,0);
 const wb=G.filter(g=>g.wbgt!=null).map(g=>g.wbgt);
 const k=[[T.kMatches,D.n],[T.kGoals,goals],[T.kGpm,(goals/D.n).toFixed(2)],[T.kWbgt,tU(wb.reduce((a,b)=>a+b,0)/wb.length,1)]];
 $('homeKpis').innerHTML=k.map(([l,v])=>`<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
 const o1=aggBreak(G,'b1'),o2=aggBreak(G,'b2');const pre=o1.g[0]+o2.g[0],post=o1.g[1]+o2.g[1];
 const pB=baselineP(post,pre+post);
 $('homeVerdict').innerHTML=`<div class="vlabel">${T.hvLabel}</div><div class="vbig">${T.hvBig}</div><p>${T.hvBody(pre,post)}</p>`;
 $('homeFinding').innerHTML=T.hvFinding(D.n);
 countScope('homeKpis');
}

// ---------- ANALYSIS ----------
const L19=['0','5','10','15','20','25','30','35','40','45','50','55','60','65','70','75','80','85','90+'];
const breakLines={id:'bl',afterDraw(c){if(!['cDist','cHist','cSub'].includes(c.canvas.id))return;const xs=c.scales.x,ys=c.scales.y;if(!xs)return;
 [[22/5,'B1'],[67/5,'B2']].forEach(([pos,lab])=>{const px=xs.left+(pos/18)*(xs.right-xs.left);const x=c.ctx;x.save();
  x.strokeStyle=RED;x.setLineDash([5,4]);x.lineWidth=1.5;x.beginPath();x.moveTo(px,ys.top);x.lineTo(px,ys.bottom);x.stroke();
  x.fillStyle=RED;x.font='800 10px Archivo';x.fillText(lab,px+3,ys.top+11);x.restore();});}};
Chart.register(breakLines);
function chartColor(){return state.theme==='dark'?'#aebbd6':'#64748b';}
function PB(){return state.theme==='dark'?'#5ea0ff':'#0a1f44';}
const dataLabels={id:'dl',afterDatasetsDraw(c){if(c.config.type!=='bar'||(c.data.labels||[]).length>6)return;const x=c.ctx;x.save();x.font='800 12px Archivo';x.fillStyle=state.theme==='dark'?'#e9eefb':'#101a30';
 const horiz=c.options.indexAxis==='y';
 c.data.datasets.forEach((ds,di)=>{c.getDatasetMeta(di).data.forEach((el,i)=>{const v=ds.data[i];if(v==null)return;
   x.textAlign=horiz?'left':'center';x.textBaseline=horiz?'middle':'bottom';
   x.fillText(c.canvas.id==='cXg'?v+'%':v, el.x+(horiz?7:0), el.y+(horiz?0:-5));});});x.restore();}};
Chart.register(dataLabels);

function makeAnalysis(){
 const T=L();Chart.defaults.color=chartColor();Chart.defaults.borderColor=state.theme==='dark'?'rgba(148,163,184,.18)':'rgba(148,163,184,.22)';Chart.defaults.font={family:'Archivo, sans-serif',size:12};
 distChart=new Chart($('cDist'),{type:'bar',data:{labels:L19,datasets:[{data:[],backgroundColor:PB(),borderRadius:4}]},
  options:{plugins:{legend:{display:false}},scales:{x:{title:{display:true,text:T.distX}},y:{beginAtZero:true,title:{display:true,text:T.distY}}}}});
 histChart=new Chart($('cHist'),{type:'line',data:{labels:L19,datasets:[
   {label:T.histLeg1,data:[],borderColor:GREY,backgroundColor:'rgba(148,163,184,.14)',fill:true,tension:.35,pointRadius:0,borderWidth:2.5},
   {label:T.histLeg2,data:[],borderColor:RED,backgroundColor:'rgba(192,57,43,.12)',fill:true,tension:.35,pointRadius:0,borderWidth:3.5}]},
  options:{plugins:{legend:{position:'bottom',labels:{boxWidth:18,font:{size:13}}}},scales:{x:{title:{display:true,text:T.histX}},y:{beginAtZero:true,title:{display:true,text:T.histY}}}}});
 const X=D.xgwin,pc=v=>Math.round(v[1]/v[0]*100);
 xgChart=new Chart($('cXg'),{type:'bar',data:{labels:[T.metrics[0],state.lang==='es'?'Ocasiones (xG)':'Chances (xG)',state.lang==='es'?'Remates':'Shots'],datasets:[{data:[pc(X.goals),pc(X.xg),pc(X.shots)],backgroundColor:[PB(),VIOLET,GREY],borderRadius:5}]},
  options:{indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{beginAtZero:true,suggestedMax:120,ticks:{callback:v=>v+'%'},title:{display:true,text:T.xgX}}}}});
 const M=D.momagg;
 momChart=new Chart($('cMom'),{type:'bar',data:{labels:T.momLabels,datasets:[{data:[M.ontop[0],M.gainer[0]],backgroundColor:[PB(),GREY],borderRadius:5}]},
  options:{indexAxis:'y',plugins:{legend:{display:false},title:{display:true,text:T.momTitle(M.postgoals),color:chartColor(),font:{size:11}}},scales:{x:{beginAtZero:true,suggestedMax:M.postgoals,ticks:{precision:0}}}}});
 $('momKpis').innerHTML=[['±'+M.swing,T.momK[0]],[M.flip+'%',T.momK[1]],[M.postgoals,T.momK[2]]].map(([v,l])=>`<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
 $('xgNote').innerHTML=T.xgNote(X.n);
 $('momNote').innerHTML=T.momNote(M);
 const S=D.subagg,per=(b,n)=>b.map(v=>+(v/n).toFixed(2));
 const sds=[{label:T.subLeg26,data:per(S.y2026.buckets,S.y2026.n),backgroundColor:PB(),borderRadius:4}];
 if(S.y2022)sds.push({type:'line',label:T.subLeg22,data:per(S.y2022.buckets,S.y2022.n),borderColor:GOLD,backgroundColor:'transparent',tension:.35,pointRadius:0,borderWidth:3});
 subChart=new Chart($('cSub'),{type:'bar',data:{labels:L19,datasets:sds},options:{plugins:{legend:{position:'bottom'}},scales:{x:{title:{display:true,text:T.distX}},y:{beginAtZero:true,title:{display:true,text:state.lang==='es'?'cambios por partido':'subs per match'}}}}});
 $('subNote').innerHTML=T.subNote(S.y2026);
 const W=D.welfare;
 welChart=new Chart($('cWel'),{type:'bar',data:{labels:T.welAxis,datasets:[
   {label:T.welLeg()[0],data:[W.hot.ev,W.hot.late],backgroundColor:RED,borderRadius:5},
   {label:T.welLeg()[1],data:[W.cool.ev,W.cool.late],backgroundColor:GREY,borderRadius:5}]},
  options:{plugins:{legend:{position:'bottom'}},scales:{y:{beginAtZero:true,title:{display:true,text:state.lang==='es'?'por partido':'per game'}}}}});
 $('welKpis').innerHTML=[[W.perMatch,T.welK[0]],[W.latePct+'%',T.welK[1]],[W.hot.ev+' v '+W.cool.ev,T.welK[2]]].map(([v,l])=>`<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
 $('welNote').innerHTML=T.welNote(W);
 // heat vs total goals (tournament-wide scatter)
 const hs=G.filter(g=>g.wbgt!=null).map(g=>({x:(state.unit==='f'?+toF(g.wbgt).toFixed(1):g.wbgt),y:g.hg+g.ag,hot:g.wbgt>=28}));
 const nH=hs.length,mX=hs.reduce((s,p)=>s+p.x,0)/nH,mY=hs.reduce((s,p)=>s+p.y,0)/nH;
 let sxy=0,sxx=0,syy=0;hs.forEach(p=>{sxy+=(p.x-mX)*(p.y-mY);sxx+=(p.x-mX)*(p.x-mX);syy+=(p.y-mY)*(p.y-mY);});
 const slope=sxx?sxy/sxx:0,intc=mY-slope*mX,rr=(sxx&&syy)?sxy/Math.sqrt(sxx*syy):0;
 const xsAll=hs.map(p=>p.x),xmn=Math.min.apply(null,xsAll),xmx=Math.max.apply(null,xsAll);
 const xlab=(state.lang==='es'?'sensación térmica':'real-feel heat')+' ('+(state.unit==='f'?'°F':'°C')+')';
 heatScatter=new Chart($('cHeatScatter'),{data:{datasets:[
   {type:'line',label:'trend',data:[{x:xmn,y:intc+slope*xmn},{x:xmx,y:intc+slope*xmx}],borderColor:GOLD,borderWidth:2.5,borderDash:[6,4],pointRadius:0,fill:false},
   {type:'scatter',label:'match',data:hs,pointBackgroundColor:hs.map(p=>p.hot?'rgba(255,77,109,.72)':'rgba(94,160,255,.72)'),pointBorderColor:hs.map(p=>p.hot?'#ff4d6d':'#5ea0ff'),pointBorderWidth:1,pointRadius:5,pointHoverRadius:7}
 ]},options:{plugins:{legend:{display:false}},scales:{x:{type:'linear',title:{display:true,text:xlab},grid:{display:false}},y:{beginAtZero:true,title:{display:true,text:state.lang==='es'?'goles en el partido':'goals in the match'},ticks:{precision:0}}}}});
 const hotG=G.filter(g=>g.wbgt!=null&&g.wbgt>=28),coolG=G.filter(g=>g.wbgt!=null&&g.wbgt<28),avgG=a=>a.length?(a.reduce((s,g)=>s+g.hg+g.ag,0)/a.length).toFixed(2):'0';
 $('heatScatterLegend').innerHTML=T.heatScatterLeg().map((l,i)=>`<span class="hl"><span class="dot" style="background:${['#5ea0ff','#ff4d6d'][i]}"></span>${l}</span>`).join('');
 $('heatScatterNote').innerHTML=T.heatScatterNote(rr,avgG(hotG),avgG(coolG),nH);
 renderMatchGrid();
 renderVenueGrid();
}
const STORDER=['group','R32','R16','QF','SF','3P','F'];
function matchesForStage(st){
 if(!st||st==='all')return G;
 if(st==='group')return G.filter(g=>g.stage==='group');
 if(st==='ko')return G.filter(g=>g.stage!=='group');
 return G.filter(g=>g.stage===st);}
function fillMatchSelect(stageFilter){const T=L();const sel=$('selMatch');
 const pool=matchesForStage(stageFilter===undefined?state.stage:stageFilter);
 const by={};pool.forEach(g=>{(by[g.stage]=by[g.stage]||[]).push(g);});
 let html=`<option value="all">${T.opt_all}</option>`;
 STORDER.forEach(st=>{const arr=by[st];if(!arr||!arr.length)return;
  html+=`<optgroup label="${T.stageLabels[st]||st}">`+arr.map(g=>`<option value="${g.id}">${flag(g.home)} ${g.home} ${g.hg}-${g.ag} ${g.away} ${flag(g.away)} · ${g.date}</option>`).join('')+`</optgroup>`;});
 sel.innerHTML=html;
 const keep=pool.some(g=>g.id===state.sel);
 if(!keep)state.sel='all';
 sel.value=state.sel;}
function fillStageSelect(){const T=L();const sel=$('selStage');if(!sel)return;const present=new Set(G.map(g=>g.stage));
 let html=`<option value="all">${T.st_all}</option>`;
 if(present.has('group'))html+=`<option value="group">${T.stageLabels.group}</option>`;
 if([...present].some(s=>s!=='group'))html+=`<option value="ko">${T.st_ko}</option>`;
 STORDER.forEach(st=>{if(st!=='group'&&present.has(st))html+=`<option value="${st}">${T.stageLabels[st]}</option>`;});
 sel.innerHTML=html;sel.value=state.stage;}

function renderAnalysis(){
 const T=L();
 if(!made.analysis){makeAnalysis();made.analysis=true;}
 const gs=selGames(),single=state.sel!=='all';
 $('scopeLbl').textContent=single?T.scope1:gs.length+' '+(state.lang==='es'?'partidos':'matches');
 const wbg=gs.filter(g=>g.wbgt!=null).map(g=>g.wbgt);
 if(wbg.length){const avg=(wbg.reduce((a,b)=>a+b,0)/wbg.length).toFixed(1);const hotN=wbg.filter(w=>w>=28).length,coolN=wbg.length-hotN;
  $('heatPitch').innerHTML=heatPitchSVG(avg,hotN,coolN);
  $('heatLegend').innerHTML=T.heatLeg().map((l,i)=>`<span class="hl"><span class="dot" style="background:${['#2fb7d8','#f6c945','#ff2e5e'][i]}"></span>${l}</span>`).join('');
  $('heatNote').innerHTML=T.heatNote(tU(avg,1),tU(28,0),hotN,coolN,gs.length);}
 const names=T.metrics,keys=['g','c','s','lc','cm'];
 function bcard(w,label){const o=aggBreak(gs,w);
  const rows=keys.map((k,i)=>{const b=o[k][0],a=o[k][1],d=a-b,cl=d<0?'dn':(d>0?'up':'fl'),sg=d>0?'+':'';
    return `<tr><td>${names[i]}</td><td>${b}</td><td>${a}</td><td class="delta ${cl}">${sg}${d}</td></tr>`;}).join('');
  const c=conf(binom(o.g[1],o.g[0]+o.g[1]));const pill=`<span class="pill ${pillC[c.lvl]}">${c.t}</span>`;
  return `<div class="bcard"><div class="bhead">${label} ${pill}</div><div class="bsub">${T.beforeAfter}</div>
   <table><thead><tr><th>${state.lang==='es'?'Métrica':'Metric'}</th><th>${T.before}</th><th>${T.after}</th><th>Δ</th></tr></thead><tbody>${rows}</tbody></table></div>`;}
 $('breaks').innerHTML=bcard('b1',"Break 1 · ~22'")+bcard('b2',"Break 2 · ~67'");
 if(single&&gs[0].possH!=null){const g0=gs[0],hp=g0.possH/(g0.possH+g0.possA)*100;
  $('pitchWrap').innerHTML=pitchSVG(hp,flag(g0.home)+' '+g0.home,g0.away+' '+flag(g0.away));}
 else if(single){const g0=gs[0];$('pitchWrap').innerHTML=`<div class="pitchprompt">${T.possNoData(g0.home,g0.away)}</div>`;}
 else $('pitchWrap').innerHTML=`<div class="pitchprompt">${T.possPrompt}</div>`;
 const buckets=new Array(19).fill(0);gs.forEach(g=>parseGoals(g.gmin).forEach(m=>{let bi=m>90?18:Math.floor((m-0.0001)/5);if(bi<0)bi=0;if(bi>18)bi=18;buckets[bi]++;}));
 distChart.data.datasets[0].data=buckets;distChart.update();
 $('distNote').textContent=single?T.distNoteSingle:T.distNoteAll;
 if(single){$('goalStrip').style.display='';$('goalStrip').innerHTML=goalStripSVG(gs[0]);}else{$('goalStrip').style.display='none';}
 const norm=(a,t)=>t?a.map(x=>+(x/t*100).toFixed(2)):a.map(_=>0);const tot=buckets.reduce((a,b)=>a+b,0);
 const b18=norm(D.base['2018'].buckets,D.base['2018'].tot),b22=norm(D.base['2022'].buckets,D.base['2022'].tot);
 histChart.data.datasets[0].data=b18.map((v,i)=>+((v+b22[i])/2).toFixed(2));
 histChart.data.datasets[1].data=norm(buckets,tot);
 histChart.data.datasets[1].label=single?'2026 · '+gs[0].home:T.histLeg2;
 histChart.update();
 const o1=aggBreak(gs,'b1'),o2=aggBreak(gs,'b2'),preS=o1.g[0]+o2.g[0],postS=o1.g[1]+o2.g[1],nS=preS+postS;
 const totG=gs.reduce((s,g)=>s+g.hg+g.ag,0),winG=preS+postS;
 $('breaksRecon').innerHTML=single?T.recon1(totG,winG,parseGoals(gs[0].gmin).sort((a,b)=>a-b)):T.reconAll(totG,winG,gs.length);
 const bt=baseTot();
 let v=T.histBase(bt.post,bt.pre+bt.post,Math.round(bt.post/(bt.pre+bt.post)*100));
 if(nS<6)v+=T.histFew(nS);
 else{const p2=postS/nS,p1=bt.post/(bt.pre+bt.post),pp=(bt.post+postS)/(bt.pre+bt.post+nS),se=Math.sqrt(pp*(1-pp)*(1/(bt.pre+bt.post)+1/nS)),z=(p2-p1)/se,p=2*(1-0.5*(1+erf(Math.abs(z)/Math.SQRT2)));
  v+=T.histSel(postS,nS,Math.round(p2*100),p2<p1,conf(p).t);}
 $('histVerdict').innerHTML=v;
 let momTxt='';if(single&&gs[0].mom)momTxt=T.momTxt(gs[0].mom,gs[0].home);
 $('readbox').innerHTML=single?T.readSingle(gs[0],momTxt):T.readAll(preS,postS);
 if(single&&gs[0].mom){$('momChartBox').style.display='none';$('momKpis').style.display='none';$('momTug').style.display='';
   $('momTug').innerHTML=tugSVG(gs[0]);$('momNote').innerHTML=T.tugNote(gs[0]);}
 else{$('momChartBox').style.display='';$('momKpis').style.display='';$('momTug').style.display='none';
   $('momNote').innerHTML=(single?T.wideNote(D.n):'')+T.momNote(D.momagg)+'<div class="scopebanner" style="margin-top:10px">'+T.eloNote+'</div>';}
 const wide=single?T.wideNote(D.n):'';
 $('xgNote').innerHTML=wide+T.xgNote(D.xgwin.n);
 $('subNote').innerHTML=wide+T.subNote(D.subagg.y2026);
 $('welNote').innerHTML=wide+T.welNote(D.welfare);
}

// ---------- VERDICT ----------
function renderVerdict(){
 const T=L();
 const o1=aggBreak(G,'b1'),o2=aggBreak(G,'b2');const pre=o1.g[0]+o2.g[0],post=o1.g[1]+o2.g[1];
 const pWithin=binom(post,pre+post);
 const hot=G.filter(g=>g.wbgt>=28);const h1=aggBreak(hot,'b1'),h2=aggBreak(hot,'b2');const hpre=h1.g[0]+h2.g[0],hpost=h1.g[1]+h2.g[1];const pHot=binom(hpost,hpre+hpost);
 const pBase=baselineP(post,pre+post);
 const any=[pWithin,pHot,pBase].some(p=>!isNaN(p)&&p<0.05);
 $('vEyebrow').textContent=T.vEyebrow(D.n);
 $('vAnswer').textContent=any?T.vYes:T.vNo;
 const ps=[pWithin,pHot,pBase].filter(x=>!isNaN(x));$('vMeter').innerHTML=meterSVG(ps.length?Math.min.apply(null,ps):NaN);
 $('vLead').textContent=T.vLead(pre,post,D.n);
 const pill=p=>{const c=conf(p);return `<span class="vstat ${vstatC[c.lvl]}">${c.t}</span>`;};
 const tests=[[T.vt1,T.vt1n(pre,post),pWithin],[T.vt2(),T.vt2n(hpre,hpost,hot.length),pHot],[T.vt3,T.vt3n(Math.round(post/(pre+post)*100)),pBase]];
 $('vTests').innerHTML=tests.map(([n,num,p])=>`<div class="vtest"><div class="vname">${n}<div class="vnum">${num}</div></div>${pill(p)}</div>`).join('');
 $('vTrend').textContent=T.vTrend;$('vNext').textContent=T.vNext;
 drawTracker();
}
function drawTracker(){const T=L();
 const gs=[...G].sort((a,b)=>(a.date<b.date?-1:a.date>b.date?1:0));
 let pre=0,post=0;const xs=[],share=[],up=[],lo=[],ref=[];
 gs.forEach((g,idx)=>{pre+=g.b1.g[0]+g.b2.g[0];post+=g.b1.g[1]+g.b2.g[1];const nT=pre+post;
   if(nT>=8){const p=post/nT,se=Math.sqrt(p*(1-p)/nT);xs.push(idx+1);share.push(+(p*100).toFixed(1));up.push(+Math.min(100,(p+1.96*se)*100).toFixed(1));lo.push(+Math.max(0,(p-1.96*se)*100).toFixed(1));ref.push(50);}});
 const cur=share.length?Math.round(share[share.length-1]):50;
 if(trackChart)trackChart.destroy();Chart.defaults.color=chartColor();
 trackChart=new Chart($('cTrack'),{type:'line',data:{labels:xs,datasets:[
   {label:'up',data:up,borderColor:'transparent',backgroundColor:'rgba(94,160,255,.16)',pointRadius:0,fill:'+1',tension:.3},
   {label:'lo',data:lo,borderColor:'transparent',backgroundColor:'rgba(94,160,255,.16)',pointRadius:0,fill:false,tension:.3},
   {label:'ref',data:ref,borderColor:GREY,borderWidth:1.5,borderDash:[5,4],pointRadius:0,fill:false},
   {label:'share',data:share,borderColor:PB(),borderWidth:2.6,pointRadius:0,tension:.3,fill:false}
 ]},options:{plugins:{legend:{display:false}},scales:{x:{title:{display:true,text:state.lang==='es'?'partidos jugados':'matches played'},ticks:{maxTicksLimit:8}},y:{suggestedMin:25,suggestedMax:75,title:{display:true,text:state.lang==='es'?'% de goles tras la pausa':'% of break goals after the break'},ticks:{callback:v=>v+'%'}}}}});
 $('trackNote').innerHTML=T.trackNote(cur,D.n);
}

// ---------- GLOSSARY ----------
function renderGlossary(){$('glossList').innerHTML=L().gloss.map(([t,d])=>`<div class="gloss"><div class="gt">${t}</div><div class="gd">${d}</div></div>`).join('');}

// ---------- SURVEY ----------
let answers={};
const SB_URL="__SBURL__",SB_KEY="__SBKEY__";
const sbOn=()=>SB_URL.slice(0,4)==="http"&&SB_KEY.length>20;
const sbHdr=()=>({'apikey':SB_KEY,'Authorization':'Bearer '+SB_KEY,'Content-Type':'application/json'});
let voted=false;try{voted=localStorage.getItem('ce_voted')==='1';}catch(e){}
function setSubmit(){const b=$('submitSurvey');if(!b)return;if(voted){b.disabled=true;b.textContent=L().svThanks;}else{b.disabled=false;b.textContent=L().sv_submit;}}
function buildSurvey(){const T=L();
 $('survey').innerHTML=T.sq.map(q=>`<div class="q"><div class="qt">${q.q}</div><div class="opts" data-q="${q.id}">${q.o.map((o,i)=>`<button data-v="${i}">${o}</button>`).join('')}</div></div>`).join('');
 $('survey').querySelectorAll('.opts').forEach(r=>r.querySelectorAll('button').forEach(b=>b.onclick=()=>{if(voted)return;r.querySelectorAll('button').forEach(x=>x.classList.remove('sel'));b.classList.add('sel');answers[r.dataset.q]=+b.dataset.v;}));
 answers={};setSubmit();tallyFn();}
const loadR=()=>{try{return JSON.parse(localStorage.getItem('ce_survey')||'[]');}catch(e){return[];}};
const saveR=r=>{try{localStorage.setItem('ce_survey',JSON.stringify(r));}catch(e){}};
function localAgg(r){const m={};r.forEach(x=>['b1feel','b2feel'].forEach(q=>{if(x[q]!=null){const k=q+':'+x[q];m[k]=(m[k]||0)+1;}}));return m;}
async function tallyFn(){const T=L();
 if(sbOn()){try{const rows=await fetch(SB_URL+'/rest/v1/poll_counts?select=id,n',{headers:sbHdr()}).then(r=>r.json());
   const m={};(rows||[]).forEach(x=>m[x.id]=x.n);const tot=[0,1,2,3].reduce((s,i)=>s+(m['b1feel:'+i]||0),0);
   $('tally').textContent=T.svTally(tot);drawSurveyCounts(m);}catch(e){$('tally').textContent=T.svTally(0);}}
 else{const r=loadR();$('tally').textContent=T.svTally(r.length);if(r.length)drawSurveyCounts(localAgg(r));}}
function drawSurveyCounts(m){const T=L();$('surveyChartBox').style.display='block';
 const c=[0,1,2,3].map(i=>[m['b1feel:'+i]||0,m['b2feel:'+i]||0]);
 if(surveyChart)surveyChart.destroy();Chart.defaults.color=chartColor();
 surveyChart=new Chart($('cSurvey'),{type:'bar',data:{labels:T.svFeel,datasets:[{label:T.svAfter1,data:c.map(x=>x[0]),backgroundColor:GREY,borderRadius:4},{label:T.svAfter2,data:c.map(x=>x[1]),backgroundColor:GREEN,borderRadius:4}]},
  options:{plugins:{legend:{position:'bottom'}},scales:{y:{beginAtZero:true,ticks:{precision:0}}}}});
 drawPerception(m);}
function drawPerception(m){const T=L();const el=$('perception');if(!el)return;
 const more=(m['b1feel:0']||0)+(m['b2feel:0']||0),less=(m['b1feel:1']||0)+(m['b2feel:1']||0),noc=(m['b1feel:2']||0)+(m['b2feel:2']||0);
 if(more+less+noc<8){el.innerHTML=T.perceptionLow;return;}
 const noticed=more+less,morePct=noticed?Math.round(more/noticed*100):0;
 const o1=aggBreak(G,'b1'),o2=aggBreak(G,'b2'),pre=o1.g[0]+o2.g[0],post=o1.g[1]+o2.g[1];
 el.innerHTML=T.perception(morePct,noticed,pre,post);}

// ---------- refresh on toggle ----------
function fullRefresh(){
 applyStatic();renderHome();renderGlossary();buildSurvey();fillMatchSelect();fillStageSelect();
 if(distChart){distChart.destroy();histChart.destroy();xgChart.destroy();momChart.destroy();subChart.destroy();welChart.destroy();if(heatScatter)heatScatter.destroy();made.analysis=false;}
 if(bcStageChart){bcStageChart.destroy();bcStageChart=null;} if(bcScatter){bcScatter.destroy();bcScatter=null;}
 if(state.tab==='analysis')renderAnalysis(); if(state.tab==='verdict')renderVerdict();
 if(state.tab==='broadcast')renderBroadcast();
 if(state.tab==='bracket')renderBracket(); if(state.tab==='updates')renderUpdates();
}

// ---------- wiring ----------
$('nav').querySelectorAll('button').forEach(b=>b.onclick=()=>{showTab(b.dataset.t);$('menu').classList.remove('open');$('navToggle').setAttribute('aria-expanded','false');});
$('navToggle').onclick=()=>{const open=$('menu').classList.toggle('open');$('navToggle').setAttribute('aria-expanded',open?'true':'false');};
$('selMatch').onchange=function(){state.sel=this.value;renderAnalysis();};
$('selStage').onchange=function(){state.stage=this.value;fillMatchSelect(state.stage);renderAnalysis();};
$('segHeat').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('segHeat').querySelectorAll('button').forEach(x=>x.classList.remove('on'));b.classList.add('on');state.heat=b.dataset.h;renderAnalysis();});
$('segScenario').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('segScenario').querySelectorAll('button').forEach(x=>x.classList.remove('on'));b.classList.add('on');state.scenario=b.dataset.sc;renderBroadcast();});
['simSpots','simCpm','simAud'].forEach(id=>{const el=$(id);if(el)el.oninput=simRecompute;});
$('moreBtn').onclick=()=>{state.more=!state.more;$('moreWrap').style.display=state.more?'':'none';$('moreBtn').textContent=state.more?L().moreHide:L().moreShow;if(state.more&&histChart){histChart.resize();xgChart.resize();momChart.resize();}};
$('langBtn').onclick=()=>{state.lang=state.lang==='en'?'es':'en';fullRefresh();};
$('themeBtn').onclick=()=>{state.theme=state.theme==='dark'?'light':'dark';document.body.classList.toggle('dark',state.theme==='dark');fullRefresh();};
$('unitBtn').onclick=()=>{state.unit=state.unit==='c'?'f':'c';fullRefresh();};
$('shareBtn').onclick=()=>{const T=L();const o1=aggBreak(G,'b1'),o2=aggBreak(G,'b2');const pre=o1.g[0]+o2.g[0],post=o1.g[1]+o2.g[1];
 const txt=T.shareText($('vAnswer').textContent||'',pre,post,D.n);const b=$('shareBtn');
 const done=()=>{b.textContent=T.shareDone;setTimeout(()=>b.textContent=T.share,2000);};
 if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(txt).then(done,done);}else{done();}};
$('submitSurvey').onclick=async()=>{const T=L();const choices=Object.keys(answers).map(k=>k+':'+answers[k]);
 if(!choices.length)return;
 if(sbOn()){const b=$('submitSurvey');b.disabled=true;
   try{const res=await fetch(SB_URL+'/rest/v1/rpc/vote',{method:'POST',headers:sbHdr(),body:JSON.stringify({choices})});if(!res.ok)throw 0;
     voted=true;try{localStorage.setItem('ce_voted','1');}catch(e){}setSubmit();tallyFn();}
   catch(e){b.disabled=false;b.textContent=T.svErr;setTimeout(setSubmit,2500);}}
 else{const r=loadR();r.push(Object.assign({ts:new Date().toISOString()},answers));saveR(r);voted=true;try{localStorage.setItem('ce_voted','1');}catch(e){}setSubmit();tallyFn();}};

// ---------- init ----------
document.body.classList.toggle('dark',state.theme==='dark');
applyStatic();renderHome();renderGlossary();buildSurvey();fillMatchSelect();fillStageSelect();armReveal();
</script>
</body></html>"""

LINKEDIN=os.environ.get("CE_LINKEDIN","https://www.linkedin.com/in/rdflopez/")
BASEURL=os.environ.get("CE_BASEURL","https://rograph.github.io/cooling-economy").rstrip("/")
OGIMAGE=(BASEURL+"/" if BASEURL else "")+"cooling_economy_card.png"
FAVICON="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>%E2%9A%BD</text></svg>"
# Shared-survey backend defaults (publishable key is browser-safe; protected by row-level security)
SB_URL=os.environ.get("CE_SB_URL","https://ooinullcvyctuquijyjv.supabase.co").rstrip("/")
SB_KEY=os.environ.get("CE_SB_KEY","sb_publishable_cn0TpE-30PM5agXBFBMhgg_tDlv3oW6")
html=(HTML.replace("__DATA__",json.dumps(DATA)).replace("__UPDATED__",DATA["updated"]).replace("__LINKEDIN__",LINKEDIN)
      .replace("__OGIMAGE__",OGIMAGE).replace("__BASEURL__",BASEURL or "").replace("__FAVICON__",FAVICON)
      .replace("__SBURL__",SB_URL).replace("__SBKEY__",SB_KEY))
open(OUT,"w",encoding="utf-8").write(html)
left=[t for t in ("__DATA__","__UPDATED__","__LINKEDIN__","__OGIMAGE__","__BASEURL__","__FAVICON__","__SBURL__","__SBKEY__") if t in html]
print("wrote",OUT,len(html),"bytes; games:",N,"; unresolved:",left)

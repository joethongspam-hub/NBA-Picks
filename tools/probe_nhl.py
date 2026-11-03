"""Probe: NHL feeds (gamelog, roster, injuries, DK props) and team odds format for NBA/NFL/NHL."""
import json, re, requests
from collections import Counter
from datetime import datetime, timedelta, timezone
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
SITE = "https://site.api.espn.com/apis/site/v2/sports"
CORE = "https://sports.core.api.espn.com/v2/sports"
COMMON = "https://site.web.api.espn.com/apis/common/v3/sports"
out = {}
def j(u, **p):
    try:
        r = S.get(u, params=p, timeout=20); return r.status_code, r.json()
    except Exception as e: return None, repr(e)
day = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y%m%d")
# --- NHL
st, sb = j(f"{SITE}/hockey/nhl/scoreboard", dates=day)
evs = sb.get("events", []) if isinstance(sb, dict) else []
out["nhl_events"] = [(e["id"], e["shortName"], e["status"]["type"]["state"]) for e in evs]
if evs:
    comp = evs[0]["competitions"][0]
    out["nhl_scoreboard_odds"] = comp.get("odds")
    tid = comp["competitors"][0]["team"]["id"]
    _, ro = j(f"{SITE}/hockey/nhl/teams/{tid}/roster")
    ath = ro.get("athletes", [])
    out["nhl_roster_shape"] = "grouped" if ath and "items" in ath[0] else "flat"
    flat = [a for g in ath for a in g.get("items", [])] if out["nhl_roster_shape"] == "grouped" else ath
    out["nhl_positions"] = Counter((a.get("position") or {}).get("abbreviation") for a in flat)
    sk = next(a for a in flat if (a.get("position") or {}).get("abbreviation") in ("C", "LW", "RW", "W", "F"))
    gk = next(a for a in flat if (a.get("position") or {}).get("abbreviation") == "G")
    season = int(day[:4]) + (1 if int(day[4:6]) >= 8 else 0)
    for kind, a in (("skater", sk), ("goalie", gk)):
        _, gl = j(f"{COMMON}/hockey/nhl/athletes/{a['id']}/gamelog", season=season)
        ev0 = None
        try:
            for stt in gl.get("seasonTypes", []):
                for c in stt.get("categories", []):
                    if c.get("events"): ev0 = c["events"][0]; break
                if ev0: break
        except Exception: pass
        out[f"nhl_{kind}_gamelog"] = {"name": a.get("displayName"), "labels": gl.get("labels"), "names": gl.get("names"),
                                      "seasonTypes": [s.get("displayName") for s in gl.get("seasonTypes", [])],
                                      "event_sample": ev0, "events_meta_sample": next(iter((gl.get("events") or {}).values()), None)}
    pid = evs[0]["id"]
    _, pb = j(f"{CORE}/hockey/leagues/nhl/events/{pid}/competitions/{pid}/odds/100/propBets", limit=1000)
    if isinstance(pb, dict):
        out["nhl_prop_types"] = Counter((it.get("type") or {}).get("name") for it in pb.get("items", []))
        out["nhl_prop_has_odds"] = sum(1 for it in pb.get("items", []) if it.get("odds"))
        out["nhl_prop_sample"] = (pb.get("items") or [None])[0]
_, inj = j(f"{SITE}/hockey/nhl/injuries")
out["nhl_injuries_top"] = list(inj.keys()) if isinstance(inj, dict) else inj
out["nhl_injury_sample"] = ((inj.get("injuries") or [{}])[0].get("injuries") or [None])[0] if isinstance(inj, dict) else None
# --- team odds format per sport (scoreboard + core odds item)
for sport, lg in (("basketball", "nba"), ("football", "nfl"), ("hockey", "nhl")):
    _, sb2 = j(f"{SITE}/{sport}/{lg}/scoreboard", **({"dates": day} if lg != "nfl" else {}))
    e = next((x for x in sb2.get("events", []) if x["status"]["type"]["state"] == "pre"), (sb2.get("events") or [None])[0])
    if not e: continue
    o = (e["competitions"][0].get("odds") or [None])[0]
    _, core = j(f"{CORE}/{sport}/leagues/{lg}/events/{e['id']}/competitions/{e['id']}/odds")
    item = (core.get("items") or [None])[0] if isinstance(core, dict) else None
    if item:
        item = {k: v for k, v in item.items() if k not in ("links",)}
    _, summ = j(f"{SITE}/{sport}/{lg}/summary", event=e["id"])
    pc = (summ.get("pickcenter") or [None])[0] if isinstance(summ, dict) else None
    out[f"{lg}_odds"] = {"event": e["shortName"], "scoreboard_odds": o, "core_item": item, "pickcenter": pc}
open("probe.json", "w").write(json.dumps(out, indent=1, default=str))
print("done")

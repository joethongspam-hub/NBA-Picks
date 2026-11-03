import json, re, requests
from collections import defaultdict
from datetime import datetime, timedelta, timezone
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
day = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y%m%d")
sb = S.get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard", params={"dates": day}, timeout=20).json()
out = {"now": datetime.now(timezone.utc).isoformat(), "games": []}
for ev in sb.get("events", []):
    st = ev["status"]["type"]
    g = {"id": ev["id"], "name": ev["shortName"], "state": st["state"], "detail": st.get("shortDetail"), "start": ev["date"]}
    if st["state"] == "in" or (st["state"] == "post" and len(out["games"]) < 1):
        base = f"https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events/{ev['id']}/competitions/{ev['id']}/odds"
        odds = S.get(base, timeout=20).json()
        g["providers"] = [(it.get("provider", {}).get("id"), it.get("provider", {}).get("name")) for it in odds.get("items", [])]
        pb = S.get(base + "/200/propBets", params={"limit": 1000}, timeout=20).json()
        g["status200"] = "ok" if pb.get("items") is not None else str(pb)[:200]
        items = pb.get("items", [])
        g["count"] = pb.get("count"); g["pages"] = pb.get("pageCount")
        grp = defaultdict(list)
        for it in items:
            t = it["type"]["name"]
            if t not in ("Total Points", "Total Rebounds", "Total Assists"): continue
            m = re.search(r"athletes/(\d+)", it["athlete"]["$ref"]); grp[(m.group(1), t)].append(it)
        g["group_sizes"] = sorted({len(v) for v in grp.values()})
        upd = sorted({it.get("lastUpdated") for v in grp.values() for it in v})
        g["lastUpdated_range"] = [upd[0], upd[-1]] if upd else None
        g["samples"] = [{"athlete": k[0], "type": k[1], "items": [{"am": it["odds"].get("american"), "total": it["odds"].get("total"),
                          "current": it.get("current"), "open": it.get("open"), "upd": it.get("lastUpdated")} for it in v]}
                        for k, v in list(grp.items())[:4]]
        # athlete names for samples
        for smp in g["samples"]:
            try:
                a = S.get(f"https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/athletes/{smp['athlete']}", timeout=10).json()
                smp["name"] = a.get("displayName")
            except Exception: pass
    out["games"].append(g)
open("probe.json", "w").write(json.dumps(out, indent=1, default=str))

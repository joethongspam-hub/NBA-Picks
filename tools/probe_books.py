import json, requests
from collections import Counter
from datetime import datetime, timedelta, timezone
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
SITE = "https://site.api.espn.com/apis/site/v2/sports"; CORE = "https://sports.core.api.espn.com/v2/sports"
out = {}
day = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y%m%d")
for sport, lg in (("basketball", "nba"), ("hockey", "nhl"), ("football", "nfl")):
    sb = S.get(f"{SITE}/{sport}/{lg}/scoreboard", params={} if lg == "nfl" else {"dates": day}, timeout=20).json()
    ev = next((e for e in sb.get("events", []) if e["status"]["type"]["state"] == "pre"), None)
    if not ev: out[lg] = "no pregame event"; continue
    eid = ev["id"]; base = f"{CORE}/{sport}/leagues/{lg}/events/{eid}/competitions/{eid}/odds"
    od = S.get(base, params={"limit": 50}, timeout=20).json()
    provs = [((it.get("provider") or {}).get("id"), (it.get("provider") or {}).get("name")) for it in od.get("items", [])]
    res = {"event": ev["shortName"], "providers": provs, "propBets": {}}
    for pid in sorted({str(p[0]) for p in provs if p[0]} | {"100", "37", "38", "41", "45", "58", "59", "1002", "1004", "2000", "25", "40"}):
        r = S.get(f"{base}/{pid}/propBets", params={"limit": 200}, timeout=20)
        try: j = r.json()
        except Exception: j = {}
        items = j.get("items", []) if isinstance(j, dict) else []
        res["propBets"][pid] = {"status": r.status_code, "count": j.get("count") if isinstance(j, dict) else None,
                                "with_odds": sum(1 for it in items if it.get("odds")),
                                "provider": (items[0].get("provider") or {}).get("$ref", "")[-40:] if items else None,
                                "types": Counter((it.get("type") or {}).get("name") for it in items).most_common(4)}
    out[lg] = res
open("probe.json", "w").write(json.dumps(out, indent=1, default=str))

"""One-off probe: does ESPN's core API expose player prop lines for NBA/NFL games?"""
import json, requests
from datetime import datetime, timedelta, timezone

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"
CORE = "https://sports.core.api.espn.com/v2/sports"
SITE = "https://site.api.espn.com/apis/site/v2/sports"
out = {"run": datetime.now(timezone.utc).isoformat(), "leagues": {}}


def get(url, **params):
    try:
        r = S.get(url, params=params, timeout=20)
        return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:300])
    except Exception as e:
        return None, repr(e)


for sport, league in (("basketball", "nba"), ("football", "nfl")):
    info = {"events": []}
    dates = [None]
    if league == "nba":
        today = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%Y%m%d")
        dates = [today]
    st, sb = get(f"{SITE}/{sport}/{league}/scoreboard", **({"dates": dates[0]} if dates[0] else {}))
    events = (sb or {}).get("events", []) if isinstance(sb, dict) else []
    info["scoreboard_status"] = st
    info["n_events"] = len(events)
    for ev in events[:1]:
        eid = ev["id"]
        e = {"id": eid, "name": ev.get("shortName"), "status": ev.get("status", {}).get("type", {}).get("description")}
        st, odds = get(f"{CORE}/{sport}/leagues/{league}/events/{eid}/competitions/{eid}/odds", limit=50)
        e["odds_status"] = st
        provs = []
        if isinstance(odds, dict):
            for it in odds.get("items", []):
                p = it.get("provider") or {}
                provs.append({"id": p.get("id"), "name": p.get("name"),
                              "has_propBets_ref": "propBets" in json.dumps(it)[:100000]})
        e["providers"] = provs
        tried = {str(p["id"]) for p in provs if p.get("id")} | {"100"}
        e["propBets"] = {}
        for pid in sorted(tried):
            st, pb = get(f"{CORE}/{sport}/leagues/{league}/events/{eid}/competitions/{eid}/odds/{pid}/propBets", limit=1000)
            rec = {"status": st}
            if isinstance(pb, dict):
                items = pb.get("items", [])
                for page in range(2, (pb.get("pageCount") or 1) + 1):
                    _, more = get(f"{CORE}/{sport}/leagues/{league}/events/{eid}/competitions/{eid}/odds/{pid}/propBets", limit=1000, page=page)
                    if isinstance(more, dict):
                        items += more.get("items", [])
                if pid == "100" and not out.get(f"raw_{league}"):
                    out[f"raw_{league}"] = items
                rec["count"] = pb.get("count", len(items))
                rec["pageCount"] = pb.get("pageCount")
                rec["sample"] = items[:3]
                types = {}
                for it in items:
                    t = (it.get("type") or {}).get("name") or (it.get("type") or {}).get("id") or "?"
                    types[t] = types.get(t, 0) + 1
                rec["types"] = dict(sorted(types.items(), key=lambda kv: -kv[1]))
            else:
                rec["body"] = str(pb)[:200]
            e["propBets"][pid] = rec
        info["events"].append(e)
    out["leagues"][league] = info

open("probe.json", "w").write(json.dumps(out, indent=1, default=str))
for lg, info in out["leagues"].items():
    for e in info["events"]:
        print(lg, e["name"], e["status"], [(k, v.get("status"), v.get("count")) for k, v in e["propBets"].items()])

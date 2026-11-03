"""Probe: can a browser page fetch ESPN live data (CORS)? What does the live box score look like?"""
import json, requests
from datetime import datetime, timedelta, timezone
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
ORIGIN = "https://joethongspam-hub.github.io"
out = {}
day = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y%m%d")
sb = S.get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard", params={"dates": day}, timeout=20).json()
ev = sb["events"][0]["id"] if sb.get("events") else None
out["event"] = ev
urls = {
    "scoreboard": f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={day}",
    "summary": f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={ev}",
    "propBets": f"https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events/{ev}/competitions/{ev}/odds/100/propBets?limit=5",
}
out["cors"] = {}
for k, u in urls.items():
    r = S.get(u, headers={"Origin": ORIGIN}, timeout=20)
    out["cors"][k] = {"status": r.status_code, "acao": r.headers.get("Access-Control-Allow-Origin"),
                      "vary": r.headers.get("Vary")}
    o = S.options(u, headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"}, timeout=20)
    out["cors"][k]["preflight"] = {"status": o.status_code, "acao": o.headers.get("Access-Control-Allow-Origin")}
summ = S.get(urls["summary"], timeout=20).json()
bs = summ.get("boxscore", {})
out["status"] = (summ.get("header", {}).get("competitions", [{}])[0].get("status", {}))
out["box_keys"] = list(bs.keys())
pl = bs.get("players", [])
if pl:
    t = pl[0]
    out["team"] = t.get("team", {}).get("abbreviation")
    st = t.get("statistics", [{}])[0]
    out["labels"] = st.get("labels"); out["names"] = st.get("names") or st.get("keys")
    out["athlete_sample"] = st.get("athletes", [])[:2]
out["competitors"] = [(c.get("team", {}).get("abbreviation"), c.get("score"), c.get("homeAway"))
                      for c in summ.get("header", {}).get("competitions", [{}])[0].get("competitors", [])]
open("probe.json", "w").write(json.dumps(out, indent=1, default=str))
print(json.dumps(out["cors"], indent=1)); print(out["labels"])

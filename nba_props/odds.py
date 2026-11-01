"""Optional real sportsbook prop lines via The Odds API (the-odds-api.com).

Set ODDS_API_KEY to enable. Without it the app estimates the line a book would
post from the player's recent averages and labels it "est.".

Cost note: each event x market x region costs 1 credit. The free tier is 500
credits/month, so the default markets are kept to four.
"""
from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass

from .http import Http

API = "https://api.the-odds-api.com/v4/sports"
BASE = f"{API}/basketball_nba"
MARKET_TO_STAT = {
    "player_points": "PTS", "player_rebounds": "REB", "player_assists": "AST",
    "player_threes": "3PM", "player_steals": "STL", "player_blocks": "BLK",
    "player_turnovers": "TOV", "player_points_rebounds_assists": "PRA",
    "player_points_rebounds": "PR", "player_points_assists": "PA",
    "player_rebounds_assists": "RA", "player_blocks_steals": "STOCKS",
}
# Two markets x ~8 games/night x 30 nights ~= 480 credits: fits the 500/month free tier
# with one pull a day. Add markets if you upgrade.
DEFAULT_MARKETS = "player_points,player_rebounds"
USAGE: dict = {}


@dataclass
class PropLine:
    line: float
    over_price: int | None
    under_price: int | None
    books: int
    source: str = ""

    @property
    def label(self) -> str:
        return self.source or f"{self.books} books"


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def american_to_prob(p: int | None) -> float | None:
    if p is None:
        return None
    return 100 / (p + 100) if p > 0 else -p / (-p + 100)


def fetch_props(http: Http, api_key: str, home_names: dict[str, str],
                markets: str = DEFAULT_MARKETS, sport: str = "basketball_nba",
                market_map: dict | None = None) -> dict[tuple[str, str], PropLine]:
    """Return {(normalized player name, STAT): PropLine} for tonight's games.

    home_names maps normalized home-team display name -> ESPN game id, used only
    to restrict requests to games on our slate.
    """
    base = f"{API}/{sport}"
    market_map = market_map or MARKET_TO_STAT
    events = http.get_json(f"{base}/events", {"apiKey": api_key}, ttl=1800) or []
    out: dict[tuple[str, str], PropLine] = {}
    for ev in events:
        if norm_name((ev.get("home_team") or "x").split()[-1]) not in home_names:   # match on nickname ("LA" vs "Los Angeles")
            continue
        params = {"apiKey": api_key, "regions": "us", "markets": markets, "oddsFormat": "american"}
        sess = getattr(http, "session", None)
        if sess is not None:
            r = sess.get(f"{base}/events/{ev['id']}/odds", params=params, timeout=20)
            for h in ("x-requests-remaining", "x-requests-used", "x-requests-last"):
                if r.headers.get(h) is not None:
                    USAGE[h.replace("x-requests-", "")] = r.headers[h]
            if r.status_code in (401, 429):
                USAGE["error"] = f"HTTP {r.status_code}: {r.text[:200]}"
                break
            data = r.json() if r.ok else {}
        else:
            data = http.get_json(f"{base}/events/{ev['id']}/odds", params, ttl=1800) or {}
        # collect per (player, stat): lines and prices across books
        acc: dict[tuple[str, str], dict] = {}
        for bk in data.get("bookmakers", []):
            for mk in bk.get("markets", []):
                stat = market_map.get(mk.get("key"))
                if not stat:
                    continue
                for oc in mk.get("outcomes", []):
                    player = oc.get("description") or ""
                    if not player:
                        continue
                    if oc.get("point") is None:
                        if (oc.get("name") or "").lower() in ("yes", "no"):     # anytime-TD style market
                            oc = {**oc, "point": 0.5, "name": "Over" if oc["name"].lower() == "yes" else "Under"}
                        else:
                            continue
                    key = (norm_name(player), stat)
                    a = acc.setdefault(key, {"lines": [], "over": {}, "under": {}})
                    pt = float(oc["point"])
                    side = (oc.get("name") or "").lower()
                    if side == "over":
                        a["lines"].append(pt)
                        a["over"].setdefault(pt, []).append(int(oc["price"]))
                    elif side == "under":
                        a["under"].setdefault(pt, []).append(int(oc["price"]))
        for key, a in acc.items():
            if not a["lines"]:
                continue
            line = statistics.median_low(a["lines"])     # consensus line
            best_over = max(a["over"].get(line, []), default=None)
            best_under = max(a["under"].get(line, []), default=None)
            out[key] = PropLine(line, best_over, best_under, len(a["lines"]))
    return out

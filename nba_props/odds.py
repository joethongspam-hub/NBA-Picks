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
        # Per book, a player can have several points (main + alternates). The main
        # line is the point whose over/under prices are closest to even; then take
        # the consensus (median) of the books' main lines.
        per_book: dict[tuple[str, str], list[tuple[float, int | None, int | None]]] = {}
        for bk in data.get("bookmakers", []):
            book_sides: dict[tuple[str, str], dict[float, dict]] = {}
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
                    side = (oc.get("name") or "").lower()
                    if side not in ("over", "under"):
                        continue
                    key = (norm_name(player), stat)
                    book_sides.setdefault(key, {}).setdefault(float(oc["point"]), {})[side] = int(oc["price"])
            for key, pts in book_sides.items():
                two = {pt: sd for pt, sd in pts.items() if "over" in sd and "under" in sd}
                if two:
                    pt = min(two, key=lambda x: abs(american_to_prob(two[x]["over"]) - american_to_prob(two[x]["under"])))
                    per_book.setdefault(key, []).append((pt, two[pt]["over"], two[pt]["under"]))
                elif len(pts) == 1:                                   # one-sided (e.g. anytime TD)
                    pt, sd = next(iter(pts.items()))
                    per_book.setdefault(key, []).append((pt, sd.get("over"), sd.get("under")))
        for key, rows in per_book.items():
            line = statistics.median_low([r[0] for r in rows])
            at = [r for r in rows if r[0] == line]
            overs = [r[1] for r in at if r[1] is not None]
            unders = [r[2] for r in at if r[2] is not None]
            out[key] = PropLine(line, max(overs) if overs else None, max(unders) if unders else None, len(rows))
    return out

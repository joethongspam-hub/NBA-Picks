"""Free sportsbook prop lines from ESPN's core API (DraftKings, provider 100).

Endpoint: sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{id}/
          competitions/{id}/odds/{provider}/propBets
Each player prop arrives as two items (same athlete, same type, same line) with
no side label: the first is the OVER, the second the UNDER (verified against
DraftKings' milestone prices for the same players).
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from .http import Http
from .odds import PropLine, norm_name

CORE = "https://sports.core.api.espn.com/v2/sports"
PROVIDER = "100"            # DraftKings on ESPN (was ESPN BET = 58)

NBA_TYPES = {
    "Total Points": "PTS", "Total Rebounds": "REB", "Total Assists": "AST",
    "Total 3-Point Field Goals": "3PM", "Total Points and Rebounds": "PR",
    "Total Points and Assists": "PA", "Total Assists and Rebounds": "RA",
    "Total Points, Rebounds, and Assists": "PRA",
}
NFL_TYPES = {
    "Total Passing Yards (incl. overtime)": "PASS_YDS", "Total Pass Completions (incl. overtime)": "PASS_CMP",
    "Total Passing Touchdowns (incl. overtime)": "PASS_TD", "Total Passing Interceptions (incl. overtime)": "INT",
    "Total Passing Attempts (incl. overtime)": "PASS_ATT", "Total Rushing Yards (incl. overtime)": "RUSH_YDS",
    "Total Carries (incl. overtime)": "RUSH_ATT", "Total Receptions (incl. overtime)": "REC",
    "Total Receiving Yards (incl. overtime)": "REC_YDS",
    "Total Rushing Plus Receiving Yards (incl. overtime)": "RUSH_REC_YDS",
    "Anytime Touchdown Scorer": "ANY_TD",
}
ONE_SIDED = {"ANY_TD"}      # "yes" price only -> treat as OVER 0.5


def _num(v):
    m = re.match(r"\s*([-+]?\d+(?:\.\d+)?)", str(v if v is not None else ""))
    return float(m.group(1)) if m else None


def _american(it):
    a = ((it.get("odds") or {}).get("american") or {}).get("value")
    try:
        return int(str(a).replace("+", "")) if a not in (None, "", "EVEN") else (100 if a == "EVEN" else None)
    except ValueError:
        return None


def _line(it):
    o = it.get("odds") or {}
    v = _num((o.get("total") or {}).get("value"))
    if v is None:
        v = _num(((it.get("current") or {}).get("target") or {}).get("value"))
    return v


def fetch_espn_props(http: Http, game_ids: list[str], sport: str, league: str, types: dict,
                     id_to_name: dict[str, str]) -> dict[tuple[str, str], PropLine]:
    def one(eid):
        base = f"{CORE}/{sport}/leagues/{league}/events/{eid}/competitions/{eid}/odds/{PROVIDER}/propBets"
        items, page, pages = [], 1, 1
        while page <= pages and page <= 6:
            data = http.get_json(base, {"limit": 1000, "page": page}, ttl=900) or {}
            items += data.get("items", [])
            pages = data.get("pageCount") or 1
            page += 1
        return items

    out: dict[tuple[str, str], PropLine] = {}
    with ThreadPoolExecutor(6) as ex:
        for items in ex.map(one, game_ids):
            groups: dict[tuple[str, str], list] = {}
            for it in items:
                stat = types.get((it.get("type") or {}).get("name"))
                if not stat or not it.get("odds"):
                    continue
                m = re.search(r"athletes/(\d+)", (it.get("athlete") or {}).get("$ref", "") or "")
                if not m:
                    continue
                groups.setdefault((m.group(1), stat), []).append(it)
            for (aid, stat), its in groups.items():
                name = id_to_name.get(aid)
                if not name:
                    continue
                if stat in ONE_SIDED:
                    price = _american(its[0])
                    if price is not None:
                        out[(norm_name(name), stat)] = PropLine(0.5, price, None, 1)
                    continue
                if len(its) < 2:
                    continue
                over, under = its[0], its[1]
                lo, lu = _line(over), _line(under)
                if lo is None or lo != lu:
                    continue
                out[(norm_name(name), stat)] = PropLine(lo, _american(over), _american(under), 1)
    return out

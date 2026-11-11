"""Daily parlay builder + grading (shared by NBA, NFL, NHL).

Legs: the day's shown picks on real sportsbook lines with a positive edge (graded A-C),
at most one leg per game (so legs are close to independent), priced -250 to -101, model probability >= 60%.

For each combination:  hit = product of leg probabilities,  payout = product of decimal odds,
value (EV) = hit * payout - 1.  Three tickets:
  safe      3 legs, highest hit chance with EV > 0
  value     3 legs, highest EV with hit >= 15%
  longshot  4-5 legs, highest EV with hit >= 5%
"""
from __future__ import annotations

import itertools
import json
from datetime import datetime
from pathlib import Path

TICKETS = [
    ("safe", "Safest", (3,), lambda t: t["ev"] > 0, lambda t: t["hit"]),
    ("value", "Best value", (3,), lambda t: t["hit"] >= 0.15, lambda t: t["ev"]),
    ("longshot", "Long shot", (4, 5), lambda t: t["hit"] >= 0.05, lambda t: t["ev"]),
]


def dec(price) -> float:
    p = int(price)
    return 1 + (p / 100 if p > 0 else 100 / -p)


def american(d: float) -> int:
    return int(round((d - 1) * 100)) if d >= 2 else int(round(-100 / (d - 1)))


def _leg(p: dict) -> dict:
    keep = ("game_id", "game", "player", "player_id", "team", "opp", "stat", "side", "line", "price",
            "prob", "edge", "grade", "line_source", "books", "projection", "dist")
    return {k: p.get(k) for k in keep}


def candidates(picks: list[dict], started: set[str], min_prob: float = 0.60) -> list[dict]:
    out, seen = [], set()
    for p in sorted(picks, key=lambda p: -p.get("edge", 0)):
        if p.get("locked") or p["game_id"] in started or p.get("line_source") in ("est.", None):
            continue
        if p.get("grade") not in ("A", "B", "C") or p.get("edge", 0) < 0.03:
            continue
        try:
            pr = int(p["price"])
        except (TypeError, ValueError):
            continue
        # Minus-money legs with a 60%+ model probability only: in the Oct 31 - Nov 6 replay,
        # plus-money legs hit 40% (model overrates long shots) vs 63% for minus-money legs.
        if not -250 <= pr < 0 or p.get("prob", 0) < min_prob:
            continue
        k = (p["player_id"], p["stat"], p["side"])
        if k not in seen:
            seen.add(k)
            out.append(p)
    # keep the 4 best legs per game, 24 overall: plenty for the search
    per_game: dict[str, int] = {}
    pool = []
    for p in out:
        if per_game.get(p["game_id"], 0) < 4:
            per_game[p["game_id"]] = per_game.get(p["game_id"], 0) + 1
            pool.append(p)
    return pool[:24]


def _ticket(legs) -> dict:
    hit, pay = 1.0, 1.0
    for l in legs:
        hit *= l["prob"]
        pay *= dec(l["price"])
    return {"legs": [_leg(l) for l in legs], "hit": round(hit, 4), "payout": round(pay, 2),
            "odds": american(pay), "ev": round(hit * pay - 1, 3)}


def build(picks: list[dict], started: set[str], separate: bool = True, min_prob: float = 0.60) -> dict:
    pool = candidates(picks, started, min_prob)
    best: dict[str, dict] = {}
    used: set = set()
    for key, label, sizes, ok, score in TICKETS:
        if separate and best:      # no player appears on more than one ticket
            taken = {l["player_id"] for t in best.values() for l in t["legs"]}
            pool = [p for p in pool if p["player_id"] not in taken]
        top = None
        for n in sizes:
            if len(pool) < n:
                continue
            for combo in itertools.combinations(pool, n):
                if len({l["game_id"] for l in combo}) < n or len({l["player_id"] for l in combo}) < n:
                    continue
                sig = frozenset((l["player_id"], l["stat"], l["side"]) for l in combo)
                if sig in used:                       # each ticket must be different
                    continue
                t = _ticket(combo)
                if t["ev"] <= 0 or not ok(t):
                    continue
                if top is None or score(t) > score(top):
                    top = t
        if top:
            best[key] = {**top, "type": key, "label": label}
            used.add(frozenset((l["player_id"], l["stat"], l["side"]) for l in top["legs"]))
    return best


def every_game(picks: list[dict], started: set[str], slate: list[str] | None = None,
               min_prob: float = 0.60) -> dict | None:
    """One leg from every game that hasn't started: the most likely qualifying leg in each game.
    Falls back to the game's best positive-edge minus-money leg on a real line; games with
    nothing usable are left out (and listed)."""
    strict, loose = {}, {}
    for p in picks:
        if p.get("locked") or p["game_id"] in started or p.get("line_source") in ("est.", None):
            continue
        if p.get("grade") not in ("A", "B", "C") or p.get("edge", 0) < 0.03:
            continue
        try:
            pr = int(p["price"])
        except (TypeError, ValueError):
            continue
        if not -250 <= pr < 0:
            continue
        g = p["game_id"]
        if p.get("prob", 0) >= min_prob and (g not in strict or p["prob"] > strict[g]["prob"]):
            strict[g] = p
        if g not in loose or p["prob"] > loose[g]["prob"]:
            loose[g] = p
    legs = [strict.get(g) or loose[g] for g in sorted(loose, key=lambda g: -(strict.get(g) or loose[g])["prob"])]
    if len(legs) < 2:
        return None
    t = _ticket(legs)
    open_games = [g for g in (slate or []) if g not in started]
    missing = [g for g in open_games if g not in loose]
    return {**t, "type": "allgames", "label": "One per game", "missing": missing,
            "games_total": len(open_games) or len(legs)}


def double_up(picks: list[dict], started: set[str], exclude: set | None = None,
              kind: str = "double", label: str = "Double up") -> dict | None:
    """A ticket paying close to even money with the highest model hit chance: one leg priced
    -115..-101, or two legs from different games whose combined odds land between -115 and +120.
    Legs: graded picks (they already pass every rule) on real lines, priced -400..-101."""
    pool, seen = [], set()
    for p in picks:
        if p.get("locked") or p["game_id"] in started or p.get("line_source") in ("est.", None):
            continue
        if p.get("grade") not in ("A", "B", "C"):
            continue
        try:
            pr = int(p["price"])
        except (TypeError, ValueError):
            continue
        k = (p["player_id"], p["stat"], p["side"])
        if exclude and p["player_id"] in exclude:
            continue
        if -400 <= pr <= -101 and k not in seen:
            seen.add(k)
            pool.append(p)
    lo, hi = dec(-115), dec(120)
    best = None
    options = [(p,) for p in pool] + [c for c in itertools.combinations(pool, 2)
                                      if c[0]["game_id"] != c[1]["game_id"] and c[0]["player_id"] != c[1]["player_id"]]
    for legs in options:
        t = _ticket(legs)
        if not lo <= t["payout"] <= hi or t["ev"] <= 0:
            continue
        if best is None or (t["hit"], -abs(t["payout"] - 2)) > (best["hit"], -abs(best["payout"] - 2)):
            best = t
    return {**best, "type": kind, "label": label} if best else None


DOUBLES = [("double", "Double up"), ("double2", "Double up #2")]


def update(hist_dir, key: str, picks: list[dict], started: set[str], now: datetime,
           all_games: bool = False, slate: list[str] | None = None, min_prob: float = 0.60,
           doubles: int = 1) -> list[dict]:
    """Keep a ticket once any of its games has started (locked); otherwise rebuild it.
    doubles=2 adds a second Double up made only from players not on the first one."""
    d = Path(hist_dir) / "parlays"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{key}.json"
    prior = {t["type"]: t for t in (json.loads(f.read_text()) if f.exists() else [])}
    fresh = build(picks, started, min_prob=min_prob)
    if all_games:
        ag = every_game(picks, started, slate, min_prob)
        if ag:
            fresh["allgames"] = ag
    taken: set = set()
    for k, label in DOUBLES[:doubles]:
        p = prior.get(k)
        if p and any(l["game_id"] in started for l in p["legs"]):
            du = p                                    # locked: keep it, and keep its players off the next one
        else:
            du = double_up(picks, started, exclude=taken, kind=k, label=label)
            if du:
                fresh[k] = du
        if du:
            taken |= {l["player_id"] for l in du["legs"]}
    out = []
    for k, label, *_ in DOUBLES[:doubles] + TICKETS + ([("allgames", "One per game")] if all_games else []):
        p = prior.get(k)
        if p and any(l["game_id"] in started for l in p["legs"]):
            out.append({**p, "locked": True})
        elif k in fresh:
            out.append({**fresh[k], "made": now.isoformat()})
    if out:
        f.write_text(json.dumps(out, indent=1))
    return out


def grade(hist_dir, graded: list[dict]) -> dict:
    """Grade saved tickets from graded leg results. Pushes/voids drop out of the ticket."""
    d = Path(hist_dir) / "parlays"
    res = {(str(r.get("date")), r["player_id"], r["stat"], r["side"]): r for r in graded}
    rows = []
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        if f.name == "results.json":
            continue
        for t in json.loads(f.read_text()):
            outs = [res.get((f.stem, l["player_id"], l["stat"], l["side"])) for l in t["legs"]]
            legs = [{**l, "result": (o or {}).get("result"), "actual": (o or {}).get("actual")} for l, o in zip(t["legs"], outs)]
            if any(o and o["result"] == "LOSS" for o in outs):
                r, pay = "LOSS", 0.0
            elif all(o and o["result"] in ("WIN", "PUSH", "VOID") for o in outs):
                live = [l for l, o in zip(t["legs"], outs) if o["result"] == "WIN"]
                if live:
                    pay = 1.0
                    for l in live:
                        pay *= dec(l["price"])
                    r = "WIN"
                else:
                    r, pay = "PUSH", 1.0
            else:
                r, pay = None, None
            rows.append({**t, "date": f.stem, "legs": legs, "result": r,
                         "profit": round(pay - 1, 2) if r in ("WIN", "LOSS") else 0.0})
    done = [x for x in rows if x["result"] in ("WIN", "LOSS")]
    by = {}
    types = [d for d in DOUBLES if any(x["type"] == d[0] for x in rows)] + TICKETS + \
        ([("allgames", "One per game")] if any(x["type"] == "allgames" for x in rows) else [])
    for k, label, *_ in types:
        g = [x for x in done if x["type"] == k]
        by[k] = {"label": label, "w": sum(x["result"] == "WIN" for x in g), "l": sum(x["result"] == "LOSS" for x in g),
                 "units": round(sum(x["profit"] for x in g), 2)}
    return {"by_type": by, "recent": sorted(rows, key=lambda x: x["date"], reverse=True)[:15]}

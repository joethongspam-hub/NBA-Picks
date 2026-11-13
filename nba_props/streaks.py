"""Hot streaks: stat thresholds a player has cleared in every one of his last 5 and/or last 10 games.

Pure box-score data (this season's games only). Sportsbook lines play no part; today's line is attached
only as a reference when there is one.
"""
from __future__ import annotations

# stat -> (smallest threshold worth showing, label). Floors keep out trivial streaks like "1+ assist".
STREAK_STATS = {
    "PTS": (10, "points"), "REB": (5, "rebounds"), "AST": (4, "assists"), "3PM": (2, "threes"),
    "PRA": (20, "pts+reb+ast"), "PR": (15, "pts+reb"), "PA": (15, "pts+ast"), "RA": (8, "reb+ast"),
    "STL": (2, "steals"), "BLK": (2, "blocks"),
}


def player_streaks(logs: list, season: int) -> list[dict]:
    """logs newest first. For each stat: the highest whole-number threshold cleared in all of the last 5
    (t5) and last 10 (t10) games, and how many games in a row the player has cleared it."""
    games = [g for g in logs if g.season == season and (g.min or 0) > 0]
    out = []
    for stat, (floor, label) in STREAK_STATS.items():
        vals = [g.get(stat) for g in games]
        t5 = int(min(vals[:5])) if len(vals) >= 5 else None
        t10 = int(min(vals[:10])) if len(vals) >= 10 else None
        t5 = t5 if t5 is not None and t5 >= floor else None
        t10 = t10 if t10 is not None and t10 >= floor else None
        if t5 is None and t10 is None:
            continue
        streak = lambda t: None if t is None else next((i for i, v in enumerate(vals) if v < t), len(vals))
        run5, run10 = streak(t5), streak(t10)
        out.append({"stat": stat, "label": label, "t5": t5, "t10": t10, "run5": run5, "run10": run10,
                    "run": max(r for r in (run5, run10) if r is not None),
                    "last5": [int(v) for v in vals[:5]], "avg10": round(sum(vals[:10]) / len(vals[:10]), 1)})
    return out


def build(players, slate_teams: dict, injuries: dict, season: int, lines: dict | None = None) -> list[dict]:
    """slate_teams: team_id -> (game_id, game label, opponent abbr). Players ruled out are skipped."""
    rows = []
    for p in players:
        if p.team_id not in slate_teams:
            continue
        inj = injuries.get(p.id) or injuries.get(p.name)
        if inj and getattr(inj, "level", "") in ("OUT", "DOUBTFUL"):
            continue
        st = player_streaks(p.logs, season)
        if not st:
            continue
        for s in st:
            pl = (lines or {}).get((p.name, s["stat"]))
            if pl is not None and getattr(pl, "line", None) is not None:
                s["line"] = pl.line
                s["clears_line"] = (s["t10"] or s["t5"]) > pl.line
        gid, glabel, opp = slate_teams[p.team_id]
        rows.append({"player": p.name, "player_id": p.id, "team_id": p.team_id, "game_id": gid, "game": glabel,
                     "opp": opp, "status": getattr(inj, "status", "") if inj else "", "streaks": st,
                     "best": max(s["run"] for s in st), "tens": sum(s["t10"] is not None for s in st)})
    rows.sort(key=lambda r: (-r["tens"], -r["best"], r["player"]))
    return rows

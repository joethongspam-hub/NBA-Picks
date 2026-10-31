"""Daily pipeline: fetch -> project -> rank -> grade yesterday -> write report.

    python -m nba_props.main                 # today's slate (US/Eastern date)
    python -m nba_props.main --date 2026-11-02
    python -m nba_props.main --slate-only    # faster: skip non-playing teams
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .espn import Espn, season_for
from .http import Http
from .model import (DEFAULT_PROP_STATS, League, best_picks, build_profile, evaluate,
                    project_team)
from .odds import DEFAULT_MARKETS, fetch_props, norm_name
from .report import render

ET = ZoneInfo("America/New_York")


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def grade_history(hist_dir: Path, players_by_id: dict, today: str) -> dict:
    """Grade saved picks from earlier days using the game logs we just pulled."""
    results_path = hist_dir / "results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else {"graded": []}
    graded_keys = {(r["date"], r["player_id"], r["stat"], r["side"]) for r in results["graded"]}
    for f in sorted((hist_dir / "picks").glob("*.json")):
        day = f.stem
        if day >= today:
            continue
        for pk in json.loads(f.read_text()):
            key = (day, pk["player_id"], pk["stat"], pk["side"])
            if key in graded_keys:
                continue
            pl = players_by_id.get(pk["player_id"])
            if not pl:
                continue
            g = next((x for x in pl.logs if x.event_id == pk["game_id"]), None)
            if g is None:
                # never played (or not final yet) -> void after 2 days
                if (datetime.fromisoformat(today) - datetime.fromisoformat(day)).days >= 2:
                    results["graded"].append({**_slim(pk), "date": day, "actual": None, "result": "VOID"})
                    graded_keys.add(key)
                continue
            actual = g.get(pk["stat"])
            if actual == pk["line"]:
                res = "PUSH"
            elif (actual > pk["line"]) == (pk["side"] == "OVER"):
                res = "WIN"
            else:
                res = "LOSS"
            results["graded"].append({**_slim(pk), "date": day, "actual": actual, "result": res})
            graded_keys.add(key)
    results_path.write_text(json.dumps(results, indent=1))
    return results


def _slim(pk):
    keep = ("game_id", "game", "player", "player_id", "team", "opp", "stat", "side", "line",
            "line_source", "projection", "prob", "edge", "grade", "score")
    return {k: pk[k] for k in keep}


def summarize(results: dict) -> dict:
    out = {}
    for label, filt in (("all", lambda r: True), ("A", lambda r: r["grade"] == "A"),
                        ("B", lambda r: r["grade"] == "B"), ("C", lambda r: r["grade"] == "C")):
        rs = [r for r in results["graded"] if filt(r) and r["result"] in ("WIN", "LOSS")]
        w = sum(r["result"] == "WIN" for r in rs)
        out[label] = {"w": w, "l": len(rs) - w, "pct": round(w / len(rs), 3) if rs else None}
    recent = sorted(results["graded"], key=lambda r: r["date"], reverse=True)[:40]
    out["recent"] = recent
    return out


def run(date: str | None = None, out_dir: str = "site", cache_dir: str = ".cache",
        hist_dir: str = "history", slate_only: bool = False, stats: list[str] | None = None,
        odds_key: str | None = None, odds_markets: str = DEFAULT_MARKETS, http: Http | None = None):
    stats = stats or DEFAULT_PROP_STATS
    now_et = datetime.now(ET)
    day = datetime.fromisoformat(date).replace(tzinfo=ET) if date else now_et
    day_s = day.strftime("%Y-%m-%d")
    season = season_for(day)
    http = http or Http(cache_dir)
    espn = Espn(http)
    out, hist = Path(out_dir), Path(hist_dir)
    out.mkdir(parents=True, exist_ok=True)
    (hist / "picks").mkdir(parents=True, exist_ok=True)

    log(f"[1/6] Schedule for {day_s} (season {season})")
    games = espn.games(day.strftime("%Y%m%d"))
    teams = espn.teams()
    slate_ids = {t.id for g in games for t in (g.home, g.away)}
    pool_ids = slate_ids if slate_only else set(teams) | slate_ids

    log(f"[2/6] Injuries + rosters for {len(pool_ids)} teams")
    injuries = espn.injuries()
    players = []
    for tid in sorted(pool_ids):
        try:
            players += espn.roster(tid)
        except Exception as e:
            log(f"   roster {tid} failed: {e}")

    log(f"[3/6] Game logs for {len(players)} players")
    espn.load_logs(players, [season, season - 1], season)

    log("[4/6] Building profiles, defense-vs-position, projections")
    profiles = {p.id: pr for p in players if (pr := build_profile(p, season))}
    league = League(players, profiles, season)
    tts = [t for g in games for tid in (g.home.id, g.away.id) if (t := g.implied_total(tid))]
    slate_tt = sum(tts) / len(tts) if tts else 0.0

    lines = {}
    if odds_key and games:
        log("   Fetching sportsbook prop lines")
        try:
            lines = fetch_props(http, odds_key, {norm_name(g.home.name): g.id for g in games}, odds_markets)
        except Exception as e:
            log(f"   odds fetch failed, falling back to estimated lines: {e}")

    by_team = {}
    for p in players:
        by_team.setdefault(p.team_id, []).append(p)
    all_picks, game_info = [], []
    for g in games:
        game_projs = []
        for team, opp in ((g.home, g.away), (g.away, g.home)):
            game_projs += project_team(by_team.get(team.id, []), team.id, team.abbr, opp.id, opp.abbr,
                                       g, league, injuries, slate_tt, day)
        for pr in game_projs:
            all_picks += evaluate(pr, stats, lines, season)
        inj_list = []
        for team in (g.away, g.home):
            for p in by_team.get(team.id, []):
                i = injuries.get(p.id) or injuries.get(p.name)
                if i:
                    prof = profiles.get(p.id)
                    inj_list.append({"team": team.abbr, "player": p.name, "status": i.status,
                                     "level": i.level, "detail": i.detail,
                                     "min": round(prof.min_base, 1) if prof else 0})
        inj_list.sort(key=lambda x: (-x["min"]))
        game_info.append({
            "id": g.id, "label": g.label, "home": g.home.abbr, "away": g.away.abbr,
            "home_name": g.home.name, "away_name": g.away.name,
            "time": g.date.astimezone(ET).strftime("%I:%M %p ET").lstrip("0"), "status": g.status,
            "odds": g.odds_text, "total": g.total,
            "tt_home": round(g.implied_total(g.home.id), 1) if g.total else None,
            "tt_away": round(g.implied_total(g.away.id), 1) if g.total else None,
            "injuries": inj_list,
            "projections": sorted([{"player": pr.player.name, "team": pr.team_abbr, "min": round(pr.minutes, 1),
                                    "status": pr.status,
                                    **{s: round(pr.mean[s], 1) for s in ("PTS", "REB", "AST", "3PM", "PRA")}}
                                   for pr in game_projs], key=lambda x: -x["PRA"]),
        })

    top, by_game = best_picks(all_picks)
    log(f"[5/6] {len(all_picks)} props evaluated, {len(top)} top picks")

    # save today's shown picks for tomorrow's grading
    shown = {(p.player_id, p.stat, p.side): p.to_dict() for p in top}
    for ps in by_game.values():
        for p in ps:
            shown[(p.player_id, p.stat, p.side)] = p.to_dict()
    if shown:
        (hist / "picks" / f"{day_s}.json").write_text(json.dumps(list(shown.values()), indent=1))

    log("[6/6] Grading earlier picks + writing report")
    results = grade_history(hist, {p.id: p for p in players}, day_s)
    record = summarize(results)

    payload = {
        "date": day_s, "generated": now_et.strftime("%b %d, %I:%M %p ET").replace(" 0", " "), "season": season,
        "line_mode": "sportsbook" if lines else "estimated",
        "games": game_info,
        "top": [p.to_dict() for p in top],
        "by_game": {gid: [p.to_dict() for p in ps] for gid, ps in by_game.items()},
        "all": [p.to_dict() for p in sorted(all_picks, key=lambda p: -p.score)],
        "record": record,
    }
    (out / "picks.json").write_text(json.dumps(payload))
    (out / "index.html").write_text(render(payload))
    with open(out / "picks.csv", "w", newline="") as f:
        cols = ["game", "player", "team", "opp", "stat", "side", "line", "line_source", "price", "projection",
                "prob", "edge", "grade", "score", "hit_l5", "hit_l10", "hit_season", "vs_opp", "minutes", "status"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for p in sorted(all_picks, key=lambda p: -p.score):
            w.writerow(p.to_dict())
    log(f"Done -> {out / 'index.html'}")
    return payload


def cli():
    ap = argparse.ArgumentParser(description="NBA player prop finder")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today, US/Eastern)")
    ap.add_argument("--out", default="site")
    ap.add_argument("--cache", default=".cache")
    ap.add_argument("--history", default="history")
    ap.add_argument("--slate-only", action="store_true", help="only load teams playing today (faster, weaker DvP)")
    ap.add_argument("--stats", help="comma list, e.g. PTS,REB,AST,3PM,PRA")
    ap.add_argument("--markets", default=os.environ.get("ODDS_MARKETS", DEFAULT_MARKETS))
    a = ap.parse_args()
    run(a.date, a.out, a.cache, a.history, a.slate_only,
        a.stats.split(",") if a.stats else None, os.environ.get("ODDS_API_KEY"), a.markets)


if __name__ == "__main__":
    cli()

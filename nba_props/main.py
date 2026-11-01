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

from .espn import Espn, Injury, season_for
from .http import Http
from .model import (DEFAULT_PROP_STATS, League, best_picks, build_profile, evaluate,
                    project_team)
from .odds import DEFAULT_MARKETS, USAGE, PropLine, fetch_props, norm_name
from .report import render

ET = ZoneInfo("America/New_York")


def game_started(g, now) -> bool:
    """True once a game has tipped (by status, or by clock as a fallback)."""
    s = (g.status or "").lower()
    if any(x in s for x in ("progress", "half", "end of", "final", "overtime", "delayed")):
        return True
    if "postponed" in s or "canceled" in s:
        return False
    return now is not None and now >= g.date


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


def backtest_summary(all_picks, shown) -> dict:
    def rec(ps):
        w = sum(p["result"] == "WIN" for p in ps)
        l = sum(p["result"] == "LOSS" for p in ps)
        return {"w": w, "l": l, "pct": round(w / (w + l), 3) if w + l else None}
    out = {"all": rec(shown)}
    for g in ("A", "B", "C"):
        out[g] = rec([p for p in shown if p["grade"] == g])
    pos = [p.to_dict() for p in all_picks if p.edge >= 0.03]
    out["all_positive_edge"] = rec(pos)
    # projection accuracy vs simply using the player's recent average (the est. line)
    acc = {}
    for stat in ("PTS", "REB", "AST", "3PM", "PRA"):
        rows = [p for p in all_picks if p.stat == stat and getattr(p, "actual", None) is not None]
        if rows:
            acc[stat] = {"n": len(rows),
                         "model_mae": round(sum(abs(p.projection - p.actual) for p in rows) / len(rows), 2),
                         "avg_mae": round(sum(abs(p.line - p.actual) for p in rows) / len(rows), 2)}
    out["accuracy"] = acc
    out["pending"] = sum(p.result == "PENDING" for p in all_picks)
    out["recent"] = sorted([p for p in shown if p.get("result") in ("WIN", "LOSS", "PUSH")],
                           key=lambda p: -p["score"])
    for r in out["recent"]:
        r.setdefault("date", "")
    return out


def backtest_range(start: str, end: str, **kw) -> dict:
    """Backtest every date in [start, end]; write per-night pages + a season summary."""
    d0, d1 = datetime.fromisoformat(start), datetime.fromisoformat(end)
    nights = []
    d = d0
    while d <= d1:
        try:
            pl = run(d.strftime("%Y-%m-%d"), backtest=True, **kw)
            if pl["games"]:
                nights.append(pl)
        except Exception as e:
            log(f"   {d:%Y-%m-%d} failed: {e}")
        d += timedelta(days=1)
    bdir = Path(kw.get("backtest_dir", "backtests"))
    allp = [p for n in nights for p in n["all"]]
    for n in nights:
        for p in n["all"]:
            p["date"] = n["date"]
    shown = [dict(p, date=n["date"]) for n in nights for p in
             {(q["player_id"], q["stat"]): q for q in n["top"] + [x for v in n["by_game"].values() for x in v]}.values()]
    summary = {"nights": [{"date": n["date"], "games": len(n["games"]), "record": {k: n["record"][k] for k in ("all", "A", "B", "C", "all_positive_edge")}} for n in nights],
               "shown": len(shown)}
    (bdir / "season_props.json").write_text(json.dumps({"all": allp, "shown": shown}))
    (bdir / "season_summary.json").write_text(json.dumps(summary, indent=1))
    return summary


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
        odds_key: str | None = None, odds_markets: str = DEFAULT_MARKETS, http: Http | None = None,
        backtest: bool = False, backtest_dir: str = "backtests"):
    """backtest=True: project a past date using only games played before it, then
    grade every prop against the real box scores. Who sat that night is taken from
    the box scores (stand-in for the pre-game injury report)."""
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

    lines: dict = {}
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
    espn.load_logs(players, [season, season - 1], season, current_ttl=1800 if backtest else 3 * 3600)

    actual = {}                                   # (player_id, event_id) -> GameLine
    final_ids = {g.id for g in games if "final" in g.status.lower()}
    if backtest:
        slate_events = {g.id for g in games}
        played = {}
        for p in players:
            for gl in p.logs:
                if gl.event_id in slate_events:
                    actual[(p.id, gl.event_id)] = gl
                    played.setdefault(gl.event_id, set()).add(p.id)
            p.logs = [gl for gl in p.logs if gl.date.astimezone(ET).strftime("%Y-%m-%d") < day_s]
        injuries = {}
        for g in games:
            if g.id not in final_ids:
                continue
            for team in (g.home, g.away):
                for p in players:
                    if p.team_id == team.id and p.id not in played.get(g.id, set()):
                        injuries[p.id] = Injury(p.id, p.name, team.id, "Out", "did not play")
        odds_key = None
        saved = hist / "lines" / f"{day_s}.json"     # real lines saved on the night, if any
        if saved.exists():
            lines = {(r["name"], r["stat"]): PropLine(r["line"], r["over"], r["under"], r["books"])
                     for r in json.loads(saved.read_text())}

    log("[4/6] Building profiles, defense-vs-position, projections")
    profiles = {p.id: pr for p in players if (pr := build_profile(p, season))}
    league = League(players, profiles, season)
    tts = [t for g in games for tid in (g.home.id, g.away.id) if (t := g.implied_total(tid))]
    slate_tt = sum(tts) / len(tts) if tts else 0.0

    # Lock games at tip-off: started games keep the picks saved before tip and
    # get no new picks or odds (the odds feed returns live in-game lines).
    use_clock = day_s == now_et.strftime("%Y-%m-%d")
    started = set() if backtest else {g.id for g in games if game_started(g, now_et if use_clock else None)}
    upcoming = [g for g in games if g.id not in started]
    pick_file = hist / "picks" / f"{day_s}.json"
    locked = []
    if not backtest and pick_file.exists():
        locked = [dict(p, locked=True) for p in json.loads(pick_file.read_text()) if p["game_id"] in started]
    lines_file = hist / "lines" / f"{day_s}.json"
    if not backtest:
        lines = {}
        if lines_file.exists():          # lines saved by an earlier run today (pregame)
            lines = {(r["name"], r["stat"]): PropLine(r["line"], r["over"], r["under"], r["books"])
                     for r in json.loads(lines_file.read_text())}
    if odds_key and upcoming:
        log("   Fetching sportsbook prop lines")
        try:
            fresh = fetch_props(http, odds_key, {norm_name(g.home.name.split()[-1]): g.id for g in upcoming}, odds_markets)
            lines.update(fresh)
        except Exception as e:
            log(f"   odds fetch failed, falling back to estimated lines: {e}")
        if lines:
            (hist / "lines").mkdir(parents=True, exist_ok=True)
            (hist / "lines" / f"{day_s}.json").write_text(json.dumps(
                [{"name": k[0], "stat": k[1], "line": v.line, "over": v.over_price, "under": v.under_price,
                  "books": v.books} for k, v in lines.items()]))
        (hist / "odds_usage.json").write_text(json.dumps(
            {"date": day_s, "props_found": len(lines), **USAGE}, indent=1))

    by_team = {}
    for p in players:
        by_team.setdefault(p.team_id, []).append(p)
    all_picks, game_info = [], []
    for g in games:
        game_projs = []
        for team, opp in ((g.home, g.away), (g.away, g.home)):
            game_projs += project_team(by_team.get(team.id, []), team.id, team.abbr, opp.id, opp.abbr,
                                       g, league, injuries, slate_tt, day)
        if g.id not in started:
            for pr in game_projs:
                all_picks += evaluate(pr, stats, lines, season)
        inj_list = []
        for team in (g.away, g.home):
            for p in by_team.get(team.id, []):
                i = injuries.get(p.id) or injuries.get(p.name)
                if i and i.level != "ACTIVE":
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

    if backtest:
        for pk in all_picks:
            gl = actual.get((pk.player_id, pk.game_id))
            if pk.game_id not in final_ids:
                pk.result = "PENDING"
            elif gl is None:
                pk.result = "VOID"
            else:
                pk.actual = gl.get(pk.stat)
                pk.result = "PUSH" if pk.actual == pk.line else \
                    ("WIN" if (pk.actual > pk.line) == (pk.side == "OVER") else "LOSS")
    top, by_game = best_picks(all_picks)
    log(f"[5/6] {len(all_picks)} props evaluated, {len(top)} top picks, {len(locked)} locked")

    # save today's shown picks for grading: locked (started games) + fresh (upcoming)
    shown = {(p.player_id, p.stat, p.side): p.to_dict() for p in top}
    for ps in by_game.values():
        for p in ps:
            shown[(p.player_id, p.stat, p.side)] = p.to_dict()
    for p in locked:
        shown[(p["player_id"], p["stat"], p["side"])] = p
    if shown and not backtest:
        pick_file.write_text(json.dumps(list(shown.values()), indent=1))
    top_d = sorted([p.to_dict() for p in top] + locked, key=lambda p: -p["score"])
    seen_pl, top_out = set(), []
    for p in top_d:
        if p["player_id"] not in seen_pl and len(top_out) < 15:
            top_out.append(p)
            seen_pl.add(p["player_id"])
    by_game_out = {gid: [p.to_dict() for p in ps] for gid, ps in by_game.items()}
    for p in locked:
        by_game_out.setdefault(p["game_id"], []).append(p)

    log("[6/6] Grading + writing report")
    if backtest:
        record = backtest_summary(all_picks, list(shown.values()))
    else:
        results = grade_history(hist, {p.id: p for p in players}, day_s)
        record = summarize(results)

    payload = {
        "date": day_s, "generated": now_et.strftime("%b %d, %I:%M %p ET").replace(" 0", " "), "season": season,
        "line_mode": "sportsbook" if lines else "estimated",
        "odds_usage": dict(USAGE),
        "games": game_info,
        "top": top_out,
        "by_game": by_game_out,
        "all": [p.to_dict() for p in sorted(all_picks, key=lambda p: -p.score)],
        "record": record,
        "backtest": backtest,
        "backtests": sorted((f.stem for f in Path(backtest_dir).glob("*.html")), reverse=True)
                     if Path(backtest_dir).exists() else [],
    }
    if backtest:
        bdir = Path(backtest_dir)
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / f"{day_s}.html").write_text(render(payload, switch=("NFL", "../nfl/")))
        (bdir / f"{day_s}.json").write_text(json.dumps(payload))
        log(f"Backtest -> {bdir / (day_s + '.html')}")
        return payload
    (out / "picks.json").write_text(json.dumps(payload))
    (out / "index.html").write_text(render(payload, switch=("NFL", "nfl/")))
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
    ap.add_argument("--backtest", metavar="YYYY-MM-DD", help="project a past date blind, grade vs actual results")
    ap.add_argument("--backtest-range", nargs=2, metavar=("START", "END"))
    ap.add_argument("--markets", default=os.environ.get("ODDS_MARKETS") or DEFAULT_MARKETS)
    a = ap.parse_args()
    if a.backtest_range:
        print(json.dumps(backtest_range(*a.backtest_range, out_dir=a.out, cache_dir=a.cache,
                                        hist_dir=a.history, slate_only=a.slate_only), indent=1))
        return
    if a.backtest:
        run(a.backtest, a.out, a.cache, a.history, a.slate_only,
            a.stats.split(",") if a.stats else None, None, a.markets, backtest=True)
        return
    run(a.date, a.out, a.cache, a.history, a.slate_only,
        a.stats.split(",") if a.stats else None, os.environ.get("ODDS_API_KEY"), a.markets)


if __name__ == "__main__":
    cli()

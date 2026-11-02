"""NFL weekly pipeline.

    python -m nfl_props.main                       # this week's upcoming games
    python -m nfl_props.main --backtest-weeks 3 8  # blind backtest of weeks 3..8
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from nba_props.espn import Injury
from nba_props.http import Http
from nba_props.model import best_picks
from nba_props.odds import USAGE, PropLine, fetch_props, norm_name
from nba_props.report import render

from nba_props.espn_props import NFL_TYPES, fetch_espn_props
from nba_props.main import game_started

from .espn_nfl import EspnNfl, season_for
from .weather import game_weather
from .model import KNOBS, League, build_profile, evaluate, project_team

ET = ZoneInfo("America/New_York")
NFL_MARKETS = {
    "player_pass_yds": "PASS_YDS", "player_pass_tds": "PASS_TD", "player_pass_attempts": "PASS_ATT",
    "player_pass_completions": "PASS_CMP", "player_pass_interceptions": "INT",
    "player_rush_yds": "RUSH_YDS", "player_rush_attempts": "RUSH_ATT", "player_receptions": "REC",
    "player_reception_yds": "REC_YDS", "player_rush_reception_yds": "RUSH_REC_YDS",
    "player_anytime_td": "ANY_TD",
}
DEFAULT_NFL_MARKETS = "player_pass_yds,player_reception_yds"
NOTE = ("Projections combine each player's opportunities (pass attempts, carries, targets) with his efficiency, "
        "shrunk toward position averages, then adjust for game script (Vegas spread), scoring environment "
        "(implied team total), opponent defense vs his position and injured teammates' vacated targets/carries. "
        "“est.” lines are estimates of where books open; check your book's actual number. For entertainment and research only.")
PROJ_COLS = [["pos", "Pos"], ["PASS_YDS", "Pass yds"], ["RUSH_YDS", "Rush yds"], ["REC", "Rec"],
             ["REC_YDS", "Rec yds"], ["ANY_TD", "TD"]]
LABELS = {"season": "Season avg", "recent": "Last 4 avg", "min": "Proj opps"}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def _rec(ps):
    w = sum(p["result"] == "WIN" for p in ps)
    l = sum(p["result"] == "LOSS" for p in ps)
    return {"w": w, "l": l, "pct": round(w / (w + l), 3) if w + l else None}


def grade_history(hist: Path, players_by_id: dict, today: datetime) -> dict:
    path = hist / "results.json"
    res = json.loads(path.read_text()) if path.exists() else {"graded": []}
    done = {(r["week"], r["player_id"], r["stat"], r["side"]) for r in res["graded"]}
    for f in sorted((hist / "picks").glob("*.json")):
        blob = json.loads(f.read_text())
        made = datetime.fromisoformat(blob["made"])
        for pk in blob["picks"]:
            key = (f.stem, pk["player_id"], pk["stat"], pk["side"])
            if key in done:
                continue
            pl = players_by_id.get(pk["player_id"])
            g = next((x for x in pl.logs if x.event_id == pk["game_id"]), None) if pl else None
            if g is None:
                if (today - made).days >= 10:
                    res["graded"].append({**pk, "week": f.stem, "date": f.stem, "actual": None, "result": "VOID"})
                    done.add(key)
                continue
            a = g.get(pk["stat"])
            r = "PUSH" if a == pk["line"] else ("WIN" if (a > pk["line"]) == (pk["side"] == "OVER") else "LOSS")
            res["graded"].append({**pk, "week": f.stem, "date": f.stem, "actual": a, "result": r})
            done.add(key)
    path.write_text(json.dumps(res, indent=1))
    out = {k: _rec([r for r in res["graded"] if f(r)]) for k, f in
           (("all", lambda r: True), ("A", lambda r: r["grade"] == "A"), ("B", lambda r: r["grade"] == "B"),
            ("C", lambda r: r["grade"] == "C"))}
    out["recent"] = sorted(res["graded"], key=lambda r: r["week"], reverse=True)[:40]
    return out


def results_only(out_dir: str = "public/nfl", cache_dir: str = ".cache", hist_dir: str = "history/nfl",
                 http: Http | None = None, notify_out: str | None = None) -> dict:
    """Grade finished NFL picks with fresh box scores; no odds, no new picks."""
    from nba_props.main import annotate_results, results_message
    from .espn_nfl import NflPlayer
    now = datetime.now(ET)
    hist, out = Path(hist_dir), Path(out_dir)
    path = hist / "results.json"
    before = json.loads(path.read_text()) if path.exists() else {"graded": []}
    done = {(r["week"], r["player_id"], r["stat"], r["side"]) for r in before["graded"]}
    pending = {}
    for f in sorted((hist / "picks").glob("*.json")):
        for pk in json.loads(f.read_text())["picks"]:
            if (f.stem, pk["player_id"], pk["stat"], pk["side"]) not in done:
                pending[pk["player_id"]] = pk
    players = [NflPlayer(pid, pk["player"], "", "") for pid, pk in pending.items()]
    log(f"[results] {len(players)} players with ungraded picks")
    if players:
        EspnNfl(http or Http(cache_dir)).load_logs(players, [season_for(now)], season_for(now), current_ttl=0)
    record = grade_history(hist, {p.id: p for p in players}, now)
    graded = json.loads(path.read_text())["graded"]
    new = [r for r in graded if (r["week"], r["player_id"], r["stat"], r["side"]) not in done]
    pj = out / "picks.json"
    if pj.exists():
        payload = json.loads(pj.read_text())
        payload["record"] = record
        annotate_results(payload, graded, key="week")
        pj.write_text(json.dumps(payload))
        (out / "index.html").write_text(render(payload, "NFL Player Props", NOTE, ("NBA", "../")))
    msg = results_message("NFL", new, record)
    if notify_out and msg:
        Path(notify_out).write_text(json.dumps({**msg, "url": ""}))
    log(f"[results] graded {len(new)} picks")
    return {"new": new, "record": record}


def run(week: int | None = None, out_dir: str = "public/nfl", cache_dir: str = ".cache",
        hist_dir: str = "history/nfl", backtest: bool = False, http: Http | None = None,
        odds_key: str | None = None, markets: str = DEFAULT_NFL_MARKETS, season: int | None = None):
    now = datetime.now(ET)
    season = season or season_for(now)
    http = http or Http(cache_dir)
    espn = EspnNfl(http)
    out, hist = Path(out_dir), Path(hist_dir)
    (hist / "picks").mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    if week is None:
        wk, games = espn.week()
        if wk and games and all(game_started(g, now) for g in games):     # week is over: move on
            wk, games = espn.week(season, wk + 1)
    else:
        wk, games = espn.week(season, week)
        wk = wk or week
    key = f"{season}-W{int(wk or 0):02d}"
    log(f"[NFL] {key}: {len(games)} games")

    teams = espn.teams()
    players = []
    for tid in sorted(teams):
        try:
            players += espn.roster(tid)
        except Exception as e:
            log(f"   roster {tid} failed: {e}")
    log(f"   {len(players)} skill players; loading game logs")
    espn.load_logs(players, [season, season - 1], season, current_ttl=1800 if backtest else 6 * 3600)
    injuries = espn.injuries() if not backtest else {}

    actual, final_ids, lines = {}, {g.id for g in games if "final" in g.status.lower()}, {}
    if backtest and games:
        cutoff = min(g.date for g in games).astimezone(ET).strftime("%Y-%m-%d")
        slate = {g.id for g in games}
        played = {}
        for p in players:
            for gl in p.logs:
                if gl.event_id in slate:
                    actual[(p.id, gl.event_id)] = gl
                    played.setdefault(gl.event_id, set()).add(p.id)
            p.logs = [gl for gl in p.logs if gl.date.astimezone(ET).strftime("%Y-%m-%d") < cutoff]
        saved = hist / "lines" / f"{key}.json"
        if saved.exists():
            lines = {(r["name"], r["stat"]): PropLine(r["line"], r["over"], r["under"], r["books"], r.get("source", ""))
                     for r in json.loads(saved.read_text())}

    profiles = {p.id: pr for p in players if (pr := build_profile(p, season))}
    league = League(players, profiles, season)

    if backtest:
        for g in games:
            if g.id not in final_ids:
                continue
            for team in (g.home, g.away):
                recent = set(league.recent_events(team.id, 3))
                for p in players:
                    if p.team_id == team.id and p.id not in played.get(g.id, set()) \
                            and any(x.event_id in recent for x in p.logs):
                        injuries[p.id] = Injury(p.id, p.name, team.id, "Out", "did not play")

    tts = [t for g in games for tid in (g.home.id, g.away.id) if (t := g.implied_total(tid))]
    league_tt = sum(tts) / len(tts) if tts else 22.5

    # Lock games at kickoff: keep the picks saved before kickoff, no new picks/odds.
    started = set() if backtest else {g.id for g in games if game_started(g, now if week is None else None)}
    upcoming = [g for g in games if g.id not in started]
    pick_file = hist / "picks" / f"{key}.json"
    prior = json.loads(pick_file.read_text()) if (pick_file.exists() and not backtest) else {}
    locked = [dict(p, locked=True) for p in prior.get("picks", []) if p["game_id"] in started]
    if not backtest and (hist / "lines" / f"{key}.json").exists():
        lines = {(r["name"], r["stat"]): PropLine(r["line"], r["over"], r["under"], r["books"], r.get("source", ""))
                 for r in json.loads((hist / "lines" / f"{key}.json").read_text())}
    if upcoming and not backtest:
        try:      # free DraftKings lines via ESPN
            dk = fetch_espn_props(http, [g.id for g in upcoming], "football", "nfl", NFL_TYPES,
                                  {p.id: p.name for p in players})
            for v in dk.values():
                v.source = "DraftKings"
            lines.update(dk)
            log(f"   DraftKings lines via ESPN: {len(dk)}")
        except Exception as e:
            log(f"   ESPN prop lines failed: {e}")
    if odds_key and upcoming and not backtest:
        try:
            lines.update(fetch_props(http, odds_key, {norm_name(g.home.name.split()[-1]): g.id for g in upcoming},
                                     markets, sport="americanfootball_nfl", market_map=NFL_MARKETS))
        except Exception as e:
            log(f"   odds fetch failed: {e}")
    if lines and not backtest:
        (hist / "lines").mkdir(parents=True, exist_ok=True)
        (hist / "lines" / f"{key}.json").write_text(json.dumps(
            [{"name": k[0], "stat": k[1], "line": v.line, "over": v.over_price, "under": v.under_price,
              "books": v.books, "source": v.source} for k, v in lines.items()]))

    by_team = {}
    for p in players:
        by_team.setdefault(p.team_id, []).append(p)
    all_picks, game_info = [], []
    for g in games:
        projs = []
        wx = game_weather(http, g) if g.id not in started else {"label": ""}
        for team, opp in ((g.home, g.away), (g.away, g.home)):
            projs += project_team(by_team.get(team.id, []), team.id, team.abbr, opp.id, opp.abbr, g,
                                  league, injuries, league_tt, wx)
        if g.id not in started:
            for pr in projs:
                all_picks += evaluate(pr, lines, season)
        inj_list = []
        for team in (g.away, g.home):
            for p in by_team.get(team.id, []):
                i = injuries.get(p.id) or injuries.get(p.name)
                prof = profiles.get(p.id)
                if i and i.level != "ACTIVE" and prof and (prof.opps["tgt"] + prof.opps["rush_att"] + prof.opps["pass_att"]) >= 3:
                    inj_list.append({"team": team.abbr, "player": f"{p.name} ({p.pos})", "status": i.status,
                                     "level": i.level, "detail": i.detail,
                                     "min": round(prof.opps["tgt"] + prof.opps["rush_att"] + prof.opps["pass_att"], 1)})
        inj_list.sort(key=lambda x: -x["min"])
        game_info.append({
            "id": g.id, "label": g.label, "home": g.home.abbr, "away": g.away.abbr,
            "time": g.date.astimezone(ET).strftime("%a %I:%M %p ET").replace(" 0", " "), "status": g.status,
            "odds": g.odds_text, "total": g.total, "weather": wx.get("label", ""),
            "tt_home": round(g.implied_total(g.home.id), 1) if g.total else None,
            "tt_away": round(g.implied_total(g.away.id), 1) if g.total else None,
            "injuries": inj_list,
            "projections": sorted([{"player": pr.player.name, "pos": pr.player.pos, "team": pr.team_abbr,
                                    "status": pr.status,
                                    **{s: round(pr.mean.get(s, 0), 2 if s == "ANY_TD" else 1)
                                       for s in ("PASS_YDS", "RUSH_YDS", "REC", "REC_YDS", "ANY_TD")}}
                                   for pr in projs],
                                  key=lambda r: -(r["PASS_YDS"] / 4 + r["RUSH_YDS"] + r["REC_YDS"])),
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
    shown = {(p.player_id, p.stat): p.to_dict() for p in top + [x for v in by_game.values() for x in v]}
    for p in locked:
        shown[(p["player_id"], p["stat"])] = p
    top_d = sorted([p.to_dict() for p in top] + locked, key=lambda p: -p["score"])
    seen_pl, top_out = set(), []
    for p in top_d:
        if p["player_id"] not in seen_pl and len(top_out) < 15:
            top_out.append(p)
            seen_pl.add(p["player_id"])
    by_game_out = {gid: [p.to_dict() for p in ps] for gid, ps in by_game.items()}
    for p in locked:
        by_game_out.setdefault(p["game_id"], []).append(p)
    log(f"   {len(all_picks)} props evaluated, {len(top)} top picks, {len(locked)} locked")

    if backtest:
        sh = list(shown.values())
        record = {"all": _rec(sh), **{g: _rec([p for p in sh if p["grade"] == g]) for g in "ABC"},
                  "all_positive_edge": _rec([p.to_dict() for p in all_picks if p.edge >= 0.03]),
                  "pending": sum(p.result == "PENDING" for p in all_picks), "accuracy": {},
                  "recent": sorted([p for p in sh if p.get("result") in ("WIN", "LOSS", "PUSH")], key=lambda p: -p["score"])}
        for s in ("PASS_YDS", "RUSH_YDS", "REC", "REC_YDS"):
            rows = [p for p in all_picks if p.stat == s and p.actual is not None]
            if rows:
                record["accuracy"][s] = {"n": len(rows),
                                         "model_mae": round(sum(abs(p.projection - p.actual) for p in rows) / len(rows), 2),
                                         "avg_mae": round(sum(abs(p.line - p.actual) for p in rows) / len(rows), 2)}
        for r in record["recent"]:
            r.setdefault("date", key)
    else:
        if shown:
            pick_file.write_text(json.dumps({"made": prior.get("made", now.isoformat()), "picks": list(shown.values())}, indent=1))
        record = grade_history(hist, {p.id: p for p in players}, now)

    payload = {
        "date": key, "label": f"Week {wk} · {season}", "generated": now.strftime("%b %d, %I:%M %p ET").replace(" 0", " "),
        "season": season, "line_mode": "sportsbook" if lines else "estimated", "backtest": backtest,
        "games": game_info, "top": top_out if not backtest else [p.to_dict() for p in top],
        "by_game": by_game_out if not backtest else {gid: [p.to_dict() for p in ps] for gid, ps in by_game.items()},
        "all": [p.to_dict() for p in sorted(all_picks, key=lambda p: -p.score)],
        "record": record, "proj_cols": PROJ_COLS, "labels": LABELS,
        "backtests": sorted((f.stem for f in (out / "backtests").glob("*.html")), reverse=True)
                     if (out / "backtests").exists() else [],
    }
    if backtest:
        bdir = out / "backtests"
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / f"{key}.html").write_text(render(payload, "NFL Player Props", NOTE, ("NBA", "../../")))
        (bdir / f"{key}.json").write_text(json.dumps(payload))
        return payload
    (out / "picks.json").write_text(json.dumps(payload))
    (out / "index.html").write_text(render(payload, "NFL Player Props", NOTE, ("NBA", "../")))
    return payload


def backtest_weeks(w0: int, w1: int, **kw) -> dict:
    nights = []
    for wk in range(w0, w1 + 1):
        try:
            pl = run(wk, backtest=True, **kw)
            if pl["games"]:
                nights.append(pl)
        except Exception as e:
            log(f"   week {wk} failed: {e!r}")
    allp = [dict(p, date=n["date"]) for n in nights for p in n["all"]]
    shown = [dict(p, date=n["date"]) for n in nights for p in
             {(q["player_id"], q["stat"]): q for q in n["top"] + [x for v in n["by_game"].values() for x in v]}.values()]
    bdir = Path(kw.get("out_dir", "public/nfl")) / "backtests"
    summary = {"weeks": [{"week": n["date"], "games": len(n["games"]),
                          "record": {k: n["record"][k] for k in ("all", "A", "B", "C", "all_positive_edge")}} for n in nights]}
    (bdir / "season_props.json").write_text(json.dumps({"all": allp, "shown": shown}))
    (bdir / "season_summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def cli():
    ap = argparse.ArgumentParser(description="NFL player prop finder")
    ap.add_argument("--week", type=int)
    ap.add_argument("--out", default="public/nfl")
    ap.add_argument("--history", default="history/nfl")
    ap.add_argument("--cache", default=".cache")
    ap.add_argument("--backtest-weeks", nargs=2, type=int, metavar=("FIRST", "LAST"))
    ap.add_argument("--results-only", action="store_true", help="grade finished picks only (no odds, no new picks)")
    ap.add_argument("--notify-out")
    a = ap.parse_args()
    if a.results_only:
        results_only(a.out, a.cache, a.history, notify_out=a.notify_out)
        return
    if a.backtest_weeks:
        print(json.dumps(backtest_weeks(*a.backtest_weeks, out_dir=a.out, hist_dir=a.history, cache_dir=a.cache), indent=1))
        return
    use_odds = os.environ.get("NFL_ODDS", "").lower() in ("1", "on", "true", "yes")
    run(a.week, a.out, a.cache, a.history, odds_key=os.environ.get("ODDS_API_KEY") if use_odds else None,
        markets=os.environ.get("NFL_ODDS_MARKETS") or DEFAULT_NFL_MARKETS)


if __name__ == "__main__":
    cli()

"""NHL daily pipeline (player props + team bets).

    python -m nhl_props.main                       # today's slate
    python -m nhl_props.main --backtest-range 2026-10-20 2026-11-02
    python -m nhl_props.main --results-only
"""
from __future__ import annotations

import nba_props.model as _NM
from nba_props import parlays as PL

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from nba_props import teambets as TB
from nba_props.espn import Injury
from nba_props.espn_props import fetch_espn_props
from nba_props.http import Http
from nba_props.main import annotate_results, game_started, results_message
from nba_props.model import best_picks
from nba_props.model_report import model_report
from nba_props.odds import DEFAULT_NHL_MARKETS, NHL_MARKET_TO_STAT, USAGE, PropLine, fetch_props, norm_name
from nba_props.report import render

from .espn_nhl import EspnNhl, NhlPlayer, season_for
from .model import League, build_profile, evaluate, implied_goals, likely_goalie, project_team

ET = ZoneInfo("America/New_York")
NHL_TYPES = {"Total Shots on Goal": "SOG", "Total Points": "PTS", "Total Assists": "AST",
             "Total Saves": "SAVES", "Anytime Goalscorer": "GOALS"}
NOTE = ("Skater projections combine ice time with per-60 shot and assist rates (goals = shots × shooting %, shrunk toward "
        "position averages), adjusted for the opponent's shot suppression, the opposing goalie, Vegas-implied team goals "
        "and injured teammates. Saves = projected shots against × save % for a confidently identified starter. "
        "“est.” lines are estimates; check your book. For entertainment and research only.")
PROJ_COLS = [["pos", "Pos"], ["toi", "TOI"], ["SOG", "SOG"], ["GOALS", "G"], ["AST", "A"], ["PTS", "Pts"], ["SAVES", "Saves"]]
LABELS = {"season": "Season avg", "recent": "L10 avg", "min": "Proj TOI"}
SWITCH = [("NBA", "../"), ("NFL", "../nfl/")]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def _rec(ps):
    w = sum(p["result"] == "WIN" for p in ps)
    l = sum(p["result"] == "LOSS" for p in ps)
    return {"w": w, "l": l, "pct": round(w / (w + l), 3) if w + l else None}


def grade_history(hist: Path, players_by_id: dict, today: str) -> dict:
    path = hist / "results.json"
    res = json.loads(path.read_text()) if path.exists() else {"graded": []}
    done = {(r["date"], r["player_id"], r["stat"], r["side"]) for r in res["graded"]}
    for f in sorted((hist / "picks").glob("*.json")):
        day = f.stem
        if day >= today:
            continue
        for pk in json.loads(f.read_text()):
            key = (day, pk["player_id"], pk["stat"], pk["side"])
            if key in done:
                continue
            pl = players_by_id.get(pk["player_id"])
            g = next((x for x in pl.logs if x.event_id == pk["game_id"]), None) if pl else None
            if g is None:
                if (datetime.fromisoformat(today) - datetime.fromisoformat(day)).days >= 2:
                    res["graded"].append({**pk, "date": day, "actual": None, "result": "VOID"})
                    done.add(key)
                continue
            a = g.get(pk["stat"])
            r = "PUSH" if a == pk["line"] else ("WIN" if (a > pk["line"]) == (pk["side"] == "OVER") else "LOSS")
            res["graded"].append({**pk, "date": day, "actual": a, "actual_min": g.s.get("toi"), "result": r})
            done.add(key)
    path.write_text(json.dumps(res, indent=1))
    from nba_props.main import record_summary
    return record_summary(res["graded"], "min")


def run(date: str | None = None, out_dir: str = "public/nhl", cache_dir: str = ".cache",
        hist_dir: str = "history/nhl", backtest: bool = False, http: Http | None = None,
        odds_key: str | None = None, markets: str = DEFAULT_NHL_MARKETS,
        allow_est: bool | None = None):
    _NM.ALLOW_EST = backtest if allow_est is None else allow_est
    now = datetime.now(ET)
    day = datetime.fromisoformat(date).replace(tzinfo=ET) if date else now
    day_s = day.strftime("%Y-%m-%d")
    season = season_for(day)
    http = http or Http(cache_dir)
    espn = EspnNhl(http)
    out, hist = Path(out_dir), Path(hist_dir)
    (hist / "picks").mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    games = espn.games(day.strftime("%Y%m%d"))
    teams = espn.teams()
    log(f"[NHL] {day_s}: {len(games)} games")
    players = []
    for tid in sorted(teams):
        try:
            players += espn.roster(tid)
        except Exception as e:
            log(f"   roster {tid} failed: {e}")
    espn.load_logs(players, [season, season - 1], season, current_ttl=1800 if backtest else 3 * 3600)
    injuries = espn.injuries() if not backtest else {}

    actual, final_ids = {}, {g.id for g in games if "final" in g.status.lower()}
    played = {}
    lines: dict = {}
    if backtest:
        slate = {g.id for g in games}
        for p in players:
            for gl in p.logs:
                if gl.event_id in slate:
                    actual[(p.id, gl.event_id)] = gl
                    played.setdefault(gl.event_id, set()).add(p.id)
            p.logs = [gl for gl in p.logs if gl.date.astimezone(ET).strftime("%Y-%m-%d") < day_s]
        saved = hist / "lines" / f"{day_s}.json"
        if saved.exists():
            lines = {(r["name"], r["stat"]): PropLine(r["line"], r["over"], r["under"], r["books"], r.get("source", ""),
                                                      r.get("open_line"), r.get("open_over"), r.get("open_under"), r.get("book_prices"))
                     for r in json.loads(saved.read_text())}

    profiles = {p.id: pr for p in players if (pr := build_profile(p, season))}
    league = League(players, profiles, season)
    by_team: dict[str, list[NhlPlayer]] = {}
    for p in players:
        by_team.setdefault(p.team_id, []).append(p)

    if backtest:
        for g in games:
            if g.id not in final_ids:
                continue
            for team in (g.home, g.away):
                recent = set(league.recent_events(team.id, 3))
                for p in by_team.get(team.id, []):
                    if p.group != "G" and p.id not in played.get(g.id, set()) and any(x.event_id in recent for x in p.logs):
                        injuries[p.id] = Injury(p.id, p.name, team.id, "Out", "did not play")

    use_clock = day_s == now.strftime("%Y-%m-%d")
    started = set() if backtest else {g.id for g in games if game_started(g, now if use_clock else None)}
    upcoming = [g for g in games if g.id not in started]
    pick_file = hist / "picks" / f"{day_s}.json"
    locked = [dict(p, locked=True) for p in (json.loads(pick_file.read_text()) if pick_file.exists() and not backtest else [])
              if p["game_id"] in started]
    lines_file = hist / "lines" / f"{day_s}.json"
    if not backtest and lines_file.exists():
        lines = {(r["name"], r["stat"]): PropLine(r["line"], r["over"], r["under"], r["books"], r.get("source", ""),
                                                  r.get("open_line"), r.get("open_over"), r.get("open_under"), r.get("book_prices"))
                 for r in json.loads(lines_file.read_text())}
    if upcoming and not backtest:
        try:
            dk = fetch_espn_props(http, [g.id for g in upcoming], "hockey", "nhl", NHL_TYPES, {p.id: p.name for p in players})
            for v in dk.values():
                v.source = "DraftKings"
            lines.update(dk)
            log(f"   DraftKings lines via ESPN: {len(dk)}")
        except Exception as e:
            log(f"   ESPN prop lines failed: {e}")
        if odds_key:                     # optional multi-book lines (FanDuel, DraftKings, ...) for line shopping
            try:
                lines.update(fetch_props(http, odds_key, {norm_name(g.home.name.split()[-1]): g.id for g in upcoming},
                                         markets, sport="icehockey_nhl", market_map=NHL_MARKET_TO_STAT))
                (hist / "odds_usage.json").write_text(json.dumps({"date": day_s, **USAGE}, indent=1))
            except Exception as e:
                log(f"   odds fetch failed: {e}")
        if lines:
            lines_file.parent.mkdir(parents=True, exist_ok=True)
            lines_file.write_text(json.dumps([{"name": k[0], "stat": k[1], "line": v.line, "over": v.over_price,
                                               "under": v.under_price, "books": v.books, "source": v.source,
                                               "open_line": v.open_line, "open_over": v.open_over, "open_under": v.open_under, "book_prices": v.book_prices}
                                              for k, v in lines.items()]))

    # team odds (also drives implied team goals for the player model)
    odds = {g.id: TB.game_odds(http, "nhl", g.id, ttl=86400 if backtest else 900) for g in games}
    imp = {}
    for g in games:
        o = odds.get(g.id)
        ig = implied_goals(o.total, o.ml_home, o.ml_away) if o else None
        if ig:
            imp[g.id] = ig
    lg_tg = (sum(a + b for a, b in imp.values()) / (2 * len(imp))) if imp else 3.05

    all_picks, game_info, team_ctx = [], [], {}
    for g in games:
        goalies = {}
        for team in (g.home, g.away):
            gl = [p for p in by_team.get(team.id, []) if p.group == "G"]
            goalies[team.id] = likely_goalie(gl, profiles, league, team.id,
                                             {k: v for k, v in injuries.items()}, day)
        projs = []
        ig = imp.get(g.id)
        for team, opp in ((g.home, g.away), (g.away, g.home)):
            tg = (ig[0] if team.id == g.home.id else ig[1]) if ig else None
            mg, mc = goalies[team.id]
            og, _ = goalies[opp.id]
            projs += project_team(by_team.get(team.id, []), team.id, team.abbr, opp.id, opp.abbr, g, league,
                                  injuries, tg, lg_tg, og, mg, mc)
        if g.id not in started:
            for pr in projs:
                all_picks += evaluate(pr, lines, season)
        team_ctx[g.id] = goalies
        inj_list = []
        for team in (g.away, g.home):
            for p in by_team.get(team.id, []):
                i = injuries.get(p.id) or injuries.get(p.name)
                prof = profiles.get(p.id)
                if i and i.level != "ACTIVE" and prof and prof.toi >= 10:
                    inj_list.append({"team": team.abbr, "player": f"{p.name} ({p.pos})", "status": i.status,
                                     "level": i.level, "detail": i.detail, "min": round(prof.toi, 1)})
        inj_list.sort(key=lambda x: -x["min"])
        gl_note = " · ".join(f"{t.abbr} G: {goalies[t.id][0].name.split()[-1]} ({goalies[t.id][1] * 100:.0f}%)"
                             for t in (g.away, g.home) if goalies[t.id][0])
        game_info.append({
            "id": g.id, "label": g.label, "home": g.home.abbr, "away": g.away.abbr,
            "time": g.date.astimezone(ET).strftime("%I:%M %p ET").lstrip("0"), "status": g.status,
            "odds": g.odds_text, "total": g.total, "weather": gl_note, "start": g.date.isoformat(),
            "tt_home": round(ig[0], 2) if ig else None, "tt_away": round(ig[1], 2) if ig else None,
            "injuries": inj_list,
            "projections": sorted([{"player": pr.player.name, "pos": pr.player.pos, "team": pr.team_abbr,
                                    "status": pr.status, "toi": round(pr.toi, 1),
                                    **{s: round(pr.mean[s], 2 if s in ("GOALS", "AST", "PTS") else 1) for s in pr.mean}}
                                   for pr in projs], key=lambda r: -(r.get("SOG", 0) + 10 * r.get("PTS", 0))),
        })

    # ---- team bets
    team_picks_all, team_shown, team_record = [], [], {}
    try:
        results = TB.team_results(http, "nhl", sorted(teams), [season, season - 1], season)
        ratings = TB.Ratings("nhl", results, day.replace(hour=0, minute=0), season)
        by_event = {r.event_id: r for r in results}
        eff = ratings.n_games / max(1, len(teams)) * 2 + (TB.SPORT["nhl"]["prior_games"] if any(r.season == season - 1 for r in results) else 0)
        for g in games:
            if g.id in started:
                continue
            mu_h, mu_a = ratings.predict(g.home.id, g.away.id)
            notes = []
            goalies = team_ctx.get(g.id, {})
            for team, oteam in ((g.home, g.away), (g.away, g.home)):
                gk, conf = goalies.get(team.id, (None, 0))
                if gk and gk.id in profiles:
                    sv = profiles[gk.id].rates["sv_pct"]
                    f = max(0.8, min(1.25, (1 - sv) / 0.1))
                    if team.id == g.home.id:
                        mu_a *= f
                    else:
                        mu_h *= f
                    if abs(f - 1) >= 0.05:
                        notes.append(f"{team.abbr} goalie {gk.name} ({sv:.3f}): opponent goals {(f - 1) * 100:+.0f}%"
                                     + ("" if conf >= 0.6 else " (starter uncertain)"))
            tp = TB.team_picks("nhl", g, mu_h, mu_a, odds.get(g.id), notes, eff)
            if backtest and g.id in by_event:
                r = by_event[g.id]
                for pk in tp:
                    pk["result"] = TB.grade_team_pick(pk, r.hs, r.as_)
                    pk["final"] = f"{pk['home']} {r.hs:g} – {pk['away']} {r.as_:g}"
            team_picks_all += tp
        if not backtest:
            team_shown = TB.save_team_picks(hist, day_s, team_picks_all, started, now)
            team_record = TB.grade_team_history(http, "nhl", hist, now)
        else:
            team_shown = [p for p in team_picks_all if p["grade"] != "-"]
            team_record = TB.summarize_team([dict(p, date=day_s) for p in team_shown])
    except Exception as e:
        log(f"   team bets failed: {e!r}")

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
    shown = {(p.player_id, p.stat, p.side): p.to_dict() for p in top + [x for v in by_game.values() for x in v]}
    for p in locked:
        shown[(p["player_id"], p["stat"], p["side"])] = p
    top_d = sorted([p.to_dict() for p in top] + locked, key=lambda p: -p["score"])
    seen, top_out = set(), []
    for p in top_d:
        if p["player_id"] not in seen and len(top_out) < 15:
            top_out.append(p)
            seen.add(p["player_id"])
    by_game_out = {gid: [p.to_dict() for p in ps] for gid, ps in by_game.items()}
    for p in locked:
        by_game_out.setdefault(p["game_id"], []).append(p)
    log(f"   {len(all_picks)} props evaluated, {len(top)} top picks, {len(team_shown)} team bets")

    if backtest:
        sh = list(shown.values())
        record = {"all": _rec(sh), **{gg: _rec([p for p in sh if p["grade"] == gg]) for gg in "ABC"},
                  "all_positive_edge": _rec([p.to_dict() for p in all_picks if p.edge >= 0.03]),
                  "pending": sum(p.result == "PENDING" for p in all_picks), "accuracy": {},
                  "recent": sorted([p for p in sh if p.get("result") in ("WIN", "LOSS", "PUSH")], key=lambda p: -p["score"])}
        for r in record["recent"]:
            r.setdefault("date", day_s)
    else:
        if shown:
            pick_file.write_text(json.dumps(list(shown.values()), indent=1))
        record = grade_history(hist, {p.id: p for p in players}, day_s)

    parlays = {}
    if not backtest:
        try:
            parlays = {"tickets": PL.update(hist, day_s, list(shown.values()), started, now),
                       "record": PL.grade(hist, json.loads((hist / "results.json").read_text())["graded"]
                                          if (hist / "results.json").exists() else [])}
        except Exception as e:
            log(f"   parlays failed: {e!r}")
    payload = {
        "parlays": parlays,
        "date": day_s, "generated": now.strftime("%b %d, %I:%M %p ET").replace(" 0", " "), "season": season,
        "line_mode": "sportsbook" if lines else "estimated", "backtest": backtest,
        "games": game_info, "top": top_out if not backtest else [p.to_dict() for p in top],
        "by_game": by_game_out if not backtest else {gid: [p.to_dict() for p in ps] for gid, ps in by_game.items()},
        "all": [p.to_dict() for p in sorted(all_picks, key=lambda p: -p.score)],
        "record": record, "proj_cols": PROJ_COLS, "labels": LABELS,
        "team": {"picks": team_shown, "all": team_picks_all, "record": team_record},
        "backtests": sorted((f.stem for f in (out / "backtests").glob("*.html")), reverse=True)
                     if (out / "backtests").exists() else [],
    }
    if backtest:
        bdir = out / "backtests"
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / f"{day_s}.html").write_text(render(payload, "NHL Player Props", NOTE, [("NBA", "../../"), ("NFL", "../../nfl/")]))
        (bdir / f"{day_s}.json").write_text(json.dumps(payload))
        return payload
    (out / "picks.json").write_text(json.dumps(payload))
    (out / "index.html").write_text(render(payload, "NHL Player Props", NOTE, SWITCH))
    return payload


def results_only(out_dir: str = "public/nhl", cache_dir: str = ".cache", hist_dir: str = "history/nhl",
                 http: Http | None = None, notify_out: str | None = None) -> dict:
    now = datetime.now(ET)
    today = now.strftime("%Y-%m-%d")
    hist, out = Path(hist_dir), Path(out_dir)
    path = hist / "results.json"
    before = json.loads(path.read_text()) if path.exists() else {"graded": []}
    done = {(r["date"], r["player_id"], r["stat"], r["side"]) for r in before["graded"]}
    pending = {}
    for f in sorted((hist / "picks").glob("*.json")) if (hist / "picks").exists() else []:
        if f.stem >= today:
            continue
        for pk in json.loads(f.read_text()):
            if (f.stem, pk["player_id"], pk["stat"], pk["side"]) not in done:
                pending[pk["player_id"]] = pk
    http = http or Http(cache_dir)
    players = [NhlPlayer(pid, pk["player"], "", "G" if pk["stat"] == "SAVES" else "C") for pid, pk in pending.items()]
    if players:
        EspnNhl(http).load_logs(players, [season_for(now)], season_for(now), current_ttl=0)
    (hist / "picks").mkdir(parents=True, exist_ok=True)
    record = grade_history(hist, {p.id: p for p in players}, today)
    graded = json.loads(path.read_text())["graded"]
    new = [r for r in graded if (r["date"], r["player_id"], r["stat"], r["side"]) not in done]
    pj = out / "picks.json"
    if pj.exists():
        payload = json.loads(pj.read_text())
        payload["record"] = record
        try:
            payload["parlays"] = {**(payload.get("parlays") or {}),
                                  "record": PL.grade(hist, json.loads((hist / "results.json").read_text())["graded"])}
        except Exception as e:
            log(f"[results] parlay grading failed: {e!r}")
        annotate_results(payload, graded)
        try:
            payload.setdefault("team", {})["record"] = TB.grade_team_history(http, "nhl", hist, now)
        except Exception as e:
            log(f"[results] team grading failed: {e!r}")
        pj.write_text(json.dumps(payload))
        (out / "index.html").write_text(render(payload, "NHL Player Props", NOTE, SWITCH))
    msg = results_message("NHL", new, record)
    if notify_out and msg:
        Path(notify_out).write_text(json.dumps({**msg, "url": ""}))
    return {"new": new, "record": record}


def backtest_range(start: str, end: str, **kw) -> dict:
    d0, d1 = datetime.fromisoformat(start), datetime.fromisoformat(end)
    nights, d = [], d0
    while d <= d1:
        try:
            pl = run(d.strftime("%Y-%m-%d"), backtest=True, **kw)
            if pl["games"]:
                nights.append(pl)
        except Exception as e:
            log(f"   {d:%Y-%m-%d} failed: {e!r}")
        d += timedelta(days=1)
    bdir = Path(kw.get("out_dir", "public/nhl")) / "backtests"
    bdir.mkdir(parents=True, exist_ok=True)
    allp = [dict(p, date=n["date"]) for n in nights for p in n["all"]]
    shown = [dict(p, date=n["date"]) for n in nights for p in
             {(q["player_id"], q["stat"]): q for q in n["top"] + [x for v in n["by_game"].values() for x in v]}.values()]
    team = [dict(p, date=n["date"]) for n in nights for p in n["team"]["all"]]
    (bdir / "season_props.json").write_text(json.dumps({"all": allp, "shown": shown, "team": team}))
    summary = {"nights": [{"date": n["date"], "games": len(n["games"]),
                           "record": {k: n["record"][k] for k in ("all", "A", "B", "C", "all_positive_edge")}} for n in nights],
               "team": TB.summarize_team([p for p in team if p["grade"] != "-"])}
    (bdir / "season_summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def cli():
    ap = argparse.ArgumentParser(description="NHL player prop + team bet finder")
    ap.add_argument("--date")
    ap.add_argument("--out", default="public/nhl")
    ap.add_argument("--history", default="history/nhl")
    ap.add_argument("--cache", default=".cache")
    ap.add_argument("--backtest-range", nargs=2, metavar=("START", "END"))
    ap.add_argument("--results-only", action="store_true")
    ap.add_argument("--notify-out")
    a = ap.parse_args()
    if a.results_only:
        results_only(a.out, a.cache, a.history, notify_out=a.notify_out)
        return
    if a.backtest_range:
        print(json.dumps(backtest_range(*a.backtest_range, out_dir=a.out, hist_dir=a.history, cache_dir=a.cache), indent=1))
        return
    import os
    use = os.environ.get("NHL_ODDS", "").lower() in ("1", "on", "all", "true", "yes")
    run(a.date, a.out, a.cache, a.history, odds_key=os.environ.get("ODDS_API_KEY") if use else None,
        markets=os.environ.get("NHL_ODDS_MARKETS") or DEFAULT_NHL_MARKETS)


if __name__ == "__main__":
    cli()

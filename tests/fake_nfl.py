"""Simulated NFL league served in ESPN-like JSON, for offline tests.

Planted truths: team 5 gives up +20% receiving yards to WRs; team 1's WR1
(player 105) is OUT this week, so team 1's other receivers should gain targets.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from tests.fake_espn import _poisson

ABBRS = ["ATL", "BUF", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "TEN", "IND", "KC", "LV", "LAR", "MIA", "MIN",
         "NE", "NO", "NYG", "NYJ", "PHI", "ARI", "PIT", "LAC", "SF", "SEA", "TB", "WSH", "CAR", "JAX", "BAL", "HOU"]
TEAMS = {str(i + 1): a for i, a in enumerate(ABBRS)}
ROLES = [("QB", 1), ("QB", 2), ("RB", 1), ("RB", 2), ("WR", 1), ("WR", 2), ("WR", 3), ("WR", 4), ("TE", 1), ("TE", 2)]
TGT_SHARE = {("WR", 1): .26, ("WR", 2): .19, ("WR", 3): .12, ("WR", 4): .04, ("TE", 1): .16, ("TE", 2): .04,
             ("RB", 1): .11, ("RB", 2): .05}
CAR_SHARE = {("RB", 1): .62, ("RB", 2): .28, ("QB", 1): .08}
CURRENT_WEEK = 9


class NflLeague:
    def __init__(self, seed=3):
        rng = self.rng = random.Random(seed)
        self.players = {}
        for tid in TEAMS:
            for j, (pos, depth) in enumerate(ROLES):
                pid = str(int(tid) * 100 + (j + 1)) if False else f"{tid}{j + 1:02d}"
                self.players[pid] = dict(id=pid, team=tid, pos=pos, depth=depth,
                                         name=f"{TEAMS[tid]} {pos}{depth}", eff=rng.uniform(.85, 1.15))
        self.logs = {pid: {2025: [], 2026: []} for pid in self.players}
        self.events, self.weeks = {}, {}
        eid = 401600000
        for season, n_weeks, start in ((2025, 17, datetime(2025, 9, 7, 17, tzinfo=timezone.utc)),
                                       (2026, CURRENT_WEEK, datetime(2026, 9, 13, 17, tzinfo=timezone.utc))):
            for wk in range(1, n_weeks + 1):
                ids = list(TEAMS)
                rng.shuffle(ids)
                day = start + timedelta(days=7 * (wk - 1))
                for k in range(0, 32, 2):
                    eid += 1
                    h, a = ids[k], ids[k + 1]
                    spread = round(rng.uniform(-9, 9) * 2) / 2
                    final = not (season == 2026 and wk == CURRENT_WEEK)
                    self.events[str(eid)] = dict(home=h, away=a, date=day, season=season, week=wk,
                                                 spread=spread, total=44.5, final=final)
                    self.weeks.setdefault((season, wk), []).append(str(eid))
                    if final:
                        for tid, opp, sp in ((h, a, spread), (a, h, -spread)):
                            self._box(str(eid), season, tid, opp, sp)

    def _box(self, eid, season, tid, opp, spread_home_view):
        rng = self.rng
        roster = [p for p in self.players.values() if p["team"] == tid]
        pass_att = max(18, int(rng.gauss(34 + 0.4 * (-spread_home_view), 5)))
        carries = max(12, int(rng.gauss(25, 4)))
        wr1_out = tid == "1" and season == 2026 and rng.random() < 0.2
        for p in roster:
            key = (p["pos"], p["depth"])
            s = dict(pass_att=0, cmp=0, pass_yds=0, pass_td=0, ints=0, rush_att=0, rush_yds=0, rush_td=0,
                     tgt=0, rec=0, rec_yds=0, rec_td=0)
            if p["id"] == "102" or (p["pos"] == "QB" and p["depth"] == 2):
                continue
            if p["id"] == "105" and wr1_out:
                continue
            share = TGT_SHARE.get(key, 0) * (1.3 if wr1_out and p["team"] == "1" and p["pos"] != "QB" else 1)
            if p["pos"] == "QB":
                s["pass_att"] = pass_att
                s["cmp"] = int(pass_att * rng.uniform(.58, .72))
                s["pass_yds"] = int(pass_att * rng.gauss(6.9, 1.2) * p["eff"])
                s["pass_td"] = _poisson(rng, 1.5)
                s["ints"] = _poisson(rng, .8)
            if key in CAR_SHARE:
                s["rush_att"] = max(0, int(rng.gauss(carries * CAR_SHARE[key], 2)))
                s["rush_yds"] = int(s["rush_att"] * rng.gauss(4.3, 1.5) * p["eff"])
                s["rush_td"] = _poisson(rng, s["rush_att"] * 0.03)
            if share:
                s["tgt"] = _poisson(rng, pass_att * share)
                s["rec"] = sum(rng.random() < .66 for _ in range(s["tgt"]))
                boost = 1.2 if (opp == "5" and p["pos"] == "WR") else 1.0
                s["rec_yds"] = int(sum(max(0, rng.gauss(11.5, 7)) for _ in range(s["rec"])) * p["eff"] * boost)
                s["rec_td"] = _poisson(rng, s["tgt"] * .045)
            if sum(s.values()) == 0 and p["pos"] != "QB":
                continue
            self.logs[p["id"]][season].append((eid, s))

    # ------------------------------------------------------------- ESPN shapes
    def teams_json(self):
        return {"sports": [{"leagues": [{"teams": [{"team": {"id": t, "abbreviation": a, "displayName": f"City {a}s"}}
                                                  for t, a in TEAMS.items()]}]}]}

    def scoreboard_json(self, params):
        season = int(params.get("dates", 2026)) if params else 2026
        wk = int(params.get("week", CURRENT_WEEK)) if params else CURRENT_WEEK
        evs = []
        for eid in self.weeks.get((season, wk), []):
            e = self.events[eid]
            h, a = e["home"], e["away"]
            fav = h if e["spread"] < 0 else a
            evs.append({"id": eid, "date": e["date"].strftime("%Y-%m-%dT%H:%MZ"),
                        "status": {"type": {"description": "Final" if e["final"] else "Scheduled"}},
                        "competitions": [{"competitors": [
                            {"homeAway": "home", "team": {"id": h, "abbreviation": TEAMS[h], "displayName": f"City {TEAMS[h]}s"}},
                            {"homeAway": "away", "team": {"id": a, "abbreviation": TEAMS[a], "displayName": f"City {TEAMS[a]}s"}}],
                            "odds": [{"details": f"{TEAMS[fav]} -{abs(e['spread'])}" if e["spread"] else "EVEN",
                                      "overUnder": e["total"]}]}]})
        return {"week": {"number": wk}, "events": evs}

    def injuries_json(self):
        return {"injuries": [{"id": "1", "injuries": [
            {"athlete": {"id": "105", "displayName": "ATL WR1"}, "status": "Out", "shortComment": "Hamstring"}]}]}

    def roster_json(self, tid):
        return {"athletes": [
            {"position": "offense", "items": [{"id": p["id"], "displayName": p["name"],
                                               "position": {"abbreviation": p["pos"]}}
                                              for p in self.players.values() if p["team"] == tid]},
            {"position": "defense", "items": [{"id": f"d{tid}", "displayName": "Some LB", "position": {"abbreviation": "LB"}}]}]}

    def gamelog_json(self, pid, season):
        names = ["completions", "passingAttempts", "passingYards", "completionPct", "passingTouchdowns", "interceptions",
                 "rushingAttempts", "rushingYards", "yardsPerRushAttempt", "rushingTouchdowns",
                 "receptions", "receivingTargets", "receivingYards", "receivingTouchdowns"]
        labels = ["CMP", "ATT", "YDS", "CMP%", "TD", "INT", "CAR", "YDS", "AVG", "TD", "REC", "TGTS", "YDS", "TD"]
        events, rows = {}, []
        for eid, s in self.logs.get(pid, {}).get(season, []):
            e = self.events[eid]
            tid = self.players[pid]["team"]
            opp = e["away"] if e["home"] == tid else e["home"]
            events[eid] = {"id": eid, "gameDate": e["date"].strftime("%Y-%m-%dT%H:%M:%S.000+00:00"),
                           "atVs": "vs" if e["home"] == tid else "@", "opponent": {"id": opp, "abbreviation": TEAMS[opp]},
                           "homeTeamId": e["home"], "awayTeamId": e["away"]}
            rows.append({"eventId": eid, "stats": [str(s["cmp"]), str(s["pass_att"]), str(s["pass_yds"]), "60.0",
                                                   str(s["pass_td"]), str(s["ints"]), str(s["rush_att"]), str(s["rush_yds"]),
                                                   "4.0", str(s["rush_td"]), str(s["rec"]), str(s["tgt"]),
                                                   str(s["rec_yds"]), str(s["rec_td"])]})
        return {"labels": labels, "names": names, "events": events,
                "seasonTypes": [{"displayName": f"{season} Regular Season",
                                 "categories": [{"events": list(reversed(rows))}]}]}


class FakeNflHttp:
    def __init__(self, lg):
        self.lg = lg

    def get_json(self, url, params=None, ttl=None):
        params = params or {}
        if url.endswith("/scoreboard"):
            return self.lg.scoreboard_json(params)
        if url.endswith("/injuries"):
            return self.lg.injuries_json()
        if url.endswith("/roster"):
            return self.lg.roster_json(url.split("/teams/")[1].split("/")[0])
        if url.endswith("/teams"):
            return self.lg.teams_json()
        if url.endswith("/gamelog"):
            return self.lg.gamelog_json(url.split("/athletes/")[1].split("/")[0], int(params["season"]))
        return None

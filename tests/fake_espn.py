"""A simulated NBA league served in ESPN's JSON shapes, for offline testing.

Built-in truths the model should recover:
  * team 8 (DEN) defends centers badly (+15% everything to C)
  * team 2 (BOS) smothers guards' points (-12%)
  * on team 1 (ATL), star player 1001 is OUT and missed the last 3 games;
    teammate 1002 absorbs his usage in games he misses.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

ABBRS = ["ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GS", "HOU", "IND", "LAC", "LAL", "MEM",
         "MIA", "MIL", "MIN", "NO", "NY", "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SA", "TOR", "UTAH", "WSH"]
TEAMS = {str(i + 1): a for i, a in enumerate(ABBRS)}
POS = ["PG", "SG", "SF", "PF", "C", "G", "F", "C", "SG", "PF", "SF", "PG", "C"]
TODAY = datetime(2026, 10, 30, tzinfo=timezone.utc)


def _poisson(rng, lam):
    lam = max(lam, 0.0)
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


class League:
    def __init__(self, seed=7):
        rng = self.rng = random.Random(seed)
        self.players = {}       # id -> dict
        for tid in TEAMS:
            for j, pos in enumerate(POS):
                pid = str(int(tid) * 1000 + j + 1)
                star = 1.6 if j == 0 else 1.0
                base_min = [35, 33, 32, 30, 30, 26, 22, 18, 16, 12, 9, 6, 4][j]
                self.players[pid] = dict(
                    id=pid, team=tid, pos=pos, name=f"{TEAMS[tid]} Player{j + 1}", min=base_min,
                    pts=rng.uniform(0.38, 0.62) * star, reb=(0.32 if pos in ("C", "PF") else 0.15) * rng.uniform(.8, 1.2),
                    ast=(0.22 if "G" in pos else 0.08) * rng.uniform(.8, 1.3) * (1.3 if j == 0 else 1),
                    fg3=(0.08 if pos != "C" else 0.02) * rng.uniform(.6, 1.4), stl=0.03, blk=0.05 if pos == "C" else 0.012,
                    tov=0.05)
        self.logs = {pid: {2026: [], 2027: []} for pid in self.players}
        self.events = {}
        eid = 401700000
        for season, start, n_rounds in ((2026, datetime(2025, 10, 22, tzinfo=timezone.utc), 82),
                                        (2027, datetime(2026, 10, 21, tzinfo=timezone.utc), 6)):
            ids = list(TEAMS)
            for r in range(n_rounds):
                rng.shuffle(ids)
                day = start + timedelta(days=int(r * (2.1 if season == 2026 else 1.5)))
                for k in range(0, 30, 2):
                    home, away = ids[k], ids[k + 1]
                    eid += 1
                    self.events[str(eid)] = dict(home=home, away=away, date=day)
                    for tid, opp in ((home, away), (away, home)):
                        self._box(str(eid), season, tid, opp, day, tid == home)

    def _box(self, eid, season, tid, opp, day, home):
        rng = self.rng
        roster = [p for p in self.players.values() if p["team"] == tid]
        star_out = (tid == "1" and season == 2027 and day > TODAY - timedelta(days=6)) or \
                   (tid == "1" and season == 2026 and rng.random() < 0.15)
        for p in roster:
            if p["id"] == "1001" and star_out:
                continue
            if rng.random() < 0.05:       # random rest / DNP
                continue
            boost = 1.0
            if p["id"] == "1002" and star_out:
                boost = 1.35
            m = max(1.0, rng.gauss(p["min"], 3.5))
            dv = 1.0
            if opp == "8" and p["pos"] == "C":
                dv = 1.15
            pdv = 0.88 if (opp == "2" and "G" in p["pos"]) else 1.0
            line = dict(
                min=round(m), pts=_poisson(rng, p["pts"] * m * dv * pdv * boost), reb=_poisson(rng, p["reb"] * m * dv),
                ast=_poisson(rng, p["ast"] * m * dv * boost), stl=_poisson(rng, p["stl"] * m), blk=_poisson(rng, p["blk"] * m * dv),
                tov=_poisson(rng, p["tov"] * m), fg3=_poisson(rng, p["fg3"] * m * pdv))
            line["fg3a"] = line["fg3"] + _poisson(rng, 3)
            self.logs[p["id"]][season].append((eid, line))

    # ------------------------------------------------------------------ ESPN shapes
    def teams_json(self):
        return {"sports": [{"leagues": [{"teams": [{"team": {"id": t, "abbreviation": a, "displayName": f"{a} Team"}}
                                                  for t, a in TEAMS.items()]}]}]}

    def scoreboard_json(self):
        pairs = [("1", "8"), ("2", "14"), ("5", "20"), ("10", "24"), ("16", "27"), ("8", "3")][:5]
        evs = []
        for i, (home, away) in enumerate(pairs):
            fav_home = i % 2 == 0
            spread = [3.5, 11.5, 1.5, 6.0, 8.5][i]
            details = f"{TEAMS[home] if fav_home else TEAMS[away]} -{spread}"
            evs.append({"id": f"40180000{i}", "date": "2026-10-30T23:30Z",
                        "status": {"type": {"description": "Scheduled"}},
                        "competitions": [{"competitors": [
                            {"homeAway": "home", "team": {"id": home, "abbreviation": TEAMS[home], "displayName": f"{TEAMS[home]} Team"}},
                            {"homeAway": "away", "team": {"id": away, "abbreviation": TEAMS[away], "displayName": f"{TEAMS[away]} Team"}}],
                            "odds": [{"details": details, "overUnder": [228.5, 214.5, 231.0, 222.0, 219.5][i]}]}]})
        return {"events": evs}

    def past_scoreboard(self, yyyymmdd):
        evs = []
        for eid, e in self.events.items():
            if e["date"].strftime("%Y%m%d") != yyyymmdd:
                continue
            h, a = e["home"], e["away"]
            evs.append({"id": eid, "date": e["date"].strftime("%Y-%m-%dT%H:%MZ"),
                        "status": {"type": {"description": "Final"}},
                        "competitions": [{"competitors": [
                            {"homeAway": "home", "team": {"id": h, "abbreviation": TEAMS[h], "displayName": TEAMS[h]}},
                            {"homeAway": "away", "team": {"id": a, "abbreviation": TEAMS[a], "displayName": TEAMS[a]}}],
                            "odds": [{"details": f"{TEAMS[h]} -2.5", "overUnder": 224.5}]}]})
        return {"events": evs} if evs else None

    def injuries_json(self):
        return {"injuries": [
            {"id": "1", "displayName": "ATL Team", "injuries": [
                {"athlete": {"id": "1001", "displayName": "ATL Player1"}, "status": "Out",
                 "shortComment": "Ankle sprain, out at least a week"},
                {"athlete": {"id": "1004", "displayName": "ATL Player4"}, "status": "Day-To-Day",
                 "shortComment": "Questionable with back tightness"}]},
            {"id": "14", "displayName": "LAL Team", "injuries": [
                {"athlete": {"id": "14005", "displayName": "LAL Player5"}, "status": "Out",
                 "shortComment": "Knee"}]}]}

    def roster_json(self, tid):
        return {"athletes": [{"id": p["id"], "displayName": p["name"], "position": {"abbreviation": p["pos"]}}
                             for p in self.players.values() if p["team"] == tid]}

    def gamelog_json(self, pid, season):
        rows = self.logs.get(pid, {}).get(season, [])
        events, cat_events = {}, []
        for eid, l in rows:
            e = self.events[eid]
            tid = self.players[pid]["team"]
            opp = e["away"] if e["home"] == tid else e["home"]
            events[eid] = {"id": eid, "gameDate": e["date"].strftime("%Y-%m-%dT%H:%M:%S.000+00:00"),
                           "atVs": "vs" if e["home"] == tid else "@",
                           "opponent": {"id": opp, "abbreviation": TEAMS[opp]},
                           "homeTeamId": e["home"], "awayTeamId": e["away"], "gameResult": "W"}
            cat_events.append({"eventId": eid, "stats": [
                str(l["min"]), f"{l['pts'] // 2}-{l['pts']}", "45.0", f"{l['fg3']}-{l['fg3a']}", "35.0",
                "2-2", "100", str(l["reb"]), str(l["ast"]), str(l["blk"]), str(l["stl"]), "2", str(l["tov"]), str(l["pts"])]})
        return {
            "labels": ["MIN", "FG", "FG%", "3PT", "3P%", "FT", "FT%", "REB", "AST", "BLK", "STL", "PF", "TO", "PTS"],
            "names": ["minutes", "fieldGoalsMade-fieldGoalsAttempted", "fieldGoalPct",
                      "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "threePointFieldGoalPct",
                      "freeThrowsMade-freeThrowsAttempted", "freeThrowPct", "totalRebounds", "assists", "blocks",
                      "steals", "fouls", "turnovers", "points"],
            "events": events,
            "seasonTypes": [{"displayName": f"{season - 1}-{str(season)[2:]} Regular Season",
                             "categories": [{"type": "event", "events": list(reversed(cat_events))}]}]}


class FakeHttp:
    def __init__(self, league: League):
        self.lg = league
        self.calls = 0

    def get_json(self, url, params=None, ttl=None):
        self.calls += 1
        params = params or {}
        if url.endswith("/scoreboard"):
            past = self.lg.past_scoreboard(params.get("dates", ""))
            return past or self.lg.scoreboard_json()
        if url.endswith("/injuries"):
            return self.lg.injuries_json()
        if url.endswith("/roster"):
            return self.lg.roster_json(url.split("/teams/")[1].split("/")[0])
        if url.endswith("/teams"):
            return self.lg.teams_json()
        if url.endswith("/gamelog"):
            return self.lg.gamelog_json(url.split("/athletes/")[1].split("/")[0], int(params["season"]))
        return None

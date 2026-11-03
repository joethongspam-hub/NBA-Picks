"""Simulated NHL league in ESPN-like JSON. Planted truths: team 5 allows +20% shots to forwards;
team 1's top center (id '101') is OUT; team 2's goalie '119' is elite (.925)."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from tests.fake_espn import _poisson

ABBRS = ["ANA", "BOS", "BUF", "CGY", "CAR", "CHI", "COL", "CBJ", "DAL", "DET", "EDM", "FLA", "LA", "MIN", "MTL", "NSH",
         "NJ", "NYI", "NYR", "OTT", "PHI", "PIT", "SJ", "SEA", "STL", "TB", "TOR", "UTA", "VAN", "VGK", "WSH", "WPG"]
TEAMS = {str(i + 1): a for i, a in enumerate(ABBRS)}
ROLES = ["C", "C", "C", "C", "LW", "LW", "LW", "LW", "RW", "RW", "RW", "RW", "D", "D", "D", "D", "D", "D", "G", "G"]
TOI = [20, 17, 14, 11, 19, 16, 13, 10, 19, 16, 13, 10, 24, 22, 20, 18, 16, 14, 60, 60]
TODAY = datetime(2026, 11, 3, tzinfo=timezone.utc)


class NhlLeague:
    def __init__(self, seed=5):
        rng = self.rng = random.Random(seed)
        self.players = {}
        for tid in TEAMS:
            for j, pos in enumerate(ROLES):
                pid = f"{tid}{j + 1:02d}"
                self.players[pid] = dict(id=pid, team=tid, pos=pos, j=j, name=f"{TEAMS[tid]} {pos}{j + 1}",
                                         shot60=(rng.uniform(7, 11) if pos != "D" else rng.uniform(4, 6)) * (1.2 if j in (0, 4, 8) else 1),
                                         sh=0.11 if pos != "D" else 0.05, a60=rng.uniform(1.0, 2.0) if pos != "D" else rng.uniform(0.8, 1.4),
                                         sv=0.925 if pid == "219" else rng.uniform(0.895, 0.912))
        self.logs = {pid: {2026: [], 2027: []} for pid in self.players}
        self.events, self.days = {}, {}
        eid = 401890000
        for season, n_rounds, start in ((2026, 82, datetime(2025, 10, 8, 23, tzinfo=timezone.utc)),
                                        (2027, 12, datetime(2026, 10, 8, 23, tzinfo=timezone.utc))):
            for r in range(n_rounds):
                ids = list(TEAMS)
                rng.shuffle(ids)
                day = start + timedelta(days=int(r * (2.1 if season == 2026 else 2.0)))
                for k in range(0, 32, 2):
                    eid += 1
                    h, a = ids[k], ids[k + 1]
                    final = day < TODAY
                    e = dict(home=h, away=a, date=day, season=season, final=final, score={h: 0, a: 0})
                    self.events[str(eid)] = e
                    self.days.setdefault(day.strftime("%Y%m%d"), []).append(str(eid))
                    if final:
                        for tid, opp in ((h, a), (a, h)):
                            self._box(str(eid), season, tid, opp, e)

    def _box(self, eid, season, tid, opp, e):
        rng = self.rng
        goalie_opp = next(p for p in self.players.values() if p["team"] == opp and p["j"] == 18)
        team_shots = 0
        for p in [p for p in self.players.values() if p["team"] == tid and p["pos"] != "G"]:
            if p["id"] == "101" and season == 2027 and e["date"] > TODAY - timedelta(days=5):
                continue
            toi = max(5.0, rng.gauss(TOI[p["j"]], 2))
            boost = 1.2 if (opp == "5" and p["pos"] != "D") else 1.0
            sog = _poisson(rng, p["shot60"] * toi / 60 * boost)
            g = sum(rng.random() < p["sh"] * (1 - (goalie_opp["sv"] - 0.9) * 5) for _ in range(sog))
            a = _poisson(rng, p["a60"] * toi / 60)
            team_shots += sog
            e["score"][tid] += g
            self.logs[p["id"]][season].append((eid, dict(g=g, a=a, pts=g + a, sog=sog, toi=round(toi, 1))))
        sa = team_shots
        ga = e["score"][tid]
        self.logs[goalie_opp["id"]][season].append((eid, dict(gs=1, toi=60.0, ga=ga, sa=sa, sv=sa - ga)))

    # ------------------------------------------------------------------ ESPN shapes
    def teams_json(self):
        return {"sports": [{"leagues": [{"teams": [{"team": {"id": t, "abbreviation": a, "displayName": a}}
                                                  for t, a in TEAMS.items()]}]}]}

    def scoreboard_json(self, d):
        evs = []
        for eid in self.days.get(d, []):
            e = self.events[eid]
            evs.append({"id": eid, "date": e["date"].strftime("%Y-%m-%dT%H:%MZ"),
                        "status": {"type": {"description": "Final" if e["final"] else "Scheduled"}},
                        "competitions": [{"competitors": [
                            {"homeAway": "home", "team": {"id": e["home"], "abbreviation": TEAMS[e["home"]], "displayName": TEAMS[e["home"]]}},
                            {"homeAway": "away", "team": {"id": e["away"], "abbreviation": TEAMS[e["away"]], "displayName": TEAMS[e["away"]]}}],
                            "odds": [{"details": f"{TEAMS[e['home']]} -130", "overUnder": 6.0}]}]})
        return {"events": evs}

    def schedule_json(self, tid, season):
        evs = []
        for eid, e in self.events.items():
            if tid not in (e["home"], e["away"]) or e["season"] != season or not e["final"]:
                continue
            evs.append({"id": eid, "date": e["date"].strftime("%Y-%m-%dT%H:%MZ"),
                        "competitions": [{"status": {"type": {"completed": True}}, "competitors": [
                            {"homeAway": "home", "id": e["home"], "score": {"value": float(e["score"][e["home"]])}},
                            {"homeAway": "away", "id": e["away"], "score": {"value": float(e["score"][e["away"]])}}]}]})
        return {"events": evs}

    def core_odds_json(self, eid):
        return {"items": [{"provider": {"id": "100"}, "overUnder": 6.0, "overOdds": -110, "underOdds": -110,
                           "homeTeamOdds": {"favorite": True, "moneyLine": -130, "spreadOdds": 190,
                                            "current": {"pointSpread": {"american": "-1.5"}}},
                           "awayTeamOdds": {"favorite": False, "moneyLine": 110, "spreadOdds": -230,
                                            "current": {"pointSpread": {"american": "+1.5"}}}}]}

    def injuries_json(self):
        return {"injuries": [{"id": "1", "injuries": [{"athlete": {"id": "101", "displayName": "ANA C1"}, "status": "Out",
                                                       "shortComment": "Lower body"}]}]}

    def roster_json(self, tid):
        return {"athletes": [{"position": "x", "items": [{"id": p["id"], "displayName": p["name"],
                                                          "position": {"abbreviation": p["pos"]}}
                                                         for p in self.players.values() if p["team"] == tid]}]}

    def gamelog_json(self, pid, season):
        p = self.players[pid]
        goalie = p["pos"] == "G"
        if goalie:
            names = ["gameStarted", "timeOnIcePerGame", "wins", "losses", "ties", "overtimeLosses", "goalsAgainst",
                     "avgGoalsAgainst", "shotsAgainst", "saves", "savePct", "shutouts"]
        else:
            names = ["goals", "assists", "points", "plusMinus", "penaltyMinutes", "shotsTotal", "shootingPct",
                     "powerPlayGoals", "powerPlayAssists", "shortHandedGoals", "shortHandedAssists", "gameWinningGoals",
                     "timeOnIcePerGame", "production"]
        events, rows = {}, []
        for eid, s in self.logs[pid][season]:
            e = self.events[eid]
            opp = e["away"] if e["home"] == p["team"] else e["home"]
            events[eid] = {"id": eid, "gameDate": e["date"].strftime("%Y-%m-%dT%H:%M:%S.000+00:00"),
                           "atVs": "vs" if e["home"] == p["team"] else "@", "opponent": {"id": opp, "abbreviation": TEAMS[opp]},
                           "homeTeamId": e["home"], "awayTeamId": e["away"]}
            m, sec = int(s["toi"]), int((s["toi"] % 1) * 60)
            if goalie:
                stats = ["1", f"{m}:{sec:02d}", "0", "0", "0", "0", str(s["ga"]), "0", str(s["sa"]), str(s["sv"]), ".900", "0"]
            else:
                stats = [str(s["g"]), str(s["a"]), str(s["pts"]), "0", "0", str(s["sog"]), "0", "0", "0", "0", "0", "0",
                         f"{m}:{sec:02d}", "0"]
            rows.append({"eventId": eid, "stats": stats})
        return {"labels": [], "names": names, "events": events,
                "seasonTypes": [{"displayName": f"{season - 1}-{str(season)[2:]} Regular Season",
                                 "categories": [{"events": list(reversed(rows))}]}]}


class FakeNhlHttp:
    def __init__(self, lg):
        self.lg = lg

    def get_json(self, url, params=None, ttl=None):
        params = params or {}
        if url.endswith("/schedule"):
            return self.lg.schedule_json(url.split("/teams/")[1].split("/")[0], int(params["season"]))
        if url.endswith("/odds") and "/competitions/" in url:
            return self.lg.core_odds_json(url.split("/events/")[1].split("/")[0])
        if url.endswith("/scoreboard"):
            return self.lg.scoreboard_json(params.get("dates", ""))
        if url.endswith("/injuries"):
            return self.lg.injuries_json()
        if url.endswith("/roster"):
            return self.lg.roster_json(url.split("/teams/")[1].split("/")[0])
        if url.endswith("/teams"):
            return self.lg.teams_json()
        if url.endswith("/gamelog"):
            return self.lg.gamelog_json(url.split("/athletes/")[1].split("/")[0], int(params["season"]))
        return None

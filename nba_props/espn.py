"""ESPN public JSON endpoints (no API key) -> plain Python data.

ESPN's undocumented feeds shift shape now and then, so every parser here is
defensive: it looks fields up by name rather than position and tolerates the
alternative layouts seen in the wild.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .http import Http

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
COMMON = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba"


# ----------------------------------------------------------------------------- models
@dataclass
class Team:
    id: str
    abbr: str
    name: str


@dataclass
class Game:
    id: str
    date: datetime
    home: Team
    away: Team
    status: str = ""
    spread_home: float | None = None   # negative = home favoured
    total: float | None = None
    odds_text: str = ""

    @property
    def label(self) -> str:
        return f"{self.away.abbr} @ {self.home.abbr}"

    def implied_total(self, team_id: str) -> float | None:
        if self.total is None:
            return None
        s = self.spread_home or 0.0
        home_tt = self.total / 2 - s / 2
        return home_tt if team_id == self.home.id else self.total - home_tt


@dataclass
class Injury:
    athlete_id: str
    name: str
    team_id: str
    status: str          # Out, Doubtful, Questionable, Day-To-Day, Probable ...
    detail: str = ""

    @property
    def level(self) -> str:
        s = self.status.lower()
        if "out" in s or "suspen" in s or "injured reserve" in s:
            return "OUT"
        if "doubt" in s:
            return "DOUBTFUL"
        if "question" in s or "day-to-day" in s or "game-time" in s or "gtd" in s:
            return "QUESTIONABLE"
        if "probable" in s:
            return "PROBABLE"
        return "QUESTIONABLE"


@dataclass
class GameLine:
    """One player's box score line for one game."""
    event_id: str
    date: datetime
    opp_id: str
    opp_abbr: str
    home: bool
    min: float
    pts: float
    reb: float
    ast: float
    stl: float
    blk: float
    tov: float
    fg3m: float
    season: int
    team_id: str = ""

    def get(self, stat: str) -> float:
        return STAT_FUNCS[stat](self)


STAT_FUNCS = {
    "PTS": lambda g: g.pts,
    "REB": lambda g: g.reb,
    "AST": lambda g: g.ast,
    "3PM": lambda g: g.fg3m,
    "STL": lambda g: g.stl,
    "BLK": lambda g: g.blk,
    "TOV": lambda g: g.tov,
    "PRA": lambda g: g.pts + g.reb + g.ast,
    "PR": lambda g: g.pts + g.reb,
    "PA": lambda g: g.pts + g.ast,
    "RA": lambda g: g.reb + g.ast,
    "STOCKS": lambda g: g.stl + g.blk,
}


@dataclass
class Player:
    id: str
    name: str
    team_id: str
    pos: str
    age: float | None = None
    logs: list[GameLine] = field(default_factory=list)   # all seasons, newest first

    @property
    def pos_group(self) -> str:
        p = (self.pos or "").upper()
        if p.startswith("C"):
            return "C"
        if "G" in p and not p.startswith("F"):
            return "G"
        return "F"


# ----------------------------------------------------------------------------- helpers
def _num(v: Any) -> float:
    if v is None:
        return 0.0
    s = str(v).strip()
    if s in ("", "-", "--"):
        return 0.0
    if "-" in s and not s.startswith("-"):      # "12-24" made-attempted -> made
        s = s.split("-")[0]
    if ":" in s:                                 # "34:12" minutes
        m, sec = s.split(":")[:2]
        return float(m) + float(sec) / 60
    try:
        return float(s)
    except ValueError:
        return 0.0


def _date(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%dT%H:%M%z"):
        try:
            return datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def season_for(d: datetime) -> int:
    """ESPN labels a season by the year it ends (2026-27 -> 2027)."""
    return d.year + 1 if d.month >= 8 else d.year


# ----------------------------------------------------------------------------- client
class Espn:
    def __init__(self, http: Http, workers: int = 8):
        self.http = http
        self.workers = workers

    # --- teams
    def teams(self) -> dict[str, Team]:
        data = self.http.get_json(f"{SITE}/teams", ttl=7 * 86400) or {}
        out: dict[str, Team] = {}
        for lg in (data.get("sports") or [{}])[0].get("leagues", []):
            for t in lg.get("teams", []):
                t = t.get("team", t)
                out[str(t["id"])] = Team(str(t["id"]), t.get("abbreviation", ""),
                                         t.get("displayName", t.get("name", "")))
        return out

    # --- schedule + vegas
    def games(self, yyyymmdd: str) -> list[Game]:
        data = self.http.get_json(f"{SITE}/scoreboard", {"dates": yyyymmdd}, ttl=1800) or {}
        games = []
        for ev in data.get("events", []):
            comp = (ev.get("competitions") or [{}])[0]
            teams = {}
            for c in comp.get("competitors", []):
                t = c.get("team", {})
                teams[c.get("homeAway")] = Team(str(t.get("id")), t.get("abbreviation", ""),
                                                t.get("displayName", ""))
            if "home" not in teams or "away" not in teams:
                continue
            g = Game(str(ev.get("id")), _date(ev.get("date") or comp.get("date")) or datetime.now(),
                     teams["home"], teams["away"],
                     status=((ev.get("status") or {}).get("type") or {}).get("description", ""))
            self._parse_odds(g, comp.get("odds") or [])
            if g.total is None:
                # Past games drop odds from the scoreboard; the game summary's
                # "pickcenter" usually keeps the closing line.
                try:
                    summ = self.http.get_json(f"{SITE}/summary", {"event": g.id}, ttl=6 * 3600) or {}
                    self._parse_odds(g, summ.get("pickcenter") or summ.get("odds") or [])
                except Exception:
                    pass
            games.append(g)
        return games

    @staticmethod
    def _parse_odds(g: Game, odds: list) -> None:
        if not odds:
            return
        o = odds[0]
        g.odds_text = o.get("details", "") or ""
        try:
            g.total = float(o["overUnder"]) if o.get("overUnder") not in (None, "") else None
        except (TypeError, ValueError):
            g.total = None
        # Prefer the explicit "details" string ("BOS -5.5") since sign conventions
        # on the numeric "spread" field have varied.
        m = re.match(r"\s*([A-Z]{2,4})\s+([-+]?\d+(?:\.\d+)?)", g.odds_text)
        if m:
            fav, line = m.group(1), abs(float(m.group(2)))
            if fav == g.home.abbr:
                g.spread_home = -line
            elif fav == g.away.abbr:
                g.spread_home = line
        elif g.odds_text.upper() in ("EVEN", "PK", "PICK"):
            g.spread_home = 0.0
        if g.spread_home is None and o.get("spread") is not None:
            try:
                sp = float(o["spread"])
                home_fav = (o.get("homeTeamOdds") or {}).get("favorite")
                g.spread_home = -abs(sp) if home_fav else (abs(sp) if home_fav is False else sp)
            except (TypeError, ValueError):
                pass

    # --- injuries
    def injuries(self) -> dict[str, Injury]:
        return parse_injuries(self.http.get_json(f"{SITE}/injuries", ttl=1200) or {})

    def roster(self, team_id: str) -> list[Player]:
        data = self.http.get_json(f"{SITE}/teams/{team_id}/roster", ttl=6 * 3600) or {}
        raw = data.get("athletes") or []
        if raw and isinstance(raw[0], dict) and "items" in raw[0]:      # grouped layout
            raw = [a for grp in raw for a in grp.get("items", [])]
        out = []
        for a in raw:
            pos = a.get("position") or {}
            out.append(Player(str(a.get("id")), a.get("displayName") or a.get("fullName", ""),
                              str(team_id), pos.get("abbreviation", "") if isinstance(pos, dict) else str(pos),
                              age=a.get("age")))
        return out

    # --- game logs
    def gamelog(self, athlete_id: str, season: int, ttl: int) -> list[GameLine]:
        data = self.http.get_json(f"{COMMON}/athletes/{athlete_id}/gamelog", {"season": season}, ttl=ttl)
        return parse_gamelog(data, season) if data else []

    def load_logs(self, players: list[Player], seasons: list[int], current: int,
                  current_ttl: int = 3 * 3600) -> None:
        def job(args):
            p, s = args
            # Past seasons never change: cache them for a month.
            ttl = current_ttl if s == current else 30 * 86400
            try:
                return p, self.gamelog(p.id, s, ttl)
            except Exception:
                return p, []

        tasks = [(p, s) for p in players for s in seasons]
        with ThreadPoolExecutor(self.workers) as ex:
            for p, lines in ex.map(job, tasks):
                p.logs.extend(lines)
        for p in players:
            seen = set()
            uniq = []
            for g in sorted(p.logs, key=lambda g: g.date, reverse=True):
                if g.event_id not in seen:
                    seen.add(g.event_id)
                    uniq.append(g)
            p.logs = uniq


def parse_injuries(data: dict) -> dict[str, Injury]:
    out: dict[str, Injury] = {}
    groups = data.get("injuries") or data.get("items") or []
    for grp in groups:
        team_id = str(grp.get("id") or (grp.get("team") or {}).get("id") or "")
        for it in grp.get("injuries", [grp]):
            ath = it.get("athlete") or {}
            aid = str(ath.get("id") or "")
            if not aid:
                m = re.search(r"/athletes/(\d+)", str(ath.get("links") or ath.get("$ref") or ""))
                aid = m.group(1) if m else ""
            name = ath.get("displayName") or ath.get("fullName") or ""
            if not (aid or name):
                continue
            tid = str((it.get("team") or ath.get("team") or {}).get("id") or team_id)
            detail = it.get("shortComment") or it.get("longComment") or ""
            det = it.get("details") or {}
            if isinstance(det, dict) and det.get("type"):
                detail = f"{det.get('type')} {det.get('detail', '')} - {detail}".strip(" -")
            out[aid or name] = Injury(aid, name, tid, str(it.get("status") or ""), detail)
    return out


# ----------------------------------------------------------------------------- gamelog parser
_LABEL_ALIASES = {
    "MIN": ("MIN", "minutes"),
    "PTS": ("PTS", "points"),
    "REB": ("REB", "totalRebounds", "rebounds"),
    "AST": ("AST", "assists"),
    "STL": ("STL", "steals"),
    "BLK": ("BLK", "blocks"),
    "TO": ("TO", "turnovers", "TOV"),
    "3PT": ("3PT", "3PM", "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "threePointsMade",
            "threePointFieldGoalsMade"),
}


def _index_map(labels: list[str], names: list[str]) -> dict[str, int]:
    idx: dict[str, int] = {}
    for key, aliases in _LABEL_ALIASES.items():
        for seq in (labels, names):
            hit = next((i for i, v in enumerate(seq) if v in aliases), None)
            if hit is not None:
                idx[key] = hit
                break
    return idx


def parse_gamelog(data: dict, season: int) -> list[GameLine]:
    labels = [str(x) for x in data.get("labels") or []]
    names = [str(x) for x in data.get("names") or []]
    idx = _index_map(labels, names)
    meta = data.get("events") or {}
    if isinstance(meta, list):                     # flattened layout
        meta_by_id = {str(e.get("id") or e.get("eventId")): e for e in meta}
        rows = [(str(e.get("id") or e.get("eventId")), e.get("stats") or []) for e in meta]
    else:
        meta_by_id = {str(k): v for k, v in meta.items()}
        rows = []
        for st in data.get("seasonTypes") or []:
            stname = (st.get("displayName") or st.get("name") or "").lower()
            if "preseason" in stname or "all-star" in stname:
                continue
            for cat in st.get("categories") or []:
                for ev in cat.get("events") or []:
                    rows.append((str(ev.get("eventId") or ev.get("id")), ev.get("stats") or []))
    out = []
    for eid, stats in rows:
        m = meta_by_id.get(eid, {})
        if not stats or "MIN" not in idx:
            continue

        def s(k):
            i = idx.get(k)
            return _num(stats[i]) if i is not None and i < len(stats) else 0.0

        mins = s("MIN")
        if mins <= 0:
            continue
        opp = m.get("opponent") or {}
        at_vs = str(m.get("atVs") or "")
        home_id = str(m.get("homeTeamId") or "")
        opp_id = str(opp.get("id") or "")
        is_home = (at_vs.lower() == "vs") if at_vs else (home_id and home_id != opp_id)
        team_id = ""
        if home_id or m.get("awayTeamId"):
            ids = {home_id, str(m.get("awayTeamId") or "")} - {opp_id, ""}
            team_id = ids.pop() if ids else ""
        out.append(GameLine(
            event_id=eid,
            date=_date(m.get("gameDate") or m.get("date")) or datetime(season - 1, 11, 1),
            opp_id=opp_id, opp_abbr=opp.get("abbreviation", ""), home=bool(is_home),
            min=mins, pts=s("PTS"), reb=s("REB"), ast=s("AST"), stl=s("STL"), blk=s("BLK"),
            tov=s("TO"), fg3m=s("3PT"), season=season, team_id=team_id,
        ))
    return out

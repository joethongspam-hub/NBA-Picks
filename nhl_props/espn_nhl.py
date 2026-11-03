"""ESPN NHL feeds -> plain Python data (schedule + odds, injuries, rosters, skater/goalie game logs)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

from nba_props.espn import Espn, Game, Injury, Team, _date, _num, parse_injuries
from nba_props.http import Http

SITE = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"
COMMON = "https://site.web.api.espn.com/apis/common/v3/sports/hockey/nhl"

SKATER_NAMES = {"goals": "g", "assists": "a", "points": "pts", "shotsTotal": "sog", "timeOnIcePerGame": "toi",
                "powerPlayGoals": "ppg", "powerPlayAssists": "ppa"}
SKATER_LABELS = {"G": "g", "A": "a", "PTS": "pts", "S": "sog", "SOG": "sog", "TOI/G": "toi", "TOI": "toi"}
GOALIE_NAMES = {"gameStarted": "gs", "timeOnIcePerGame": "toi", "goalsAgainst": "ga", "shotsAgainst": "sa", "saves": "sv"}
GOALIE_LABELS = {"GS": "gs", "TOI/G": "toi", "TOI": "toi", "GA": "ga", "SA": "sa", "SV": "sv"}


@dataclass
class NhlLine:
    event_id: str
    date: datetime
    opp_id: str
    opp_abbr: str
    home: bool
    season: int
    team_id: str = ""
    s: dict = field(default_factory=dict)

    def get(self, stat: str) -> float:
        return STAT_FUNCS[stat](self.s)


STAT_FUNCS = {
    "SOG": lambda s: s.get("sog", 0), "PTS": lambda s: s.get("pts", 0), "AST": lambda s: s.get("a", 0),
    "GOALS": lambda s: s.get("g", 0), "SAVES": lambda s: s.get("sv", 0),
}


@dataclass
class NhlPlayer:
    id: str
    name: str
    team_id: str
    pos: str                  # C, LW, RW, D, G
    logs: list[NhlLine] = field(default_factory=list)

    @property
    def group(self) -> str:
        return "G" if self.pos == "G" else "D" if self.pos == "D" else "F"


def season_for(d: datetime) -> int:
    return d.year + 1 if d.month >= 8 else d.year


class EspnNhl:
    def __init__(self, http: Http, workers: int = 8):
        self.http = http
        self.workers = workers

    def teams(self) -> dict[str, Team]:
        data = self.http.get_json(f"{SITE}/teams", ttl=7 * 86400) or {}
        out = {}
        for lg in (data.get("sports") or [{}])[0].get("leagues", []):
            for t in lg.get("teams", []):
                t = t.get("team", t)
                out[str(t["id"])] = Team(str(t["id"]), t.get("abbreviation", ""), t.get("displayName", ""))
        return out

    def games(self, yyyymmdd: str) -> list[Game]:
        data = self.http.get_json(f"{SITE}/scoreboard", {"dates": yyyymmdd}, ttl=1800) or {}
        out = []
        for ev in data.get("events", []):
            comp = (ev.get("competitions") or [{}])[0]
            teams = {}
            for c in comp.get("competitors", []):
                t = c.get("team", {})
                teams[c.get("homeAway")] = Team(str(t.get("id")), t.get("abbreviation", ""), t.get("displayName", ""))
            if "home" not in teams or "away" not in teams:
                continue
            st = (ev.get("status") or {}).get("type") or {}
            g = Game(str(ev.get("id")), _date(ev.get("date") or comp.get("date")) or datetime.now(),
                     teams["home"], teams["away"], status=st.get("description", ""))
            o = (comp.get("odds") or [{}])[0] if comp.get("odds") else {}
            try:
                g.total = float(o["overUnder"]) if o.get("overUnder") not in (None, "") else None
            except (TypeError, ValueError):
                g.total = None
            g.odds_text = o.get("details", "") or ""
            out.append(g)
        return out

    def injuries(self) -> dict[str, Injury]:
        return parse_injuries(self.http.get_json(f"{SITE}/injuries", ttl=1200) or {})

    def roster(self, team_id: str) -> list[NhlPlayer]:
        data = self.http.get_json(f"{SITE}/teams/{team_id}/roster", ttl=6 * 3600) or {}
        raw = data.get("athletes") or []
        if raw and isinstance(raw[0], dict) and "items" in raw[0]:
            raw = [a for grp in raw for a in grp.get("items", [])]
        out = []
        for a in raw:
            pos = a.get("position") or {}
            ab = (pos.get("abbreviation", "") if isinstance(pos, dict) else str(pos)).upper()
            if ab in ("C", "LW", "RW", "W", "F", "D", "G"):
                out.append(NhlPlayer(str(a.get("id")), a.get("displayName") or a.get("fullName", ""), str(team_id),
                                     "LW" if ab in ("W", "F") else ab))
        return out

    def load_logs(self, players: list[NhlPlayer], seasons: list[int], current: int, current_ttl: int = 3 * 3600):
        def job(args):
            p, s = args
            ttl = current_ttl if s == current else 30 * 86400
            try:
                data = self.http.get_json(f"{COMMON}/athletes/{p.id}/gamelog", {"season": s}, ttl=ttl)
                return p, parse_gamelog(data, s, p.pos == "G") if data else []
            except Exception:
                return p, []

        with ThreadPoolExecutor(self.workers) as ex:
            for p, lines in ex.map(job, [(p, s) for p in players for s in seasons]):
                p.logs.extend(lines)
        for p in players:
            seen, uniq = set(), []
            for g in sorted(p.logs, key=lambda g: g.date, reverse=True):
                if g.event_id not in seen:
                    seen.add(g.event_id)
                    uniq.append(g)
            p.logs = uniq


def parse_gamelog(data: dict, season: int, goalie: bool) -> list[NhlLine]:
    labels = [str(x) for x in data.get("labels") or []]
    names = [str(x) for x in data.get("names") or []]
    nm_map, lb_map = (GOALIE_NAMES, GOALIE_LABELS) if goalie else (SKATER_NAMES, SKATER_LABELS)
    idx = {}
    for i, n in enumerate(names):
        if n in nm_map:
            idx.setdefault(nm_map[n], i)
    if not idx:
        for i, l in enumerate(labels):
            if l in lb_map:
                idx.setdefault(lb_map[l], i)
    meta = data.get("events") or {}
    meta_by_id = {str(k): v for k, v in meta.items()} if isinstance(meta, dict) else \
        {str(e.get("id") or e.get("eventId")): e for e in meta}
    rows = []
    for st in data.get("seasonTypes") or []:
        nm = (st.get("displayName") or "").lower()
        if "preseason" in nm or "all-star" in nm:
            continue
        for cat in st.get("categories") or []:
            for ev in cat.get("events") or []:
                rows.append((str(ev.get("eventId") or ev.get("id")), ev.get("stats") or []))
    out = []
    for eid, stats in rows:
        if not stats or not idx:
            continue
        m = meta_by_id.get(eid, {})
        vals = {}
        for f, i in idx.items():
            vals[f] = _num(stats[i]) if i < len(stats) else 0.0
        if vals.get("toi", 0) <= 0:
            continue
        opp = m.get("opponent") or {}
        home_id, opp_id = str(m.get("homeTeamId") or ""), str(opp.get("id") or "")
        ids = {home_id, str(m.get("awayTeamId") or "")} - {opp_id, ""}
        at_vs = str(m.get("atVs") or "")
        out.append(NhlLine(eid, _date(m.get("gameDate") or m.get("date")) or datetime(season - 1, 11, 1),
                           opp_id, opp.get("abbreviation", ""),
                           (at_vs.lower() == "vs") if at_vs else bool(home_id and home_id != opp_id),
                           season, ids.pop() if ids else "", vals))
    return out

"""ESPN NFL feeds -> plain Python data (schedule + odds, injuries, rosters, game logs).

Like the NBA client, parsers look fields up by name and tolerate layout changes.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

from nba_props.espn import Espn, Game, Injury, Team, _date, _num, parse_injuries
from nba_props.http import Http

SITE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
COMMON = "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl"
SKILL = {"QB", "RB", "FB", "WR", "TE"}

FIELDS = ["pass_att", "cmp", "pass_yds", "pass_td", "ints", "rush_att", "rush_yds", "rush_td",
          "tgt", "rec", "rec_yds", "rec_td"]

# ESPN gamelog "names" -> our field
NAME_MAP = {
    "completions": "cmp", "passingAttempts": "pass_att", "passingYards": "pass_yds",
    "passingTouchdowns": "pass_td", "interceptions": "ints",
    "rushingAttempts": "rush_att", "rushingYards": "rush_yds", "rushingTouchdowns": "rush_td",
    "receptions": "rec", "receivingTargets": "tgt", "receivingYards": "rec_yds",
    "receivingTouchdowns": "rec_td",
}
# Fallback when only labels are present: (category-start label, label) -> field
LABEL_SEQ = {
    "passing": {"CMP": "cmp", "ATT": "pass_att", "YDS": "pass_yds", "TD": "pass_td", "INT": "ints"},
    "rushing": {"CAR": "rush_att", "ATT": "rush_att", "YDS": "rush_yds", "TD": "rush_td"},
    "receiving": {"REC": "rec", "TGTS": "tgt", "TGT": "tgt", "YDS": "rec_yds", "TD": "rec_td"},
}
CAT_START = {"CMP": "passing", "C/ATT": "passing", "CAR": "rushing", "REC": "receiving", "FUM": None}


@dataclass
class NflLine:
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
    "PASS_YDS": lambda s: s["pass_yds"], "PASS_ATT": lambda s: s["pass_att"], "PASS_CMP": lambda s: s["cmp"],
    "PASS_TD": lambda s: s["pass_td"], "INT": lambda s: s["ints"],
    "RUSH_YDS": lambda s: s["rush_yds"], "RUSH_ATT": lambda s: s["rush_att"],
    "REC": lambda s: s["rec"], "REC_YDS": lambda s: s["rec_yds"],
    "RUSH_REC_YDS": lambda s: s["rush_yds"] + s["rec_yds"],
    "ANY_TD": lambda s: s["rush_td"] + s["rec_td"],
}


@dataclass
class NflPlayer:
    id: str
    name: str
    team_id: str
    pos: str
    logs: list[NflLine] = field(default_factory=list)

    @property
    def pos_group(self) -> str:
        return "RB" if self.pos in ("RB", "FB") else self.pos


def season_for(d: datetime) -> int:
    """NFL seasons are labelled by the year they start (Sept 2026 -> 2026)."""
    return d.year if d.month >= 3 else d.year - 1


class EspnNfl:
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

    def week(self, season: int | None = None, week: int | None = None, seasontype: int = 2):
        """Return (week_number, games). With no week, the current week from ESPN."""
        params = {}
        if week is not None:
            params = {"seasontype": seasontype, "week": week, "dates": season}
        data = self.http.get_json(f"{SITE}/scoreboard", params, ttl=1800) or {}
        wk = (data.get("week") or {}).get("number")
        games = []
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
                     teams["home"], teams["away"], status=st.get("description", "") or st.get("name", ""))
            Espn._parse_odds(g, comp.get("odds") or [])
            if g.total is None:
                try:
                    summ = self.http.get_json(f"{SITE}/summary", {"event": g.id}, ttl=6 * 3600) or {}
                    Espn._parse_odds(g, summ.get("pickcenter") or summ.get("odds") or [])
                except Exception:
                    pass
            games.append(g)
        return wk, games

    def injuries(self) -> dict[str, Injury]:
        return parse_injuries(self.http.get_json(f"{SITE}/injuries", ttl=1200) or {})

    def roster(self, team_id: str) -> list[NflPlayer]:
        data = self.http.get_json(f"{SITE}/teams/{team_id}/roster", ttl=6 * 3600) or {}
        raw = data.get("athletes") or []
        if raw and isinstance(raw[0], dict) and "items" in raw[0]:
            raw = [a for grp in raw for a in grp.get("items", [])]
        out = []
        for a in raw:
            pos = a.get("position") or {}
            ab = (pos.get("abbreviation", "") if isinstance(pos, dict) else str(pos)).upper()
            if ab in SKILL:
                out.append(NflPlayer(str(a.get("id")), a.get("displayName") or a.get("fullName", ""),
                                     str(team_id), "RB" if ab == "FB" else ab))
        return out

    def load_logs(self, players: list[NflPlayer], seasons: list[int], current: int, current_ttl: int = 6 * 3600):
        def job(args):
            p, s = args
            ttl = current_ttl if s == current else 30 * 86400
            try:
                data = self.http.get_json(f"{COMMON}/athletes/{p.id}/gamelog", {"season": s}, ttl=ttl)
                return p, parse_gamelog(data, s) if data else []
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


def _field_index(labels: list[str], names: list[str]) -> dict[str, int]:
    idx = {}
    for i, n in enumerate(names):
        f = NAME_MAP.get(n)
        if f and f not in idx:
            idx[f] = i
    if idx:
        return idx
    cat = None
    for i, lab in enumerate(labels):
        lab = lab.upper()
        if lab in CAT_START:
            cat = CAT_START[lab]
        if lab == "C/ATT":
            idx.setdefault("cmp", i)
            idx.setdefault("pass_att", i)
        elif cat and lab in LABEL_SEQ[cat]:
            f = LABEL_SEQ[cat][lab]
            idx.setdefault(f, i)
    return idx


def parse_gamelog(data: dict, season: int) -> list[NflLine]:
    labels = [str(x) for x in data.get("labels") or []]
    names = [str(x) for x in data.get("names") or []]
    idx = _field_index(labels, names)
    meta = data.get("events") or {}
    if isinstance(meta, list):
        meta_by_id = {str(e.get("id") or e.get("eventId")): e for e in meta}
        rows = [(str(e.get("id") or e.get("eventId")), e.get("stats") or []) for e in meta]
    else:
        meta_by_id = {str(k): v for k, v in meta.items()}
        rows = []
        for st in data.get("seasonTypes") or []:
            nm = (st.get("displayName") or st.get("name") or "").lower()
            if "preseason" in nm or "pro bowl" in nm:
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
        for f in FIELDS:
            i = idx.get(f)
            raw = stats[i] if i is not None and i < len(stats) else 0
            if f in ("cmp", "pass_att") and isinstance(raw, str) and ("/" in raw or "-" in raw[1:]):   # "22/35"
                raw = raw.replace("-", "/")
                a, b = raw.split("/")[:2]
                raw = a if f == "cmp" else b
            vals[f] = _num(raw)
        opp = m.get("opponent") or {}
        at_vs = str(m.get("atVs") or "")
        home_id = str(m.get("homeTeamId") or "")
        opp_id = str(opp.get("id") or "")
        team_id = ""
        if home_id or m.get("awayTeamId"):
            ids = {home_id, str(m.get("awayTeamId") or "")} - {opp_id, ""}
            team_id = ids.pop() if ids else ""
        out.append(NflLine(eid, _date(m.get("gameDate") or m.get("date")) or datetime(season, 10, 1),
                           opp_id, opp.get("abbreviation", ""),
                           (at_vs.lower() == "vs") if at_vs else bool(home_id and home_id != opp_id),
                           season, team_id, vals))
    return out

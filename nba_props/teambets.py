"""Team bets (moneyline, spread / puck line, total) for NBA, NFL and NHL.

Model
  * Team offense/defense ratings fit to this season's scores (recency-weighted,
    opponent-adjusted, with home advantage), blended with last season early on.
  * Injury adjustment supplied by each sport's player model (points lost from
    rotation players out, backup QB, starting goalie quality).
  * Scores -> distributions: NBA/NFL margin & total ~ Normal; NHL goals ~ Poisson
    per team (moneyline incl. OT, puck line +/-1.5, total).
  * Probabilities are blended heavily toward the no-vig market (sides and totals
    are the sharpest markets), then compared with the price to get an edge.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .http import Http
from .odds import american_to_prob

SITE = "https://site.api.espn.com/apis/site/v2/sports"
CORE = "https://sports.core.api.espn.com/v2/sports"

SPORT = {
    "nba": {"path": ("basketball", "nba"), "avg": 114.0, "hfa": 2.0, "half_life": 15, "sd_margin": 12.5,
            "sd_total": 18.0, "prior_games": 10},
    "nfl": {"path": ("football", "nfl"), "avg": 22.5, "hfa": 1.5, "half_life": 5, "sd_margin": 13.5,
            "sd_total": 13.5, "prior_games": 4},
    "nhl": {"path": ("hockey", "nhl"), "avg": 3.05, "hfa": 0.15, "half_life": 15, "sd_margin": None,
            "sd_total": None, "prior_games": 10},
}
KNOBS = {"model_weight": 0.35, "prev_weight": 0.3}


def _f(v):
    try:
        if isinstance(v, dict):
            v = v.get("value", v.get("american", v.get("displayValue")))
        return float(str(v).replace("+", ""))
    except (TypeError, ValueError):
        return None


def _i(v):
    x = _f(v)
    return int(x) if x is not None else None


# ----------------------------------------------------------------------------- data
@dataclass
class Result:
    event_id: str
    date: datetime
    home: str
    away: str
    hs: float
    as_: float
    season: int


def team_results(http: Http, league: str, team_ids: list[str], seasons: list[int], current: int) -> list[Result]:
    """Completed regular-season games from each team's schedule (deduped by event)."""
    sport, lg = SPORT[league]["path"]
    out: dict[str, Result] = {}
    for season in seasons:
        ttl = 3 * 3600 if season == current else 30 * 86400
        for tid in team_ids:
            try:
                data = http.get_json(f"{SITE}/{sport}/{lg}/teams/{tid}/schedule",
                                     {"season": season, "seasontype": 2}, ttl=ttl) or {}
            except Exception:
                continue
            for ev in data.get("events", []):
                comp = (ev.get("competitions") or [{}])[0]
                st = ((comp.get("status") or ev.get("status") or {}).get("type") or {})
                if not st.get("completed"):
                    continue
                cs = {c.get("homeAway"): c for c in comp.get("competitors", [])}
                if "home" not in cs or "away" not in cs:
                    continue
                hs, as_ = _f(cs["home"].get("score")), _f(cs["away"].get("score"))
                if hs is None or as_ is None:
                    continue
                try:
                    d = datetime.fromisoformat((ev.get("date") or comp.get("date")).replace("Z", "+00:00"))
                except Exception:
                    continue
                out[str(ev.get("id"))] = Result(str(ev.get("id")), d, str(cs["home"].get("id") or (cs["home"].get("team") or {}).get("id")),
                                                str(cs["away"].get("id") or (cs["away"].get("team") or {}).get("id")),
                                                hs, as_, season)
    return sorted(out.values(), key=lambda r: r.date)


@dataclass
class GameOdds:
    spread_home: float | None = None       # home handicap (-3.5 = home favored by 3.5)
    spread_home_price: int | None = None
    spread_away_price: int | None = None
    total: float | None = None
    over_price: int | None = None
    under_price: int | None = None
    ml_home: int | None = None
    ml_away: int | None = None
    open: dict = field(default_factory=dict)


def game_odds(http: Http, league: str, event_id: str, ttl: int = 900) -> GameOdds | None:
    sport, lg = SPORT[league]["path"]
    try:
        data = http.get_json(f"{CORE}/{sport}/leagues/{lg}/events/{event_id}/competitions/{event_id}/odds", ttl=ttl) or {}
    except Exception:
        return None
    items = data.get("items") or []
    it = next((x for x in items if str((x.get("provider") or {}).get("id")) == "100"), items[0] if items else None)
    if not it:
        return None
    h, a = it.get("homeTeamOdds") or {}, it.get("awayTeamOdds") or {}
    o = GameOdds()
    o.total = _f(it.get("overUnder"))
    o.over_price, o.under_price = _i(it.get("overOdds")), _i(it.get("underOdds"))
    o.ml_home, o.ml_away = _i(h.get("moneyLine")), _i(a.get("moneyLine"))
    cur_h = ((h.get("current") or {}).get("pointSpread") or {}).get("american")
    o.spread_home = _f(cur_h)
    if o.spread_home is None and _f(it.get("spread")) is not None:
        sp = abs(_f(it.get("spread")))
        o.spread_home = -sp if h.get("favorite") else sp
    o.spread_home_price, o.spread_away_price = _i(h.get("spreadOdds")), _i(a.get("spreadOdds"))
    op_h, op_a = h.get("open") or {}, a.get("open") or {}
    o.open = {"spread_home": _f((op_h.get("pointSpread") or {}).get("american")),
              "ml_home": _i((op_h.get("moneyLine") or {}).get("american")),
              "ml_away": _i((op_a.get("moneyLine") or {}).get("american")),
              "total": _f(((it.get("open") or {}).get("total") or {}).get("american") if isinstance(it.get("open"), dict) else None)}
    return o


# ----------------------------------------------------------------------------- ratings
class Ratings:
    """score_home = avg + hfa/2 + off[home] - def[away];  score_away = avg - hfa/2 + off[away] - def[home]"""

    def __init__(self, league: str, results: list[Result], asof: datetime, season: int):
        cfg = SPORT[league]
        self.league, self.cfg = league, cfg
        rows = []
        for r in results:
            if r.date >= asof:
                continue
            if r.season == season:
                age = sum(1 for x in results if r.date < x.date < asof and (x.home in (r.home, r.away) or x.away in (r.home, r.away))) / 2
                w = 0.5 ** (age / cfg["half_life"])
            elif r.season == season - 1:
                w = KNOBS["prev_weight"] * 0.5
            else:
                continue
            rows.append((r, w))
        self.n_games = sum(1 for r, _ in rows if r.season == season)
        tot_w = sum(w for _, w in rows) or 1
        self.avg = sum(w * (r.hs + r.as_) / 2 for r, w in rows) / tot_w if rows else cfg["avg"]
        self.hfa = cfg["hfa"]
        teams = {t for r, _ in rows for t in (r.home, r.away)}
        off = {t: 0.0 for t in teams}
        de = {t: 0.0 for t in teams}
        k = cfg["prior_games"]                       # shrink toward average
        for _ in range(30):
            no, nd = {t: 0.0 for t in teams}, {t: 0.0 for t in teams}
            wo, wd = {t: k for t in teams}, {t: k for t in teams}
            for r, w in rows:
                eh = self.avg + self.hfa / 2
                ea = self.avg - self.hfa / 2
                no[r.home] += w * (r.hs - eh + de[r.away]); wo[r.home] += w
                no[r.away] += w * (r.as_ - ea + de[r.home]); wo[r.away] += w
                nd[r.home] += w * (ea + off[r.away] - r.as_); wd[r.home] += w
                nd[r.away] += w * (eh + off[r.home] - r.hs); wd[r.away] += w
            off = {t: no[t] / wo[t] for t in teams}
            de = {t: nd[t] / wd[t] for t in teams}
        self.off, self.de = off, de

    def predict(self, home: str, away: str) -> tuple[float, float]:
        h = self.avg + self.hfa / 2 + self.off.get(home, 0) - self.de.get(away, 0)
        a = self.avg - self.hfa / 2 + self.off.get(away, 0) - self.de.get(home, 0)
        floor = 0.5 if self.league == "nhl" else 1.0
        return max(floor, h), max(floor, a)


# ----------------------------------------------------------------------------- probabilities
def _phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _pois(k, lam):
    return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1)) if lam > 0 else (1.0 if k == 0 else 0.0)


def outcome_probs(league: str, mu_h: float, mu_a: float, odds: GameOdds) -> dict:
    """Model probabilities for home ML, home covering the spread, and over the total."""
    out = {}
    if league in ("nba", "nfl"):
        cfg = SPORT[league]
        m = mu_h - mu_a
        out["ml_home"] = _phi(m / cfg["sd_margin"])
        if odds.spread_home is not None:
            # home covers if margin + spread_home > 0
            out["spread_home"] = 1 - _phi((-odds.spread_home - m) / cfg["sd_margin"])
            if abs(odds.spread_home - round(odds.spread_home)) < 1e-9:      # integer line: remove push mass
                push = _phi((-odds.spread_home + 0.5 - m) / cfg["sd_margin"]) - _phi((-odds.spread_home - 0.5 - m) / cfg["sd_margin"])
                out["spread_home"] = (out["spread_home"] - push / 2) / max(1e-6, 1 - push)
        if odds.total is not None:
            out["over"] = 1 - _phi((odds.total - (mu_h + mu_a)) / cfg["sd_total"])
        return out
    # NHL: independent Poisson goals per team (regulation-ish), OT/SO as coin flip
    ph = [_pois(k, mu_h) for k in range(15)]
    pa = [_pois(k, mu_a) for k in range(15)]
    win = sum(ph[i] * pa[j] for i in range(15) for j in range(15) if i > j)
    tie = sum(ph[i] * pa[i] for i in range(15))
    out["ml_home"] = win + 0.52 * tie
    if odds.spread_home is not None:
        need = -odds.spread_home                    # home -1.5 -> margin >= 2 ; home +1.5 -> margin >= -1
        out["spread_home"] = sum(ph[i] * pa[j] for i in range(15) for j in range(15) if i - j > need)
    if odds.total is not None:
        out["over"] = sum(ph[i] * pa[j] for i in range(15) for j in range(15) if i + j > odds.total)
    return out


def _novig(p1, p2):
    a, b = american_to_prob(p1), american_to_prob(p2)
    if a is None or b is None:
        return None, a, b
    return a / (a + b), a, b


def team_picks(league: str, game, mu_h: float, mu_a: float, odds: GameOdds, notes: list[str],
               n_games: int) -> list[dict]:
    """One candidate per market (ML, spread, total): the side with the larger edge."""
    if not odds:
        return []
    probs = outcome_probs(league, mu_h, mu_a, odds)
    mw = KNOBS["model_weight"] * min(1.0, n_games / (2 * SPORT[league]["prior_games"]))
    hab, aab = game.home.abbr, game.away.abbr
    spread_name = "Puck line" if league == "nhl" else "Spread"
    markets = []
    if odds.ml_home is not None and odds.ml_away is not None and "ml_home" in probs:
        markets.append(("Moneyline", probs["ml_home"], odds.ml_home, odds.ml_away, f"{hab} ML", f"{aab} ML", None))
    if odds.spread_home is not None and "spread_home" in probs:
        sh = odds.spread_home
        markets.append((spread_name, probs["spread_home"], odds.spread_home_price or -110, odds.spread_away_price or -110,
                        f"{hab} {sh:+g}", f"{aab} {-sh:+g}", sh))
    if odds.total is not None and "over" in probs:
        markets.append(("Total", probs["over"], odds.over_price or -110, odds.under_price or -110,
                        f"Over {odds.total:g}", f"Under {odds.total:g}", odds.total))
    out = []
    for market, p_model, price_a, price_b, lab_a, lab_b, line in markets:
        fair, ia, ib = _novig(price_a, price_b)
        if fair is None:
            continue
        pa = fair + mw * (p_model - fair)
        pb = 1 - pa
        ea, eb = pa - ia, pb - ib
        side_a = ea >= eb
        edge = ea if side_a else eb
        grade = "A" if edge >= .05 else "B" if edge >= .03 else "C" if edge >= .015 else "-"
        out.append({
            "game_id": game.id, "game": game.label, "market": market, "pick": lab_a if side_a else lab_b,
            "side": ("home" if market != "Total" else "over") if side_a else ("away" if market != "Total" else "under"),
            "line": line, "price": price_a if side_a else price_b, "prob": round(pa if side_a else pb, 3),
            "model_prob": round(p_model if side_a else 1 - p_model, 3), "edge": round(edge, 3), "grade": grade,
            "proj": f"{hab} {mu_h:.1f} – {aab} {mu_a:.1f}" if league != "nhl" else f"{hab} {mu_h:.2f} – {aab} {mu_a:.2f}",
            "mu_h": round(mu_h, 2), "mu_a": round(mu_a, 2), "home": hab, "away": aab, "notes": list(notes),
            "score": round(edge * 100, 2),
        })
    return out


def grade_team_pick(pk: dict, hs: float, as_: float) -> str:
    m = pk["market"]
    if m == "Moneyline":
        if hs == as_:
            return "PUSH"
        home_won = hs > as_
        return "WIN" if (pk["side"] == "home") == home_won else "LOSS"
    if m in ("Spread", "Puck line"):
        adj = hs - as_ + pk["line"]                    # home perspective
        if adj == 0:
            return "PUSH"
        return "WIN" if (pk["side"] == "home") == (adj > 0) else "LOSS"
    tot = hs + as_
    if tot == pk["line"]:
        return "PUSH"
    return "WIN" if (pk["side"] == "over") == (tot > pk["line"]) else "LOSS"


def final_scores(http: Http, league: str, event_id: str) -> tuple[float, float] | None:
    sport, lg = SPORT[league]["path"]
    try:
        data = http.get_json(f"{SITE}/{sport}/{lg}/summary", {"event": event_id}, ttl=0) or {}
    except Exception:
        return None
    comp = ((data.get("header") or {}).get("competitions") or [{}])[0]
    if not (((comp.get("status") or {}).get("type") or {}).get("completed")):
        return None
    cs = {c.get("homeAway"): c for c in comp.get("competitors", [])}
    if "home" not in cs or "away" not in cs:
        return None
    hs, as_ = _f(cs["home"].get("score")), _f(cs["away"].get("score"))
    return (hs, as_) if hs is not None and as_ is not None else None


def summarize_team(graded: list[dict]) -> dict:
    from .model_report import _row
    rows = [r for r in graded if r.get("result") in ("WIN", "LOSS")]
    out = {"all": _row("All team bets", rows)}
    out["by_grade"] = [_row(f"Grade {g}", [r for r in rows if r["grade"] == g]) for g in "ABC"
                       if any(r["grade"] == g for r in rows)]
    out["by_market"] = [_row(m, [r for r in rows if r["market"] == m]) for m in ("Moneyline", "Spread", "Puck line", "Total")
                        if any(r["market"] == m for r in rows)]
    out["recent"] = sorted(graded, key=lambda r: r.get("date", ""), reverse=True)[:20]
    return out


# ----------------------------------------------------------------------------- history (lock + grade)
def save_team_picks(hist_dir, key: str, fresh: list[dict], started: set[str], now: datetime) -> list[dict]:
    """Keep picks for games that already started (locked at tip/puck drop), replace the rest."""
    import json
    from pathlib import Path
    d = Path(hist_dir) / "team"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{key}.json"
    prior = json.loads(f.read_text()) if f.exists() else {}
    locked = [dict(p, locked=True) for p in prior.get("picks", []) if p["game_id"] in started]
    shown = locked + [p for p in fresh if p["game_id"] not in started and p["grade"] != "-"]
    if shown:
        f.write_text(json.dumps({"made": prior.get("made", now.isoformat()), "picks": shown}, indent=1))
    return shown


def grade_team_history(http: Http, league: str, hist_dir, now: datetime) -> dict:
    import json
    from pathlib import Path
    d = Path(hist_dir) / "team"
    path = d / "results.json"
    res = json.loads(path.read_text()) if path.exists() else {"graded": []}
    done = {(r["date"], r["game_id"], r["market"]) for r in res["graded"]}
    finals: dict[str, tuple | None] = {}
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        if f.name == "results.json":
            continue
        blob = json.loads(f.read_text())
        made = datetime.fromisoformat(blob.get("made", now.isoformat()))
        for pk in blob.get("picks", []):
            if pk.get("grade") == "-" or (f.stem, pk["game_id"], pk["market"]) in done:
                continue
            if pk["game_id"] not in finals:
                finals[pk["game_id"]] = final_scores(http, league, pk["game_id"])
            sc = finals[pk["game_id"]]
            if sc is None:
                if (now - made).days >= 4:
                    res["graded"].append({**pk, "date": f.stem, "result": "VOID"})
                    done.add((f.stem, pk["game_id"], pk["market"]))
                continue
            res["graded"].append({**pk, "date": f.stem, "final": f"{pk['home']} {sc[0]:g} – {pk['away']} {sc[1]:g}",
                                  "result": grade_team_pick(pk, *sc)})
            done.add((f.stem, pk["game_id"], pk["market"]))
    if d.exists():
        path.write_text(json.dumps(res, indent=1))
    return summarize_team(res["graded"])

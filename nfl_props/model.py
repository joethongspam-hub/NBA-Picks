"""NFL projection model: opportunity x efficiency.

For each skill player:
  opportunities (pass attempts / carries / targets), blended from recent games,
      season and last season
    x game script (underdogs throw more, favourites run more: Vegas spread)
    + targets / carries freed up by injured teammates
  efficiency (yards per attempt/carry/target, catch rate, TD rate), shrunk hard
      toward position averages because NFL samples are tiny
    x opponent defense vs that position (shrunk)
    x scoring environment (Vegas implied team total)

Yards use a gamma distribution (right-skewed), low counts (TDs, INTs,
receptions) negative-binomial/Poisson, attempts/completions normal.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from nba_props.espn import Game, Injury
from nba_props.model import VIG_PROB, Pick, _nb_cdf, _phi, _short, _to_american, est_line, market_disagrees
from nba_props.odds import PropLine, american_to_prob, norm_name

from .espn_nfl import STAT_FUNCS, NflLine, NflPlayer

# Tuned on the 2026 weeks 3-7 backtest (tests/tune_nfl.py)
KNOBS = {
    "model_weight": 0.6,     # blend of model vs market probability
    "vol_scale": 0.97,       # global opportunity calibration
    "eff_shrink": 1.0,       # multiplies efficiency prior strength
    "dvp_prior": 40.0,       # player-games of shrinkage for defense-vs-position
    "dvp_power": 1.0,
    "script": 1.0,           # strength of spread -> pass/run mix
    "env_scale": 1.0,        # strength of implied team total
    "absorb": 0.4,           # share of injured teammates' opportunities redistributed
    "prev_weight": 0.4,      # weight of last-season games
    "qb_shrink": 1.0,        # extra multiplier on QB efficiency prior strength
    "qb_vol": 1.08,          # QB pass-attempt calibration
    "weather": 1.0,          # 0 disables weather adjustments
    "wind_start": 12.0,      # mph (10 m height) where wind starts to bite
    "wind_k": 0.01,          # passing efficiency lost per mph above wind_start
}


def weather_factors(wx: dict | None) -> tuple[dict, str | None]:
    """Multipliers for passing efficiency/volume and rushing volume from game weather."""
    f = {"pass_eff": 1.0, "pass_vol": 1.0, "rush_vol": 1.0, "td": 1.0}
    if not wx or wx.get("indoor") is not False or not KNOBS["weather"]:
        return f, None
    s = KNOBS["weather"]
    notes = []
    wind = max(wx.get("wind", 0), 0.75 * wx.get("gust", 0))
    if wind > KNOBS["wind_start"]:
        loss = min(0.2, KNOBS["wind_k"] * (wind - KNOBS["wind_start"])) * s
        f["pass_eff"] *= 1 - loss
        f["pass_vol"] *= 1 - loss / 3
        f["rush_vol"] *= 1 + loss / 2
        f["td"] *= 1 - loss / 2
        notes.append(f"wind {wx.get('wind', 0):.0f} mph" + (f" (gusts {wx['gust']:.0f})" if wx.get("gust", 0) > wind + 5 else ""))
    if wx.get("snow", 0) >= 0.1 or wx.get("precip", 0) >= 0.04:
        f["pass_eff"] *= 1 - 0.04 * s
        f["rush_vol"] *= 1 + 0.02 * s
        notes.append("snow" if wx.get("snow", 0) >= 0.1 else "rain")
    if wx.get("temp", 60) <= 20:
        f["pass_eff"] *= 1 - 0.02 * s
        notes.append(f"{wx['temp']}°F")
    if not notes or f["pass_eff"] > 0.995:
        return f, None
    return f, f"Weather: {', '.join(notes)}: passing trimmed {(1 - f['pass_eff']) * 100:.0f}%"

# Efficiency priors: (league-average value, prior strength in opportunities)
PRIORS = {
    "QB": {"cmp_pct": (.645, 150), "ypa": (6.9, 150), "ptd": (.045, 300), "int": (.023, 400),
           "ypc": (4.5, 40), "rtd": (.03, 80)},
    "RB": {"ypc": (4.3, 80), "rtd": (.028, 150), "catch": (.78, 40), "ypt": (5.8, 40), "ctd": (.03, 100)},
    "WR": {"ypc": (6.5, 20), "rtd": (.02, 50), "catch": (.63, 60), "ypt": (8.0, 60), "ctd": (.045, 120)},
    "TE": {"ypc": (4.0, 20), "rtd": (.02, 50), "catch": (.70, 60), "ypt": (7.2, 60), "ctd": (.045, 120)},
}
POS_STATS = {
    "QB": ["PASS_YDS", "PASS_TD", "PASS_ATT", "PASS_CMP", "INT", "RUSH_YDS"],
    "RB": ["RUSH_YDS", "RUSH_ATT", "REC", "REC_YDS", "RUSH_REC_YDS", "ANY_TD"],
    "WR": ["REC", "REC_YDS", "ANY_TD"],
    "TE": ["REC", "REC_YDS", "ANY_TD"],
}
YARDS = {"PASS_YDS", "RUSH_YDS", "REC_YDS", "RUSH_REC_YDS"}
NORMAL = {"PASS_ATT", "PASS_CMP"}
POISSON = {"PASS_TD", "INT", "ANY_TD"}
CV_DEFAULT = {"PASS_YDS": .30, "RUSH_YDS": .55, "REC_YDS": .70, "RUSH_REC_YDS": .50,
              "PASS_ATT": .17, "PASS_CMP": .22, "REC": .50, "RUSH_ATT": .40}
MIN_VIEW = {"PASS_YDS": 120, "RUSH_YDS": 15, "REC_YDS": 15, "RUSH_REC_YDS": 25, "PASS_ATT": 15,
            "PASS_CMP": 10, "REC": 1.3, "RUSH_ATT": 5, "PASS_TD": .5, "INT": .3, "ANY_TD": .15}
FULL = {"PASS_YDS": "passing yards", "PASS_TD": "passing TDs", "PASS_ATT": "pass attempts",
        "PASS_CMP": "completions", "INT": "interceptions", "RUSH_YDS": "rushing yards",
        "RUSH_ATT": "carries", "REC": "receptions", "REC_YDS": "receiving yards",
        "RUSH_REC_YDS": "rush+rec yards", "ANY_TD": "anytime TD"}
DVP_FAMILY = {"QB": ["pass_yds", "pass_td"], "RB": ["rush_yds", "rec_yds", "td"], "WR": ["rec", "rec_yds", "td"],
              "TE": ["rec", "rec_yds", "td"]}


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def _wmean(pairs):
    tw = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / tw if tw else 0.0


# ----------------------------------------------------------------------------- distributions
def _gammainc_lower_reg(a: float, x: float) -> float:
    """Regularized lower incomplete gamma P(a, x) (Numerical Recipes)."""
    if x <= 0:
        return 0.0
    gln = math.lgamma(a)
    if x < a + 1:
        ap, s = a, 1.0 / a
        d = s
        for _ in range(500):
            ap += 1
            d *= x / ap
            s += d
            if abs(d) < abs(s) * 1e-12:
                break
        return s * math.exp(-x + a * math.log(x) - gln)
    b = x + 1 - a
    c = 1 / 1e-300
    d = 1 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        de = d * c
        h *= de
        if abs(de - 1) < 1e-12:
            break
    return 1 - math.exp(-x + a * math.log(x) - gln) * h


def prob_over_under(stat: str, mu: float, cv: float, line: float) -> tuple[float, float]:
    mu = max(mu, 0.01)
    integer = abs(line - round(line)) < 1e-9
    if stat in YARDS:
        k = 1 / max(cv, 0.15) ** 2
        theta = mu / k
        if integer:
            under = _gammainc_lower_reg(k, max(line - 0.5, 0) / theta)
            over = 1 - _gammainc_lower_reg(k, (line + 0.5) / theta)
        else:
            under = _gammainc_lower_reg(k, line / theta)
            over = 1 - under
        return over, under
    if stat in NORMAL:
        sd = max(cv * mu, 1.0)
        if integer:
            return 1 - _phi((line + 0.5 - mu) / sd), _phi((line - 0.5 - mu) / sd)
        over = 1 - _phi((line - mu) / sd)
        return over, 1 - over
    var = mu * 1.05 if stat in POISSON else max(mu * 1.05, (cv * mu) ** 2)
    if integer:
        kk = int(round(line))
        return 1 - _nb_cdf(kk, mu, var), _nb_cdf(kk - 1, mu, var)
    under = _nb_cdf(int(math.floor(line)), mu, var)
    return 1 - under, under


# ----------------------------------------------------------------------------- profiles
@dataclass
class Profile:
    player: NflPlayer
    n_cur: int
    opps: dict          # per-game: pass_att, rush_att, tgt
    eff: dict           # cmp_pct, ypa, ptd, int, ypc, rtd, catch, ypt, ctd
    season_avg: dict    # per stat
    l4_avg: dict
    cv: dict


def _weights(p: NflPlayer, season: int):
    out = []
    for i, g in enumerate(p.logs[:30]):
        w = 1.0 if g.season == season else KNOBS["prev_weight"] if g.season == season - 1 else 0.0
        if i < 4:
            w *= 1.5
        if w > 0:
            out.append((g, w))
    return out


def build_profile(p: NflPlayer, season: int) -> Profile | None:
    if not p.logs:
        return None
    gw = _weights(p, season)
    if not gw:
        return None
    pos = p.pos_group if p.pos_group in PRIORS else "WR"
    opps = {k: _wmean([(g.s[k], w) for g, w in gw]) for k in ("pass_att", "rush_att", "tgt")}

    def shrunk(num_key, den_key, prior_key, ratio=1.0):
        mean, k = PRIORS[pos][prior_key]
        k *= KNOBS["eff_shrink"] * (KNOBS["qb_shrink"] if pos == "QB" else 1.0)
        num = sum(g.s[num_key] * w for g, w in gw)
        den = sum(g.s[den_key] * w for g, w in gw)
        return (num + k * mean) / (den + k)

    eff = {"ypc": shrunk("rush_yds", "rush_att", "ypc"), "rtd": shrunk("rush_td", "rush_att", "rtd")}
    if pos == "QB":
        eff.update(cmp_pct=shrunk("cmp", "pass_att", "cmp_pct"), ypa=shrunk("pass_yds", "pass_att", "ypa"),
                   ptd=shrunk("pass_td", "pass_att", "ptd"), int=shrunk("ints", "pass_att", "int"))
    else:
        eff.update(catch=shrunk("rec", "tgt", "catch"), ypt=shrunk("rec_yds", "tgt", "ypt"),
                   ctd=shrunk("rec_td", "tgt", "ctd"))
    cur = [g for g in p.logs if g.season == season]
    prev = [g for g in p.logs if g.season == season - 1]
    n = len(cur)
    w = n / (n + 4)
    season_avg, l4, cv = {}, {}, {}
    for s in STAT_FUNCS:
        ac = statistics.mean([g.get(s) for g in cur]) if cur else None
        ap = statistics.mean([g.get(s) for g in prev]) if prev else None
        season_avg[s] = (w * ac + (1 - w) * ap) if (ac is not None and ap is not None) else (ac if ac is not None else ap or 0)
        l4[s] = statistics.mean([g.get(s) for g in p.logs[:4]])
        vals = [g.get(s) for g in p.logs[:17]]
        m = statistics.mean(vals)
        pcv = statistics.pstdev(vals) / m if len(vals) >= 4 and m > 0 else None
        d = CV_DEFAULT.get(s, .6)
        cv[s] = d if pcv is None else _clip(0.5 * d + 0.5 * pcv, d * 0.7, d * 1.5)
    return Profile(p, n, opps, eff, season_avg, l4, cv)


# ----------------------------------------------------------------------------- league context
class League:
    def __init__(self, players: list[NflPlayer], profiles: dict[str, Profile], season: int):
        self.season = season
        self.profiles = profiles
        self.team_events: dict[str, dict] = defaultdict(dict)
        for p in players:
            for g in p.logs:
                if g.season == season and (g.team_id or p.team_id) == p.team_id:
                    self.team_events[p.team_id][g.event_id] = g.date
        self.dvp_tab = self._build_dvp(players)

    def recent_events(self, team_id: str, k: int):
        ev = self.team_events.get(team_id, {})
        return [e for e, _ in sorted(ev.items(), key=lambda kv: kv[1], reverse=True)[:k]]

    @staticmethod
    def _fam(g: NflLine, fam: str) -> float:
        s = g.s
        return {"pass_yds": s["pass_yds"], "pass_td": s["pass_td"], "rush_yds": s["rush_yds"],
                "rec_yds": s["rec_yds"], "rec": s["rec"], "td": s["rush_td"] + s["rec_td"]}[fam]

    def _build_dvp(self, players):
        obs, exp, tot, cnt = defaultdict(float), defaultdict(float), defaultdict(float), defaultdict(float)
        for p in players:
            pg = p.pos_group
            if pg not in DVP_FAMILY:
                continue
            for off, wt in ((0, 1.0), (1, 0.3)):
                logs = [g for g in p.logs if g.season == self.season - off]
                if len(logs) < 3:
                    continue
                for fam in DVP_FAMILY[pg]:
                    mean = statistics.mean([self._fam(g, fam) for g in logs])
                    for g in logs:
                        if not g.opp_id:
                            continue
                        obs[(g.opp_id, pg, fam)] += wt * self._fam(g, fam)
                        exp[(g.opp_id, pg, fam)] += wt * mean
                        tot[(pg, fam)] += mean
                        cnt[(pg, fam)] += 1
        out = {}
        for key, e in exp.items():
            _, pg, fam = key
            k = tot[(pg, fam)] / max(1, cnt[(pg, fam)]) * KNOBS["dvp_prior"]
            out[key] = _clip((obs[key] + k) / (e + k), 0.8, 1.2)
        return out

    def dvp(self, opp_id, pg, fam):
        return self.dvp_tab.get((opp_id, pg, fam), 1.0) ** KNOBS["dvp_power"]


# ----------------------------------------------------------------------------- projection
@dataclass
class Projection:
    player: NflPlayer
    team_abbr: str
    opp_abbr: str
    game: Game
    mean: dict
    opps: dict
    status: str
    reasons: list
    stat_reasons: dict
    profile: Profile


def project_team(team_players, team_id, team_abbr, opp_id, opp_abbr, game: Game, league: League,
                 injuries: dict[str, Injury], league_tt: float, wx: dict | None = None) -> list[Projection]:
    wf, wx_note = weather_factors(wx)
    profs = league.profiles
    listed = {p.id: injuries.get(p.id) or injuries.get(p.name) for p in team_players}
    inj = {k: v for k, v in listed.items() if v and v.level != "ACTIVE"}        # "Active" = cleared to play
    recent3 = league.recent_events(team_id, 3)

    def played_recent(p):
        ev = {g.event_id for g in p.logs}
        return sum(e in ev for e in recent3)

    def is_out(p):
        i = inj.get(p.id)
        return bool(i and i.level in ("OUT", "DOUBTFUL"))

    # starting QB = most attempts over the team's last 2 games
    qbs = [p for p in team_players if p.pos == "QB" and p.id in profs]
    recent2 = set(league.recent_events(team_id, 2))
    qb_note = None
    qb_eff_f = 1.0
    starter_override = None
    starter = max(qbs, key=lambda q: sum(g.s["pass_att"] for g in q.logs if g.event_id in recent2), default=None)
    # A QB on the report but cleared to play (e.g. back from injury) who has
    # clearly more starts than the stand-in gets the job back.
    returning = [q for q in qbs if not is_out(q) and listed.get(q.id) and profs[q.id].opps["pass_att"] >= 20]

    def starts(q):          # games with 15+ attempts this season and last
        return sum(g.s["pass_att"] >= 15 for g in q.logs if g.season >= league.season - 1)

    if starter and not is_out(starter) and returning:
        best = max(returning, key=starts)
        if best.id != starter.id and starts(best) > starts(starter) + 2:
            qb_note = f"{best.name} cleared to return as the starter"
            starter = best
    if starter and is_out(starter):
        backups = [q for q in qbs if not is_out(q) and q.id != starter.id]
        if backups:
            new = max(backups, key=lambda q: sum(g.s["pass_att"] for g in q.logs[:6]))
            qb_note = f"{_short(starter.name)} out: {new.name} expected to start"
            if profs[new.id].opps["pass_att"] < 15:
                qb_eff_f = 0.88
            starter_opps = profs[starter.id].opps["pass_att"]
            starter = new
            starter_override = starter_opps
        else:
            starter = None

    # vacated opportunities from injured teammates who were playing lately
    out_mates = [(p, profs[p.id]) for p in team_players
                 if p.id in profs and is_out(p) and p.pos != "QB" and (played_recent(p) or not recent3)]
    vac = {k: sum(pr.opps[k] * (played_recent(p) / max(1, len(recent3)) if recent3 else 1)
                  for p, pr in out_mates) for k in ("tgt", "rush_att")}

    # eligible
    active = []
    for p in team_players:
        pr = profs.get(p.id)
        if not pr or is_out(p):
            continue
        if p.pos == "QB":
            if starter is None or p.id != starter.id:
                continue
        elif recent3 and not played_recent(p):
            continue
        o = pr.opps
        if p.pos == "RB" and o["rush_att"] + o["tgt"] < 6:
            continue
        if p.pos in ("WR", "TE") and o["tgt"] < 2.5:
            continue
        active.append((p, pr))
    act_tot = {k: sum(pr.opps[k] for p, pr in active if p.pos != "QB") or 1.0 for k in ("tgt", "rush_att")}

    # game script + environment
    spread = None
    if game.spread_home is not None:
        spread = game.spread_home if team_id == game.home.id else -game.spread_home   # + = underdog
    pass_vol = _clip(1 + 0.010 * KNOBS["script"] * (spread or 0), 0.9, 1.1)
    rush_vol = _clip(1 - 0.012 * KNOBS["script"] * (spread or 0), 0.88, 1.12)
    tt = game.implied_total(team_id)
    env_td = env_y = 1.0
    env_note = None
    if tt and league_tt:
        r = tt / league_tt
        env_td = _clip(r ** (1.0 * KNOBS["env_scale"]), 0.7, 1.35)
        env_y = _clip(r ** (0.3 * KNOBS["env_scale"]), 0.9, 1.1)
        if abs(r - 1) >= 0.06:
            env_note = f"Implied team total {tt:.1f} ({'high' if r > 1 else 'low'} vs avg {league_tt:.1f})"
    script_note = None
    if spread is not None and abs(spread) >= 6:
        script_note = (f"{'Underdog' if spread > 0 else 'Favorite'} by {abs(spread):g}: "
                       f"expect {'more passing' if spread > 0 else 'more rushing'}")

    out = []
    vs = KNOBS["vol_scale"]
    for p, pr in active:
        pos = p.pos_group if p.pos_group in PRIORS else "WR"
        e = pr.eff
        reasons, sr = [], defaultdict(list)
        i = inj.get(p.id)
        status = i.level if i else "ACTIVE"
        if i:
            reasons.append(f"Listed {i.status}" + (f": {i.detail}" if i.detail else ""))
        if script_note:
            reasons.append(script_note)
        m, opps = {}, {}
        if pos == "QB":
            att = (starter_override if starter_override else pr.opps["pass_att"]) * pass_vol * vs * KNOBS["qb_vol"] * wf["pass_vol"]
            ra = pr.opps["rush_att"] * vs
            d_y = league.dvp(opp_id, "QB", "pass_yds")
            d_t = league.dvp(opp_id, "QB", "pass_td")
            m["PASS_ATT"] = att
            m["PASS_CMP"] = att * e["cmp_pct"] * qb_eff_f * wf["pass_eff"] ** 0.5
            m["PASS_YDS"] = att * e["ypa"] * d_y * env_y * qb_eff_f * wf["pass_eff"]
            m["PASS_TD"] = att * e["ptd"] * d_t * env_td * qb_eff_f * wf["td"]
            m["INT"] = att * e["int"] / qb_eff_f
            m["RUSH_YDS"] = ra * e["ypc"] * env_y
            m["RUSH_ATT"] = ra
            opps = {"att": att}
            for s, d in (("PASS_YDS", d_y), ("PASS_TD", d_t)):
                if abs(d - 1) >= 0.06:
                    sr[s].append(f"{opp_abbr} {'allows' if d > 1 else 'limits'} {FULL[s]} to QBs ({(d - 1) * 100:+.0f}%)")
            if qb_note:
                reasons.append(qb_note)
        else:
            tgt = pr.opps["tgt"] * pass_vol * vs * wf["pass_vol"]
            ra = pr.opps["rush_att"] * rush_vol * vs * wf["rush_vol"]
            add_t = vac["tgt"] * KNOBS["absorb"] * pr.opps["tgt"] / act_tot["tgt"]
            add_r = vac["rush_att"] * KNOBS["absorb"] * pr.opps["rush_att"] / act_tot["rush_att"]
            tgt += add_t
            ra += add_r
            if out_mates and (add_t >= 0.6 or add_r >= 1.0):
                names = ", ".join(_short(x.name) for x, _ in out_mates[:3])
                note = f"{names} out: " + ", ".join(
                    x for x in (f"+{add_t:.1f} targets" if add_t >= 0.3 else "", f"+{add_r:.1f} carries" if add_r >= 0.5 else "") if x)
                reasons.append(note)
            d_ry = league.dvp(opp_id, pos, "rush_yds") if pos == "RB" else 1.0
            d_cy = league.dvp(opp_id, pos, "rec_yds")
            d_rec = league.dvp(opp_id, pos, "rec") if pos != "RB" else 1.0
            d_td = league.dvp(opp_id, pos, "td")
            ypt = e["ypt"] * qb_eff_f * wf["pass_eff"]
            m["RUSH_ATT"] = ra
            m["RUSH_YDS"] = ra * e["ypc"] * d_ry * env_y
            m["REC"] = tgt * e["catch"] * d_rec * (qb_eff_f ** 0.5) * wf["pass_eff"] ** 0.5
            m["REC_YDS"] = tgt * ypt * d_cy * env_y
            m["RUSH_REC_YDS"] = m["RUSH_YDS"] + m["REC_YDS"]
            m["ANY_TD"] = (ra * e["rtd"] + tgt * e["ctd"] * qb_eff_f * wf["td"]) * d_td * env_td
            opps = {"tgt": tgt, "car": ra}
            for s, d in (("RUSH_YDS", d_ry), ("REC_YDS", d_cy), ("REC", d_rec), ("ANY_TD", d_td)):
                if abs(d - 1) >= 0.06:
                    sr[s].append(f"{opp_abbr} {'allows' if d > 1 else 'limits'} {FULL[s]} to {pos}s ({(d - 1) * 100:+.0f}%)")
            if qb_eff_f < 1:
                reasons.append("Backup QB starting: receiving efficiency trimmed")
        if env_note:
            for s in ("PASS_YDS", "PASS_TD", "ANY_TD", "REC_YDS", "RUSH_YDS", "RUSH_REC_YDS"):
                sr[s].append(env_note)
        if wx_note:
            for s in ("PASS_YDS", "PASS_CMP", "PASS_TD", "PASS_ATT", "REC", "REC_YDS", "RUSH_ATT", "RUSH_YDS"):
                sr[s].insert(0, wx_note)
        sr["RUSH_REC_YDS"] = sr["RUSH_YDS"] + [x for x in sr["REC_YDS"] if x not in sr["RUSH_YDS"]]
        out.append(Projection(p, team_abbr, opp_abbr, game, m, opps, status, reasons, dict(sr), pr))
    return out


# ----------------------------------------------------------------------------- evaluation
def _hits(logs, stat, line, side):
    vals = [g.get(stat) for g in logs]
    return sum((v > line) if side == "OVER" else (v < line) for v in vals), len(vals)


def evaluate(proj: Projection, lines: dict[tuple[str, str], PropLine], season: int) -> list[Pick]:
    p, pr = proj.player, proj.profile
    pos = p.pos_group if p.pos_group in POS_STATS else "WR"
    picks = []
    cur = [g for g in p.logs if g.season == season]
    vs_opp = [g for g in p.logs if g.opp_abbr == proj.opp_abbr][:4]
    for s in POS_STATS[pos]:
        if s not in proj.mean:
            continue
        if s == "RUSH_YDS" and pos == "QB" and pr.opps["rush_att"] < 3:
            continue
        mu = proj.mean[s]
        view = 0.4 * pr.l4_avg[s] + 0.6 * pr.season_avg[s]
        real = lines.get((norm_name(p.name), s))
        if real:
            line, src = real.line, real.label
        else:
            if view < MIN_VIEW.get(s, 1):
                continue
            line = 0.5 if s == "ANY_TD" else (est_line(view) if s in POISSON else math.floor(view) + 0.5)
            src = "est."
        cv = pr.cv.get(s, .6)
        over_m, under_m = prob_over_under(s, mu, cv, line)
        if real and real.under_price is None:
            # one-sided market (anytime TD "yes"): strip ~8% vig, under not bettable
            io = american_to_prob(real.over_price) or VIG_PROB
            fair_o, iu = io * 0.92, 1.0
        elif real:
            io = american_to_prob(real.over_price) or VIG_PROB
            iu = american_to_prob(real.under_price) or VIG_PROB
            fair_o = io / (io + iu)
        else:
            fair_o, _ = prob_over_under(s, max(view, .05), cv, line)
            io, iu = min(.97, fair_o + VIG_PROB - .5), min(.97, (1 - fair_o) + VIG_PROB - .5)
        mw = KNOBS["model_weight"]
        over = fair_o + mw * (over_m - fair_o)
        under = (1 - fair_o) + mw * (under_m - (1 - fair_o))
        if over - io >= under - iu:
            side, prob, edge, price = "OVER", over, over - io, real.over_price if real else _to_american(io)
        else:
            side, prob, edge, price = "UNDER", under, under - iu, real.under_price if real else _to_american(iu)
        h5, h10, hs, hv = (_hits(p.logs[:5], s, line, side), _hits(p.logs[:10], s, line, side),
                           _hits(cur, s, line, side), _hits(vs_opp, s, line, side))
        sample = min(1.0, len(p.logs[:17]) / 8)
        status_f = {"QUESTIONABLE": 0.6, "PROBABLE": 0.95}.get(proj.status, 1.0)
        reliability = sample * status_f
        score = edge * 100 * reliability
        grade = ("A" if edge >= .08 and reliability >= .5 else "B" if edge >= .05 else "C" if edge >= .03 else "-")
        reasons = list(proj.stat_reasons.get(s, [])) + list(proj.reasons)
        if market_disagrees(real, line, mu):
            grade, score = "-", 0.0
            reasons.insert(0, f"Market strongly disagrees ({real.books} books at {line:g} vs projection {mu:.1f}): "
                              "likely news the model can't see; skipped")
        if h10[1] >= 5:
            reasons.append(f"{side.title()} hit {h5[0]}/{h5[1]} last 5, {h10[0]}/{h10[1]} last 10 at {line}")
        if hv[1]:
            reasons.append(f"Last {hv[1]} vs {proj.opp_abbr}: " + ", ".join(f"{g.get(s):g}" for g in vs_opp))
        opp_txt = proj.opps.get("att") or proj.opps.get("tgt", 0) + proj.opps.get("car", 0)
        picks.append(Pick(
            game_id=proj.game.id, game=proj.game.label, player=p.name, player_id=p.id, team=proj.team_abbr,
            opp=proj.opp_abbr, stat=s, side=side, line=line, line_source=src, price=price,
            projection=round(mu, 2 if s in POISSON else 1), prob=round(prob, 3), edge=round(edge, 3),
            score=round(score, 2), grade=grade, hit_l5=f"{h5[0]}/{h5[1]}", hit_l10=f"{h10[0]}/{h10[1]}",
            hit_season=f"{hs[0]}/{hs[1]}", vs_opp=f"{hv[0]}/{hv[1]}", minutes=round(opp_txt, 1),
            status=proj.status, season_avg=round(pr.season_avg[s], 1), l10_avg=round(pr.l4_avg[s], 1),
            reasons=reasons))
    return picks

"""NHL projection model.

Skaters:  ice time (TOI) x per-60 rates (shots, assists; goals = shots x shooting %,
          shrunk hard toward position averages)
          x opponent shot suppression vs forwards/defense (shrunk)
          x opposing goalie quality (goals/assists/points)
          x Vegas-implied team goals (scoring environment)
          + shots/points freed up by injured teammates.
Goalies:  projected shots against (opponent shots-for, own team shots-allowed)
          x save % (shrunk); only for a confidently identified starter.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from nba_props.espn import Game, Injury
import nba_props.model as NM
from nba_props.model import (DEMOTE, LAST_GAME_NOTE, VIG_PROB, Pick, _nb_cdf, _phi, _short, _to_american,
                             against_last_game, est_line, market_disagrees, shop)
from nba_props.odds import PropLine, american_to_prob, norm_name

from .espn_nhl import STAT_FUNCS, NhlLine, NhlPlayer

KNOBS = {
    "model_weight": 0.6,
    "toi_scale": 1.0,
    "sh_prior": 150.0,       # shots of shrinkage for shooting %
    "sv_prior": 1200.0,      # shots of shrinkage for goalie save %
    "dvp_prior": 40.0,
    "goalie_power": 1.0,
    "env_scale": 1.0,
    "absorb": 0.35,
    "rate_l10": 0.35,
}
SH_PRIOR = {"F": 0.105, "D": 0.045}
LEAGUE_SV = 0.900
STATS = {"F": ["SOG", "PTS", "AST", "GOALS"], "D": ["SOG", "PTS", "AST", "GOALS"], "G": ["SAVES"]}
POISSON = {"PTS", "AST", "GOALS"}
MIN_VIEW = {"SOG": 1.2, "PTS": 0.3, "AST": 0.2, "GOALS": 0.12, "SAVES": 15}
FULL = {"SOG": "shots on goal", "PTS": "points", "AST": "assists", "GOALS": "goals", "SAVES": "saves"}


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def implied_goals(total: float | None, ml_home: int | None, ml_away: int | None) -> tuple[float, float] | None:
    """Split a game total into team goals matching the no-vig moneyline (Poisson, OT ~ coin flip)."""
    if not total or ml_home is None or ml_away is None:
        return None
    a, b = american_to_prob(ml_home), american_to_prob(ml_away)
    target = a / (a + b)

    def p_home(share):
        lh, la = total * share, total * (1 - share)
        ph = [math.exp(-lh) * lh ** k / math.factorial(k) for k in range(14)]
        pa = [math.exp(-la) * la ** k / math.factorial(k) for k in range(14)]
        win = sum(ph[i] * pa[j] for i in range(14) for j in range(14) if i > j)
        tie = sum(ph[i] * pa[i] for i in range(14))
        return win + 0.52 * tie
    lo, hi = 0.2, 0.8
    for _ in range(40):
        mid = (lo + hi) / 2
        if p_home(mid) < target:
            lo = mid
        else:
            hi = mid
    s = (lo + hi) / 2
    return total * s, total * (1 - s)


# ----------------------------------------------------------------------------- profiles
@dataclass
class Profile:
    player: NhlPlayer
    n_cur: int
    toi: float
    rates: dict           # per minute: sog, a, g (skaters) ; sv_pct, sa (goalies)
    season_avg: dict
    l10_avg: dict
    cv_toi: float = 0.2
    base_vol: dict = field(default_factory=dict)


def _per_min(logs, key):
    t = sum(g.s.get("toi", 0) for g in logs)
    return sum(g.s.get(key, 0) for g in logs) / t if t > 0 else None


def build_profile(p: NhlPlayer, season: int) -> Profile | None:
    cur = [g for g in p.logs if g.season == season]
    prev = [g for g in p.logs if g.season == season - 1]
    if not cur and not prev:
        return None
    n = len(cur)
    w = n / (n + 10)
    last10, last5 = p.logs[:10], p.logs[:5]
    t5, tc, tp = _mean(g.s["toi"] for g in last5), _mean(g.s["toi"] for g in cur), _mean(g.s["toi"] for g in prev)
    toi = (w * (0.5 * t5 + 0.5 * tc) + (1 - w) * (0.5 * t5 + 0.5 * tp)) if cur and prev else \
          (0.5 * t5 + 0.5 * (tc if cur else tp))
    season_avg, l10 = {}, {}
    for s in STAT_FUNCS:
        ac, ap = _mean(g.get(s) for g in cur), _mean(g.get(s) for g in prev)
        season_avg[s] = (w * ac + (1 - w) * ap) if (cur and prev) else (ac if cur else ap)
        l10[s] = _mean(g.get(s) for g in last10)
    rates = {}
    if p.group == "G":
        shots = sum(g.s.get("sa", 0) for g in p.logs[:40])
        saves = sum(g.s.get("sv", 0) for g in p.logs[:40])
        k = KNOBS["sv_prior"]
        rates["sv_pct"] = (saves + k * LEAGUE_SV) / (shots + k)
    else:
        a = KNOBS["rate_l10"]
        for key in ("sog", "a"):
            rc, rp, r10 = _per_min(cur, key), _per_min(prev, key), _per_min(last10, key) or 0.0
            if rc is not None and rp is not None:
                rates[key] = w * ((1 - a) * rc + a * r10) + (1 - w) * ((1 - a) * rp + a * r10)
            elif rc is not None:
                rates[key] = (1 - a) * rc + a * r10
            else:
                rates[key] = (1 - a) * (rp or 0) + a * r10
        shots = sum(g.s.get("sog", 0) for g in p.logs[:82])
        goals = sum(g.s.get("g", 0) for g in p.logs[:82])
        k = KNOBS["sh_prior"]
        rates["sh"] = (goals + k * SH_PRIOR[p.group]) / (shots + k)
    tois = [g.s["toi"] for g in last10]
    cv = statistics.pstdev(tois) / _mean(tois) if len(tois) >= 3 and _mean(tois) else 0.25
    prof = Profile(p, n, toi, rates, season_avg, l10, cv)
    if p.group != "G":
        prof.base_vol = {"sog": rates["sog"] * toi, "a": rates["a"] * toi, "g": rates["sog"] * toi * rates["sh"]}
    return prof


# ----------------------------------------------------------------------------- league context
class League:
    def __init__(self, players: list[NhlPlayer], profiles: dict[str, Profile], season: int):
        self.season = season
        self.profiles = profiles
        self.team_events: dict[str, dict] = defaultdict(dict)
        team_shots = defaultdict(lambda: defaultdict(float))        # team -> event -> shots for
        opp_of = {}
        for p in players:
            for g in p.logs:
                if g.season == season and (g.team_id or p.team_id) == p.team_id:
                    self.team_events[p.team_id][g.event_id] = g.date
                    if p.group != "G":
                        team_shots[p.team_id][g.event_id] += g.s.get("sog", 0)
                        opp_of[(p.team_id, g.event_id)] = g.opp_id
        self.shots_for = {t: _mean(ev.values()) for t, ev in team_shots.items() if ev}
        against = defaultdict(list)
        for t, ev in team_shots.items():
            for e, sf in ev.items():
                o = opp_of.get((t, e))
                if o:
                    against[o].append(sf)
        self.shots_against = {t: _mean(v) for t, v in against.items()}
        self.lg_shots = _mean(self.shots_for.values()) or 29.0
        self.dvp_tab = self._build_dvp(players)

    def recent_events(self, team_id, k):
        ev = self.team_events.get(team_id, {})
        return [e for e, _ in sorted(ev.items(), key=lambda kv: kv[1], reverse=True)[:k]]

    def last_game(self, team_id):
        ev = self.team_events.get(team_id, {})
        return max(ev.values()) if ev else None

    def _build_dvp(self, players):
        obs, exp, tot, cnt = defaultdict(float), defaultdict(float), defaultdict(float), defaultdict(float)
        for p in players:
            if p.group == "G":
                continue
            for off, wt in ((0, 1.0), (1, 0.3)):
                logs = [g for g in p.logs if g.season == self.season - off]
                if len(logs) < 3:
                    continue
                r = _per_min(logs, "sog") or 0
                for g in logs:
                    if not g.opp_id:
                        continue
                    e = r * g.s["toi"]
                    obs[(g.opp_id, p.group)] += wt * g.s.get("sog", 0)
                    exp[(g.opp_id, p.group)] += wt * e
                    tot[p.group] += e
                    cnt[p.group] += 1
        out = {}
        for key, e in exp.items():
            k = tot[key[1]] / max(1, cnt[key[1]]) * KNOBS["dvp_prior"]
            out[key] = _clip((obs[key] + k) / (e + k), 0.82, 1.18)
        return out

    def dvp(self, opp, group):
        return self.dvp_tab.get((opp, group), 1.0)


def likely_goalie(goalies: list[NhlPlayer], profiles, league: League, team_id: str, inj: dict, today):
    """(goalie, confidence 0-1). Starts in the team's last 5 games; backups often start back-to-backs."""
    recent5 = league.recent_events(team_id, 5)
    cand = [g for g in goalies if g.id in profiles and not (inj.get(g.id) and inj[g.id].level in ("OUT", "DOUBTFUL"))]
    if not cand:
        return None, 0.0
    starts = {g.id: sum(1 for x in g.logs if x.event_id in recent5 and x.s.get("gs", 1) >= 1 and x.s.get("toi", 0) >= 30)
              for g in cand}
    best = max(cand, key=lambda g: (starts[g.id], profiles[g.id].n_cur))
    conf = starts[best.id] / max(1, len(recent5)) if recent5 else 0.5
    last = league.last_game(team_id)
    last_local = last.astimezone(today.tzinfo) if (last and today and today.tzinfo) else last
    if last_local and today and (today.date() - last_local.date()).days == 1:      # back-to-back
        played_last = any(x.event_id == league.recent_events(team_id, 1)[0] for x in best.logs) if recent5 else False
        if played_last:
            conf *= 0.4
    return best, conf


# ----------------------------------------------------------------------------- projection
@dataclass
class Projection:
    player: NhlPlayer
    team_abbr: str
    opp_abbr: str
    game: Game
    mean: dict
    toi: float
    status: str
    reasons: list
    stat_reasons: dict
    profile: Profile
    goalie_conf: float = 1.0


def project_team(team_players, team_id, team_abbr, opp_id, opp_abbr, game: Game, league: League,
                 injuries: dict[str, Injury], team_goals: float | None, lg_team_goals: float,
                 opp_goalie: NhlPlayer | None, my_goalie: NhlPlayer | None, my_goalie_conf: float) -> list[Projection]:
    profs = league.profiles
    inj = {p.id: injuries.get(p.id) or injuries.get(p.name) for p in team_players}
    inj = {k: v for k, v in inj.items() if v and v.level != "ACTIVE"}
    recent5 = league.recent_events(team_id, 5)

    def out(p):
        i = inj.get(p.id)
        return bool(i and i.level in ("OUT", "DOUBTFUL"))

    skaters = [p for p in team_players if p.group != "G" and p.id in profs]
    out_mates = []
    for p in skaters:
        if out(p) and profs[p.id].toi >= 12:
            played = {g.event_id for g in p.logs}
            pres = sum(e in played for e in recent5) / len(recent5) if recent5 else 1.0
            if pres > 0:
                out_mates.append((p, profs[p.id], pres))
    active = []
    for p in skaters:
        pr = profs[p.id]
        if out(p) or pr.n_cur < 2 or pr.toi < 10:
            continue
        played = {g.event_id for g in p.logs}
        if len(recent5) >= 4 and sum(e in played for e in recent5) < 2:
            continue
        active.append((p, pr))
    vac = {k: sum(pr.base_vol[k] * pres for _, pr, pres in out_mates) for k in ("sog", "a", "g")}
    act = {k: sum(pr.base_vol[k] for _, pr in active) or 1.0 for k in ("sog", "a", "g")}

    # goalie + environment
    gf = 1.0
    g_note = None
    if opp_goalie is not None and opp_goalie.id in profs:
        sv = profs[opp_goalie.id].rates["sv_pct"]
        gf = _clip(((1 - sv) / (1 - LEAGUE_SV)) ** KNOBS["goalie_power"], 0.75, 1.3)
        if abs(gf - 1) >= 0.06:
            g_note = f"Opposing goalie {opp_goalie.name} ({sv:.3f} sv%): goals {'easier' if gf > 1 else 'harder'} ({(gf - 1) * 100:+.0f}%)"
    env_g = env_s = 1.0
    env_note = None
    if team_goals and lg_team_goals:
        r = team_goals / lg_team_goals
        env_g = _clip(r ** KNOBS["env_scale"], 0.75, 1.3)
        env_s = _clip(r ** (0.3 * KNOBS["env_scale"]), 0.92, 1.08)
        if abs(r - 1) >= 0.08:
            env_note = f"Implied team goals {team_goals:.2f} ({'high' if r > 1 else 'low'} vs avg {lg_team_goals:.2f})"

    res = []
    for p, pr in active:
        reasons, sr = [], defaultdict(list)
        i = inj.get(p.id)
        status = i.level if i else "ACTIVE"
        if i:
            reasons.append(f"Listed {i.status}" + (f": {i.detail}" if i.detail else ""))
        toi = pr.toi * KNOBS["toi_scale"] * (0.97 if status == "QUESTIONABLE" else 1.0)
        d = league.dvp(opp_id, p.group)
        sog = pr.rates["sog"] * toi * d * env_s
        ast = pr.rates["a"] * toi * env_g * gf ** 0.8
        goals = sog * pr.rates["sh"] * gf * (env_g / env_s)
        if out_mates:
            add_s = vac["sog"] * KNOBS["absorb"] * pr.base_vol["sog"] / act["sog"]
            add_a = vac["a"] * KNOBS["absorb"] * pr.base_vol["a"] / act["a"]
            add_g = vac["g"] * KNOBS["absorb"] * pr.base_vol["g"] / act["g"]
            sog, ast, goals = sog + add_s, ast + add_a, goals + add_g
            if add_s >= 0.25 or add_a + add_g >= 0.08:
                reasons.append(f"{', '.join(_short(x.name) for x, _, _ in out_mates[:3])} out: +{add_s:.1f} shots, +{add_a + add_g:.2f} pts")
        if abs(d - 1) >= 0.05:
            sr["SOG"].append(f"{opp_abbr} {'allows' if d > 1 else 'limits'} shots to {'defensemen' if p.group == 'D' else 'forwards'} ({(d - 1) * 100:+.0f}%)")
        for s in ("GOALS", "PTS", "AST"):
            if g_note:
                sr[s].append(g_note)
            if env_note:
                sr[s].append(env_note)
        m = {"SOG": sog, "AST": ast, "GOALS": goals, "PTS": goals + ast}
        res.append(Projection(p, team_abbr, opp_abbr, game, m, toi, status, reasons, dict(sr), pr))

    # goalie saves
    if my_goalie is not None and my_goalie.id in profs:
        gp = profs[my_goalie.id]
        opp_sf = league.shots_for.get(opp_id, league.lg_shots)
        my_sa = league.shots_against.get(team_id, league.lg_shots)
        sa = 0.5 * opp_sf + 0.5 * my_sa
        sv = gp.rates["sv_pct"]
        notes = [f"Projected starter ({my_goalie_conf * 100:.0f}% of recent starts)",
                 f"Expected shots against {sa:.1f} ({opp_abbr} shots for {opp_sf:.1f}, team allows {my_sa:.1f})"]
        res.append(Projection(my_goalie, team_abbr, opp_abbr, game, {"SAVES": sa * sv}, gp.toi, "ACTIVE",
                              notes, {}, gp, my_goalie_conf))
    return res


# ----------------------------------------------------------------------------- evaluation
def _probs(stat, mu, line, cv=0.5):
    mu = max(mu, 0.01)
    integer = abs(line - round(line)) < 1e-9
    if stat == "SAVES":
        sd = max(4.0, 0.2 * mu)
        if integer:
            return 1 - _phi((line + 0.5 - mu) / sd), _phi((line - 0.5 - mu) / sd)
        o = 1 - _phi((line - mu) / sd)
        return o, 1 - o
    var = mu * 1.03 if stat in POISSON else mu * 1.25
    if integer:
        k = int(round(line))
        return 1 - _nb_cdf(k, mu, var), _nb_cdf(k - 1, mu, var)
    u = _nb_cdf(int(math.floor(line)), mu, var)
    return 1 - u, u


def _hits(logs, stat, line, side):
    vals = [g.get(stat) for g in logs]
    return sum((v > line) if side == "OVER" else (v < line) for v in vals), len(vals)


def evaluate(proj: Projection, lines: dict, season: int) -> list[Pick]:
    p, pr = proj.player, proj.profile
    out = []
    cur = [g for g in p.logs if g.season == season]
    vs_opp = [g for g in p.logs if g.opp_abbr == proj.opp_abbr][:4]
    for s in STATS[p.group]:
        if s not in proj.mean:
            continue
        if s == "SAVES" and proj.goalie_conf < 0.6:
            continue
        mu = proj.mean[s]
        view = 0.55 * pr.l10_avg[s] + 0.45 * pr.season_avg[s]
        real = lines.get((norm_name(p.name), s))
        if s == "GOALS" and not real:
            continue                        # anytime goal: only real "yes" prices (no under to bet)
        if real:
            line, src = real.line, real.label
        else:
            if not NM.ALLOW_EST:
                continue
            if view < MIN_VIEW[s]:
                continue
            line = 0.5 if s == "GOALS" else est_line(view)
            src = "est."
        over_m, under_m = _probs(s, mu, line)
        if real and real.under_price is None:
            io = american_to_prob(real.over_price) or VIG_PROB
            fair_o, iu = io * 0.92, 1.0
        elif real:
            io = american_to_prob(real.over_price) or VIG_PROB
            iu = american_to_prob(real.under_price) or VIG_PROB
            fair_o = io / (io + iu)
        else:
            fair_o, _ = _probs(s, max(view, .05), line)
            io, iu = min(.97, fair_o + VIG_PROB - .5), min(.97, (1 - fair_o) + VIG_PROB - .5)
        mw = KNOBS["model_weight"]
        over = fair_o + mw * (over_m - fair_o)
        under = (1 - fair_o) + mw * (under_m - (1 - fair_o))
        if over - io >= under - iu:
            side, prob, edge, price = "OVER", over, over - io, (real.over_price if real else _to_american(io))
        else:
            side, prob, edge, price = "UNDER", under, under - iu, (real.under_price if real else _to_american(iu))
        h5, h10, hs, hv = (_hits(p.logs[:5], s, line, side), _hits(p.logs[:10], s, line, side),
                           _hits(cur, s, line, side), _hits(vs_opp, s, line, side))
        sample = min(1.0, len(p.logs[:30]) / 12)
        stability = 1 - _clip(pr.cv_toi - 0.12, 0, 0.45)
        status_f = {"QUESTIONABLE": 0.6, "PROBABLE": 0.95}.get(proj.status, 1.0)
        reliability = sample * stability * status_f * (proj.goalie_conf if s == "SAVES" else 1.0)
        score = edge * 100 * reliability
        grade = "A" if edge >= .08 and reliability >= .5 else "B" if edge >= .05 else "C" if edge >= .03 else "-"
        reasons = list(proj.stat_reasons.get(s, [])) + list(proj.reasons)
        if against_last_game(p.logs, lambda g: g.get(s), side, line):
            grade, score = "-", 0.0
            reasons.insert(0, LAST_GAME_NOTE)
        try:
            long_shot = int(price) >= 100
        except (TypeError, ValueError):
            long_shot = False
        if long_shot and grade != "-":
            grade, score = "-", 0.0
            reasons.insert(0, "Plus-money: not graded (NHL plus-money picks went 27-45 on real lines)")
        blocked = NM.NHL_BLOCKED.get((s, side))
        if blocked:
            grade, score = "-", 0.0
            reasons.insert(0, blocked)
        if market_disagrees(real, line, mu):
            grade, score = "-", 0.0
            reasons.insert(0, f"Market strongly disagrees ({real.books} books at {line:g} vs projection {mu:.1f}): skipped")
        if h10[1] >= 5:
            reasons.append(f"{side.title()} hit {h10[0]}/{h10[1]} of last {h10[1]} at {line}")
        if p.logs:
            lg = p.logs[0].get(s)
            reasons.append(f"Last game: {lg:g} ({'over' if lg > line else 'under' if lg < line else 'at'} the line)")
        if hv[1]:
            reasons.append(f"Last {hv[1]} vs {proj.opp_abbr}: " + ", ".join(f"{g.get(s):g}" for g in vs_opp))
        out.append(Pick(
            game_id=proj.game.id, game=proj.game.label, player=p.name, player_id=p.id, team=proj.team_abbr,
            opp=proj.opp_abbr, stat=s, side=side, line=line, line_source=src, price=price,
            projection=round(mu, 2 if s in POISSON else 1), prob=round(prob, 3), edge=round(edge, 3),
            score=round(score, 2), grade=grade, hit_l5=f"{h5[0]}/{h5[1]}", hit_l10=f"{h10[0]}/{h10[1]}",
            hit_season=f"{hs[0]}/{hs[1]}", vs_opp=f"{hv[0]}/{hv[1]}", minutes=round(proj.toi, 1),
            status=proj.status, season_avg=round(pr.season_avg[s], 2), l10_avg=round(pr.l10_avg[s], 2),
            reasons=reasons, last_game=p.logs[0].get(s) if p.logs else None,
            open_line=getattr(real, "open_line", None) if real else None,
            open_price=(getattr(real, "open_over", None) if side == "OVER" else getattr(real, "open_under", None)) if real else None,
            books=shop(real, side),
            dist=({"k": "normal", "sd": round(max(4.0, 0.2 * mu), 3)} if s == "SAVES"
                  else {"k": "count", "var": round(mu * (1.03 if s in POISSON else 1.25), 3)})))
    return out

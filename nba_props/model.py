"""Projection model and prop ranking.

For every rotation player on tonight's slate:

  projection = per-minute rate  x  projected minutes
               x opponent defense vs his position (DvP, per stat)
               x game environment (Vegas implied team total)
               x personal home/away split
               + usage/volume freed up by injured teammates

then compares the projection with the line (real if an odds key is set,
otherwise an estimate of where books open) using a per-stat distribution fit to
his own game-to-game variance. Picks are ranked by edge x reliability.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .espn import STAT_FUNCS, Game, GameLine, Injury, Player
from .odds import PropLine, american_to_prob, norm_name

BASE_STATS = ["PTS", "REB", "AST", "3PM", "STL", "BLK", "TOV"]
COMBOS = {"PRA": ["PTS", "REB", "AST"], "PR": ["PTS", "REB"], "PA": ["PTS", "AST"],
          "RA": ["REB", "AST"], "STOCKS": ["STL", "BLK"]}
COUNT_STATS = {"3PM", "STL", "BLK", "TOV", "STOCKS"}          # low-count -> negative binomial
DEFAULT_PROP_STATS = ["PTS", "REB", "AST", "3PM", "PRA", "PR", "PA", "RA", "STL", "BLK"]

# How strongly the game total moves each stat (elasticity).
ENV_ELASTICITY = {"PTS": 0.9, "REB": 0.3, "AST": 0.6, "3PM": 0.7, "STL": 0.3, "BLK": 0.2, "TOV": 0.4}
# Share of an injured teammate's volume the remaining roster typically absorbs.
ABSORB = {"PTS": 0.55, "REB": 0.65, "AST": 0.55, "3PM": 0.45, "STL": 0.4, "BLK": 0.45, "TOV": 0.5}
VIG_PROB = 110 / 210                                            # -110 implied
MODEL_WEIGHT = 0.6                                              # model vs market blend


def _to_american(p: float) -> int:
    p = min(max(p, 0.02), 0.98)
    return int(round(-100 * p / (1 - p))) if p >= 0.5 else int(round(100 * (1 - p) / p))

FULL = {"PTS": "points", "REB": "rebounds", "AST": "assists", "3PM": "threes", "STL": "steals",
        "BLK": "blocks", "TOV": "turnovers", "PRA": "pts+reb+ast", "PR": "pts+reb", "PA": "pts+ast",
        "RA": "reb+ast", "STOCKS": "stl+blk"}


# ----------------------------------------------------------------------------- math
def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _nb_cdf(k: int, mu: float, var: float) -> float:
    """P(X <= k) for a negative binomial (Poisson if not overdispersed)."""
    if k < 0:
        return 0.0
    if mu <= 0:
        return 1.0
    total = 0.0
    if var <= mu * 1.0001:
        for i in range(k + 1):
            total += math.exp(-mu + i * math.log(mu) - math.lgamma(i + 1))
        return min(1.0, total)
    r = mu * mu / (var - mu)
    p = r / (r + mu)
    for i in range(k + 1):
        total += math.exp(math.lgamma(i + r) - math.lgamma(r) - math.lgamma(i + 1)
                          + r * math.log(p) + i * math.log(1 - p))
    return min(1.0, total)


def prob_over_under(stat: str, mu: float, sd: float, line: float) -> tuple[float, float]:
    integer_line = abs(line - round(line)) < 1e-9
    if stat in COUNT_STATS:
        var = max(sd * sd, mu * 1.02)
        if integer_line:
            k = int(round(line))
            under = _nb_cdf(k - 1, mu, var)
            over = 1 - _nb_cdf(k, mu, var)
        else:
            under = _nb_cdf(int(math.floor(line)), mu, var)
            over = 1 - under
        return over, under
    sd = max(sd, 0.5)
    if integer_line:
        return 1 - _phi((line + 0.5 - mu) / sd), _phi((line - 0.5 - mu) / sd)
    over = 1 - _phi((line - mu) / sd)
    return over, 1 - over


def est_line(v: float) -> float:
    """Where a book would likely hang the line: nearest x.5."""
    lo = math.floor(v) - 0.5
    hi = math.floor(v) + 0.5
    best = lo if abs(v - lo) < abs(v - hi) else hi
    return max(0.5, best)


def _short(name: str) -> str:
    parts = [x for x in name.split() if x.rstrip(".").lower() not in ("jr", "sr", "ii", "iii", "iv")]
    return parts[-1] if parts else name


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


# ----------------------------------------------------------------------------- profiles
@dataclass
class Profile:
    player: Player
    n_cur: int
    rates: dict[str, float]          # per-minute, blended
    min_base: float
    min_cv: float
    season_avg: dict[str, float]     # per game, blended season-level average (all stats incl combos)
    l10_avg: dict[str, float]
    last_game: datetime | None
    base_vol: dict[str, float] = field(default_factory=dict)   # rate * min_base

    @property
    def id(self):
        return self.player.id


def _rate(logs: list[GameLine], stat: str) -> float | None:
    m = sum(g.min for g in logs)
    return sum(g.get(stat) for g in logs) / m if m > 0 else None


def build_profile(p: Player, season: int) -> Profile | None:
    cur = [g for g in p.logs if g.season == season]
    prev = [g for g in p.logs if g.season == season - 1]
    if not cur and not prev:
        return None
    last10, last5 = p.logs[:10], p.logs[:5]
    n = len(cur)
    w = n / (n + 10)
    rates = {}
    for s in BASE_STATS:
        rc, rp, r10 = _rate(cur, s), _rate(prev, s), _rate(last10, s) or 0.0
        if rc is not None and rp is not None:
            rates[s] = w * (0.65 * rc + 0.35 * r10) + (1 - w) * (0.6 * rp + 0.4 * r10)
        elif rc is not None:
            rates[s] = 0.65 * rc + 0.35 * r10
        else:
            rates[s] = 0.6 * (rp or 0) + 0.4 * r10
    m5 = _mean(g.min for g in last5)
    mc, mp = _mean(g.min for g in cur), _mean(g.min for g in prev)
    if cur and prev:
        min_base = w * (0.5 * m5 + 0.5 * mc) + (1 - w) * (0.55 * m5 + 0.45 * mp)
    elif cur:
        min_base = 0.5 * m5 + 0.5 * mc
    else:
        min_base = 0.5 * m5 + 0.5 * mp
    mins10 = [g.min for g in last10]
    cv = statistics.pstdev(mins10) / _mean(mins10) if len(mins10) >= 3 and _mean(mins10) else 0.3
    all_stats = list(STAT_FUNCS)
    season_avg = {}
    for s in all_stats:
        a_c, a_p = _mean(g.get(s) for g in cur), _mean(g.get(s) for g in prev)
        season_avg[s] = (w * a_c + (1 - w) * a_p) if (cur and prev) else (a_c if cur else a_p)
    l10_avg = {s: _mean(g.get(s) for g in last10) for s in all_stats}
    prof = Profile(p, n, rates, min_base, cv, season_avg, l10_avg, p.logs[0].date if p.logs else None)
    prof.base_vol = {s: rates[s] * min_base for s in BASE_STATS}
    return prof


# ----------------------------------------------------------------------------- league context
class League:
    """Cross-player context: team schedules and opponent defense vs position."""

    def __init__(self, players: list[Player], profiles: dict[str, Profile], season: int):
        self.season = season
        self.players = players
        self.profiles = profiles
        self.team_events: dict[str, dict[str, datetime]] = defaultdict(dict)
        for p in players:
            for g in p.logs:
                if g.season == season and (g.team_id or p.team_id) == p.team_id:
                    self.team_events[p.team_id][g.event_id] = g.date
        self.dvp = self._build_dvp()

    def recent_events(self, team_id: str, k: int) -> list[str]:
        ev = self.team_events.get(team_id, {})
        return [e for e, _ in sorted(ev.items(), key=lambda kv: kv[1], reverse=True)[:k]]

    def last_game_date(self, team_id: str) -> datetime | None:
        ev = self.team_events.get(team_id, {})
        return max(ev.values()) if ev else None

    def _build_dvp(self):
        """Ratio of what players actually produced vs each opponent to what their
        own per-minute rates predicted, pooled by opponent x position x stat and
        shrunk toward 1.0."""
        obs = defaultdict(float)
        exp = defaultdict(float)
        exp_all = defaultdict(float)
        cnt_all = defaultdict(float)
        for p in self.players:
            prof = self.profiles.get(p.id)
            if not prof:
                continue
            for season_off, wt in ((0, 1.0), (1, 0.35)):
                s_logs = [g for g in p.logs if g.season == self.season - season_off]
                if len(s_logs) < 3:
                    continue
                rates = {s: _rate(s_logs, s) or 0.0 for s in BASE_STATS}
                for g in s_logs:
                    if g.min < 12 or not g.opp_id:
                        continue
                    for s in BASE_STATS:
                        e = rates[s] * g.min
                        key = (g.opp_id, p.pos_group, s)
                        obs[key] += wt * g.get(s)
                        exp[key] += wt * e
                        exp_all[(p.pos_group, s)] += e
                        cnt_all[(p.pos_group, s)] += 1
        out = {}
        for key, e in exp.items():
            _, pg, s = key
            per_game = exp_all[(pg, s)] / max(1, cnt_all[(pg, s)])
            k = per_game * 30            # prior worth ~30 player-games
            out[key] = _clip((obs[key] + k) / (e + k), 0.82, 1.18)
        return out

    def dvp_factor(self, opp_id: str, pos_group: str, stat: str) -> float:
        return self.dvp.get((opp_id, pos_group, stat), 1.0)


# ----------------------------------------------------------------------------- per-player projection
@dataclass
class Projection:
    player: Player
    team_abbr: str
    opp_abbr: str
    game: Game
    minutes: float
    mean: dict[str, float]
    sd: dict[str, float]
    status: str
    reasons: list[str]
    stat_reasons: dict[str, list[str]]
    profile: Profile


def _sd_from_logs(p: Player, stat: str, proj: float, hist_mean: float) -> float:
    vals = [g.get(stat) for g in p.logs[:30]]
    if len(vals) >= 5:
        sd = statistics.pstdev(vals)
    else:
        sd = math.sqrt(max(proj, 0.5)) * 1.2
    if hist_mean > 0:
        sd *= math.sqrt(max(proj, 0.1) / hist_mean)
    floor = math.sqrt(max(proj, 0.1)) * (0.9 if stat in COUNT_STATS else 1.0)
    return max(sd, floor)


def _with_without(p: Player, mate: Player, team_id: str, stats: list[str]):
    """Per-game averages for p when `mate` sat vs played, on this team only."""
    mate_seasons: dict[int, list[GameLine]] = defaultdict(list)
    for g in mate.logs:
        if g.team_id in ("", team_id):
            mate_seasons[g.season].append(g)
    with_, without = [], []
    for g in p.logs:
        if g.team_id and g.team_id != team_id:
            continue
        ml = mate_seasons.get(g.season)
        if not ml:
            continue
        if g.event_id in {x.event_id for x in ml}:
            with_.append(g)
        elif g.date >= min(x.date for x in ml):
            without.append(g)
    if len(with_) < 3 or len(without) < 3:
        return None
    return ({s: _mean(x.get(s) for x in with_) for s in stats},
            {s: _mean(x.get(s) for x in without) for s in stats}, len(without))


def project_team(team_players: list[Player], team_id: str, team_abbr: str, opp_id: str,
                 opp_abbr: str, game: Game, league: League, injuries: dict[str, Injury],
                 slate_tt_avg: float, today: datetime) -> list[Projection]:
    profiles = league.profiles
    inj = {p.id: injuries.get(p.id) or injuries.get(p.name) for p in team_players}
    recent5 = league.recent_events(team_id, 5)
    team_n = len(league.team_events.get(team_id, {}))

    # --- who is out, and how much of their production was still in recent games
    out_mates = []
    for p in team_players:
        i = inj.get(p.id)
        prof = profiles.get(p.id)
        if i and i.level in ("OUT", "DOUBTFUL") and prof and prof.min_base >= 12:
            played = {g.event_id for g in p.logs}
            presence = (sum(e in played for e in recent5) / len(recent5)) if recent5 else 1.0
            if presence > 0:
                out_mates.append((p, prof, presence))

    # --- eligible rotation players
    active = []
    for p in team_players:
        prof = profiles.get(p.id)
        i = inj.get(p.id)
        if not prof or (i and i.level in ("OUT", "DOUBTFUL")):
            continue
        if prof.n_cur < 2 or prof.min_base < 14:
            continue
        played = {g.event_id for g in p.logs}
        if team_n >= 4 and sum(e in played for e in recent5) < 2 and not i:
            continue                                   # fell out of the rotation
        active.append((p, prof))

    vacated = {s: sum(pr.base_vol[s] * pres for _, pr, pres in out_mates) for s in BASE_STATS}
    vac_min = sum(pr.min_base * pres for _, pr, pres in out_mates)
    act_vol = {s: sum(pr.base_vol[s] for _, pr in active) or 1.0 for s in BASE_STATS}
    act_min = sum(pr.min_base for _, pr in active) or 1.0
    key_out = max(out_mates, key=lambda t: t[1].min_base * t[2], default=None)

    # --- game-level factors
    tt = game.implied_total(team_id)
    env = {s: 1.0 for s in BASE_STATS}
    env_note = ""
    if tt and slate_tt_avg:
        ratio = tt / slate_tt_avg
        env = {s: _clip(ratio ** ENV_ELASTICITY[s], 0.9, 1.1) for s in BASE_STATS}
        if abs(ratio - 1) >= 0.025:
            env_note = f"Implied team total {tt:.1f} ({'high' if ratio > 1 else 'low'} vs slate avg {slate_tt_avg:.1f})"
    spread = game.spread_home if team_id == game.home.id else (-game.spread_home if game.spread_home is not None else None)
    last = league.last_game_date(team_id)
    rest_days = None
    if last:
        rest_days = (today.date() - last.astimezone(today.tzinfo or timezone.utc).date()).days
    is_home = team_id == game.home.id

    out = []
    for p, prof in active:
        reasons, stat_reasons = [], defaultdict(list)
        i = inj.get(p.id)
        status = i.level if i else "ACTIVE"
        if i:
            reasons.append(f"Listed {i.status}" + (f": {i.detail}" if i.detail else ""))

        # minutes
        mins = prof.min_base
        mf = 1.0
        if rest_days == 1:
            mf *= 0.96 if mins >= 30 else 0.99
            reasons.append("Back-to-back")
        elif rest_days is not None and rest_days >= 3:
            mf *= 1.01
        if spread is not None and abs(spread) >= 9:
            if mins >= 28:
                mf *= max(0.93, 1 - 0.007 * (abs(spread) - 8))
                reasons.append(f"Blowout risk (spread {spread:+.1f}) trims starter minutes")
            elif mins < 22:
                mf *= 1.03
        if status == "QUESTIONABLE":
            mf *= 0.97
        mins_adj = mins * mf
        mins_shown = min(40.0, mins_adj + vac_min * (prof.min_base / act_min) * 0.8)

        # home/away personal split (shrunk)
        home_g = [g for g in p.logs[:60] if g.home]
        away_g = [g for g in p.logs[:60] if not g.home]
        ha = 1.0
        if len(home_g) >= 5 and len(away_g) >= 5:
            rh, ra = _rate(home_g, "PTS") or 0, _rate(away_g, "PTS") or 0
            if rh > 0 and ra > 0:
                split = (rh / ra) if is_home else (ra / rh)
                k = min(len(home_g), len(away_g)) / (min(len(home_g), len(away_g)) + 25)
                ha = _clip(1 + 0.5 * (math.sqrt(split) - 1) * k, 0.96, 1.04)

        wow = _with_without(p, key_out[0], team_id, BASE_STATS) if key_out else None

        mean = {}
        for s in BASE_STATS:
            base = prof.rates[s] * mins_adj
            d = league.dvp_factor(opp_id, p.pos_group, s)
            v = base * d * env[s] * (ha if s in ("PTS", "3PM", "AST") else 1.0)
            if abs(d - 1) >= 0.05:
                stat_reasons[s].append(
                    f"{opp_abbr} {'allows' if d > 1 else 'limits'} {FULL[s]} to {p.pos_group}s ({(d - 1) * 100:+.0f}% vs expected)")
            if env_note and ENV_ELASTICITY[s] >= 0.6:
                stat_reasons[s].append(env_note)
            # injury volume
            if out_mates:
                redis = vacated[s] * ABSORB[s] * (prof.base_vol[s] / act_vol[s])
                add = redis
                if wow:
                    w_with, w_without, n_wo = wow
                    delta = _clip(w_without[s] - w_with[s], -0.4 * base - 0.5, 0.4 * base + 0.5)
                    k = n_wo / (n_wo + 6)
                    add = (1 - k * 0.6) * redis + k * 0.6 * delta
                v += add
                if abs(add) >= max(0.6, 0.06 * base):
                    names = ", ".join(_short(m.name) for m, _, _ in out_mates[:3])
                    stat_reasons[s].append(f"{names} out: {add:+.1f} {FULL[s]}"
                                           + (" (with/without split)" if wow else " (usage share)"))
            mean[s] = max(0.0, v)
        for c, parts in COMBOS.items():
            mean[c] = sum(mean[x] for x in parts)
            for x in parts:
                for r in stat_reasons[x]:
                    if r not in stat_reasons[c]:
                        stat_reasons[c].append(r)

        sd = {s: _sd_from_logs(p, s, mean[s], prof.season_avg.get(s, 0)) for s in mean}
        out.append(Projection(p, team_abbr, opp_abbr, game, mins_shown, mean, sd, status,
                              reasons, dict(stat_reasons), prof))
    return out


# ----------------------------------------------------------------------------- props
@dataclass
class Pick:
    game_id: str
    game: str
    player: str
    player_id: str
    team: str
    opp: str
    stat: str
    side: str
    line: float
    line_source: str
    price: int | None
    projection: float
    prob: float
    edge: float
    score: float
    grade: str
    hit_l5: str
    hit_l10: str
    hit_season: str
    vs_opp: str
    minutes: float
    status: str
    season_avg: float
    l10_avg: float
    reasons: list[str]

    def to_dict(self):
        return self.__dict__.copy()


def _hits(logs: list[GameLine], stat: str, line: float, side: str) -> tuple[int, int]:
    vals = [g.get(stat) for g in logs]
    h = sum((v > line) if side == "OVER" else (v < line) for v in vals)
    return h, len(vals)


def evaluate(proj: Projection, stats: list[str], lines: dict[tuple[str, str], PropLine],
             season: int) -> list[Pick]:
    p, prof = proj.player, proj.profile
    picks = []
    cur_logs = [g for g in p.logs if g.season == season]
    opp_logs = [g for g in p.logs if g.opp_abbr == proj.opp_abbr][:5]
    for s in stats:
        mu = proj.mean[s]
        real = lines.get((norm_name(p.name), s))
        book_view = 0.55 * prof.l10_avg[s] + 0.45 * prof.season_avg[s]
        if real:
            line, src = real.line, f"{real.books} books"
        else:
            if book_view < 0.7:
                continue
            line, src = est_line(book_view), "est."
        over_m, under_m = prob_over_under(s, mu, proj.sd[s], line)
        if real:
            io = american_to_prob(real.over_price) or VIG_PROB
            iu = american_to_prob(real.under_price) or VIG_PROB
            fair_o = io / (io + iu)
        else:
            # Price the estimated line the way a book would: fair to its own
            # (recent-average) view, plus ~2.4% vig on each side.
            fair_o, _ = prob_over_under(s, book_view, proj.sd[s] * math.sqrt(max(book_view, .1) / max(mu, .1)), line)
            io, iu = min(.97, fair_o + VIG_PROB - .5), min(.97, (1 - fair_o) + VIG_PROB - .5)
        # Shrink the model toward the market: books are sharp, so trust our
        # adjustments only partially.
        over = fair_o + MODEL_WEIGHT * (over_m - fair_o)
        under = (1 - fair_o) + MODEL_WEIGHT * (under_m - (1 - fair_o))
        e_over, e_under = over - io, under - iu
        if e_over >= e_under:
            side, prob, edge, price = "OVER", over, e_over, (real.over_price if real else _to_american(io))
        else:
            side, prob, edge, price = "UNDER", under, e_under, (real.under_price if real else _to_american(iu))
        h5 = _hits(p.logs[:5], s, line, side)
        h10 = _hits(p.logs[:10], s, line, side)
        hs = _hits(cur_logs, s, line, side)
        hv = _hits(opp_logs, s, line, side)
        sample = min(1.0, len(p.logs[:40]) / 15)
        stability = 1 - _clip(prof.min_cv - 0.12, 0, 0.45)
        status_f = {"QUESTIONABLE": 0.6, "PROBABLE": 0.95}.get(proj.status, 1.0)
        reliability = sample * stability * status_f
        hit_bonus = ((h10[0] / h10[1]) - 0.5) * 6 if h10[1] >= 5 else 0
        score = edge * 100 * reliability + hit_bonus * reliability
        grade = "A" if score >= 9 else "B" if score >= 6 else "C" if score >= 3 else "-"
        reasons = list(proj.stat_reasons.get(s, [])) + list(proj.reasons)
        if h10[1] >= 5:
            reasons.append(f"{side.title()} hit {h10[0]}/{h10[1]} of last {h10[1]} at {line}")
        if hv[1]:
            reasons.append(f"Last {hv[1]} vs {proj.opp_abbr}: " + ", ".join(f"{g.get(s):g}" for g in opp_logs))
        picks.append(Pick(
            game_id=proj.game.id, game=proj.game.label, player=p.name, player_id=p.id,
            team=proj.team_abbr, opp=proj.opp_abbr, stat=s, side=side, line=line, line_source=src,
            price=price, projection=round(mu, 1), prob=round(prob, 3), edge=round(edge, 3),
            score=round(score, 2), grade=grade,
            hit_l5=f"{h5[0]}/{h5[1]}", hit_l10=f"{h10[0]}/{h10[1]}", hit_season=f"{hs[0]}/{hs[1]}",
            vs_opp=f"{hv[0]}/{hv[1]}", minutes=round(proj.minutes, 1), status=proj.status,
            season_avg=round(prof.season_avg[s], 1), l10_avg=round(prof.l10_avg[s], 1), reasons=reasons))
    return picks


def best_picks(picks: list[Pick], per_game: int = 6, per_player: int = 1, top_n: int = 15):
    """Top picks per game (max `per_player` per player) plus a best-overall list
    (one per player). Only positive-edge picks are kept."""
    good = sorted([p for p in picks if p.edge > 0.02 and p.score >= 3], key=lambda p: -p.score)
    by_game: dict[str, list[Pick]] = defaultdict(list)
    used: dict[tuple[str, str], int] = defaultdict(int)
    for p in good:
        if len(by_game[p.game_id]) < per_game and used[(p.game_id, p.player_id)] < per_player:
            by_game[p.game_id].append(p)
            used[(p.game_id, p.player_id)] += 1
    top, seen = [], set()
    for p in good:
        if p.player_id not in seen:
            top.append(p)
            seen.add(p.player_id)
        if len(top) >= top_n:
            break
    return top, by_game

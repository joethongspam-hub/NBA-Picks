import sys, json
from multiprocessing import Pool
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
CACHE = sys.argv[1]
CONFIGS = {
    "baseline": {},
    "no_dvp": {"dvp_power": 0},
    "dvp_strong_prior": {"dvp_prior": 120},
    "no_injury": {"absorb_scale": 0},
    "half_injury": {"absorb_scale": 0.5},
    "b2b_0.92": {"b2b": 0.92},
    "min_0.96": {"min_scale": 0.96},
    "min_0.94": {"min_scale": 0.94},
    "no_env": {"env_scale": 0},
    "l10_0.2": {"rate_l10": 0.2},
    "tuned": {},
    "tuned_no_blowout": {"blowout": 0},
    "tuned_b2b_off": {"b2b": 1.0},
    "c1_min95_abs35": {"min_scale": 0.95, "absorb_scale": 0.35},
    "c2_min95_abs35_dvp120": {"min_scale": 0.95, "absorb_scale": 0.35, "dvp_prior": 120},
    "c3_min95_abs0": {"min_scale": 0.95, "absorb_scale": 0},
    "c4_min97_abs35_dvp120": {"min_scale": 0.97, "absorb_scale": 0.35, "dvp_prior": 120},
    "c5_min95_abs35_dvp120_env.5": {"min_scale": 0.95, "absorb_scale": 0.35, "dvp_prior": 120, "env_scale": 0.5},
    "c6_min93_abs35_dvp120": {"min_scale": 0.93, "absorb_scale": 0.35, "dvp_prior": 120},
}


def one(name):
    import nba_props.model as Mo
    from tests.analyze import season, rec
    Mo.KNOBS.update(CONFIGS[name])
    d = season(CACHE)
    allp = [p for p in d["all"] if p["result"] in ("WIN", "LOSS", "PUSH")]
    pos = [p for p in allp if p["edge"] > 0.02]
    shown = [p for p in d["shown"] if p["result"] in ("WIN", "LOSS", "PUSH")]
    import statistics as st
    pts = [p for p in allp if p["stat"] == "PTS"]
    buckets = {}
    for lo, hi in ((.02, .04), (.04, .06), (.06, .08), (.08, .12), (.12, 1)):
        buckets[f"e{lo}"] = rec([p for p in pos if lo <= p["edge"] < hi])
    for lo, hi in ((3, 6), (6, 9), (9, 99)):
        buckets[f"s{lo}"] = rec([p for p in pos if lo <= p["score"] < hi])
    print(name, json.dumps(buckets), flush=True)
    return name, rec(shown), rec(pos), rec([p for p in pos if p["side"] == "OVER"]), rec([p for p in pos if p["side"] == "UNDER"]), \
        round(st.mean(abs(p["projection"] - p["actual"]) for p in pts), 3), round(st.mean(p["projection"] - p["actual"] for p in pts), 2)


if __name__ == "__main__":
    names = sys.argv[2].split(",") if len(sys.argv) > 2 else list(CONFIGS)
    with Pool(4, maxtasksperchild=1) as pool:
        for r in pool.imap(one, names):
            print("%-18s shown %-16s pos %-18s over %-18s under %-18s PTS mae %s bias %s" % r, flush=True)

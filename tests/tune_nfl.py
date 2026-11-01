"""Offline NFL tuning on a data snapshot.  python tests/tune_nfl.py /tmp/nflsnap/.cache [names]"""
import json, statistics as st, sys, tempfile
from multiprocessing import Pool
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
CACHE = sys.argv[1]
CONFIGS = {
    "baseline": {},
    "no_weather": {"weather": 0},
    "wind_k_.015": {"wind_k": 0.015},
    "wind_start_10": {"wind_start": 10.0},
    "absorb_0.4": {"absorb": 0.4},
    "vol_0.95": {"vol_scale": 0.95},
    "qb_shrink_0.4": {"qb_shrink": 0.4},
    "eff_shrink_0.6": {"eff_shrink": 0.6},
    "no_dvp": {"dvp_power": 0},
    "dvp_prior_100": {"dvp_prior": 100},
    "script_0.5": {"script": 0.5},
    "env_0.5": {"env_scale": 0.5},
    "prev_0.7": {"prev_weight": 0.7},
    "t1_abs.4_qbvol1.05": {"absorb": 0.4, "qb_vol": 1.05},
    "t2_abs.4_qbvol1.05_vol.97": {"absorb": 0.4, "qb_vol": 1.05, "vol_scale": 0.97},
    "t3_abs.4_qbvol1.08_vol.97": {"absorb": 0.4, "qb_vol": 1.08, "vol_scale": 0.97},
    "t4_abs.3_qbvol1.05": {"absorb": 0.3, "qb_vol": 1.05},
}


def rec(ps):
    w = sum(p["result"] == "WIN" for p in ps); l = sum(p["result"] == "LOSS" for p in ps)
    return f"{w}-{l} ({w / max(1, w + l) * 100:.1f}%)"


def one(name):
    import nfl_props.main as M
    import nfl_props.model as Mo
    from tests.offline import OfflineHttp
    M.log = lambda *a: None
    Mo.KNOBS.update(CONFIGS[name])
    t = tempfile.mkdtemp()
    M.backtest_weeks(3, 8, out_dir=t + "/nfl", hist_dir=t + "/h", http=OfflineHttp(CACHE))
    d = json.loads(Path(t + "/nfl/backtests/season_props.json").read_text())
    allp = [p for p in d["all"] if p["result"] in ("WIN", "LOSS", "PUSH")]
    pos = [p for p in allp if p["edge"] >= .03]
    shown = [p for p in d["shown"] if p["result"] in ("WIN", "LOSS")]
    bias = {}
    for s in ("PASS_YDS", "RUSH_YDS", "REC_YDS", "REC"):
        r = [p for p in allp if p["stat"] == s]
        bias[s] = round(st.mean(p["projection"] - p["actual"] for p in r), 1) if r else None
    gA = rec([p for p in pos if p["grade"] == "A"])
    return name, rec(shown), rec(pos), gA, rec([p for p in pos if p["side"] == "OVER"]), \
        rec([p for p in pos if p["side"] == "UNDER"]), json.dumps(bias)


if __name__ == "__main__":
    names = sys.argv[2].split(",") if len(sys.argv) > 2 else list(CONFIGS)
    with Pool(2, maxtasksperchild=1) as pool:
        for r in pool.imap(one, names):
            print("%-16s shown %-15s pos %-17s A %-17s over %-17s under %-17s bias %s" % r, flush=True)

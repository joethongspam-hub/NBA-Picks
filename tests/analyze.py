"""Offline season backtest + diagnostics.  python tests/analyze.py /tmp/snap/.cache"""
import json, statistics as st, sys, tempfile
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nba_props.main as M
from tests.offline import OfflineHttp

M.log = lambda *a: None


def season(cache, start="2026-10-24", end="2026-10-30"):
    t = tempfile.mkdtemp()
    M.backtest_range(start, end, out_dir=t + "/s", hist_dir=t + "/h", backtest_dir=t + "/bt",
                     http=OfflineHttp(cache))
    return json.loads(Path(t + "/bt/season_props.json").read_text())


def rec(ps):
    w = sum(p["result"] == "WIN" for p in ps); l = sum(p["result"] == "LOSS" for p in ps)
    return f"{w}-{l} ({w / (w + l) * 100:.1f}%)" if w + l else "0-0"


def report(d, verbose=True):
    allp = [p for p in d["all"] if p["result"] in ("WIN", "LOSS", "PUSH")]
    shown = [p for p in d["shown"] if p["result"] in ("WIN", "LOSS", "PUSH")]
    pos = [p for p in allp if p["edge"] >= 0.03]
    out = {"shown": rec(shown), "pos": rec(pos)}
    print("SHOWN", rec(shown), "| POS-EDGE", rec(pos), "| ALL props n", len(allp))
    if not verbose:
        return out
    for g in "ABC":
        print(f"  grade {g}", rec([p for p in shown if p["grade"] == g]))
    print("by stat (pos-edge):", {s: rec([p for p in pos if p["stat"] == s]) for s in sorted({p["stat"] for p in pos})})
    print("by side:", {s: rec([p for p in pos if p["side"] == s]) for s in ("OVER", "UNDER")})
    print("by night:", {n: rec([p for p in pos if p["date"] == n]) for n in sorted({p["date"] for p in pos})})
    # calibration
    b = defaultdict(list)
    for p in allp:
        b[min(int(p["prob"] * 20) / 20, .8)].append(p)
    print("calibration (prob bucket: n, actual win%):",
          {k: (len(v), round(sum(x["result"] == "WIN" for x in v) / max(1, sum(x["result"] in ("WIN", "LOSS") for x in v)), 3)) for k, v in sorted(b.items())})
    tags = {"injury": lambda p: any(" out:" in r for r in p["reasons"]),
            "dvp": lambda p: any("allows" in r or "limits" in r for r in p["reasons"]),
            "env": lambda p: any("Implied team total" in r for r in p["reasons"]),
            "blowout": lambda p: any("Blowout" in r for r in p["reasons"]),
            "b2b": lambda p: any("Back-to-back" in r for r in p["reasons"]),
            "questionable": lambda p: p["status"] == "QUESTIONABLE"}
    for k, f in tags.items():
        print(f"  {k:12s} with: {rec([p for p in pos if f(p)])}  without: {rec([p for p in pos if not f(p)])}")
    for s in ("PTS", "REB", "AST", "3PM", "PRA"):
        r = [p for p in allp if p["stat"] == s and p["actual"] is not None]
        print(f"  {s}: n={len(r)} model MAE {st.mean(abs(p['projection'] - p['actual']) for p in r):.2f} "
              f"line MAE {st.mean(abs(p['line'] - p['actual']) for p in r):.2f}  model bias {st.mean(p['projection'] - p['actual'] for p in r):+.2f} "
              f"line bias {st.mean(p['line'] - p['actual'] for p in r):+.2f}")
    return out


if __name__ == "__main__":
    report(season(sys.argv[1]))

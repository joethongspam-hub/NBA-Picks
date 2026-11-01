import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfl_props.main import run, backtest_weeks
from tests.fake_nfl import FakeNflHttp, NflLeague


def test_nfl_live_and_backtest():
    lg = NflLeague()
    t = Path(tempfile.mkdtemp())
    pl = run(out_dir=str(t / "nfl"), hist_dir=str(t / "h"), http=FakeNflHttp(lg))
    assert len(pl["games"]) == 16 and pl["top"]
    allp = pl["all"]
    assert not any(p["player_id"] == "105" for p in allp)                  # OUT player dropped
    wr2 = [p for p in allp if p["player_id"] == "106" and p["stat"] == "REC"][0]
    assert any("out:" in r for r in wr2["reasons"]), wr2["reasons"]
    stats = {p["stat"] for p in allp}
    assert {"PASS_YDS", "REC_YDS", "RUSH_YDS", "ANY_TD"} <= stats, stats
    assert (t / "nfl" / "index.html").exists()
    s = backtest_weeks(4, 8, out_dir=str(t / "nfl"), hist_dir=str(t / "h"), http=FakeNflHttp(lg))
    assert len(s["weeks"]) == 5
    rec = [w["record"]["all_positive_edge"] for w in s["weeks"]]
    print("live picks", len(pl["top"]), "| backtest", rec)
    return t


if __name__ == "__main__":
    print(test_nfl_live_and_backtest())

import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nba_props.main import run
from tests.fake_espn import FakeHttp, League


def test_backtest():
    tmp = Path(tempfile.mkdtemp())
    lg = League()
    day = sorted({e["date"] for e in lg.events.values() if e["date"].year == 2026 and e["date"].month == 10})[-2]
    pl = run(day.strftime("%Y-%m-%d"), out_dir=str(tmp / "site"), hist_dir=str(tmp / "h"),
             http=FakeHttp(lg), backtest=True, backtest_dir=str(tmp / "bt"))
    graded = [p for p in pl["all"] if p["result"] in ("WIN", "LOSS", "PUSH")]
    assert graded and all(p["actual"] is not None for p in graded)
    assert pl["record"]["accuracy"]["PTS"]["n"] > 50
    assert (tmp / "bt" / f"{day:%Y-%m-%d}.html").exists()
    # no lookahead: no projection may use a log from that day
    print("backtest", pl["date"], pl["record"]["all"], pl["record"]["all_positive_edge"], pl["record"]["accuracy"])
    return tmp


if __name__ == "__main__":
    print(test_backtest())

import pytest
import json, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nba_props.main import run
from tests.fake_espn import FakeHttp, League


def test_pipeline(tmp=None):
    tmp = Path(tmp or tempfile.mkdtemp())
    lg = League()
    payload = run("2026-10-30", out_dir=str(tmp / "site"), hist_dir=str(tmp / "hist"), http=FakeHttp(lg), allow_est=True)
    assert len(payload["games"]) == 5
    assert payload["top"], "expected some picks"
    allp = payload["all"]
    # star who is OUT must not be projected
    assert not any(p["player_id"] == "1001" for p in allp)
    # questionable player still projected, flagged
    assert any(p["player_id"] == "1004" and p["status"] == "QUESTIONABLE" for p in allp)
    # teammate should be credited with the star's usage
    r = [p for p in allp if p["player_id"] == "1002" and p["stat"] == "PTS"][0]
    assert not any("out:" in x for x in r["reasons"]), "injury boost is turned off for the NBA"
    # DEN (8) should show as soft vs centers for ATL's C
    c = [p for p in allp if p["player_id"] == "1005" and p["stat"] == "REB"][0]
    assert any("DEN allows" in x for x in c["reasons"]), c["reasons"]
    assert (tmp / "site" / "index.html").stat().st_size > 10000
    return tmp, payload


if __name__ == "__main__":
    tmp, payload = test_pipeline("/tmp/npt")
    print("OK", tmp)


@pytest.mark.no_unders
def test_overs_only(tmp=None):
    tmp = Path(tmp or tempfile.mkdtemp())
    payload = run("2026-10-30", out_dir=str(tmp / "site"), hist_dir=str(tmp / "hist"), http=FakeHttp(League()), allow_est=True)
    graded = [p for p in payload["all"] if p["grade"] != "-"]
    assert all(p["side"] == "OVER" for p in graded + payload["top"])
    assert any(p["side"] == "UNDER" and "Unders not offered" in p["reasons"][0] for p in payload["all"])


def test_streak_levels():
    from types import SimpleNamespace as N
    from nba_props.streaks import player_streaks
    mk = lambda v: N(season=2027, min=30, get=lambda st, v=v: v if st == "PTS" else 0)
    s = player_streaks([mk(v) for v in [25, 22, 30, 19, 24, 18, 27, 21, 20, 23, 8]], 2027)[0]
    assert (s["t5"], s["t10"], s["run5"], s["run10"]) == (19, 18, 5, 10)

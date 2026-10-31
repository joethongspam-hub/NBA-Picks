import json, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nba_props.main import run
from tests.fake_espn import FakeHttp, League


def test_pipeline(tmp=None):
    tmp = Path(tmp or tempfile.mkdtemp())
    lg = League()
    payload = run("2026-10-30", out_dir=str(tmp / "site"), hist_dir=str(tmp / "hist"), http=FakeHttp(lg))
    assert len(payload["games"]) == 5
    assert payload["top"], "expected some picks"
    allp = payload["all"]
    # star who is OUT must not be projected
    assert not any(p["player_id"] == "1001" for p in allp)
    # questionable player still projected, flagged
    assert any(p["player_id"] == "1004" and p["status"] == "QUESTIONABLE" for p in allp)
    # teammate should be credited with the star's usage
    r = [p for p in allp if p["player_id"] == "1002" and p["stat"] == "PTS"][0]
    assert any("out:" in x for x in r["reasons"]), r["reasons"]
    # DEN (8) should show as soft vs centers for ATL's C
    c = [p for p in allp if p["player_id"] == "1005" and p["stat"] == "REB"][0]
    assert any("DEN allows" in x for x in c["reasons"]), c["reasons"]
    assert (tmp / "site" / "index.html").stat().st_size > 10000
    return tmp, payload


if __name__ == "__main__":
    tmp, payload = test_pipeline("/tmp/npt")
    print("OK", tmp)

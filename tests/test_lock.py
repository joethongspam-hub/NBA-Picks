"""Picks lock at tip-off: a later run keeps pregame picks for started games."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nba_props.main as M
from tests.fake_espn import FakeHttp, League

M.log = lambda *a: None


def test_lock():
    lg = League()
    t = Path(tempfile.mkdtemp())
    kw = dict(out_dir=str(t / "s"), hist_dir=str(t / "h"))
    M.run("2026-10-30", http=FakeHttp(lg), **kw)
    before = json.loads((t / "h/picks/2026-10-30.json").read_text())
    g0 = before[0]["game_id"]
    pre = {(p["player_id"], p["stat"], p["side"], p["line"]) for p in before if p["game_id"] == g0}
    # second run: first game now in progress, and the injury report changed
    sb = lg.scoreboard_json

    def live():
        d = sb()
        for e in d["events"]:
            if e["id"] == g0:
                e["status"]["type"]["description"] = "Halftime"
        return d
    lg.scoreboard_json = live
    lg.injuries_json = lambda: {"injuries": []}
    pl = M.run("2026-10-30", http=FakeHttp(lg), **kw)
    after = json.loads((t / "h/picks/2026-10-30.json").read_text())
    post = {(p["player_id"], p["stat"], p["side"], p["line"]) for p in after if p["game_id"] == g0}
    assert pre == post, "started game's picks must not change"
    assert all(p.get("locked") for p in after if p["game_id"] == g0)
    assert not any(p["game_id"] == g0 for p in pl["all"]), "no fresh props for a started game"
    print("lock OK:", len(pre), "picks kept for the started game")


if __name__ == "__main__":
    test_lock()

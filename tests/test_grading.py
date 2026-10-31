import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nba_props.main import grade_history, summarize
from nba_props.espn import Espn
from tests.fake_espn import FakeHttp, League


def test_grading():
    lg = League()
    espn = Espn(FakeHttp(lg))
    p = espn.roster("1")[1]
    espn.load_logs([p], [2027], 2027)
    g = p.logs[0]
    tmp = Path(tempfile.mkdtemp()); (tmp / "picks").mkdir()
    base = dict(game_id=g.event_id, game="x", player=p.name, player_id=p.id, team="ATL", opp="DEN",
                line_source="est.", projection=0, prob=.6, edge=.1, grade="A", score=10)
    picks = [dict(base, stat="PTS", side="OVER", line=g.pts - 0.5),
             dict(base, stat="REB", side="OVER", line=g.reb + 0.5),
             dict(base, stat="AST", side="UNDER", line=g.ast + 0.5, game_id="nope")]
    (tmp / "picks" / "2026-10-20.json").write_text(json.dumps(picks))
    res = grade_history(tmp, {p.id: p}, "2026-10-30")
    out = {r["stat"]: r["result"] for r in res["graded"]}
    assert out == {"PTS": "WIN", "REB": "LOSS", "AST": "VOID"}, out
    s = summarize(res)
    assert s["A"]["w"] == 1 and s["A"]["l"] == 1
    # idempotent
    assert len(grade_history(tmp, {p.id: p}, "2026-10-30")["graded"]) == 3


if __name__ == "__main__":
    test_grading(); print("grading OK")

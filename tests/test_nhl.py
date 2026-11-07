import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nhl_props.main as M
from tests.fake_nhl import FakeNhlHttp, NhlLeague

M.log = lambda *a: None


def test_nhl():
    lg = NhlLeague()
    t = Path(tempfile.mkdtemp())
    days = sorted(d for d in lg.days if d.startswith("2026"))
    day = days[-1]
    orig = lg.scoreboard_json

    def pregame(d):
        sb = orig(d)
        for e in sb["events"]:
            e["status"]["type"]["description"] = "Scheduled"
        return sb
    lg.scoreboard_json = pregame
    ds = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    pl = M.run(ds, out_dir=str(t / "nhl"), hist_dir=str(t / "h"), http=FakeNhlHttp(lg))
    lg.scoreboard_json = orig
    assert len(pl["games"]) == 16 and pl["top"], "expected picks"
    stats = {p["stat"] for p in pl["all"]}
    assert {"SOG", "PTS", "AST"} <= stats, stats          # anytime goal needs a real DK price (none in the fake league)
    assert not any(p["player_id"] == "101" for p in pl["all"]), "OUT player must be dropped"
    team = pl["team"]["all"]
    assert team and {p["market"] for p in team} == {"Moneyline", "Puck line", "Total"}
    # backtest a couple of nights
    s = M.backtest_range(f"{days[-4][:4]}-{days[-4][4:6]}-{days[-4][6:]}", ds, out_dir=str(t / "nhl"),
                         hist_dir=str(t / "h"), http=FakeNhlHttp(lg))
    print("NHL OK: live picks", len(pl["top"]), "| saves picks", sum(p["stat"] == "SAVES" for p in pl["all"]),
          "| team bets", len(team), "| backtest nights", len(s["nights"]), "team", s["team"]["all"])
    return t


if __name__ == "__main__":
    print(test_nhl())

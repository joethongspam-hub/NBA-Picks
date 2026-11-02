"""Results-only run grades saved picks, annotates the page, builds a notification, fetches no odds."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nba_props.main as M
from tests.fake_espn import FakeHttp, League

M.log = lambda *a: None


def test_results():
    lg = League()
    t = Path(tempfile.mkdtemp())
    day = sorted({e["date"] for e in lg.events.values() if e["date"].year == 2026})[-2].strftime("%Y-%m-%d")
    orig = lg.past_scoreboard

    def pregame(d):                                   # first run: games not started yet
        sb = orig(d)
        for e in (sb or {}).get("events", []):
            e["status"]["type"]["description"] = "Scheduled"
        return sb
    lg.past_scoreboard = pregame
    M.run(day, out_dir=str(t / "s"), hist_dir=str(t / "h"), http=FakeHttp(lg))
    lg.past_scoreboard = orig
    calls = []

    class Spy(FakeHttp):
        def get_json(self, url, params=None, ttl=None):
            calls.append(url)
            return super().get_json(url, params, ttl)
    out = M.results_only(out_dir=str(t / "s"), hist_dir=str(t / "h"), http=Spy(lg), notify_out=str(t / "n.json"))
    assert out["new"] and all(r["result"] in ("WIN", "LOSS", "PUSH", "VOID") for r in out["new"])
    assert all("/gamelog" in u for u in calls), "results run must only fetch box scores"
    page = json.loads((t / "s/picks.json").read_text())
    assert any(p.get("result") in ("WIN", "LOSS") for p in page["top"])
    msg = json.loads((t / "n.json").read_text())
    print("results OK:", msg["title"], "|", msg["body"].splitlines()[0], "| calls", len(calls))


if __name__ == "__main__":
    test_results()

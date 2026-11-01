# NBA + NFL Player Props Finder

Every day this app pulls the NBA schedule, injury report, Vegas lines and every player's game logs,
projects each rotation player's stat line, and ranks the props with the biggest edge. The output is a
phone-friendly web page (`site/index.html`), plus `picks.csv` and `picks.json`.

## What goes into a projection

| Factor | How it's used |
|---|---|
| **Per-minute production** | Blend of this season, last 10 games, and last season (last season fades out as games pile up) |
| **Projected minutes** | Last 5 games and season average, then adjusted for the factors below |
| **Injuries – the player** | OUT/Doubtful players are dropped. Questionable players lose 3% of minutes and get a lower confidence score |
| **Injuries – teammates** | An injured teammate's points, rebounds, assists etc. get handed to the players still active. If a player has 3+ games without that teammate, those games are blended in too (a "with/without" split). A teammate who has been out a while already shows up in recent games, so he only counts for the games he actually played lately |
| **Opponent defense vs position** | For every team, what guards, forwards and centers actually produced against them compared with their own per-minute rates. Calculated separately for each stat and pulled toward average when the sample is small |
| **Game environment** | Vegas implied team total compared with the slate average (pace and efficiency), with a different strength for each stat |
| **Blowout risk** | Spreads of 9+ cut starters' minutes and add a little to the bench |
| **Rest** | Back-to-backs cut minutes for heavy-minute players |
| **Home/away** | The player's own split, pulled toward no difference |
| **Trends & history** | Hit rate over the last 5 and 10 games and the season at the line, plus recent games vs. this opponent |

Each stat is modeled with the player's own game-to-game spread: a normal curve for points, rebounds,
assists and combos, and a negative binomial for low counts (threes, steals, blocks). Model
probabilities are blended 60/40 with the market price, because books are sharp. Then **edge = win
probability − implied probability from the price**. The score is edge × reliability (sample size,
how steady his minutes are, injury status), and grades are A ≥ 9, B ≥ 6, C ≥ 3.

## Lines: estimated vs. real

**DraftKings lines are pulled free from ESPN on every run** (no key needed) for points, rebounds, assists,
threes and the combos (NBA), and passing/rushing/receiving props plus anytime TD (NFL) when ESPN publishes them.
Props without a DraftKings line fall back to the options below.


* **No key (default):** the app estimates where a book would open (a mix of the last 10 games and the
  season average, rounded to x.5) and prices it the way a book would. Edges then come only from what
  the market's simple average misses: matchups, injuries, pace, rest. The page shows **est. lines**.
  Always check your book's real number.
* **Real lines:** get a free key at [the-odds-api.com](https://the-odds-api.com) and set
  `ODDS_API_KEY`. The app then uses the consensus line across US books and the best available price.
  The free tier (500 credits a month) covers about 4 markets × the nightly slate, once a day. Change markets
  with `ODDS_MARKETS` (e.g. `player_points,player_rebounds,player_assists,player_threes,player_points_rebounds_assists`).

## Run it on your computer

```bash
pip install -r requirements.txt
python -m nba_props.main                 # today's slate
python -m nba_props.main --date 2026-11-02
python -m nba_props.main --slate-only    # faster: only teams playing today
open site/index.html                     # (Windows: start site\index.html)
```

The first run loads about 400 players' game logs, which takes a minute or two. After that, results are cached in `.cache/`.

## Run it automatically every day (free, on GitHub)

1. Create a new GitHub repo and push this folder to it.
2. **Settings → Pages → Source: GitHub Actions.**
3. (Optional) **Settings → Secrets → Actions →** add `ODDS_API_KEY`.
4. **Actions → Daily NBA props → Run workflow** once to test it.

It then runs at 11 AM, 3:30 PM (real lines) and 5:45 PM Central. **Picks lock at tip-off**: once a game starts,
later runs keep its pregame picks (and never use live in-game lines), so the track record only grades bets you could
actually have made. It publishes the page to `https://<you>.github.io/<repo>/`,
and saves each day's picks in `history/` so the **Track record** tab can grade them the next day.

## Phone notifications

1. Install the free **ntfy** app (iOS / Android) and subscribe to a topic name only you know,
   e.g. `nba-picks-` followed by random letters. Anyone who knows the topic can read it, so keep it unguessable.
2. In the repo: **Settings → Secrets and variables → Actions → New repository secret**, Name `NTFY_TOPIC`,
   Secret = that topic name.

Every scheduled run that produces new or changed picks then sends a notification listing the top picks. Tap it to open the page.
To test: **Actions → Daily NBA props → Run workflow**, notify = `test`.

## Backtest a past date

See how the model would have done on a night that's already played:

```bash
python -m nba_props.main --backtest 2026-10-30
```

It hides every game from that date onward, projects the slate, then grades each pick against the real
box scores. You get a page with the win-loss record by grade and the model's average miss compared with just
using the player's recent average. On GitHub: **Actions → Daily NBA props → Run workflow** and fill in
`backtest_date`. The result appears at `.../backtests/<date>.html` and is linked from the Track record tab.
(Who sat out is taken from the box scores, which is slightly cleaner than the real pre-game injury report.)

## NFL

Same idea, weekly: `python -m nfl_props.main` (this week's upcoming games) and
`python -m nfl_props.main --backtest-weeks 3 8`. The page lives at `/nfl/` on your site.

The NFL model projects **opportunities × efficiency**:

* **Opportunities:** pass attempts, carries and targets per game, weighted toward the last 4 games, with last season fading out.
* **Game script:** underdogs throw more and favorites run more (from the Vegas spread).
* **Injured teammates:** their targets and carries get redistributed. If the starting QB is out, the backup is projected and his receivers' efficiency is trimmed.
* **Efficiency:** yards per attempt/carry/target, catch rate and TD rate, pulled hard toward position averages, because NFL samples are tiny.
* **Defense vs position and scoring environment:** opponent defense against QBs, RBs, WRs and TEs, plus the implied team total.

* **Weather:** domes and retractable roofs count as indoors. For outdoor games, the Open-Meteo game-time
  forecast (free) is used: wind above about 12 mph trims passing efficiency (about 1% per mph, up to 20%) and shifts
  volume toward the run; rain or snow trims passing about 4% more, and temperatures at or below 20°F about 2%.

Props: passing yards/TDs/attempts/completions/INTs, rushing yards/carries, receptions, receiving yards,
rush+rec yards, anytime TD. The workflow runs Wednesday, Thursday and Sunday morning (**Actions → Weekly NFL props**,
with optional backtest weeks).

Multi-book NFL lines from the Odds API use the same `ODDS_API_KEY` and are opt-in: add a repo **variable**
`NFL_ODDS` = `on`. They're pulled on the Thursday and Sunday runs only (about 60 credits/week). Optionally set
`NFL_ODDS_MARKETS` (default `player_pass_yds,player_reception_yds`). The NBA's Odds API pull is likewise opt-in
(`NBA_ODDS` = `on`), since the NBA gets free DraftKings lines from ESPN.

## Tests

```bash
python tests/test_pipeline.py   # full run against a simulated league in ESPN's JSON format
python tests/test_grading.py
python tests/test_backtest.py
python tests/test_nfl.py
```

## Data sources

ESPN's public JSON feeds (scoreboard and odds, injuries, rosters, player game logs). They're free
and need no key, but they aren't officially documented, so if ESPN changes a format, the parsers in
`nba_props/espn.py` are the place to fix it.

*For research and entertainment. No model beats the closing line every night, so bet responsibly.*

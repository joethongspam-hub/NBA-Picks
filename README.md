# NBA Player Props Finder

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

It then runs at 11 AM and 5 PM Central, publishes the page to `https://<you>.github.io/<repo>/`,
and saves each day's picks in `history/` so the **Track record** tab can grade them the next day.

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

## Tests

```bash
python tests/test_pipeline.py   # full run against a simulated league in ESPN's JSON format
python tests/test_grading.py
python tests/test_backtest.py
```

## Data sources

ESPN's public JSON feeds (scoreboard and odds, injuries, rosters, player game logs). They're free
and need no key, but they aren't officially documented, so if ESPN changes a format, the parsers in
`nba_props/espn.py` are the place to fix it.

*For research and entertainment. No model beats the closing line every night, so bet responsibly.*

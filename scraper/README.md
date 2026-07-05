# SofaScore NPL NSW scraper + projections

Extends the WC26 match-intel workflow (Playwright loads the JSON endpoint in
Chromium, parses the `<pre>` tag — gets past Cloudflare) from single matches to
a whole league season, then projects the next round from the scraped data.

**Run this on your laptop**, not in the Claude sandbox — SofaScore is not
reachable from the sandbox, so none of this has been executed against live
data. Verify JSON key names against a real response before building on top.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Pull the league

```bash
python sofascore_league_intel.py                 # full pull (standings, all matches, per-match stats)
python sofascore_league_intel.py --skip-details  # fast: standings + results + fixtures only
```

Defaults to NPL NSW 2026 (`unique-tournament 1274`, `season 88562` — the
`#id:...` fragment on the SofaScore league page URL). Edit `TOURNAMENT_ID` /
`SEASON_ID` at the top for any other competition.

Output in `data/`:

| file | contents |
|---|---|
| `standings.csv` | ladder with GF/GA, split total / home / away |
| `matches.csv` | every match: round, kickoff UTC, status, score (played + upcoming) |
| `match_stats.csv` | flattened team stats per finished match (possession, shots, corners, ...) |
| `match_snapshots.json` | full per-match snapshots: gk metrics, defensive actions, shot counts |

Coverage caveat for NPL NSW tier: no shotmap (so no shot-based xG) and no
running-performance data; per-match statistics exist for some but not all
games. Standings and results are always complete.

## Project the next round

```bash
python projections.py               # fixtures in the next 7 days
python projections.py --next-days 3
```

Fits Poisson attack/defence strengths from all played matches (with home
advantage estimated from the league's real home/away goal split) and prints,
for each upcoming fixture: expected goals, 1X2, BTTS, over/under 2.5, and fair
odds. "xG" here is model-expected goals — SofaScore has no shot-based xG at
this tier.

## Feed it back

Commit `data/` (or paste the projections output) into the Claude session and
the projections can be sanity-checked against market prices from there.

`sofascore_scraper.py` is a plain-`requests` fallback (no browser needed) —
works from most residential IPs; if it hits 403s, use the Playwright version.

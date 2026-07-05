"""projections.py — round projections from the scraped league data.

Reads data/matches.csv (from sofascore_league_intel.py), fits per-team
attack/defence strengths from played matches, and projects every upcoming
fixture: expected goals, 1X2, BTTS, over/under 2.5.

Model: goals-based Poisson.
  - team attack  = goals scored per game vs league average
  - team defence = goals conceded per game vs league average
  - home advantage estimated from the league's actual home/away goal split
  - matchday means: lambda_home = league_home_avg * att(H) * def(A), etc.
No shot data enters this (Sofascore has no shotmap/xG at NPL NSW tier), so
"xG" here means model-expected goals, not shot-based xG.

Usage: python projections.py [--data data] [--next-days 7]
"""

import argparse
import csv
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def load_matches(path: Path) -> list[dict]:
    with path.open() as fh:
        return list(csv.DictReader(fh))


def fit_strengths(played: list[dict]):
    gf = defaultdict(float); ga = defaultdict(float); n = defaultdict(int)
    home_goals = away_goals = 0
    for m in played:
        hg, ag = int(m["home_goals"]), int(m["away_goals"])
        h, a = m["home"], m["away"]
        gf[h] += hg; ga[h] += ag; n[h] += 1
        gf[a] += ag; ga[a] += hg; n[a] += 1
        home_goals += hg; away_goals += ag
    games = len(played)
    league_home_avg = home_goals / games
    league_away_avg = away_goals / games
    league_avg = (league_home_avg + league_away_avg) / 2

    att, dfn = {}, {}
    for team in n:
        att[team] = (gf[team] / n[team]) / league_avg
        dfn[team] = (ga[team] / n[team]) / league_avg
    return att, dfn, league_home_avg, league_away_avg


def pois(l: float, k: int) -> float:
    return math.exp(-l) * l**k / math.factorial(k)


def project(lh: float, la: float, max_goals: int = 10) -> dict:
    M = [[pois(lh, i) * pois(la, j) for j in range(max_goals + 1)] for i in range(max_goals + 1)]
    hw = sum(M[i][j] for i in range(max_goals + 1) for j in range(max_goals + 1) if i > j)
    dr = sum(M[i][i] for i in range(max_goals + 1))
    btts = sum(M[i][j] for i in range(1, max_goals + 1) for j in range(1, max_goals + 1))
    over = sum(M[i][j] for i in range(max_goals + 1) for j in range(max_goals + 1) if i + j > 2.5)
    return {"home": hw, "draw": dr, "away": 1 - hw - dr, "btts": btts, "over25": over}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--next-days", type=int, default=7, help="project fixtures within N days")
    args = ap.parse_args()

    matches = load_matches(args.data / "matches.csv")
    played = [m for m in matches if m["status"] == "finished" and m["home_goals"] not in ("", None)]
    horizon = datetime.now(timezone.utc) + timedelta(days=args.next_days)
    upcoming = [
        m for m in matches
        if m["status"] == "notstarted"
        and m["start_utc"]
        and datetime.strptime(m["start_utc"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc) <= horizon
    ]
    print(f"{len(played)} played matches fitted; projecting {len(upcoming)} fixtures\n")

    att, dfn, home_avg, away_avg = fit_strengths(played)
    print(f"league averages: home {home_avg:.2f}, away {away_avg:.2f} goals/game\n")

    for m in sorted(upcoming, key=lambda m: m["start_utc"]):
        h, a = m["home"], m["away"]
        if h not in att or a not in att:
            print(f"skipping {h} v {a} (team not in fitted data)")
            continue
        lh = home_avg * att[h] * dfn[a]
        la = away_avg * att[a] * dfn[h]
        p = project(lh, la)
        print(f"{m['start_utc']}  {h} v {a}")
        print(f"  xG {lh:.2f} - {la:.2f} (total {lh + la:.2f})")
        print(f"  1X2  H {p['home']:.0%}  D {p['draw']:.0%}  A {p['away']:.0%}"
              f"   BTTS {p['btts']:.0%}   O2.5 {p['over25']:.0%} / U2.5 {1 - p['over25']:.0%}")
        print(f"  fair odds  H {1/p['home']:.2f}  D {1/p['draw']:.2f}  A {1/p['away']:.2f}"
              f"  BTTS-Y {1/p['btts']:.2f}  O2.5 {1/p['over25']:.2f}  U2.5 {1/(1-p['over25']):.2f}\n")


if __name__ == "__main__":
    main()

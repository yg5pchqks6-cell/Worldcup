"""sofascore_league_intel.py

Extends the WC26 match-intel workflow (Playwright -> goto the JSON endpoint,
parse the <pre> tag) from single matches to a whole league season — built for
NPL NSW (unique-tournament 1274, season 88562) but works for any competition.

What it pulls on top of the match-level endpoints you already had
(shotmap / statistics / lineups / graph):

    - standings          total + home + away splits (GF/GA per team)
    - events/last        every played match, paginated
    - events/next        upcoming fixtures
    - per-match snapshot for each finished match, reusing the same parsers
      as sofascore_match_intel.py

Outputs (under data/):
    standings.csv        one row per team per scope (total/home/away)
    matches.csv          one row per match, played + upcoming
    match_stats.csv      flattened team stats per finished match
    match_snapshots.json full snapshots (gk metrics, defensive actions, ...)

Then run projections.py against data/ to get xG / 1X2 / BTTS / O-U 2.5
for the next round.

Requires: playwright, beautifulsoup4
    pip install playwright beautifulsoup4
    playwright install chromium

Note: run this in your own environment (Jupyter/local) — Sofascore isn't
reachable from the Claude sandbox, so this hasn't been executed against live
data. Sanity-check the JSON key names against a real response before building
on top of it; Sofascore shuffles field names occasionally. Heads-up for NPL
NSW specifically: expect shotmap (hence real xG) and running-performance to be
absent at this tier — the code treats every endpoint as optional and keeps
going, so you still get standings, results, and whatever team stats exist.
"""

import asyncio
import csv
import json
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser
from bs4 import BeautifulSoup

BASE = "https://www.sofascore.com/api/v1"

TOURNAMENT_ID = 1274   # NPL NSW
SEASON_ID = 88562      # 2026 (the #id:... fragment on the league page URL)
OUT_DIR = Path("data")


def match_id_from_url(url: str) -> str:
    return url.split("id:")[-1]


class SofascoreSession:
    """Same session pattern as sofascore_match_intel.py: one browser/context
    reused across many requests instead of a fresh launch per call."""

    def __init__(self, browser: Browser):
        self._browser = browser

    @classmethod
    async def create(cls):
        pw = await async_playwright().start()
        browser = await pw.chromium.launch()
        session = cls(browser)
        session._pw = pw  # keep a reference so it isn't garbage collected
        return session

    async def close(self):
        await self._browser.close()
        await self._pw.stop()

    async def _fetch_json(self, endpoint: str) -> Optional[dict]:
        page = await self._browser.new_page()
        try:
            await page.goto(f"{BASE}/{endpoint}")
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")
            pre = soup.select_one("pre")
            if pre is None:
                return None
            return json.loads(pre.text)
        except Exception as e:
            print(f"  [warn] {endpoint} failed: {e}")
            return None
        finally:
            await page.close()

    # ---- match endpoints (unchanged from the WC26 script) -----------------

    async def shotmap(self, match_id: str) -> Optional[list]:
        data = await self._fetch_json(f"event/{match_id}/shotmap")
        return data.get("shotmap") if data else None

    async def statistics(self, match_id: str) -> Optional[dict]:
        return await self._fetch_json(f"event/{match_id}/statistics")

    async def lineups(self, match_id: str) -> Optional[dict]:
        return await self._fetch_json(f"event/{match_id}/lineups")

    async def momentum(self, match_id: str) -> Optional[list]:
        data = await self._fetch_json(f"event/{match_id}/graph")
        return data.get("graphPoints") if data else None

    async def event_details(self, match_id: str) -> Optional[dict]:
        return await self._fetch_json(f"event/{match_id}")

    # ---- league endpoints (new) --------------------------------------------

    async def standings(self, tournament_id: int, season_id: int, scope: str = "total") -> Optional[dict]:
        """scope: total | home | away"""
        return await self._fetch_json(
            f"unique-tournament/{tournament_id}/season/{season_id}/standings/{scope}"
        )

    async def events_page(self, tournament_id: int, season_id: int, direction: str, page: int) -> Optional[dict]:
        """direction: 'last' (played, newest first) or 'next' (fixtures)."""
        return await self._fetch_json(
            f"unique-tournament/{tournament_id}/season/{season_id}/events/{direction}/{page}"
        )

    async def all_events(self, tournament_id: int, season_id: int, direction: str) -> list:
        events, page = [], 0
        while True:
            data = await self.events_page(tournament_id, season_id, direction, page)
            if not data or not data.get("events"):
                break
            events.extend(data["events"])
            if not data.get("hasNextPage"):
                break
            page += 1
            await asyncio.sleep(0.5)
        return events


# ---- parsing helpers (same as sofascore_match_intel.py) ---------------------

def parse_team_statistics(stats_json: dict) -> dict:
    out = {"home": {}, "away": {}}
    if not stats_json:
        return out
    periods = stats_json.get("statistics", [])
    all_period = next((p for p in periods if p.get("period") == "ALL"), None)
    if not all_period:
        return out
    for group in all_period.get("groups", []):
        for item in group.get("statisticsItems", []):
            name = item.get("name")
            out["home"][name] = item.get("homeValue", item.get("home"))
            out["away"][name] = item.get("awayValue", item.get("away"))
    return out


def parse_goalkeeper_metrics(lineups_json: dict) -> dict:
    out = {}
    if not lineups_json:
        return out
    for side in ("home", "away"):
        team = lineups_json.get(side, {})
        for entry in team.get("players", []):
            player = entry.get("player", {})
            if player.get("position") != "G":
                continue
            st = entry.get("statistics", {})
            out[side] = {
                "name": player.get("name"),
                "saves": st.get("saves"),
                "goalsPrevented": st.get("goalsPrevented"),
                "rating": st.get("rating"),
            }
            break
    return out


def parse_defensive_actions(lineups_json: dict) -> dict:
    totals = {"home": {}, "away": {}}
    if not lineups_json:
        return totals
    fields = ["totalTackle", "interceptionWon", "duelWon", "duelLost", "totalClearance"]
    for side in ("home", "away"):
        team = lineups_json.get(side, {})
        agg = {f: 0 for f in fields}
        for entry in team.get("players", []):
            st = entry.get("statistics", {})
            for f in agg:
                if isinstance(st.get(f), (int, float)):
                    agg[f] += st[f]
        totals[side] = agg
    return totals


# ---- league flattening -------------------------------------------------------

def flatten_standings(standings_json: dict, scope: str) -> list:
    rows = []
    if not standings_json:
        return rows
    for group in standings_json.get("standings", []):
        for row in group.get("rows", []):
            rows.append({
                "scope": scope,
                "position": row.get("position"),
                "team_id": row["team"]["id"],
                "team": row["team"]["name"],
                "played": row.get("matches"),
                "wins": row.get("wins"),
                "draws": row.get("draws"),
                "losses": row.get("losses"),
                "goals_for": row.get("scoresFor"),
                "goals_against": row.get("scoresAgainst"),
                "points": row.get("points"),
            })
    return rows


def flatten_event(ev: dict) -> dict:
    from datetime import datetime, timezone
    ts = ev.get("startTimestamp")
    return {
        "event_id": ev["id"],
        "round": ev.get("roundInfo", {}).get("round"),
        "start_utc": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if ts else None,
        "status": ev.get("status", {}).get("type"),
        "home_id": ev["homeTeam"]["id"],
        "home": ev["homeTeam"]["name"],
        "away_id": ev["awayTeam"]["id"],
        "away": ev["awayTeam"]["name"],
        "home_goals": ev.get("homeScore", {}).get("current"),
        "away_goals": ev.get("awayScore", {}).get("current"),
        "home_goals_ht": ev.get("homeScore", {}).get("period1"),
        "away_goals_ht": ev.get("awayScore", {}).get("period1"),
    }


def write_csv(rows: list, path: Path):
    if not rows:
        print(f"  [warn] nothing to write for {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({k for r in rows for k in r}, key=lambda k: list(rows[0].keys()).index(k) if k in rows[0] else 99)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {path} ({len(rows)} rows)")


# ---- orchestration -----------------------------------------------------------

async def build_match_snapshot(session: SofascoreSession, match_id: str) -> dict:
    details, stats, lineups, shotmap = await asyncio.gather(
        session.event_details(match_id),
        session.statistics(match_id),
        session.lineups(match_id),
        session.shotmap(match_id),
    )
    event = details.get("event", {}) if details else {}
    return {
        "match_id": match_id,
        "home_team": event.get("homeTeam", {}).get("name"),
        "away_team": event.get("awayTeam", {}).get("name"),
        "score": f"{event.get('homeScore', {}).get('current')} - {event.get('awayScore', {}).get('current')}",
        "team_stats": parse_team_statistics(stats),
        "goalkeepers": parse_goalkeeper_metrics(lineups),
        "defensive_actions": parse_defensive_actions(lineups),
        "shot_count": len(shotmap) if shotmap else 0,  # >0 means real xG exists for this match
    }


async def build_league_dataset(tournament_id: int = TOURNAMENT_ID,
                               season_id: int = SEASON_ID,
                               out_dir: Path = OUT_DIR,
                               with_match_details: bool = True):
    session = await SofascoreSession.create()
    try:
        print("standings ...")
        standings_rows = []
        for scope in ("total", "home", "away"):
            data = await session.standings(tournament_id, season_id, scope)
            standings_rows += flatten_standings(data, scope)
        write_csv(standings_rows, out_dir / "standings.csv")

        print("matches ...")
        played = await session.all_events(tournament_id, season_id, "last")
        upcoming = await session.all_events(tournament_id, season_id, "next")
        print(f"  {len(played)} played, {len(upcoming)} upcoming")
        write_csv([flatten_event(e) for e in played + upcoming], out_dir / "matches.csv")

        if with_match_details:
            finished = [e for e in played if e.get("status", {}).get("type") == "finished"]
            print(f"match snapshots for {len(finished)} finished matches ...")
            snapshots, stat_rows = [], []
            for i, ev in enumerate(finished, 1):
                print(f"  {i}/{len(finished)}: {ev['homeTeam']['name']} v {ev['awayTeam']['name']}")
                snap = await build_match_snapshot(session, str(ev["id"]))
                snapshots.append(snap)
                for side in ("home", "away"):
                    for stat, val in snap["team_stats"][side].items():
                        stat_rows.append({"event_id": ev["id"], "side": side, "stat": stat, "value": val})
                await asyncio.sleep(1)  # be polite between matches
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "match_snapshots.json").write_text(json.dumps(snapshots, indent=1, default=str))
            print(f"  wrote {out_dir / 'match_snapshots.json'}")
            write_csv(stat_rows, out_dir / "match_stats.csv")
    finally:
        await session.close()


if __name__ == "__main__":
    import sys
    fast = "--skip-details" in sys.argv
    asyncio.run(build_league_dataset(with_match_details=not fast))
    print("done. Now run: python projections.py")

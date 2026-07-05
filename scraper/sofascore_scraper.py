#!/usr/bin/env python3
"""SofaScore league scraper — NPL NSW by default (unique-tournament 1274, season 88562).

Pulls everything SofaScore exposes for a league season:
  - standings (total / home / away)
  - all played matches + upcoming fixtures
  - per-match statistics, lineups and incidents (goals, cards, subs)

Run it from a normal network (laptop/home) — SofaScore's API refuses
datacenter/cloud IPs. Output lands in data/ as raw JSON plus flat CSVs
that projections.py consumes.

Usage:
    pip install -r requirements.txt
    python sofascore_scraper.py                    # full pull, NPL NSW 2026
    python sofascore_scraper.py --skip-details     # standings + results only (fast)
    python sofascore_scraper.py --tournament 1274 --season 88562 --out data
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import requests

BASE = "https://api.sofascore.com/api/v1"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": "https://www.sofascore.com/",
    "Origin": "https://www.sofascore.com",
}

REQUEST_DELAY_S = 1.2  # be polite; the API bans aggressive clients
MAX_RETRIES = 4


class SofaScoreClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._last_request = 0.0

    def get(self, path: str, ok_404: bool = False) -> dict | None:
        """GET a JSON endpoint with throttling and backoff. Returns None on 404."""
        wait = REQUEST_DELAY_S - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(MAX_RETRIES):
            self._last_request = time.monotonic()
            try:
                resp = self.session.get(f"{BASE}{path}", timeout=20)
            except requests.RequestException as exc:
                print(f"  ! network error on {path}: {exc} (retry {attempt + 1})")
                time.sleep(2**attempt)
                continue
            if resp.status_code == 404:
                if ok_404:
                    return None
                raise RuntimeError(f"404 for {path}")
            if resp.status_code == 403:
                raise RuntimeError(
                    f"403 for {path} — SofaScore is blocking this IP/client. "
                    "Run from a residential connection, not a cloud host/VPN."
                )
            if resp.status_code == 429 or resp.status_code >= 500:
                backoff = 5 * (2**attempt)
                print(f"  ! HTTP {resp.status_code} on {path}, backing off {backoff}s")
                time.sleep(backoff)
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"gave up on {path} after {MAX_RETRIES} attempts")


def dump(obj: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False))


def fetch_standings(client: SofaScoreClient, ut: int, season: int, out: Path) -> list[dict]:
    rows: list[dict] = []
    for scope in ("total", "home", "away"):
        data = client.get(f"/unique-tournament/{ut}/season/{season}/standings/{scope}", ok_404=True)
        if data is None:
            print(f"  standings/{scope}: not available")
            continue
        dump(data, out / "raw" / f"standings_{scope}.json")
        for group in data.get("standings", []):
            for row in group.get("rows", []):
                rows.append(
                    {
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
                    }
                )
        print(f"  standings/{scope}: {sum(1 for r in rows if r['scope'] == scope)} teams")
    return rows


def fetch_events(client: SofaScoreClient, ut: int, season: int, direction: str, out: Path) -> list[dict]:
    """Page through events/last (played) or events/next (fixtures)."""
    events: list[dict] = []
    page = 0
    while True:
        data = client.get(
            f"/unique-tournament/{ut}/season/{season}/events/{direction}/{page}", ok_404=True
        )
        if data is None or not data.get("events"):
            break
        events.extend(data["events"])
        if not data.get("hasNextPage"):
            break
        page += 1
    dump({"events": events}, out / "raw" / f"events_{direction}.json")
    print(f"  events/{direction}: {len(events)} matches")
    return events


def flatten_event(ev: dict) -> dict:
    status = ev.get("status", {}).get("type", "")
    return {
        "event_id": ev["id"],
        "round": ev.get("roundInfo", {}).get("round"),
        "start_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime(ev.get("startTimestamp", 0))),
        "status": status,
        "home_id": ev["homeTeam"]["id"],
        "home": ev["homeTeam"]["name"],
        "away_id": ev["awayTeam"]["id"],
        "away": ev["awayTeam"]["name"],
        "home_goals": ev.get("homeScore", {}).get("current"),
        "away_goals": ev.get("awayScore", {}).get("current"),
        "home_goals_ht": ev.get("homeScore", {}).get("period1"),
        "away_goals_ht": ev.get("awayScore", {}).get("period1"),
    }


def fetch_match_details(client: SofaScoreClient, event_ids: list[int], out: Path) -> list[dict]:
    """Per-match statistics/lineups/incidents. Stats coverage varies by fixture."""
    stat_rows: list[dict] = []
    for i, eid in enumerate(event_ids, 1):
        print(f"  match details {i}/{len(event_ids)} (event {eid})")
        for kind in ("statistics", "lineups", "incidents"):
            data = client.get(f"/event/{eid}/{kind}", ok_404=True)
            if data is None:
                continue
            dump(data, out / "raw" / "events" / f"{eid}_{kind}.json")
            if kind == "statistics":
                for period in data.get("statistics", []):
                    if period.get("period") != "ALL":
                        continue
                    for group in period.get("groups", []):
                        for item in group.get("statisticsItems", []):
                            stat_rows.append(
                                {
                                    "event_id": eid,
                                    "group": group.get("groupName"),
                                    "stat": item.get("name"),
                                    "home": item.get("home"),
                                    "away": item.get("away"),
                                }
                            )
    return stat_rows


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  wrote {path} ({len(rows)} rows)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tournament", type=int, default=1274, help="unique-tournament id (1274 = NPL NSW)")
    ap.add_argument("--season", type=int, default=88562, help="season id (88562 = 2026)")
    ap.add_argument("--out", type=Path, default=Path("data"), help="output directory")
    ap.add_argument("--skip-details", action="store_true", help="skip per-match stats/lineups/incidents")
    args = ap.parse_args()

    client = SofaScoreClient()
    out = args.out

    print("standings…")
    standings = fetch_standings(client, args.tournament, args.season, out)
    write_csv(standings, out / "standings.csv")

    print("matches…")
    played = fetch_events(client, args.tournament, args.season, "last", out)
    upcoming = fetch_events(client, args.tournament, args.season, "next", out)
    matches = [flatten_event(e) for e in played + upcoming]
    write_csv(matches, out / "matches.csv")

    if not args.skip_details:
        finished = [e["id"] for e in played if e.get("status", {}).get("type") == "finished"]
        print(f"per-match details for {len(finished)} finished matches…")
        stats = fetch_match_details(client, finished, out)
        write_csv(stats, out / "match_stats.csv")

    print("done. Feed data/ to projections.py, or commit it and hand it back to Claude.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

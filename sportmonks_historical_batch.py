"""Discover and import bounded batches of *completed historical* Sportmonks fixtures.

This is a manual retrospective research importer, not a live match monitor.
Discovery uses league-filtered date ranges, then enriches at most ten new
completed fixtures using the existing verified single-fixture importer.
"""
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from sportmonks_historical_import import (
    DB_PATH, FINISHED_STATES, ensure_schema, get_fixture,
    store_finished_fixture,
)

BASE = "https://api.sportmonks.com/v3/football/fixtures"
MAX_WINDOW_DAYS = 14
MAX_PAGES = 5
MAX_FIXTURES = 10
MAX_PER_PAGE = 50
MIN_AGE_DAYS = 14
SUPPORTED_LEAGUES = {8: "English Premier League"}


def parse_config(environ=None, today=None):
    env = environ if environ is not None else os.environ
    today = today or datetime.now(timezone.utc).date()
    raw_start = env.get("HISTORY_START_DATE", "").strip()
    raw_end = env.get("HISTORY_END_DATE", "").strip()
    try:
        start = date.fromisoformat(raw_start)
        end = date.fromisoformat(raw_end)
    except ValueError:
        raise ValueError("Use dates in YYYY-MM-DD format.") from None

    if start > end:
        raise ValueError("Start date must not be later than end date.")
    days = (end - start).days + 1
    if not (1 <= days <= MAX_WINDOW_DAYS):
        raise ValueError(
            f"Limit each historical discovery run to 1-{MAX_WINDOW_DAYS} days."
        )
    if end > today - timedelta(days=MIN_AGE_DAYS):
        raise ValueError(
            f"Historical data must be at least {MIN_AGE_DAYS} days old."
        )
    raw_league = env.get("HISTORY_LEAGUE_ID", "8").strip()
    if not raw_league.isdecimal() or int(raw_league) not in SUPPORTED_LEAGUES:
        raise ValueError("Only verified Sportmonks league ID 8 is supported.")
    raw_limit = env.get("HISTORY_MAX_FIXTURES", "5").strip()
    if not raw_limit.isdecimal() or not 1 <= int(raw_limit) <= MAX_FIXTURES:
        raise ValueError(f"HISTORY_MAX_FIXTURES must be 1-{MAX_FIXTURES}.")
    refresh = env.get("HISTORY_REFRESH_EXISTING", "false").strip().lower()
    if refresh not in ("true", "false"):
        raise ValueError("HISTORY_REFRESH_EXISTING must be true or false.")
    return {
        "start": start,
        "end": end,
        "league_id": int(raw_league),
        "limit": int(raw_limit),
        "refresh_existing": refresh == "true",
    }


def discover_completed(session, token, config):
    """Return all qualifying fixture IDs within a strictly bounded window.

    Paginate using the API's has_more and current page. Fail closed if
    pagination metadata is inconsistent or a safety page limit is reached.
    Do not trust discovery alone for final completion: the per-ID importer
    rechecks state before storing anything.
    """
    start = config["start"].isoformat()
    end = config["end"].isoformat()
    endpoint = f"{BASE}/between/{start}/{end}"
    seen = {}
    for page in range(1, MAX_PAGES + 1):
        try:
            response = session.get(
                endpoint,
                headers={
                    "Authorization": token,
                    "Accept": "application/json",
                },
                params={
                    "filters": f"fixtureLeagues:{config['league_id']}",
                    "page": page,
                    "per_page": MAX_PER_PAGE,
                    "order": "asc",
                },
                timeout=45,
            )
        except requests.RequestException:
            raise RuntimeError(
                "Could not access Sportmonks discovery endpoint."
            ) from None
        if not response.ok:
            raise RuntimeError(
                f"Historical discovery failed with HTTP {response.status_code}. "
                "Check API permissions or rate limits; no tokens were logged."
            )
        try:
            body = response.json()
        except ValueError:
            raise RuntimeError("Sportmonks discovery returned invalid JSON.") from None
        if not isinstance(body, dict):
            raise RuntimeError(
                "Historical discovery returned an unexpected JSON root; "
                "a response object is required."
            )
        if body.get("error") or body.get("errors"):
            raise RuntimeError(
                "Historical discovery returned provider errors inside "
                "an HTTP-success response. Check subscription access."
            )
        data = body.get("data")
        pagination = body.get("pagination")
        if not isinstance(data, list):
            # Never mistake a malformed response or an error envelope
            # for an empty result from the league/date query.
            raise RuntimeError(
                "Incomplete discovery response: missing fixture data list. "
                "No historical coverage was established."
            )
        if pagination is None and page == 1 and not data:
            # Some API responses with no matching fixtures contain
            # {data: []} but omit pagination. This is safe only for
            # the FIRST page of an explicitly empty result: there are
            # no fixtures to paginate, and no results can be skipped.
            # This does NOT certify official-season coverage.
            print(
                f"Historical discovery {start} through {end}: "
                "explicit empty fixture list with no pagination; "
                "skipping this window."
            )
            return []
        if not isinstance(pagination, dict):
            raise RuntimeError(
                "Incomplete discovery response: nonempty fixture data "
                "without pagination; refusing to assume full coverage."
            )
        for item in data:
            if not isinstance(item, dict):
                continue
            fid = item.get("id")
            if (not isinstance(fid, int) or isinstance(fid, bool)
                    or item.get("state_id") not in FINISHED_STATES
                    or item.get("league_id") != config["league_id"]):
                continue
            timestamp = str(item.get("starting_at") or "")
            if timestamp[:10] < start or timestamp[:10] > end:
                continue
            seen[fid] = timestamp
        has_more = pagination.get("has_more")
        if not isinstance(has_more, bool):
            raise RuntimeError(
                "Discovery has no valid has_more flag; cannot establish coverage."
            )
        current_page = pagination.get("current_page")
        if current_page is not None and int(current_page) != page:
            raise RuntimeError("Unexpected historical discovery page sequence.")
        if not has_more:
            return [
                key for key, _ in sorted(
                    seen.items(), key=lambda pair: (pair[1], pair[0])
                )
            ]
        if page == MAX_PAGES:
            raise RuntimeError(
                "Discovery exceeds the page safety limit. "
                "Choose a shorter date window; no fixtures were imported."
            )
    return []  # unreachable with valid pagination


def already_imported(conn):
    return {
        int(row[0]) for row in conn.execute(
            "SELECT fixture_id FROM sportmonks_historical_fixtures"
        )
    }


def run_batch(session, token, conn, config):
    """Discover all pages first; import at most the selected historical sample."""
    ensure_schema(conn)
    discovered = discover_completed(session, token, config)
    existing = already_imported(conn)
    candidates = (
        discovered if config["refresh_existing"]
        else [fid for fid in discovered if fid not in existing]
    )
    chosen = candidates[:config["limit"]]
    print(f"Historical league: {SUPPORTED_LEAGUES[config['league_id']]}")
    print(f"Date window: {config['start']} through {config['end']}")
    print(f"Completed fixtures discovered: {len(discovered)}")
    print(f"Already stored from this date window: "
          f"{len(set(discovered) & existing)}")
    print(f"Selected for this import: {len(chosen)}")
    print(f"Remaining eligible after this batch: "
          f"{max(0, len(candidates) - len(chosen))}")
    imported = 0
    for fid in chosen:
        # get_fixture and store_finished_fixture were verified in the
        # existing single-ID workflow and guard against non-completed states.
        fixture = get_fixture(session, token, fid)
        if fixture.get("league_id") != config["league_id"]:
            raise RuntimeError(
                f"Fixture {fid} was not in the selected league; refusing import."
            )
        if fixture.get("state_id") not in FINISHED_STATES:
            print(f"Fixture {fid}: no longer completed; skipped.")
            continue
        stamp = str(fixture.get("starting_at") or "")[:10]
        if not (config["start"].isoformat() <= stamp <= config["end"].isoformat()):
            raise RuntimeError(
                f"Fixture {fid} was outside the requested historical window."
            )
        imported += int(store_finished_fixture(conn, fixture))
    print(f"Completed historical fixtures imported: {imported}")
    print("Source IDs remain Sportmonks IDs; no results-table joins were made.")
    return {
        "discovered": len(discovered),
        "selected": len(chosen),
        "imported": imported,
        "remaining": max(0, len(candidates) - len(chosen)),
    }


def main():
    token = os.environ.get("SPORTMONKS_API_TOKEN", "").strip()
    if not token:
        raise ValueError("Missing SPORTMONKS_API_TOKEN GitHub Actions secret.")
    config = parse_config()
    with requests.Session() as session:
        with sqlite3.connect(DB_PATH) as conn:
            outcome = run_batch(session, token, conn, config)
    if not outcome["discovered"]:
        print(
            "No completed historical fixtures were discovered for the selected "
            "dates and league. Try another past date window."
        )


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError, RuntimeError, requests.RequestException, sqlite3.Error
    ) as exc:
        sys.exit(str(exc))

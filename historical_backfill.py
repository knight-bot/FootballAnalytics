"""Resumable multi-window import of *completed* Premier League history.

Runs the existing, guarded 14-day Sportmonks importer in chronological
windows. Checkpoints only after each successful window. Re-running a
range skips stored IDs; an interrupted an interrupted window preserves previously committed fixtures.
No forecasts, live games, credentials in output, or provider ID joins.
"""
import json
import os
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from sportmonks_historical_batch import (
    MAX_FIXTURES, MAX_WINDOW_DAYS, MIN_AGE_DAYS, run_batch, already_imported,
)
from sportmonks_historical_import import DB_PATH

MAX_RANGE_DAYS = 84
MAX_PER_RUN = 30
STATUS_FILE = Path(__file__).resolve().parent / ".historical_backfill_status.json"


def parse_backfill_config(env=None, today=None):
    env = env if env is not None else os.environ
    today = today or datetime.now(timezone.utc).date()
    try:
        start = date.fromisoformat(env.get("BACKFILL_START_DATE", ""))
        end = date.fromisoformat(env.get("BACKFILL_END_DATE", ""))
    except (ValueError, TypeError):
        raise ValueError("Set BACKFILL_START_DATE and BACKFILL_END_DATE as YYYY-MM-DD.") from None
    days = (end - start).days + 1
    if not 1 <= days <= MAX_RANGE_DAYS:
        raise ValueError(f"Choose 1-{MAX_RANGE_DAYS} consecutive historical days.")
    if end > today - timedelta(days=MIN_AGE_DAYS):
        raise ValueError(
            f"Last selected day must be at least {MIN_AGE_DAYS} days old."
        )
    raw = str(env.get("BACKFILL_MAX_FIXTURES", "20"))
    if not raw.isdecimal() or not 1 <= int(raw) <= MAX_PER_RUN:
        raise ValueError(f"Choose 1-{MAX_PER_RUN} enrichment requests per run.")
    if str(env.get("BACKFILL_LEAGUE_ID", "8")) != "8":
        raise ValueError("Only validated historical Premier League ID 8 is supported.")
    return {"start": start, "end": end, "budget": int(raw), "league_id": 8}


def historical_windows(start, end):
    """Produce nonoverlapping chronological windows, each at most 14 days."""
    day = start
    while day <= end:
        stop = min(end, day + timedelta(days=MAX_WINDOW_DAYS - 1))
        yield day, stop
        day = stop + timedelta(days=1)


def has_fixture_table(conn):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='sportmonks_historical_fixtures'"
    ).fetchone() is not None


def run_backfill(session, token, conn, config):
    """Resume by stored IDs and preserve fixture-level atomic commits.

    The underlying importer commits after each valid fixture; if a later
    API call fails, count the persisted partial window and flag the job.
    The workflow pushes all saved fixtures before reporting failure.
    """
    summary = {
        "requested_start": config["start"].isoformat(),
        "requested_end": config["end"].isoformat(),
        "fixture_budget": config["budget"],
        "enrichment_requests": 0,
        "newly_imported": 0,
        "partial_saved_on_error": 0,
        "windows_completed": 0,
        "last_successful_window_end": None,
        "windows": [],
        "complete_requested_range": False,
        "has_error": False,
        "error": "",
    }
    remaining = config["budget"]
    for start, end in historical_windows(config["start"], config["end"]):
        if remaining == 0:
            break
        window_config = {
            "start": start, "end": end,
            "league_id": config["league_id"],
            "limit": min(MAX_FIXTURES, remaining),
            "refresh_existing": False,
        }
        before_ids = already_imported(conn) if has_fixture_table(conn) else set()
        try:
            result = run_batch(session, token, conn, window_config)
        except (ValueError, RuntimeError, requests.RequestException,
                sqlite3.Error) as exc:
            conn.rollback()  # only any unfinished fixture; earlier fixtures commit
            after_ids = already_imported(conn) if has_fixture_table(conn) else set()
            partially_saved = len(after_ids - before_ids)
            summary["newly_imported"] += partially_saved
            summary["partial_saved_on_error"] += partially_saved
            summary["has_error"] = True
            # Existing importer error messages deliberately avoid credentials.
            # Surface a safe HTTP status for rate-limit troubleshooting,
            # never arbitrary provider messages or API headers/tokens.
            http = re.search(r"HTTP (4[0-9]{2}|5[0-9]{2})", str(exc))
            reason = http.group(0) if http else type(exc).__name__
            summary["error"] = (
                f"Window {start.isoformat()} to {end.isoformat()}: "
                f"{reason}. Previous completed fixtures remain saved."
            )
            break
        conn.commit()  # durable checkpoint after this valid window
        used = result["selected"]
        remaining -= used
        summary["enrichment_requests"] += used
        summary["newly_imported"] += result["imported"]
        summary["windows_completed"] += 1
        summary["last_successful_window_end"] = end.isoformat()
        summary["windows"].append({
            "start": start.isoformat(), "end": end.isoformat(),
            **result,
        })
        if result["remaining"]:
            # Finish the earliest incomplete window on the next run.
            break
    expected = list(historical_windows(config["start"], config["end"]))
    summary["complete_requested_range"] = (
        not summary["has_error"]
        and len(summary["windows"]) == len(expected)
        and all(row["remaining"] == 0 for row in summary["windows"])
    )
    return summary


def backfill_markdown(summary):
    state = (
        "Error after checkpoint" if summary["has_error"]
        else "Range exhausted" if summary["complete_requested_range"]
        else "More fixtures / windows remain for a future manual run"
    )
    lines = [
        "## Historical Sportmonks Backfill",
        "",
        f"**Window:** {summary['requested_start']} to "
        f"{summary['requested_end']}",
        f"**Status:** {state}",
        f"**Fixture enrichment calls:** {summary['enrichment_requests']}",
        f"**Completed fixtures saved:** {summary['newly_imported']}",
        f"**Persisted before later API failure:** "
        f"{summary['partial_saved_on_error']}",
        f"**Windows successfully checkpointed:** {summary['windows_completed']}",
        "**Last successful date window ended:** "
        + str(summary["last_successful_window_end"] or "None"),
        "",
        "| Start | End | Discovered | New saved | Still eligible in window |",
        "|---|---|---:|---:|---:|",
    ]
    for row in summary["windows"]:
        lines.append(
            f"| {row['start']} | {row['end']} | {row['discovered']} | "
            f"{row['imported']} | {row['remaining']} |"
        )
    lines.extend([
        "",
        "Rerun the same dates to resume; already stored fixture IDs are "
        "skipped. Source associations are never automatically approved.",
        "These counts cover the provider's licensed discovery results, "
        "not an independently certified complete league schedule.",
    ])
    if summary["has_error"]:
        lines.append("**Import error:** " + summary["error"])
    return "\n".join(lines) + "\n"


def main():
    STATUS_FILE.unlink(missing_ok=True)
    token = os.environ.get("SPORTMONKS_API_TOKEN", "").strip()
    if not token:
        raise ValueError("Missing SPORTMONKS_API_TOKEN GitHub Actions secret.")
    config = parse_backfill_config()
    # A 429 may require a long quota reset; stop and checkpoint safely.
    # Never leave a CI job waiting for an unbounded Retry-After.
    retry = Retry(
        total=2, backoff_factor=1, status_forcelist=[500, 502, 503, 504],
        allowed_methods=frozenset({"GET"}), respect_retry_after_header=False,
    )
    with requests.Session() as session:
        session.mount("https://api.sportmonks.com/", HTTPAdapter(max_retries=retry))
        with sqlite3.connect(DB_PATH) as conn:
            result = run_backfill(session, token, conn, config)
    STATUS_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
    markdown = backfill_markdown(result)
    print(markdown)
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")
    # An error is reported after the workflow commits completed windows.
    # This script therefore returns 0 even for a partial failure, and
    # the workflow's final verify-status step raises the failure.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, sqlite3.Error) as exc:
        sys.exit(f"Historical backfill setup failed: {exc}")

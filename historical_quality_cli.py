"""Publish local Premier League source quality for an ended July-June window.

This is a read-only measurement of records stored in football.db,
NOT official schedule completeness and never an auto-approval action.
"""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from historical_season_quality import build_quality_report, QUALITY_ORDER
from historical_reports import season_label

DB_PATH = Path(__file__).resolve().parent / "football.db"


def last_ended_season_start(today):
    return today.year - 1 if today.month >= 7 else today.year - 2


def compact_quality_summary(report):
    lines = [
        "## Completed-Window Historical Source Coverage",
        "",
        f"**Competition:** {report['competition']}",
        f"**Date-derived season:** {report['season']}",
        f"**Locally stored finished results:** "
        f"{report['locally_recorded_results']}",
        f"**Reviewed source links:** "
        f"{report['grades']['A'] + report['grades']['B']}",
        f"**Reviewed games with complete standard xG:** {report['grades']['A']}",
        "",
        "| Evidence quality | Recorded matches |",
        "|---|---:|",
    ]
    lines.extend(
        f"| {grade} | {report['grades'][grade]} |"
        for grade in QUALITY_ORDER
    )
    lines.extend([
        "",
        "A: reviewed + complete xG; B: reviewed + incomplete xG; "
        "C: unreviewed candidate; D: source conflict, ambiguous or "
        "stale; U: no imported candidate.",
        "",
        "**Important:** These are records present in the local SQLite "
        "database, not a verified official league fixture count. "
        "No unreviewed xG is assigned to a result.",
    ])
    return "\n".join(lines) + "\n"


def main():
    today = datetime.now(timezone.utc).date()
    year = last_ended_season_start(today)
    if not DB_PATH.exists():
        raise FileNotFoundError("football.db is missing.")
    with sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True) as conn:
        report = build_quality_report(conn, "Premier League", year)
    md = compact_quality_summary(report)
    print(md)
    output = os.environ.get("GITHUB_STEP_SUMMARY")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(md + "\n")


if __name__ == "__main__":
    main()

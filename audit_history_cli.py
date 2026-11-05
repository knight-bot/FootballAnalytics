"""Print a small, read-only historical data quality report.

Can run from GitHub Actions without any API token.
"""
import os
import sqlite3
import sys
from pathlib import Path

from historical_audit import audit_database

DB_PATH = Path(__file__).resolve().parent / "football.db"


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError("football.db not found")
    with sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True) as conn:
        report = audit_database(conn)

    fixtures = report["sportmonks_fixtures"]
    flagged = [row for row in fixtures if row["issue_count"]]
    complete_xg = sum(
        row["standard_xg_home"] is not None
        and row["standard_xg_away"] is not None
        for row in fixtures
    )

    lines = [
        "# FootballAnalytics Historical Data Audit",
        "",
        f"- Completed football-data.org results: {report['results_count']}",
        f"- Invalid completed result records: {report['invalid_result_rows']}",
        f"- Imported Sportmonks historical fixtures: {len(fixtures)}",
        f"- Fixtures with standard home and away xG: {complete_xg}",
        f"- Sportmonks fixtures with audit findings: {len(flagged)}",
    ]
    for issue in report["checks"]:
        lines.append(f"- Notice: {issue}")
    for row in flagged[:20]:
        lines.append(
            f"- Fixture {row['fixture_id']}: {row['issues']}"
        )
    if len(flagged) > 20:
        lines.append(f"- ...and {len(flagged) - 20} additional flagged fixtures")

    summary = "\n".join(lines) + "\n"
    print(summary)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(summary)

    # A source coverage warning is diagnostic. A structurally invalid
    # completed result should be investigated before further research.
    if report["invalid_result_rows"]:
        print("Audit failed: invalid completed result records present.")
        return 1
    print("Read-only audit complete. Provider coverage is not guaranteed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

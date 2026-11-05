"""Read-only summary of recorded historical Premier League scoring trends.

Runs within the existing GitHub historical audit. Emits explicit sample
counts and never assumes an official season's results are complete.
No future fixtures, external API calls, odds or recommendations.
"""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from historical_reports import list_seasons
from historical_statistical_research import historical_season_comparison

DB_PATH = Path(__file__).resolve().parent / "football.db"


def build_scoring_summary(conn, competition="Premier League",
                          as_of_date=None):
    seasons = list_seasons(conn, competition)
    if not seasons:
        return (
            "## Recorded historical league scoring trends\n\n"
            f"No stored completed {competition} matches were found.\n"
        )
    latest = seasons[0]
    study = historical_season_comparison(
        conn, competition, latest, years=4, as_of_date=as_of_date
    )
    lines = [
        "## Recorded historical league scoring trends",
        "",
        f"**Competition:** {competition}",
        "**Source:** locally stored football-data.org FINISHED results",
        "",
        "| July-June window | Valid stored matches | Goals per match | "
        "Home goals/match | Away goals/match | "
        "Calendar interval finished? |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in study["by_season"]:
        def value(key):
            x = row[key]
            return f"{x:.3f}" if x is not None else "N/A"
        lines.append(
            f"| {row['season']} | {row['recorded_matches']} | "
            f"{value('goals_per_match')} | "
            f"{value('home_goals_per_match')} | "
            f"{value('away_goals_per_match')} | "
            f"{'Yes' if row['calendar_window_complete'] else 'No'} |"
        )
    lines.extend([
        "",
        "**Interpretation:** Counts and averages describe games present in "
        "this local database. A finished calendar window is not evidence "
        "that every official league fixture was imported. This is not a "
        "forecast or betting analysis.",
        "",
    ])
    return "\n".join(lines)


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError("football.db not found")
    with sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode=ro", uri=True
    ) as conn:
        md = build_scoring_summary(
            conn, as_of_date=datetime.now(timezone.utc).date()
        )
    print(md)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as file:
            file.write("\n" + md + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

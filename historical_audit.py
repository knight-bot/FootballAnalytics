"""Read-only, source-aware checks for historical football data.

No API access, no credentials, and no data modifications. Counts represent
records present in the local SQLite database, not provider-wide coverage.
"""
import sqlite3

TABLES = {
    "matches",
    "sportmonks_historical_fixtures",
    "sportmonks_historical_teams",
    "sportmonks_historical_metrics",
    "sportmonks_historical_statistics",
    "sportmonks_historical_pressure",
}


def table_exists(conn, table):
    if table not in TABLES:
        raise ValueError("Unexpected table")
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _fixture_counts(conn, table):
    if not table_exists(conn, table):
        return {}
    return {
        int(fixture_id): int(n)
        for fixture_id, n in conn.execute(
            f"SELECT fixture_id, COUNT(*) FROM {table} GROUP BY fixture_id"
        )
    }


def audit_database(conn):
    """Return an honest coverage overview of both *separate* data sources."""
    report = {
        "results_count": 0,
        "invalid_result_rows": 0,
        "competitions": [],
        "sportmonks_fixtures": [],
        "checks": [],
    }

    if table_exists(conn, "matches"):
        report["results_count"] = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE status = 'FINISHED'"
        ).fetchone()[0]
        report["invalid_result_rows"] = conn.execute("""
            SELECT COUNT(*) FROM matches
            WHERE status = 'FINISHED' AND (
                date IS NULL OR TRIM(date) = ''
                OR home_team IS NULL OR TRIM(home_team) = ''
                OR away_team IS NULL OR TRIM(away_team) = ''
                OR home_team = away_team
                OR home_goals IS NULL OR away_goals IS NULL
                OR home_goals < 0 OR away_goals < 0
            )
        """).fetchone()[0]
        report["competitions"] = [
            {
                "competition": name or "Unspecified",
                "completed_matches": count,
                "latest_match": latest,
            }
            for name, count, latest in conn.execute("""
                SELECT competition, COUNT(*), MAX(date)
                FROM matches
                WHERE status='FINISHED'
                GROUP BY competition
                ORDER BY COUNT(*) DESC, competition
            """)
        ]
        if report["invalid_result_rows"]:
            report["checks"].append(
                f"{report['invalid_result_rows']} completed result record(s) "
                "have missing or inconsistent values."
            )
    else:
        report["checks"].append("No football-data.org matches table found.")

    if not table_exists(conn, "sportmonks_historical_fixtures"):
        report["checks"].append(
            "No Sportmonks history table exists. Import a completed fixture first."
        )
        return report

    counts = {
        name: _fixture_counts(conn, name)
        for name in (
            "sportmonks_historical_teams",
            "sportmonks_historical_metrics",
            "sportmonks_historical_statistics",
            "sportmonks_historical_pressure",
        )
    }
    xg = {}
    if table_exists(conn, "sportmonks_historical_metrics"):
        for fixture_id, location, value in conn.execute("""
            SELECT fixture_id, location, value
            FROM sportmonks_historical_metrics
            WHERE type_id=5304 AND location IN ('home', 'away')
        """):
            xg.setdefault(int(fixture_id), {})[location] = value

    for (
        fixture_id, name, match_date, league_id, season_id,
        state_id, raw_stats, raw_pressure, raw_scores,
        raw_metrics, imported_at,
    ) in conn.execute("""
        SELECT fixture_id, name, match_date, league_id, season_id,
               state_id, stat_records, pressure_records, score_records,
               metric_records, imported_at
        FROM sportmonks_historical_fixtures
        ORDER BY match_date DESC, fixture_id DESC
    """):
        fixture_id = int(fixture_id)
        stats_saved = counts["sportmonks_historical_statistics"].get(
            fixture_id, 0
        )
        pressure_saved = counts["sportmonks_historical_pressure"].get(
            fixture_id, 0
        )
        metrics_saved = counts["sportmonks_historical_metrics"].get(
            fixture_id, 0
        )
        participants_saved = counts["sportmonks_historical_teams"].get(
            fixture_id, 0
        )
        home_xg = xg.get(fixture_id, {}).get("home")
        away_xg = xg.get(fixture_id, {}).get("away")
        issues = []
        if state_id not in {5, 7, 8}:
            issues.append("Unexpected historical match state")
        if not match_date:
            issues.append("Missing kickoff date")
        if participants_saved < 2:
            issues.append("Fewer than two team records")
        if home_xg is None or away_xg is None:
            issues.append("Standard xG not recorded for both sides")
        if raw_stats and not stats_saved:
            issues.append("Statistics returned but no numeric rows saved")
        elif stats_saved < raw_stats:
            issues.append("Some statistics were not numeric or not parsed")
        if raw_pressure and not pressure_saved:
            issues.append("Pressure returned but no minute values saved")
        elif pressure_saved < raw_pressure:
            issues.append("Some pressure records were not parsed")
        if metrics_saved < raw_metrics:
            issues.append("Expected-metric records differ from last import count")
        report["sportmonks_fixtures"].append({
            "fixture_id": fixture_id,
            "match": name or f"Fixture {fixture_id}",
            "match_date": match_date,
            "league_id": league_id,
            "season_id": season_id,
            "imported_at": imported_at,
            "participants_saved": participants_saved,
            "statistics_returned": raw_stats,
            "statistics_saved": stats_saved,
            "pressure_returned": raw_pressure,
            "pressure_saved": pressure_saved,
            "metrics_saved": metrics_saved,
            "standard_xg_home": home_xg,
            "standard_xg_away": away_xg,
            "issues": "; ".join(issues) if issues else "None detected",
            "issue_count": len(issues),
        })

    if not report["sportmonks_fixtures"]:
        report["checks"].append("No completed Sportmonks fixtures are stored.")
    elif len(report["sportmonks_fixtures"]) < 5:
        report["checks"].append(
            "Fewer than five Sportmonks fixtures are stored. "
            "This small sample cannot establish season-wide trends."
        )

    return report

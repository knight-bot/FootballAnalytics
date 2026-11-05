"""Deterministic reports from locally stored *completed* football matches.

No network calls, LLMs, predictions or joins between independent providers.
Each report states its source, time window, IDs and missing-data limitations.
"""
from datetime import date

from historical_audit import table_exists


def season_for_date(value):
    """European July–June date window, not the source's official season ID."""
    try:
        year, month = int(value[:4]), int(value[5:7])
    except (ValueError, TypeError, IndexError):
        return None
    if month < 1 or month > 12:
        return None
    return year if month >= 7 else year - 1


def season_label(start_year):
    return f"{start_year}/{str(start_year + 1)[-2:]}"


def list_competitions(conn):
    if not table_exists(conn, "matches"):
        return []
    return [
        row[0] for row in conn.execute(
            "SELECT DISTINCT competition FROM matches "
            "WHERE status='FINISHED' AND competition IS NOT NULL "
            "ORDER BY competition"
        ) if row[0]
    ]


def list_seasons(conn, competition):
    if not table_exists(conn, "matches"):
        return []
    dates = conn.execute(
        "SELECT DISTINCT substr(date, 1, 7) FROM matches "
        "WHERE status='FINISHED' AND competition=? AND date IS NOT NULL",
        (competition,),
    )
    return sorted(
        {season for (value,) in dates
         if (season := season_for_date(value)) is not None},
        reverse=True,
    )


def list_teams(conn, competition, start_year):
    if not table_exists(conn, "matches"):
        return []
    start, end = _bounds(start_year)
    rows = conn.execute(
        "SELECT home_team, away_team FROM matches "
        "WHERE status='FINISHED' AND competition=? "
        "AND date >= ? AND date < ?",
        (competition, start, end),
    )
    return sorted({
        team for home, away in rows
        for team in (home, away)
        if team and team.strip()
    })


def _bounds(start_year):
    if not isinstance(start_year, int) or not (1900 <= start_year <= 2200):
        raise ValueError("Invalid season starting year.")
    return f"{start_year}-07-01", f"{start_year+1}-07-01"


def _safe(value):
    return str(value).replace("|", r"\|").replace("\n", " ").strip()


def _score(team_goals, opponent_goals):
    return f"{team_goals}-{opponent_goals}"


def build_team_report(conn, competition, start_year, team):
    """Return source-referenced Markdown and summary of completed results."""
    if not table_exists(conn, "matches"):
        raise ValueError("No historical match results table exists.")
    start, end = _bounds(start_year)
    selected = list(conn.execute(
        "SELECT match_id, date, home_team, away_team, home_goals, away_goals "
        "FROM matches "
        "WHERE status='FINISHED' AND competition=? "
        "AND date >= ? AND date < ? "
        "AND (home_team=? OR away_team=?) "
        "ORDER BY date, match_id",
        (competition, start, end, team, team),
    ))
    games = []
    skipped = 0
    for match_id, kickoff, home, away, hg, ag in selected:
        if (not home or not away or home == away or hg is None
                or ag is None or hg < 0 or ag < 0):
            skipped += 1
            continue
        at_home = team == home
        gf, ga = (hg, ag) if at_home else (ag, hg)
        points = 3 if gf > ga else (1 if gf == ga else 0)
        games.append({
            "id": match_id,
            "date": kickoff[:10],
            "venue": "Home" if at_home else "Away",
            "opponent": away if at_home else home,
            "gf": int(gf),
            "ga": int(ga),
            "points": points,
        })

    if not games:
        return {
            "markdown": (
                f"# Historical team report: {_safe(team)}\n\n"
                "No valid completed results were stored for this selection. "
                "No statistics or conclusions were generated.\n"
            ),
            "summary": {"matches": 0, "excluded": skipped},
        }

    def group_stats(items):
        count = len(items)
        scored = sum(item["gf"] for item in items)
        conceded = sum(item["ga"] for item in items)
        points = sum(item["points"] for item in items)
        return {
            "played": count,
            "wins": sum(item["points"] == 3 for item in items),
            "draws": sum(item["points"] == 1 for item in items),
            "losses": sum(item["points"] == 0 for item in items),
            "gf": scored,
            "ga": conceded,
            "points": points,
            "goals_per_match": scored / count if count else None,
            "conceded_per_match": conceded / count if count else None,
        }

    whole = group_stats(games)
    home = group_stats([g for g in games if g["venue"] == "Home"])
    away = group_stats([g for g in games if g["venue"] == "Away"])
    recent = games[-5:]

    lines = [
        f"# Historical research: {_safe(team)}",
        "",
        f"**Competition:** {_safe(competition)}",
        f"**Date-derived season:** {season_label(start_year)} "
        f"(1 July {start_year} to 30 June {start_year+1})",
        "**Source:** locally stored football-data.org completed results",
        f"**Matches used:** {whole['played']}",
        f"**Incomplete results excluded:** {skipped}",
        "",
        "## Recorded season summary",
        "",
        f"- Results: {whole['wins']} wins, {whole['draws']} draws, "
        f"{whole['losses']} losses",
        f"- Goals scored: {whole['gf']}; goals conceded: {whole['ga']}",
        f"- Points calculated from recorded results: {whole['points']} "
        "(not an official standings total)",
        f"- Goals per recorded match: {whole['goals_per_match']:.2f}; "
        f"conceded per match: {whole['conceded_per_match']:.2f}",
        "",
        "## Home and away split",
        "",
        "| Venue | Played | W | D | L | Goals for | Goals against | Points |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for venue, values in (("Home", home), ("Away", away)):
        lines.append(
            f"| {venue} | {values['played']} | {values['wins']} | "
            f"{values['draws']} | {values['losses']} | {values['gf']} | "
            f"{values['ga']} | {values['points']} |"
        )
    lines.extend([
        "",
        "## Five most recent recorded results in this selection",
        "",
        "| Date (UTC) | Venue | Opponent | Team score | Points | Source match ID |",
        "|---|---|---|---:|---:|---:|",
    ])
    for game in reversed(recent):
        lines.append(
            f"| {_safe(game['date'])} | {game['venue']} | "
            f"{_safe(game['opponent'])} | "
            f"{_score(game['gf'], game['ga'])} | {game['points']} | "
            f"{game['id']} |"
        )
    lines.extend([
        "",
        "## Evidence and limitations",
        "",
        "- Every match ID above refers to the football-data.org dataset, "
        "not a Sportmonks fixture ID.",
        "- Season boundaries are inferred from dates and may differ from "
        "the competition's official season designation.",
        "- Summaries describe only recorded completed matches. Missing "
        "fixtures, point deductions and official standings are not reconstructed.",
        "- These observations are not a forecast of future results.",
        "",
    ])
    return {"markdown": "\n".join(lines), "summary": {**whole, "excluded": skipped}}


def list_sportmonks_fixtures(conn):
    if not table_exists(conn, "sportmonks_historical_fixtures"):
        return []
    return [
        {"id": int(fid), "name": name or f"Fixture {fid}", "date": dt or ""}
        for fid, name, dt in conn.execute(
            "SELECT fixture_id, name, match_date "
            "FROM sportmonks_historical_fixtures "
            "ORDER BY match_date DESC, fixture_id DESC"
        )
    ]


def build_sportmonks_report(conn, fixture_id):
    """Summarize only facts for a selected, imported completed fixture."""
    if not table_exists(conn, "sportmonks_historical_fixtures"):
        raise ValueError("No Sportmonks historical fixture table exists.")
    row = conn.execute(
        "SELECT name, match_date, league_id, season_id, state_id, "
        "stat_records, pressure_records, metric_records, imported_at "
        "FROM sportmonks_historical_fixtures WHERE fixture_id=?",
        (int(fixture_id),),
    ).fetchone()
    if row is None:
        raise ValueError("This Sportmonks fixture is not stored locally.")
    (name, kickoff, league_id, season_id, state_id, stat_records,
     pressure_records, metric_records, imported_at) = row
    if state_id not in {5, 7, 8}:
        raise ValueError("Stored fixture is not marked as completed.")

    sides = {"home": "Home team", "away": "Away team"}
    if table_exists(conn, "sportmonks_historical_teams"):
        for team_name, location in conn.execute(
            "SELECT name, location FROM sportmonks_historical_teams "
            "WHERE fixture_id=?", (int(fixture_id),),
        ):
            if location in sides and team_name:
                sides[location] = team_name

    metrics = {}
    if table_exists(conn, "sportmonks_historical_metrics"):
        for type_id, location, value in conn.execute(
            "SELECT type_id, location, value "
            "FROM sportmonks_historical_metrics "
            "WHERE fixture_id=? AND location IN ('home', 'away') "
            "AND type_id IN (5304, 5305, 7943, 9687)",
            (int(fixture_id),),
        ):
            metrics.setdefault((int(type_id), location), []).append(value)

    def value_for(type_id, side):
        values = metrics.get((type_id, side), [])
        return f"{values[0]:.2f}" if len(values) == 1 else "Not confirmed"

    stored_stats = stored_pressure = 0
    if table_exists(conn, "sportmonks_historical_statistics"):
        stored_stats = conn.execute(
            "SELECT COUNT(*) FROM sportmonks_historical_statistics "
            "WHERE fixture_id=?", (int(fixture_id),),
        ).fetchone()[0]
    if table_exists(conn, "sportmonks_historical_pressure"):
        stored_pressure = conn.execute(
            "SELECT COUNT(*) FROM sportmonks_historical_pressure "
            "WHERE fixture_id=?", (int(fixture_id),),
        ).fetchone()[0]

    lines = [
        f"# Historical fixture research: {_safe(name or fixture_id)}",
        "",
        f"**Source:** Sportmonks Football API v3, imported historical records",
        f"**Sportmonks fixture ID:** {int(fixture_id)}",
        f"**Kickoff (provider timestamp):** {_safe(kickoff)}",
        f"**League ID:** {_safe(league_id)}; "
        f"**Season ID:** {_safe(season_id)}",
        f"**Last imported:** {_safe(imported_at)}",
        "",
        "## Expected-goals-related measurements",
        "",
        f"| Metric | {_safe(sides['home'])} | {_safe(sides['away'])} |",
        "|---|---:|---:|",
    ]
    for type_id, label in (
        (5304, "Standard xG"),
        (5305, "Expected goals on target"),
        (7943, "Non-penalty xG"),
        (9687, "Expected goals against"),
    ):
        lines.append(
            f"| {label} (type {type_id}) | "
            f"{value_for(type_id, 'home')} | {value_for(type_id, 'away')} |"
        )

    lines.extend([
        "",
        "## Local data availability",
        "",
        "| Type | Returned at last import | Numeric records stored |",
        "|---|---:|---:|",
        f"| General statistics | {stat_records} | {stored_stats} |",
        f"| Pressure Index | {pressure_records} | {stored_pressure} |",
        f"| xG-related metrics | {metric_records} | "
        f"{sum(len(values) for values in metrics.values())} "
        "(shown metric types only) |",
        "",
        "## Evidence and limitations",
        "",
        "- Missing measurements are not zero; unconfirmed or duplicate "
        "side/type records are explicitly marked.",
        "- Pressure Index represents attacking momentum, not a count "
        "of defensive pressing actions.",
        "- This fixture has not been automatically matched to any "
        "football-data.org match ID.",
        "- This report summarizes past match data. It is not a "
        "pre-match projection or prediction.",
        "",
    ])
    return {
        "markdown": "\n".join(lines),
        "summary": {
            "fixture_id": int(fixture_id),
            "statistics_stored": stored_stats,
            "pressure_stored": stored_pressure,
        },
    }

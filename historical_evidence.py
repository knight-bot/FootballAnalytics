"""Small, source-referenced evidence packs from completed historical data.

No network calls or cross-provider record matching. Every evidence item is
tied to source IDs and a known database query, with missing values labelled.
"""
from historical_audit import table_exists
from historical_reports import _bounds, season_label


def _summary(games):
    n = len(games)
    if not n:
        return None
    return {
        "matches": n,
        "wins": sum(g["points"] == 3 for g in games),
        "draws": sum(g["points"] == 1 for g in games),
        "losses": sum(g["points"] == 0 for g in games),
        "goals_for": sum(g["gf"] for g in games),
        "goals_against": sum(g["ga"] for g in games),
        "points": sum(g["points"] for g in games),
    }


def team_evidence(conn, competition, start_year, team):
    """Evidence for one recorded team/competition/date-derived season."""
    start, end = _bounds(start_year)
    if not table_exists(conn, "matches"):
        return {"title": "No results database", "source": "football-data.org",
                "evidence": [], "limitations": ["No matches table exists."]}

    rows = list(conn.execute("""
        SELECT match_id, date, home_team, away_team, home_goals, away_goals
        FROM matches
        WHERE status='FINISHED' AND competition=?
          AND date >= ? AND date < ?
          AND (home_team=? OR away_team=?)
        ORDER BY date, match_id
    """, (competition, start, end, team, team)))
    games = []
    rejected_ids = []
    for match_id, kickoff, home, away, home_goals, away_goals in rows:
        if (not home or not away or home == away or
                home_goals is None or away_goals is None or
                home_goals < 0 or away_goals < 0 or not kickoff):
            rejected_ids.append(match_id)
            continue
        at_home = home == team
        gf = int(home_goals if at_home else away_goals)
        ga = int(away_goals if at_home else home_goals)
        games.append({
            "id": int(match_id), "date": kickoff[:10],
            "venue": "home" if at_home else "away",
            "opponent": away if at_home else home,
            "gf": gf, "ga": ga,
            "points": 3 if gf > ga else (1 if gf == ga else 0),
        })

    evidence = []
    def add(identifier, title, fact, selected):
        if selected:
            evidence.append({
                "id": identifier,
                "title": title,
                "fact": fact,
                "source": "football-data.org",
                "match_ids": [g["id"] for g in selected],
            })

    for identifier, label, selection in (
        ("FD_OVERALL", "All recorded results", games),
        ("FD_HOME", "Recorded home results",
         [g for g in games if g["venue"] == "home"]),
        ("FD_AWAY", "Recorded away results",
         [g for g in games if g["venue"] == "away"]),
    ):
        stats = _summary(selection)
        if stats:
            fact = (
                f"{stats['matches']} completed matches: {stats['wins']} wins, "
                f"{stats['draws']} draws, {stats['losses']} losses; "
                f"{stats['goals_for']} goals scored, "
                f"{stats['goals_against']} conceded; "
                f"{stats['points']} points calculated from results."
            )
            add(identifier, label, fact, selection)

    recent = games[-5:]
    if recent:
        recent_description = "; ".join(
            f"{g['date']} {g['venue']} vs {g['opponent']}, "
            f"score {g['gf']}-{g['ga']}"
            for g in recent
        )
        add("FD_RECENT", "Last five recorded results (or fewer)",
            recent_description, recent)

    limitations = [
        "Historical observations only; these are not forecasts.",
        "The July-June season is grouped by date, not an official season ID.",
        "Only stored completed results are included; official standings "
        "and point deductions are not reconstructed.",
        "Football-data.org match IDs are not Sportmonks fixture IDs.",
    ]
    if rejected_ids:
        limitations.append(
            f"{len(rejected_ids)} incomplete or inconsistent "
            "completed-result rows were excluded."
        )
    if len(games) < 5:
        limitations.append(
            "Fewer than five valid matches are available for this selection."
        )

    return {
        "title": f"{team} | {competition} | {season_label(start_year)}",
        "source": "football-data.org",
        "selection": {
            "competition": competition, "season_start": start_year,
            "team": team, "match_count": len(games),
        },
        "evidence": evidence,
        "limitations": limitations,
    }


def sportmonks_evidence(conn, fixture_id):
    """Evidence for one imported finished fixture, without guessing scores."""
    if not table_exists(conn, "sportmonks_historical_fixtures"):
        raise ValueError("No Sportmonks historical fixtures are stored.")
    fixture_id = int(fixture_id)
    row = conn.execute("""
        SELECT name, match_date, state_id, stat_records, pressure_records,
               metric_records, imported_at
        FROM sportmonks_historical_fixtures WHERE fixture_id=?
    """, (fixture_id,)).fetchone()
    if row is None:
        raise ValueError("Fixture ID is not in the local historical database.")
    name, kickoff, state, raw_stats, raw_pressure, raw_metrics, imported = row
    if state not in {5, 7, 8}:
        raise ValueError("This fixture is not marked completed.")

    evidence = [{
        "id": "SM_FIXTURE", "title": "Completed historical fixture",
        "fact": f"{name}, kickoff {kickoff}, imported {imported}. "
                f"Sportmonks fixture ID {fixture_id}.",
        "source": "Sportmonks Football API v3",
        "fixture_id": fixture_id,
    }]
    names = {}
    if table_exists(conn, "sportmonks_historical_teams"):
        for team, location in conn.execute(
            "SELECT name, location FROM sportmonks_historical_teams "
            "WHERE fixture_id=?", (fixture_id,),
        ):
            if location in ("home", "away") and team:
                names[location] = team
    metrics = {}
    if table_exists(conn, "sportmonks_historical_metrics"):
        for typ, side, value in conn.execute(
            "SELECT type_id, location, value "
            "FROM sportmonks_historical_metrics WHERE fixture_id=? "
            "AND type_id IN (5304, 5305, 7943, 9687) "
            "AND location IN ('home', 'away')",
            (fixture_id,),
        ):
            metrics.setdefault((typ, side), []).append(value)

    for typ, label in (
        (5304, "Standard expected goals (xG)"),
        (5305, "Expected goals on target (xGoT)"),
        (7943, "Non-penalty xG"),
        (9687, "Expected goals against (xGA)"),
    ):
        for side in ("home", "away"):
            values = metrics.get((typ, side), [])
            if len(values) != 1 or values[0] is None:
                continue
            evidence.append({
                "id": f"SM_{typ}_{side.upper()}",
                "title": f"{label}: {names.get(side, side.title())}",
                "fact": f"{names.get(side, side.title())} recorded "
                        f"{float(values[0]):.2f} for {label} in this "
                        "completed fixture.",
                "source": "Sportmonks Football API v3",
                "fixture_id": fixture_id, "metric_type_id": typ,
            })

    saved_stats = 0
    saved_pressure = 0
    if table_exists(conn, "sportmonks_historical_statistics"):
        saved_stats = conn.execute(
            "SELECT COUNT(*) FROM sportmonks_historical_statistics "
            "WHERE fixture_id=?", (fixture_id,),
        ).fetchone()[0]
    if table_exists(conn, "sportmonks_historical_pressure"):
        saved_pressure = conn.execute(
            "SELECT COUNT(*) FROM sportmonks_historical_pressure "
            "WHERE fixture_id=?", (fixture_id,),
        ).fetchone()[0]

    evidence.append({
        "id": "SM_COVERAGE", "title": "Records saved locally",
        "fact": f"Last import returned {raw_stats} statistics entries, "
                f"{raw_pressure} pressure entries and {raw_metrics} "
                f"expected-metric entries. Locally stored: {saved_stats} "
                f"numeric statistics and {saved_pressure} minute pressure "
                "values. These are record counts, not event counts.",
        "source": "Sportmonks Football API v3",
        "fixture_id": fixture_id,
    })
    limitations = [
        "Retrospective fixture data, not a pre-match forecast.",
        "Missing statistical metrics are not equivalent to zero.",
        "The Pressure Index reflects attacking momentum, not "
        "the count of defensive pressing actions.",
        "Stored numeric counts may be smaller than returned record counts "
        "because some API values are nonnumeric or unsupported.",
        "No automatic joining with football-data.org IDs is performed.",
    ]
    if not any(e["id"].startswith("SM_5304_") for e in evidence):
        limitations.append("Standard xG is missing for at least one side.")

    return {
        "title": name or f"Historical fixture {fixture_id}",
        "source": "Sportmonks Football API v3",
        "selection": {"fixture_id": fixture_id},
        "evidence": evidence,
        "limitations": limitations,
    }


def offline_review(pack):
    """A transparent, no-fee fallback that never invents conclusions."""
    if not pack["evidence"]:
        return {
            "observations": [],
            "limitations": pack["limitations"],
        }
    return {
        "observations": [
            {
                "text": entry["fact"],
                "evidence_ids": [entry["id"]],
            }
            for entry in pack["evidence"]
        ],
        "limitations": pack["limitations"],
    }

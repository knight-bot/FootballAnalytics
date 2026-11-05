"""Read-only coverage and descriptive historical xG vs goals analysis.

Only the stored Sportmonks STANDARD xG (type_id 5304) is used.
Goal-versus-xG comparisons require a currently valid, operator-reviewed
one-to-one link to completed football-data.org match results. The app
does not itself independently verify the Sportmonks final score.
No API calls, scores for future fixtures, or odds/wager functionality.
"""
from math import isfinite
from historical_audit import table_exists
from historical_fixture_linkage import candidate_links
from historical_reports import _bounds, season_label
from historical_team_strength import _valid_result

STANDARD_XG_TYPE = 5304
SM_TABLE = "sportmonks_historical_fixtures"
METRIC_TABLE = "sportmonks_historical_metrics"
TEAM_TABLE = "sportmonks_historical_teams"


def _exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _standard_xg_by_fixture(conn):
    """Return exactly one valid xG value per side; duplicates are ambiguous."""
    if not _exists(conn, METRIC_TABLE):
        return {}
    teams = {}
    if _exists(conn, TEAM_TABLE):
        for fid, pid, location in conn.execute(
            f"SELECT fixture_id, participant_id, location FROM {TEAM_TABLE}"
        ):
            if location in ("home", "away"):
                teams.setdefault((int(fid), location), []).append(int(pid))
    values = {}
    for fid, location, pid, value in conn.execute(
        f"SELECT fixture_id, location, participant_id, value "
        f"FROM {METRIC_TABLE} WHERE type_id=?",
        (STANDARD_XG_TYPE,),
    ):
        if location not in ("home", "away"):
            continue
        key = (int(fid), location)
        valid_pids = teams.get(key, [])
        # Require a unique known participant for this fixture and side.
        if len(valid_pids) != 1 or int(pid) != valid_pids[0]:
            values.setdefault(key, []).append(None)
        elif isinstance(value, (int, float)) and isfinite(value) and value >= 0:
            values.setdefault(key, []).append(float(value))
        else:
            values.setdefault(key, []).append(None)
    fixture_ids = {
        fid for fid, _ in values
    } | {fid for fid, _ in teams}
    out = {}
    for fid in fixture_ids:
        paired = {}
        for side in ("home", "away"):
            found = values.get((fid, side), [])
            paired[side] = found[0] if len(found) == 1 else None
        out[fid] = paired
    return out


def imported_xg_coverage(conn):
    """Coverage *within locally imported Sportmonks fixtures*, not league-wide."""
    if not _exists(conn, SM_TABLE):
        return {
            "imported": 0, "complete_both_sides": 0,
            "partial_one_side": 0, "missing_both_sides": 0,
            "rows": [],
        }
    xg = _standard_xg_by_fixture(conn)
    rows = []
    for fid, name, kickoff, league_id, state_id in conn.execute(
        f"SELECT fixture_id, name, match_date, league_id, state_id "
        f"FROM {SM_TABLE} ORDER BY match_date, fixture_id"
    ):
        fixture = xg.get(int(fid), {})
        home, away = fixture.get("home"), fixture.get("away")
        sides = int(home is not None) + int(away is not None)
        rows.append({
            "sportmonks_id": int(fid),
            "fixture": name or f"Fixture {fid}",
            "kickoff": kickoff or "",
            "league_id": league_id,
            "completed_state": state_id in (5, 7, 8),
            "home_xg": home,
            "away_xg": away,
            "xg_coverage": (
                "Both sides" if sides == 2
                else "One side only" if sides == 1
                else "Neither side"
            ),
        })
    return {
        "imported": len(rows),
        "complete_both_sides": sum(
            row["xg_coverage"] == "Both sides" for row in rows
        ),
        "partial_one_side": sum(
            row["xg_coverage"] == "One side only" for row in rows
        ),
        "missing_both_sides": sum(
            row["xg_coverage"] == "Neither side" for row in rows
        ),
        "rows": rows,
    }


def analyze_team_xg(conn, competition, season_start, team):
    """Retrospective goal-minus-xG for reviewed historical matches only."""
    if not isinstance(competition, str) or not competition.strip():
        raise ValueError("A competition is required.")
    if not isinstance(team, str) or not team.strip():
        raise ValueError("A team is required.")
    if not table_exists(conn, "matches"):
        raise ValueError("No completed match-results table exists.")
    start, end = _bounds(season_start)
    completed = conn.execute(
        "SELECT match_id, date, home_team, away_team, home_goals, away_goals "
        "FROM matches WHERE status='FINISHED' AND competition=? "
        "AND date>=? AND date<? AND (home_team=? OR away_team=?) "
        "ORDER BY date, match_id",
        (competition, start, end, team, team),
    ).fetchall()
    eligible = {
        int(row[0]): row for row in completed if _valid_result(row)
    }
    links = {
        row["match_id"]: row for row in candidate_links(conn)
        if row["status"] == "reviewed"
        and row["match_id"] in eligible
    }
    xg_by_fixture = _standard_xg_by_fixture(conn)
    pairs = []
    unavailable = []
    for match_id, result in eligible.items():
        link = links.get(match_id)
        if not link:
            continue
        sid = link["sportmonks_id"]
        metrics = xg_by_fixture.get(sid, {})
        hxg, axg = metrics.get("home"), metrics.get("away")
        if hxg is None or axg is None:
            unavailable.append({
                "match_id": match_id,
                "sportmonks_id": sid,
                "reason": (
                    "Standard xG type 5304 is missing, invalid, has "
                    "a mismatched participant ID, or is ambiguous "
                    "for at least one side."
                ),
            })
            continue
        _, kickoff, home, away, hg, ag = result
        is_home = home == team
        gf = hg if is_home else ag
        ga = ag if is_home else hg
        xgf, xga = (hxg, axg) if is_home else (axg, hxg)
        pairs.append({
            "match_id": match_id,
            "sportmonks_id": sid,
            "date": kickoff[:10],
            "venue": "Home" if is_home else "Away",
            "opponent": away if is_home else home,
            "goals_for": gf,
            "goals_against": ga,
            "xg_for": xgf,
            "xg_against": xga,
            "goals_minus_xg": gf - xgf,
            "conceded_minus_xga": ga - xga,
            "goal_difference": gf - ga,
            "xg_difference": xgf - xga,
        })
    total_xgf = sum(row["xg_for"] for row in pairs)
    total_xga = sum(row["xg_against"] for row in pairs)
    total_gf = sum(row["goals_for"] for row in pairs)
    total_ga = sum(row["goals_against"] for row in pairs)
    stored = imported_xg_coverage(conn)
    warnings = [
        "Sportmonks final scores are NOT stored locally. Reviewed links "
        "depend on manual operator attestation of source-score agreement.",
        "All comparisons use completed, currently valid reviewed links; "
        "candidate or stale links are excluded.",
        "Missing, duplicate, negative or mismatched-participant standard "
        "xG is excluded; missing is not zero.",
        "This is observed goal-minus-xG for a selected historical "
        "sample, not a forecast, statistical calibration, or proof "
        "of finishing ability.",
        "Selected reviewed fixtures can be nonrepresentative. "
        "No league-wide xG coverage is assumed.",
    ]
    if len(pairs) < 5:
        warnings.append(
            "Fewer than five eligible linked matches with complete "
            "standard xG: numerical aggregates are especially unstable."
        )
    if unavailable:
        warnings.append(
            f"{len(unavailable)} reviewed matches lack unambiguous "
            "two-sided standard xG and are excluded from comparisons."
        )
    return {
        "team": team,
        "competition": competition,
        "season": season_label(season_start),
        "recorded_completed": len(completed),
        "valid_completed": len(eligible),
        "invalid_completed": len(completed) - len(eligible),
        "reviewed_links": len(links),
        "xg_complete_links": len(pairs),
        "reviewed_missing_xg": len(unavailable),
        "unreviewed_or_stale": len(eligible) - len(links),
        "imported_sportmonks_coverage": {
            key: stored[key] for key in (
                "imported", "complete_both_sides",
                "partial_one_side", "missing_both_sides"
            )
        },
        "total_goals_for": total_gf if pairs else None,
        "total_goals_against": total_ga if pairs else None,
        "total_xg_for": total_xgf if pairs else None,
        "total_xg_against": total_xga if pairs else None,
        "goals_minus_xg": (total_gf - total_xgf) if pairs else None,
        "conceded_minus_xga": (total_ga - total_xga) if pairs else None,
        "match_rows": pairs,
        "excluded_reviewed_rows": unavailable,
        "warnings": warnings,
    }


def team_xg_markdown(report):
    """Source-ID-backed, bounded historical xG section for research export."""
    def val(x):
        return "Unavailable" if x is None else f"{x:.2f}"
    lines = [
        "## Historical standard xG versus recorded goals",
        "",
        f"**Team:** {report['team']}",
        f"**Competition:** {report['competition']}",
        f"**July–June season:** {report['season']}",
        f"**Valid stored completed results:** {report['valid_completed']}",
        f"**Currently reviewed historical links:** {report['reviewed_links']}",
        f"**Reviewed matches with standard xG for BOTH teams:** "
        f"{report['xg_complete_links']}",
        f"**Reviewed matches excluded for incomplete/ambiguous standard xG:** "
        f"{report['reviewed_missing_xg']}",
        f"**Recorded team matches without a currently reviewed link:** "
        f"{report['unreviewed_or_stale']}",
        "",
        "| Statistic | Recorded value for matched sample |",
        "|---|---:|",
        f"| Goals scored | {val(report['total_goals_for'])} |",
        f"| Standard xG for | {val(report['total_xg_for'])} |",
        f"| Goals minus xG | {val(report['goals_minus_xg'])} |",
        f"| Goals conceded | {val(report['total_goals_against'])} |",
        f"| Standard xG against | {val(report['total_xg_against'])} |",
        f"| Conceded minus xGA | {val(report['conceded_minus_xga'])} |",
        "",
    ]
    if report["match_rows"]:
        lines.extend([
            "| Date | Opponent | Venue | GF-GA | xG for | xG against | "
            "football-data.org ID | Sportmonks ID |",
            "|---|---|---|---|---:|---:|---:|---:|",
        ])
        for row in report["match_rows"]:
            opponent = row["opponent"].replace("|", "/").replace("\n", " ")
            lines.append(
                f"| {row['date']} | {opponent} | {row['venue']} | "
                f"{row['goals_for']}-{row['goals_against']} | "
                f"{row['xg_for']:.2f} | {row['xg_against']:.2f} | "
                f"{row['match_id']} | {row['sportmonks_id']} |"
            )
        lines.append("")
    else:
        lines.extend([
            "No completed, currently reviewed match has complete "
            "two-sided standard xG in this selection. "
            "**No goal-minus-xG aggregate has been calculated.**",
            "",
        ])
    lines.append("### Interpretive limits")
    lines.append("")
    lines.extend(f"- {item}" for item in report["warnings"])
    lines.append("")
    return "\n".join(lines)

"""Historical team-strength indicators from locally stored completed results.

Descriptive, retrospective league-normalized goal statistics only. No API
calls, future fixtures, betting recommendations, or unverified provider joins.
The shrunk indices are regularized historical observations, NOT calibrated
probabilities, validated skill estimates, or predictions.
"""
from collections import defaultdict
from datetime import date
import math

from historical_audit import table_exists
from historical_reports import _bounds, season_label

DEFAULT_PRIOR_MATCHES = 5
MIN_RELIABLE_SAMPLE = 5


def _valid_result(row):
    match_id, kickoff, home, away, hg, ag = row
    if (not isinstance(kickoff, str) or
            not isinstance(home, str) or not home.strip() or
            not isinstance(away, str) or not away.strip() or
            home.strip() == away.strip() or
            not isinstance(hg, int) or isinstance(hg, bool) or
            not isinstance(ag, int) or isinstance(ag, bool) or
            hg < 0 or ag < 0):
        return False
    try:
        date.fromisoformat(kickoff[:10])
    except (ValueError, TypeError):
        return False
    return True


def _ratio(total, n, baseline, pseudo_matches):
    """Return raw and baseline-shrunk indices, or None if undefined."""
    if not n or baseline <= 0:
        return None, None
    raw = (total / n) / baseline
    smoothed = (total + pseudo_matches * baseline) / (
        (n + pseudo_matches) * baseline
    )
    return raw, smoothed


def _scope(matches, team, kind, attack_baseline, defense_baseline, prior):
    games = []
    for game in matches:
        is_home = game["home"] == team
        is_away = game["away"] == team
        if not (is_home or is_away):
            continue
        if kind == "home" and not is_home:
            continue
        if kind == "away" and not is_away:
            continue
        gf, ga = (
            (game["hg"], game["ag"]) if is_home
            else (game["ag"], game["hg"])
        )
        games.append((game["id"], gf, ga))
    played = len(games)
    gf = sum(item[1] for item in games)
    ga = sum(item[2] for item in games)
    attack, attack_shrunk = _ratio(
        gf, played, attack_baseline, prior
    )
    defense, defense_shrunk = _ratio(
        ga, played, defense_baseline, prior
    )
    return {
        "played": played,
        "wins": sum(a > b for _, a, b in games),
        "draws": sum(a == b for _, a, b in games),
        "losses": sum(a < b for _, a, b in games),
        "goals_for": gf,
        "goals_against": ga,
        "goals_for_per_match": gf / played if played else None,
        "goals_against_per_match": ga / played if played else None,
        "points": sum(3 if a > b else (1 if a == b else 0)
                      for _, a, b in games),
        "attack_index": attack,
        "attack_shrunk": attack_shrunk,
        "defense_index": defense,
        "defense_shrunk": defense_shrunk,
        "attack_baseline": (
            attack_baseline if attack_baseline > 0 else None
        ),
        "defense_baseline": (
            defense_baseline if defense_baseline > 0 else None
        ),
        "match_ids": [item[0] for item in games],
        "sample_flag": (
            "No recorded games" if not played
            else "Small sample" if played < MIN_RELIABLE_SAMPLE
            else "Recorded sample only"
        ),
    }


def analyze_season(conn, competition, season_start, prior_matches=DEFAULT_PRIOR_MATCHES):
    """Compute historical per-team attack/defense indices within one season.

    Season is the existing app's July-to-June date window.
    Home attack/defense are compared against the observed league home-goal
    and away-goal per-match rates. Away indices reverse these baselines.
    All comparisons use ONLY eligible completed results in this same window.
    """
    if not table_exists(conn, "matches"):
        raise ValueError("The historical matches table is not available.")
    if not isinstance(competition, str) or not competition.strip():
        raise ValueError("Select a recorded competition.")
    if (isinstance(prior_matches, bool)
            or not isinstance(prior_matches, (int, float))
            or not math.isfinite(prior_matches)
            or prior_matches < 0 or prior_matches > 20):
        raise ValueError("Prior matches must be a finite number from 0 to 20.")
    start, end = _bounds(season_start)
    rows = conn.execute(
        "SELECT match_id, date, home_team, away_team, "
        "home_goals, away_goals FROM matches "
        "WHERE status='FINISHED' AND competition=? "
        "AND date>=? AND date<? ORDER BY date, match_id",
        (competition, start, end),
    ).fetchall()
    games = []
    invalid_ids = []
    for row in rows:
        if not _valid_result(row):
            invalid_ids.append(row[0])
            continue
        mid, kickoff, home, away, hg, ag = row
        games.append({
            "id": int(mid), "date": kickoff[:10],
            "home": home.strip(), "away": away.strip(),
            "hg": int(hg), "ag": int(ag),
        })
    n = len(games)
    home_goals = sum(game["hg"] for game in games)
    away_goals = sum(game["ag"] for game in games)
    home_rate = home_goals / n if n else 0.0
    away_rate = away_goals / n if n else 0.0
    overall_rate = (home_goals + away_goals) / (2 * n) if n else 0.0
    names = sorted({
        name for game in games for name in (game["home"], game["away"])
    })
    teams = []
    for name in names:
        scopes = {
            "overall": _scope(
                games, name, "overall",
                overall_rate, overall_rate, prior_matches,
            ),
            "home": _scope(
                games, name, "home",
                home_rate, away_rate, prior_matches,
            ),
            "away": _scope(
                games, name, "away",
                away_rate, home_rate, prior_matches,
            ),
        }
        teams.append({"name": name, "scopes": scopes})
    flags = []
    if not n:
        flags.append("No valid completed results exist for this selection.")
    if invalid_ids:
        flags.append(
            f"{len(invalid_ids)} completed result rows were excluded "
            "because a required value was invalid."
        )
    if n and (home_rate == 0 or away_rate == 0 or overall_rate == 0):
        flags.append(
            "At least one observed league goal-rate baseline is zero. "
            "Indices using a zero baseline are undefined, not zero."
        )
    if n and n < 30:
        flags.append(
            "Fewer than 30 completed league matches are recorded. "
            "The reference baselines are especially sample-sensitive."
        )
    flags.append(
        "These are descriptive within-sample ratios, not forecasting "
        "probabilities or demonstrated predictive performance."
    )
    flags.append(
        "The historical data may be incomplete or uneven by team; "
        "opponent strength, injuries and schedule differences are "
        "not controlled."
    )
    return {
        "competition": competition,
        "season_start": season_start,
        "season": season_label(season_start),
        "source": "football-data.org (locally stored completed results)",
        "matches": n,
        "excluded": len(invalid_ids),
        "excluded_match_ids": invalid_ids,
        "match_ids": [game["id"] for game in games],
        "date_first": games[0]["date"] if games else None,
        "date_last": games[-1]["date"] if games else None,
        "prior_matches": prior_matches,
        "league_home_goals_per_match": home_rate if n else None,
        "league_away_goals_per_match": away_rate if n else None,
        "league_goals_per_team_match": overall_rate if n else None,
        "teams": teams,
        "warnings": flags,
    }


def team_strength(analysis, name):
    return next(
        (entry for entry in analysis["teams"] if entry["name"] == name),
        None,
    )


def strength_markdown(analysis, team):
    """Compact source-attributed analysis section for manual ChatGPT upload."""
    record = team_strength(analysis, team)
    if record is None:
        return (
            "## Historical league-adjusted team-strength indicators\n\n"
            "No valid recorded matches for this team in this window.\n"
        )
    def f(value):
        return "Undefined" if value is None else f"{value:.3f}"
    lines = [
        "## Historical league-adjusted team-strength indicators",
        "",
        f"**Team:** {team}",
        f"**Source:** {analysis['source']}",
        f"**Season window:** {analysis['season']} (July–June)",
        f"**Valid recorded league fixtures:** {analysis['matches']}",
        f"**Excluded recorded rows:** {analysis['excluded']}",
        f"**League home goals/match:** "
        f"{f(analysis['league_home_goals_per_match'])}",
        f"**League away goals/match:** "
        f"{f(analysis['league_away_goals_per_match'])}",
        f"**League goals per team-match:** "
        f"{f(analysis['league_goals_per_team_match'])}",
        f"**Prior strength:** {analysis['prior_matches']} baseline-equivalent "
        "matches (stabilization, not statistical validation)",
        "",
        "| Venue | Matches | GF | GA | Attack raw | Attack shrunk | "
        "Defense raw | Defense shrunk |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, label in (
        ("overall", "All"), ("home", "Home"), ("away", "Away")
    ):
        scope = record["scopes"][key]
        lines.append(
            f"| {label} | {scope['played']} | {scope['goals_for']} | "
            f"{scope['goals_against']} | {f(scope['attack_index'])} | "
            f"{f(scope['attack_shrunk'])} | {f(scope['defense_index'])} | "
            f"{f(scope['defense_shrunk'])} |"
        )
    lines.extend([
        "",
        "An attack index over 1 means more recorded goals scored per match "
        "than the relevant league baseline. A defense index below 1 "
        "means fewer goals conceded per match than that baseline. "
        "Smoothed indices shrink toward 1 using the listed number of "
        "baseline-equivalent matches. These are **not predictions**.",
        "",
        "### Match-level provenance for these calculations",
        "",
        "football-data.org match IDs: "
        + (", ".join(str(mid)
                     for mid in record["scopes"]["overall"]["match_ids"])
           or "None"),
        "",
        "### Analytical warnings",
        "",
    ])
    if any(
        s["played"] < MIN_RELIABLE_SAMPLE
        for s in record["scopes"].values()
    ):
        lines.append(
            "- At least one home/away sample has fewer than five matches; "
            "interpret venue-specific indices cautiously."
        )
    lines.extend(f"- {warning}" for warning in analysis["warnings"])
    return "\n".join(lines) + "\n"

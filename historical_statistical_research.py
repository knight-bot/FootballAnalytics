"""Statistical summaries of completed historical football results.

Read-only: never requests future fixtures, odds, wagers or external APIs.
Sources: the local football-data.org results table, and separately the
operator-reviewed, two-sided standard xG rows provided by analyze_team_xg.
Uncertainty uses deterministic fixture-level bootstrap resampling; it
describes the selected stored sample, not population or future certainty.
"""
from datetime import date, datetime, timezone
from math import sqrt
from random import Random

from historical_advanced_research import _completed_matches
from historical_reports import season_label

MIN_SEASON_BOOTSTRAP = 30
MIN_XG_BOOTSTRAP = 10
MIN_FORM_MATCHES = 5
BOOTSTRAP_SAMPLES = 600
BOOTSTRAP_SEED = 24061


def _percentile(sorted_values, fraction):
    """Linear-interpolation empirical percentile of a sorted sequence."""
    n = len(sorted_values)
    if not n:
        return None
    x = (n - 1) * fraction
    lo = int(x)
    hi = min(lo + 1, n - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (x - lo)


def _boot_mean_interval(values, minimum, seed=BOOTSTRAP_SEED):
    """Approximate 95% percentile interval, resampling complete matches."""
    if len(values) < minimum:
        return None
    rng = Random(seed)
    n = len(values)
    sample_means = sorted(
        sum(values[rng.randrange(n)] for _ in range(n)) / n
        for _ in range(BOOTSTRAP_SAMPLES)
    )
    return (_percentile(sample_means, .025),
            _percentile(sample_means, .975))


def _wilson(successes, count, z=1.959963984540054):
    """Wilson 95% interval for a binary outcome among stored matches."""
    if count == 0:
        return None
    p = successes / count
    den = 1 + z*z/count
    center = (p + z*z/(2*count))/den
    radius = z*sqrt((p*(1-p)+z*z/(4*count))/count)/den
    return (max(0.0, center-radius), min(1.0, center+radius))


def recorded_season_statistics(conn, competition, year, team):
    """League score frequencies and selected team's retrospective form.

    Previous-match form is calculated using ONLY completed fixtures with
    a STRICTLY EARLIER calendar date than the historical focal game.
    Same-date games never enter each other's reference periods, even
    if provider timestamps are ambiguous. No future match row exists.
    """
    if not isinstance(team, str) or not team.strip():
        raise ValueError("Choose a recorded team.")
    games, invalid_ids = _completed_matches(conn, competition, year)
    home_wins = sum(g[4] > g[5] for g in games)
    draws = sum(g[4] == g[5] for g in games)
    away_wins = len(games) - home_wins - draws
    totals = [g[4] + g[5] for g in games]
    n = len(games)
    league = {
        "recorded_matches": n,
        "home_wins": home_wins, "draws": draws, "away_wins": away_wins,
        "home_win_fraction": home_wins / n if n else None,
        "draw_fraction": draws / n if n else None,
        "away_win_fraction": away_wins / n if n else None,
        "home_win_wilson95": _wilson(home_wins, n),
        "draw_wilson95": _wilson(draws, n),
        "away_win_wilson95": _wilson(away_wins, n),
        "goals_per_match": sum(totals) / n if n else None,
        "goals_per_match_bootstrap95": _boot_mean_interval(
            totals, MIN_SEASON_BOOTSTRAP
        ),
        "match_ids": [g[0] for g in games],
        "excluded_match_ids": invalid_ids,
    }
    selected = []
    for mid, when, home, away, hg, ag in games:
        if team == home:
            selected.append({
                "match_id": mid, "date": when[:10], "opponent": away,
                "venue": "Home", "goals_for": hg, "goals_against": ag,
            })
        elif team == away:
            selected.append({
                "match_id": mid, "date": when[:10], "opponent": home,
                "venue": "Away", "goals_for": ag, "goals_against": hg,
            })
    selected.sort(key=lambda g: (g["date"], g["match_id"]))
    rows = []
    for g in selected:
        earlier = [r for r in selected if r["date"] < g["date"]]
        previous = earlier[-MIN_FORM_MATCHES:]
        count = len(previous)
        points = sum(
            3 if t["goals_for"] > t["goals_against"]
            else 1 if t["goals_for"] == t["goals_against"] else 0
            for t in previous
        )
        rows.append({
            **g,
            "previous_matches": count,
            "previous_match_ids": [r["match_id"] for r in previous],
            "previous_five_points_per_game": (
                points / count if count == MIN_FORM_MATCHES else None
            ),
            "previous_five_goals_for_per_game": (
                sum(t["goals_for"] for t in previous) / count
                if count == MIN_FORM_MATCHES else None
            ),
            "previous_five_goals_against_per_game": (
                sum(t["goals_against"] for t in previous) / count
                if count == MIN_FORM_MATCHES else None
            ),
        })
    home = [r for r in selected if r["venue"] == "Home"]
    away = [r for r in selected if r["venue"] == "Away"]

    def outcome_stats(sub):
        return {
            "matches": len(sub),
            "wins": sum(g["goals_for"] > g["goals_against"] for g in sub),
            "draws": sum(g["goals_for"] == g["goals_against"] for g in sub),
            "losses": sum(g["goals_for"] < g["goals_against"] for g in sub),
            "total_goals_for": sum(g["goals_for"] for g in sub),
            "total_goals_against": sum(g["goals_against"] for g in sub),
            "source_ids": [r["match_id"] for r in sub],
        }
    warnings = [
        "All rates describe valid FINISHED results stored locally, "
        "NOT an independently verified complete official season.",
        "Wilson intervals describe sampling uncertainty for recorded "
        "binary outcomes under an independence approximation; "
        "football matches are not strictly independent.",
        "Goals-per-match bootstrap resamples whole completed fixtures; "
        "this is a descriptive sensitivity interval, not a guarantee.",
        "The last-five form for each COMPLETED match uses only same-season "
        "earlier dates; the focal game and later or same-date games "
        "are never used in its preceding-form calculations.",
        "No past-performance statistic here estimates an upcoming fixture.",
    ]
    if n < MIN_SEASON_BOOTSTRAP:
        warnings.append(
            f"Only {n} league results stored; goals uncertainty withheld "
            f"below {MIN_SEASON_BOOTSTRAP} completed games."
        )
    return {
        "competition": competition,
        "season": season_label(year),
        "team": team,
        "league": league,
        "team_overall": outcome_stats(selected),
        "team_home": outcome_stats(home),
        "team_away": outcome_stats(away),
        "team_rows": rows,
        "form_rows_available": sum(
            r["previous_five_points_per_game"] is not None for r in rows
        ),
        "warnings": warnings,
    }


def historical_season_comparison(conn, competition, final_year,
                                 years=4, as_of_date=None):
    """Compare recorded completed league goal frequencies across years.

    The selected season may still be underway and is explicitly marked
    as incomplete. A completed July-June calendar interval is not proof
    that all official fixtures have been imported.
    """
    if isinstance(years, bool) or not isinstance(years, int) or not 2 <= years <= 8:
        raise ValueError("Compare between two and eight recorded years.")
    if as_of_date is None:
        as_of_date = datetime.now(timezone.utc).date()
    if type(as_of_date) is not date:
        raise ValueError("as_of_date must be a date.")
    timeline = []
    for year in range(final_year - years + 1, final_year + 1):
        games, excluded = _completed_matches(conn, competition, year)
        end = date(year+1, 7, 1)
        totals = [g[4] + g[5] for g in games]
        n = len(totals)
        timeline.append({
            "season": season_label(year),
            "year": year,
            "recorded_matches": n,
            "excluded_match_count": len(excluded),
            "goals_per_match": sum(totals)/n if n else None,
            "home_goals_per_match": (
                sum(g[4] for g in games)/n if n else None
            ),
            "away_goals_per_match": (
                sum(g[5] for g in games)/n if n else None
            ),
            "calendar_window_complete": end <= as_of_date,
            "sample_size_sufficient": n >= MIN_SEASON_BOOTSTRAP,
        })
    return {
        "competition": competition,
        "year_count": years,
        "by_season": timeline,
        "warnings": [
            "Yearly figures cover only locally stored completed fixtures; "
            "a closed season calendar does not certify schedule coverage.",
            "No causal conclusions about team strength or league rules "
            "follow from the raw year-to-year differences.",
            "Ongoing calendar seasons and years below 30 stored matches "
            "are flagged, not interpreted as complete season results.",
        ],
    }


def reviewed_xg_sensitivity(xg_report):
    """Resampling sensitivity of observed GF-xG, reviewed match sample only.

    At least ten distinct reviewed completed-match observations required.
    No independent fixture selection, no raw Sportmonks join, and no
    xG-based predictions are performed in this function.
    """
    if not isinstance(xg_report, dict) or not isinstance(
            xg_report.get("match_rows"), list):
        raise ValueError("A reviewed xG report is required.")
    ids = set()
    diffs = []
    for row in xg_report["match_rows"]:
        mid = row.get("match_id")
        if type(mid) is not int or mid in ids:
            raise ValueError("Invalid or duplicate reviewed source match IDs.")
        ids.add(mid)
        gf, xg = row.get("goals_for"), row.get("xg_for")
        if (type(gf) is not int or gf < 0 or
            type(xg) not in (int, float) or not (0 <= xg < float("inf"))):
            raise ValueError("Invalid goals or standard xG observation.")
        diffs.append(gf-xg)
    n = len(diffs)
    interval = _boot_mean_interval(diffs, MIN_XG_BOOTSTRAP)
    return {
        "reviewed_matches": n,
        "source_match_ids": sorted(ids),
        "mean_goals_minus_xg_per_match": sum(diffs)/n if n else None,
        "bootstrap_mean_difference95": interval,
        "mean_absolute_difference": (
            sum(abs(d) for d in diffs)/n if n else None
        ),
        "warnings": [
            "Only currently operator-reviewed matches with unambiguous "
            "two-sided standard xG are eligible for this sample.",
            "The bootstrap interval quantifies resampling sensitivity "
            "within these recorded matches; it is NOT a forecast "
            "or evidence of persistent finishing skill.",
        ] + (
            [f"Fewer than {MIN_XG_BOOTSTRAP} reviewed matches: "
             "bootstrap uncertainty withheld."]
            if n < MIN_XG_BOOTSTRAP else []
        ),
    }


def statistical_research_markdown(season, comparison, sensitivity):
    """Source-grounded text section reusable by ChatGPT export and UI."""
    def fmt(x):
        return "Unavailable" if x is None else f"{x:.3f}"
    def band(x):
        return "Unavailable" if x is None else f"[{x[0]:.3f}, {x[1]:.3f}]"

    lg = season["league"]
    rows = [
        "## Historical statistical research and uncertainty",
        "",
        f"**Competition:** {season['competition']}",
        f"**July-June season:** {season['season']}",
        f"**Team:** {season['team']}",
        f"**Locally recorded completed league games:** {lg['recorded_matches']}",
        f"**Recorded home wins / draws / away wins:** "
        f"{lg['home_wins']} / {lg['draws']} / {lg['away_wins']}",
        f"**Historical home-win fraction:** {fmt(lg['home_win_fraction'])}",
        f"**Home-win Wilson 95% interval:** "
        f"{band(lg['home_win_wilson95'])}",
        f"**Recorded goals per match:** {fmt(lg['goals_per_match'])}",
        f"**Historical goals/match resampling 95% interval:** "
        f"{band(lg['goals_per_match_bootstrap95'])}",
        "",
        "### Completed-season team outcomes",
        "",
        "| Venue | Matches | Wins | Draws | Losses | GF | GA |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key, label in (
        ("team_overall", "All"), ("team_home", "Home"),
        ("team_away", "Away"),
    ):
        v = season[key]
        rows.append(
            f"| {label} | {v['matches']} | {v['wins']} | {v['draws']} | "
            f"{v['losses']} | {v['total_goals_for']} | "
            f"{v['total_goals_against']} |"
        )
    rows.extend([
        "",
        "**Recorded completed-match source IDs:** "
        + (", ".join(map(str, lg["match_ids"])) or "None"),
        "",
        "### Historical last-five form, computed before each completed match",
        "",
        "| Completed match ID | Date | Previous source IDs | "
        "Earlier five points/game | Earlier five GF/game |",
        "|---:|---|---|---:|---:|",
    ])
    for row in season["team_rows"]:
        rows.append(
            f"| {row['match_id']} | {row['date']} | "
            f"{', '.join(map(str, row['previous_match_ids'])) or 'None'} | "
            f"{fmt(row['previous_five_points_per_game'])} | "
            f"{fmt(row['previous_five_goals_for_per_game'])} |"
        )
    rows.extend([
        "",
        "### Locally recorded league scoring across seasons",
        "",
        "| Season | Stored matches | Goals / match | "
        "Calendar interval ended? | 30+ recorded matches? |",
        "|---|---:|---:|---|---|",
    ])
    for item in comparison["by_season"]:
        rows.append(
            f"| {item['season']} | {item['recorded_matches']} | "
            f"{fmt(item['goals_per_match'])} | "
            f"{'Yes' if item['calendar_window_complete'] else 'No'} | "
            f"{'Yes' if item['sample_size_sufficient'] else 'No'} |"
        )
    rows.extend([
        "",
        "### Sensitivity of reviewed historical xG differences",
        "",
        f"**Completed reviewed xG fixtures:** "
        f"{sensitivity['reviewed_matches']}",
        "**Mean observed goals minus xG / reviewed match:** "
        + fmt(sensitivity["mean_goals_minus_xg_per_match"]),
        "**Bootstrap 95% interval (match resampling):** "
        + band(sensitivity["bootstrap_mean_difference95"]),
        "**Eligible football-data.org match IDs:** "
        + (", ".join(map(str, sensitivity["source_match_ids"])) or "None"),
        "",
        "### Interpretation limitations",
        "",
    ])
    for warning in (
        season["warnings"] + comparison["warnings"] + sensitivity["warnings"]
    ):
        rows.append(f"- {warning}")
    return "\n".join(rows) + "\n"

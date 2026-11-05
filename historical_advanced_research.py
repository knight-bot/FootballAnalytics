"""Offline historical football diagnostics with explicit sampling limits.

No predictions, upcoming fixtures, betting odds, wagers, provider API requests,
provider identity guesses, or database writes. xG results are accepted ONLY
from the reviewed-pair analysis performed by historical_xg_analysis.
"""
from collections import Counter, defaultdict
from datetime import date
from math import isfinite, sqrt
from statistics import median

MIN_OPPONENT_REFERENCE_MATCHES = 3
MIN_CORRELATION_MATCHES = 10


def _date_bounds(season_start):
    if isinstance(season_start, bool) or not isinstance(season_start, int):
        raise ValueError("Season starting year must be an integer.")
    if not 1900 <= season_start <= 2199:
        raise ValueError("Season starting year is out of range.")
    return f"{season_start}-07-01", f"{season_start + 1}-07-01"


def _valid_match(row):
    mid, stamp, home, away, hg, ag = row
    if not isinstance(stamp, str) or len(stamp) < 10:
        return False
    try:
        date.fromisoformat(stamp[:10])
    except ValueError:
        return False
    return (
        isinstance(mid, int) and not isinstance(mid, bool)
        and isinstance(home, str) and bool(home.strip())
        and isinstance(away, str) and bool(away.strip())
        and home.strip() != away.strip()
        and isinstance(hg, int) and not isinstance(hg, bool) and hg >= 0
        and isinstance(ag, int) and not isinstance(ag, bool) and ag >= 0
    )


def _completed_matches(conn, competition, year):
    if not isinstance(competition, str) or not competition.strip():
        raise ValueError("A recorded competition is required.")
    start, end = _date_bounds(year)
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='matches'"
    ).fetchone():
        raise ValueError("No locally stored match-results table exists.")
    selected = list(conn.execute(
        "SELECT match_id, date, home_team, away_team, home_goals, away_goals "
        "FROM matches WHERE status='FINISHED' AND competition=? "
        "AND date>=? AND date<? ORDER BY date, match_id",
        (competition, start, end),
    ))
    games = [row for row in selected if _valid_match(row)]
    rejected = [row[0] for row in selected if not _valid_match(row)]
    return games, rejected


def season_sample_balance(conn, competition, year):
    """Check relative distribution of locally stored finished league games.

    This is NOT a schedule completeness validator: missing whole fixtures
    cannot be inferred from the sample alone.
    """
    games, rejected = _completed_matches(conn, competition, year)
    counts = defaultdict(lambda: {"home": 0, "away": 0, "ids": []})
    signatures = Counter()
    for mid, when, home, away, hg, ag in games:
        counts[home]["home"] += 1
        counts[away]["away"] += 1
        counts[home]["ids"].append(mid)
        counts[away]["ids"].append(mid)
        signatures[(when[:10], home, away)] += 1
    teams = []
    for name, count in sorted(counts.items()):
        total = count["home"] + count["away"]
        teams.append({
            "team": name, "played": total,
            "home": count["home"], "away": count["away"],
            "home_away_gap": abs(count["home"] - count["away"]),
            "match_ids": count["ids"],
        })
    duplicates = [
        {"date": d, "home": h, "away": a, "count": n}
        for (d, h, a), n in sorted(signatures.items()) if n > 1
    ]
    played_counts = [r["played"] for r in teams]
    warnings = [
        "These counts include only valid FINISHED results stored locally. "
        "They do not establish official season completeness.",
        "Uneven games per team may reflect incomplete imports or "
        "a season still in progress, not an on-field performance effect.",
    ]
    if rejected:
        warnings.append(
            f"{len(rejected)} invalid finished row(s) were excluded."
        )
    if duplicates:
        warnings.append(
            f"{len(duplicates)} same-date, same-home-and-away fixture "
            "signature(s) are duplicated; check source records."
        )
    if played_counts and max(played_counts) - min(played_counts) >= 5:
        warnings.append(
            "Stored match counts differ by at least five games between "
            "teams; compare teams cautiously."
        )
    return {
        "competition": competition,
        "season": f"{year}/{str(year+1)[-2:]}",
        "valid_matches": len(games),
        "excluded_match_ids": rejected,
        "teams": teams,
        "team_count": len(teams),
        "min_team_matches": min(played_counts) if played_counts else None,
        "median_team_matches": median(played_counts) if played_counts else None,
        "max_team_matches": max(played_counts) if played_counts else None,
        "date_first": games[0][1][:10] if games else None,
        "date_last": games[-1][1][:10] if games else None,
        "duplicate_signatures": duplicates,
        "warnings": warnings,
    }


def opponent_context(conn, competition, year, team,
                     min_other_matches=MIN_OPPONENT_REFERENCE_MATCHES):
    """Contextualize recorded team goals against opponents' other games.

    For each selected match, compare the opponent's other games IN THE
    SAME VENUE and the same season, excluding all games against the target.
    This is retrospective season description, NOT a held-out forecast.
    """
    if not isinstance(team, str) or not team.strip():
        raise ValueError("Choose a valid team.")
    if (isinstance(min_other_matches, bool) or
            not isinstance(min_other_matches, int) or
            not 1 <= min_other_matches <= 20):
        raise ValueError("Minimum comparison count must be 1-20.")
    games, rejected = _completed_matches(conn, competition, year)
    selected = [g for g in games if team in (g[2], g[3])]
    reference = defaultdict(list)
    for mid, when, home, away, hg, ag in games:
        if team in (home, away):
            continue  # exclude *all* matches against selected team
        reference[(home, "Home")].append((mid, hg, ag))
        reference[(away, "Away")].append((mid, ag, hg))
    rows = []
    for mid, when, home, away, hg, ag in selected:
        is_home = home == team
        opponent = away if is_home else home
        opponent_venue = "Away" if is_home else "Home"
        gf = hg if is_home else ag
        ga = ag if is_home else hg
        refs = reference.get((opponent, opponent_venue), [])
        n = len(refs)
        scored = sum(r[1] for r in refs) / n if n else None
        conceded = sum(r[2] for r in refs) / n if n else None
        enough = n >= min_other_matches
        rows.append({
            "match_id": mid, "date": when[:10],
            "opponent": opponent, "team_venue": "Home" if is_home else "Away",
            "opponent_venue": opponent_venue,
            "team_goals_for": gf, "team_goals_against": ga,
            "opponent_other_games": n,
            "comparison_eligible": enough,
            "opponent_other_goals_for_per_match": scored if enough else None,
            "opponent_other_goals_against_per_match": conceded if enough else None,
            "goals_above_opponent_other_conceded_avg": (
                gf - conceded if enough else None
            ),
            "conceded_above_opponent_other_scored_avg": (
                ga - scored if enough else None
            ),
            "reference_match_ids": [ref[0] for ref in refs] if enough else [],
        })
    comparable = [r for r in rows if r["comparison_eligible"]]
    n = len(comparable)
    mean_scored_gap = (
        sum(r["goals_above_opponent_other_conceded_avg"]
            for r in comparable) / n if n else None
    )
    mean_conceded_gap = (
        sum(r["conceded_above_opponent_other_scored_avg"]
            for r in comparable) / n if n else None
    )
    warnings = [
        "Opponent reference samples use valid completed matches in the "
        "same recorded season and opponent venue, excluding ALL "
        "head-to-head games against the selected team.",
        "These reference samples may include matches played later than "
        "the selected fixture. This is retrospective context, not a "
        "chronological forecast or proof of opponent-adjusted ability.",
        "Only opponents with enough OTHER same-venue matches are "
        "included in the contextual averages; missing baselines "
        "remain undefined, not zero.",
    ]
    if n < 5:
        warnings.append("Fewer than five selected matches have usable "
                        "opponent-context references: interpret cautiously.")
    if rejected:
        warnings.append(f"{len(rejected)} invalid completed league rows "
                        "were excluded from opponent references.")
    return {
        "team": team, "competition": competition,
        "season": f"{year}/{str(year+1)[-2:]}",
        "recorded_team_matches": len(selected),
        "matched_context_count": n,
        "unmatched_context_count": len(selected) - n,
        "minimum_reference_matches": min_other_matches,
        "mean_scored_above_opponent_other_conceded_avg": mean_scored_gap,
        "mean_conceded_above_opponent_other_scored_avg": mean_conceded_gap,
        "rows": rows, "warnings": warnings,
    }


def _pearson(pairs):
    if len(pairs) < MIN_CORRELATION_MATCHES:
        return None
    xs, ys = zip(*pairs)
    xm, ym = sum(xs)/len(xs), sum(ys)/len(ys)
    sxx = sum((x-xm)**2 for x in xs)
    syy = sum((y-ym)**2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    r = sum((x-xm)*(y-ym) for x, y in pairs) / sqrt(sxx*syy)
    return max(-1.0, min(1.0, r))


def historical_xg_diagnostics(xg_report):
    """Summarize already-reviewed historical xG rows without new joins.

    The calling report is expected to have already enforced manual source
    associations and type 5304 checks. This function doesn't promote any
    independent Sportmonks case study into a match-level observation.
    """
    if not isinstance(xg_report, dict) or not isinstance(
            xg_report.get("match_rows"), list):
        raise ValueError("Expected a reviewed historical xG analysis report.")
    rows = sorted(
        xg_report["match_rows"],
        key=lambda r: (r["date"], r["match_id"]),
    )
    seen = set()
    for row in rows:
        match_id = row["match_id"]
        if match_id in seen:
            raise ValueError("Duplicate reviewed match IDs in xG analysis.")
        seen.add(match_id)
        if row["venue"] not in ("Home", "Away"):
            raise ValueError("Unknown recorded venue in reviewed xG rows.")
        for field in ("xg_for", "xg_against", "goals_for", "goals_against"):
            v = row[field]
            if (isinstance(v, bool) or not isinstance(v, (int,float))
                    or not isfinite(v) or v < 0):
                raise ValueError("Invalid reviewed xG/goal observation.")
    scopes = {}
    for scope in ("Overall", "Home", "Away"):
        sub = rows if scope == "Overall" else [
            row for row in rows if row["venue"] == scope
        ]
        n = len(sub)
        if not n:
            scopes[scope] = {
                "matches": 0, "goals_for": None, "xg_for": None,
                "goals_against": None, "xg_against": None,
                "goals_minus_xg": None, "conceded_minus_xga": None,
                "mean_abs_goals_minus_xg": None,
            }
            continue
        gf = sum(r["goals_for"] for r in sub)
        ga = sum(r["goals_against"] for r in sub)
        xgf = sum(r["xg_for"] for r in sub)
        xga = sum(r["xg_against"] for r in sub)
        scopes[scope] = {
            "matches": n, "goals_for": gf, "xg_for": xgf,
            "goals_against": ga, "xg_against": xga,
            "goals_minus_xg": gf-xgf,
            "conceded_minus_xga": ga-xga,
            "mean_abs_goals_minus_xg": sum(
                abs(r["goals_for"]-r["xg_for"]) for r in sub
            ) / n,
        }
    cum_gf, cum_xgf = 0, 0.0
    timeline = []
    for row in rows:
        cum_gf += row["goals_for"]
        cum_xgf += row["xg_for"]
        timeline.append({
            "match_id": row["match_id"], "date": row["date"],
            "cumulative_goals": cum_gf,
            "cumulative_xg": cum_xgf,
            "cumulative_goals_minus_xg": cum_gf-cum_xgf,
        })
    correlation = _pearson([(r["xg_for"], r["goals_for"]) for r in rows])
    outliers = sorted(
        [{
            "match_id": r["match_id"], "date": r["date"],
            "opponent": r.get("opponent", "Unknown"),
            "goals_minus_xg": r["goals_for"]-r["xg_for"],
        } for r in rows],
        key=lambda r: (-abs(r["goals_minus_xg"]), r["match_id"]),
    )[:3]
    warnings = [
        "All xG figures are from previously operator-reviewed, source-linked "
        "historical matches with complete two-sided standard xG.",
        "The reviewed subset can be selected and highly incomplete. "
        "Do not extrapolate the totals or correlations to a full season.",
        "Goal-minus-xG is an observed difference, not a validated "
        "measure of persistent skill or future outcomes.",
    ]
    if len(rows) < MIN_CORRELATION_MATCHES:
        warnings.append(
            f"Correlation is withheld below {MIN_CORRELATION_MATCHES} "
            "independent reviewed matches."
        )
    elif correlation is None:
        warnings.append("Correlation is undefined because one observed "
                        "series has no variation.")
    return {
        "team": xg_report.get("team"),
        "competition": xg_report.get("competition"),
        "season": xg_report.get("season"),
        "included_matches": len(rows),
        "eligible_source_match_ids": sorted(seen),
        "venue_scopes": scopes,
        "historical_xg_goals_correlation": correlation,
        "cumulative_timeline": timeline,
        "largest_historical_deviations": outliers,
        "warnings": warnings,
    }


def advanced_markdown(sample, opponents, xg):
    """Bounded Markdown for the existing ChatGPT historical research pack."""
    def f(x):
        return "Unavailable" if x is None else f"{x:.3f}"
    lines = [
        "## Advanced retrospective research diagnostics",
        "",
        f"**Competition:** {sample['competition']}",
        f"**Historical season:** {sample['season']}",
        f"**Stored valid league matches:** {sample['valid_matches']}",
        f"**Recorded teams:** {sample['team_count']}",
        f"**Recorded matches per team (min / median / max):** "
        f"{f(sample['min_team_matches'])} / "
        f"{f(sample['median_team_matches'])} / "
        f"{f(sample['max_team_matches'])}",
        f"**Team under study:** {opponents['team']}",
        "",
        "### Opponent-context descriptive comparisons",
        "",
        f"**Team games with adequate other-match references:** "
        f"{opponents['matched_context_count']} / "
        f"{opponents['recorded_team_matches']}",
        f"**Observed GF minus opponents' other same-venue GA averages:** "
        f"{f(opponents['mean_scored_above_opponent_other_conceded_avg'])}",
        f"**Observed GA minus opponents' other same-venue GF averages:** "
        f"{f(opponents['mean_conceded_above_opponent_other_scored_avg'])}",
        "",
        "| Completed fixture ID | Opponent | Venue | Reference games | "
        "Observed goals | Baseline conceded | Historical reference match IDs |",
        "|---:|---|---|---:|---:|---:|---|",
    ]
    for r in opponents["rows"]:
        refs = ", ".join(str(v) for v in r["reference_match_ids"]) or "None"
        opponent = str(r["opponent"]).replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {r['match_id']} | {opponent} | {r['team_venue']} | "
            f"{r['opponent_other_games']} | {r['team_goals_for']} | "
            f"{f(r['opponent_other_goals_against_per_match'])} | {refs} |"
        )
    lines.extend([
        "",
        "### Reviewed historical xG diagnostic splits",
        "",
        f"**Complete reviewed matches:** {xg['included_matches']}",
        "",
        "| Venue | Matches | GF | xGF | GF - xGF | GA | xGA | GA - xGA |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for venue in ("Overall", "Home", "Away"):
        r = xg["venue_scopes"][venue]
        lines.append(
            f"| {venue} | {r['matches']} | {f(r['goals_for'])} | "
            f"{f(r['xg_for'])} | {f(r['goals_minus_xg'])} | "
            f"{f(r['goals_against'])} | {f(r['xg_against'])} | "
            f"{f(r['conceded_minus_xga'])} |"
        )
    lines.extend([
        "",
        "**Within-reviewed-sample correlation (xG for vs goals scored):** "
        + f(xg["historical_xg_goals_correlation"]),
        "",
        "### Caveats",
        "",
    ])
    for message in sample["warnings"] + opponents["warnings"] + xg["warnings"]:
        lines.append(f"- {message}")
    return "\n".join(lines) + "\n"

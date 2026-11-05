"""Plan bounded, retrospective Sportmonks imports from local historical gaps.

No API calls or database writes. A window is a suggestion for the EXISTING
manually triggered Sportmonks importer, NOT a guarantee Sportmonks has a
corresponding fixture or licensed xG coverage.

Only finished football-data.org results with no imported match candidate
can generate discovery windows. Unreviewed candidates need manual review,
not another blind import.
"""
from datetime import date, datetime, timedelta, timezone

from historical_coverage_matrix import coverage_matrix
from historical_reports import season_label
from sportmonks_historical_batch import (
    MAX_WINDOW_DAYS, MIN_AGE_DAYS, SUPPORTED_LEAGUES,
)

COMPETITION_TO_LEAGUE = {"Premier League": 8}
MAX_PLAN_WINDOWS = 12


def _validate_inputs(
    competition, start_year, max_windows, as_of_date,
):
    if competition not in COMPETITION_TO_LEAGUE:
        raise ValueError(
            "Historical import planning currently supports Premier League "
            "(verified Sportmonks league ID 8) only."
        )
    if isinstance(start_year, bool) or not isinstance(start_year, int):
        raise ValueError("A historical season start year is required.")
    if isinstance(max_windows, bool) or not isinstance(max_windows, int) or not (
        1 <= max_windows <= MAX_PLAN_WINDOWS
    ):
        raise ValueError(
            f"Select 1-{MAX_PLAN_WINDOWS} import windows."
        )
    if as_of_date is not None and type(as_of_date) is not date:
        raise ValueError("as_of_date must be a date or None.")
    if COMPETITION_TO_LEAGUE[competition] not in SUPPORTED_LEAGUES:
        raise ValueError("Unsupported import league mapping.")


def plan_historical_imports(
    conn, competition, start_year, max_windows=6, as_of_date=None,
):
    """Return prioritized short historical import windows and review tasks.

    Windows cover at most 14 inclusive calendar days; the latest date is
    14+ days old to satisfy the existing batch importer's age guard.
    Ranking prioritizes more currently unmatched *locally stored*
    finished results, with older windows breaking ties.
    """
    _validate_inputs(competition, start_year, max_windows, as_of_date)
    today = as_of_date or datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=MIN_AGE_DAYS)
    evidence = coverage_matrix(conn, competition, start_year)
    missing = []
    too_recent = []
    for row in evidence["rows"]:
        if row["coverage_status"] != "no_imported_candidate":
            continue
        try:
            match_date = date.fromisoformat(row["date"])
        except (ValueError, TypeError):
            # Invalid dates are already excluded by coverage_matrix.
            continue
        if match_date <= cutoff:
            missing.append((match_date, row))
        else:
            too_recent.append(row["match_id"])
    missing.sort(key=lambda item: (item[0], item[1]["match_id"]))

    all_windows = []
    while missing:
        anchor = missing[0][0]
        latest = min(anchor + timedelta(days=MAX_WINDOW_DAYS - 1), cutoff)
        group = []
        while missing and missing[0][0] <= latest:
            group.append(missing.pop(0))
        end_date = group[-1][0]
        all_windows.append({
            "start_date": anchor.isoformat(),
            "end_date": end_date.isoformat(),
            "local_missing_results": len(group),
            "source_match_ids": [row["match_id"] for _, row in group],
            "example_match": (
                f"{group[0][1]['home_team']} vs {group[0][1]['away_team']}"
            ),
        })

    # Prioritize windows with more missing local results, without
    # pretending to know Sportmonks availability before requesting it.
    all_windows.sort(
        key=lambda w: (-w["local_missing_results"], w["start_date"])
    )
    selected = []
    for rank, window in enumerate(all_windows[:max_windows], start=1):
        selected.append({"priority": rank, **window})

    review_candidates = [
        row for row in evidence["rows"]
        if row["coverage_status"] == "review_candidate"
    ]
    existing_missing_xg = [
        row for row in evidence["rows"]
        if row["coverage_status"] == "reviewed_missing_xg"
    ]
    manual_resolution = [
        row for row in evidence["rows"]
        if row["coverage_status"] in ("stale_review", "ambiguous", "score_mismatch")
    ]
    status_counts = evidence["status_counts"]
    return {
        "competition": competition,
        "season": season_label(start_year),
        "sportmonks_league_id": COMPETITION_TO_LEAGUE[competition],
        "as_of_date": today.isoformat(),
        "last_eligible_date": cutoff.isoformat(),
        "valid_stored_results": evidence["valid_finished_rows"],
        "already_reviewed_with_xg": status_counts["reviewed_complete_xg"],
        "review_candidates": len(review_candidates),
        "review_queue": review_candidates,
        "manual_resolution_count": len(manual_resolution),
        "manual_resolution_queue": manual_resolution,
        "reviewed_missing_xg_count": len(existing_missing_xg),
        "missing_xg_queue": existing_missing_xg,
        "unmatched_eligible": (
            sum(w["local_missing_results"] for w in all_windows)
        ),
        "unmatched_too_recent": len(too_recent),
        "unmatched_too_recent_ids": too_recent,
        "total_windows": len(all_windows),
        "shown_windows": len(selected),
        "omitted_windows": max(0, len(all_windows) - len(selected)),
        "windows": selected,
        "warnings": [
            "Import suggestions are based on valid completed fixtures "
            "already stored in football.db. Missing results from an "
            "official league schedule cannot be detected.",
            "The existing batch importer discovers Sportmonks league ID "
            "8 historical completed fixtures, NOT specific football-data.org "
            "match IDs; suggested counts are local gaps only.",
            "No import window exceeds 14 inclusive days or contains a "
            "match less than 14 days old.",
            "Importing does not approve cross-provider fixture links. "
            "Each candidate requires separate operator score verification.",
            "Existing reviewed links missing xG need a source coverage "
            "investigation, not an assumption that refreshing will "
            "necessarily recover the data.",
            "Stored source-score disagreements must be resolved "
            "manually and never automatically converted into links.",
            "Sportmonks access depends on the user's licensed "
            "subscription and API limits. This planner makes no API calls.",
        ],
    }


def import_plan_markdown(plan):
    """Portable plan for a bounded historical-only manual import workflow."""
    lines = [
        "# Historical Sportmonks Import Gap Plan",
        "",
        f"**Competition:** {plan['competition']}",
        f"**Date-derived season:** {plan['season']}",
        f"**Sportmonks historical league ID:** "
        f"{plan['sportmonks_league_id']}",
        f"**As-of date (UTC):** {plan['as_of_date']}",
        f"**Latest eligible historical date:** {plan['last_eligible_date']}",
        f"**Valid locally recorded finished results:** "
        f"{plan['valid_stored_results']}",
        f"**Already reviewed with complete xG:** "
        f"{plan['already_reviewed_with_xg']}",
        f"**Unreviewed match candidates (check source scores first):** "
        f"{plan['review_candidates']}",
        f"**Ambiguous/stale links needing manual resolution:** "
        f"{plan['manual_resolution_count']}",
        f"**Reviewed links with missing standard xG:** "
        f"{plan['reviewed_missing_xg_count']}",
        f"**Old unmatched recorded results eligible for import discovery:** "
        f"{plan['unmatched_eligible']}",
        f"**Too-recent unmatched results excluded:** "
        f"{plan['unmatched_too_recent']}",
        "",
        "## Suggested historical import windows",
        "",
        "| Priority | Start | End | Local unmatched results | "
        "football-data.org source IDs |",
        "|---:|---|---|---:|---|",
    ]
    for w in plan["windows"]:
        lines.append(
            f"| {w['priority']} | {w['start_date']} | "
            f"{w['end_date']} | {w['local_missing_results']} | "
            f"{', '.join(str(x) for x in w['source_match_ids'])} |"
        )
    if not plan["windows"]:
        lines.append(
            "| - | No currently eligible uncovered windows | - | 0 | - |"
        )
    lines.extend([
        "",
        f"**Additional eligible windows not displayed:** "
        f"{plan['omitted_windows']}",
        "",
        "Run each selected date window using the existing manual GitHub "
        "Action **Discover and Import Historical Sportmonks Fixtures**. "
        "Keep refresh_existing off for new historical discovery. "
        "Use bounded max_fixtures and repeat only if the importer "
        "reports additional completed fixtures remaining.",
        "",
        "**Review is a separate process:** Do not equate a newly "
        "imported Sportmonks fixture with a football-data.org match "
        "until the original final scores, teams and kickoff are "
        "checked and the manual link workflow confirms the association.",
        "",
        "## Research limitations",
        "",
    ])
    lines.extend(f"- {w}" for w in plan["warnings"])
    lines.append("")
    return "\n".join(lines)

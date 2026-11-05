"""Auditable coverage matrix for completed historical matches.

Cross-provider links are accepted only when currently operator-reviewed.
The module creates no associations and makes no API requests. It assesses
coverage of LOCALLY STORED completed results, not a whole provider season.
"""
from collections import Counter

from historical_audit import table_exists
from historical_fixture_linkage import candidate_links, LINK_TABLE
from historical_reports import _bounds, season_label
from historical_team_strength import _valid_result
from historical_xg_analysis import _standard_xg_by_fixture

LINK_STATUSES = (
    "reviewed_complete_xg",
    "reviewed_missing_xg",
    "review_candidate",
    "ambiguous",
    "stale_review",
    "no_imported_candidate",
)


def coverage_matrix(conn, competition, season_start, team=None):
    """Return per-result historical linkage/xG coverage and explicit gaps.

    Unreviewed Sportmonks metrics are never presented as measurements
    belonging to the result's fixture. The score from football-data.org
    is included only as an original-source result, not a verification of
    Sportmonks' stored final score (which the importer does not retain).
    """
    if not isinstance(competition, str) or not competition.strip():
        raise ValueError("Choose a recorded competition.")
    if team is not None and (not isinstance(team, str) or not team.strip()):
        raise ValueError("Team must be a recorded nonblank name or None.")
    if not table_exists(conn, "matches"):
        raise ValueError("The historical results table is not available.")
    start, end = _bounds(season_start)
    sql = (
        "SELECT match_id, date, home_team, away_team, "
        "home_goals, away_goals FROM matches "
        "WHERE status='FINISHED' AND competition=? "
        "AND date>=? AND date<? "
    )
    args = [competition, start, end]
    if team is not None:
        sql += "AND (home_team=? OR away_team=?) "
        args.extend([team, team])
    sql += "ORDER BY date, match_id"
    raw = list(conn.execute(sql, args))
    valid = [row for row in raw if _valid_result(row)]
    excluded = [int(row[0]) for row in raw if not _valid_result(row)]
    candidates_by_match = {}
    for item in candidate_links(conn):
        mid = item["match_id"]
        if mid is not None:
            candidates_by_match.setdefault(int(mid), []).append(item)
    xg_by_id = _standard_xg_by_fixture(conn)
    stale_review_match_ids = set()
    if _exists(conn, LINK_TABLE):
        stale_review_match_ids = {
            int(mid) for (mid,) in conn.execute(
                f"SELECT football_data_match_id FROM {LINK_TABLE}"
            )
        }
    rows = []

    for mid, kickoff, home, away, hg, ag in valid:
        matching = candidates_by_match.get(int(mid), [])
        reviewed = [r for r in matching if r["status"] == "reviewed"]
        ambiguous = (
            len(matching) > 1 or
            any(r["status"] == "ambiguous" for r in matching)
        )
        status = "no_imported_candidate"
        chosen = None
        if ambiguous:
            status = "ambiguous"
        elif len(reviewed) == 1:
            chosen = reviewed[0]
            vals = xg_by_id.get(chosen["sportmonks_id"], {})
            status = (
                "reviewed_complete_xg"
                if vals.get("home") is not None and
                vals.get("away") is not None
                else "reviewed_missing_xg"
            )
        elif (int(mid) in stale_review_match_ids
              or any(r["status"] == "stale_review" for r in matching)):
            status = "stale_review"
        elif len(matching) == 1 and matching[0]["status"] == "review_candidate":
            chosen = matching[0]
            status = "review_candidate"

        sid = chosen["sportmonks_id"] if chosen else None
        hxg = axg = None
        if status == "reviewed_complete_xg":
            vals = xg_by_id[sid]
            hxg, axg = vals["home"], vals["away"]
        rows.append({
            "match_id": int(mid),
            "date": kickoff[:10],
            "home_team": home,
            "away_team": away,
            "home_goals": int(hg),
            "away_goals": int(ag),
            "coverage_status": status,
            # Candidate IDs may be displayed, but never treated as joined.
            "review_candidate_sportmonks_id": (
                sid if status == "review_candidate" else None
            ),
            "reviewed_sportmonks_id": (
                sid if status.startswith("reviewed_") else None
            ),
            "reviewed_home_xg": hxg,
            "reviewed_away_xg": axg,
        })
    counts = Counter(row["coverage_status"] for row in rows)
    count = len(rows)
    reviewed_total = counts["reviewed_complete_xg"] + counts["reviewed_missing_xg"]
    complete_xg = counts["reviewed_complete_xg"]
    cautions = [
        "All denominators count VALID COMPLETED MATCHES PRESENT IN THE "
        "LOCAL football-data.org database, not all fixtures that "
        "should exist in an official season.",
        "Sportmonks does not currently persist final scores. "
        "A reviewed cross-provider link is operator-attested, not "
        "independently score-verified by the application.",
        "A candidate is not an established link. Unreviewed fixture "
        "metrics are never attached to a football-data.org result.",
        "A missing metric is unknown, not zero; xG is available here "
        "only for a currently reviewed match with unambiguous standard "
        "xG for BOTH sides.",
        "This is a retrospective data quality audit, not future-match "
        "research or a validated model-performance measurement.",
    ]
    if team is not None and count < 5:
        cautions.append(
            "Fewer than five valid completed team results are stored "
            "for this selection."
        )
    if excluded:
        cautions.append(
            f"{len(excluded)} invalid finished match rows in the "
            "selected stored window were excluded."
        )
    return {
        "competition": competition,
        "season": season_label(season_start),
        "team": team,
        "stored_finished_rows": len(raw),
        "valid_finished_rows": count,
        "excluded_match_ids": excluded,
        "status_counts": {key: counts[key] for key in LINK_STATUSES},
        "reviewed_total": reviewed_total,
        "complete_xg": complete_xg,
        "reviewed_pct_of_stored_valid": (
            100 * reviewed_total / count if count else None
        ),
        "complete_xg_pct_of_stored_valid": (
            100 * complete_xg / count if count else None
        ),
        "rows": rows,
        "warnings": cautions,
    }


def coverage_markdown(result):
    """Bounded, source-ID-grounded description of historical data gaps."""
    def pct(value):
        return "N/A" if value is None else f"{value:.1f}%"
    lines = [
        "## Historical match data coverage",
        "",
        f"**Competition:** {result['competition']}",
        f"**July–June window:** {result['season']}",
        f"**Team:** {result['team'] or 'All teams'}",
        f"**Valid stored completed results:** {result['valid_finished_rows']}",
        f"**Excluded stored completed rows:** "
        f"{len(result['excluded_match_ids'])}",
        f"**Operator-reviewed links:** {result['reviewed_total']} "
        f"({pct(result['reviewed_pct_of_stored_valid'])} of stored valid results)",
        f"**Reviewed links with complete standard xG:** "
        f"{result['complete_xg']} "
        f"({pct(result['complete_xg_pct_of_stored_valid'])} of stored valid results)",
        "",
        "| Historical coverage status | Stored match count |",
        "|---|---:|",
    ]
    for status in LINK_STATUSES:
        lines.append(f"| {status} | {result['status_counts'][status]} |")
    lines.extend([
        "",
        "### Match-by-match coverage (football-data.org IDs)",
        "",
        "| Date | Home | Away | Source match ID | Status | "
        "Reviewed Sportmonks ID | Standard xG home | Standard xG away |",
        "|---|---|---|---:|---|---:|---:|---:|",
    ])
    for item in result["rows"]:
        def safe(s):
            return str(s).replace("|", "/").replace("\n", " ")
        h = (f"{item['reviewed_home_xg']:.2f}"
             if item["reviewed_home_xg"] is not None else "Missing")
        a = (f"{item['reviewed_away_xg']:.2f}"
             if item["reviewed_away_xg"] is not None else "Missing")
        lines.append(
            f"| {item['date']} | {safe(item['home_team'])} | "
            f"{safe(item['away_team'])} | {item['match_id']} | "
            f"{item['coverage_status']} | "
            f"{item['reviewed_sportmonks_id'] or 'None'} | {h} | {a} |"
        )
    lines.extend(["", "### Interpretation safeguards", ""])
    lines.extend(f"- {w}" for w in result["warnings"])
    return "\n".join(lines) + "\n"

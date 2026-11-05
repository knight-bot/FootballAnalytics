"""Shared read-only research readiness status for historical football data."""
from collections import Counter

from historical_audit import audit_database
from historical_fixture_linkage import candidate_links
from historical_xg_analysis import imported_xg_coverage, _standard_xg_by_fixture

MIN_REVIEWED_XG_SAMPLE = 10


def assess_research_readiness(conn):
    """Separate locally stored results, independent xG and reviewed links."""
    audit = audit_database(conn)
    imported = imported_xg_coverage(conn)
    links = candidate_links(conn)
    counts = Counter(row["status"] for row in links)
    reviewed = [r for r in links if r["status"] == "reviewed"]
    xg = _standard_xg_by_fixture(conn)
    eligible = [
        row for row in reviewed
        if xg.get(row["sportmonks_id"], {}).get("home") is not None
        and xg.get(row["sportmonks_id"], {}).get("away") is not None
    ]
    saved_scores = sum(
        row["stored_final_score_home"] is not None
        and row["stored_final_score_away"] is not None
        for row in audit["sportmonks_fixtures"]
    )
    valid = audit["results_count"] - audit["invalid_result_rows"]
    results_status = (
        "unavailable" if valid == 0
        else "needs_quality_review" if audit["invalid_result_rows"]
        else "stored_results_available"
    )
    xg_status = (
        "reviewed_sample_available"
        if len(eligible) >= MIN_REVIEWED_XG_SAMPLE
        else "small_reviewed_sample" if eligible
        else "no_reviewed_xg_sample"
    )
    notes = [
        "The denominator is locally stored completed matches, not a "
        "verified official league schedule.",
        "Imported Sportmonks xG is independent until each provider "
        "association is explicitly operator-reviewed.",
        "Score agreement never automatically approves a link.",
        "Ten reviewed matches is a display threshold, not proof "
        "of representative xG evidence or future accuracy.",
    ]
    actions = []
    if audit["invalid_result_rows"]:
        actions.append("Resolve invalid recorded result rows.")
    if counts["score_mismatch"] or counts["stale_review"] or counts["ambiguous"]:
        actions.append("Investigate conflicting, stale or ambiguous links.")
    if counts["review_candidate"]:
        actions.append("Compare source scores and manually review candidates.")
    if saved_scores < imported["imported"]:
        actions.append("Consider a bounded refresh for missing source scores.")
    if xg_status != "reviewed_sample_available":
        actions.append("Withhold strong xG conclusions pending reviewed data.")
    return {
        "stored_completed_results": audit["results_count"],
        "invalid_results": audit["invalid_result_rows"],
        "valid_completed_results": valid,
        "imported_sportmonks_fixtures": imported["imported"],
        "imported_two_sided_standard_xg": imported["complete_both_sides"],
        "imported_final_score_evidence": saved_scores,
        "reviewed_source_links": len(reviewed),
        "reviewed_two_sided_xg": len(eligible),
        "unreviewed_candidates": counts["review_candidate"],
        "score_mismatches": counts["score_mismatch"],
        "ambiguous_links": counts["ambiguous"],
        "stale_reviews": counts["stale_review"],
        "unmatched_sportmonks": counts["unmatched"],
        "results_status": results_status,
        "xg_status": xg_status,
        "reviewed_link_ids": sorted(
            row["match_id"] for row in reviewed if row["match_id"] is not None
        ),
        "reviewed_xg_source_match_ids": sorted(
            row["match_id"] for row in eligible if row["match_id"] is not None
        ),
        "notes": notes,
        "next_actions": actions,
    }


def readiness_markdown(status):
    """Reusable source-availability summary for exported reports."""
    metrics = [
        ("Completed local match records", "stored_completed_results"),
        ("Invalid local completed records", "invalid_results"),
        ("Independent imported Sportmonks fixtures", "imported_sportmonks_fixtures"),
        ("Imported fixtures with two-sided xG", "imported_two_sided_standard_xg"),
        ("Imported fixtures with stored scores", "imported_final_score_evidence"),
        ("Operator-reviewed cross-provider links", "reviewed_source_links"),
        ("Reviewed links with two-sided xG", "reviewed_two_sided_xg"),
        ("Unreviewed fixture candidates", "unreviewed_candidates"),
        ("Source-score mismatches", "score_mismatches"),
        ("Ambiguous links", "ambiguous_links"),
        ("Stale reviews", "stale_reviews"),
    ]
    lines = [
        "## Research data readiness and provenance", "",
        "| Local evidence type | Count |", "|---|---:|",
    ]
    lines.extend(f"| {label} | {status[key]} |" for label, key in metrics)
    lines.extend([
        "", f"**Results status:** {status['results_status']}",
        f"**Reviewed xG status:** {status['xg_status']}",
        "", "### Priorities", "",
    ])
    lines.extend(f"- {item}" for item in status["next_actions"])
    lines.extend(["", "### Research cautions", ""])
    lines.extend(f"- {item}" for item in status["notes"])
    lines.append("")
    return "\n".join(lines)

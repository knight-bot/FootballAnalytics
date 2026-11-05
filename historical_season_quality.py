"""Seasonal evidence-quality matrix for locally stored completed results.

A = reviewed association and complete two-sided standard xG
B = reviewed association but incomplete xG
C = unreviewed plausible source candidate
D = ambiguous, stale, or score-conflicting source association
U = no imported association
None of these imply a verified official-season fixture denominator.
"""
from collections import Counter, defaultdict

from historical_coverage_matrix import coverage_matrix
from historical_reports import season_label

QUALITY = {
    "reviewed_complete_xg": "A",
    "reviewed_missing_xg": "B",
    "review_candidate": "C",
    "score_mismatch": "D",
    "ambiguous": "D",
    "stale_review": "D",
    "no_imported_candidate": "U",
}
QUALITY_ORDER = ("A", "B", "C", "D", "U")


def build_quality_report(conn, competition, season_start):
    """Use the established conservative match-status engine, read-only."""
    matrix = coverage_matrix(conn, competition, season_start)
    months = defaultdict(lambda: Counter())
    teams = defaultdict(lambda: Counter())
    examples = defaultdict(list)
    for item in matrix["rows"]:
        grade = QUALITY[item["coverage_status"]]
        months[item["date"][:7]][grade] += 1
        for name in (item["home_team"], item["away_team"]):
            teams[name][grade] += 1
        examples[grade].append(item["match_id"])

    def format_rows(source, name_key):
        out = []
        for name, counts in sorted(source.items()):
            total = sum(counts.values())
            entry = {name_key: name, "recorded_results": total}
            entry.update({g: counts[g] for g in QUALITY_ORDER})
            entry["reviewed_pct_of_local"] = (
                round(100 * (counts["A"] + counts["B"]) / total, 2)
                if total else None
            )
            entry["linked_xg_pct_of_local"] = (
                round(100 * counts["A"] / total, 2) if total else None
            )
            out.append(entry)
        return out

    total = len(matrix["rows"])
    totals = Counter(
        QUALITY[item["coverage_status"]] for item in matrix["rows"]
    )
    return {
        "competition": competition,
        "season": season_label(season_start),
        "locally_recorded_results": total,
        "grades": {grade: totals[grade] for grade in QUALITY_ORDER},
        "reviewed_link_coverage_pct": (
            100 * (totals["A"] + totals["B"]) / total if total else None
        ),
        "reviewed_xg_coverage_pct": (
            100 * totals["A"] / total if total else None
        ),
        "by_month": format_rows(months, "month"),
        "by_team": format_rows(teams, "team"),
        "source_ids_by_grade": {
            grade: sorted(examples[grade]) for grade in QUALITY_ORDER
        },
        "warnings": [
            "All denominators count valid completed results already "
            "stored locally, NOT the official league schedule.",
            "An A grade establishes a currently operator-reviewed "
            "link with two unambiguous stored standard xG figures. "
            "It does not prove provider correctness or season completeness.",
            "A B grade means an approved association exists but "
            "one or both standard xG values are unavailable.",
            "C-grade matches are candidates only; their Sportmonks "
            "metrics are never joined to football-data.org results.",
            "D-grade records need investigation: source-score conflict, "
            "ambiguous candidates or stale manual reviews.",
            "U-grade results have no locally imported source candidate. "
            "They may reflect missing imports or provider coverage.",
            "A team occurs in each home and away match: team-table "
            "totals are two observations per locally stored game.",
        ],
    }


def quality_markdown(report):
    def pct(n):
        return "N/A" if n is None else f"{n:.2f}%"
    lines = [
        "# Historical Season Source-Quality Audit",
        "",
        f"**Competition:** {report['competition']}",
        f"**Season (July-June):** {report['season']}",
        f"**Valid locally stored completed games:** "
        f"{report['locally_recorded_results']}",
        "**Operator-reviewed association coverage of local results:** "
        + pct(report["reviewed_link_coverage_pct"]),
        "**Operator-reviewed two-sided xG coverage of local results:** "
        + pct(report["reviewed_xg_coverage_pct"]),
        "",
        "| Evidence grade | Locally stored games |",
        "|---|---:|",
    ]
    lines.extend(
        f"| {grade} | {report['grades'][grade]} |"
        for grade in QUALITY_ORDER
    )
    for title, rows, key in (
        ("By month", report["by_month"], "month"),
        ("By recorded team", report["by_team"], "team"),
    ):
        lines.extend([
            "", f"## {title}", "",
            f"| {key} | Locally stored | A | B | C | D | U | "
            "Reviewed xG % |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for row in rows:
            name = str(row[key]).replace("|", "/").replace("\n", " ")
            lines.append(
                f"| {name} | {row['recorded_results']} | "
                + " | ".join(str(row[g]) for g in QUALITY_ORDER)
                + f" | {pct(row['linked_xg_pct_of_local'])} |"
            )
    lines.extend(["", "## Original result IDs by evidence grade", ""])
    for grade in QUALITY_ORDER:
        ids = report["source_ids_by_grade"][grade]
        lines.append(
            f"- **{grade}:** "
            + (", ".join(str(x) for x in ids) if ids else "None")
        )
    lines.extend(["", "## Interpretation safeguards", ""])
    lines.extend("- " + warning for warning in report["warnings"])
    return "\n".join(lines) + "\n"

"""Build a single source-grounded Markdown pack for manual ChatGPT upload.

Uses only the local completed-match SQLite database. No API requests,
credentials, future-match analysis, or cross-provider fixture ID joins.
"""
from historical_audit import audit_database
from historical_fixture_linkage import reviewed_links_for_team
from historical_team_strength import analyze_season, strength_markdown
from historical_xg_analysis import analyze_team_xg, team_xg_markdown
from historical_coverage_matrix import coverage_matrix, coverage_markdown
from historical_evidence import team_evidence
from historical_reports import (
    build_sportmonks_report,
    build_team_report,
    list_sportmonks_fixtures,
    season_label,
)

MAX_SPORTMONKS_CASES = 8


def _clean(value):
    """Keep a source field on one Markdown line without changing its meaning."""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _chosen_fixture_ids(fixture_ids):
    if fixture_ids is None:
        return []
    if not isinstance(fixture_ids, (list, tuple)):
        raise ValueError("Fixture selection must be a list of Sportmonks IDs.")
    selected = []
    for fixture_id in fixture_ids:
        if isinstance(fixture_id, bool):
            raise ValueError("Fixture IDs must be positive integers.")
        if isinstance(fixture_id, int):
            numeric = fixture_id
        elif isinstance(fixture_id, str) and fixture_id.isdecimal():
            numeric = int(fixture_id)
        else:
            raise ValueError("Fixture IDs must be positive integers.")
        if numeric <= 0:
            raise ValueError("Fixture IDs must be positive integers.")
        if numeric not in selected:
            selected.append(numeric)
    if len(selected) > MAX_SPORTMONKS_CASES:
        raise ValueError(
            f"Select at most {MAX_SPORTMONKS_CASES} Sportmonks fixtures "
            "for one export."
        )
    return selected


def build_chatgpt_research_pack(
    conn, competition, season_start, team, fixture_ids=None,
):
    """Create a bounded historical report with auditable source provenance.

    Sportmonks cases are explicitly selected independent case studies, not
    fixtures matched to the chosen football-data.org team.
    """
    if not competition or not team:
        raise ValueError("Choose a recorded competition and team.")
    selected = _chosen_fixture_ids(fixture_ids)
    available = {
        row["id"]: row for row in list_sportmonks_fixtures(conn)
    }
    missing = [fixture_id for fixture_id in selected if fixture_id not in available]
    if missing:
        raise ValueError(
            "These Sportmonks fixture IDs are not in the local database: "
            + ", ".join(map(str, missing))
        )

    team_report = build_team_report(
        conn, competition, season_start, team
    )
    evidence = team_evidence(conn, competition, season_start, team)
    audit = audit_database(conn)
    strength = analyze_season(conn, competition, season_start)
    xg_review = analyze_team_xg(conn, competition, season_start, team)
    linkage_coverage = coverage_matrix(conn, competition, season_start, team)
    reviewed_links = reviewed_links_for_team(
        conn, competition, season_start, team,
    )
    audit_by_id = {
        item["fixture_id"]: item for item in audit["sportmonks_fixtures"]
    }

    section = [
        "# Historical Football Research Pack for ChatGPT",
        "",
        "**Purpose:** Retrospective, educational football performance research "
        "using completed matches stored in FootballAnalytics.",
        "**Generation:** Deterministic local SQLite queries; no AI or "
        "external API request was used to create this file.",
        "**Sources:** football-data.org completed results and separately "
        "selected Sportmonks Football API v3 historical fixtures.",
        "",
        "## How to use this report",
        "",
        "Upload this Markdown file into ChatGPT and ask for a critical "
        "explanation of the recorded historical performance. Check the "
        "source IDs in the evidence sections before accepting any conclusion.",
        "",
        "**Critical source rule:** A football-data.org match ID is NOT a "
        "Sportmonks fixture ID. Only explicitly operator-reviewed "
        "associations in Part A.1 may be considered linked, subject to "
        "the stated manual-review limitations. Independently selected "
        "Sportmonks case studies in Part B are NOT associated with this "
        "team unless separately reviewed.",
        "",
        "## Data scope",
        "",
        f"- Selected football-data.org team: {_clean(team)}",
        f"- Selected competition: {_clean(competition)}",
        f"- Date-derived season: {season_label(season_start)} "
        f"(July {season_start} through June {season_start + 1})",
        f"- Valid recorded team matches: "
        f"{team_report['summary'].get('played', 0)}",
        f"- Excluded team result rows: "
        f"{team_report['summary'].get('excluded', 0)}",
        f"- Separate Sportmonks historical case studies requested: "
        f"{len(selected)}",
        f"- Completed results in the entire local database: "
        f"{audit['results_count']}",
        f"- Invalid completed results detected in entire database: "
        f"{audit['invalid_result_rows']}",
        "",
        "## Part A: Recorded Team Performance",
        "",
        team_report["markdown"].strip(),
        "",
        "### Exact source evidence behind the team summary",
        "",
    ]
    if evidence["evidence"]:
        for item in evidence["evidence"]:
            section.extend([
                f"**{item['id']} | {_clean(item['title'])}**",
                "",
                _clean(item["fact"]),
                "",
                "Source: football-data.org; match IDs: "
                + (", ".join(str(v) for v in item.get("match_ids", []))
                   or "Not available"),
                "",
            ])
    else:
        section.extend([
            "No valid team-result evidence is available for this selection.",
            "",
        ])

    section.extend([
        "### Limitations specific to this team selection",
        "",
    ])
    section.extend(f"- {_clean(item)}" for item in evidence["limitations"])
    section.extend([
        "",
        "## Part A.1: Operator-Reviewed Historical Match Links",
        "",
        "These cross-provider associations were explicitly confirmed by a "
        "GitHub workflow operator after comparing the original source "
        "final scores. The application itself has not independently "
        "confirmed Sportmonks' final scores, because that value was not "
        "persisted in the imported records. The current stored names, "
        "league and kickoff have been rechecked.",
        "",
        f"Currently valid operator-reviewed links for selected team: "
        f"{len(reviewed_links)}",
        "",
    ])
    if not reviewed_links:
        section.extend([
            "No operator-reviewed matching Sportmonks fixtures are available "
            "for this team and season. Missing advanced statistics must "
            "not be interpreted as zero.",
            "",
        ])
    else:
        for link in reviewed_links[:MAX_SPORTMONKS_CASES]:
            section.extend([
                f"**Reviewed association: football-data.org match "
                f"{link['match_id']} ↔ Sportmonks fixture "
                f"{link['sportmonks_id']}**",
                "",
                f"- Recorded fixture: {_clean(link['result_match'])}",
                f"- Recorded final score (football-data.org): "
                f"{_clean(link['result_score'])}",
                f"- Kickoff difference: "
                f"{link['kickoff_difference_minutes']} minutes",
                f"- Review: {_clean(link['reason'])}",
                "",
                build_sportmonks_report(
                    conn, link["sportmonks_id"]
                )["markdown"].strip(),
                "",
            ])
        if len(reviewed_links) > MAX_SPORTMONKS_CASES:
            section.extend([
                f"**Export limit:** {len(reviewed_links) - MAX_SPORTMONKS_CASES} "
                "additional operator-reviewed fixtures are not included "
                "in this bounded report.",
                "",
            ])
    section.extend([
        "",
        "## Part A.2: League-Adjusted Historical Goal Indicators",
        "",
        strength_markdown(strength, team).strip(),
        "",
        "## Part A.3: Reviewed Historical xG Evidence",
        "",
        team_xg_markdown(xg_review).strip(),
        "",
        "## Part A.4: Match-by-Match Historical Coverage",
        "",
        coverage_markdown(linkage_coverage).strip(),
        "",
        "## Part B: Independent Sportmonks Historical Case Studies",
        "",
        "The following are **separately selected historical fixtures**. They "
        "must not be treated as matches involving the Part A team unless "
        "verified separately. Statistics describe completed games, not "
        "future outcomes.",
        "",
    ])
    warnings = []
    if not selected:
        section.extend([
            "No Sportmonks fixtures were selected for this report.",
            "",
            "To include xG and pressure records, select completed Sportmonks "
            "fixtures on the dashboard before downloading a new report.",
            "",
        ])
    for fixture_id in selected:
        fixture = build_sportmonks_report(conn, fixture_id)
        audit_row = audit_by_id.get(fixture_id)
        section.extend([
            f"### Sportmonks fixture {fixture_id}",
            "",
            fixture["markdown"].strip(),
            "",
        ])
        if audit_row:
            section.extend([
                "**Coverage and quality audit for this fixture**",
                "",
                f"- API statistics records at last import: "
                f"{audit_row['statistics_returned']}",
                f"- Numeric statistic rows stored: "
                f"{audit_row['statistics_saved']}",
                f"- API Pressure Index records at last import: "
                f"{audit_row['pressure_returned']}",
                f"- Minute-level pressure values stored: "
                f"{audit_row['pressure_saved']}",
                f"- Home standard xG: "
                f"{_clean(audit_row['standard_xg_home']) if audit_row['standard_xg_home'] is not None else 'Missing'}",
                f"- Away standard xG: "
                f"{_clean(audit_row['standard_xg_away']) if audit_row['standard_xg_away'] is not None else 'Missing'}",
                f"- Audit findings: {_clean(audit_row['issues'])}",
                "",
            ])
            if audit_row["issue_count"]:
                warnings.append(
                    f"Sportmonks fixture {fixture_id}: {audit_row['issues']}"
                )
        else:
            warnings.append(
                f"Sportmonks fixture {fixture_id}: no audit row available."
            )
    section.extend([
        "## Part C: Quality Warnings and Research Boundaries",
        "",
        "- The two sources are separate. No automatic fixture-ID matching, "
        "team-name mapping, or season reconciliation has been carried out.",
        "- The team report is calculated from locally stored completed matches. "
        "It is not a certified full-season dataset or official standings.",
        "- Sportmonks selection is a bounded historical sample, not a full "
        "Premier League season or representative league-wide sample.",
        "- Raw API record counts and saved numeric-value counts measure "
        "storage coverage; they do not count shots, tackles, or goals.",
        "- Pressure Index indicates attacking momentum and must not be "
        "presented as a count of defensive pressing events.",
        "- A missing metric is unknown, not zero. Do not fill missing "
        "values with plausible estimates.",
        "- Avoid causal conclusions from a small number of matches. "
        "Observed correlations do not establish why a result occurred.",
        "- The report has no current news, injury verification, live match "
        "information, or future-result data.",
        "",
    ])
    if audit["checks"]:
        section.append("### Database audit notices")
        section.append("")
        section.extend(
            f"- {_clean(notice)}" for notice in audit["checks"]
        )
        section.append("")
    if warnings:
        section.append("### Selected fixture audit warnings")
        section.append("")
        section.extend(f"- {_clean(notice)}" for notice in warnings)
        section.append("")

    section.extend([
        "## Suggested ChatGPT Analysis Request",
        "",
        "> Analyze only the completed historical football data contained "
        "in this report. Summarize the recorded team's performance and "
        "home/away differences. Discuss the separately selected Sportmonks "
        "fixtures only as independent case studies. Reference source "
        "match IDs or fixture IDs for important numerical claims. "
        "Identify sampling bias, missing statistics, inconsistent coverage "
        "and uncertainty. Distinguish what the numbers show from "
        "interpretations that need more evidence. Do not infer provider "
        "identity matches or make future-match predictions.",
        "",
    ])

    return {
        "markdown": "\n".join(section),
        "team_match_count": team_report["summary"].get("played", 0),
        "sportmonks_fixture_count": len(selected),
        "audit_warning_count": len(warnings),
        "fixture_ids": selected,
        "reviewed_link_count": len(reviewed_links),
        "reviewed_xg_count": xg_review["xg_complete_links"],
        "stored_coverage_count": linkage_coverage["valid_finished_rows"],
    }

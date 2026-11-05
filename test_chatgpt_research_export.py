"""Offline tests for the one-file historical research export."""
import sqlite3
import unittest

from confirm_historical_link import confirm_link

from chatgpt_research_export import (
    MAX_SPORTMONKS_CASES,
    build_chatgpt_research_pack,
)
from sportmonks_historical_import import (
    ensure_schema, store_finished_fixture,
)


def sample_fixture(fixture_id=9001, include_xg=True):
    return {
        "id": fixture_id, "name": "Example United vs Sample City",
        "starting_at": "2024-11-08 18:00:00",
        "league_id": 8, "season_id": 555, "state_id": 5,
        "participants": [
            {"id": 100, "name": "Example United",
             "meta": {"location": "home"}},
            {"id": 200, "name": "Sample City",
             "meta": {"location": "away"}},
        ],
        "scores": [{"id": 1}],
        "statistics": [
            {"type_id": 42, "participant_id": 100, "location": "home",
             "data": {"value": 10}},
            {"type_id": 42, "participant_id": 200, "location": "away",
             "data": {"value": 5}},
        ],
        "pressure": [
            {"participant_id": 100, "minute": 1, "pressure": 40.5},
            {"participant_id": 200, "minute": 1, "pressure": 22.5},
        ],
        "xgfixture": [
            {"type_id": 5304, "participant_id": 100, "location": "home",
             "data": {"value": 1.72}},
            {"type_id": 5304, "participant_id": 200, "location": "away",
             "data": {"value": 0.85}},
        ] if include_xg else [],
    }


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY,
                date TEXT, competition TEXT,
                home_team TEXT, away_team TEXT,
                home_goals INTEGER, away_goals INTEGER, status TEXT
            )
        """)
        self.conn.executemany("""
            INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (701, "2024-09-01T16:00:00Z", "Example League",
             "North", "South", 2, 0, "FINISHED"),
            (702, "2024-10-01T16:00:00Z", "Example League",
             "South", "North", 1, 1, "FINISHED"),
            (703, "2024-11-01T16:00:00Z", "Example League",
             "North", "South", None, None, "FINISHED"),
            (704, "2024-10-01T16:00:00Z", "Other League",
             "North", "South", 8, 0, "FINISHED"),
            (705, "2025-08-01T16:00:00Z", "Example League",
             "North", "South", 5, 0, "FINISHED"),
            (706, "2024-10-03T16:00:00Z", "Example League",
             "North", "South", 7, 0, "SCHEDULED"),
        ])
        ensure_schema(self.conn)
        store_finished_fixture(self.conn, sample_fixture())

    def tearDown(self):
        self.conn.close()

    def make(self, fixture_ids=None):
        return build_chatgpt_research_pack(
            self.conn, "Example League", 2024, "North",
            fixture_ids=fixture_ids,
        )

    def test_results_and_match_ids_are_traceable(self):
        export = self.make()
        md = export["markdown"]
        self.assertEqual(export["team_match_count"], 2)
        self.assertIn("football-data.org", md)
        self.assertIn("701", md)
        self.assertIn("702", md)
        self.assertIn("- Goals scored: 3; goals conceded: 1", md)
        self.assertNotIn("| 705 |", md)
        self.assertNotIn("| 704 |", md)
        self.assertNotIn("| 706 |", md)
        self.assertIn("No Sportmonks fixtures were selected", md)

    def test_optional_sportmonks_case_is_separate_not_joined(self):
        export = self.make([9001])
        md = export["markdown"]
        self.assertEqual(export["sportmonks_fixture_count"], 1)
        self.assertIn("Sportmonks fixture 9001", md)
        self.assertIn("1.72", md)
        self.assertIn("0.85", md)
        self.assertIn("Numeric statistic rows stored: 2", md)
        self.assertIn("Minute-level pressure values stored: 2", md)
        self.assertIn("NOT a Sportmonks fixture ID", md)
        self.assertIn("Independent Sportmonks Historical Case Studies", md)

    def test_no_unverified_id_can_be_selected(self):
        with self.assertRaises(ValueError):
            self.make([999999])

    def test_fractional_fixture_id_is_rejected(self):
        with self.assertRaises(ValueError):
            self.make([9001.5])

    def test_repeated_fixture_ids_are_deduplicated(self):
        export = self.make([9001, 9001])
        self.assertEqual(export["sportmonks_fixture_count"], 1)
        self.assertEqual(export["fixture_ids"], [9001])

    def test_fixture_export_count_is_bounded(self):
        with self.assertRaises(ValueError):
            self.make(list(range(1000, 1000 + MAX_SPORTMONKS_CASES + 1)))

    def test_missing_xg_is_unknown_and_flagged(self):
        store_finished_fixture(self.conn, sample_fixture(9002, include_xg=False))
        export = self.make([9002])
        self.assertGreater(export["audit_warning_count"], 0)
        self.assertIn("Not confirmed", export["markdown"])
        self.assertIn("Missing", export["markdown"])
        self.assertIn("Standard xG not recorded", export["markdown"])

    def test_reviewed_same_team_fixture_automatically_appears(self):
        self.conn.execute(
            "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (901, "2024-11-08T18:00:00Z", "Premier League",
             "Example United", "Sample City", 2, 1, "FINISHED"),
        )
        self.assertTrue(
            confirm_link(self.conn, 9001, 901, "unit-tester", True)
        )
        report = build_chatgpt_research_pack(
            self.conn, "Premier League", 2024, "Example United",
        )
        self.assertEqual(report["reviewed_link_count"], 1)
        md = report["markdown"]
        self.assertIn("football-data.org match 901", md)
        self.assertIn("Sportmonks fixture 9001", md)
        self.assertIn("1.72", md)
        self.assertIn("operator-reviewed", md.lower())

    def test_unreviewed_fixture_never_auto_links(self):
        self.conn.execute(
            "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (901, "2024-11-08T18:00:00Z", "Premier League",
             "Example United", "Sample City", 2, 1, "FINISHED"),
        )
        report = build_chatgpt_research_pack(
            self.conn, "Premier League", 2024, "Example United",
        )
        self.assertEqual(report["reviewed_link_count"], 0)
        self.assertIn("No operator-reviewed matching", report["markdown"])

    def test_invalid_historical_completed_rows_are_disclosed(self):
        export = self.make()
        self.assertIn("Excluded team result rows: 1", export["markdown"])
        self.assertIn(
            "Invalid completed results detected in entire database: 1",
            export["markdown"],
        )

    def test_historical_strength_section_is_included(self):
        export = self.make()
        md = export["markdown"]
        self.assertIn("Part A.2: League-Adjusted Historical Goal Indicators", md)
        self.assertIn("Historical league-adjusted team-strength indicators", md)
        self.assertIn("League home goals/match", md)
        self.assertIn("football-data.org match IDs: 701, 702", md)

    def test_xg_section_excludes_unreviewed_fixture(self):
        result = self.make()
        self.assertIn("Part A.3: Reviewed Historical xG Evidence", result["markdown"])
        self.assertEqual(result["reviewed_xg_count"], 0)
        self.assertIn("No goal-minus-xG aggregate", result["markdown"])

    def test_xg_section_uses_operator_reviewed_team_and_both_sides(self):
        self.conn.execute(
            "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (901, "2024-11-08T18:00:00Z", "Premier League",
             "Example United", "Sample City", 2, 1, "FINISHED"),
        )
        confirm_link(self.conn, 9001, 901, "unit-tester", True)
        report = build_chatgpt_research_pack(
            self.conn, "Premier League", 2024, "Example United",
        )
        self.assertEqual(report["reviewed_xg_count"], 1)
        md = report["markdown"]
        self.assertIn("Part A.3: Reviewed Historical xG Evidence", md)
        self.assertIn("1.72", md)
        self.assertIn("0.85", md)
        self.assertIn("901", md)
        self.assertIn("9001", md)

    def test_match_by_match_coverage_is_included_without_unverified_xg(self):
        report = self.make()
        self.assertEqual(report["stored_coverage_count"], 2)
        md = report["markdown"]
        self.assertIn("Part A.4: Match-by-Match Historical Coverage", md)
        self.assertIn("Historical match data coverage", md)
        self.assertIn("701", md)
        self.assertIn("702", md)
        self.assertIn("no_imported_candidate", md)
        self.assertIn("not all fixtures that", md.lower())

    def test_advanced_historical_context_section_is_exported(self):
        report = self.make()
        md = report["markdown"]
        self.assertIn(
            "Part A.5: Advanced Retrospective Research Diagnostics", md
        )
        self.assertIn("Opponent-context descriptive comparisons", md)
        self.assertIn("Reviewed historical xG diagnostic splits", md)
        self.assertIn("Stored valid league matches", md)
        self.assertEqual(report["opponent_context_matches"], 0)
        self.assertIn("Unavailable", md)

    def test_statistical_history_and_sample_uncertainty_export(self):
        pack = self.make()
        md = pack["markdown"]
        self.assertIn(
            "Part A.6: Statistical Research and Sample Uncertainty", md
        )
        self.assertIn("Historical statistical research and uncertainty", md)
        self.assertIn("Historical last-five form", md)
        self.assertIn("Home-win Wilson 95% interval", md)
        self.assertEqual(pack["historical_form_matches"], 0)
        self.assertFalse(pack["xg_bootstrap_available"])
        self.assertIn("Bootstrap 95% interval (match resampling)", md)

    def test_no_external_api_is_required(self):
        export = self.make()
        self.assertIn(
            "no AI or external API request was used", export["markdown"]
        )


if __name__ == "__main__":
    unittest.main()

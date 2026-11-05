"""Offline tests for the one-file historical research export."""
import sqlite3
import unittest

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
        self.assertIn("2 goals scored", md)
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

    def test_invalid_historical_completed_rows_are_disclosed(self):
        export = self.make()
        self.assertIn("Excluded team result rows: 1", export["markdown"])
        self.assertIn(
            "Invalid completed results detected in entire database: 1",
            export["markdown"],
        )

    def test_no_external_api_is_required(self):
        export = self.make()
        self.assertIn(
            "no AI or external API request was used", export["markdown"]
        )


if __name__ == "__main__":
    unittest.main()

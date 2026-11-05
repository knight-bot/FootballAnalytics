"""Offline accuracy and source-provenance tests for research reports."""
import sqlite3
import unittest

from historical_reports import (
    build_sportmonks_report,
    build_team_report,
    list_competitions,
    list_seasons,
    list_sportmonks_fixtures,
    list_teams,
    season_for_date,
)


class ResearchReportTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY, date TEXT, competition TEXT,
                home_team TEXT, away_team TEXT,
                home_goals INTEGER, away_goals INTEGER, status TEXT
            )
        """)
        self.conn.executemany(
            "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
                (10, "2024-06-30T18:00:00Z", "Example League",
                 "Wolves", "Tigers", 2, 1, "FINISHED"),
                (11, "2024-08-03T18:00:00Z", "Example League",
                 "Wolves", "Tigers", 3, 1, "FINISHED"),
                (12, "2025-05-03T18:00:00Z", "Example League",
                 "Tigers", "Wolves", 2, 2, "FINISHED"),
                (13, "2025-07-02T18:00:00Z", "Example League",
                 "Wolves", "Tigers", 5, 0, "FINISHED"),
                (14, "2024-11-02T18:00:00Z", "Another League",
                 "Wolves", "Tigers", 7, 0, "FINISHED"),
                (15, "2024-12-02T18:00:00Z", "Example League",
                 "Wolves", "Tigers", None, None, "SCHEDULED"),
            ],
        )

    def tearDown(self):
        self.conn.close()

    def make_sportmonks_fixture(self, include_xg=True):
        self.conn.executescript("""
            CREATE TABLE sportmonks_historical_fixtures (
                fixture_id INTEGER PRIMARY KEY, name TEXT, match_date TEXT,
                league_id INTEGER, season_id INTEGER, state_id INTEGER,
                stat_records INTEGER, pressure_records INTEGER,
                metric_records INTEGER, imported_at TEXT
            );
            CREATE TABLE sportmonks_historical_teams (
                fixture_id INTEGER, name TEXT, location TEXT
            );
            CREATE TABLE sportmonks_historical_metrics (
                fixture_id INTEGER, type_id INTEGER, location TEXT, value REAL
            );
            CREATE TABLE sportmonks_historical_statistics (
                fixture_id INTEGER, type_id INTEGER, value REAL
            );
            CREATE TABLE sportmonks_historical_pressure (
                fixture_id INTEGER, minute INTEGER, pressure REAL
            );
        """)
        self.conn.execute(
            "INSERT INTO sportmonks_historical_fixtures VALUES "
            "(999, 'Sampleville vs Others', '2024-08-03 18:00:00', "
            "8, 51, 5, 2, 2, 2, '2025-01-01T00:00:00Z')"
        )
        self.conn.executemany(
            "INSERT INTO sportmonks_historical_teams VALUES (?, ?, ?)", [
                (999, "Sampleville", "home"),
                (999, "Others", "away"),
            ],
        )
        if include_xg:
            self.conn.executemany(
                "INSERT INTO sportmonks_historical_metrics VALUES (?, ?, ?, ?)", [
                    (999, 5304, "home", 1.7),
                    (999, 5304, "away", 0.8),
                ],
            )
        self.conn.executemany(
            "INSERT INTO sportmonks_historical_statistics VALUES (?, ?, ?)", [
                (999, 42, 7),
                (999, 42, 3),
            ],
        )
        self.conn.execute(
            "INSERT INTO sportmonks_historical_pressure VALUES (999, 1, 42)"
        )

    def test_season_grouping_never_crosses_july_window(self):
        self.assertEqual(season_for_date("2024-06-30T18:00Z"), 2023)
        self.assertEqual(season_for_date("2024-07-01T00:00Z"), 2024)
        self.assertIsNone(season_for_date("invalid"))
        self.assertEqual(list_seasons(self.conn, "Example League"), [
            2025, 2024, 2023,
        ])

    def test_team_report_uses_exact_competition_and_season(self):
        report = build_team_report(
            self.conn, "Example League", 2024, "Wolves",
        )
        self.assertEqual(report["summary"]["played"], 2)
        self.assertEqual(report["summary"]["wins"], 1)
        self.assertEqual(report["summary"]["draws"], 1)
        self.assertEqual(report["summary"]["gf"], 5)
        self.assertEqual(report["summary"]["ga"], 3)
        self.assertIn("football-data.org", report["markdown"])
        self.assertIn("| 11 |", report["markdown"])
        self.assertIn("| 12 |", report["markdown"])
        self.assertNotIn("| 13 |", report["markdown"])
        self.assertNotIn("| 14 |", report["markdown"])

    def test_report_options_are_derived_from_real_rows(self):
        self.assertEqual(
            list_competitions(self.conn), ["Another League", "Example League"]
        )
        self.assertEqual(
            list_teams(self.conn, "Example League", 2024), ["Tigers", "Wolves"]
        )

    def test_empty_season_does_not_invent_results(self):
        report = build_team_report(
            self.conn, "Example League", 2020, "Wolves",
        )
        self.assertEqual(report["summary"]["matches"], 0)
        self.assertIn("No valid completed results", report["markdown"])

    def test_sportmonks_fixture_is_separate_and_traceable(self):
        self.make_sportmonks_fixture()
        fixtures = list_sportmonks_fixtures(self.conn)
        self.assertEqual(fixtures[0]["id"], 999)
        report = build_sportmonks_report(self.conn, 999)
        self.assertIn("1.70", report["markdown"])
        self.assertIn("0.80", report["markdown"])
        self.assertIn("Sportmonks fixture ID:** 999", report["markdown"])
        self.assertIn("not been automatically matched", report["markdown"])
        self.assertNotIn("football-data.org match ID: 999", report["markdown"])

    def test_missing_xg_is_not_zero(self):
        self.make_sportmonks_fixture(include_xg=False)
        report = build_sportmonks_report(self.conn, 999)
        self.assertIn("Not confirmed", report["markdown"])
        self.assertNotIn("| Standard xG (type 5304) | 0.00", report["markdown"])

    def test_unknown_fixture_is_rejected(self):
        self.make_sportmonks_fixture()
        with self.assertRaises(ValueError):
            build_sportmonks_report(self.conn, 1000)


if __name__ == "__main__":
    unittest.main()

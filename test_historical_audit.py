"""Offline tests for the read-only historical data audit."""
import sqlite3
import unittest

from historical_audit import audit_database


class HistoricalAuditTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_missing_tables_reported_without_failure(self):
        result = audit_database(self.conn)
        self.assertEqual(result["results_count"], 0)
        self.assertEqual(result["sportmonks_fixtures"], [])
        self.assertTrue(result["checks"])

    def test_completed_results_count_and_invalid_rows(self):
        self.conn.execute("""
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY, date TEXT, competition TEXT,
                home_team TEXT, away_team TEXT, home_goals INTEGER,
                away_goals INTEGER, status TEXT
            )
        """)
        self.conn.executemany("""
            INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (1, "2024-01-01", "Test League", "A", "B", 1, 0, "FINISHED"),
            (2, "2024-01-02", "Test League", "A", "A", 1, 0, "FINISHED"),
            (3, "2024-01-03", "Test League", "A", "B", None, None, "SCHEDULED"),
        ])
        result = audit_database(self.conn)
        self.assertEqual(result["results_count"], 2)
        self.assertEqual(result["invalid_result_rows"], 1)
        self.assertEqual(
            result["competitions"][0]["completed_matches"], 2
        )

    def make_sportmonks_tables(self, raw_stats=2, raw_pressure=2):
        self.conn.executescript("""
            CREATE TABLE sportmonks_historical_fixtures (
                fixture_id INTEGER PRIMARY KEY, name TEXT, match_date TEXT,
                league_id INTEGER, season_id INTEGER, state_id INTEGER,
                stat_records INTEGER, pressure_records INTEGER,
                score_records INTEGER, metric_records INTEGER,
                imported_at TEXT
            );
            CREATE TABLE sportmonks_historical_teams (
                fixture_id INTEGER, participant_id INTEGER, name TEXT
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
        self.conn.execute("""
            INSERT INTO sportmonks_historical_fixtures VALUES
            (10, 'Example Match', '2024-05-01', 8, 1, 5,
             ?, ?, 4, 2, '2024-05-02')
        """, (raw_stats, raw_pressure))
        self.conn.executemany("""
            INSERT INTO sportmonks_historical_teams VALUES (?, ?, ?)
        """, [(10, 100, "Home"), (10, 200, "Away")])
        self.conn.executemany("""
            INSERT INTO sportmonks_historical_metrics VALUES (?, ?, ?, ?)
        """, [(10, 5304, "home", 1.5), (10, 5304, "away", 0.8)])

    def test_complete_fixture_has_no_issue_flags(self):
        self.make_sportmonks_tables()
        self.conn.executemany("""
            INSERT INTO sportmonks_historical_statistics VALUES (?, ?, ?)
        """, [(10, 86, 6), (10, 86, 3)])
        self.conn.executemany("""
            INSERT INTO sportmonks_historical_pressure VALUES (?, ?, ?)
        """, [(10, 1, 40), (10, 2, 65)])
        result = audit_database(self.conn)
        fixture = result["sportmonks_fixtures"][0]
        self.assertEqual(fixture["issue_count"], 0)
        self.assertEqual(fixture["standard_xg_home"], 1.5)
        self.assertEqual(fixture["standard_xg_away"], 0.8)

    def test_raw_records_not_saved_are_flagged(self):
        self.make_sportmonks_tables(raw_stats=84, raw_pressure=190)
        result = audit_database(self.conn)
        fixture = result["sportmonks_fixtures"][0]
        self.assertGreater(fixture["issue_count"], 0)
        self.assertIn("Statistics returned but no numeric", fixture["issues"])
        self.assertIn("Pressure returned but no minute", fixture["issues"])


if __name__ == "__main__":
    unittest.main()

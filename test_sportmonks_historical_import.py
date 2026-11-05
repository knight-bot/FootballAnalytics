"""Offline checks for the completed-fixture Sportmonks importer."""
import sqlite3
import unittest

from sportmonks_historical_import import (
    ensure_schema,
    store_finished_fixture,
)


def sample_fixture():
    return {
        "id": 19872618,
        "name": "Example Historical Fixture",
        "starting_at": "2025-04-15 18:00:00",
        "league_id": 8,
        "season_id": 222,
        "state_id": 5,
        "statistics": [
            {"id": 1, "type_id": 42, "participant_id": 10,
             "location": "home", "data": {"value": 14}},
            {"id": 2, "type_id": 86, "participant_id": 20,
             "location": "away", "data": {"value": 5}},
        ],
        "pressure": [
            {"id": 100, "participant_id": 10, "minute": 1, "pressure": 37.5},
            {"id": 101, "participant_id": 20, "minute": 1, "pressure": 41.0},
        ],
        "scores": [{"id": 1}],
        "participants": [
            {"id": 10, "name": "Example Home", "meta": {"location": "home"}},
            {"id": 20, "name": "Example Away", "meta": {"location": "away"}},
        ],
        "xgfixture": [
            {"type_id": 5304, "participant_id": 10,
             "location": "home", "data": {"value": 1.72}},
            {"type_id": 5304, "participant_id": 20,
             "location": "away", "data": {"value": 0.89}},
        ],
    }


class HistoricalImportTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE matches (match_id INTEGER PRIMARY KEY)")
        self.conn.execute("INSERT INTO matches VALUES (42)")
        ensure_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_inserts_expected_metrics_without_changing_existing_matches(self):
        fixture = sample_fixture()
        self.assertTrue(store_finished_fixture(self.conn, fixture))
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM sportmonks_historical_metrics"
            ).fetchone()[0], 2
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM sportmonks_historical_statistics"
            ).fetchone()[0], 2
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM sportmonks_historical_pressure"
            ).fetchone()[0], 2
        )
        self.assertEqual(
            self.conn.execute("SELECT match_id FROM matches").fetchone()[0],
            42,
        )

    def test_reimport_replaces_metrics_without_duplicates(self):
        fixture = sample_fixture()
        store_finished_fixture(self.conn, fixture)
        fixture["xgfixture"] = fixture["xgfixture"][:1]
        fixture["statistics"] = fixture["statistics"][:1]
        fixture["pressure"] = fixture["pressure"][:1]
        store_finished_fixture(self.conn, fixture)
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM sportmonks_historical_fixtures"
            ).fetchone()[0], 1
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM sportmonks_historical_metrics"
            ).fetchone()[0], 1
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM sportmonks_historical_statistics"
            ).fetchone()[0], 1
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM sportmonks_historical_pressure"
            ).fetchone()[0], 1
        )

    def test_missing_arrays_do_not_erase_existing_records(self):
        fixture = sample_fixture()
        store_finished_fixture(self.conn, fixture)
        fixture["statistics"] = []
        fixture["pressure"] = []
        fixture["xgfixture"] = []
        store_finished_fixture(self.conn, fixture)
        for table in (
            "sportmonks_historical_metrics",
            "sportmonks_historical_statistics",
            "sportmonks_historical_pressure",
        ):
            count = self.conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            self.assertEqual(count, 2)

    def test_skips_unfinished_fixtures(self):
        fixture = sample_fixture()
        fixture["state_id"] = 1
        self.assertFalse(store_finished_fixture(self.conn, fixture))
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM sportmonks_historical_fixtures"
            ).fetchone()[0], 0
        )


if __name__ == "__main__":
    unittest.main()

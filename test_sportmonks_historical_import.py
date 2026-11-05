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
        "statistics": [{"id": 1}, {"id": 2}],
        "pressure": [{"id": 1}],
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
            self.conn.execute("SELECT match_id FROM matches").fetchone()[0],
            42,
        )

    def test_reimport_replaces_metrics_without_duplicates(self):
        fixture = sample_fixture()
        store_finished_fixture(self.conn, fixture)
        fixture["xgfixture"] = fixture["xgfixture"][:1]
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

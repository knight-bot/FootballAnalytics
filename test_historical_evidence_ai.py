"""Offline evidence and AI-response validation; never calls paid APIs."""
import json
import sqlite3
import unittest

from historical_ai import (
    HistoricalAIError, explain_historical_evidence, validate_response,
)
from historical_evidence import (
    offline_review, sportmonks_evidence, team_evidence,
)


class EvidenceBuilderTests(unittest.TestCase):
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
                (10, "2024-08-01T19:00:00Z", "Example League",
                 "North", "South", 2, 0, "FINISHED"),
                (11, "2024-09-01T19:00:00Z", "Example League",
                 "South", "North", 1, 1, "FINISHED"),
                (12, "2024-10-01T19:00:00Z", "Example League",
                 "North", "South", None, None, "FINISHED"),
                (13, "2024-11-01T19:00:00Z", "Example League",
                 "North", "South", 4, 0, "SCHEDULED"),
                (14, "2025-07-01T19:00:00Z", "Example League",
                 "North", "South", 7, 0, "FINISHED"),
            ],
        )

    def tearDown(self):
        self.conn.close()

    def test_grouped_team_evidence_contains_precise_source_match_ids(self):
        pack = team_evidence(
            self.conn, "Example League", 2024, "North",
        )
        self.assertEqual(pack["selection"]["match_count"], 2)
        evidence = {item["id"]: item for item in pack["evidence"]}
        self.assertEqual(evidence["FD_OVERALL"]["match_ids"], [10, 11])
        self.assertEqual(evidence["FD_HOME"]["match_ids"], [10])
        self.assertEqual(evidence["FD_AWAY"]["match_ids"], [11])
        self.assertIn("1 wins", evidence["FD_OVERALL"]["fact"])
        self.assertIn("1 draws", evidence["FD_OVERALL"]["fact"])
        self.assertNotIn("7 goals", evidence["FD_OVERALL"]["fact"])
        self.assertTrue(any("excluded" in x for x in pack["limitations"]))

    def test_offline_mode_never_generates_unreferenced_claims(self):
        pack = team_evidence(
            self.conn, "Example League", 2024, "North",
        )
        review = offline_review(pack)
        known = {item["id"] for item in pack["evidence"]}
        self.assertTrue(review["observations"])
        self.assertTrue(all(
            set(row["evidence_ids"]).issubset(known)
            for row in review["observations"]
        ))

    def test_no_matches_generate_no_observations(self):
        pack = team_evidence(
            self.conn, "Example League", 2012, "North",
        )
        self.assertEqual(pack["evidence"], [])
        self.assertEqual(offline_review(pack)["observations"], [])

    def test_completed_sportmonks_xg_is_source_specific(self):
        self.conn.executescript("""
            CREATE TABLE sportmonks_historical_fixtures (
                fixture_id INTEGER PRIMARY KEY, name TEXT, match_date TEXT,
                state_id INTEGER, stat_records INTEGER,
                pressure_records INTEGER, metric_records INTEGER,
                imported_at TEXT
            );
            CREATE TABLE sportmonks_historical_teams (
                fixture_id INTEGER, name TEXT, location TEXT
            );
            CREATE TABLE sportmonks_historical_metrics (
                fixture_id INTEGER, type_id INTEGER, location TEXT, value REAL
            );
        """)
        self.conn.execute(
            "INSERT INTO sportmonks_historical_fixtures VALUES "
            "(333, 'East vs West', '2024-11-01', 5, 4, 20, 2, '2025-01-01')"
        )
        self.conn.executemany(
            "INSERT INTO sportmonks_historical_teams VALUES (?, ?, ?)",
            [(333, "East", "home"), (333, "West", "away")]
        )
        self.conn.executemany(
            "INSERT INTO sportmonks_historical_metrics VALUES (?, ?, ?, ?)",
            [(333, 5304, "home", 1.8), (333, 5304, "away", 0.7)]
        )
        pack = sportmonks_evidence(self.conn, 333)
        evidence = {item["id"]: item for item in pack["evidence"]}
        self.assertEqual(evidence["SM_5304_HOME"]["fixture_id"], 333)
        self.assertIn("1.80", evidence["SM_5304_HOME"]["fact"])
        self.assertIn("0.70", evidence["SM_5304_AWAY"]["fact"])
        self.assertTrue(all(
            item["source"] == "Sportmonks Football API v3"
            for item in pack["evidence"]
        ))


class FakeResponse:
    ok = True
    status_code = 200

    def __init__(self, output):
        self.output = output

    def json(self):
        return {
            "status": "completed",
            "output": [{"type": "message", "content": [{
                "type": "output_text",
                "text": json.dumps(self.output),
            }]}],
        }


class FakeSession:
    def __init__(self, output):
        self.output = output
        self.last_request = None

    def post(self, url, **kwargs):
        self.last_request = {"url": url, **kwargs}
        return FakeResponse(self.output)


class AIReviewTests(unittest.TestCase):
    def setUp(self):
        self.pack = {
            "title": "Example historical research",
            "source": "football-data.org",
            "selection": {},
            "evidence": [{
                "id": "FD_OVERALL",
                "fact": "Two recorded matches, one win and one draw.",
                "source": "football-data.org",
                "match_ids": [10, 11],
                "title": "Season evidence",
            }],
            "limitations": ["Recorded matches only."],
        }

    def test_valid_ai_response_preserves_all_local_caveats(self):
        output = {
            "observations": [{
                "text": "The team recorded one win and one draw.",
                "evidence_ids": ["FD_OVERALL"],
            }],
            "limitations": [],
        }
        result = validate_response(self.pack, output)
        self.assertEqual(result["mode"], "ai_assisted")
        self.assertIn("Recorded matches only.", result["limitations"])

    def test_hallucinated_citation_is_rejected(self):
        output = {
            "observations": [{
                "text": "Unverified claim",
                "evidence_ids": ["FAKE_MATCH_999"],
            }],
            "limitations": [],
        }
        with self.assertRaises(HistoricalAIError):
            validate_response(self.pack, output)

    def test_no_api_key_prevents_any_network_action(self):
        with self.assertRaises(HistoricalAIError):
            explain_historical_evidence(self.pack, "", session=FakeSession({}))

    def test_model_request_is_stateless_and_cites_existing_evidence(self):
        model_output = {
            "observations": [{
                "text": "One win and one draw were recorded.",
                "evidence_ids": ["FD_OVERALL"],
            }],
            "limitations": ["Sample size is small."],
        }
        fake = FakeSession(model_output)
        result = explain_historical_evidence(
            self.pack, "private_test_token", session=fake,
        )
        self.assertEqual(result["observations"][0]["evidence_ids"],
                         ["FD_OVERALL"])
        self.assertFalse(fake.last_request["json"]["store"])
        self.assertNotIn("tools", fake.last_request["json"])
        self.assertIn("json_schema",
                      fake.last_request["json"]["text"]["format"]["type"])
        self.assertEqual(
            fake.last_request["json"]["max_output_tokens"], 900
        )


if __name__ == "__main__":
    unittest.main()

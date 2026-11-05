"""Offline pagination, safety and database tests for historical discovery.

All sample fixtures are fictional completed games. No API calls are made.
"""
import sqlite3
import unittest
from datetime import date

from sportmonks_historical_batch import (
    BASE, MAX_PER_PAGE, discover_completed, parse_config, run_batch,
)


class FakeResponse:
    status_code = 200
    ok = True

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeSession:
    """Simulates two discovery pages and per-fixture enrichment requests."""

    def __init__(self, pages=None):
        self.calls = []
        self.pages = pages or [
            [
                {"id": 101, "state_id": 5, "league_id": 8,
                 "starting_at": "2025-09-13 15:00:00"},
                {"id": 102, "state_id": 1, "league_id": 8,
                 "starting_at": "2025-09-13 15:00:00"},
                {"id": 103, "state_id": 5, "league_id": 999,
                 "starting_at": "2025-09-13 15:00:00"},
            ],
            [
                {"id": 104, "state_id": 5, "league_id": 8,
                 "starting_at": "2025-09-14 13:00:00"},
                {"id": 101, "state_id": 5, "league_id": 8,
                 "starting_at": "2025-09-13 15:00:00"},
            ],
        ]

    def get(self, url, *, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params})
        if "/between/" in url:
            page = params["page"]
            data = self.pages[page-1] if page <= len(self.pages) else []
            return FakeResponse({
                "data": data,
                "pagination": {
                    "current_page": page,
                    "per_page": MAX_PER_PAGE,
                    "has_more": page < len(self.pages),
                },
            })
        fixture_id = int(url.split("/")[-1])
        return FakeResponse({"data": {
            "id": fixture_id,
            "name": f"Example Home vs Example Away {fixture_id}",
            "league_id": 8,
            "season_id": 12345,
            "state_id": 5,
            "starting_at": (
                "2025-09-13 15:00:00" if fixture_id == 101
                else "2025-09-14 13:00:00"
            ),
            "participants": [
                {"id": 10, "name": "Example Home",
                 "meta": {"location": "home"}},
                {"id": 20, "name": "Example Away",
                 "meta": {"location": "away"}},
            ],
            "statistics": [
                {"type_id": 42, "participant_id": 10,
                 "location": "home", "data": {"value": 10}},
            ],
            "pressure": [],
            "scores": [],
            "xgfixture": [
                {"type_id": 5304, "participant_id": 10,
                 "location": "home", "data": {"value": 1.5}},
                {"type_id": 5304, "participant_id": 20,
                 "location": "away", "data": {"value": 0.7}},
            ],
        }})


def config(limit=5):
    return {
        "start": date(2025, 9, 13),
        "end": date(2025, 9, 14),
        "league_id": 8,
        "limit": limit,
        "refresh_existing": False,
    }


class BatchDiscoveryTests(unittest.TestCase):
    def test_date_and_subscription_guards(self):
        parsed = parse_config({
            "HISTORY_START_DATE": "2025-09-13",
            "HISTORY_END_DATE": "2025-09-14",
            "HISTORY_LEAGUE_ID": "8",
            "HISTORY_MAX_FIXTURES": "5",
        }, today=date(2026, 11, 5))
        self.assertEqual(parsed["limit"], 5)
        with self.assertRaises(ValueError):
            parse_config({
                "HISTORY_START_DATE": "2026-11-01",
                "HISTORY_END_DATE": "2026-11-02",
            }, today=date(2026, 11, 5))
        with self.assertRaises(ValueError):
            parse_config({
                "HISTORY_START_DATE": "2025-01-01",
                "HISTORY_END_DATE": "2025-02-01",
            }, today=date(2026, 11, 5))
        with self.assertRaises(ValueError):
            parse_config({
                "HISTORY_START_DATE": "2025-09-13",
                "HISTORY_END_DATE": "2025-09-14",
                "HISTORY_LEAGUE_ID": "999",
            }, today=date(2026, 11, 5))

    def test_pages_are_followed_and_only_completed_league_games_included(self):
        session = FakeSession()
        ids = discover_completed(session, "dummy_token", config())
        self.assertEqual(ids, [101, 104])
        self.assertEqual(len(session.calls), 2)
        self.assertTrue(all(
            call["params"]["filters"] == "fixtureLeagues:8"
            for call in session.calls
        ))
        self.assertTrue(all(
            "api_token" not in call["url"] for call in session.calls
        ))

    def test_discovery_requires_valid_pagination_metadata(self):
        session = FakeSession()
        def malformed(url, *, params=None, headers=None, timeout=None):
            return FakeResponse({"data": [], "pagination": {}})
        session.get = malformed
        with self.assertRaises(RuntimeError):
            discover_completed(session, "dummy_token", config())

    def test_discovery_rejects_unbounded_pagination(self):
        pages = [[{"id": 100 + page, "state_id": 5, "league_id": 8,
                   "starting_at": "2025-09-13 15:00:00"}]
                 for page in range(6)]
        with self.assertRaises(RuntimeError):
            discover_completed(FakeSession(pages), "dummy_token", config())

    def test_imports_numeric_historical_data_without_touching_results(self):
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                "CREATE TABLE matches (match_id INTEGER PRIMARY KEY)"
            )
            conn.execute("INSERT INTO matches VALUES (7777)")
            session = FakeSession()
            outcome = run_batch(session, "dummy_token", conn, config())
            self.assertEqual(outcome["discovered"], 2)
            self.assertEqual(outcome["imported"], 2)
            saved = conn.execute(
                "SELECT COUNT(*) FROM sportmonks_historical_fixtures"
            ).fetchone()[0]
            self.assertEqual(saved, 2)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM sportmonks_historical_metrics"
            ).fetchone()[0], 4)
            self.assertEqual(conn.execute(
                "SELECT match_id FROM matches"
            ).fetchone()[0], 7777)
        finally:
            conn.close()

    def test_second_run_skips_previously_saved_and_respects_limit(self):
        conn = sqlite3.connect(":memory:")
        try:
            first = run_batch(
                FakeSession(), "dummy_token", conn, config(limit=1)
            )
            self.assertEqual(first["imported"], 1)
            self.assertEqual(first["remaining"], 1)
            second = run_batch(
                FakeSession(), "dummy_token", conn, config(limit=1)
            )
            self.assertEqual(second["imported"], 1)
            self.assertEqual(second["remaining"], 0)
            third = run_batch(
                FakeSession(), "dummy_token", conn, config(limit=1)
            )
            self.assertEqual(third["selected"], 0)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM sportmonks_historical_fixtures"
            ).fetchone()[0], 2)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()

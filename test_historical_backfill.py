"""Offline deterministic tests for resumable historical data backfills.

Provider fixture responses are invented and requests never reach the web.
"""
import sqlite3
import unittest
from datetime import date

from historical_backfill import (
    MAX_RANGE_DAYS, backfill_markdown, historical_windows,
    parse_backfill_config, run_backfill, safe_import_failure,
)
from test_sportmonks_historical_batch import FakeSession


def config(start="2025-09-01", end="2025-09-30", budget=20):
    return {
        "start": date.fromisoformat(start),
        "end": date.fromisoformat(end),
        "budget": budget,
        "league_id": 8,
    }


class BackfillTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE matches (match_id INTEGER PRIMARY KEY)")
        self.db.execute("INSERT INTO matches VALUES (501)")

    def tearDown(self):
        self.db.close()

    def test_window_split_is_disjoint_and_bounded(self):
        spans = list(historical_windows(
            date(2025, 9, 1), date(2025, 10, 1)
        ))
        self.assertEqual(spans, [
            (date(2025, 9, 1), date(2025, 9, 14)),
            (date(2025, 9, 15), date(2025, 9, 28)),
            (date(2025, 9, 29), date(2025, 10, 1)),
        ])

    def test_config_rejects_unbounded_and_recent_intervals(self):
        c = parse_backfill_config({
            "BACKFILL_START_DATE":"2025-09-01",
            "BACKFILL_END_DATE":"2025-10-01",
            "BACKFILL_MAX_FIXTURES":"30",
        }, today=date(2026, 11, 6))
        self.assertEqual(c["budget"], 30)
        for start, end, cap in (
            ("2026-11-04","2026-11-05","10"),
            ("2025-01-01","2025-04-01","10"),
            ("2025-09-01","2025-09-15","31"),
            ("2025-09-01","2025-09-15","0"),
        ):
            with self.subTest(start=start, end=end, cap=cap):
                with self.assertRaises(ValueError):
                    parse_backfill_config({
                        "BACKFILL_START_DATE": start,
                        "BACKFILL_END_DATE": end,
                        "BACKFILL_MAX_FIXTURES": cap,
                    }, today=date(2026, 11, 6))

    def test_no_fixtures_before_season_then_imports_next_window(self):
        # The Premier League began on 2025-08-15, so the preceding
        # 2025-08-01..14 window can legitimately have zero league games.
        from test_sportmonks_historical_batch import FakeResponse

        class FirstWindowEmpty(FakeSession):
            def get(self, url, *, params=None, headers=None, timeout=None):
                if "/between/2025-08-01/2025-08-14" in url:
                    return FakeResponse({"data": []})
                if "/between/2025-08-15/2025-08-28" in url:
                    return FakeResponse({
                        "data": [{
                            "id": 101, "state_id": 5, "league_id": 8,
                            "starting_at": "2025-08-15 19:00:00",
                        }],
                        "pagination": {
                            "current_page": 1, "has_more": False,
                        },
                    })
                response = super().get(
                    url, params=params, headers=headers, timeout=timeout
                )
                if isinstance(response.payload, dict) and isinstance(
                    response.payload.get("data"), dict
                ):
                    response.payload["data"]["starting_at"] = (
                        "2025-08-15 19:00:00"
                    )
                return response

        report = run_backfill(
            FirstWindowEmpty(), "dummy_token", self.db,
            config(start="2025-08-01", end="2025-08-28", budget=10),
        )
        self.assertFalse(report["has_error"])
        self.assertTrue(report["complete_requested_range"])
        self.assertEqual(report["windows_completed"], 2)
        self.assertEqual(report["enrichment_requests"], 1)
        self.assertEqual(report["newly_imported"], 1)
        self.assertEqual(
            [(x["discovered"], x["imported"]) for x in report["windows"]],
            [(0, 0), (1, 1)],
        )

    def test_one_window_stores_and_then_skips_same_ids(self):
        # Synthetic fixtures within the first window.
        rows = [
            {"id":101, "state_id":5, "league_id":8,
             "starting_at":"2025-09-13 15:00:00"},
        ]
        session = FakeSession(pages=[rows])
        result = run_backfill(
            session, "dummy", self.db,
            config(end="2025-09-14", budget=10)
        )
        self.assertFalse(result["has_error"])
        self.assertEqual(result["enrichment_requests"],1)
        self.assertEqual(result["newly_imported"],1)
        self.assertTrue(result["complete_requested_range"])
        again = run_backfill(
            FakeSession(pages=[rows]), "dummy", self.db,
            config(end="2025-09-14", budget=10)
        )
        self.assertEqual(again["newly_imported"],0)
        self.assertEqual(again["enrichment_requests"],0)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM sportmonks_historical_fixtures"
        ).fetchone()[0],1)
        self.assertEqual(self.db.execute(
            "SELECT match_id FROM matches"
        ).fetchone()[0],501)

    def test_budget_resumes_earliest_incomplete_window(self):
        fixtures = [
            {"id":100+i, "state_id":5, "league_id":8,
             "starting_at":"2025-09-13 15:00:00"}
            for i in range(3)
        ]
        class FixtureSession(FakeSession):
            def get(self, url, **kw):
                if "/between/" in url:
                    return super().get(url, **kw)
                # Simulate enriched result for three fixture IDs.
                response = super().get(url, **kw)
                return response
        # FakeSession returns state 5 for all IDs.
        sample=FixtureSession(pages=[fixtures])
        first=run_backfill(sample, "dummy", self.db,
                           config(end="2025-09-14",budget=2))
        self.assertEqual(first["enrichment_requests"],2)
        self.assertFalse(first["complete_requested_range"])
        second=run_backfill(FixtureSession(pages=[fixtures]),"dummy",
                            self.db,config(end="2025-09-14",budget=2))
        self.assertEqual(second["enrichment_requests"],1)
        self.assertTrue(second["complete_requested_range"])

    def test_error_rolls_back_failed_window_and_keeps_checkpoint(self):
        rows=[{"id":101,"state_id":5,"league_id":8,
               "starting_at":"2025-09-13 15:00:00"}]
        class FailSecondWindow(FakeSession):
            def get(self,url,**kw):
                if "/between/2025-09-15/" in url:
                    raise RuntimeError("synthetic provider outage")
                return super().get(url,**kw)
        report=run_backfill(
            FailSecondWindow(pages=[rows]),"dummy",self.db,
            config(start="2025-09-01",end="2025-09-20")
        )
        self.assertTrue(report["has_error"])
        self.assertEqual(report["windows_completed"],1)
        self.assertEqual(report["newly_imported"],1)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM sportmonks_historical_fixtures"
        ).fetchone()[0],1)
        self.assertIn("Error after checkpoint",backfill_markdown(report))
        self.assertNotIn("dummy",report["error"])

    def test_later_fixture_error_preserves_prior_committed_fixture(self):
        data = [
            {"id":101, "state_id":5, "league_id":8,
             "starting_at":"2025-09-13 15:00:00"},
            {"id":104, "state_id":5, "league_id":8,
             "starting_at":"2025-09-14 13:00:00"},
        ]
        class LateFailure(FakeSession):
            def get(self,url,**kw):
                if url.endswith("/104"):
                    raise RuntimeError("synthetic later fixture failure")
                return super().get(url,**kw)
        report=run_backfill(
            LateFailure(pages=[data]),"dummy",self.db,
            config(start="2025-09-13",end="2025-09-14")
        )
        self.assertTrue(report["has_error"])
        self.assertEqual(report["partial_saved_on_error"],1)
        self.assertEqual(report["newly_imported"],1)
        self.assertEqual(report["windows_completed"],0)
        self.assertEqual(self.db.execute(
            "SELECT fixture_id FROM sportmonks_historical_fixtures"
        ).fetchall(),[(101,)])
        resumed=run_backfill(
            FakeSession(pages=[data]),"dummy",self.db,
            config(start="2025-09-13",end="2025-09-14")
        )
        self.assertFalse(resumed["has_error"])
        self.assertEqual(resumed["newly_imported"],1)
        self.assertTrue(resumed["complete_requested_range"])

    def test_safe_error_category_preserves_status_but_not_sensitive_payload(self):
        cases = [
            (RuntimeError("Historical discovery failed with HTTP 403. Check API permissions or rate limits; no tokens were logged."), "HTTP 403"),
            (RuntimeError("Historical discovery failed with HTTP 401. Check subscription."), "HTTP 401"),
            (RuntimeError("Historical discovery failed with HTTP 429."), "HTTP 429"),
            (RuntimeError("Incomplete discovery response; refusing to assume all historical pages were retrieved."), "omitted required data"),
            (RuntimeError("Discovery exceeds the page safety limit."), "shorter date window"),
            (RuntimeError("Could not access Sportmonks discovery endpoint."), "Network error"),
        ]
        for exc, expected in cases:
            with self.subTest(message=str(exc)):
                self.assertIn(expected, safe_import_failure(exc))
        text = safe_import_failure(RuntimeError(
            "provider x?token=SECRET&password=SECRET"
        ))
        self.assertNotIn("SECRET", text)
        self.assertIn("Unexpected historical import failure", text)

    def test_rate_limit_is_reported_without_credentials(self):
        class RateLimitedSession(FakeSession):
            def get(self,url,**kw):
                if "/between/" in url:
                    response = super().get(url,**kw)
                    response.ok = False
                    response.status_code = 429
                    return response
                return super().get(url,**kw)
        report=run_backfill(
            RateLimitedSession(),"dummy-secret",self.db,
            config(end="2025-09-14")
        )
        self.assertTrue(report["has_error"])
        self.assertIn("HTTP 429",report["error"])
        self.assertNotIn("dummy-secret",report["error"])
        self.assertEqual(report["newly_imported"],0)

    def test_empty_range_has_no_fabricated_imports(self):
        report=run_backfill(
            FakeSession(pages=[[]]),"dummy",self.db,
            config(end="2025-09-14",budget=20)
        )
        self.assertEqual(report["enrichment_requests"],0)
        self.assertEqual(report["newly_imported"],0)
        self.assertTrue(report["complete_requested_range"])


if __name__ == "__main__":
    unittest.main()

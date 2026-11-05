"""Offline safety and coverage tests for historical import planning.

No HTTP requests, API tokens, or actual import workflow actions.
"""
import sqlite3
import unittest
from datetime import date, datetime

from confirm_historical_link import confirm_link
from historical_import_planner import (
    import_plan_markdown, plan_historical_imports,
)
from sportmonks_historical_import import ensure_schema, store_finished_fixture


def fixture(fid, when, home, away, home_xg=1.2, away_xg=0.8):
    xg_rows = []
    for side, pid, value in (
        ("home", 101, home_xg), ("away", 202, away_xg)
    ):
        if value is not None:
            xg_rows.append({
                "type_id": 5304,
                "location": side,
                "participant_id": pid,
                "data": {"value": value},
            })
    return {
        "id": fid,
        "name": f"{home} vs {away}",
        "starting_at": when,
        "league_id": 8,
        "season_id": 2024,
        "state_id": 5,
        "scores": [],
        "statistics": [],
        "pressure": [],
        "participants": [
            {"id": 101, "name": home, "meta": {"location": "home"}},
            {"id": 202, "name": away, "meta": {"location": "away"}},
        ],
        "xgfixture": xg_rows,
    }


class ImportPlannerTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY,
                date TEXT,
                competition TEXT,
                home_team TEXT,
                away_team TEXT,
                home_goals INTEGER,
                away_goals INTEGER,
                status TEXT
            )
        """)
        matches = [
            (1, "2024-08-01T14:00:00Z", "Premier League",
             "Arsenal FC", "Everton FC", 2, 1, "FINISHED"),
            (2, "2024-08-10T14:00:00Z", "Premier League",
             "Everton FC", "Arsenal FC", 0, 2, "FINISHED"),
            (3, "2024-08-17T14:00:00Z", "Premier League",
             "Arsenal FC", "Liverpool FC", 1, 1, "FINISHED"),
            (4, "2024-08-21T14:00:00Z", "Premier League",
             "Liverpool FC", "Arsenal FC", 3, 1, "FINISHED"),
            (5, "2024-09-06T14:00:00Z", "Premier League",
             "Arsenal FC", "Chelsea FC", 1, 0, "FINISHED"),
            (6, "2025-08-03T14:00:00Z", "Premier League",
             "Arsenal FC", "Chelsea FC", 4, 1, "FINISHED"),
            (7, "2024-08-04T14:00:00Z", "Other League",
             "Arsenal FC", "Chelsea FC", 2, 0, "FINISHED"),
            (8, "2024-09-10T14:00:00Z", "Premier League",
             "Arsenal FC", "Chelsea FC", 3, 2, "SCHEDULED"),
        ]
        self.conn.executemany(
            "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)", matches
        )
        ensure_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def plan(self, first=2024, **kwargs):
        return plan_historical_imports(
            self.conn, "Premier League", first,
            max_windows=kwargs.pop("max_windows", 6),
            as_of_date=kwargs.pop("as_of_date", date(2026, 11, 5)),
            **kwargs,
        )

    def test_groups_into_bounded_windows_with_actual_missing_dates(self):
        p = self.plan()
        self.assertEqual(p["unmatched_eligible"], 5)
        self.assertEqual(p["total_windows"], 3)
        self.assertEqual(p["shown_windows"], 3)
        windows = sorted(p["windows"], key=lambda w: w["start_date"])
        self.assertEqual(
            [(w["start_date"], w["end_date"]) for w in windows],
            [
                ("2024-08-01", "2024-08-10"),
                ("2024-08-17", "2024-08-21"),
                ("2024-09-06", "2024-09-06"),
            ],
        )
        self.assertEqual(
            [w["source_match_ids"] for w in windows],
            [[1, 2], [3, 4], [5]],
        )
        for w in windows:
            length = (date.fromisoformat(w["end_date"]) -
                      date.fromisoformat(w["start_date"])).days + 1
            self.assertLessEqual(length, 14)
            self.assertGreaterEqual(length, 1)

    def test_highest_coverage_first_and_oldest_tie_break(self):
        p = self.plan()
        self.assertEqual(
            [w["source_match_ids"] for w in p["windows"]],
            [[1, 2], [3, 4], [5]],
        )
        self.assertEqual([w["priority"] for w in p["windows"]],
                         [1, 2, 3])

    def test_limit_only_hides_extra_windows_not_targets(self):
        p = self.plan(max_windows=1)
        self.assertEqual(p["shown_windows"], 1)
        self.assertEqual(p["omitted_windows"], 2)
        self.assertEqual(p["unmatched_eligible"], 5)
        self.assertEqual(p["windows"][0]["local_missing_results"], 2)

    def test_existing_candidate_requires_review_not_new_discovery(self):
        store_finished_fixture(self.conn, fixture(
            9001, "2024-08-01 14:00:00", "Arsenal", "Everton"
        ))
        p = self.plan()
        self.assertEqual(p["review_candidates"], 1)
        self.assertEqual(p["unmatched_eligible"], 4)
        self.assertNotIn(
            1, [mid for w in p["windows"] for mid in w["source_match_ids"]]
        )
        self.assertEqual(p["review_queue"][0]["match_id"], 1)

    def test_reviewed_fixture_with_xg_is_counted_not_reimported(self):
        store_finished_fixture(self.conn, fixture(
            9001, "2024-08-01 14:00:00", "Arsenal", "Everton"
        ))
        confirm_link(self.conn, 9001, 1, "reviewer", True)
        p = self.plan()
        self.assertEqual(p["already_reviewed_with_xg"], 1)
        self.assertEqual(p["review_candidates"], 0)
        self.assertEqual(p["unmatched_eligible"], 4)

    def test_reviewed_missing_xg_is_separate_source_investigation(self):
        store_finished_fixture(self.conn, fixture(
            9001, "2024-08-01 14:00:00", "Arsenal", "Everton",
            home_xg=1.2, away_xg=None,
        ))
        confirm_link(self.conn, 9001, 1, "reviewer", True)
        p = self.plan()
        self.assertEqual(p["reviewed_missing_xg_count"], 1)
        self.assertEqual(p["missing_xg_queue"][0]["match_id"], 1)
        self.assertEqual(p["unmatched_eligible"], 4)

    def test_stale_review_is_not_silently_reimported_or_joined(self):
        store_finished_fixture(self.conn, fixture(
            9001, "2024-08-01 14:00:00", "Arsenal", "Everton"
        ))
        confirm_link(self.conn, 9001, 1, "reviewer", True)
        self.conn.execute(
            "UPDATE sportmonks_historical_teams SET name='Unknown'"
            " WHERE fixture_id=9001 AND location='home'"
        )
        p = self.plan()
        self.assertEqual(p["manual_resolution_count"], 1)
        self.assertEqual(p["unmatched_eligible"], 4)
        self.assertEqual(p["manual_resolution_queue"][0]["match_id"], 1)

    def test_duplicates_are_ambiguous_and_excluded_from_discovery(self):
        store_finished_fixture(self.conn, fixture(
            9001, "2024-08-01 14:00:00", "Arsenal", "Everton"
        ))
        store_finished_fixture(self.conn, fixture(
            9002, "2024-08-01 14:00:00", "Arsenal", "Everton"
        ))
        p = self.plan()
        self.assertEqual(p["manual_resolution_count"], 1)
        self.assertEqual(p["unmatched_eligible"], 4)

    def test_historical_age_cutoff_is_enforced(self):
        self.conn.executemany(
            "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)", [
                (20, "2026-10-22T14:00:00Z", "Premier League",
                 "A", "B", 1, 1, "FINISHED"),
                (21, "2026-10-23T14:00:00Z", "Premier League",
                 "A", "C", 1, 1, "FINISHED"),
            ],
        )
        p = self.plan(first=2026)
        self.assertEqual(p["last_eligible_date"], "2026-10-22")
        self.assertEqual(p["unmatched_eligible"], 1)
        self.assertEqual(p["unmatched_too_recent"], 1)
        self.assertEqual(p["windows"][0]["source_match_ids"], [20])
        self.assertEqual(p["unmatched_too_recent_ids"], [21])

    def test_wrong_competition_or_configuration_rejected(self):
        for args in (
            {"competition": "Other League", "start_year": 2024},
            {"competition": "Premier League", "start_year": True},
            {"competition": "Premier League", "start_year": 1800},
            {"competition": "Premier League", "start_year": 2024,
             "max_windows": 0},
            {"competition": "Premier League", "start_year": 2024,
             "max_windows": 13},
            {"competition": "Premier League", "start_year": 2024,
             "max_windows": True},
            {"competition": "Premier League", "start_year": 2024,
             "as_of_date": datetime(2026, 11, 5)},
        ):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    plan_historical_imports(self.conn, **args)

    def test_empty_window_does_not_invent_data(self):
        p = self.plan(first=2022)
        self.assertEqual(p["valid_stored_results"], 0)
        self.assertEqual(p["total_windows"], 0)
        self.assertEqual(p["review_candidates"], 0)
        self.assertEqual(p["unmatched_eligible"], 0)

    def test_markdown_explicitly_disclaims_provider_mapping(self):
        p = self.plan(max_windows=2)
        report = import_plan_markdown(p)
        self.assertIn("Historical Sportmonks Import Gap Plan", report)
        self.assertIn("2024-08-01", report)
        self.assertIn("1, 2", report)
        self.assertIn("original final scores", report)
        self.assertIn("No import window exceeds 14", report)

    def test_read_only_no_changes_to_original_tables(self):
        before = self.conn.iterdump()
        snapshot_before = list(before)
        self.plan()
        snapshot_after = list(self.conn.iterdump())
        self.assertEqual(snapshot_before, snapshot_after)


if __name__ == "__main__":
    unittest.main()

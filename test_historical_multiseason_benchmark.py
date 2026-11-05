"""Offline regression tests for rolling-origin retrospective historical folds."""
import sqlite3
import unittest
from datetime import date, datetime
from historical_multiseason_benchmark import (
    evaluate_historical_seasons, multiseason_markdown,
    paired_heldout_delta_interval,
)


class MultiSeasonTests(unittest.TestCase):
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
            "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)", [
                (101, "2022-08-01", "Demo League", "Alpha", "Beta", 2, 1, "FINISHED"),
                (102, "2023-02-01", "Demo League", "Beta", "Alpha", 1, 1, "FINISHED"),
                (201, "2023-08-01", "Demo League", "Alpha", "Beta", 1, 2, "FINISHED"),
                (202, "2024-02-01", "Demo League", "Beta", "Alpha", 3, 1, "FINISHED"),
                (301, "2024-08-01", "Demo League", "Alpha", "Beta", 4, 1, "FINISHED"),
                (302, "2024-10-01", "Demo League", "Beta", "Alpha", 1, 2, "FINISHED"),
                (303, "2025-03-01", "Demo League", "Alpha", "Beta", 2, 0, "FINISHED"),
                (401, "2025-08-01", "Demo League", "Alpha", "Beta", 0, 1, "FINISHED"),
                (402, "2026-02-01", "Demo League", "Beta", "Alpha", 1, 2, "FINISHED"),
                (403, "2025-10-01", "Other League", "Alpha", "Beta", 9, 9, "FINISHED"),
                (404, "2025-10-02", "Demo League", "Alpha", "Beta", 10, 10, "SCHEDULED"),
            ],
        )

    def tearDown(self):
        self.conn.close()

    def evaluate(self, first=2023, last=2025, **kwargs):
        return evaluate_historical_seasons(
            self.conn, "Demo League", first, last,
            lookback_seasons=kwargs.pop("lookback_seasons", 1),
            shrinkage=kwargs.pop("shrinkage", 5),
            min_train=kwargs.pop("min_train", 2),
            min_test=kwargs.pop("min_test", 2),
            as_of_date=kwargs.pop("as_of_date", date(2026, 8, 1)),
            **kwargs,
        )

    def test_several_seasons_are_evaluated_once_each(self):
        result = self.evaluate()
        self.assertEqual(result["seasons_included"], 3)
        self.assertEqual(result["seasons_skipped"], 0)
        self.assertEqual(result["heldout_matches"], 7)
        self.assertEqual(
            result["heldout_match_ids"],
            [201, 202, 301, 302, 303, 401, 402],
        )
        self.assertEqual(
            [r["train_matches"] for r in result["by_season"]],
            [2, 2, 3],
        )
        self.assertEqual(
            [r["test_matches"] for r in result["by_season"]],
            [2, 3, 2],
        )

    def test_pooled_mae_weights_by_matches_not_equal_seasons(self):
        result = self.evaluate()
        rows = result["by_season"]
        expected = sum(
            r["baseline_mae"] * r["test_matches"] for r in rows
        ) / 7
        self.assertAlmostEqual(result["pooled_baseline"]["mae"], expected)
        expected_adjusted = sum(
            r["adjusted_mae"] * r["test_matches"] for r in rows
        ) / 7
        self.assertAlmostEqual(
            result["pooled_adjusted"]["mae"], expected_adjusted
        )
        self.assertAlmostEqual(
            result["pooled_mae_delta"],
            expected_adjusted - expected,
        )
        self.assertEqual(
            result["pooled_baseline"]["team_goal_observations"], 14
        )

    def test_later_holdout_is_not_used_in_earlier_fold(self):
        first = self.evaluate()
        self.conn.execute(
            "UPDATE matches SET home_goals=14 WHERE match_id=301"
        )
        second = self.evaluate()
        self.assertEqual(
            first["by_season"][0]["baseline_mae"],
            second["by_season"][0]["baseline_mae"],
        )
        self.assertNotEqual(
            first["by_season"][1]["baseline_mae"],
            second["by_season"][1]["baseline_mae"],
        )
        # 2024 can legally become 2025's training set.
        self.assertNotEqual(
            first["by_season"][2]["baseline_mae"],
            second["by_season"][2]["baseline_mae"],
        )

    def test_in_progress_season_is_excluded_without_evaluation(self):
        result = self.evaluate(
            first=2025, last=2026, as_of_date=date(2026, 11, 5)
        )
        self.assertEqual(result["seasons_included"], 1)
        self.assertEqual(result["seasons_skipped"], 1)
        self.assertEqual(result["by_season"][1]["status"], "skipped")
        self.assertIn(
            "not ended", result["by_season"][1]["reason"]
        )

    def test_weak_coverage_is_excluded_not_averaged_in(self):
        r = self.evaluate(min_train=3, min_test=3)
        self.assertEqual(r["seasons_included"], 0)
        self.assertEqual(r["heldout_matches"], 0)
        self.assertIsNone(r["pooled_baseline"])
        self.assertIsNone(r["pooled_mae_delta"])
        self.assertEqual(r["seasons_skipped"], 3)

    def test_missing_training_history_is_reported(self):
        self.conn.execute("DELETE FROM matches WHERE match_id IN (101, 102)")
        result = self.evaluate()
        self.assertEqual(result["seasons_skipped"], 1)
        self.assertIn(
            "No valid completed earlier-season",
            result["by_season"][0]["reason"],
        )
        self.assertEqual(result["seasons_included"], 2)

    def test_missing_test_history_is_reported(self):
        self.conn.execute("DELETE FROM matches WHERE match_id IN (301,302,303)")
        result = self.evaluate()
        self.assertEqual(result["by_season"][1]["status"], "skipped")
        self.assertIn(
            "No valid completed held-out",
            result["by_season"][1]["reason"],
        )

    def test_invalid_configuration_rejected(self):
        bad = [
            dict(first=2026, last=2025),
            dict(first=2010, last=2020),
            dict(first=True, last=2025),
            dict(min_train=0),
            dict(min_test=False),
            dict(as_of_date="2026-08-01"),
            dict(as_of_date=datetime(2026,8,1)),
            dict(shrinkage=0),
            dict(lookback_seasons=6),
        ]
        for args in bad:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    self.evaluate(**args)

    def test_no_future_fixture_results_are_loaded(self):
        result = self.evaluate()
        self.assertNotIn(404, result["heldout_match_ids"])
        self.assertNotIn(403, result["heldout_match_ids"])
        self.assertNotIn(101, result["heldout_match_ids"])

    def test_markdown_includes_source_ids_and_skipped_rows(self):
        result = self.evaluate(
            first=2024, last=2026, as_of_date=date(2026, 11, 5)
        )
        md = multiseason_markdown(result)
        self.assertIn("2024/25", md)
        self.assertIn("2025/26", md)
        self.assertIn("2026/27", md)
        self.assertIn("skipped", md)
        self.assertIn("301, 302, 303, 401, 402", md)
        self.assertIn("Goal RMSE", md)
        self.assertIn("Pooled MAE difference", md)

    def test_sensitivity_is_withheld_on_short_holdout(self):
        result = self.evaluate()
        self.assertIsNone(result["paired_mae_delta_bootstrap95"])
        self.assertIsNotNone(result["leave_one_season_out_delta_range"])
        low, high = result["leave_one_season_out_delta_range"]
        self.assertLessEqual(low, high)
        md = multiseason_markdown(result)
        self.assertIn("Paired held-out match bootstrap 95% interval", md)
        self.assertIn("Leave-one-held-out-season-out", md)

    def test_match_paired_bootstrap_is_deterministic(self):
        rows = [
            {"league_absolute_error": 2.0,
             "adjusted_absolute_error": 1.25 + (i % 2) * .1}
            for i in range(50)
        ]
        a = paired_heldout_delta_interval(rows)
        self.assertEqual(a, paired_heldout_delta_interval(rows))
        self.assertLess(a[1], 0)
        self.assertIsNone(paired_heldout_delta_interval(rows[:49]))

    def test_one_year_only_does_not_claim_year_robustness(self):
        result = self.evaluate(first=2024, last=2024)
        self.assertEqual(result["seasons_included"], 1)
        self.assertIsNone(result["leave_one_season_out_delta_range"])
        self.assertIsNone(result["paired_mae_delta_bootstrap95"])

    def test_input_database_remains_unchanged(self):
        before = self.conn.execute(
            "SELECT COUNT(*), SUM(home_goals) FROM matches"
        ).fetchone()
        self.evaluate()
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*), SUM(home_goals) FROM matches"
            ).fetchone(), before,
        )

    def test_default_thresholds_warn_on_tiny_dataset(self):
        result = evaluate_historical_seasons(
            self.conn, "Demo League", 2023, 2025,
            lookback_seasons=1,
            as_of_date=date(2026,8,1),
        )
        self.assertEqual(result["seasons_included"], 0)
        self.assertEqual(result["seasons_skipped"], 3)
        self.assertIsNone(result["pooled_adjusted"])


if __name__ == "__main__":
    unittest.main()

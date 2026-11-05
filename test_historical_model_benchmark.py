"""Offline tests for strictly retrospective chronological goal-model evaluation."""
import sqlite3
import unittest
from historical_model_benchmark import (
    run_historical_benchmark, benchmark_markdown,
)


class HistoricalBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY,
                date TEXT, competition TEXT, home_team TEXT, away_team TEXT,
                home_goals INTEGER, away_goals INTEGER, status TEXT
            )
        """)
        rows = [
            # Training season 2023/24: four completed games.
            (10, "2023-08-12T16:00:00Z", "Example League",
             "Alpha", "Beta", 2, 1, "FINISHED"),
            (11, "2023-09-02T16:00:00Z", "Example League",
             "Beta", "Alpha", 1, 2, "FINISHED"),
            (12, "2024-01-02T16:00:00Z", "Example League",
             "Alpha", "Beta", 3, 0, "FINISHED"),
            (13, "2024-03-02T16:00:00Z", "Example League",
             "Beta", "Alpha", 2, 2, "FINISHED"),
            # Strictly held-out season 2024/25
            (20, "2024-09-01T16:00:00Z", "Example League",
             "Alpha", "Beta", 0, 1, "FINISHED"),
            (21, "2025-03-01T16:00:00Z", "Example League",
             "Beta", "Alpha", 1, 0, "FINISHED"),
            # Outside scope
            (22, "2024-10-01T16:00:00Z", "Other League",
             "Alpha", "Beta", 15, 10, "FINISHED"),
            (23, "2024-10-02T16:00:00Z", "Example League",
             "Alpha", "Beta", 15, 10, "SCHEDULED"),
            (24, "2025-07-01T16:00:00Z", "Example League",
             "Alpha", "Beta", 10, 10, "FINISHED"),
        ]
        self.conn.executemany(
            "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)", rows,
        )

    def tearDown(self):
        self.conn.close()

    def run_test(self, lookback=1, shrinkage=5):
        return run_historical_benchmark(
            self.conn, "Example League", 2024, lookback, shrinkage,
        )

    def test_only_prior_years_train_and_later_games_test(self):
        r = self.run_test()
        self.assertEqual(r["train_matches"], 4)
        self.assertEqual(r["test_matches"], 2)
        self.assertEqual(r["train_match_ids"], [10, 11, 12, 13])
        self.assertEqual(r["heldout_match_ids"], [20, 21])
        self.assertEqual(r["train_window"], ("2023-07-01", "2024-07-01"))
        self.assertEqual(r["test_window"], ("2024-07-01", "2025-07-01"))

    def test_league_averages_are_from_training_only(self):
        r = self.run_test()
        self.assertAlmostEqual(r["league_home_baseline"], 2.0)
        self.assertAlmostEqual(r["league_away_baseline"], 1.25)
        # Held-out outcomes are low scoring, never used to fit the means.
        self.assertEqual([row["home_goals"] for row in r["rows"]], [0, 1])
        self.assertAlmostEqual(r["rows"][0]["league_home_estimated"], 2.0)

    def test_holdout_score_changes_do_not_affect_training_model(self):
        a = self.run_test()
        self.conn.execute(
            "UPDATE matches SET home_goals=8, away_goals=6 "
            "WHERE match_id=20"
        )
        b = self.run_test()
        for old, new in zip(a["rows"], b["rows"]):
            self.assertEqual(
                old["adjusted_home_estimated"],
                new["adjusted_home_estimated"],
            )
            self.assertEqual(
                old["adjusted_away_estimated"],
                new["adjusted_away_estimated"],
            )
        self.assertNotEqual(
            a["team_adjusted"]["mae"], b["team_adjusted"]["mae"]
        )

    def test_error_metrics_are_mathematically_consistent(self):
        r = self.run_test()
        baseline = r["league_baseline"]
        # Held-out goal observations: 0,1,1,0 versus 2,1.25,2,1.25.
        expected_mae = (2 + .25 + 1 + 1.25) / 4
        self.assertAlmostEqual(baseline["mae"], expected_mae)
        self.assertAlmostEqual(
            baseline["rmse"],
            ((2**2 + .25**2 + 1**2 + 1.25**2)/4)**0.5,
        )
        self.assertAlmostEqual(
            r["mae_change_adjusted_minus_baseline"],
            r["team_adjusted"]["mae"] - baseline["mae"],
        )
        self.assertEqual(baseline["team_goal_observations"], 4)

    def test_training_outlier_affects_only_fitted_parameters(self):
        a = self.run_test()
        self.conn.execute(
            "UPDATE matches SET home_goals=7 WHERE match_id=10"
        )
        b = self.run_test()
        self.assertNotEqual(
            a["league_home_baseline"], b["league_home_baseline"]
        )
        self.assertEqual(a["heldout_match_ids"], b["heldout_match_ids"])

    def test_unknown_team_defaults_to_training_league(self):
        self.conn.execute(
            "INSERT INTO matches VALUES "
            "(25,'2024-12-01','Example League','Newcomer','Beta',1,0,'FINISHED')"
        )
        r = self.run_test()
        self.assertEqual(r["unseen_team_matches"], 1)
        self.assertTrue(
            any("not seen in the training" in warning
                for warning in r["warnings"])
        )
        self.assertEqual(len(r["rows"]), 3)

    def test_invalid_result_rows_excluded_and_reported(self):
        self.conn.executemany(
            "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",
            [
                (30, "2023-12-02", "Example League",
                 "Alpha", "Beta", -1, 2, "FINISHED"),
                (31, "2024-12-02", "Example League",
                 "Alpha", "Beta", None, 2, "FINISHED"),
            ],
        )
        r = self.run_test()
        self.assertEqual(r["excluded_train_ids"], [30])
        self.assertEqual(r["excluded_test_ids"], [31])
        self.assertEqual(r["train_matches"], 4)
        self.assertEqual(r["test_matches"], 2)

    def test_no_training_or_holdout_rejected(self):
        with self.assertRaisesRegex(ValueError, "earlier-season"):
            run_historical_benchmark(self.conn, "Example League", 2023, 1)
        with self.assertRaisesRegex(ValueError, "held-out"):
            run_historical_benchmark(self.conn, "Example League", 2026, 1)

    def test_bad_config_is_rejected(self):
        for lookback in (0, 6, True, "2"):
            with self.subTest(lookback=lookback):
                with self.assertRaises(ValueError):
                    self.run_test(lookback=lookback)
        for shrinkage in (0, 21, False, "5"):
            with self.subTest(shrinkage=shrinkage):
                with self.assertRaises(ValueError):
                    self.run_test(shrinkage=shrinkage)
        with self.assertRaises(ValueError):
            run_historical_benchmark(
                self.conn, "Example League", 2099, 1
            )

    def test_zero_goal_training_baseline_rejected(self):
        self.conn.execute(
            "UPDATE matches SET away_goals=0 "
            "WHERE date<'2024-07-01'"
        )
        with self.assertRaisesRegex(ValueError, "zero"):
            self.run_test()

    def test_report_includes_source_ids_and_warnings(self):
        r = self.run_test()
        md = benchmark_markdown(r)
        self.assertIn("10, 11, 12, 13", md)
        self.assertIn("20, 21", md)
        self.assertIn("Goal MAE", md)
        self.assertIn("Held-out season:** 2024/25", md)
        self.assertIn("No live or future-match results", md)
        self.assertNotIn("Sportmonks", md)


if __name__ == "__main__":
    unittest.main()

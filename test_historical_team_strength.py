"""Purely offline checks for retrospective historical goal-strength indices."""
import sqlite3
import unittest

from historical_team_strength import (
    analyze_season, strength_markdown, team_strength,
)


class HistoricalStrengthTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY,
                date TEXT, competition TEXT, home_team TEXT, away_team TEXT,
                home_goals INTEGER, away_goals INTEGER, status TEXT
            )
        """)
        self.conn.executemany(
            "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
                (1, "2024-08-01T15:00:00Z", "Example League",
                 "A", "B", 2, 0, "FINISHED"),
                (2, "2024-08-02T15:00:00Z", "Example League",
                 "B", "A", 1, 1, "FINISHED"),
                (3, "2024-08-03T15:00:00Z", "Example League",
                 "C", "A", 0, 3, "FINISHED"),
                (4, "2024-08-04T15:00:00Z", "Example League",
                 "A", "C", 0, 2, "FINISHED"),
                (5, "2025-07-01T15:00:00Z", "Example League",
                 "A", "B", 12, 0, "FINISHED"),
                (6, "2024-08-05T15:00:00Z", "Other League",
                 "A", "B", 10, 0, "FINISHED"),
                (7, "2024-08-06T15:00:00Z", "Example League",
                 "A", "B", 20, 0, "SCHEDULED"),
            ],
        )

    def tearDown(self):
        self.conn.close()

    def make(self, prior=4):
        return analyze_season(
            self.conn, "Example League", 2024, prior_matches=prior
        )

    def test_only_finished_same_competition_and_july_year(self):
        a = self.make()
        self.assertEqual(a["matches"], 4)
        self.assertEqual(a["excluded"], 0)
        self.assertEqual(a["match_ids"], [1, 2, 3, 4])
        self.assertEqual(a["season"], "2024/25")
        self.assertEqual(a["date_first"], "2024-08-01")
        self.assertEqual(a["date_last"], "2024-08-04")

    def test_league_home_away_overall_baselines(self):
        a = self.make()
        self.assertAlmostEqual(a["league_home_goals_per_match"], 0.75)
        self.assertAlmostEqual(a["league_away_goals_per_match"], 1.5)
        self.assertAlmostEqual(a["league_goals_per_team_match"], 1.125)

    def test_team_indices_correctly_use_scoring_and_conceding(self):
        a = self.make()
        team = team_strength(a, "A")
        overall = team["scopes"]["overall"]
        self.assertEqual(overall["played"], 4)
        self.assertEqual(overall["goals_for"], 6)
        self.assertEqual(overall["goals_against"], 3)
        self.assertEqual(overall["points"], 7)
        self.assertAlmostEqual(overall["attack_index"], 4/3)
        self.assertAlmostEqual(overall["defense_index"], 2/3)

    def test_home_venue_compares_different_league_baselines(self):
        scope = team_strength(self.make(), "A")["scopes"]["home"]
        self.assertEqual(scope["played"], 2)
        self.assertEqual(scope["goals_for"], 2)
        self.assertEqual(scope["goals_against"], 2)
        self.assertAlmostEqual(scope["attack_baseline"], 0.75)
        self.assertAlmostEqual(scope["defense_baseline"], 1.5)
        self.assertAlmostEqual(scope["attack_index"], 4/3)
        self.assertAlmostEqual(scope["defense_index"], 2/3)
        self.assertAlmostEqual(scope["attack_shrunk"], 5/4.5)
        self.assertAlmostEqual(scope["defense_shrunk"], 8/9)

    def test_away_venue_reverses_baselines(self):
        scope = team_strength(self.make(), "A")["scopes"]["away"]
        self.assertEqual(scope["played"], 2)
        self.assertEqual(scope["goals_for"], 4)
        self.assertEqual(scope["goals_against"], 1)
        self.assertAlmostEqual(scope["attack_baseline"], 1.5)
        self.assertAlmostEqual(scope["defense_baseline"], 0.75)
        self.assertAlmostEqual(scope["attack_index"], 4/3)
        self.assertAlmostEqual(scope["defense_index"], 2/3)

    def test_pseudo_matches_shrink_towards_one(self):
        raw = team_strength(self.make(0), "A")["scopes"]["overall"]
        shrink = team_strength(self.make(10), "A")["scopes"]["overall"]
        self.assertAlmostEqual(raw["attack_index"], raw["attack_shrunk"])
        self.assertGreater(raw["attack_shrunk"], shrink["attack_shrunk"])
        self.assertGreater(shrink["attack_shrunk"], 1)
        self.assertLess(raw["defense_shrunk"], shrink["defense_shrunk"])
        self.assertLess(shrink["defense_shrunk"], 1)

    def test_zero_baselines_are_undefined_not_zero(self):
        self.conn.execute("DELETE FROM matches")
        self.conn.execute(
            "INSERT INTO matches VALUES "
            "(10, '2024-09-01', 'Example League', 'A', 'B', 0, 0, 'FINISHED')"
        )
        a = self.make()
        row = team_strength(a, "A")["scopes"]["home"]
        self.assertIsNone(row["attack_index"])
        self.assertIsNone(row["defense_shrunk"])
        self.assertTrue(any("zero" in x.lower() for x in a["warnings"]))

    def test_no_recorded_games_does_not_invent_teams(self):
        a = analyze_season(self.conn, "Example League", 2022)
        self.assertEqual(a["matches"], 0)
        self.assertEqual(a["teams"], [])
        self.assertIsNone(a["league_home_goals_per_match"])

    def test_malformed_results_are_excluded_and_counted(self):
        self.conn.executemany(
            "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
                (8, "2024-13-09", "Example League",
                 "A", "B", 1, 1, "FINISHED"),
                (9, "2024-08-09", "Example League",
                 "A", "B", None, 1, "FINISHED"),
                (10, "2024-08-10", "Example League",
                 "A", "A", 1, 1, "FINISHED"),
                (11, "2024-08-11", "Example League",
                 "", "B", 1, 0, "FINISHED"),
            ],
        )
        a = self.make()
        self.assertEqual(a["matches"], 4)
        self.assertEqual(a["excluded"], 4)
        self.assertEqual(a["excluded_match_ids"], [9, 10, 11, 8])
        self.assertTrue(any("excluded" in x for x in a["warnings"]))

    def test_invalid_shrinkage_is_rejected(self):
        for v in (-1, 21, float("nan"), float("inf"), True, "5"):
            with self.subTest(prior=v):
                with self.assertRaises(ValueError):
                    self.make(v)

    def test_venue_sample_flags_are_separate(self):
        scope = team_strength(self.make(), "A")["scopes"]["home"]
        self.assertEqual(scope["sample_flag"], "Small sample")
        self.assertEqual(scope["played"], 2)

    def test_other_teams_and_source_provenance(self):
        a = self.make()
        self.assertEqual([t["name"] for t in a["teams"]], ["A", "B", "C"])
        markdown = strength_markdown(a, "A")
        self.assertIn("football-data.org match IDs: 1, 2, 3, 4", markdown)
        self.assertIn("Attack shrunk", markdown)
        self.assertIn("not predictions", markdown.lower())
        self.assertNotIn("Sportmonks fixture ID:", markdown)

    def test_unknown_team_does_not_invent_data(self):
        a = self.make()
        self.assertIsNone(team_strength(a, "Unrecorded"))
        self.assertIn("No valid recorded matches", strength_markdown(a, "Unrecorded"))


if __name__ == "__main__":
    unittest.main()

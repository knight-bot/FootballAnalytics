"""Offline source-provenance tests for historical standard xG analysis."""
import sqlite3
import unittest

from confirm_historical_link import confirm_link
from historical_xg_analysis import (
    analyze_team_xg, imported_xg_coverage, team_xg_markdown,
)
from sportmonks_historical_import import ensure_schema, store_finished_fixture


def fake_fixture(fid, when, home, away, xg_home, xg_away):
    metrics = []
    for pid, side, value in ((10, "home", xg_home),
                              (20, "away", xg_away)):
        if value is not None:
            metrics.append({
                "type_id": 5304, "participant_id": pid, "location": side,
                "data": {"value": value},
            })
    return {
        "id": fid,
        "name": f"{home} vs {away}",
        "starting_at": when,
        "league_id": 8,
        "season_id": 2024,
        "state_id": 5,
        "statistics": [],
        "pressure": [],
        "scores": [],
        "participants": [
            {"id": 10, "name": home, "meta": {"location": "home"}},
            {"id": 20, "name": away, "meta": {"location": "away"}},
        ],
        "xgfixture": metrics,
    }


class StandardXgTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY, date TEXT, competition TEXT,
                home_team TEXT, away_team TEXT, home_goals INTEGER,
                away_goals INTEGER, status TEXT
            )
        """)
        self.conn.executemany(
            "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",
            [
                (201, "2024-10-01T14:00:00Z", "Premier League",
                 "Arsenal FC", "Everton FC", 2, 1, "FINISHED"),
                (202, "2024-11-01T14:00:00Z", "Premier League",
                 "Everton FC", "Arsenal FC", 0, 3, "FINISHED"),
                (203, "2024-12-01T14:00:00Z", "Premier League",
                 "Arsenal FC", "Newcastle United FC", 1, 1, "FINISHED"),
                (204, "2025-08-01T14:00:00Z", "Premier League",
                 "Arsenal FC", "Everton FC", 6, 0, "FINISHED"),
                (205, "2024-09-01T14:00:00Z", "Other League",
                 "Arsenal FC", "Everton FC", 9, 0, "FINISHED"),
                (206, "2024-09-02T14:00:00Z", "Premier League",
                 "Arsenal FC", "Everton FC", 8, 0, "SCHEDULED"),
            ],
        )
        ensure_schema(self.conn)
        store_finished_fixture(self.conn, fake_fixture(
            9001, "2024-10-01 14:00:00",
            "Arsenal", "Everton", 1.4, 0.8,
        ))
        store_finished_fixture(self.conn, fake_fixture(
            9002, "2024-11-01 14:00:00",
            "Everton", "Arsenal", 0.7, None,
        ))
        store_finished_fixture(self.conn, fake_fixture(
            9003, "2024-12-01 14:00:00",
            "Arsenal", "Newcastle United", 1.1, 1.3,
        ))

    def tearDown(self):
        self.conn.close()

    def run_team(self, team="Arsenal FC", year=2024,
                 competition="Premier League"):
        return analyze_team_xg(self.conn, competition, year, team)

    def test_imported_coverage_is_not_the_full_league(self):
        cover = imported_xg_coverage(self.conn)
        self.assertEqual(cover["imported"], 3)
        self.assertEqual(cover["complete_both_sides"], 2)
        self.assertEqual(cover["partial_one_side"], 1)
        self.assertEqual(cover["missing_both_sides"], 0)
        self.assertEqual(
            {r["sportmonks_id"] for r in cover["rows"]},
            {9001, 9002, 9003},
        )

    def test_unreviewed_candidates_never_join(self):
        result = self.run_team()
        self.assertEqual(result["valid_completed"], 3)
        self.assertEqual(result["reviewed_links"], 0)
        self.assertEqual(result["xg_complete_links"], 0)
        self.assertEqual(result["unreviewed_or_stale"], 3)
        self.assertIsNone(result["total_xg_for"])
        self.assertIsNone(result["goals_minus_xg"])
        self.assertIn("No goal-minus-xG aggregate", team_xg_markdown(result))

    def test_one_reviewed_pair_has_correct_arithmetic_and_source_ids(self):
        self.assertTrue(confirm_link(self.conn, 9001, 201, "reviewer", True))
        result = self.run_team()
        self.assertEqual(result["reviewed_links"], 1)
        self.assertEqual(result["xg_complete_links"], 1)
        self.assertEqual(result["total_goals_for"], 2)
        self.assertEqual(result["total_goals_against"], 1)
        self.assertAlmostEqual(result["total_xg_for"], 1.4)
        self.assertAlmostEqual(result["total_xg_against"], .8)
        self.assertAlmostEqual(result["goals_minus_xg"], .6)
        self.assertAlmostEqual(result["conceded_minus_xga"], .2)
        row, = result["match_rows"]
        self.assertEqual((row["match_id"], row["sportmonks_id"]), (201, 9001))
        self.assertEqual(row["venue"], "Home")
        self.assertAlmostEqual(row["xg_difference"], .6)
        md = team_xg_markdown(result)
        self.assertIn("9001", md)
        self.assertIn("201", md)
        self.assertIn("1.40", md)

    def test_second_reviewed_match_with_missing_xg_is_excluded(self):
        confirm_link(self.conn, 9001, 201, "reviewer", True)
        confirm_link(self.conn, 9002, 202, "reviewer", True)
        result = self.run_team()
        self.assertEqual(result["reviewed_links"], 2)
        self.assertEqual(result["xg_complete_links"], 1)
        self.assertEqual(result["reviewed_missing_xg"], 1)
        self.assertEqual(result["total_goals_for"], 2)
        self.assertEqual(result["excluded_reviewed_rows"][0]["match_id"], 202)

    def test_reviewed_away_match_respects_team_side(self):
        store_finished_fixture(self.conn, fake_fixture(
            9002, "2024-11-01 14:00:00",
            "Everton", "Arsenal", .7, 1.9,
        ))
        confirm_link(self.conn, 9002, 202, "reviewer", True)
        result = self.run_team()
        self.assertEqual(result["xg_complete_links"], 1)
        row, = result["match_rows"]
        self.assertEqual(row["venue"], "Away")
        self.assertEqual((row["goals_for"], row["goals_against"]), (3, 0))
        self.assertAlmostEqual(row["xg_for"], 1.9)
        self.assertAlmostEqual(row["xg_against"], .7)

    def test_duplicate_side_metrics_are_not_silently_averaged(self):
        confirm_link(self.conn, 9001, 201, "reviewer", True)
        self.conn.execute("""
            INSERT INTO sportmonks_historical_metrics
            (fixture_id, type_id, location, participant_id, value)
            VALUES (9001, 5304, 'home', 999, 100)
        """)
        result = self.run_team()
        self.assertEqual(result["reviewed_missing_xg"], 1)
        self.assertIsNone(result["total_xg_for"])
        self.assertEqual(imported_xg_coverage(
            self.conn
        )["complete_both_sides"], 1)

    def test_negative_and_wrong_participant_metrics_are_invalid(self):
        confirm_link(self.conn, 9001, 201, "reviewer", True)
        self.conn.execute(
            "UPDATE sportmonks_historical_metrics SET value=-1 "
            "WHERE fixture_id=9001 AND location='home'"
        )
        self.assertEqual(self.run_team()["xg_complete_links"], 0)
        self.conn.execute(
            "UPDATE sportmonks_historical_metrics "
            "SET value=1.4, participant_id=999 "
            "WHERE fixture_id=9001 AND location='home'"
        )
        self.assertEqual(self.run_team()["xg_complete_links"], 0)

    def test_stale_review_is_excluded_after_team_change(self):
        confirm_link(self.conn, 9001, 201, "reviewer", True)
        self.conn.execute(
            "UPDATE sportmonks_historical_teams "
            "SET name='Wrong Team' WHERE fixture_id=9001 "
            "AND location='home'"
        )
        result = self.run_team()
        self.assertEqual(result["reviewed_links"], 0)
        self.assertEqual(result["xg_complete_links"], 0)

    def test_wrong_year_and_competition_excluded(self):
        confirm_link(self.conn, 9001, 201, "reviewer", True)
        self.assertEqual(self.run_team(year=2025)["xg_complete_links"], 0)
        self.assertEqual(self.run_team(
            competition="Other League"
        )["xg_complete_links"], 0)
        self.assertEqual(self.run_team(team="Everton FC")["xg_complete_links"], 1)

    def test_missing_sportmonks_tables_do_not_create_xg(self):
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("""
                CREATE TABLE matches (
                    match_id INTEGER PRIMARY KEY, date TEXT, competition TEXT,
                    home_team TEXT, away_team TEXT, home_goals INTEGER,
                    away_goals INTEGER, status TEXT
                )
            """)
            conn.execute(
                "INSERT INTO matches VALUES "
                "(1,'2024-09-01','Premier League','A','B',1,0,'FINISHED')"
            )
            self.assertEqual(imported_xg_coverage(conn)["imported"], 0)
            result = analyze_team_xg(conn, "Premier League", 2024, "A")
            self.assertEqual(result["reviewed_links"], 0)
            self.assertIsNone(result["total_xg_for"])
        finally:
            conn.close()

    def test_bad_selection_rejected(self):
        for competition, team in (("", "Arsenal FC"),
                                  ("Premier League", "")):
            with self.assertRaises(ValueError):
                self.run_team(team=team, competition=competition)


if __name__ == "__main__":
    unittest.main()

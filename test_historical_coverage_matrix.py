"""Offline provenance and coverage-regression tests for historical fixture audit."""
import sqlite3
import unittest

from confirm_historical_link import confirm_link
from historical_coverage_matrix import (
    LINK_STATUSES, coverage_matrix, coverage_markdown,
)
from sportmonks_historical_import import ensure_schema, store_finished_fixture


def example_fixture(fid, date, home, away, home_xg, away_xg):
    metric_rows = []
    for pid, side, value in (
        (10, "home", home_xg), (20, "away", away_xg)
    ):
        if value is not None:
            metric_rows.append({
                "type_id": 5304, "location": side,
                "participant_id": pid, "data": {"value": value},
            })
    return {
        "id": fid, "name": f"{home} vs {away}",
        "starting_at": date, "state_id": 5,
        "league_id": 8, "season_id": 2024,
        "scores": [], "statistics": [], "pressure": [],
        "participants": [
            {"id": 10, "name": home, "meta": {"location": "home"}},
            {"id": 20, "name": away, "meta": {"location": "away"}},
        ],
        "xgfixture": metric_rows,
    }


class HistoricalCoverageTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("""
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY, date TEXT, competition TEXT,
                home_team TEXT, away_team TEXT, home_goals INTEGER,
                away_goals INTEGER, status TEXT
            )
        """)
        self.db.executemany(
            "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",
            [
                (201, "2024-10-01T14:00:00Z", "Premier League",
                 "Arsenal FC", "Everton FC", 2, 1, "FINISHED"),
                (202, "2024-11-01T14:00:00Z", "Premier League",
                 "Everton FC", "Arsenal FC", 0, 3, "FINISHED"),
                (203, "2024-12-01T14:00:00Z", "Premier League",
                 "Arsenal FC", "Newcastle United FC", 1, 1, "FINISHED"),
                (204, "2025-08-01T14:00:00Z", "Premier League",
                 "Arsenal FC", "Everton FC", 4, 0, "FINISHED"),
                (205, "2024-10-01T14:00:00Z", "Other League",
                 "Arsenal FC", "Everton FC", 9, 0, "FINISHED"),
                (206, "2024-09-01T14:00:00Z", "Premier League",
                 "Arsenal FC", "Everton FC", 8, 0, "SCHEDULED"),
            ],
        )
        ensure_schema(self.db)
        store_finished_fixture(self.db, example_fixture(
            9001, "2024-10-01 14:00:00",
            "Arsenal", "Everton", 1.4, 0.8,
        ))
        store_finished_fixture(self.db, example_fixture(
            9002, "2024-11-01 14:00:00",
            "Everton", "Arsenal", 0.7, None,
        ))

    def tearDown(self):
        self.db.close()

    def analyze(self, team="Arsenal FC", year=2024, league="Premier League"):
        return coverage_matrix(self.db, league, year, team)

    def test_candidate_is_not_a_verified_xg_join(self):
        result = self.analyze()
        self.assertEqual(result["valid_finished_rows"], 3)
        self.assertEqual(result["reviewed_total"], 0)
        self.assertEqual(result["complete_xg"], 0)
        self.assertEqual(result["status_counts"]["review_candidate"], 2)
        self.assertEqual(result["status_counts"]["no_imported_candidate"], 1)
        self.assertEqual(result["reviewed_pct_of_stored_valid"], 0)
        self.assertEqual(result["complete_xg_pct_of_stored_valid"], 0)
        first = result["rows"][0]
        self.assertEqual(first["review_candidate_sportmonks_id"], 9001)
        self.assertIsNone(first["reviewed_sportmonks_id"])
        self.assertIsNone(first["verified_home_xg"])
        self.assertIsNone(first["verified_away_xg"])

    def test_verified_only_after_operator_attestation(self):
        confirm_link(self.db, 9001, 201, "tester", True)
        result = self.analyze()
        self.assertEqual(result["reviewed_total"], 1)
        self.assertEqual(result["complete_xg"], 1)
        self.assertAlmostEqual(result["reviewed_pct_of_stored_valid"], 100/3)
        self.assertAlmostEqual(result["complete_xg_pct_of_stored_valid"], 100/3)
        first = result["rows"][0]
        self.assertEqual(first["coverage_status"], "reviewed_complete_xg")
        self.assertEqual(first["reviewed_sportmonks_id"], 9001)
        self.assertIsNone(first["review_candidate_sportmonks_id"])
        self.assertAlmostEqual(first["verified_home_xg"], 1.4)
        self.assertAlmostEqual(first["verified_away_xg"], 0.8)

    def test_reviewed_link_with_missing_xg_does_not_claim_coverage(self):
        confirm_link(self.db, 9002, 202, "tester", True)
        result = self.analyze()
        self.assertEqual(result["reviewed_total"], 1)
        self.assertEqual(result["complete_xg"], 0)
        self.assertEqual(result["status_counts"]["reviewed_missing_xg"], 1)
        self.assertIsNone(result["rows"][1]["verified_home_xg"])
        self.assertIsNone(result["rows"][1]["verified_away_xg"])
        self.assertEqual(result["rows"][1]["reviewed_sportmonks_id"], 9002)

    def test_ambiguous_candidates_do_not_auto_join(self):
        store_finished_fixture(self.db, example_fixture(
            9003, "2024-10-01 14:00:00",
            "Arsenal", "Everton", 1.9, 1.5,
        ))
        result = self.analyze()
        self.assertEqual(result["rows"][0]["coverage_status"], "ambiguous")
        self.assertIsNone(result["rows"][0]["verified_home_xg"])
        self.assertIsNone(result["rows"][0]["reviewed_sportmonks_id"])

    def test_stale_review_is_disclosed_without_data_attachment(self):
        confirm_link(self.db, 9001, 201, "tester", True)
        self.db.execute(
            "UPDATE sportmonks_historical_teams SET name='Unknown Town' "
            "WHERE fixture_id=9001 AND location='home'"
        )
        result = self.analyze()
        self.assertEqual(result["status_counts"]["stale_review"], 1)
        self.assertEqual(result["reviewed_total"], 0)
        self.assertEqual(result["complete_xg"], 0)
        self.assertIsNone(result["rows"][0]["verified_home_xg"])

    def test_mismatched_participant_xg_is_missing_not_zero(self):
        confirm_link(self.db, 9001, 201, "tester", True)
        self.db.execute(
            "UPDATE sportmonks_historical_metrics "
            "SET participant_id=999 WHERE fixture_id=9001 "
            "AND location='home' AND type_id=5304"
        )
        result = self.analyze()
        self.assertEqual(result["status_counts"]["reviewed_missing_xg"], 1)
        self.assertIsNone(result["rows"][0]["verified_home_xg"])

    def test_scope_and_status_exclusions(self):
        result = self.analyze()
        self.assertEqual([r["match_id"] for r in result["rows"]],
                         [201, 202, 203])
        next_year = self.analyze(year=2025)
        self.assertEqual([r["match_id"] for r in next_year["rows"]], [204])
        other = self.analyze(league="Other League")
        self.assertEqual([r["match_id"] for r in other["rows"]], [205])
        all_teams = coverage_matrix(self.db, "Premier League", 2024)
        self.assertEqual(all_teams["valid_finished_rows"], 3)

    def test_invalid_finished_rows_are_excluded(self):
        self.db.execute(
            "INSERT INTO matches VALUES "
            "(999,'2024-10-07','Premier League',"
            "'Arsenal FC','Arsenal FC',0,0,'FINISHED')"
        )
        result = self.analyze()
        self.assertEqual(result["stored_finished_rows"], 4)
        self.assertEqual(result["valid_finished_rows"], 3)
        self.assertEqual(result["excluded_match_ids"], [999])

    def test_empty_season_denominators_are_not_misleading(self):
        result = self.analyze(year=2022)
        self.assertEqual(result["valid_finished_rows"], 0)
        self.assertIsNone(result["reviewed_pct_of_stored_valid"])
        self.assertIsNone(result["complete_xg_pct_of_stored_valid"])

    def test_no_imports_still_exposes_missing_coverage(self):
        db = sqlite3.connect(":memory:")
        try:
            db.execute(
                "CREATE TABLE matches ("
                "match_id INTEGER PRIMARY KEY, date TEXT, "
                "competition TEXT, home_team TEXT, away_team TEXT, "
                "home_goals INTEGER, away_goals INTEGER, status TEXT)"
            )
            db.execute(
                "INSERT INTO matches VALUES "
                "(5,'2024-10-01','Premier League','A','B',1,0,'FINISHED')"
            )
            report = coverage_matrix(db, "Premier League", 2024)
            self.assertEqual(report["valid_finished_rows"], 1)
            self.assertEqual(
                report["rows"][0]["coverage_status"],
                "no_imported_candidate",
            )
        finally:
            db.close()

    def test_research_report_preserves_source_id_provenance(self):
        confirm_link(self.db, 9001, 201, "tester", True)
        report = coverage_markdown(self.analyze())
        self.assertIn("Source match ID", report)
        self.assertIn("201", report)
        self.assertIn("9001", report)
        self.assertIn("1.40", report)
        self.assertIn("reviewed_complete_xg", report)
        self.assertIn("not all fixtures", report.lower())

    def test_bad_inputs_rejected(self):
        for comp, team in (("", None), ("Premier League", ""),
                           ("Premier League", 1)):
            with self.subTest(competition=comp, team=team):
                with self.assertRaises(ValueError):
                    coverage_matrix(self.db, comp, 2024, team)
        with self.assertRaises(ValueError):
            self.analyze(year=1800)


if __name__ == "__main__":
    unittest.main()

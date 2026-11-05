"""Offline regression tests of descriptive historical research.

Uses synthetic completed results and synthetic reviewed-xG reports, never
API calls, live fixtures or wagering data.
"""
import sqlite3
import unittest
from datetime import date, datetime, timedelta
from math import isfinite

from historical_statistical_cli import build_scoring_summary
from historical_statistical_research import (
    _boot_mean_interval, _wilson, historical_season_comparison,
    recorded_season_statistics, reviewed_xg_sensitivity,
    statistical_research_markdown,
)


class StatisticalResearchTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("""
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY, date TEXT, competition TEXT,
                home_team TEXT, away_team TEXT,
                home_goals INTEGER, away_goals INTEGER, status TEXT
            )
        """)
        rows = []
        for i in range(35):
            when = (date(2024, 8, 1) + timedelta(days=max(0, i-1))).isoformat()
            if i < 8:
                home, away = ("A", "B") if i % 2 == 0 else ("C", "A")
            else:
                home, away = ("B", "C") if i % 2 == 0 else ("C", "D")
            hg, ag = ((2,1) if i%3 == 0 else
                      (1,1) if i%3 == 1 else (0,2))
            rows.append((100+i, when, "Example League",
                         home, away, hg, ag, "FINISHED"))
        rows.extend([
            (1, "2023-09-02", "Example League", "A", "B", 1,0,"FINISHED"),
            (2, "2023-10-02", "Example League", "B", "C", 2,0,"FINISHED"),
            (3, "2025-09-01", "Example League", "A", "B", 1,1,"FINISHED"),
            (4, "2025-10-01", "Example League", "B", "A", 1,2,"FINISHED"),
            (5, "2024-09-01", "Other League", "A", "B", 10,0,"FINISHED"),
            (6, "2024-10-01", "Example League", "A", "B", 20,0,"SCHEDULED"),
            (7, "2024-12-01", "Example League", "A", "A", 3,0,"FINISHED"),
            (8, "2024-12-02", "Example League", "A", "B", None,0,"FINISHED"),
        ])
        self.db.executemany(
            "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",rows
        )

    def tearDown(self):
        self.db.close()

    def report(self):
        return recorded_season_statistics(
            self.db,"Example League",2024,"A"
        )

    @staticmethod
    def xg(rows):
        return {"match_rows": rows}

    @staticmethod
    def xg_row(n, goals=2, xg=1.4):
        return {"match_id": n, "goals_for": goals, "xg_for": xg}

    def test_only_valid_completed_same_league_eligible(self):
        r=self.report()
        lg=r["league"]
        self.assertEqual(lg["recorded_matches"],35)
        self.assertEqual(lg["excluded_match_ids"],[7,8])
        self.assertNotIn(5,lg["match_ids"])
        self.assertNotIn(6,lg["match_ids"])
        self.assertEqual(lg["home_wins"] + lg["draws"] +
                         lg["away_wins"], 35)
        self.assertEqual(r["team_overall"]["matches"],8)

    def test_outcome_fractions_and_wilson_intervals(self):
        lg=self.report()["league"]
        self.assertAlmostEqual(
            lg["home_win_fraction"]+lg["draw_fraction"]+
            lg["away_win_fraction"],1
        )
        for key, frac in (
            ("home_win_wilson95",lg["home_win_fraction"]),
            ("draw_wilson95",lg["draw_fraction"]),
            ("away_win_wilson95",lg["away_win_fraction"]),
        ):
            lower,upper=lg[key]
            self.assertLessEqual(lower,frac)
            self.assertGreaterEqual(upper,frac)
            self.assertTrue(0<=lower<=upper<=1)
        self.assertIsNone(_wilson(0,0))

    def test_bootstrap_deterministic_and_withheld_below_threshold(self):
        lg=self.report()["league"]
        self.assertIsNotNone(lg["goals_per_match_bootstrap95"])
        a,b=lg["goals_per_match_bootstrap95"]
        self.assertLessEqual(a,lg["goals_per_match"])
        self.assertGreaterEqual(b,lg["goals_per_match"])
        self.assertEqual(
            _boot_mean_interval([1,3]*15,30),
            _boot_mean_interval([1,3]*15,30)
        )
        self.assertIsNone(_boot_mean_interval([1]*29,30))
        self.assertEqual(_boot_mean_interval([2]*30,30),(2,2))

    def test_last_five_form_uses_only_strictly_earlier_dates(self):
        r=self.report()
        first,second=r["team_rows"][:2]
        self.assertEqual(first["date"],second["date"])
        self.assertEqual(first["previous_matches"],0)
        self.assertEqual(second["previous_matches"],0)
        self.assertIsNone(second["previous_five_points_per_game"])
        later=next(row for row in r["team_rows"] if row["match_id"]==106)
        self.assertEqual(later["previous_matches"],5)
        self.assertEqual(later["previous_match_ids"],[101,102,103,104,105])
        self.assertNotIn(106,later["previous_match_ids"])
        self.assertIsNotNone(later["previous_five_points_per_game"])

    def test_all_form_references_precede_focal_date(self):
        r=self.report()
        known={row["match_id"]:row["date"] for row in r["team_rows"]}
        for row in r["team_rows"]:
            for mid in row["previous_match_ids"]:
                self.assertLess(known[mid],row["date"])

    def test_team_home_away_totals_are_consistent(self):
        r=self.report()
        self.assertEqual(
            r["team_home"]["matches"]+r["team_away"]["matches"],8
        )
        self.assertEqual(
            r["team_overall"]["wins"] +
            r["team_overall"]["losses"] +
            r["team_overall"]["draws"],8
        )
        ids=r["team_overall"]["source_ids"]
        self.assertEqual(set(ids),set(range(100,108)))

    def test_multiple_historical_years_and_incomplete_calendar(self):
        result=historical_season_comparison(
            self.db,"Example League",2025,3,
            as_of_date=date(2026,6,30),
        )
        self.assertEqual(result["year_count"],3)
        rows=result["by_season"]
        self.assertEqual([r["recorded_matches"] for r in rows],[2,35,2])
        self.assertTrue(rows[1]["calendar_window_complete"])
        self.assertFalse(rows[2]["calendar_window_complete"])
        self.assertFalse(rows[0]["sample_size_sufficient"])
        self.assertTrue(rows[1]["sample_size_sufficient"])
        self.assertIsNotNone(rows[0]["goals_per_match"])

    def test_wrong_configurations_rejected(self):
        for y in (0,1,9,True,"3"):
            with self.assertRaises(ValueError):
                historical_season_comparison(
                    self.db,"Example League",2024,years=y
                )
        with self.assertRaises(ValueError):
            historical_season_comparison(
                self.db,"Example League",2024,4,
                as_of_date=datetime(2026,1,1)
            )
        with self.assertRaises(ValueError):
            recorded_season_statistics(
                self.db,"Example League",2024,""
            )

    def test_zero_or_unavailable_results_are_not_fabricated(self):
        r=recorded_season_statistics(
            self.db,"Example League",2022,"A"
        )
        self.assertIsNone(r["league"]["home_win_fraction"])
        self.assertIsNone(r["league"]["goals_per_match_bootstrap95"])
        self.assertEqual(r["team_rows"],[])

    def test_reviewed_xg_withheld_for_small_samples(self):
        r=reviewed_xg_sensitivity(self.xg([
            self.xg_row(n) for n in range(1,10)
        ]))
        self.assertEqual(r["reviewed_matches"],9)
        self.assertIsNone(r["bootstrap_mean_difference95"])
        empty=reviewed_xg_sensitivity(self.xg([]))
        self.assertIsNone(empty["mean_goals_minus_xg_per_match"])
        self.assertIsNone(empty["bootstrap_mean_difference95"])

    def test_xg_interval_for_ten_eligible_reviewed_games(self):
        r=reviewed_xg_sensitivity(self.xg([
            self.xg_row(n,2,1.4) for n in range(1,11)
        ]))
        self.assertEqual(r["reviewed_matches"],10)
        self.assertAlmostEqual(r["mean_goals_minus_xg_per_match"],0.6)
        lower,upper=r["bootstrap_mean_difference95"]
        self.assertAlmostEqual(lower,0.6)
        self.assertAlmostEqual(upper,0.6)
        self.assertEqual(r["source_match_ids"],list(range(1,11)))

    def test_missing_or_duplicate_xg_evidence_rejected(self):
        one=self.xg_row(1)
        with self.assertRaisesRegex(ValueError,"duplicate"):
            reviewed_xg_sensitivity(self.xg([one,one]))
        for val in (-1,float("nan"),float("inf"),None,True):
            with self.subTest(xg=val):
                with self.assertRaises(ValueError):
                    reviewed_xg_sensitivity(self.xg([
                        self.xg_row(1,1,val)
                    ]))
        with self.assertRaises(ValueError):
            reviewed_xg_sensitivity({"match_rows":"not a list"})

    def test_zero_xg_is_not_treated_as_missing(self):
        r=reviewed_xg_sensitivity(self.xg([
            self.xg_row(n,0,0.0) for n in range(1,11)
        ]))
        self.assertEqual(r["mean_goals_minus_xg_per_match"],0)
        self.assertEqual(r["bootstrap_mean_difference95"],(0.0,0.0))

    def test_markdown_preserves_source_and_uncertainty(self):
        season=self.report()
        years=historical_season_comparison(
            self.db,"Example League",2024,2,
            as_of_date=date(2026,11,5),
        )
        sensitive=reviewed_xg_sensitivity(self.xg([]))
        md=statistical_research_markdown(season,years,sensitive)
        self.assertIn("Historical statistical research and uncertainty",md)
        self.assertIn("2024/25",md)
        self.assertIn("Earlier five",md)
        self.assertIn("100",md)
        self.assertIn("95% interval",md)
        self.assertIn("Unavailable",md)

    def test_github_research_summary_uses_recorded_season_counts(self):
        summary = build_scoring_summary(
            self.db, "Example League", as_of_date=date(2026,11,5)
        )
        self.assertIn("Recorded historical league scoring trends",summary)
        self.assertIn("2024/25",summary)
        self.assertIn("| 2024/25 | 35 |",summary)
        self.assertIn("not evidence",summary.lower())
        self.assertNotIn("Sportsbook",summary)

    def test_github_summary_empty_data_is_reported(self):
        summary = build_scoring_summary(self.db,"Unknown League")
        self.assertIn("No stored completed Unknown League",summary)

    def test_analysis_does_not_modify_database(self):
        before=list(self.db.iterdump())
        self.report()
        historical_season_comparison(
            self.db,"Example League",2024,2,
            as_of_date=date(2026,11,5),
        )
        reviewed_xg_sensitivity(self.xg([]))
        self.assertEqual(before,list(self.db.iterdump()))


if __name__=="__main__":
    unittest.main()

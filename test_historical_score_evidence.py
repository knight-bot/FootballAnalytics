"""Offline tests for source-final-score capture and conservative link quality.

All score records and teams are invented examples. No API requests, no
automatic approvals, no upcoming fixtures.
"""
import sqlite3
import unittest

from confirm_historical_link import confirm_link
from historical_audit import audit_database
from historical_coverage_matrix import coverage_matrix
from historical_fixture_linkage import candidate_links
from historical_import_planner import plan_historical_imports
from historical_score_evidence import (
    compare_stored_score, extract_current_final_score,
    stored_final_scores,
)
from sportmonks_historical_import import (
    ensure_schema, store_finished_fixture,
)
from datetime import date


def sample_fixture(score=(2, 1), state=5, fid=9001):
    entries = [
        {"description": "1ST_HALF", "participant_id": 10,
         "score": {"participant": "home", "goals": 1}},
        {"description": "1ST_HALF", "participant_id": 20,
         "score": {"participant": "away", "goals": 0}},
    ]
    if score is not None:
        entries.extend([
            {"description": "CURRENT", "participant_id": 10,
             "score": {"participant": "home", "goals": score[0]}},
            {"description": "CURRENT", "participant_id": 20,
             "score": {"participant": "away", "goals": score[1]}},
        ])
    return {
        "id": fid,
        "name": "Arsenal vs Everton",
        "starting_at": "2024-10-03 18:00:00",
        "league_id": 8, "season_id": 2024, "state_id": state,
        "participants": [
            {"id": 10, "name": "Arsenal",
             "meta": {"location": "home"}},
            {"id": 20, "name": "Everton",
             "meta": {"location": "away"}},
        ],
        "scores": entries, "statistics": [], "pressure": [],
        "xgfixture": [
            {"type_id": 5304, "location": "home",
             "participant_id": 10, "data": {"value": 1.5}},
            {"type_id": 5304, "location": "away",
             "participant_id": 20, "data": {"value": 0.8}},
        ],
    }


class SourceFinalScoreTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("""
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY, date TEXT, competition TEXT,
                home_team TEXT, away_team TEXT, home_goals INTEGER,
                away_goals INTEGER, status TEXT
            )
        """)
        self.db.execute(
            "INSERT INTO matches VALUES "
            "(101,'2024-10-03T18:00:00Z','Premier League',"
            "'Arsenal FC','Everton FC',2,1,'FINISHED')"
        )
        ensure_schema(self.db)

    def tearDown(self):
        self.db.close()

    def test_current_score_uses_correct_period_and_venue(self):
        fixture = sample_fixture(score=(2, 1))
        self.assertEqual(extract_current_final_score(fixture), (2, 1))
        # Do not use the first-half score, or whichever row came first.
        fixture["scores"] = fixture["scores"][::-1]
        self.assertEqual(extract_current_final_score(fixture), (2, 1))

    def test_no_current_score_is_unavailable_not_zero(self):
        self.assertIsNone(extract_current_final_score(sample_fixture(None)))

    def test_non_regular_time_and_unfinished_are_not_interpreted(self):
        for state in (1, 7, 8):
            with self.subTest(state=state):
                self.assertIsNone(
                    extract_current_final_score(sample_fixture(state=state))
                )

    def test_invalid_score_and_duplicate_are_not_saved(self):
        for goal in (-1, 2.0, True, "2", None):
            with self.subTest(goal=goal):
                self.assertIsNone(extract_current_final_score(
                    sample_fixture((goal, 1))
                ))
        fixture = sample_fixture()
        fixture["scores"].append(dict(fixture["scores"][-2]))
        self.assertIsNone(extract_current_final_score(fixture))

    def test_side_and_participant_mismatch_rejected(self):
        fixture = sample_fixture()
        fixture["scores"][-2]["participant_id"] = 999
        self.assertIsNone(extract_current_final_score(fixture))
        fixture = sample_fixture()
        fixture["scores"][-2]["score"]["participant"] = "away"
        self.assertIsNone(extract_current_final_score(fixture))
        fixture = sample_fixture()
        fixture["participants"].append(dict(fixture["participants"][0]))
        self.assertIsNone(extract_current_final_score(fixture))

    def test_import_records_scored_source_and_preserves_results(self):
        self.assertTrue(store_finished_fixture(self.db, sample_fixture()))
        self.assertEqual(stored_final_scores(self.db), {9001: (2, 1)})
        self.assertEqual(
            self.db.execute(
                "SELECT home_goals, away_goals FROM matches"
            ).fetchone(), (2, 1),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT score_type FROM sportmonks_historical_final_scores"
            ).fetchone()[0], "CURRENT",
        )

    def test_bad_refresh_fails_closed_instead_of_stale_score(self):
        store_finished_fixture(self.db, sample_fixture())
        store_finished_fixture(self.db, sample_fixture(score=None))
        self.assertEqual(stored_final_scores(self.db), {})
        # Fixture and valid xG records are preserved across refresh.
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM sportmonks_historical_metrics"
        ).fetchone()[0], 2)

    def test_import_updated_current_score_replaces_prior_source_evidence(self):
        store_finished_fixture(self.db, sample_fixture((2, 1)))
        store_finished_fixture(self.db, sample_fixture((3, 1)))
        self.assertEqual(stored_final_scores(self.db), {9001: (3, 1)})

    def test_comparison_does_not_approve_link(self):
        store_finished_fixture(self.db, sample_fixture())
        rows = candidate_links(self.db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "review_candidate")
        self.assertEqual(rows[0]["score_comparison"], "agrees")
        self.assertEqual(rows[0]["sportmonks_stored_final_score"], "2-1")
        self.assertIn("manually compare source scores", rows[0]["reason"])
        self.assertEqual(compare_stored_score(None, 2, 1), "unavailable")
        self.assertEqual(compare_stored_score((3, 1), 2, 1), "mismatch")
        self.assertEqual(compare_stored_score((2, 1), 2, 1), "agrees")

    def test_source_disagreement_blocks_manual_approval(self):
        store_finished_fixture(self.db, sample_fixture((3, 1)))
        row, = candidate_links(self.db)
        self.assertEqual(row["status"], "score_mismatch")
        self.assertEqual(row["score_comparison"], "mismatch")
        with self.assertRaisesRegex(ValueError, "Cannot confirm"):
            confirm_link(self.db, 9001, 101, "operator", True)
        audit = coverage_matrix(self.db, "Premier League", 2024)
        self.assertEqual(audit["status_counts"]["score_mismatch"], 1)
        self.assertEqual(audit["reviewed_total"], 0)
        self.assertEqual(audit["complete_xg"], 0)
        plan = plan_historical_imports(
            self.db, "Premier League", 2024, as_of_date=date(2026, 11, 5)
        )
        self.assertEqual(plan["manual_resolution_count"], 1)
        self.assertEqual(plan["unmatched_eligible"], 0)

    def test_old_review_becomes_stale_when_source_score_conflicts(self):
        store_finished_fixture(self.db, sample_fixture((2, 1)))
        self.assertTrue(confirm_link(
            self.db, 9001, 101, "operator", attested=True
        ))
        self.assertEqual(candidate_links(self.db)[0]["status"], "reviewed")
        store_finished_fixture(self.db, sample_fixture((3, 1)))
        self.assertEqual(candidate_links(self.db)[0]["status"], "stale_review")
        matrix = coverage_matrix(self.db, "Premier League", 2024)
        self.assertEqual(matrix["reviewed_total"], 0)
        self.assertEqual(matrix["complete_xg"], 0)

    def test_legacy_without_source_scores_still_requires_manual_review(self):
        store_finished_fixture(self.db, sample_fixture(None))
        row, = candidate_links(self.db)
        self.assertEqual(row["score_comparison"], "unavailable")
        self.assertEqual(row["status"], "review_candidate")
        self.assertTrue(confirm_link(
            self.db, 9001, 101, "operator", True
        ))
        self.assertEqual(candidate_links(self.db)[0]["status"], "reviewed")

    def test_audit_exposes_saved_score_coverage(self):
        store_finished_fixture(self.db, sample_fixture())
        report = audit_database(self.db)
        item, = report["sportmonks_fixtures"]
        self.assertEqual(item["stored_final_score_home"], 2)
        self.assertEqual(item["stored_final_score_away"], 1)
        store_finished_fixture(self.db, sample_fixture(None))
        item, = audit_database(self.db)["sportmonks_fixtures"]
        self.assertIsNone(item["stored_final_score_home"])

    def test_empty_score_table_on_old_database_is_valid(self):
        self.db.execute(
            "DROP TABLE sportmonks_historical_final_scores"
        )
        self.assertEqual(stored_final_scores(self.db), {})
        # A legacy importer database remains readable.
        self.assertEqual(candidate_links(self.db), [])

    def test_query_is_readonly_after_evidence_import(self):
        store_finished_fixture(self.db, sample_fixture())
        before = list(self.db.iterdump())
        candidate_links(self.db)
        coverage_matrix(self.db, "Premier League", 2024)
        audit_database(self.db)
        self.assertEqual(before, list(self.db.iterdump()))


if __name__ == "__main__":
    unittest.main()

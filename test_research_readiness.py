"""Offline shared-readiness regression tests for stored vs reviewed evidence."""
import sqlite3
import unittest

from confirm_historical_link import confirm_link
from research_readiness import (
    MIN_REVIEWED_XG_SAMPLE, assess_research_readiness,
    readiness_markdown,
)
from sportmonks_historical_import import ensure_schema, store_finished_fixture
from test_historical_score_evidence import sample_fixture


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY, date TEXT, competition TEXT,
                home_team TEXT, away_team TEXT,
                home_goals INTEGER, away_goals INTEGER, status TEXT
            )
        """)
        ensure_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def add_game(self, mid, day):
        self.conn.execute(
            "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",
            (
                mid, f"2024-10-{day:02d}T18:00:00Z", "Premier League",
                "Arsenal FC", "Everton FC", 2, 1, "FINISHED",
            ),
        )

    def add_fixture(self, fid, day):
        fixture = sample_fixture(score=(2,1), fid=fid)
        fixture["starting_at"] = f"2024-10-{day:02d} 18:00:00"
        store_finished_fixture(self.conn, fixture)

    def test_no_data_is_not_marked_ready(self):
        status = assess_research_readiness(self.conn)
        self.assertEqual(status["stored_completed_results"], 0)
        self.assertEqual(status["results_status"], "unavailable")
        self.assertEqual(status["xg_status"], "no_reviewed_xg_sample")
        self.assertEqual(status["reviewed_two_sided_xg"], 0)

    def test_independent_import_does_not_count_as_reviewed_xg(self):
        self.add_game(101, 3)
        self.add_fixture(9001, 3)
        status = assess_research_readiness(self.conn)
        self.assertEqual(status["stored_completed_results"], 1)
        self.assertEqual(status["imported_sportmonks_fixtures"], 1)
        self.assertEqual(status["imported_two_sided_standard_xg"], 1)
        self.assertEqual(status["imported_final_score_evidence"], 1)
        self.assertEqual(status["unreviewed_candidates"], 1)
        self.assertEqual(status["reviewed_two_sided_xg"], 0)
        self.assertEqual(status["reviewed_link_ids"], [])
        self.assertIn("operator-reviewed", readiness_markdown(status))

    def test_approved_link_contributes_only_small_sample(self):
        self.add_game(101,3)
        self.add_fixture(9001,3)
        confirm_link(self.conn,9001,101,"operator",True)
        status=assess_research_readiness(self.conn)
        self.assertEqual(status["reviewed_two_sided_xg"],1)
        self.assertEqual(status["reviewed_link_ids"],[101])
        self.assertEqual(status["reviewed_xg_source_match_ids"],[101])
        self.assertEqual(status["xg_status"],"small_reviewed_sample")

    def test_mismatch_is_blocked_and_reported(self):
        self.add_game(101,3)
        bad=sample_fixture(score=(3,1),fid=9001)
        store_finished_fixture(self.conn,bad)
        status=assess_research_readiness(self.conn)
        self.assertEqual(status["score_mismatches"],1)
        self.assertEqual(status["reviewed_source_links"],0)
        self.assertEqual(status["reviewed_two_sided_xg"],0)
        self.assertTrue(any("conflicting" in s.lower()
                            for s in status["next_actions"]))

    def test_ten_reviewed_matches_are_still_not_claimed_representative(self):
        for i in range(MIN_REVIEWED_XG_SAMPLE):
            mid=101+i
            fid=9001+i
            day=3+i
            self.add_game(mid,day)
            self.add_fixture(fid,day)
            confirm_link(self.conn,fid,mid,"operator",True)
        status=assess_research_readiness(self.conn)
        self.assertEqual(status["reviewed_two_sided_xg"],10)
        self.assertEqual(status["xg_status"],"reviewed_sample_available")
        self.assertIn("not proof", " ".join(status["notes"]).lower())

    def test_readiness_is_readonly(self):
        self.add_game(101,3)
        self.add_fixture(9001,3)
        before=list(self.conn.iterdump())
        first=assess_research_readiness(self.conn)
        self.assertEqual(first,assess_research_readiness(self.conn))
        self.assertEqual(before,list(self.conn.iterdump()))


if __name__ == "__main__":
    unittest.main()

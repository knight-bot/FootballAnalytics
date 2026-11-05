"""Regression tests for manual-only, atomic historical batch approval."""
import sqlite3
import unittest

from bulk_confirm_historical_links import (
    MAX_REVIEW_PAIRS, confirm_review_batch, parse_review_pairs,
)
from historical_fixture_linkage import candidate_links
from sportmonks_historical_import import ensure_schema, store_finished_fixture
from test_historical_score_evidence import sample_fixture


class BulkHistoricalReviewTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("""
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY, date TEXT, competition TEXT,
                home_team TEXT, away_team TEXT, home_goals INTEGER,
                away_goals INTEGER, status TEXT
            )
        """)
        ensure_schema(self.db)
        self.add_pair(9001, 101, "2024-10-03", "Arsenal", "Everton")
        self.add_pair(9002, 102, "2024-10-04", "Chelsea", "Liverpool")

    def tearDown(self):
        self.db.close()

    def add_pair(self, sid, mid, when, home, away, score=(2, 1)):
        self.db.execute(
            "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",
            (mid, when+"T18:00:00Z", "Premier League",
             home+" FC", away+" FC", 2, 1, "FINISHED")
        )
        fixture=sample_fixture(score=score, fid=sid)
        fixture["name"]=f"{home} vs {away}"
        fixture["starting_at"]=when+" 18:00:00"
        fixture["participants"][0]["name"]=home
        fixture["participants"][1]["name"]=away
        store_finished_fixture(self.db,fixture)

    def review(self,pairs=None,attested=True):
        return confirm_review_batch(
            self.db, pairs if pairs is not None else [(9001,101),(9002,102)],
            "test-operator", attested=attested
        )

    def count(self):
        return self.db.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE name='reviewed_historical_fixture_links'"
        ).fetchone()[0] and self.db.execute(
            "SELECT COUNT(*) FROM reviewed_historical_fixture_links"
        ).fetchone()[0]

    def test_requires_per_pair_review_check_and_global_attestation(self):
        self.assertEqual(
            parse_review_pairs("9001:101:CHECKED; 9002:102:CHECKED"),
            [(9001,101),(9002,102)]
        )
        for invalid in (
            "9001:101", "9001:101:YES", "9001:101:CHECKED;",
            "9001:101:CHECKED;9001:102:CHECKED",
            "9001:101:CHECKED;9002:101:CHECKED",
            "0:1:CHECKED", "x:1:CHECKED",
            "1:2:CHECKED;"*(MAX_REVIEW_PAIRS+1),
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    parse_review_pairs(invalid)
        with self.assertRaises(ValueError):
            self.review(attested=False)
        self.assertEqual(self.count(),0)

    def test_two_valid_explicit_reviews_commit_together(self):
        report=self.review()
        self.assertEqual(report,{
            "submitted":2,"inserted":2,"already_reviewed":0,
        })
        self.assertEqual(self.count(),2)
        self.assertTrue(all(
            row["status"]=="reviewed" for row in candidate_links(self.db)
        ))
        repeat=self.review()
        self.assertEqual(repeat["inserted"],0)
        self.assertEqual(repeat["already_reviewed"],2)

    def test_one_mismatch_rejects_entire_batch(self):
        self.db.execute(
            "UPDATE matches SET home_goals=3 WHERE match_id=102"
        )
        with self.assertRaises(ValueError):
            self.review()
        self.assertEqual(self.count(),0)
        self.assertEqual(
            {r["sportmonks_id"]:r["status"] for r in candidate_links(self.db)},
            {9001:"review_candidate",9002:"score_mismatch"}
        )

    def test_wrong_ids_and_duplicate_batch_reject_without_writes(self):
        for pairs in (
            [(9001,999),(9002,102)],
            [(9001,101),(9001,101)],
            [(9001,101),(9002,101)],
            [(9001,101),(9002,0)],
        ):
            with self.subTest(pairs=pairs):
                with self.assertRaises(ValueError):
                    self.review(pairs)
                self.assertEqual(self.count(),0)

    def test_stale_review_blocks_all_new_changes(self):
        self.review([(9001,101)])
        self.db.execute(
            "UPDATE sportmonks_historical_teams "
            "SET name='Different' WHERE fixture_id=9001 AND location='home'"
        )
        with self.assertRaises(ValueError):
            self.review()
        self.assertEqual(self.count(),1)

    def test_all_readonly_on_failed_batch(self):
        before=list(self.db.iterdump())
        with self.assertRaises(ValueError):
            self.review([(9001,101),(9002,999)])
        self.assertEqual(before,list(self.db.iterdump()))


if __name__=="__main__":
    unittest.main()

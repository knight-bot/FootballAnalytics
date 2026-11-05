"""Offline historical fixture linkage tests with fictional completed fixtures."""
import sqlite3
import unittest
from datetime import datetime, timezone

from historical_fixture_linkage import (
    candidate_links, normalize_team, parse_utc, reviewed_links_for_team,
)
from confirm_historical_link import confirm_link


class FixtureLinkTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript("""
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY,
                date TEXT, competition TEXT, home_team TEXT, away_team TEXT,
                home_goals INTEGER, away_goals INTEGER, status TEXT
            );
            CREATE TABLE sportmonks_historical_fixtures (
                fixture_id INTEGER PRIMARY KEY, name TEXT, match_date TEXT,
                league_id INTEGER, state_id INTEGER
            );
            CREATE TABLE sportmonks_historical_teams (
                fixture_id INTEGER, participant_id INTEGER, name TEXT,
                location TEXT
            );
        """)
        self.add_result()
        self.add_fixture()

    def tearDown(self):
        self.conn.close()

    def add_result(self, match_id=101, date="2024-10-03T18:00:00Z",
                   competition="Premier League", home="Arsenal FC",
                   away="Everton FC", status="FINISHED"):
        self.conn.execute(
            "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (match_id, date, competition, home, away, 2, 1, status),
        )

    def add_fixture(self, fixture_id=9001, date="2024-10-03 18:00:00",
                    league=8, home="Arsenal", away="Everton", state=5):
        self.conn.execute(
            "INSERT INTO sportmonks_historical_fixtures VALUES "
            "(?, ?, ?, ?, ?)",
            (fixture_id, f"{home} vs {away}", date, league, state),
        )
        self.conn.executemany(
            "INSERT INTO sportmonks_historical_teams VALUES (?, ?, ?, ?)",
            [(fixture_id, 10, home, "home"),
             (fixture_id, 20, away, "away")],
        )

    def test_normalization_is_exact_not_fuzzy(self):
        self.assertEqual(normalize_team("Arsenal FC"), "arsenal")
        self.assertEqual(normalize_team("AFC Bournemouth"), "bournemouth")
        self.assertEqual(normalize_team("Brighton & Hove Albion FC"),
                         "brighton and hove albion")
        self.assertEqual(normalize_team("Tottenham"), "tottenham hotspur")
        self.assertNotEqual(normalize_team("Manchester"),
                            normalize_team("Manchester City"))
        self.assertEqual(normalize_team(""), "")

    def test_utc_datetime_and_invalid_date(self):
        self.assertEqual(
            parse_utc("2024-10-03T19:00:00+01:00"),
            datetime(2024, 10, 3, 18, tzinfo=timezone.utc),
        )
        self.assertIsNone(parse_utc("not a timestamp"))
        self.assertIsNone(parse_utc(None))

    def test_one_to_one_historical_match_is_only_a_candidate(self):
        row, = candidate_links(self.conn)
        self.assertEqual(row["status"], "review_candidate")
        self.assertEqual(row["sportmonks_id"], 9001)
        self.assertEqual(row["match_id"], 101)
        self.assertEqual(row["result_score"], "2-1")
        self.assertEqual(row["kickoff_difference_minutes"], 0.0)
        self.assertIn("manually compare source scores", row["reason"])

    def test_home_away_swap_is_not_a_valid_match(self):
        self.conn.execute(
            "UPDATE sportmonks_historical_teams SET location='away' "
            "WHERE participant_id=10"
        )
        self.conn.execute(
            "UPDATE sportmonks_historical_teams SET location='home' "
            "WHERE participant_id=20"
        )
        row, = candidate_links(self.conn)
        self.assertEqual(row["status"], "unmatched")

    def test_different_competitions_and_unsupported_leagues_reject(self):
        self.conn.execute(
            "UPDATE matches SET competition='Example Cup'"
        )
        self.assertEqual(candidate_links(self.conn)[0]["status"], "unmatched")
        self.conn.execute(
            "UPDATE sportmonks_historical_fixtures SET league_id=999"
        )
        self.assertEqual(candidate_links(self.conn)[0]["status"], "unmatched")

    def test_too_distant_kickoff_rejects(self):
        self.conn.execute(
            "UPDATE sportmonks_historical_fixtures "
            "SET match_date='2024-10-04 03:00:00'"
        )
        self.assertEqual(candidate_links(self.conn)[0]["status"], "unmatched")

    def test_duplicate_provider_candidates_are_ambiguous(self):
        self.add_fixture(fixture_id=9002)
        statuses = [item["status"] for item in candidate_links(self.conn)]
        self.assertEqual(statuses, ["ambiguous", "ambiguous"])
        with self.assertRaises(ValueError):
            confirm_link(self.conn, 9001, 101, "operator", True)

    def test_duplicate_results_are_ambiguous(self):
        self.add_result(match_id=102)
        self.assertEqual(candidate_links(self.conn)[0]["status"], "ambiguous")

    def test_only_completed_matches_are_included(self):
        self.conn.execute("UPDATE matches SET status='SCHEDULED'")
        self.assertEqual(candidate_links(self.conn)[0]["status"], "unmatched")
        self.conn.execute("UPDATE matches SET status='FINISHED'")
        self.conn.execute(
            "UPDATE sportmonks_historical_fixtures SET state_id=1"
        )
        self.assertEqual(candidate_links(self.conn)[0]["status"], "unmatched")

    def test_attestation_and_pair_check_required(self):
        with self.assertRaises(ValueError):
            confirm_link(self.conn, 9001, 101, "operator", False)
        with self.assertRaises(ValueError):
            confirm_link(self.conn, 9001, 999, "operator", True)
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE name='reviewed_historical_fixture_links'"
            ).fetchone()[0], 0,
        )

    def test_explicit_review_preserves_match_data(self):
        changed = confirm_link(self.conn, 9001, 101, "operator", True)
        self.assertTrue(changed)
        self.assertEqual(candidate_links(self.conn)[0]["status"], "reviewed")
        reviewed = reviewed_links_for_team(
            self.conn, "Premier League", 2024, "Arsenal FC"
        )
        self.assertEqual(len(reviewed), 1)
        self.assertEqual(reviewed[0]["match_id"], 101)
        self.assertEqual(
            self.conn.execute("SELECT home_goals FROM matches").fetchone()[0],
            2,
        )
        self.assertFalse(confirm_link(self.conn, 9001, 101, "operator", True))

    def test_stale_manual_review_does_not_authorize_join(self):
        confirm_link(self.conn, 9001, 101, "operator", True)
        self.conn.execute(
            "UPDATE sportmonks_historical_teams "
            "SET name='Some Other Team' WHERE location='home'"
        )
        self.assertEqual(candidate_links(self.conn)[0]["status"], "stale_review")
        self.assertEqual(
            reviewed_links_for_team(
                self.conn, "Premier League", 2024, "Arsenal FC"
            ),
            [],
        )

    def test_wrong_year_is_not_in_team_report(self):
        confirm_link(self.conn, 9001, 101, "operator", True)
        self.assertEqual(
            reviewed_links_for_team(
                self.conn, "Premier League", 2025, "Arsenal FC"
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()

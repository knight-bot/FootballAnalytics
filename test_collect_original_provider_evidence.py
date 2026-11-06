"""Offline tests of the original-provider evidence workflow.

Never uses real API credentials, provider networks or source approval.
"""
import sqlite3
import unittest

from collect_original_provider_evidence import (
    _football_data_fields, _original_get, _sportmonks_fields,
    collect_evidence, compare_original_evidence, evidence_summary,
    selected_candidates,
)
from sportmonks_historical_import import ensure_schema, store_finished_fixture
from test_historical_score_evidence import sample_fixture


def fd_match(mid=101, score=(2, 1), home="Arsenal FC", away="Everton FC"):
    return {
        "id": mid, "competition": {"code": "PL"},
        "utcDate": "2025-09-13T18:00:00Z",
        "status": "FINISHED",
        "homeTeam": {"name": home}, "awayTeam": {"name": away},
        "score": {"duration": "REGULAR", "fullTime": {
            "home": score[0], "away": score[1],
        }},
    }


def sportmonks(mid=9001, score=(2, 1), home="Arsenal", away="Everton"):
    fixture = sample_fixture(fid=mid, score=score)
    fixture["starting_at"] = "2025-09-13 18:00:00"
    fixture["participants"][0]["name"] = home
    fixture["participants"][1]["name"] = away
    return fixture


class FakeResponse:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, sm=None, fd=None, sm_status=200, fd_status=200):
        self.sm = sm if sm is not None else {"data": sportmonks()}
        self.fd = fd if fd is not None else fd_match()
        self.sm_status, self.fd_status = sm_status, fd_status
        self.calls = []

    def get(self, url, *, headers, params=None, timeout):
        self.calls.append((url, headers, params, timeout))
        if "sportmonks.com" in url:
            return FakeResponse(self.sm, self.sm_status)
        return FakeResponse(self.fd, self.fd_status)


class OriginalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY, date TEXT,
                competition TEXT, home_team TEXT, away_team TEXT,
                home_goals INTEGER, away_goals INTEGER, status TEXT
            )
        """)
        self.conn.execute(
            "INSERT INTO matches VALUES "
            "(101, '2025-09-13T18:00:00Z', 'Premier League', "
            "'Arsenal FC', 'Everton FC', 2, 1, 'FINISHED')"
        )
        ensure_schema(self.conn)
        store_finished_fixture(self.conn, sportmonks())

    def tearDown(self):
        self.conn.close()

    def test_authenticated_original_records_are_consistent_not_approved(self):
        s = FakeSession()
        before = list(self.conn.iterdump())
        out = collect_evidence(
            s, self.conn, "PRIVATE_SM", "PRIVATE_FD",
            "2025-09-12", "2025-09-25",
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(
            out[0]["automatic_consistency"], "CONSISTENT_REQUIRES_REVIEW"
        )
        self.assertFalse(out[0]["operator_approved"])
        self.assertEqual(len(out[0]["provider_evidence"]), 2)
        self.assertIn("CONSISTENT_REQUIRES_REVIEW", evidence_summary(out))
        self.assertNotIn("PRIVATE_SM", str(out))
        self.assertNotIn("PRIVATE_FD", str(out))
        self.assertIn("PRIVATE_SM", str(s.calls))  # header used privately
        self.assertEqual(before, list(self.conn.iterdump()))

    def test_missing_original_provider_is_unavailable_not_verified(self):
        for sm_status, fd_status in ((403, 200), (200, 403)):
            with self.subTest(sm=sm_status, fd=fd_status):
                s = FakeSession(sm_status=sm_status, fd_status=fd_status)
                out = collect_evidence(
                    s, self.conn, "PRIVATE_SM", "PRIVATE_FD",
                    "2025-09-12", "2025-09-25",
                )
                self.assertEqual(out[0]["automatic_consistency"], "UNAVAILABLE")
                self.assertFalse(out[0]["operator_approved"])
                code = out[0]["provider_evidence"][
                    0 if sm_status == 403 else 1
                ]["http_status"]
                self.assertEqual(code, 403)

    def test_source_score_disagreement_blocks_consistency(self):
        s = FakeSession(fd=fd_match(score=(3, 1)))
        out = collect_evidence(
            s, self.conn, "token1", "token2",
            "2025-09-12", "2025-09-25",
        )
        self.assertEqual(out[0]["automatic_consistency"], "CONFLICT")

    def test_stored_score_difference_blocks_consistency(self):
        candidate = selected_candidates(
            self.conn, "2025-09-12", "2025-09-25",
        )[0]
        candidate["result_score"] = "1-0"
        result, _ = compare_original_evidence(
            candidate, _sportmonks_fields(
                {"data": sportmonks()}, 9001
            ), _football_data_fields(fd_match(), 101)
        )
        self.assertEqual(result, "CONFLICT")

    def test_wrong_original_ids_are_not_accepted(self):
        self.assertIsNone(
            _sportmonks_fields({"data": sportmonks()}, 9002)
        )
        self.assertIsNone(_football_data_fields(fd_match(), 999))
        self.assertIsNone(_sportmonks_fields({"data": {}}, 9001))

    def test_wrong_competition_kickoff_or_home_away_blocks(self):
        alterations = [
            {"competition": {"code": "ELC"}},
            {"utcDate": "2025-09-14T18:00:00Z"},
            {"homeTeam": {"name": "Everton FC"}},
            {"status": "SCHEDULED"},
            {"score": {"duration": "PENALTY_SHOOTOUT",
                       "fullTime": {"home": 2, "away": 1}}},
        ]
        for change in alterations:
            with self.subTest(change=change):
                fd = fd_match()
                fd.update(change)
                out = collect_evidence(
                    FakeSession(fd=fd), self.conn, "token1", "token2",
                    "2025-09-12", "2025-09-25",
                )
                self.assertEqual(out[0]["automatic_consistency"], "CONFLICT")

    def test_missing_final_score_is_unavailable(self):
        fd = fd_match()
        fd["score"]["fullTime"]["away"] = None
        out = collect_evidence(
            FakeSession(fd=fd), self.conn, "token1", "token2",
            "2025-09-12", "2025-09-25",
        )
        self.assertEqual(out[0]["automatic_consistency"], "UNAVAILABLE")

    def test_selection_bounds_and_date_filter(self):
        self.assertEqual(len(selected_candidates(
            self.conn, "2025-09-12", "2025-09-25",
        )), 1)
        self.assertEqual(selected_candidates(
            self.conn, "2025-08-01", "2025-08-25",
        ), [])
        for limit in (0, 11, True, -1):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    selected_candidates(
                        self.conn, "2025-09-12", "2025-09-25", limit,
                    )

    def test_providers_are_requested_by_original_id_with_headers(self):
        s = FakeSession()
        collect_evidence(
            s, self.conn, "SM_KEY", "FD_KEY",
            "2025-09-12", "2025-09-25",
        )
        self.assertEqual(s.calls[0][0],
                         "https://api.sportmonks.com/v3/football/fixtures/9001")
        self.assertEqual(s.calls[0][2], {"include": "participants;scores"})
        self.assertEqual(s.calls[1][0],
                         "https://api.football-data.org/v4/matches/101")
        self.assertEqual(s.calls[1][1]["X-Auth-Token"], "FD_KEY")

    def test_malformed_http_success_is_unavailable(self):
        bad = FakeSession(sm={"data": "invalid"})
        out = collect_evidence(
            bad, self.conn, "SM_KEY", "FD_KEY",
            "2025-09-12", "2025-09-25",
        )
        self.assertEqual(out[0]["automatic_consistency"], "UNAVAILABLE")

    def test_http_error_does_not_print_response_payload_or_secret(self):
        sess = FakeSession(sm={"errors": ["raw credential"]},sm_status=403)
        body, info = _original_get(
            sess, "https://api.sportmonks.com/v3/football/fixtures/9001",
            {"Authorization": "PRIVATE_TOKEN"},
        )
        self.assertIsNone(body)
        self.assertEqual(info, {"status": "HTTP_ERROR", "http_status": 403})
        self.assertNotIn("PRIVATE_TOKEN", str(info))
        self.assertNotIn("raw credential", str(info))


if __name__ == "__main__":
    unittest.main()

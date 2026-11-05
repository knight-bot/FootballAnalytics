"""GitHub Actions-only manual confirmation of one historical provider link.

The Sportmonks importer does not persist the final score. The operator must
check that score in both provider source records before approving any link.
This script checks teams, league, completed state, kickoff and uniqueness,
but cannot independently substantiate the operator's score attestation.
"""
import os
import sqlite3
import sys
from datetime import datetime, timezone

from sportmonks_historical_import import DB_PATH
from historical_fixture_linkage import (
    candidate_links, initialize_link_table, LINK_TABLE,
)


def _positive_integer(value):
    if not value or not str(value).isdecimal() or int(value) <= 0:
        raise ValueError("Both provider IDs must be positive integers.")
    return int(value)


def confirm_link(conn, sportmonks_id, result_id, actor, attested):
    if attested is not True:
        raise ValueError(
            "Confirmation requires an explicit independent source-score "
            "comparison by the operator."
        )
    sid = _positive_integer(str(sportmonks_id))
    mid = _positive_integer(str(result_id))
    actor = str(actor or "").strip()
    if not actor or len(actor) > 100:
        raise ValueError("Missing or invalid reviewing actor.")

    rows = [row for row in candidate_links(conn)
            if row["sportmonks_id"] == sid]
    if len(rows) != 1:
        raise ValueError("Sportmonks fixture was not found exactly once.")
    candidate = rows[0]
    if candidate["match_id"] != mid or candidate["status"] not in (
        "review_candidate", "reviewed",
    ):
        raise ValueError(
            "Cannot confirm: records do not uniquely match in both "
            "team names, competition and kickoff. See the review page."
        )

    with conn:
        initialize_link_table(conn)
        previous = conn.execute(
            f"SELECT football_data_match_id FROM {LINK_TABLE} "
            "WHERE sportmonks_fixture_id=?",
            (sid,),
        ).fetchone()
        if previous:
            if previous[0] == mid:
                print("Exact link was already reviewed; no change.")
                return False
            raise ValueError("This Sportmonks fixture has a different reviewed link.")
        conflict = conn.execute(
            f"SELECT sportmonks_fixture_id FROM {LINK_TABLE} "
            "WHERE football_data_match_id=?",
            (mid,),
        ).fetchone()
        if conflict:
            raise ValueError(
                "This football-data.org match already has a reviewed link."
            )
        conn.execute(
            f"INSERT INTO {LINK_TABLE} "
            "(sportmonks_fixture_id, football_data_match_id, "
            "reviewed_by, reviewed_at) VALUES (?, ?, ?, ?)",
            (sid, mid, actor, datetime.now(timezone.utc).isoformat()),
        )
    print(
        f"Stored operator-reviewed historical association: "
        f"Sportmonks {sid} -> football-data.org {mid}."
    )
    print(
        "Final-score agreement was attested by the reviewing operator "
        "rather than independently checked by this script."
    )
    return True


def main():
    actor = os.environ.get("GITHUB_ACTOR", "")
    ack = os.environ.get("HISTORICAL_SCORE_CHECKED", "").strip()
    if ack != "YES_I_COMPARED_BOTH_SCORES":
        raise ValueError(
            "To confirm, explicitly attest that you personally checked "
            "the final scores in both original providers."
        )
    sid = os.environ.get("SPORTMONKS_FIXTURE_ID", "")
    mid = os.environ.get("FOOTBALL_DATA_MATCH_ID", "")
    with sqlite3.connect(DB_PATH) as conn:
        confirm_link(conn, sid, mid, actor, attested=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, sqlite3.Error) as exc:
        sys.exit(str(exc))

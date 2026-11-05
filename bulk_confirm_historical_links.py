"""Bounded, atomic human-attested approval of historical fixture pairs.

All records MUST be explicitly checked by the workflow operator in both
original providers. A successful candidate score comparison NEVER grants
automatic approval. A malformed or conflicting batch changes no links.
"""
import os
import sqlite3
import sys
from datetime import datetime, timezone

from historical_fixture_linkage import (
    LINK_TABLE, _exists, candidate_links, initialize_link_table,
)
from sportmonks_historical_import import DB_PATH

MAX_REVIEW_PAIRS = 20
PER_ITEM_ACK = "CHECKED"
GLOBAL_ACK = "YES_I_COMPARED_ALL_SOURCE_SCORES"


def parse_review_pairs(raw):
    """Read only ID:ID:CHECKED entries separated by semicolons."""
    if not isinstance(raw, str) or len(raw) > 1600 or not raw.strip():
        raise ValueError("Enter 1-20 explicitly checked fixture pairs.")
    pieces = [p.strip() for p in raw.split(";")]
    if not 1 <= len(pieces) <= MAX_REVIEW_PAIRS or any(not p for p in pieces):
        raise ValueError("Enter 1-20 semicolon-separated checked pairs.")
    pairs = []
    sids, mids = set(), set()
    for piece in pieces:
        parts = [item.strip() for item in piece.split(":")]
        if len(parts) != 3 or parts[2] != PER_ITEM_ACK:
            raise ValueError(
                "Each entry must be SportmonksID:ResultID:CHECKED "
                "after comparing original score records."
            )
        sid_text, mid_text = parts[:2]
        if (not sid_text.isdecimal() or not mid_text.isdecimal()
                or not 0 < int(sid_text) < 2**63
                or not 0 < int(mid_text) < 2**63):
            raise ValueError("Provider IDs must be positive SQLite integers.")
        sid, mid = int(sid_text), int(mid_text)
        if sid in sids or mid in mids:
            raise ValueError(
                "Batch contains duplicate provider identifiers; "
                "one-to-one review is required."
            )
        sids.add(sid)
        mids.add(mid)
        pairs.append((sid, mid))
    return pairs


def confirm_review_batch(conn, pairs, actor, attested=False):
    """Validate *all* candidate pairs before any atomic SQLite writes.

    This deliberately does not call confirm_link(), whose per-pair
    transaction would allow partial approval on a later failed row.
    """
    if attested is not True:
        raise ValueError("The operator must attest independent source-score checks.")
    if not isinstance(actor, str) or not 1 <= len(actor.strip()) <= 100:
        raise ValueError("A valid GitHub reviewing actor is required.")
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= MAX_REVIEW_PAIRS:
        raise ValueError("Invalid number of reviewed pairs.")
    if (any(type(sid) is not int or type(mid) is not int
            or sid <= 0 or mid <= 0 for sid, mid in pairs)
            or len({sid for sid, _ in pairs}) != len(pairs)
            or len({mid for _, mid in pairs}) != len(pairs)):
        raise ValueError("Duplicate or invalid provider identifiers.")

    candidates = {r["sportmonks_id"]: r for r in candidate_links(conn)}
    for sid, mid in pairs:
        row = candidates.get(sid)
        if (row is None or row["match_id"] != mid
                or row["status"] not in ("review_candidate", "reviewed")):
            raise ValueError(
                f"Fixture {sid} to result {mid} is not an unambiguous "
                "review-eligible match. No links were approved."
            )
        if row["score_comparison"] == "mismatch":
            raise ValueError("A source-score conflict blocks the entire batch.")

    existing = {}
    reverse = {}
    if _exists(conn, LINK_TABLE):
        existing = {
            int(sid): int(mid) for sid, mid in conn.execute(
                f"SELECT sportmonks_fixture_id, football_data_match_id "
                f"FROM {LINK_TABLE}"
            )
        }
        reverse = {mid: sid for sid, mid in existing.items()}
    for sid, mid in pairs:
        if sid in existing and existing[sid] != mid:
            raise ValueError("A reviewed fixture already links elsewhere.")
        if mid in reverse and reverse[mid] != sid:
            raise ValueError("A reviewed result already links elsewhere.")

    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    with conn:
        initialize_link_table(conn)
        for sid, mid in pairs:
            if existing.get(sid) == mid:
                continue
            conn.execute(
                f"INSERT INTO {LINK_TABLE} "
                "(sportmonks_fixture_id, football_data_match_id, "
                "reviewed_by, reviewed_at) VALUES (?, ?, ?, ?)",
                (sid, mid, actor.strip(), now),
            )
            inserted += 1
    return {
        "submitted": len(pairs),
        "inserted": inserted,
        "already_reviewed": len(pairs) - inserted,
    }


def main():
    raw = os.environ.get("HISTORICAL_REVIEW_PAIRS", "")
    ack = os.environ.get("HISTORICAL_BULK_SCORES_CHECKED", "")
    if ack != GLOBAL_ACK:
        raise ValueError(
            "Explicitly attest that you checked every pair in both "
            "original provider records."
        )
    pairs = parse_review_pairs(raw)
    actor = os.environ.get("GITHUB_ACTOR", "")
    with sqlite3.connect(DB_PATH) as conn:
        report = confirm_review_batch(conn, pairs, actor, attested=True)
    print(
        f"Operator-attested historical pair review: "
        f"{report['submitted']} submitted; {report['inserted']} newly "
        f"approved; {report['already_reviewed']} already approved."
    )
    print(
        "These matches were approved only because the operator "
        "attested source comparison, never by automatic score matching."
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, sqlite3.Error) as exc:
        sys.exit(str(exc))

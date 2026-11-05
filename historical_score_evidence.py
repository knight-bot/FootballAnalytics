"""Strictly retrospective Sportmonks final-score evidence and cross-source checks.

Sportmonks API v3 score records use score.participant, score.goals, and
description='CURRENT' for the current/final match score. Only FINISHED
regular-time (state_id=5) fixtures are automatically compared here.
Other finished states (extra time/penalties) require manual review.

No API calls, no automatic provider link approval, no upcoming fixtures.
"""
from datetime import datetime, timezone

SCORE_TABLE = "sportmonks_historical_final_scores"


def ensure_score_schema(conn):
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCORE_TABLE} (
            fixture_id INTEGER PRIMARY KEY,
            home_goals INTEGER NOT NULL CHECK(home_goals >= 0),
            away_goals INTEGER NOT NULL CHECK(away_goals >= 0),
            score_type TEXT NOT NULL DEFAULT 'CURRENT',
            recorded_at TEXT NOT NULL
        )
    """)


def _nonnegative_int(value):
    if type(value) is int and value >= 0:
        return value
    return None


def extract_current_final_score(fixture):
    """Return (home goals, away goals), or None if evidence is ambiguous.

    Refuse non-regular full-time states; do not interpret period goals
    as cumulative match totals, infer unknown sides, or average duplicates.
    An unambiguous participant->side mapping is required.
    """
    if fixture.get("state_id") != 5:
        return None
    participants = fixture.get("participants")
    scores = fixture.get("scores")
    if not isinstance(participants, list) or not isinstance(scores, list):
        return None
    side_ids = {"home": [], "away": []}
    for participant in participants:
        if not isinstance(participant, dict):
            continue
        meta = participant.get("meta")
        side = meta.get("location") if isinstance(meta, dict) else None
        pid = participant.get("id")
        if side in side_ids and type(pid) is int and pid > 0:
            side_ids[side].append(pid)
    if any(len(ids) != 1 for ids in side_ids.values()):
        return None
    if side_ids["home"][0] == side_ids["away"][0]:
        return None
    accepted = {"home": [], "away": []}
    for record in scores:
        if not isinstance(record, dict):
            continue
        # API type IDs may vary. Only the documented CURRENT description
        # and the nested score structure are treated as final scores.
        if record.get("description") != "CURRENT":
            continue
        data = record.get("score")
        if not isinstance(data, dict):
            return None
        side = data.get("participant")
        goals = _nonnegative_int(data.get("goals"))
        pid = record.get("participant_id")
        if side not in accepted or goals is None or type(pid) is not int:
            return None
        if pid != side_ids[side][0]:
            return None
        accepted[side].append(goals)
    if any(len(vals) != 1 for vals in accepted.values()):
        return None
    return accepted["home"][0], accepted["away"][0]


def replace_score_evidence(conn, fixture):
    """Update a single imported finished fixture's source-score evidence.

    An incomplete response clears previously saved evidence for that
    fixture. Fail-closed: outdated scores cannot silently survive a
    refresh that no longer provides unambiguous CURRENT entries.
    Requires surrounding import transaction for atomicity.
    """
    ensure_score_schema(conn)
    fid = fixture.get("id")
    if type(fid) is not int or fid <= 0:
        raise ValueError("Fixture ID must be a positive integer.")
    parsed = extract_current_final_score(fixture)
    conn.execute(f"DELETE FROM {SCORE_TABLE} WHERE fixture_id=?", (fid,))
    if parsed is not None:
        conn.execute(
            f"INSERT INTO {SCORE_TABLE} "
            "(fixture_id, home_goals, away_goals, score_type, recorded_at) "
            "VALUES (?, ?, ?, 'CURRENT', ?)",
            (
                fid, parsed[0], parsed[1],
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return parsed


def stored_final_scores(conn):
    """Read a source-specific fixture->score map without creating tables."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (SCORE_TABLE,),
    ).fetchone()
    if not exists:
        return {}
    return {
        int(fid): (int(h), int(a))
        for fid, h, a in conn.execute(
            f"SELECT fixture_id, home_goals, away_goals FROM {SCORE_TABLE}"
        )
    }


def compare_stored_score(stored, home_goals, away_goals):
    """Return agreement/mismatch/unavailable, never approve an association."""
    if stored is None:
        return "unavailable"
    if type(home_goals) is not int or type(away_goals) is not int:
        return "unavailable"
    if home_goals < 0 or away_goals < 0:
        return "unavailable"
    return (
        "agrees" if stored == (home_goals, away_goals) else "mismatch"
    )

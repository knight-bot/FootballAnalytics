"""Import a small, manually selected set of *completed* Sportmonks fixtures.

For historical research only. Does not pull live fixtures, odds or predictions.
Stores source-specific metrics in separate SQLite tables.
"""
import os
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

API_URL = "https://api.sportmonks.com/v3/football/fixtures"
DB_PATH = Path(__file__).resolve().parent / "football.db"
FINISHED_STATES = {5, 7, 8}  # FT, AET, FT_PEN (Sportmonks v3)


def fixture_ids_from_env():
    raw = os.environ.get("SPORTMONKS_HISTORICAL_FIXTURE_IDS", "").strip()
    values = [value.strip() for value in raw.split(",") if value.strip()]
    if not values or len(values) > 5 or any(not x.isdecimal() for x in values):
        raise ValueError("Provide 1 to 5 comma-separated numeric fixture IDs.")
    return list(dict.fromkeys(int(value) for value in values))


def get_fixture(session, token, fixture_id):
    response = session.get(
        f"{API_URL}/{fixture_id}",
        headers={"Authorization": token, "Accept": "application/json"},
        params={"include": "state;participants;statistics;scores;xGFixture;pressure"},
        timeout=45,
    )
    if not response.ok:
        raise RuntimeError(
            f"Sportmonks rejected fixture {fixture_id}: HTTP {response.status_code}. "
            "Check fixture coverage and subscription. No credentials were logged."
        )
    payload = response.json()
    fixture = payload.get("data")
    if not isinstance(fixture, dict) or fixture.get("id") != fixture_id:
        raise ValueError(f"Unexpected data response for fixture {fixture_id}.")
    return fixture


def ensure_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sportmonks_historical_fixtures (
            fixture_id INTEGER PRIMARY KEY,
            name TEXT,
            match_date TEXT,
            league_id INTEGER,
            season_id INTEGER,
            state_id INTEGER,
            stat_records INTEGER NOT NULL,
            pressure_records INTEGER NOT NULL,
            score_records INTEGER NOT NULL,
            metric_records INTEGER NOT NULL,
            imported_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sportmonks_historical_teams (
            fixture_id INTEGER NOT NULL,
            participant_id INTEGER NOT NULL,
            name TEXT,
            location TEXT,
            PRIMARY KEY (fixture_id, participant_id)
        );
        CREATE TABLE IF NOT EXISTS sportmonks_historical_metrics (
            fixture_id INTEGER NOT NULL,
            type_id INTEGER NOT NULL,
            location TEXT NOT NULL,
            participant_id INTEGER NOT NULL DEFAULT 0,
            value REAL NOT NULL,
            PRIMARY KEY (fixture_id, type_id, location, participant_id)
        );
        CREATE TABLE IF NOT EXISTS sportmonks_historical_statistics (
            fixture_id INTEGER NOT NULL,
            entry_index INTEGER NOT NULL,
            type_id INTEGER NOT NULL,
            participant_id INTEGER NOT NULL DEFAULT 0,
            location TEXT NOT NULL,
            value REAL NOT NULL,
            PRIMARY KEY (fixture_id, entry_index)
        );
        CREATE TABLE IF NOT EXISTS sportmonks_historical_pressure (
            fixture_id INTEGER NOT NULL,
            participant_id INTEGER NOT NULL,
            minute INTEGER NOT NULL,
            pressure REAL NOT NULL,
            PRIMARY KEY (fixture_id, participant_id, minute)
        );
    """)


def normalized_value(item):
    data = item.get("data")
    if not isinstance(data, dict):
        return None
    value = data.get("value")
    if isinstance(value, bool):
        return None
    try:
        return float(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def store_finished_fixture(conn, fixture):
    """Upsert one finished fixture with its xG metrics, atomically."""
    state_id = fixture.get("state_id")
    if state_id not in FINISHED_STATES:
        print(
            f"Fixture {fixture['id']}: state {state_id} is not completed; "
            "skipped (no data saved)."
        )
        return False

    fixture_id = int(fixture["id"])
    xg_items = next(
        (fixture[key] for key in ("xgfixture", "expected", "xGFixture")
         if isinstance(fixture.get(key), list)),
        [],
    )
    statistics = fixture.get("statistics") or []
    pressure = fixture.get("pressure") or []
    scores = fixture.get("scores") or []
    participants = fixture.get("participants") or []

    metrics = []
    for item in xg_items:
        if not isinstance(item, dict):
            continue
        value = normalized_value(item)
        type_id = item.get("type_id")
        if type_id is None or value is None:
            continue
        metrics.append((
            fixture_id,
            int(type_id),
            str(item.get("location") or "unknown"),
            int(item.get("participant_id") or 0),
            value,
        ))

    teams = []
    for item in participants:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        metadata = item.get("meta") or {}
        location = metadata.get("location") if isinstance(metadata, dict) else None
        teams.append((
            fixture_id,
            int(item["id"]),
            str(item.get("name") or ""),
            str(location or "unknown"),
        ))

    # Retain only numeric historical team-statistic values. Unknown
    # type IDs are stored as IDs instead of being guessed or relabelled.
    stat_rows = []
    for index, item in enumerate(statistics):
        if not isinstance(item, dict):
            continue
        type_id = item.get("type_id")
        value = normalized_value(item)
        if type_id is None or value is None:
            continue
        try:
            stat_rows.append((
                fixture_id, index, int(type_id),
                int(item.get("participant_id") or 0),
                str(item.get("location") or "unknown"), value,
            ))
        except (TypeError, ValueError):
            continue

    # Pressure Index records represent attacking momentum by minute,
    # not a count of defensive pressing actions.
    pressure_rows = []
    for item in pressure:
        if not isinstance(item, dict):
            continue
        try:
            if item.get("participant_id") is None or item.get("minute") is None:
                continue
            value = float(item["pressure"])
            if not math.isfinite(value):
                continue
            pressure_rows.append((
                fixture_id, int(item["participant_id"]),
                int(item["minute"]), value,
            ))
        except (KeyError, TypeError, ValueError):
            continue

    fetched_at = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute("""
            INSERT INTO sportmonks_historical_fixtures
            (fixture_id, name, match_date, league_id, season_id, state_id,
             stat_records, pressure_records, score_records, metric_records,
             imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fixture_id) DO UPDATE SET
              name=excluded.name,
              match_date=excluded.match_date,
              league_id=excluded.league_id,
              season_id=excluded.season_id,
              state_id=excluded.state_id,
              stat_records=excluded.stat_records,
              pressure_records=excluded.pressure_records,
              score_records=excluded.score_records,
              metric_records=excluded.metric_records,
              imported_at=excluded.imported_at
        """, (
            fixture_id, fixture.get("name"), fixture.get("starting_at"),
            fixture.get("league_id"), fixture.get("season_id"), state_id,
            len(statistics), len(pressure), len(scores), len(metrics),
            fetched_at,
        ))
        # Replace metric rows only for this fixture; do not affect others.
        if teams:
            conn.execute(
                "DELETE FROM sportmonks_historical_teams WHERE fixture_id=?",
                (fixture_id,),
            )
        # If an API include is temporarily absent or empty, preserve the
        # previously imported rows instead of silently erasing them.
        if metrics:
            conn.execute(
                "DELETE FROM sportmonks_historical_metrics WHERE fixture_id=?",
                (fixture_id,),
            )
        if stat_rows:
            conn.execute(
                "DELETE FROM sportmonks_historical_statistics WHERE fixture_id=?",
                (fixture_id,),
            )
            conn.executemany("""
                INSERT INTO sportmonks_historical_statistics
                  (fixture_id, entry_index, type_id, participant_id, location, value)
                VALUES (?, ?, ?, ?, ?, ?)
            """, stat_rows)
        if pressure_rows:
            conn.execute(
                "DELETE FROM sportmonks_historical_pressure WHERE fixture_id=?",
                (fixture_id,),
            )
            conn.executemany("""
                INSERT INTO sportmonks_historical_pressure
                  (fixture_id, participant_id, minute, pressure)
                VALUES (?, ?, ?, ?)
            """, pressure_rows)
        conn.executemany("""
            INSERT OR REPLACE INTO sportmonks_historical_metrics
              (fixture_id, type_id, location, participant_id, value)
            VALUES (?, ?, ?, ?, ?)
        """, metrics)
        conn.executemany("""
            INSERT OR REPLACE INTO sportmonks_historical_teams
              (fixture_id, participant_id, name, location)
            VALUES (?, ?, ?, ?)
        """, teams)

    print(
        f"Fixture {fixture_id}: saved {len(metrics)} xG-related metrics, "
        f"{len(stat_rows)} numeric match-statistic values, "
        f"{len(pressure_rows)} minute-level Pressure Index values."
    )
    return True


def main():
    token = os.environ.get("SPORTMONKS_API_TOKEN", "").strip()
    if not token:
        raise ValueError("Missing SPORTMONKS_API_TOKEN secret.")

    fixture_ids = fixture_ids_from_env()
    imported = 0
    session = requests.Session()
    with sqlite3.connect(DB_PATH) as conn:
        ensure_schema(conn)
        for fixture_id in fixture_ids:
            fixture = get_fixture(session, token, fixture_id)
            imported += store_finished_fixture(conn, fixture)
        total = conn.execute(
            "SELECT COUNT(*) FROM sportmonks_historical_fixtures"
        ).fetchone()[0]

    print(f"Historical fixture imports this run: {imported}")
    print(f"Total Sportmonks historical fixtures stored: {total}")
    print("Original football-data.org matches table is unchanged.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, requests.RequestException, sqlite3.Error) as exc:
        sys.exit(str(exc))

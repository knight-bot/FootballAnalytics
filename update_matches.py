
import os
import time
import sqlite3
import requests
from datetime import datetime, timedelta, timezone

# ==========================================
# 1. CONFIGURATION
# ==========================================

TOKEN = os.environ["FOOTBALL_API_TOKEN"]
URL = "https://api.football-data.org/v4/matches"

today = datetime.now(timezone.utc).date()

# Collect the previous 60 completed calendar days
start_date = today - timedelta(days=60)
end_date = today

headers = {"X-Auth-Token": TOKEN}

# ==========================================
# 2. COLLECT HISTORICAL DATA IN BATCHES
# ==========================================

all_matches = {}
cursor = start_date
batch_number = 0

while cursor < end_date:

    # Keep each request safely under 10 days
    window_end = min(
        cursor + timedelta(days=9),
        end_date
    )

    params = {
        "dateFrom": cursor.isoformat(),
        "dateTo": window_end.isoformat(),
        "status": "FINISHED"
    }

    batch_number += 1

    print(
        f"Batch {batch_number}: "
        f"{cursor} to {window_end}",
        flush=True
    )

    response = requests.get(
        URL,
        headers=headers,
        params=params,
        timeout=30
    )

    if not response.ok:
        print("HTTP status:", response.status_code)
        print("API error:", response.text[:1000])
        raise RuntimeError("Football API request failed")

    batch_matches = response.json().get("matches", [])

    for match in batch_matches:
        if match.get("id") is not None:
            all_matches[match["id"]] = match

    print("Matches in batch:", len(batch_matches))

    cursor = window_end

    # Respect the free plan's rate limit
    if cursor < end_date:
        time.sleep(7)

matches = list(all_matches.values())

print("\nUnique matches retrieved:", len(matches))

# ==========================================
# 3. OPEN SQLITE DATABASE
# ==========================================

conn = sqlite3.connect("football.db")

conn.execute("""
CREATE TABLE IF NOT EXISTS matches (
    match_id INTEGER PRIMARY KEY,
    date TEXT,
    competition TEXT,
    home_team TEXT,
    away_team TEXT,
    home_goals INTEGER,
    away_goals INTEGER,
    status TEXT,
    updated_at TEXT
)
""")

# ==========================================
# 4. INSERT OR UPDATE MATCHES
# ==========================================

new_count = 0
changed_count = 0
unchanged_count = 0

for match in matches:

    score = match.get("score", {}).get("fullTime") or {}

    match_id = match["id"]

    values = (
        match["utcDate"],
        match.get("competition", {}).get("name"),
        match.get("homeTeam", {}).get("name"),
        match.get("awayTeam", {}).get("name"),
        score.get("home"),
        score.get("away"),
        match["status"]
    )

    old = conn.execute("""
        SELECT date, competition, home_team,
               away_team, home_goals, away_goals, status
        FROM matches
        WHERE match_id = ?
    """, (match_id,)).fetchone()

    timestamp = datetime.now(timezone.utc).isoformat()

    if old is None:

        conn.execute("""
            INSERT INTO matches (
                match_id, date, competition,
                home_team, away_team,
                home_goals, away_goals,
                status, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (match_id, *values, timestamp))

        new_count += 1

    elif old != values:

        conn.execute("""
            UPDATE matches
            SET date=?, competition=?, home_team=?,
                away_team=?, home_goals=?, away_goals=?,
                status=?, updated_at=?
            WHERE match_id=?
        """, (*values, timestamp, match_id))

        changed_count += 1

    else:
        unchanged_count += 1

# ==========================================
# 5. SAVE AND REPORT
# ==========================================

conn.commit()

total = conn.execute(
    "SELECT COUNT(*) FROM matches"
).fetchone()[0]

print("\n========== DATABASE SUMMARY ==========")
print("API batches:", batch_number)
print("New matches:", new_count)
print("Changed matches:", changed_count)
print("Unchanged matches:", unchanged_count)
print("Total stored matches:", total)
print("======================================")

conn.close()

print("\nHistorical database updated successfully!")

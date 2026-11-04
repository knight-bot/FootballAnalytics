
import os
import sqlite3
import requests
from datetime import datetime, timedelta, timezone

# ==========================================
# STEP 1: API CONFIGURATION
# ==========================================

TOKEN = os.environ["FOOTBALL_API_TOKEN"]

URL = "https://api.football-data.org/v4/matches"

today = datetime.now(timezone.utc).date()


params = {
    "dateFrom": (today - timedelta(days=9)).isoformat(),
    "dateTo": today.isoformat(),
    "status": "FINISHED"
}

headers = {
    "X-Auth-Token": TOKEN
}

# ==========================================
# STEP 2: COLLECT FOOTBALL DATA
# ==========================================

print("Connecting to football-data.org...")
print("Date range:", params["dateFrom"], "to", params["dateTo"])

response = requests.get(
    URL,
    headers=headers,
    params=params,
    timeout=30
)

print("HTTP status:", response.status_code)

# Display the actual API error, if any
if not response.ok:
    print("API error details:", response.text[:1000])
    raise RuntimeError("Football API request failed")

matches = response.json().get("matches", [])

print("Matches retrieved:", len(matches))

# ==========================================
# STEP 3: CONNECT TO SQLITE DATABASE
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
# STEP 4: DETECT NEW OR CHANGED MATCHES
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
            SET date = ?,
                competition = ?,
                home_team = ?,
                away_team = ?,
                home_goals = ?,
                away_goals = ?,
                status = ?,
                updated_at = ?
            WHERE match_id = ?
        """, (*values, timestamp, match_id))

        changed_count += 1

    else:
        unchanged_count += 1

# ==========================================
# STEP 5: SAVE DATABASE
# ==========================================

conn.commit()

total = conn.execute(
    "SELECT COUNT(*) FROM matches"
).fetchone()[0]

conn.close()

# ==========================================
# STEP 6: DISPLAY RESULTS
# ==========================================

print("\n========== UPDATE SUMMARY ==========")
print("New matches:", new_count)
print("Changed matches:", changed_count)
print("Unchanged matches:", unchanged_count)
print("Total stored matches:", total)
print("Database file: football.db")
print("====================================")

print("\nDatabase update completed successfully!")


import os
import sqlite3
import requests
from datetime import datetime, timedelta, timezone

# API configuration
TOKEN = os.environ["FOOTBALL_API_TOKEN"]
URL = "https://api.football-data.org/v4/matches"

today = datetime.now(timezone.utc).date()

params = {
    "dateFrom": (today - timedelta(days=30)).isoformat(),
    "dateTo": today.isoformat(),
    "status": "FINISHED"
}

# Collect completed match results
response = requests.get(
    URL,
    headers={"X-Auth-Token": TOKEN},
    params=params,
    timeout=30
)


if response.status_code != 200:
    print("HTTP status:", response.status_code)
    print("API error:", response.text[:1000])
    raise RuntimeError("Football API request failed")

matches = response.json().get("matches", [])

# Open persistent SQLite database
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

new_count = 0
changed_count = 0

for m in matches:
    score = m.get("score", {}).get("fullTime", {})
    mid = m["id"]

    values = (
        m["utcDate"],
        m["competition"]["name"],
        m["homeTeam"]["name"],
        m["awayTeam"]["name"],
        score.get("home"),
        score.get("away"),
        m["status"]
    )

    old = conn.execute("""
        SELECT date, competition, home_team,
               away_team, home_goals, away_goals, status
        FROM matches WHERE match_id = ?
    """, (mid,)).fetchone()

    timestamp = datetime.now(timezone.utc).isoformat()

    if old is None:
        conn.execute("""
            INSERT INTO matches
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (mid, *values, timestamp))
        new_count += 1

    elif old != values:
        conn.execute("""
            UPDATE matches
            SET date=?, competition=?, home_team=?,
                away_team=?, home_goals=?, away_goals=?,
                status=?, updated_at=?
            WHERE match_id=?
        """, (*values, timestamp, mid))
        changed_count += 1

conn.commit()
conn.close()

print(f"Retrieved: {len(matches)} matches")
print(f"New: {new_count}")
print(f"Changed: {changed_count}")
print("Database update completed.")

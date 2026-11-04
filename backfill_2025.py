
import os
import sqlite3
import requests
from datetime import datetime, timezone

# ===================================
# 1. RETRIEVE HISTORICAL MATCHES
# ===================================

token = os.environ["FOOTBALL_API_TOKEN"]

url = "https://api.football-data.org/v4/competitions/PL/matches"

response = requests.get(
    url,
    headers={"X-Auth-Token": token},
    params={
        "season": 2025,
        "status": "FINISHED"
    },
    timeout=30
)

if not response.ok:
    print("API error:", response.text[:1000])
    response.raise_for_status()

matches = response.json().get("matches", [])

print("Historical matches retrieved:", len(matches))

# ===================================
# 2. CONNECT TO EXISTING DATABASE
# ===================================

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

# ===================================
# 3. IMPORT HISTORICAL MATCHES
# ===================================

added = 0

for m in matches:

    score = m.get("score", {}).get("fullTime") or {}

    values = (
        m["id"],
        m["utcDate"],
        m["competition"]["name"],
        m["homeTeam"]["name"],
        m["awayTeam"]["name"],
        score.get("home"),
        score.get("away"),
        m["status"],
        datetime.now(timezone.utc).isoformat()
    )

    cursor = conn.execute("""
        INSERT OR IGNORE INTO matches (
            match_id, date, competition,
            home_team, away_team,
            home_goals, away_goals,
            status, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, values)

    added += cursor.rowcount

# ===================================
# 4. SAVE AND VERIFY
# ===================================

conn.commit()

total = conn.execute(
    "SELECT COUNT(*) FROM matches"
).fetchone()[0]

conn.close()

print("\n====== HISTORICAL IMPORT ======")
print("New records imported:", added)
print("Total database records:", total)
print("==============================")

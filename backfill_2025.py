
import os
import time
import sqlite3
import requests
from datetime import datetime, timezone

# ==========================================
# 1. CONFIGURATION
# ==========================================

TOKEN = os.environ["FOOTBALL_API_TOKEN"]

URL = (
    "https://api.football-data.org/v4/"
    "competitions/PL/matches"
)

SEASONS = [2023, 2024, 2025, 2026]

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
# 2. RETRIEVE AND IMPORT EACH SEASON
# ==========================================

total_added = 0

try:
    for index, season in enumerate(SEASONS):

        print(f"\nImporting {season}-{season+1} season")

        response = requests.get(
            URL,
            headers={"X-Auth-Token": TOKEN},
            params={
                "season": season,
                "status": "FINISHED"
            },
            timeout=30
        )

        if not response.ok:
            print("API error:", response.text[:1000])
            response.raise_for_status()

        matches = response.json().get("matches", [])

        print("Matches retrieved:", len(matches))

        added = 0

        for match in matches:

            score = (
                match.get("score", {}).get("fullTime") or {}
            )

            values = (
                match["id"],
                match["utcDate"],
                match["competition"]["name"],
                match["homeTeam"]["name"],
                match["awayTeam"]["name"],
                score.get("home"),
                score.get("away"),
                match["status"],
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

        total_added += added

        print("New matches imported:", added)

        # Respect API request limits
        if index < len(SEASONS) - 1:
            time.sleep(7)

    # Save changes only after successful collection
    conn.commit()

    total = conn.execute(
        "SELECT COUNT(*) FROM matches"
    ).fetchone()[0]

    print("\n========== FINAL SUMMARY ==========")
    print("Seasons processed:", len(SEASONS))
    print("New records added:", total_added)
    print("Total database records:", total)
    print("===================================")

finally:
    conn.close()

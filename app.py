
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

# ==========================================
# 1. DASHBOARD CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="Football Analytics",
    page_icon="⚽",
    layout="wide"
)

DB_FILE = Path(__file__).resolve().parent / "football.db"

# Check whether Streamlit has received a newer copy of the local
# historical-results database. This does not call the football API.
@st.fragment(run_every="5m")
def check_database_file():
    if not DB_FILE.exists():
        return

    current_version = DB_FILE.stat().st_mtime_ns
    previous_version = st.session_state.get("database_file_version")

    if previous_version is None:
        st.session_state["database_file_version"] = current_version
    elif current_version != previous_version:
        st.session_state["database_file_version"] = current_version
        st.cache_data.clear()
        st.rerun()


check_database_file()

st.title("⚽ Football Analytics")
st.caption("Historical football statistics and performance analysis")

# ==========================================
# 2. LOAD SQLITE DATABASE
# ==========================================

if not DB_FILE.exists():
    st.error("football.db was not found in the repository.")
    st.stop()


@st.cache_data(ttl=300)
def load_data(database_version):
    with sqlite3.connect(DB_FILE) as conn:
        data = pd.read_sql_query("""
            SELECT *
            FROM matches
            WHERE status = 'FINISHED'
              AND home_goals IS NOT NULL
              AND away_goals IS NOT NULL
        """, conn)

    return data


df = load_data(DB_FILE.stat().st_mtime_ns)

if df.empty:
    st.warning("The database has no completed matches.")
    st.stop()

df["date"] = pd.to_datetime(
    df["date"], utc=True, errors="coerce"
)

df = df.dropna(
    subset=["date", "competition", "home_team", "away_team"]
)

df["home_goals"] = df["home_goals"].astype(int)
df["away_goals"] = df["away_goals"].astype(int)

# ==========================================
# 3. ORGANIZE MATCHES INTO SEASONS
# ==========================================

def get_season(row):
    year = row["date"].year
    month = row["date"].month

    # Calendar-year competitions
    if row["competition"] in [
        "Campeonato Brasileiro Série A",
        "Copa Libertadores"
    ]:
        return str(year)

    # Typical European football season
    start = year if month >= 7 else year - 1
    return f"{start}-{(start + 1) % 100:02d}"


df["season"] = df.apply(get_season, axis=1)

# ==========================================
# 4. SIDEBAR FILTERS
# ==========================================

st.sidebar.header("Filters")

# Reload the latest database file that has been deployed with this app.
if st.sidebar.button("Reload database", help="Reloads the database copy deployed to Streamlit."):
    st.cache_data.clear()
    st.rerun()

if "updated_at" in df.columns:
    last_changed = pd.to_datetime(
        df["updated_at"], utc=True, errors="coerce"
    ).max()
    if pd.notna(last_changed):
        st.sidebar.caption(
            "Latest stored change: "
            + last_changed.strftime("%d %b %Y %H:%M UTC")
        )

st.sidebar.caption(
    "Checks for changes to the deployed historical database every "
    "5 minutes while this page is open. "
    "This does not trigger the GitHub data collector."
)

competitions = sorted(df["competition"].unique())

default_index = (
    competitions.index("Premier League")
    if "Premier League" in competitions else 0
)

competition = st.sidebar.selectbox(
    "Competition",
    competitions,
    index=default_index
)

available_seasons = sorted(
    df.loc[
        df["competition"] == competition, "season"
    ].unique(),
    reverse=True
)

season = st.sidebar.selectbox(
    "Season",
    available_seasons
)

games = df[
    (df["competition"] == competition)
    & (df["season"] == season)
].copy()

st.subheader(f"{competition} | {season}")

# ==========================================
# 5. GENERAL STATISTICS
# ==========================================

teams = sorted(
    set(games["home_team"]).union(games["away_team"])
)

total_goals = (
    games["home_goals"] + games["away_goals"]
).sum()

c1, c2, c3, c4 = st.columns(4)

c1.metric("Matches", len(games))
c2.metric("Teams", len(teams))
c3.metric("Total goals", int(total_goals))
c4.metric(
    "Goals per match",
    round(total_goals / len(games), 2)
)

st.caption(
    f"Data coverage: "
    f"{games['date'].min().strftime('%d %b %Y')} to "
    f"{games['date'].max().strftime('%d %b %Y')}"
)

# ==========================================
# 6. CALCULATE TEAM PERFORMANCE
# ==========================================

home = pd.DataFrame({
    "Team": games["home_team"],
    "Venue": "Home",
    "GF": games["home_goals"],
    "GA": games["away_goals"]
})

away = pd.DataFrame({
    "Team": games["away_team"],
    "Venue": "Away",
    "GF": games["away_goals"],
    "GA": games["home_goals"]
})

team_games = pd.concat(
    [home, away], ignore_index=True
)

team_games["Win"] = (
    team_games["GF"] > team_games["GA"]
).astype(int)

team_games["Draw"] = (
    team_games["GF"] == team_games["GA"]
).astype(int)

team_games["Loss"] = (
    team_games["GF"] < team_games["GA"]
).astype(int)

team_games["Points"] = (
    team_games["Win"] * 3 + team_games["Draw"]
)

stats = team_games.groupby("Team").agg(
    Matches=("GF", "count"),
    Wins=("Win", "sum"),
    Draws=("Draw", "sum"),
    Losses=("Loss", "sum"),
    Goals_For=("GF", "sum"),
    Goals_Against=("GA", "sum"),
    Points=("Points", "sum")
).reset_index()

stats["Goal_Difference"] = (
    stats["Goals_For"] - stats["Goals_Against"]
)

stats["Goals_Per_Match"] = (
    stats["Goals_For"] / stats["Matches"]
).round(2)

stats["Win_Rate"] = (
    stats["Wins"] / stats["Matches"] * 100
).round(1)

stats = stats.sort_values(
    ["Points", "Goal_Difference"],
    ascending=False
)

# ==========================================
# 7. PERFORMANCE TABLE
# ==========================================

st.divider()
st.subheader("Team Performance")

st.dataframe(
    stats,
    hide_index=True,
    use_container_width=True
)

st.caption(
    "Statistics reflect matches available in the database, "
    "not necessarily the official final league standings."
)

# ==========================================
# 8. SCORING VISUALIZATION
# ==========================================

st.divider()
st.subheader("Average Goals Scored per Match")

chart_data = (
    stats.sort_values("Goals_Per_Match")
    .set_index("Team")[["Goals_Per_Match"]]
)

st.bar_chart(chart_data)

# ==========================================
# 9. TEAM COMPARISON
# ==========================================

st.divider()
st.subheader("Compare Two Teams")

if len(teams) >= 2:

    left, right = st.columns(2)

    with left:
        team_a = st.selectbox(
            "First team", teams, index=0
        )

    with right:
        team_b = st.selectbox(
            "Second team", teams, index=1
        )

    if team_a == team_b:
        st.info("Select two different teams.")

    else:
        indexed = stats.set_index("Team")

        a = indexed.loc[team_a]
        b = indexed.loc[team_b]

        metrics = [
            "Matches", "Wins", "Draws",
            "Losses", "Goals_For",
            "Goals_Against", "Goal_Difference",
            "Goals_Per_Match", "Win_Rate"
        ]

        comparison = pd.DataFrame({
            "Statistic": metrics,
            team_a: [a[m] for m in metrics],
            team_b: [b[m] for m in metrics]
        })

        st.dataframe(
            comparison,
            hide_index=True,
            use_container_width=True
        )

        st.subheader("Home and Away Performance")

        venue_stats = (
            team_games[
                team_games["Team"].isin(
                    [team_a, team_b]
                )
            ]
            .groupby(["Team", "Venue"])
            .agg(
                Matches=("GF", "count"),
                Wins=("Win", "sum"),
                Goals_For=("GF", "sum"),
                Goals_Against=("GA", "sum")
            )
            .reset_index()
        )

        st.dataframe(
            venue_stats,
            hide_index=True,
            use_container_width=True
        )

# ==========================================
# 10. MATCH HISTORY
# ==========================================

st.divider()
st.subheader("Recent Completed Matches")

recent = games.sort_values(
    "date", ascending=False
).copy()

recent["Date"] = recent["date"].dt.strftime("%d %b %Y")

recent["Score"] = (
    recent["home_goals"].astype(str)
    + " - "
    + recent["away_goals"].astype(str)
)

recent = recent[
    ["Date", "home_team", "Score", "away_team"]
].rename(columns={
    "home_team": "Home Team",
    "away_team": "Away Team"
})

st.dataframe(
    recent.head(30),
    hide_index=True,
    use_container_width=True
)

# ==========================================
# 11. DATABASE DETAILS
# ==========================================

st.divider()
st.caption(
    f"Database contains {len(df):,} completed match records. "
    "Season labels are inferred from match dates. "
    "This dashboard provides descriptive historical analysis."
)

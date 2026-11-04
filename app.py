
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
# 11. ADVANCED HISTORICAL ANALYTICS
# ==========================================

st.divider()
st.header("Historical Team Analytics")
st.caption(
    "Explore completed results across seasons. These are descriptive "
    "statistics, not forecasts or official standings."
)

# Build one record per team per completed match, across all available
# seasons of the selected competition.
history_games = df[df["competition"] == competition].copy()

home_history = pd.DataFrame({
    "Season": history_games["season"],
    "Date": history_games["date"],
    "Team": history_games["home_team"],
    "Opponent": history_games["away_team"],
    "Venue": "Home",
    "GF": history_games["home_goals"],
    "GA": history_games["away_goals"],
})

away_history = pd.DataFrame({
    "Season": history_games["season"],
    "Date": history_games["date"],
    "Team": history_games["away_team"],
    "Opponent": history_games["home_team"],
    "Venue": "Away",
    "GF": history_games["away_goals"],
    "GA": history_games["home_goals"],
})

historical_team_matches = pd.concat(
    [home_history, away_history], ignore_index=True
)
historical_team_matches["Win"] = (
    historical_team_matches["GF"] > historical_team_matches["GA"]
).astype(int)
historical_team_matches["Draw"] = (
    historical_team_matches["GF"] == historical_team_matches["GA"]
).astype(int)
historical_team_matches["Points"] = (
    3 * historical_team_matches["Win"]
    + historical_team_matches["Draw"]
)

history_teams = sorted(historical_team_matches["Team"].unique())
team_for_history = st.selectbox(
    "Select a team to study",
    history_teams,
    key="historical_team_selection",
)

selected_history = historical_team_matches[
    historical_team_matches["Team"] == team_for_history
].copy()

# 11A: Season-to-season performance
st.subheader("Season-by-Season Performance")

season_history = (
    selected_history.groupby("Season")
    .agg(
        Matches=("GF", "count"),
        Wins=("Win", "sum"),
        Goals_For=("GF", "sum"),
        Goals_Against=("GA", "sum"),
        Points=("Points", "sum"),
    )
    .reset_index()
    .sort_values("Season")
)
season_history["Goals/game"] = (
    season_history["Goals_For"] / season_history["Matches"]
).round(2)
season_history["Conceded/game"] = (
    season_history["Goals_Against"] / season_history["Matches"]
).round(2)
season_history["Points/game"] = (
    season_history["Points"] / season_history["Matches"]
).round(2)

st.dataframe(season_history, hide_index=True, use_container_width=True)
if len(season_history) > 1:
    st.line_chart(
        season_history.set_index("Season")[
            ["Goals/game", "Conceded/game"]
        ]
    )
    st.bar_chart(
        season_history.set_index("Season")[["Points/game"]]
    )
else:
    st.info("Only one season is available for this team.")

st.caption(
    "Per-match rates allow comparison between partial and completed "
    "seasons, but small samples are less reliable."
)

# 11B: Home and away splits in the selected season
current_team_games = selected_history[
    selected_history["Season"] == season
].copy()

st.subheader(f"Home vs Away | {season}")

if current_team_games.empty:
    st.info(f"{team_for_history} has no recorded matches in {season}.")
else:
    venue_summary = (
        current_team_games.groupby("Venue")
        .agg(
            Matches=("GF", "count"),
            Wins=("Win", "sum"),
            Goals_For=("GF", "sum"),
            Goals_Against=("GA", "sum"),
            Points=("Points", "sum"),
        )
        .reset_index()
    )
    venue_summary["Goals/game"] = (
        venue_summary["Goals_For"] / venue_summary["Matches"]
    ).round(2)
    venue_summary["Conceded/game"] = (
        venue_summary["Goals_Against"] / venue_summary["Matches"]
    ).round(2)
    venue_summary["Points/game"] = (
        venue_summary["Points"] / venue_summary["Matches"]
    ).round(2)

    st.dataframe(venue_summary, hide_index=True, use_container_width=True)
    st.bar_chart(
        venue_summary.set_index("Venue")[
            ["Goals/game", "Conceded/game"]
        ]
    )

    # 11C: Retrospective opponent-strength categories
    st.subheader("Results by Opponent Strength")
    league_rank = stats.copy()
    league_rank["Points/game"] = (
        league_rank["Points"] / league_rank["Matches"]
    )
    league_rank = league_rank.sort_values(
        ["Points/game", "Goal_Difference"],
        ascending=[False, False],
    )
    upper_half = set(
        league_rank.head(max(1, len(league_rank) // 2))["Team"]
    )

    current_team_games["Opponent group"] = (
        current_team_games["Opponent"]
        .map(lambda t: "Upper half" if t in upper_half else "Lower half")
    )

    opponent_summary = (
        current_team_games.groupby("Opponent group")
        .agg(
            Matches=("GF", "count"),
            Wins=("Win", "sum"),
            Goals_For=("GF", "sum"),
            Goals_Against=("GA", "sum"),
            Points=("Points", "sum"),
        )
        .reset_index()
    )
    opponent_summary["Points/game"] = (
        opponent_summary["Points"] / opponent_summary["Matches"]
    ).round(2)
    opponent_summary["Goals/game"] = (
        opponent_summary["Goals_For"] / opponent_summary["Matches"]
    ).round(2)
    opponent_summary["Conceded/game"] = (
        opponent_summary["Goals_Against"] / opponent_summary["Matches"]
    ).round(2)

    st.dataframe(
        opponent_summary, hide_index=True, use_container_width=True
    )
    st.caption(
        "Upper/lower half is based on each opponent's points per game "
        "in the selected season, using currently stored final results. "
        "This is a retrospective grouping, not their strength at "
        "the time each match was played. Points deductions are not included."
    )

    # 11D: Match-by-match rolling historical form
    st.subheader("Match-by-Match Form")
    form = current_team_games.sort_values("Date").reset_index(drop=True)
    form["Match number"] = range(1, len(form) + 1)
    form["Points/game (up to last 5)"] = (
        form["Points"].rolling(window=5, min_periods=1).mean()
    )
    form["Goals/game (up to last 5)"] = (
        form["GF"].rolling(window=5, min_periods=1).mean()
    )

    st.line_chart(
        form.set_index("Match number")[
            ["Points/game (up to last 5)", "Goals/game (up to last 5)"]
        ]
    )
    st.caption(
        "Each point averages the current and up to four earlier "
        "completed matches. Early points use fewer than five games."
    )

# ==========================================
# 12. DATABASE DETAILS
# ==========================================

st.divider()
st.caption(
    f"Database contains {len(df):,} completed match records. "
    "Season labels are inferred from match dates. "
    "This dashboard provides descriptive historical analysis."
)

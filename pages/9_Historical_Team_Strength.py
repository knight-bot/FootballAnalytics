"""Read-only Streamlit dashboard for historical league-adjusted team strength."""
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd
import streamlit as st

from historical_reports import list_competitions, list_seasons, season_label
from historical_team_strength import analyze_season, team_strength

st.set_page_config(
    page_title="Historical Team Strength | FootballAnalytics",
    page_icon="📊", layout="wide",
)
st.title("Historical Team Strength")
st.caption(
    "Attack and defense indices calculated exclusively from recorded "
    "completed match results. No odds, future fixtures, or model forecasts."
)

DB = Path(__file__).resolve().parent.parent / "football.db"
if not DB.exists():
    st.error("football.db is missing from the deployment.")
    st.stop()


def connect_ro():
    return sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)


@st.cache_data(ttl=300, show_spinner=False)
def options(db_stamp):
    with closing(connect_ro()) as conn:
        competitions = list_competitions(conn)
        seasons = {c: list_seasons(conn, c) for c in competitions}
    return competitions, seasons


@st.cache_data(ttl=300, show_spinner=False)
def compute(db_stamp, competition, year, prior):
    with closing(connect_ro()) as conn:
        return analyze_season(conn, competition, year, prior_matches=prior)


db_stamp = DB.stat().st_mtime_ns
competitions, seasons = options(db_stamp)
if not competitions:
    st.warning("No recorded completed matches are available.")
    st.stop()

c1, c2, c3 = st.columns([2, 1.4, 1])
with c1:
    competition = st.selectbox("Competition", competitions)
with c2:
    years = seasons[competition]
    if not years:
        st.warning("No historical season available for this competition.")
        st.stop()
    year = st.selectbox("July–June season", years, format_func=season_label)
with c3:
    prior = st.selectbox(
        "Baseline shrinkage (matches)",
        options=[0, 3, 5, 10],
        index=2,
        help=(
            "Adds the equivalent of several league-average matches to "
            "stabilize extreme ratios in small samples. Not validation."
        ),
    )

analysis = compute(db_stamp, competition, year, prior)
if not analysis["matches"]:
    st.warning("No valid completed results available for this selection.")
    st.stop()

st.subheader("Observed league baselines")
a, b, c, d = st.columns(4)
a.metric("Valid completed fixtures", analysis["matches"])
b.metric(
    "Home goals per fixture",
    f"{analysis['league_home_goals_per_match']:.2f}",
)
c.metric(
    "Away goals per fixture",
    f"{analysis['league_away_goals_per_match']:.2f}",
)
d.metric(
    "Goals per team-match",
    f"{analysis['league_goals_per_team_match']:.2f}",
)
st.caption(
    f"Window: {analysis['season']} | "
    f"First stored fixture: {analysis['date_first']} | "
    f"Last stored fixture: {analysis['date_last']} | "
    f"Excluded completed rows: {analysis['excluded']}"
)

if analysis["warnings"]:
    with st.expander("Data-quality and interpretation warnings", expanded=True):
        for warning in analysis["warnings"]:
            st.markdown(f"- {warning}")

st.divider()
st.subheader("Historical team comparison")

def value_or_none(value):
    return round(value, 3) if value is not None else None

records = []
for entry in analysis["teams"]:
    overall = entry["scopes"]["overall"]
    records.append({
        "Team": entry["name"],
        "Matches": overall["played"],
        "Wins": overall["wins"],
        "Draws": overall["draws"],
        "Losses": overall["losses"],
        "GF": overall["goals_for"],
        "GA": overall["goals_against"],
        "Pts (recorded)": overall["points"],
        "Attack index (raw)": value_or_none(overall["attack_index"]),
        "Attack index (shrunk)": value_or_none(overall["attack_shrunk"]),
        "Defense index (raw)": value_or_none(overall["defense_index"]),
        "Defense index (shrunk)": value_or_none(overall["defense_shrunk"]),
        "Sample caution": "Yes" if overall["played"] < 5 else "No",
    })
frame = pd.DataFrame(records)
st.dataframe(
    frame.sort_values(
        ["Pts (recorded)", "Team"], ascending=[False, True]
    ),
    hide_index=True, use_container_width=True,
)
st.download_button(
    "Download historical team-strength table (.csv)",
    frame.to_csv(index=False).encode("utf-8"),
    file_name=f"historical_team_strength_{year}.csv",
    mime="text/csv",
)
st.caption(
    "This is a comparison of locally recorded matches, not official "
    "standings. Teams may have different numbers of recorded games."
)

st.divider()
st.subheader("Explore one team's historical profile")
names = [row["name"] for row in analysis["teams"]]
team = st.selectbox("Team", names)
selected = team_strength(analysis, team)
summary = selected["scopes"]["overall"]
x, y, z = st.columns(3)
x.metric("Recorded matches", summary["played"])
y.metric("Recorded goals for / against",
         f"{summary['goals_for']} / {summary['goals_against']}")
z.metric("Recorded points", summary["points"])

venues = []
for label, key in (
    ("All", "overall"), ("Home", "home"), ("Away", "away")
):
    scope = selected["scopes"][key]
    venues.append({
        "Venue": label,
        "Played": scope["played"],
        "GF/match": value_or_none(scope["goals_for_per_match"]),
        "GA/match": value_or_none(scope["goals_against_per_match"]),
        "Attack index": value_or_none(scope["attack_index"]),
        "Attack shrunk": value_or_none(scope["attack_shrunk"]),
        "Defense index": value_or_none(scope["defense_index"]),
        "Defense shrunk": value_or_none(scope["defense_shrunk"]),
        "Sample": scope["sample_flag"],
    })
st.dataframe(pd.DataFrame(venues), hide_index=True, use_container_width=True)

plot_data = pd.DataFrame([
    {
        "Venue": row["Venue"],
        "Attack (shrunk)": row["Attack shrunk"],
        "Defense (shrunk)": row["Defense shrunk"],
    }
    for row in venues
]).set_index("Venue")
st.bar_chart(plot_data)

st.info(
    "**How to read indices:** 1.00 means the same goal rate as the "
    "recorded league baseline. For attack, higher means more goals "
    "scored per match; for defense, lower means fewer conceded. "
    "These are descriptive, not probabilities or future-match assessments."
)
if any(row["Played"] < 5 for row in venues):
    st.warning(
        "This team has fewer than five recorded games in at least one "
        "venue category. Venue-specific comparisons are unstable."
    )
with st.expander("Match IDs used for this team's calculations"):
    st.write(summary["match_ids"])
st.caption(
    "Source: football-data.org completed results in the local database. "
    "No Sportmonks statistics are mixed into these goal-based indices."
)

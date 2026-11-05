"""One-click historical football research export for ChatGPT.

The export runs locally from football.db and does not require OpenAI API
credentials. Sportmonks examples remain independent of the selected team.
"""
import sqlite3
from contextlib import closing
from pathlib import Path

import streamlit as st

from chatgpt_research_export import (
    MAX_SPORTMONKS_CASES, build_chatgpt_research_pack,
)
from historical_reports import (
    list_competitions, list_seasons, list_sportmonks_fixtures,
    list_teams, season_label,
)

st.set_page_config(
    page_title="ChatGPT Research Export | Football Analytics",
    page_icon="📄", layout="wide",
)
st.title("ChatGPT-ready Historical Research Export")
st.caption(
    "One Markdown file containing recorded results, supporting match IDs, "
    "optional completed-match Sportmonks examples, and data-quality warnings."
)
st.info(
    "No AI API key is necessary. This page only reads the saved historical "
    "database; it makes no OpenAI or Sportmonks requests."
)

DB_PATH = Path(__file__).resolve().parent.parent / "football.db"
if not DB_PATH.exists():
    st.error("football.db is missing in this deployment.")
    st.stop()


def open_database():
    return sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode=ro", uri=True,
    )


@st.cache_data(ttl=300, show_spinner=False)
def available_data(db_version):
    with closing(open_database()) as conn:
        competitions = list_competitions(conn)
        seasons = {
            comp: list_seasons(conn, comp) for comp in competitions
        }
        fixtures = list_sportmonks_fixtures(conn)
    return competitions, seasons, fixtures


@st.cache_data(ttl=300, show_spinner=False)
def teams_for(db_version, competition, year):
    with closing(open_database()) as conn:
        return list_teams(conn, competition, year)


@st.cache_data(ttl=300, show_spinner=False)
def generate_pack(db_version, competition, year, team, ids):
    with closing(open_database()) as conn:
        return build_chatgpt_research_pack(
            conn, competition, year, team, fixture_ids=list(ids),
        )


version = DB_PATH.stat().st_mtime_ns
competitions, seasons, imported_fixtures = available_data(version)
if not competitions:
    st.warning("No recorded completed results are available for export.")
    st.stop()

st.subheader("1. Select the recorded team results")
competition = st.selectbox(
    "Competition", competitions,
    index=(
        competitions.index("Premier League")
        if "Premier League" in competitions else 0
    ),
)
season_years = seasons.get(competition, [])
if not season_years:
    st.warning("No valid historical date windows exist for this competition.")
    st.stop()

year = st.selectbox(
    "Historical July–June window", season_years,
    format_func=season_label,
)
teams = teams_for(version, competition, year)
if not teams:
    st.warning("No teams have completed results in this date window.")
    st.stop()
team = st.selectbox("Team", teams)

st.divider()
st.subheader("2. Optional: Select separate Sportmonks case studies")
st.caption(
    "These fixtures are NOT automatically linked to the selected team. "
    "Choose them only to include independent completed-match examples "
    "such as xG and Pressure Index coverage."
)

ids = []
if imported_fixtures:
    labels = {
        row["id"]: (
            f"{row['name']} | {row['date']} | "
            f"Sportmonks ID {row['id']}"
        )
        for row in imported_fixtures
    }
    ids = st.multiselect(
        f"Historical Sportmonks fixtures (maximum {MAX_SPORTMONKS_CASES})",
        [row["id"] for row in imported_fixtures],
        default=[],
        format_func=lambda fid: labels[fid],
        max_selections=MAX_SPORTMONKS_CASES,
    )
else:
    st.info("No historical Sportmonks fixtures are stored yet.")

st.divider()
st.subheader("3. Generate and download your report")
try:
    pack = generate_pack(version, competition, year, team, tuple(ids))
except (ValueError, sqlite3.Error) as exc:
    st.error(f"Unable to generate report: {exc}")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Recorded team matches", pack["team_match_count"])
c2.metric("Operator-reviewed linked fixtures", pack["reviewed_link_count"])
c3.metric("Separate Sportmonks case studies", pack["sportmonks_fixture_count"])
c4.metric("Selected fixture audit flags", pack["audit_warning_count"])

st.download_button(
    "Download ChatGPT research report (.md)",
    data=pack["markdown"].encode("utf-8"),
    file_name=f"football_historical_research_{year}.md",
    mime="text/markdown",
    type="primary",
)
st.caption(
    "Download the file and upload it to ChatGPT for a critical historical "
    "analysis. The generated file includes a ready-to-use analysis request."
)

with st.expander("Preview report and source IDs"):
    st.text_area(
        "Complete Markdown report",
        value=pack["markdown"],
        height=480,
    )

st.warning(
    "Only manually operator-reviewed associations listed in Part A.1 "
    "are linked to the selected team's results. Independently selected "
    "Sportmonks fixtures remain unrelated case studies. "
    "All coverage is limited to the stored historical sample."
)

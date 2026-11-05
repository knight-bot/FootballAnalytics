"""Evidence-first reports using stored, completed football matches only."""
import sqlite3
from contextlib import closing
from pathlib import Path

import streamlit as st

from historical_reports import (
    build_sportmonks_report,
    build_team_report,
    list_competitions,
    list_seasons,
    list_sportmonks_fixtures,
    list_teams,
    season_label,
)

st.set_page_config(
    page_title="Historical Research Reports | Football Analytics",
    page_icon="📝",
    layout="wide",
)
st.title("Historical Football Research Reports")
st.caption(
    "Source-labeled, reproducible reports from your local SQLite database. "
    "No external requests or generative AI are used on this page."
)
st.info(
    "These reports describe completed matches. They cannot forecast upcoming "
    "results, verify current news, or establish a team's present form."
)

DB_PATH = Path(__file__).resolve().parent.parent / "football.db"
if not DB_PATH.is_file():
    st.error("The football.db file is not available in this deployment.")
    st.stop()


def connect_read_only():
    return sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode=ro", uri=True,
    )


@st.cache_data(ttl=300, show_spinner=False)
def load_options(db_version):
    with closing(connect_read_only()) as conn:
        competitions = list_competitions(conn)
        seasons = {
            competition: list_seasons(conn, competition)
            for competition in competitions
        }
        fixtures = list_sportmonks_fixtures(conn)
        return competitions, seasons, fixtures


@st.cache_data(ttl=300, show_spinner=False)
def teams_for(db_version, competition, year):
    with closing(connect_read_only()) as conn:
        return list_teams(conn, competition, year)


@st.cache_data(ttl=300, show_spinner=False)
def team_report(db_version, competition, year, team):
    with closing(connect_read_only()) as conn:
        return build_team_report(conn, competition, year, team)


@st.cache_data(ttl=300, show_spinner=False)
def fixture_report(db_version, fixture_id):
    with closing(connect_read_only()) as conn:
        return build_sportmonks_report(conn, fixture_id)


db_version = DB_PATH.stat().st_mtime_ns
competitions, seasons_by_competition, fixtures = load_options(db_version)

team_tab, fixture_tab = st.tabs([
    "Team season research", "Sportmonks fixture research",
])

with team_tab:
    st.subheader("Retrospective season report")
    if not competitions:
        st.warning("No completed match results have been saved.")
    else:
        comp = st.selectbox(
            "Competition", competitions,
            index=(competitions.index("Premier League")
                   if "Premier League" in competitions else 0),
            key="research_comp",
        )
        available_years = seasons_by_competition.get(comp, [])
        if not available_years:
            st.warning("No date-valid seasons were found for this competition.")
        else:
            year = st.selectbox(
                "July–June date window",
                available_years,
                format_func=season_label,
                key="research_season",
            )
            teams = teams_for(db_version, comp, year)
            if not teams:
                st.warning("There are no recorded teams in this time window.")
            else:
                team = st.selectbox(
                    "Team", teams, key="research_team",
                )
                report = team_report(db_version, comp, year, team)
                summary = report["summary"]
                if summary["matches"]:
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Recorded matches", summary["played"])
                    c2.metric("Wins", summary["wins"])
                    c3.metric("Recorded goals scored", summary["gf"])
                    c4.metric("Recorded goals conceded", summary["ga"])
                st.markdown(report["markdown"])
                st.download_button(
                    "Download team research report (.md)",
                    data=report["markdown"].encode("utf-8"),
                    file_name=f"team_research_{year}.md",
                    mime="text/markdown",
                )

with fixture_tab:
    st.subheader("Imported Sportmonks match report")
    if not fixtures:
        st.info(
            "No manually imported historical Sportmonks fixtures are stored. "
            "Use the existing historical-import GitHub Actions workflow "
            "with a completed fixture ID."
        )
    else:
        fixture_choices = [f["id"] for f in fixtures]
        labels = {
            f["id"]: f"{f['name']} | {f['date']} | ID {f['id']}"
            for f in fixtures
        }
        fixture_id = st.selectbox(
            "Historical fixture",
            fixture_choices,
            format_func=lambda fid: labels[fid],
            key="research_fixture",
        )
        try:
            report = fixture_report(db_version, fixture_id)
        except ValueError as exc:
            st.warning(str(exc))
        else:
            st.markdown(report["markdown"])
            st.download_button(
                "Download fixture research report (.md)",
                data=report["markdown"].encode("utf-8"),
                file_name=f"sportmonks_fixture_{fixture_id}.md",
                mime="text/markdown",
            )

st.divider()
st.caption(
    "Research integrity: Sportmonks IDs and football-data.org IDs are not "
    "interchangeable. The report intentionally does not merge these datasets. "
    "Provider data may be incomplete, and the July–June window is only a "
    "date-derived grouping, not a claim about official season coverage."
)

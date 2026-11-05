"""Historical xG coverage and actual-goals comparison, read-only."""
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd
import streamlit as st

from historical_reports import list_competitions, list_seasons, list_teams, season_label
from historical_xg_analysis import analyze_team_xg, imported_xg_coverage

st.set_page_config(
    page_title="Historical xG Analysis | FootballAnalytics",
    page_icon="📐", layout="wide",
)
st.title("Historical xG Coverage and Analysis")
st.caption(
    "Compare actual goals against stored standard xG (Sportmonks type 5304) "
    "only in completed matches with currently valid, operator-reviewed links."
)
st.info(
    "This is historical descriptive analysis, not future-match estimation. "
    "The two providers are linked only after a human attests that "
    "the original final scores agree."
)

DB_PATH = Path(__file__).resolve().parent.parent / "football.db"
if not DB_PATH.exists():
    st.error("football.db is unavailable.")
    st.stop()


def db():
    return sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode=ro", uri=True,
    )


@st.cache_data(ttl=300, show_spinner=False)
def available(db_version):
    with closing(db()) as conn:
        comps = list_competitions(conn)
        return (
            comps,
            {c: list_seasons(conn, c) for c in comps},
            imported_xg_coverage(conn),
        )


@st.cache_data(ttl=300, show_spinner=False)
def options_and_analysis(db_version, competition, year):
    with closing(db()) as conn:
        return list_teams(conn, competition, year)


@st.cache_data(ttl=300, show_spinner=False)
def get_analysis(db_version, competition, year, team):
    with closing(db()) as conn:
        return analyze_team_xg(conn, competition, year, team)


version = DB_PATH.stat().st_mtime_ns
competitions, seasons, coverage = available(version)

st.subheader("1. Coverage of imported Sportmonks fixtures")
a, b, c, d = st.columns(4)
a.metric("Locally imported", coverage["imported"])
b.metric("Standard xG: both sides", coverage["complete_both_sides"])
c.metric("Standard xG: one side", coverage["partial_one_side"])
d.metric("Standard xG: neither side", coverage["missing_both_sides"])
st.caption(
    "Counts refer only to the fixtures imported into this SQLite database, "
    "NOT every match in the Premier League or the provider's catalog."
)
if coverage["rows"]:
    with st.expander("Inspect imported historical fixtures and missing xG"):
        st.dataframe(
            pd.DataFrame(coverage["rows"]),
            hide_index=True, use_container_width=True,
        )
        st.download_button(
            "Download Sportmonks xG coverage table (.csv)",
            data=pd.DataFrame(coverage["rows"]).to_csv(index=False),
            file_name="sportmonks_historical_xg_coverage.csv",
            mime="text/csv",
        )
else:
    st.warning("No Sportmonks fixtures have been imported in this deployment.")

st.divider()
st.subheader("2. Goals versus xG for a selected recorded team")
if not competitions:
    st.warning("No locally recorded completed football-data.org results.")
    st.stop()
competition = st.selectbox("Competition", competitions)
years = seasons.get(competition, [])
if not years:
    st.warning("No recorded season for this competition.")
    st.stop()
year = st.selectbox("July–June historical season", years, format_func=season_label)
teams = options_and_analysis(version, competition, year)
if not teams:
    st.warning("No completed team results for this selection.")
    st.stop()
team = st.selectbox("Team", teams)

analysis = get_analysis(version, competition, year, team)
e, f, g, h = st.columns(4)
e.metric("Valid completed results", analysis["valid_completed"])
f.metric("Reviewed fixture links", analysis["reviewed_links"])
g.metric("Reviewed links with both xG values", analysis["xg_complete_links"])
h.metric("Reviewed links missing xG", analysis["reviewed_missing_xg"])

if not analysis["match_rows"]:
    st.warning(
        "No eligible reviewed fixture has complete standard xG for both teams. "
        "This is missing verified data, not evidence that xG is zero."
    )
    st.caption(
        "Verify matching fixtures on Historical Fixture Link Review, then "
        "confirm corresponding provider final scores through the manual "
        "GitHub Action. Only then will reviewed xG appear here."
    )
else:
    st.subheader("Observed aggregate for included historical matches")
    x1, x2, x3 = st.columns(3)
    x1.metric("Recorded goals", analysis["total_goals_for"])
    x2.metric("Standard xG", f"{analysis['total_xg_for']:.2f}")
    x3.metric("Goals minus xG", f"{analysis['goals_minus_xg']:+.2f}")
    st.caption(
        "These aggregates cover only the reviewed matches with "
        "complete xG, not the team's entire recorded season."
    )
    st.subheader("Source-backed completed matches")
    df = pd.DataFrame(analysis["match_rows"])
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.download_button(
        "Download reviewed historical xG evidence (.csv)",
        data=df.to_csv(index=False),
        file_name=f"reviewed_historical_xg_{year}.csv",
        mime="text/csv",
    )
    chart = pd.DataFrame({
        "Statistic": ["Goals for", "xG for", "Goals against", "xG against"],
        "Historical total": [
            analysis["total_goals_for"], analysis["total_xg_for"],
            analysis["total_goals_against"], analysis["total_xg_against"],
        ],
    }).set_index("Statistic")
    st.bar_chart(chart)

with st.expander("Data quality and interpretation warnings", expanded=True):
    for warning in analysis["warnings"]:
        st.markdown(f"- {warning}")

st.caption(
    "No Sportmonks API call or write happens on this page. Historical "
    "goals are from football-data.org and standard xG is from Sportmonks; "
    "operator-reviewed links are required for every joined observation."
)

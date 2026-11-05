"""Read-only per-match historical results-to-xG coverage audit."""
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd
import streamlit as st

from historical_coverage_matrix import coverage_matrix, coverage_markdown
from historical_season_quality import build_quality_report, quality_markdown
from historical_reports import list_competitions, list_seasons, list_teams, season_label

st.set_page_config(
    page_title="Historical Coverage Audit | FootballAnalytics",
    page_icon="🧾", layout="wide",
)
st.title("Historical Fixture and xG Coverage Audit")
st.caption(
    "Inspect each locally recorded completed fixture and see exactly "
    "why advanced statistics can or cannot be linked to it."
)
st.info(
    "This is a read-only historical data-quality tool. Candidate links "
    "are NOT verified. Reviewed links depend on a human comparison of "
    "the two providers' original final scores."
)

DB_PATH = Path(__file__).resolve().parent.parent / "football.db"
if not DB_PATH.exists():
    st.error("football.db is unavailable in this deployment.")
    st.stop()


def open_readonly():
    return sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)


@st.cache_data(ttl=300, show_spinner=False)
def options(db_version):
    with closing(open_readonly()) as conn:
        competitions = list_competitions(conn)
        seasons = {
            comp: list_seasons(conn, comp) for comp in competitions
        }
    return competitions, seasons


@st.cache_data(ttl=300, show_spinner=False)
def team_options(db_version, competition, year):
    with closing(open_readonly()) as conn:
        return list_teams(conn, competition, year)


@st.cache_data(ttl=300, show_spinner=False)
def inspect(db_version, competition, year, team):
    with closing(open_readonly()) as conn:
        return coverage_matrix(conn, competition, year, team)


@st.cache_data(ttl=300, show_spinner=False)
def season_grades(db_version, competition, year):
    with closing(open_readonly()) as conn:
        return build_quality_report(conn, competition, year)


stamp = DB_PATH.stat().st_mtime_ns
competitions, seasons = options(stamp)
if not competitions:
    st.warning("No locally recorded finished fixtures exist.")
    st.stop()

col1, col2, col3 = st.columns([2, 1.6, 2])
with col1:
    competition = st.selectbox("Competition", competitions)
with col2:
    years = seasons.get(competition, [])
    if not years:
        st.warning("No historical seasons are available for this competition.")
        st.stop()
    year = st.selectbox("July–June season", years, format_func=season_label)
with col3:
    teams = team_options(stamp, competition, year)
    choice = st.selectbox(
        "Match selection", ["All recorded teams"] + teams,
    )
    team = None if choice == "All recorded teams" else choice

result = inspect(stamp, competition, year, team)

st.subheader("Linkage and standard xG coverage")
a, b, c, d = st.columns(4)
a.metric("Valid stored finished games", result["valid_finished_rows"])
b.metric("Operator-reviewed links", result["reviewed_total"])
c.metric("Reviewed games with complete xG", result["complete_xg"])
d.metric("Excluded invalid stored results",
         len(result["excluded_match_ids"]))

left, right = st.columns(2)
with left:
    value = result["reviewed_pct_of_stored_valid"]
    st.metric(
        "Reviewed links / stored results",
        f"{value:.1f}%" if value is not None else "N/A",
    )
with right:
    value = result["complete_xg_pct_of_stored_valid"]
    st.metric(
        "Reviewed xG / stored results",
        f"{value:.1f}%" if value is not None else "N/A",
    )

st.caption(
    "Denominator: valid completed results physically present in the "
    "selected local SQLite database. This is NOT a percentage of all "
    "matches that should exist in the official league season."
)

status_table = pd.DataFrame([
    {"Status": key, "Stored matches": count}
    for key, count in result["status_counts"].items()
])
st.dataframe(status_table, hide_index=True, use_container_width=True)
st.bar_chart(status_table.set_index("Status"))

st.subheader("Recorded historical matches: source-level audit")
if result["rows"]:
    frame = pd.DataFrame(result["rows"])
    allowed = list(result["status_counts"])
    selected_statuses = st.multiselect(
        "Filter by linkage / data status",
        allowed, default=allowed,
    )
    filtered = frame[
        frame["coverage_status"].isin(selected_statuses)
    ].copy()
    st.dataframe(filtered, use_container_width=True, hide_index=True)
    st.download_button(
        "Download full historical coverage CSV",
        data=frame.to_csv(index=False).encode("utf-8"),
        file_name=f"historical_match_coverage_{year}.csv",
        mime="text/csv",
    )
else:
    st.warning("No valid stored finished fixtures in this selection.")

st.download_button(
    "Download historical coverage research report (.md)",
    data=coverage_markdown(result).encode("utf-8"),
    file_name=f"historical_match_coverage_{year}.md",
    mime="text/markdown",
)
with st.expander("Coverage limitations", expanded=True):
    for warning in result["warnings"]:
        st.markdown(f"- {warning}")

st.caption(
    "To review potential matches, open Historical Fixture Link Review. "
    "Only unambiguous completed candidates can be operator-confirmed. "
    "This page does not modify source records or create links."
)


st.divider()
st.subheader("Season-wide source-quality coverage")
st.caption(
    "Evidence levels use ALL locally recorded teams in the selected "
    "competition and season, regardless of the optional team filter "
    "above. These are local records, not the official league schedule."
)
quality = season_grades(stamp, competition, year)
q1, q2, q3, q4 = st.columns(4)
q1.metric("A: Reviewed, complete two-sided xG", quality["grades"]["A"])
q2.metric("B: Reviewed, incomplete xG", quality["grades"]["B"])
q3.metric("C: Unreviewed candidates", quality["grades"]["C"])
q4.metric("D: Conflicts or stale/ambiguous", quality["grades"]["D"])
st.caption(
    f"U: No imported source candidate for {quality['grades']['U']} "
    "locally recorded completed results. No missing data is "
    "interpreted as zero."
)

if quality["by_month"]:
    month_frame = pd.DataFrame(quality["by_month"])
    st.markdown("**Monthly local source-quality coverage**")
    st.dataframe(month_frame, hide_index=True, use_container_width=True)
    st.bar_chart(
        month_frame.set_index("month")[["A", "B", "C", "D", "U"]]
    )
    st.download_button(
        "Download monthly source-quality CSV",
        data=month_frame.to_csv(index=False).encode("utf-8"),
        file_name=f"historical_source_quality_month_{year}.csv",
        mime="text/csv",
    )
with st.expander("Recorded team-by-team data-quality coverage"):
    if quality["by_team"]:
        team_frame = pd.DataFrame(quality["by_team"])
        st.dataframe(
            team_frame, hide_index=True, use_container_width=True,
        )
        st.download_button(
            "Download team source-quality CSV",
            data=team_frame.to_csv(index=False).encode("utf-8"),
            file_name=f"historical_source_quality_team_{year}.csv",
            mime="text/csv",
        )
    else:
        st.info("No valid locally recorded completed matches in this season.")

st.download_button(
    "Download source-quality season report (.md)",
    data=quality_markdown(quality).encode("utf-8"),
    file_name=f"historical_source_quality_{year}.md",
    mime="text/markdown",
)
with st.expander("Meaning and limitations of the source-quality grades"):
    for notice in quality["warnings"]:
        st.markdown("- " + notice)

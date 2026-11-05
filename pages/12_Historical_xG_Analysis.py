"""Historical xG coverage and actual-goals comparison, read-only."""
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd
import streamlit as st

from historical_reports import list_competitions, list_seasons, list_teams, season_label
from historical_xg_analysis import analyze_team_xg, imported_xg_coverage
from historical_advanced_research import (
    season_sample_balance, opponent_context,
    historical_xg_diagnostics, advanced_markdown,
)

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


@st.cache_data(ttl=300, show_spinner=False)
def advanced_context(db_version, competition, year, team):
    with closing(db()) as conn:
        sample = season_sample_balance(conn, competition, year)
        opponents = opponent_context(conn, competition, year, team)
    return sample, opponents


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


st.divider()
st.subheader("3. Deeper retrospective research")
st.caption(
    "Historical league coverage, opponents' other same-venue results, "
    "and trends from reviewed match-level xG only. These calculations "
    "do not generate estimates for upcoming fixtures."
)
sample_balance, opponent_research = advanced_context(
    version, competition, year, team
)
xg_diagnostics = historical_xg_diagnostics(analysis)
q1, q2, q3, q4 = st.columns(4)
q1.metric("Recorded league fixtures", sample_balance["valid_matches"])
q2.metric("Recorded teams", sample_balance["team_count"])
q3.metric(
    "Team games with opponent context",
    f"{opponent_research['matched_context_count']}/"
    f"{opponent_research['recorded_team_matches']}"
)
q4.metric("Reviewed games in xG diagnostics",
          xg_diagnostics["included_matches"])
st.caption(
    "These totals describe matches actually recorded in the local "
    "database. They do not establish completeness of an official season."
)

with st.expander("Season sample balance across recorded teams"):
    if sample_balance["teams"]:
        balance_table = pd.DataFrame([
            {key: item[key] for key in
             ("team", "played", "home", "away", "home_away_gap")}
            for item in sample_balance["teams"]
        ])
        st.dataframe(balance_table, hide_index=True, use_container_width=True)
    else:
        st.caption("No valid locally recorded completed games.")
    for notice in sample_balance["warnings"]:
        st.markdown(f"- {notice}")

with st.expander("Opponent-context analysis of completed team matches"):
    st.caption(
        "For each recorded match, compare the opponent's other games "
        "at the same venue within the season, excluding all games "
        "against the selected team. Later games may be included because "
        "this is historical description, not a chronological forecast."
    )
    gap = opponent_research[
        "mean_scored_above_opponent_other_conceded_avg"
    ]
    if gap is None:
        st.warning(
            "Too few recorded other-match observations for reliable "
            "opponent-context comparisons. No missing baseline was "
            "replaced with zero."
        )
    else:
        st.metric(
            "Goals versus opponents' other-game conceding average",
            f"{gap:+.3f} per recorded match"
        )
    if opponent_research["rows"]:
        opponent_table = pd.DataFrame(opponent_research["rows"])
        st.dataframe(opponent_table, hide_index=True, use_container_width=True)
        st.download_button(
            "Download opponent-context source audit (.csv)",
            opponent_table.to_csv(index=False).encode("utf-8"),
            file_name=f"historical_opponent_context_{year}.csv",
            mime="text/csv",
        )
    for notice in opponent_research["warnings"]:
        st.markdown(f"- {notice}")

st.markdown("**Reviewed xG by venue**")
venue_rows = [
    {"Venue": venue, **summary}
    for venue, summary in xg_diagnostics["venue_scopes"].items()
]
st.dataframe(
    pd.DataFrame(venue_rows), hide_index=True, use_container_width=True,
)
if xg_diagnostics["cumulative_timeline"]:
    st.markdown("**Cumulative goals versus xG in reviewed historical matches**")
    timeline = pd.DataFrame(xg_diagnostics["cumulative_timeline"])
    st.line_chart(
        timeline.set_index("date")[["cumulative_goals", "cumulative_xg"]]
    )
    if xg_diagnostics["largest_historical_deviations"]:
        with st.expander("Largest recorded goals-minus-xG deviations"):
            st.dataframe(
                pd.DataFrame(xg_diagnostics["largest_historical_deviations"]),
                hide_index=True, use_container_width=True,
            )
else:
    st.info(
        "No eligible reviewed match-level xG for trend analysis. "
        "The underlying recorded goal results may still support "
        "opponent-context research."
    )
correlation = xg_diagnostics["historical_xg_goals_correlation"]
if correlation is None:
    st.caption(
        "Historical xG-goals correlation is unavailable: at least "
        "10 distinct reviewed matches with varying observations "
        "are required."
    )
else:
    st.caption(
        f"Within this reviewed historical subset: Pearson correlation "
        f"between match xG and recorded goals = {correlation:.3f}. "
        "This descriptive relationship is not a validated forecast."
    )
with st.expander("xG sample and interpretation cautions"):
    for notice in xg_diagnostics["warnings"]:
        st.markdown(f"- {notice}")

st.download_button(
    "Download advanced historical research section (.md)",
    advanced_markdown(
        sample_balance, opponent_research, xg_diagnostics
    ).encode("utf-8"),
    file_name=f"historical_advanced_research_{year}.md",
    mime="text/markdown",
)

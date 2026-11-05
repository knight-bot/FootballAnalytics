"""Historical completeness and research audit for local football data.

This page is read-only. The two providers use different fixture IDs and are
shown separately until an explicit matching and verification step exists.
"""
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from historical_audit import audit_database

st.set_page_config(
    page_title="Historical Data Audit | Football Analytics",
    page_icon="📋",
    layout="wide",
)

DB_PATH = Path(__file__).resolve().parent.parent / "football.db"
st.title("Historical Data Quality & Coverage")
st.caption(
    "Verify historical data before drawing conclusions. "
    "Coverage here means records saved locally, not every match available "
    "from a data provider."
)

if not DB_PATH.exists():
    st.error("football.db is not available to the deployed application.")
    st.stop()


@st.cache_data(ttl=300, show_spinner=False)
def load_audit(file_version):
    with sqlite3.connect(DB_PATH) as connection:
        return audit_database(connection)


audit = load_audit(DB_PATH.stat().st_mtime_ns)
fixtures = pd.DataFrame(audit["sportmonks_fixtures"])
competitions = pd.DataFrame(audit["competitions"])

c1, c2, c3, c4 = st.columns(4)
c1.metric("Completed result records", audit["results_count"])
c2.metric("Historical Sportmonks fixtures", len(fixtures))
c3.metric(
    "Fixtures with both sides' standard xG",
    int(
        sum(
            row["standard_xg_home"] is not None
            and row["standard_xg_away"] is not None
            for row in audit["sportmonks_fixtures"]
        )
    ),
)
c4.metric(
    "Fixtures with audit flags",
    int(
        sum(row["issue_count"] > 0 for row in audit["sportmonks_fixtures"])
    ),
)

for check in audit["checks"]:
    st.warning(check)

st.divider()
st.subheader("1. Completed Results by Competition")
if competitions.empty:
    st.info("No completed result records are stored.")
else:
    st.dataframe(
        competitions.rename(columns={
            "competition": "Competition",
            "completed_matches": "Saved completed matches",
            "latest_match": "Latest completed match",
        }),
        hide_index=True,
        use_container_width=True,
    )
    st.caption(
        "Match counts are not league standings or season-completeness "
        "guarantees. Some competitions have different season formats."
    )

st.divider()
st.subheader("2. Sportmonks Fixture Data Checks")
if fixtures.empty:
    st.info(
        "No historical Sportmonks fixtures are stored. "
        "Run the manual Sportmonks import using a completed fixture ID."
    )
else:
    league_options = sorted(
        fixtures["league_id"].dropna().astype(int).unique().tolist()
    )
    if len(league_options) > 1:
        league = st.selectbox(
            "Filter by Sportmonks league ID",
            ["All"] + league_options,
        )
        if league != "All":
            fixtures = fixtures.loc[fixtures["league_id"] == league].copy()

    st.dataframe(
        fixtures.rename(columns={
            "fixture_id": "Fixture ID",
            "match": "Match",
            "match_date": "Kickoff",
            "league_id": "League ID",
            "season_id": "Season ID",
            "imported_at": "Imported at (UTC)",
            "participants_saved": "Teams saved",
            "statistics_returned": "Statistics from API",
            "statistics_saved": "Numeric statistics stored",
            "pressure_returned": "Pressure from API",
            "pressure_saved": "Minute-level pressure stored",
            "metrics_saved": "Expected metrics stored",
            "standard_xg_home": "Home xG",
            "standard_xg_away": "Away xG",
            "issues": "Audit findings",
            "issue_count": "Number of findings",
        }),
        hide_index=True,
        use_container_width=True,
    )

    if (fixtures["issue_count"] > 0).any():
        st.warning(
            "Some imported fixtures have missing or unparsed fields. "
            "Check their audit findings before interpreting those statistics."
        )
    else:
        st.success(
            "No issues detected by these checks for the selected sample. "
            "This does not prove the source records are complete or correct."
        )

    st.download_button(
        "Export this historical audit (CSV)",
        data=fixtures.to_csv(index=False).encode("utf-8"),
        file_name="football_historical_data_audit.csv",
        mime="text/csv",
        use_container_width=False,
    )

    st.subheader("3. Historical xG Comparison")
    st.caption(
        "Compare xG recorded in the selected completed fixtures. "
        "Missing values are left blank, never treated as zero."
    )
    chart_data = fixtures[
        ["fixture_id", "match", "standard_xg_home", "standard_xg_away"]
    ].dropna(subset=["standard_xg_home", "standard_xg_away"])
    if chart_data.empty:
        st.info(
            "No fixtures in this sample have standard xG for both sides."
        )
    else:
        chart_data = chart_data.copy()
        chart_data["Fixture"] = (
            chart_data["match"]
            + " (ID "
            + chart_data["fixture_id"].astype(str)
            + ")"
        )
        st.bar_chart(
            chart_data.set_index("Fixture")[
                ["standard_xg_home", "standard_xg_away"]
            ].rename(columns={
                "standard_xg_home": "Home xG",
                "standard_xg_away": "Away xG",
            })
        )

    if len(fixtures) < 5:
        st.info(
            "This sample is too small for meaningful season-wide or "
            "team-wide averages. Collect more completed historical matches "
            "before attempting broader comparisons."
        )

st.divider()
st.subheader("How to interpret this audit")
st.markdown(
    "The football-data.org results and Sportmonks advanced statistics "
    "are separate datasets. Their fixture identifiers are not "
    "interchangeable, and this page deliberately does not join them. "
    "A successful import confirms data was stored, not that every "
    "available metric was returned. Missing data should be investigated "
    "before using it in any research model."
)
st.caption(
    "The report runs entirely against local SQLite data and makes no "
    "external API calls. Respect the licensing terms of each data source "
    "before sharing or redistributing its records."
)

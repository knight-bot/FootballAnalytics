"""Read-only planner for filling historical Sportmonks import gaps.

Uses locally stored completed match dates only. This page does not
access APIs, trigger GitHub Actions, or update the database.
"""
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from historical_import_planner import (
    COMPETITION_TO_LEAGUE, MAX_PLAN_WINDOWS,
    plan_historical_imports, import_plan_markdown,
)
from historical_reports import list_seasons, season_label

st.set_page_config(
    page_title="Historical Import Gap Planner | FootballAnalytics",
    page_icon="🗓️", layout="wide",
)
st.title("Historical Import Gap Planner")
st.caption(
    "Prioritize bounded historical Sportmonks import windows using "
    "locally recorded completed Premier League results with no "
    "imported matching candidates."
)
st.info(
    "Planning does not fetch fixtures or approve links. Importing "
    "requires the existing manual GitHub Action, and cross-provider "
    "matches still require separate human source-score review."
)

DB_PATH = Path(__file__).resolve().parent.parent / "football.db"
if not DB_PATH.exists():
    st.error("football.db was not found in this deployment.")
    st.stop()


def open_database():
    return sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode=ro", uri=True,
    )


@st.cache_data(ttl=300, show_spinner=False)
def seasons_for(db_version, competition):
    with closing(open_database()) as conn:
        return list_seasons(conn, competition)


@st.cache_data(ttl=300, show_spinner=False)
def make_plan(db_version, competition, year, limit, today):
    with closing(open_database()) as conn:
        return plan_historical_imports(
            conn, competition, year, max_windows=limit, as_of_date=today,
        )


stamp = DB_PATH.stat().st_mtime_ns
competition = st.selectbox(
    "Historical competition", list(COMPETITION_TO_LEAGUE),
)
years = seasons_for(stamp, competition)
if not years:
    st.warning("No recorded completed historical results for this competition.")
    st.stop()

a, b = st.columns([1.5, 1])
with a:
    year = st.selectbox(
        "Historical July–June season",
        years, format_func=season_label,
    )
with b:
    max_windows = st.selectbox(
        "Maximum suggested windows", [3, 6, 9, MAX_PLAN_WINDOWS],
        index=1,
    )
today = datetime.now(timezone.utc).date()
plan = make_plan(stamp, competition, year, max_windows, today)

st.subheader("What currently needs attention?")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Old results missing candidates", plan["unmatched_eligible"])
c2.metric("Candidates requiring review", plan["review_candidates"])
c3.metric("Ambiguous or stale", plan["manual_resolution_count"])
c4.metric("Reviewed but missing xG", plan["reviewed_missing_xg_count"])
st.caption(
    f"Latest eligible completed-match date: "
    f"{plan['last_eligible_date']}. "
    "This is a date eligibility check, not an assertion that Sportmonks "
    "has statistics for those fixtures."
)

st.subheader("Suggested historical import windows")
if plan["windows"]:
    for w in plan["windows"]:
        st.markdown(
            f"**Priority {w['priority']}:** "
            f"{w['start_date']} to {w['end_date']} "
            f"({w['local_missing_results']} missing local result(s))"
        )
    frame = pd.DataFrame([
        {
            "Priority": w["priority"],
            "Start": w["start_date"],
            "End": w["end_date"],
            "Missing local results": w["local_missing_results"],
            "football-data.org source IDs": ", ".join(
                str(mid) for mid in w["source_match_ids"]
            ),
        }
        for w in plan["windows"]
    ])
    st.dataframe(frame, use_container_width=True, hide_index=True)
    st.download_button(
        "Download import windows (.csv)",
        frame.to_csv(index=False).encode("utf-8"),
        file_name=f"historical_import_windows_{year}.csv",
        mime="text/csv",
    )
else:
    st.info(
        "No completed, old-enough stored results currently require "
        "Sportmonks fixture discovery in this selection."
    )
if plan["omitted_windows"]:
    st.warning(
        f"{plan['omitted_windows']} additional eligible windows are "
        "not shown due to the per-plan window limit."
    )
if plan["unmatched_too_recent"]:
    st.caption(
        f"{plan['unmatched_too_recent']} uncovered locally stored "
        "match(es) are not old enough for the historical importer."
    )

st.markdown(
    "**Manual import action:** "
    "[Discover and Import Historical Sportmonks Fixtures]"
    "(https://github.com/knight-bot/FootballAnalytics/actions/"
    "workflows/sportmonks-historical-batch.yml)"
)
st.caption(
    "Copy one start/end pair from the table into the GitHub Action. "
    "Leave refresh_existing OFF. Import at most 10 completed historical "
    "fixtures in one run; repeated runs automatically skip stored IDs."
)

st.divider()
st.subheader("Tasks that do not require another discovery import")
with st.expander("Candidates needing original-source score review"):
    if plan["review_queue"]:
        st.dataframe(
            pd.DataFrame(plan["review_queue"]),
            hide_index=True, use_container_width=True,
        )
    else:
        st.caption("No review candidates in this stored selection.")
with st.expander("Ambiguous / stale records requiring manual resolution"):
    if plan["manual_resolution_queue"]:
        st.dataframe(
            pd.DataFrame(plan["manual_resolution_queue"]),
            hide_index=True, use_container_width=True,
        )
    else:
        st.caption("No ambiguous or stale local links.")
with st.expander("Reviewed matches missing standard xG"):
    if plan["missing_xg_queue"]:
        st.dataframe(
            pd.DataFrame(plan["missing_xg_queue"]),
            hide_index=True, use_container_width=True,
        )
        st.caption(
            "A missing standard xG value might be due to provider "
            "coverage or incomplete imports. Do not assume re-importing "
            "will supply it."
        )
    else:
        st.caption("No currently reviewed links with incomplete xG.")

with st.expander("Coverage limitations", expanded=True):
    for item in plan["warnings"]:
        st.markdown(f"- {item}")

st.download_button(
    "Download full historical import plan (.md)",
    data=import_plan_markdown(plan).encode("utf-8"),
    file_name=f"historical_import_gap_plan_{year}.md",
    mime="text/markdown",
)
st.caption(
    "Local read-only evidence. Importing, provider-score verification "
    "and updating football.db are separate manual workflows."
)

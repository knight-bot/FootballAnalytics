"""Compare retrospective goal-model errors across held-out historical seasons."""
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from historical_multiseason_benchmark import (
    evaluate_historical_seasons, multiseason_markdown,
    MAX_EVALUATION_SEASONS,
)
from historical_reports import list_competitions, list_seasons, season_label

st.set_page_config(
    page_title="Multi-Season Historical Evaluation | FootballAnalytics",
    page_icon="📚", layout="wide",
)
st.title("Multi-Season Historical Model Evaluation")
st.caption(
    "Evaluate recorded historical goal errors across successive "
    "completed July–June season windows. No upcoming fixture analysis."
)
st.info(
    "This is a rolling-origin retrospective evaluation: for each historical "
    "test season, the models train only on earlier seasons. Test seasons "
    "with insufficient data are excluded and explained."
)

DB_PATH = Path(__file__).resolve().parent.parent / "football.db"
if not DB_PATH.exists():
    st.error("football.db is missing.")
    st.stop()


def readonly_conn():
    return sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode=ro", uri=True,
    )


@st.cache_data(ttl=300, show_spinner=False)
def options(db_version):
    with closing(readonly_conn()) as conn:
        competitions = list_competitions(conn)
        seasons = {name: list_seasons(conn, name) for name in competitions}
    return competitions, seasons


@st.cache_data(ttl=300, show_spinner=False)
def evaluate(db_version, competition, first_year, last_year, lookback,
             smoothing, as_of):
    with closing(readonly_conn()) as conn:
        return evaluate_historical_seasons(
            conn, competition, first_year, last_year,
            lookback_seasons=lookback,
            shrinkage=smoothing,
            as_of_date=as_of,
        )


version = DB_PATH.stat().st_mtime_ns
competitions, all_seasons = options(version)
if not competitions:
    st.warning("No completed match records are available.")
    st.stop()
competition = st.selectbox("Competition", competitions)
today = datetime.now(timezone.utc).date()
completed_seasons = sorted(
    year for year in all_seasons[competition]
    if date(year + 1, 7, 1) <= today
)
if not completed_seasons:
    st.warning(
        "No recorded July–June season has reached its calendar end. "
        "The historical multi-season benchmark requires finished "
        "calendar windows."
    )
    st.stop()

c1, c2, c3, c4 = st.columns([1.5, 1.5, 1.2, 1.2])
with c1:
    first_year = st.selectbox(
        "First held-out season", completed_seasons,
        index=max(0, len(completed_seasons) - 2),
        format_func=season_label,
    )
with c2:
    last_year = st.selectbox(
        "Last held-out season", completed_seasons,
        index=len(completed_seasons) - 1,
        format_func=season_label,
    )
with c3:
    lookback = st.selectbox(
        "Earlier training seasons", [1, 2, 3, 4, 5], index=1,
        help=(
            "Each held-out season is evaluated using only data "
            "from the selected number of preceding seasons."
        ),
    )
with c4:
    smoothing = st.selectbox(
        "Fixed team smoothing", [3, 5, 10, 15], index=1,
        help=(
            "Do not choose this using the reported test errors "
            "if you want an unbiased final evaluation."
        ),
    )
if first_year > last_year:
    st.warning("The first held-out season must precede the last one.")
    st.stop()
if last_year - first_year + 1 > MAX_EVALUATION_SEASONS:
    st.warning(
        f"Select at most {MAX_EVALUATION_SEASONS} consecutive "
        "historical held-out seasons."
    )
    st.stop()

try:
    summary = evaluate(
        version, competition, first_year, last_year,
        lookback, smoothing, today,
    )
except (ValueError, sqlite3.Error) as exc:
    st.error(f"Unable to evaluate historical seasons: {exc}")
    st.stop()

st.subheader("Historical evaluation coverage")
a, b, c, d = st.columns(4)
a.metric("Included held-out seasons", summary["seasons_included"])
b.metric("Skipped seasons", summary["seasons_skipped"])
c.metric("Completed test fixtures used", summary["heldout_matches"])
d.metric(
    "Goal observations scored", summary["heldout_matches"] * 2
)

season_rows = []
for row in summary["by_season"]:
    season_rows.append({
        "Season": row["season"],
        "Status": row["status"],
        "Earlier training games": row["train_matches"],
        "Held-out games": row["test_matches"],
        "League baseline MAE": row["baseline_mae"],
        "Team model MAE": row["adjusted_mae"],
        "Team minus baseline MAE": row["mae_delta"],
        "Reason": row["reason"],
    })
table = pd.DataFrame(season_rows)
st.dataframe(table, hide_index=True, use_container_width=True)

included = table[table["Status"] == "included"].copy()
if not included.empty:
    st.subheader("Season-by-season historical goal errors")
    chart_rows = included.set_index("Season")[
        ["League baseline MAE", "Team model MAE"]
    ]
    st.bar_chart(chart_rows)
    st.caption(
        "Each value is the average absolute error in goals per "
        "team-match for *completed* matches in that historical season."
    )

st.subheader("Pooled historical evaluation")
if not summary["pooled_baseline"]:
    st.warning(
        "No seasons passed the fixed coverage requirements "
        "(at least 50 training and 30 held-out completed games). "
        "No pooled score is shown. Choose seasons with more data."
    )
else:
    baseline, adjusted = (
        summary["pooled_baseline"], summary["pooled_adjusted"]
    )
    score_table = pd.DataFrame([
        {
            "Historical method": "Earlier-season league averages",
            "Goal MAE": baseline["mae"],
            "Goal RMSE": baseline["rmse"],
            "Mean goal residual": baseline["mean_error"],
        },
        {
            "Historical method": "Earlier-season team adjustments",
            "Goal MAE": adjusted["mae"],
            "Goal RMSE": adjusted["rmse"],
            "Mean goal residual": adjusted["mean_error"],
        },
    ])
    st.dataframe(score_table, use_container_width=True, hide_index=True)
    delta = summary["pooled_mae_delta"]
    if delta < -1e-10:
        st.success(
            f"On the included historical seasons, team adjustments "
            f"reduced average absolute goal error by {abs(delta):.4f} "
            "compared with the baseline. This is not proof of future accuracy."
        )
    elif delta > 1e-10:
        st.warning(
            f"On the included historical seasons, team adjustments "
            f"increased average absolute goal error by {delta:.4f} "
            "compared with the simpler baseline."
        )
    else:
        st.info("Both historical methods had the same pooled goal MAE.")
    st.caption(
        "Pooled values are weighted by completed match observations, "
        "not a simple average of each season's error."
    )

st.markdown("**Retrospective error robustness**")
paired = summary["paired_mae_delta_bootstrap95"]
if paired is None:
    st.caption(
        "Paired MAE bootstrap uncertainty is withheld until 50 "
        "eligible held-out completed games have been recorded."
    )
else:
    st.caption(
        f"Approximate 95% match-paired resampling interval for "
        f"team-adjusted minus baseline MAE: "
        f"{paired[0]:+.4f} to {paired[1]:+.4f}. "
        "Repeated clubs and seasons weaken the independence assumption. "
        "This is historical uncertainty, not future accuracy."
    )
sensitivity = summary["leave_one_season_out_delta_range"]
if sensitivity is None:
    st.caption(
        "Leave-one-season-out sensitivity requires three eligible "
        "historical held-out seasons."
    )
else:
    st.caption(
        f"Historical MAE delta after omitting each held-out season "
        f"in turn ranged from {sensitivity[0]:+.4f} to "
        f"{sensitivity[1]:+.4f} goals per team-match."
    )

if summary["seasons_included"] < 2:
    st.warning(
        "Fewer than two seasons passed. This cannot establish "
        "multi-season consistency."
    )
with st.expander("Methodology and limitations", expanded=True):
    for warning in summary["warnings"]:
        st.markdown(f"- {warning}")

st.divider()
st.subheader("Download research evidence")
st.download_button(
    "Download multi-season evaluation report (.md)",
    multiseason_markdown(summary).encode("utf-8"),
    file_name=f"historical_multiseason_evaluation_{first_year}_{last_year}.md",
    mime="text/markdown",
)
st.download_button(
    "Download per-season audit table (.csv)",
    table.to_csv(index=False).encode("utf-8"),
    file_name=f"historical_multiseason_audit_{first_year}_{last_year}.csv",
    mime="text/csv",
)
st.caption(
    "Source: locally stored completed football-data.org match records. "
    "No API calls, no unverified Sportmonks joins, and no future match output."
)

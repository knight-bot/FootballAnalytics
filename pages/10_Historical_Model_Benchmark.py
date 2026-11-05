"""Read-only retrospective evaluation of completed historical goal models."""
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd
import streamlit as st

from historical_model_benchmark import (
    benchmark_markdown, run_historical_benchmark,
)
from historical_reports import (
    list_competitions, list_seasons, season_label,
)

st.set_page_config(
    page_title="Historical Model Benchmark | FootballAnalytics",
    page_icon="🧪", layout="wide",
)
st.title("Historical Goal-Model Benchmark")
st.caption(
    "Evaluate simple goal-rate methods on completed historical seasons "
    "that were not used for training. This does not analyze upcoming fixtures."
)
st.info(
    "A model is only useful if it improves on a basic baseline when tested "
    "on results it has not seen. Both models below are trained exclusively "
    "on earlier seasons and evaluated on completed matches."
)

DB_PATH = Path(__file__).resolve().parent.parent / "football.db"
if not DB_PATH.exists():
    st.error("football.db is unavailable in this deployment.")
    st.stop()


def open_readonly():
    return sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode=ro", uri=True
    )


@st.cache_data(ttl=300, show_spinner=False)
def get_options(db_version):
    with closing(open_readonly()) as conn:
        competitions = list_competitions(conn)
        seasons = {
            competition: list_seasons(conn, competition)
            for competition in competitions
        }
        return competitions, seasons


@st.cache_data(ttl=300, show_spinner=False)
def evaluate(db_version, competition, test_season, lookback, shrinkage):
    with closing(open_readonly()) as conn:
        return run_historical_benchmark(
            conn, competition, test_season, lookback, shrinkage
        )


version = DB_PATH.stat().st_mtime_ns
competitions, seasons = get_options(version)
if not competitions:
    st.warning("No completed match results are available.")
    st.stop()
col1, col2, col3, col4 = st.columns([2, 1.5, 1.2, 1.2])
with col1:
    competition = st.selectbox("Competition", competitions)
with col2:
    years = seasons[competition]
    if not years:
        st.warning("No recorded historical season for this competition.")
        st.stop()
    heldout_year = st.selectbox(
        "Held-out season", years, format_func=season_label
    )
with col3:
    lookback = st.selectbox(
        "Training lookback (seasons)", [1, 2, 3, 4, 5], index=1,
    )
with col4:
    shrinkage = st.selectbox(
        "Team regularization", [3, 5, 10, 15], index=1,
    )

try:
    result = evaluate(
        version, competition, heldout_year, lookback, shrinkage
    )
except (ValueError, sqlite3.Error) as exc:
    st.warning(str(exc))
    st.caption(
        "A valid holdout needs at least one completed earlier-season "
        "training match and one completed later-season test match."
    )
    st.stop()

st.subheader("Chronological sample split")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Earlier training fixtures", result["train_matches"])
c2.metric("Held-out completed fixtures", result["test_matches"])
c3.metric("Teams in training", result["trained_team_count"])
c4.metric("Holdout matches with unseen team",
          result["unseen_team_matches"])
st.caption(
    f"Training: {result['train_window'][0]} to before "
    f"{result['train_window'][1]} | "
    f"Test: {result['test_window'][0]} to before "
    f"{result['test_window'][1]}"
)

st.subheader("Historical error comparison")
a, b = result["league_baseline"], result["team_adjusted"]
metric_data = pd.DataFrame([
    {
        "Historical method": "Training-period league home/away means",
        "Goal MAE": round(a["mae"], 4),
        "Goal RMSE": round(a["rmse"], 4),
        "Mean residual": round(a["mean_error"], 4),
    },
    {
        "Historical method": "Training-only regularized team adjustment",
        "Goal MAE": round(b["mae"], 4),
        "Goal RMSE": round(b["rmse"], 4),
        "Mean residual": round(b["mean_error"], 4),
    },
])
st.dataframe(metric_data, hide_index=True, use_container_width=True)
diff = result["mae_change_adjusted_minus_baseline"]
if abs(diff) < 1e-10:
    st.info(
        "Both historical methods have the same mean absolute goal error "
        "on this held-out sample."
    )
elif diff < 0:
    st.success(
        f"The team-adjusted method achieved {abs(diff):.3f} fewer "
        "goals of MAE than the league baseline on this particular "
        "held-out historical sample. This is not proof that it "
        "generalizes to other seasons."
    )
else:
    st.warning(
        f"The team-adjusted method achieved {diff:.3f} more "
        "goals of MAE than the simpler baseline on this held-out "
        "historical sample."
    )

st.caption(
    "MAE: average absolute goal error per team per completed game. "
    "RMSE: root-mean-square goal error, which penalizes large errors. "
    "Mean residual: estimates minus actual goals; values above zero "
    "indicate overestimation."
)
with st.expander("Methodology, limitations and missing-data warnings",
                 expanded=True):
    for warning in result["warnings"]:
        st.markdown(f"- {warning}")

st.divider()
st.subheader("Audit completed historical test matches")
st.caption(
    "These rows are already-completed historical matches. "
    "Per-match errors are provided for auditability, "
    "not for generating live match recommendations."
)
audit_rows = [
    {
        "Source match ID": row["match_id"],
        "Date": row["date"],
        "Recorded fixture": f"{row['home']} vs {row['away']}",
        "Recorded result": (
            f"{row['home_goals']}-{row['away_goals']}"
        ),
        "League baseline goal MAE": round(
            row["league_absolute_error"], 4
        ),
        "Team-adjusted goal MAE": round(
            row["adjusted_absolute_error"], 4
        ),
        "Unseen team": row["unseen_team"],
    }
    for row in result["rows"]
]
audit_df = pd.DataFrame(audit_rows)
st.dataframe(audit_df, hide_index=True, use_container_width=True)
st.download_button(
    "Download held-out historical audit CSV",
    audit_df.to_csv(index=False).encode("utf-8"),
    file_name=f"retrospective_model_audit_{heldout_year}.csv",
    mime="text/csv",
)

report = benchmark_markdown(result)
st.download_button(
    "Download model evaluation report (.md)",
    report.encode("utf-8"),
    file_name=f"historical_model_benchmark_{heldout_year}.md",
    mime="text/markdown",
)
with st.expander("Preview historical model evaluation report"):
    st.text_area("Report", report, height=320)

st.caption(
    "Source: football-data.org locally saved FINISHED results; "
    "no Sportmonks data are joined in this preliminary benchmark."
)

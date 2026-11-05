"""Read-only analysis of separately imported historical Sportmonks data."""
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Sportmonks Historical Stats | Football Analytics",
    page_icon="⚽",
    layout="wide",
)

DB_PATH = Path(__file__).resolve().parent.parent / "football.db"
st.title("Sportmonks Historical Match Statistics")
st.caption(
    "Only manually imported completed fixtures. These are observed "
    "historical metrics, not forecasts or current-team ratings."
)

if not DB_PATH.exists():
    st.warning("football.db is missing from the deployed application.")
    st.stop()


@st.cache_data(ttl=300)
def read_history(db_version):
    with sqlite3.connect(DB_PATH) as conn:
        exists = conn.execute("""
            SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='sportmonks_historical_fixtures'
        """).fetchone()
        if not exists:
            return (
                pd.DataFrame(), pd.DataFrame(),
                pd.DataFrame(), pd.DataFrame(),
            )
        fixtures = pd.read_sql_query("""
            SELECT * FROM sportmonks_historical_fixtures
            ORDER BY match_date DESC, fixture_id DESC
        """, conn)
        metrics = pd.read_sql_query("""
            SELECT x.fixture_id, x.type_id, x.location,
                   x.participant_id, x.value, t.name AS participant_name
            FROM sportmonks_historical_metrics AS x
            LEFT JOIN sportmonks_historical_teams AS t
            ON x.fixture_id=t.fixture_id AND
               x.participant_id=t.participant_id
        """, conn)
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "sportmonks_historical_statistics" in tables:
            statistics = pd.read_sql_query("""
                SELECT s.fixture_id, s.type_id, s.location,
                       s.participant_id, s.value,
                       t.name AS participant_name
                FROM sportmonks_historical_statistics AS s
                LEFT JOIN sportmonks_historical_teams AS t
                  ON s.fixture_id=t.fixture_id
                 AND s.participant_id=t.participant_id
            """, conn)
        else:
            statistics = pd.DataFrame()

        if "sportmonks_historical_pressure" in tables:
            pressure = pd.read_sql_query("""
                SELECT p.fixture_id, p.participant_id, p.minute,
                       p.pressure, t.name AS participant_name
                FROM sportmonks_historical_pressure AS p
                LEFT JOIN sportmonks_historical_teams AS t
                  ON p.fixture_id=t.fixture_id
                 AND p.participant_id=t.participant_id
            """, conn)
        else:
            pressure = pd.DataFrame()

        return fixtures, metrics, statistics, pressure


fixtures, all_metrics, all_statistics, all_pressure = read_history(
    DB_PATH.stat().st_mtime_ns
)

if fixtures.empty:
    st.info(
        "No historical Sportmonks fixtures have been imported yet. "
        "Run the manual GitHub Actions workflow "
        "'Import Sportmonks Historical Matches' with a completed fixture ID."
    )
    st.stop()


def label(row):
    return f"{row['name'] or 'Fixture'} | {row['match_date']} | ID {row['fixture_id']}"


options = fixtures["fixture_id"].astype(int).tolist()
fixture_id = st.selectbox(
    "Choose an imported completed fixture",
    options,
    format_func=lambda f: label(
        fixtures.loc[fixtures["fixture_id"] == f].iloc[0]
    ),
)
selected = fixtures.loc[fixtures["fixture_id"] == fixture_id].iloc[0]

st.subheader(str(selected["name"] or f"Fixture {fixture_id}"))
st.caption(
    f"Kickoff: {selected['match_date']} | "
    f"Sportmonks fixture ID: {fixture_id} | "
    f"Last imported: {selected['imported_at']}"
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Statistics records", int(selected["stat_records"]))
c2.metric("Pressure records", int(selected["pressure_records"]))
c3.metric("Score records", int(selected["score_records"]))
c4.metric("Expected-metric records", int(selected["metric_records"]))
st.caption(
    "These numbers count returned API records, not necessarily shots, "
    "successful defensive actions, or other on-field events."
)

metric_names = {
    5304: "Expected Goals (xG)",
    5305: "Expected Goals on Target (xGoT)",
    7939: "Expected Points (xPTS)",
    7940: "Expected Goals from Penalties",
    7941: "Expected Goals from Free Kicks",
    7942: "Expected Goals from Corners",
    7943: "Non-Penalty xG",
    7944: "Expected Goals from Set Plays",
    7945: "Expected Goals from Open Play",
    9684: "Expected Goals Difference",
    9685: "Shooting Performance",
    9686: "Expected Goals Prevented",
    9687: "Expected Goals Against (xGA)",
}

rows = all_metrics.loc[
    all_metrics["fixture_id"] == fixture_id
].copy()

st.subheader("Expected-goals and related metrics")
if rows.empty:
    st.warning(
        "No numeric xG-related metrics were returned for this fixture. "
        "Missing values are not equivalent to zero."
    )
else:
    rows["Metric"] = rows["type_id"].map(metric_names).fillna(
        "Unlabelled metric"
    )
    rows["Team / side"] = rows["participant_name"].fillna(
        rows["location"].str.title()
    )
    display_cols = ["Metric", "Team / side", "location", "value", "type_id"]
    st.dataframe(
        rows[display_cols].rename(columns={
            "location": "Home/Away", "value": "Recorded value",
            "type_id": "Type ID",
        }).sort_values(["Metric", "Home/Away"]),
        hide_index=True,
        use_container_width=True,
    )

    standard_xg = rows[rows["type_id"] == 5304]
    if not standard_xg.empty:
        st.subheader("Standard xG (Type 5304)")
        chart = standard_xg.set_index("Team / side")[["value"]]
        st.bar_chart(chart)
        st.caption(
            "These values are estimates describing chances in the "
            "completed match. Other metric types must not be added to "
            "this xG total."
        )

st.divider()
st.subheader("Historical Match Statistics")

stat_names = {
    42: "Total Shots",
    86: "Shots on Target",
    45: "Ball Possession",
    34: "Corners",
    78: "Tackles",
}
if all_statistics.empty:
    st.info(
        "No saved numeric fixture-statistic data is available yet. "
        "Re-import this completed fixture with the updated manual "
        "Sportmonks historical workflow to populate this section."
    )
else:
    stats = all_statistics[
        all_statistics["fixture_id"] == fixture_id
    ].copy()
    if stats.empty:
        st.info("No numeric match statistics were returned for this fixture.")
    else:
        stats["Statistic"] = stats["type_id"].map(stat_names).fillna(
            stats["type_id"].map(lambda x: f"Type {x} (unmapped)")
        )
        stats["Team / side"] = stats["participant_name"].fillna(
            stats["location"].str.title()
        )
        st.dataframe(
            stats[["Statistic", "Team / side", "value", "type_id"]]
            .rename(columns={
                "value": "Recorded value",
                "type_id": "Sportmonks Type ID",
            })
            .sort_values(["Statistic", "Team / side"]),
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            "Values come directly from historical fixture statistics. "
            "Unknown type IDs remain visible rather than being guessed. "
            "Different metrics use different units and should not be added."
        )

st.subheader("Pressure Index by Match Minute")

if all_pressure.empty:
    st.info(
        "Minute-level Pressure Index has not yet been saved. "
        "Re-import a completed fixture using the updated workflow."
    )
else:
    pressure = all_pressure[
        all_pressure["fixture_id"] == fixture_id
    ].copy()
    if pressure.empty:
        st.info("No minute-level Pressure Index was available.")
    else:
        pressure["Team / side"] = pressure["participant_name"].fillna(
            pressure["participant_id"].map(lambda x: f"Team {x}")
        )
        trend = pressure.pivot_table(
            index="minute",
            columns="Team / side",
            values="pressure",
            aggfunc="mean",
        ).sort_index()
        st.line_chart(trend)
        st.caption(
            f"{len(pressure):,} recorded pressure points over minutes "
            f"{pressure['minute'].min()}–{pressure['minute'].max()}. "
            "Sportmonks Pressure Index measures attacking momentum "
            "at each minute, not the number of defensive pressing events. "
            "This describes the completed match, not future performance."
        )

st.divider()
st.info(
    "This page uses a small, manually selected historical sample. "
    "It does not automatically match Sportmonks fixture IDs to "
    "football-data.org IDs, nor does it represent live league coverage."
)
st.caption(
    "Source: Sportmonks Football API v3, accessed using the project's "
    "authorized account. Respect the provider's retention and "
    "redistribution terms if making the dashboard public."
)

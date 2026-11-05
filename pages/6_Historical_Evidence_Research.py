"""Historical research editor with transparent, checkable evidence.

Offline evidence review always works. Optional AI only runs on a deliberate
button click when an OpenAI API credential exists on the app's server.
"""
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import streamlit as st

from historical_ai import HistoricalAIError, explain_historical_evidence
from historical_evidence import (
    offline_review, sportmonks_evidence, team_evidence,
)
from historical_reports import (
    list_competitions, list_seasons, list_sportmonks_fixtures,
    list_teams, season_label,
)

st.set_page_config(
    page_title="Historical Evidence Research | Football Analytics",
    page_icon="🔎", layout="wide",
)
st.title("Historical Evidence Research")
st.caption(
    "Review documented past matches. Generated observations are grounded "
    "in source IDs and do not represent upcoming-match predictions."
)

DB = Path(__file__).resolve().parent.parent / "football.db"
if not DB.is_file():
    st.error("football.db was not found in the Streamlit deployment.")
    st.stop()


def read_only_connection():
    return sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)


@st.cache_data(ttl=300)
def available_sources(version):
    with closing(read_only_connection()) as conn:
        comps = list_competitions(conn)
        seasons = {c: list_seasons(conn, c) for c in comps}
        fixtures = list_sportmonks_fixtures(conn)
    return comps, seasons, fixtures


@st.cache_data(ttl=300)
def available_teams(version, competition, year):
    with closing(read_only_connection()) as conn:
        return list_teams(conn, competition, year)


@st.cache_data(ttl=300)
def load_team_pack(version, competition, year, team):
    with closing(read_only_connection()) as conn:
        return team_evidence(conn, competition, year, team)


@st.cache_data(ttl=300)
def load_sportmonks_pack(version, fixture_id):
    with closing(read_only_connection()) as conn:
        return sportmonks_evidence(conn, fixture_id)


version = DB.stat().st_mtime_ns
competitions, seasons, fixtures = available_sources(version)
source = st.radio(
    "Choose a historical evidence source",
    ["Completed team results", "Imported Sportmonks fixture"],
    horizontal=True,
)
pack = None
if source == "Completed team results":
    if not competitions:
        st.warning("No completed football-data.org results are stored.")
    else:
        comp = st.selectbox(
            "Competition", competitions,
            index=(competitions.index("Premier League")
                   if "Premier League" in competitions else 0),
        )
        choices = seasons.get(comp, [])
        if choices:
            year = st.selectbox(
                "July–June historical window",
                choices, format_func=season_label,
            )
            teams = available_teams(version, comp, year)
            if teams:
                team = st.selectbox("Team", teams)
                pack = load_team_pack(version, comp, year, team)
            else:
                st.warning("There are no recorded teams in this selection.")
        else:
            st.warning("No historical seasons are available.")
else:
    if not fixtures:
        st.info(
            "No completed Sportmonks fixtures are in the database. "
            "Import selected historical matches using the existing "
            "manual GitHub Actions workflow."
        )
    else:
        options = [row["id"] for row in fixtures]
        label = {row["id"]:
                 f"{row['name']} | {row['date']} | ID {row['id']}"
                 for row in fixtures}
        fid = st.selectbox(
            "Imported completed fixture", options,
            format_func=lambda x: label[x],
        )
        try:
            pack = load_sportmonks_pack(version, fid)
        except ValueError as exc:
            st.error(str(exc))

if pack is None:
    st.stop()

st.divider()
st.subheader(pack["title"])
st.caption(
    f"Original provider: {pack['source']} | "
    f"Verified evidence groups: {len(pack['evidence'])}"
)
if not pack["evidence"]:
    st.warning(
        "No suitable historical evidence exists for this selection. "
        "No claims will be generated."
    )
    st.stop()

with st.expander("Inspect source evidence and original IDs", expanded=True):
    for item in pack["evidence"]:
        st.markdown(f"**{item['id']} | {item['title']}**")
        st.write(item["fact"])
        if "match_ids" in item:
            st.caption(
                "football-data.org match IDs: "
                + ", ".join(map(str, item["match_ids"]))
            )
        if "fixture_id" in item:
            st.caption(
                f"Sportmonks fixture ID: {item['fixture_id']}"
            )

st.download_button(
    "Export evidence (JSON)",
    data=json.dumps(pack, indent=2, ensure_ascii=False).encode("utf-8"),
    file_name="historical_evidence.json",
    mime="application/json",
)

st.divider()
st.subheader("Offline evidence review")
st.caption("Free, deterministic, and available without an AI API key.")
offline = offline_review(pack)
for item in offline["observations"]:
    st.write(item["text"])
    st.caption("Recorded evidence: " + ", ".join(item["evidence_ids"]))

st.divider()
st.subheader("Optional AI-assisted historical interpretation")
key = os.environ.get("OPENAI_API_KEY", "").strip()
if not key:
    st.info(
        "AI interpretation is not configured on this deployment. "
        "The offline evidence review above works without an additional key."
    )
else:
    st.caption(
        "Clicking Generate sends only the selected historical evidence pack "
        "to the configured AI service. It may incur API usage charges. "
        "The model does not browse the web or access live match data."
    )

fingerprint = hashlib.sha256(
    json.dumps(pack, sort_keys=True, ensure_ascii=False).encode("utf-8")
).hexdigest()

if st.button(
    "Generate evidence-cited interpretation",
    disabled=not bool(key),
    type="primary",
):
    with st.spinner("Checking historical source-backed observations"):
        try:
            analysis = explain_historical_evidence(pack, key)
        except HistoricalAIError as exc:
            st.error(str(exc))
        else:
            st.session_state["historical_ai_result"] = (
                fingerprint, analysis
            )

stored = st.session_state.get("historical_ai_result")
if stored is not None and stored[0] == fingerprint:
    review = stored[1]
    allowed = {item["id"]: item for item in pack["evidence"]}
    for number, item in enumerate(review["observations"], 1):
        st.markdown(f"**Observation {number}**")
        st.write(item["text"])
        st.caption(
            "Referenced local evidence: "
            + ", ".join(item["evidence_ids"])
        )
        with st.expander("Verify cited evidence"):
            for ref in item["evidence_ids"]:
                st.markdown(f"**{ref}**")
                st.write(allowed[ref]["fact"])
    st.subheader("Uncertainty and data limitations")
    for limitation in review["limitations"]:
        st.write("- " + limitation)
    st.warning(
        "An evidence ID confirms the cited record exists. It does not "
        "guarantee the model interpreted that record correctly. "
        "Verify each claim against the evidence above."
    )
else:
    st.subheader("Known limitations")
    for limitation in pack["limitations"]:
        st.write("- " + limitation)

st.caption(
    "No current fixtures, wagering, prices or future outcomes are used. "
    "The football-data.org and Sportmonks datasets remain separate."
)

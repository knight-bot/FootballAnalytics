"""Review historical Sportmonks <-> football-data.org fixture candidates.

This page is read-only. Associations become reviewed only after a human
checks actual source scores and uses the separate manual GitHub Action.
"""
import csv
import io
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd
import streamlit as st

from historical_fixture_linkage import candidate_links

st.set_page_config(
    page_title="Historical Fixture Link Review | FootballAnalytics",
    page_icon="🔗", layout="wide",
)
st.title("Historical Fixture Link Review")
st.caption(
    "Compare stored completed Sportmonks fixtures to recorded "
    "football-data.org results before linking their statistics."
)
st.warning(
    "Candidate links are NOT automatically approved. Newly imported or "
    "refreshed regular-time Sportmonks fixtures can contain stored "
    "CURRENT final-score evidence. Any conflicting source score blocks "
    "review. Manual confirmation still requires checking both original "
    "provider records, even when stored scores agree."
)

DB_PATH = Path(__file__).resolve().parent.parent / "football.db"
if not DB_PATH.exists():
    st.error("football.db is missing.")
    st.stop()


@st.cache_data(ttl=300, show_spinner=False)
def read_candidates(db_version):
    with closing(sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode=ro", uri=True,
    )) as conn:
        return candidate_links(conn)


rows = read_candidates(DB_PATH.stat().st_mtime_ns)
if not rows:
    st.info(
        "No two-provider historical fixture records are available. "
        "Import completed Sportmonks fixtures first."
    )
    st.stop()

counts = {
    key: sum(r["status"] == key for r in rows)
    for key in ("reviewed", "review_candidate", "score_mismatch",
                "ambiguous", "unmatched", "stale_review")
}
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Operator-reviewed", counts["reviewed"])
c2.metric("Review candidates", counts["review_candidate"])
c3.metric("Score mismatches", counts["score_mismatch"])
c4.metric("Ambiguous", counts["ambiguous"])
c5.metric("Unmatched / stale", counts["unmatched"]+counts["stale_review"])

status = st.multiselect(
    "Show link statuses",
    options=list(counts),
    default=list(counts),
)
filtered = [row for row in rows if row["status"] in status]
st.dataframe(
    pd.DataFrame(filtered),
    use_container_width=True,
    hide_index=True,
)
buffer = io.StringIO()
writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
writer.writeheader()
writer.writerows(rows)
st.download_button(
    "Download candidate-review CSV",
    data=buffer.getvalue(),
    file_name="historical_fixture_link_review.csv",
    mime="text/csv",
)
st.divider()
st.subheader("Prepare a bounded bulk source review")
st.caption(
    "Use this worksheet to compare original provider fixture pages "
    "one by one. Do not mark a pair checked unless you independently "
    "verified its home and away teams, kickoff and final score in "
    "BOTH providers. Score agreement shown here is not approval."
)
eligible = [row for row in rows if row["status"] == "review_candidate"]
if eligible:
    worksheet = pd.DataFrame([
        {
            "sportmonks_fixture_id": r["sportmonks_id"],
            "football_data_match_id": r["match_id"],
            "sportmonks_match": r["sportmonks_match"],
            "football_data_match": r["result_match"],
            "sportmonks_date": r["sportmonks_date"],
            "result_date": r["result_date"],
            "sportmonks_stored_final_score":
                r["sportmonks_stored_final_score"],
            "football_data_final_score": r["result_score"],
            "score_comparison": r["score_comparison"],
            "original_sources_independently_checked": "NO",
            "reviewer_notes": "",
        }
        for r in eligible
    ])
    st.download_button(
        "Download manually checked fixture review worksheet (.csv)",
        data=worksheet.to_csv(index=False).encode("utf-8"),
        file_name="historical_source_review_worksheet.csv",
        mime="text/csv",
    )
    st.caption(
        "After independently checking each eligible pair, enter ONLY "
        "personally verified pairs into the bulk GitHub Action as "
        "SportmonksID:MatchID:CHECKED, separated with semicolons. "
        "Maximum 20 entries per approval run."
    )
    st.markdown(
        "[Confirm Checked Historical Fixture Pairs in GitHub Actions]"
        "(https://github.com/knight-bot/FootballAnalytics/actions/workflows/"
        "confirm-bulk-historical-links.yml)"
    )
else:
    st.info("No unambiguous, unreviewed candidates to prepare.")

st.subheader("Manual confirmation process")
st.markdown(
    "1. Find a **review_candidate** row with two IDs and identical "
    "home/away teams, league, and a matching kickoff.\n"
    "2. Compare **both original provider match pages** yourself. Inspect "
    "the stored score comparison, when present. A mismatch blocks "
    "approval; an agreement supports but does NOT replace manual "
    "source review. Older fixtures may require a refresh to make "
    "the source score available locally.\n"
    "3. Open GitHub Actions > **Confirm Reviewed Historical Fixture Link**. "
    "Enter the corresponding Sportmonks and football-data.org IDs and "
    "explicitly attest that you compared both final scores.\n"
    "4. When the GitHub Action saves the link and your Streamlit app "
    "refreshes its database, the status should change to **reviewed**.\n"
    "5. Do not confirm **score_mismatch**, ambiguous, unmatched or stale rows."
)
st.info(
    "The dashboard never writes to football.db. GitHub Actions performs "
    "the explicit confirmation and stores reviewed associations in "
    "a dedicated table. Existing results and metrics remain unchanged."
)

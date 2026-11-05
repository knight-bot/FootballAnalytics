# Phase 13: historical fixture linkage

This feature identifies **candidate matches** between the two local data
providers, then supports explicit manual review. It performs no network
requests, forecasts, or gambling recommendations.

## What changes

- \`historical_fixture_linkage.py\`: compares only completed Sportmonks
  fixtures and completed football-data.org Premier League results. It
  requires matching home and away team identities, matching competition,
  kickoff times at most 120 minutes apart, and an unambiguous one-to-one
  candidate.
- \`pages/8_Historical_Fixture_Link_Review.py\`: shows every candidate,
  ambiguity, unmatched record, and currently valid operator-reviewed
  link. Allows a CSV export. The page is **read-only**.
- \`confirm_historical_link.py\` + a manual GitHub Action: saves an
  operator-reviewed association **only after** the operator attests that
  they independently compared the final score in each provider.
- \`chatgpt_research_export.py\`: lists currently valid operator-reviewed
  cases for the selected team in **Part A.1**, automatically; independent
  manual case-study selections remain in Part B.

All existing result and statistics tables remain separate. Links are
stored in a new \`reviewed_historical_fixture_links\` table. There is no
fuzzy automatic linking, no guess based on partial team names, and no
automatic acceptance when one match has multiple possible partners.

## Why confirmation is manual

Older stored Sportmonks fixtures captured the **number** of score
records but not the actual result. The upgraded importer can now persist
strict `CURRENT` final-score evidence for an unambiguous regular-time
`FINISHED` match. After those fixtures are refreshed, the matcher checks
whether the stored Sportmonks score agrees with the football-data.org
result. A discrepancy receives `score_mismatch` and cannot be approved.
For extra-time or penalty-ending fixtures, or absent/ambiguous score
records, the stored comparison remains unavailable.

A reviewed association means **the GitHub workflow operator attested**
that the original sources' final scores agreed. It is not a separately
independent source-level verification by the application. If the stored
fixture data changes later, the matcher automatically downgrades the link
to \`stale_review\` rather than silently continuing to join it.

## How to use it

1. Allow the latest Streamlit app deployment to refresh.
2. Open **Historical Fixture Link Review** in the Streamlit sidebar.
3. Inspect the \`review_candidate\` rows. Check original provider
   pages for both match IDs; confirm the home and away teams, kickoff,
   competition **and final score**.
4. Open the GitHub Actions workflow:
   \`https://github.com/knight-bot/FootballAnalytics/actions/workflows/confirm-historical-fixture-link.yml\`
5. Enter the Sportmonks fixture ID and the football-data.org match ID
   from the same unambiguous candidate row, tick the score-confirmation
   checkbox **only after actually comparing both sources**, and click
   Run workflow.
6. When the workflow succeeds, confirm the database save step succeeded
   too. Refresh Streamlit and verify the row says \`reviewed\`.
7. Open **ChatGPT Research Export**, choose that team's competition and
   season, and download the updated Markdown report. Any reviewed,
   currently valid fixture matching that selection appears in Part A.1.

**Do not confirm** any \`unmatched\`, \`ambiguous\` or \`stale_review\`
entry. Do not assume the presence of a Sportmonks metric means every
match in a team's season has that metric.

## Offline testing

Run GitHub Actions -> **Audit Historical Football Data** -> Run workflow.

The offline unit tests check exact naming, kickoff windows, home/away
direction, league constraints, incomplete fixtures, conflicting
matches, duplicate candidates, explicit score-check attestation,
stale links, and safe team-report inclusion.

Stored score agreement corroborates an association but never approves
it automatically. Operator attestation remains required. A green offline
test suite cannot establish actual provider-wide coverage; manual
verification remains essential.

See [Historical source-score quality checks](HISTORICAL_SOURCE_SCORE_QA.md)
for the controlled refresh procedure.

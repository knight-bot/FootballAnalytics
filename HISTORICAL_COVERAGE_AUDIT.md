# Historical match coverage audit

**Historical Fixture and xG Coverage Audit** is a read-only Streamlit page
for checking which locally stored completed match results can be linked to
operator-reviewed Sportmonks data.

It does not fetch current fixtures, build wagering recommendations, or
make future-match forecasts.

## What to do

1. Open the **Historical Coverage Audit** page in Streamlit.
2. Choose the competition, July–June historical season, and optionally
   one team. The default is every team in that stored competition/season.
3. Inspect the valid stored match count and the percentage of those
   matches with currently operator-reviewed cross-provider links.
4. Inspect the percentage with both standard Sportmonks xG values
   stored under those reviewed links.
5. Filter the source-by-source table by coverage status, download the
   CSV, or download a standalone Markdown research report.
6. For eligible \`review_candidate\` rows, use **Historical Fixture
   Link Review** to cross-check original provider score records
   before submitting a manual confirmation.
7. Open **ChatGPT Research Export** and select the same team and
   historical season. Its **Part A.4** now includes the full recorded
   match-by-match coverage audit.

## Coverage statuses

| Status | Meaning |
|---|---|
| reviewed_complete_xg | Currently operator-reviewed link and exactly one valid standard xG value for each side |
| reviewed_missing_xg | Currently operator-reviewed link, but one or both standard xG values are missing, invalid or ambiguous |
| review_candidate | Source team identities, competition and kickoff agree, but the original Sportmonks final score has not been independently checked by the app |
| score_mismatch | Stored Sportmonks CURRENT final score conflicts with the recorded football-data.org result; do not confirm |
| ambiguous | More than one possible local association; do not confirm blindly |
| stale_review | A previously reviewed source association no longer agrees with the currently stored identifying records |
| no_imported_candidate | No unambiguous locally stored Sportmonks candidate is available for this completed result |

The source result's match ID and score are always preserved. The
Sportmonks fixture ID and standard xG values are attached to that
result only if its link remains reviewed. Unreviewed candidates may show
their separate candidate Sportmonks ID for manual checking, but no
cross-provider statistics are joined to them.

**Important source caveat:** Older imported Sportmonks fixtures lack
stored final scores. New regular-time imports can preserve unambiguous
`CURRENT` scores and automatically flag disagreement with the
other source. This is a source-consistency check, not automatic linking.
A reviewed association is still *operator-attested*.

## Denominators and sample limitations

The reviewed-link and reviewed-xG coverage percentages use the
number of **valid FINISHED results physically stored in the local
football-data.org results table for that selection** as denominator.

These are not estimates of completeness of the official league season.
The app cannot infer missing matches it never imported. A full-season
coverage claim requires a separate comparison with an authoritative
schedule/results source.

A missing metric is **unknown, not zero**. No future fixtures are
included. Review small samples carefully.

## Verification

Run the GitHub workflow:

https://github.com/knight-bot/FootballAnalytics/actions/workflows/historical-audit.yml

The offline test suite now covers review candidates, reviewed/complete
xG, reviewed/missing xG, ambiguous and stale links, wrong participant IDs,
competition and season filters, zero-denominator behavior, and untouched
SQLite data.

The feature is designed to be read-only. Running the tests and
manually verifying the deployed Streamlit page are still required to
establish runtime success after a new commit.

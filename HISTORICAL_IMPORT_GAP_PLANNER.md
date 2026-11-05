# Historical Import Gap Planner

This read-only page identifies **completed football-data.org results already
stored locally** that still lack an imported Sportmonks matching candidate.
It turns those gaps into bounded, manual Sportmonks batch-import windows.

The purpose is retrospective historical data quality research, not live
gameweek assessment or wagering recommendations.

## Immediate next import

The previous historical batch run for **2026-10-17 through 2026-10-21**
reported ten discovered completed Sportmonks fixtures and initially
imported five. If the other five are still absent from football.db,
you can re-run the *existing* manual importer with:

- **start_date:** \`2026-10-17\`
- **end_date:** \`2026-10-21\`
- **max_fixtures:** \`10\`
- **refresh_existing:** \`false\`

Open:

https://github.com/knight-bot/FootballAnalytics/actions/workflows/sportmonks-historical-batch.yml

The existing importer skips fixture IDs that are already present when
\`refresh_existing\` is false. If the missing fixtures have since
been imported, the workflow should report no new imports.

The import requires the existing \`SPORTMONKS_API_TOKEN\` secret and
account access to the subscribed historical Sportmonks data. This
planning update does **not** run the API importer itself.

## Plan historical gaps for other dates

1. Open **Historical Import Gap Planner** in the Streamlit sidebar.
2. Choose **Premier League** and a date-derived historical season.
3. Inspect the categorized work queue:
   - **Old results missing candidates:** possible new historical imports
   - **Candidates requiring review:** source records already discovered,
     requiring manual final-score comparison
   - **Score conflicts, ambiguous or stale:** manual source investigation
     needed; conflicting matches cannot be confirmed
   - **Reviewed but missing xG:** inspect Sportmonks coverage or import
     completeness; refreshing may not create unavailable xG
4. Copy a suggested start/end date window into the existing manual
   batch-import GitHub Action.
5. Import at most **10 fixtures** per run. The discovery endpoint
   is restricted to no more than **14 inclusive days**, at least
   **14 days old**, and league ID **8**.
6. Return to **Historical Coverage Audit** and **Historical Fixture
   Link Review** to evaluate new candidates.
7. Confirm a link **only after** checking both original providers'
   teams, kickoff date and final score. Importing alone never approves
   a link and never attaches xG to a football-data.org result.

The planner ranks windows by the number of locally recorded results
with no imported candidate, using older dates to break ties.
Its stated numbers are counts of **local gaps**, not promises of
available Sportmonks fixtures or metrics. The importer may discover
other completed league fixtures in the same dates.

## Why no automatic matching or scheduled historical import?

Provider IDs differ. The upgraded importer can preserve unambiguous
historical `CURRENT` full-time scores and flag conflicts, but a
name/date/score match is not proof that every recorded metric is correct.
Manual approval and source audit remain necessary.

This phase therefore leaves both importing and match verification
manual. No new API secrets or paid OpenAI API subscription are needed
for the planner itself.

## Known limitations

- The planner only knows about results already stored in football.db.
  It cannot identify completely missing fixtures from an official
  league season without an independent schedule comparison.
- Only the Premier League's verified Sportmonks league mapping is
  implemented, because the historical importer is restricted to
  Sportmonks league ID 8.
- Proposed date windows are disjoint and at most 14 days long; their
  ranking is a simple data-gap heuristic, not a promise of maximum
  provider match coverage.
- The API may have no xG coverage even if the fixture can be imported.
  Missing is unknown, not zero.
- Reviewed links depend on an operator's attestation that source
  final scores agree; they are not independently score-verified
  by the app.

## Test the feature

Run the GitHub Actions **Audit Historical Football Data** workflow:
https://github.com/knight-bot/FootballAnalytics/actions/workflows/historical-audit.yml

The new offline planner unit tests include historical date cutoffs,
bounded windows, selection priorities, stale and ambiguous links,
no-candidate and missing-xG classification, and read-only behavior.

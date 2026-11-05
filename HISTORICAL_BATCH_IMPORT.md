# Sportmonks historical batch import

This workflow discovers **completed historical Premier League fixtures** by
date range, then saves a small batch of advanced statistics into separate
Sportmonks tables within football.db.

It is intended for retrospective football research. It does not fetch live or
upcoming matches, create future forecasts, or use odds.

## Gap-driven historical date selection

For an evidence-backed choice of historical import dates, first open
**Historical Import Gap Planner** in the Streamlit dashboard. It uses
the local completed-match coverage audit to propose bounded date
windows where stored results still lack imported Sportmonks candidates.
It does not run API requests or automatically establish provider links.
See [Historical Import Gap Planner](HISTORICAL_IMPORT_GAP_PLANNER.md).

## How to run

1. In GitHub, open **Actions**.
2. Select **Discover and Import Historical Sportmonks Fixtures**.
3. Click **Run workflow** on branch \`main\`.
4. Keep the default historical test dates (17–21 October 2026) or choose
   another *past* window of **at most 14 calendar days**.
5. Keep \`max_fixtures\` at **5** for the first run.
6. Leave \`refresh_existing\` off, then run the workflow.
7. Open **Discover and import completed historical fixtures** in the logs.
   Look for "Completed fixtures discovered", "Selected for this import",
   "Remaining eligible after this batch", and "imported".
8. Refresh Streamlit and open **Historical Data Audit** and
   **Sportmonks Historical Stats** to inspect the imported sample.

The workflow uses the existing \`SPORTMONKS_API_TOKEN\` GitHub Actions
**secret**. Never put the token in the code, a report, or a screenshot.

## What it actually does

- Uses Sportmonks Football API v3's
  \`/football/fixtures/between/YYYY-MM-DD/YYYY-MM-DD\` endpoint.
- Filters discovery to Sportmonks Premier League ID \`8\`.
- Collects all discovery pages within a five-page safety limit.
- Retains only finished matches at least 14 days old, checks IDs and dates,
  and selects at most 10 per run (default 5).
- Skips fixtures already in the SQLite Sportmonks history table unless
  **refresh existing** is explicitly selected.
- For each selected fixture, calls the established fixture-by-ID importer to
  retrieve available xG-related metrics, numeric team stats and minute-level
  Pressure Index records.
- Preserves the independent football-data.org \`matches\` table. The two
  providers use **different IDs**, so the importer does not join their data.
- Runs fully offline unit tests before contacting Sportmonks.
- Saves updated SQLite tables back to GitHub if the import changes the file.

## Backfill final-score evidence for old historical imports

The importer now saves a strict `CURRENT` final score (both home and
away) from the Sportmonks `scores` include **only** for completed
regular-time state 5 when the values and participants are unambiguous.
Extra-time and penalty-ending matches stay manual-review cases.

Pre-upgrade fixtures do not magically acquire these saved values.
For the **October 17–21, 2026** window, which now contains all ten
discovered records, use the existing manual GitHub Action with:
`start_date=2026-10-17`,
`end_date=2026-10-21`,
`max_fixtures=10`,
`refresh_existing=true`.

This performs a bounded source refresh, not a new history import or a
cross-provider link approval. Source score disagreement blocks new
approval; agreement never approves a link by itself.

See [Historical source-score quality checks](HISTORICAL_SOURCE_SCORE_QA.md).

## Limits and caveats

- Importing 5 fixtures is a *sample*, **not a complete season or league**.
- The 14-day maximum and 10-fixture cap are intentional guards against
  expensive or incomplete imports. Repeat the manual workflow to process
  remaining qualifying fixtures in the same date window; it skips already
  stored IDs by default.
- Some leagues, seasons, matches, or includes might not be available under
  the connected account. A successful API request does not guarantee
  complete statistical coverage.
- API responses can contain nonnumeric values that are not stored by our
  normalized numeric importer. Use the Data Audit to find coverage gaps.
- A provider subscription or trial may expire, at which point new imports
  may stop even though the local stored dataset remains.
- GitHub workflow logs report how many records were discovered, imported and
  still eligible. They do not establish whether *every match the provider
  might eventually publish* has already been released.
- This workflow is **manual**, not scheduled. If the selected window yields
  zero matches, use another historical date window rather than a future date.
- See the Sportmonks API documentation for additional restrictions and terms
  concerning data retention, licensing and publication.

## API source

Sportmonks Football API v3:
\`https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/fixtures/get-fixtures-by-date-range\`

## Testing without Sportmonks API usage

Run the **Audit Historical Football Data** GitHub Action. It executes the
historical importer tests with fake fixture responses and makes no Sportmonks
requests. Real import access and Streamlit deployment still require runtime
verification.

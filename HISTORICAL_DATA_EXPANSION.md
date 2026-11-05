# Historical data expansion: backfill, manual bulk review, quality audit

This phase expands the **retrospective, completed-match** data pipeline.
It does not calculate upcoming outcomes or gambling recommendations.

## 1. Why this phase exists

The November 5, 2026 stored-data audit found 1,921 finished match
results, 11 independent Sportmonks historical fixture imports with
two-sided xG, 10 unreviewed provider-pair candidates and 0 approved
provider associations.

The underlying results history is much larger than the reviewed xG
sample. Raw Sportmonks xG must not be silently assigned to football-data.org
matches on team names alone.

## 2. Resumable historical backfill

Open [Backfill Completed Historical Football Data](https://github.com/knight-bot/FootballAnalytics/actions/workflows/historical-backfill.yml).

Choose the `main` branch and set:
- `start_date`: a past historical date with actual matches, such as
  `2025-08-15`, the first day of the 2025/26 Premier League season.
- `end_date`: at most 84 inclusive days later. For the first small
  check, use `2025-08-28` (14 days, 10 fixture enrichments).
- `max_fixtures`: 10 for the first check, then up to 30 per run.

**Empty-date windows:** The 2025/26 Premier League began on
15 August 2025. Earlier August windows can legitimately contain no
league fixtures. The importer accepts an explicitly empty first-page
`data: []` response with no pagination, but rejects missing fixture
data, embedded error responses, and missing pagination when fixtures
exist. An empty response is not proof of licensed historical coverage.

The backfill splits the selected range into adjacent 14-day windows,
uses the existing Sportmonks Premier League league ID 8 discovery, and
enriches at most 10 completed fixtures from each window and at most
the total user-selected budget per run.

Completed fixtures are saved atomically by the existing importer.
Previously stored IDs are skipped on rerun; repeat the SAME start/end
dates to resume until the workflow summary says
`Range exhausted` / `All selected historical windows fully checked`.
If a later API call fails, earlier committed fixtures survive, and
the workflow pushes the saved database before reporting failure.

HTTP 500/502/503/504 responses use short bounded retries. HTTP 429
rate limits stop the batch cleanly instead of waiting indefinitely
inside CI. Resume after the provider's quota resets.

No script can promise every league match exists in the subscribed
Sportmonks data, and there is no automatic cross-provider joining.

### Refresh already imported historical scores first

The backfill intentionally skips existing fixture IDs. To obtain
unambiguous `CURRENT` final-score evidence on older imports, use the
original [Discover and Import Historical Sportmonks Fixtures](https://github.com/knight-bot/FootballAnalytics/actions/workflows/sportmonks-historical-batch.yml)
workflow with:

| Input | Value |
|---|---|
| start_date | `2026-10-17` |
| end_date | `2026-10-21` |
| max_fixtures | `10` |
| refresh_existing | `true` |

This is a *source refresh*, not an approval and not a new-data backfill.

## 3. Review up to 20 historical fixture pairs per workflow

Open **Historical Fixture Link Review** in Streamlit and download
the **manual source-review worksheet**. For every candidate under
consideration, independently compare BOTH original providers'
team identities, kickoff and final scores.

Only after personally checking a pair, enter it in
[Confirm Checked Historical Fixture Pairs](https://github.com/knight-bot/FootballAnalytics/actions/workflows/confirm-bulk-historical-links.yml)
using:

```text
SportmonksFixtureID:FootballDataMatchID:CHECKED;OtherSportmonksID:OtherResultID:CHECKED
```

The IDs above are placeholders, not actual review instructions.
For each entry the `CHECKED` token means **you personally verified
the original records**. You must also check the separate
`all_scores_compared` confirmation box.

A single approval run accepts at most 20 distinct one-to-one pairs.
The workflow performs full validation before writing any rows.
Mismatches, ambiguous results, stale reviews and inconsistent IDs
block the batch. If any pair is invalid, no new association in that
batch is approved. Already-approved exact pairs are idempotent.

Source-score agreement in the app is evidence for review, NOT an
automatically granted approval. Missing source-score fields may still
be checked manually against original provider records.

The original single-match
[Confirm Reviewed Historical Fixture Link](https://github.com/knight-bot/FootballAnalytics/actions/workflows/confirm-historical-fixture-link.yml)
workflow remains available.

## 4. Evidence quality grades

The existing **Historical Coverage Audit** Streamlit page now displays
season-wide counts and local-source evidence grades:

| Grade | Meaning |
|---|---|
| A | Currently operator-reviewed one-to-one association with both valid standard xG values |
| B | Reviewed association, but missing or invalid two-sided standard xG |
| C | Unreviewed matching candidate; its xG is NOT joined to the result |
| D | Conflicting source scores, ambiguous candidates or stale reviewed link |
| U | Locally recorded finished result with no imported candidate |

The page displays grade counts **by month and by recorded team**,
provides CSV downloads, and exports a Markdown evidence-quality report
with original result match IDs.

**The denominator is valid finished matches already stored in the
local database, not an independently verified complete official
Premier League schedule.** Two team rows are generated per match in
the team table.

The quality system intentionally never replaces missing xG with zero.

## 5. What needs manual input

You still need to:
1. Trigger a deliberate source-score refresh for old imported fixtures.
2. Run an initial, bounded backfill and inspect API subscription access.
3. Repeat backfill windows to increase historical coverage.
4. Independently check original source records and submit approved pairs.
5. Inspect updated source-quality grades and research exports in Streamlit.

Automated tests prove that the code handles expected data correctly,
not that licensed source data exists or that every provider record is
correct. The deployed Streamlit host also needs manual acceptance
verification after the code update.

## Official API references

- Sportmonks API v3 fixture date-range and pagination:
  https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/fixtures/get-fixtures-by-date-range
- Sportmonks API rate limits:
  https://docs.sportmonks.com/v3/api/rate-limit

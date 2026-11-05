# Historical source-score quality checks

## What changed

The completed historical fixture importer now extracts and stores
unambiguous Sportmonks Football API v3 \`CURRENT\` scores for the
home and away participants, **only for finished regular-time fixtures**
(\`state_id=5\`). The score originates from the existing \`scores\` API
include, which earlier imported records had not saved numerically.

The stored evidence lives in the separate
\`sportmonks_historical_final_scores\` SQLite table. It never
overwrites football-data.org match results, and it never creates
automatic provider links.

Extra-time and penalty states \`7\` and \`8\`, missing scores, duplicate
\`CURRENT\` records, invalid goal counts, or mismatched participants
are *unavailable*, not guessed. A refresh which stops returning valid
final-score evidence clears the previously saved score for that
fixture rather than silently retaining stale evidence.

## Current verified data state

The most recent audit after the completed October historical import
found:

- **1,921** locally stored completed football-data.org results
- **11** imported completed Sportmonks historical fixtures
- **11** Sportmonks fixtures with both standard xG values
- **10** historical cross-provider match candidates awaiting review
- **0** valid operator-reviewed cross-provider links
- **0** stored unambiguous \`CURRENT\` final scores in existing imports

The final two zeros are not a software failure: the old source imports
predate persistence of final score values. The original API score
records are not recovered by changing the parser alone.

## One controlled historical refresh

Open the existing manual workflow:

https://github.com/knight-bot/FootballAnalytics/actions/workflows/sportmonks-historical-batch.yml

For the already imported October window use:

| Workflow input | Value |
|---|---|
| start_date | \`2026-10-17\` |
| end_date | \`2026-10-21\` |
| max_fixtures | \`10\` |
| refresh_existing | \`true\` |

This re-fetches up to 10 *already completed* historical fixtures and
preserves their source score evidence when unambiguous. It is not a
request to collect a different set of games. It uses the established
Sportmonks API token secret.

Other older imported fixtures may require their own separate, bounded
refresh only if investigation justifies it.

## How to interpret cross-provider score checks

1. \`score_comparison=agrees\`: a stored Sportmonks CURRENT score
   matches the football-data.org result for a conservative name/date
   candidate. It remains **review_candidate** until an operator
   independently confirms both original provider records.
2. \`score_comparison=mismatch\`: stored final scores disagree.
   The candidate becomes **score_mismatch** and approval is blocked.
   A previously operator-reviewed association becomes
   **stale_review** and cannot contribute to joined xG analysis.
3. \`score_comparison=unavailable\`: the fixture has no reliable
   stored CURRENT score. Follow the original manual source verification
   procedure; never replace missing evidence with zero.

**Do not treat matching final scores as sufficient to approve a link.**
The separate **Confirm Reviewed Historical Fixture Link** GitHub Action
remains mandatory for creating an approved cross-provider association.
The reviewing operator must personally compare the original records.

## Audit and research integration

- **Historical Fixture Link Review** displays the stored score and
  comparison status, including explicitly blocked mismatches.
- **Historical Coverage Audit** counts score conflicts separately and
  prevents unreviewed advanced metrics from attaching to a result.
- **Historical Import Gap Planner** directs score conflicts to manual
  investigation rather than repeatedly recommending a discovery import.
- **Audit Historical Football Data** reports score-evidence coverage,
  reviewed links and score conflicts separately from the presence of xG.
- **Historical xG Analysis** and the ChatGPT report continue to
  include only currently valid operator-reviewed provider links.

## Offline regression testing

The historical audit workflow now runs 15 additional score evidence
tests checking strict parsing, missing and duplicated scores, source
disagreements, stale reviews, safe source-ID handling, and read-only
audit queries.

Green unit tests do not automatically certify historical source
accuracy, a full official league schedule, or a Streamlit deployment.
Actual imported scores and reviewed links must be checked separately.

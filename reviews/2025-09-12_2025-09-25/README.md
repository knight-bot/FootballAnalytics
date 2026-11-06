# Historical backfill audit: September 12–25, 2025

Prepared November 6, 2026 (Singapore).

## Import execution

- [Run 7](https://github.com/knight-bot/FootballAnalytics/actions/runs/42088500644): requested maximum 20; imported 10 due to the internal per-window cap of 10.
- [Run 8](https://github.com/knight-bot/FootballAnalytics/actions/runs/42088790227): resumed identical dates with maximum 10; skipped the prior 10 and imported the remaining 10.
- Total newly imported: **20**, within the requested maximum. Provider discovery returned 20; final status: **Range exhausted**. This is not independent proof of official schedule completeness.
- Data committed to main in 0f8c0ba and cc4b5f0. No source-link approval workflow was invoked.

## Audit findings

The post-import audit and quality commands succeeded in both workflows; 25 importer regression tests passed per run. A read-only local check of the resulting database returned SQLite integrity_check = ok.

For the requested window: 20 unique Sportmonks fixtures and 20 distinct football-data.org candidates; all are review_candidate, all kickoff differences are 0 minutes, all stored final scores agree, all have standard home and away xG, and none has an audit finding. These are local consistency checks, not independent original-record verification.

Repository totals after import:

| Measure | Count |
|---|---:|
| Completed result records | 1,921 |
| Invalid completed results | 0 |
| Imported Sportmonks fixtures / two-sided standard xG | 61 / 61 |
| Stored unambiguous CURRENT final scores | 50 |
| Review candidates | 60 |
| Reviewed links | 0 |
| Score conflicts / ambiguous or stale links | 0 / 0 |
| Fixtures with audit findings | 0 |

The remaining one imported fixture is unmatched. Eleven older imports lack saved unambiguous final-score evidence. The 2025/26 local sample has 380 results: A=0, B=0, C=50, D=0, U=330. Unreviewed xG remains unavailable as approved cross-provider evidence.

## Review queue

[source_review_queue.csv](source_review_queue.csv) contains the 20 newly imported pairs, both provider IDs, team names, UTC kickoffs, stored scores, candidate status and original API record URLs. The URLs are constructed from the repository's provider endpoints and stored IDs; they have **not been fetched or independently verified** and require appropriate provider authentication. No credentials are included.

Every row is marked original_sources_independently_checked=NO. Before approving a pair, retrieve BOTH original provider records and compare competition, home/away identities, kickoff and completed final scores. Record the reviewer, UTC verification time and evidence in the worksheet. Any conflict blocks approval. Do not submit CHECKED attestations from this unverified worksheet.

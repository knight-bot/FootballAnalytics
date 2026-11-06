# ChatGPT Work handoff: verify historical xG source associations

## Purpose

Continue the user-authorized historical data-quality work in
`knight-bot/FootballAnalytics`, using GitHub and, where available, the
connected browser / authenticated provider sites. The goal is to
**independently verify and prepare up to 10 historical fixture links**,
then safely record only associations that are actually verified.
Do not infer approval from the existence of imported data.

This is retrospective football research, **not** future-game advice,
predictions, gambling or betting recommendations.

## Current evidence snapshot (recheck before acting)

From the successful 2025-09-12 to 2025-09-25 backfill and its audit,
GitHub Actions run:
https://github.com/knight-bot/FootballAnalytics/actions/runs/42088790227

- 1,921 locally recorded completed football-data.org results.
- 61 imported historical Sportmonks fixtures with two-sided standard xG.
- 50 imports with stored unambiguous CURRENT score evidence.
- 60 candidate cross-provider source associations awaiting human review.
- **0 currently operator-reviewed source associations.**
- No saved source-score conflicts were reported by that run.
- In locally recorded 2025/26 Premier League matches: 50 class C
  unreviewed candidates, 0 A/B reviewed, 330 U with no candidate.

This is an audit snapshot, NOT live or independently certified coverage.
Re-read the repository, latest workflow runs, and current SQLite database
before making decisions. Avoid duplicating work from other agents/users.

## Work plan

1. Open the repository on `main`; review `README.md`,
   `HISTORICAL_DATA_EXPANSION.md`,
   `DEPLOYMENT_CHECKLIST.md`, `research_readiness.py`,
   `historical_fixture_linkage.py`,
   `bulk_confirm_historical_links.py`, and the current audit results.
2. Run or inspect the **Audit Historical Football Data** workflow.
   Confirm source-match candidates, xG completeness, contradictions,
   stale approvals, score evidence, and database integrity.
3. Use the **Historical Fixture Link Review** Streamlit page to export
   the candidate review worksheet. If needed, use the repo's read-only
   Python tools against the actual current `football.db` to build the
   same table. Start with up to **10** unambiguous 2025/26 Premier League
   candidates with stored full-time source scores, preferably across
   different match dates and clubs.
4. For EACH candidate, independently open the **original provider
   records** from both Sportmonks and football-data.org (legitimate
   authenticated provider APIs/pages if access is authorized).
   Verify the real match IDs, league, season, home club, away club,
   date and timezone, and both teams' full-time goals. The original
   provider records must be checked individually. Club-name aliases,
   a locally stored copy, matching names, kickoff times or matching
   scores are *supporting information only* and NEVER substitute for
   consulting the actual original provider records.
5. Preserve an evidence log (CSV/Markdown or PR), containing both
   immutable source IDs, the original source URLs/endpoints, date of
   inspection, checked values, and a rationale. Do not include API
   keys, cookies, auth headers, response secrets, or personal info.
   Classify each row as VERIFIED, BLOCKED, CONFLICT, or UNAVAILABLE.
   No fabricated URLs or inferred evidence. If a provider's original
   record is inaccessible, mark UNAVAILABLE, do not approve.
6. For **only genuinely VERIFIED** associations, use the existing
   reviewed-link workflow:
   https://github.com/knight-bot/FootballAnalytics/actions/workflows/confirm-bulk-historical-links.yml
   Enter at most 20 distinct `SportmonksID:FootballDataMatchID:CHECKED`
   pairs. The "all_scores_compared" attestation is truthful ONLY if
   BOTH original providers' data for EVERY submitted association were
   independently inspected. If this cannot be done, do NOT check the
   box or submit the workflow. If the connected app requires extra
   authorization or approval, request it through the normal UI.
7. Re-run the historical audit; confirm valid reviewed links and
   the reviewed two-sided xG count rise only for verified links. Check
   that there are no new score conflicts or stale associations and
   that tests pass. Confirm the relevant research exports are
   source-grounded.
8. Return a concise completion report: which IDs were examined,
   original provider evidence URLs, which were independently verified,
   which were approved (with commit/run link), which remain blocked,
   the final audit counts, and specific unresolved access problems.

## Absolute safety / data-integrity rules

- Never bypass the application's manual review gate, set approvals
  directly in SQL, or mark `CHECKED` without consulting both original
  source records.
- Do not manufacture proof from the importer, cached dashboard, GitHub
  logs, match-name strings, or general sports reporting.
- Do not approve conflicting, ambiguous, incomplete or inaccessible
  provider records. Do not extrapolate reviewed xG from unreviewed games.
- Do not delete or overwrite existing historical evidence as a workaround.
- Avoid new bulk imports while the first verification cohort is under
  review; focus on proving the existing evidence chain.
- If Work cannot access a provider's original records, stop that
  verification and give the user the exact access blocker, rather than
  claiming the match is verified.

## Authentication workaround (added after Work browser access failures)

The first Work inspection of 10 September candidates could not access
either provider's original fixture records. Sportmonks browser requests
returned "No token provided"; football-data.org returned HTTP 403.
These are access failures, NOT match mismatches or verified pairs.

The repository's GitHub Actions already provides the two existing
secrets `SPORTMONKS_API_TOKEN` and `FOOTBALL_API_TOKEN` to import
workflows. It now also provides a dedicated, **read-only evidence
collection workflow**:

https://github.com/knight-bot/FootballAnalytics/actions/workflows/collect-original-provider-evidence.yml

Use the inputs `start_date=2025-09-12`,
`end_date=2025-09-25`, `max_pairs=10`. The workflow fetches
original records via BOTH authenticated provider APIs by their
individual immutable match ID. It creates a downloadable artifact
named `original-historical-source-evidence`, containing only a
sanitized JSON field snapshot, request outcome and SHA-256 checksum
for each original-record pair, plus a summary. It **does not include**
API tokens, raw provider responses, or human approvals.

If either API responds 401, 403, 429 or cannot be reached, a row
remains UNAVAILABLE and must NOT be approved. Even when two fresh
original provider records are automatically consistent, the
`CONSISTENT_REQUIRES_REVIEW` label means independent inspection of
the provider evidence by a reviewer is STILL required. No code path
in this workflow writes cross-provider association approvals or
touches the SQLite database.

Ask Work to run the authenticated GitHub Action, download and inspect
the original provider evidence artifact, and report trustworthy
records, blocked records and precise API permission failures.
**Do not falsely certify independent source checks if only a
cached/local fixture record was available.**

## Useful navigation

- Latest backfill and summary:
  https://github.com/knight-bot/FootballAnalytics/actions/runs/42088790227
- Audit workflow:
  https://github.com/knight-bot/FootballAnalytics/actions/workflows/historical-audit.yml
- Review workflow:
  https://github.com/knight-bot/FootballAnalytics/actions/workflows/confirm-bulk-historical-links.yml
- Project methodology:
  https://github.com/knight-bot/FootballAnalytics/blob/main/HISTORICAL_DATA_EXPANSION.md

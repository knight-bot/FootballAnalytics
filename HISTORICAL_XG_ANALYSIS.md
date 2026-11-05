# Historical xG coverage and goals-versus-xG analysis

This feature uses **standard expected goals** from the locally imported
Sportmonks Football API v3 records, identified by **type ID 5304**. It
compares xG with recorded completed-match goals only for links that the
project's historical matching workflow currently marks **reviewed**.

This is descriptive historical research. It does not estimate scores
for upcoming matches or recommend wagers.

## Extended historical diagnostics

The existing **Historical xG Analysis** page now includes season
sample-balance checks, opponent other-game context, home/away xG
splits, cumulative reviewed-match goals-versus-xG trends, and
guarded descriptive correlation. These also appear in the
ChatGPT research export under **Part A.5**.

See [Advanced Retrospective Research](HISTORICAL_ADVANCED_RESEARCH.md)
for the methodology and interpretation limits.

## How to use

1. Open **Historical xG Analysis** in the Streamlit sidebar.
2. Inspect the imported Sportmonks coverage summary. It counts
   imported fixtures with two, one, or zero valid standard xG values.
   These counts refer to the locally stored sample, not the entire league.
3. Choose a competition, July–June historical season and team.
4. Inspect the number of completed football-data.org results, manually
   reviewed cross-provider links, and reviewed fixtures containing
   standard xG for **both sides**.
5. If completed reviewed xG exists, compare recorded goals, xG for,
   xG against, and goals-minus-xG across the *included sample*.
6. Export the source-ID-backed match evidence CSV if useful.
7. Open **ChatGPT Research Export** to get these same figures and
   source references under **Part A.3**.

## How provider joining is handled

- Sportmonks fixture IDs do **not** equal football-data.org match IDs.
- Only links currently flagged \`reviewed\` by
  \`historical_fixture_linkage.candidate_links\` can contribute a
  goal-versus-xG observation.
- Each such link was approved through a manual GitHub Actions
  confirmation, after an operator attested that the original provider
  records agree on the final score. This remains **operator-attested**,
  not independently machine-verified, because the older importer did
  not persist Sportmonks' final score.
- A link that has become \`stale_review\` or \`ambiguous\` will not
  contribute to xG totals.

## Which xG data are accepted

To compare a match's goals with xG, BOTH home and away sides must have
exactly one finite, nonnegative **type 5304** xG value each, attached
to the correct unique local Sportmonks participant ID for that side.

The following values are **excluded**, not estimated:

- No xG saved on one or both sides
- Duplicate xG measurements for a side
- Wrong/unknown participant ID or side
- Negative, infinite or nonnumeric xG values
- No currently valid reviewed link to the recorded match

A missing xG value is **unknown, not zero**. The exported research
report discloses how many reviewed fixtures were excluded.

## What the analysis calculates

For an included completed match, from the selected team's perspective:

- \`goals_minus_xg = goals_scored - standard_xg_for\`
- \`conceded_minus_xga = goals_conceded - opponent_standard_xg\`
- \`xg_difference = standard_xg_for - opponent_standard_xg\`
- \`actual_goal_difference = goals_scored - goals_conceded\`

Totals are sums only over included, reviewed, complete-xG matches.
They are **not** full-season estimates if only a small sample is
linked. This initial module deliberately does not calculate or rank
future-match probabilities.

Even a positive goals-minus-xG figure does not prove a team has a
persistent finishing ability: sample selection, chance quality models,
goalkeeper performance, opponent differences and random variation
all affect the historical relationship.

## Verification

Run <https://github.com/knight-bot/FootballAnalytics/actions/workflows/historical-audit.yml>
in GitHub Actions. The offline unit tests check:

- Unreviewed matches cannot be joined
- Operator-reviewed matches use the correct venue and score
- Source IDs remain available in exports
- Duplicate, negative, missing or incorrect-participant xG is rejected
- Stale reviewed links cannot contribute observations
- Competition, season, and completed-state boundaries are enforced

The code and tests can be checked offline without spending API calls.
A successful test suite is not proof of complete Sportmonks coverage
or independent confirmation of final scores.

## Further data-quality work

Import sufficient licensed historical data for selected competitions,
verify its source and retention terms, and review match associations
before drawing broad statistical conclusions. xG alone is not a
substitute for complete, high-quality historical records.

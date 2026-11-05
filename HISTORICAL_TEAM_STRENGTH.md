# Historical team-strength analysis (first analysis module)

The dashboard now includes **Historical Team Strength**. It calculates
retrospective goal-based attacking and defensive performance using
locally stored, valid, completed football-data.org match results.

No API token, external call, match forecasting, or wagering information
is required. The metrics are descriptive and are **not calibrated
probabilities or a validated forecasting model**.

## How to use

1. Refresh the Streamlit app and open **Historical Team Strength**.
2. Select a competition and a July–June historical season.
3. Inspect the observed league-wide home/away goal baselines.
4. Compare recorded teams in the table, or select one for a home/away
   breakdown and bar chart.
5. Export the historical comparison table to CSV.
6. Open **ChatGPT Research Export** to download a Markdown report that
   now includes the selected team's league-adjusted indices in Part A.2.

The team comparison uses all **valid completed results actually stored**
for that competition and season. It is **not** an official league table.

## Calculation methodology

Let \`N\` be the number of valid completed matches in the selected
competition and July–June window:

- Recorded league home scoring baseline
  \`H = total home goals / N\`
- Recorded league away scoring baseline
  \`A = total away goals / N\`
- Recorded league per-team scoring baseline
  \`L = (total home goals + total away goals) / (2*N)\`

For a particular team, calculate goals scored (\`GF\`) and conceded
(\`GA\`) across \`n\` matches in each scope:

| Scope | Attack baseline | Defense baseline |
|---|---|---|
| All matches | L | L |
| Home matches | H | A |
| Away matches | A | H |

Raw attacking index: \`(GF/n) / attack_baseline\`

Raw defensive index: \`(GA/n) / defense_baseline\`

A value of 1.00 means exactly the observed league scoring/conceding
rate for that venue. Higher attack numbers mean *more* goals scored
per match; lower defensive numbers mean *fewer* goals conceded per
match. These are goal ratios, not shot-quality or xG measures.

### Small-sample shrinkage

A naive ratio can look extreme after only a couple of matches, so
the interface also shows a baseline-shrunk version. With
\`k\` baseline-equivalent matches:

\`shrunk_index = (observed_goal_total + k*league_rate) / ((n+k)*league_rate)\`

The default \`k=5\` is a deliberately transparent heuristic, **not**
an optimized prior, validated estimator, or confidence interval.
The UI lets you change \`k\` to 0, 3, 5, or 10.

If \`n=0\` or the observed league baseline is zero, the index is
**undefined**, rather than zero. The UI flags very small team/venue
samples. Both the number of observations and the source match IDs
remain visible.

## Current limitations

- League baselines depend on the local sample. If updates or
  historical seasons are incomplete, comparisons can be biased.
- No opponent-strength, possession, shot quality, expected goals
  (xG), or lineup adjustments have been applied to these first
  goal-rate indices.
- Teams can have unequal recorded game counts; the comparison table
  is **not** an official ranking.
- Normalizing by the observed league average is an interpretable
  statistic, but it does not establish predictive accuracy.
- The current dataset includes dates grouped into the July–June window,
  not a source-verified official season identity.
- xG data from Sportmonks are **not** combined with goal ratios until
  source fixtures are individually verified and linked.

## Verification

Run **Audit Historical Football Data** under GitHub Actions. It now
executes the new \`test_historical_team_strength.py\` unit tests,
covering goal baselines, source filtering, home/away direction,
smoothing, invalid results, and zero baselines. This is an offline
code-quality check, not proof of validity against all real matches.

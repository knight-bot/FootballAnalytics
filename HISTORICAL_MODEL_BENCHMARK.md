# Retrospective historical goal-model benchmarking

This module is an educational **historical model-evaluation** tool.
It does **not** provide live match scores, betting advice, fixture picks,
odds, gameweek recommendations, or an API to estimate upcoming games.

## How to use

1. Open Streamlit -> **Historical Model Benchmark**.
2. Choose the competition, a historical held-out July–June season,
   training lookback (1–5 earlier seasons), and team smoothing strength.
3. Inspect the actual training and held-out fixture counts and dates.
4. Compare the MAE, RMSE, and mean signed residual on **already completed**
   held-out historical results.
5. Export the evaluation summary as Markdown and audit rows as CSV.
6. Repeat with other held-out seasons to see whether one result was a fluke.

Alternatively, run the **Audit Historical Football Data** workflow for
fully offline unit tests (the benchmarking UI requires Streamlit hosting).

## Data split and leakage controls

- Training includes only valid local \`matches\` table rows marked
  \`FINISHED\` in **earlier** July–June seasons of the same competition.
- Held-out matches come from a **later** July–June season.
- All model parameters are frozen before that test season starts.
- No held-out matches are used to fit, tune, or recalibrate parameters.
- A selected season that has not ended is only assessed on its
  already-stored finished matches and is flagged as incomplete.
- Fixture IDs are included in the Markdown report for source audits.
- The model intentionally does not join Sportmonks xG with these results:
  some imported Sportmonks fixtures are not yet operator-reviewed.

The same team may appear in both training and evaluation; this is
chronologically valid. Newly promoted or missing teams revert to the
training league's baseline for unknown home/away rates.

**Important:** The smoothing option is a *predefined* research parameter.
Choosing it based on the held-out results would leak test information
into model selection. Compare presets only as a sensitivity analysis;
for serious model selection, use separate earlier validation seasons.

## Two historical methods compared

**Baseline:** Training-period average home goals and average away goals
for each match in the held-out set.

**Team-adjusted method:** Start with the same home/away league goal
rates, multiplied by regularized historical team attacking and opponent
defensive factors for the relevant venue, all calculated from training
results. For an observed team/venue goal total \`G\` over \`n\` games,
a training league venue baseline \`b\`, and \`k\` smoothing matches:

\`relative_index = (G + k*b) / ((n+k)*b)\`

For example, home goal-rate estimation uses home-team home-attacking
strength and away-team away-conceding tendency, each relative to the
TRAINING league home-goal rate. This arithmetic is tested, but the
method has no guaranteed real-world forecasting skill.

**Scoring metrics:**
- \`MAE = mean(abs(estimated goals - actual goals))\`
- \`RMSE = sqrt(mean((estimated goals - actual goals)^2))\`
- \`Mean residual = mean(estimated goals - actual goals)\`

The unit is goals per team-match; every completed held-out game
contributes two observations, one for each team. Lower MAE/RMSE
indicates lower error **on that historical test sample only**.
A positive residual means average overestimation. A single holdout
cannot demonstrate stable performance or reliable uncertainty.

## Limitations and next evaluation milestones

- Seasonal sample completeness, data-provider reliability, and
  accurate source fixture IDs must be independently checked.
- Today's model does not use xG, possession, opponent scheduling
  adjustments, injury data, or actual lineup changes.
- One training/test split can be misleading: repeat the analysis
  over several separate held-out past seasons.
- Do not optimize smoothing or select the final model using the
  same held-out period you are reporting as an unbiased test.
- These are historical **goal estimation error comparisons**, not
  validated win/draw/loss probabilities or guaranteed outcomes.

If the more complex method performs worse than the league baseline,
that is valuable information. More parameters are not an automatic
improvement, regardless of how impressive a chart looks.

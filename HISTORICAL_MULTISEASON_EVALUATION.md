# Multi-season retrospective model evaluation

## Robustness extensions

The dashboard and Markdown report now include (a) a deterministic
match-paired 95% bootstrap sensitivity interval for the historical
MAE difference when at least 50 held-out matches exist, and
(b) a leave-one-season-out MAE-delta range when at least three held-out
seasons are eligible. Neither should be interpreted as future accuracy.
See [Statistical Historical Research](HISTORICAL_STATISTICAL_RESEARCH.md).

The **Multi-Season Historical Evaluation** Streamlit page expands the
single-holdout model audit into rolling-origin historical tests over
multiple completed seasons.

This is strictly an educational retrospective evaluation of goal-estimation
errors. It has no odds, wagering recommendations, live match modeling, or
future fixture output.

## Run it

1. Open the Streamlit **Multi-Season Historical Evaluation** page.
2. Select a competition (e.g. Premier League).
3. Choose the first and last held-out **completed July–June** seasons
   (at most eight consecutive seasons).
4. Leave **Earlier training seasons** at 2 and **Fixed team smoothing**
   at 5 for the first comparison.
5. Inspect the **per-season status table**. Excluded seasons show an
   explicit reason rather than appearing in the aggregate metrics.
6. Review each included season's MAE and the pooled historical MAE and RMSE.
7. Download the Markdown evaluation and CSV season-audit table.

The fixed minimum sample thresholds are **50 valid training matches** and
**30 valid test matches per fold**. A tiny or incomplete local database may
produce **no eligible folds**; that is correct behavior, not a reason to
fabricate sample records.

## Models compared

- **Training-league baseline:** Earlier seasons' recorded home/away goal
  averages.
- **Training-team adjustment:** Earlier seasons' recorded home/away team
  attacking and conceding indices, regularized toward the same baseline.

Each fold uses the existing \`run_historical_benchmark\` implementation.
A later held-out season is **never included in that fold's training data**.

Under *rolling-origin* evaluation, a season that was held out in an earlier
fold can legitimately be used to train a later fold, because its recorded
results were historically available before the later fold. This isn't
leakage. The source fixture IDs in **different held-out folds** must,
however, be distinct.

## How the pooled metrics work

Every completed match supplies two goal observations (home and away).
The pooled MAE, RMSE and signed mean error are computed from all the
included held-out observations, so longer test seasons contribute more.

Pooled MAE **is not** the simple arithmetic mean of the per-season MAEs
when the held-out seasons contain different numbers of matches.

The key comparison is:

\`delta = team-adjusted pooled MAE - league-baseline pooled MAE\`

Negative delta means the adjusted method had lower recorded goal error
**on the evaluated historical folds only**. It is not evidence of any
guaranteed performance on other seasons.

## Warnings

- A completed *calendar window* is not evidence that the database
  contains all games from that league season.
- Missing matches can bias both the fitted training averages and the
  held-out error estimates. Audit per-season coverage and provider
  consistency before treating the aggregate as representative.
- An entire historical season with too little recorded data is skipped.
  All skipped seasons and reasons remain in the report.
- Changes to smoothing, selected folds or minimum thresholds based on
  the displayed holdout scores amount to test-set selection. Proper
  model tuning needs a distinct, earlier validation period and a final,
  untouched evaluation period.
- More than one historical fold is better evidence than a single
  convenient example, but it still doesn't prove generalization.
- xG isn't evaluated here. Some Sportmonks advanced data has not been
  source-verified and linked to the goal-results dataset.

## Offline tests

Run <https://github.com/knight-bot/FootballAnalytics/actions/workflows/historical-audit.yml>
under GitHub Actions. Tests cover chronological separation, weighted
pooling, incomplete seasons, skipped low-coverage folds, data exclusions,
and source match IDs.

**Next technical milestone:** Audit historical fixture coverage and
evaluate the quality and completeness of *verified* xG records before
testing additional retrospective analytical methods.

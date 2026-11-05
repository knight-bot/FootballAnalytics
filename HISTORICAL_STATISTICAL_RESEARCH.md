# Statistical historical research, sample uncertainty and robustness

This development batch extends the **existing** Streamlit pages and
research exports. It uses locally stored football-data.org completed
results and the already operator-reviewed source-linked standard xG rows.

The goal is reliable retrospective football research. There is no
upcoming-fixture scoring, odds, wagering, or future-game selection.

## Where the additions appear

- **Historical xG Analysis** (existing page): section
  **Recorded-match statistical research**.
- **ChatGPT Research Export**: **Part A.6: Statistical Research and
  Sample Uncertainty**, alongside the existing historical evidence.
- **Multi-Season Historical Evaluation** (existing page):
  **Retrospective error robustness**.
- **Audit Historical Football Data** (existing GitHub Action):
  a new **Recorded historical league scoring trends** summary on every run.

No additional Streamlit pages were created.

## Recorded league outcome and scoring summaries

For one selected July-June date-derived season:

- Count *valid stored FINISHED* matches, excluding invalid rows.
- Calculate recorded home wins, draws, away wins, and frequencies.
- Calculate goals per completed match.
- Use Wilson-score **approximate 95% intervals** for each recorded
  binary outcome fraction. These assume independent observations;
  repeated clubs violate that assumption to some extent.
- When at least **30** matches are recorded, display a deterministic
  **600-resample match-level percentile bootstrap interval** for
  league goals per game. With fewer than 30 stored results, withhold
  the interval rather than showing a falsely precise number.

These are descriptive uncertainties for the stored sample, *not*
guarantees or confidence measures for upcoming football matches.

## Historical form: no focal-match leakage

The selected team has a match-by-match historical table with its
recorded completed results and opponent and home/away details.

For each **already completed** focal match, prior form uses only
the team's preceding **five matches in the same selected season
played on strictly earlier calendar dates**. The focal result,
same-date results and later games are excluded from its form row.
With fewer than five earlier stored games, the form statistics are
**unavailable**, not zero or extrapolated.

Each form row includes source match IDs. The report can therefore
be audited independently.

## Historical league scoring comparisons

The selected league's last four date-derived seasons are displayed
with counts of locally stored completed matches and recorded home,
away and total goals per match.

The newest season can still be underway. This is marked as an
incomplete *calendar interval*. Even for ended intervals, database
coverage cannot be certified without comparison to an official
schedule. Differences between years are observations, not causal
explanations.

At the time of the November 5, 2026 audit, the stored
Premier League records showed:

| Season | Locally stored valid matches | Goals per match |
|---|---:|---:|
| 2023/24 | 380 | 3.279 |
| 2024/25 | 380 | 2.934 |
| 2025/26 | 380 | 2.750 |
| 2026/27 | 90 | 2.700 |

Those figures are historical database summaries; they are not
official season completeness certifications. The latest value
is from an ongoing July-June calendar interval.

## xG uncertainty: only reviewed pairs

The optional xG sensitivity section uses ONLY match rows from
\`historical_xg_analysis.analyze_team_xg\`, after:

- A valid locally completed football-data.org result;
- A currently valid operator-reviewed cross-provider match association;
- One unambiguous Sportmonks standard xG value per side.

When at least **10 distinct eligible matches** are present, it
calculates a deterministic 600-resample percentile interval for
mean recorded goals-minus-xG per reviewed match. Otherwise the
interval is **unavailable**.

If zero reviewed matches are available, the code displays no xG
estimate or interval even when raw Sportmonks xG exists. Selecting
reviewed matches can introduce strong selection bias; bootstrap
uncertainty cannot correct that bias.

## Multi-season benchmark robustness

The multi-season historical goal-error benchmark now adds:

1. An **approximately 95% match-paired bootstrap interval** for the
   mean difference in historical MAE (team-adjusted minus baseline)
   when at least **50** distinct held-out completed matches are
   present. The resampling unit is a whole match, preserving home and
   away goal errors as a pair. Repeated teams make match independence
   imperfect.
2. A **leave-one-held-out-season-out sensitivity range** when at
   least **three included historical evaluation seasons** exist. This
   reveals whether the pooled historical comparison is sensitive
   to dropping one evaluation season.

Neither establishes future predictive reliability. The benchmark
still uses earlier historical seasons for training and distinct
later historical held-out seasons for retrospective comparison.

## Testing and reproducibility

The GitHub Actions historical audit runs syntax checks and the
offline unit suite, including deterministic resampling and source
leakage tests. Current successful audit:

https://github.com/knight-bot/FootballAnalytics/actions/workflows/historical-audit.yml

The scoring summary is produced by
\`historical_statistical_cli.py\` and appended to the same
GitHub Actions run summary.

### Remaining source dependency

The previously audited database contains 11 imported Sportmonks
fixtures with both sides' standard xG but **no currently approved
cross-provider links**. Therefore verified historical xG-to-goals
samples are still unavailable until the bounded source-score refresh
and manual association approvals are completed.

The statistics pipeline does not manufacture xG coverage in
the meantime; the goal-only historical research remains usable.

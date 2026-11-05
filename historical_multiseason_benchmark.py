"""Multi-season retrospective benchmarking of *completed* historical fixtures.

Runs the fixed, existing goal-error benchmark on successive held-out seasons.
Each fold trains only on preceding seasons; earlier holdouts can naturally
become training data for *later* folds. Never estimates future fixtures.

No provider joins, API requests, odds, or wagering functionality.
"""
from datetime import date, datetime, timezone
from random import Random
from historical_model_benchmark import (
    _metrics, run_historical_benchmark, DEFAULT_SHRINKAGE,
)
from historical_reports import _bounds, season_label

MAX_EVALUATION_SEASONS = 8
DEFAULT_MIN_TRAIN = 50
DEFAULT_MIN_TEST = 30

MIN_BOOTSTRAP_HELDOUT = 50
BOOTSTRAP_REPS = 600


def paired_heldout_delta_interval(rows, minimum=MIN_BOOTSTRAP_HELDOUT):
    """Match-paired historical goal-MAE improvement uncertainty, not a forecast.

    One complete held-out match is a resampling unit, so its home/away
    goal errors remain paired. This assumes matches are independent,
    which is imperfect with repeated teams and seasons.
    """
    if len(rows) < minimum:
        return None
    values = [
        row["adjusted_absolute_error"] - row["league_absolute_error"]
        for row in rows
    ]
    rng = Random(20261105)
    n = len(values)
    boot = sorted(
        sum(values[rng.randrange(n)] for _ in range(n)) / n
        for _ in range(BOOTSTRAP_REPS)
    )
    def pct(p):
        pos = (n_boot-1)*p
        i = int(pos)
        j = min(i+1, n_boot-1)
        return boot[i] + (boot[j]-boot[i])*(pos-i)
    n_boot = len(boot)
    return pct(.025), pct(.975)



def _positive_threshold(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def evaluate_historical_seasons(
    conn, competition, first_test_season, last_test_season,
    lookback_seasons=2, shrinkage=DEFAULT_SHRINKAGE,
    min_train=DEFAULT_MIN_TRAIN, min_test=DEFAULT_MIN_TEST,
    as_of_date=None,
):
    """Evaluate at most eight disjoint historical held-out July-June seasons.

    Incomplete calendar windows, absent data, and undersized samples are
    listed as skipped rather than silently included in pooled results.
    Every *included* held-out fixture appears exactly once across folds.
    """
    if (isinstance(first_test_season, bool)
            or isinstance(last_test_season, bool)
            or not isinstance(first_test_season, int)
            or not isinstance(last_test_season, int)):
        raise ValueError("Season start years must be integers.")
    # _bounds validates each 1900..2200 date-derived season start.
    _bounds(first_test_season)
    _bounds(last_test_season)
    if (first_test_season > last_test_season
            or last_test_season - first_test_season + 1
            > MAX_EVALUATION_SEASONS):
        raise ValueError(
            f"Choose 1-{MAX_EVALUATION_SEASONS} consecutive "
            "historical held-out seasons in chronological order."
        )
    _positive_threshold(min_train, "Minimum training match count")
    _positive_threshold(min_test, "Minimum held-out match count")
    if as_of_date is None:
        as_of_date = datetime.now(timezone.utc).date()
    if type(as_of_date) is not date:
        raise ValueError("as_of_date must be a date.")
    if not isinstance(competition, str) or not competition.strip():
        raise ValueError("A competition is required.")

    year_rows = []
    included_results = []
    heldout_rows_by_season = {}
    heldout_ids = set()
    for year in range(first_test_season, last_test_season + 1):
        _, exclusive_end = _bounds(year)
        item = {
            "year": year,
            "season": season_label(year),
            "status": "skipped",
            "reason": "",
            "train_matches": 0,
            "test_matches": 0,
            "unseen_team_matches": 0,
            "baseline_mae": None,
            "adjusted_mae": None,
            "baseline_rmse": None,
            "adjusted_rmse": None,
            "mae_delta": None,
        }
        if date.fromisoformat(exclusive_end) > as_of_date:
            item["reason"] = (
                "Calendar season has not ended. Excluded from complete-"
                "window retrospective evaluation."
            )
            year_rows.append(item)
            continue
        try:
            result = run_historical_benchmark(
                conn, competition, year,
                lookback_seasons=lookback_seasons,
                shrinkage=shrinkage,
            )
        except ValueError as exc:
            # Invalid numerical options and unknown tables are errors at the
            # configuration level, not missing-season data. Validate above
            # and restrict the catch to anticipated absence of coverage.
            message = str(exc)
            if not any(token in message for token in (
                "No valid completed earlier-season",
                "No valid completed held-out",
                "zero home or away goal baseline",
            )):
                raise
            item["reason"] = f"Unavailable or unsuitable historical data: {message}"
            year_rows.append(item)
            continue
        item["train_matches"] = result["train_matches"]
        item["test_matches"] = result["test_matches"]
        item["unseen_team_matches"] = result["unseen_team_matches"]
        if result["train_matches"] < min_train:
            item["reason"] = (
                f"Training coverage below threshold: "
                f"{result['train_matches']} < {min_train} completed matches."
            )
        elif result["test_matches"] < min_test:
            item["reason"] = (
                f"Test coverage below threshold: "
                f"{result['test_matches']} < {min_test} completed matches."
            )
        if item["reason"]:
            year_rows.append(item)
            continue
        test_ids = set(result["heldout_match_ids"])
        if len(test_ids) != result["test_matches"]:
            raise ValueError(
                "Duplicate source match IDs within a held-out season."
            )
        if test_ids & heldout_ids:
            raise ValueError(
                "Overlapping held-out source match IDs across seasons."
            )
        if test_ids & set(result["train_match_ids"]):
            raise ValueError(
                "Training and evaluation source match IDs overlap."
            )
        heldout_ids.update(test_ids)
        item.update({
            "status": "included",
            "reason": "Eligible completed historical window",
            "baseline_mae": result["league_baseline"]["mae"],
            "adjusted_mae": result["team_adjusted"]["mae"],
            "baseline_rmse": result["league_baseline"]["rmse"],
            "adjusted_rmse": result["team_adjusted"]["rmse"],
            "mae_delta": result["mae_change_adjusted_minus_baseline"],
        })
        year_rows.append(item)
        included_results.extend(result["rows"])
        heldout_rows_by_season[year] = result["rows"]

    pooled_baseline = (
        _metrics(included_results, "league") if included_results else None
    )
    pooled_adjusted = (
        _metrics(included_results, "adjusted") if included_results else None
    )
    included = [r for r in year_rows if r["status"] == "included"]
    skipped = [r for r in year_rows if r["status"] == "skipped"]
    # A negative delta means the adjusted model recorded lower MAE.
    difference = (
        pooled_adjusted["mae"] - pooled_baseline["mae"]
        if included_results else None
    )
    paired_interval = paired_heldout_delta_interval(included_results)
    leave_one_season_out = None
    if len(heldout_rows_by_season) >= 3:
        sensitivity_deltas = []
        for omitted in heldout_rows_by_season:
            kept = [
                row for year, rows in heldout_rows_by_season.items()
                if year != omitted for row in rows
            ]
            sensitivity_deltas.append(
                sum(row["adjusted_absolute_error"] -
                    row["league_absolute_error"] for row in kept)
                / len(kept)
            )
        leave_one_season_out = (
            min(sensitivity_deltas), max(sensitivity_deltas)
        )
    warnings = [
        "Rolling-origin folds use only preceding seasons for each fit. "
        "A season held out in an earlier fold may become training data "
        "for a later fold; that is not leakage.",
        "All included test windows have ended by the evaluation date. "
        "This does not establish that provider fixture coverage is complete.",
        "Hyperparameters and evaluation windows must not be chosen after "
        "inspecting results if a final unbiased test is intended.",
        "Pooled MAE and RMSE weight by goal observations, not by equal "
        "season averages. Only included historical folds contribute.",
        "The evaluation contains no live fixtures, betting rankings, "
        "future-game scores, or wagering recommendations.",
        "Match-paired resampling of absolute-goal error differences "
        "assumes game observations are independent; repeated teams "
        "and seasons make this imperfect. Intervals describe this "
        "historical holdout only and are NOT future accuracy guarantees.",
        "Leave-one-season-out differences assess sensitivity to a "
        "single included historical season, not causal model superiority.",
    ]
    if skipped:
        warnings.append(
            f"{len(skipped)} historical season(s) excluded from pooled "
            "results due to incomplete dates or inadequate coverage."
        )
    if paired_interval is None:
        warnings.append(
            f"Paired historical error interval withheld below "
            f"{MIN_BOOTSTRAP_HELDOUT} completed held-out matches."
        )
    if leave_one_season_out is None:
        warnings.append(
            "Leave-one-season-out sensitivity requires at least "
            "three eligible held-out years."
        )
    if len(included) < 2:
        warnings.append(
            "Fewer than two valid held-out seasons. This is not "
            "a multi-season demonstration of generalization."
        )
    return {
        "competition": competition,
        "first_test_season": first_test_season,
        "last_test_season": last_test_season,
        "lookback_seasons": lookback_seasons,
        "shrinkage": shrinkage,
        "min_train": min_train,
        "min_test": min_test,
        "as_of_date": as_of_date.isoformat(),
        "seasons_requested": len(year_rows),
        "seasons_included": len(included),
        "seasons_skipped": len(skipped),
        "heldout_matches": len(included_results),
        "heldout_match_ids": sorted(heldout_ids),
        "by_season": year_rows,
        "pooled_baseline": pooled_baseline,
        "pooled_adjusted": pooled_adjusted,
        "pooled_mae_delta": difference,
        "paired_mae_delta_bootstrap95": paired_interval,
        "leave_one_season_out_delta_range": leave_one_season_out,
        "warnings": warnings,
    }


def multiseason_markdown(summary):
    """Auditable text-only retrospective model-evaluation summary."""
    def fmt(x):
        return "N/A" if x is None else f"{x:.4f}"

    lines = [
        "# Multi-season retrospective football model evaluation",
        "",
        f"**Competition:** {summary['competition']}",
        f"**Historical test range:** "
        f"{season_label(summary['first_test_season'])} to "
        f"{season_label(summary['last_test_season'])}",
        f"**Evaluation date (UTC):** {summary['as_of_date']}",
        f"**Prior training seasons per fold:** "
        f"{summary['lookback_seasons']}",
        f"**Team shrinkage (training only):** "
        f"{summary['shrinkage']}",
        f"**Minimum train/test completed matches:** "
        f"{summary['min_train']} / {summary['min_test']}",
        f"**Included holdout seasons:** {summary['seasons_included']}",
        f"**Excluded holdout seasons:** {summary['seasons_skipped']}",
        f"**Total distinct held-out completed matches:** "
        f"{summary['heldout_matches']}",
        "",
        "## Historical season-by-season results",
        "",
        "| Season | Status | Train | Test | Baseline MAE | "
        "Team-adjusted MAE | Delta | Explanation |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in summary["by_season"]:
        safe_reason = r["reason"].replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {r['season']} | {r['status']} | "
            f"{r['train_matches']} | {r['test_matches']} | "
            f"{fmt(r['baseline_mae'])} | "
            f"{fmt(r['adjusted_mae'])} | "
            f"{fmt(r['mae_delta'])} | {safe_reason} |"
        )
    lines.extend([
        "",
        "## Pooled historical scoring errors",
        "",
        "| Method | Goal MAE | Goal RMSE | Mean goal residual |",
        "|---|---:|---:|---:|",
    ])
    for key, label in (
        ("pooled_baseline", "Earlier-season league baseline"),
        ("pooled_adjusted", "Earlier-season team-adjusted model"),
    ):
        metric = summary[key]
        lines.append(
            f"| {label} | {fmt(metric['mae'] if metric else None)} | "
            f"{fmt(metric['rmse'] if metric else None)} | "
            f"{fmt(metric['mean_error'] if metric else None)} |"
        )
    lines.extend([
        "",
        f"**Pooled MAE difference (adjusted minus baseline):** "
        f"{fmt(summary['pooled_mae_delta'])}. "
        "Negative indicates a smaller historical error for the "
        "team-adjusted method on included windows only.",
        "",
        f"**Paired held-out match bootstrap 95% interval for MAE delta:** "
        + (
            f"[{fmt(summary['paired_mae_delta_bootstrap95'][0])}, "
            f"{fmt(summary['paired_mae_delta_bootstrap95'][1])}]"
            if summary['paired_mae_delta_bootstrap95'] is not None
            else "Unavailable"
        ),
        "**Leave-one-held-out-season-out MAE delta range:** "
        + (
            f"[{fmt(summary['leave_one_season_out_delta_range'][0])}, "
            f"{fmt(summary['leave_one_season_out_delta_range'][1])}]"
            if summary['leave_one_season_out_delta_range'] is not None
            else "Unavailable"
        ),
        "",
        "**Distinct source match IDs (football-data.org):** "
        + (", ".join(str(x) for x in summary["heldout_match_ids"])
           or "None"),
        "",
        "## Interpretation warnings",
        "",
    ])
    lines.extend(f"- {text}" for text in summary["warnings"])
    lines.append("")
    return "\n".join(lines)

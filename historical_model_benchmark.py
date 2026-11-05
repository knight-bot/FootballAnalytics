"""Offline retrospective goal-model benchmark on completed historical seasons.

A held-out season is NEVER used for training, tuning, or selecting priors.
No future fixture input, live recommendations, odds or wagering output.
Models:
  (1) Training-period home/away league goal averages.
  (2) Training-period team home/away goal-rate ratios, shrunk toward 1.
Evaluate mean absolute error, root mean square error, and mean residual
on actual completed held-out matches. No external calls or extra packages.
"""
from collections import defaultdict
from datetime import datetime, timezone
from math import sqrt
from historical_audit import table_exists
from historical_reports import _bounds, season_label
from historical_team_strength import _valid_result

DEFAULT_SHRINKAGE = 5
MIN_TRAINING_SAMPLE_WARNING = 50
MIN_TEST_SAMPLE_WARNING = 30


def _match_rows(conn, competition, start, end):
    rows = conn.execute(
        "SELECT match_id, date, home_team, away_team, home_goals, away_goals "
        "FROM matches WHERE status='FINISHED' AND competition=? "
        "AND date>=? AND date<? ORDER BY date, match_id",
        (competition, start, end),
    ).fetchall()
    games, invalid = [], []
    for row in rows:
        if not _valid_result(row):
            invalid.append(row[0])
            continue
        match_id, kickoff, home, away, hg, ag = row
        games.append({
            "match_id": int(match_id), "date": kickoff[:10],
            "home": home.strip(), "away": away.strip(),
            "home_goals": int(hg), "away_goals": int(ag),
        })
    return games, invalid


def _team_rates(training, home_avg, away_avg, shrinkage):
    counts = defaultdict(lambda: {
        "home_n": 0, "away_n": 0, "home_gf": 0, "home_ga": 0,
        "away_gf": 0, "away_ga": 0,
    })
    for game in training:
        home = counts[game["home"]]
        away = counts[game["away"]]
        home["home_n"] += 1
        home["home_gf"] += game["home_goals"]
        home["home_ga"] += game["away_goals"]
        away["away_n"] += 1
        away["away_gf"] += game["away_goals"]
        away["away_ga"] += game["home_goals"]
    def ratio(team, venue, which, baseline):
        group = counts.get(team)
        if not group:
            return 1.0
        n = group[f"{venue}_n"]
        if not n:
            return 1.0
        goals = group[f"{venue}_{which}"]
        return (goals + shrinkage * baseline) / (
            (n + shrinkage) * baseline
        )
    return counts, ratio


def _metrics(rows, prefix):
    errors = []
    for row in rows:
        for side in ("home", "away"):
            errors.append(
                row[f"{prefix}_{side}_estimated"]
                - row[f"{side}_goals"]
            )
    n = len(errors)
    return {
        "mae": sum(abs(e) for e in errors)/n,
        "rmse": sqrt(sum(e*e for e in errors)/n),
        "mean_error": sum(errors)/n,
        "team_goal_observations": n,
    }


def run_historical_benchmark(
    conn, competition, test_season, lookback_seasons=2,
    shrinkage=DEFAULT_SHRINKAGE,
):
    """Compare training-only models against one strictly later held-out season.

    This function intentionally offers NO ability to generate a model value
    for a future match or pair of arbitrary teams.
    """
    if not table_exists(conn, "matches"):
        raise ValueError("No locally recorded match-results table exists.")
    if not isinstance(competition, str) or not competition.strip():
        raise ValueError("Choose a valid competition.")
    if isinstance(test_season, bool) or not isinstance(test_season, int):
        raise ValueError("The held-out July–June season must be an integer.")
    if (isinstance(lookback_seasons, bool) or
            not isinstance(lookback_seasons, int) or
            lookback_seasons < 1 or lookback_seasons > 5):
        raise ValueError("Lookback must be one to five earlier seasons.")
    if (isinstance(shrinkage, bool) or
            not isinstance(shrinkage, int) or shrinkage < 1
            or shrinkage > 20):
        raise ValueError("Shrinkage must be 1 to 20 matches.")

    test_start, test_end = _bounds(test_season)
    train_start, _ = _bounds(test_season - lookback_seasons)
    now = datetime.now(timezone.utc).date()
    if datetime.fromisoformat(test_start).date() > now:
        raise ValueError("The held-out season cannot start in the future.")

    train, invalid_train = _match_rows(
        conn, competition, train_start, test_start
    )
    test, invalid_test = _match_rows(
        conn, competition, test_start, test_end
    )
    if not train:
        raise ValueError(
            "No valid completed earlier-season matches exist to train on. "
            "Choose a later held-out season or increase lookback."
        )
    if not test:
        raise ValueError(
            "No valid completed held-out matches exist for this selection."
        )
    if train[-1]["date"] >= test[0]["date"]:
        raise AssertionError("Chronological train/test separation failed.")
    # No results are fitted on held-out fixtures, even for same-season
    # earlier dates; model parameters stay frozen across the test period.
    home_avg = sum(g["home_goals"] for g in train) / len(train)
    away_avg = sum(g["away_goals"] for g in train) / len(train)
    if home_avg <= 0 or away_avg <= 0:
        raise ValueError(
            "Training sample has a zero home or away goal baseline; "
            "team ratios cannot be evaluated safely."
        )
    teams, ratio = _team_rates(train, home_avg, away_avg, shrinkage)
    results = []
    unseen_matches = 0
    for g in test:
        unseen = g["home"] not in teams or g["away"] not in teams
        unseen_matches += int(unseen)
        h_est = (
            home_avg *
            ratio(g["home"], "home", "gf", home_avg) *
            ratio(g["away"], "away", "ga", home_avg)
        )
        a_est = (
            away_avg *
            ratio(g["away"], "away", "gf", away_avg) *
            ratio(g["home"], "home", "ga", away_avg)
        )
        results.append({
            "match_id": g["match_id"],
            "date": g["date"],
            "home": g["home"],
            "away": g["away"],
            "home_goals": g["home_goals"],
            "away_goals": g["away_goals"],
            "unseen_team": unseen,
            "league_home_estimated": home_avg,
            "league_away_estimated": away_avg,
            "adjusted_home_estimated": h_est,
            "adjusted_away_estimated": a_est,
            "league_absolute_error": (
                abs(home_avg-g["home_goals"])
                + abs(away_avg-g["away_goals"])
            ) / 2,
            "adjusted_absolute_error": (
                abs(h_est-g["home_goals"])
                + abs(a_est-g["away_goals"])
            ) / 2,
        })
    baseline = _metrics(results, "league")
    adjusted = _metrics(results, "adjusted")
    delta = adjusted["mae"] - baseline["mae"]
    warnings = [
        "Only completed held-out historical results are evaluated. "
        "No live or future-match results are generated.",
        "Training includes ONLY earlier July–June seasons. "
        "Parameters are frozen before the held-out season starts.",
        "This is a single chronological holdout, not independent proof "
        "of generalizability. Evaluate multiple later seasons.",
        "No xG, team transfers, coaching changes, schedule strength, "
        "injuries, or lineup information was included.",
    ]
    if len(train) < MIN_TRAINING_SAMPLE_WARNING:
        warnings.append(
            f"Only {len(train)} training matches. The fitted averages "
            "are especially unstable."
        )
    if len(test) < MIN_TEST_SAMPLE_WARNING:
        warnings.append(
            f"Only {len(test)} held-out completed matches. "
            "Do not treat this as full-season performance."
        )
    if test_end > now.isoformat():
        warnings.append(
            "The selected July–June season has not ended. "
            "Only its already-recorded completed games were evaluated."
        )
    if unseen_matches:
        warnings.append(
            f"{unseen_matches} held-out matches involve a team not "
            "seen in the training data; its missing venue ratios default "
            "to the league baseline."
        )
    if invalid_train or invalid_test:
        warnings.append(
            f"Excluded {len(invalid_train)} invalid training rows and "
            f"{len(invalid_test)} invalid held-out rows."
        )
    return {
        "competition": competition,
        "train_window": (train_start, test_start),
        "test_window": (test_start, test_end),
        "test_season": season_label(test_season),
        "train_matches": len(train),
        "test_matches": len(test),
        "train_match_ids": [g["match_id"] for g in train],
        "heldout_match_ids": [g["match_id"] for g in test],
        "excluded_train_ids": invalid_train,
        "excluded_test_ids": invalid_test,
        "trained_team_count": len(teams),
        "unseen_team_matches": unseen_matches,
        "league_home_baseline": home_avg,
        "league_away_baseline": away_avg,
        "shrinkage_matches": shrinkage,
        "league_baseline": baseline,
        "team_adjusted": adjusted,
        "mae_change_adjusted_minus_baseline": delta,
        "rows": results,
        "warnings": warnings,
    }


def benchmark_markdown(result):
    def num(x):
        return f"{x:.3f}"
    return "\n".join([
        "# Retrospective Historical Goal-Model Benchmark",
        "",
        "**Purpose:** Evaluate completed historical matches, not live "
        "match outcomes or wagering decisions.",
        f"**Competition:** {result['competition']}",
        f"**Earlier training window:** {result['train_window'][0]} "
        f"to before {result['train_window'][1]}",
        f"**Held-out season:** {result['test_season']}",
        f"**Training matches:** {result['train_matches']}",
        f"**Held-out matches:** {result['test_matches']}",
        f"**Baseline home/away training goal rates:** "
        f"{num(result['league_home_baseline'])} / "
        f"{num(result['league_away_baseline'])}",
        f"**Team ratio shrinkage:** {result['shrinkage_matches']} "
        "baseline-equivalent matches",
        "",
        "| Historical model | Goal MAE (lower is better) | "
        "Goal RMSE (lower is better) | Mean residual (estimate - actual) |",
        "|---|---:|---:|---:|",
        f"| Training league home/away means | "
        f"{num(result['league_baseline']['mae'])} | "
        f"{num(result['league_baseline']['rmse'])} | "
        f"{num(result['league_baseline']['mean_error'])} |",
        f"| Training-only team home/away adjustment | "
        f"{num(result['team_adjusted']['mae'])} | "
        f"{num(result['team_adjusted']['rmse'])} | "
        f"{num(result['team_adjusted']['mean_error'])} |",
        "",
        f"**Difference in MAE (adjusted minus baseline):** "
        f"{num(result['mae_change_adjusted_minus_baseline'])} "
        "(negative means lower error on this holdout).",
        "",
        "**Method:** Historical home and away goal-rate ratios fitted "
        "only on training matches; held-out results were never used "
        "in fitting or selecting hyperparameters.",
        "",
        f"**Historical training source match IDs:** "
        + ", ".join(str(x) for x in result["train_match_ids"]),
        "",
        f"**Held-out source match IDs:** "
        + ", ".join(str(x) for x in result["heldout_match_ids"]),
        "",
        "## Limitations",
        "",
    ] + [f"- {item}" for item in result["warnings"]]) + "\n"

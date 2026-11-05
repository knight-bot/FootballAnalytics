"""Conservative, read-only historical cross-provider match candidate matching.

Older imported Sportmonks records do not have persisted final scores.
Newer/explicitly refreshed regular-time fixtures may have strict CURRENT
score evidence. Score agreement can corroborate, but can NEVER automatically
approve a provider association. Conflicting source scores block review.
Confirmation occurs in a separate, explicit operator workflow.
No network, odds, future fixtures, or writes occur in this module.
"""
from collections import Counter
from datetime import datetime, timezone
import re
import unicodedata

from historical_score_evidence import stored_final_scores, compare_stored_score

FINISHED_STATES = (5, 7, 8)
MAX_TIME_DIFFERENCE_MINUTES = 120
SPORTMONKS_LEAGUES = {8: "Premier League"}
LINK_TABLE = "reviewed_historical_fixture_links"

# Explicit narrow aliases for provider spelling differences. No fuzzy
# substring matching: "United" or "City" alone would be dangerously broad.
TEAM_ALIASES = {
    "brighton hove albion": "brighton and hove albion",
    "newcastle": "newcastle united",
    "nottingham forest": "nottingham forest",
    "nottm forest": "nottingham forest",
    "man utd": "manchester united",
    "man city": "manchester city",
    "spurs": "tottenham hotspur",
    "tottenham": "tottenham hotspur",
    "wolves": "wolverhampton wanderers",
    "west ham": "west ham united",
}


def _exists(conn, table):
    # Each table argument is an internal constant, not user input.
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def normalize_team(value):
    if not isinstance(value, str) or not value.strip():
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = " ".join(text.split())
    # Strip common *whole* prefix/suffix club designators only.
    text = re.sub(r"^(afc|fc) ", "", text)
    text = re.sub(r" (football club|afc|fc)$", "", text)
    return TEAM_ALIASES.get(text, text)


def parse_utc(timestamp):
    if not isinstance(timestamp, str) or not timestamp.strip():
        return None
    try:
        parsed = datetime.fromisoformat(
            timestamp.strip().replace("Z", "+00:00")
        )
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # Sportmonks stored timestamps are UTC in the import workflow.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _get_reviewed(conn):
    if not _exists(conn, LINK_TABLE):
        return {}
    return {
        int(sid): {
            "match_id": int(fid),
            "reviewed_by": actor,
            "reviewed_at": date,
        }
        for sid, fid, actor, date in conn.execute(
            f"SELECT sportmonks_fixture_id, football_data_match_id, "
            f"reviewed_by, reviewed_at FROM {LINK_TABLE}"
        )
    }


def candidate_links(conn):
    """Show potential *completed historical* one-to-one fixture relationships.

    Every row has status: review_candidate, ambiguous, unmatched,
    reviewed or stale_review. A reviewed link is only valid while current
    local records still uniquely support the same underlying candidate.
    """
    if not all(_exists(conn, name) for name in (
        "matches", "sportmonks_historical_fixtures",
        "sportmonks_historical_teams",
    )):
        return []

    results = []
    for match_id, kickoff, competition, home, away, hg, ag in conn.execute(
        "SELECT match_id, date, competition, home_team, away_team, "
        "home_goals, away_goals FROM matches "
        "WHERE status='FINISHED' AND home_goals IS NOT NULL "
        "AND away_goals IS NOT NULL AND home_goals>=0 AND away_goals>=0"
    ):
        stamp = parse_utc(kickoff)
        home_norm, away_norm = normalize_team(home), normalize_team(away)
        if stamp and home_norm and away_norm and home_norm != away_norm:
            results.append({
                "match_id": int(match_id), "kickoff": stamp,
                "competition": competition,
                "home": home, "away": away,
                "home_norm": home_norm, "away_norm": away_norm,
                "score": f"{hg}-{ag}",
                "home_goals": hg, "away_goals": ag,
            })

    members = {}
    for fixture_id, name, location in conn.execute(
        "SELECT fixture_id, name, location "
        "FROM sportmonks_historical_teams"
    ):
        members.setdefault(int(fixture_id), {}).setdefault(
            location, []
        ).append(name)

    source_scores = stored_final_scores(conn)
    provisional = []
    for fixture_id, name, date, league_id, state_id in conn.execute(
        "SELECT fixture_id, name, match_date, league_id, state_id "
        "FROM sportmonks_historical_fixtures "
        "ORDER BY match_date DESC, fixture_id DESC"
    ):
        sid = int(fixture_id)
        teams = members.get(sid, {})
        home_names, away_names = teams.get("home", []), teams.get("away", [])
        home_name = home_names[0] if len(home_names) == 1 else ""
        away_name = away_names[0] if len(away_names) == 1 else ""
        stamp = parse_utc(date)
        row = {
            "sportmonks_id": sid,
            "sportmonks_match": name or f"Fixture {sid}",
            "sportmonks_date": date or "",
            "sportmonks_home": home_name,
            "sportmonks_away": away_name,
            "match_id": None,
            "result_match": "",
            "result_date": "",
            "result_score": "",
            "sportmonks_stored_final_score": (
                f"{source_scores[sid][0]}-{source_scores[sid][1]}"
                if sid in source_scores else ""
            ),
            "score_comparison": "unavailable",
            "kickoff_difference_minutes": None,
            "status": "unmatched",
            "reason": "",
        }
        if league_id not in SPORTMONKS_LEAGUES:
            row["reason"] = "Unsupported Sportmonks league; no cross-league mapping."
            provisional.append((row, []))
            continue
        if state_id not in FINISHED_STATES or not stamp:
            row["reason"] = "Fixture is not completed or has no valid UTC kickoff."
            provisional.append((row, []))
            continue
        home_norm, away_norm = normalize_team(home_name), normalize_team(away_name)
        if not home_norm or not away_norm or home_norm == away_norm:
            row["reason"] = "Missing or ambiguous home/away participant names."
            provisional.append((row, []))
            continue
        options = []
        for result in results:
            if result["competition"] != SPORTMONKS_LEAGUES[league_id]:
                continue
            if (result["home_norm"] != home_norm
                    or result["away_norm"] != away_norm):
                continue
            delta = abs((stamp - result["kickoff"]).total_seconds()) / 60
            if delta <= MAX_TIME_DIFFERENCE_MINUTES:
                options.append((delta, result))
        options.sort(key=lambda value: (value[0], value[1]["match_id"]))
        provisional.append((row, options))

    usage = Counter(
        candidate["match_id"]
        for _, options in provisional
        for _, candidate in options
    )
    reviewed = _get_reviewed(conn)
    rows = []
    for row, options in provisional:
        reviewed_link = reviewed.get(row["sportmonks_id"])
        if options:
            delta, result = options[0]
            row["match_id"] = result["match_id"]
            row["result_match"] = f"{result['home']} vs {result['away']}"
            row["result_date"] = result["kickoff"].isoformat()
            row["result_score"] = result["score"]
            row["kickoff_difference_minutes"] = round(delta, 1)
            row["score_comparison"] = compare_stored_score(
                source_scores.get(sid),
                result["home_goals"], result["away_goals"],
            )
            if len(options) != 1 or usage[result["match_id"]] != 1:
                row["status"] = "ambiguous"
                row["reason"] = (
                    "More than one plausible record exists. "
                    "Do not confirm a link."
                )
            elif row["score_comparison"] == "mismatch":
                row["status"] = "score_mismatch"
                row["reason"] = (
                    "BLOCKED: stored Sportmonks CURRENT final score conflicts "
                    "with football-data.org final result. Investigate "
                    "source records; do not approve this association."
                )
            else:
                row["status"] = "review_candidate"
                row["reason"] = (
                    "Teams, league and kickoff agree. "
                    + (
                        "Stored Sportmonks CURRENT score also agrees, "
                        "but manually compare source scores before approval."
                        if row["score_comparison"] == "agrees"
                        else "Sportmonks final score was not stored: "
                        "manually compare source scores."
                    )
                )
        elif not row["reason"]:
            row["reason"] = (
                "No completed Premier League result with both teams and "
                "a kickoff within two hours."
            )
        if reviewed_link:
            if (row["status"] == "review_candidate"
                    and row["match_id"] == reviewed_link["match_id"]):
                row["status"] = "reviewed"
                row["reason"] = (
                    "Manually reviewed via the GitHub Action by "
                    f"{reviewed_link['reviewed_by']} on "
                    f"{reviewed_link['reviewed_at']}. "
                    "Score confirmation was operator-attested."
                )
            else:
                row["status"] = "stale_review"
                row["reason"] = (
                    "A stored review no longer agrees with a unique "
                    "candidate. Treat this link as unverified."
                )
        rows.append(row)
    return rows


def reviewed_links_for_team(conn, competition, year, team):
    """Read only *currently valid reviewed* links for a recorded team."""
    start, end = f"{year}-07-01", f"{year + 1}-07-01"
    eligible = {
        int(match_id)
        for (match_id,) in conn.execute(
            "SELECT match_id FROM matches "
            "WHERE status='FINISHED' AND competition=? AND "
            "date>=? AND date<? AND (home_team=? OR away_team=?)",
            (competition, start, end, team, team),
        )
    }
    return [
        row for row in candidate_links(conn)
        if row["status"] == "reviewed" and row["match_id"] in eligible
    ]


def initialize_link_table(conn):
    """Only used by the explicit review GitHub Action, never the web page."""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {LINK_TABLE} (
            sportmonks_fixture_id INTEGER PRIMARY KEY,
            football_data_match_id INTEGER NOT NULL UNIQUE,
            reviewed_by TEXT NOT NULL,
            reviewed_at TEXT NOT NULL
        )
    """)

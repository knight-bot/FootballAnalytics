"""Read-only, authenticated historical original-provider evidence collection.

Run only in GitHub Actions with pre-existing provider secrets. Produces
sanitized per-match source snapshots and conservative consistency outcomes.
It NEVER writes to football.db or confirms a fixture association.
"""
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests

from historical_fixture_linkage import candidate_links, normalize_team, parse_utc
from historical_score_evidence import extract_current_final_score
from sportmonks_historical_import import DB_PATH

SPORTMONKS = "https://api.sportmonks.com/v3/football/fixtures"
FOOTBALL_DATA = "https://api.football-data.org/v4/matches"
MAX_PAIRS = 10
OUT_DIR = Path("historical_provider_evidence")


def selected_candidates(conn, date_start, date_end, limit=MAX_PAIRS):
    if not (isinstance(date_start, str) and isinstance(date_end, str)
            and len(date_start) == 10 and len(date_end) == 10
            and date_start <= date_end):
        raise ValueError("Use a valid ordered ISO date window.")
    if type(limit) is not int or not 1 <= limit <= MAX_PAIRS:
        raise ValueError("Only 1-10 historical candidates can be checked.")
    rows = [
        row for row in candidate_links(conn)
        if row["status"] == "review_candidate"
        and row["score_comparison"] == "agrees"
        and date_start <= str(row["sportmonks_date"])[:10] <= date_end
        and type(row["match_id"]) is int
    ]
    return sorted(
        rows, key=lambda r: (r["sportmonks_date"], r["sportmonks_id"])
    )[:limit]


def _original_get(session, url, headers, params=None):
    """No arbitrary provider text/headers or credential-bearing URLs logged."""
    try:
        response = session.get(
            url, headers=headers, params=params, timeout=25,
        )
    except requests.RequestException:
        return None, {"status": "NETWORK_ERROR", "http_status": None}
    code = response.status_code
    if code != 200:
        return None, {"status": "HTTP_ERROR", "http_status": code}
    try:
        data = response.json()
    except ValueError:
        return None, {"status": "INVALID_JSON", "http_status": code}
    return data, {"status": "RECEIVED", "http_status": code}


def _sportmonks_fields(payload, expected_id):
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or type(data.get("id")) is not int:
        return None
    if data["id"] != expected_id:
        return None
    side = {}
    for member in data.get("participants", []):
        if not isinstance(member, dict):
            continue
        meta = member.get("meta")
        loc = meta.get("location") if isinstance(meta, dict) else None
        if loc in ("home", "away"):
            side.setdefault(loc, []).append(member.get("name"))
    if any(len(side.get(k, [])) != 1 for k in ("home", "away")):
        return None
    score = extract_current_final_score(data)
    return {
        "id": data["id"], "league_id": data.get("league_id"),
        "state_id": data.get("state_id"),
        "kickoff_utc": data.get("starting_at"),
        "home": side["home"][0], "away": side["away"][0],
        "final_score": list(score) if score is not None else None,
    }


def _football_data_fields(payload, expected_id):
    if not isinstance(payload, dict) or payload.get("id") != expected_id:
        return None
    teams = payload.get("homeTeam"), payload.get("awayTeam")
    score = payload.get("score")
    score = score if isinstance(score, dict) else {}
    full = score.get("fullTime")
    full = full if isinstance(full, dict) else {}
    goals = full.get("home"), full.get("away")
    return {
        "id": payload["id"],
        "competition": (
            payload.get("competition", {}).get("code")
            if isinstance(payload.get("competition"), dict) else None
        ),
        "status": payload.get("status"),
        "duration": score.get("duration"),
        "kickoff_utc": payload.get("utcDate"),
        "home": teams[0].get("name") if isinstance(teams[0], dict) else None,
        "away": teams[1].get("name") if isinstance(teams[1], dict) else None,
        "final_score": (
            list(goals) if all(type(x) is int and x >= 0 for x in goals)
            else None
        ),
    }


def compare_original_evidence(candidate, sm, fd):
    """Original-provider evidence may pass automatic checks, NOT approval."""
    if sm is None or fd is None:
        return "UNAVAILABLE", "At least one provider returned no usable record."
    if (sm["league_id"] != 8 or sm["state_id"] != 5
            or fd["competition"] != "PL" or fd["status"] != "FINISHED"
            or fd["duration"] not in (None, "REGULAR")):
        return "CONFLICT", "League or completed regular-time status differs."
    first = parse_utc(sm["kickoff_utc"])
    second = parse_utc(fd["kickoff_utc"])
    local = parse_utc(candidate["result_date"])
    if not first or not second or not local:
        return "UNAVAILABLE", "One or more original kickoff timestamps missing."
    if abs((first-second).total_seconds()) > 120 or (
            abs((second-local).total_seconds()) > 120):
        return "CONFLICT", "Original kickoff timestamps disagree."
    for side in ("home", "away"):
        name_a = normalize_team(sm[side])
        name_b = normalize_team(fd[side])
        if not name_a or not name_b:
            return "UNAVAILABLE", "Original provider team name unavailable."
        if name_a != name_b:
            return "CONFLICT", "Original home/away team identities disagree."
        stored = (
            candidate["sportmonks_home"] if side == "home"
            else candidate["sportmonks_away"]
        )
        if normalize_team(stored) != name_a:
            return "CONFLICT", "Original team identity differs from local candidate."
    if sm["final_score"] is None or fd["final_score"] is None:
        return "UNAVAILABLE", "Original completed final scores unavailable."
    scores = (
        "-".join(map(str, sm["final_score"])),
        "-".join(map(str, fd["final_score"])),
    )
    if (scores[0] != scores[1]
            or scores[0] != candidate["result_score"]
            or scores[0] != candidate["sportmonks_stored_final_score"]):
        return "CONFLICT", "Original and locally stored final scores disagree."
    return (
        "CONSISTENT_REQUIRES_REVIEW",
        "Fresh authenticated original records agree on identities, "
        "kickoff and score. Manual evidence review still required.",
    )


def collect_evidence(session, conn, sportmonks_token, football_token,
                     start, end, limit=MAX_PAIRS):
    entries = []
    candidates = selected_candidates(conn, start, end, limit)
    blocked_provider = set()
    for candidate in candidates:
        sid, mid = candidate["sportmonks_id"], candidate["match_id"]
        urls = (
            f"{SPORTMONKS}/{sid}",
            f"{FOOTBALL_DATA}/{mid}",
        )
        checks = []
        for provider, url, headers, params in (
            ("sportmonks", urls[0], {
                "Authorization": sportmonks_token,
                "Accept": "application/json",
            }, {"include": "participants;scores"}),
            ("football_data", urls[1], {
                "X-Auth-Token": football_token,
                "Accept": "application/json",
            }, None),
        ):
            if provider in blocked_provider:
                payload, transport = None, {
                    "status": "SKIPPED_AFTER_AUTH_FAILURE",
                    "http_status": None,
                }
            else:
                payload, transport = _original_get(
                    session, url, headers=headers, params=params,
                )
            if transport["http_status"] in (401, 403):
                blocked_provider.add(provider)
            parser = (
                _sportmonks_fields
                if provider == "sportmonks" else _football_data_fields
            )
            values = parser(payload, sid if provider == "sportmonks" else mid) if payload else None
            checks.append({
                "provider": provider,
                "record_url": url,
                "queried_at_utc": datetime.now(timezone.utc).isoformat(),
                **transport,
                "original_fields": values,
            })
        outcome, reason = compare_original_evidence(
            candidate,
            checks[0]["original_fields"], checks[1]["original_fields"],
        )
        entry = {
            "sportmonks_id": sid,
            "football_data_match_id": mid,
            "stored_home": candidate["sportmonks_home"],
            "stored_away": candidate["sportmonks_away"],
            "stored_utc": candidate["sportmonks_date"],
            "stored_score": candidate["result_score"],
            "provider_evidence": checks,
            "automatic_consistency": outcome,
            "reason": reason,
            "operator_approved": False,
        }
        # Hash the precise sanitized evidence record, not a credential or token.
        digest_text = json.dumps(
            entry, sort_keys=True, ensure_ascii=True,
        ).encode("utf-8")
        entry["sanitized_evidence_sha256"] = hashlib.sha256(
            digest_text
        ).hexdigest()
        entries.append(entry)
    return entries


def evidence_summary(entries):
    statuses = {}
    for entry in entries:
        key = entry["automatic_consistency"]
        statuses[key] = statuses.get(key, 0) + 1
    lines = [
        "## Independent original-provider evidence collection",
        "",
        f"**Candidate pairs inspected:** {len(entries)}",
        f"**Original records consistent, pending manual review:** "
        f"{statuses.get('CONSISTENT_REQUIRES_REVIEW',0)}",
        f"**Conflicts:** {statuses.get('CONFLICT',0)}",
        f"**Unavailable original evidence:** {statuses.get('UNAVAILABLE',0)}",
        "**Approved:** 0 (approval intentionally not implemented)",
        "",
        "| Sportmonks ID | football-data.org ID | Automated finding |",
        "|---:|---:|---|",
    ]
    for item in entries:
        lines.append(
            f"| {item['sportmonks_id']} | {item['football_data_match_id']} | "
            f"{item['automatic_consistency']} |"
        )
    lines.extend([
        "",
        "Results are from authenticated original provider endpoints accessed "
        "by GitHub Actions. They require independent manual inspection "
        "of the evidence artifact before any reviewed-link approval.",
        "Provider tokens and raw responses are NEVER included in the artifact.",
    ])
    return "\n".join(lines) + "\n"


def main():
    sm = os.getenv("SPORTMONKS_API_TOKEN", "")
    fd = os.getenv("FOOTBALL_API_TOKEN", "")
    if not sm or not fd:
        raise ValueError(
            "Both existing GitHub Actions provider token secrets are required."
        )
    start = os.getenv("EVIDENCE_START_DATE", "2025-09-12")
    end = os.getenv("EVIDENCE_END_DATE", "2025-09-25")
    limit = int(os.getenv("EVIDENCE_MAX_PAIRS", "10"))
    with sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True) as conn:
        with requests.Session() as session:
            entries = collect_evidence(
                session, conn, sm, fd, start, end, limit,
            )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR/"original_provider_evidence.json").write_text(
        json.dumps(entries, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    summary = evidence_summary(entries)
    (OUT_DIR/"README.md").write_text(summary, encoding="utf-8")
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a",
                  encoding="utf-8") as f:
            f.write("\n"+summary+"\n")


if __name__ == "__main__":
    main()

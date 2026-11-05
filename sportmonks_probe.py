"""Check which historical fixture fields a Sportmonks account can read.

This diagnostic does not store credentials or publish match data.
Use it to verify API access before adding a separate historical dataset.
"""
import os
import sys

import requests


def main():
    token = os.environ.get("SPORTMONKS_API_TOKEN", "").strip()
    fixture_id = os.environ.get("SPORTMONKS_FIXTURE_ID", "19872618").strip()

    if not token:
        sys.exit("Missing SPORTMONKS_API_TOKEN GitHub Actions secret.")
    if not fixture_id.isdecimal():
        sys.exit("Fixture ID must be numeric.")

    url = f"https://api.sportmonks.com/v3/football/fixtures/{fixture_id}"

    # Avoid attaching the token to the URL. Never print the token.
    # Start with post-match statistical fields, not betting or news fields.
    params = {"include": "statistics;participants;scores;xGFixture;pressure"}
    headers = {
        "Authorization": token,
        "Accept": "application/json",
    }

    print("Testing Sportmonks fixture endpoint")
    print("Fixture ID:", fixture_id)

    try:
        response = requests.get(
            url, params=params, headers=headers, timeout=30
        )
    except requests.RequestException as exc:
        sys.exit(f"Connection failed: {type(exc).__name__}")

    print("HTTP status:", response.status_code)

    if not response.ok:
        # Avoid echoing whole server responses or request objects into logs.
        print("Request rejected. Check account access, enabled includes,")
        print("and whether the selected fixture is covered by your plan.")
        if response.status_code == 401:
            print("Likely authentication issue: check the secret value.")
        if response.status_code == 403:
            print("Likely subscription/fixture coverage restriction.")
        if response.status_code == 429:
            print("Rate limit reached.")
        sys.exit(1)

    try:
        payload = response.json()
    except ValueError:
        sys.exit("API returned a non-JSON response.")

    fixture = payload.get("data")
    if not isinstance(fixture, dict):
        sys.exit("API succeeded but did not return a fixture data object.")

    print("Fixture record found:", bool(fixture.get("id")))
    print("Available related data:")
    for field in ("statistics", "participants", "scores", "expected", "xgfixture", "xGFixture", "pressure"):
        value = fixture.get(field)
        if isinstance(value, list):
            detail = f"{len(value)} entries"
        elif isinstance(value, dict):
            detail = "object"
        else:
            detail = "not present"
        print(f"  {field}: {detail}")

    # API responses can use different field names. Report only counts;
    # do not expose the full response or authentication details.
    xg_values = next(
        (fixture[key] for key in ("xgfixture", "expected", "xGFixture")
         if isinstance(fixture.get(key), list)),
        None,
    )
    if xg_values is None:
        print("No recognized team xG array in the fixture response.")
    else:
        print("Team xG records detected:", len(xg_values))
    # Sportmonks' published expected-statistic type IDs. Each type
    # represents a distinct metric. Do not sum these different types.
    metric_names = {
        5304: "Expected Goals (xG)",
        5305: "Expected Goals on Target (xGoT)",
        7939: "Expected Points (xPTS)",
        7940: "Expected Goals from Penalties",
        7941: "Expected Goals from Free Kicks",
        7942: "Expected Goals from Corners",
        7943: "Non-Penalty xG",
        7944: "Expected Goals from Set Plays",
        7945: "Expected Goals from Open Play",
        9684: "Expected Goals Difference",
        9685: "Shooting Performance",
        9686: "Expected Goals Prevented",
        9687: "Expected Goals Against",
    }
    xg_records = fixture.get("xgfixture")
    if isinstance(xg_records, list) and xg_records:
        print("Historical match expected metrics:")
        for item in sorted(
            (x for x in xg_records if isinstance(x, dict)),
            key=lambda x: (
                int(x.get("type_id") or 0),
                str(x.get("location") or ""),
            ),
        ):
            type_id = item.get("type_id")
            location = item.get("location") or "unknown"
            value = (item.get("data") or {}).get("value")
            name = metric_names.get(type_id, "Unknown metric")
            print(
                f"  {name} (type {type_id}), "
                f"{location}: {value if value is not None else 'missing'}"
            )
        print(
            "Only type 5304 represents regular team xG; "
            "do not total the different metric types."
        )
    else:
        print("No historical xG metric records were returned.")
    print("Field inspection complete. No data was saved.")


if __name__ == "__main__":
    main()

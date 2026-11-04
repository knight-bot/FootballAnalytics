"""Explore selected historical StatsBomb Open Data match events.

This page is intentionally separate from our football-data.org SQLite
database because competition and season coverage are different.
"""
import requests
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Historical Event Lab | Football Analytics",
    page_icon="⚽",
    layout="wide",
)

BASE = "https://raw.githubusercontent.com/hudl/open-data/master/data"

st.title("🔬 Historical Event Lab")
st.caption(
    "Explore shots, expected goals (xG), and defensive events from "
    "selected historical matches in StatsBomb Open Data."
)
st.info(
    "This is a separate historical dataset. It is not a live or "
    "complete feed for the current Premier League season."
)


@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def get_open_data(path):
    """Read an openly published JSON data file from StatsBomb."""
    url = f"{BASE}/{path}"
    response = requests.get(url, timeout=45)
    response.raise_for_status()
    return response.json()


try:
    competitions = get_open_data("competitions.json")
except (requests.RequestException, ValueError) as exc:
    st.error(f"Unable to load the StatsBomb competition list: {exc}")
    st.stop()

if not competitions:
    st.warning("The available competition list is empty.")
    st.stop()


def competition_label(record):
    return (
        f"{record.get('competition_name', 'Unknown')} "
        f"({record.get('country_name', 'Unknown')}, "
        f"{record.get('competition_gender', 'unknown')})"
    )


with st.sidebar:
    st.header("Historical event data")
    names = sorted({competition_label(c) for c in competitions})
    selected_name = st.selectbox(
        "Competition", names, key="statsbomb_competition"
    )
    possible_seasons = [
        record for record in competitions
        if competition_label(record) == selected_name
    ]
    possible_seasons = sorted(
        possible_seasons,
        key=lambda c: str(c.get("season_name", "")),
        reverse=True,
    )
    season_labels = [
        f"{c['season_name']} (competition {c['competition_id']}, "
        f"season {c['season_id']})"
        for c in possible_seasons
    ]
    season_choice = st.selectbox(
        "Season", range(len(possible_seasons)),
        format_func=lambda i: season_labels[i],
        key="statsbomb_season",
    )
    selected_season = possible_seasons[season_choice]

competition_id = selected_season["competition_id"]
season_id = selected_season["season_id"]

try:
    fixtures = get_open_data(
        f"matches/{competition_id}/{season_id}.json"
    )
except (requests.RequestException, ValueError) as exc:
    st.error(f"Unable to load match list: {exc}")
    st.stop()

if not fixtures:
    st.warning("No historical matches were published for this season.")
    st.stop()

fixtures = sorted(
    fixtures, key=lambda m: (m.get("match_date", ""), m.get("match_id", 0)),
    reverse=True,
)


def team_name(match, side):
    return match.get(f"{side}_team", {}).get(f"{side}_team_name", "Unknown")


def fixture_label(match):
    return (
        f"{match.get('match_date', 'Unknown date')} | "
        f"{team_name(match, 'home')} "
        f"{match.get('home_score', '?')}-"
        f"{match.get('away_score', '?')} "
        f"{team_name(match, 'away')} "
        f"(match {match['match_id']})"
    )


chosen_index = st.selectbox(
    "Historical match",
    range(len(fixtures)),
    format_func=lambda i: fixture_label(fixtures[i]),
)
fixture = fixtures[chosen_index]
home_team = team_name(fixture, "home")
away_team = team_name(fixture, "away")

st.subheader(f"{home_team} vs {away_team}")
st.caption(
    f"{fixture.get('match_date', '')} | "
    f"Recorded final score: {fixture.get('home_score', '?')}–"
    f"{fixture.get('away_score', '?')}"
)

try:
    events = get_open_data(f"events/{fixture['match_id']}.json")
except (requests.RequestException, ValueError) as exc:
    st.error(f"Unable to load event details for this match: {exc}")
    st.stop()

team_order = [home_team, away_team]


def kind(event):
    return event.get("type", {}).get("name", "")


def event_team(event):
    return event.get("team", {}).get("name", "")


def shot_xg(event):
    value = event.get("shot", {}).get("statsbomb_xg")
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


summary_rows = []
shot_rows = []

for side in team_order:
    team_events = [e for e in events if event_team(e) == side]
    shots = [e for e in team_events if kind(e) == "Shot"]
    tackles = [
        e for e in team_events
        if kind(e) == "Duel"
        and e.get("duel", {}).get("type", {}).get("name") == "Tackle"
    ]

    summary_rows.append({
        "Team": side,
        "Shots": len(shots),
        "Total xG": round(sum(shot_xg(e) for e in shots), 2),
        "Shot-event goals": sum(
            e.get("shot", {}).get("outcome", {}).get("name") == "Goal"
            for e in shots
        ),
        "Pressures": sum(kind(e) == "Pressure" for e in team_events),
        "Tackles": len(tackles),
        "Interceptions": sum(
            kind(e) == "Interception" for e in team_events
        ),
        "Clearances": sum(kind(e) == "Clearance" for e in team_events),
        "Blocks": sum(kind(e) == "Block" for e in team_events),
    })

    for shot in shots:
        position = shot.get("location") or []
        if len(position) < 2:
            continue
        shot_rows.append({
            "Team": side,
            "Pitch X": float(position[0]),
            "Pitch Y": float(position[1]),
            "xG": round(shot_xg(shot), 3),
            "Marker size": max(shot_xg(shot), 0.02) * 250,
            "Player": shot.get("player", {}).get("name", "Unknown"),
            "Outcome": shot.get("shot", {}).get(
                "outcome", {}
            ).get("name", "Unknown"),
        })

summary = pd.DataFrame(summary_rows)

st.subheader("Match Event Summary")
st.dataframe(summary, hide_index=True, use_container_width=True)
st.caption(
    "xG is the sum of StatsBomb shot-event xG values, not a live estimate. "
    "Shot-event goals may differ from the recorded final score because "
    "own goals and other scoring adjustments are handled separately."
)

st.subheader("Shot Locations")
if shot_rows:
    shot_df = pd.DataFrame(shot_rows)
    st.scatter_chart(
        shot_df,
        x="Pitch X",
        y="Pitch Y",
        size="Marker size",
        color="Team",
        height=430,
    )
    st.dataframe(
        shot_df[["Team", "Player", "xG", "Outcome", "Pitch X", "Pitch Y"]]
        .sort_values("xG", ascending=False),
        hide_index=True,
        use_container_width=True,
    )
    st.caption(
        "Locations use StatsBomb's 120 × 80 pitch coordinates. "
        "This is a coordinate scatterplot rather than a pitch drawing; "
        "larger markers represent higher-xG attempts."
    )
else:
    st.warning("This match has no shot events with available locations.")

st.subheader("What the defensive metrics mean")
st.markdown(
    "**Pressures** count StatsBomb Pressure events. "
    "**Tackles** count Duel events classified as tackles; they are not "
    "necessarily successful tackles. **Interceptions, clearances, and "
    "blocks** count those event types. These counts are descriptive "
    "and do not measure overall defensive quality on their own."
)
st.divider()
st.markdown(
    "Data source: [StatsBomb Open Data](https://github.com/hudl/open-data). "
    "The selection is historical and limited to matches published in "
    "that repository. Follow StatsBomb's attribution and logo "
    "requirements when publishing analyses using the dataset."
)

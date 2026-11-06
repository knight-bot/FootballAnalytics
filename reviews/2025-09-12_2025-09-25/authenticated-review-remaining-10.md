# Authenticated review of the remaining September fixtures

Reviewed November 6, 2026. The collector on main returned two original-provider snapshots for each of the ten remaining eligible pairs from September 12–25, 2025. All twenty requests returned HTTP 200. The archive digest and all ten individual evidence hashes passed verification. Each returned provider ID matched its request. All pairs agreed on the home and away clubs, Premier League competition (Sportmonks 8 and football-data.org PL), UTC kickoff, completed status (5 and FINISHED/REGULAR), and home–away final score. Each row below is independently verified and approved.

| Sportmonks record | Football-data.org record | Sportmonks home vs away | Football-data.org home vs away | UTC kickoff (both) | FT (both) |
|---|---|---|---|---|---|
| [19427500](https://api.sportmonks.com/v3/football/fixtures/19427500) | [537831](https://api.football-data.org/v4/matches/537831) | Liverpool vs Everton | Liverpool FC vs Everton FC | 2025-09-20T11:30:00Z | 2–1 |
| [19427497](https://api.sportmonks.com/v3/football/fixtures/19427497) | [537827](https://api.football-data.org/v4/matches/537827) | Brighton & Hove Albion vs Tottenham Hotspur | Brighton & Hove Albion FC vs Tottenham Hotspur FC | 2025-09-20T14:00:00Z | 2–2 |
| [19427498](https://api.sportmonks.com/v3/football/fixtures/19427498) | [537829](https://api.football-data.org/v4/matches/537829) | Burnley vs Nottingham Forest | Burnley FC vs Nottingham Forest FC | 2025-09-20T14:00:00Z | 1–1 |
| [19427503](https://api.sportmonks.com/v3/football/fixtures/19427503) | [537833](https://api.football-data.org/v4/matches/537833) | West Ham United vs Crystal Palace | West Ham United FC vs Crystal Palace FC | 2025-09-20T14:00:00Z | 1–2 |
| [19427504](https://api.sportmonks.com/v3/football/fixtures/19427504) | [537834](https://api.football-data.org/v4/matches/537834) | Wolverhampton Wanderers vs Leeds United | Wolverhampton Wanderers FC vs Leeds United FC | 2025-09-20T14:00:00Z | 1–3 |
| [19427501](https://api.sportmonks.com/v3/football/fixtures/19427501) | [537832](https://api.football-data.org/v4/matches/537832) | Manchester United vs Chelsea | Manchester United FC vs Chelsea FC | 2025-09-20T16:30:00Z | 2–1 |
| [19427499](https://api.sportmonks.com/v3/football/fixtures/19427499) | [537830](https://api.football-data.org/v4/matches/537830) | Fulham vs Brentford | Fulham FC vs Brentford FC | 2025-09-20T19:00:00Z | 3–1 |
| [19427496](https://api.sportmonks.com/v3/football/fixtures/19427496) | [537825](https://api.football-data.org/v4/matches/537825) | AFC Bournemouth vs Newcastle United | AFC Bournemouth vs Newcastle United FC | 2025-09-21T13:00:00Z | 0–0 |
| [19427502](https://api.sportmonks.com/v3/football/fixtures/19427502) | [537826](https://api.football-data.org/v4/matches/537826) | Sunderland vs Aston Villa | Sunderland AFC vs Aston Villa FC | 2025-09-21T13:00:00Z | 1–1 |
| [19427495](https://api.sportmonks.com/v3/football/fixtures/19427495) | [537828](https://api.football-data.org/v4/matches/537828) | Arsenal vs Manchester City | Arsenal FC vs Manchester City FC | 2025-09-21T15:30:00Z | 1–1 |

[Collection and downloadable artifact](https://github.com/knight-bot/FootballAnalytics/actions/runs/42170932165) · [Approval](https://github.com/knight-bot/FootballAnalytics/actions/runs/42171105759) · [Full audit](https://github.com/knight-bot/FootballAnalytics/actions/runs/42171197626)

Database commit 9a3e011 contains exactly the earlier ten reviewed pairs plus these ten. SQLite integrity passed. Reviewed two-sided standard xG covers 20/380 local 2025/26 Premier League results (5.26%). Across the database 40 candidates remain outside this date window, one import is unmatched and eleven imports lack a stored unambiguous final score. Stored score conflicts, invalid completed results and stale or ambiguous associations are all zero.

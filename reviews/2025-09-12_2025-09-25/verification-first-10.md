# September 2025 source verification, first 10 pairs

Reviewed November 6, 2026 against [main at b4b4f9e](https://github.com/knight-bot/FootballAnalytics/tree/b4b4f9e9a4afd2cdc9d6b93cc5e815379d50ab59). Selected the first ten rows in the existing September worksheet after checking that both IDs still form a unique unreviewed candidate with agreeing stored scores. Worksheet order is ascending kickoff, then Sportmonks ID.

All 20 original API endpoints were individually requested. Each Sportmonks workspace request timed out. A browser retry of 19427485 reached Sportmonks and returned “No token provided.” Each football-data.org endpoint returned HTTP 403 restricted access. A browser retry of 537817 returned the same restriction. Neither provider supplied a match payload. These checks establish access outcomes only. The teams, UTC kickoffs and home–away scores below come from the local worksheet. Original IDs, teams, league, season, kickoffs and scores remain unverified for all ten pairs. No approval was submitted.

| # | Fixture in worksheet (home vs away) | Stored kickoff UTC | Stored FT | Sportmonks request | football-data.org request | Attempt times UTC (SM / FD) | Status |
|---:|---|---|---|---|---|---|---|
| 1 | Arsenal vs Nottingham Forest | 2025-09-13 11:30:00 | 3-0 | [19427485](https://api.sportmonks.com/v3/football/fixtures/19427485?include=participants;scores) | [537817](https://api.football-data.org/v4/matches/537817) | 04:26:10 / 04:26:15 | UNAVAILABLE |
| 2 | AFC Bournemouth vs Brighton & Hove Albion | 2025-09-13 14:00:00 | 2-1 | [19427486](https://api.sportmonks.com/v3/football/fixtures/19427486?include=participants;scores) | [537815](https://api.football-data.org/v4/matches/537815) | 04:26:21 / 04:26:26 | UNAVAILABLE |
| 3 | Crystal Palace vs Sunderland | 2025-09-13 14:00:00 | 0-0 | [19427489](https://api.sportmonks.com/v3/football/fixtures/19427489?include=participants;scores) | [537816](https://api.football-data.org/v4/matches/537816) | 04:26:32 / 04:26:35 | UNAVAILABLE |
| 4 | Everton vs Aston Villa | 2025-09-13 14:00:00 | 0-0 | [19427490](https://api.sportmonks.com/v3/football/fixtures/19427490?include=participants;scores) | [537820](https://api.football-data.org/v4/matches/537820) | 04:26:41 / 04:26:45 | UNAVAILABLE |
| 5 | Fulham vs Leeds United | 2025-09-13 14:00:00 | 1-0 | [19427491](https://api.sportmonks.com/v3/football/fixtures/19427491?include=participants;scores) | [537821](https://api.football-data.org/v4/matches/537821) | 04:26:51 / 04:26:55 | UNAVAILABLE |
| 6 | Newcastle United vs Wolverhampton Wanderers | 2025-09-13 14:00:00 | 1-0 | [19427493](https://api.sportmonks.com/v3/football/fixtures/19427493?include=participants;scores) | [537823](https://api.football-data.org/v4/matches/537823) | 04:27:01 / 04:27:04 | UNAVAILABLE |
| 7 | West Ham United vs Tottenham Hotspur | 2025-09-13 16:30:00 | 0-3 | [19427494](https://api.sportmonks.com/v3/football/fixtures/19427494?include=participants;scores) | [537824](https://api.football-data.org/v4/matches/537824) | 04:27:10 / 04:27:13 | UNAVAILABLE |
| 8 | Brentford vs Chelsea | 2025-09-13 19:00:00 | 2-2 | [19427487](https://api.sportmonks.com/v3/football/fixtures/19427487?include=participants;scores) | [537818](https://api.football-data.org/v4/matches/537818) | 04:27:19 / 04:27:23 | UNAVAILABLE |
| 9 | Burnley vs Liverpool | 2025-09-14 13:00:00 | 0-1 | [19427488](https://api.sportmonks.com/v3/football/fixtures/19427488?include=participants;scores) | [537819](https://api.football-data.org/v4/matches/537819) | 04:27:29 / 04:27:33 | UNAVAILABLE |
| 10 | Manchester City vs Manchester United | 2025-09-14 15:30:00 | 3-0 | [19427492](https://api.sportmonks.com/v3/football/fixtures/19427492?include=participants;scores) | [537822](https://api.football-data.org/v4/matches/537822) | 04:27:39 / 04:27:42 | UNAVAILABLE |

## Final audit

[GitHub Actions audit on main](https://github.com/knight-bot/FootballAnalytics/actions/runs/42162622608) passed, including research and evidence tests, Streamlit smoke tests and historical quality reporting. A separate read-only SQLite integrity check returned ok.

Across the database there are 1,921 completed results, 0 invalid results, 61 independent imports with two-sided standard xG, 50 saved final scores and 60 unreviewed candidate links. There are 0 stored score conflicts, 0 ambiguous or stale links and 0 valid reviewed links. The research readiness report lists no reviewed xG source IDs. The 2025/26 Premier League has 0/380 locally recorded results with reviewed two-sided xG, 50 unreviewed candidates and 330 results without a candidate. Approval requires access to both original records and agreement on IDs, competition, season, sides, kickoff and full-time goals.

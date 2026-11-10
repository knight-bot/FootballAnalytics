# Authenticated original-record review, September 12–25, 2025

On November 6, 2026, the collector fetched both original records for each of the first ten pairs. This follow-up resolves the access failures recorded in the earlier worksheet. All 20 requests returned HTTP 200. I inspected the provider-specific fields in the sanitized JSON and checked each returned ID, Premier League competition (Sportmonks 8 and football-data.org PL), home and away sides, UTC kickoff, completed state, and full-time goals. Every pair agreed. Both providers returned the UTC kickoffs and scores shown below. The 2025/26 season is identified by competition and kickoff date.

| Sportmonks ID | Football-data.org ID | Sportmonks teams | Football-data.org teams | Kickoff UTC | FT |
|---:|---:|---|---|---|---|
| [19427485](https://api.sportmonks.com/v3/football/fixtures/19427485) | [537817](https://api.football-data.org/v4/matches/537817) | Arsenal v Nottingham Forest | Arsenal FC v Nottingham Forest FC | 2025-09-13T11:30:00Z | 3–0 |
| [19427486](https://api.sportmonks.com/v3/football/fixtures/19427486) | [537815](https://api.football-data.org/v4/matches/537815) | AFC Bournemouth v Brighton & Hove Albion | AFC Bournemouth v Brighton & Hove Albion FC | 2025-09-13T14:00:00Z | 2–1 |
| [19427489](https://api.sportmonks.com/v3/football/fixtures/19427489) | [537816](https://api.football-data.org/v4/matches/537816) | Crystal Palace v Sunderland | Crystal Palace FC v Sunderland AFC | 2025-09-13T14:00:00Z | 0–0 |
| [19427490](https://api.sportmonks.com/v3/football/fixtures/19427490) | [537820](https://api.football-data.org/v4/matches/537820) | Everton v Aston Villa | Everton FC v Aston Villa FC | 2025-09-13T14:00:00Z | 0–0 |
| [19427491](https://api.sportmonks.com/v3/football/fixtures/19427491) | [537821](https://api.football-data.org/v4/matches/537821) | Fulham v Leeds United | Fulham FC v Leeds United FC | 2025-09-13T14:00:00Z | 1–0 |
| [19427493](https://api.sportmonks.com/v3/football/fixtures/19427493) | [537823](https://api.football-data.org/v4/matches/537823) | Newcastle United v Wolverhampton Wanderers | Newcastle United FC v Wolverhampton Wanderers FC | 2025-09-13T14:00:00Z | 1–0 |
| [19427494](https://api.sportmonks.com/v3/football/fixtures/19427494) | [537824](https://api.football-data.org/v4/matches/537824) | West Ham United v Tottenham Hotspur | West Ham United FC v Tottenham Hotspur FC | 2025-09-13T16:30:00Z | 0–3 |
| [19427487](https://api.sportmonks.com/v3/football/fixtures/19427487) | [537818](https://api.football-data.org/v4/matches/537818) | Brentford v Chelsea | Brentford FC v Chelsea FC | 2025-09-13T19:00:00Z | 2–2 |
| [19427488](https://api.sportmonks.com/v3/football/fixtures/19427488) | [537819](https://api.football-data.org/v4/matches/537819) | Burnley v Liverpool | Burnley FC v Liverpool FC | 2025-09-14T13:00:00Z | 0–1 |
| [19427492](https://api.sportmonks.com/v3/football/fixtures/19427492) | [537822](https://api.football-data.org/v4/matches/537822) | Manchester City v Manchester United | Manchester City FC v Manchester United FC | 2025-09-14T15:30:00Z | 3–0 |

All ten evidence row hashes matched. The ZIP SHA-256 was `ecc81cc1b855a809eac9ffae2ad95ca2ecd96ffeb14ff5ca297465c1454d917a`. [Collection and downloadable evidence](https://github.com/knight-bot/FootballAnalytics/actions/runs/42166419866)

The [approval workflow](https://github.com/knight-bot/FootballAnalytics/actions/runs/42167174013) recorded all ten associations. The [post-approval audit](https://github.com/knight-bot/FootballAnalytics/actions/runs/42167292174) passed on [the database commit](https://github.com/knight-bot/FootballAnalytics/commit/ad7944c25478a738530282e29d670647ed6baf4d). An independent read-only check found the exact ten reviewed ID pairs from the artifact and SQLite integrity was OK. Reviewed two-sided xG coverage is 10/380 local 2025/26 Premier League results. There are zero stored score conflicts and zero ambiguous or stale links.

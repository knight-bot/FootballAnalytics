# FootballAnalytics

A Streamlit research dashboard for **completed historical football
matches**, backed by SQLite. Includes recorded match statistics,
source-aware Sportmonks xG, retrospective evaluation and downloadable
research evidence.

## Start locally

```bash
git clone https://github.com/knight-bot/FootballAnalytics.git
cd FootballAnalytics
python -m pip install -r requirements.txt
streamlit run app.py
```

The website reads the checked-in `football.db`. Browsing and exporting
research does **not** need an OpenAI or Sportmonks API key.

## Research workflow

The homepage's **Research workspace** shows the numbers of stored
results, independent imported fixtures, operator-reviewed source links
and reviewed two-sided xG matches. Follow its links to the existing
Streamlit pages:

1. **Historical xG Analysis:** completed goal records, form,
   opponent context and xG where operator-reviewed.
2. **Historical Fixture Link Review:** unreviewed candidates, source
   score discrepancies and stale associations.
3. **Historical Coverage Audit:** local sample completeness and
   source-level evidence gaps.
4. **Multi-Season Historical Evaluation:** held-out historical
   goal-model errors and sensitivity diagnostics.
5. **ChatGPT Research Export:** a Markdown report and JSON evidence
   manifest with source IDs, counts and explicit limitations.

## Source integrity

The two providers use different fixture IDs. Importing Sportmonks
metrics does not mean they belong to any particular football-data.org
result. A source association must be unambiguous and explicitly
approved after a human compares the original final scores.
Stored score disagreement blocks approval; a match-score agreement
alone never approves it.

**Stored ≠ candidate ≠ operator-reviewed ≠ usable linked xG.**
Missing data is unknown, not zero. Counts from the local database
are not independent proof of complete official league seasons.

The platform is retrospective and does not generate future-match
recommendations, odds or wagers.

## Verification and deployment

The [historical audit workflow](https://github.com/knight-bot/FootballAnalytics/actions/workflows/historical-audit.yml)
automatically tests Python computations, database safeguards,
Streamlit rendering and source-provenance exports on code changes
to `main`. GitHub Actions also prints real historical scoring trends.

Follow the [Deployment and Acceptance Checklist](DEPLOYMENT_CHECKLIST.md)
for live Streamlit host and manual source-link verification.
Passing CI is not sufficient evidence that the external hosting
deployment is current.

## Further documentation

- [Historical data source score QA](HISTORICAL_SOURCE_SCORE_QA.md)
- [Historical coverage](HISTORICAL_COVERAGE_AUDIT.md)
- [Historical statistical research](HISTORICAL_STATISTICAL_RESEARCH.md)
- [One-file research export](CHATGPT_RESEARCH_EXPORT.md)

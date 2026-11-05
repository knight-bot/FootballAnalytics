# Deployment and acceptance checklist

This checklist distinguishes **code verification** from actual live
Streamlit deployment and **operator-attested** cross-provider evidence.

## 1. Verify the repository build

Open [Audit Historical Football Data](https://github.com/knight-bot/FootballAnalytics/actions/workflows/historical-audit.yml).

The latest workflow run for the deployed `main` commit must have:
- Successful Python syntax checks and historical unit tests.
- Successful **Streamlit AppTest** smoke tests for `app.py` and six
  core research pages, using the checked-in `football.db`.
- Successful read-only historical data-quality and scoring summaries.

A green run for an *older commit* does not validate later changes.

## 2. Check the live Streamlit environment

In the hosting settings confirm:
- GitHub repository: `knight-bot/FootballAnalytics`
- Branch: `main`
- Entry point: `app.py`
- Dependencies installed from `requirements.txt`
- The deployed `football.db` corresponds to the current commit.

Refresh the deployed site. Confirm it shows **Research workspace**
near the top, with four indicators:
completed results, independent Sportmonks fixtures, operator-reviewed
links and reviewed two-sided xG matches.

A new import in GitHub will not appear in the deployed app until
the hosting platform updates its checked-out database.

## 3. Manually navigate the primary research workflow

- **Historical xG Analysis:** Open it, change a team and season,
  inspect the overall/historical research sections. If no reviewed
  xG matches exist, the page should clearly say that joined xG is
  unavailable, not display fabricated totals.
- **Historical Fixture Link Review:** See candidate and mismatch
  statuses. Do not treat stored score agreement as approval.
- **Historical Coverage Audit:** Select a team, filter a coverage
  status and download CSV. The denominator must be local recorded
  completed matches, not the official league schedule.
- **Multi-Season Historical Evaluation:** Check eligible/skipped
  seasons, error comparison and uncertainty labels.
- **ChatGPT Research Export:** Change the team, then download
  both the **Markdown research report** and **JSON source manifest**.
  Check the report and manifest show the same selected team/season,
  match IDs, reviewed links and independent case-study IDs.

## 4. Trust and data-quality acceptance criteria

- Results sourced from football-data.org and independent Sportmonks
  fixtures must remain distinct without operator-reviewed links.
- Conflicting stored final scores must block approval.
- Stale/ambiguous links cannot contribute xG to team reports.
- Missing xG must remain unknown rather than zero.
- Historical research may proceed without linked xG, but claims
  involving xG must be withheld or qualified.
- Neither the site nor its downloads should include API secrets.
- No page view or research export should modify `football.db`.

## 5. Pending work requiring real source/operator access

1. Refresh older completed Sportmonks fixtures with the manual,
   bounded import action if their source scores were not persisted.
2. Confirm eligible associations only after comparing BOTH original
   providers' final-score records.
3. Re-run the audit and verify reviewed counts change in the
   deployed homepage and research exports.

**Acceptance status:** Passing local/CI tests does not substitute
for the manual live-host inspection and source-review steps above.
Do not claim full release readiness until those checks are completed.

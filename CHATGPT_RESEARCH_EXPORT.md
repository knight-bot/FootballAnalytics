# ChatGPT-ready historical research export

This feature creates **one Markdown file** that can be uploaded to ChatGPT
for critical historical football analysis. It uses local \`football.db\`
only. **No OpenAI API key is needed.**

## Use the Streamlit page

1. Open **ChatGPT Research Export** in the FootballAnalytics dashboard.
2. Select the competition, historical July–June date window, and team.
3. Optionally choose up to **8 imported, completed Sportmonks fixtures**.
4. Click **Download ChatGPT research report (.md)**.
5. Upload that file to your ChatGPT conversation. The report includes a
   suggested request asking for evidence-based, retrospective interpretation.

The preview shows the exact Markdown that will be exported. The file contains
a team historical-results report, home/away differences, source match IDs,
league-adjusted goal-strength indicators (Part A.2), reviewed historical
standard xG (Part A.3), a **match-by-match coverage audit** (Part A.4),
optional independent Sportmonks case studies, and limitations.

## Critical source rule

The two providers have **different IDs**. Selecting a Sportmonks fixture
alongside a team report does **not** mean the fixture involves that team. The
separately selected case studies are independent.

A historical candidate matcher exists, but only **currently
operator-reviewed** source associations may appear as linked team examples.
Operators attest that they compared source final scores; the application
does not independently verify those source scores. Ambiguous, stale and
unreviewed candidates cannot contribute to joined historical xG.

## What this tool does not do

- No predictions, future-match recommendations or betting calculations.
- No AI requests, automatic web research or fresh match collection.
- No assumptions that a small sample represents a complete season.
- No substitution of zero for missing xG or other missing metrics.
- No official standings reconstruction, disciplinary point deductions or
  inferred provider season IDs.

## Quality and data-sharing notes

Check **Historical Coverage Audit** and **Historical Data Audit** for
match-by-match and metric-level gaps. Some numeric rows may be absent even
when the Sportmonks API returned statistical records. Coverage ratios are
defined against valid results **stored locally**, not the complete official
schedule.

The exported report contains provider-derived football data and names, which
will be shared with ChatGPT if you upload the file. Follow each provider's
licensing and redistribution terms before sharing data externally; use only
data that your account is authorized to process.

## Verify the feature

Open GitHub Actions -> **Audit Historical Football Data** -> **Run workflow**.
The workflow runs syntax checks and offline unit tests, without spending
Sportmonks or OpenAI API calls.

The Streamlit page and downloaded file also require a manual deployment test
after the changes reach the hosting environment.

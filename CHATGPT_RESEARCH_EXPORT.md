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
optional separate Sportmonks fixture records, and coverage warnings.

## Critical source rule

The two providers have **different IDs**. Selecting a Sportmonks fixture
alongside a team report does **not** mean the fixture involves that team. The
case studies are independent unless explicitly verified elsewhere.

No automatic team-name or match-ID mapping occurs. Do not combine statistics
across providers as if they belong to the same match.

## What this tool does not do

- No predictions, future-match recommendations or betting calculations.
- No AI requests, automatic web research or fresh match collection.
- No assumptions that a small sample represents a complete season.
- No substitution of zero for missing xG or other missing metrics.
- No official standings reconstruction, disciplinary point deductions or
  inferred provider season IDs.

## Quality and data-sharing notes

Check the **Historical Data Audit** page for more detail about incomplete
statistics. Some numeric rows may be absent even when the Sportmonks API
returned statistical records.

The exported report contains provider-derived football data and names, which
will be shared with ChatGPT if you upload the file. Follow each provider's
licensing and redistribution terms before sharing data externally; use only
data that your account is authorized to process.

## Verify the feature

Open GitHub Actions -> **Audit Historical Football Data** -> **Run workflow**.
The workflow runs syntax checks and offline unit tests (including the eight
new export tests), without spending Sportmonks or OpenAI API calls.

The Streamlit page and downloaded file also require a manual deployment test
after the changes reach the hosting environment.

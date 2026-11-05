# Historical Evidence Research

This page offers **retrospective, educational football-data research** from
completed matches already saved in football.db. It does not fetch current games,
make forecasts, produce odds, or recommend wagers.

## Open the page

Deploy the repository's Streamlit app, then select
**Historical Evidence Research** from the page list.

1. Choose **Completed team results** or **Imported Sportmonks fixture**.
2. Pick a competition / historical date window / team, or an imported fixture.
3. Open **Inspect source evidence and original IDs** to check the original
   provider IDs supporting every fact.
4. Use **Offline evidence review** and **Export evidence (JSON)**. Neither
   needs an API key or network call.

## Optional AI-assisted explanation

The optional **Generate evidence-cited interpretation** button is disabled
unless the **deployed Streamlit server** has an existing \`OPENAI_API_KEY\`
environment variable. A secret present only in GitHub Actions does *not*
automatically become available to a separate Streamlit deployment.

- The button must be clicked explicitly. No automated or scheduled calls.
- The selected evidence pack is sent to the configured API to explain past
  results. An API subscription may be charged for the request.
- The API request uses the Responses API with \`store=false\`. This is not a
  statement that no transient processing or other retention occurs.
- The application validates that each model observation cites IDs in its
  source evidence. It does **not** automatically prove the claim is logically
  supported by those IDs, so every observation must be checked by a reader.
- The original database limitations are always displayed even if the model
  forgets them.
- Optional model selection uses the server variable
  \`OPENAI_HISTORICAL_MODEL\`, defaulting to \`gpt-4.1-mini\`.
- Do not commit API credentials to Git, put them into browser forms, or paste
  them into publicly shared screenshots.

## Limitations

- The results source and Sportmonks source remain separate: their IDs are not
  interchangeable and this feature does not infer cross-provider mappings.
- Historical season windows are grouped July–June from match dates, not
  provider-certified season boundaries.
- Only locally stored, completed fixtures are represented.
- Missing figures are not zero. A small sample cannot justify league-wide
  conclusions.
- AI is strictly optional. If no key is set, the evidence review remains
  functional, with zero external model API requests.

## Tests

The manual **Audit Historical Football Data** workflow runs offline syntax
checks, source-evidence tests, and a read-only summary of your local database.
All its tests use mock data and make no external AI requests.

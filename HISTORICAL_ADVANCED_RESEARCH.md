# Advanced retrospective football research

The **Historical xG Analysis** page now includes three additional
historical research diagnostics. The consolidated **ChatGPT Research
Export** includes the same calculations in **Part A.5**. Both read
locally stored completed football matches.

This is descriptive historical analysis. It does not generate forecasts
for upcoming matches, odds, wagers, or fixture recommendations.

## 1. Check the sample before drawing conclusions

The **season sample balance** section counts valid \`FINISHED\` league
matches actually stored in SQLite. It reports the number of teams,
minimum/median/maximum matches recorded per team, home/away counts,
invalid rows, duplicate same-date fixture signatures, and source IDs.

**Important:** These figures cannot certify a complete official
season. A missing fixture does not appear in the local database, so
we cannot detect it without an independent authoritative schedule.
A league might have uneven counts because of incomplete imports
rather than performance differences.

## 2. Put a team's historical scores into opponent context

For every completed game involving the selected team:

- Find the opponent's other valid completed games in the **same
  July–June league season** and at the **same opponent venue**.
- Exclude **all** the opponent's games against the selected team.
  This prevents using the actual target-opponent head-to-head score
  as the comparison reference.
- Require at least **three** opponent other-game references.
  If fewer are present, display **Unavailable**, not zero.
- Compare recorded goals against that opponent's other-game scoring
  and conceding averages, preserving exact reference match IDs.

These averages are **not held-out predictions**. They may include
completed games played *after* the game being described. They
therefore provide retrospective context only, not a valid
chronological prediction experiment or a causal measure of ability.

## 3. Review historical xG carefully

Advanced xG diagnostics operate only on the match rows that the
existing \`analyze_team_xg\` module has already confirmed as having:

- A locally stored completed football-data.org result.
- A currently valid **operator-reviewed** cross-provider fixture link.
- A unique, valid Sportmonks **standard xG** (type 5304)
  observation for both home and away.

They report:

- Actual goals and xG, overall and separated by home/away.
- Goals-minus-xG and conceded-minus-xGA on the included sample.
- A chronological cumulative goals-versus-xG display for reviewed
  matches only.
- Up to three largest recorded goals-minus-xG deviations with
  source-match IDs.
- A descriptive Pearson xG-versus-goals correlation **only when
  there are at least ten distinct reviewed matches** and both
  series vary. Otherwise the correlation remains unavailable.

No xG values from independent, unreviewed Sportmonks case studies
are treated as if they belong to the selected team's matches.
Positive goals-minus-xG does not prove stable finishing skill.
Correlation does not establish causation or prospective accuracy.

## Reporting and testing

The existing Streamlit **Historical xG Analysis** page now displays
the above results with a CSV source audit and a downloadable
advanced Markdown research section. The consolidated ChatGPT export
automatically adds Part A.5.

Run the **Audit Historical Football Data** workflow to validate
the integration:

https://github.com/knight-bot/FootballAnalytics/actions/workflows/historical-audit.yml

The Python diagnostics were also tested against an offline
synthetic SQLite dataset covering missing references, season filters,
venue orientation, cumulative xG values, source IDs and empty
samples. Actual production dataset coverage remains a separate
issue and must be checked after data imports and reviews.

**Next substantive data dependency:** More historical Sportmonks
fixtures with *reviewed* cross-provider associations. This analysis
will not infer missing xG or silently use unmatched data.

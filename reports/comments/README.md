# Monthly report commentary

One TOML file per portfolio and month. Everything else in the report (NAV, returns,
allocation, contributors, risk) is computed from `daily_holdings`; **these files are the
only hand-written part**, and without them a report is rendered as a **DRAFT** with a
visible banner and cannot be published.

```
reports/comments/
  visionnaire/2026-06.toml
  batisseur/2026-06.toml
  nakamoto/2026-06.toml
  _template.toml
```

## Format

```toml
market_comment = [
  "One paragraph on the tape / macro / earnings context of the month.",
  "Second bullet.",
  "Third bullet.",
]
mgmt_comment = [
  "How the book did: <strong>{pf_mtd_pct}%</strong> vs <strong>{bench_mtd_pct}%</strong> for the {bench_pri_lbl} (alpha <strong>{alpha_mtd_pct}pp</strong>). Cash at month-end: <strong>{cash_pct}%</strong>.",
  "<strong>Moves.</strong> What changed and why (or 'no moves').",
  "<strong>Positioning.</strong> Concentration, layers, what you are watching.",
]
```

Placeholders filled automatically: `{pf_mtd_pct}` `{bench_mtd_pct}` `{alpha_mtd_pct}`
`{cash_pct}` `{bench_pri_lbl}`. Light HTML (`<strong>`) is allowed. Keep the LSFin tone:
"according to my thesis", "aims for", no "undervalued" in absolute terms, no
recommendation language (see memory `project_monthly_report` compliance notes).

## Workflow

1. The 2nd of each month, **Monthly reports** (GitHub Action) regenerates the drafts for
   the previous month into `reports/drafts/<pid>/` and opens an issue *Checklist mensuelle*.
2. Write the three TOML files, commit them.
3. Run the **Publish monthly report** action (portfolio + month) — or locally
   `python scripts/publish_report.py <pid> --month YYYY-MM`. It renders the PDF with
   headless Chromium, uploads it to the `research-docs` bucket and adds the row that the
   site's *Documents* section reads. It refuses to publish a draft.

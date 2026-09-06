# Budget data and provenance

The budget page consumes version-controlled releases under `data/curated/budgets/`.
It does not read the loose working CSVs or extract PDFs during a build. Each year belongs
to exactly one selected release; updating the data is an explicit editorial change.

## Current release: reviewed 6 September 2026

`mof-2026.json` contains FY2024 actual, FY2025 revised and FY2026 estimated expenditure,
from **MOF Analysis of Revenue and Expenditure FY2026**, published on 12 February 2026:

- [Official PDF](https://isomer-user-content.by.gov.sg/153/b25a4bb9-db1b-428d-ab48-4528e0ee0d37/fy2026_analysis_of_revenue_and_expenditure_2026.pdf): Table 3.4, page 29 (operating); Table 3.5, page 30 (development).
- Table 3.3, page 28, independently cross-checks the FY2025/FY2026 breakdown.
- [MOF source index](https://www.mof.gov.sg/news-resources/revenue-and-expenditure/) links the release and currently distinguishes revised FY2025 from estimated FY2026.

The PDF was downloaded and its rendered tables visually checked. Its SHA-256 is recorded
in the release; a local copy is retained at `data/raw/budgets/analysis-2026.pdf` (ignored by Git).
The JSON is a reviewed extraction, not a claim that future PDF layouts can be parsed automatically.

Scope is **operating plus development expenditure**, excluding other Consolidated/Development
Fund outlays and special transfers. Amounts are rounded S$ millions. Source dashes remain
`null`, not fabricated numeric observations; they contribute nothing to chart aggregates.

| FY | Basis | Published operating | Published development | Sum of extracted components |
|---|---|---:|---:|---:|
| 2024 | Actual | 88,896 | 23,385 | 112,279 |
| 2025 | Revised | 97,468 | 26,991 | 124,459 |
| 2026 | Estimated | 103,269 | 34,054 | 137,325 |

The published FY2026 total is 137,323. Rounded components need not sum exactly to rounded
control totals. Validation uses at most S$0.5m rounding error per numeric component plus
S$0.5m for its control, for both annual and sector totals. It never rescales values to force a match.

## Reconciliation of the old working files

`GovernmentTotalExpenditure.csv` previously supplied the charts. It contained FY2024
**revised**, FY2025 **estimated**, and FY2026 **estimated** values. The separate
`2025+2026.csv` was not consumed by the page. Its totals were 142,071.62 for FY2025 and
156,958.68 for FY2026; these are not the total-expenditure series used by the charts.

A concrete scope mismatch appears in National Development:

| FY2026 development, S$ million | Amount |
|---|---:|
| Detailed development expenditure | 1,447.0929 |
| Other Development Fund outlays | 12,166.4426 |
| Combined allocation | 13,613.5355 |
| Working CSV value | 13,613.54 |

The [detailed estimates PDF](https://isomer-user-content.by.gov.sg/153/c72498dd-0ea7-459a-a125-3ecaf1023081/fy2026_revenue_and_expenditure_estimates_for_fy2026-fy2027.pdf), printed page 180,
separates development expenditure from other outlays (land-related expenditure and loans).
Its explanatory notes, page iii, explicitly exclude other outlays from expenditure.
The original working file therefore cannot be substituted as a newer edition of the same series.
This example explains the largest individual mismatch; it is not a complete audit of every
working-file entry. The chart now uses the independently reviewed expenditure tables instead.

Classification also differs: Manpower spans Social and Economic Development; MDDI spans
three sectors. Organs of State is retained as the official aggregate. The chart keeps these
allocations separate and labels the basis of year-on-year comparisons. Budget passage does
not change an estimate into actual expenditure.

The original CSVs and PDFs have been retained without modification.

## Historical release

`historical.json` preserves FY1997-FY2023 from the existing `GovernmentTotalExpenditure.csv`,
grouped by year, sector and ministry. No amounts were changed. The original file's SHA-256
is recorded, but its original download date and exact data.gov.sg dataset revision are unknown.
These years passed structural validation; they have **not** been rechecked against historical
PDFs. The page makes this limitation visible. Earlier ministry/sector classifications may differ.

## Updating a release

1. Retain the official source and record its URL, publication date, SHA-256 and review date.
2. Extract a complete set of years with explicit estimate bases; retain source dashes.
3. Check the rendered tables and footnotes, especially exclusions and sector reclassifications.
4. Add or replace an explicitly selected release in `astro/src/lib/budgets.ts`.
5. Run `cd astro && bun test tests/budgets.test.ts`, then `bun run build` and inspect `/budgets`.

Validation rejects malformed amounts, duplicate rows, mixed bases, incomplete coverage,
overlapping year selections and unreconciled totals. Publication fingerprints include these
curated JSON files. Source retrieval and editorial review remain separate from deterministic
validation, aggregation and rendering.

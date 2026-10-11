# Python Scripts

This directory contains scripts for the data pipeline. 

## Instructions
To install dependencies:

```bash
cd python
uv sync
```
When a new sitting is added to the Hansard, we need to
1. Ingest that sitting's transcript in our desired format using the Hansard API
1. Generate summaries for the questions, bills, and motions in that sitting
1. Review MP summaries for changed inputs and explicitly select any replacements

For example, if the sitting on 27 February 2026 has just been added, we would run
```bash
uv run batch_process_sqlite.py 27-02-2026
uv run generate_summaries_sqlite.py --sittings 27-02-2026
uv run generate_summaries_sqlite.py --members
```

These scripts are described below. See [architecture](../docs/architecture.md) for module
boundaries and [operations](../docs/operations.md) for daily automation and verification.


## Historical reports

See [supported layouts, read-only inspection and verification](../historical/README.md).
Historical processing runs separately and does not write the site database.

## Main Scripts

### `batch_process_sqlite.py`

Ingests parliament sitting data for a given date range (inclusive of both start and end) into the SQLite database at `data/parliament.db`.

#### Usage
```bash
uv run batch_process_sqlite.py START_DATE [END_DATE]
```

#### Examples
```bash
# Single date
uv run batch_process_sqlite.py 14-01-2026

# Range of dates
uv run batch_process_sqlite.py 12-01-2026 14-01-2026
```

### `generate_summaries_sqlite.py`

Generates AI summaries for sitting sections and MP profiles using Gemini. By default, only missing summaries are generated (`--only-blank` remains an alias). Replacing existing text requires `--regenerate`; changing the configured model or prompts never triggers replacement on its own.

#### Usage
```bash
# For sittings
uv run generate_summaries_sqlite.py --sittings START_DATE [END_DATE] [--only-blank]

# For MPs
uv run generate_summaries_sqlite.py --members [--only-blank]
```

#### Examples
```bash
# Range of dates
uv run generate_summaries_sqlite.py --sittings 12-01-2026 14-01-2026

# MPs (based on last 20 contributions)
uv run generate_summaries_sqlite.py --members

# Only fill in missing summaries
uv run generate_summaries_sqlite.py --sittings 12-01-2026 --only-blank
```

## Summary provenance and review

`summary_jobs.py` assembles deterministic inputs for sections, bills and members.
Each generation attempt records entity ID/type, full input hash, prompt key and template hash
(the prompt version), model, UTC timestamp, status, input size and available token usage.
Successful text and its provenance commit together. A failed replacement leaves the last
successful text and its provenance intact. Old summaries are labelled `provenance_unknown`;
we do not guess their model or backfill fabricated metadata.

Review is read-only, works on databases without the new history table, and makes no API calls:

```bash
uv run generate_summaries_sqlite.py --sittings 05-08-2026 --review
uv run generate_summaries_sqlite.py --members --review
uv run generate_summaries_sqlite.py --sittings 05-08-2026 --review --model MODEL_TO_COMPARE
```

JSONL output reports `missing`, `provenance_unknown`, `input_changed`, `prompt_changed`,
`model_changed` and `over_input_limit`, plus the current summary's generation metadata and
latest attempt status. These are review signals, not a regeneration queue.

To explicitly replace selected summaries after reviewing cost/scope:

```bash
uv run generate_summaries_sqlite.py --sittings 05-08-2026 --id SECTION_OR_BILL_ID --regenerate
uv run generate_summaries_sqlite.py --members --id MEMBER_ID --regenerate
```

`--id` is repeatable. Without it, `--regenerate` replaces all eligible summaries in the selected
scope. The daily job continues to fill blanks only; member generation remains a separate command.
Members without a `member_summaries` row are included when filling blanks.

Prompts are no longer silently truncated. A prompt over the default **20,000 characters** is
recorded as `blocked` without an LLM request; shorter eligible jobs still run. To process a
reviewed long input, explicitly raise `--max-input-chars N`. This limit includes the prompt
instructions and title as well as source text. No chunking or automatic extra requests are added.
Blocked jobs are reported in counts but do not fail the process; provider failures exit nonzero.

History lives in `summary_attempts`, created by normal schema initialisation on a generation
run. It is excluded from publication fingerprints: metadata-only changes do not rebuild the site.
Changes to the successful summary text do trigger publication. Usage fields are stored separately;
cached tokens are a subset of prompt tokens, not an additional total.

## AI detection

An internal pipeline that tests prepared parliamentary speeches with Pangram's AI-text detector.
Every output goes to `data/ai_detection/`, which is ignored by git because results link named MPs
to scores.

### Export

`export_pangram_speeches.py` reads the database read-only and splits debates into one row per
speaker turn. It drops presiding-officer turns, the President's own address, translated vernacular
passages and turns under `--min-words`. The default scope is the President's Address debate.

```bash
uv run export_pangram_speeches.py                      # 2020, 2023 and 2025 Address debates
uv run export_pangram_speeches.py --years 2020 2025 --min-words 200
uv run export_pangram_speeches.py --scope prepared --years 2021 2026 --through 09-10 --min-words 500
```

`--scope prepared` widens the export to every motion, adjournment motion and bill second-reading
debate, writes to `ai_detection/prepared_speeches/` and adds `debate_type` to each speech. Speech IDs
start with the debate type (`pa` Address, `bp` bill, `bu` Budget and Committee of Supply, `mo` other
motion, `am` adjournment), so an Address speech keeps the same ID in either scope. `--through MM-DD`
keeps the same calendar window in every year, so a partial year can be compared like for like.

Each export writes `speeches.jsonl` (text plus member, role and section mappings), `members.csv`,
one `pangram_upload_<year>.csv` (`tag`,`text`) per year and `manifest.json` (parameters, word counts,
exclusions, output hashes). The `tag` is the `speech_id`, so Pangram results join back to `speeches.jsonl`.

### Scanning

`run_pangram_bulk.py` sends exported speeches to the Pangram Bulk API (`PANGRAM_API_KEY` in `.env`).
It is a dry run unless `--submit` is given; the dry run prints words, billable units and the
estimated cost at the bulk rate. Every run first collects results for jobs already submitted.

```bash
uv run run_pangram_bulk.py --years 2020                       # plan and cost only
uv run run_pangram_bulk.py --years 2020 --submit              # spend credits
uv run run_pangram_bulk.py --years 2020 2025 --exclude-office-holders --limit 2 --submit
```

State is kept in `<export>/pangram/`: `jobs.jsonl` (append-only submissions), `raw/<bulk_id>/`
(unmodified responses) and `results.jsonl` (one line per speech with the full result, including
windows). A speech already in `jobs.jsonl` is never resent, including after a submission with an
unknown outcome. Pangram deletes bulk results 48 hours after completion, so an interrupted run
should be resumed promptly. Pass `--export-dir ../data/ai_detection/prepared_speeches` for the
wider export.

For scans on the Pangram dashboard instead, `--write-csv` writes the same selection as a `tag`,`text`
upload and sends nothing. Speeches with a saved result are never selected, wherever it came from.

```bash
uv run run_pangram_bulk.py --export-dir ../data/ai_detection/prepared_speeches --years 2021 \
  --exclude-office-holders --write-csv ../data/ai_detection/prepared_speeches/dashboard_upload_2021.csv
```

### Cost estimates

`estimate_pangram_cost.py` prices a wider scan without sending anything. It counts speeches in
motions, adjournment motions and bill debates, split and filtered as in the export, and prints words
and bulk cost per year, with and without office holders, then by debate type.

```bash
uv run estimate_pangram_cost.py                       # 2020-2026, speeches of 500+ words
uv run estimate_pangram_cost.py --years 2023 --min-words 150
```

### Dashboard reports

`import_pangram_dashboard.py` reads report files saved from the dashboard history, keeps a report
only if the text Pangram scanned equals the exported text, renames window fields to the bulk API's
and appends to the same `results.jsonl`. The downloaded files are kept in `pangram/raw/dashboard/`,
and reports already imported are skipped.

```bash
uv run import_pangram_dashboard.py ~/Downloads/pangram-history-reports-*.jsonl
```

### Portraits

`fetch_mp_photos.py` takes only freely licensed Wikipedia lead images of MPs who spoke and records
the file page, author and licence in `ai_detection/photos/credits.json`. Official portraits from
parliament.gov.sg are not used: their terms forbid reproduction without written permission.

```bash
uv run fetch_mp_photos.py          # once; skips members already in credits.json
```

## Reruns and offline replay

Each sitting is imported in one SQLite transaction. Replaying a sitting preserves its IDs,
bill links and summaries. Merged transcript sections retain all Hansard source IDs in
`section_sources`; existing databases gain this table on the next `init_db()` call.

Existing titles, categories, types and ministry assignments are treated as curated metadata
and preserved. Transcript bodies, order, speakers and attendance refresh from the source.
Changed transcripts retain their old summaries pending explicit review. Summary provenance records
input and prompt hashes so subsequent reviews can identify changes without making LLM calls.

Ambiguous matches, removed sections or splits of an existing merged section abort and roll
back the sitting. Resolve those cases explicitly; `cleanup_duplicates_sqlite.py` remains a
manual repair tool, not a daily pipeline step. No historical duplicates are silently removed.

Fetched JSON is stored by date and SHA-256 under `data/raw/hansard/`, with source URL and
retrieval time in a companion `.meta.json`. HTTP failures raise after bounded retries;
invalid payloads raise instead of being treated as a day without a sitting. The date loop
stops on failure, so later dates cannot advance the watermark past that failure.

Replay a saved response without network access (use the response file, not `.meta.json`):

```bash
uv run batch_process_sqlite.py 05-08-2026 --source-file /absolute/path/to/response.json
```

Set `PARLIAMENT_DB_PATH` to an absolute path to use a scratch database. Raw snapshots default
to `raw/hansard/` beside that database; `HANSARD_RAW_DIR` can override their location.
Database write helpers do not commit: callers must use `with db.get_connection():`.

## Regression tests

From the repository root:

```bash
cd python
uv run python -m unittest discover -s tests -v
```

Tests use synthetic Hansard fixtures, temporary databases, and mocked build/deploy commands.
They exercise replay, legacy adoption, rollback, bill matching and publication recovery;
they do not call Hansard, Gemini or Cloudflare.

## Supporting Modules

| File | Description |
|------|-------------|
| `db_sqlite.py` | Database connection and CRUD operations for SQLite |
| `hansard_api.py` | Client for fetching data from the Hansard API |
| `parliament_sitting.py` | Parsing and structuring of sitting data |
| `prompts.py` | Prompt templates for AI summary generation |
| `util.py` | Shared utility functions |
| `publication.py` | Fingerprint frontend inputs and record successful publication |
| `summary_jobs.py` | Deterministic summary inputs, provenance and read-only review |

## Manual changes
Below are the manual changes that were made post-ingestion.

### Changes in ministry names
- Before 8 July 2024, the Ministry of Digital Development and Information was known as the Ministry for Communications and Information.
- Before 25 July 2020, the Ministry of Sustainability and the Environment was known as the Ministry for the Environment and Water Resources.

Sections before the changes were re-categorised under the new ministry names after ingestion using an adhoc script.

### Errors in the Hansard
Note that this is just a list of errors that we have found so far, and it is very possible that there might be more that we are not aware of. Feel free to contact us or raise an issue if you identify more that need correcting!
- In the sitting on [14 October 2025](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=14-10-2025), Senior Minister of State for Finance Jeffrey Siow is mistakenly referred to as "Second Minister for Defence" (an appointment that did not exist at the time) by the Speaker of Parliament. As such, the [Finance (Income Taxes)](https://secondreading.app/bills/finance-income-taxes-bill-27d4c8bd) and [Corporate and Accounting Laws (Amendment) Bill](https://secondreading.app/bills/corporate-and-accounting-laws-amendment-bill-3af9d1cf) were categorised under MINDEF by the ingestion script, and needed to be manually re-categorised under MOF in the SQLite database.
- In the sitting on [3 March 2020](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=03-03-2020), the section on "Committee of Supply Reporting Progress" is mistakenly classified as a bill introduction (`sectionType: "BI"`) instead of an oral statement (`sectionType: "OS"`). This was fixed by manually updating the section type in the SQLite database.
- The following bills have inconsistencies between readings in the Hansard API. The bill's correct name was taken from the [AGC's website](https://sso.agc.gov.sg/Browse/Bills-Supp) and the relevant section in the database was manually updated.

    | Bill | First reading | Second reading | Issue |
    |-----------|--------------|--------------|--------------|
    | [Anti-Money Laundering and Other Matters Bill](https://secondreading.app/bills/anti-money-laundering-and-other-matters-bill-63c02e23) | [2 July 2024](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=02-07-2024) | [6 August 2024](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=06-08-2024) | First reading title: "Anti-***m***oney Laundering and Other Matters Bill" |
    | [Society of Saint Maur Incorporation (Amendment) Bill](https://secondreading.app/bills/society-of-saint-maur-incorporation-amendment-bill-7300d809) | [3 August 2023](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=03-08-2023) | [6 February 2024](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=06-02-2024) | Second reading title: "***The*** Society of Saint Maur Incorporation (Amendment) Bill" |
    | [Post-appeal Applications in Capital Cases Bill](https://secondreading.app/bills/post-appeal-applications-in-capital-cases-bill-27de4ec4) | [7 November 2022](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=07-11-2022) | [29 November 2022](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=29-11-2022) | Second reading title: "Post-***A***ppeal Applications in Capital Cases Bill" |
    | [Second Supplementary Supply (FY 2021) Bill](https://secondreading.app/bills/second-supplementary-supply-fy-2021-bill-14e100ec) | [28 February 2022](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=28-02-2022) | [11 March 2022](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=11-03-2022) | Second reading title: "Second Supplementary Supply (2021) Bill" (missing FY)|
    | [Economic Expansion Incentives (Relief from Income Tax) (Amendment) Bill](https://secondreading.app/bills/economic-expansion-incentives-relief-from-income-tax-amendment-bill-600db014) | [10 January 2022](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=10-01-2022) | [14 February 2022](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=14-02-2022) | Second reading title: "Economic Expansion Incentives (Relief ***F***rom Income Tax) (Amendment) Bill" |
    | [Statute Law Reform Bill](https://secondreading.app/bills/statute-law-reform-bill-7651a3be) | [3 November 2020](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=03-11-2020) | [5 January 2021](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=05-01-2021) | First reading title: "Statute Law Reform Bill" (statute misspelt as statue)
    | [Housing and Development (Amendment) Bill](https://secondreading.app/bills/housing-and-development-amendment-bill-7dd8b039) | [3 September 2020](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=03-09-2020) | [6 October 2020](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=06-10-2020) | Second reading title: "Housing and Development ***Board*** (Amendment) Bill" |
    | [Supplementary Supply (FY 2019) Bill](https://secondreading.app/bills/supplementary-supply-fy-2019-bill-8e3e7084) | [26 February 2020](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=26-02-2020) | [6 March 2020](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=06-03-2020) | Second reading title: "Supplementary Supply (FY2019) Bill" (no space between FY and 2019) |
    | [Goods and Services Tax (Amendment) Bill](https://secondreading.app/bills/goods-and-services-tax-amendment-bill-b7b098fe) | [7 October 2019](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=07-10-2019) | [4 November 2019](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=04-11-2019) | First reading title: "Good and Services Tax (Amendment) Bill" (missing s in Goods) |
    | [Supply Bill](https://secondreading.app/bills/supply-bill-a2c167b5) | [26 February 2019](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=26-02-2019) | [8 March 2019](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=08-03-2019) | First reading title: "Supply B***I***ll" |
    | [Tobacco (Control of Advertisements and Sale) (Amendment) Bill](https://secondreading.app/bills/tobacco-control-of-advertisements-and-sale-amendment-bill-7b226009) | [14 January 2019](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=14-01-2019) | [11 February 2019](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=11-02-2019) | First reading title: "Tobacco (Control of Advertisements and Sale (Amendment) Bill" (missing bracket after Sale)|
    | [Supplementary Supply (FY 2016) Bill](https://secondreading.app/bills/supplementary-supply-fy-2016-bill-7c9afa41) | [28 February 2017](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=28-02-2017) | [9 March 2017](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=09-03-2017) | Second reading title: "Supplementary Supply (FY2016) Bill" (no space between FY and 2016) |
    | [Income Tax (Amendment No. 3) Bill](https://secondreading.app/bills/income-tax-amendment-no-3-bill-3c6d575a) | [10 October 2016](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=10-10-2016) | [10 November 2016](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=10-11-2016) | First reading title: "Income Tax ***(Amendment) (No 3)*** Bill", Second reading title: "Income Tax (Amendment No 3) Bill" (missing period)
    | [Income Tax (Amendment No. 2) Bill](https://secondreading.app/bills/income-tax-amendment-no-2-bill-cd45a145) | [14 April 2016](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=14-04-2016) | [9 May 2016](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=09-05-2016) | First reading title: "Income Tax (Amendment No 2) Bill" (missing period) |
    | [Final Supply (FY 2015) Bill](https://secondreading.app/bills/final-supply-fy-2015-bill-267ef755) | [4 April 2016](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=04-04-2016) | [14 April 2016](https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=14-04-2016) | Second reading title: "Final Supply (FY2015) Bill" (no space between FY and 2015)| 
    
    
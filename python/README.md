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
1. Update the summaries for the MPs' contributions based on any new involvements from this sitting

For example, if the sitting on 27 February 2026 has just been added, we would run
```bash
uv run batch_process_sqlite.py 27-02-2026
uv run generate_summaries_sqlite.py --sittings 27-02-2026
uv run generate_summaries_sqlite.py --members
```

These scripts are described in more detail below.


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

Generates AI summaries for sitting sections and MP profiles using Gemini. The `--only-blank` flag generates summaries only for entries that don't have one yet.

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

## Supporting Modules

| File | Description |
|------|-------------|
| `db_sqlite.py` | Database connection and CRUD operations for SQLite |
| `hansard_api.py` | Client for fetching data from the Hansard API |
| `parliament_sitting.py` | Parsing and structuring of sitting data |
| `prompts.py` | Prompt templates for AI summary generation |
| `util.py` | Shared utility functions |

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
    
    
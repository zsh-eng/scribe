# Offline historical archive

This directory contains the historical report collection and transformation tools.
It does not write `data/parliament.db`, call a summary model, or supply files to Astro.
All archive data is under `historical/data/`, which Git and site publication ignore.

## Files

- `inventory.py`: official sitting-date discovery and comparison with the active database.
- `archive.py`: resumable source collection, offline transformation and aggregate counts.
- `legacy_hansard.py`: semantic, flat and Word-export HTML parsing.
- `modern_hansard.py`: structured reports with all source fields retained.
- `verify_archive.py` and `catalog.json`: full archive integrity checks and per-file hashes.
- `quality_review.py` and `QUALITY_REVIEW.md`: unresolved cases and source checks.
- `tests/`: official source fixtures and regression checks.
- `FORMAT_NOTES.md`: parsing rules, workarounds and known limits.
- `CAPACITY.md`: existing site counts and Cloudflare asset limits.

Run from the repository root. Use the existing Python environment; no additional library is required.

```bash
PYTHONPATH=python:historical python/.venv/bin/python -m unittest discover -s historical/tests -v
PYTHONPATH=python:historical python/.venv/bin/python historical/legacy_hansard.py 09-01-2012 historical/tests/fixtures/reports/09-01-2012.json.gz
```

The inspection command reads a saved report and prints metadata, attendance, sections,
source identities and warnings. It does not open the application database or use the network.

## Output contract

Each sitting has a raw compressed API response, a compressed normalized JSON record and
an independent state file. The date uses ISO format. The normalized record includes source
provenance, institution, sitting metadata, attendance, sections, speaker labels and a parsing
audit. Unknown fields remain null or have an explicit warning. Full normalized report text
is retained even when section boundaries cannot be established.

`data/index.jsonl` lists processing status by date. `data/summary.json` gives aggregate counts.
A report with retained text but unresolved structure is not proof of a correct section import.
Archive IDs are not approved public IDs for the application database.

## Verification

The retained four-format sample suite checks source hashes, complete non-attendance text
coverage and order, tables, appendix links, multiline titles, selected classifications and
speaker sets. Repeated transformations must preserve source IDs and text. The active pipeline
has a separate test suite and still rejects legacy reports.

## Completed collection (2026-09-08)

The official index contains 1,753 sitting dates from 1955-04-22 to 2026-08-05.
The active database contains 331 of these. All 1,422 missing reports were fetched and
transformed into 30,395 retained sections or blocks. This includes attendance and
procedural blocks; the active database's 19,868 filtered sections have a different scope.
Coverage means all dates returned by the official index, not records absent from that index.

The full archive verifier passed for all 1,422 reports. It checks file presence, source
hashes, dates, official institution labels, source text retention, structured source fields,
and section identities/order. The 32 historical tests and 27 active pipeline tests passed.
A `parsed` status means sections were produced, not that all classifications or names are
correct. See `QUALITY_REVIEW.md` for unresolved cases and the limits of these checks.

## Repeat the collection and checks

```bash
python/.venv/bin/python historical/inventory.py
python/.venv/bin/python historical/archive.py fetch
python/.venv/bin/python historical/archive.py transform
python/.venv/bin/python historical/archive.py summary
python/.venv/bin/python historical/verify_archive.py --write
python/.venv/bin/python historical/quality_review.py > historical/data/quality.json
python/.venv/bin/python historical/capacity_projection.py > historical/data/capacity.json
```

Inventory discovery reuses saved search pages; use `--refresh` to query them again.
Fetch reuses saved raw reports. Transform reads saved reports and replaces normalized output.
Use `--date YYYY-MM-DD` on archive commands to inspect or repeat selected dates.

The useful outputs are `data/normalized/*.json.gz`, with original JSON responses in
`data/raw/*.json.gz`, per-date state in `data/state/`, and discovery evidence in
`data/inventory/`. `data/verification.json` records the full integrity result. The tracked
`catalog.json` records hashes and counts for this completed collection.

Archive data is local and ignored by Git. Back up `historical/data/` separately if it must
survive deletion of this checkout. The catalog does not contain the transcripts.
Do not add these outputs to the site build. `CAPACITY.md` compares publication options
without building, importing, or deploying the archive.

# Offline historical archive

This directory contains the historical report collection and transformation tools.
It does not write `data/parliament.db`, call a summary model, or supply files to Astro.
All archive data is under `historical/data/`, which Git and site publication ignore.

## Files

- `inventory.py`: official sitting-date discovery and comparison with the active database.
- `archive.py`: resumable source collection, offline transformation and aggregate counts.
- `legacy_hansard.py`: semantic, flat and Word-export HTML parsing.
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

The complete collection, its exceptions and the final capacity comparison will be documented
after inventory discovery and processing finish. Do not add these outputs to the site build.

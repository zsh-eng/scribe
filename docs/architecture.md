# Architecture

The pipeline uses ordinary Python functions, SQLite transactions and a shell runner.
Each stage has one concrete output; no workflow engine or generic repository layer is
needed for the current single-machine daily job.

## Hansard path

`hansard_api.py` → `parliament_sitting.py` / `util.py` → `classification.py`
→ `batch_process_sqlite.py` / `db_sqlite.py` → SQLite.

- The API client owns HTTP retries and immutable raw-response snapshots.
- The parser and HTML/name helpers turn source data into sections and speakers.
  Classification contains pure ministry rules and has no network or database dependency.
- The batch script owns sequencing and one transaction per sitting. Database helpers
  own SQL and identity matching; they do not independently commit ingestion writes.
- `section_sources` connects Hansard IDs (including merged sections) to stable public
  IDs. Replays refresh transcripts and attendance while preserving curated metadata,
  bill links and summaries. Ambiguous identity changes fail the whole sitting.

The daily date window remains latest stored sitting + one day through today. Failed
fetches stop the run before later dates advance that watermark. An older source correction
requires an explicit date-range replay; there is no background re-fetch queue.

## Summaries

`summary_jobs.py` assembles ordered inputs and provenance; `prompts.py` owns prompt
text; `generate_summaries_sqlite.py` owns CLI selection and provider calls. A successful
summary and its attempt metadata commit together. Failed replacements retain prior text.

Input hashes, template hashes and model names support review. They never automatically
trigger regeneration. Default runs fill blanks; `--regenerate` explicitly replaces text.
See [commands and limits](../python/README.md#summary-provenance-and-review).

## Publication and site

`publication.py` fingerprints published data and frontend inputs. The daily shell script
builds and deploys only when needed, then records the successful fingerprint. Publication
can be retried independently with `--publish-only`.

Astro queries SQLite at build time through `src/lib/db.ts`, a stable re-export entry point.
`src/lib/queries/` groups SQL by sittings, members, bills, ministries, sections and overview;
`connection.ts` owns the connection and `types.ts` the query result shapes. Keep SQL in
these modules and presentation in pages/components. Preact islands handle browser interaction.

Budget data takes a separate, reviewed path: source PDFs → curated release JSON →
`src/lib/budgets.ts` validation/grouping → budget charts. Working CSVs are not the canonical
chart data. See [source provenance and update procedure](data-sources.md).

## AI-detection research

`export_pangram_speeches.py` → `run_pangram_bulk.py` / `import_pangram_dashboard.py`
→ `build_pangram_explorer.py`. An internal research pipeline: it reads SQLite but never
writes it, and its outputs stay in git-ignored `data/ai_detection/`. See the
[AI-detection guide](ai-detection.md).

## Evolving the project

Keep the Python directory flat while modules have clear jobs; current script paths are
also the operational CLI contract. Add a package only when additional entry points or
reuse justify it. Keep pure transformations independent of provider and storage code.

`python/schema.sql` is the schema source. Current additions use idempotent creation on
initialisation. A change to an existing column or constraint needs an explicit versioned
migration, a backup/rollback procedure and a test against an old database; editing a
`CREATE TABLE IF NOT EXISTS` definition will not migrate existing tables.

Consider a workflow scheduler when jobs need independent schedules, distributed workers
or frequent selective backfills. Consider dataframe tooling when tabular transformations
become more complex than the current small curated budget aggregation. Neither is required
by the present data volume. Preserve replay and transaction contracts if tooling changes.

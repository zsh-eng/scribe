# Operations

Run commands from the repository root unless otherwise stated.

## Daily automation (macOS)

The repository includes:
- `scripts/daily_pipeline.sh` (daily ingest + summaries + publication recovery)
- `launchd/com.secondreading.daily.plist` (LaunchAgent template scheduled for 13:00 Asia/Singapore)

### Script defaults
- Date window: latest ingested sitting date in DB + 1 day, through `today` (`DD-MM-YYYY`, Asia/Singapore)
  - If no sittings exist in DB yet, fallback window is `today-2` to `today`
- Pipeline order: atomic sitting imports -> sitting summaries (`--only-blank`) -> publication check
- Sitting dates are discovered from the official search index before import, deduplicated and processed oldest first. The index is paged by moving the upper date before the oldest returned date. Broad windows avoid the upstream HTTP 500 response for empty narrow searches; dates outside the requested range are excluded locally.
- An empty sitting table permits the fallback window. A missing or unreadable database stops the job with its error; it never silently moves the date window forward.
- Deploy policy: compare all published inputs with the last successful publication; deploy only on clean `main`
- HTTP or parsing failures stop ingestion before later dates can advance the latest-sitting date. The next run retries the same window; no separate retry queue is maintained.

### Script options
```bash
scripts/daily_pipeline.sh \
  [--start-date DD-MM-YYYY] \
  [--end-date DD-MM-YYYY] \
  [--lookback-days N] \
  [--skip-summaries] \
  [--skip-deploy] \
  [--force-deploy] \
  [--publish-only] \
  [--dry-run]
```
`--lookback-days` overrides the incremental default and uses a recent window of `today-N` to `today`.

### Reruns and recovery

Imports preserve existing public IDs, curated classifications and summaries. Each sitting
commits as one transaction. Ambiguous legacy duplicates or removed/split sections stop the
import for review; the daily job no longer deletes duplicates automatically.

Successful Hansard responses are retained under `data/raw/hansard/`. See
[offline replay and import rules](../python/README.md#reruns-and-offline-replay).

Publication fingerprints cover all frontend database tables, Astro files and curated budget releases (plus legacy CSV inputs).
The marker at `data/parliament.published.json` is written only after a successful build and
deploy. Missing markers trigger one publication. Failed or skipped deployments remain pending,
including when the latest sitting is already today. Keep the marker with its database backup.

To retry publication without re-fetching or making LLM calls:

```bash
scripts/daily_pipeline.sh --publish-only
```

`PARLIAMENT_DB_PATH` selects the database for both Python and Astro; the publication marker
is stored beside that database. Model changes do not trigger summary regeneration.
Raw responses and publication state are local, ignored data; back them up with the database.

### Setup
1. Sync dependencies and ensure deploy auth
   ```bash
   cd /Users/admin/scribe/python && uv sync
   cd /Users/admin/scribe/astro && bun install
   # If needed:
   # cd /Users/admin/scribe/astro && wrangler login
   ```

1. Create log directories
   ```bash
   mkdir -p /Users/admin/scribe/logs/pipeline
   mkdir -p /Users/admin/Library/Logs/second-reading
   ```

1. Install LaunchAgent
   ```bash
   mkdir -p /Users/admin/Library/LaunchAgents
   cp /Users/admin/scribe/launchd/com.secondreading.daily.plist \
      /Users/admin/Library/LaunchAgents/com.secondreading.daily.plist

   launchctl bootstrap gui/$(id -u) /Users/admin/Library/LaunchAgents/com.secondreading.daily.plist
   launchctl enable gui/$(id -u)/com.secondreading.daily
   ```

### Manual runs (these can change data or publish)
```bash
# Smoke tests
/Users/admin/scribe/scripts/daily_pipeline.sh --dry-run
/Users/admin/scribe/scripts/daily_pipeline.sh --dry-run --start-date 08-03-2026 --end-date 10-03-2026

# Functional run without deployment
/Users/admin/scribe/scripts/daily_pipeline.sh --start-date 08-03-2026 --end-date 10-03-2026 --skip-deploy

# Replay check (unchanged input preserves IDs and summaries)
/Users/admin/scribe/scripts/daily_pipeline.sh --start-date 08-03-2026 --end-date 10-03-2026 --skip-deploy

# Retry publication independently
/Users/admin/scribe/scripts/daily_pipeline.sh --publish-only

# launchd checks
plutil -lint /Users/admin/scribe/launchd/com.secondreading.daily.plist
launchctl kickstart -k gui/$(id -u)/com.secondreading.daily
launchctl print gui/$(id -u)/com.secondreading.daily
```


## Local verification

```bash
(cd python && uv run python -m unittest discover -s tests -v)
(cd astro && bun test && bun run build)
bash -n scripts/daily_pipeline.sh
```

Tests use temporary databases and fake providers. A full site build reads the selected
SQLite database and writes `astro/dist`; it does not ingest, generate summaries or deploy.

Before manual database repairs, take a SQLite backup using its backup API or `.backup`
command; copying a database while WAL writes are active is not a reliable backup.

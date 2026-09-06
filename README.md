# Second Reading
**Second Reading** is a web app that aims to make it easier for the public to understand what goes on during Singapore's Parliament sittings. It aggregates data from the [Hansard](https://sprs.parl.gov.sg/search/#/home), which contains the official reports of parliamentary debates, and organises the data from each session into a more user-friendly format.

NOTE: Second Reading only contains data for sittings from the 13th Parliament onwards (January 2016 - present).


## Features
### Cleaner interface for sitting reports
The official Hansard reports are text-only and rather difficult to read. Thus, each sitting's report is broken down into sections, organised by content type, and properly paginated where necessary, allowing the user to view the proceedings in a more digestible manner.

### Categorisation by content type
Broadly speaking, each sitting has three categories of content: questions, bills, and (other) motions. These are each collated into their own respective pages, and users can search through them.

### Categorisation by speaker
Each question, bill, and motion is tagged to their respective speakers. MPs have their own individual page which lists which of these they have spoken on. Users can then use the MP's page to find out more about their involvement in Parliament.

### Categorisation by ministry
Each question, bill, and motion is usually associated with a particular ministry. Thus, where possible, each piece of content is tagged to the ministry. This serves as a proxy for the topic of discussion, and users can thus use each ministry's page to find parliamentary discussions that are related to that ministry and/or topic.

### AI-generated summaries
These are provided for:
- Each section of a sitting
- Each MP's contributions in Parliament (based on their last 20 involvements)

## Tech Stack
### Frontend and Backend
Second Reading is written in [Astro](https://astro.build/) and uses SQLite for its database. For more details, please refer to the `astro/` directory. The summaries are generated using Gemini 3.7 Flash (`gemini-3.7-flash`).

### Data Processing
Data is fetched from the Hansard API, processed, and then inserted into the database using the Python scripts found in the `python/` directory. For more details, please refer to the [`README.md`](python/README.md) there.

Note that the script only works for Hansard data for sittings from ~2012 onwards, as earlier sittings have their data stored in a different format. Additionally, after ingesting the data, we performed several [manual modifications](python/README.md#manual-changes) to our database to correct some errors in the Hansard API.

## Setup
If you wish to replicate Second Reading independently, you can follow the steps below.
1.  **Clone the repository**
    ```bash
    git clone https://github.com/isaacyclai/second-reading.git
    cd second-reading
    ```

1.  **Install frontend dependencies**
    ```bash
    cd astro
    bun install
    ```

1. **Install Python dependencies**
    
    We use `uv` to manage dependencies.
    ```bash
    cd python
    uv sync
    ```

1. **Setup database**

    Then, run the following script from the `python/` directory. Dates should be in `DD-MM-YYYY` format.
    ```bash
    uv run batch_process_sqlite.py <start_date> <end_date>
    ```

1. **(Optional) Generate summaries**
    
    Add your Gemini API key in the `.env` file:
    ```bash
    GEMINI_API_KEY=your_gemini_api_key
    ```
    To generate summaries for sessions and members, run the following.
    ```bash
    uv run generate_summaries_sqlite.py --sittings <start_date> <end_date>
    uv run generate_summaries_sqlite.py --members
    ```

1.  **Run Development Server**

    From the `astro/` directory:
    ```bash
    bun run build
    bun run dev
    ```
    Open [http://localhost:4321](http://localhost:4321) to view the app.

## Daily Automation (macOS launchd + caffeinate)

The repository includes:
- `scripts/daily_pipeline.sh` (daily ingest + summaries + publication recovery)
- `launchd/com.secondreading.daily.plist` (LaunchAgent template scheduled for 13:00 Asia/Singapore)

### Script defaults
- Date window: latest ingested sitting date in DB + 1 day, through `today` (`DD-MM-YYYY`, Asia/Singapore)
  - If no sittings exist in DB yet, fallback window is `today-2` to `today`
- Pipeline order: atomic sitting imports -> sitting summaries (`--only-blank`) -> publication check
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
[offline replay and import rules](python/README.md#reruns-and-offline-replay).

Publication fingerprints cover all frontend database tables, Astro files and budget CSVs.
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

### Testing
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

## Acknowledgements
This project is inspired by the creators of [Telescope](https://telescope.gov.sg/) and [Pair Search](https://search.pair.gov.sg/).

The copyright to the Hansard is owned by the Singapore Government.

# Second Reading

Second Reading makes Singapore's parliamentary proceedings easier to browse, search and
understand. It groups Hansard transcripts by sitting, speaker, ministry and content type,
with AI summaries and curated budget charts. The current dataset starts with the
13th Parliament (January 2016).

## Start locally

Use Bun for the frontend and uv with Python 3.12+ for the pipeline. Run these commands
from the repository root; each subshell returns you there.

```bash
(cd astro && bun install --frozen-lockfile)
(cd python && uv sync --locked)

# Use an existing data/parliament.db, or import a small date range:
(cd python && uv run batch_process_sqlite.py 27-02-2026)

# Build once to create the Pagefind search index, then start development:
(cd astro && bun run build && bun run dev)
```

Open http://localhost:4321. `PARLIAMENT_DB_PATH` can select another database for both
Python and Astro. Summary generation is optional and requires `GEMINI_API_KEY` in
`python/.env`; see the [pipeline commands](python/README.md).

## Project map

| Path | Responsibility |
| --- | --- |
| `python/` | Fetch, parse, classify and store Hansard; generate and review summaries |
| `astro/` | Static Astro site, Preact interactions, Pagefind search and build-time SQL |
| `scripts/`, `launchd/` | Daily orchestration and publication recovery |
| `data/curated/` | Versioned, reviewed budget releases |
| `data/` (ignored remainder) | Local SQLite database, raw sources and publication marker |
| `docs/` | Architecture, operations and source reconciliation |

- [Architecture and change boundaries](docs/architecture.md)
- [Daily operations, recovery and verification](docs/operations.md)
- [Summary review, offline replay and historical manual corrections](python/README.md)
- [Budget sources and reconciliation](docs/data-sources.md)
- [Frontend development](astro/README.md)

The retired Next.js/Supabase implementation remains available in Git history before
this cleanup. Astro and SQLite are the active application and database.

## Acknowledgements

Inspired by [Telescope](https://telescope.gov.sg/) and [Pair Search](https://search.pair.gov.sg/).
Copyright to the Hansard belongs to the Singapore Government.

# Project Guidelines for Claude

## Package Manager

Use **bun** as the package manager for this project, not npm or yarn.

```bash
# Install dependencies
bun install

# Add a package
bun add <package>

# Add a dev dependency
bun add -d <package>

# Run scripts
bun run dev
bun run build
```

## Project Structure

- `python/` - Data pipeline scripts (uses uv/pip)
- `astro/` - Astro static site (uses bun)
- `src/` - Legacy Next.js app (being replaced)
- `data/` - SQLite database (`parliament.db`)

## Database

- SQLite database at `data/parliament.db`
- Python scripts use `db_sqlite.py` for data ingestion
- Astro uses `better-sqlite3` for build-time queries

### Bill Reading Status

The `bills` table only stores `first_reading_date` and `first_reading_session_id`. There are **no** `second_reading_date` or `third_reading_date` columns.

Bill reading status is derived from the `sections` table:
- **First Reading**: `section_type = 'BI'` — bill introduction, no debate. In Singapore Parliament, "Introduction" and "First Reading" are the same event (the Clerk reads the bill's short title). The `getBillStatus()` function no longer distinguishes them.
- **Second Reading**: `section_type = 'BP'` — debate on bill principles; this is the main transcript content

The `getBills()` and `getBill()` functions in `src/lib/db.ts` include a `hasSecondReading` boolean computed via an `EXISTS` subquery on sections. The `BillReadingStatus` component and `getBillStatus()` function in `src/lib/types.ts` use this field to determine display status.

The Hansard records all readings (including third reading when it occurs), but the data pipeline currently only tracks first reading (`BI`) and second reading (`BP`). Voting records are available as PDFs at `https://www.parliament.gov.sg/parliamentary-business/votes-and-proceedings` — it is technically possible to derive passing status from these, but they are not currently ingested.

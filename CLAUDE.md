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
- **First Reading**: `section_type = 'BI'` — bill introduction, no debate
- **Second Reading**: `section_type = 'BP'` — debate on bill principles; this is the main transcript content

The `getBills()` and `getBill()` functions in `src/lib/db.ts` include a `hasSecondReading` boolean computed via an `EXISTS` subquery on sections. The `BillTimeline` component and `getBillStatus()` function in `src/lib/types.ts` use this field to determine display status.

No third reading data is currently tracked in the database.

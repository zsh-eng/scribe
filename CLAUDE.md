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
